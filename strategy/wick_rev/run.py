#!/usr/bin/env python3
"""WICK-REV runner (W15-0063). Runs on Ben's PC: it reads the Databento archive.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.wick_rev.run --mode readback    # G1a
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.wick_rev.run --mode preflight   # G2, counts only
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.wick_rev.run --mode train       # full training run
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.wick_rev.run --mode holdout     # spends the ledger, once

Modes
  readback   G1a: first / last bar, bars per year, gaps and roll counts for the owned NQ 1-minute and CL 1-hour files.
  preflight  G2: sec 5 item 1 per combination on the TRAINING side. Refuses outcomes: it never calls the race or the
             trade simulation (`study.analyse` is not imported on this path's data flow).
  train      sec 5 for all 6 combinations (MCL 30m reported only, from the IBKR file) on training sessions; writes the
             verdict file the holdout run reads.
  holdout    the combination-directions that SHOW AN EDGE on the verdict file, all together, on 2022-01-03 -> 2025-09-22.
             Refuses --combos / --limit. Writes holdout_w15_0063.json. One-way door.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import report_io
from strategy.wick_rev import bars as B
from strategy.wick_rev import holdout as HO
from strategy.wick_rev import report as R
from strategy.wick_rev import signals as G
from strategy.wick_rev import spec as S

ROOT = Path(__file__).resolve().parents[2]
VERDICT_DEFAULT = ROOT / "var" / "state" / "w15_0063_training_verdict.json"
MCL30_DEFAULT = ROOT / "var" / "w15_0063" / "mcl_30m_ibkr.csv"


class Refused(SystemExit):
    pass


# --- loaders (touch the archive; not unit-tested against real files) -----------------------------
def _archive_root(archive: Path | None) -> Path:
    if archive is not None:
        return Path(archive)
    from common.tsmom_fetch import default_archive
    return default_archive()


def load_nq_1m(archive: Path | None) -> pd.DataFrame:
    from common.dbn_io import read_dbn
    from strategy.w16.fetch import bar_path
    p = bar_path(_archive_root(archive), "NQ", "ohlcv-1m")
    if not p.exists():
        raise SystemExit(f"missing {p} (the W16 NQ 1-minute file)")
    return B.split_held_v0(read_dbn(p), "NQ.v.0")


def load_cl_1h(archive: Path | None) -> pd.DataFrame:
    from strategy.htf import bars as HB
    from strategy.htf.fetch import bar_path
    root = _archive_root(archive)
    if not bar_path(root).exists() and bar_path(root.parent).exists():
        root = root.parent
    if not bar_path(root).exists():
        raise SystemExit(f"missing {bar_path(root)} (the HTF CL 1-hour file)")
    return HB.load_1h(root)


def load_mcl_30m(path: Path | None) -> pd.DataFrame | None:
    """IBKR 30-minute MCL bars from sub 3a: CSV with ts (UTC), open, high, low, close, volume, held_id."""
    p = Path(path) if path else MCL30_DEFAULT
    if not p.exists():
        return None
    d = pd.read_csv(p, encoding="utf-8")
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    return d.set_index("ts").sort_index()[["open", "high", "low", "close", "volume", "held_id"]]


# --- building a Series from source bars ---------------------------------------------------------
def make_series(src: pd.DataFrame, market: str, tf: str, *, start: str, end: str,
                fine_src: pd.DataFrame | None = None) -> G.Series:
    """Cut by SESSION date FIRST, then resample, then back-adjust."""
    cut = B.cut_sessions(src, start, end)
    bars = B.back_adjust_bars(B.build_bars(cut, S.BAR_MINUTES[tf]))
    fine = None
    if fine_src is not None:
        fine = B.fine_frame(B.cut_sessions(fine_src, start, end))
    return G.series_from_bars(bars, market, tf, fine)


def build_all(archive, mcl30_path, *, start: str, end: str, only=None, log=print) -> dict:
    """{(market, tf): Series} in the fixed order; a missing source is skipped and said so."""
    out = {}
    want = [c for c in S.COMBOS if only is None or c in only]
    nq = cl = None
    for market, tf in want:
        if market == "MNQ":
            nq = load_nq_1m(archive) if nq is None else nq
            out[(market, tf)] = make_series(nq, market, tf, start=start, end=end, fine_src=nq)
        elif tf == "30m":
            d = load_mcl_30m(mcl30_path)
            if d is None:
                log("MCL 30m: no IBKR file yet (sub 3a) - skipped, listed as not run")
                continue
            out[(market, tf)] = make_series(d, market, tf, start="1990-01-01", end="2100-01-01")   # the IBKR file is its own window
        else:
            cl = load_cl_1h(archive) if cl is None else cl
            fine = cl if tf == "4H" else None            # 4H doubles resolve on the 1-hour bars; MCL 1H cannot
            out[(market, tf)] = make_series(cl, market, tf, start=start, end=end, fine_src=fine)
        log(f"{market} {tf}: {out[(market, tf)].n} bars")
    return out


# --- modes ------------------------------------------------------------------------------------
def _score_all(series: dict, window_label: str) -> tuple[str, dict]:
    from strategy.wick_rev import study
    parts, verdicts = [], {}
    for (market, tf), s in series.items():
        reported = (market, tf) in S.REPORTED_ONLY
        res = study.analyse(s, reported_only=reported)
        parts.append(R.combo_report(res, window=window_label if not reported else
                                    f"IBKR window {pd.Timestamp(s.t_open[0], tz='UTC').date()} .. "
                                    f"{pd.Timestamp(s.t_open[-1], tz='UTC').date()}  (reported only; inside the holdout dates, never scored)"))
        for side, sd in res["sides"].items():
            rd = sd.get("reading", {})
            verdicts[f"{market}-{tf}-{'up' if side == 1 else 'down'}"] = {
                "verdict": rd.get("verdict"), "shows_edge": bool(rd.get("shows_edge", False)),
                "tradeable": bool(rd.get("tradeable", False))}
    return "\n\n".join(parts), verdicts


def mode_preflight(series: dict, window: str) -> str:
    rows = [(m, tf, G.counts_only(s)) for (m, tf), s in series.items()]
    return R.counts_report(rows, window)


def mode_train(series: dict, verdict_path: Path) -> str:
    text, verdicts = _score_all(series, f"training {S.TRAIN_FROM} .. {S.TRAIN_TO}")
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    verdict_path.write_text(json.dumps({"window": [S.TRAIN_FROM, S.TRAIN_TO], "verdicts": verdicts},
                                       indent=2) + "\n", encoding="utf-8")
    shows = [k for k, v in verdicts.items() if v["shows_edge"]]
    tail = ("\n\nCombination-directions that SHOW AN EDGE on training (sec 6 criteria 1-4): "
            + (", ".join(shows) if shows else "none") + f"\nverdict file: {verdict_path}")
    return text + tail


def mode_holdout(series_hold: dict, series_seen: dict, verdict_path: Path) -> str:
    """Scores ONLY the listed combination-directions, all together, and spends the ledger once."""
    v = json.loads(Path(verdict_path).read_text(encoding="utf-8"))["verdicts"]
    wanted = sorted(k for k, x in v.items() if x["shows_edge"])
    if not wanted:
        raise Refused("no combination-direction shows an edge on training: the holdout is not spent (sec 8).")
    HO.split_dates(["2022-01-03"], spend=True, candidate=S.CANDIDATE, verdict="PASS")       # one-way door
    from strategy.wick_rev import study
    parts = ["HOLDOUT (spent) - " + f"{S.HOLD_FROM} .. {S.HOLD_TO}", "scored together: " + ", ".join(wanted),
             "The reading rule for this window is not registered: tables only; the verdict wording goes to the Result doc.", ""]
    for (market, tf), s in series_hold.items():
        keys = [k for k in wanted if k.startswith(f"{market}-{tf}-")]
        if not keys:
            continue
        res = study.analyse(s, reported_only=True)          # tables; no sec 6 verdict
        res["sides"] = {side: sd for side, sd in res["sides"].items()
                        if f"{market}-{tf}-{'up' if side == 1 else 'down'}" in keys}
        parts.append(R.combo_report(res, window=f"holdout {S.HOLD_FROM} .. {S.HOLD_TO}"))
    parts.append("\nSEEN WINDOW - seen -- not evidence (counts and P(rev) only)")
    for (market, tf), s in series_seen.items():
        for side, d in study.seen_summary(s).items():
            if f"{market}-{tf}-{'up' if side == 1 else 'down'}" in wanted:
                parts.append(f"  {market} {tf} {'up' if side == 1 else 'down'}: {d}")
    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="WICK-REV (W15-0063) runner.")
    ap.add_argument("--mode", required=True, choices=["readback", "preflight", "train", "holdout"])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--mcl30", type=Path, default=None, help="IBKR MCL 30-minute CSV from sub 3a")
    ap.add_argument("--combos", default=None, help="e.g. MNQ:1H,MNQ:4H (training modes only)")
    ap.add_argument("--verdict", type=Path, default=VERDICT_DEFAULT)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    if a.mode == "holdout" and (a.combos or a.limit is not None):
        raise Refused("--combos / --limit are refused on the holdout: a narrowed sample is not the registered sample (sec 8).")
    if a.limit is not None:
        raise Refused("--limit is not supported.")
    only = None
    if a.combos:
        only = {tuple(x.split(":")) for x in a.combos.split(",")}
        bad = only - set(S.COMBOS)
        if bad:
            raise SystemExit(f"unknown combos {sorted(bad)}")

    if a.mode == "readback":
        from strategy.wick_rev import readback as RB
        text = RB.run(_archive_root(a.archive), a.mcl30 or MCL30_DEFAULT)
        out = a.out or ROOT / "var" / "reports" / "w15_0063_readback.txt"
        report_io.emit(R.header("G1a read-back") + "\n" + text, out)
        return 0
    if a.mode in ("preflight", "train"):
        series = build_all(_archive_root(a.archive), a.mcl30, start=S.TRAIN_FROM, end=S.TRAIN_TO, only=only)
        if a.mode == "preflight":
            text = R.header("G2 count-only pre-flight (training side)") + "\n" + mode_preflight(
                series, f"{S.TRAIN_FROM} .. {S.TRAIN_TO}")
        else:
            text = R.header("training run (sec 5)") + "\n" + mode_train(series, a.verdict)
        report_io.emit(text, a.out or ROOT / "var" / "reports" / f"w15_0063_{a.mode}.txt")
        return 0
    # holdout
    if not Path(a.verdict).exists():
        raise SystemExit(f"no training verdict file at {a.verdict}: run --mode train first")
    hold = build_all(_archive_root(a.archive), None, start=S.HOLD_FROM, end=S.HOLD_TO,
                     only={c for c in S.PRIMARY_COMBOS})
    seen = build_all(_archive_root(a.archive), None, start=S.SEEN_FROM, end="2100-01-01",
                     only={c for c in S.PRIMARY_COMBOS})
    text = R.header("holdout run (sec 8)") + "\n" + mode_holdout(hold, seen, a.verdict)
    report_io.emit(text, a.out or ROOT / "var" / "reports" / "w15_0063_holdout.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
