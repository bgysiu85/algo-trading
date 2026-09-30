"""H-A daily rows (REGISTERED_otf_gate.md sec 2.3): the host's OWN daily rows -- strategy.tl_v0.bars.load_market,
training rows only (the loader cuts 2022-01-01 onward before any bar is built), UTC days with Sunday rows folded,
TSMOM roll rule, difference back-adjustment on the roll session. ISO weeks and calendar months of the session date
are built in otf.Stack (iso_week_key / month_key).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.otf_gate.holdout import H as HOLD

COLS = ["date", "open", "high", "low", "close"]


def load_daily(archive, market: str, loader=None) -> pd.DataFrame:
    """One market's signal-series daily rows. `loader(market) -> (MarketBars, c0)` is injectable for tests."""
    if loader is None:
        from strategy.tl_v0 import bars as B
        from strategy.tl_v0.spec import MARKETS
        from strategy.tsmom import archive as A
        A.read_manifest(Path(archive))
        loader = lambda n: B.load_market(Path(archive), MARKETS[n])
    mb = loader(market)[0]
    f = mb.frame[COLS].copy()
    f["date"] = pd.to_datetime(f["date"])
    # the loader already cut the holdout; assert it through the one implementation (G3/G4)
    keep, n_locked, _ = HOLD.split_dates("H-A", [d.strftime("%Y-%m-%d") for d in f["date"]])
    if n_locked:
        raise SystemExit(f"REFUSED: {market} daily rows include {n_locked} sessions after the H-A training end.")
    return f.reset_index(drop=True)
