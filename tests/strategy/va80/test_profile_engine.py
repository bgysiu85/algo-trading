"""VA80: profile / POC / value area (every tie rule), setup / trigger / exits, and the G4 look-ahead guards."""
import numpy as np
import pytest

from strategy.va80 import engine as E
from strategy.va80 import spec as S
from strategy.va80.profile import build_profile, value_area
from tests.strategy.va80 import synth as Y

T = 0.25


def _ladder(vols, base=100.0, last_close=None):
    """A profile with exactly `vols` volume on consecutive ticks from `base` (one single-tick bar per tick)."""
    px = base + T * np.arange(len(vols))
    return build_profile(px, px, np.array(vols, dtype=float), last_close if last_close is not None else base)


# ------------------------------------------------------------------ profile
def test_hand_built_session_poc_vah_val():
    p = _ladder([1, 2, 4, 8, 10, 8, 4, 2, 1])            # total 40 -> 70% = 28
    assert p.total == 40 and p.price(p.poc) == 101.0
    # 10 -> +8 above (tie above wins) 18 -> +8 below 26 -> +4 above (tie above) 30 >= 28: stop
    assert value_area(p) == (100.75, 101.5)


def test_va_tie_goes_to_the_tick_above_and_the_next_larger_side_wins():
    p = _ladder([5, 5, 10, 5, 5])                        # POC middle; up == down every step -> always above first
    val, vah = value_area(p, 0.5)                        # need 15: 10 +5(above)
    assert (val, vah) == (100.5, 100.75)
    q = _ladder([7, 1, 10, 6, 1])                        # below (1) < above (6): above first, then below 1 vs above 1 -> above
    val, vah = value_area(q, 0.75)                       # total 25, need 18.75: 10+6=16, +1(tie: above)=17, +7? below is 1 -> ...
    assert vah >= 100.75 and val <= 100.5


def test_poc_ties_go_to_the_tick_closest_to_the_prior_close_then_the_lower():
    vols = [1, 5, 2, 5, 1]
    assert _ladder(vols, last_close=100.25).price(_ladder(vols, last_close=100.25).poc) == 100.25   # nearer idx1
    p3 = _ladder(vols, last_close=100.75)
    assert p3.price(p3.poc) == 100.75                                                                # nearer idx3
    p2 = _ladder(vols, last_close=100.5)                                                            # exactly equidistant
    assert p2.price(p2.poc) == 100.25                                                                # -> the lower one


def test_volume_is_spread_evenly_over_every_tick_of_a_bar():
    p = build_profile([101.0], [100.0], [10.0], 100.5)     # 5 ticks: 100.0 .. 101.0
    assert p.vol.tolist() == [2.0] * 5 and p.total == 10.0
    p2 = build_profile([101.0, 100.5], [100.0, 100.5], [10.0, 4.0], 100.5)
    assert p2.vol.tolist() == [2.0, 2.0, 6.0, 2.0, 2.0]


def test_exact_share_stops_the_area_and_float_error_does_not_add_a_tick():
    p = _ladder([1] * 10)                                # POC tie: closest to last close (100.0) -> idx 0
    assert p.price(p.poc) == 100.0
    val, vah = value_area(p, 0.7)                        # need 7 of 10 -> exactly 7 ticks
    assert (vah - val) / T == 6
    p3 = _ladder([1, 1, 1])                              # 3 * 0.7 = 2.0999999999999996 vs 0.3*7 style floats
    assert value_area(p3, 0.6667) is not None


def test_area_stops_at_the_profile_edge_when_one_side_runs_out():
    p = _ladder([9, 1, 1, 1], last_close=100.0)          # POC at the very bottom; only ticks above
    val, vah = value_area(p, 0.9)                        # need 10.8 of 12: 9 + 1 + 1
    assert val == 100.0 and vah == 100.5
    assert value_area(_ladder([3.0]), 0.7) == (100.0, 100.0)


# ------------------------------------------------------------------ session validity
def test_session_ok_missing_open_gap_and_tail():
    s = Y.path_sess()
    assert E.session_ok(s)
    drop = lambda idx: E.Sess(s.date, np.delete(s.minute, idx), *(np.delete(a, idx) for a in (s.o, s.h, s.l, s.c, s.v)), s.inst, s.close_min)
    assert not E.session_ok(drop([0]))                                    # no 09:30 bar
    assert E.session_ok(drop(list(range(50, 54))))                        # 5-minute gap between starts (gap = 5): ok
    assert not E.session_ok(drop(list(range(50, 55))))                    # gap of 6 minutes: skipped
    assert not E.session_ok(drop(list(range(385, 390))))                  # the last 5 bars missing: a tail gap of 6
    early = Y.path_sess(close_min=780)
    assert E.session_ok(early) and early.n == 210


# ------------------------------------------------------------------ setup / trigger (VAL = 100, VAH = 110)
VAL, VAH = 100.0, 110.0
DOWN_IN = ((570, 112.0), (599, 108.0), (629, 105.0), (959, 105.0))      # opens above, in by 09:59, in again by 10:29
HEAD = DOWN_IN[:-1] + ((699, 105.0),)                                    # the same path, open-ended after 11:39


def test_short_setup_two_brackets_accepted_then_entry_at_the_next_bar():
    s = Y.path_sess(knots=DOWN_IN)
    st = E.setup(s, VAL, VAH)
    assert st["open"] == S.ABOVE and st["trigger"] and st["side"] == S.SHORT and not st["rotated"]
    assert s.minute[st["j"]] == 630 and st["entry_minute"] == 630          # entry = the bar AFTER the trigger bracket
    assert st["entry_px"] == 105.0
    assert st["target"] == VAL and st["stop"] == 112.0 + T                 # HOD before the entry + 1 tick


def test_open_exactly_at_the_edge_is_not_outside():
    s = Y.path_sess(knots=((570, 110.0), (599, 108.0), (629, 105.0), (959, 105.0)))
    assert E.setup(s, VAL, VAH) == {"open": S.INSIDE, "trigger": False}
    assert E.setup(Y.path_sess(knots=((570, 100.0), (959, 105.0))), VAL, VAH)["open"] == S.INSIDE


def test_consecutive_means_consecutive_an_outside_bracket_resets_the_run():
    knots = ((570, 112.0), (599, 108.0), (629, 112.5), (659, 105.0), (689, 105.0), (959, 105.0))
    s = Y.path_sess(knots=knots)
    st = E.setup(s, VAL, VAH)
    # bracket 0 inside (108), bracket 1 outside (112.5 at 10:29), bracket 2 inside, bracket 3 inside -> trigger at 11:30
    assert st["trigger"] and st["entry_minute"] == 690
    one = E.setup(s, VAL, VAH, E.Params(accept=1))
    assert one["entry_minute"] == 600                                       # a single accepted bracket: after 09:59


def test_second_bracket_must_end_by_1500():
    late = ((570, 112.0), (869, 112.0), (870, 108.0), (959, 108.0))          # inside from 14:30
    s = Y.path_sess(knots=late)
    # brackets 14:30-15:00 (k=10) inside, 15:00-15:30 (k=11) would complete a pair but ends 15:30 > 15:00
    assert E.setup(s, VAL, VAH)["trigger"] is False
    ok = ((570, 112.0), (839, 112.0), (840, 108.0), (959, 108.0))            # inside from 14:00: pair completes at 15:00
    st = E.setup(Y.path_sess(knots=ok), VAL, VAH)
    assert st["trigger"] and st["entry_minute"] == 900


def test_a_bracket_counts_only_once_its_last_bar_has_closed_g4():
    """Change the CLOSE of the last bar (10:29) of the trigger bracket -> the trigger moves/vanishes; change a bar in
    the next bracket -> nothing changes."""
    s = Y.path_sess(knots=DOWN_IN)
    base = E.setup(s, VAL, VAH)
    i = 629 - 570
    mut = Y.path_sess(knots=DOWN_IN, overrides={629: (105.0, 113.0, 105.0, 113.0)})       # last bar closes outside
    assert E.setup(mut, VAL, VAH)["entry_minute"] != base["entry_minute"]
    same = Y.path_sess(knots=DOWN_IN, overrides={630: (105.0, 113.0, 105.0, 113.0)})      # the entry bar itself
    st = E.setup(same, VAL, VAH)
    assert st["entry_minute"] == base["entry_minute"] and st["stop"] == base["stop"]      # the stop reads only bars before
    assert i == 59


def test_already_rotated_the_far_edge_traded_before_the_entry():
    knots = ((570, 112.0), (585, 99.0), (599, 108.0), (629, 105.0), (959, 105.0))       # dipped to 99 < VAL first
    st = E.setup(Y.path_sess(knots=knots), VAL, VAH)
    assert st["trigger"] and st["rotated"] and "stop" not in st
    touch = ((570, 112.0), (585, 100.0), (599, 108.0), (629, 105.0), (959, 105.0))      # exactly AT the edge: at or through
    assert E.setup(Y.path_sess(knots=touch), VAL, VAH)["rotated"] is True


def test_long_setup_mirrors_the_short():
    knots = ((570, 98.0), (599, 102.0), (629, 105.0), (959, 105.0))
    s = Y.path_sess(knots=knots)
    st = E.setup(s, VAL, VAH)
    assert st["open"] == S.BELOW and st["side"] == S.LONG and st["target"] == VAH
    assert st["stop"] == float(s.l[:st["j"]].min()) - T == 98.0 - T
    high = ((570, 98.0), (585, 111.0), (599, 102.0), (629, 105.0), (959, 105.0))
    assert E.setup(Y.path_sess(knots=high), VAL, VAH)["rotated"] is True


def test_bracket_length_and_acceptance_grid_parameters():
    s = Y.path_sess(knots=((570, 112.0), (614, 108.0), (900, 108.0), (959, 108.0)))
    assert E.setup(s, VAL, VAH, E.Params(length=15, accept=2))["entry_minute"] == 615   # 09:30 bracket closes at 110.7 (out); 09:45 and 10:00 in
    assert E.setup(s, VAL, VAH, E.Params(length=60, accept=2))["entry_minute"] == 690    # 60-min brackets ending 10:30 and 11:30 both close inside


# ------------------------------------------------------------------ exits
def _short(knots, overrides=None):
    s = Y.path_sess(knots=knots, overrides=overrides)
    st = E.setup(s, VAL, VAH)
    return s, st


def test_target_fills_only_when_price_trades_one_tick_through():
    s, st = _short(HEAD + ((700, 100.25), (701, 99.75), (959, 99.75)))
    k, px, why = E.walk_exit(s, st["j"], st["side"], st["target"], st["stop"])
    assert (why, px, s.minute[k]) == (S.TARGET, VAL, 701)
    s2, st2 = _short(HEAD + ((700, 100.25), (701, 100.0), (959, 100.0)))         # touches VAL, never through
    assert E.walk_exit(s2, st2["j"], st2["side"], st2["target"], st2["stop"])[2] == S.TIME


def test_stop_fills_at_the_stop_gap_at_the_open_and_wins_a_tie():
    s, st = _short(HEAD + ((700, 112.5), (959, 112.5)))
    k, px, why = E.walk_exit(s, st["j"], st["side"], st["target"], st["stop"])
    assert (why, px) == (S.STOP, 112.25)
    over = {720: (105.0, 105.0, 105.0, 105.0), 721: (115.0, 116.0, 115.0, 115.5)}     # opens THROUGH the stop
    s3, st3 = _short(DOWN_IN, over)
    k, px, why = E.walk_exit(s3, st3["j"], st3["side"], st3["target"], st3["stop"])
    assert (why, px, s3.minute[k]) == (S.STOP, 115.0, 721)
    both = {720: (105.0, 113.0, 99.0, 105.0)}                                          # reaches the stop AND the target
    s4, st4 = _short(DOWN_IN, both)
    assert E.walk_exit(s4, st4["j"], st4["side"], st4["target"], st4["stop"])[2] == S.STOP


def test_time_exit_is_the_close_of_the_last_bar_and_early_close_is_honoured():
    s, st = _short(DOWN_IN)
    k, px, why = E.walk_exit(s, st["j"], st["side"], st["target"], st["stop"])
    assert (why, k, px) == (S.TIME, s.n - 1, 105.0) and s.minute[k] == 959
    e = Y.path_sess(knots=DOWN_IN, close_min=780)
    st = E.setup(e, VAL, VAH)
    assert E.walk_exit(e, st["j"], st["side"], st["target"], st["stop"])[0] == e.n - 1 and e.minute[-1] == 779


def test_the_entry_bar_can_itself_hit_the_target_or_stop():
    over = {630: (105.0, 105.0, 99.0, 99.5)}                                           # entry bar trades through VAL
    s, st = _short(DOWN_IN, over)
    k, px, why = E.walk_exit(s, st["j"], st["side"], st["target"], st["stop"])
    assert (why, px, s.minute[k]) == (S.TARGET, VAL, 630)


def test_walk_exit_matches_a_slow_bar_by_bar_reference():
    rng = np.random.default_rng(3)
    for n in range(60):
        base = 105 + rng.normal(0, 3)
        s = Y.path_sess(knots=((570, base), (959, base + rng.normal(0, 8))),
                        overrides={int(m): (base, base + rng.uniform(0, 9), base - rng.uniform(0, 9), base + rng.normal(0, 3))
                                   for m in rng.integers(575, 950, 20)})
        side = int(rng.choice([-1, 1]))
        j = int(rng.integers(30, 200))
        tgt, stp = (100.0, 112.25) if side == -1 else (110.0, 97.75)
        got = E.walk_exit(s, j, side, tgt, stp)
        ref = None
        for i in range(j, s.n):
            hs = s.h[i] >= stp if side == -1 else s.l[i] <= stp
            ht = s.l[i] <= tgt - T if side == -1 else s.h[i] >= tgt + T
            if hs:
                gap = (s.o[i] >= stp) if side == -1 else (s.o[i] <= stp)
                ref = (i, float(s.o[i]) if gap else stp, S.STOP)
                break
            if ht:
                ref = (i, tgt, S.TARGET)
                break
        ref = ref or (s.n - 1, float(s.c[-1]), S.TIME)
        assert got == ref


# ------------------------------------------------------------------ evaluate: statuses, guards, count-only
def _store(sessions):
    st = E.Store({})
    for s in sessions:
        st._s[s.date] = s
    return st


def test_statuses_data_and_roll_skips():
    a, b, c = (Y.path_sess(date=d, knots=DOWN_IN) for d in ("2019-03-04", "2019-03-05", "2019-03-06"))
    days = ["2019-03-04", "2019-03-05", "2019-03-06"]
    r = E.evaluate(_store([a, b, c]), days)
    assert [x["status"] for x in r] == ["skip_data", "ok", "ok"]           # nothing before the first day
    r2 = E.evaluate(_store([a, c]), days)
    assert [x["status"] for x in r2] == ["skip_data", "skip_data", "skip_data"]   # b missing -> b, and the one after it, skipped
    c2 = Y.path_sess(date="2019-03-06", knots=DOWN_IN, inst=2)
    assert [x["status"] for x in E.evaluate(_store([a, b, c2]), days)] == ["skip_data", "ok", "skip_roll"]
    mixed = Y.path_sess(date="2019-03-05", knots=DOWN_IN)
    mixed.inst = frozenset({1, 2})
    assert E.evaluate(_store([a, mixed, c]), days)[1]["status"] == "skip_roll"


def test_g4_profile_comes_only_from_the_prior_session():
    prev = Y.path_sess(date="2019-03-04", knots=((570, 100.0), (700, 110.0), (959, 105.0)))
    today = Y.path_sess(date="2019-03-05", knots=DOWN_IN)
    base = E.evaluate(_store([prev, today]), ["2019-03-04", "2019-03-05"])[1]
    other = Y.path_sess(date="2019-03-05", knots=((570, 300.0), (959, 300.0)))     # wildly different today
    r = E.evaluate(_store([prev, other]), ["2019-03-04", "2019-03-05"])[1]
    assert r["va_width"] == base["va_width"]                                         # VAH - VAL unchanged
    moved = Y.path_sess(date="2019-03-04", knots=((570, 100.0), (700, 140.0), (959, 105.0)))
    assert E.evaluate(_store([moved, today]), ["2019-03-04", "2019-03-05"])[1]["va_width"] != base["va_width"]


def test_evaluate_without_exit_never_calls_walk_exit(monkeypatch):
    monkeypatch.setattr(E, "walk_exit", lambda *a, **k: (_ for _ in ()).throw(AssertionError("outcome read")))
    prev = Y.path_sess(date="2019-03-04", knots=((570, 100.0), (700, 110.0), (959, 105.0)))
    today = Y.path_sess(date="2019-03-05", knots=DOWN_IN)
    r = E.evaluate(_store([prev, today]), ["2019-03-04", "2019-03-05"], want_exit=False)
    assert r[1]["trigger"] in (True, False) and r[1]["trade"] is None


def test_counts_do_not_move_when_every_bar_after_the_entry_minute_is_poisoned():
    frames = Y.rth_frames(Y.xnys_days("2019-03-04", 90), seed=8)
    days = sorted(frames)
    base = E.evaluate(E.Store(frames), days)
    n_trig = sum(r["trigger"] for r in base)
    assert n_trig > 5 and any(r["status"] == "ok" and not r["trigger"] and r["open"] != S.INSIDE for r in base)
    for i in range(1, len(days)):
        d, pd_ = days[i], days[i - 1]
        s = E.from_frame(frames[d], d)
        r0 = base[i]
        if r0["status"] != "ok":
            continue
        cut = s.minute[np.searchsorted(s.minute, 0)]
        if r0["trigger"]:
            st = E.setup(s, *E.Store(frames).va(pd_, S.VA_SHARE))
            keep_open_at = st["j"]
        else:
            keep_open_at = int(np.searchsorted(s.minute, S.DEADLINE_MIN))            # nothing at/after 15:00 may matter
        f = frames[d].copy()
        rows = np.arange(len(f)) > keep_open_at if r0["trigger"] else np.arange(len(f)) >= keep_open_at
        f.loc[f.index[rows], ["open", "high", "low", "close", "volume"]] = np.nan
        if r0["trigger"]:
            f.iloc[keep_open_at, [f.columns.get_loc(c) for c in ("high", "low", "close")]] = np.nan   # only the entry OPEN
        pois = E.Store({pd_: frames[pd_], d: f})
        pois._s[d] = E.from_frame(f, d)
        r1 = E.evaluate(pois, [pd_, d])[1]
        assert {k: r1[k] for k in ("status", "open", "trigger", "rotated", "side", "va_width")} == \
               {k: r0[k] for k in ("status", "open", "trigger", "rotated", "side", "va_width")}


def test_a_share_that_is_met_exactly_stops_even_when_the_float_sum_falls_a_hair_short():
    """0.9 + 0.5 + 0.2 = 80% of 2.0 exactly on paper; in floating point the running sum is not >= 1.6, and without the
    1e-9 tolerance the area would add one more tick."""
    p = _ladder([0.5, 0.9, 0.2, 0.4])
    assert value_area(p, 0.8) == (100.0, 100.5)
