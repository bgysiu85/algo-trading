"""The G6 diagnostic reports what is behind a data stop; it changes no rule and reads no P&L."""
import numpy as np
import pandas as pd

from strategy.otf_gate import diag_g6 as DG
from tests.strategy.otf_gate import synth as Y


def test_it_names_the_missing_day_and_the_wide_switch():
    df = Y.cme_minutes("2020-01-06", 4, seed=2, roll_at=("2020-01-09", "09:00"), skip_dates=("2020-01-15",))
    k = int(np.flatnonzero(df["held_id"].to_numpy()[1:] != df["held_id"].to_numpy()[:-1])[0]) + 1
    df = pd.concat([df.iloc[:k - 10], df.iloc[k:]])
    text = DG.report({"ES": df})
    assert "2020-01-15" in text and "bars carrying that CME label     0" in text
    assert "roll switches more than 5 minutes apart: 1" in text and "11 min apart" in text


def test_a_clean_series_reports_nothing_missing():
    df = Y.cme_minutes("2020-01-06", 2, seed=4)
    text = DG.report({"NQ": df})
    assert "missing from the rebuilt CME sessions: 0" in text and "more than 5 minutes apart: 0" in text
