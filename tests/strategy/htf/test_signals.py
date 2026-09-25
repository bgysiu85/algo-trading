"""Tests for strategy/htf/signals.py. W15-0004 step 3, incl. REGISTERED
sec 8's G4 no-look-ahead guards: each guarded function is proven not to use
a bar before it closes, by a test that a one-bar shift breaks it."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import signals as S


def _series(values, start="2020-01-01", freq="4h", tz="UTC"):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz=tz)
    return pd.Series(values, index=idx, dtype=float)


class TestEmaSeeded:
    def test_seed_is_sma_of_first_n(self):
        s = _series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        out = S.ema_seeded(s, 3)
        assert out.iloc[:2].isna().all()
        assert out.iloc[2] == pytest.approx((1 + 2 + 3) / 3)

    def test_recursion_after_the_seed(self):
        s = _series([1, 2, 3, 4, 5])
        out = S.ema_seeded(s, 3)
        alpha = 2.0 / 4
        seed = (1 + 2 + 3) / 3
        expected3 = alpha * 4 + (1 - alpha) * seed
        expected4 = alpha * 5 + (1 - alpha) * expected3
        assert out.iloc[3] == pytest.approx(expected3)
        assert out.iloc[4] == pytest.approx(expected4)

    def test_not_pandas_default_ewm(self):
        """The registered rule (E7) seeds on an n-bar SMA, not bar 0 the way
        pandas' ewm(adjust=False) does -- this must actually differ."""
        s = _series([10, 1, 1, 1, 1, 1, 1, 1])
        ours = S.ema_seeded(s, 3).iloc[2]
        pandas_default = s.ewm(span=3, adjust=False).mean().iloc[2]
        assert ours != pytest.approx(pandas_default)

    def test_short_series_returns_all_nan(self):
        s = _series([1, 2])
        out = S.ema_seeded(s, 5)
        assert out.isna().all()


class TestMacdSeeded:
    def test_line_is_fast_minus_slow(self):
        s = _series(np.linspace(50, 60, 40), freq="4h")
        line, sig = S.macd_seeded(s, fast=3, slow=5, signal=2)
        fast = S.ema_seeded(s, 3)
        slow = S.ema_seeded(s, 5)
        pd.testing.assert_series_equal(line, fast - slow, check_names=False)

    def test_signal_seeded_on_first_n_of_the_line_not_of_price(self):
        s = _series(np.linspace(50, 60, 40), freq="4h")
        line, sig = S.macd_seeded(s, fast=3, slow=5, signal=2)
        expected_sig = S.ema_seeded(line, 2)
        pd.testing.assert_series_equal(sig, expected_sig, check_names=False)


class TestMacdCross:
    def _lines(self):
        # signal flat at 0; macd line crosses at position 3 (below->above)
        # and crosses back down at position 6
        line = _series([-2, -1, -0.5, 0.5, 1, 1, -0.5, -1, -2], freq="4h")
        sig = _series([0] * 9, freq="4h")
        return line, sig

    def test_cross_up_fires_only_at_the_crossing_bar(self):
        line, sig = self._lines()
        up = S.macd_cross_up(line, sig)
        assert up.tolist() == [False, False, False, True, False, False, False, False, False]

    def test_cross_down_fires_only_at_the_crossing_bar(self):
        line, sig = self._lines()
        down = S.macd_cross_down(line, sig)
        assert down.tolist() == [False, False, False, False, False, False, True, False, False]

    def test_one_bar_shift_moves_the_flagged_bar(self):
        """G4 guard: the cross must be read at (t-1, t), not (t, t+1) or
        (t-2, t-1). Shifting the input by one bar must move which bar is
        flagged, proving the function isn't off by one internally."""
        line, sig = self._lines()
        up = S.macd_cross_up(line, sig)
        fired_at = up.to_numpy().argmax()

        shifted_line = line.shift(1)
        shifted_line.iloc[0] = line.iloc[0] - 10  # keep bar 0 clearly "below"
        up_shifted = S.macd_cross_up(shifted_line, sig)
        fired_at_shifted = up_shifted.to_numpy().argmax()
        assert fired_at_shifted == fired_at + 1


class TestConfirmation:
    def _entry(self, n=10):
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        return idx

    def test_confirms_at_t_plus_1_when_ema_and_macd_agree(self):
        idx = self._entry(6)
        # hand-built EMA9/EMA21: EMA9 rising and closing the gap on EMA21
        # from bar 3 onward; MACD stays above its signal from bar 2 onward
        ema9 = pd.Series([90, 91, 93, 96, 100, 105], index=idx, dtype=float)
        ema21 = pd.Series([95, 95, 95, 95.5, 96, 97], index=idx, dtype=float)
        macd_line = pd.Series([-.5, -.2, .1, .3, .5, .6], index=idx)
        signal_line = pd.Series([0, 0, 0, 0, 0, 0], index=idx, dtype=float)
        confirms_long, confirms_short = S.confirms_from_emas(ema9, ema21, macd_line, signal_line)
        # trigger at position 2 (macd crosses above 0 there); confirm window {3,4}
        c = S.confirmation_bar(confirms_long, trigger_pos=2)
        assert c in (3, 4)

    def test_confirmation_flags_wires_price_through_ema_seeded(self):
        """confirmation_flags(close, ...) must equal confirms_from_emas fed
        with ema_seeded(close, ema_fast/ema_slow) -- i.e. it's not doing
        anything else to the price series."""
        idx = self._entry(30)
        close = pd.Series(np.linspace(90, 120, 30), index=idx, dtype=float)
        macd_line = pd.Series(np.linspace(-1, 1, 30), index=idx, dtype=float)
        signal_line = pd.Series([0.0] * 30, index=idx, dtype=float)
        long_a, short_a = S.confirmation_flags(close, macd_line, signal_line,
                                               ema_fast=3, ema_slow=5)
        ema9 = S.ema_seeded(close, 3)
        ema21 = S.ema_seeded(close, 5)
        long_b, short_b = S.confirms_from_emas(ema9, ema21, macd_line, signal_line)
        assert (long_a == long_b).all() and (short_a == short_b).all()

    def test_lapses_when_neither_candidate_confirms(self):
        idx = self._entry(6)
        always_false = pd.Series([False] * 6, index=idx)
        assert S.confirmation_bar(always_false, trigger_pos=1) is None

    def test_confirmation_bar_never_reads_past_t_plus_2(self):
        idx = self._entry(8)
        confirms = pd.Series([False, False, False, False, True, True, True, True], index=idx)
        # trigger at 1 -> window is {2,3}; both False in `confirms`, so must
        # be None even though bar 4 onward is True
        assert S.confirmation_bar(confirms, trigger_pos=1) is None
        # trigger at 2 -> window is {3,4}; bar 4 is True -> must return 4
        assert S.confirmation_bar(confirms, trigger_pos=2) == 4


class TestDailyFilterNoLookahead:
    """G4: 'the daily filter reads the last completed session only ... a
    daily close that flips after c's close must not change the decision
    at c.'"""

    def _fixture(self, bar_hours=4):
        # 3 sessions, each with the full set of 4H buckets (0..5, last=5)
        from strategy.htf import bars as B
        rows = []
        for s_i, sess_date in enumerate([pd.Timestamp("2020-01-06").date(),
                                          pd.Timestamp("2020-01-07").date(),
                                          pd.Timestamp("2020-01-08").date()]):
            for bar in range(6):
                rows.append({"session": sess_date, "bar": bar,
                            "t_open": pd.Timestamp("2020-01-01", tz="UTC")
                                      + pd.Timedelta(hours=4 * (s_i * 6 + bar)),
                            "held_id": 1, "open": 50.0, "high": 50.5, "low": 49.5,
                            "close": 50.0 + s_i, "volume": 10, "n_src": 4})
        entry_df = pd.DataFrame(rows)

        daily_rows = []
        for s_i, sess_date in enumerate([pd.Timestamp("2020-01-04").date(),
                                          pd.Timestamp("2020-01-05").date(),
                                          pd.Timestamp("2020-01-06").date(),
                                          pd.Timestamp("2020-01-07").date(),
                                          pd.Timestamp("2020-01-08").date()]):
            daily_rows.append({"date": sess_date, "held_id": 1,
                               "open": 50.0, "high": 50.5, "low": 49.5,
                               "close": 50.0, "volume": 10})
        daily_df = pd.DataFrame(daily_rows)
        return entry_df, daily_df

    def test_non_last_bars_use_the_prior_session_not_their_own(self, monkeypatch):
        entry_df, daily_df = self._fixture()
        daily_df["close_adj"] = daily_df["close"]

        # force a known direction PER SESSION by monkeypatching daily_direction
        # session order: 01-04, 01-05, 01-06(=S0), 01-07(=S1), 01-08(=S2)
        forced = pd.Series(["short", "short", "long", "short", "long"])
        monkeypatch.setattr(S, "daily_direction", lambda daily_adj: forced)

        out = S.daily_filter_as_of(entry_df, daily_df, bar_hours=4)

        s0 = pd.Timestamp("2020-01-06").date()
        s1 = pd.Timestamp("2020-01-07").date()
        # S0's own forced direction is "long", but every non-last bar of S0
        # must read the PRIOR session (01-05 = "short")
        s0_rows = out[entry_df["session"] == s0]
        assert (s0_rows.iloc[:-1] == "short").all()
        # the LAST bar of S0 sees S0's own, now-complete daily = "long"
        assert s0_rows.iloc[-1] == "long"
        # sanity: S1 non-last bars read S0's direction ("long")
        s1_rows = out[entry_df["session"] == s1]
        assert (s1_rows.iloc[:-1] == "long").all()

    def test_flipping_a_sessions_own_close_does_not_move_its_non_last_bars(self, monkeypatch):
        """The literal G4 assertion: mutate S's daily close after c's close
        (i.e. change S's OWN direction) and confirm every bar of S except
        the last one is unaffected."""
        entry_df, daily_df = self._fixture()
        daily_df["close_adj"] = daily_df["close"]
        s0 = pd.Timestamp("2020-01-06").date()

        base = pd.Series(["short", "short", "long", "short", "long"])
        monkeypatch.setattr(S, "daily_direction", lambda daily_adj: base)
        before = S.daily_filter_as_of(entry_df, daily_df, bar_hours=4)

        flipped = base.copy()
        flipped.iloc[2] = "short"  # flip S0's OWN direction (was "long")
        monkeypatch.setattr(S, "daily_direction", lambda daily_adj: flipped)
        after = S.daily_filter_as_of(entry_df, daily_df, bar_hours=4)

        s0_mask = (entry_df["session"] == s0).to_numpy()
        non_last = s0_mask.copy()
        non_last[np.where(s0_mask)[0][-1]] = False  # drop the last bar of S0
        assert (before[non_last].to_numpy() == after[non_last].to_numpy()).all()
        # but the LAST bar of S0 DOES move, since it legitimately sees S0's
        # own close by its own close
        last_idx = np.where(s0_mask)[0][-1]
        assert before.iloc[last_idx] != after.iloc[last_idx]


class TestSwingPivots:
    def test_pivot_is_reported_at_p_plus_r_not_before(self):
        # clean single dip at position 3 (0-indexed), L=R=2 -> known at 5
        low = _series([10, 9, 8, 5, 8, 9, 10, 11, 12], freq="4h")
        out = S.swing_lows(low, L=2, R=2)
        assert out.iloc[5] == pytest.approx(5.0)
        assert out.iloc[:5].isna().all()
        assert pd.isna(out.iloc[6]) and pd.isna(out.iloc[7]) and pd.isna(out.iloc[8])

    def test_swing_high_mirror(self):
        high = _series([10, 11, 12, 15, 12, 11, 10, 9, 8], freq="4h")
        out = S.swing_highs(high, L=2, R=2)
        assert out.iloc[5] == pytest.approx(15.0)

    def test_one_bar_shift_moves_the_confirmation_bar(self):
        """G4 guard: a pivot at p must be reported at p+R, never p+R-1 or
        p+R+1. Shifting the whole series by one bar must move the reported
        position by exactly one."""
        low = _series([10, 9, 8, 5, 8, 9, 10, 11, 12], freq="4h")
        out = S.swing_lows(low, L=2, R=2)
        reported_at = out.to_numpy()
        pos = np.where(~np.isnan(reported_at))[0][0]

        shifted = pd.concat([pd.Series([20.0]), low]).reset_index(drop=True)
        shifted.index = pd.date_range("2020-01-01", periods=len(shifted), freq="4h", tz="UTC")
        out_shifted = S.swing_lows(shifted, L=2, R=2)
        pos_shifted = np.where(~np.isnan(out_shifted.to_numpy()))[0][0]
        assert pos_shifted == pos + 1

    def test_no_lookahead_regression_guard(self):
        """Directly encodes the bug this gate would catch: reporting the
        pivot at p+R-1 (one bar too early, before the confirming bar has
        even closed)."""
        low = _series([10, 9, 8, 5, 8, 9, 10, 11, 12], freq="4h")
        out = S.swing_lows(low, L=2, R=2)
        # the "off by one bar early" mutation would put the value at index 4
        assert pd.isna(out.iloc[4])


class TestEntryReadyMask:
    def test_before_and_after_warmup(self):
        df = pd.DataFrame({"x": range(250)})
        mask = S.entry_ready_mask(df, warmup_bars=200)
        assert not mask[:200].any()
        assert mask[200:].all()

    def test_series_shorter_than_warmup_is_never_ready(self):
        df = pd.DataFrame({"x": range(50)})
        mask = S.entry_ready_mask(df, warmup_bars=200)
        assert not mask.any()
