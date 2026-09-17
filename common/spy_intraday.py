#!/usr/bin/env python3
"""Sessions, assertions and the holdout cut for the intraday-momentum study.

    .venv\\Scripts\\python.exe -m common.spy_intraday --assert
    .venv\\Scripts\\python.exe -m common.spy_intraday --assert --symbols SPY QQQ IWM
    .venv\\Scripts\\python.exe -m common.spy_intraday --make-holdout

Registration: claude/spy_intraday_spec_20260917.md, sections 4, 8.6, 9 and
12. Bars come from common/spy_intraday_data.py.

THIS MODULE COMPUTES NO P/L, AND THAT IS THE POINT
---------------------------------------------------
Spec section 12 step 1: pull the window, run the assertions, report session
counts and exclusions, and STOP before any P/L exists. Every strategy in this
project that produced a number before its data was checked produced a number
that later had to be withdrawn -- the UTC entry_time that moved every
time-of-day conclusion four hours, the 08:00 TRF prints that manufactured a
pattern, the adjustment factor VW9 traded as a price. The verdict lives in
common/spy_intraday_study.py and cannot be reached from here.

THE FOUR PRICES, FROM 30-MINUTE BAR CLOSES
-------------------------------------------
With useRTH=True the RTH grid is exactly thirteen bars labelled by interval
START -- 09:30, 10:00, ... 15:30 -- so:

    r1   = close(09:30 bar) / close(PRIOR session's 15:30 bar) - 1
    r12  = close(15:00 bar) / close(14:30 bar) - 1
    r13  = close(15:30 bar) / close(15:00 bar) - 1

r1 spans the overnight boundary deliberately (spec section 3). r13 is the
traded window. r12 exists only for the reported-not-scored double filter.

WHAT IS ASSERTED, AND WHY EACH ONE EXISTS
------------------------------------------
Every check below is here because its absence has already cost this project a
result, either in this study's spec or in an earlier one.

  1. Bar grid. Every included session has bars at 09:30, 14:30, 15:00 and
     15:30 and no session starts at anything but 09:30 ET. A session whose
     first bar is 08:30 or 10:30 is a timestamp that was converted wrongly,
     and it is the single cheapest detector of that whole class -- the MCL
     book stored entry_time in UTC and was read as ET for weeks while looking
     entirely coherent.

  2. DST. Both transitions of every year are represented and the session
     after each one still starts at 09:30 ET. A tz-naive pipeline passes
     check 1 all year and fails here twice a year.

  3. Half-days. The market closes at 13:00 ET about nine times a year and
     there is NO 15:30 bar. These are excluded and COUNTED. Spec section 4:
     a silent NaN would drop the most unusual sessions in the sample.

  4. Session gaps. r1 reads the PRIOR session's close, so a session missing
     from the cache does not produce a gap -- it produces a WRONG r1, computed
     across the hole, with no NaN to notice. Consecutive session spacing is
     reported and anything over four calendar days is listed by name.

  5. Adjustment. The largest overnight moves are listed. SPY, QQQ and IWM had
     no split in this window and the pull is consistently unadjusted, so
     nothing here should approach the ~900% a reverse split prints or the
     ~0.4% a mixed dividend series would inject four times a year. This is
     the check VW9 did not have.

  6. Cross-cache agreement. The 10:00 price read from the 30-minute cache
     must equal the 09:55 close read from the independently pulled 5-minute
     cache, to the cent. Two caches, two pulls, one number -- the cheapest
     available control on the whole data path, and section 4's standard:
     measure on a second source BEFORE stating a conclusion.

SIGMA1, AND WHY A 5-MINUTE PROXY IS SOUND FOR A PERCENTILE GATE
----------------------------------------------------------------
    sigma1 = sqrt( sum over bars in 09:30-10:00 of ln(close_i/close_i-1)^2 )

with close_0 the OPEN of the 09:30 bar, so the window's own opening move is
included and the overnight gap is not. Six terms at 5-minute, thirty at
1-minute.

A 5-minute realised vol is systematically SMALLER than a 1-minute one over
the same window, and noisier. Neither matters here, because H-S2 gates on a
trailing PERCENTILE RANK of sigma1, and a rank is invariant to any monotone
rescaling. What would matter is the two disagreeing about WHICH sessions are
the volatile ones. So the registered agreement check is a rank correlation
between the 5-minute and 1-minute sigma1 over whatever overlap IB gives, plus
the share of sessions on which the two put a session on the same side of the
67th percentile. That is the quantity the gate actually depends on.

THE HOLDOUT
-----------
holdout_spy.json, cut by --make-holdout BEFORE the first P/L run. The existing
holdout.json governs the small-cap universe and does not apply (spec section
9). The cut reuses holdout.split so there is still ONE implementation of the
split arithmetic -- the rule that exists because two studies were once written
without it and would have read the locked slice while printing an ordinary
looking number.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import holdout
from common.report_io import emit
from common.spy_intraday_data import CACHE_ROOT, slug

ET = ZoneInfo("America/New_York")

SPY_HOLDOUT_PATH = Path(__file__).resolve().parents[1] / "holdout_spy.json"
LOCK_FRACTION = 0.20            # spec section 9: the most recent 20% of sessions

# Bar labels, by interval START, on the RTH 30-minute grid.
B_OPEN = "09:30"                # its CLOSE is the 10:00 price
B_1430 = "14:30"
B_1500 = "15:00"                # its CLOSE is the 15:30 price
B_1530 = "15:30"                # its CLOSE is the 16:00 price
REQUIRED_30 = (B_OPEN, B_1430, B_1500, B_1530)

# The full RTH 30-minute grid, labelled by interval START. Order matters: it
# is what CONTIGUITY is judged against, which is what separates a legitimate
# early close from a hole in the cache.
GRID_30 = ("09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
           "13:00", "13:30", "14:00", "14:30", "15:00", "15:30")
FULL_DAY_BARS = len(GRID_30)
HALF_DAY_LAST = "12:30"         # its close is the 13:00 early close

# BEFORE 2009, SPY CLOSED AT 16:15, NOT 16:00.
#
# Measured, not assumed: the depth probe of 2026-09-17 returned exactly 14.00
# thirty-minute bars per session for 2005, 2007 and 2008 against 13.00 for
# 2011 onward, with the last bar labelled 16:00 instead of 15:30, and 81
# five-minute bars against 78 with the last labelled 16:10. 2009 came back at
# 13.19 -- the transition year, mixed.
#
# The extra bar is 16:00-16:15. It does NOT move any of the four prices the
# rule needs: the 15:30 bar still runs 15:30-16:00, so its close is still the
# 16:00 price. What it breaks is an equality test on the grid, and the first
# version of this module had one -- every pre-2009 session would have been
# marked "not a full day" and dropped in silence. That is the same shape as
# the half-day defect in amendment C, one era earlier, and it only matters
# because the probe showed IB serves 30-minute bars back to 2004 and made a
# replication leg over the paper's own sample affordable.
GRID_30_EXT = GRID_30 + ("16:00",)
SIGMA_WINDOW_END = "10:00"      # exclusive: 09:30..09:55 at 5-minute
GAP_DAYS_FLAG = 4               # a long weekend is 3; Thanksgiving week is 4

# UNSCHEDULED FULL-MARKET CLOSURES. Weekdays the NYSE was shut for something
# other than a holiday, so a gap spanning one is EXPLAINED and not a hole.
#
# The first version of the gap check counted calendar days and flagged three
# gaps on this cache. Two were these -- President Ford's national day of
# mourning and Hurricane Sandy -- and one was a genuine hole. A check that
# cannot tell a real absence from a day the market was closed produces three
# alarms where there is one defect, and the cost of that is that the real one
# stops being read.
UNSCHEDULED_CLOSURES = {
    "2004-06-11",               # national day of mourning, Reagan
    "2007-01-02",               # national day of mourning, Ford
    "2012-10-29", "2012-10-30",  # Hurricane Sandy
    "2018-12-05",               # national day of mourning, G.H.W. Bush
    "2025-01-09",               # national day of mourning, Carter
}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_bars(bars: str, symbol: str) -> pd.DataFrame:
    """Every cached chunk for one symbol, de-duplicated and sorted.

    Chunks OVERLAP by construction (spy_intraday_data.CHUNK_DAYS is shorter
    than the request duration), so duplicates are expected and dropping them
    is not papering over anything. Duplicates that DISAGREE are a different
    matter and are counted rather than silently resolved.
    """
    d = CACHE_ROOT / slug(bars) / symbol
    if not d.exists():
        return pd.DataFrame()
    frames = []
    for p in sorted(d.glob(f"{symbol}_*.csv")):
        f = pd.read_csv(p, encoding="utf-8")
        if f.empty:
            continue
        f["ts_et"] = pd.to_datetime(f["ts_et"], utc=True).dt.tz_convert(ET)
        frames.append(f.set_index("ts_et"))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames).sort_index()
    dup = df.index.duplicated(keep="first")
    df.attrs["dup_dropped"] = int(dup.sum())
    # A duplicate whose CLOSE disagrees is not an overlap, it is two different
    # answers to the same question, and it must be seen rather than resolved.
    conflict = (df.groupby(level=0)["close"].nunique() > 1).sum()
    df.attrs["dup_conflicts"] = int(conflict)
    return df[~dup]


def hhmm(idx) -> pd.Index:
    return idx.strftime("%H:%M")


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------

def build_sessions(df30: pd.DataFrame) -> pd.DataFrame:
    """One row per session date, with the four prices the rule needs."""
    if df30.empty:
        return pd.DataFrame()
    g = df30.copy()
    g["sess"] = g.index.strftime("%Y-%m-%d")
    g["hhmm"] = hhmm(g.index)
    rows = []
    for sess, part in g.groupby("sess", sort=True):
        by = dict(zip(part["hhmm"], part["close"]))
        labels = list(part["hhmm"])
        first, last = labels[0], labels[-1]
        # Contiguous from 09:30 with no internal hole. This is what tells a
        # 13:00 early close (a real session, fully recorded) apart from a
        # session with bars missing out of the middle (a defect). Both are
        # "not a full day" and they must NOT be treated alike, because the
        # first one's closing price is real and the second one's is not.
        contiguous = labels == list(GRID_30_EXT[:len(labels)])
        half = contiguous and last == HALF_DAY_LAST
        rows.append({
            "sess": sess,
            "n_bars": len(part),
            "first_bar": first,
            "last_bar": last,
            "open_0930": float(part["open"].iloc[0]),
            "p_1000": by.get(B_OPEN, np.nan),
            "p_1500": by.get(B_1430, np.nan),
            "p_1530": by.get(B_1500, np.nan),
            "p_1600": by.get(B_1530, np.nan),
            "last_close": float(part["close"].iloc[-1]),
            "half_day": half,
            "contiguous": contiguous,
            # The thirteen core bars, present and in order. A trailing
            # 16:00 bar from the pre-2009 16:15 close is ALLOWED and does not
            # make the session anything other than full.
            "full": (len(labels) >= FULL_DAY_BARS
                     and labels[:FULL_DAY_BARS] == list(GRID_30)),
            "extended_close": len(labels) > FULL_DAY_BARS,
        })
    s = pd.DataFrame(rows).set_index("sess")
    # PRIOR CLOSE IS THE PRIOR SESSION'S LAST CLOSE, NOT ITS 15:30 BAR.
    #
    # On a full day those are the same number. On a half-day the market closed
    # at 13:00 and the 13:00 print IS that session's closing price -- so the
    # session FOLLOWING a half-day has a perfectly good r1 and must not be
    # dropped. Reading p_1600 here instead silently NaN'd it, which threw away
    # the day after Thanksgiving, the day after Christmas Eve and the day
    # after July 3rd every year: about nine sessions a year, and precisely the
    # unusual ones spec section 4 warns against losing quietly. Caught by the
    # planted-defect test, not by reading the code.
    #
    # An INCOMPLETE session is different: its last close is whatever the cache
    # happens to end on, so the session after it has no trustworthy prior
    # close and is marked rather than computed.
    # THE SESSION'S CLOSING PRICE, WHICH IS NOT ALWAYS ITS LAST BAR'S CLOSE.
    #   full day        the 16:00 price = close of the 15:30 bar. On a
    #                   pre-2009 session the LAST bar closes at 16:15, and
    #                   using it here would put a 15-minute-later price into
    #                   the next session's r1 four thousand times.
    #   clean half-day  the 13:00 print, which is its last close (amendment C)
    #   incomplete      nothing trustworthy; the next session is marked
    s["session_close"] = np.where(
        s["full"], s["p_1600"],
        np.where(s["half_day"], s["last_close"], np.nan))
    s["prior_close"] = pd.Series(s["session_close"], index=s.index).shift(1)
    s["prior_sess"] = pd.Series(s.index, index=s.index).shift(1)
    s["prior_ok"] = (s["full"] | s["half_day"]).shift(1, fill_value=False)
    s["r1"] = np.where(s["prior_ok"], s["p_1000"] / s["prior_close"] - 1.0,
                       np.nan)
    s["r12"] = s["p_1530"] / s["p_1500"] - 1.0
    s["r13"] = s["p_1600"] / s["p_1530"] - 1.0
    return s


def sigma1(df_fine: pd.DataFrame) -> pd.Series:
    """Realised vol of 09:30-10:00 per session, from the fine-grained cache."""
    if df_fine.empty:
        return pd.Series(dtype=float)
    f = df_fine.copy()
    f["hhmm"] = hhmm(f.index)
    f = f[(f["hhmm"] >= B_OPEN) & (f["hhmm"] < SIGMA_WINDOW_END)]
    f["sess"] = f.index.strftime("%Y-%m-%d")
    out = {}
    for sess, part in f.groupby("sess", sort=True):
        if len(part) < 2:
            continue
        # close_0 is the window's OPEN, so the opening move inside the window
        # counts and the overnight gap does not.
        px = np.concatenate([[part["open"].iloc[0]], part["close"].to_numpy()])
        r = np.diff(np.log(px))
        out[sess] = float(np.sqrt(np.sum(r * r)))
    return pd.Series(out, name="sigma1")


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------

def market_closed_days(y0: int, y1: int) -> set[str]:
    """Weekdays the NYSE is closed: federal holidays as the exchange keeps
    them, plus Good Friday, plus the unscheduled closures above.

    The NYSE calendar is NOT the federal one: it trades on Columbus Day and
    Veterans Day and closes on Good Friday, which is not a federal holiday at
    all. Taking the federal list unchanged would explain away two absences a
    year that are real and flag one that is not.
    """
    from pandas.tseries.holiday import (GoodFriday, USFederalHolidayCalendar)
    cal = USFederalHolidayCalendar()
    hol = cal.holidays(f"{y0}-01-01", f"{y1}-12-31")
    keep = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in hol
            if pd.Timestamp(d).strftime("%B %d") not in ("October 14",)}
    names = cal.rules
    drop = {r.name for r in names if r.name in ("Columbus Day", "Veterans Day")}
    if drop:
        rebuilt = set()
        for r in names:
            if r.name in drop:
                continue
            for d in r.dates(f"{y0}-01-01", f"{y1}-12-31"):
                rebuilt.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
        keep = rebuilt
    for d in GoodFriday.dates(f"{y0}-01-01", f"{y1}-12-31"):
        keep.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
    return keep | UNSCHEDULED_CLOSURES


def dst_transitions(years) -> list[date]:
    """US DST boundaries: second Sunday in March, first Sunday in November."""
    out = []
    for y in years:
        d = date(y, 3, 1)
        sundays = [d + timedelta(days=i) for i in range(31)
                   if (d + timedelta(days=i)).month == 3
                   and (d + timedelta(days=i)).weekday() == 6]
        out.append(sundays[1])
        n = date(y, 11, 1)
        nov = [n + timedelta(days=i) for i in range(30)
               if (n + timedelta(days=i)).month == 11
               and (n + timedelta(days=i)).weekday() == 6]
        out.append(nov[0])
    return out


def check(s: pd.DataFrame, df30: pd.DataFrame) -> dict:
    res = {}
    res["n_sessions_cached"] = len(s)
    if s.empty:
        return res

    bad_start = s[s["first_bar"] != B_OPEN]
    res["bad_first_bar"] = list(bad_start.index[:20])
    res["n_bad_first_bar"] = len(bad_start)

    half = s[s["half_day"]]
    res["half_days"] = list(half.index)
    res["n_half_days"] = len(half)

    incomplete = s[(~s["full"]) & (~s["half_day"])]
    res["incomplete"] = list(incomplete.index[:20])
    res["n_incomplete"] = len(incomplete)

    # Sessions that ARE tradeable but whose prior close cannot be trusted,
    # because the session before them was incomplete. The FIRST cached session
    # is excluded: it has no prior session at all, which is a property of the
    # window's edge and not a defect, and counting it here would put a
    # permanent 1 next to a line that is supposed to read zero.
    res["n_prior_unusable"] = int(
        (s["full"] & ~s["prior_ok"]).iloc[1:].sum())

    res["bars_per_session"] = (s["n_bars"].value_counts()
                               .sort_index().to_dict())

    years = sorted({int(x[:4]) for x in s.index})
    res["years"] = years
    missing_dst = []
    for t in dst_transitions(years):
        after = [x for x in s.index if x >= t.isoformat()][:1]
        if not after:
            continue
        row = s.loc[after[0]]
        if row["first_bar"] != B_OPEN:
            missing_dst.append((t.isoformat(), after[0], row["first_bar"]))
    res["dst_bad"] = missing_dst
    res["dst_checked"] = len(dst_transitions(years))

    idx = pd.to_datetime(pd.Series(list(s.index)))
    gaps = idx.diff().dt.days
    closed = market_closed_days(int(s.index[0][:4]), int(s.index[-1][:4]))
    big, explained = [], []
    for i in range(1, len(s)):
        if gaps.iloc[i] <= GAP_DAYS_FLAG:
            continue
        a, b = s.index[i - 1], s.index[i]
        missing = [d.strftime("%Y-%m-%d")
                   for d in pd.bdate_range(a, b, inclusive="neither")]
        unexplained = [d for d in missing if d not in closed]
        row = (str(a), str(b), int(gaps.iloc[i]), unexplained)
        (big if unexplained else explained).append(row)
    res["gaps"] = big
    res["n_gaps"] = len(big)
    res["gaps_explained"] = explained
    res["gap_days_counts"] = (gaps.dropna().astype(int).value_counts()
                              .sort_index().to_dict())

    ov = (s["open_0930"] / s["prior_close"] - 1.0).dropna().abs()
    res["max_overnight"] = (ov.sort_values(ascending=False).head(8)
                            .round(5).to_dict())
    res["dup_dropped"] = int(df30.attrs.get("dup_dropped", 0))
    res["dup_conflicts"] = int(df30.attrs.get("dup_conflicts", 0))
    return res


def cross_cache(s: pd.DataFrame, df5: pd.DataFrame) -> dict:
    """The 10:00 price, read from two independently pulled caches.

    THE LAST BAR STRICTLY BEFORE 10:00, whatever the fine cache's bar size --
    09:55 at five minutes, 09:59 at one. The first version hard-coded "09:55",
    which silently compared the 30-minute 10:00 price against a price FIVE
    MINUTES EARLIER once the fine cache became 1-minute, and reported a
    maximum disagreement of $4.96 across 5,476 sessions. That is not a data
    defect, it is this function asking the wrong question, and it is exactly
    the shape it exists to catch -- which is the argument for having run it.
    """
    if df5.empty:
        return {"status": "fine cache absent -- check NOT RUN"}
    f = df5.copy()
    f["hhmm"] = hhmm(f.index)
    f = f[f["hhmm"] < SIGMA_WINDOW_END]
    if f.empty:
        return {"status": "no bars before 10:00 in the fine cache -- NOT RUN"}
    f["sess"] = f.index.strftime("%Y-%m-%d")
    fine = f.groupby("sess")["close"].last()
    both = s["p_1000"].dropna().index.intersection(fine.index)
    if len(both) == 0:
        return {"status": "no overlapping sessions -- check NOT RUN"}
    d = (s.loc[both, "p_1000"] - fine.loc[both]).abs()
    return {"status": "run", "n": len(both),
            "max_abs_diff": float(d.max()), "n_over_1c": int((d > 0.01).sum()),
            "worst": d.sort_values(ascending=False).head(5).round(4).to_dict()}


def abs_r13_by_year(s: pd.DataFrame) -> pd.DataFrame:
    """Spec section 12 step 2. The economics assume 0.20-0.30% average."""
    t = s.dropna(subset=["r13"]).copy()
    t["year"] = [x[:4] for x in t.index]
    g = t.groupby("year")["r13"]
    return pd.DataFrame({
        "n": g.size(),
        "mean_abs_pct": (g.apply(lambda x: x.abs().mean()) * 100).round(4),
        "median_abs_pct": (g.apply(lambda x: x.abs().median()) * 100).round(4),
        "sd_pct": (g.std() * 100).round(4),
    })


# --------------------------------------------------------------------------
# holdout
# --------------------------------------------------------------------------

def make_holdout(days: list[str]) -> dict:
    rec = holdout.split(days, LOCK_FRACTION)
    h = hashlib.sha256()
    for d in days:
        h.update(f"SPY|{d}\n".encode())
    rec.update({
        "cut_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lock_fraction": LOCK_FRACTION,
        "sources": ["bar_cache_spy/30min/SPY"],
        "universe_fingerprint": h.hexdigest(),
        "note": ("SPY intraday momentum (H-S1/H-S2) ONLY. holdout.json governs "
                 "the small-cap universe and does not apply to this study, and "
                 "this file does not apply to that one. Opened exactly ONCE, "
                 "and only after a cell has cleared all five gates on the "
                 "training window; the result of opening it is final."),
    })
    return rec


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def render(symbol: str, s: pd.DataFrame, res: dict, xc: dict,
           sig: pd.Series, r13y: pd.DataFrame, now: datetime) -> list[str]:
    L = [f"SPY INTRADAY -- DATA AND ASSERTIONS, {symbol}", "",
         f"  run at    {now:%Y-%m-%d %H:%M:%S} ET",
         f"  cache     {CACHE_ROOT / '30min' / symbol}",
         f"  tape      IB reqHistoricalData, TRADES, useRTH=True,",
         f"            split-adjusted and consistently NOT dividend-adjusted",
         "",
         "  NO P/L IS COMPUTED HERE. Spec section 12 step 1 stops at this",
         "  report on purpose.", ""]
    if s.empty:
        return L + ["  NO BARS CACHED. Run common.spy_intraday_data --pull first."]

    usable = s[s["full"]].dropna(subset=["r1", "r13"])
    L += ["SESSION COUNTS", "",
          f"  cached sessions          {res['n_sessions_cached']:>6}",
          f"  first / last             {s.index[0]} -> {s.index[-1]}",
          f"  half-days excluded       {res['n_half_days']:>6}   "
          f"(no 15:30 bar; market closed 13:00 ET)",
          f"  incomplete excluded      {res['n_incomplete']:>6}   "
          f"(not a full grid and not a clean early close)",
          f"  full days, prior close    {res['n_prior_unusable']:>6}   "
          f"unusable because the session before was incomplete",
          f"  USABLE for the rule      {len(usable):>6}   "
          f"(full grid, and a prior close to compute r1 from)", ""]

    L += ["ASSERTIONS", ""]
    ok = lambda b: "PASS" if b else "**FAIL**"                # noqa: E731
    L += [f"  {ok(res['n_bad_first_bar'] == 0)}  every session starts at "
          f"09:30 ET            ({res['n_bad_first_bar']} bad)",
          f"  {ok(not res['dst_bad'])}  DST: session after each transition "
          f"starts 09:30   ({res['dst_checked']} transitions checked)",
          f"  {ok(res['dup_conflicts'] == 0)}  overlapping chunks agree on "
          f"price               ({res['dup_dropped']} dup rows dropped, "
          f"{res['dup_conflicts']} conflicting)",
          f"  {ok(res['n_gaps'] == 0)}  no session gap over {GAP_DAYS_FLAG} "
          f"calendar days       ({res['n_gaps']} flagged)"]
    if xc.get("status") == "run":
        L.append(f"  {ok(xc['n_over_1c'] == 0)}  10:00 price agrees across the "
                 f"30m and 5m caches ({xc['n']} sessions, max diff "
                 f"{xc['max_abs_diff']:.4f})")
    else:
        L.append(f"  ....  cross-cache 10:00 check: {xc['status']}")
    L.append("")

    if res["n_bad_first_bar"]:
        L += ["  SESSIONS NOT STARTING AT 09:30 -- a timestamp conversion "
              "defect until proven otherwise:",
              f"    {res['bad_first_bar']}", ""]
    if res["dst_bad"]:
        L += ["  DST TRANSITIONS WHERE THE NEXT SESSION DID NOT START 09:30:"]
        for t, sess, got in res["dst_bad"]:
            L.append(f"    transition {t}  session {sess}  first bar {got}")
        L.append("")
    if res["gaps"]:
        L += ["  UNEXPLAINED SESSION GAPS. r1 reads the PRIOR session's close,",
              "  so a hole here is a wrong r1, not a NaN -- there is nothing",
              "  to notice. The weekdays named are absent from the cache and",
              "  are not holidays or known closures:"]
        for a, b, n, miss in res["gaps"][:15]:
            L.append(f"    {a} -> {b}   {n} days   missing: {', '.join(miss)}")
        if len(res["gaps"]) > 15:
            L.append(f"    ... and {len(res['gaps']) - 15} more")
        L.append("")
    if res.get("gaps_explained"):
        L += ["  Gaps over four days that ARE explained, and are not defects:"]
        for a, b, n, _ in res["gaps_explained"][:10]:
            L.append(f"    {a} -> {b}   {n} days   (holiday or known closure)")
        L.append("")

    L += ["  bars per session: " + ", ".join(
        f"{k}x{v}" for k, v in res["bars_per_session"].items()),
        f"  (a full RTH day is {FULL_DAY_BARS} thirty-minute bars)", ""]

    L += ["  largest overnight moves (prior close -> 09:30 open). A split or a",
          "  mixed adjustment series prints here first:"]
    for k, v in res["max_overnight"].items():
        L.append(f"    {k}   {v * 100:>7.3f}%")
    L += ["", "HALF-DAYS EXCLUDED, BY NAME", ""]
    if res["half_days"]:
        for i in range(0, len(res["half_days"]), 6):
            L.append("    " + "  ".join(res["half_days"][i:i + 6]))
    else:
        L.append("    none found -- SUSPICIOUS on a multi-year window, which")
        L.append("    should carry roughly nine a year.")
    L.append("")

    L += ["|r13| BY YEAR -- the spec's economics assume 0.20-0.30%", ""]
    L.append("    year      n   mean|r13|%  median|r13|%   sd%")
    for y, row in r13y.iterrows():
        L.append(f"    {y}   {int(row['n']):>4}   {row['mean_abs_pct']:>9.4f}   "
                 f"{row['median_abs_pct']:>10.4f}   {row['sd_pct']:>6.4f}")
    allmean = usable["r13"].abs().mean() * 100
    L += ["", f"    whole window mean |r13| = {allmean:.4f}%", ""]
    if allmean < 0.18:
        L += ["    BELOW THE REGISTERED ASSUMPTION. Spec section 12 step 2:",
              "    the arithmetic changes and the study is RE-REGISTERED",
              "    before it is run.", ""]

    L += ["SIGMA1", ""]
    if sig.empty:
        L += ["    no fine-grained cache -- sigma1 NOT COMPUTED, and H-S2",
              "    cannot run until it is.", ""]
    else:
        L += [f"    sessions with sigma1   {len(sig)}",
              f"    median                 {sig.median():.5f}",
              f"    67th percentile (full sample, for scale ONLY -- the gate",
              f"    uses a TRAILING 252-session percentile, point-in-time)"
              f"  {sig.quantile(0.67):.5f}", ""]

    L += ["WHAT HAPPENS NEXT", "",
          "  Nothing, until the FAIL lines above are zero and the session",
          "  count is read. Then, in order: H0 first (spec section 12 step 3),",
          "  and only if the control is flat, H-S1 and H-S2.",
          "  The holdout is cut BEFORE any of that: --make-holdout."]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--assert", dest="do_assert", action="store_true")
    ap.add_argument("--make-holdout", action="store_true")
    ap.add_argument("--symbols", nargs="+", default=["SPY"])
    ap.add_argument("--fine", default="5 mins", choices=["5 mins", "1 min"],
                    help="which cache sigma1 and the cross-check read")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if not (args.do_assert or args.make_holdout):
        sys.exit("pass --assert or --make-holdout")

    blocks = []
    for sym in args.symbols:
        df30 = load_bars("30 mins", sym)
        df5 = load_bars(args.fine, sym)
        s = build_sessions(df30)
        res = check(s, df30)
        xc = cross_cache(s, df5) if not s.empty else {"status": "no 30m cache"}
        sig = sigma1(df5)
        r13y = abs_r13_by_year(s) if not s.empty else pd.DataFrame()
        blocks += render(sym, s, res, xc, sig, r13y, datetime.now(ET)) + ["", ""]

        if args.make_holdout and sym == "SPY":
            usable = s[s["full"]].dropna(subset=["r1", "r13"])
            days = list(usable.index)
            if len(days) < 20:
                blocks += [f"HOLDOUT NOT CUT: only {len(days)} usable sessions."]
            elif SPY_HOLDOUT_PATH.exists():
                blocks += [f"HOLDOUT NOT CUT: {SPY_HOLDOUT_PATH.name} already "
                           f"exists. A holdout that can be re-cut is not a "
                           f"holdout -- delete it deliberately or keep it."]
            else:
                rec = make_holdout(days)
                SPY_HOLDOUT_PATH.write_text(
                    json.dumps(rec, indent=2) + "\n", encoding="utf-8")
                blocks += [f"HOLDOUT CUT -> {SPY_HOLDOUT_PATH.name}",
                           json.dumps(rec, indent=2), ""]

    emit("\n".join(blocks), args.out or "var/reports/spy_intraday_assert.txt",
         header="common.spy_intraday --assert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
