#!/usr/bin/env python3
r"""H-Q1 (W05-0003 step 7): G5 (positive control), then H-Q1 itself --
top-of-book imbalance kept/discarded on T1's triggers -- plus the section 4
fill check, run for the record.

    python -m strategy.orb.tensec_hq1 --jobs 8

docs/research/REGISTERED_10sec.md sections 5.2, 5.3, 4 and 7.

PRECONDITION: step 6 (G4) has run -- MBP-1 windows are on disk at
`<archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/<day>/<symbol>.dbn.zst` (board
W05-0003 subitem 6, Done 2026-09-28, 2,357 windows). Step 5 (H-X1) already
returned NOT ADOPTABLE on criteria computable without MBP-1 (subitem 5,
2026-09-24) -- section 7.1's retirement clause has already fired for the
sub-minute confirmation family regardless of anything in this module. H-Q1
is a SEPARATE hypothesis, scored on its own bar (section 7's "Plus, for
H-Q1" clause), unaffected by H-X1's verdict -- the parent item's 2026-09-24
Update says so explicitly. The section 4 fill check is completed here too,
for the study's own record, even though it cannot turn H-X1's already-failed
verdict into a pass (section 7.1).

ORDER OF OPERATIONS (section 10: "scoring H-Q1 after a failed positive
control" is explicitly listed as a way this run would be wrong)
------------------------------------------------------------------------
  1. G5 (section 5.3) -- MUST pass before section 5.2 is scored at all.
  2. Section 5.2 -- bucket table (KEPT/DISCARDED/FLAT/NO_BOOK), the shuffled-
     label null, the two denominators, composition (reported, never scored).
  3. Section 7, criteria 1-6, on T2's KEPT book (the "Plus, for H-Q1" bar).
  4. Section 4 -- the fill check, on T1's own entries. This affects H-X1's
     record, not H-Q1's: H-Q1 never re-prices T1's entry, it only decides
     whether to keep or discard the trade T1 already produced.

THE SIGNAL, EXACTLY (section 3.3)
------------------------------------
I(t) = the top-of-book imbalance, time-weighted over the TRIGGER BAR ITSELF
-- the same 10 seconds that decided the trigger -- not the 60-second window
`common.l2_features` was originally built for. `f1_quote_imbalance` takes
`window_s` as a parameter for exactly this reason: called here with
`window_s=10` and `t=` the trigger bar's END (`strategy.orb.tensec_g4.
bar_bounds`), it is the SAME half-open-at-t, time-weighted machinery, just a
different window length. Its own bucket rules (FLAT at exactly 0.0, NO_BOOK
when no valid quote stood anywhere in the bar) are section 3.3's NO_BOOK /
FLAT buckets exactly -- nothing is re-implemented, only signed and bucketed
on the sign: I_s = I for a long, -I for a short (section 3.3); I_s > 0 KEEP,
I_s < 0 DISCARD.

A NOTE ON SIGNING, BECAUSE THIS PROJECT HAS BEEN BITTEN BY A SIGN BEFORE
--------------------------------------------------------------------------
Section 5.3 asks whether "the mid moved the way I_s pointed". Read literally
against the RAW (unsigned) mid change, that question reverses itself on the
short half of the population: I_s = side * I, so testing "I_s > 0 predicts
raw mid-up" is really testing "side * I > 0 predicts mid-up", which for
shorts (side = -1) asks whether NEGATIVE raw imbalance predicts a mid
INCREASE -- backwards from what quote imbalance is supposed to mean, and
enough to drag a genuinely predictive signal down to a coin flip once longs
and shorts are pooled. The registration's own confident prediction (section
9: "G5: PASSES, high confidence") only holds if "the way I_s pointed" is
read in the TRADE's own frame -- I_s > 0 predicts the trade's FAVOURABLE
move (up for a long, down for a short). Algebraically that is
`side * (m1 - m0) > 0`, and since `I_s = side * I`, comparing `I_s` against
`side * (m1 - m0)` is identical to comparing raw `I` against the raw mid
change (`side` cancels) -- one honest, side-invariant test, not two tests
that quietly disagree about what "pointed" means. See `g5_positive_control`.

Reads:
  var/cache/orb_sip/tensec_hx1_trades.csv.gz          T1 trigger list (step 5)
  <archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/...       MBP-1 windows (step 6)

Writes:
  var/reports/tensec_hq1_RESULT.txt                    this module's report
  var/cache/orb_sip/tensec_hq1_trades.csv.gz           per-trade signal + bucket
"""
from __future__ import annotations

import argparse
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import l2_features as L2
from common.breadth import RESAMPLES, SEED, cluster_bootstrap
from strategy.orb import sip_context as C
from strategy.orb import sip_report as P
from strategy.orb.tensec_g4 import TRADES_DEFAULT, bar_bounds, load_trades, plan_edge, windows

CSV_DEFAULT = Path("var/cache/orb_sip/tensec_hq1_trades.csv.gz")
OUT_DEFAULT = Path("var/reports/tensec_hq1_RESULT.txt")
LEVEL = "BASE"

G5_LOOKAHEAD_S = 10
G5_ALPHA = 0.01
NO_BOOK_WARN_PCT = 5.0        # section 3.3
HOLDOUT_START = "2026-05-01"
DROPS = (1, 3, 5)
MIN_R_PER_TRADE = 0.05        # section 7 criterion 3, same bar as H-X1
MIN_TRADES = 100              # section 7 criterion 4

KEPT, DISCARDED, FLAT, NO_BOOK = "KEPT", "DISCARDED", "FLAT", "NO_BOOK"
BUCKETS = (KEPT, DISCARDED, FLAT, NO_BOOK)

# section 5.2.4 composition -- same edges sip_volume.composition uses, so a
# reader who has seen that study's "when" buckets does not have to learn a
# second convention for the same thing.
_WHEN_EDGES = [569, 575, 580, 600, 660, 780, 960]
_WHEN_NAMES = ["<=575", "576-580", "581-600", "601-660", "661-780", "781+"]


# --------------------------------------------------------------------------
# reading the MBP-1 archive
# --------------------------------------------------------------------------

class Windows:
    """Cache one G4 window file per (symbol, day). One T1 trigger per
    symbol-day by construction (tensec_engine: "at most one trade"), so this
    buys nothing over reading directly -- kept only so this module's shape
    matches `Claude outputs/w02_0013_l2_screen.py`'s own `Windows`, the
    precedent this module's G5 is deliberately built to resemble."""

    def __init__(self, archive: Path):
        self.root = archive / "g4_10sec" / "XNAS.ITCH" / "mbp-1" / "windows"
        self._cache: dict[tuple, pd.DataFrame | None] = {}

    def get(self, symbol: str, day: str) -> pd.DataFrame | None:
        k = (symbol, day)
        if k in self._cache:
            return self._cache[k]
        p = self.root / day / f"{symbol}.dbn.zst"
        if not p.exists():
            self._cache[k] = None
            return None
        from common.dbn_io import read_dbn
        try:
            df = read_dbn(p)
        except Exception as e:                                   # noqa: BLE001
            print(f"  ! unreadable {p}: {type(e).__name__}: {e}", flush=True)
            df = None
        self._cache[k] = df
        return df


def in_window_population(df: pd.DataFrame, edge: date, holdout_start: date) -> pd.DataFrame:
    """Exactly the population `tensec_g4.windows()` pulled a window for --
    derived by taking G4's own (symbol, day) keys and joining back to the
    full trade row, rather than re-deriving the OK / edge / holdout filter a
    second time and risking the two falling out of step (PROGRAM_INDEX: the
    MC5 four-minute window shift was exactly this kind of duplicated-filter
    drift)."""
    ws = windows(df, edge, holdout_start)
    keys = pd.DataFrame({"symbol": [w.symbol for w in ws], "date": [w.day for w in ws]})
    return df.merge(keys, on=["symbol", "date"], how="inner")


# --------------------------------------------------------------------------
# exact one-sided binomial (no scipy in this environment)
# --------------------------------------------------------------------------

def log_binom_sf(k: int, n: int) -> float:
    """log P(X >= k) for X ~ Binomial(n, 0.5), exact, by direct log-space
    summation. Matches `Claude outputs/w02_0013_l2_screen.py`'s own
    `log_binom_sf` (same reasoning: n is at most a few thousand here, so this
    is fast enough and exact -- no normal approximation)."""
    if k <= 0:
        return 0.0
    if k > n:
        return float("-inf")
    logs = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) - n * math.log(2)
            for i in range(k, n + 1)]
    m = max(logs)
    return m + math.log(sum(math.exp(x - m) for x in logs))


# --------------------------------------------------------------------------
# G5 -- the positive control (section 5.3)
# --------------------------------------------------------------------------

def g5_positive_control(pop: pd.DataFrame, wins: Windows) -> dict:
    """At each T1 trigger's bar END t: m0 = the Nasdaq mid strictly before t
    (the same information `f1_quote_imbalance`'s own window is allowed to
    read -- half-open at t), m1 = the mid 10 seconds later. Among triggers
    with a real move in the trade's own frame (`side * (m1 - m0) != 0`) and
    a scorable signal (not FLAT, not NO_BOOK), I_s's sign must call the
    trade's favourable direction right more than half the time, one-sided
    exact binomial p < 0.01. See the module docstring for why this is read
    in the trade's frame rather than against the raw mid change."""
    right = wrong = 0
    skipped_no_window = skipped_no_book = skipped_flat_mid = skipped_flat_sig = 0
    for r in pop.itertuples():
        df = wins.get(r.symbol, r.date)
        if df is None or df.empty:
            skipped_no_window += 1
            continue
        _, t = bar_bounds(r.date, r.t1_trigger_sec)
        now = L2.as_of(df, t, strict=True)
        later = L2.as_of(df, t + timedelta(seconds=G5_LOOKAHEAD_S))
        if not L2._valid_quote(now) or not L2._valid_quote(later):
            skipped_no_book += 1
            continue
        m0 = (float(now["bid_px_00"]) + float(now["ask_px_00"])) / 2.0
        m1 = (float(later["bid_px_00"]) + float(later["ask_px_00"])) / 2.0
        signed_move = int(r.side) * (m1 - m0)
        if signed_move == 0:
            skipped_flat_mid += 1
            continue
        f1 = L2.f1_quote_imbalance(df, t, window_s=10)
        if f1.value is None or f1.bucket == "FLAT":
            skipped_flat_sig += 1
            continue
        i_s = f1.value if r.side == 1 else -f1.value
        called_favorable = i_s > 0
        moved_favorable = signed_move > 0
        if called_favorable == moved_favorable:
            right += 1
        else:
            wrong += 1
    n = right + wrong
    share = right / n if n else float("nan")
    p = math.exp(log_binom_sf(right, n)) if n else float("nan")
    return {"right": right, "wrong": wrong, "n": n, "share": share, "p": p,
            "passes": bool(n and share > 0.5 and p < G5_ALPHA),
            "skipped_no_window": skipped_no_window, "skipped_no_book": skipped_no_book,
            "skipped_flat_mid": skipped_flat_mid, "skipped_flat_sig": skipped_flat_sig}


# --------------------------------------------------------------------------
# the signal itself, and the bucket assignment
# --------------------------------------------------------------------------

def add_signal(pop: pd.DataFrame, wins: Windows) -> pd.DataFrame:
    """One row per in-window T1 trade: I_s, its bucket, and (for the
    composition and fill-check reads) the spread at the trigger. Never reads
    anything at or after t (`f1_quote_imbalance`'s own half-open window)."""
    out = pop.copy()
    i_s = np.full(len(out), np.nan)
    bucket = np.full(len(out), "", dtype=object)
    spread_dollars = np.full(len(out), np.nan)
    n_no_window = 0
    for pos, r in enumerate(out.itertuples()):
        df = wins.get(r.symbol, r.date)
        if df is None or df.empty:
            bucket[pos] = NO_BOOK
            n_no_window += 1
            continue
        _, t = bar_bounds(r.date, r.t1_trigger_sec)
        f1 = L2.f1_quote_imbalance(df, t, window_s=10)
        now = L2.as_of(df, t, strict=True)
        if L2._valid_quote(now):
            spread_dollars[pos] = float(now["ask_px_00"]) - float(now["bid_px_00"])
        if f1.bucket == "NO_BOOK":
            bucket[pos] = NO_BOOK
            continue
        val = f1.value if r.side == 1 else -f1.value
        i_s[pos] = val
        if f1.bucket == "FLAT" or val == 0:
            bucket[pos] = FLAT
        elif val > 0:
            bucket[pos] = KEPT
        else:
            bucket[pos] = DISCARDED
    out["i_s"] = i_s
    out["bucket"] = bucket
    out["spread_dollars"] = spread_dollars
    if n_no_window:
        print(f"  {n_no_window:,} of {len(out):,} T1 triggers have no G4 window on disk "
              "(NO_BOOK)", flush=True)

    net = pd.DataFrame({"entry_px": out["t1_entry_px"], "exit_px": out["t1_exit_px"],
                        "exit_reason": out["t1_exit_reason"], "side": out["side"],
                        "r": out["r"]})
    net = P.add_net(net)
    out["R_BASE"] = net[f"R_{LEVEL}"].to_numpy()
    out["gross_R"] = net["gross_R"].to_numpy()
    return out


# --------------------------------------------------------------------------
# section 5.2.1 -- the bucket table
# --------------------------------------------------------------------------

def drop_top(totals_by_symbol: dict[str, float], n: int) -> float:
    ranked = sorted(totals_by_symbol.values(), reverse=True)
    return float(sum(ranked[n:]))


def bucket_stats(d: pd.DataFrame) -> dict:
    n = len(d)
    if n == 0:
        return dict(n=0, mean_net=float("nan"), gross=float("nan"), total=0.0,
                   drop5=0.0, win_rate=float("nan"), boot_p=float("nan"))
    by_sym = d.groupby("symbol")["R_BASE"].apply(list).to_dict()
    tot = {k: float(sum(v)) for k, v in by_sym.items()}
    boot = cluster_bootstrap(by_sym, RESAMPLES, SEED)
    boot_p = float(np.mean(np.asarray(boot["totals"]) > 0))
    return dict(n=n, mean_net=float(d["R_BASE"].mean()),
               gross=float(d["gross_R"].sum()), total=float(d["R_BASE"].sum()),
               drop5=drop_top(tot, 5), win_rate=float((d["R_BASE"] > 0).mean()),
               boot_p=boot_p)


def bucket_table(d: pd.DataFrame) -> dict[str, dict]:
    return {b: bucket_stats(d[d["bucket"] == b]) for b in BUCKETS}


# --------------------------------------------------------------------------
# section 5.2.2 -- the shuffled-label null
# --------------------------------------------------------------------------

def shuffled_kept_null(d: pd.DataFrame, draws: int = RESAMPLES, seed: int = SEED) -> dict:
    """KEPT/DISCARDED labels dealt to the same trades at random, proportion
    preserved -- FLAT and NO_BOOK trades never enter this population (they
    are not part of the keep/discard rule at all). Mirrors
    `strategy.orb.sip_volume.shuffled_label_null` (draws over a boolean
    `keep` mask, `strategy.orb.sip_context._mean_and_drop5` underneath) but
    generic rather than hard-wired to that module's CONFIRMED/WEAK labels."""
    t = d[d["bucket"].isin([KEPT, DISCARDED])]
    if t.empty:
        return dict(draws=draws, obs_mean=float("nan"), obs_drop5=float("nan"),
                   mean_p95=float("nan"), drop5_p95=float("nan"),
                   mean_beats=False, drop5_beats=False, n_kept=0, n_discarded=0)
    syms, si = np.unique(t["symbol"].to_numpy(), return_inverse=True)
    r = t["R_BASE"].to_numpy(float)
    keep = (t["bucket"].to_numpy() == KEPT)
    n_sym = len(syms)
    obs_mean, obs_drop5 = C._mean_and_drop5(si, r, keep, n_sym)
    rng = np.random.default_rng(seed)
    perm = keep.copy()
    means = np.empty(draws)
    drops = np.empty(draws)
    for i in range(draws):
        rng.shuffle(perm)
        means[i], drops[i] = C._mean_and_drop5(si, r, perm, n_sym)
    return {"draws": draws, "obs_mean": obs_mean, "obs_drop5": obs_drop5,
            "mean_p95": float(np.nanpercentile(means, 95)),
            "drop5_p95": float(np.nanpercentile(drops, 95)),
            "mean_beats": bool(obs_mean > np.nanpercentile(means, 95)),
            "drop5_beats": bool(obs_drop5 > np.nanpercentile(drops, 95)),
            "n_kept": int(keep.sum()), "n_discarded": int((~keep).sum())}


# --------------------------------------------------------------------------
# section 5.2.3 -- the two denominators
# --------------------------------------------------------------------------

def two_denominators(d: pd.DataFrame) -> dict:
    t = d[d["bucket"].isin([KEPT, DISCARDED])]
    kept = t[t["bucket"] == KEPT]["R_BASE"]
    disc = t[t["bucket"] == DISCARDED]["R_BASE"]
    n_pop = len(t)
    per_trade_kept = float(kept.mean()) if len(kept) else float("nan")
    per_trade_disc = float(disc.mean()) if len(disc) else float("nan")
    per_trade_delta = per_trade_kept - per_trade_disc
    per_symday_kept = float(kept.sum() / n_pop) if n_pop else float("nan")
    per_symday_disc = float(disc.sum() / n_pop) if n_pop else float("nan")
    per_symday_delta = per_symday_kept - per_symday_disc
    sign_agree = (np.sign(per_trade_delta) == np.sign(per_symday_delta)) or (
        per_trade_delta == 0 and per_symday_delta == 0)
    return dict(per_trade_kept=per_trade_kept, per_trade_disc=per_trade_disc,
               per_trade_delta=per_trade_delta, per_symday_kept=per_symday_kept,
               per_symday_disc=per_symday_disc, per_symday_delta=per_symday_delta,
               sign_agree=bool(sign_agree))


# --------------------------------------------------------------------------
# section 5.2.4 -- composition, reported, never scored
# --------------------------------------------------------------------------

def composition(d: pd.DataFrame) -> dict:
    t = d[d["bucket"].isin([KEPT, DISCARDED])].copy()
    out = {"n": len(t)}
    if t.empty:
        return out
    t["entry_min"] = t["t1_trigger_sec"] // 60
    t["when"] = pd.cut(t["entry_min"], bins=_WHEN_EDGES, labels=_WHEN_NAMES)
    out["by_when"] = (t.groupby("when", observed=True)["bucket"]
                      .apply(lambda s: float((s == KEPT).mean())).to_dict())
    out["by_side"] = (t.groupby("side")["bucket"]
                      .apply(lambda s: float((s == KEPT).mean())).to_dict())
    ticks = np.round(t["spread_dollars"].to_numpy(float) / 0.01)
    t["tick_bucket"] = np.where(np.isnan(ticks), "n/a",
                                np.where(ticks <= 1, "1-tick", "2+ ticks"))
    out["by_spread"] = (t.groupby("tick_bucket")["bucket"]
                        .apply(lambda s: float((s == KEPT).mean())).to_dict())
    out["by_venue"] = ("NOT COMPUTED -- this codebase has no per-symbol listing-"
                       "venue table (section 7.2 item 2's NYSE/Nasdaq split was "
                       "read by hand for ORB's five biggest carriers, not built "
                       "as reusable infrastructure). Would need a one-time "
                       "exchange-listing pull before this split can be reported.")
    return out


# --------------------------------------------------------------------------
# section 7, criteria 1-6, on T2's KEPT book
# --------------------------------------------------------------------------

def section7(d: pd.DataFrame) -> dict:
    kept = d[d["bucket"] == KEPT]
    n = len(kept)
    if n == 0:
        return dict(n=0, drop3=0.0, drop5=0.0, boot_p=0.0, mean_r=float("nan"),
                   half1=0.0, half2=0.0, long_r=0.0, short_r=0.0,
                   crit1=False, crit2=False, crit3=False, crit4=False,
                   crit5=False, crit6=False, passes=False)
    by_sym = kept.groupby("symbol")["R_BASE"].apply(list).to_dict()
    tot = {k: float(sum(v)) for k, v in by_sym.items()}
    drop3, drop5 = drop_top(tot, 3), drop_top(tot, 5)
    boot = cluster_bootstrap(by_sym, RESAMPLES, SEED)
    boot_p = float(np.mean(np.asarray(boot["totals"]) > 0))
    mean_r = float(kept["R_BASE"].mean())
    split_date = kept["date"].sort_values().iloc[n // 2]
    half1 = float(kept[kept["date"] < split_date]["R_BASE"].sum())
    half2 = float(kept[kept["date"] >= split_date]["R_BASE"].sum())
    long_r = float(kept[kept["side"] == 1]["R_BASE"].sum())
    short_r = float(kept[kept["side"] == -1]["R_BASE"].sum())
    crit1 = drop3 > 0 and drop5 > 0
    crit2 = boot_p >= 0.95
    crit3 = mean_r >= MIN_R_PER_TRADE
    crit4 = n >= MIN_TRADES
    crit5 = half1 > 0 and half2 > 0
    crit6 = long_r > 0 and short_r > 0
    return dict(n=n, drop3=drop3, drop5=drop5, boot_p=boot_p, mean_r=mean_r,
               half1=half1, half2=half2, long_r=long_r, short_r=short_r,
               crit1=crit1, crit2=crit2, crit3=crit3, crit4=crit4,
               crit5=crit5, crit6=crit6,
               passes=bool(crit1 and crit2 and crit3 and crit4 and crit5 and crit6))


# --------------------------------------------------------------------------
# section 4 -- the fill check, on T1's own entries
# --------------------------------------------------------------------------

def fill_check(pop: pd.DataFrame, wins: Windows) -> dict:
    """Each T1 entry re-priced at the Nasdaq ask (long) or bid (short)
    standing at the fill instant (`t1_entry_sec`, in ET -> UTC, same day),
    no added slippage, against the modelled fill (`t1_entry_px`). `diff =
    side * (quote_price - modelled_entry)`: positive means the quote-based
    fill was WORSE than modelled (paid more on a long, received less on a
    short) -- `side` again cancels the long/short asymmetry so one pooled
    median answers the question for both. A pass is suspended if the MEDIAN
    diff is worse than modelled (section 4)."""
    et = ZoneInfo("America/New_York")
    utc = ZoneInfo("UTC")
    diffs = []
    n_no_book = n_no_window = 0
    for r in pop.itertuples():
        df = wins.get(r.symbol, r.date)
        if df is None or df.empty:
            n_no_window += 1
            continue
        d = date.fromisoformat(r.date)
        fill_t = (datetime(d.year, d.month, d.day, tzinfo=et)
                  + timedelta(seconds=int(r.t1_entry_sec))).astimezone(utc)
        q = L2.as_of(df, fill_t)
        if not L2._valid_quote(q):
            n_no_book += 1
            continue
        quote_px = float(q["ask_px_00"]) if r.side == 1 else float(q["bid_px_00"])
        diffs.append(int(r.side) * (quote_px - float(r.t1_entry_px)))
    n = len(diffs)
    median_diff = float(np.median(diffs)) if n else float("nan")
    return {"n": n, "n_no_book": n_no_book, "n_no_window": n_no_window,
            "median_diff": median_diff,
            "understated": bool(n and median_diff > 0)}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def render(g5: dict, bt: dict, null: dict, denom: dict, comp: dict,
          s7: dict, fc: dict, n_pop: int, n_no_book_share: float) -> list[str]:
    L = []
    a = L.append
    a("H-Q1 (top-of-book imbalance kept/discarded) -- W05-0003 step 7")
    a("docs/research/REGISTERED_10sec.md sections 5.2, 5.3, 4 and 7 -- "
      "H-X1 (step 5) already NOT ADOPTABLE; H-Q1 is scored separately")
    a("=" * 78)
    a(f"population: {n_pop:,} T1 triggers inside the MBP-1 in-sample window (section 6.1)")
    if n_no_book_share > NO_BOOK_WARN_PCT:
        a(f"  *** NO_BOOK is {n_no_book_share:.1f}% of the population -- above the "
          f"{NO_BOOK_WARN_PCT:.0f}% flag in section 3.3 ***")
    a("")
    a("-- G5, section 5.3: positive control (must PASS before section 5.2 is scored) --")
    a(f"  right {g5['right']:,}  wrong {g5['wrong']:,}  n {g5['n']:,}  "
      f"share {g5['share']*100:.1f}%  one-sided binomial p {g5['p']:.2e}")
    a(f"  skipped: no window {g5['skipped_no_window']:,}  no book {g5['skipped_no_book']:,}  "
      f"flat mid {g5['skipped_flat_mid']:,}  flat/no signal {g5['skipped_flat_sig']:,}")
    a(f"  G5: {'PASSES' if g5['passes'] else 'FAILS'} (needs share > 50% and p < {G5_ALPHA})")
    a("")
    if not g5["passes"]:
        a("*** G5 FAILED: section 5.3/10 says section 5.2 (H-Q1 itself) is NOT scored below. ***")
        a("  Section 7.1's retirement clause fires for top-of-book imbalance as an entry")
        a("  selector on this project: no threshold on |I|, no snapshot-instead-of-time-")
        a("  weighted, no deeper book (MBP-10), no longer window, no second venue.")
        a("")
        a("=" * 78)
        a("VERDICT: H-Q1 NOT SCORED (G5 failed).")
        _append_fill_check(L, fc)
        return L
    a("-- section 5.2.1: bucket table (BASE friction) --")
    a(f"  {'bucket':<12}{'trades':>8}{'mean net R':>12}{'gross R':>12}{'total R':>12}"
      f"{'drop-top-5':>12}{'win rate':>10}{'boot P>0':>10}")
    for b in BUCKETS:
        s = bt[b]
        if s["n"]:
            a(f"  {b:<12}{s['n']:>8,}{s['mean_net']:>+12.4f}{s['gross']:>+12.2f}"
              f"{s['total']:>+12.2f}{s['drop5']:>+12.2f}{s['win_rate']*100:>9.1f}%"
              f"{s['boot_p']:>10.3f}")
        else:
            a(f"  {b:<12}{0:>8,}")
    a("")
    a("-- section 5.2.2: shuffled-label null (2,000 draws, seed 20260916) --")
    a(f"  n kept {null['n_kept']:,}  n discarded {null['n_discarded']:,}")
    a(f"  KEPT mean R {null['obs_mean']:+.4f}  null 95th pct {null['mean_p95']:+.4f}  "
      f"{'BEATS' if null['mean_beats'] else 'DOES NOT BEAT'}")
    a(f"  KEPT drop-top-5 {null['obs_drop5']:+.2f}  null 95th pct {null['drop5_p95']:+.2f}  "
      f"{'BEATS' if null['drop5_beats'] else 'DOES NOT BEAT'}")
    a("")
    a("-- section 5.2.3: two denominators, KEPT against DISCARDED --")
    a(f"  per-trade   KEPT {denom['per_trade_kept']:+.4f}R  DISCARDED {denom['per_trade_disc']:+.4f}R  "
      f"delta {denom['per_trade_delta']:+.4f}R")
    a(f"  per-symday  KEPT {denom['per_symday_kept']:+.4f}R  DISCARDED {denom['per_symday_disc']:+.4f}R  "
      f"delta {denom['per_symday_delta']:+.4f}R")
    a(f"  sign agreement: {'YES' if denom['sign_agree'] else 'NO -- REFUSAL'}")
    a("")
    a("-- section 5.2.4: composition (reported, never scored) --")
    a(f"  KEPT share by time-of-day bucket: {comp.get('by_when', {})}")
    a(f"  KEPT share by side (1=long,-1=short): {comp.get('by_side', {})}")
    a(f"  KEPT share by spread bucket: {comp.get('by_spread', {})}")
    a(f"  KEPT share by listing venue: {comp.get('by_venue', 'n/a')}")
    a("")
    a("-- section 7, criteria 1-6, on T2's KEPT book --")
    a(f"  1. drop-top-3 {s7['drop3']:+.2f}R, drop-top-5 {s7['drop5']:+.2f}R, both > 0: "
      f"{'PASS' if s7['crit1'] else 'FAIL'}")
    a(f"  2. symbol-cluster bootstrap P(total>0) = {s7['boot_p']:.3f} >= 0.95: "
      f"{'PASS' if s7['crit2'] else 'FAIL'}")
    a(f"  3. mean net R = {s7['mean_r']:+.4f}R >= +0.05R: {'PASS' if s7['crit3'] else 'FAIL'}")
    a(f"  4. trades = {s7['n']} >= 100: {'PASS' if s7['crit4'] else 'FAIL'}")
    a(f"  5. both halves > 0 ({s7['half1']:+.2f}R, {s7['half2']:+.2f}R): "
      f"{'PASS' if s7['crit5'] else 'FAIL'}")
    a(f"  6. both sides > 0 (long {s7['long_r']:+.2f}R, short {s7['short_r']:+.2f}R): "
      f"{'PASS' if s7['crit6'] else 'FAIL'}")
    a("")
    a("=" * 78)
    overall = (s7["passes"] and null["mean_beats"] and null["drop5_beats"]
              and denom["sign_agree"])
    if overall:
        a("VERDICT: H-Q1 clears every computable bar (G5, section 5.2 items 2-3, section 7).")
    else:
        a("VERDICT: H-Q1 NOT ADOPTABLE.")
        a("  Section 7.1's retirement clause fires: top-of-book imbalance is retired as an")
        a("  entry selector on this project (no threshold on |I|, no snapshot-instead-of-")
        a("  time-weighted, no deeper book, no longer window, no second venue) unless a")
        a("  stated reason says the CONSTRUCTION, not the idea, was at fault.")
    _append_fill_check(L, fc)
    return L


def _append_fill_check(L: list[str], fc: dict) -> None:
    a = L.append
    a("")
    a("-- section 4: the fill check, on T1's own entries (affects H-X1's record only) --")
    a(f"  n {fc['n']:,}  no book at fill instant {fc['n_no_book']:,}  no window {fc['n_no_window']:,}")
    a(f"  median quote-based fill vs modelled: {fc['median_diff']:+.4f}  "
      f"{'UNDERSTATES entry cost' if fc['understated'] else 'does not understate'}")
    if fc["understated"]:
        a("  Per section 4: 'a pass on a fill model that fails its own check is not a pass.'")
        a("  Moot for H-X1 here -- it already failed section 7 on other criteria (step 5).")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--csv", default=str(CSV_DEFAULT))
    p.add_argument("--holdout-start", default=HOLDOUT_START)
    a = p.parse_args(argv)

    df = load_trades(a.trades)
    edge = plan_edge(date.today())
    holdout_start = date.fromisoformat(a.holdout_start)
    pop = in_window_population(df, edge, holdout_start)
    print(f"in-window T1 population: {len(pop):,} trades", flush=True)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()
    wins = Windows(archive)

    print("G5 (positive control) ...", flush=True)
    g5 = g5_positive_control(pop, wins)

    scored = add_signal(pop, wins)
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(a.csv, index=False, encoding="utf-8", compression="gzip")
    n_pop = len(scored)
    n_no_book = int((scored["bucket"] == NO_BOOK).sum())
    no_book_share = (n_no_book / n_pop * 100.0) if n_pop else 0.0

    fc = fill_check(pop, wins)

    if g5["passes"]:
        bt = bucket_table(scored)
        null = shuffled_kept_null(scored)
        denom = two_denominators(scored)
        comp = composition(scored)
        s7 = section7(scored)
    else:
        bt = null = denom = comp = s7 = {}

    L = render(g5, bt, null, denom, comp, s7, fc, n_pop, no_book_share)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}\nwrote {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
