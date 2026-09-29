#!/usr/bin/env python3
"""W16 DVP-F1 weekly forward scorer: price-then-pull new NQ 1-minute (and
1-day, for the read-back) bars, read them back, run the FROZEN rule (commit
2ff1a15) on newly-completed sessions, append the trades to the forward
ledger, check the two registered early stops, and write a report. Board
W16-0014 subitem 2. REGISTERED_w16_dvp_forward.md.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_forward            # estimate, then STOP
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_forward --confirm  # pull, score, append, report

Meant to be run AT LEAST WEEKLY (sec 2: "pulled at least weekly for the
sessions since the last pull") from 2026-09-29 on. Every run is safe to
repeat: a day already on disk is never re-bought (same discipline as
strategy.w16.fetch/.fetch_trades), and a day already in the ledger's
`scored_dates` is never re-scored -- so running this twice in one week, or
skipping a week and catching up, both land on the same ledger a strict
weekly cadence would have produced.

WHY THIS IS ITS OWN, DAY-PARTITIONED ARCHIVE, NOT strategy.w16.fetch's
------------------------------------------------------------------------
`fetch.py` buys ONE file per (root, schema) covering the whole
2010-06-06..today range -- right for a one-off historical pull, wrong for a
window that grows by a handful of sessions every week: there is no way to
"append" to an existing .dbn.zst file, so a script built on fetch.py's
layout would have to re-buy the entire history every run. This instead
buys one file per (day, schema) -- the same day-partitioned layout
`strategy.w16.fetch_trades` already uses for exactly this reason (its own
module docstring) -- so a weekly run only prices and buys the handful of
days since the last one.

WHY IT PULLS ITS OWN ohlcv-1d TOO, INSTEAD OF REUSING strategy.w16.fetch's
------------------------------------------------------------------------
`fetch.py`'s owned `ohlcv-1d` file was bought once, on 2026-09-27, and ends
there -- it has no bars for 2026-09-29 on. Every session this study reads
is by definition after that file's end, so this module buys its own daily
bar, one file per new day, beside the 1-minute one, and runs the exact same
UTC-calendar-day close comparison `strategy.w16.readback`'s G1 already
does (reusing that module's `run`, not a second implementation of it).

WHY NQ ONLY, NOT ES TOO
--------------------------
sec 2: "Data: Databento GLBX NQ.v.0 ohlcv-1m". DVP-F1 forward-tests the one
rule DVP-v1 scored (NQ only, sec 2 "Instrument: 1 MNQ"); ES was never part
of this line (DVP-v0/v1's sec 3.6 ES rows are reported-only, and DVP-F1
carries none of that forward). Buying ES bars nobody reads would just be
spend with no gate to justify it.

THE FROZEN RULE
------------------
sec 1: `strategy.w16.drift_vwap.generate_dvp_trades(frames, "NQ", dates,
p_ref=None, loss_rule="total", trigger_minutes=5)` at commit 2ff1a15 --
verified unchanged at HEAD (`git diff 2ff1a15 HEAD -- strategy/w16/
drift_vwap.py` is empty, 2026-09-29). This module imports and calls that
function directly, with those exact keyword arguments, rather than
re-deriving them -- sec 1: "No parameter, filter or time window changes
during the test." If a future commit DOES touch drift_vwap.py, that diff
stops being empty, which is the earliest and most literal way this module
could be caught running something other than the frozen rule.

THE LEDGER, holdout_w16_dvp_forward -- NOT A HOLDOUT
------------------------------------------------------
`w16_dvp_forward_ledger.json` (repo root, alongside `holdout_w16_dvp.json`)
is not a holdout cut -- DVP-F1 spends no holdout, it trades data that does
not exist yet (REGISTERED module docstring: "the only fresh evidence left
is data that does not exist yet"). It is an append-only trade log plus the
running cumulative state (scored dates, drawdown, the early-stop flag once
tripped) -- committed to git after every run so the weekly record is
auditable the same way a spent holdout ledger is.

EARLY STOP IS A LATCH, NOT A GATE CHECKED FRESH EACH RUN
------------------------------------------------------------
sec 4: "Either stop ends the test." Once `ledger["stopped"]` is set, this
module refuses to pull or score anything further -- printing the stop and
writing a report from the ledger as it stands, exit code 3 -- rather than
silently continuing (or, worse, un-stopping if a later week's numbers
happened to recover). Ending the test is a one-way door, the same shape as
every other spend-once ledger in this project.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from common.tsmom_data_price import DATASET, require_databento
from common.tsmom_fetch import _is_symbology_miss, _key, _price, _retry, _scrub, default_archive
from strategy.w16 import drift_vwap as D
from strategy.w16 import dvp_runner as DR
from strategy.w16 import preflight as PF
from strategy.w16 import readback as RB
from strategy.w16 import runner as R
from strategy.w16 import sessions as S

MARKET = "NQ"
SYMBOL = "NQ.v.0"
STYPE_IN = "continuous"
SCHEMAS = ("ohlcv-1m", "ohlcv-1d")
ARCHIVE_SUBDIR = "w16_dvp_forward"

FORWARD_START = "2026-09-29"
FORWARD_END = "2027-03-26"
FROZEN_COMMIT = "2ff1a15"
CANDIDATE = "DVP-F1"
LEVEL = "L2"

MIN_TRADES_STOP_A = 150            # sec 4 Stop A: >=150 trades, net <= $0
DD_STOP_B_USD = 3300.00            # sec 4 Stop B: drawdown worse than ($3,300)

MAX_COST = 50.00                   # same ceiling as fetch.py/fetch_trades.py;
                                    # a weekly NQ-only day or two of bars is
                                    # pennies, so hitting this means the
                                    # window widened, not that data got
                                    # expensive.
BOARD = "W16-0014"
REGISTRATION = "docs/research/REGISTERED_w16_dvp_forward.md"

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "w16_dvp_forward_ledger.json"


# ---------------------------------------------------------------------
# archive layout + pricing/pull (day-partitioned, NQ only, two schemas)
# ---------------------------------------------------------------------

def day_path(root_dir: Path, schema: str, day: str) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / schema / f"{day}.dbn.zst"


def manifest_path(root_dir: Path) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / "manifest_w16_dvp_forward.json"


def request(day: str, schema: str, cap: str | None = None) -> dict:
    """The one request shape, in one place. `cap` clips `end` to the
    dataset's real availability instead of day+1's midnight -- see
    `_is_end_after_available` (same convention as strategy.w16.fetch_trades)."""
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    end = f"{nxt}T00:00:00Z"
    if cap is not None and cap < end:
        end = cap
    return dict(dataset=DATASET, schema=schema, symbols=[SYMBOL],
               stype_in=STYPE_IN, start=f"{day}T00:00:00Z", end=end)


def _parse_ts(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _dataset_end_precise(client) -> str:
    """The dataset's actual end TIMESTAMP, fetched lazily and only once a
    "today" day is actually hit -- see strategy.w16.fetch_trades, same
    reasoning."""
    try:
        rng = client.metadata.get_dataset_range(dataset=DATASET)
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    v = rng.get("end") or rng.get("end_date")
    if v is None:
        raise SystemExit("dataset range lookup returned no end")
    return _parse_ts(v).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_end_after_available(e: Exception) -> bool:
    return "data_end_after_available_end" in str(e)


def _is_no_session(e: Exception) -> bool:
    return _is_symbology_miss(e)


def plan(client, root_dir: Path, days: list[str]):
    """Every (day, schema) file that would actually run, its cost, and any
    day Databento reports as having nothing to sell (skipped, not an
    abort) -- same shape as strategy.w16.fetch_trades.plan, widened to two
    schemas per day."""
    jobs, have, no_session = [], 0, []
    usd, nbytes = 0.0, 0
    cap = None
    for day in days:
        day_no_session = False
        for schema in SCHEMAS:
            out = day_path(root_dir, schema, day)
            if out.exists():
                have += 1
                continue
            kw = request(day, schema)
            try:
                u, n = _retry(lambda kw=kw: _price(client, kw))
            except Exception as e:                       # noqa: BLE001
                if _is_no_session(e):
                    day_no_session = True
                    continue
                if _is_end_after_available(e):
                    if cap is None:
                        cap = _dataset_end_precise(client)
                    kw = request(day, schema, cap=cap)
                    if kw["start"] >= kw["end"]:
                        day_no_session = True
                        continue
                    try:
                        u, n = _retry(lambda kw=kw: _price(client, kw))
                    except Exception as e2:               # noqa: BLE001
                        raise SystemExit(
                            f"pricing failed on {day} {schema} (capped at "
                            f"the dataset's real end {cap}) -- nothing "
                            f"downloaded: {_scrub(e2)}")
                else:
                    raise SystemExit(
                        f"pricing failed on {day} {schema} -- nothing "
                        f"downloaded: {_scrub(e)}")
            jobs.append((day, schema, out, kw))
            usd += u
            nbytes += n
        if day_no_session:
            no_session.append(day)
    return jobs, usd, nbytes, have, no_session


def download(client, jobs):
    """The actual get_range + to_file loop, extracted so a caller (main)
    can print progress and a test can pin the writes without re-parsing
    argv. Same "only a finished download takes the real name" guard as
    every other W16 puller."""
    done, failed = [], []
    for day, schema, out, kw in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        try:
            data = _retry(lambda kw=kw: client.timeseries.get_range(**kw))
            data.to_file(tmp)
        except Exception as e:                           # noqa: BLE001
            failed.append((day, schema, _scrub(e)[:80]))
            if tmp.exists():
                tmp.unlink()
            continue
        tmp.replace(out)
        done.append((day, schema, out))
    return done, failed


# ---------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------

def _default_ledger() -> dict:
    return {
        "candidate": CANDIDATE, "market": MARKET, "level": LEVEL,
        "frozen_commit": FROZEN_COMMIT, "forward_start": FORWARD_START,
        "forward_end": FORWARD_END, "registration": REGISTRATION, "board": BOARD,
        "scored_dates": [], "trades": [], "runs": [], "stopped": None,
    }


def read_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return _default_ledger()
    rec = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    for k, v in _default_ledger().items():
        rec.setdefault(k, v)
    return rec


def write_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------
# which sessions are due
# ---------------------------------------------------------------------

def _day_before(day_str: str) -> str:
    return (date.fromisoformat(day_str) - timedelta(days=1)).isoformat()


def candidate_dates(ledger: dict, *, as_of: str) -> list[str]:
    """XNYS trading days in [FORWARD_START, FORWARD_END] that are strictly
    before `as_of` (so a session in progress is never scored on a partial
    day) and not already in the ledger's `scored_dates`. Safe to call every
    week, or after skipping several: it always returns exactly the gap."""
    y0, y1 = int(FORWARD_START[:4]), int(FORWARD_END[:4])
    cutoff = min(FORWARD_END, _day_before(as_of))
    if cutoff < FORWARD_START:
        return []
    scored = set(ledger.get("scored_dates", []))
    return [d for d in S.session_date_range(y0, y1)
           if FORWARD_START <= d <= cutoff and d not in scored]


# ---------------------------------------------------------------------
# read-back (G1, scoped to the new days) + the frozen rule
# ---------------------------------------------------------------------

def _load_1m_from_days(archive: Path, days: list[str]) -> pd.DataFrame:
    from common.dbn_io import read_dbn
    frames = []
    for d in days:
        p = day_path(archive, "ohlcv-1m", d)
        if not p.exists():
            continue
        raw = read_dbn(p)
        df = raw[raw["symbol"] == SYMBOL].copy() if "symbol" in raw.columns else raw.copy()
        if "instrument_id" in df.columns and "held_id" not in df.columns:
            df = df.rename(columns={"instrument_id": "held_id"})
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def _owned_1d_from_days(archive: Path, days: list[str]) -> pd.DataFrame:
    """The daily bar bought alongside the 1-minute one for the same days,
    reduced the same way strategy.w16.readback.owned_daily reduces
    fetch.py's single whole-history file -- multiple day files in, the
    same {date, open, high, low, close, volume} shape out."""
    from common.dbn_io import read_dbn
    frames = []
    for d in days:
        p = day_path(archive, "ohlcv-1d", d)
        if not p.exists():
            continue
        raw = read_dbn(p)
        frames.append(raw[raw["symbol"] == SYMBOL].copy() if "symbol" in raw.columns else raw.copy())
    if not frames:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    d = pd.concat(frames).sort_index()
    d["date"] = (d.index.tz_convert(None) if d.index.tz is not None else d.index).normalize().date
    d = d.drop_duplicates("date", keep="first").sort_values("date")
    cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in d.columns]
    return d[cols].reset_index(drop=True)


def read_back(archive: Path, days: list[str]) -> dict:
    """G1, scoped to just the days this run is about to score -- reuses
    strategy.w16.readback.run so the pass rule (>=99% daily-close
    agreement) is the exact one already tested there, not a second copy."""
    df_1m = _load_1m_from_days(archive, days)
    owned_1d = _owned_1d_from_days(archive, days)
    return RB.run(df_1m, owned_1d)


def score_new_days(archive: Path, days: list[str]) -> tuple[list[dict], dict]:
    """Read back, then run the frozen rule (sec 1) on `days`. Raises
    SystemExit if the read-back gate fails -- sec 0's "stops until
    explained" discipline: a failed gate must never reach the ledger."""
    gate = read_back(archive, days)
    if not gate["passed"]:
        raise SystemExit(
            "G1 read-back FAILED for the new NQ sessions -- "
            f"{gate['daily_agreement']['n_within_tol']}/{gate['daily_agreement']['n_compared']} "
            f"({gate['daily_agreement']['pct_within_tol']:.4%}) within tolerance, "
            f"below the {gate['pass_threshold_pct']:.0%} needed. The ledger is "
            "untouched. REGISTERED_w16_dvp_forward.md sec 0: the study stops "
            "until this is explained.")
    df_1m = _load_1m_from_days(archive, days)
    frames = PF.session_frames(df_1m)
    trades = D.generate_dvp_trades(frames, MARKET, days, p_ref=None,
                                   loss_rule="total", trigger_minutes=5)
    return trades, gate


# ---------------------------------------------------------------------
# cumulative scoring + the two early stops
# ---------------------------------------------------------------------

def cumulative_summary(ledger: dict) -> dict:
    """The whole forward book to date, per 1 MNQ at L2 -- R.price_all reads
    trade["market"]=="NQ" and converts to MNQ via FULL_TO_MICRO the same
    way dvp_v1.py's price_mnq does, so this is the exact scoring convention
    sec 2 registers."""
    priced = R.price_all(ledger.get("trades", []), LEVEL)
    s = R.summarize(priced)
    s["win_rate"] = (s["wins"] / s["n_trades"]) if s["n_trades"] else None
    s["break_even_win_rate"] = DR.break_even_win_rate(s["avg_win"], s["avg_loss"])
    return s


def check_early_stop(summary: dict) -> dict | None:
    """sec 4, checked after every session (in practice: after every run
    that scores at least one new session). Returns the stop record to
    latch into ledger["stopped"], or None if neither has fired yet."""
    n, net, dd = summary["n_trades"], summary["net"], summary["max_drawdown"]
    if n >= MIN_TRADES_STOP_A and net is not None and net <= 0:
        return {"stop": "A", "detail": f"net {net:+.2f} <= $0 after {n} trades (>= {MIN_TRADES_STOP_A})"}
    if dd is not None and dd < -DD_STOP_B_USD:
        return {"stop": "B", "detail": f"drawdown {dd:+.2f} worse than (${DD_STOP_B_USD:,.2f})"}
    return None


# ---------------------------------------------------------------------
# the weekly cycle
# ---------------------------------------------------------------------

def run(archive: Path, *, as_of: str | None = None, client=None,
       confirm: bool = False, max_cost: float = MAX_COST) -> dict:
    """The whole weekly cycle: what's due -> price -> (confirm) pull ->
    read back -> score -> append -> latch a stop if one fires. Returns a
    result dict main() turns into stdout + the report; never writes
    anything on an estimate-only call."""
    ledger = read_ledger()
    as_of = as_of or date.today().isoformat()

    if ledger.get("stopped"):
        return {"as_of": as_of, "already_stopped": True, "stopped": ledger["stopped"],
               "summary": cumulative_summary(ledger), "ledger": ledger}

    days = candidate_dates(ledger, as_of=as_of)
    if not days:
        return {"as_of": as_of, "no_new_sessions": True,
               "summary": cumulative_summary(ledger), "ledger": ledger}

    jobs, usd, nbytes, have, no_session = plan(client, archive, days)
    result = {"as_of": as_of, "days_due": days, "n_jobs": len(jobs),
              "n_have": have, "no_session": no_session,
              "estimated_usd": usd, "estimated_bytes": nbytes}

    if usd > max_cost:
        raise SystemExit(
            f"ABORT: ${usd:.2f} exceeds --max-cost ${max_cost:.2f}. A weekly "
            "NQ-only pull should cost pennies -- this usually means the "
            "forward window widened or the ledger's scored_dates is wrong, "
            "not that data got expensive. Nothing downloaded.")

    if not confirm:
        result["estimate_only"] = True
        result["summary"] = cumulative_summary(ledger)
        return result

    done, failed = download(client, jobs)
    result["n_downloaded"] = len(done)
    result["n_failed"] = len(failed)
    result["failed"] = [f"{d} {s}: {m}" for d, s, m in failed]

    rec = {"pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "days_due": days, "estimated_usd": round(usd, 4),
          "files_pulled": [str(p) for _, _, p in done],
          "files_failed": [f"{d} {s}" for d, s, _ in failed], "no_session": no_session}
    mp = manifest_path(archive)
    mp.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {"runs": []}
    existing.setdefault("runs", []).append(rec)
    mp.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    scorable = [d for d in days
               if all(day_path(archive, sch, d).exists() for sch in SCHEMAS)]
    if not scorable:
        result["nothing_scored"] = True
        result["summary"] = cumulative_summary(ledger)
        return result

    trades, gate = score_new_days(archive, scorable)
    ledger["trades"].extend(trades)
    ledger["scored_dates"] = sorted(set(ledger["scored_dates"]) | set(scorable))
    ledger["runs"].append({
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dates_scored": scorable, "n_trades_new": len(trades),
        "n_trades_live_new": sum(1 for t in trades if not t.get("voided")),
        "gate_passed": gate["passed"], "usd_spent": round(usd, 4),
    })

    summary = cumulative_summary(ledger)
    stop = check_early_stop(summary)
    if stop is not None:
        stop = {**stop, "as_of_date": scorable[-1],
               "n_trades": summary["n_trades"], "net": summary["net"],
               "max_drawdown": summary["max_drawdown"],
               "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        ledger["stopped"] = stop

    write_ledger(ledger)

    result.update({"scored_dates": scorable, "n_trades_new": len(trades),
                   "n_trades_live_new": sum(1 for t in trades if not t.get("voided")),
                   "gate": gate, "summary": summary, "stop": ledger.get("stopped"),
                   "ledger": ledger})
    return result


# ---------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------

def _d(x) -> str:
    if x is None:
        return "n/a"
    return f"(${abs(x):,.2f})" if x < 0 else f"${x:,.2f}"


def txt_report(r: dict) -> str:
    L = [f"=== W16 DVP-F1 -- forward paper test, as of {r['as_of']} ===",
        f"frozen rule: commit {FROZEN_COMMIT}  candidate: {CANDIDATE}  "
        f"window: {FORWARD_START} -> {FORWARD_END}", ""]

    if r.get("already_stopped"):
        st = r["stopped"]
        L.append(f"STOPPED (Stop {st['stop']}) on {st.get('as_of_date', '?')}: {st['detail']}")
        L.append("FAILED FORWARD -- see REGISTERED_w16_dvp_forward.md sec 4. A Result doc is due.")
        L.append("")
    elif r.get("no_new_sessions"):
        L.append(f"No new completed sessions since the last run as of {r['as_of']}.")
        L.append("")
    elif r.get("estimate_only"):
        L.append(f"ESTIMATE ONLY -- {r['n_jobs']} file(s) to price/pull, "
                 f"{r['n_have']} already on disk, {len(r.get('no_session', []))} no-session day(s).")
        L.append(f"days due: {', '.join(r['days_due'])}")
        L.append(f"estimate: ${r['estimated_usd']:.2f}  {r['estimated_bytes']:,} bytes")
        L.append("Nothing downloaded, nothing scored. Re-run with --confirm to spend it.")
        L.append("")
    else:
        L.append(f"scored {len(r.get('scored_dates', []))} new session(s): "
                 f"{', '.join(r.get('scored_dates', []))}")
        L.append(f"new trades: {r.get('n_trades_new', 0)} "
                 f"({r.get('n_trades_live_new', 0)} live, "
                 f"{r.get('n_trades_new', 0) - r.get('n_trades_live_new', 0)} voided)")
        if r.get("failed"):
            L.append(f"FAILED pulls (retry next run): {r['failed']}")
        L.append(f"spent this run: ${r.get('estimated_usd', 0.0):.2f}")
        L.append("")

    s = r.get("summary", {})
    if s:
        wr = f"{s['win_rate']:.1%}" if s.get("win_rate") is not None else "n/a"
        bewr = f"{s['break_even_win_rate']:.1%}" if s.get("break_even_win_rate") is not None else "n/a"
        L.append("--- cumulative book, per 1 MNQ at L2 ---")
        L.append(f"trades: {s.get('n_trades', 0)}  wins: {s.get('wins', 0)}  "
                 f"losses: {s.get('losses', 0)}  win rate: {wr}  break-even: {bewr}")
        L.append(f"gross: {_d(s.get('gross'))}  cost: {_d(s.get('cost'))}  net: {_d(s.get('net'))}")
        L.append(f"avg win: {_d(s.get('avg_win'))}  avg loss: {_d(s.get('avg_loss'))}  "
                 f"largest loss: {_d(s.get('largest_loss'))}")
        L.append(f"max drawdown from peak: {_d(s.get('max_drawdown'))}")
        L.append("")

    stop = r.get("stop")
    if stop and not r.get("already_stopped"):
        L.append(f"*** EARLY STOP {stop['stop']} FIRED THIS RUN: {stop['detail']} ***")
        L.append("FAILED FORWARD -- REGISTERED_w16_dvp_forward.md sec 4. A Result doc is due; "
                 "this scorer will refuse to pull or score anything further.")
        L.append("")

    L.append(f"Stop A watch: net <= $0 once trades >= {MIN_TRADES_STOP_A}.")
    L.append(f"Stop B watch: drawdown worse than {_d(-DD_STOP_B_USD)}.")
    L.append("Paper-order routing (subitem 3): not yet wired -- simulated book only.")
    return "\n".join(L) + "\n"


def default_out_path(as_of: str) -> Path:
    return Path("D:/Trading/Claude outputs") / f"w16_0014_forward_{as_of}.json"


def write_report(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    out.with_suffix(".txt").write_text(txt_report(result), encoding="utf-8")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(
        description="W16-0014 weekly forward scorer for DVP-F1 (frozen rule, commit "
                    f"{FROZEN_COMMIT}). CAN SPEND.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--as-of", default=None,
                    help="override 'today' (YYYY-MM-DD), mainly for testing/reproducibility")
    ap.add_argument("--max-cost", type=float, default=MAX_COST)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--confirm", action="store_true",
                    help="actually pull + score + append to the ledger. Without it, "
                        "this only estimates what is due.")
    a = ap.parse_args(argv)

    archive = a.archive or default_archive()
    as_of = a.as_of or date.today().isoformat()

    if client is None:
        databento = require_databento()
        client = databento.Historical(_key())

    print(f"W16-0014 DVP-F1 forward scorer -- frozen rule commit {FROZEN_COMMIT}, "
         f"candidate {CANDIDATE}\nwindow    {FORWARD_START} -> {FORWARD_END}\n"
         f"as of     {as_of}\ntarget    {Path(archive) / DATASET / ARCHIVE_SUBDIR}/\n"
         f"ledger    {LEDGER_PATH}\n")

    result = run(archive, as_of=as_of, client=client, confirm=a.confirm, max_cost=a.max_cost)
    txt = txt_report(result)
    print(txt)

    out = a.out or default_out_path(as_of)
    write_report(result, out)
    print(f"report: {out}")

    if result.get("already_stopped"):
        return 3
    if not a.confirm:
        return 0
    if result.get("n_failed"):
        print("INCOMPLETE. Re-run: pulled days are on disk and free to skip.")
        return 1
    if result.get("stop"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
