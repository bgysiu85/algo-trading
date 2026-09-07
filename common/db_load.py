#!/usr/bin/env python3
"""Push the file artefacts into the database, idempotently.

    python -m common.db_load --all
    python -m common.db_load --backtests var/reports/screened var/state/screened
    python -m common.db_load --minute-bars bar_cache_db

WHY IDEMPOTENT IS THE WHOLE DESIGN
-----------------------------------
A loader that appends turns "I re-ran that" into duplicated rows and doubled
sums, and nothing about the result looks wrong: the tables are still valid, the
queries still return, the numbers are just twice what they should be. So every
artefact carries a run_id derived from its source path and that file's
modification time, and a load DELETES that run_id before inserting it.

Re-running a load is then a no-op. Loading a file that has changed replaces its
rows and leaves the older run alone, which is the property that makes "compare
two runs" possible at all -- something the files themselves never allowed,
because each run overwrote the last.

WHAT A run_id IS
-----------------
    <kind>:<name>:<file mtime, to the second>

Deterministic, so the same file always lands on the same run_id, and legible,
so a row in a result set says where it came from without a join.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, insert

from common import db as D

BATCH = 5_000


def run_id(kind: str, name: str, path: Path) -> str:
    mt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return f"{kind}:{name}:{mt.strftime('%Y%m%dT%H%M%S')}"


def _date(v):
    if not v:
        return None
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _ts(v):
    """A timestamp column, tz-stripped.

    SQL Server's DATETIME has no zone, so a tz-aware value would either be
    rejected or silently truncated depending on the driver. Everything is
    normalised to UTC first and stored naive, and the column names say utc so
    nobody has to guess later.
    """
    if not v:
        return None
    import pandas as pd
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.to_pydatetime()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return None if f is None else int(f)


def replace(conn, table, key_col, key, rows) -> int:
    """Delete one run's rows, then insert its replacements."""
    conn.execute(delete(table).where(table.c[key_col] == key))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(table), rows[i:i + BATCH])
    return len(rows)


def note_load(conn, rid, kind, path: Path, rows, notes=""):
    conn.execute(delete(D.load_run).where(D.load_run.c.run_id == rid))
    conn.execute(insert(D.load_run), [{
        "run_id": rid, "kind": kind, "source_path": str(path),
        "source_mtime": datetime.fromtimestamp(path.stat().st_mtime),
        "loaded_at": datetime.now(), "rows": rows, "notes": notes[:512]}])


# --- the screen ------------------------------------------------------------

def load_screen(conn, survivors: Path, rejects: Path | None, params: dict):
    rid = run_id("screen", params.get("dataset", "?"), survivors)
    rows = []
    for p in json.load(open(survivors)):
        rows.append({"run_id": rid, "symbol": p["symbol"],
                     "session_date": _date(p["date"]), "is_reject": False})
    n_rej = 0
    if rejects and rejects.exists():
        for p in json.load(open(rejects)):
            rows.append({"run_id": rid, "symbol": p["symbol"],
                         "session_date": _date(p["date"]), "is_reject": True})
            n_rej += 1
    conn.execute(delete(D.screen_run).where(D.screen_run.c.run_id == rid))
    conn.execute(insert(D.screen_run), [{
        "run_id": rid, "run_at": datetime.now(),
        "n_candidates": len(rows) - n_rej, "n_rejects": n_rej, **params}])
    n = replace(conn, D.screen_candidate, "run_id", rid, rows)
    note_load(conn, rid, "screen", survivors, n,
              f"{len(rows)-n_rej} candidates, {n_rej} rejects")
    return rid, n


# --- real trades -----------------------------------------------------------

def load_flex(conn, summary: Path | None, round_trips: Path | None,
              executions=None):
    out = {}
    if round_trips and round_trips.exists():
        rid = run_id("flex", "round_trips", round_trips)
        seq, rows = {}, []
        for r in csv.DictReader(open(round_trips, newline="")):
            k = (r["symbol"], r["date"])
            seq[k] = seq.get(k, 0) + 1
            rows.append({
                "symbol": r["symbol"], "trade_date": _date(r["date"]),
                "seq": seq[k], "entry_et": r.get("entry_et") or None,
                "exit_et": r.get("exit_et") or None,
                "fills": _i(r.get("fills")), "shares": _f(r.get("shares")),
                "max_position": _i(r.get("max_position")),
                "avg_buy_price": _f(r.get("avg_buy_price")),
                "avg_sell_price": _f(r.get("avg_sell_price")),
                "gross_pnl": _f(r.get("gross_pnl")),
                "commission": _f(r.get("commission")),
                "net_pnl": _f(r.get("net_pnl")),
                "open_at_end": bool(_i(r.get("open_at_end")))})
        # Natural key, no run column: these are Ben's actual positions and
        # there is only ever one true answer for a given symbol-day. A rerun
        # replaces the lot rather than accumulating a second opinion.
        conn.execute(delete(D.flex_round_trip))
        for i in range(0, len(rows), BATCH):
            conn.execute(insert(D.flex_round_trip), rows[i:i + BATCH])
        note_load(conn, rid, "flex_round_trip", round_trips, len(rows))
        out["round_trips"] = len(rows)
    return out


def load_executions(conn, execs) -> int:
    """From common.flex Execution objects, so the timezone work is not redone."""
    rows = [{
        "trade_id": e.trade_id, "symbol": e.symbol,
        "trade_date": _date(e.trade_date), "dt_utc": _ts(e.dt_raw),
        "et_minute": e.et_minute, "qty": float(e.qty), "price": float(e.price),
        "commission": float(e.commission), "fifo_pnl": float(e.fifo_pnl),
        "side": e.side, "time_known": bool(e.time_known)} for e in execs]
    conn.execute(delete(D.flex_execution))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(D.flex_execution), rows[i:i + BATCH])
    return len(rows)


# --- backtests -------------------------------------------------------------

def load_backtest(conn, reports: Path, states: Path, strategy: str,
                  universe: str, meta: dict | None = None):
    trades_p = reports / f"backtest_trades_{strategy}.csv"
    state_p = states / f"backtest_state_{strategy}.json"
    if not trades_p.exists():
        return None, 0
    rid = run_id("backtest", f"{universe}:{strategy}", trades_p)

    rows = []
    for i, r in enumerate(csv.DictReader(open(trades_p, newline="")), start=1):
        rows.append({
            "run_id": rid, "seq": i, "symbol": r["symbol"],
            "session_date": _date(r["date"]),
            "entry_ts": _ts(r.get("entry_time")),
            "exit_ts": _ts(r.get("exit_time")),
            "entry_price": _f(r.get("entry_price")),
            "exit_price": _f(r.get("exit_price")), "qty": _i(r.get("qty")),
            "reason": (r.get("reason") or "")[:32],
            "bars_held": _i(r.get("bars_held")), "gross": _f(r.get("gross")),
            "commission": _f(r.get("commission")), "net": _f(r.get("net")),
            "cycles": _i(r.get("cycles")),
            "shares_traded": _i(r.get("shares_traded")),
            "adds": _i(r.get("adds")), "max_qty": _i(r.get("max_qty")),
            "timeframe": _i(r.get("timeframe")),
            "setup_kind": (r.get("setup_kind") or "")[:32] or None,
            "trade_exit_mode": (r.get("exit_mode") or "")[:24] or None,
            "r_multiple": _f(r.get("r_multiple")),
            "session_block": (r.get("session_block") or "")[:24] or None})

    cov = []
    if state_p.exists():
        try:
            done = (json.loads(state_p.read_text()).get("done") or {})
        except json.JSONDecodeError:
            done = {}
        for key, rec in done.items():
            sym, _, day = key.partition("|")
            if not day:
                continue
            cov.append({"run_id": rid, "symbol": sym, "session_date": _date(day),
                        "status": str(rec.get("status"))[:24],
                        "bars": _i(rec.get("bars")),
                        "session_bars": _i(rec.get("session_bars")),
                        "trades": _i(rec.get("trades")),
                        "net": _f(rec.get("net"))})

    conn.execute(delete(D.backtest_run).where(D.backtest_run.c.run_id == rid))
    conn.execute(insert(D.backtest_run), [{
        "run_id": rid, "run_at": datetime.now(), "strategy": strategy,
        "universe": universe, "n_trades": len(rows), "n_pairs": len(cov),
        **(meta or {})}])
    replace(conn, D.backtest_trade, "run_id", rid, rows)
    replace(conn, D.backtest_coverage, "run_id", rid, cov)
    note_load(conn, rid, "backtest", trades_p, len(rows),
              f"{len(cov)} coverage rows from {state_p.name}")
    return rid, len(rows)


# --- market data -----------------------------------------------------------

def load_dollar_volume(conn, path: Path) -> int:
    rows = [{"symbol": r["symbol"], "session_date": _date(r["date"]),
             "close": _f(r.get("close")), "volume": _i(r.get("volume")),
             "dollar_volume": _f(r.get("dollar_volume"))}
            for r in csv.DictReader(open(path, newline=""))]
    conn.execute(delete(D.day_dollar_volume))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(D.day_dollar_volume), rows[i:i + BATCH])
    note_load(conn, run_id("dollar_volume", "all", path), "dollar_volume",
              path, len(rows))
    return len(rows)


def cache_files_by_symbol(root: Path) -> dict:
    """{symbol: [paths]} for a bar cache window directory."""
    out: dict[str, list[Path]] = {}
    for p in sorted(root.glob("*.csv.gz")):
        sym = p.name.rsplit("_", 1)[0]
        out.setdefault(sym, []).append(p)
    return out


def minute_rows(paths) -> list[dict]:
    """Every distinct minute bar across one symbol's cache windows.

    THE DEDUPLICATION IS NOT AN OPTIMISATION. Each file holds three sessions
    ending on its own date, so consecutive files for one symbol share two of
    them. Loaded file by file, every bar would be stored about three times, and
    a SUM(volume) over the table would read three times the market's volume
    while looking entirely reasonable.
    """
    import pandas as pd
    seen: dict = {}
    sym = paths[0].name.rsplit("_", 1)[0] if paths else ""
    for p in paths:
        with gzip.open(p, "rt") as fh:
            df = pd.read_csv(fh, index_col=0, parse_dates=[0])
        if df.empty:
            continue
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        idx = idx.tz_convert("UTC").tz_localize(None)
        for ts, r in zip(idx.to_pydatetime(), df.itertuples(index=False)):
            seen[ts] = {"symbol": sym, "ts_utc": ts,
                        "open": _f(getattr(r, "open", None)),
                        "high": _f(getattr(r, "high", None)),
                        "low": _f(getattr(r, "low", None)),
                        "close": _f(getattr(r, "close", None)),
                        "volume": _i(getattr(r, "volume", None))}
    return [seen[k] for k in sorted(seen)]


def load_minute_bars(conn, root: Path, progress=print) -> tuple[int, int]:
    by_sym = cache_files_by_symbol(root)
    total, n_sym = 0, 0
    for sym, paths in by_sym.items():
        rows = minute_rows(paths)
        if not rows:
            continue
        # Per SYMBOL, not per file: one symbol's bars are replaced together,
        # so an interrupted load can be resumed by re-running without leaving
        # a half-loaded symbol behind.
        conn.execute(delete(D.bar_minute).where(D.bar_minute.c.symbol == sym))
        for i in range(0, len(rows), BATCH):
            conn.execute(insert(D.bar_minute), rows[i:i + BATCH])
        total += len(rows)
        n_sym += 1
        if progress and n_sym % 100 == 0:
            progress(f"  {n_sym:,}/{len(by_sym):,} symbols  {total:,} bars")
    return n_sym, total


def load_daily_bars(conn, archive: Path, dataset: str) -> int:
    from common.dbn_io import daily_frame
    df = daily_frame(archive, dataset)
    if df.empty:
        return 0
    rows = [{"dataset": dataset, "symbol": r.symbol,
             "session_date": _date(r.date), "open": _f(r.open),
             "high": _f(r.high), "low": _f(r.low), "close": _f(r.close),
             "volume": _i(r.volume),
             "dollar_volume": _f(r.close) * _f(r.volume)
             if r.close and r.volume else None}
            for r in df.itertuples(index=False)]
    conn.execute(delete(D.bar_daily).where(D.bar_daily.c.dataset == dataset))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(D.bar_daily), rows[i:i + BATCH])
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Load file artefacts into SQL Server")
    ap.add_argument("--url")
    ap.add_argument("--screen", nargs=2, metavar=("SURVIVORS.json", "REJECTS.json"))
    ap.add_argument("--flex", metavar="ROUND_TRIPS.csv")
    ap.add_argument("--backtests", nargs=3,
                    metavar=("REPORTS_DIR", "STATES_DIR", "UNIVERSE"))
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--dollar-volume", metavar="CSV")
    ap.add_argument("--minute-bars", metavar="CACHE_ROOT")
    ap.add_argument("--daily-bars", nargs=2, metavar=("ARCHIVE", "DATASET"))
    a = ap.parse_args(argv)

    eng = D.engine(a.url)
    D.create_all(eng)
    with eng.begin() as conn:
        if a.screen:
            rid, n = load_screen(conn, Path(a.screen[0]), Path(a.screen[1]), {})
            print(f"screen        {n:,} rows   {rid}")
        if a.flex:
            got = load_flex(conn, None, Path(a.flex))
            print(f"round trips   {got.get('round_trips', 0):,}")
        if a.dollar_volume:
            print(f"dollar volume {load_dollar_volume(conn, Path(a.dollar_volume)):,}")
        if a.backtests:
            reports, states, universe = a.backtests
            for s in a.strategy:
                rid, n = load_backtest(conn, Path(reports), Path(states), s,
                                       universe)
                print(f"backtest {s:<8} {n:,} trades   {rid or '(absent)'}")
        if a.daily_bars:
            arch, ds = a.daily_bars
            print(f"daily bars    {load_daily_bars(conn, Path(arch), ds):,}  ({ds})")
        if a.minute_bars:
            root = Path(a.minute_bars)
            if not (root / "3d_to_2000").exists() and root.name != "3d_to_2000":
                print(f"no 3d_to_2000 window under {root}")
            else:
                w = root if root.name == "3d_to_2000" else root / "3d_to_2000"
                n_sym, n = load_minute_bars(conn, w)
                print(f"minute bars   {n:,} rows over {n_sym:,} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
