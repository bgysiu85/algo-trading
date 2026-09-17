#!/usr/bin/env python3
r"""H-B3 -- take a signal only if the name ranks top-N by session range at that minute.

    python -m common.range_rank --jobs 8

Registered in docs/research/REGISTERED_range_rank.md before this file
existed. Six books from one `run_day` per session: MCL and MC5 as published,
each gated at N = 3 (the registered cell) and at N = 1 (reported, declared in
advance, not read). The gate is `entry_gate` on both engines: an AND-mask over
the rule's own entries, signal-ordinal, `None` bit-identical.

THE RANK, EXACTLY (registration §1). At minute m of the session (04:00 = 0),
each point-in-time name carries the running mean of (high - low) / close over
its session-day bars printed STRICTLY BEFORE minute m, in percent --
`universe_lift.measure`'s `range_pct`, as a running series. The competitor
set at minute m is every record of the session with `first_seen <= m`: the
watchlist as the trader would have seen it, not the tape. Rank is 1 + the
number of visible competitors with a strictly larger value; ties are inside
the cut. The gate at m is True when the name is itself visible, has a value,
and ranks <= N.

For MC5 the gate is stamped on the 5-minute bar labels the engine trades,
with the value at the label's minute -- i.e. from bars before the 5-minute
bar STARTED. That is up to five minutes more conservative than necessary and
in the safe direction, as MC5's floor is.

WHERE THE GATE CANNOT BIND. With fewer than N names visible the gate admits
every signal. The report counts, for every baseline entry, how many names
were visible at that minute, so that NOTHING cannot be read as "selection does
not help" where it means "there was nothing to select from".
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.entry_shares import QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
REGISTERED = "docs/research/REGISTERED_range_rank.md"
SESSION_MINUTES = 330                 # 04:00 -> 09:30 ET
N_REGISTERED = 3
N_REPORTED = 1
BOOKS = (("MCL", "mcl", None), ("MCL-top3", "mcl", N_REGISTERED), ("MCL-top1", "mcl", N_REPORTED),
         ("MC5", "mc5", None), ("MC5-top3", "mc5", N_REGISTERED), ("MC5-top1", "mc5", N_REPORTED))
PAIRED = (("MCL", "MCL-top3"), ("MC5", "MC5-top3"))
REPORTED = (("MCL", "MCL-top1"), ("MC5", "MC5-top1"))


# --- the rank ----------------------------------------------------------------------

def minute_of(ts) -> int:
    """Minutes since 04:00 ET of a tz-aware timestamp; may be outside [0, 330)."""
    t = pd.Timestamp(ts).tz_convert(ET)
    return (t.hour - 4) * 60 + t.minute


def running_range_pct(day_df: pd.DataFrame) -> np.ndarray:
    """Per minute m in [0, SESSION_MINUTES): the running mean of
    (high - low) / close over the session-day bars printed strictly before
    minute m, in percent; NaN until the first bar has printed. `day_df` is
    the symbol's bars for the session day only, in time order."""
    out = np.full(SESSION_MINUTES, np.nan)
    if day_df.empty:
        return out
    mins = np.array([minute_of(t) for t in day_df.index])
    h = day_df["high"].to_numpy(dtype=float)
    lo = day_df["low"].to_numpy(dtype=float)
    c = day_df["close"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(c > 0, (h - lo) / c, np.nan)
    keep = (mins >= 0) & (mins < SESSION_MINUTES) & np.isfinite(r)
    mins, r = mins[keep], r[keep]
    if len(mins) == 0:
        return out
    # cumulative mean through each printed bar, placed at the NEXT minute
    csum, cnt = np.cumsum(r), np.arange(1, len(r) + 1)
    mean_after = csum / cnt * 100.0
    # For minute m, the last bar with minute < m.
    j = np.searchsorted(mins, np.arange(SESSION_MINUTES), side="left") - 1
    ok = j >= 0
    out[ok] = mean_after[j[ok]]
    return out


def first_seen_minute(rec: dict) -> int:
    return max(0, minute_of(rec["first_seen"]))


def gates_for_session(values: dict[str, np.ndarray], seen: dict[str, int],
                      n: int) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """{symbol: gate[m]} and {symbol: visible_count[m]} for one session.

    `values[s][m]` is the running range_pct; `seen[s]` the minute the screen
    surfaced s. A name competes at m iff seen[s] <= m and its value at m is
    finite. The gate is True iff the name competes and its rank <= n."""
    syms = sorted(values)
    M = np.vstack([values[s] for s in syms]) if syms else np.empty((0, SESSION_MINUTES))
    S = np.array([seen[s] for s in syms])[:, None]
    m_idx = np.arange(SESSION_MINUTES)[None, :]
    competing = (S <= m_idx) & np.isfinite(M)
    V = np.where(competing, M, -np.inf)
    gates, visible = {}, {}
    for i, s in enumerate(syms):
        mine = V[i]
        # competitors strictly above me, among those competing. Strictly, so
        # the name itself is never counted and ties fall inside the cut.
        above = (V > mine[None, :]) & competing
        rank = 1 + above.sum(axis=0)
        vis = competing.sum(axis=0)
        gates[s] = competing[i] & (rank <= n)
        visible[s] = vis
    return gates, visible


def gate_series(gate: np.ndarray, index: pd.DatetimeIndex) -> pd.Series:
    """The gate stamped on a bar index (1-minute bars, or 5-minute labels):
    each bar takes the gate's value at its own minute; bars outside the
    session are False."""
    mins = np.array([minute_of(t) for t in index]) if len(index) else np.array([], dtype=int)
    ok = (mins >= 0) & (mins < SESSION_MINUTES)
    vals = np.zeros(len(index), dtype=bool)
    vals[ok] = gate[mins[ok]]
    return pd.Series(vals, index=index)


# --- one session ---------------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    from strategy.mc5 import mc5

    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    # Per-symbol frames, and the session-day slice of each for the rank.
    recs = [r for r in universe if r.get("first_seen")]
    per_sym, values, seen = {}, {}, {}
    for rec in recs:
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        local = df.index.tz_convert(ET)
        per_sym[s] = df
        values[s] = running_range_pct(df[local.date == d])
        seen[s] = first_seen_minute(rec)
    gates = {n: gates_for_session(values, seen, n) for n in (N_REGISTERED, N_REPORTED)}

    res = {"books": {name: [] for name, _, _ in BOOKS}, "symdays": 0, "errors": 0,
           "error_days": [], "refused": {name: [] for name, _, n in BOOKS if n},
           "binding": {name: [0, 0, Counter()] for name, _, n in BOOKS if n}}
    for rec in recs:
        s = rec["symbol"]
        if s not in per_sym:
            continue
        df = per_sym[s]
        floor = first_seen_time(rec)
        try:
            idx5 = mc5.to_5m(df).index
            got = {}
            for name, eng, n in BOOKS:
                mod, extra = engines[eng]
                if n is None:
                    gate = None
                else:
                    g = gates[n][0][s]
                    gate = gate_series(g, idx5 if eng == "mc5" else df.index)
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, entry_gate=gate, **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [G.trade_row(t, s, day, k) for k, t in enumerate(trades, 1)]
        # Binding and refusal, read off the BASELINE's entries: at each
        # baseline entry minute, how many names were visible, and was the
        # gate False there (= this trade refused, exactly).
        for name, eng, n in BOOKS:
            if n is None:
                continue
            base_name = "MCL" if eng == "mcl" else "MC5"
            g, vis = gates[n][0][s], gates[n][1][s]
            for t in got[base_name]:
                m = minute_of(t.entry_time)
                if not (0 <= m < SESSION_MINUTES):
                    continue
                b = res["binding"][name]
                b[1] += 1
                b[2][int(vis[m])] += 1
                if vis[m] > n:        # more names than the cut: the gate can refuse
                    b[0] += 1
                if not g[m]:
                    row = G.trade_row(t, s, day, 0)
                    res["refused"][name].append(row)
    return day, res, ""


# --- cli --------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/range_rank.txt")
    p.add_argument("--csv", default="var/reports/range_rank_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "range_rank")

    books = {name: [] for name, _, _ in BOOKS}
    refused = {name: [] for name, _, n in BOOKS if n}
    binding = {name: [0, 0, Counter()] for name, _, n in BOOKS if n}
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        for name in refused:
            refused[name] += r["refused"][name]
            b, rb = binding[name], r["binding"][name]
            b[0] += rb[0]
            b[1] += rb[1]
            b[2].update(rb[2])
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]
    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    binding_t = {k: (v[0], v[1], dict(v[2])) for k, v in binding.items()}
    emit("\n".join(G.render("H-B3: TAKE A SIGNAL ONLY IF THE NAME RANKS TOP-N BY SESSION RANGE AT THAT MINUTE",
                            REGISTERED, books, PAIRED, REPORTED, symdays, errors, run_days,
                            elapsed, jobs, refused, binding_t, error_days)),
         a.out, header=f"common.range_rank pairs={a.pairs} dataset={a.dataset} sessions={len(run_days)} "
                       f"symbol_days={symdays} cut={cut} qty={QTY} N={N_REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED, "N": N_REGISTERED})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
