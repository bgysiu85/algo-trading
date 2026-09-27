"""bars.py: weekend folding, the held-contract bar frame, the holdout cut."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import common.tl_v0_holdout as H
from strategy.tl_v0 import bars as B
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows


def _rows(dates, contract="A", **kw):
    n = len(dates)
    base = {"open": np.arange(n) + 10.0, "high": np.arange(n) + 11.0,
            "low": np.arange(n) + 9.0, "close": np.arange(n) + 10.5, "volume": np.ones(n)}
    base.update(kw)
    return pd.DataFrame({"date": pd.to_datetime(dates), "contract": contract, **base})


def test_a_sunday_stub_is_folded_into_monday():
    r = _rows(["2020-01-03", "2020-01-05", "2020-01-06"],
              open=[10.0, 20.0, 30.0], high=[11.0, 50.0, 31.0], low=[9.0, 5.0, 29.0],
              close=[10.5, 20.5, 30.5])
    f, note = B.fold_weekend(r)
    assert list(f["date"].dt.day) == [3, 6]
    mon = f.iloc[1]
    assert mon["open"] == 20.0            # Sunday's open is the true reopen
    assert mon["high"] == 50.0 and mon["low"] == 5.0
    assert mon["close"] == 30.5 and mon["volume"] == 2.0
    assert note["sunday_rows_folded"] == 1 and note["sunday_rows_dropped"] == 0


def test_a_sunday_with_no_next_row_of_the_same_contract_is_dropped():
    r = pd.concat([_rows(["2020-01-03", "2020-01-05"], "A"), _rows(["2020-01-06"], "B")])
    f, note = B.fold_weekend(r)
    assert note["sunday_rows_dropped"] == 1 and note["sunday_rows_folded"] == 0
    assert (f["date"].dt.dayofweek < 5).all()
    b = f[f["contract"] == "B"].iloc[0]
    assert b["open"] == 10.0              # B's Monday untouched by A's Sunday


def test_saturday_rows_are_dropped_and_counted():
    f, note = B.fold_weekend(_rows(["2020-01-03", "2020-01-04", "2020-01-06"]))
    assert note["saturday_rows_dropped"] == 1 and len(f) == 2


def test_the_adjusted_series_is_continuous_through_every_roll():
    rows, con, _ = contracts_and_rows()
    mb = B.build_bars(rows, con, ROOT, "XX")
    f = mb.frame
    assert mb.notes["rolls"] >= 3
    for R in np.nonzero(f["roll_after"].to_numpy())[0]:
        # adjusted close on R == the NEW contract's raw close on R, shifted
        # by the offset still to come; the next bar is the new contract
        assert f.loc[R, "close"] == pytest.approx(f.loc[R, "new_close_raw"] + f.loc[R + 1, "off"])
        assert f.loc[R + 1, "contract"] == f.loc[R, "next_contract"] != f.loc[R, "contract"]
    last = f["contract"].iloc[-1]
    seg = f[f["contract"] == last]
    assert (seg["off"] == 0).all() and np.allclose(seg["close"], seg["rc"])


def test_within_a_contract_adjusted_and_raw_differences_agree():
    rows, con, _ = contracts_and_rows()
    f = B.build_bars(rows, con, ROOT, "XX").frame
    same = f["contract"] == f["contract"].shift(1)
    assert np.allclose(f["close"].diff()[same], f["rc"].diff()[same])


def test_the_bar_traded_on_a_roll_session_is_the_old_contract():
    rows, con, _ = contracts_and_rows()
    f = B.build_bars(rows, con, ROOT, "XX").frame
    R = int(np.nonzero(f["roll_after"].to_numpy())[0][0])
    old = f.loc[R, "contract"]
    raw = rows[(rows["contract"] == old) & (rows["date"] == f.loc[R, "date"])].iloc[0]
    assert f.loc[R, "rc"] == pytest.approx(raw["close"])
    assert f.loc[R, "ro"] == pytest.approx(raw["open"])


def test_the_training_calendar_goes_through_split_dates(monkeypatch):
    """Gate G4: the runner takes its dates through the one implementation.
    Mutation: a build_bars that skipped split_dates would see 2022 rows."""
    calls = []
    real = H.split_dates

    def spy(dates, **kw):
        calls.append(kw)
        return real(dates, **kw)

    monkeypatch.setattr(H, "split_dates", spy)
    rows, con, _ = contracts_and_rows(n=3000, start="2012-01-02")
    assert rows["date"].max() >= pd.Timestamp("2022-01-01")
    mb = B.build_bars(rows, con, ROOT, "XX")
    assert calls and all(not kw.get("spend") for kw in calls)
    assert mb.frame["date"].max() < pd.Timestamp("2022-01-01")


def test_nothing_before_the_registered_training_start():
    rows, con, _ = contracts_and_rows(n=400, start="2010-01-04")
    f = B.build_bars(rows, con, ROOT, "XX").frame
    assert f["date"].min() >= pd.Timestamp("2010-06-01")


def test_a_held_contract_without_a_bar_is_carried_and_flagged():
    rows, con, _ = contracts_and_rows()
    f0 = B.build_bars(rows, con, ROOT, "XX").frame
    j = next(k for k in range(100, len(f0)) if f0.loc[k, "contract"] == f0.loc[k - 1, "contract"])
    d, c = f0.loc[j, "date"], f0.loc[j, "contract"]
    rows2 = rows[~((rows["date"] == d) & (rows["contract"] == c))]
    f = B.build_bars(rows2, con, ROOT, "XX").frame
    assert f.loc[j, "stale"]
    assert f.loc[j, "rc"] == f.loc[j, "ro"] == f.loc[j - 1, "rc"]
