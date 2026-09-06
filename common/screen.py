#!/usr/bin/env python3
"""Rebuild the watchlist from daily bars: which names, on which mornings.

    python -m common.screen --report
    python -m common.screen --pairs var/state/screen_pairs.json
    python -m common.screen --validate var/state/flex_pairs_all.json

WHAT THIS IS FOR
----------------
Every backtest in this project was HANDED its universe -- 407 hindsight pairs
which turned out to be 401 of Ben's own trades. PROGRAM_INDEX section 4 names
that as the bias no amount of drop-top-N can remove, and
claude/session_aware_screening.md section 3 says plainly that the screener has
never been simulated. This module simulates it.

THE LOOK-AHEAD TRAP, WHICH IS THE WHOLE DIFFICULTY
---------------------------------------------------
MCL picks its watchlist at 04:00 ET. A daily bar is not known until 20:00. So
ANY rule using today's daily volume, high, low or close to decide what to trade
this morning is look-ahead -- it selects names using information from after the
decision. Applied naively it produces a spectacular backtest and an untradeable
strategy, and it would not look wrong: the P/L would simply be large.

So the rules here are split, and the split is enforced rather than described:

  TRADEABLE (stage 1) -- uses only data available before the session opens:
    a loose sanity range on the previous close, and the trailing 10-day average
    dollar volume. A live scanner at 03:59 has both.

    Note what is NOT here: MCL's $2-20 band. It is enforced at ENTRY by the
    strategy, on the price at that moment. Applying it to the prior close
    rejected 39% of the names Ben actually traded, because the live scanner
    reads premarket_close and a $1.50 stock that gaps to $4 passes it.

  FETCH FILTER (stage 2) -- uses today's daily bar, and is therefore NOT a
    trading rule. Its only job is to decide which symbol-days are worth
    spending minute-bar data on, cutting ~11,000 names a day to a few dozen.

Stage 2 leaks, and the leak has to be measured rather than argued about. It
excludes days that were quiet in aggregate, so a backtest run only on stage-2
survivors describes "days that turned out active" and will overstate. The
control is in section 4 of the report: take a random sample of days stage 2
REJECTED, pull their minute bars, and confirm the strategy produces no entries
there. MCL requires a volume surge to arm, so the expected answer is that it
produces almost none -- but expected is not measured, and this project has been
wrong about exactly that kind of expectation before.

Until that control has been run, treat every number downstream as an upper
bound.

WHAT IS MISSING AND CANNOT BE FIXED HERE
-----------------------------------------
Float. MCL's universe rule is float < 20m and no Databento tier carries
fundamentals. Using today's float retroactively is look-ahead on the filter the
whole universe definition rests on -- a name with 3m float last year may have
60m now after dilution, and small caps dilute constantly. The screen therefore
runs WITHOUT float, and section 3 of the report measures what that costs by
comparing recall against the known pair list. Sourcing point-in-time float is a
separate problem; pretending the filter is present is not an option.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from common.dbn_io import daily_frame
from common.report_io import emit

from common.databento_fetch import default_archive

DATASET_DEFAULT = "EQUS.MINI"

# Exchange TEST symbols. These are not securities -- venues publish them
# continuously so members can verify connectivity, and they carry real-looking
# prices and volume on a tape that makes no distinction.
#
# ZVZZT was the SECOND most frequent name in the first candidate list: 30 of
# 864 sessions. It would have been "traded" in the backtest, produced P/L, and
# appeared in the results as an ordinary symbol -- and because its prints are
# arbitrary, its contribution would have been noise dressed as a finding. Every
# venue has its own set; below are the published Nasdaq, NYSE, Cboe and IEX
# ones plus the shapes they follow.
TEST_SYMBOLS = frozenset({
    "ZAZZT", "ZBZZT", "ZCZZT", "ZEXIT", "ZIEXT", "ZJZZT", "ZTEST", "ZVV",
    "ZVZZC", "ZVZZT", "ZWZZT", "ZXIET", "ZXZZT", "ZZZ", "ZZZZ",
    "ATEST", "CTEST", "MTEST", "NTEST", "PTEST", "QTEST", "ZTST",
})
_TEST_RE = re.compile(r"^(Z[A-Z]ZZ[TC]|[A-Z]?TEST[A-Z]?|.*\.TEST)$")


def is_test_symbol(sym: str) -> bool:
    s = (sym or "").upper()
    return s in TEST_SYMBOLS or bool(_TEST_RE.match(s))


@dataclass
class Config:
    """Every threshold, with its provenance. Nothing here is swept.

    A screen tuned to maximise backtest P/L is a screen fitted to the outcome
    it is meant to predict. These are set from MCL's shipped universe rule and
    from measurement, and they change only for a stated reason.
    """
    # -- stage 1: tradeable, known before the session --------------------
    #
    # These are a SANITY range, not MCL's $2-20 band. Measured 2026-09-06: the
    # 587 symbol-days Ben actually traded had a median prior close of $2.60 and
    # a p10 of $0.77, and applying $2-20 to the PRIOR close rejected 39% of
    # them. That is not a universe disagreement, it is the wrong column: MCL's
    # live scanner screens on premarket_close, the price at 04:00, so a $1.50
    # stock that gaps to $4 pre-market passes live and fails here. MCL already
    # enforces the real band at entry (ENFORCE_PRICE_BAND), which is both the
    # right place and not look-ahead. The screen must not enforce it twice, and
    # must not enforce it on a price from the wrong day.
    price_min: float = 0.50         # sanity floor -- below p10 of the real set
    price_max: float = 50.0         # sanity ceiling
    #
    # Measured: prior_avg_dollar_vol on the traded names is p10 $1,513, median
    # $53,478. A $200,000 floor rejected 67% of them. It was also asking the
    # wrong question -- what matters is not what a name traded BEFORE the event
    # but whether an order can be filled ON the day, and these names do ~24x
    # their prior average when they run. Liquidity is a SIZING constraint
    # (max_pct_of_dollar_vol below), not a universe filter. PROGRAM_INDEX
    # already records the volume-floor study failing this way: eight of 21
    # names produced zero trades and the excluded ones held ~$872 of winners
    # against ~$115 of losers.
    min_avg_dollar_vol: float = 25_000.0    # measured 2026-09-06, see above
    avg_vol_days: int = 10          # matches TradingView's 10-day RVOL basis

    # -- stage 2: fetch filter, uses today's bar, NOT a trading rule -----
    # Left alone deliberately. Measured on the traded names: median daily RVOL
    # 23.9x against this 5x threshold, and the range rule rejects 1%. Neither
    # is binding, and both are MCL's own rule rather than a guess of mine --
    # so there is nothing here to justify changing.
    min_rvol: float = 5.0           # MCL universe rule, RVOL(1D) >= 5x
    min_range_pct: float = 10.0     # GUESS, but measured non-binding
    max_candidates_per_day: int = 60  # GUESS -- caps a runaway day

    # Sizing, not screening. Carried here so the backtest can cap a position at
    # a share of the day's actual dollar volume instead of pretending a $53k/day
    # name can absorb any order. Not applied by this module -- it is the
    # backtest's job -- but it is the reason the liquidity floor could come
    # down, so it belongs beside it.
    max_pct_of_dollar_vol: float = 1.0   # GUESS -- never calibrated

    def marked(self) -> str:
        return (
            f"  prior-close sanity  ${self.price_min:.2f}-${self.price_max:.0f}"
            "   [NOT MCL's band -- see below]\n"
            f"  avg $ volume >=     ${self.min_avg_dollar_vol:,.0f}"
            f" over {self.avg_vol_days}d   [measured 2026-09-06]\n"
            f"  RVOL >=             {self.min_rvol:.1f}x"
            "   [MCL universe rule, non-binding]\n"
            f"  day range >=        {self.min_range_pct:.0f}%"
            "   [GUESS, measured non-binding]\n"
            f"  max per day         {self.max_candidates_per_day}   [GUESS]\n"
            f"  size cap            {self.max_pct_of_dollar_vol:.1f}% of the"
            " day's $ volume   [GUESS, applied downstream]\n"
            "  NOTE: MCL's $2-20 band is enforced at ENTRY by the strategy, on\n"
            "  the price at the time, not here on the prior close. Applying it\n"
            "  here rejected 39% of the names Ben actually traded, because a\n"
            "  $1.50 stock that gaps to $4 pre-market passes the live scanner\n"
            "  and fails a prior-close test."
        )


# --------------------------------------------------------------------------

def features(daily: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Per symbol-day features, with the look-ahead boundary made explicit.

    Columns prefixed `prior_` use only data from BEFORE the session. Everything
    else uses today's bar and may only be read by the fetch filter.
    """
    if daily.empty:
        return daily
    df = daily.sort_values(["symbol", "date"]).copy()
    g = df.groupby("symbol", sort=False)

    df["prior_close"] = g["close"].shift(1)
    dollar_vol = df["close"] * df["volume"]
    # shift(1) BEFORE rolling: the average must exclude today entirely. Rolling
    # first and shifting after is the same arithmetic; rolling on an unshifted
    # series and using it as "prior" is the bug, and it is invisible in the
    # numbers because the result is merely a bit better.
    df["prior_avg_dollar_vol"] = (
        dollar_vol.groupby(df["symbol"], sort=False)
        .transform(lambda s: s.shift(1).rolling(cfg.avg_vol_days, min_periods=3).mean()))
    df["prior_avg_vol"] = (
        df["volume"].groupby(df["symbol"], sort=False)
        .transform(lambda s: s.shift(1).rolling(cfg.avg_vol_days, min_periods=3).mean()))

    df["rvol"] = df["volume"] / df["prior_avg_vol"]
    df["range_pct"] = (df["high"] - df["low"]) / df["prior_close"] * 100.0
    df["gap_pct"] = (df["open"] - df["prior_close"]) / df["prior_close"] * 100.0
    df["dollar_vol"] = dollar_vol
    return df


def stage1(df: pd.DataFrame, cfg: Config) -> pd.Series:
    """Tradeable mask: decidable at 03:59 on the morning in question."""
    return (
        df["prior_close"].between(cfg.price_min, cfg.price_max)
        & (df["prior_avg_dollar_vol"] >= cfg.min_avg_dollar_vol)
    )


def stage2(df: pd.DataFrame, cfg: Config) -> pd.Series:
    """Fetch filter. Uses today's bar and is NOT a trading rule -- see module
    docstring. Only ever used to decide what minute data to buy."""
    return (df["rvol"] >= cfg.min_rvol) & (df["range_pct"] >= cfg.min_range_pct)


def select(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Candidate symbol-days: stage 1 AND stage 2, capped per day.

    The cap is applied by RVOL rank within the date. It exists so one wild
    session cannot produce four hundred candidates and dominate the minute-bar
    bill; it is a GUESS and it is reported, because a cap that binds often is
    quietly changing the universe.
    """
    m = stage1(df, cfg) & stage2(df, cfg) & ~df["symbol"].map(is_test_symbol)
    out = df[m].copy()
    if out.empty:
        return out
    out["rank"] = out.groupby("date")["rvol"].rank(ascending=False, method="first")
    return out[out["rank"] <= cfg.max_candidates_per_day].drop(columns="rank")


def pairs(sel: pd.DataFrame) -> list[dict]:
    return [{"symbol": s, "date": d}
            for s, d in sorted(zip(sel["symbol"], sel["date"]))]


# --------------------------------------------------------------------------

def _q(s: pd.Series) -> str:
    s = s.dropna()
    if s.empty:
        return "no data"
    return (f"p10 {s.quantile(.10):>12,.2f}   median {s.median():>12,.2f}"
            f"   p90 {s.quantile(.90):>12,.2f}")


def diagnose(df: pd.DataFrame, cfg: Config,
             known: list[tuple[str, str]] | None, n_sessions: int) -> str:
    """Which threshold is actually doing the cutting, measured not guessed.

    3.5 candidates a session against a live scanner's 20-60 means a filter is
    wrong, and four of the five are marked GUESS. Loosening them one at a time
    until the count looks right would be fitting the screen to an intuition;
    this instead reports what each threshold rejects and what the known pairs
    -- names Ben actually traded -- actually looked like on the day.

    The known pairs are the closest thing to ground truth available: whatever
    generated them, a screen meant to reproduce it should not be rejecting 92%.
    """
    out, A = [], None
    out = []
    A = out.append
    A("3b. WHAT EACH THRESHOLD REJECTS")

    band = df["prior_close"].between(cfg.price_min, cfg.price_max)
    liq = df["prior_avg_dollar_vol"] >= cfg.min_avg_dollar_vol
    rv = df["rvol"] >= cfg.min_rvol
    rng = df["range_pct"] >= cfg.min_range_pct
    n = len(df)
    for name, m in (("prior-close sanity", band), ("liquidity floor", liq),
                    ("RVOL", rv), ("day range", rng)):
        A(f"  {name:<18} passes {int(m.sum()):>9,}  ({100*m.mean():.1f}% of all rows)")

    A("")
    A("  candidates/session with ONE threshold relaxed at a time:")
    base = (band & liq & rv & rng).sum() / max(n_sessions, 1)
    A(f"    all as configured                {base:>6.1f}")
    for label, m in (("no prior-close sanity", liq & rv & rng),
                     ("no liquidity floor", band & rv & rng),
                     ("no RVOL rule", band & liq & rng),
                     ("no range rule", band & liq & rv)):
        A(f"    {label:<32} {m.sum()/max(n_sessions,1):>6.1f}")
    for v in (1.5, 2.0, 3.0):
        m = band & liq & (df["rvol"] >= v) & rng
        A(f"    RVOL >= {v:<24.1f} {m.sum()/max(n_sessions,1):>6.1f}")
    for v in (2.0, 5.0):
        m = band & liq & rv & (df["range_pct"] >= v)
        A(f"    range >= {str(int(v))+chr(37):<24} {m.sum()/max(n_sessions,1):>6.1f}")

    if not known:
        return "\n".join(out)

    idx = df.set_index(["symbol", "date"])
    have = [k for k in known if k in idx.index]
    if not have:
        A("")
        A("  (no known pairs found in the archive)")
        return "\n".join(out)
    k = idx.loc[have]

    A("")
    A(f"3c. THE {len(have)} KNOWN PAIRS, AS THE DAILY BARS SAW THEM")
    A(f"  prior_close        {_q(k['prior_close'])}")
    A(f"  prior_avg_$vol     {_q(k['prior_avg_dollar_vol'])}")
    A(f"  rvol (daily)       {_q(k['rvol'])}")
    A(f"  range_pct          {_q(k['range_pct'])}")
    A(f"  gap_pct            {_q(k['gap_pct'])}")

    kb = k["prior_close"].between(cfg.price_min, cfg.price_max)
    kl = k["prior_avg_dollar_vol"] >= cfg.min_avg_dollar_vol
    kr = k["rvol"] >= cfg.min_rvol
    kg = k["range_pct"] >= cfg.min_range_pct
    A("")
    A("  rejected by (independently -- a pair can fail several):")
    for name, m in (("prior-close sanity", ~kb), ("liquidity floor", ~kl),
                    ("RVOL", ~kr), ("day range", ~kg)):
        A(f"    {name:<18} {int(m.sum()):>4} of {len(k)}"
          f"  ({100*m.mean():.0f}%)")
    A(f"    passes everything  {int((kb & kl & kr & kg).sum()):>4} of {len(k)}")
    # The band MCL actually applies, reported for information only. It is
    # enforced at entry on the live price, so a prior close outside it does not
    # mean the trade was outside the universe -- but the gap between the two
    # numbers is the whole reason the screen stopped applying it.
    mcl = k["prior_close"].between(2.0, 20.0)
    A("")
    A(f"  for information: {int((~mcl).sum())} of {len(k)} had a PRIOR close")
    A("  outside MCL's $2-20. The strategy still judges them on the entry")
    A("  price, so this is not by itself a universe mismatch.")
    return "\n".join(out)


def report(df: pd.DataFrame, sel: pd.DataFrame, cfg: Config,
           known: list[tuple[str, str]] | None = None) -> str:
    out, A = [], None
    out = []
    A = out.append

    A("1. THRESHOLDS")
    A(cfg.marked())

    dates = sorted(df["date"].unique())
    A("")
    A("2. COVERAGE")
    A(f"  symbol-days in the daily archive   {len(df):,}")
    A(f"  distinct symbols                   {df['symbol'].nunique():,}")
    A(f"  sessions                           {len(dates)}"
      f"   {dates[0]} -> {dates[-1]}" if dates else "  no sessions")
    s1 = stage1(df, cfg).sum()
    A(f"  pass stage 1 (tradeable)           {s1:,}"
      f"  ({100*s1/max(len(df),1):.1f}%)")
    n_test = int(df["symbol"].map(is_test_symbol).sum())
    A(f"  exchange TEST symbols excluded     {n_test:,}"
      f"  ({df[df['symbol'].map(is_test_symbol)]['symbol'].nunique()} distinct)")
    A(f"  pass stage 1 AND stage 2           {len(sel):,}")
    if dates:
        per = len(sel) / len(dates)
        A(f"  candidates per session             {per:.1f} mean")
        byday = sel.groupby("date").size() if not sel.empty else pd.Series(dtype=int)
        if not byday.empty:
            A(f"    median {byday.median():.0f}   p90 {byday.quantile(0.9):.0f}"
              f"   max {byday.max()}")
            capped = (byday >= cfg.max_candidates_per_day).sum()
            A(f"    sessions hitting the cap         {capped}"
              f"  {'<-- cap is binding, raise it or tighten RVOL' if capped > len(dates)*0.05 else ''}")

    A("")
    A("3. RECALL AGAINST THE KNOWN PAIRS")
    if known:
        lo, hi = dates[0], dates[-1]
        k = [p for p in known if lo <= p[1] <= hi]
        got = {(r.symbol, r.date) for r in sel.itertuples()}
        hit = [p for p in k if p in got]
        A(f"  known pairs inside the archive's dates   {len(k)}")
        A(f"  the screen would have surfaced           {len(hit)}"
          f"  ({100*len(hit)/max(len(k),1):.0f}%)")
        A("  Misses are not automatically failures -- Ben traded names outside")
        A("  the $2-20 band and outside any RVOL rule. But a LOW recall means")
        A("  the screen is not reproducing the thing that generated those")
        A("  trades, and the backtest would be measuring a different strategy.")
        miss = [p for p in k if p not in got][:8]
        if miss:
            A(f"  examples missed: {', '.join(f'{s} {d}' for s, d in miss)}")
    else:
        A("  (no known pair list supplied -- pass --validate)")

    A("")
    A(diagnose(df, cfg, known, len(dates)))

    A("")
    A("4. THE CONTROL THAT HAS NOT BEEN RUN")
    A("  Stage 2 uses today's daily bar and therefore leaks. A backtest on")
    A("  survivors describes 'days that turned out active'. Before any P/L")
    A("  from this universe is believed: sample rejected symbol-days, pull")
    A("  their minute bars, and confirm the strategy produces (almost) no")
    A("  entries. Until then every downstream figure is an UPPER BOUND.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild the watchlist from daily bars")
    ap.add_argument("--archive", default=str(default_archive()),
                    help="archive root (default: %(default)s)")
    ap.add_argument("--dataset", default=DATASET_DEFAULT)
    ap.add_argument("--pairs", metavar="OUT.json", help="write candidate pairs")
    ap.add_argument("--features", metavar="OUT.csv", help="write the feature table")
    ap.add_argument("--out", metavar="OUT.txt",
                    default="var/reports/screen_report.txt",
                    help="save the report as UTF-8 (default: %(default)s)")
    ap.add_argument("--validate", metavar="KNOWN.json",
                    help="pair list to measure recall against")
    ap.add_argument("--min-rvol", type=float)
    ap.add_argument("--min-range-pct", type=float)
    ap.add_argument("--min-avg-dollar-vol", type=float)
    ap.add_argument("--max-per-day", type=int)
    a = ap.parse_args(argv)

    cfg = Config()
    if a.min_rvol is not None:
        cfg.min_rvol = a.min_rvol
    if a.min_range_pct is not None:
        cfg.min_range_pct = a.min_range_pct
    if a.min_avg_dollar_vol is not None:
        cfg.min_avg_dollar_vol = a.min_avg_dollar_vol
    if a.max_per_day is not None:
        cfg.max_candidates_per_day = a.max_per_day

    daily = daily_frame(a.archive, a.dataset)
    if daily.empty:
        sys.exit(f"No daily bars in {a.archive}/{a.dataset}/ohlcv-1d/. "
                 "Run: python -m common.databento_universe --confirm")

    df = features(daily, cfg)
    sel = select(df, cfg)

    known = None
    if a.validate:
        known = [(p["symbol"], p["date"]) for p in json.load(open(a.validate))]

    emit(report(df, sel, cfg, known), a.out,
         header=f"common.screen  dataset={a.dataset}  archive={a.archive}")

    if a.pairs:
        Path(a.pairs).parent.mkdir(parents=True, exist_ok=True)
        pl = pairs(sel)
        json.dump(pl, open(a.pairs, "w"), indent=1)
        print(f"\nwrote {a.pairs}  ({len(pl)} candidate symbol-days)")
    if a.features:
        Path(a.features).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(a.features, index=False)
        print(f"wrote {a.features}  ({len(df):,} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
