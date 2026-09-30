#!/usr/bin/env python3
"""CHARTMARK-S v3 engine: v2's order machine, backstop and exits (strategy.chartmark_s2.engine, itself v1's), with v3's context."""
from __future__ import annotations

from strategy.chartmark_s2.engine import TradeT, simulate as _sim2                # noqa: F401
from strategy.chartmark_s3 import spec as S
from strategy.chartmark_s3.data import Frame, Ind, context_tiers


def simulate(fr: Frame, ind: Ind, p: S.Params = S.BASE, *, start: int = 40) -> tuple[list[TradeT], dict]:
    return _sim2(fr, ind, p, start=start, ctx_fn=context_tiers)
