#!/usr/bin/env python3
"""OTF-G v1 runner, TRAINING SIDE ONLY. W15-0025.

    python -m strategy.otf_gate.run --preflight --out "D:\\Trading\\Claude outputs\\w15_0025_otf_preflight_YYYYMMDD.txt"
    python -m strategy.otf_gate.run --run        # refuses without a matching, cleared pre-flight (see below)

--preflight is COUNT-ONLY (sec 5, G2): host columns market, spec, share, sizing, equity, direction, entry_date,
entry_j (H-A) and B1 entry times and sides (H-B); the state census; kept / removed counts; the G4 / G6 data checks.
No gross, net, exit or outcome is loaded or computed. It writes the .txt (the --out path) and a .json beside it
carrying the SHA-256 of every input.

--run (P&L) is the sub 5 step: it refuses unless a pre-flight on disk matches the current inputs and did not stop,
and until the study module (costs G5, C-R, sec 4 criteria) is built it stops there. No --holdout, --limit,
--spend, --seen, --markets, --window, --hosts or --variant exists: those are refused (sec 6, 7).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.otf_gate import bars_ha as BA
from strategy.otf_gate import bars_hb as BB
from strategy.otf_gate import books as BK
from strategy.otf_gate import preflight as PF
from strategy.otf_gate import spec as S
from strategy.otf_gate.holdout import H as HOLD

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "Claude outputs"
BOOKS = OUT_DIR / "tl_v1_backtest_trades_20260929.csv"
REFUSED = ("--holdout", "--limit", "--spend", "--seen", "--markets", "--window", "--hosts", "--variant")
STEM = "w15_0025_otf_preflight"


def default_archive_ha() -> Path:
    from strategy.tl_v1.run import default_archive
    return default_archive()


def default_archive_hb() -> Path:
    from common.tsmom_fetch import default_archive
    return default_archive()


def daily_sha256(daily: dict) -> str:
    """Identity of the H-A daily rows used: SHA-256 over date/open/high/low/close of every market, in name order."""
    h = hashlib.sha256()
    for m in sorted(daily):
        f = daily[m]
        h.update(m.encode())
        h.update(pd.DatetimeIndex(f["date"]).asi8.tobytes())
        for c in ("open", "high", "low", "close"):
            h.update(np.ascontiguousarray(f[c].to_numpy(dtype=float)).tobytes())
    return h.hexdigest()


def hb_files(archive, roots=S.HB_ROOTS) -> dict:
    from strategy.w16.fetch import bar_path
    return {r: bar_path(Path(archive), r, "ohlcv-1m") for r in roots}


def build_and_run_preflight(books_path, *, ha_loader, hb_loader, hb_train_frames, hb_hashes=None,
                            expected_trades=S.HA_TRADES):
    """All the G2 work. `ha_loader(market) -> daily frame`; `hb_loader(root) -> 1-min frame`;
    `hb_train_frames(df_1m_training) -> {date_str: RTH session frame}` (strategy.w16.preflight.session_frames)."""
    books = BK.read_books(books_path, with_pnl=False)
    host = BK.host_a(books)
    daily_a = {m: ha_loader(m) for m in sorted(host["market"].unique())}
    sessions = {m: pd.DatetimeIndex(f["date"]) for m, f in daily_a.items()}
    rep_a = PF.run_ha(books, daily_a, sessions, expected_trades)

    entries, daily_b, counts, checks = {}, {}, {}, {}
    for root in S.HB_ROOTS:
        raw = hb_loader(root)
        daily, sw = BB.rebuild_daily(raw, strict=False)
        daily_b[root] = daily
        train_1m = BB.cut_training(raw.sort_index())
        frames = hb_train_frames(train_1m)
        keep_days, _, _ = HOLD.split_dates("H-B", list(frames))
        entries[root], counts[root] = BK.run_b1_entries(frames, root, keep_days)
        checks[root] = {"sessions": BB.session_check(daily), "switches": sw}
    rep_b = PF.run_hb(entries, daily_b, counts, checks)

    agree = None
    if "ES" in daily_a and len(daily_b.get("ES", [])):
        common = pd.DatetimeIndex(sorted(set(daily_a["ES"]["date"]) & set(daily_b["ES"]["date"])))
        agree = PF.agreement(otf_stack(daily_a["ES"]), rep_b["_stacks"]["ES"], common)
    return rep_a, rep_b, agree, input_hashes(books_path, daily_a, hb_hashes)


def input_hashes(books_path, daily_a, hb_hashes) -> dict:
    return {"books": PF.sha256(books_path), "h_a_daily_rows": daily_sha256(daily_a),
            **{f"h_b_{r}_1m": h for r, h in (hb_hashes or {}).items()}}


def otf_stack(daily):
    from strategy.otf_gate import otf
    return otf.Stack(daily)


def data_stop(rep_b: dict) -> bool:
    """G6: a rebuilt-session shortfall > 1% in any year, or a roll switch more than 5 minutes apart."""
    for ch in rep_b["checks"].values():
        if ch["sessions"]["stop"] or (len(ch["switches"]) and not bool(ch["switches"]["ok"].all())):
            return True
    return False


def write_preflight(out_txt: Path, rep_a, rep_b, agree, inputs) -> str:
    text = PF.render(rep_a, rep_b, agree=agree)
    if data_stop(rep_b):
        text = ("*** G6 DATA STOP: rebuilt sessions missing > 1% in a year, or a roll switch > 5 minutes apart. "
                "Report to Ben; no state result below is usable. ***\n\n") + text
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(text, encoding="utf-8")
    js = PF.clean(rep_a, rep_b, inputs)
    js["data_stop"] = bool(data_stop(rep_b))
    js["agreement"] = agree
    out_txt.with_suffix(".json").write_text(json.dumps(js, indent=1, default=str), encoding="utf-8")
    return text


def latest_preflight(out_dir: Path) -> Path | None:
    hits = sorted(Path(out_dir).glob(f"{STEM}_*.json"))
    return hits[-1] if hits else None


def require_preflight(out_dir: Path, inputs: dict) -> dict:
    pj = latest_preflight(out_dir)
    if pj is None:
        raise SystemExit("REFUSED: no pre-flight on disk. Run --preflight first (sec 5, G2).")
    rec = json.loads(pj.read_text(encoding="utf-8"))
    if rec["inputs_sha256"] != inputs:
        raise SystemExit(f"REFUSED: {pj.name} was made on different inputs. Re-run --preflight.")
    if rec["stop"] or rec.get("data_stop"):
        raise SystemExit(f"REFUSED: the pre-flight stopped (kept H-A {rec['kept_a']}, kept H-B {rec['kept_b']}, "
                         f"data stop {rec.get('data_stop')}). The counts are the finding; back to Ben before any P&L.")
    return rec


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- the registered sample, window, hosts and variants are fixed (sec 6, 7).\n")
        return 2
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--books", type=Path, default=BOOKS)
    ap.add_argument("--archive-ha", type=Path, default=None)
    ap.add_argument("--archive-hb", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT_DIR / f"{STEM}_{date.today().strftime('%Y%m%d')}.txt")
    a = ap.parse_args(argv)
    HOLD.load_for(a.books)

    from strategy.otf_gate.bars_ha import load_daily
    from strategy.w16.preflight import session_frames
    arch_a = a.archive_ha or default_archive_ha()
    arch_b = a.archive_hb or default_archive_hb()
    files = hb_files(arch_b)
    hashes = {r: PF.sha256(p) for r, p in files.items()}
    args = dict(ha_loader=lambda m: load_daily(arch_a, m), hb_loader=lambda r: BB.load_root(arch_b, r),
                hb_train_frames=session_frames, hb_hashes=hashes)
    if a.preflight:
        rep_a, rep_b, agree, inputs = build_and_run_preflight(a.books, **args)
        text = write_preflight(a.out, rep_a, rep_b, agree, inputs)
        print(text)
        print(f"wrote {a.out} / {a.out.with_suffix('.json')}")
        return 0
    host = BK.host_a(BK.read_books(a.books, with_pnl=False))
    require_preflight(a.out.parent, input_hashes(a.books, {m: args["ha_loader"](m) for m in sorted(host["market"].unique())}, hashes))
    raise SystemExit("--run: the pre-flight is on disk and cleared, but the study module (IBKR costs G5, C-R, sec 4 "
                     "criteria; W15-0025 sub 5, blocked by W15-0033) is not built yet.")


if __name__ == "__main__":
    sys.exit(main())
