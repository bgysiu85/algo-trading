#!/usr/bin/env python3
"""G3 -- TL-bounce Pine <-> Python parity export. REGISTERED_tl_bounce.md
sec 5.1 (gate G3): touch bars, entries, stops and X1 exits, CL1! 4-hour,
2015-2019, back-adjustment OFF to match Ben's chart (TL_bounce.pine's own
header: "a plain continuous front-month chart, not adjusted").

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_bounce.parity_export

Writes one row per 4-hour bar in the window to
var/reports/tl_bounce_parity_python.csv, with the same series
TL_bounce.pine plots to its Data Window: sup, res, touch_long, touch_short,
sup_break, res_break, stop, pos, atr14. Ben diffs this against TradingView's
own CSV export of the same columns on the same chart/window (Data Window ->
Export chart data). Never compared by a chat reading Ben's live editor
(sec 7 -- see also the W15-0015 subitem-1 Update on why that line is not
crossed here either).

WHY RAW, NOT BACK-ADJUSTED
---------------------------
Every other TL-bounce/HTF-Ben run is on the back-adjusted series (sec 2.1).
This export is the one deliberate exception: TL_bounce.pine runs on Ben's
plain continuous CL1! chart, so G3 has to compare like with like -- the RAW
resampled bars, not back_adjust()'s output. market_signals() and e0_filter()
only read columns by the name *_adj, not by what adjustment (if any)
produced them, so the raw OHLC is passed through under those names
unmodified -- no adjustment math runs at all.

NO P&L, NO STOP-DISTANCE STATS -- this is a bar-by-bar SERIES export for a
diff, not a count or a dollar figure; that is preflight.py's job (G2).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.tl_bounce import lines as L
from strategy.tl_bounce import sim as S
from strategy.tl_bounce.signals import market_signals
from strategy.tl_bounce.spec import ATR_LEN, PIVOT_R

OUT_CSV = Path("var/reports/tl_bounce_parity_python.csv")
WINDOW_START = "2015-01-01"
WINDOW_END = "2019-12-31"


def _raw_as_adj(frame: pd.DataFrame) -> pd.DataFrame:
    """Alias raw open/high/low/close as *_adj so market_signals/e0_filter
    (which only ever read the *_adj columns) run on the UNADJUSTED series --
    see module docstring. No values are changed."""
    out = frame.copy()
    for c in ("open", "high", "low", "close"):
        out[c + "_adj"] = out[c]
    return out


def build_rows(archive_1h, *, engine_start: str | None = None) -> pd.DataFrame:
    df_1h = B.load_1h(archive_1h)
    if engine_start is not None:
        # DIAGNOSTIC (2026-09-28, first real G3 diff): a Pine indicator only
        # "remembers" back to whatever bar the chart has loaded when it's
        # added -- if that's later than this script's own archive start,
        # the two engines build genuinely different trade/line histories by
        # the comparison window (an open position or an armed line can
        # persist indefinitely), which is not a code bug but an unfair
        # comparison. This truncates the PYTHON side to start no earlier
        # than the Pine side's own first loaded bar, so both walks share
        # the same warm-up.
        df_1h = df_1h[df_1h.index >= pd.Timestamp(engine_start, tz="UTC")]
    entry_raw = _raw_as_adj(B.resample(df_1h, "4H"))
    higher_raw = _raw_as_adj(B.daily(df_1h))

    e0 = L.e0_filter(entry_raw, higher_raw, 24, R=PIVOT_R, atr_len=ATR_LEN)
    sig = market_signals(entry_raw, e0=e0)
    entries, _ = S.simulate(sig, e0_on=True, x1_on=True, allow_reentry=True)

    # pos[j]: the walk's position state as of bar j's close, reconstructed
    # from the entries list (sim.simulate() does not expose it per-bar
    # directly) -- flat from the entry bar up to but NOT including the exit
    # bar, matching TL_bounce.pine's own `pos := 0` on the exit bar (blocks
    # 1 and 3 there fire at that bar's OPEN, before this close is plotted).
    pos = np.zeros(sig.n, dtype=int)
    for e in entries:
        end = e.exit_j if e.exit_j is not None else sig.n
        pos[e.entry_j:end] = e.direction

    t = entry_raw["t_open"]
    mask = ((t >= pd.Timestamp(WINDOW_START, tz="UTC")) &
            (t <= pd.Timestamp(WINDOW_END, tz="UTC"))).to_numpy()
    df = pd.DataFrame({
        "t_open": t, "held_id": entry_raw["held_id"].to_numpy(),
        "open": entry_raw["open"].to_numpy(), "high": entry_raw["high"].to_numpy(),
        "low": entry_raw["low"].to_numpy(), "close": entry_raw["close"].to_numpy(),
        "sup": sig.sup, "res": sig.res,
        "touch_long": sig.touch_long.astype(int),
        "touch_short": sig.touch_short.astype(int),
        "sup_break": sig.sup_breaks.astype(int),
        "res_break": sig.res_breaks.astype(int),
        "pos": pos, "atr14": sig.atr,
    })
    return df.loc[mask].reset_index(drop=True)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="G3: TL-bounce Pine<->Python parity export (no P&L)")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    ap.add_argument("--engine-start", type=str, default=None,
                    help="truncate the 1H archive to start no earlier than "
                         "this date (diagnostic: match the Pine chart's own "
                         "first loaded bar so both engines share one "
                         "warm-up history -- see build_rows docstring)")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    df = build_rows(archive, engine_start=a.engine_start)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(f"G3 -- TL-bounce parity export: {len(df)} 4-hour bars, "
          f"{WINDOW_START} to {WINDOW_END}, back-adjustment OFF")
    print(f"wrote {a.out}")
    print("\nCompare against TradingView: paste TL_bounce.pine yourself "
          "(sec 7 -- never by a chat), CL1! chart, 4-hour, back-adjustment "
          "OFF, same window; Data Window -> Export chart data for sup, res, "
          "touch_long, touch_short, sup_break, res_break, pos, atr14; diff "
          "the two CSVs. Zero mismatches, or each one explained (sec 5.1 G3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
