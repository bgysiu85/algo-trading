"""pnl.py (raw held-contract booking, costs, daily MTM) and signals.py
(no look-ahead anywhere, weekly filter on completed weeks only)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.tl_v0_lines import find_pivots, walk_line_and_breaks
from strategy.tl_v0 import bars as B
from strategy.tl_v0 import pnl, signals as S
from strategy.tl_v0.sim import Trade
from strategy.tl_v0.spec import FRICTION, MARKETS
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows

M = MARKETS["CL"]            # $100/pt, $1 tick


@pytest.fixture(scope="module")
def frame():
    rows, con, _ = contracts_and_rows(n=900, carry=2.5)
    return B.build_bars(rows, con, ROOT, "XX").frame


def _trade_across_rolls(f, d=1, qty=3.0, stop_fill=False):
    rolls = np.nonzero(f["roll_after"].to_numpy())[0]
    e, x = int(rolls[0]) - 10, int(rolls[1]) + 10
    return Trade(d, e, x, float(f.loc[e, "open"]), float(f.loc[x, "close"]), np.nan, qty,
                 "stop" if stop_fill else "data_end", stop_fill), 2


def test_raw_legs_equal_the_adjusted_move_and_rolls_are_charged(frame):
    t, n_rolls = _trade_across_rolls(frame)
    b = pnl.book(t, frame, M)
    assert b.n_rolls == n_rolls and b.sides == 2 + 2 * n_rolls
    assert b.gross == pytest.approx(3.0 * 100 * (t.exit_px - t.entry_px))
    assert b.entry_contract != b.exit_contract
    # the raw entry is the old contract's own price, not the adjusted one
    assert b.entry_raw == pytest.approx(frame.loc[t.entry_j, "ro"])
    assert b.net("mid", 3.0) == pytest.approx(b.gross - FRICTION["mid"] * 3.0 * 6)


def test_booking_refuses_a_trade_whose_legs_do_not_add_up(frame):
    t, _ = _trade_across_rolls(frame)
    bad = frame.copy()
    R = int(np.nonzero(bad["roll_after"].to_numpy())[0][0])
    bad.loc[R, "new_close_raw"] += 1.0            # a wrong roll price
    with pytest.raises(pnl.BookingError):
        pnl.book(t, bad, M)


def test_booking_refuses_an_exit_outside_the_traded_contracts_bar(frame):
    t, _ = _trade_across_rolls(frame)
    x = t.exit_j
    wild = Trade(t.direction, t.entry_j, x, t.entry_px, float(frame.loc[x, "high"]) + 5.0,
                 np.nan, t.qty, "stop", True)
    with pytest.raises(pnl.BookingError):
        pnl.book(wild, frame, M)
    off_open = Trade(t.direction, t.entry_j, x, t.entry_px + 0.01, t.exit_px, np.nan, t.qty,
                     "data_end", False)
    with pytest.raises(pnl.BookingError):
        pnl.book(off_open, frame, M)


def test_slippage_is_one_vehicle_tick_per_contract_on_stop_fills_only(frame):
    t, _ = _trade_across_rolls(frame, stop_fill=True)
    assert pnl.book(t, frame, M).slip == pytest.approx(3.0 * M.tick_usd)
    t2, _ = _trade_across_rolls(frame, stop_fill=False)
    assert pnl.book(t2, frame, M).slip == 0.0


def test_the_daily_mark_to_market_sums_to_the_trade_list(frame):
    ts = []
    for e, x, d in ((50, 50, 1), (60, 140, -1), (200, 420, 1)):
        ts.append(Trade(d, e, x, float(frame.loc[e, "open"]), float(frame.loc[x, "low"]),
                        np.nan, 2.0, "stop", True))
    bs = [pnl.book(t, frame, M) for t in ts]
    dm = pnl.daily(ts, bs, frame, M)
    for i, lv in enumerate(("low", "mid", "high")):
        assert dm[:, i].sum() == pytest.approx(sum(b.net(lv, 2.0) for b in bs))


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------

def test_armed_line_next_agrees_with_the_walk(frame):
    c, h = frame["close"].to_numpy(), frame["high"].to_numpy()
    a = S.atr_gated(h, frame["low"].to_numpy(), c)
    ph = find_pivots(h, 5, "high")
    line, br = walk_line_and_breaks(len(c), ph, 5, c, a, "high")
    now, nxt = S.armed_line_next(len(c), ph, line, br)
    ok = ~np.isnan(now)
    assert ok.sum() > 50
    assert np.all(np.isnan(now[br]))                     # a broken line is not armed after the close
    conf = {p[1] for p in ph}
    j = np.array([k for k in range(len(c) - 1)
                  if ok[k] and not np.isnan(line[k + 1]) and (k + 1) not in conf])
    assert len(j) > 50
    assert np.allclose(nxt[j], line[j + 1])              # same line, one bar on
    assert np.all(np.isnan(nxt[~ok]))


@pytest.mark.parametrize("R", [3, 5, 8])
def test_no_signal_array_changes_when_the_future_is_cut_off(frame, R):
    """The strongest look-ahead guard available without the archive: every
    value known at close j must be identical whether or not bars after j
    exist. Catches peeking at the forming week, centred windows, anything
    computed on the whole series. Mutation-checked below."""
    full = S.market_signals(frame, R)
    for j in range(120, len(frame) - 1, 11):
        part = S.market_signals(frame.iloc[: j + 1].reset_index(drop=True), R)
        for name in ("up", "dn", "htf", "cand_v0_long", "cand_v0_short", "cand_rev_long",
                     "cand_rev_short", "swlo", "swhi", "atr"):
            a, b = getattr(full, name)[: j + 1], getattr(part, name)
            assert np.array_equal(a, b, equal_nan=True), (name, j)


def test_the_cutoff_guard_can_fail(frame, monkeypatch):
    """Mutation: let the weekly alignment use the CURRENT week (key without
    the 7-day step back) -- the guard above must then fail."""
    real = S.align_weekly

    def peeking(daily_dates, weekly, cols):
        dd = pd.DataFrame({"date": pd.to_datetime(daily_dates).astype("datetime64[ns]")})
        dd["key"] = dd["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize().astype("datetime64[ns]")
        dd = dd.reset_index().rename(columns={"index": "_orig"})
        w = weekly[["week_end"] + cols].sort_values("week_end").copy()
        w["week_end"] = w["week_end"].astype("datetime64[ns]")
        m = pd.merge_asof(dd.sort_values("key"), w, left_on="key", right_on="week_end",
                          direction="backward").sort_values("_orig")
        return m[cols].reset_index(drop=True)

    monkeypatch.setattr(S, "align_weekly", peeking)
    full = S.market_signals(frame, 3)
    diffs = 0
    for j in range(150, 700, 7):
        part = S.market_signals(frame.iloc[: j + 1].reset_index(drop=True), 3)
        diffs += int(not np.array_equal(full.htf[: j + 1], part.htf, equal_nan=True)
                     or not np.array_equal(full.cand_rev_long[: j + 1], part.cand_rev_long, equal_nan=True))
    assert diffs > 0
    monkeypatch.setattr(S, "align_weekly", real)


@pytest.mark.parametrize("R", [3, 5, 8])
def test_a_day_sees_only_the_prior_completed_week(frame, R):
    """Every day, not a sample: the weekly state a day reads is the last week
    that ENDED before that day's own week. Mutation: aligning to the current
    (forming) week changes the value on the days of every break week."""
    w = S.weekly_state(frame, R)
    al = S.align_weekly(frame["date"], w, ["dir", "sup_next", "res_next"])
    ends = w["week_end"].to_numpy()
    changed = 0
    for j, d in enumerate(frame["date"]):
        this_end = d.to_period("W-FRI").end_time.normalize().to_datetime64()
        k = np.searchsorted(ends, this_end, side="left") - 1      # last week_end < this week's
        if k < 0:
            assert np.isnan(al.loc[j, "dir"])
            continue
        for col in ("dir", "sup_next", "res_next"):
            assert np.array_equal([al.loc[j, col]], [w[col].iloc[k]], equal_nan=True), (j, col)
        if k + 1 < len(w) and not all(
                np.array_equal([w[c].iloc[k + 1]], [w[c].iloc[k]], equal_nan=True)
                for c in ("dir", "sup_next", "res_next")):
            changed += 1
    assert changed > 0          # the check above was exercised on break weeks


def test_weekly_atr_is_unknown_for_the_first_13_weeks(frame, monkeypatch):
    """Pine's ta.atr gives no value for the first 13 bars on the weekly chart
    too, so no weekly line can break there."""
    seen = []
    real = S.walk_line_and_breaks

    def spy(n, pivots, R, closes, atr, kind):
        seen.append(np.asarray(atr))
        return real(n, pivots, R, closes, atr, kind)

    monkeypatch.setattr(S, "walk_line_and_breaks", spy)
    S.weekly_state(frame, 3)
    assert len(seen) == 2
    for a in seen:
        assert np.isnan(a[:13]).all() and np.isfinite(a[13:]).all()
