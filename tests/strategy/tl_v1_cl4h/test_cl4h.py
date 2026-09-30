"""TL-v1 CL 4-hour variant (W15-0027): the training cut, the daily-in-place-of-weekly alignment,
booking and costs, and the run end to end. Each test breaks when the rule it names breaks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import costs as C
from strategy.tl_v0.sim import Trade
from strategy.tl_v1_cl4h import engine as E
from strategy.tl_v1_cl4h import run as RUN
from tests.strategy.htf.test_preflight import _synth_1h


@pytest.fixture(scope="module")
def synth():
    return _synth_1h(n_days=900, seed=3)


@pytest.fixture(scope="module")
def frames(synth):
    return E.build_frames(synth)


def _across_the_cut():
    df = _synth_1h(n_days=120, seed=5)
    df.index = df.index + (pd.Timestamp("2021-11-15", tz="UTC") - df.index[0])
    return df


def test_training_cut_happens_before_any_bar_exists():
    df = _across_the_cut()
    assert pd.to_datetime(df.index).year.max() == 2022          # the raw frame does reach 2022
    frame, daily = E.build_frames(df)
    assert frame["session"].max() <= pd.Timestamp(E.TRAIN_END)
    assert daily["session"].max() <= pd.Timestamp(E.TRAIN_END)
    assert frame["date"].dt.year.max() <= 2021 or frame["date"].max() < pd.Timestamp("2022-01-01 23:00")
    # mutation: cut_training is what does it
    assert len(E.cut_training(df)) < len(df)


def test_align_daily_never_sees_the_session_it_is_inside():
    ds = pd.DataFrame({"session": pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08"]),
                       "dir": [1.0, -1.0, 1.0], "res_next": [1.0, 2.0, 3.0], "sup_next": [1.0, 2.0, 3.0]})
    s4 = pd.Series(pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-05"]))
    out = E.align_daily(s4, ds, ["dir", "res_next"])
    assert np.isnan(out["dir"].iloc[0])                 # first session: nothing completed yet
    assert out["dir"].iloc[1] == 1.0 and out["res_next"].iloc[1] == 1.0     # session 07 sees 06
    assert out["dir"].iloc[2] == -1.0 and out["res_next"].iloc[2] == 2.0    # 08 sees 07
    assert out["dir"].iloc[3] == 1.0                                        # 09 sees 08
    assert np.isnan(out["dir"].iloc[4])


def test_htf_and_safety_line_use_only_completed_daily_sessions(frames):
    """Look-ahead guard: cutting the data after session k, and the daily bars after k - 1,
    leaves every 4H bar of session <= k unchanged."""
    frame, daily = frames
    sess = np.sort(frame["session"].unique())
    k = sess[len(sess) // 2]
    full = E.signals_4h(frame, daily, 5)
    f2 = frame[frame["session"] <= k].reset_index(drop=True)
    d2 = daily[daily["session"] < k].reset_index(drop=True)
    part = E.signals_4h(f2, d2, 5)
    m = len(f2)
    np.testing.assert_array_equal(full.htf[:m], part.htf)
    np.testing.assert_allclose(full.cand_rev_long[:m], part.cand_rev_long, equal_nan=True)
    # mutation: the weekly-based htf that market_signals itself computes is a different series
    from strategy.tl_v0.signals import market_signals
    assert not np.array_equal(market_signals(frame, 5).htf, full.htf)


def test_ctx_uses_the_daily_htf_and_a_training_only_er_threshold(frames):
    frame, daily = frames
    ctx = E.Ctx4H(frame, daily)
    np.testing.assert_array_equal(ctx.v0sig(5).htf, E.signals_4h(frame, daily, 5).htf)
    assert ctx.er_thr[0.25] == pytest.approx(float(np.nanquantile(ctx.er, 0.25)))


def _mini_frame(held):
    n = len(held)
    return pd.DataFrame({"date": pd.date_range("2020-01-01", periods=n, freq="4h"),
                         "session": pd.date_range("2020-01-01", periods=n, freq="4h").normalize(),
                         "held_id": held})


def test_roll_counting_ignores_a_change_at_the_entry_bar_and_counts_later_ones():
    held = np.array([1, 1, 2, 2, 3, 3])
    assert E.n_rolls(held, 0, 5) == 2
    assert E.n_rolls(held, 2, 5) == 1          # the 1->2 change is AT the entry bar's own contract
    assert E.n_rolls(held, 4, 4) == 0


def test_booking_costs_are_amendment_a_per_side_with_two_sides_per_roll():
    frame = _mini_frame([1, 1, 2, 2])
    t = Trade(1, 0, 3, 50.00, 51.00, 49.0, 1.0, "stop", True)
    df = E.book_trades([t], frame, qty_override=1.0)
    r = df.iloc[0]
    assert r["gross"] == pytest.approx(100.0)                      # $1.00 x 100 $/pt x 1 MCL
    assert r["n_rolls"] == 1
    for lv in ("low", "mid", "high"):
        assert r["cost_" + lv] == pytest.approx(C.per_side("MCL", lv) * 4)     # 2 sides + 2 for the roll
        assert r["net_" + lv] == pytest.approx(100.0 - C.per_side("MCL", lv) * 4)
    short = E.book_trades([Trade(-1, 0, 1, 50.0, 51.0, 52.0, 2.0, "stop", True)], frame).iloc[0]
    assert short["gross"] == pytest.approx(-1.0 * 2.0 * 100.0)


def test_fix_book_is_one_third_mcl_per_sleeve_and_one_mcl_alone(frames):
    frame, daily = frames
    ctx = E.Ctx4H(frame, daily)
    res, counts, gates = E.run_all(ctx, books=("FIX",))
    per = res["v1"]["FIX"]
    for (R, tag), df in per.items():
        if len(df):
            assert set(df["qty"]) == {1.0 / 3.0 if tag == "sleeve" else 1.0}
    assert (res["C1"]["FIX"]["qty"] == 1.0).all() if len(res["C1"]["FIX"]) else True
    assert set(res) == {"v1", "v1-A+", "v1-A3", "v1-2touch", "C2 v0-rev", "C1"}
    # the A+ checklist can only remove breaks, never add: v1's sleeve entries never exceed v1-A+'s by more than reversals
    g = gates[("v1", 5)]
    assert not (g.qual_up & ~g.raw_up).any() and not (g.qual_dn & ~g.raw_dn).any()


def test_c3_is_seeded_and_matches_the_daily_studys_coding(frames):
    frame, daily = frames
    ctx = E.Ctx4H(frame, daily)
    setup = E.c3_setup(ctx)
    a = E.c3_draw(ctx, setup, 7)
    b = E.c3_draw(ctx, setup, 7)
    assert a == b
    from strategy.tl_v1 import controls as K
    ref = K.c3_setup({"CL": ctx})
    for R in setup:
        assert setup[R]["n_sel"] == ref[("CL", R)]["n_sel"]


def test_runner_refuses_the_holdout_and_limit_and_writes_a_report_without_a_verdict(tmp_path, synth):
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--holdout"])
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--limit", "5"])
    rep = RUN.run(synth, tmp_path, "t", draws=5, log=lambda s: None)
    text = rep.read_text(encoding="utf-8")
    assert "REPORTED ONLY" in text and "SCOPED RUN" in text        # draws != 1000
    assert "VERDICT:" not in text.upper()
    names = {p.name for p in tmp_path.iterdir()}
    for kind in ("trades", "books", "counts", "c3", "grid"):
        assert f"w15_0027_tl_v1_cl4h_{kind}_t.csv" in names
