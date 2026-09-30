#!/usr/bin/env python3
"""VA80 v1 runner, TRAINING SIDE ONLY. W15-0025.

    python -m strategy.va80.run --preflight --out "D:\\Trading\\Claude outputs\\w15_0025_va80_preflight_YYYYMMDD.txt"
    python -m strategy.va80.run --run        # refuses without a matching, cleared pre-flight

--preflight is COUNT-ONLY (sec 5, G2): value-area profiles from the PRIOR session, setups and triggers read only up
to each entry bar; counts per year, VA width, and trigger counts for the 27 neighbour cells. No outcome, no far-edge
rate, no P&L. It writes the .txt (the --out path) and a .json beside it with the SHA-256 of every input.

--run (outcomes, P&L) is the sub 5 step: refused unless a pre-flight on disk matches the current inputs and did not
stop, and until the study module (IBKR costs G5, C-RT / C-ND draws, sec 4 criteria) is built it stops there. No
--holdout, --limit, --spend, --seen, --markets, --window, --cells or --variant exists: those are refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.va80 import preflight as PF
from strategy.va80 import spec as S
from strategy.va80.engine import Store
from strategy.va80.holdout import H as HOLD

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "Claude outputs"
REFUSED = ("--holdout", "--limit", "--spend", "--seen", "--markets", "--window", "--cells", "--variant")
STEM = "w15_0025_va80_preflight"
ROOTS = ("ES", "NQ")


def default_archive() -> Path:
    from common.tsmom_fetch import default_archive
    return default_archive()


def cut_training(df_1m: pd.DataFrame, host: str = "ES") -> pd.DataFrame:
    """Keep only bars whose ET calendar date is a TRAINING day -- through the one split implementation, before any
    session, profile or bracket is built (G3)."""
    from strategy.w16.readback import local_naive_et
    et_day = local_naive_et(df_1m.index).strftime("%Y-%m-%d")
    keep, _, _ = HOLD.split_dates(host, sorted(set(et_day)))
    return df_1m.loc[pd.Series(et_day, index=df_1m.index).isin(set(keep)).to_numpy()]


def build_store(df_1m: pd.DataFrame, frames_fn) -> tuple[Store, dict, list]:
    """(store, frames, training XNYS days). `frames_fn(df) -> {date: RTH frame}` = strategy.w16.preflight.session_frames."""
    frames = frames_fn(cut_training(df_1m.sort_index()))
    keep, _, _ = HOLD.split_dates("ES", list(frames))
    frames = {d: frames[d] for d in keep}
    days = PF.days_for(min(frames), max(frames)) if frames else []
    return Store(frames), frames, days


def run_preflight(loader, frames_fn, roots=ROOTS):
    reps, hashes = {}, {}
    for r in roots:
        store, frames, days = build_store(loader(r), frames_fn)
        reps[r] = PF.run(store, days, r)
        hashes[f"{r}_session_frames"] = PF.sha256_frames(frames)
    return reps, hashes


def input_hashes(loader, frames_fn, roots=ROOTS) -> dict:
    """SHA-256 identity of the training session frames of each root (no counting)."""
    out = {}
    for r in roots:
        _, frames, _ = build_store(loader(r), frames_fn)
        out[f"{r}_session_frames"] = PF.sha256_frames(frames)
    return out


def write_preflight(out_txt: Path, reps, hashes) -> str:
    text = PF.render(reps)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(text, encoding="utf-8")
    out_txt.with_suffix(".json").write_text(json.dumps(PF.clean(reps, hashes), indent=1, default=str), encoding="utf-8")
    return text


def latest_preflight(out_dir: Path) -> Path | None:
    hits = sorted(Path(out_dir).glob(f"{STEM}_*.json"))
    return hits[-1] if hits else None


def require_preflight(out_dir: Path, hashes: dict) -> dict:
    pj = latest_preflight(out_dir)
    if pj is None:
        raise SystemExit("REFUSED: no pre-flight on disk. Run --preflight first (sec 5, G2).")
    rec = json.loads(pj.read_text(encoding="utf-8"))
    if rec["inputs_sha256"] != hashes:
        raise SystemExit(f"REFUSED: {pj.name} was made on different inputs. Re-run --preflight.")
    if rec["stop"]:
        raise SystemExit(f"REFUSED: the pre-flight stopped ({rec['triggers']} ES triggers < {S.MIN_TRIGGERS}). The counts "
                         "are the finding (sec 5 stop rule); back to Ben before any outcome is read.")
    return rec


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- the registered sample, window, cells and variants are fixed (sec 6, 7).\n")
        return 2
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT_DIR / f"{STEM}_{date.today().strftime('%Y%m%d')}.txt")
    a = ap.parse_args(argv)

    from strategy.otf_gate.preflight import sha256
    from strategy.w16.fetch import bar_path
    from strategy.w16.preflight import load_root_bars, session_frames
    arch = a.archive or default_archive()
    loader = lambda r: load_root_bars(arch, r)
    if a.preflight:
        reps, hashes = run_preflight(loader, session_frames)
        hashes.update({f"{r}_1m_file": sha256(bar_path(Path(arch), r, "ohlcv-1m")) for r in ROOTS})
        text = write_preflight(a.out, reps, hashes)
        print(text)
        print(f"wrote {a.out} / {a.out.with_suffix('.json')}")
        return 0
    hashes = input_hashes(loader, session_frames)
    hashes.update({f"{r}_1m_file": sha256(bar_path(Path(arch), r, "ohlcv-1m")) for r in ROOTS})
    require_preflight(a.out.parent, hashes)
    raise SystemExit("--run: the pre-flight is on disk and cleared, but the study module (IBKR costs G5, C-RT / C-ND "
                     "draws, sec 4 criteria; W15-0025 sub 5, blocked by W15-0033) is not built yet.")


if __name__ == "__main__":
    sys.exit(main())
