"""Tests for strategy/macro_events/impact_map.py (synthetic bars only)."""
import numpy as np
import pandas as pd
import pytest

from strategy.macro_events import impact_map as M


def _bars(n=1500, seed=1, start="2012-01-02", boost_dates=(), boost=3.0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    rr = rng.lognormal(0, 0.25, n)
    for d in boost_dates:
        rr[dates.get_loc(pd.Timestamp(d))] *= boost
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame({"date": dates, "rh": close + rr / 2, "rl": close - rr / 2, "close": close})


def _ev(**kw):
    out = {e: set() for e in M.EVENTS}
    for k, v in kw.items():
        out[k] = {pd.Timestamp(x) for x in v}
    return out


def test_planted_event_effect_is_detected():
    dates = pd.bdate_range("2012-01-02", periods=1500)
    days = list(dates[100:1400:26])                       # ~50 event days
    r = M.prepare(_bars(boost_dates=days))
    t = M.build_table({"X": r}, _ev(CPI=days))
    row = t[(t.market == "X") & (t.event == "CPI")].iloc[0]
    assert row.range_ratio_excess > 1.0
    assert row.range_ratio_p < 0.001
    assert row.range_exceed_q90 > 0.8


def test_no_effect_is_not_flagged():
    dates = pd.bdate_range("2012-01-02", periods=1500)
    days = list(dates[100:1400:26])
    r = M.prepare(_bars())
    t = M.build_table({"X": r}, _ev(CPI=days))
    assert not t["supported"].any()


def test_baseline_never_uses_the_event_day_itself():
    b = _bars(n=100)
    r1 = M.prepare(b)
    b2 = b.copy()
    d = b2["date"].iloc[60]
    b2.loc[b2["date"] == d, "rh"] += 50.0                 # blow up ONE day's high
    r2 = M.prepare(b2)
    # that day's ratio changes, but the ratio of the day BEFORE it must not
    prev = b["date"].iloc[59]
    assert r1.loc[r1.date == prev, "range_ratio"].iloc[0] == pytest.approx(
        r2.loc[r2.date == prev, "range_ratio"].iloc[0])
    # the day's OWN range must not enter its baseline: the ratio scales exactly with the range
    old = (b["rh"] - b["rl"]).iloc[60]
    new = (b2["rh"] - b2["rl"]).iloc[60]
    x1 = r1.loc[r1.date == d, "range_ratio"].iloc[0]
    x2 = r2.loc[r2.date == d, "range_ratio"].iloc[0]
    assert x2 / x1 == pytest.approx(new / old)


def test_overlap_days_are_not_clean():
    b = _bars()
    dates = pd.bdate_range("2012-01-02", periods=1500)
    both = list(dates[200:400:10])
    r = M.prepare(b)
    t = M.build_table({"CL": r}, _ev(CPI=both, EIA_WPSR=both))     # CL: EIA is relevant
    for e in ("CPI", "EIA_WPSR"):
        row = t[t.event == e].iloc[0]
        assert row.n_clean == 0 and row.n_all == len(both)


def test_unscheduled_rows_are_ignored():
    cal = pd.DataFrame({"date": pd.to_datetime(["2012-03-01", "2012-03-02"]),
                        "event": ["FOMC", "FOMC_UNSCHEDULED"], "kind": ["scheduled", "unscheduled"]})
    ev = M.event_dates(cal)
    assert ev["FOMC"] == {pd.Timestamp("2012-03-01")}


def test_holdout_row_is_refused():
    b = _bars(n=3000, start="2016-01-04")                 # runs past 2022-01-01
    with pytest.raises(M.ImpactRefused):
        M.prepare(b)


def test_holm_is_monotone_and_capped():
    p = [0.001, 0.02, 0.5, 0.04]
    a = M.holm(p)
    assert all(x >= y for x, y in zip(a, p))
    assert max(a) <= 1.0
    assert a[0] == pytest.approx(0.004)


def test_render_brackets_negatives_and_runs_end_to_end(tmp_path):
    r = M.prepare(_bars())
    t = M.build_table({"X": r}, _ev(CPI=list(pd.bdate_range("2012-06-01", periods=60)[::2])))
    txt = M.render(t, {"X": "n"}, "test")
    assert "SUPPORTED cells" in txt
    cal = tmp_path / "cal.csv"
    pd.DataFrame({"date": ["2013-01-09"], "event": ["CPI"], "kind": ["scheduled"]}).to_csv(cal, index=False)
    class MB:  # stand-in for MarketBars
        frame = _bars()
    out = M.run(tmp_path, cal, tmp_path, "t", loader=lambda n: (MB, None), markets=["X"])
    assert out.exists()


def _wed_bars(n=1500, seed=3, wed_boost=1.5):
    b = _bars(n=n, seed=seed)
    wed = b["date"].dt.dayofweek == 2
    mid = (b["rh"] + b["rl"]) / 2
    half = (b["rh"] - b["rl"]) / 2
    half = half.where(~wed, half * wed_boost)
    b["rh"], b["rl"] = mid + half, mid - half
    return b


def test_weekday_matching_removes_a_pure_wednesday_effect():
    b = _wed_bars()
    days = list(b.loc[b["date"].dt.dayofweek == 2, "date"].iloc[5:200:4])   # 'events' on Wednesdays only
    r = M.prepare(b)
    t = M.build_table({"X": r}, _ev(CPI=days))
    row = t[t.event == "CPI"].iloc[0]
    assert row.matched
    assert row.range_ratio_excess_unmatched > 0.25          # weekday-blind comparison is fooled
    assert abs(row.range_ratio_excess) < 0.12               # matched comparison is not
    assert row.range_p_holm > 0.05 and not row.supported


def test_eia_is_only_tested_for_energy_markets_and_never_hides_fomc_days():
    b = _bars()
    dates = pd.bdate_range("2012-01-02", periods=1500)
    weds = list(dates[dates.dayofweek == 2][10:300])
    fomc = weds[::5]
    r = M.prepare(b)
    t = M.build_table({"X": r, "CL": r}, _ev(FOMC=fomc, EIA_WPSR=weds))
    assert not ((t.market == "X") & (t.event == "EIA_WPSR")).any()
    x = t[(t.market == "X") & (t.event == "FOMC")].iloc[0]
    cl = t[(t.market == "CL") & (t.event == "FOMC")].iloc[0]
    assert x.n_clean == x.n_all                               # EIA overlap ignored for non-energy
    assert cl.n_clean == 0                                    # but counted for CL


def test_unmatchable_weekday_falls_back_and_can_never_be_supported():
    b = _bars(boost_dates=[])
    dates = pd.bdate_range("2012-01-02", periods=1500)
    weds = list(dates[dates.dayofweek == 2][10:400])          # every Wednesday is an event day
    days = weds[:60]
    boosted = _bars(boost_dates=days, boost=3.0)
    r = M.prepare(boosted)
    t = M.build_table({"CL": r}, _ev(EIA_WPSR=weds))
    row = t[t.event == "EIA_WPSR"].iloc[0]
    assert not row.matched
    assert not row.supported


def test_holm_counts_untested_slots_as_p_one():
    assert M.holm([0.01], m=48)[0] == pytest.approx(0.48)
    assert M.holm([0.01], m=1)[0] == pytest.approx(0.01)
