#!/usr/bin/env python3
"""W15-0037 sub 2 -- CHARTMARK-v2 F1 weekly forward scorer (the scored book). REGISTERED_chartmark_v2_forward.md.

    python -m strategy.chartmark_v2.forward            # freeze check + estimate of what is due, then STOP (nothing bought, nothing written)
    python -m strategy.chartmark_v2.forward --confirm  # pull, read back, regression gate, score, append to the ledger, report

Runs the FROZEN engine (strategy.chartmark_v2.engine / spec at commit f3872ff) for K1, V-SESSION and V-WICKGATE on new CL 1H bars
(Databento GLBX.MDP3 CL.c.0, day-partitioned, the W16 dvp_forward pattern). Scored sessions: 2026-10-01 .. 2027-09-30.

HOW A WEEK IS SCORED (and why a session is never re-scored)
  Every run rebuilds the frame (warm-up + every forward day on disk), runs engine.simulate(start = first forward bar) from the FIXED
  start, and keeps only trades that have CLOSED (exit bar known; an open position is reported, marked to the last close, and never
  ledgered). Closed trades are appended to forward_chartmark_v2.json. The engine is deterministic and causal, so the closed trades
  of a longer frame contain the closed trades of a shorter one as a prefix (truncation invariance, tested). Before anything is
  appended, the ledger's existing trades must be reproduced EXACTLY by the new simulation (same entry bar, exit bar, reason, arm,
  rolls, points to half a tick); any difference refuses the run and leaves the ledger untouched. Nothing recorded can be re-scored.

GATES, in order (each refuses, none warns)
  G-freeze      strategy/chartmark_v2/engine.py and spec.py byte-identical to FROZEN_COMMIT in the working tree and HEAD.
  G-regression  (scoring runs only) the engine, run on the 2016-2021 training frame, reproduces step C's K1 trade list exactly
                (317 trades, same entry/exit bars, prices to the tick) and, on the seen-window CSV, Amendment 5.4's 69 trades / +2.29 pts.
  G-readback    the forward days' hourly bars agree with Databento ohlcv-1d closes within 1 tick on >= 99% of UTC days; gap hours listed.
  G-contiguous  only the unbroken run of forward days on disk is scored (a missing or deferred day stops the cutoff there).

EARLY STOPS (per rule, latched, evaluated trade by trade so the result does not depend on how often this runs)
  Stop A: after >= 30 closed trades, net at mid <= ($1,000) per MCL.   Stop B: drawdown from peak at mid worse than ($2,300).
  There is no early pass. If K1 stops, the ledger says paper_orders = STOPPED and the runner must read that flag.

INTERPRETATIONS FIXED HERE, BEFORE ANY FORWARD BAR WAS SCORED (PRE-RUN; written up in the handover)
  JF1 Warm-up: the archive is NOT read. Indicator warm-up comes from one Databento pull of CL.c.0 1H bars for sessions from
      WARMUP_FIRST_SESSION (2026-06-01) up to the first forward day. EMAs/ATR/MACD converge in far fewer bars than that, and the
      2022-2025 holdout region never enters a frame. Registration sec 2 says "archive plus the forward bars"; the difference is
      warm-up provenance only, not a rule.
  JF2 Complete sessions: UTC day D is pulled only when D < today (UTC) and the dataset's end is past D+1 00:00Z. Session S is scored
      once UTC day S (which holds its last bar) is on disk; sessions after the cutoff are cut from the frame by session label.
  JF3 Stops and ledger use CLOSED trades only (an open trade's worst case is the $0.60 backstop, about $60).
  JF4 C3 "while flat": each drawn entry must not overlap an already accepted random trade (entry..exit bars); pool = every forward bar
      (V-SESSION: bars opening 02:00-12:00 NY); exits = the rule's own backstop + EMA21 walk; 1,000 draws, registered seed.
  JF5 At the window end a still-open position is closed at the last close and ledgered as WINDOW_END (J11). The F7 extension to
      2027-12-31 is NOT implemented here: if a rule has < 50 trades on 2027-09-30 it needs a POST-RUN amendment and a small change.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zlib import crc32

import numpy as np
import pandas as pd

from strategy.chartmark import book as BK
from strategy.chartmark.data import Frame, Ind, indicators, load_seen_frame, load_training_frame, make_frame
from strategy.chartmark_v2 import confirm_c as CC
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S
from strategy.htf import bars as HB
from strategy.htf import book as HBK
from strategy.htf import readback as RB

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "forward_chartmark_v2.json"
OUT = ROOT / "Claude outputs"
REF_STEPC = Path(__file__).resolve().parent / "ref_stepC_k1_trades.csv"
SEEN_CSV = ROOT / "Claude outputs" / "w15_0032_cl1_1h_bars_indicators.csv"

BOARD = "W15-0037"
REGISTRATION = "docs/research/REGISTERED_chartmark_v2_forward.md"
FROZEN_COMMIT = "f3872ff"
STRICT_PATHS = ("strategy/chartmark_v2/engine.py", "strategy/chartmark_v2/spec.py")
SHARED_PATHS = ("strategy/chartmark/spec.py", "strategy/htf/bars.py", "strategy/futbt/loading.py")   # regression-gated, may change

FIRST_BAR_ET = "2026-09-30 18:00"          # first scored bar (session 2026-10-01)
FIRST_SESSION = "2026-10-01"
WINDOW_END = "2027-09-30"                  # last scored CME session
WARMUP_FIRST_SESSION = "2026-06-01"
WARMUP_FIRST_UTC_DAY = "2026-05-31"        # 18:00 ET on 31 May opens session 1 June
FIRST_UTC_DAY = "2026-09-30"               # first per-day file (holds the first forward bars, 22:00Z)
HALF_1_LAST = "2027-03-31"                 # F5 halves by entry session date

STEPC_TRADES = 317                         # regression gate: step C's K1 trade count (2016-2021)
SEEN_TRADES, SEEN_GROSS_PTS = 69, 2.29     # regression gate: Amendment 5.4 seen-window K1

STOP_A_MIN_TRADES, STOP_A_NET = 30, -1000.0
STOP_B_DD = 2300.0
DRAWS = 1000
C3_LABEL = b"CL-v2-F1"
READBACK_TOL, READBACK_PASS = 0.01, 0.99   # 1 tick, 99% of sessions (registration sec 2)
MAX_COST = 5.00

RULES = {"K1": S.K1,
         "V-SESSION": S.variants_of(S.K1)["V-SESSION"],
         "V-WICKGATE": S.variants_of(S.K1)["V-WICKGATE"]}
C3_P = {"K1": 95, "V-SESSION": 99, "V-WICKGATE": 99}          # F3
SCHEMAS = ("ohlcv-1h", "ohlcv-1d")
SYMBOL, STYPE_IN = "CL.c.0", "continuous"
ARCHIVE_SUBDIR = "w15_chartmark_v2_forward"
REFUSED = ("--holdout", "--limit", "--seen", "--rule", "--rules", "--candidate", "--window", "--from", "--to", "--start", "--end",
           "--first", "--last", "--force", "--rescore", "--reset", "--reseed", "--draws", "--theta", "--backstop", "--params",
           "--variant", "--variants", "--no-gate", "--skip-gate", "--skip-regression", "--skip-freeze", "--extend", "--k1")


class ForwardRefused(SystemExit):
    """SystemExit so a scheduled run cannot swallow a refusal as a value error."""


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < -0.005 else f"${abs(x):,.0f}" if abs(x) < 0.005 else f"${x:,.0f}"


# ----------------------------------------------------------------------------------------------- G-freeze
def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)


def freeze_check(root: Path = ROOT, commit: str = FROZEN_COMMIT, strict: tuple = STRICT_PATHS) -> dict:
    """The engine and spec must equal `commit` in the working tree (staged or not) AND in HEAD. Refuses otherwise."""
    try:
        ok = _git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    except Exception as e:                                             # noqa: BLE001
        raise ForwardRefused(f"REFUSED (G-freeze): git is not usable here ({e}).")
    if ok.returncode != 0:
        raise ForwardRefused(f"REFUSED (G-freeze): commit {commit} is not in this repository.")
    dirty = []
    for p in strict:
        wt = _git(root, "diff", "--quiet", commit, "--", p)
        head = _git(root, "diff", "--quiet", commit, "HEAD", "--", p)
        if wt.returncode > 1 or head.returncode > 1:
            raise ForwardRefused(f"REFUSED (G-freeze): git diff failed for {p}: {(wt.stderr + head.stderr).strip()}")
        if wt.returncode == 1 or head.returncode == 1:
            dirty.append(p)
    if dirty:
        raise ForwardRefused(f"REFUSED (G-freeze): {dirty} differ from frozen commit {commit}. The forward test runs the frozen "
                             "engine only; a change after a forward bar is a POST-RUN amendment, not something to score through.")
    return dict(commit=commit, head=_git(root, "rev-parse", "HEAD").stdout.strip() or "unknown", strict_paths=list(strict))


# ----------------------------------------------------------------------------------------------- G-regression
def compare_trade_lists(df: pd.DataFrame, ref: pd.DataFrame) -> list[str]:
    """Engine trades (BK.trade_frame columns) against the committed step-C reference. Empty list = identical."""
    out = []
    if len(df) != len(ref):
        out.append(f"trade count {len(df)} != {len(ref)}")
    m = min(len(df), len(ref))
    a, b = df.iloc[:m].reset_index(drop=True), ref.iloc[:m].reset_index(drop=True)
    bad_t = (a["entry_t"].astype(str) != b["entry_t"].astype(str)) | (a["exit_t"].astype(str) != b["exit_t"].astype(str))
    bad_px = ((a["entry_px"] - b["entry_px"]).abs() > 0.005) | ((a["exit_px"] - b["exit_px"]).abs() > 0.005)
    bad_r = (a["exit_reason"].astype(str) != b["exit_reason"].astype(str)) | (a["n_rolls"].astype(int) != b["n_rolls"].astype(int))
    for name, mask in (("entry/exit bar", bad_t), ("price beyond a tick", bad_px), ("exit reason / rolls", bad_r)):
        if mask.any():
            out.append(f"{int(mask.sum())} trades differ on {name}; first at index {int(np.nonzero(mask.to_numpy())[0][0])}")
    return out


def regression_gate(archive, *, ref_csv: Path = REF_STEPC, seen_csv: Path = SEEN_CSV, training_frame: Frame | None = None,
                    seen_frame: Frame | None = None) -> dict:
    """Step C's K1 list on 2016-2021 and Amendment 5.4's seen-window K1, reproduced by the current working tree. Refuses on any diff."""
    if not Path(ref_csv).exists():
        raise ForwardRefused(f"REFUSED (G-regression): reference {ref_csv} is missing.")
    ref = pd.read_csv(ref_csv)
    if len(ref) != STEPC_TRADES:
        raise ForwardRefused(f"REFUSED (G-regression): the reference file holds {len(ref)} trades, not {STEPC_TRADES}.")
    fr = training_frame if training_frame is not None else load_training_frame(archive)
    start = CC.window_start(fr)
    ind = indicators(fr)
    trades, _ = E.simulate(fr, ind, S.K1, start=start)
    diffs = compare_trade_lists(BK.trade_frame(trades, fr, "MCL", "mid"), ref)
    if diffs:
        raise ForwardRefused("REFUSED (G-regression): step C's K1 trade list is NOT reproduced on 2016-2021: " + "; ".join(diffs)
                             + ". Something the engine depends on has changed (shared modules, data, code). Nothing was scored.")
    if seen_frame is None:
        if not Path(seen_csv).exists():
            raise ForwardRefused(f"REFUSED (G-regression): seen-window file {seen_csv} is missing.")
        seen_frame = load_seen_frame(seen_csv)
    st, _ = E.simulate(seen_frame, indicators(seen_frame), S.K1)
    pts = sum(t.exit_px - t.entry_px for t in st)
    if len(st) != SEEN_TRADES or abs(pts - SEEN_GROSS_PTS) > 0.005:
        raise ForwardRefused(f"REFUSED (G-regression): seen-window K1 gives {len(st)} trades / {pts:+.2f} pts, registered "
                             f"{SEEN_TRADES} / {SEEN_GROSS_PTS:+.2f} (Amendment 5.4). Nothing was scored.")
    return dict(passed=True, step_c_trades=len(trades), seen_trades=len(st), seen_pts=round(pts, 2))


# ----------------------------------------------------------------------------------------------- archive layout, pricing, pull
def _dataset():
    from common.tsmom_data_price import DATASET
    return DATASET


def day_path(archive, schema: str, day: str) -> Path:
    return Path(archive) / _dataset() / ARCHIVE_SUBDIR / schema / f"{day}.dbn.zst"


def warmup_path(archive) -> Path:
    return Path(archive) / _dataset() / ARCHIVE_SUBDIR / "ohlcv-1h" / "warmup.dbn.zst"


def manifest_path(archive) -> Path:
    return Path(archive) / _dataset() / ARCHIVE_SUBDIR / "manifest_w15_0037.json"


def read_manifest(archive) -> dict:
    p = manifest_path(archive)
    if p.exists():
        rec = json.loads(p.read_text(encoding="utf-8"))
    else:
        rec = {}
    rec.setdefault("runs", [])
    rec.setdefault("no_session", [])
    return rec


def write_manifest(archive, rec: dict) -> None:
    p = manifest_path(archive)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")


def request(schema: str, start: str, end: str) -> dict:
    return dict(dataset=_dataset(), schema=schema, symbols=[SYMBOL], stype_in=STYPE_IN, start=start, end=end)


def day_request(day: str, schema: str) -> dict:
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    return request(schema, f"{day}T00:00:00Z", f"{nxt}T00:00:00Z")


def warmup_request() -> dict:
    return request("ohlcv-1h", f"{WARMUP_FIRST_UTC_DAY}T00:00:00Z", f"{FIRST_UTC_DAY}T00:00:00Z")


def forward_days(last_day: str) -> list[str]:
    """UTC calendar days FIRST_UTC_DAY .. last_day inclusive."""
    d0, d1 = date.fromisoformat(FIRST_UTC_DAY), date.fromisoformat(last_day)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _dataset_end(client) -> datetime:
    from common.tsmom_fetch import _scrub
    try:
        rng = client.metadata.get_dataset_range(dataset=_dataset())
    except Exception as e:                                             # noqa: BLE001
        raise ForwardRefused(f"dataset range lookup failed: {_scrub(e)}")
    v = rng.get("end") or rng.get("end_date")
    if v is None:
        raise ForwardRefused("dataset range lookup returned no end")
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def plan(client, archive, days: list[str], manifest: dict):
    """Files to buy: the warm-up (once) and each (day, schema) not on disk and not known to be a no-session day. A day whose end
    (D+1 00:00Z) is past the dataset's end is DEFERRED (JF2), never bought partial. Returns (jobs, usd, bytes, have, no_session, deferred)."""
    from common.tsmom_fetch import _is_symbology_miss, _price, _retry, _scrub
    jobs, usd, nbytes, have, no_session, deferred = [], 0.0, 0, 0, [], []
    known_empty = set(manifest.get("no_session", []))
    need_warm = not warmup_path(archive).exists()
    need_days = [(d, s) for d in days if d not in known_empty for s in SCHEMAS if not day_path(archive, s, d).exists()]
    have += sum(1 for d in days for s in SCHEMAS if day_path(archive, s, d).exists()) + (0 if need_warm else 1)
    if not (need_warm or need_days):
        return jobs, usd, nbytes, have, no_session, deferred
    end_dt = _dataset_end(client)
    todo = ([("warmup", "ohlcv-1h", warmup_path(archive), warmup_request())] if need_warm else [])
    todo += [(d, s, day_path(archive, s, d), day_request(d, s)) for d, s in need_days]
    skip_days = set()
    for tag, schema, out, kw in todo:
        end_req = datetime.fromisoformat(kw["end"].replace("Z", "+00:00"))
        if end_req > end_dt or tag in skip_days:
            if tag != "warmup":
                skip_days.add(tag)
                if tag not in deferred:
                    deferred.append(tag)
            else:
                deferred.append("warmup")
            continue
        try:
            u, n = _retry(lambda kw=kw: _price(client, kw))
        except Exception as e:                                         # noqa: BLE001
            if _is_symbology_miss(e) and tag != "warmup":
                if tag not in no_session:
                    no_session.append(tag)
                continue
            raise ForwardRefused(f"pricing failed on {tag} {schema} -- nothing downloaded: {_scrub(e)}")
        jobs.append((tag, schema, out, kw))
        usd += u
        nbytes += n
    jobs = [j for j in jobs if j[0] not in no_session]
    return jobs, usd, nbytes, have, no_session, deferred


def download(client, jobs):
    from common.tsmom_fetch import _retry, _scrub
    done, failed = [], []
    for tag, schema, out, kw in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        try:
            data = _retry(lambda kw=kw: client.timeseries.get_range(**kw))
            data.to_file(tmp)
        except Exception as e:                                         # noqa: BLE001
            failed.append((tag, schema, _scrub(e)[:80]))
            if tmp.exists():
                tmp.unlink()
            continue
        tmp.replace(out)
        done.append((tag, schema, out))
    return done, failed


# ----------------------------------------------------------------------------------------------- reading, frame, read-back
def _read_one(path: Path) -> pd.DataFrame:
    from common.dbn_io import read_dbn
    df = read_dbn(path)
    if df is None or df.empty:
        return pd.DataFrame()
    if "symbol" in df.columns:
        df = df[df["symbol"] == SYMBOL].copy()
    return df


def load_raw_1h(archive, days: list[str]) -> pd.DataFrame:
    """Warm-up file + per-day ohlcv-1h files, as one UTC-indexed frame. Missing files are simply absent (G-contiguous decides)."""
    parts = []
    if warmup_path(archive).exists():
        parts.append(_read_one(warmup_path(archive)))
    for d in days:
        p = day_path(archive, "ohlcv-1h", d)
        if p.exists():
            parts.append(_read_one(p))
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts).sort_index() if parts else pd.DataFrame()


def load_daily_1d(archive, days: list[str]) -> pd.DataFrame:
    parts = []
    for d in days:
        p = day_path(archive, "ohlcv-1d", d)
        if p.exists():
            x = _read_one(p)
            if not x.empty:
                parts.append(x)
    if not parts:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    d = pd.concat(parts).sort_index()
    d["date"] = (d.index.tz_convert(None) if d.index.tz is not None else d.index).normalize().date
    d = d.drop_duplicates("date", keep="first").sort_values("date")
    return d[[c for c in ("date", "open", "high", "low", "close", "volume") if c in d.columns]].reset_index(drop=True)


def available_days(archive, days: list[str], manifest: dict) -> list[str]:
    """G-contiguous: the unbroken prefix of `days` for which every schema file exists (or the day is a known no-session day)."""
    empty = set(manifest.get("no_session", []))
    ok = []
    for d in days:
        if d in empty or all(day_path(archive, s, d).exists() for s in SCHEMAS):
            ok.append(d)
        else:
            break
    return ok


def frame_from_raw(raw: pd.DataFrame, last_session: str | None) -> Frame | None:
    """Raw CL.c.0 1H rows -> the engine frame (session labels as strategy.htf.bars; settlement print excluded; difference-back-adjusted;
    roll flag = held contract changes between bars). Sessions before WARMUP_FIRST_SESSION or after `last_session` are cut FIRST."""
    if raw is None or raw.empty:
        return None
    d = HB.split_held(raw)
    sess = HB.session_of(HB.local_naive(d.index))
    keep = np.asarray(sess >= pd.Timestamp(WARMUP_FIRST_SESSION))
    if last_session:
        keep &= np.asarray(sess <= pd.Timestamp(last_session))
    d = d[keep]
    if d.empty:
        return None
    e = HB.back_adjust(HB.resample(d, "1H"))
    held = e["held_id"].to_numpy()
    ra = np.zeros(len(e), bool)
    ra[:-1] = held[1:] != held[:-1]
    return make_frame(pd.to_datetime(e["t_open"], utc=True), e["open_adj"], e["high_adj"], e["low_adj"], e["close_adj"],
                      e["volume"], ra, "CL 1H forward (back-adjusted)")


def forward_start(fr: Frame) -> int | None:
    t0 = pd.Timestamp(FIRST_BAR_ET, tz=HB.ET).tz_convert("UTC")
    idx = np.nonzero(np.asarray(fr.t >= t0))[0]
    return int(idx[0]) if len(idx) else None


def read_back(raw: pd.DataFrame, daily: pd.DataFrame, days: list[str]) -> dict:
    """G-readback over the forward days: UTC-day close of the raw hourly bars vs the ohlcv-1d close, within 1 tick on >= 99%."""
    d = HB.split_held(raw) if not raw.empty else raw
    if not d.empty:
        d = d[np.asarray(d.index.tz_convert("UTC").strftime("%Y-%m-%d").isin(days))]
    utc = RB.utc_daily(d)
    ag = RB.daily_agreement(utc, daily, tol=READBACK_TOL, roll_days=RB.utc_roll_days(d))
    gaps = RB.gaps_over(d, hours=3) if not d.empty else []
    return dict(passed=bool(ag["n_compared"] > 0 and ag["pct_within_tol"] >= READBACK_PASS), agreement=ag, gaps_over_3h=gaps)


# ----------------------------------------------------------------------------------------------- ledger
def default_ledger() -> dict:
    return dict(board=BOARD, registration=REGISTRATION, frozen_commit=FROZEN_COMMIT, first_bar_et=FIRST_BAR_ET,
                first_session=FIRST_SESSION, window_end=WINDOW_END, scored_through_session=None, complete=False,
                paper_orders="ALLOWED", rules={n: dict(trades=[], stopped=None) for n in RULES}, runs=[])


def read_ledger(path: Path | None = None) -> dict:
    path = path or LEDGER_PATH
    if not path.exists():
        return default_ledger()
    rec = json.loads(path.read_text(encoding="utf-8"))
    base = default_ledger()
    for k, v in base.items():
        rec.setdefault(k, v)
    for n in RULES:
        rec["rules"].setdefault(n, dict(trades=[], stopped=None))
    if rec["frozen_commit"] != FROZEN_COMMIT:
        raise ForwardRefused(f"REFUSED: the ledger was written under commit {rec['frozen_commit']}, this code freezes {FROZEN_COMMIT}.")
    return rec


def write_ledger(ledger: dict, path: Path | None = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def trade_row(t: E.Trade, fr: Frame, reason: str | None = None) -> dict:
    ny = fr.ny
    return dict(entry_t=ny[t.entry_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"),
                exit_t=ny[t.exit_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"),
                placed_t=ny[t.placed_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"),
                entry_px=round(float(t.entry_px), 4), exit_px=round(float(t.exit_px), 4),
                pts=round(float(t.exit_px - t.entry_px), 4), reason=reason or t.reason, arm=t.arm, n_rolls=int(t.n_rolls),
                gap_fill=bool(t.gap_fill), clauses=[int(c) for c in t.clauses], level=round(float(t.level), 4))


def check_prefix(frozen: list[dict], fresh: list[dict], rule: str) -> None:
    """The recorded trades must be reproduced by the new simulation. Any difference refuses the run (nothing is re-scored)."""
    if len(fresh) < len(frozen):
        raise ForwardRefused(f"REFUSED: {rule}: the ledger holds {len(frozen)} closed trades but the simulation of the data on disk "
                             f"finds only {len(fresh)}. Data on disk changed or was removed. Ledger untouched.")
    for i, (a, b) in enumerate(zip(frozen, fresh)):
        same = (a["entry_t"], a["exit_t"], a["reason"], a["arm"], a["n_rolls"]) == (b["entry_t"], b["exit_t"], b["reason"], b["arm"], b["n_rolls"])
        if not same or abs(a["pts"] - b["pts"]) > 0.005:
            raise ForwardRefused(f"REFUSED: {rule}: recorded trade {i + 1} ({a['entry_t']} -> {a['exit_t']}, {a['reason']}, {a['pts']:+.2f} pts) "
                                 f"is not reproduced by the simulation ({b['entry_t']} -> {b['exit_t']}, {b['reason']}, {b['pts']:+.2f}). "
                                 "A session already scored is never re-scored; ledger untouched. Tell Ben; do not edit the ledger.")


# ----------------------------------------------------------------------------------------------- books, stops
def rows_df(rows: list[dict], sym: str = "MCL", level: str = "mid") -> pd.DataFrame:
    recs = []
    for r in rows:
        et, xt = pd.Timestamp(r["entry_t"]), pd.Timestamp(r["exit_t"])
        gross = r["pts"] * S.MULT[sym]
        cost = S.per_side(sym, level) * (2 + 2 * r["n_rolls"])
        recs.append(dict(entry_t=et, exit_t=xt, year=et.year, gross=gross, cost=cost, net=gross - cost, exit_reason=r["reason"]))
    return pd.DataFrame(recs, columns=["entry_t", "exit_t", "year", "gross", "cost", "net", "exit_reason"])


def apply_stops(rows: list[dict]) -> tuple[list[dict], dict | None]:
    """Trade by trade, in exit order. Returns the rows up to and including the trade that fired a stop, and the stop record."""
    eq = peak = 0.0
    kept: list[dict] = []
    for r in rows:
        kept.append(r)
        eq += rows_df([r])["net"].iloc[0]
        peak = max(peak, eq)
        n = len(kept)
        if n >= STOP_A_MIN_TRADES and eq <= STOP_A_NET:
            return kept, dict(stop="A", detail=f"net {money(eq)} <= {money(STOP_A_NET)} after {n} trades (>= {STOP_A_MIN_TRADES})",
                              at_trade=n, exit_t=r["exit_t"], net=round(eq, 2), drawdown=round(peak - eq, 2))
        if peak - eq > STOP_B_DD:
            return kept, dict(stop="B", detail=f"drawdown {money(-(peak - eq))} worse than {money(-STOP_B_DD)} after {n} trades",
                              at_trade=n, exit_t=r["exit_t"], net=round(eq, 2), drawdown=round(peak - eq, 2))
    return kept, None


def book_stats(rows: list[dict]) -> dict:
    out = {}
    for lv in S.LEVELS:
        out[f"net_{lv}"] = float(rows_df(rows, "MCL", lv)["net"].sum()) if rows else 0.0
    out["cl_net_mid"] = float(rows_df(rows, "CL", "mid")["net"].sum()) if rows else 0.0
    mid = rows_df(rows)
    s = HBK.summarize(mid)
    out.update(n=s.trades, wins=s.wins, losses=s.losses, gross=s.gross, cost=s.cost, net=s.net, avg_win=s.avg_win, avg_loss=s.avg_loss,
               largest_loss=s.largest_loss, streak=s.worst_loss_streak, dd=BK.max_drawdown(mid),
               win_rate=(s.wins / s.trades) if s.trades else None)
    if rows:
        d = mid["entry_t"].dt.strftime("%Y-%m-%d")
        out["half1"] = float(mid.loc[d <= HALF_1_LAST, "net"].sum())
        out["half2"] = float(mid.loc[d > HALF_1_LAST, "net"].sum())
    else:
        out["half1"] = out["half2"] = 0.0
    return out


# ----------------------------------------------------------------------------------------------- controls (on the forward bars)
def c1_rows(fr: Frame, start: int) -> list[dict]:
    return [trade_row(t, fr) for t in CC.donchian_c1(fr, start)]


def c3_pool(fr: Frame, ind: Ind, p: S.Params, start: int, session_only: bool):
    """Every forward bar as a standalone random entry at its open (JF4): backstop = open - p.backstop, exits by the rule's own walk."""
    per = S.per_side("MCL", "mid")
    es, xs, nets = [], [], []
    for e in range(max(start, 3), fr.n - 1):
        if np.isnan(ind.e21[e - 1]) or np.isnan(ind.atr[e - 1]):
            continue
        if session_only and not (S.SESSION_FIRST <= ind.hour[e] <= S.SESSION_LAST):
            continue
        fill = float(fr.o[e])
        stop = fill - p.backstop
        if fr.l[e] <= stop:
            x, px = e, stop
        else:
            x, px, _, _ = E._walk(fr, ind, p, e, fill, stop)
        rolls = int(fr.roll_after[e:x].sum()) if x > e else 0
        es.append(e)
        xs.append(x)
        nets.append((px - fill) * S.MULT["MCL"] - per * (2 + 2 * rolls))
    return np.array(es, int), np.array(xs, int), np.array(nets, float)


def c3_draws(es, xs, nets, n_trades: int, draws: int = DRAWS):
    """1,000 seeded draws of n_trades non-overlapping random trades. Returns (totals, n_short) or (None, 0) when there is nothing to draw."""
    if n_trades <= 0 or len(es) == 0:
        return None, 0
    tot = np.empty(draws)
    short = 0
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(C3_LABEL), n_trades])
        acc_e, acc_x, s = [], [], 0.0
        for i in rng.permutation(len(es)):
            if len(acc_e) >= n_trades:
                break
            if any(es[i] <= ax and ae <= xs[i] for ae, ax in zip(acc_e, acc_x)):
                continue
            acc_e.append(es[i])
            acc_x.append(xs[i])
            s += nets[i]
        short += int(len(acc_e) < n_trades)
        tot[d] = s
    return tot, short


def criteria(rule: str, st: dict, c1_net: float, c3: dict | None, through: str | None) -> list[dict]:
    """F1-F8 as they stand TODAY. PROVISIONAL: nothing passes early (registration sec 4); the final read is after WINDOW_END."""
    p = C3_P[rule]
    end_reached = through is not None and through >= WINDOW_END
    n = st["n"]
    avg_loss = st["avg_loss"]
    rows = [
        dict(n="F1", name="Net > $0 at mid", value=st["net_mid"], ok=st["net_mid"] > 0),
        dict(n="F2", name="Net > $0 at high friction", value=st["net_high"], ok=st["net_high"] > 0),
        dict(n="F3", name=f"Beats random entries (C3) p{p} on net", value=(st["net_mid"], c3[f"p{p}"] if c3 else None),
             ok=(st["net_mid"] > c3[f"p{p}"]) if c3 else None),
        dict(n="F4", name="Beats Donchian 20/10 long (C1) on net", value=(st["net_mid"], c1_net), ok=st["net_mid"] > c1_net),
        dict(n="F5", name="Both halves net > $0 (to 31 Mar 2027 / from 1 Apr 2027)", value=(st["half1"], st["half2"]),
             ok=(st["half1"] > 0 and st["half2"] > 0) if end_reached else None),
        dict(n="F6", name="Win rate >= 20% and average loss no worse than ($70)", value=(st["win_rate"], avg_loss),
             ok=None if not n else bool(st["win_rate"] >= 0.20 and (avg_loss is None or avg_loss >= -70.0))),
        dict(n="F7", name="At least 50 trades", value=n, ok=(n >= 50) if end_reached else None),
        dict(n="F8", name="Paper book agrees with the engine", value=None, ok=None),
    ]
    return rows


# ----------------------------------------------------------------------------------------------- the weekly cycle
def run(archive, *, as_of: str | None = None, client=None, client_factory=None, confirm: bool = False, max_cost: float = MAX_COST,
        ledger_path: Path | None = None, root: Path = ROOT, regression=None, draws: int = DRAWS, log=print) -> dict:
    today = as_of or datetime.now(timezone.utc).date().isoformat()
    res: dict = dict(as_of=today, frozen=freeze_check(root))
    ledger = read_ledger(ledger_path)
    if ledger.get("complete"):
        res.update(already_complete=True, ledger=ledger)
        return res

    last_day = min((date.fromisoformat(today) - timedelta(days=1)).isoformat(), WINDOW_END)
    if last_day < FIRST_UTC_DAY:
        res.update(no_new_sessions=True, ledger=ledger)
        return res
    days = forward_days(last_day)
    manifest = read_manifest(archive)

    jobs, usd, nbytes, have, no_session, deferred = [], 0.0, 0, 0, [], []
    need_client = not warmup_path(archive).exists() or any(
        d not in set(manifest["no_session"]) and not all(day_path(archive, s, d).exists() for s in SCHEMAS) for d in days)
    if need_client:
        if client is None:
            if client_factory is None:
                from common.tsmom_data_price import require_databento
                from common.tsmom_fetch import _key
                client_factory = lambda: require_databento().Historical(_key())       # noqa: E731
            client = client_factory()
        jobs, usd, nbytes, have, no_session, deferred = plan(client, archive, days, manifest)
    res.update(days_due=days, n_jobs=len(jobs), n_have=have, no_session=no_session, deferred=deferred,
               estimated_usd=usd, estimated_bytes=nbytes)
    if usd > max_cost:
        raise ForwardRefused(f"ABORT: ${usd:.2f} exceeds --max-cost ${max_cost:.2f}. A weekly pull of one symbol's hourly bars should "
                             "cost pennies -- this means the scope moved. Nothing downloaded.")
    if not confirm:
        res.update(estimate_only=True, ledger=ledger)
        return res

    done, failed = download(client, jobs) if jobs else ([], [])
    res.update(n_downloaded=len(done), n_failed=len(failed), failed=[f"{t} {s}: {m}" for t, s, m in failed])
    manifest["no_session"] = sorted(set(manifest["no_session"]) | set(no_session))
    manifest["runs"].append(dict(pulled_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), files=[str(p) for _, _, p in done],
                                 failed=[f"{t} {s}" for t, s, _ in failed], no_session=no_session, deferred=deferred,
                                 estimated_usd=round(usd, 4)))
    write_manifest(archive, manifest)

    ok_days = available_days(archive, days, manifest)
    if not ok_days or not warmup_path(archive).exists():
        res.update(nothing_scored=True, ledger=ledger)
        return res
    cutoff = ok_days[-1]
    if ledger["scored_through_session"] and cutoff < ledger["scored_through_session"]:
        raise ForwardRefused(f"REFUSED: data on disk now ends at session {cutoff}, before the ledger's {ledger['scored_through_session']}.")

    # ---- G-regression (scoring runs only), then the read-back
    gate = (regression or regression_gate)(archive)
    raw = load_raw_1h(archive, ok_days)
    daily = load_daily_1d(archive, ok_days)
    rb = read_back(raw, daily, ok_days)
    if not rb["passed"]:
        ag = rb["agreement"]
        raise ForwardRefused(f"REFUSED (G-readback): {ag['n_within_tol']}/{ag['n_compared']} ({ag['pct_within_tol']:.2%}) UTC days agree with ohlcv-1d "
                             f"within 1 tick, below 99%. Worst: {ag['misses'][:3]}. Ledger untouched; the study stops until this is explained.")

    fr = frame_from_raw(raw, cutoff)
    start = forward_start(fr) if fr is not None else None
    if fr is None or start is None or start >= fr.n - 1:
        res.update(nothing_scored=True, ledger=ledger)
        return res
    complete = cutoff >= WINDOW_END
    ind = indicators(fr)
    pre = E.precompute(fr, ind)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_ledger = json.loads(json.dumps(ledger))
    books, controls, open_pos = {}, {}, {}
    c1 = c1_rows(fr, start)
    c1_net = float(rows_df(c1)["net"].sum()) if c1 else 0.0
    for name, p in RULES.items():
        sim, cnt = E.simulate(fr, ind, p, start=start, pre=pre)
        closed = [t for t in sim if t.reason != "data_end"]
        rows = [trade_row(t, fr) for t in closed]
        tail = sim[-1] if sim and sim[-1].reason == "data_end" else None
        if tail is not None and complete:
            rows.append(trade_row(tail, fr, reason="WINDOW_END"))              # JF5 / J11
            tail = None
        led = new_ledger["rules"][name]
        check_prefix(led["trades"], rows, name)
        if led["stopped"] is None:
            kept, stop = apply_stops(rows)
            led["trades"] = kept
            if stop is not None:
                led["stopped"] = {**stop, "detected_at": now, "as_of_session": cutoff}
                if name == "K1":
                    new_ledger["paper_orders"] = f"STOPPED: K1 stop {stop['stop']} ({stop['detail']})"
        st = book_stats(led["trades"])
        es, xs, nets = c3_pool(fr, ind, p, start, session_only=(name == "V-SESSION"))
        tot, short = c3_draws(es, xs, nets, st["n"], draws)
        c3 = None
        if tot is not None:
            c3 = {f"p{q}": float(np.percentile(tot, q)) for q in (5, 50, 95, 99)}
            c3.update(rank=float((tot < st["net_mid"]).mean()), draws=draws, short_draws=short, pool=int(len(es)))
        books[name], controls[name] = st, c3
        open_pos[name] = None if tail is None else dict(trade_row(tail, fr), marked="last close, provisional")
        books[name]["criteria"] = criteria(name, st, c1_net, c3, cutoff)
        books[name]["counts"] = dict(orders=cnt["orders"], fills=cnt["fills"], unfilled=cnt["unfilled"])

    new_ledger["scored_through_session"] = cutoff
    new_ledger["complete"] = bool(complete)
    new_ledger["runs"].append(dict(run_at=now, through_session=cutoff, days=len(ok_days), usd_spent=round(usd, 4),
                                   trades={n: len(new_ledger["rules"][n]["trades"]) for n in RULES},
                                   readback_pct=round(rb["agreement"]["pct_within_tol"], 4), gate=gate))
    write_ledger(new_ledger, ledger_path)
    res.update(scored_through=cutoff, gate=gate, readback=rb, books=books, controls=controls, open_positions=open_pos,
               c1=dict(net=c1_net, n=len(c1)), ledger=new_ledger, start_bar=str(fr.ny[start]), last_bar=str(fr.ny[-1]), n_bars=fr.n)
    return res


# ----------------------------------------------------------------------------------------------- report
def _fmt(c: dict) -> str:
    v = c["value"]
    if v is None:
        return "n/a"
    if c["n"] == "F6":
        wr, al = v
        return f"win rate {wr:.0%}, avg loss {money(al)}" if wr is not None else "no trades"
    if isinstance(v, tuple):
        return "(" + ", ".join("n/a" if x is None else money(x) for x in v) + ")"
    return str(v) if isinstance(v, int) else money(v)


def txt_report(r: dict) -> str:
    L = [f"=== W15-0037 CHARTMARK-v2 F1 forward test, as of {r['as_of']} ===",
         f"frozen engine: commit {FROZEN_COMMIT}   scored sessions {FIRST_SESSION} .. {WINDOW_END}   1 MCL, IBKR costs, negatives in brackets",
         "STEP C's FAIL: CHARTMARK-v2 failed its registered 2016-2021 confirmation (6 of 9 criteria). This test runs on Ben's decision (W15-0038).", ""]
    if r.get("already_complete"):
        L.append("COMPLETE: the window has been scored to 2027-09-30. Final read vs F1-F8 -> Result doc (sub 5).")
    elif r.get("no_new_sessions"):
        L.append("No completed forward session yet (first scored session is 2026-10-01).")
    elif r.get("estimate_only"):
        L.append(f"ESTIMATE ONLY -- {r['n_jobs']} file(s) to buy, {r['n_have']} already on disk, {len(r['no_session'])} no-session day(s), "
                 f"{len(r['deferred'])} deferred (not yet available).")
        L.append(f"estimate ${r['estimated_usd']:.2f}  {r['estimated_bytes']:,} bytes. Nothing downloaded, nothing scored. Re-run with --confirm.")
    elif r.get("nothing_scored"):
        L.append(f"Nothing scored this run (deferred days {r.get('deferred')}, failed {r.get('failed')}).")
    else:
        L.append(f"scored through session {r['scored_through']}   frame {r['n_bars']} bars, first forward bar {r['start_bar']}, last {r['last_bar']}")
        g = r["gate"]
        L.append(f"G-freeze ok ({r['frozen']['head'][:7]} HEAD)   G-regression ok (step C K1 {g['step_c_trades']} trades; seen {g['seen_trades']} / {g['seen_pts']:+.2f} pts)   "
                 f"G-readback {r['readback']['agreement']['n_within_tol']}/{r['readback']['agreement']['n_compared']} days, "
                 f"{len(r['readback']['gaps_over_3h'])} gap(s) > 3h")
        L.append(f"spent this run ${r['estimated_usd']:.2f}")
        L.append("")
        for name in RULES:
            st, led = r["books"][name], r["ledger"]["rules"][name]
            L.append(f"--- {name}{'  [STOPPED: ' + led['stopped']['detail'] + ']' if led['stopped'] else ''} ---")
            wr = f"{st['win_rate']:.0%}" if st["win_rate"] is not None else "n/a"
            L.append(f"  trades {st['n']}  wins {st['wins']}  losses {st['losses']}  win rate {wr}  gross {money(st['gross'])}  costs {money(st['cost'])}  "
                     f"net mid {money(st['net'])}")
            L.append(f"  net low / mid / high {money(st['net_low'])} / {money(st['net_mid'])} / {money(st['net_high'])}   1 CL mid {money(st['cl_net_mid'])}   "
                     f"max drawdown {money(st['dd'])}")
            L.append(f"  avg win {money(st['avg_win'])}  avg loss {money(st['avg_loss'])}  largest loss {money(st['largest_loss'])}  worst losing run {st['streak']}")
            L.append(f"  stop A watch (>=30 trades, net <= {money(STOP_A_NET)}): net {money(st['net_mid'])} after {st['n']}   "
                     f"stop B watch (drawdown > {money(STOP_B_DD)}): {money(st['dd'])}")
            op = r["open_positions"][name]
            if op:
                L.append(f"  OPEN position (provisional, not ledgered): in {op['entry_t']} at {op['entry_px']:.2f}, marked {op['exit_px']:.2f} = {op['pts']:+.2f} pts")
            c3 = r["controls"][name]
            if c3:
                L.append(f"  C3 random entries ({c3['draws']:,} draws, pool {c3['pool']}): p50 {money(c3['p50'])}  p95 {money(c3['p95'])}  p99 {money(c3['p99'])}; "
                         f"beats {100 * c3['rank']:.0f}% of draws")
            L.append(f"  PROVISIONAL F-criteria today (nothing passes early; final read after {WINDOW_END}):")
            for c in st["criteria"]:
                flag = "n/a yet" if c["ok"] is None else ("pass" if c["ok"] else "fail")
                L.append(f"    {c['n']} {c['name']:<62s} {flag:8s} {_fmt(c)}")
            L.append("")
        L.append(f"C1 Donchian 20/10 long on the same bars: {r['c1']['n']} trades, net mid {money(r['c1']['net'])}")
    L.append("")
    L.append("Paper-order routing (sub 4): not built -- this is the engine book only. Nobody reads a rule as working before 30 Sep 2027.")
    return "\n".join(L) + "\n"


def default_out_path(as_of: str) -> Path:
    return OUT / f"w15_0037_forward_{as_of}.json"


def write_report(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in result.items() if k not in ("ledger",)}
    out.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    out.with_suffix(".txt").write_text(txt_report(result), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- CLI
def main(argv=None, client=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- the forward test has one window, three frozen rules and no narrowing or re-scoring flags "
                         "(registration sec 1, sec 9).\n")
        return 2
    ap = argparse.ArgumentParser(description="W15-0037 weekly forward scorer for CHARTMARK-v2 F1 (frozen engine). CAN SPEND.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--as-of", default=None, help="UTC date treated as 'today' (testing); never later than today")
    ap.add_argument("--max-cost", type=float, default=MAX_COST)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--confirm", action="store_true", help="pull, score, append to the ledger. Without it: freeze check + estimate only.")
    a = ap.parse_args(argv)
    today_utc = datetime.now(timezone.utc).date().isoformat()
    as_of = a.as_of or today_utc
    if as_of > today_utc:
        sys.stderr.write(f"REFUSED: --as-of {as_of} is in the future (today UTC is {today_utc}).\n")
        return 2
    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()
    print(f"W15-0037 forward scorer -- frozen engine {FROZEN_COMMIT}\nwindow  {FIRST_SESSION} .. {WINDOW_END}\nas of   {as_of} (UTC)\n"
          f"target  {Path(archive) / _dataset() / ARCHIVE_SUBDIR}\nledger  {LEDGER_PATH}\n")
    result = run(archive, as_of=as_of, client=client, confirm=a.confirm, max_cost=a.max_cost)
    print(txt_report(result))
    write_report(result, a.out or default_out_path(as_of))
    if result.get("n_failed"):
        print("INCOMPLETE. Re-run: files already on disk are free to skip.")
        return 1
    stopped = [n for n, v in result.get("ledger", {}).get("rules", {}).items() if v.get("stopped")]
    return 3 if (stopped and a.confirm) else 0


if __name__ == "__main__":
    raise SystemExit(main())
