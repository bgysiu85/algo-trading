#!/usr/bin/env python3
"""CHARTMARK-S v3 G6 (sec 5): the same ten marks and tolerances as v2 (v2 Amendment 1 K6), counts only. If G6 fails the study
closes; the rule is not adjusted."""
from __future__ import annotations

import os
from pathlib import Path

from strategy.chartmark_s2.parity import ACCEPT_1, ACCEPT_2, REJECTED, fills_near, run as _run2      # noqa: F401
from strategy.chartmark_s3 import engine as E
from strategy.chartmark_s3 import spec as S

OUT = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))


def run(csv, log=print) -> tuple[str, bool]:
    return _run2(csv, log, simulate=E.simulate, params=S.BASE, name="CHARTMARK-S v3")


if __name__ == "__main__":
    run(OUT / "w15_0032_cl1_1h_bars_indicators.csv")
