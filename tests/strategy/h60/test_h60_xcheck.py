"""Gate G2 -- the cross-source price check and split finder (REGISTERED_h60_v0.md §5.1)."""
from __future__ import annotations

import numpy as np
import pytest

from strategy.h60 import xcheck as XC
from tests.strategy.h60 import _synth as S


def test_classify_split_bad_day_and_reversal():
    r = np.r_[np.full(10, 1.0), np.full(10, 0.5)]           # a 2-for-1 at 10
    split, bad, rev = XC.classify(r)
    assert list(np.flatnonzero(split)) == [10] and not bad.any() and rev == 0

    r = np.full(20, 1.0)
    r[7] = 1.015                                              # 1.5% off: bad, not a split
    split, bad, _ = XC.classify(r)
    assert not split.any() and list(np.flatnonzero(bad)) == [7]

    r = np.full(20, 1.0)
    r[7] = 1.30                                               # one wrong day, 30% off
    split, bad, rev = XC.classify(r)
    assert not split.any() and list(np.flatnonzero(bad)) == [7] and rev == 1

    r = np.full(20, 1.0)
    r[7:9] = 0.6                                              # two days, then back
    split, bad, rev = XC.classify(r)
    assert not split.any() and list(np.flatnonzero(bad)) == [7, 8]


def test_the_literal_reading_would_have_passed_the_wrong_day(monkeypatch):
    """Why the reversal rule exists: with it off, the 30% day is a one-day
    'segment' and is not flagged."""
    monkeypatch.setattr(XC, "REVERSAL_SESSIONS", 0)
    r = np.full(20, 1.0)
    r[7] = 1.30
    split, bad, _ = XC.classify(r)
    assert split.sum() == 2 and not bad[7]


def make(n_days=40, ratio_by_sym=None):
    days = S.sessions(n_days)
    frames, eod = [], {}
    for sym, ratio in (ratio_by_sym or {}).items():
        closes = np.full(n_days * 7, 100.0)
        frames.append(S.bars_from_closes(sym, days, closes))
        eod[sym] = {d: 100.0 / ratio[i] for i, d in enumerate(days) if ratio[i] is not None}
    p = S.panel(frames)
    return p, (lambda code: eod.get(code, {}))


def test_run_finds_splits_bad_days_unverified_and_mapping_failures():
    n = 40
    good = [1.0] * n
    split = [1.0] * 20 + [0.5] * 20          # EODHD adjusts: ratio steps at 20
    noisy = [1.0] * n
    noisy[5] = 1.05
    wrong = [1.0 if i % 3 else 1.1 for i in range(n)]       # 1 in 3 days off: > 20%
    missing = [1.0] * n
    missing[3] = None
    p, loader = make(n, {"AAA": good, "SPL": split, "NOI": noisy, "BAD": wrong,
                         "MIS": missing})
    x = XC.run(p, loader=loader)
    assert x.split_days == {("SPL", 20)}
    assert ("NOI", 5) in x.bad_days
    assert ("MIS", 3) in x.unverified_days and ("MIS", 3) not in x.bad_days
    assert "BAD" in x.excluded_codes and ("BAD", 0) in x.excluded_code_days
    assert ("AAA", 0) not in x.excluded_days
    assert x.eligible_days == 5 * n
    assert x.stop                                       # BAD alone is > 2% of all days
    assert "STOP" in XC.report(x, p)


def test_the_two_percent_stop():
    n = 40
    syms = {f"S{i:02d}": [1.0] * n for i in range(60)}
    syms["S00"][4] = 1.05                  # 1 bad day in 2,400
    p, loader = make(n, syms)
    x = XC.run(p, loader=loader)
    assert len(x.bad_days) == 1 and not x.stop and "PASS" in XC.report(x, p)


def test_a_day_missing_its_last_bar_is_unverified():
    days = S.sessions(3)
    df = S.bars_from_closes("AAA", days, np.full(21, 100.0))
    df = df[~((df["session"] == days[1]) & (df["bar"] == 6))]
    other = S.bars_from_closes("BBB", days, np.full(21, 100.0))
    p = S.panel([df, other])
    x = XC.run(p, loader=lambda code: {d: 100.0 for d in days})
    assert x.unverified_days == {("AAA", 1)}


def test_load_eod_reads_the_swing_file_format(tmp_path):
    (tmp_path / "BRK-B.csv").write_text(
        "date,open,high,low,close,adjusted_close,volume\n"
        "2020-01-06,1,1,1,227.5,227.5,10\n2020-01-07,1,1,1,x,1,1\n", encoding="utf-8")
    import datetime as dt
    assert XC.load_eod("BRK.B", tmp_path) == {dt.date(2020, 1, 6): 227.5}
    assert XC.load_eod("NOPE", tmp_path) == {}
