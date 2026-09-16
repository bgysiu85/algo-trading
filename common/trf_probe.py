#!/usr/bin/env python3
r"""Can the reported-late prints be told from the live ones at trade level?

    python -m common.trf_probe                                   # estimate only
    python -m common.trf_probe --confirm                         # pull ALTS 2025-08-11 trades
    python -m common.trf_probe --symbol SLGB --date 2025-10-27 --confirm

WHY
---
`tape_spikes` (claude/tape_spikes_RESULT_20260917.md) showed that until the
TRF began opening at 04:00 on 2026-03-30, off-exchange overnight trades were
reported at 08:00 and landed in that minute's bar at hours-old prices. Every
high, low and volume from 08:00 on is contaminated on 426 of the 551 sessions.
Repairing that from bars is a guess; repairing it from trades is possible only
if the reported prints carry something a live print does not.

This pulls ONE symbol-day of the `trades` schema -- the worst one seen --
and asks the data, for every print, whether it is "wild" (more than 25% from
the running median of the prints around it) and what else is different about
it: its `flags`, `side`, `publisher_id`, and above all the gap between
`ts_event` and `ts_recv`. If a reported print carries its execution time in
`ts_event` and its report time in `ts_recv`, the two populations separate on
that alone and clean bars can be rebuilt for the whole archive. If nothing
separates them, the repair needs a different feed.

It then rebuilds the 08:00-08:40 bars from the trades with the candidate
prints removed and prints them beside the archive's bars, so the reader can
see what a clean bar would have looked like.

SPENDING: estimates first, refuses without --confirm, aborts over --max-cost
(default $0.25). The key is DATABENTO_API_KEY only, resolved as every other
Databento tool here resolves it, and never printed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit

ET = ZoneInfo("America/New_York")
WILD = 0.25           # a print more than 25% from the running median
MEDIAN_WINDOW = 51    # prints either side


def wild_mask(px: pd.Series) -> pd.Series:
    med = px.rolling(MEDIAN_WINDOW, center=True, min_periods=5).median()
    return ((px / med) > 1 + WILD) | ((med / px) > 1 + WILD)


def analyse(df: pd.DataFrame, bars: pd.DataFrame | None, symbol: str, day: str) -> list[str]:
    """df: trades for one symbol-day, UTC-indexed on ts_recv (Databento's
    default) with a ts_event column. bars: the archive's 1-minute bars for the
    same symbol-day, or None."""
    d = df.copy()
    if "ts_event" not in d.columns:
        d["ts_event"] = d.index
    # Several prints share a ts_recv, so the index is not unique; every
    # operation below works on positions, with the receipt time as a column.
    recv = pd.to_datetime(pd.Series(d.index), utc=True)
    d = d.reset_index(drop=True)
    d["recv_et"] = recv.dt.tz_convert(ET)
    ev = pd.to_datetime(d["ts_event"], utc=True)
    d["event_et"] = ev.dt.tz_convert(ET)
    d["lag_s"] = (recv - ev).dt.total_seconds()
    d["wild"] = wild_mask(d["price"].astype(float))
    d["minute"] = d["recv_et"].dt.strftime("%H:%M")
    d["hour"] = d["recv_et"].dt.hour
    w = d[d["wild"]]; n = d[~d["wild"]]

    L = [f"TRADE-LEVEL PROBE -- {symbol} {day}, {len(d):,} prints 04:00-09:30 ET", "",
         f"  columns: {', '.join(c for c in df.columns)}", "",
         f"  wild prints (>{WILD:.0%} from the running median of {MEDIAN_WINDOW}): {len(w):,}",
         f"    by hour of receipt: " + ", ".join(f"{h:02d}:xx {c:,}" for h, c in w.groupby('hour').size().items()),
         f"    worst minutes: " + ", ".join(f"{m} {c:,}" for m, c in w.groupby('minute').size().sort_values(ascending=False).head(5).items()),
         ""]

    def dist(s: pd.Series, name: str) -> str:
        if s.empty:
            return f"    {name:<8} (none)"
        q = s.quantile([0, .1, .5, .9, 1]).values
        return (f"    {name:<8} n {len(s):>7,}   min {q[0]:>10,.1f}   p10 {q[1]:>10,.1f}"
                f"   p50 {q[2]:>10,.1f}   p90 {q[3]:>10,.1f}   max {q[4]:>10,.1f}")

    L += ["THE LAG: ts_recv minus ts_event, seconds", "",
          dist(n["lag_s"], "live"), dist(w["lag_s"], "wild"), ""]
    sep = None
    if not w.empty and not n.empty:
        # The cleanest single cut, if there is one: a lag threshold that keeps
        # most live prints and drops most wild ones.
        best = None
        for thr in (1, 5, 30, 60, 300, 900, 3600):
            keep_live = float((n["lag_s"].abs() <= thr).mean())
            drop_wild = float((w["lag_s"].abs() > thr).mean())
            L.append(f"    |lag| <= {thr:>5}s   keeps {keep_live:6.1%} of live   drops {drop_wild:6.1%} of wild")
            if best is None or keep_live + drop_wild > best[0]:
                best = (keep_live + drop_wild, thr, keep_live, drop_wild)
        sep = best
        L.append("")

    for col in ("flags", "side", "publisher_id", "action"):
        if col in d.columns:
            ct = pd.crosstab(d[col], d["wild"])
            ct.columns = ["live" if not c else "wild" for c in ct.columns]
            L += [f"  {col} against wild:"] + [f"    {line}" for line in ct.to_string().splitlines()] + [""]
    extra = [c for c in d.columns if c not in ("ts_event", "rtype", "publisher_id", "instrument_id", "action",
                                                "side", "depth", "price", "size", "flags", "ts_in_delta",
                                                "sequence", "symbol", "recv_et", "event_et", "lag_s", "wild",
                                                "minute", "hour")]
    if extra:
        L += [f"  other columns present, not analysed: {', '.join(extra)}", ""]

    # Where the wild prints' EXECUTION time falls, if ts_event carries it.
    if not w.empty:
        ev = w["event_et"]
        L += ["WHEN THE WILD PRINTS SAY THEY WERE EXECUTED (ts_event, ET)", "",
              f"    same day 04:00-09:30: {int(((ev.dt.date.astype(str) == day) & (ev.dt.hour >= 4) & (ev.dt.hour < 10)).sum()):,}",
              f"    same day before 04:00: {int(((ev.dt.date.astype(str) == day) & (ev.dt.hour < 4)).sum()):,}",
              f"    an earlier day: {int((ev.dt.date.astype(str) < day).sum()):,}",
              f"    earliest: {ev.min()}   latest: {ev.max()}", ""]

    # Rebuild 08:00-08:40 bars without the candidate prints, beside the archive's.
    if sep is not None and bars is not None and not bars.empty:
        thr = sep[1]
        keep = d[d["lag_s"].abs() <= thr]
        def ohlcv(x):
            g = x.groupby(x["recv_et"].dt.floor("1min"))
            return pd.DataFrame({"open": g["price"].first(), "high": g["price"].max(),
                                 "low": g["price"].min(), "close": g["price"].last(),
                                 "volume": g["size"].sum()})
        raw = ohlcv(d); cln = ohlcv(keep)
        b = bars.copy(); b.index = b.index.tz_convert(ET)
        L += [f"08:00-08:40 REBUILT FROM TRADES, |lag| <= {thr}s KEPT, BESIDE THE ARCHIVE'S BARS", "",
              f"  {'minute':<7}{'arch high':>10}{'arch low':>10}{'arch vol':>10} | {'raw high':>9}{'raw low':>9}{'raw vol':>9} | {'clean high':>11}{'clean low':>10}{'clean vol':>10}"]
        for ts in pd.date_range(f"{day} 08:00", f"{day} 08:40", freq="1min", tz=ET):
            a = b.loc[ts] if ts in b.index else None
            r = raw.loc[ts] if ts in raw.index else None
            c = cln.loc[ts] if ts in cln.index else None
            f = lambda x, k: f"{x[k]:>10,.2f}" if x is not None else f"{'-':>10}"
            fv = lambda x: f"{int(x['volume']):>10,}" if x is not None else f"{'-':>10}"
            L.append(f"  {ts:%H:%M}  {f(a,'high')}{f(a,'low')}{fv(a)} | {f(r,'high')[1:]}{f(r,'low')[1:]}{fv(r)[1:]} | {f(c,'high')} {f(c,'low')}{fv(c)}")
        L += ["", "  If the archive's column matches 'raw' and 'clean' is sane, the archive's",
              "  bars are these trades and the lag cut is the repair. If 'clean' is still",
              "  wild, the lag does not carry the report/execute distinction on this feed.", ""]

    L += ["WHAT THIS DECIDES", "",
          "  Whether a trade-level rebuild of the 426 contaminated sessions is",
          "  possible with the fields this feed carries. If a lag cut separates the",
          "  two populations, the cleaning rule is registerable: state the threshold,",
          "  rebuild the bars for every symbol-day, re-run MCL as published on both",
          "  and print them side by side. If not, the honest test set stays at the",
          "  115 sessions since 2026-03-30.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbol", default="ALTS")
    p.add_argument("--date", default="2025-08-11")
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--archive", default=None)
    p.add_argument("--max-cost", type=float, default=0.25)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common.databento_fetch import _key, _scrub, default_archive
    from common.dbn_io import read_dbn

    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    out_dir = archive / a.dataset / "trades"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"probe_{a.symbol}_{a.date}.dbn.zst"
    start = pd.Timestamp(f"{a.date} 04:00", tz=ET).tz_convert("UTC")
    end = pd.Timestamp(f"{a.date} 09:30", tz=ET).tz_convert("UTC")
    kw = dict(dataset=a.dataset, schema="trades", symbols=[a.symbol], stype_in="raw_symbol",
              start=start.isoformat(), end=end.isoformat())

    if not path.exists():
        import databento as db
        client = db.Historical(_key())
        try:
            cost = float(client.metadata.get_cost(**kw))
        except Exception as e:                              # noqa: BLE001
            sys.exit(f"estimate failed: {_scrub(e)}")
        print(f"trf_probe: {a.symbol} {a.date} trades 04:00-09:30 ET  estimated ${cost:.4f}", flush=True)
        if cost > a.max_cost:
            sys.exit(f"over --max-cost {a.max_cost:.2f}; not spending")
        if not a.confirm:
            print("  add --confirm to pull", flush=True)
            return 0
        try:
            client.timeseries.get_range(**kw, path=str(path))
        except Exception as e:                              # noqa: BLE001
            sys.exit(f"pull failed: {_scrub(e)}")
        print(f"  saved {path}", flush=True)
    else:
        print(f"trf_probe: using {path}", flush=True)

    import databento as db
    st = db.DBNStore.from_file(path)
    df = st.to_df()
    if "symbol" in df.columns:
        df = df[df["symbol"] == a.symbol]
    bars = None
    slice_path = archive / a.dataset / "ohlcv-1m" / f"{a.date}_0400_0930.dbn.zst"
    if slice_path.exists():
        f = read_dbn(slice_path)
        bars = f[f["symbol"] == a.symbol]
    text = "\n".join(analyse(df, bars, a.symbol, a.date))
    emit(text, a.out or f"var/reports/trf_probe_{a.symbol}_{a.date}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
