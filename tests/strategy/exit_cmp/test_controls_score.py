import numpy as np
import pandas as pd
import pytest

from strategy.exit_cmp import book as BKX
from strategy.exit_cmp import controls as CT
from strategy.exit_cmp import score as SC
from strategy.exit_cmp import spec as S
from tests.strategy.exit_cmp.helpers import world


def test_c_randx_with_the_identity_shuffle_is_the_baseline_exactly():
    """The vectorised control is checked against the walk: B-STOP's own holding times, unshuffled, give B-STOP's own net."""
    for scen in S.SCENARIOS:
        fr, ind, trades, entries, st = world(seed=3, n=6000, roll_every=700)
        base = st.run("B-STOP", scen)
        prep = CT.prepare(st, scen)
        hold = np.array([x.exit_j - en.e for x, en in zip(base, entries)])
        net = CT.draw_net(prep, hold, np.arange(len(hold)), "MCL", "mid")
        assert net == pytest.approx(float(BKX.trade_frame(fr, entries, base, st.roll_cum)["net"].sum()), abs=1e-9)


def test_c_randx_is_seeded_and_ordered():
    fr, ind, trades, entries, st = world(seed=3, n=6000)
    ex = st.run("R-BEN", "FLAT")
    a = CT.c_randx(st, "R-BEN", ex, "FLAT", draws=60)
    b = CT.c_randx(st, "R-BEN", ex, "FLAT", draws=60)
    assert a == b and a["p5"] <= a["p50"] <= a["p95"] <= a["p99"]
    assert CT.c_randx(st, "R-MOM", st.run("R-MOM", "FLAT"), "FLAT", draws=60) != a


def test_paired_refuses_a_different_entry_set():
    fr, ind, trades, entries, st = world(seed=3, n=6000)
    a = BKX.trade_frame(fr, entries, st.run("B-STOP", "FLAT"), st.roll_cum)
    with pytest.raises(ValueError):
        SC.paired(a.iloc[:-1], a)


def dframe(vals_by_year, per=10):
    rows = []
    for y, v in vals_by_year.items():
        for i in range(per):
            rows.append((pd.Timestamp(f"{y}-{1 + i % 12:02d}-10"), y, v / per))
    return pd.DataFrame(rows, columns=["entry_t", "year", "net"])


def test_criteria_pass_when_every_year_helps():
    d = dframe({y: 100.0 for y in range(2010, 2022)})
    r = SC.criteria("R-BEN", d_mid=d, d_high=d, rule_net_mid=-5000.0, c_p99=-6000.0, grid_positive=7, trigger_n=900)
    assert r["verdict"] == "PASS" and all(row[3] for row in r["rows"])


def test_one_year_carrying_everything_fails_several_criteria():
    d = dframe({**{y: -10.0 for y in range(2010, 2022)}, 2018: 2000.0})
    r = SC.criteria("R-BEN", d_mid=d, d_high=d, rule_net_mid=0.0, c_p99=-1.0, grid_positive=7, trigger_n=900)
    ok = {row[0]: row[3] for row in r["rows"]}
    assert r["verdict"] == "FAIL" and not ok[4] and not ok[5] and not ok[7]


def test_not_read_below_200_triggers_and_incomplete_without_the_grid():
    d = dframe({y: 100.0 for y in range(2010, 2022)})
    assert SC.criteria("X-JUMP", d_mid=d, d_high=d, rule_net_mid=1, c_p99=0, grid_positive=9, trigger_n=199)["verdict"].startswith("NOT READ")
    assert SC.criteria("X-JUMP", d_mid=d, d_high=d, rule_net_mid=1, c_p99=0, grid_positive=None, trigger_n=500)["verdict"] == "INCOMPLETE"


def test_halves_split_on_the_calendar():
    d = dframe({2015: 50.0, 2016: -10.0})
    assert SC.halves(d) == (50.0, -10.0)
