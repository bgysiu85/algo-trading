#!/usr/bin/env python3
"""Turn spread_sampler.py's CSV into the measured cost distribution for G2.

    python -m strategy.swing.spread_report var/reports/spread_samples.csv
    python -m strategy.swing.spread_report var/reports/*.csv --position-usd 9000
    python -m strategy.swing.spread_report --self-test

WHAT IT ANSWERS
---------------
`swing_preflight_20260914.md` section 3.5 estimates an all-in round trip of
2.5-5.5 bps for a large cap and 7-20 bps for a mid cap. Those are ASSUMED. G2
says a candidate is not accepted until they are MEASURED. This report replaces
the spread-crossing line of that table with a number off the tape, and tells
you which side of the G2 threshold (40 bps) the universe sits on.

WHAT IT REFUSES TO DO
---------------------
  * It will not pool a row whose md_type is not 1. Delayed quotes populate bid
    and ask like live ones and would produce a precise, meaningless number.
    Non-live rows are COUNTED and reported, never silently dropped and never
    mixed in.
  * It will not report a percentile for a symbol with fewer than --min-obs
    usable observations. A spread from nine quotes is not a distribution.
  * It reports coverage in the same pass as the result, per the project's
    standing rule: rows in, rows usable, rows rejected and why.

THE COST MODEL, STATED
----------------------
Crossing the spread costs the HALF spread on each leg, so a round trip that
takes liquidity on both sides pays ONE FULL QUOTED SPREAD. That is the
assumption this report prints, and it is deliberate:

    effective spread / quoted spread ~ 0.97 at exchanges, 0.76 at wholesalers

An IBKR Pro account routes to exchanges and ATSs and does not receive the
wholesaler price improvement that makes published effective spreads look
tight. So the full quoted spread is the honest figure here, and any tighter
number has to come from Ben's own fills rather than from a published average.

  quoted spread (cents) = ask - bid
  quoted spread (bps)   = 10000 * (ask - bid) / mid
  round trip (bps)      = the same number, by the paragraph above

DEPTH IS REPORTED BECAUSE IT BINDS BEFORE SPREAD DOES
------------------------------------------------------
At a USD 9,000 position in a mid cap above $40, the pre-flight found the order
can be several multiples of the entire displayed book at the touch. Spread
tells you what one round lot costs; depth tells you whether the quote applies
to your order at all. Both are printed, and the report flags every symbol where
the target position exceeds the median displayed dollar depth.

NO REPO IMPORTS, DELIBERATELY
------------------------------
Same reasoning as the collector: nothing from `common/`, and no colour emitted
anywhere, so a report written to a .txt is plain by construction.

TIME OF DAY IS NOT A DETAIL
----------------------------
Spreads at 09:30 are not spreads at 11:00. A swing strategy that enters on the
open pays the open's spread, so the pooled median is the wrong number for it.
The report buckets by ET half-hour rather than leaving that to be discovered
later.
"""
from __future__ import annotations

import argparse
import csv
import glob
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

G2_THRESHOLD_BPS = 40.0        # swing_preflight_20260914.md section 8, G2

# IBKR tiered, marketable both legs, from the pre-flight section 3.3:
#   0.0035 commission + 0.0030 exchange take + ~0.0004 reg/clearing, per share,
#   per leg. Round trip therefore ~2 x 0.0069 = 0.0138 per share.
FEES_PER_SHARE_RT = 0.0138


# ------------------------------------------------------------------ util ----

def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def fmt(x: float, w: int = 8, d: int = 2) -> str:
    if x != x:
        return "n/a".rjust(w)
    if x < 0:
        return f"({abs(x):,.{d}f})".rjust(w)     # accounting brackets
    return f"{x:,.{d}f}".rjust(w)


RTH_OPEN_MIN = 9 * 60 + 30      # 09:30 ET
RTH_CLOSE_MIN = 16 * 60         # 16:00 ET
EXT_OPEN_MIN = 4 * 60           # 04:00 ET, pre-market
EXT_CLOSE_MIN = 20 * 60         # 20:00 ET, post-market

SESSIONS = {
    "rth": (RTH_OPEN_MIN, RTH_CLOSE_MIN, "regular hours, 09:30-16:00 ET"),
    "ext": (EXT_OPEN_MIN, EXT_CLOSE_MIN, "extended hours, 04:00-20:00 ET"),
    "all": (0, 24 * 60, "every hour of the clock"),
}


def et_time(ts_utc: str) -> datetime:
    """The ET wall clock for a UTC stamp. UTC-4 in summer, UTC-5 in winter.

    The offset is derived from the date rather than assumed, because a run that
    straddles the DST change would otherwise mislabel half its rows -- and a
    mislabelled 09:30 bucket is exactly the kind of error that reads as a real
    finding about the open.
    """
    dt = datetime.strptime(ts_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    y = dt.year
    # 2nd Sunday in March -> 1st Sunday in November, 07:00 UTC both ends.
    mar = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar + timedelta(days=(6 - mar.weekday()) % 7 + 7, hours=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7, hours=6)
    offset = -4 if dst_start <= dt < dst_end else -5
    return dt + timedelta(hours=offset)


def et_minutes(ts_utc: str) -> int:
    """Minutes past ET midnight."""
    et = et_time(ts_utc)
    return et.hour * 60 + et.minute


def in_session(ts_utc: str, session: str) -> bool:
    lo, hi, _ = SESSIONS[session]
    return lo <= et_minutes(ts_utc) <= hi


def et_bucket(ts_utc: str) -> str:
    """ET half-hour label."""
    et = et_time(ts_utc)
    half = 0 if et.minute < 30 else 30
    return f"{et.hour:02d}:{half:02d}"


# ------------------------------------------------------------------ load ----

class Rejects:
    def __init__(self):
        self.not_live = 0
        self.md_types: dict[str, int] = defaultdict(int)
        self.missing = 0
        self.crossed = 0
        self.nonpositive = 0
        self.wide = 0          # > 10% of mid: a stub quote, not a spread
        self.out_of_session = 0
        self.session = "rth"

    def total(self) -> int:
        return (self.not_live + self.missing + self.crossed
                + self.nonpositive + self.wide + self.out_of_session)


def load(paths: list[str], max_rel: float,
         session: str = "rth") -> tuple[list[dict], Rejects, int]:
    """Read the sample CSVs, keeping only rows that belong in the answer.

    `session` defaults to "rth" and that default is the point. A sampler left
    running through the Australian day collects 13 hours of quotes of which
    under 5% fall inside US regular hours, and the overnight book is four to
    five times wider. Pooling them produced 34.27 bps against the honest 8.00
    -- a number that passed the G2 gate and meant nothing. Out-of-session rows
    are COUNTED and reported, never silently dropped.
    """
    if session not in SESSIONS:
        raise ValueError(f"session must be one of {sorted(SESSIONS)}")
    rows: list[dict] = []
    rej = Rejects()
    rej.session = session
    total = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                total += 1
                if not in_session(r["ts_utc"], session):
                    rej.out_of_session += 1
                    continue
                mdt = (r.get("md_type") or "").strip()
                rej.md_types[mdt or "(blank)"] += 1
                if mdt != "1":
                    rej.not_live += 1
                    continue
                try:
                    bid = float(r["bid"]); ask = float(r["ask"])
                except (ValueError, KeyError, TypeError):
                    rej.missing += 1
                    continue
                if bid <= 0 or ask <= 0:
                    rej.nonpositive += 1
                    continue
                if ask < bid:
                    rej.crossed += 1
                    continue
                mid = (bid + ask) / 2.0
                rel = (ask - bid) / mid
                if rel > max_rel:
                    rej.wide += 1
                    continue

                def size(k):
                    try:
                        return float(r[k])
                    except (ValueError, KeyError, TypeError):
                        return float("nan")

                rows.append({
                    "ts": r["ts_utc"],
                    "sym": r["symbol"],
                    "mid": mid,
                    "cents": (ask - bid) * 100.0,
                    "bps": rel * 10000.0,
                    "bid_sz": size("bid_size"),
                    "ask_sz": size("ask_size"),
                })
    return rows, rej, total


# ---------------------------------------------------------------- report ----

def build(rows, rej, total, args) -> str:
    L: list[str] = []
    def w(s=""):
        L.append(s)

    w("=" * 78)
    w("MEASURED SPREAD - candidate swing universe")
    w("swing_preflight_20260914.md G2: cost measured, not assumed")
    w("=" * 78)
    w(f"generated      {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}")
    w(f"inputs         {', '.join(args.csv)}")

    # ---- coverage, in the same pass as the result --------------------------
    w()
    w("-" * 78)
    w("COVERAGE")
    w("-" * 78)
    sess = getattr(rej, "session", "rth")
    _, _, sess_label = SESSIONS[sess]
    w(f"  session filter           {sess:>9}   ({sess_label})")
    w(f"  rows read                {total:>9,}")
    w(f"  rows usable              {len(rows):>9,}"
      f"   ({100.0*len(rows)/total if total else 0:5.1f}%)")
    w(f"  rows rejected            {rej.total():>9,}")
    w(f"      {'outside the session':<21}{rej.out_of_session:>9,}")
    w(f"      {'not live (md_type)':<21}{rej.not_live:>9,}")
    w(f"      {'bid/ask missing':<21}{rej.missing:>9,}")
    w(f"      {'non-positive':<21}{rej.nonpositive:>9,}")
    w(f"      {'crossed (ask < bid)':<21}{rej.crossed:>9,}")
    w(f"      {'wider than ' + format(args.max_rel*100, '.0f') + '% of mid':<21}{rej.wide:>9,}")
    w()
    w("  market data types seen (1=live 2=frozen 3=delayed 4=delayed-frozen):")
    for k in sorted(rej.md_types):
        w(f"      {k:>10}  {rej.md_types[k]:>9,}")

    if not rows:
        w()
        w("!! NO USABLE ROWS. Nothing below can be computed.")
        if rej.out_of_session and not rej.not_live:
            w(f"!! Every row fell outside {sess_label}. The sampler ran while the US")
            w("!! market was shut. Re-run it across a real session, or pass")
            w("!! --session ext / --session all if you deliberately want those hours.")
        if rej.not_live:
            w("!! Every row was rejected for market data type. The subscription is")
            w("!! most likely on the live account and not shared to paper, so IB")
            w("!! served delayed quotes. Fix that and re-run; do not 'work around'")
            w("!! it by accepting md_type 3, which would measure nothing.")
        return "\n".join(L)

    if total and rej.out_of_session / total > 0.20:
        w()
        w("  " + "!" * 74)
        w(f"  !! {100.0*rej.out_of_session/total:.1f}% of the rows collected fall OUTSIDE "
          f"{sess_label}.")
        w("  !! They are excluded above. The collector was most likely left running")
        w("  !! through hours the US market was shut -- the overnight and pre-market")
        w("  !! book is several times wider, and pooling it produces a precise number")
        w("  !! that answers a question no strategy asks.")
        w("  !! Re-run the sampler across a real session before treating the figures")
        w("  !! below as the universe's cost.")
        w("  " + "!" * 74)

    live_only = set(rej.md_types) - {"1"}
    if live_only:
        w()
        w(f"  NOTE: {rej.not_live:,} non-live rows were counted and EXCLUDED.")
        w("  Nothing below mixes them in.")

    syms = sorted({r["sym"] for r in rows})
    dates = sorted({r["ts"][:10] for r in rows})
    w()
    w(f"  symbols {len(syms)}   sessions {len(dates)}   "
      f"{dates[0]} .. {dates[-1]}")

    # ---- pooled ------------------------------------------------------------
    bps = [r["bps"] for r in rows]
    cents = [r["cents"] for r in rows]
    w()
    w("-" * 78)
    w("POOLED QUOTED SPREAD")
    w("-" * 78)
    w("  A round trip that takes liquidity on both sides pays ONE full quoted")
    w("  spread. Effective/quoted is ~0.97 at exchanges, so no price-improvement")
    w("  discount is applied -- see the module docstring.")
    w()
    w(f"  {'':14}{'p10':>9}{'p25':>9}{'p50':>9}{'p75':>9}{'p90':>9}{'p99':>9}")
    for lbl, xs, d in (("cents/share", cents, 3), ("basis points", bps, 2)):
        w(f"  {lbl:14}" + "".join(
            fmt(pct(xs, p), 9, d) for p in (10, 25, 50, 75, 90, 99)))

    med = pct(bps, 50)
    w()
    w(f"  median round-trip spread cost   {med:6.2f} bps")
    w(f"  G2 threshold                    {G2_THRESHOLD_BPS:6.2f} bps")
    verdict = "PASS" if med <= G2_THRESHOLD_BPS else "FAIL"
    w(f"  pooled verdict                  {verdict}")
    w()
    w("  Caveat that must travel with that verdict: the median is not the number")
    w("  a strategy pays. It pays its own universe's spread at its own entry")
    w("  times -- see the per-symbol and time-of-day tables below.")

    # ---- per symbol --------------------------------------------------------
    per = defaultdict(list)
    for r in rows:
        per[r["sym"]].append(r)

    w()
    w("-" * 78)
    w("BY SYMBOL")
    w("-" * 78)
    w(f"  {'sym':<7}{'n':>7}{'mid':>9}{'cents p50':>11}{'bps p50':>9}"
      f"{'bps p90':>9}{'$depth p50':>12}{'G2':>5}")
    thin: list[str] = []
    short: list[str] = []
    for s in syms:
        rs = per[s]
        if len(rs) < args.min_obs:
            short.append(f"{s}({len(rs)})")
            continue
        b = [r["bps"] for r in rs]
        c = [r["cents"] for r in rs]
        m = statistics.median([r["mid"] for r in rs])
        depths = [min(r["bid_sz"], r["ask_sz"]) * r["mid"]
                  for r in rs
                  if r["bid_sz"] == r["bid_sz"] and r["ask_sz"] == r["ask_sz"]]
        dmed = statistics.median(depths) if depths else float("nan")
        b50 = pct(b, 50)
        flag = "ok" if b50 <= G2_THRESHOLD_BPS else "FAIL"
        w(f"  {s:<7}{len(rs):>7,}{m:>9.2f}{pct(c,50):>11.3f}"
          f"{b50:>9.2f}{pct(b,90):>9.2f}"
          f"{(f'{dmed:,.0f}' if dmed == dmed else 'n/a'):>12}{flag:>5}")
        if dmed == dmed and dmed < args.position_usd:
            thin.append(f"{s} (${dmed:,.0f})")
    if short:
        w()
        w(f"  below --min-obs {args.min_obs}, no percentiles reported: "
          + ", ".join(short))

    # ---- depth -------------------------------------------------------------
    w()
    w("-" * 78)
    w(f"DEPTH AGAINST A USD {args.position_usd:,.0f} POSITION")
    w("-" * 78)
    if thin:
        w("  Median displayed dollar depth at the touch is SMALLER than the target")
        w("  position in these names. The quoted spread understates their cost --")
        w("  the order walks the book rather than trading at the touch:")
        w()
        for t in thin:
            w(f"      {t}")
        w()
        w("  Either size down in these names or drop them from the universe.")
    else:
        w("  Every symbol's median displayed depth at the touch exceeds the target")
        w(f"  position of USD {args.position_usd:,.0f}. Spread is the binding cost,")
        w("  not depth, at this size.")

    # ---- time of day -------------------------------------------------------
    w()
    w("-" * 78)
    w("BY TIME OF DAY (ET half-hour)")
    w("-" * 78)
    w("  A strategy that enters on the open pays the open's spread, not the")
    w("  pooled median.")
    w()
    tod = defaultdict(list)
    for r in rows:
        tod[et_bucket(r["ts"])].append(r["bps"])
    w(f"  {'ET':<8}{'n':>8}{'bps p25':>10}{'bps p50':>10}{'bps p75':>10}"
      f"{'bps p90':>10}{'vs pooled':>11}")
    for k in sorted(tod):
        xs = tod[k]
        if len(xs) < args.min_obs:
            continue
        m2 = pct(xs, 50)
        w(f"  {k:<8}{len(xs):>8,}{pct(xs,25):>10.2f}{m2:>10.2f}"
          f"{pct(xs,75):>10.2f}{pct(xs,90):>10.2f}"
          f"{(m2/med if med else float('nan')):>10.2f}x")

    # ---- all-in ------------------------------------------------------------
    w()
    w("-" * 78)
    w("ALL-IN ROUND TRIP, MEASURED SPREAD + SCHEDULED FEES")
    w("-" * 78)
    w(f"  Fees are IBKR tiered, marketable both legs: {FEES_PER_SHARE_RT:.4f}/share")
    w("  round trip (0.0035 commission + 0.0030 exchange take + ~0.0004 reg and")
    w("  clearing, per leg). Financing is NOT included -- G3 requires it to be")
    w("  charged separately at 7.13%/yr per day held (~0.99 bps/day at 2:1).")
    w()
    w(f"  {'sym':<7}{'mid':>9}{'spread bps':>12}{'fee bps':>10}{'all-in bps':>12}"
      f"{'USD @ pos':>11}")
    allin_all: list[float] = []
    for s in syms:
        rs = per[s]
        if len(rs) < args.min_obs:
            continue
        m = statistics.median([r["mid"] for r in rs])
        sp = pct([r["bps"] for r in rs], 50)
        fee_bps = 10000.0 * FEES_PER_SHARE_RT / m
        tot = sp + fee_bps
        allin_all.append(tot)
        w(f"  {s:<7}{m:>9.2f}{sp:>12.2f}{fee_bps:>10.2f}{tot:>12.2f}"
          f"{args.position_usd*tot/10000.0:>11.2f}")
    if allin_all:
        w()
        w(f"  {'universe':<7}{'':>9}{'':>12}{'':>10}"
          f"{statistics.median(allin_all):>12.2f}"
          f"{args.position_usd*statistics.median(allin_all)/10000.0:>11.2f}"
          "   <- median")

    # ---- what could be wrong ----------------------------------------------
    w()
    w("-" * 78)
    w("WHAT COULD BE WRONG WITH THIS")
    w("-" * 78)
    w("  * SNAPSHOTS, NOT A CONTINUOUS TAPE. The sampler reads the quote every")
    w("    --interval seconds. That is an unbiased sample of the spread over")
    w("    time, but it is NOT the spread at the moments a strategy would trade,")
    w("    and it will under-represent brief dislocations entirely.")
    w(f"  * ONLY {sess_label.upper()} IS COUNTED. Out-of-hours quotes were")
    w(f"    excluded ({rej.out_of_session:,} rows). That is correct for a strategy")
    w("    trading the regular session and wrong for one that does not.")
    w(f"  * {len(dates)} session(s) is a small sample of market conditions. A")
    w("    quiet week understates the cost of a volatile one, and the pre-flight")
    w("    already established that gap sessions are exactly when spreads widen.")
    w("  * DISPLAYED depth is not available depth. Hidden and reserve size is")
    w("    real, and cuts in the favourable direction; the book also disappears")
    w("    faster than it displays when it matters.")
    w("  * This measures the QUOTE, not a fill. It is the correct input to a")
    w("    cost model and it is not a measurement of slippage. Only real fills")
    w("    measure slippage, which is what common/friction_quotes.py is for.")
    w("  * No impact model. A marketable order moves the book; nothing here")
    w("    prices that.")
    w()
    w("=" * 78)
    return "\n".join(L)


# ------------------------------------------------------------- self-test ----

def self_test() -> int:
    ok = True
    if abs(pct([1, 2, 3, 4], 50) - 2.5) > 1e-9:
        print("  FAIL pct median"); ok = False
    if abs(pct([10], 90) - 10) > 1e-9:
        print("  FAIL pct single"); ok = False
    print("[self-test] percentiles OK")

    if fmt(-4.08, 8, 2).strip() != "(4.08)":
        print(f"  FAIL brackets: {fmt(-4.08,8,2)!r}"); ok = False
    if fmt(3.6, 8, 2).strip() != "3.60":
        print("  FAIL positive fmt"); ok = False
    print("[self-test] accounting brackets OK")

    # 2026-07-01 13:30Z is 09:30 ET (summer, UTC-4)
    if et_bucket("2026-07-01T13:30:00Z") != "09:30":
        print(f"  FAIL summer ET: {et_bucket('2026-07-01T13:30:00Z')}"); ok = False
    # 2026-01-05 14:30Z is 09:30 ET (winter, UTC-5)
    if et_bucket("2026-01-05T14:30:00Z") != "09:30":
        print(f"  FAIL winter ET: {et_bucket('2026-01-05T14:30:00Z')}"); ok = False
    if et_bucket("2026-07-01T20:00:00Z") != "16:00":
        print("  FAIL close bucket"); ok = False
    print("[self-test] ET bucketing OK (both sides of DST)")

    tmp = Path(tempfile.mkdtemp(prefix="swing_report_selftest_")) / "s.csv"
    try:
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["ts_utc", "symbol", "bid", "ask", "bid_size",
                         "ask_size", "last", "volume", "md_type", "batch"])
            for i in range(40):
                wr.writerow([f"2026-07-01T13:{30+i%20:02d}:00Z", "AAPL",
                             250.00, 250.02, 500, 600, 250.01, 1e6, 1, 0])
            for i in range(40):
                wr.writerow([f"2026-07-01T13:{30+i%20:02d}:00Z", "CLF",
                             12.00, 12.04, 300, 200, 12.02, 5e5, 1, 0])
            wr.writerow(["2026-07-01T13:30:00Z", "XXX", 10, 10.1, 1, 1,
                         10, 1, 3, 0])                       # delayed
            wr.writerow(["2026-07-01T13:30:00Z", "YYY", "", "", "", "",
                         "", "", 1, 0])                      # missing
            wr.writerow(["2026-07-01T13:30:00Z", "ZZZ", 10.5, 10.0, 1, 1,
                         10, 1, 1, 0])                       # crossed

        class A:
            csv = [str(tmp)]
            min_obs = 10
            position_usd = 9000.0
            max_rel = 0.10
            session = "rth"
        rows, rej, total = load([str(tmp)], A.max_rel)
        if total != 83 or len(rows) != 80:
            print(f"  FAIL load counts: total={total} usable={len(rows)}"); ok = False
        if rej.not_live != 1 or rej.missing != 1 or rej.crossed != 1:
            print(f"  FAIL reject split: live={rej.not_live} "
                  f"missing={rej.missing} crossed={rej.crossed}"); ok = False
        print("[self-test] load and reject accounting OK")

        txt = build(rows, rej, total, A)
        for need in ("COVERAGE", "POOLED QUOTED SPREAD", "BY SYMBOL",
                     "BY TIME OF DAY", "ALL-IN ROUND TRIP",
                     "WHAT COULD BE WRONG"):
            if need not in txt:
                print(f"  FAIL report missing section {need}"); ok = False
        # AAPL 2c on 250.01 = 0.80 bps; CLF 4c on 12.02 = 33.3 bps
        if "0.80" not in txt or "33.2" not in txt and "33.3" not in txt:
            print("  FAIL expected bps values absent"); ok = False
        print("[self-test] report builds with expected values OK")
        if not txt.isascii():
            print("  FAIL report is not pure ASCII"); ok = False
        else:
            print("[self-test] report is pure ASCII OK")
    finally:
        tmp.unlink(missing_ok=True)
        tmp.parent.rmdir()

    print("\n[self-test] PASS" if ok else "\n[self-test] FAILED")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Measured spread distribution from spread_sampler.py output")
    ap.add_argument("csv", nargs="*", help="one or more sample CSVs (globs ok)")
    ap.add_argument("--out", default=None,
                    help="also write the report here (plain text, no colour)")
    ap.add_argument("--min-obs", type=int, default=30,
                    help="minimum usable observations before a percentile is "
                         "reported for a symbol or bucket (default 30)")
    ap.add_argument("--position-usd", type=float, default=9000.0,
                    help="target position size for the depth check (default 9000)")
    ap.add_argument("--session", choices=sorted(SESSIONS), default="rth",
                    help="which hours count. rth (default) is 09:30-16:00 ET, "
                         "the hours a swing strategy actually trades; ext is "
                         "04:00-20:00 ET; all is every row.")
    ap.add_argument("--max-rel", type=float, default=0.10,
                    help="reject quotes wider than this fraction of mid as stubs "
                         "(default 0.10)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if not a.csv:
        ap.error("give at least one CSV, or --self-test")

    paths: list[str] = []
    for pat in a.csv:
        hits = glob.glob(pat)
        paths.extend(hits if hits else [pat])
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        sys.exit(f"not found: {missing}")
    a.csv = paths

    rows, rej, total = load(paths, a.max_rel, a.session)
    txt = build(rows, rej, total, a)
    print(txt)
    if a.out:
        Path(a.out).write_text(txt + "\n", encoding="utf-8")
        print(f"\n[written] {Path(a.out).resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # a pager or `head` closed the stream; not an error in this tool
        try:
            sys.stdout.close()
        except Exception:                            # noqa: BLE001
            pass
        raise SystemExit(0)
