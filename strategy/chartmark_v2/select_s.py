#!/usr/bin/env python3
"""CHARTMARK-v2 step S -- selection on the development window ONLY (Amendment 4.2). W15-0036 step 3.

    python -m strategy.chartmark_v2.select_s

Runs K1-K4 on bars whose New York date is 2010-06-06 .. 2015-12-31 and nothing else: the training frame is cut at
2015-12-31 BEFORE any indicator, engine step or P&L is computed, so no bar from 2016-01-01 on enters a calculation.
Winner = highest net at mid friction, 1 MCL, among candidates with >= 75 trades in the window (tie -> smaller max drawdown).
Writes selection_chartmark_v2.json (winner, the four nets, timestamp, git commit) in the repo root, plus a report
(.txt + .json) in the output folder. Refuses: any P&L/holdout/limit flag, --markets, a second selection (the file exists),
and a candidate pool that is not backed by the G2 pre-flight file. No confirmation-window number, control, grid or variant is
computed here; those are step C, which needs the selection file this writes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from strategy.chartmark.data import Frame, indicators, load_training_frame, make_frame
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S
from strategy.htf import book as HBK

ROOT = Path(__file__).resolve().parents[2]
SELECTION_PATH = ROOT / "selection_chartmark_v2.json"
OUT = Path(r"D:\Trading\Claude outputs")
GUARDED = ("strategy/chartmark_v2", "docs/research/REGISTERED_chartmark_v2.md")
REFUSED = ("--holdout", "--limit", "--seen", "--pnl", "--backtest", "--spend", "--variants", "--grid", "--controls",
           "--confirm", "--conf", "--from", "--to", "--first", "--last", "--markets", "--candidate")


def cut_frame(fr: Frame, last_day: str = S.DEV_LAST) -> Frame:
    """Bars whose NY date <= last_day. The last kept bar's roll flag is cleared (it would describe the next, dropped bar)."""
    keep = np.asarray(fr.ny.strftime("%Y-%m-%d") <= last_day)
    k = int(keep.sum())
    if k == 0 or not keep[:k].all():
        raise SystemExit("frame is not time-ordered or has no bar in the development window")
    ra = fr.roll_after[:k].copy()
    ra[-1] = False
    return make_frame(fr.t[:k], fr.o[:k], fr.h[:k], fr.l[:k], fr.c[:k], fr.v[:k], ra, fr.label + f" [cut at {last_day}]")


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def evaluate_candidate(fr: Frame, ind, name: str, pre) -> dict:
    trades, cnt = E.simulate(fr, ind, S.CANDIDATES[name], pre=pre)
    out = dict(name=name, params=repr(S.CANDIDATES[name]), n=len(trades), counts=cnt)
    for lv in S.LEVELS:
        df = _book().trade_frame(trades, fr, "MCL", lv)
        s = HBK.summarize(df) if len(df) else None
        out[lv] = dict(net=float(s.net) if s else 0.0, gross=float(s.gross) if s else 0.0, cost=float(s.cost) if s else 0.0,
                       wins=s.wins if s else 0, losses=s.losses if s else 0,
                       avg_win=s.avg_win if s else None, avg_loss=s.avg_loss if s else None,
                       largest_loss=s.largest_loss if s else None, streak=s.worst_loss_streak if s else 0,
                       dd=float(_book().max_drawdown(df)))
        if lv == "mid":
            out["year_net"] = {int(y): float(v) for y, v in (HBK.year_table(df) if len(df) else {}).items()}
            out["exits"] = {}
            for t in trades:
                out["exits"][t.reason] = out["exits"].get(t.reason, 0) + 1
            out["arms"] = {}
            for t in trades:
                out["arms"][t.arm] = out["arms"].get(t.arm, 0) + 1
            out["data_end_exits"] = out["exits"].get("data_end", 0)
    return out


def _book():
    from strategy.chartmark import book as bk
    return bk


def choose(results: dict, pool: list[str]) -> tuple[str | None, list[str]]:
    """Amendment 4.2. Returns (winner or None, candidates dropped for < 75 trades / outside the pre-flight pool)."""
    dropped = [k for k, r in results.items() if r["n"] < S.MIN_TRADES_WINDOW or k not in pool]
    ok = [k for k in results if k not in dropped]
    if not ok:
        return None, dropped
    # highest net at mid (compared to the cent); tie -> smaller max drawdown at mid; residual tie -> registration order K1..K4
    best = sorted(ok, key=lambda k: (-round(results[k]["mid"]["net"], 2), round(results[k]["mid"]["dd"], 2), k))
    return best[0], dropped


def _git(*args) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_state() -> dict:
    dirty = [ln for ln in _git("status", "--porcelain", "--", *GUARDED).splitlines() if ln.strip()]
    return dict(commit=_git("rev-parse", "HEAD") or "unknown", dirty_registered_paths=dirty)


def preflight_pool(out_dir: Path) -> tuple[list[str], str]:
    files = sorted(out_dir.glob("w15_0036_v2_preflight_*.json"))
    if not files:
        raise SystemExit("REFUSED: no G2 pre-flight file (w15_0036_v2_preflight_*.json) in the output folder -- run "
                         "python -m strategy.chartmark_v2.preflight first.")
    f = files[-1]
    blocks = json.loads(f.read_text(encoding="utf-8"))
    return [k for k in S.CANDIDATES if blocks.get(k, {}).get("eligible")], f.name


def render(res: dict, sel: dict, fr: Frame, pf_name: str, stamp: str) -> str:
    L = [f"W15-0036 CHARTMARK-v2 step S -- selection on the DEVELOPMENT window only, run {stamp}",
         f"Registered: REGISTERED_chartmark_v2.md Amendment 4.2 (+ Amendment 5). Window {S.DEV_FIRST} .. {S.DEV_LAST}; "
         f"{fr.n} bars {fr.ny[0]} .. {fr.ny[-1]}.",
         "1 MCL, IBKR costs (MCL $0.77 per side + 0/1/2 ticks). Negatives in brackets. Nothing from 2016-01-01 on was computed.",
         f"Candidate pool from the G2 pre-flight file {pf_name}.", ""]
    L += ["SELECTION:", f"  WINNER: {sel['winner'] or 'NONE -- NOT READ, stop and report to Ben'}"]
    if sel["dropped"]:
        L.append(f"  dropped (fewer than {S.MIN_TRADES_WINDOW} trades in the window, or not in the pre-flight pool): {sel['dropped']}")
    L += ["", f"  {'':4} {'prev-high':>9} {'theta':>6} {'trades':>7} {'W/L':>9} {'gross':>10} {'costs':>9} {'net LOW':>10} "
          f"{'net MID':>10} {'net HIGH':>10} {'max DD':>9}"]
    for k, r in res.items():
        p = S.CANDIDATES[k]
        m = r["mid"]
        L.append(f"  {k:<4} {('on' if p.prev_high else 'off'):>9} {p.theta:>6.2f} {r['n']:>7} {m['wins']:>4}/{m['losses']:<4} "
                 f"{money(m['gross']):>10} {money(m['cost']):>9} {money(r['low']['net']):>10} {money(m['net']):>10} "
                 f"{money(r['high']['net']):>10} {money(m['dd']):>9}"
                 + ("   <== winner" if k == sel["winner"] else ""))
    L.append("")
    for k, r in res.items():
        m = r["mid"]
        L += [f"== {k}: avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  "
              f"worst losing run {m['streak']}",
              f"   exits {r['exits']}   arms {r['arms']}   fills {r['counts']['fills']}  orders {r['counts']['orders']}  "
              f"positions cut at the window end (data_end) {r['data_end_exits']}",
              f"   net per year (mid): " + "  ".join(f"{y}: {money(v)}" for y, v in sorted(r['year_net'].items()))]
    L += ["", "CAVEATS:",
          "  * This is a selection on 2010-2015 among four fixed candidates, not a verdict. The rule is only tested in step C on 2016-2021.",
          "  * Prices are difference-back-adjusted over the whole training archive (the loader); that adds a constant to early prices "
          "that is set by later rolls. Every rule is relative to the bars around it, so the constant does not change a decision.",
          "  * A position still open at 2015-12-31 is closed at that last close (data_end), reported per candidate.",
          "  * Gross, low/high net and drawdown are reported for reading only; the choice uses net at mid, then drawdown for a tie.",
          f"  * Git: {sel['git_commit']}" + (f"  UNCOMMITTED changes under the registered paths: {sel['dirty_registered_paths']}" if sel["dirty_registered_paths"] else ""),
          ""]
    return "\n".join(L)


def run(archive, out_dir: Path, stamp: str, *, selection_path: Path = SELECTION_PATH, log=print) -> dict:
    if selection_path.exists():
        raise SystemExit(f"REFUSED: {selection_path.name} already exists. A second selection is a re-selection; "
                         "if the first run failed, tell Ben -- do not delete it to re-run.")
    pool, pf_name = preflight_pool(out_dir)
    fr = cut_frame(load_training_frame(archive))
    ind = indicators(fr)
    pre = E.precompute(fr, ind)
    res = {k: evaluate_candidate(fr, ind, k, pre) for k in S.CANDIDATES}
    winner, dropped = choose(res, pool)
    g = git_state()
    sel = dict(winner=winner, dropped=dropped, window=[S.DEV_FIRST, S.DEV_LAST],
               nets_mid_1mcl={k: round(r["mid"]["net"], 2) for k, r in res.items()},
               trades={k: r["n"] for k, r in res.items()},
               max_dd_mid_1mcl={k: round(r["mid"]["dd"], 2) for k, r in res.items()},
               params={k: dict(prev_high=S.CANDIDATES[k].prev_high, theta=S.CANDIDATES[k].theta) for k in res},
               rule="Amendment 4.2: highest net at mid, 1 MCL, >= 75 trades in the window; tie -> smaller max drawdown",
               preflight_file=pf_name, timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               git_commit=g["commit"], dirty_registered_paths=g["dirty_registered_paths"],
               last_bar_used=str(fr.ny[-1]))
    text = render(res, sel, fr, pf_name, stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"w15_0036_v2_stepS_{stamp}.txt").write_text(text, encoding="utf-8")
    (out_dir / f"w15_0036_v2_stepS_{stamp}.json").write_text(
        json.dumps(dict(selection=sel, candidates={k: {q: v for q, v in r.items() if q != "counts"} for k, r in res.items()}),
                   indent=1, default=str), encoding="utf-8")
    if winner is not None:                    # NOT READ -> no selection file, step C stays locked
        selection_path.write_text(json.dumps(sel, indent=2) + "\n", encoding="utf-8")
    log(text)
    return sel


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- step S is K1-K4 on the development window only (Amendment 4.2).\n")
        return 2
    ap = argparse.ArgumentParser(description="CHARTMARK-v2 step S (development window only).")
    ap.add_argument("--archive", help="archive path (default: the program's futures archive)")
    ap.add_argument("--out", default=str(OUT), help="output folder")
    a = ap.parse_args(argv)
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
