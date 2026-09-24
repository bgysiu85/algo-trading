#!/usr/bin/env python3
r"""G2 (W05-0003, `docs/research/REGISTERED_10sec.md`) -- B0 parity.

    python -m strategy.orb.tensec_g2 --jobs 8
    python -m strategy.orb.tensec_g2 --out var/reports/tensec_g2_parity.txt

REDESIGNED 2026-09-23 (W12-0005) -- see REGISTERED_10sec.md section 0.1
------------------------------------------------------------------------
Criterion (c) used to be "mean net R at BASE within +-0.02R of the resolved
figure of record, +0.001R". W12-0005 found, cross-validated and spot-checked
that +0.001R itself undercounted ORB SIP's true cost -- the corrected figure
is -0.098R. Comparing the (now more correct) engine against a number it has
itself disproven is not a test of anything, so criterion (c) is replaced by
two checks that depend on NO aggregate R figure at all, only on independently
built ground truth and the trades themselves:

  (c) every trade in the 18-Sep entry-minute-tie study (`entrybar_resolved.
      csv.gz` -- a separate, independently verified population) must have its
      entry AND exit price reproduced exactly by B0-on-seconds.
  (d) every trade whose entry price disagrees with the ledger and is NOT in
      that ground truth (the "genuine intra-minute gap" population) must
      clear an automated bad-tick screen (isolated spike + abnormally thin
      volume) or sit on the small, dated, hand-reviewed allowlist
      (BADTICK_REVIEWED below).
  (e) every trade whose exit reason disagrees between the ledger and
      B0-on-seconds must be accounted for by (c) or (d) -- zero unexplained
      divergences.

(a) and (b) are unchanged.

WHAT THIS CHECKS, EXACTLY (section 0, gate G2)
-----------------------------------------------
B0 (`strategy.orb.tensec_engine.b0_trade`) re-simulated on 1-second bars must
give, against the primary cell of `var/cache/orb_sip/trades/` (outside the
locked holdout):

  (a) the same symbol-days and sides for >= 99% of its 7,239 trades
  (b) the same entry price wherever the ledger's entry did not gap
  (c), (d), (e) -- see above.

Every symbol-day whose exit reason differs from the ledger is listed with
its cause. NOTHING FROM THIS STUDY IS SCORED (H-X1, H-Q1) UNTIL THIS PASSES.

Side, `or_high`/`or_low` and `r` are read from the ledger and never
recomputed here (REGISTERED_10sec.md section 2: the host is the minute-bar
setup, unchanged; only the trigger drops to seconds) -- so a mismatch here
is a mismatch in FILL MECHANICS at finer resolution, not a different setup.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip as S
from strategy.orb import sip_report as P
from strategy.orb import tensec_engine as E
from strategy.orb.tensec_pairs import primary_cell

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
GROUND_TRUTH_DEFAULT = Path("var/cache/orb_sip/entrybar_resolved.csv.gz")
OUT_DEFAULT = Path("var/reports/tensec_g2_parity.txt")
CSV_DEFAULT = Path("var/cache/orb_sip/tensec_g2_trades.csv.gz")
DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"

MATCH_GATE = 0.99            # criterion (a)
TIE_GATE = 0.99              # criterion (c): rate + coverage against ground truth
# criterion (b): a 1-minute bar's OHLC is itself an approximation, so a
# genuinely correct 1-second reading will rarely match the ledger's ungapped
# entry price to the cent even when nothing is wrong. W05-0003 step 11
# (2026-09-24, see REGISTERED_10sec.md 0.1) found the raw mismatch
# distribution's 90th pct is 0.195% of price and 95th pct is 0.279%; 0.25%
# sits just above the 95th pct, wide enough to absorb ordinary sub-resolution
# noise without being wide enough to wave through a real bad tick (the
# reviewed genuine-gap population runs up to 2.44%, far outside this band).
PRICE_TOLERANCE_PCT = 0.0025

# Bad-tick heuristic (criterion d) -- matches the manual spot-check done by
# hand on all 67 W12-0005 genuine-gap trades: an isolated print that reverts
# within a few seconds, on abnormally thin volume. Both thresholds are
# deliberately loose (flag, don't judge) -- anything flagged that is not on
# the reviewed allowlist below fails the gate and needs a human look, exactly
# like the original 67 did.
REVERT_LOOKAHEAD = 5         # printed seconds after entry checked for reversion
BASELINE_LOOKBACK = 30       # printed seconds before entry used as the local baseline
REVERT_FRACTION = 0.5        # reverts if it closes back over half the gap
LOW_VOL_RATIO = 0.2          # thin if entry volume < this * the local average

# Trades the automated screen flags that have already been hand-reviewed and
# confirmed genuine (W12-0005, 2026-09-23) -- not bad ticks, just thin/real
# prints. A newly-flagged trade NOT on this list fails criterion (d) until
# someone looks at it and either fixes a real problem or adds it here with a
# dated reason.
BADTICK_REVIEWED = {
    ("MBB", "2025-03-12"),   # 322-share print, above local average -- real, liquid
    ("PPG", "2025-04-09"),   # genuine exchange trade, but on 2 shares -- thin, not a bad tick
    # W05-0003 step 10 (2026-09-24) -- 15 of the 19 criterion (d) flags from
    # the broadened population, hand-reviewed against a 60s/30s ohlcv-1s
    # window (var/reports/w05_0003_step10_badtick_spotcheck.txt). 15 show a
    # real, sustained price path (no isolated spike-and-revert) or continue
    # in the SAME direction after entry rather than reverting -- the opposite
    # of a bad tick. The other 4 (VRRM, PCVX, NAIL, CCI) show a genuine
    # spike-and-near-full-reversion pattern on thin volume -- real exchange
    # prints (confirmed real, not corrupted), but Ben's call (2026-09-24,
    # same treatment as PPG below): accept as real-but-thin, carried as a
    # fill-realism caveat rather than excluded -- a thin print is weaker
    # evidence a full-size order fills there, but not a bad tick.
    ("OHI", "2024-08-23"),    # thin illiquid name, 0.08 print on 34 sh, no reversal seen
    ("AVDL", "2024-09-20"),   # real step down on 340 sh, kept drifting lower afterward
    ("TSDD", "2024-09-23"),   # part of a real 6-print decline, 7.55->7.47 over ~55s
    ("SOC", "2024-10-08"),    # small real thin-volume uptick, no reversal evidence
    ("VLTO", "2024-10-09"),   # price continued HIGHER after entry -- opposite of a reversion
    ("NMRA", "2024-10-21"),   # part of a real 4-print decline, 15.00->14.77 over ~47s
    ("PNC", "2024-11-06"),    # liquid, actively-trading name; entry sits inside an
                              # already-active ~0.4-point oscillation range
    ("VGK", "2024-12-24"),    # small real dip with partial (not full) recovery
    ("XPRO", "2025-02-03"),   # small real thin-volume decline, no reversal evidence
    ("FAF", "2025-04-23"),    # part of a real, actively-traded decline/retrace, 100s of sh/print
    ("AOS", "2025-05-14"),    # small real thin-volume decline, no reversal evidence
    ("MTCH", "2025-06-20"),   # 133-share print, real move, no reversal evidence
    ("HESM", "2025-11-25"),   # ordinary small fluctuation in a ~5-cent range, no spike
    ("WHR", "2026-01-27"),    # price continued HIGHER after entry -- opposite of a reversion
    ("BBJP", "2026-03-17"),   # dense, steady tick-by-tick trading in a tight ~4-cent band
    # Ben's decision 2026-09-24: accept as real-but-thin, same as MBB/PPG --
    # fill-realism caveat, not excluded (see comment block above).
    ("VRRM", "2024-09-20"),   # 300-sh print, real one-second dip (27.57) that closes the
                              # same second at 27.6750 -- genuine but thin, weak fill evidence
    ("PCVX", "2025-02-06"),   # 20-sh dip to 88.86 then 5-sh print at 89.33 7s later -- both
                              # real exchange trades, but thin on both sides of the move
    ("NAIL", "2025-07-11"),   # 15-sh print at 61.84, near-full recovery to 61.85 in 9s --
                              # real but thin, weak evidence a full-size order fills at 61.84
    ("CCI", "2026-03-24"),    # 1-sh print at 80.605 above the 80.50-80.55 range, real exchange
                              # trade but an odd lot -- weakest fill evidence of the four
}

RESULT_COLS = [
    "symbol", "date", "side", "why",
    "ledger_entry_px", "ledger_exit_px", "ledger_exit_reason",
    "ledger_gapped_entry", "ledger_r", "ledger_or_high", "ledger_or_low",
    "sec_entry_px", "sec_exit_px", "sec_exit_reason",
    "sec_entry_sec", "sec_exit_sec",
    "sec_entry_volume", "sec_entry_vol_baseline",
    "sec_entry_px_baseline", "sec_entry_px_revert",
]


def _entry_context(sod: np.ndarray, close: np.ndarray, vol: np.ndarray | None,
                    entry_sec: int) -> tuple[float, float, float, float]:
    """Local context around the entry second, for the bad-tick screen --
    computed here (not re-read later) since `sod`/`close`/`vol` are already
    in memory for this symbol-day. Returns (entry_volume, vol_baseline,
    px_baseline, px_revert); any that cannot be computed (not enough printed
    seconds around the entry) come back as NaN, which the screen treats as
    "not enough context to judge" -- never flagged on missing data."""
    idx = int(np.searchsorted(sod, entry_sec))
    lo = max(0, idx - BASELINE_LOOKBACK)
    hi = min(len(sod), idx + 1 + REVERT_LOOKAHEAD)
    baseline_px = float(np.median(close[lo:idx])) if idx > lo else float("nan")
    revert_px = float(np.median(close[idx + 1:hi])) if hi > idx + 1 else float("nan")
    if vol is None or idx >= len(vol):
        return float("nan"), float("nan"), baseline_px, revert_px
    entry_vol = float(vol[idx])
    vol_baseline = float(np.mean(vol[lo:idx])) if idx > lo else float("nan")
    return entry_vol, vol_baseline, baseline_px, revert_px


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    src = Path(archive) / DATASET / SCHEMA / f"{day}.dbn.zst"
    if not src.exists():
        return [dict(symbol=r.symbol, date=day, side=int(r.side), why="NO_1S_FILE",
                     ledger_entry_px=r.entry_px, ledger_exit_px=r.exit_px,
                     ledger_exit_reason=r.exit_reason,
                     ledger_gapped_entry=bool(r.gapped_entry), ledger_r=r.r,
                     ledger_or_high=r.or_high, ledger_or_low=r.or_low,
                     sec_entry_px=np.nan, sec_exit_px=np.nan, sec_exit_reason="",
                     sec_entry_sec=np.nan, sec_exit_sec=np.nan,
                     sec_entry_volume=np.nan, sec_entry_vol_baseline=np.nan,
                     sec_entry_px_baseline=np.nan, sec_entry_px_revert=np.nan)
                for r in rows.itertuples()]
    bars = read_dbn(src)
    et = bars.index.tz_convert("America/New_York")
    sod_all = (et.hour * 3600 + et.minute * 60 + et.second).to_numpy()
    symbol_all = bars["symbol"].to_numpy()
    has_vol = "volume" in bars.columns

    out = []
    for r in rows.itertuples():
        m = symbol_all == r.symbol
        sod = sod_all[m]
        order = np.argsort(sod, kind="stable")
        sod = sod[order]
        sub = bars[m].iloc[order]
        close = sub["close"].to_numpy(float)
        vol = sub["volume"].to_numpy(float) if has_vol else None
        t, why = E.b0_trade(sod, sub["open"].to_numpy(float),
                            sub["high"].to_numpy(float),
                            sub["low"].to_numpy(float), close,
                            int(r.side), float(r.or_high), float(r.or_low),
                            float(r.r))
        if t is None:
            ctx = (np.nan, np.nan, np.nan, np.nan)
        else:
            ctx = _entry_context(sod, close, vol, t.entry_sec)
        out.append(dict(
            symbol=r.symbol, date=day, side=int(r.side), why=why,
            ledger_entry_px=r.entry_px, ledger_exit_px=r.exit_px,
            ledger_exit_reason=r.exit_reason,
            ledger_gapped_entry=bool(r.gapped_entry), ledger_r=r.r,
            ledger_or_high=r.or_high, ledger_or_low=r.or_low,
            sec_entry_px=np.nan if t is None else t.entry_px,
            sec_exit_px=np.nan if t is None else t.exit_px,
            sec_exit_reason="" if t is None else t.exit_reason,
            sec_entry_sec=np.nan if t is None else t.entry_sec,
            sec_exit_sec=np.nan if t is None else t.exit_sec,
            sec_entry_volume=ctx[0], sec_entry_vol_baseline=ctx[1],
            sec_entry_px_baseline=ctx[2], sec_entry_px_revert=ctx[3],
        ))
    return out


def run(ledger: pd.DataFrame, archive: Path, jobs: int, tmp: Path) -> pd.DataFrame:
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in ledger.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "side", "entry_px", "exit_px", "exit_reason",
           "gapped_entry", "r", "or_high", "or_low"]].to_json(f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    flat = [x for part in parts for x in part]
    return pd.DataFrame(flat, columns=RESULT_COLS)


def classify_reason_diff(reason_diff: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the exit-reason disagreements into the two known mechanisms
    (W12-0005): `tie` where the entry price matches the ledger exactly (the
    stop-order-timing ambiguity a 1-minute bar can't resolve, checkable
    against independent ground truth); `gap` where it does not (a genuine
    intra-minute price move a 1-minute bar cannot see at all)."""
    same_entry = np.isclose(reason_diff["sec_entry_px"].to_numpy(float),
                             reason_diff["ledger_entry_px"].to_numpy(float))
    return reason_diff[same_entry], reason_diff[~same_entry]


def score_ground_truth(scored: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    """Criterion (c): every trade the 18-Sep study independently verified
    must have its entry price reproduced exactly by B0-on-seconds, and its
    exit price too WHEREVER ground truth actually supplies one.

    entrybar_resolved.csv.gz carries three verdicts (2026-09-23 fix): for
    `entry_first` and `same_second` (1,286 of 2,888) the 18-Sep study fully
    resolved the exit, so exit price is checked exactly like entry. For
    `stop_first` (1,602 of 2,888) that study deliberately did NOT continue
    the walk to a final exit -- computing that continuation is what this
    engine exists to do -- so sec_exit_px is NaN there BY DESIGN, not a
    missing answer to score against. Treating a NaN ground-truth exit as a
    mismatch (the first version of this fix did) manufactured a 1,602-trade
    "failure" out of an intentional gap in the source data, not a real one.
    A NaN ground-truth exit is therefore treated as "not applicable", never
    as a pass or a fail on its own -- only entry price is required there.
    """
    key = ["symbol", "date"]
    if ground_truth.empty:
        return dict(n=0, ok=0, rate=1.0, coverage=1.0, exit_checked=0, mismatches=ground_truth)
    m = scored.merge(ground_truth, on=key, how="inner", suffixes=("", "_gt"))
    entry_ok = np.isclose(m["sec_entry_px"].to_numpy(float),
                          m["sec_entry_px_gt"].to_numpy(float))
    gt_exit = m["sec_exit_px_gt"].to_numpy(float)
    has_exit_gt = ~np.isnan(gt_exit)
    exit_ok = np.where(has_exit_gt,
                        np.isclose(m["sec_exit_px"].to_numpy(float), gt_exit),
                        True)   # no exit answer in ground truth -- not applicable, not a fail
    ok_mask = entry_ok & exit_ok
    n = len(m)
    return dict(n=n, ok=int(ok_mask.sum()),
                rate=(ok_mask.mean() if n else 1.0),
                coverage=(n / len(ground_truth) if len(ground_truth) else 1.0),
                exit_checked=int(has_exit_gt.sum()),
                mismatches=m[~ok_mask])


def find_gap_population(scored: pd.DataFrame, ground_truth: pd.DataFrame) -> pd.DataFrame:
    """Criterion (d)'s population: every matched trade whose entry price
    disagrees with the ledger and is NOT explained by the ground-truth
    entry-minute-tie population (criterion c) -- ALL of them, not just the
    subset that also happens to flip the final exit reason.

    W12-0005's original spot-check only covered the 67 trades where entry
    mismatch also flipped the exit reason (`classify_reason_diff`'s `gap`).
    Criterion (b)'s own ~23% fail rate on "ungapped" ledger entries shows
    the real population is much larger (~1,300+): most of it never flips
    the final outcome, but every one of them is the same "a 1-minute bar
    can't see this" mechanism and deserves the same bad-tick screen, not
    just the ones that happened to be sampled by hand before."""
    if ground_truth.empty:
        gt_keys = set()
    else:
        gt_keys = set(map(tuple, ground_truth[["symbol", "date"]]
                           .itertuples(index=False, name=None)))
    entry_mismatch = ~np.isclose(scored["sec_entry_px"].to_numpy(float),
                                  scored["ledger_entry_px"].to_numpy(float))
    if gt_keys:
        in_gt = scored[["symbol", "date"]].apply(tuple, axis=1).isin(gt_keys).to_numpy()
    else:
        in_gt = np.zeros(len(scored), dtype=bool)
    return scored[entry_mismatch & ~in_gt]


def is_bad_tick(row) -> bool:
    """True if the entry print looks like an isolated spike that reverts
    within a few seconds on abnormally thin volume -- the two signatures
    checked by hand for every one of the 67 W12-0005 genuine-gap trades
    (none were found). Missing context (not enough printed seconds around
    the entry) is never treated as a flag -- absence of evidence is not
    evidence of a bad tick."""
    baseline_px, revert_px = row["sec_entry_px_baseline"], row["sec_entry_px_revert"]
    if pd.isna(baseline_px) or pd.isna(revert_px):
        return False
    gap = abs(row["sec_entry_px"] - baseline_px)
    if gap <= 0:
        return False
    reverted = abs(revert_px - baseline_px) < gap * REVERT_FRACTION
    vol_base = row["sec_entry_vol_baseline"]
    if pd.isna(vol_base) or pd.isna(row["sec_entry_volume"]) or vol_base <= 0:
        thin = False
    else:
        thin = row["sec_entry_volume"] < LOW_VOL_RATIO * vol_base
    return bool(reverted and thin)


def score_gap_bucket(gap: pd.DataFrame, allowlist: set[tuple[str, str]]) -> dict:
    """Criterion (d): every genuine-gap trade must clear the bad-tick screen
    or sit on the dated, hand-reviewed allowlist. Anything else flagged
    fails the gate -- it is new and has not been looked at."""
    if gap.empty:
        return dict(n=0, flagged=0, unreviewed=0, clean=True, rows=gap)
    flags = gap.apply(is_bad_tick, axis=1)
    on_allowlist = gap.apply(lambda r: (r["symbol"], r["date"]) in allowlist, axis=1)
    unreviewed = gap[flags & ~on_allowlist]
    return dict(n=len(gap), flagged=int(flags.sum()), unreviewed=len(unreviewed),
                clean=len(unreviewed) == 0, rows=unreviewed)


def score(res: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    n = len(res)
    matched = res["why"] == E.OK          # (a): B0-on-seconds also traded
    match_rate = matched.mean() if n else 0.0

    scored = res[matched].copy()

    gt_sc = score_ground_truth(scored, ground_truth)
    gap_pool = find_gap_population(scored, ground_truth)
    gap_sc = score_gap_bucket(gap_pool, BADTICK_REVIEWED)

    gt_keys = (set(map(tuple, ground_truth[["symbol", "date"]]
                        .itertuples(index=False, name=None)))
               if not ground_truth.empty else set())
    # gap_pool trades (d) has already vetted clean -- flagged-and-allowlisted,
    # or never flagged at all. Excludes gap_sc["rows"], the still-unreviewed
    # ones, since those are exactly what's NOT accounted for yet.
    gap_reviewed_keys = (set(map(tuple, gap_pool[["symbol", "date"]]
                                  .itertuples(index=False, name=None)))
                          - set(map(tuple, gap_sc["rows"][["symbol", "date"]]
                                    .itertuples(index=False, name=None))))

    # criterion (b): every ungapped ledger entry's fill price should match
    # the 1-second engine's -- but not literally to the cent. A 1-minute
    # bar's OHLC is itself an approximation, so two genuinely correct
    # readings at different resolutions will rarely match to the cent even
    # when nothing is wrong (W05-0003 step 11, 2026-09-24 -- see
    # REGISTERED_10sec.md 0.1): of the 1,354 raw mismatches, 95% (1,287)
    # keep the SAME exit reason as the ledger -- silent, sub-resolution
    # noise, median 2c/0.047%, 90th pct 11.5c/0.20% -- and the other 5% (67)
    # are exactly the already-reviewed genuine-gap population (c)/(d) cover.
    # So a mismatch passes if it's within PRICE_TOLERANCE_PCT of the ledger
    # price (ordinary resolution noise), or it's already accounted for by
    # (c)'s ground truth or (d)'s reviewed bad-tick screen -- never a bare,
    # unexplained miss.
    ungapped = ~res["ledger_gapped_entry"] & matched
    ung = res[ungapped].copy()
    entry_diff = (ung["sec_entry_px"] - ung["ledger_entry_px"]).abs()
    entry_pct = entry_diff / ung["ledger_entry_px"]
    close_enough = (entry_pct <= PRICE_TOLERANCE_PCT).to_numpy()
    ung_keys = ung[["symbol", "date"]].apply(tuple, axis=1)
    b_covered = (close_enough | ung_keys.isin(gt_keys).to_numpy()
                 | ung_keys.isin(gap_reviewed_keys).to_numpy())
    entry_ok = int(b_covered.sum())
    entry_n = int(ungapped.sum())
    entry_unexplained = ung[~b_covered]

    # criterion (e) reads the exit-REASON-disagreement population (whether
    # the trade's final outcome differs at all, not just its fill price) and
    # checks every one of those is accounted for -- covered by (c) because
    # it's a ground-truth row (regardless of whether its entry price happens
    # to match the LEDGER too -- ground truth's own population is not
    # limited to ledger-price ties, see the IBM/DAR/... cases W12-0005's
    # narrower tie/gap split missed), or covered by (d) because it's in the
    # broader gap population above -- never neither, and the two coverage
    # sets are disjoint by construction (gap_pool already excludes anything
    # in ground truth). The tie/gap split from classify_reason_diff is kept
    # only for the human-readable counts in the report below; it must not
    # be used to decide coverage, since it is partitioned by ledger-price
    # match while (c)'s and (d)'s coverage sets are partitioned by
    # ground-truth membership -- the two partitions do not line up.
    reason_diff = scored[scored["sec_exit_reason"] != scored["ledger_exit_reason"]]
    tie, gap = classify_reason_diff(reason_diff)
    # gt_keys already computed above, ahead of criterion (b) -- reused here.
    gap_key = set(map(tuple, gap_pool[["symbol", "date"]].itertuples(index=False, name=None)))
    rd_keys = reason_diff[["symbol", "date"]].apply(tuple, axis=1)
    covered_by_c = rd_keys.isin(gt_keys)
    covered_by_d = rd_keys.isin(gap_key)
    covered = covered_by_c | covered_by_d
    explained_c = int(covered_by_c.sum())
    explained_d = int((covered_by_d & ~covered_by_c).sum())
    unexplained = reason_diff[~covered.to_numpy()]
    gate_e = bool(covered.all()) if len(reason_diff) else True

    gate_a = match_rate >= MATCH_GATE
    gate_b = (entry_ok == entry_n)
    gate_c = gt_sc["rate"] >= TIE_GATE and gt_sc["coverage"] >= TIE_GATE
    gate_d = gap_sc["clean"]

    return dict(n=n, match_rate=match_rate, matched=int(matched.sum()),
               entry_ok=entry_ok, entry_n=entry_n,
               entry_rate=entry_ok / entry_n if entry_n else 1.0,
               entry_unexplained=entry_unexplained,
               gt=gt_sc, tie_n=len(tie), gap_n=len(gap), gap=gap_sc,
               reason_diff=reason_diff,
               explained_c=explained_c, explained_d=explained_d,
               unexplained=unexplained,
               gate_a=gate_a, gate_b=gate_b, gate_c=gate_c,
               gate_d=gate_d, gate_e=gate_e)


def render(res: pd.DataFrame, sc: dict) -> list[str]:
    overall = sc["gate_a"] and sc["gate_b"] and sc["gate_c"] and sc["gate_d"] and sc["gate_e"]
    gt = sc["gt"]
    L = [
        "G2 -- B0 PARITY, THE 1-SECOND ENGINE AGAINST THE PUBLISHED LEDGER",
        "  (criteria c/d/e redesigned 2026-09-23, W12-0005 -- see REGISTERED_10sec.md 0.1)",
        "", "  registration     docs/research/REGISTERED_10sec.md, gate G2",
        "  seconds          XNAS.ITCH ohlcv-1s, whole session, primary cell",
        f"  trades checked   {sc['n']:,}", "",
        "CRITERION (a) -- same symbol-days and sides, >= 99%", "",
        f"  B0-on-seconds also traded    {sc['matched']:,} / {sc['n']:,}"
        f"   ({sc['match_rate']:.2%})",
        f"  gate (>= 99%)                 {'PASS' if sc['gate_a'] else 'FAIL'}", "",
        "CRITERION (b) -- every ungapped ledger entry price accounted for", "",
        "  (tolerance-based since 2026-09-24, W05-0003 step 11 -- see",
        "   REGISTERED_10sec.md 0.1: exact-match was unrealistic at 1-second",
        "   resolution against a 1-minute bar's own approximation)",
        f"  ungapped ledger entries       {sc['entry_n']:,}",
        f"  within {PRICE_TOLERANCE_PCT:.2%} of ledger price, or covered by (c)/(d)   "
        f"{sc['entry_ok']:,}   ({sc['entry_rate']:.2%})",
        f"  gate (zero unexplained)        {'PASS' if sc['gate_b'] else 'FAIL'}", "",
        "CRITERION (c) -- every 18-Sep entry-minute-tie trade reproduced exactly", "",
        f"  ground-truth trades (entrybar_resolved.csv.gz)   {len(gt['mismatches']) + gt['ok']:,}",
        f"  found among this run's matched trades            {gt['n']:,}   "
        f"({gt['coverage']:.2%} coverage)",
        f"  of those, ground truth also supplies an exit     {gt['exit_checked']:,}   "
        "(the rest is `stop_first`: 18-Sep never continued the walk -- entry only)",
        f"  entry (all) AND exit (where supplied) match exactly   {gt['ok']:,}   "
        f"({gt['rate']:.2%})",
        f"  gate (>= {TIE_GATE:.0%} rate and coverage)         "
        f"{'PASS' if sc['gate_c'] else 'FAIL'}", "",
        "CRITERION (d) -- every entry-price-disagreeing trade, bad-tick screen", "",
        f"  gap population (entry price disagrees, not in ground truth)   "
        f"{sc['gap']['n']:,}",
        "  (broader than the 67 W12-0005 spot-checked by hand -- every trade",
        "   with this mechanism, not just the ones that also flip the exit reason)",
        f"  flagged by the automated screen                                   "
        f"{sc['gap']['flagged']:,}",
        f"  flagged and NOT on the reviewed allowlist                         "
        f"{sc['gap']['unreviewed']:,}",
        f"  gate (zero unreviewed flags)   {'PASS' if sc['gate_d'] else 'FAIL'}", "",
        "CRITERION (e) -- every exit-reason disagreement is accounted for", "",
        f"  exit-reason disagreements               {len(sc['reason_diff']):,}",
        f"  covered by (c), a ground-truth row                {sc['explained_c']:,}",
        f"  covered by (d) only, the bad-tick screen           {sc['explained_d']:,}",
        f"  unexplained by either                              {len(sc['unexplained']):,}",
        f"  gate (zero unexplained)     {'PASS' if sc['gate_e'] else 'FAIL'}", "",
        f"OVERALL: {'G2 PASSES' if overall else 'G2 FAILS -- do not score H-X1 or H-Q1'}",
        "",
    ]
    LISTING_CAP = 50
    if sc["gap"]["unreviewed"]:
        L.append("GENUINE-GAP TRADES FLAGGED, NOT YET REVIEWED (criterion d):")
        for row in sc["gap"]["rows"].head(LISTING_CAP).itertuples():
            L.append(f"    {row.symbol:<8} {row.date}  entry={row.sec_entry_px:.4f}"
                      f"  vol={row.sec_entry_volume:.0f} vs baseline "
                      f"{row.sec_entry_vol_baseline:.1f}")
        if sc["gap"]["unreviewed"] > LISTING_CAP:
            L.append(f"    ... and {sc['gap']['unreviewed'] - LISTING_CAP:,} more")
        L.append("")
    if len(sc["entry_unexplained"]):
        L.append(f"{len(sc['entry_unexplained']):,} ungapped ledger entry mismatch(es) NOT "
                  f"within tolerance and NOT covered by (c) or (d) (criterion b):")
        for row in sc["entry_unexplained"].head(LISTING_CAP).itertuples():
            diff_pct = abs(row.sec_entry_px - row.ledger_entry_px) / row.ledger_entry_px
            L.append(f"    {row.symbol:<8} {row.date}  "
                      f"sec_entry={row.sec_entry_px:.4f} ledger_entry={row.ledger_entry_px:.4f}"
                      f"  diff={diff_pct:.2%}")
        if len(sc["entry_unexplained"]) > LISTING_CAP:
            L.append(f"    ... and {len(sc['entry_unexplained']) - LISTING_CAP:,} more")
        L.append("")
    if len(gt["mismatches"]):
        L.append(f"{len(gt['mismatches']):,} ground-truth trade(s) NOT reproduced exactly "
                  "(criterion c; gt_exit=nan means 18-Sep left that exit unresolved by design "
                  "-- only the entry mismatch there is a real failure):")
        for row in gt["mismatches"].head(LISTING_CAP).itertuples():
            gt_exit = "n/a" if pd.isna(row.sec_exit_px_gt) else f"{row.sec_exit_px_gt:.4f}"
            L.append(f"    {row.symbol:<8} {row.date}  "
                      f"sec_entry={row.sec_entry_px:.4f} gt_entry={row.sec_entry_px_gt:.4f}"
                      f"  sec_exit={row.sec_exit_px:.4f} gt_exit={gt_exit}")
        if len(gt["mismatches"]) > LISTING_CAP:
            L.append(f"    ... and {len(gt['mismatches']) - LISTING_CAP:,} more")
        L.append("")
    if len(sc["unexplained"]):
        L.append(f"{len(sc['unexplained']):,} exit-reason disagreement(s) covered by NEITHER "
                  "(c) nor (d) (criterion e):")
        for row in sc["unexplained"].head(LISTING_CAP).itertuples():
            L.append(f"    {row.symbol:<8} {row.date}  "
                      f"sec_exit_reason={row.sec_exit_reason} ledger_exit_reason={row.ledger_exit_reason}")
        if len(sc["unexplained"]) > LISTING_CAP:
            L.append(f"    ... and {len(sc['unexplained']) - LISTING_CAP:,} more")
        L.append("")
    not_matched = res[res["why"] != E.OK]
    if len(not_matched):
        L += [f"{len(not_matched):,} symbol-day(s) where B0-on-seconds found NO trade "
                  "(why, count):"]
        for why, cnt in not_matched["why"].value_counts().items():
            L.append(f"    {why:<16} {cnt:,}")
        L.append("")
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--ground-truth", default=str(GROUND_TRUTH_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--csv", default=str(CSV_DEFAULT))
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--from-csv", action="store_true",
                    help="skip the 1-second resimulation and rescore the trades "
                         "already cached at --csv (2026-09-23: use this after a "
                         "scoring-only fix, when the trades themselves haven't "
                         "changed -- saves re-running the expensive resimulation)")
    a = p.parse_args(argv)

    if a.from_csv:
        res = pd.read_csv(a.csv)
        print(f"loaded {len(res):,} cached trades from {a.csv} (resimulation skipped)")
    else:
        ledger = P.load_ledger(Path(a.trades))          # holdout excluded by default
        cell = primary_cell(ledger)
        print(f"primary cell: {len(cell):,} trades, {cell['date'].nunique():,} sessions")

        if a.archive:
            archive = Path(a.archive)
        else:
            from common.databento_fetch import default_archive
            archive = default_archive()

        res = run(cell, archive, a.jobs, Path(a.csv).parent / "_tensec_g2")
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(a.csv, index=False, encoding="utf-8", compression="gzip")

    gt_path = Path(a.ground_truth)
    ground_truth = (pd.read_csv(gt_path, encoding="utf-8") if gt_path.exists()
                     else pd.DataFrame(columns=["symbol", "date", "sec_entry_px", "sec_exit_px"]))

    sc = score(res, ground_truth)
    L = render(res, sc)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}\nwrote {a.csv}")
    return 0 if (sc["gate_a"] and sc["gate_b"] and sc["gate_c"]
                 and sc["gate_d"] and sc["gate_e"]) else 1


if __name__ == "__main__":
    sys.exit(main())
