#!/usr/bin/env python3
"""Does a name's history of running — and holding — predict anything?

    python -m common.prior_spike

THE CLAIM, from two directions
------------------------------
`warrior_0_universe_and_risk.md` §7.1, the daily-chart trust check. Before
trading a name he zooms out on the daily and rejects it if it has a history of
popping and giving the whole move back:

    "up ~300% two weeks earlier, fully retraced -- that's a little shady. If it
     had gone up 300% and HELD that level, that'd be different."   -- V-3HR 17:34

`warrior_3_gap_and_go.md` §1 states the same thing as two rows of a grading
rubric: **former runner, retail interest** is ideal; **former pump-and-dump** is
avoid. Warrior 3 §2 makes the point that these are one computation, not two:
find prior spikes in the daily history and measure what fraction was retained.
High retention is the first row, low retention the second, and the §7.1 filter
is the same number with a threshold on it.

**We have never tested whether prior-spike retention predicts anything.** It is
cheap — a symbol filter rather than a setup filter — and the daily archive is
already on disk.

PINNED BEFORE RUNNING
---------------------
Every one of these is a free parameter and a sweep over them would be fitting.

    LOOKBACK_SESSIONS  60   the daily window searched for a prior spike
    QUIET_SESSIONS      5   sessions immediately before the trade, EXCLUDED
                            from the search so today's own move cannot be
                            found as its own "prior" spike
    SPIKE_MIN        1.00   a run of +100% peak-over-base counts as a spike.
                            He says 300%; 100% is looser on purpose, because a
                            threshold set at his example would find almost
                            nothing and the null would be about the threshold
    RETAINED_HIGH     0.5   at or above: "former runner"
    RETAINED_LOW      0.2   below: "former pump-and-dump"

RETENTION is (last close before the trade − base) / (peak − base), where base
is the lowest close preceding the peak inside the window. 1.0 means the entire
run was held; 0.0 means it went all the way back.

WHAT THE ANSWER LOOKS LIKE EITHER WAY
--------------------------------------
If high-retention names produce better MCL trades than low-retention ones, in
both halves and after drop-top-3, the filter earns a registration. If they do
not, three separate rules across two Warrior documents lose their basis at once
and should stop being quoted as candidates.

The population with NO prior spike at all is reported as its own row rather
than dropped. On this universe it may well be the majority, and a filter that
silently discards most of the universe is a different filter from the one
described.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
SPLIT = "2026-03-20"
QTY = 100

LOOKBACK_SESSIONS = 60
QUIET_SESSIONS = 5
SPIKE_MIN = 1.00
RETAINED_HIGH = 0.50
RETAINED_LOW = 0.20


def prior_spike(closes: pd.Series) -> dict | None:
    """The largest prior run in this window, and how much of it was held.

    `closes` is one symbol's daily closes, oldest first, ALREADY trimmed to
    end QUIET_SESSIONS before the trade -- the trim belongs to the caller so
    that this function cannot accidentally see the move being traded and
    report it as history.

    Returns None when there is no qualifying spike, which is information and
    not a failure: "this name has never run" is one of the rubric's own
    categories.
    """
    if closes is None or len(closes) < 3:
        return None
    vals = [float(v) for v in closes if pd.notna(v) and float(v) > 0]
    if len(vals) < 3:
        return None

    # The best (peak, base) pair in the window: for each peak, the lowest close
    # BEFORE it. Scanned forward keeping the running minimum, so base always
    # precedes peak and the run is a real up-move rather than a range.
    best = None
    run_min = vals[0]
    for i in range(1, len(vals)):
        px = vals[i]
        if run_min > 0 and (px - run_min) / run_min >= SPIKE_MIN:
            gain = (px - run_min) / run_min
            if best is None or gain > best["run_pct"]:
                best = {"run_pct": gain, "peak": px, "base": run_min,
                        "peak_i": i}
        run_min = min(run_min, px)
    if best is None:
        return None

    last = vals[-1]
    span = best["peak"] - best["base"]
    retained = 0.0 if span <= 0 else (last - best["base"]) / span
    best["retained"] = max(0.0, min(1.0, retained))
    best["sessions_since_peak"] = len(vals) - 1 - best["peak_i"]
    return best


def label(spike: dict | None) -> str:
    if spike is None:
        return "no prior spike"
    if spike["retained"] >= RETAINED_HIGH:
        return "former runner"
    if spike["retained"] < RETAINED_LOW:
        return "pump and dump"
    return "partial hold"


def history_for(daily: pd.DataFrame, symbol: str, on: str) -> pd.Series | None:
    """That symbol's closes over the window, ending QUIET_SESSIONS before `on`.

    The quiet gap is the whole reason this is a separate function: without it
    the search runs right up to the trade and finds the move being traded,
    which would score every winner as a "former runner" by construction.
    """
    rows = daily[(daily["symbol"] == symbol) & (daily["date"] < on)]
    if rows.empty:
        return None
    rows = rows.sort_values("date")
    if QUIET_SESSIONS:
        rows = rows.iloc[:-QUIET_SESSIONS] if len(rows) > QUIET_SESSIONS \
            else rows.iloc[0:0]
    return rows["close"].tail(LOOKBACK_SESSIONS) if not rows.empty else None


def stats(reals: list[float], drop: int = 3) -> dict:
    if not reals:
        return {"n": 0, "net": 0.0, "per": 0.0, "dropped": 0.0, "win": 0.0}
    net = sum(reals)
    top = sorted(reals, reverse=True)[:drop]
    return {"n": len(reals), "net": net, "per": net / len(reals),
            "dropped": net - sum(top),
            "win": 100.0 * sum(1 for r in reals if r > 0) / len(reals)}


def render(groups: dict[str, list], n_trades: int, n_sessions: int) -> list[str]:
    L = ["PRIOR-SPIKE RETENTION -- does a name's history predict its trades?",
         "",
         f"  {n_sessions} cached sessions, {n_trades} MCL trades, {QTY} shares "
         f"flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         "",
         f"  window {LOOKBACK_SESSIONS} sessions, ending {QUIET_SESSIONS} "
         f"sessions before the trade",
         f"  a spike is a run of +{SPIKE_MIN * 100:.0f}% peak-over-base",
         f"  former runner >= {RETAINED_HIGH:.0%} retained, pump and dump "
         f"< {RETAINED_LOW:.0%}",
         "  All pinned before running. A sweep over them would be fitting.", "",
         f"  {'group':<18}{'trades':>7}{'net':>10}{'per':>9}{'win%':>7}"
         f"{'drop top 3':>12}{'early':>10}{'late':>10}"]

    order = ["former runner", "partial hold", "pump and dump", "no prior spike"]
    got = {}
    for name in order:
        rows = groups.get(name, [])
        if not rows:
            continue
        s = stats([r["real"] for r in rows])
        early = sum(r["real"] for r in rows if r["date"] < SPLIT)
        late = sum(r["real"] for r in rows if r["date"] >= SPLIT)
        got[name] = dict(s, early=early, late=late)
        L.append(f"  {name:<18}{s['n']:>7}${s['net']:>9,.0f}${s['per']:>8.2f}"
                 f"{s['win']:>6.1f}%${s['dropped']:>11,.0f}"
                 f"${early:>9,.0f}${late:>9,.0f}")
    L.append("")

    hi, lo = got.get("former runner"), got.get("pump and dump")
    if not hi or not lo:
        L += ["  ONE OF THE TWO GROUPS IS EMPTY, so there is nothing to",
              "  compare. Either the spike threshold finds almost nothing on",
              "  this universe, or the retention split does not divide it.",
              "  Report the counts, change nothing.", ""]
        return L + tail()

    gap = hi["per"] - lo["per"]
    L += ["THE RUBRIC'S OWN CLAIM: former runners beat pump-and-dumps", "",
          f"  former runner  {hi['per']:+.2f}/trade over {hi['n']} trades",
          f"  pump and dump  {lo['per']:+.2f}/trade over {lo['n']} trades",
          f"  gap            {gap:+.2f}/trade", ""]

    halves_agree = (hi["early"] - lo["early"]) * (hi["late"] - lo["late"]) > 0
    survives = hi["dropped"] > lo["dropped"]

    if gap > 0 and halves_agree and survives:
        L += ["  SUPPORTED. Former runners beat pump-and-dumps on the total,",
              "  in both halves, and after drop-top-3. That is enough to",
              "  register the filter as a hypothesis and test it on the locked",
              "  holdout — it is NOT enough to turn it on, because MCL was",
              "  fitted on these sessions.", ""]
    elif gap > 0:
        reasons = []
        if not halves_agree:
            reasons.append("the sign flips between halves")
        if not survives:
            reasons.append("it does not survive drop-top-3")
        L += [f"  NOT SUPPORTED: the gap points the right way but "
              f"{' and '.join(reasons)}.",
              "  A handful of trades, or one period, is the result.", ""]
    else:
        L += ["  INVERTED. Pump-and-dumps did BETTER on this universe than",
              "  former runners. Three rules across two Warrior documents rest",
              "  on the opposite -- §7.1's trust check and both history rows of",
              "  the Gap-and-Go rubric -- and they should stop being quoted as",
              "  candidates until something explains this.", ""]
    return L + tail()


def tail() -> list[str]:
    return ["WHAT THIS DOES NOT SHOW", "",
            "  Whether the filter helps the SCREEN. This scores trades MCL",
            "  already took; a filter's real job is changing which names reach",
            "  the watchlist, and that needs the screener simulation.",
            "",
            "  Nothing here is out of sample. MCL was fitted on these",
            "  sessions. holdout.json is clean for this filter and should be",
            "  spent on it only once there is something worth spending it on.",
            "",
            "  IB bars are SPLIT-ADJUSTED and a reverse split follows a price",
            "  collapse — exactly the names this measures. An adjusted history",
            "  can turn a real collapse into a flat line, which biases the",
            "  pump-and-dump group toward looking better than it was."]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--archive", default=None,
                   help="Databento archive root (default: the configured one)")
    p.add_argument("--dataset", default="EQUS.MINI")
    p.add_argument("--out", default="var/reports/prior_spike.txt")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame

    a = build_parser().parse_args(argv)
    daily = daily_frame(Path(a.archive) if a.archive else default_archive(),
                        a.dataset)
    if daily.empty:
        raise SystemExit(
            f"no daily bars under {a.archive or default_archive()}/{a.dataset}"
            "/ohlcv-1d/. Pull them with common.databento_universe first.")
    daily["date"] = daily["date"].astype(str)

    sessions = load_sessions(Path(a.cache))
    groups: dict[str, list] = defaultdict(list)
    n = 0
    for sym, d, df in sessions:
        try:
            trades = MCL.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                entry_shares=QTY, **LIVE)
        except Exception:                                   # noqa: BLE001
            continue
        if not trades:
            continue
        spike = prior_spike(history_for(daily, sym, d))
        key = label(spike)
        for t in trades:
            n += 1
            groups[key].append({"symbol": sym, "date": d,
                                "real": t.net - MEASURED_FRICTION})

    emit("\n".join(render(groups, n, len(sessions))), a.out,
         header=f"common.prior_spike  cache={a.cache} dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
