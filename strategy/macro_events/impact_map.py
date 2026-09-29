#!/usr/bin/env python3
"""W15-0023 step 2: macro-event impact map on the daily futures bars.

QUESTION (descriptive, not a trading rule): on the day a scheduled macro release
lands (CPI, NFP, FOMC decision, EIA weekly crude report), is each futures market's
daily range / absolute move bigger than on ordinary days, and by how much?

The answer decides which (market, event) pairs step 3 may pre-register an entry-flag
test on. Nothing here is a strategy and no P&L is computed.

DATA. The same 12 markets and the same holdout-safe loader as TL-v0
(strategy.tl_v0.bars.load_market: training rows only, 2010-06-01 .. 2021-12-31,
Sunday rows folded, held-contract roll rule). Rows dated 2022-01-01 onward never
reach this module; run() and prepare() both refuse a frame that contains one.

MEASURES (both scale-free, so markets and vol regimes are comparable):
  range_ratio  = (high - low) of the session / mean (high - low) of the PRIOR 20 sessions
  move_ratio   = |close - previous close| / the same prior-20-session mean range
The baseline mean uses sessions t-20 .. t-1 only (never the event day itself).

COMPARISON. Event days are compared with "quiet" days. An event day that shares its
date with another RELEVANT event type is reported in the "all" count but excluded from
the "clean" count, which is the one the flag reads.

POST-RESULT AMENDMENT (step 2b, 2026-09-29). The first run (stamp 20260929) was read
before these two changes; they are disclosed as post-result. They fix two design flaws,
not a threshold:
  (a) RELEVANT EVENTS. EIA (crude inventories) is only relevant to CL and NG. For every
      other market, overlap and "quiet" are defined by CPI, NFP and FOMC only, and the
      EIA cell is not tested. Reason: run 1 dropped FOMC to 11 clean days per market
      because every FOMC decision falls on an EIA Wednesday, which says nothing about
      ES or gold.
  (b) WEEKDAY-MATCHED BASELINE. Run 1 compared event days with quiet days of any
      weekday; EIA days are all Wednesdays and NFP days all Fridays. Now each event day
      is compared with quiet days of the SAME weekday (drawn with replacement, 5,000
      seeded draws). Where a weekday has fewer than 20 quiet days (CL/NG on Wednesdays:
      every Wednesday is an EIA day) the cell falls back to the unmatched comparison
      and is marked matched=False; it can never be SUPPORTED, only listed.
  Holm still runs over the original 12 x 4 = 48 slots (untested EIA cells count as
  p = 1), so dropping cells cannot make anything easier to flag.

For each cell:
  excess   = median(event ratio) - mean of the permutation medians (the weekday-matched
             expectation); excess_unmatched keeps run 1's definition for comparison
  p        = one-sided permutation p: (1 + #draws whose median >= observed) / 5,001
  Holm     = Holm step-down adjustment across the 48 slots
FLAG "SUPPORTED" = n_clean >= 30 (the project's power floor) AND matched AND Holm p <
0.05 on range_ratio. The flag only picks pairs worth a step-3 registration; it is not
a finding about profitability.

NOT INCLUDED: volume (the daily archive rows carry OHLC only here), OPEC (the
calendar holds only 3 dates), unscheduled FOMC calls (mostly no announcement),
and any intraday timing inside the session.

Run on Ben's PC (the archive is on E:):
    python -m strategy.macro_events.impact_map
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CALENDAR_DEFAULT = Path(__file__).with_name("macro_event_calendar.csv")

EVENTS: tuple[str, ...] = ("CPI", "NFP", "FOMC", "EIA_WPSR")
LOOKBACK = 20                 # sessions in the baseline range
N_PERM = 5000
SEED = 20260929
MIN_CLEAN = 30                # project power floor
ALPHA = 0.05
HOLDOUT_START = pd.Timestamp("2022-01-01")


class ImpactRefused(SystemExit):
    """A guard fired; nothing was computed."""


# ---------------------------------------------------------------- calendar
def load_calendar(path: Path) -> pd.DataFrame:
    cal = pd.read_csv(path, dtype=str)
    need = {"date", "event", "kind"}
    if not need <= set(cal.columns):
        raise ImpactRefused(f"calendar {path} lacks columns {sorted(need - set(cal.columns))}")
    cal["date"] = pd.to_datetime(cal["date"])
    return cal


def event_dates(cal: pd.DataFrame) -> dict[str, set[pd.Timestamp]]:
    """Scheduled dates per event type. Unscheduled rows are ignored on purpose."""
    sched = cal[cal["kind"] == "scheduled"]
    return {e: set(sched.loc[sched["event"] == e, "date"]) for e in EVENTS}


# ---------------------------------------------------------------- ratios
def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-session range_ratio and move_ratio. `frame` needs date, rh, rl, close
    (the MarketBars.frame columns: raw high/low of the traded contract, and the
    back-adjusted close)."""
    f = frame.sort_values("date").reset_index(drop=True)
    if (pd.to_datetime(f["date"]) >= HOLDOUT_START).any():
        raise ImpactRefused("a session dated on/after 2022-01-01 reached the impact map "
                            "(holdout) -- refusing")
    rng = (f["rh"] - f["rl"]).astype(float)
    prior = rng.shift(1).rolling(LOOKBACK).mean()          # sessions t-20 .. t-1
    move = f["close"].astype(float).diff().abs()
    out = pd.DataFrame({
        "date": pd.to_datetime(f["date"]),
        "range_ratio": rng / prior,
        "move_ratio": move / prior,
    })
    out = out[prior.notna() & (prior > 0)].reset_index(drop=True)
    return out


# ---------------------------------------------------------------- stats
ENERGY = ("CL", "NG")          # markets for which the EIA crude report is a relevant event
MIN_POOL = 20                  # quiet days needed on a weekday to match against it


def relevant_events(market: str) -> tuple[str, ...]:
    return EVENTS if market in ENERGY else tuple(e for e in EVENTS if e != "EIA_WPSR")


def _perm_matched(clean_dates, clean_vals, quiet: pd.DataFrame, meas: str,
                  rng: np.random.Generator):
    """Draw, N_PERM times, one quiet day of the SAME weekday for every event day.
    Returns (perm_medians, matched). matched=False -> some weekday had < MIN_POOL quiet
    days, so the draw falls back to the pooled quiet days (weekday-blind)."""
    wd_ev = pd.DatetimeIndex(clean_dates).dayofweek.to_numpy()
    wd_q = quiet["date"].dt.dayofweek.to_numpy()
    qv = quiet[meas].to_numpy()
    ok = ~np.isnan(qv)
    pools = {w: qv[(wd_q == w) & ok] for w in range(5)}
    need = {int(w): int((wd_ev == w).sum()) for w in np.unique(wd_ev)}
    if all(len(pools[w]) >= MIN_POOL for w in need):
        cols = [pools[w][rng.integers(0, len(pools[w]), size=(N_PERM, k))] for w, k in need.items()]
        return np.median(np.concatenate(cols, axis=1), axis=1), True
    pool = qv[ok]
    return np.median(pool[rng.integers(0, len(pool), size=(N_PERM, len(clean_vals)))], axis=1), False


def holm(pvals: list[float], m: int | None = None) -> list[float]:
    """Holm step-down adjusted p-values (monotone, capped at 1) over m slots
    (default len(pvals)); slots that were never tested count as p = 1."""
    m = len(pvals) if m is None else max(m, len(pvals))
    order = np.argsort(pvals)
    adj = np.empty(len(pvals))
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * pvals[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def market_cells(name: str, ratios: pd.DataFrame, ev: dict[str, set], cell_seed: int) -> list[dict]:
    """One row per TESTED event type for this market (p not yet Holm-adjusted)."""
    dates = ratios["date"]
    rel = relevant_events(name)
    any_event = pd.Series(False, index=ratios.index)
    count = pd.Series(0, index=ratios.index)
    for e in rel:
        hit = dates.isin(ev[e])
        any_event |= hit
        count += hit.astype(int)
    quiet = ratios[~any_event]
    rows = []
    for k, e in enumerate(EVENTS):
        if e not in rel:
            continue
        is_e = dates.isin(ev[e])
        clean = is_e & (count == 1)
        row = {"market": name, "event": e, "n_all": int(is_e.sum()), "n_clean": int(clean.sum()),
               "n_quiet": int(len(quiet))}
        for meas in ("range_ratio", "move_ratio"):
            q = quiet[meas].dropna().to_numpy()
            cd = ratios.loc[clean & ratios[meas].notna(), "date"]
            c = ratios.loc[clean, meas].dropna().to_numpy()
            a = ratios.loc[is_e, meas].dropna().to_numpy()
            row[f"{meas}_quiet_median"] = float(np.median(q)) if len(q) else np.nan
            row[f"{meas}_all_median"] = float(np.median(a)) if len(a) else np.nan
            row[f"{meas}_clean_median"] = float(np.median(c)) if len(c) else np.nan
            row[f"{meas}_excess_unmatched"] = row[f"{meas}_clean_median"] - row[f"{meas}_quiet_median"]
            if len(c) >= 2 and len(q) >= 2:
                g = np.random.default_rng([SEED, cell_seed, k, 0 if meas == "range_ratio" else 1])
                meds, matched = _perm_matched(cd, c, quiet, meas, g)
                obs = float(np.median(c))
                row[f"{meas}_excess"] = obs - float(meds.mean())
                row[f"{meas}_p"] = (1 + int((meds >= obs).sum())) / (N_PERM + 1)
                if meas == "range_ratio":
                    row["matched"] = matched
            else:
                row[f"{meas}_excess"] = np.nan
                row[f"{meas}_p"] = np.nan
                if meas == "range_ratio":
                    row["matched"] = False
        q90 = np.quantile(quiet["range_ratio"].dropna(), 0.9) if len(quiet) else np.nan
        c = ratios.loc[clean, "range_ratio"].dropna().to_numpy()
        row["range_exceed_q90"] = float((c > q90).mean()) if len(c) else np.nan   # expected 0.10
        rows.append(row)
    return rows


def build_table(ratios_by_market: dict[str, pd.DataFrame], ev: dict[str, set]) -> pd.DataFrame:
    rows: list[dict] = []
    for i, (name, r) in enumerate(ratios_by_market.items()):
        rows += market_cells(name, r, ev, i)
    t = pd.DataFrame(rows)
    slots = len(ratios_by_market) * len(EVENTS)              # 12 x 4 = 48; untested cells = p 1
    ok = t["range_ratio_p"].notna()
    adj = pd.Series(np.nan, index=t.index)
    adj[ok] = holm(t.loc[ok, "range_ratio_p"].tolist(), slots)
    t["range_p_holm"] = adj
    t["supported"] = (t["n_clean"] >= MIN_CLEAN) & t["matched"] & (t["range_p_holm"] < ALPHA)
    return t


# ---------------------------------------------------------------- report
def _neg(x: float, fmt: str = "{:.2f}") -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a"
    s = fmt.format(abs(x))
    return f"({s})" if x < 0 else s


def render(t: pd.DataFrame, notes: dict[str, dict], stamp: str) -> str:
    L = []
    L.append(f"W15-0023 step 2b -- macro-event impact map (weekday-matched) -- {stamp}")
    L.append("Descriptive only. Training rows 2010-06-01 .. 2021-12-31 (holdout untouched).")
    L.append(f"Baseline = mean range of prior {LOOKBACK} sessions. Quiet = none of the market's RELEVANT events that day")
    L.append("(CPI, NFP, FOMC; plus EIA for CL and NG only). Event days are compared with quiet days of the SAME weekday.")
    L.append(f"p = one-sided permutation ({N_PERM} draws, seed {SEED}); Holm over 48 slots (untested EIA cells count as p = 1).")
    L.append(f"SUPPORTED = n_clean >= {MIN_CLEAN}, weekday-matched, Holm p < {ALPHA} on range_ratio. Negatives in brackets.")
    L.append("AMENDMENT: the relevance rule and weekday matching were added AFTER run 1 was read (see module docstring).")
    L.append("")
    L.append(f"{'market':6} {'event':9} {'n_clean':>7} {'n_all':>6} {'rng_event':>9} {'rng_exc':>8} {'unm_exc':>8} "
             f"{'p':>7} {'holm':>7} {'>q90':>5} {'mv_exc':>8} {'match':>5} {'flag':>10}")
    for _, r in t.iterrows():
        if r["supported"]:
            flag = "SUPPORTED"
        elif (not r["matched"]) and r["range_p_holm"] < ALPHA and r["n_clean"] >= MIN_CLEAN:
            flag = "unmatched*"
        else:
            flag = "-"
        L.append(f"{r['market']:6} {r['event']:9} {r['n_clean']:7d} {r['n_all']:6d} "
                 f"{_neg(r['range_ratio_clean_median']):>9} "
                 f"{_neg(r['range_ratio_excess']):>8} {_neg(r['range_ratio_excess_unmatched']):>8} "
                 f"{_neg(r['range_ratio_p'], '{:.4f}'):>7} "
                 f"{_neg(r['range_p_holm'], '{:.4f}'):>7} {_neg(r['range_exceed_q90'], '{:.2f}'):>5} "
                 f"{_neg(r['move_ratio_excess']):>8} {'yes' if r['matched'] else 'NO':>5} {flag:>10}")
    L.append("")
    sup = t[t["supported"]]
    L.append(f"SUPPORTED cells: {len(sup)} of {len(t)} tested")
    for _, r in sup.iterrows():
        base = r["range_ratio_clean_median"] - r["range_ratio_excess"]
        L.append(f"  {r['market']:5} {r['event']:9} range x{r['range_ratio_clean_median']/base:.2f} of the weekday-matched quiet median, n={r['n_clean']}")
    um = t[(~t["matched"]) & (t["n_clean"] >= MIN_CLEAN)]
    if len(um):
        L.append("* unmatched = no quiet days on the event's weekday (every Wednesday is an EIA day), so the comparison is")
        L.append("  weekday-blind and cannot be SUPPORTED: " + ", ".join(f"{r['market']} {r['event']}" for _, r in um.iterrows()))
    L.append("")
    L.append("Per-market data notes (sessions used / rolls / stale bars):")
    for m, n in notes.items():
        L.append(f"  {m:5} {n}")
    L.append("")
    L.append("Caveats: daily bars only (an event's effect inside the day is not resolved); OHLC only, no volume;")
    L.append("EIA dates before 2025 are rule-based; OPEC excluded; medians of ratios, not returns -- a bigger day says")
    L.append("nothing about direction or about any strategy's P&L.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- run
def run(archive: Path, calendar: Path, out_dir: Path, stamp: str, *, loader=None,
        markets: list[str] | None = None) -> Path:
    cal = load_calendar(calendar)
    ev = event_dates(cal)
    if loader is None:
        from strategy.tl_v0.bars import load_market
        from strategy.tl_v0.spec import MARKETS
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        names = markets or list(MARKETS)
        loader = lambda n: load_market(archive, MARKETS[n])
    else:
        names = markets or []
    ratios, notes = {}, {}
    for n in names:
        mb, _c0 = loader(n)
        ratios[n] = prepare(mb.frame)
        notes[n] = f"{len(ratios[n])} sessions, first {ratios[n]['date'].min().date()}, last {ratios[n]['date'].max().date()}"
    t = build_table(ratios, ev)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = out_dir / f"w15_0023_impact_map_{stamp}.csv"
    txt = out_dir / f"w15_0023_impact_map_{stamp}.txt"
    t.to_csv(csv, index=False)
    txt.write_text(render(t, notes, stamp), encoding="utf-8")
    print(txt.read_text(encoding="utf-8"))
    print(f"wrote {txt}\nwrote {csv}")
    return txt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--calendar", type=Path, default=CALENDAR_DEFAULT)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    a = ap.parse_args(argv)
    archive = a.archive
    if archive is None:
        from strategy.tl_v0.run import default_archive
        archive = default_archive()
    run(archive, a.calendar, a.out_dir, a.stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
