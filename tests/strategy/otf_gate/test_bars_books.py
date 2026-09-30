"""OTF-G: H-B daily rebuild (G4 d, G6), roll back-adjustment, B1 entry mirror, host books (G2 loader, G5)."""
import numpy as np
import pandas as pd
import pytest

from strategy.otf_gate import bars_hb as BB
from strategy.otf_gate import books as BK
from strategy.otf_gate import otf
from strategy.otf_gate import spec as S
from strategy.w16 import signals as SIG
from tests.strategy.otf_gate import synth as Y

ET = "America/New_York"


def _idx(*stamps):
    return pd.DatetimeIndex([pd.Timestamp(s, tz=ET) for s in stamps]).tz_convert("UTC")


# ------------------------------------------------------------------ labels (G4 d)
def test_trading_date_label_18_to_17_et_and_maintenance_hour_dropped():
    idx = _idx("2020-01-05 17:59", "2020-01-05 18:00",      # Sunday: before the open (no bar in life) / the open
               "2020-01-06 16:59", "2020-01-06 17:00", "2020-01-06 17:59", "2020-01-06 18:00")
    lab, ins = BB.trading_labels(idx)
    got = [str(pd.Timestamp(x).date()) for x in lab]
    assert got[1] == "2020-01-06"                # Sunday 18:00 ET -> Monday's session
    assert got[2] == "2020-01-06"                # Monday 16:59 -> Monday
    assert got[5] == "2020-01-07"                # Monday 18:00 ET -> Tuesday's session
    assert ins.tolist() == [False, True, True, False, False, True]     # the 17:00-17:59 hour belongs to no session


def test_label_is_dst_aware():
    # 2020-03-08 (US DST starts, 02:00 ET): Sunday 18:00 EDT is 22:00 UTC, the normal winter one is 23:00 UTC
    idx = pd.DatetimeIndex(["2020-03-08 22:00", "2020-03-06 21:59", "2020-03-06 22:00"], tz="UTC")
    lab, ins = BB.trading_labels(idx)
    assert [str(pd.Timestamp(x).date()) for x in lab] == ["2020-03-09", "2020-03-06", "2020-03-06"]
    assert ins.tolist() == [True, True, False]     # 21:59 UTC = 16:59 EST (in); 22:00 UTC = 17:00 EST (maintenance)


def test_daily_ohlc_and_a_bar_after_17_et_belongs_to_the_next_session():
    df = Y.cme_minutes("2020-01-06", 2, seed=4)
    daily, sw = BB.rebuild_daily(df)
    assert len(daily) == 10 and len(sw) == 0
    d0 = df[(df.index >= pd.Timestamp("2020-01-05 18:00", tz=ET)) & (df.index < pd.Timestamp("2020-01-06 17:00", tz=ET))]
    r = daily.iloc[0]
    assert r["date"] == pd.Timestamp("2020-01-06")
    assert (r["open"], r["high"], r["low"], r["close"]) == (d0["open"].iloc[0], d0["high"].max(), d0["low"].min(), d0["close"].iloc[-1])
    assert r["n_bars"] == 1380


def test_g4d_state_for_session_s_ignores_everything_from_18_et_the_evening_before_onward():
    """The bar labelled s-1 ends 17:00 ET before s; the entry at s 10:01 can not see label s. A one-bar shift of
    the day boundary (18:00 bars counted in the old day) would make the mutation below change the result."""
    df = Y.cme_minutes("2020-01-06", 12, seed=9)
    daily, _ = BB.rebuild_daily(df)
    s = daily["date"].iloc[40]
    base = otf.Stack(daily).states_at([s]).iloc[0][["d", "w", "m"]].tolist()
    df2 = df.copy()
    cut = pd.Timestamp(s.strftime("%Y-%m-%d") + " 00:00", tz=ET) - pd.Timedelta(hours=6)   # 18:00 ET the evening before s
    mask = df2.index >= cut.tz_convert("UTC")
    df2.loc[mask, ["open", "high", "low", "close"]] *= 2.3
    d2, _ = BB.rebuild_daily(df2)
    assert otf.Stack(d2).states_at([s]).iloc[0][["d", "w", "m"]].tolist() == base
    # ... but altering the LAST minute of label s-1 (16:59 ET) is visible to the daily leg's data
    df3 = df.copy()
    last = pd.Timestamp(s.strftime("%Y-%m-%d") + " 16:59", tz=ET) - pd.Timedelta(days=1)
    while last.dayofweek >= 5:
        last -= pd.Timedelta(days=1)
    df3.loc[last.tz_convert("UTC"), "close"] += 500.0
    d3, _ = BB.rebuild_daily(df3)
    prev = daily["date"].iloc[39]
    assert d3.loc[d3["date"] == prev, "close"].iloc[0] != daily.loc[daily["date"] == prev, "close"].iloc[0]


# ------------------------------------------------------------------ rolls
def test_roll_back_adjustment_is_additive_and_continuous():
    df = Y.cme_minutes("2020-01-06", 3, seed=2, roll_at=("2020-01-15", "09:00"), roll_gap=7.0)
    sw = BB.find_switches(df)
    assert len(sw) == 1 and bool(sw["ok"].iloc[0]) and sw["minutes"].iloc[0] == 1.0
    adj = BB.back_adjust(df, sw)
    k = int(sw["k"].iloc[0])
    assert adj["open"].iloc[k] == pytest.approx(df["open"].iloc[k])                  # last segment unadjusted
    gap = float(sw["gap"].iloc[0])
    assert adj["close"].iloc[k - 1] + 0.0 == pytest.approx(df["close"].iloc[k - 1] + gap)
    assert adj["open"].iloc[k] - adj["close"].iloc[k - 1] == pytest.approx(0.0, abs=1e-9)   # continuity
    # a difference inside one contract is the same on both series
    assert (adj["high"] - adj["low"]).iloc[:k].tolist() == pytest.approx((df["high"] - df["low"]).iloc[:k].tolist())


def test_two_rolls_accumulate():
    df = Y.cme_minutes("2020-01-06", 3, seed=2, roll_at=("2020-01-10", "09:00"), roll_gap=5.0)
    later = df.index >= pd.Timestamp("2020-01-20 09:00", tz=ET).tz_convert("UTC")
    df.loc[later, ["open", "high", "low", "close"]] += 3.0
    df.loc[later, "held_id"] = 3
    sw = BB.find_switches(df)
    assert len(sw) == 2
    adj = BB.back_adjust(df, sw)
    k0, k1 = (int(x) for x in sw["k"])
    assert adj["open"].iloc[k0] - adj["close"].iloc[k0 - 1] == pytest.approx(0, abs=1e-9)
    assert adj["open"].iloc[k1] - adj["close"].iloc[k1 - 1] == pytest.approx(0, abs=1e-9)


def test_a_switch_more_than_5_minutes_apart_stops_the_build_and_is_reported():
    df = Y.cme_minutes("2020-01-06", 2, seed=2, roll_at=("2020-01-09", "09:00"))
    k = int(np.flatnonzero(df["held_id"].to_numpy()[1:] != df["held_id"].to_numpy()[:-1])[0]) + 1
    df = pd.concat([df.iloc[:k - 10], df.iloc[k:]])           # 10 minutes missing right at the switch
    sw = BB.find_switches(df)
    assert not sw["ok"].iloc[0] and sw["minutes"].iloc[0] == 11.0
    with pytest.raises(BB.RollGapError, match="more than 5 minutes"):
        BB.rebuild_daily(df, strict=True)
    daily, sw2 = BB.rebuild_daily(df, strict=False)        # the pre-flight lists it instead of dying
    assert len(daily) and not sw2["ok"].all()


# ------------------------------------------------------------------ G3 cut first, G6 sessions
def test_the_holdout_cut_runs_before_any_bar_is_built(monkeypatch):
    seen = {}
    real = BB.HOLD.split_dates

    def spy(host, dates, **k):
        seen["host"], seen["n"] = host, len(list(dates))
        return real(host, dates, **k)
    monkeypatch.setattr(BB.HOLD, "split_dates", spy)
    df = Y.cme_minutes("2020-01-06", 1)
    BB.rebuild_daily(df)
    assert seen["host"] == "H-B" and seen["n"] == 5


def test_bars_after_the_training_end_never_reach_the_daily_frame():
    df = Y.cme_minutes("2023-12-25", 2, seed=6)          # week 1 ends 2023-12-29; week 2 = 2024-01-01.. (locked)
    daily, _ = BB.rebuild_daily(df)
    assert daily["date"].max() == pd.Timestamp("2023-12-29")
    assert (daily["date"] <= "2023-12-29").all()


def test_session_check_flags_more_than_one_percent_missing_in_a_year():
    df = Y.cme_minutes("2020-01-06", 4, seed=1)
    daily, _ = BB.rebuild_daily(df)
    ok = BB.session_check(daily)
    assert ok["years"][2020]["missing"] == 0 and ok["stop"] is False
    bad = BB.session_check(daily.drop(index=[3, 4]).reset_index(drop=True))
    assert bad["years"][2020]["missing"] == 2 and bad["stop"] is True       # 2 of ~18 days: > 1%


# ------------------------------------------------------------------ B1 entry mirror
def _cases():
    out = []
    for i, (drift, vol) in enumerate([(0.05, 0.9), (-0.05, 0.9), (0.0, 0.3), (0.0, 1.6), (0.2, 0.5), (-0.2, 0.5)] * 8):
        out.append(Y.rth_session(f"2019-03-{4 + (i % 5):02d}", seed=100 + i, vol=vol, drift=drift))
    return out


def _crafted():
    """No-trigger and void (gap through the range) sessions, built from random ones."""
    out = []
    for i in range(3):
        d = f"2019-04-{1 + i:02d}"
        df = Y.rth_session(d, seed=300 + i, vol=0.9)
        naive = SIG._naive_et(df)
        t = naive.time
        from datetime import time as dtime
        rb = df[(t >= dtime(9, 30)) & (t < dtime(10, 0))]
        mid = (rb["high"].max() + rb["low"].min()) / 2
        flat = df.copy()
        after = t >= dtime(10, 0)
        flat.loc[after, ["open", "high", "low", "close"]] = mid            # never leaves the range -> no trigger
        out.append((d, flat))
        tr = SIG.orb_session(df, d, market="ES")["trade"]
        if tr and not tr.get("voided"):
            v = df.copy()
            pos = v.index.get_loc(pd.Timestamp(tr["fill_time"]))
            lo, hi = rb["low"].min(), rb["high"].max()
            v.iloc[pos, v.columns.get_loc("open")] = (lo - 1.0) if tr["direction"] == "long" else (hi + 1.0)
            out.append((d, v))
    return out


def test_b1_entry_mirrors_the_frozen_engine_on_random_sessions():
    n_long = n_short = n_void = n_none = 0
    cases = [(f"2019-03-{4 + (i % 5):02d}", df) for i, df in enumerate(_cases())] + _crafted()
    for d, df in cases:
        mine = BK.b1_entry(df, d, market="ES")
        ref = SIG.orb_session(df, d, market="ES")
        assert mine["skipped"] == ref["skipped"]
        tr = ref["trade"]
        if tr is None:
            assert mine["entry"] is None and mine["voided"] is None
            n_none += 1
        elif tr.get("voided"):
            assert mine["entry"] is None and mine["voided"]
            n_void += 1
        else:
            assert mine["entry"]["direction"] == (1 if tr["direction"] == "long" else -1)
            assert str(mine["entry"]["fill_time"]) == tr["fill_time"]
            n_long += tr["direction"] == "long"
            n_short += tr["direction"] == "short"
    assert n_long > 3 and n_short > 3 and n_none >= 1 and n_void >= 1      # the comparison was not vacuous


def test_b1_entry_reads_no_bar_after_the_fill_and_computes_no_exit():
    df = Y.rth_session("2019-03-05", seed=101, vol=0.9)
    base = BK.b1_entry(df, "2019-03-05", market="ES")
    assert base["entry"] is not None
    fill = base["entry"]["fill_time"]
    poisoned = df.copy()
    after = poisoned.index > fill
    poisoned.loc[after, ["open", "high", "low", "close"]] = np.nan          # nothing after the fill may matter
    again = BK.b1_entry(poisoned, "2019-03-05", market="ES")
    assert again["entry"] == base["entry"]
    assert set(base["entry"]) == set(BK.ENTRY_KEYS)                          # no stop / target / exit / net keys


def test_run_b1_entries_counts_add_up():
    frames = {f"2019-03-{d:02d}": Y.rth_session(f"2019-03-{d:02d}", seed=200 + d, vol=0.9) for d in (4, 5, 6, 7, 8, 11)}
    e, c = BK.run_b1_entries(frames, "ES", list(frames))
    assert c["sessions"] == 6 and c["entries"] == len(e)
    assert c["sessions"] == c["skipped"] + c["no_trigger"] + c["voided"] + c["entries"]
    assert list(e.columns) == list(BK.ENTRY_KEYS)


# ------------------------------------------------------------------ H-A books (G2 loader, G4, G5)
def test_preflight_loader_never_reads_a_pnl_column(tmp_path, monkeypatch):
    d = Y.daily_frame()
    p = tmp_path / "b.csv"
    Y.books_csv(p, d)
    seen = {}
    real = pd.read_csv

    def spy(*a, **k):
        seen["usecols"] = k.get("usecols")
        return real(*a, **k)
    monkeypatch.setattr(pd, "read_csv", spy)
    df = BK.read_books(p, with_pnl=False)
    assert not set(BK.PNL_COLS) & set(df.columns)
    assert seen["usecols"] is not None and not set(BK.PNL_COLS) & set(seen["usecols"])
    assert not {"gross", "net_mid", "exit_date", "exit_j", "exit_px", "reason"} & set(seen["usecols"])
    assert set(BK.PNL_COLS) <= set(BK.read_books(p, with_pnl=True).columns)


def test_convention_and_count_checks(tmp_path):
    d = Y.daily_frame()
    p = tmp_path / "b.csv"
    Y.books_csv(p, d, n=30)
    host = BK.host_a(BK.read_books(p, with_pnl=False))
    assert BK.check_convention(host, {"ES": pd.DatetimeIndex(d["date"])}) == 30
    off = host.assign(entry_j=host["entry_j"] + 1)
    with pytest.raises(SystemExit, match="G4 FAILED"):
        BK.check_convention(off, {"ES": pd.DatetimeIndex(d["date"])})
    with pytest.raises(SystemExit, match="G5 FAILED"):
        BK.check_count(host)                       # 30, not 1,175
    assert BK.check_count(host, 30) == 30


def test_g5_reproduce_and_recost():
    h = pd.DataFrame({"market": ["ES", "ES"], "gross": [100.0, -50.0], "qty": [0.5, 0.25], "sides": [2, 4]})
    # recost: net = gross - (fee + k*tick) * qty * sides
    got = BK.recost(h, {"ES": 2.0}, {"ES": 12.5}, 1)
    assert got.tolist() == [100.0 - 14.5 * 0.5 * 2, -50.0 - 14.5 * 0.25 * 4]
    with pytest.raises(SystemExit, match="G5 OPEN"):
        BK.recost(h, {}, {"ES": 12.5}, 0)
    rows = pd.DataFrame({"net_mid": [-500.0, -347.0] + [0.0] * 1173})
    assert BK.check_reproduce(rows) == (1175, -847.0)
    with pytest.raises(SystemExit, match="G5 FAILED"):
        BK.check_reproduce(rows.assign(net_mid=1.0))
