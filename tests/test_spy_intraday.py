#!/usr/bin/env python3
"""The intraday-momentum data assertions, each shown FIRING on a planted defect.

`common/spy_intraday.py` checks five things before any P/L is allowed to
exist (docs/research/REGISTERED_spy_intraday_data.md, amendment G). A check
that has never been seen to fail is indistinguishable from its absence -- the
recurring shape in this project's §4 -- so every one of them is exercised
twice here: once against a clean synthetic cache, where it must PASS, and once
against a cache with its specific defect planted, where it must FAIL.

The defects are not invented. Each is a failure this project has already had:

    timestamps shifted four hours   the screened MCL book stored entry_time in
                                    UTC and was read as ET for weeks, moving
                                    every time-of-day conclusion while looking
                                    entirely coherent
    a 1-for-10 reverse split        VW9 traded the adjustment factor and took
                                    positions at $4,152/share
    a missing stretch of sessions   r1 reads the PRIOR session's close, so a
                                    hole produces a WRONG r1 rather than a NaN
                                    -- there is nothing to notice
    two rows, one timestamp,        the cache is assembled from deliberately
      different prices              overlapping chunks; an overlap that
                                    DISAGREES is two answers, not a duplicate
    DST mishandled                  a tz-naive pipeline passes every other
                                    check all year and fails this one twice

The sixth test is the one that motivated amendment C: the session AFTER a
half-day must keep its r1, because the 13:00 print IS the prior session's
close. Reading the 15:30 bar instead silently discarded about nine sessions a
year -- the day after Thanksgiving, after Christmas Eve, after July 3rd --
which are exactly the unusual sessions the spec warns against losing quietly.
That defect was in the first version of the module and this test is why it is
not in the current one.

No IB connection is used or needed. Every cache here is synthetic.
"""
from __future__ import annotations

import sys
import types
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# common.spy_intraday imports common.spy_intraday_data for the cache layout,
# which imports ib_async at module scope. ib_async is a RUNTIME dependency of
# the puller and irrelevant to the pure frame arithmetic under test, so it is
# stubbed rather than required -- these tests must run anywhere, including a
# machine with no broker library installed.
if "ib_async" not in sys.modules:                             # pragma: no cover
    try:
        import ib_async                                       # noqa: F401
    except ImportError:
        _stub = types.ModuleType("ib_async")

        def _attr(name):
            if name == "util":
                return types.SimpleNamespace(df=lambda x: None)
            return type("_Stub", (), {"__init__": lambda self, *a, **k: None})

        _stub.__getattr__ = _attr
        sys.modules["ib_async"] = _stub

from common import spy_intraday as SI                          # noqa: E402

GRID = list(SI.GRID_30)
HALF = GRID[:7]                      # contiguous, ends at the 12:30 bar
HOLED = [t for t in GRID if t not in ("11:30", "12:00")]       # internal hole
HALF_DAYS = {"2024-11-29", "2025-11-28"}
HOLE_DAY = "2025-05-15"


def _rows(sess: str, times, px0: float, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    out, px = [], px0
    for t in times:
        o = px
        px = px * (1.0 + rng.normal(0, 0.0015))
        out.append({"ts_et": pd.Timestamp(f"{sess} {t}", tz=SI.ET),
                    "open": o, "high": max(o, px), "low": min(o, px),
                    "close": px, "volume": 1e6})
    return out


def _weekdays(a: date, b: date) -> list[str]:
    out, d = [], a
    while d < b:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _frame() -> pd.DataFrame:
    rows = []
    for i, ds in enumerate(_weekdays(date(2024, 1, 2), date(2026, 1, 1))):
        times = HALF if ds in HALF_DAYS else (HOLED if ds == HOLE_DAY else GRID)
        rows += _rows(ds, times, 400.0 + i * 0.05, i)
    return pd.DataFrame(rows)


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    """A writable synthetic cache root, swapped in for the real one."""
    monkeypatch.setattr(SI, "CACHE_ROOT", tmp_path)

    def write(df: pd.DataFrame, bars: str = "30 mins", symbol: str = "SPY"):
        d = tmp_path / SI.slug(bars) / symbol
        d.mkdir(parents=True, exist_ok=True)
        df.to_csv(d / f"{symbol}_synth.csv", index=False, encoding="utf-8")
        loaded = SI.load_bars(bars, symbol)
        sess = SI.build_sessions(loaded)
        return sess, SI.check(sess, loaded)

    return write


# --------------------------------------------------------------------------
# the clean case -- every check must PASS, or the failures below prove nothing
# --------------------------------------------------------------------------

def test_clean_cache_passes_every_check(cache):
    s, res = cache(_frame())
    assert res["n_bad_first_bar"] == 0
    assert res["dst_bad"] == []
    assert res["dup_conflicts"] == 0
    assert res["n_gaps"] == 0
    assert res["n_prior_unusable"] == 1     # only the day after HOLE_DAY
    assert res["n_half_days"] == len(HALF_DAYS)
    assert res["n_incomplete"] == 1         # HOLE_DAY itself
    assert res["dst_checked"] == 4          # two years, two transitions each


# --------------------------------------------------------------------------
# one planted defect each
# --------------------------------------------------------------------------

def test_utc_timestamps_read_as_et_are_caught(cache):
    """The MCL defect: a whole cache shifted four hours still looks coherent."""
    bad = _frame()
    bad["ts_et"] = bad["ts_et"] + pd.Timedelta(hours=4)
    _, res = cache(bad)
    assert res["n_bad_first_bar"] > 0


def test_missing_sessions_are_caught_as_a_gap(cache):
    """A hole makes r1 WRONG, not NaN, because r1 reads the prior close."""
    f = _frame()
    ds = f["ts_et"].dt.strftime("%Y-%m-%d")
    _, res = cache(f[~ds.between("2025-06-09", "2025-06-20")])
    assert res["n_gaps"] >= 1
    assert any(days > SI.GAP_DAYS_FLAG for _, _, days in res["gaps"])


def test_overlapping_chunks_that_disagree_are_caught(cache):
    """Overlap is by design; overlap that disagrees on price is not."""
    f = _frame()
    _, clean = cache(f)
    assert clean["dup_conflicts"] == 0
    _, res = cache(pd.concat([f, f.iloc[[500]].assign(close=999.0)],
                             ignore_index=True))
    assert res["dup_conflicts"] >= 1


def test_a_reverse_split_left_in_is_caught(cache):
    """VW9's defect: the adjustment factor printing as a price."""
    f = _frame()
    mask = f["ts_et"].dt.strftime("%Y-%m-%d") >= "2025-03-03"
    for c in ("open", "high", "low", "close"):
        f.loc[mask, c] = f.loc[mask, c] * 10.0
    _, res = cache(f)
    assert max(res["max_overnight"].values()) > 5.0        # ~900%


def test_mishandled_dst_is_caught(cache):
    """Shifting only the summer sessions is what a tz-naive pipeline does."""
    f = _frame()
    ds = f["ts_et"].dt.strftime("%Y-%m-%d")
    mask = ds.between("2025-03-10", "2025-11-01")
    f.loc[mask, "ts_et"] = f.loc[mask, "ts_et"] + pd.Timedelta(hours=1)
    _, res = cache(f)
    assert res["dst_bad"], "a one-hour summer shift must fail the DST check"


# --------------------------------------------------------------------------
# amendment C -- the defect this test suite found
# --------------------------------------------------------------------------

def test_session_after_a_half_day_keeps_its_r1(cache):
    """The 13:00 print IS the prior close. Nine sessions a year ride on this."""
    s, _ = cache(_frame())
    for hd in sorted(HALF_DAYS):
        later = [x for x in s.index if x > hd]
        assert later, f"no session after {hd}"
        nxt = later[0]
        assert s.loc[nxt, "full"]
        assert not np.isnan(s.loc[nxt, "r1"]), (
            f"{nxt} lost its r1 after the {hd} half-day")
        assert s.loc[nxt, "prior_close"] == pytest.approx(
            s.loc[hd, "last_close"])


def test_session_after_an_incomplete_one_does_not_get_an_r1(cache):
    """The other half: a defective session's last close is not a close."""
    s, _ = cache(_frame())
    nxt = [x for x in s.index if x > HOLE_DAY][0]
    assert s.loc[nxt, "full"]
    assert np.isnan(s.loc[nxt, "r1"]), (
        "a session following an incomplete one must NOT get an r1")


def test_a_clean_early_close_is_not_counted_as_incomplete(cache):
    """Contiguity, not bar count, separates the two."""
    s, res = cache(_frame())
    for hd in HALF_DAYS:
        assert s.loc[hd, "half_day"] and s.loc[hd, "contiguous"]
        assert not s.loc[hd, "full"]
    assert not s.loc[HOLE_DAY, "half_day"]
    assert not s.loc[HOLE_DAY, "contiguous"]
    assert HOLE_DAY in res["incomplete"]


# --------------------------------------------------------------------------
# the pre-2009 16:15 close -- measured by the depth probe, not assumed
# --------------------------------------------------------------------------

EXT = GRID + ["16:00"]           # 14 bars; the last runs 16:00-16:15


def _ext_frame() -> pd.DataFrame:
    rows = []
    for i, ds in enumerate(_weekdays(date(2007, 1, 2), date(2007, 7, 1))):
        rows += _rows(ds, EXT, 140.0 + i * 0.02, i)
    return pd.DataFrame(rows)


def test_pre_2009_extended_close_sessions_are_still_full_days(cache):
    """14 bars is a full SPY session in 2007, not a malformed one.

    The depth probe returned 14.00 thirty-minute bars per session for 2005,
    2007 and 2008 against 13.00 from 2011 on. An equality test on the grid --
    which the first version of this module had -- drops every one of them
    without a NaN or a warning anywhere.
    """
    s, res = cache(_ext_frame())
    assert res["n_incomplete"] == 0, "a 16:15-close session is not incomplete"
    assert res["n_half_days"] == 0
    assert s["full"].all()
    assert s["extended_close"].all()
    assert res["n_bad_first_bar"] == 0


def test_prior_close_on_an_extended_session_is_1600_not_1615(cache):
    """The 15:30 bar still closes at 16:00. The 16:00 bar closes at 16:15.

    Reading the LAST bar's close here would feed a price fifteen minutes too
    late into the next session's r1, on every session before 2009.
    """
    s, _ = cache(_ext_frame())
    later = s.index[1:]
    for sess in later[:20]:
        prev = s.index[s.index.get_loc(sess) - 1]
        assert s.loc[sess, "prior_close"] == pytest.approx(s.loc[prev, "p_1600"])
        # and it is genuinely a DIFFERENT number from the last bar's close,
        # so the test could actually fail if the wrong one were used
        assert s.loc[prev, "p_1600"] != s.loc[prev, "last_close"]


def test_a_modern_session_has_no_extended_close(cache):
    s, _ = cache(_frame())
    assert not s["extended_close"].any()


# --------------------------------------------------------------------------
# the cross-cache control, both ways
# --------------------------------------------------------------------------

def _consistent_caches(tmp_path):
    """One 5-minute price path; the 30-minute bars AGGREGATED from it."""
    rng = np.random.default_rng(7)
    labels = [f"{9 + (30 + 5 * k) // 60:02d}:{(30 + 5 * k) % 60:02d}"
              for k in range(78)]
    rows, px = [], 400.0
    for ds in _weekdays(date(2025, 1, 2), date(2025, 7, 1)):
        for t in labels:
            o = px
            px = px * (1.0 + rng.normal(0, 0.0007))
            rows.append({"ts_et": pd.Timestamp(f"{ds} {t}", tz=SI.ET),
                         "open": o, "high": max(o, px), "low": min(o, px),
                         "close": px, "volume": 2e5})
    fine = pd.DataFrame(rows)
    d5 = tmp_path / SI.slug("5 mins") / "SPY"
    d5.mkdir(parents=True, exist_ok=True)
    fine.to_csv(d5 / "SPY_synth.csv", index=False, encoding="utf-8")

    agg = (fine.set_index("ts_et").resample("30min")
           .agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).dropna())
    agg = agg[agg.index.strftime("%H:%M").isin(GRID)]
    d30 = tmp_path / SI.slug("30 mins") / "SPY"
    d30.mkdir(parents=True, exist_ok=True)
    agg.reset_index().to_csv(d30 / "SPY_synth.csv", index=False,
                             encoding="utf-8")
    return fine


def test_cross_cache_check_passes_when_the_two_caches_agree(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(SI, "CACHE_ROOT", tmp_path)
    _consistent_caches(tmp_path)
    s = SI.build_sessions(SI.load_bars("30 mins", "SPY"))
    xc = SI.cross_cache(s, SI.load_bars("5 mins", "SPY"))
    assert xc["status"] == "run" and xc["n"] > 100
    assert xc["n_over_1c"] == 0
    assert xc["max_abs_diff"] == pytest.approx(0.0, abs=1e-9)


def test_cross_cache_check_fails_when_the_5m_cache_is_a_different_series(
        tmp_path, monkeypatch):
    monkeypatch.setattr(SI, "CACHE_ROOT", tmp_path)
    _consistent_caches(tmp_path)
    d5 = tmp_path / SI.slug("5 mins") / "SPY" / "SPY_synth.csv"
    f = pd.read_csv(d5, encoding="utf-8")
    f["close"] = f["close"] + 1.0            # a whole dollar out, silently
    f.to_csv(d5, index=False, encoding="utf-8")
    s = SI.build_sessions(SI.load_bars("30 mins", "SPY"))
    xc = SI.cross_cache(s, SI.load_bars("5 mins", "SPY"))
    assert xc["n_over_1c"] > 0


def test_cross_cache_check_reports_not_run_rather_than_passing(tmp_path,
                                                               monkeypatch):
    """An absent 5-minute cache must not read as agreement. §8.3."""
    monkeypatch.setattr(SI, "CACHE_ROOT", tmp_path)
    d30 = tmp_path / SI.slug("30 mins") / "SPY"
    d30.mkdir(parents=True, exist_ok=True)
    _frame().to_csv(d30 / "SPY_synth.csv", index=False, encoding="utf-8")
    s = SI.build_sessions(SI.load_bars("30 mins", "SPY"))
    xc = SI.cross_cache(s, pd.DataFrame())
    assert xc["status"] != "run" and "NOT RUN" in xc["status"]


# --------------------------------------------------------------------------
# sigma1
# --------------------------------------------------------------------------

def test_sigma1_is_rank_invariant_to_bar_size_scaling():
    """The gate uses a percentile RANK, so a monotone rescale must not move it.

    This is the property amendment E leans on when it accepts a 5-minute proxy
    for a 1-minute quantity, so it is asserted rather than assumed.
    """
    rng = np.random.default_rng(3)
    a = pd.Series(rng.lognormal(size=500))
    b = a * 2.5                                   # a pure scale change
    assert a.rank().equals(b.rank())
    assert ((a >= a.quantile(0.67)) == (b >= b.quantile(0.67))).all()


def test_sigma1_excludes_the_overnight_gap(tmp_path, monkeypatch):
    """close_0 is the 09:30 OPEN, so a huge gap must not enter sigma1."""
    monkeypatch.setattr(SI, "CACHE_ROOT", tmp_path)
    labels = [f"09:{m:02d}" for m in (30, 35, 40, 45, 50, 55)]
    rows = []
    for i, ds in enumerate(["2025-03-03", "2025-03-04"]):
        base = 400.0 if i == 0 else 480.0         # a 20% overnight gap
        for k, t in enumerate(labels):
            o = base + k * 0.01
            rows.append({"ts_et": pd.Timestamp(f"{ds} {t}", tz=SI.ET),
                         "open": o, "high": o, "low": o,
                         "close": o + 0.01, "volume": 1.0})
    d5 = tmp_path / SI.slug("5 mins") / "SPY"
    d5.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(d5 / "SPY_synth.csv", index=False,
                              encoding="utf-8")
    sig = SI.sigma1(SI.load_bars("5 mins", "SPY"))
    assert len(sig) == 2
    # Both sessions have the same tiny within-window drift. If the gap leaked
    # in, the second would be orders of magnitude larger.
    assert sig["2025-03-04"] < 5.0 * sig["2025-03-03"]
