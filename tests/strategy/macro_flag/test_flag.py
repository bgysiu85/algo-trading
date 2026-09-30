"""MFLAG-v1: the flag, its convention and look-ahead guards (REGISTERED_macro_flag_v1.md G4)."""
import numpy as np
import pandas as pd
import pytest

from strategy.macro_flag import flag as F
from strategy.macro_flag import spec as S
from tests.strategy.macro_flag import synth as Y


def _keys(dates, market="ES"):
    return pd.DataFrame({"market": market, "entry_date": pd.to_datetime(dates)})


def test_flag_cells_are_the_twelve_of_run_2b():
    n = sum(len(v) for v in S.FLAG_CELLS.values())
    assert n == 12 and set(S.FLAG_CELLS) == {"ES", "CL", "6A", "6E", "6J", "GC", "SI", "MTN"}
    assert "FOMC" not in S.FLAG_CELLS["MTN"]          # Holm 0.0504: not a flag cell
    assert "EIA_WPSR" not in S.FLAG_CELLS["CL"]
    assert not set(S.FLAG_CELLS) & {"RTY", "NG", "6B", "HG"}


def test_placebo_is_the_24_other_cells_and_disjoint():
    pc = S.placebo_cells()
    assert sum(len(v) for v in pc.values()) == 24
    for m, evs in pc.items():
        assert not set(evs) & set(S.FLAG_CELLS.get(m, ()))


def test_window_is_event_day_and_next_session():
    fri = pd.Timestamp("2015-03-06")                                # a Friday session
    nxt, prv, aft = pd.Timestamp("2015-03-09"), pd.Timestamp("2015-03-05"), pd.Timestamp("2015-03-10")
    cal = Y.calendar({"NFP": [fri]})
    keys = _keys([prv, fri, nxt, aft])
    h = F.hits(keys, {"ES": Y.SESSIONS}, cal, {"ES": ("NFP",)})
    got = {(int(r.idx), r.part) for r in h.itertuples()}
    assert got == {(1, "W1"), (2, "W2")}                            # not the day before, not d+2
    assert set(F.hits(keys, {"ES": Y.SESSIONS}, cal, {"ES": ("NFP",)}, "w1")["part"]) == {"W1"}
    assert set(F.hits(keys, {"ES": Y.SESSIONS}, cal, {"ES": ("NFP",)}, "w2")["part"]) == {"W2"}
    wide = F.hits(keys, {"ES": Y.SESSIONS}, cal, {"ES": ("NFP",)}, "wide")
    assert set(wide["idx"]) == {0, 1, 2}


def test_a_one_session_shift_of_the_calendar_breaks_the_flag():
    """Mutation test: if the window were computed off by one session, the flagged set must change."""
    days = Y.nfp_fridays()
    b = Y.books(markets=["ES"], n_per_market=200)
    keys = b.loc[b.spec == "C1", ["market", "entry_date"]].loc[lambda d: d.index < 10**9]
    keys = keys.iloc[:200].reset_index(drop=True)
    true = F.mask_from(keys.index, F.hits(keys, Y.sessions_all(), Y.calendar({"NFP": days}), {"ES": ("NFP",)}))
    shifted = [Y.SESSIONS[Y.SESSIONS.get_loc(d) + 1] for d in days]
    bad = F.mask_from(keys.index, F.hits(keys, Y.sessions_all(), Y.calendar({"NFP": shifted}), {"ES": ("NFP",)}))
    assert true.sum() > 0 and not np.array_equal(true, bad)


def test_flag_cannot_see_pnl():
    b = Y.books(markets=["ES"])
    with pytest.raises(ValueError):
        F.hits(b[["market", "entry_date", "net_mid"]], Y.sessions_all(), Y.calendar(), {"ES": ("NFP",)})
    keys = b.loc[b.spec == "C1", ["market", "entry_date"]].iloc[:60].reset_index(drop=True)
    cal = Y.calendar({"NFP": Y.nfp_fridays()})
    a = F.hits(keys, Y.sessions_all(), cal, {"ES": ("NFP",)})
    a2 = F.hits(keys.copy(), Y.sessions_all(), cal, {"ES": ("NFP",)})
    assert a.equals(a2)


def test_convention_check_passes_and_fails():
    b = Y.books(markets=["ES", "CL"])
    h = b[b.spec == "C1"].iloc[:100]
    assert F.check_convention(h, Y.sessions_all()) == len(h)
    bad = h.copy()
    bad["entry_j"] = bad["entry_j"] + 1
    with pytest.raises(F.ConventionError):
        F.check_convention(bad, Y.sessions_all())


def test_training_only():
    h = pd.DataFrame({"entry_date": pd.to_datetime(["2021-12-30", "2022-01-03"])})
    with pytest.raises(SystemExit):
        F.assert_training(h)
    F.assert_training(h.iloc[:1])
