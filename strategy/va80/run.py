#!/usr/bin/env python3
"""VA80 v1 runner, TRAINING SIDE ONLY. W15-0025 (pre-flight, sub 4) and W15-0041 (study layer, sub 5).

    python -m strategy.va80.run --preflight --out "D:\\Trading\\Claude outputs\\w15_0025_va80_preflight_YYYYMMDD.txt"
    python -m strategy.va80.run --run --out "D:\\Trading\\Claude outputs\\w15_0025_va80_run_YYYYMMDD.txt"

--preflight is COUNT-ONLY (sec 5, G2): value-area profiles from the PRIOR session, setups and triggers read only up
to each entry bar; counts per year, VA width, and trigger counts for the 27 neighbour cells. No outcome, no far-edge
rate, no P&L. It writes the .txt (the --out path) and a .json beside it with the SHA-256 of every input.

--run reads outcomes and P&L: IBKR costs (Amendment 2), the 80% check, C-RT / C-ND (1,000 seeded draws), the 27-cell
grid, the reported variants, the seven criteria of sec 4. It is refused unless a pre-flight on disk matches the current
inputs (SHA-256 of the session frames and of the 1-minute files) and did not stop. It writes <stem>.txt, .md (for the
monday Result doc), .html (the artifact page) and .json beside the --out path. It never touches the holdout: no
--holdout, --limit, --spend, --seen, --markets, --window, --cells or --variant exists, those are refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.va80 import preflight as PF
from strategy.va80 import report as RP
from strategy.va80 import spec as S
from strategy.va80 import study as ST
from strategy.va80.engine import Store
from strategy.va80.holdout import H as HOLD

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "Claude outputs"
REFUSED = ("--holdout", "--limit", "--spend", "--seen", "--markets", "--window", "--cells", "--variant")
STEM = "w15_0025_va80_preflight"
RUN_STEM = "w15_0025_va80_run"
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


def run_study(loader, frames_fn, out_txt: Path, *, draws: int = S.CR_DRAWS, file_hashes: dict | None = None,
              log=print) -> list[Path]:
    """The sub 5 run. Builds the training stores once, checks them against the pre-flight on disk BEFORE any outcome is
    read, then runs the study and writes <stem>.txt / .md / .html / .json. Returns the four paths (txt first)."""
    out_txt = Path(out_txt)
    built = {r: build_store(loader(r), frames_fn) for r in ROOTS}
    hashes = {f"{r}_session_frames": PF.sha256_frames(built[r][1]) for r in ROOTS}
    hashes.update(file_hashes or {})
    require_preflight(out_txt.parent, hashes)
    res = ST.analyse({r: (built[r][0], built[r][2]) for r in ROOTS}, draws=draws, log=log)
    inputs = dict(hashes, preflight_json=latest_preflight(out_txt.parent).name)
    return RP.write_all(res, out_txt, inputs)


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
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    stamp = date.today().strftime("%Y%m%d")

    from strategy.otf_gate.preflight import sha256
    from strategy.w16.fetch import bar_path
    from strategy.w16.preflight import load_root_bars, session_frames
    arch = a.archive or default_archive()
    loader = lambda r: load_root_bars(arch, r)
    file_hashes = {f"{r}_1m_file": sha256(bar_path(Path(arch), r, "ohlcv-1m")) for r in ROOTS}
    if a.preflight:
        out = a.out or OUT_DIR / f"{STEM}_{stamp}.txt"
        reps, hashes = run_preflight(loader, session_frames)
        hashes.update(file_hashes)
        text = write_preflight(out, reps, hashes)
        print(text)
        print(f"wrote {out} / {out.with_suffix('.json')}")
        return 0
    out = a.out or OUT_DIR / f"{RUN_STEM}_{stamp}.txt"
    paths = run_study(loader, session_frames, out, file_hashes=file_hashes)
    print(paths[0].read_text(encoding="utf-8"))
    print("wrote " + " / ".join(str(p) for p in paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
