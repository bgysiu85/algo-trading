"""W05-0003 subitem 10 -- hand spot-check of the 19 trades flagged by G2's
broadened criterion (d) bad-tick screen (2026-09-24).

Same spirit as W12-0005's original 67-trade spot-check (docs/research/
REGISTERED_10sec.md 0.1, claude/w12_0005_orb_sip_recheck_RESULT_20260923.md):
look directly at the printed seconds around each flagged entry and judge
whether it's a real (if thin) trade or an isolated bad tick. Where that
spot-check used two aggregate numbers (a baseline median and a revert
median), this one prints the full second-by-second window so the judgment
isn't just re-deriving what the automated screen already computed -- it's
an independent look at the shape of the tape.

Usage (on D:\\Trading, in the repo's venv):
    python -m strategy.orb.badtick19_spotcheck
Writes var/reports/w05_0003_step10_badtick_spotcheck.txt and prints it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"
WINDOW_BEFORE = 60   # seconds before entry to show
WINDOW_AFTER = 30    # seconds after entry to show
CSV_DEFAULT = Path("var/cache/orb_sip/tensec_g2_trades.csv.gz")
GROUND_TRUTH_DEFAULT = Path("var/cache/orb_sip/entrybar_resolved.csv.gz")
OUT_DEFAULT = Path("var/reports/w05_0003_step10_badtick_spotcheck.txt")


def _flagged_population() -> pd.DataFrame:
    """Re-derive the 19-trade population from the live tensec_g2 scoring
    logic, rather than a hardcoded list, so this stays correct if the trades
    or the screen ever change."""
    from strategy.orb import tensec_g2 as G

    res = pd.read_csv(CSV_DEFAULT)
    gt_path = GROUND_TRUTH_DEFAULT
    ground_truth = (pd.read_csv(gt_path, encoding="utf-8") if gt_path.exists()
                     else pd.DataFrame(columns=["symbol", "date", "sec_entry_px", "sec_exit_px"]))
    sc = G.score(res, ground_truth)
    flagged = sc["gap"]["rows"]
    return res.merge(flagged[["symbol", "date"]], on=["symbol", "date"], how="inner")


def _window(archive: Path, symbol: str, day: str, entry_sec: int) -> pd.DataFrame:
    from common.dbn_io import read_dbn

    src = archive / DATASET / SCHEMA / f"{day}.dbn.zst"
    bars = read_dbn(src)
    et = bars.index.tz_convert("America/New_York")
    sod = (et.hour * 3600 + et.minute * 60 + et.second).to_numpy()
    m = bars["symbol"].to_numpy() == symbol
    sod_m = sod[m]
    order = np.argsort(sod_m, kind="stable")
    sod_m = sod_m[order]
    sub = bars[m].iloc[order].copy()
    sub["sod"] = sod_m
    lo, hi = entry_sec - WINDOW_BEFORE, entry_sec + WINDOW_AFTER
    return sub[(sub["sod"] >= lo) & (sub["sod"] <= hi)]


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    a = p.parse_args(argv)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()

    trades = _flagged_population()
    print(f"{len(trades):,} flagged trade(s) to spot-check")

    lines = [
        "W05-0003 STEP 10 -- HAND SPOT-CHECK OF G2 CRITERION (D)'S 19 FLAGGED TRADES",
        "  (2026-09-24, same method as W12-0005's 67-trade spot-check -- see",
        "   docs/research/REGISTERED_10sec.md 0.1 and the W12-0005 result doc)",
        "",
        f"  window shown: {WINDOW_BEFORE}s before entry to {WINDOW_AFTER}s after, ohlcv-1s",
        "",
    ]
    for r in trades.itertuples():
        entry_sec = int(r.sec_entry_sec)
        win = _window(archive, r.symbol, r.date, entry_sec)
        lines.append(f"{'=' * 70}")
        lines.append(f"{r.symbol}  {r.date}  entry_sec={entry_sec}  "
                      f"entry_px={r.sec_entry_px:.4f}  side={r.side}")
        lines.append(f"  automated screen: baseline_px={r.sec_entry_px_baseline:.4f}  "
                      f"revert_px={r.sec_entry_px_revert:.4f}  "
                      f"entry_vol={r.sec_entry_volume:.0f}  "
                      f"vol_baseline={r.sec_entry_vol_baseline:.1f}")
        lines.append(f"  {'sod':>7} {'hh:mm:ss':>10} {'open':>10} {'high':>10} "
                      f"{'low':>10} {'close':>10} {'volume':>8}")
        for row in win.itertuples():
            hh, mm, ss = int(row.sod // 3600), int(row.sod % 3600 // 60), int(row.sod % 60)
            marker = "  <-- ENTRY" if int(row.sod) == entry_sec else ""
            vol = row.volume if hasattr(row, "volume") else float("nan")
            lines.append(f"  {int(row.sod):>7} {hh:02d}:{mm:02d}:{ss:02d} "
                          f"{row.open:>10.4f} {row.high:>10.4f} {row.low:>10.4f} "
                          f"{row.close:>10.4f} {vol:>8.0f}{marker}")
        lines.append("")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
