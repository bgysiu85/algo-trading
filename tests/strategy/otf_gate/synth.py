"""Synthetic inputs for the OTF-G tests: 1-minute CME-style bars, RTH sessions, host books, daily frames."""
import numpy as np
import pandas as pd

ET = "America/New_York"


def cme_minutes(start_monday: str, weeks: int, *, seed=0, base=4000.0, vol=0.25, ids=None, roll_at=None,
                roll_gap=5.0, skip_dates=()):
    """1-min bars from Sunday 18:00 ET to Friday 16:59 ET for `weeks` weeks (17:00-17:59 maintenance hour absent).
    ids: instrument id for the first segment; roll_at: (label date, 'HH:MM' ET) at which id switches, raw price
    of the new contract is `roll_gap` higher than the old one at the switch."""
    rng = np.random.default_rng(seed)
    idx = []
    for w in range(weeks):
        mon = pd.Timestamp(start_monday) + pd.Timedelta(weeks=w)
        for dd in range(5):
            label = mon + pd.Timedelta(days=dd)
            if label.strftime("%Y-%m-%d") in skip_dates:
                continue
            start = (label - pd.Timedelta(days=1)).replace(hour=18)      # 18:00 ET the evening before
            if dd == 0:
                start = (label - pd.Timedelta(days=1)).replace(hour=18)    # Sunday 18:00
            end = label.replace(hour=17)                                    # 17:00 ET exclusive
            idx.append(pd.date_range(start, end, freq="min", inclusive="left"))
    naive = idx[0].append(idx[1:]) if len(idx) > 1 else idx[0]
    loc = naive.tz_localize(ET, ambiguous="NaT", nonexistent="NaT")
    keep = ~pd.isna(loc)
    loc = loc[keep]
    utc = loc.tz_convert("UTC")
    n = len(utc)
    step = rng.normal(0, vol, n)
    close = base + np.cumsum(step)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 0.2, n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.2, n)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": rng.integers(1, 50, n)}, index=utc)
    df["held_id"] = ids or 1
    if roll_at:
        d, hhmm = roll_at
        cut = pd.Timestamp(f"{d} {hhmm}", tz=ET).tz_convert("UTC")
        m = df.index >= cut
        df.loc[m, ["open", "high", "low", "close"]] += roll_gap
        df.loc[m, "held_id"] = 2
    return df


def rth_session(date_str: str, *, seed=0, base=4000.0, vol=0.6, drift=0.0):
    """One RTH session (09:30-15:59 ET, 1-min) with a random walk."""
    rng = np.random.default_rng(seed)
    naive = pd.date_range(f"{date_str} 09:30", f"{date_str} 15:59", freq="min")
    utc = naive.tz_localize(ET).tz_convert("UTC")
    close = base + np.cumsum(rng.normal(drift, vol, len(utc)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 0.4, len(utc))
    low = np.minimum(open_, close) - rng.uniform(0, 0.4, len(utc))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": rng.integers(1, 50, len(utc)), "held_id": 1}, index=utc)


def daily_frame(start="2015-01-05", weeks=140, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=5 * weeks)
    c = 1000 + np.cumsum(rng.normal(0.2, 6, len(dates)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0.5, 4, len(dates))
    l = np.minimum(o, c) - rng.uniform(0.5, 4, len(dates))
    return pd.DataFrame({"date": dates, "open": o, "high": h, "low": l, "close": c})


def books_csv(path, daily: pd.DataFrame, n=40, seed=5, market="ES", extra_markets=()):
    """A host-books CSV with the real column names; one C1 frac row set per market."""
    rng = np.random.default_rng(seed)
    rows = []
    for mk in (market, *extra_markets):
        js = np.sort(rng.choice(np.arange(60, len(daily) - 5), size=n, replace=False))
        for j in js:
            rows.append(dict(market=mk, spec="C1", R=0, share="single", sizing="frac", equity=22129.0,
                             direction=int(rng.choice([-1, 1])), entry_date=daily["date"].iloc[j].strftime("%Y-%m-%d"),
                             exit_date=daily["date"].iloc[j + 3].strftime("%Y-%m-%d"), entry_j=int(j), exit_j=int(j + 3),
                             gross=float(rng.normal(0, 50)), qty=float(rng.uniform(0.1, 1)), sides=2,
                             net_low=float(rng.normal(0, 50)), net_mid=float(rng.normal(0, 50)),
                             net_high=float(rng.normal(0, 50))))
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8")
    return df
