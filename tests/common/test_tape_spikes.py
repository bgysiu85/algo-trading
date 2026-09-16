#!/usr/bin/env python3
"""The spike census measures what it says and prints what a decision needs."""
from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from common import tape_spikes as S


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_spike_mask_flags_a_high_or_low_far_from_both_open_and_close():
    d = bars([(8.6, 20.05, 6.7, 8.62),    # ALTS 08:07: both
              (9.0, 9.06, 8.84, 8.87),     # ordinary
              (8.83, 19.24, 8.77, 8.87),   # high only
              (8.98, 9.10, 6.82, 8.96),    # low only
              (5.0, 6.0, 5.0, 5.9)])       # a real 20% bar whose close follows: not a spike
    assert list(S.spike_mask(d)) == [True, False, True, True, False]


def test_the_threshold_is_symmetric_in_ratio():
    up = bars([(4.0, 5.01, 4.0, 4.0)])       # 25.25% over
    dn = bars([(4.0, 4.0, 3.19, 4.0)])       # 4/3.19 = 1.254
    edge = bars([(4.0, 5.0, 3.2, 4.0)])      # exactly 1.25 both ways: not a spike
    assert bool(S.spike_mask(up)[0]) and bool(S.spike_mask(dn)[0])
    assert not bool(S.spike_mask(edge)[0])


def fake_day(spikes, dump, of, mcl, month="2025-08"):
    return {"bars": 1000, "spikes": spikes, "by_minute": Counter({"08:07": spikes}),
            "by_hour": Counter({8: spikes}), "symbols": 10, "symbols_spiking": 2,
            "spike_syms_0800": 2, "dump": dump, "dump_of": of, "mcl": mcl, "ib": None}


def test_render_attributes_mcl_trades_by_spike_and_hour():
    F = S.MEASURED_FRICTION
    mcl = [{"symbol": "A", "date": "2025-08-11", "net": -100 + F, "entry_spike": True, "exit_spike": True, "entry_hour": 8, "reason": "trailing_stop"},
           {"symbol": "B", "date": "2025-08-11", "net": 10 + F, "entry_spike": False, "exit_spike": False, "entry_hour": 6, "reason": "trailing_stop"},
           {"symbol": "C", "date": "2025-08-11", "net": -5 + F, "entry_spike": False, "exit_spike": False, "entry_hour": 8, "reason": "window_close"}]
    got = {"2025-08-11": fake_day(60, 1162, 1771, mcl)}
    txt = "\n".join(S.render(["2025-08-11"], got, 1.0, 1, None))
    assert "08:00" in txt and "60" in txt
    assert "either" in txt and "(100.00)" in txt
    assert "neither, entered 08:00-08:59" in txt
    assert "1,162" in txt and "66%" in txt
    assert "WHAT THIS DECIDES" in txt


def test_render_with_ib_rows_prints_the_cross_check():
    got = {"2025-08-11": fake_day(3, 0, 1, [])}
    got["2025-08-11"]["ib"] = [{"symbol": "A", "ib_bars": 300, "ib_spikes": 0, "xn_bars": 330, "xn_spikes": 3}]
    txt = "\n".join(S.render(["2025-08-11"], got, 1.0, 1, "bar_cache/3d_to_2000"))
    assert "THE SAME SYMBOL-DAYS ON IB'S BARS" in txt and "1 symbol-days" in txt
