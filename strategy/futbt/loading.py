#!/usr/bin/env python3
"""Loading the training-side frames for the W15-0022 runners (Ben's machine only: reads the archive).

Daily (12 markets): strategy.tl_v0.bars.load_rows / build_bars, which cut 2022-01-01 onward BEFORE any
row is folded or any bar built (common.tl_v0_holdout.split_dates), plus held-contract volume.

CL 4-hour (BREIT-CAP's scored secondary, CRUDELE's reported variant): CL.c.0 1-hour bars from
strategy.htf.bars.load_1h. UNLIKE the daily loader, load_1h returns every bar in the file, so the cut is
made HERE, first, on the SESSION date (18:00 New York open), before resampling or back-adjusting:
sessions on or after 2022-01-01 are dropped (the registered training window, 2010-06 -> 2021-12-31).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.futbt import core as K
from strategy.futbt.holdout import LOCK_FROM
from strategy.tl_v0.spec import MARKETS

CL4H_TRAIN_START = "2010-06-06"


def default_archive() -> Path:
    from common.tsmom_fetch import DATASET, default_archive as da
    return da() / DATASET


def load_daily(archive: Path, names: list[str], *, loader=None, log=print) -> tuple[dict, dict]:
    """{market: Frame}, {market: notes}. `loader(name) -> (Frame, notes)` is injectable for tests."""
    if loader is None:
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        def loader(name):
            fr, _mb, notes = K.load_market_v(archive, MARKETS[name])
            return fr, notes
    frames, notes = {}, {}
    for name in names:
        fr, nt = loader(name)
        frames[name], notes[name] = fr, nt
        log(f"{name}: {fr.n} sessions {fr.dates[0].date()} .. {fr.dates[-1].date()}")
    return frames, notes


def cut_1h_to_training(df_1h: pd.DataFrame) -> pd.DataFrame:
    from strategy.htf import bars as HB
    naive = HB.local_naive(df_1h.index)
    sess = HB.session_of(naive)
    keep = (sess < pd.Timestamp(LOCK_FROM)) & (sess >= pd.Timestamp(CL4H_TRAIN_START))
    return df_1h[keep.to_numpy() if hasattr(keep, "to_numpy") else keep]


def frame_cl4h_from_1h(df_1h: pd.DataFrame) -> K.Frame:
    from strategy.htf import bars as HB
    df = cut_1h_to_training(df_1h)
    entry = HB.back_adjust(HB.resample(df, "4H"))
    return K.frame_from_4h(entry, MARKETS["CL"])


def load_cl4h(archive: Path) -> K.Frame:
    from strategy.htf import bars as HB
    return frame_cl4h_from_1h(HB.load_1h(archive))
