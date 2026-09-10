#!/usr/bin/env python3
"""Push the file artefacts into the database, idempotently.

    python -m common.db_load --backtests var/reports/screened var/state/screened
    python -m common.db_load --minute-bars bar_cache_db
    python -m common.db_load --flex-executions var/flex/*.csv
    python -m common.db_load --compound var/reports/compound_run.csv \
                                        var/reports/compound_sweep.csv

Every table has exactly one flag that fills it; FILLED_BY says which, and a
test fails if a table is ever added without one.

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


def load_executions(conn, execs, source: Path | None = None) -> int:
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
    if source is not None:
        note_load(conn, run_id("flex", "executions", source), "flex_execution",
                  source, len(rows))
    return len(rows)


def load_flex_executions(conn, paths, tz: str | None = None) -> int:
    """Parse the Flex reports and load the fills.

    The parse is not repeated here. common.flex resolves the report's timezone
    by SCORING candidate zones against the fills that cross midnight, and gets a
    different answer in different parts of the year because the US and Australia
    change DST on different dates. Re-deriving an ET minute from the stored
    timestamp with a constant offset would be wrong for part of every year and
    would look right in the table.
    """
    from common import flex as F
    execs = F.load_many([str(p) for p in paths])
    F.measure_offsets(execs, force=tz)
    newest = max(paths, key=lambda p: Path(p).stat().st_mtime)
    return load_executions(conn, execs, Path(newest))


# --- the compounding replay ------------------------------------------------

# The two modes write different columns, and a loader that guessed from the
# filename would load a sweep into the single-run table the first time somebody
# passed --out. The header decides, and an unrecognised one is an error rather
# than a partial load.
RUN_COLS = {"source", "capital", "per_trade_pct", "total_pct", "taken",
            "final", "multiple", "max_drawdown"}
SWEEP_COLS = {"source", "per_trade_pct", "total_pct", "final", "multiple",
              "max_drawdown", "taken", "skipped"}


def load_compound(conn, path: Path) -> tuple[str, str, int]:
    with open(path, newline="") as fh:
        rdr = csv.DictReader(fh)
        head = set(rdr.fieldnames or [])
        rows = list(rdr)
    rid = run_id("compound", path.stem, path)

    if "capital" in head and RUN_COLS <= head:
        kind, table = "compound_run", D.compound_run
        out = [{"run_id": rid, "source": r["source"],
                "run_at": datetime.now(), "capital": _f(r["capital"]),
                "per_trade_pct": _f(r["per_trade_pct"]),
                "total_pct": _f(r["total_pct"]),
                "dv_cap_pct": _f(r.get("dv_cap_pct")),
                "dv_applied": bool(_i(r.get("dv_applied"))),
                "taken": _i(r["taken"]),
                "skipped_concurrency": _i(r.get("skipped_concurrency")),
                "skipped_ruined": _i(r.get("skipped_ruined")),
                "skipped_too_small": _i(r.get("skipped_too_small")),
                "dv_capped": _i(r.get("dv_capped")), "final": _f(r["final"]),
                "multiple": _f(r["multiple"]),
                "max_drawdown": _f(r["max_drawdown"])} for r in rows]
    elif SWEEP_COLS <= head:
        kind, table = "compound_sweep", D.compound_sweep
        out = [{"run_id": rid, "source": r["source"],
                "per_trade_pct": _f(r["per_trade_pct"]),
                "total_pct": _f(r["total_pct"]), "final": _f(r["final"]),
                "multiple": _f(r["multiple"]),
                "max_drawdown": _f(r["max_drawdown"]),
                "taken": _i(r["taken"]), "skipped": _i(r.get("skipped")),
                "dv_capped": _i(r.get("dv_capped"))} for r in rows]
    else:
        raise SystemExit(
            f"{path} is neither a compound run nor a compound sweep.\n"
            f"  columns found: {sorted(head)}\n"
            "  a run needs 'capital'; a sweep needs 'skipped'.\n"
            "  Produce one with: python -m common.compound_sim [--sweep]")

    n = replace(conn, table, "run_id", rid, out)
    note_load(conn, rid, kind, path, n)
    return kind, rid, n


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


def load_minute_bars(conn, root: Path, dataset: str,
                     progress=print) -> tuple[int, int]:
    """One tape's minute bars.

    `dataset` is REQUIRED and is part of the key. EQUS.MINI and XNAS.BASIC hold
    different observations of the same minute -- EQUS.MINI publishes a measured
    median 4.8% of the consolidated tape -- so without it the second load would
    delete the first tape's bars for each symbol and the table would look
    complete while silently holding a mixture, or the wrong one.
    """
    by_sym = cache_files_by_symbol(root)
    total, n_sym = 0, 0
    for sym, paths in by_sym.items():
        rows = minute_rows(paths)
        if not rows:
            continue
        for r in rows:
            r["dataset"] = dataset
        # Per SYMBOL AND DATASET, not per file: one symbol's bars on one tape
        # are replaced together, so an interrupted load resumes by re-running
        # without leaving a half-loaded symbol behind -- and without touching
        # the other tape.
        conn.execute(delete(D.bar_minute).where(
            (D.bar_minute.c.symbol == sym)
            & (D.bar_minute.c.dataset == dataset)))
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


# --- the controls -----------------------------------------------------------

def load_leak_control(conn, path: Path) -> tuple[str, int]:
    """The leakage control's measurements.

    The verdict stays in the text report; these are the figures, so a later run
    can be compared against this one. That comparison is the reason the
    database exists and it is exactly what a .txt cannot do.
    """
    rid = run_id("leak", path.stem, path)
    rows = [{
        "run_id": rid, "strategy": r["strategy"],
        "population": r["population"], "run_at": datetime.now(),
        "days": _i(r.get("days")), "trades": _i(r.get("trades")),
        "days_with_a_trade": _i(r.get("days_with_a_trade")),
        "net": _f(r.get("net")),
        "entries_per_day": _f(r.get("entries_per_day")),
        "share_of_days_traded": _f(r.get("share_of_days_traded")),
        "net_per_day": _f(r.get("net_per_day")),
        "net_per_trade": _f(r.get("net_per_trade")),
    } for r in csv.DictReader(open(path, newline=""))]
    n = replace(conn, D.leak_control, "run_id", rid, rows)
    note_load(conn, rid, "leak_control", path, n)
    return rid, n


def load_holdout(conn, path: Path) -> tuple[str, int]:
    """The committed holdout cut.

    Keyed on the universe fingerprint, so loading the same cut twice is a
    no-op and loading a cut against a DIFFERENT universe leaves both rows
    visible. A holdout that quietly moved is the thing this makes impossible to
    miss.
    """
    rec = json.loads(path.read_text())
    row = {
        "universe_fingerprint": rec["universe_fingerprint"],
        "cut_at": _ts(rec.get("cut_at")),
        "lock_from": _date(rec["lock_from"]),
        "both_halves_split": _date(rec["both_halves_split"]),
        "train_first": _date(rec["train_first"]),
        "train_last": _date(rec["train_last"]),
        "lock_fraction": _f(rec.get("lock_fraction")),
        "n_sessions": _i(rec.get("n_sessions")),
        "n_train": _i(rec.get("n_train")),
        "n_locked": _i(rec.get("n_locked")),
        "n_early": _i(rec.get("n_early")),
        "n_late": _i(rec.get("n_late")),
        "note": (rec.get("note") or "")[:512],
    }
    conn.execute(delete(D.holdout_cut).where(
        D.holdout_cut.c.universe_fingerprint == row["universe_fingerprint"]))
    conn.execute(insert(D.holdout_cut), [row])
    note_load(conn, run_id("holdout", rec["universe_fingerprint"][:12], path),
              "holdout_cut", path, 1,
              f"locked from {rec['lock_from']}, {rec['n_locked']} sessions")
    return rec["universe_fingerprint"], 1


def load_orb_preflight(conn, path: Path, dataset: str) -> int:
    """The per-symbol-day ORB measurements.

    The report renders distributions; these are the rows behind them, so a
    later question -- what does the R distribution look like above $5, do thin
    opens cluster on particular dates -- is a query rather than a re-run over
    25,769 symbol-days.
    """
    def b(v):
        s = str(v).strip().lower()
        return None if s in ("", "none") else s in ("true", "1")

    rows = []
    for r in csv.DictReader(open(path, newline="")):
        rows.append({
            "dataset": dataset, "symbol": r["symbol"],
            "session_date": _date(r["date"]),
            "orb_minutes": _i(r["orb_minutes"]),
            "population": r.get("population"), "status": r.get("status"),
            "range_bars": _i(r.get("range_bars")),
            "rth_bars": _i(r.get("rth_bars")),
            "orb_high": _f(r.get("orb_high")), "orb_low": _f(r.get("orb_low")),
            "width_pct": _f(r.get("width_pct")),
            "orb_volume": _f(r.get("orb_volume")),
            "price_at_range_end": _f(r.get("price_at_range_end")),
            "change_from_open_pct": _f(r.get("change_from_open_pct")),
            "in_price_band": b(r.get("in_price_band")),
            "passes_rth_move": b(r.get("passes_rth_move")),
            "up_trigger": b(r.get("up_trigger")),
            "down_trigger": b(r.get("down_trigger")),
            "up_trigger_bar": _i(r.get("up_trigger_bar")),
            "up_close_over_pct": _f(r.get("up_close_over_pct")),
            "near_level": b(r.get("near_level")),
            "retest_touch": b(r.get("retest_touch")),
            "retest_zone": b(r.get("retest_zone")),
            "entry_px": _f(r.get("entry_px")),
            "r_structure_pct": _f(r.get("r_structure_pct")),
            "r_opposite_pct": _f(r.get("r_opposite_pct")),
            "r_rangefrac_pct": _f(r.get("r_rangefrac_pct")),
            "bars_to_2r": _i(r.get("bars_to_2r")),
            "bars_to_stop": _i(r.get("bars_to_stop"))})
    conn.execute(delete(D.orb_preflight).where(
        D.orb_preflight.c.dataset == dataset))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(D.orb_preflight), rows[i:i + BATCH])
    note_load(conn, run_id("orb", dataset, path), "orb_preflight", path,
              len(rows))
    return len(rows)


# --- the paper sessions ----------------------------------------------------

def _et_naive(v):
    """A fill log's ts_et: an ET WALL CLOCK, stored naive.

    Deliberately NOT _ts(), which normalises to UTC. Passing an ET string
    through a UTC normaliser is harmless only while the string stays naive --
    the moment one carries an offset it would be converted and stored, under a
    column called ts_et, on a different clock from every row beside it. Two
    clocks in one column is not a thing a query can detect, so this refuses
    instead.
    """
    if not v:
        return None
    try:
        t = datetime.strptime(str(v).strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return t


def load_paper_fills(conn, paths) -> tuple[int, list[str]]:
    """The live trader's own fill logs -- var/fills/*_fills_YYYYMMDD.csv.

    THE SESSION IS THE UNIT, NOT THE FILE. See db.paper_fill's own note: a fill
    log grows while the session is live, so keying on path+mtime the way every
    other loader does would double-count every row of a mid-session load. This
    deletes each session_date it is about to write and then writes it.

    session_date comes from the ROWS, not the filename. The filename is the
    trader's convention and nothing enforces it; ts_et is what the row actually
    happened at. A file holding two dates -- a log that was appended across a
    restart -- then lands each row in its own session instead of all of them
    under whichever date the filename claimed.
    """
    rows, seen, files = [], set(), []
    now = datetime.now()
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        files.append(path.name)
        with path.open(newline="") as fh:
            for r in csv.DictReader(fh):
                ts = _et_naive(r.get("ts_et"))
                if ts is None:
                    # A row with no usable timestamp cannot be keyed and cannot
                    # be de-duplicated. Dropping it is right; dropping it
                    # SILENTLY is not, so it is counted and reported.
                    continue
                d = ts.date()
                seen.add(d)
                rows.append({
                    "session_date": d, "ts_et": ts,
                    "strategy": (r.get("strategy") or "MCL")[:24],
                    "symbol": (r.get("symbol") or "")[:24],
                    "action": (r.get("action") or "")[:8],
                    "status": (r.get("status") or "")[:32],
                    "reason": (r.get("reason") or "")[:32],
                    "ref_close": _f(r.get("ref_close")),
                    "ref_kind": (r.get("ref_kind") or "")[:24],
                    "bid": _f(r.get("bid")), "ask": _f(r.get("ask")),
                    "spread": _f(r.get("spread")),
                    "spread_pct": _f(r.get("spread_pct")),
                    "limit_sent": _f(r.get("limit_sent")),
                    "qty": _i(r.get("qty")),
                    "fill_price": _f(r.get("fill_price")),
                    "filled_qty": _i(r.get("filled_qty")),
                    "slippage_vs_ref": _f(r.get("slippage_vs_ref")),
                    "seconds_to_fill": _f(r.get("seconds_to_fill")),
                    "entry_price": _f(r.get("entry_price")),
                    "exit_price": _f(r.get("exit_price")),
                    "trade_pnl": _f(r.get("trade_pnl")),
                    "trade_pct": _f(r.get("trade_pct")),
                    "hold_minutes": _f(r.get("hold_minutes")),
                    "reject_reason": (r.get("reject_reason") or "")[:255],
                    "macd": _f(r.get("macd")), "macd_sig": _f(r.get("macd_sig")),
                    "mfi": _f(r.get("mfi")), "rsi": _f(r.get("rsi")),
                    "vol": _f(r.get("vol")), "prev_vol": _f(r.get("prev_vol")),
                    "trail_avg": _f(r.get("trail_avg")),
                    "source_file": path.name[:255], "loaded_at": now})

    # DE-DUPLICATE WITHIN THE BATCH, on the primary key. Two files can overlap:
    # FillLog rolls a log aside as <name>_preHHMMSS.csv when its header changes,
    # and a glob picks up both. Inserting a duplicate key is an IntegrityError
    # that aborts the whole load -- after the DELETE has already run, which
    # would leave the session EMPTY rather than unchanged.
    KEY = ("session_date", "ts_et", "strategy", "symbol", "action", "status")
    unique, dropped = {}, 0
    for r in rows:
        k = tuple(r[c] for c in KEY)
        if k in unique:
            dropped += 1
        unique[k] = r
    rows = list(unique.values())

    for d in sorted(seen):
        conn.execute(delete(D.paper_fill)
                     .where(D.paper_fill.c.session_date == d))
    for i in range(0, len(rows), BATCH):
        conn.execute(insert(D.paper_fill), rows[i:i + BATCH])
    if files:
        newest = max((Path(p) for p in paths if Path(p).exists()),
                     key=lambda p: p.stat().st_mtime)
        note_load(conn, run_id("paper", "fills", newest), "paper_fill",
                  newest, len(rows),
                  f"{len(seen)} session(s), {len(files)} file(s)"
                  + (f", {dropped} duplicate row(s) collapsed" if dropped else ""))
    return len(rows), sorted(str(d) for d in seen)


# --- which flag fills which table ------------------------------------------

# THE POINT OF THIS MAP IS THE TEST THAT READS IT. Three tables shipped that
# nothing could ever fill -- flex_execution had a loader no CLI path called,
# and the two compound tables had no loader at all. They were not empty because
# nobody had run the load; they were empty because there was no load to run,
# and an empty table looks identical either way. A table with no way in is a
# claim the database makes and cannot honour.
FILLED_BY = {
    "screen_run": "--screen",
    "screen_candidate": "--screen",
    "flex_round_trip": "--flex",
    "flex_execution": "--flex-executions",
    "backtest_run": "--backtests",
    "backtest_trade": "--backtests",
    "backtest_coverage": "--backtests",
    "day_dollar_volume": "--dollar-volume",
    "bar_minute": "--minute-bars",
    "orb_preflight": "--orb-preflight",
    "bar_daily": "--daily-bars",
    "compound_run": "--compound",
    "compound_sweep": "--compound",
    "leak_control": "--leak",
    "holdout_cut": "--holdout",
    "paper_fill": "--paper-fills",
    "load_run": "--screen",     # written by note_load on every load     # written by note_load on every load
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Load file artefacts into SQL Server")
    ap.add_argument("--url")
    ap.add_argument("--screen", nargs=2, metavar=("SURVIVORS.json", "REJECTS.json"))
    ap.add_argument("--flex", metavar="ROUND_TRIPS.csv")
    ap.add_argument("--flex-executions", nargs="+", metavar="FLEX.csv",
                    help="the raw IBKR Flex EXECUTION-level report(s)")
    ap.add_argument("--tz", default=None,
                    help="force the Flex report timezone (see common.flex --tz-report)")
    ap.add_argument("--paper-fills", nargs="+", metavar="FILLS.csv",
                    help="the live trader's own fill logs, var/fills/*.csv. "
                         "Safe to run mid-session and again at the end: the "
                         "SESSION is replaced, not appended.")
    ap.add_argument("--compound", nargs="+", metavar="CSV",
                    help="compound_run.csv and/or compound_sweep.csv")
    ap.add_argument("--leak", metavar="LEAK_CONTROL.csv")
    ap.add_argument("--holdout", nargs="?", const="holdout.json",
                    metavar="HOLDOUT.json",
                    help="the committed cut (default: holdout.json)")
    ap.add_argument("--backtests", nargs=3,
                    metavar=("REPORTS_DIR", "STATES_DIR", "UNIVERSE"))
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--dollar-volume", metavar="CSV")
    ap.add_argument("--minute-bars", nargs=2,
                    metavar=("CACHE_ROOT", "DATASET"),
                    help="the bar cache and the tape it was built from -- the "
                         "dataset is part of the key, see db.bar_minute")
    ap.add_argument("--orb-preflight", nargs=2,
                    metavar=("PREFLIGHT.csv", "DATASET"))
    ap.add_argument("--daily-bars", nargs=2, metavar=("ARCHIVE", "DATASET"))
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)

    eng = D.engine(a.url)
    D.create_all(eng)
    with eng.begin() as conn:
        if a.screen:
            rid, n = load_screen(conn, Path(a.screen[0]), Path(a.screen[1]), {})
            print(f"screen        {n:,} rows   {rid}")
        if a.flex:
            got = load_flex(conn, None, Path(a.flex))
            print(f"round trips   {got.get('round_trips', 0):,}")
        if a.flex_executions:
            n = load_flex_executions(conn, [Path(p) for p in a.flex_executions],
                                     tz=a.tz)
            print(f"executions    {n:,} fills")
        if a.paper_fills:
            n, days = load_paper_fills(conn, [Path(x) for x in a.paper_fills])
            print(f"paper fills   {n:,} rows over {len(days)} session(s)"
                  + (f"   {days[0]}..{days[-1]}" if days else ""))
        if a.compound:
            for p in a.compound:
                kind, rid, n = load_compound(conn, Path(p))
                print(f"{kind:<13} {n:,} rows   {rid}")
        if a.leak:
            rid, n = load_leak_control(conn, Path(a.leak))
            print(f"leak control  {n:,} rows   {rid}")
        if a.holdout:
            fp, n = load_holdout(conn, Path(a.holdout))
            print(f"holdout cut   fingerprint {fp[:16]}...")
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
            root, ds = Path(a.minute_bars[0]), a.minute_bars[1]
            if not (root / "3d_to_2000").exists() and root.name != "3d_to_2000":
                print(f"no 3d_to_2000 window under {root}")
            else:
                w = root if root.name == "3d_to_2000" else root / "3d_to_2000"
                n_sym, n = load_minute_bars(conn, w, ds)
                print(f"minute bars   {n:,} rows over {n_sym:,} symbols  ({ds})")
        if a.orb_preflight:
            n = load_orb_preflight(conn, Path(a.orb_preflight[0]),
                                   a.orb_preflight[1])
            print(f"orb preflight {n:,} rows   ({a.orb_preflight[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
