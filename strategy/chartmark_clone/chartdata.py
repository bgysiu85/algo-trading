#!/usr/bin/env python3
"""Indicator and daily data behind the chart: everything is computed causally from the 1H frame (bars <= t only matter)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.chartmark.data import Frame, Ind, indicators
from strategy.chartmark_clone import daily as DL
from strategy.htf.signals import macd_seeded


@dataclass
class ChartData:
    fr: Frame
    ind: Ind
    macd: np.ndarray
    sig: np.ndarray
    daily: DL.Daily
    hour: np.ndarray
    wday: np.ndarray


def build_chart_data(fr: Frame) -> ChartData:
    ind = indicators(fr)
    line, sig = macd_seeded(pd.Series(fr.c))
    ny = fr.ny
    return ChartData(fr, ind, line.to_numpy(), sig.to_numpy(), DL.build_daily(fr),
                     np.asarray(ny.hour), np.asarray(ny.weekday))
