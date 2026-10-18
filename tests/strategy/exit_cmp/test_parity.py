"""B-V1 in the rule engine reproduces the CHARTMARK-v1 engine trade for trade (the code-level twin of gate G2), money included."""
import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import book as BK
from strategy.exit_cmp import book as BKX
from tests.strategy.exit_cmp.helpers import world


@pytest.mark.parametrize("seed,roll", [(1, None), (2, 600), (3, 450), (4, None), (7, 900)])
def test_b_v1_reproduces_v1(seed, roll):
    fr, ind, trades, entries, st = world(seed=seed, roll_every=roll)
    assert len(trades) > 15
    mine = st.run("B-V1", "HOLD", cap=None)
    for t, x in zip(trades, mine):
        assert (x.exit_j, x.reason) == (t.exit_j, t.reason)
        assert x.exit_px == pytest.approx(t.exit_px, abs=1e-12)
    for sym in ("MCL", "CL"):
        for level in ("low", "mid", "high"):
            a = BKX.trade_frame(fr, entries, mine, st.roll_cum, sym, level)
            b = BK.trade_frame(trades, fr, sym, level)
            assert np.allclose(a["net"].to_numpy(), b["net"].to_numpy(), atol=1e-9)
            assert (a["entry_t"].astype(str).to_numpy() == b["entry_t"].astype(str).to_numpy()).all()
            assert (a["exit_t"].astype(str).to_numpy() == b["exit_t"].astype(str).to_numpy()).all()


def test_rolls_are_charged_two_extra_sides():
    fr, ind, trades, entries, st = world(seed=3, roll_every=450)
    df = BKX.trade_frame(fr, entries, st.run("B-V1", "HOLD", cap=None), st.roll_cum, "MCL", "mid")
    assert (df["n_rolls"] > 0).any()
    assert np.allclose(df["cost"], 1.77 * (2 + 2 * df["n_rolls"]))


def test_same_entries_for_every_rule_set():
    fr, ind, trades, entries, st = world(seed=4)
    for rid in ("B-STOP", "R-BEN", "R-MOM", "X-ALERT-touch", "X-JUMP"):
        df = BKX.trade_frame(fr, entries, st.run(rid, "FLAT"), st.roll_cum)
        assert (df["entry_j"].to_numpy() == np.array([x.e for x in entries])).all()
        assert (df["entry_px"].to_numpy() == np.array([x.entry_px for x in entries])).all()
