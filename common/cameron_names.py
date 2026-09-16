#!/usr/bin/env python3
"""Does his name selection beat our ranking? — item 1c, registered first.

    python -m common.cameron_names --archive E:\\Databento
    python -m common.cameron_names --archive E:\\Databento --coverage-only

REGISTERED BEFORE THIS FILE WAS WRITTEN
----------------------------------------
`docs/research/REGISTERED_cameron_names.md`, commit `f1fa64c`. Read it first.
The arms, thresholds, controls and refusals are fixed there, and the one that
governs every line below is:

    He names the symbol he TRADED, in a recap published after the close. His
    pick is made with the whole session known and ours is made at a tick.

    So HIS names beating OURS is not evidence of anything. Only a NULL closes
    the thread.

This project has already paid for that leak once -- +$4.72/trade on a universe
chosen with the day known against (9.81) on the point-in-time one, and the
$14.53 between them was look-ahead, not edge.

THE PRIMARY TEST HAS NO LOOK-AHEAD IN IT
-----------------------------------------
`best_rank` and `first_rank` in `screen_pairs_pit.json` were computed from the
tape as it stood at each tick. Asking "what rank did OUR screen give the name
he traded" uses nothing from after that tick, so §2 of the registration is the
real experiment and the P/L arms in §4 are a caveated secondary.

Our rank is NOT "volatility", which is what the handover called it. It is
`premarket_change` descending, symbol ascending, capped at `max_symbols`
(`screen_sim.screen_frame`). The report says so, because a reader who believes
they are looking at a volatility ranking will draw a different conclusion from
the same number.

A CLARIFICATION MADE BEFORE RUNNING, NOT AFTER
-----------------------------------------------
The registration's pass criterion -- his mentions reaching `best_rank <= 5` at
a rate 15 points above the control -- did not say which denominator. It matters
and it is not cosmetic:

    over PRESENT mentions      the control is drawn from our universe, so it is
                               present by construction. This is the like-for-
                               like comparison and the criterion is judged here.

    over ALL mentions          deflated by every name our screen never carried.
                               Printed beside it, never compared to the control,
                               because a rate whose denominator includes cases
                               the control cannot have is two numbers that look
                               comparable and are not.

Both are printed. The criterion is judged on the first. This paragraph was
written before the module was run and is committed with it.

THE ABSENT NAMES ARE A RESULT, NOT A SHORTFALL
-----------------------------------------------
A mention our universe does not carry is our screen declining a name he traded.
Dropping those would compute the rank distribution over exactly the names our
screen likes, and then report that our screen likes them. They are counted and
sent through `screen_miss.diagnose` for the clause that kept each one out.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common.report_io import emit

CENSUS = "docs/research/warrior_census_dated.csv"
PAIRS = "var/state/screen_pairs_pit.json"

# Our watchlist cut. The whole question is whether his names land inside it.
TOP_N = 5
# Matched draws for the rank control. Enough that the third decimal of the
# mean is stable; the closed form below is what says the draw is unbiased.
CONTROL_DRAWS = 2000
CONTROL_SEED = 20260916
# The registered pass criterion, AMENDED before the first run: mean rank-AUC.
# The original -- top-5 rate 15 points over the control -- cannot be passed,
# because a random name from our own universe is already inside the top 5
# 93.7% of the time on a median 11-name list. See the amendment in the
# registration. A criterion that cannot pass is a control whose output is
# indistinguishable from the failure it detects.
AUC_MIN = 0.60
# Kept only so the superseded figure can still be printed beside its real
# control, which is the thing that makes it readable rather than misleading.
MARGIN_PP = 15.0
# The census `symbols` cell is free text. This one is a company, not a ticker,
# and is excluded BY NAME and counted rather than silently dropped -- a filter
# that quietly removes what it cannot parse reports a coverage rate over the
# rows it happened to understand.
NOT_A_TICKER = {"SPACEX"}
TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
MAX_BACK = 5


# ---------------------------------------------------------------- mentions
def split_symbols(cell: str) -> list[str]:
    s = (cell or "").strip()
    if not s or s == "?":
        return []
    return [t.strip().upper() for t in re.split(r"[;,/ ]+", s)
            if t.strip() and t.strip() != "?"]


def mentions(census: Path) -> tuple[list[dict], dict]:
    """[{publish_date, symbol, videoId}], and what was thrown away.

    The second return is not diagnostics. It is the part of his corpus this
    module cannot speak for, and it is printed.
    """
    out, dropped = [], Counter()
    for r in csv.DictReader(census.open(encoding="utf-8-sig")):
        if not r.get("publish_date"):
            dropped["no publish date"] += 1
            continue
        for s in split_symbols(r.get("symbols", "")):
            if s in NOT_A_TICKER:
                dropped["not a ticker"] += 1
            elif not TICKER_RE.match(s):
                dropped["unparseable"] += 1
            else:
                out.append({"publish_date": r["publish_date"], "symbol": s,
                            "videoId": r["videoId"]})
    return out, dict(dropped)


def map_to_session(publish: str, sessions: set[str]) -> str | None:
    """The nearest session at or before the publish date.

    The rule validated two ways: against the calendar in
    `tests/docs/test_warrior_census_dates.py` (233 direct hits against 194 at
    a one-day lag) and against the data in `common.regime_labels` (AUC 0.730
    against 0.668). Not a fixed shift -- the residual is a weekend.
    """
    d = dt.date.fromisoformat(publish)
    for back in range(MAX_BACK + 1):
        c = (d - dt.timedelta(days=back)).isoformat()
        if c in sessions:
            return c
    return None


def to_symbol_days(ment: list[dict], sessions: set[str]) -> tuple[list, int, int]:
    """(session, symbol) pairs, de-duplicated.

    He can publish two recaps naming the same symbol on the same session, and
    counting that twice would weight one name by how often he talked about it
    rather than by how often our screen had to find it.
    """
    seen, out, unmapped = set(), [], 0
    for m in ment:
        s = map_to_session(m["publish_date"], sessions)
        if s is None:
            unmapped += 1
            continue
        key = (s, m["symbol"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": s, "symbol": m["symbol"]})
    dupes = len(ment) - unmapped - len(out)
    return sorted(out, key=lambda r: (r["date"], r["symbol"])), unmapped, dupes


# ---------------------------------------------------------------- coverage
def load_pairs(path: Path) -> dict[str, dict[str, dict]]:
    rows = json.loads(Path(path).read_text())
    if not rows:
        sys.exit(f"{path} is empty -- run `python -m common.screen_sim` first")
    by: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by[r["date"]][r["symbol"]] = r
    return dict(by)


def coverage(sym_days: list[dict], pit: dict[str, dict[str, dict]]) -> dict:
    """Presence, and the rank we gave the ones we had.

    `best_rank` and `first_rank` are kept in separate columns and never
    pooled. best_rank is the best the name ever reached; a name that touched
    rank 3 at 09:25 was not on a five-name watchlist at 05:00. Two numbers
    that look comparable and are not is how this project loses an afternoon.
    """
    present, absent = [], []
    for sd in sym_days:
        rec = pit.get(sd["date"], {}).get(sd["symbol"])
        (present if rec else absent).append({**sd, "rec": rec})
    return {
        "n_all": len(sym_days),
        "present": present,
        "absent": absent,
        "best": Counter(p["rec"]["best_rank"] for p in present),
        "first": Counter(p["rec"]["first_rank"] for p in present),
        "top_best": sum(1 for p in present if p["rec"]["best_rank"] <= TOP_N),
        "top_first": sum(1 for p in present if p["rec"]["first_rank"] <= TOP_N),
    }


def rank_auc(rank: int, pool: list[int]) -> float:
    """One name's rank against the REST of its own session's universe.

    The chance it outranks a randomly chosen other name from our list that
    day, ties at a half. 0.500 is no information, exactly and by symmetry --
    which is what makes the control below an exact expectation rather than an
    assumed one.

    A lower rank number is better, so a "win" is another name ranking HIGHER.
    """
    others = [r for r in pool]
    # self appears once in the pool; remove exactly one instance, not all the
    # names that happen to share its rank -- 550 of 551 sessions have ties.
    others.remove(rank)
    if not others:
        return 0.5                      # a one-name session orders nothing
    wins = sum(1 for r in others if r > rank)
    ties = sum(1 for r in others if r == rank)
    return (wins + 0.5 * ties) / len(others)


def pool_ranks(universe: dict, field: str) -> list[int]:
    return [r[field] for r in universe.values()]


def observed_auc(present: list[dict], pit: dict, field: str) -> list[float]:
    """His names' rank-AUCs. One per present mention, never pooled across
    fields -- best_rank and first_rank are different questions."""
    out = []
    for p in present:
        u = pit.get(p["date"])
        if not u:
            continue
        out.append(rank_auc(p["rec"][field], pool_ranks(u, field)))
    return out


def control_top_rate(sym_days: list[dict], pit: dict, field: str) -> float:
    """The share of a session's OWN universe inside the top cut, averaged over
    the matched sessions. The exact expectation of the matched draw.

    Computed from the ranks rather than assumed to be `min(N, n)/n`. That
    closed form needs the ranks to enumerate 1..n within a session and they do
    not: `best_rank` is the best a name ever reached, so 2024-07-02 ranks six
    names 1, 1, 3, 3, 3, 4. The assumed form gives 0.536 against a true 0.937
    and would have raised a wrong-pool alarm on correct data.
    """
    tot, n = 0.0, 0
    for sd in sym_days:
        u = pit.get(sd["date"])
        if not u:
            continue
        ranks = pool_ranks(u, field)
        tot += sum(1 for r in ranks if r <= TOP_N) / len(ranks)
        n += 1
    return 100.0 * tot / n if n else 0.0


def control(sym_days: list[dict], pit: dict, field: str, draws: int,
            seed: int) -> dict:
    """Matched random draws: one name per mention, from THAT session's universe.

    Drawn from the pooled universe instead, the control would inherit the size
    distribution of busy sessions and beat his names on arithmetic alone.

    Returns the mean rank-AUC per draw (the statistic) and the top-cut rate per
    draw (the superseded one, kept so it can be printed with its real control).
    The rank-AUC control has an exact expectation of 0.500 by symmetry, and the
    report checks the draws against it -- a draw that sampled the wrong pool
    would still return a plausible percentage, and nothing else would say so.
    """
    rng = random.Random(seed)
    pools = [(pit[sd["date"]], pool_ranks(pit[sd["date"]], field))
             for sd in sym_days if pit.get(sd["date"])]
    if not pools:
        return {"auc": 0.5, "aucs": [], "top": 0.0, "n": 0}
    aucs, tops = [], []
    for _ in range(draws):
        a, t = [], 0
        for u, ranks in pools:
            r = rng.choice(ranks)
            a.append(rank_auc(r, ranks))
            t += r <= TOP_N
        aucs.append(sum(a) / len(a))
        tops.append(100.0 * t / len(pools))
    return {"auc": sum(aucs) / len(aucs), "aucs": sorted(aucs),
            "top": sum(tops) / len(tops), "n": len(pools)}


def beat_rate(observed: float, rates: list[float]) -> float:
    """How often chance alone reproduces the observed rate. The project's
    permutation form: a number that is not significant should look ordinary
    against its own null, and this says how ordinary."""
    if not rates:
        return 1.0
    return sum(1 for r in rates if r >= observed) / len(rates)


def halves(sym_days: list[dict]) -> tuple[list, list]:
    from common.regime_study import halves_split
    dates = sorted({sd["date"] for sd in sym_days})
    if len(dates) < 2:
        return sym_days, []
    cut = halves_split(dates)
    return ([sd for sd in sym_days if sd["date"] < cut],
            [sd for sd in sym_days if sd["date"] >= cut])


def top_rate(cov: dict, key: str = "top_best") -> float:
    """Over PRESENT mentions -- the denominator the control can match. See the
    clarification in the module docstring."""
    return 100.0 * cov[key] / len(cov["present"]) if cov["present"] else 0.0


# ---------------------------------------------------------------- the arms
def arm_universes(sym_days, pit, present_only=True):
    """Per session: the HIS universe and the OURS universe, as `pit_h0.run_day`
    takes them.

    Both arms are the SAME pair records off the SAME file, subset two ways. A
    name cannot be ranked from one tape here and scored on another, because
    there is only one tape in the function.
    """
    his: dict[str, list[dict]] = defaultdict(list)
    for sd in sym_days:
        rec = pit.get(sd["date"], {}).get(sd["symbol"])
        if rec is not None:
            his[sd["date"]].append(rec)
        elif not present_only:
            continue
    ours: dict[str, list[dict]] = {}
    for day in his:
        ours[day] = [r for r in pit.get(day, {}).values()
                     if r["best_rank"] <= TOP_N]
    return dict(his), ours


def pnl_arms(his_u, ours_u, slices, trail):
    """H0 on both arms, session by session, reading each slice ONCE.

    `run_day` is `pit_h0`'s, not a second copy: the entry floor, the exit and
    the share size all come from the module that produced every other H0 figure
    in this project, so these numbers sit on the same axis as those.
    """
    from common.dbn_io import read_dbn
    from common.pit_h0 import run_day

    got = {"HIS": [], "OURS": []}
    unread = []
    for day in sorted(his_u):
        path = slices.get(day)
        if path is None:
            unread.append(day)
            continue
        try:
            bars = read_dbn(Path(path))
        except Exception as e:                              # noqa: BLE001
            unread.append(f"{day} ({type(e).__name__})")
            continue
        if bars.empty:
            unread.append(f"{day} (empty)")
            continue
        got["HIS"] += run_day(bars, day, his_u[day],
                              as_screened=True, trail=trail)
        got["OURS"] += run_day(bars, day, ours_u.get(day, []),
                               as_screened=True, trail=trail)
    return got, unread


def diagnose_absent(absent, slices, daily, cadence):
    """Which clause kept each declined name out, via `screen_miss.diagnose`.

    Not re-implemented here. The clause test is the simultaneous tick-by-tick
    one, and a second version of it written for this report would eventually
    disagree with the screen it claims to describe.
    """
    from common.dbn_io import read_dbn
    from common.screen_sim import ScreenConfig, accumulate
    from common.screen_miss import diagnose, NOT_ON_TAPE
    from common.screen_sim import prior_closes, load_repaired

    cfg = ScreenConfig()
    rep = load_repaired()
    pc = prior_closes(daily, rep)
    by_date = {d: g.set_index("symbol")["prior_close"]
               for d, g in pc.groupby("date")}
    want: dict[str, list[str]] = defaultdict(list)
    for a in absent:
        want[a["date"]].append(a["symbol"])

    causes = Counter()
    for day, names in sorted(want.items()):
        path = slices.get(day)
        if path is None:
            causes[NOT_ON_TAPE] += len(names)
            continue
        bars = read_dbn(Path(path))
        acc = accumulate(bars, cfg)
        prior = by_date.get(day)
        d_et = dt.date.fromisoformat(day)
        for s in names:
            pv = None if prior is None else prior.get(s)
            causes[diagnose(acc, s, pv, d_et, cfg, cadence)["why"]] += 1
    return causes


# ---------------------------------------------------------------- report
def render(cov, ctrl, aucs, auc_e, auc_l, ctrl_e, ctrl_l, dropped, unmapped,
           dupes, causes, pnl, n_sessions, elapsed) -> list[str]:
    from common.pit_h0 import DROP, FRICTIONS, score, halves_split

    pres = len(cov["present"])
    obs = top_rate(cov)
    L = ["DOES HIS NAME SELECTION BEAT OUR RANKING?", "",
         "  Registered in docs/research/REGISTERED_cameron_names.md,",
         "  commit f1fa64c, BEFORE this module was written.", "",
         f"  {cov['n_all']:,} de-duplicated (session, symbol) pairs "
         f"across {n_sessions} sessions",
         f"  {unmapped} mentions mapped to no session in our universe",
         f"  {dupes} duplicate mentions of the same symbol-day, counted once",
         f"  elapsed {elapsed:.1f}s"]
    for k, v in sorted(dropped.items()):
        L.append(f"  {v} census entries excluded: {k}")
    L += ["",
          "  THE READING IS REGISTERED AND ONE-DIRECTIONAL. He names the symbol",
          "  he TRADED, after the close. His names beating ours is the expected",
          "  outcome of a post-hoc pick and settles nothing. Only a null closes",
          "  item 1c.", ""]

    L += ["1. COVERAGE -- did our screen carry the name at all?", "",
          "  No look-ahead in this section. Rank was computed from the tape as",
          "  it stood at each tick.", "",
          f"  in our universe on the day   {pres:>5,} of {cov['n_all']:,}"
          f"   ({100.0 * pres / cov['n_all'] if cov['n_all'] else 0:.1f}%)",
          f"  our screen declined          {len(cov['absent']):>5,}", ""]

    L += ["2. THE RANK WE GAVE THEM", "",
          "  Our rank is premarket_change descending, symbol ascending, capped",
          "  at max_symbols. NOT volatility, whatever the handover called it.",
          "",
          "  best_rank is the best the name ever reached; first_rank is what it",
          "  was when we first saw it. A name that touched rank 3 at 09:25 was",
          "  not on a five-name watchlist at 05:00, so they are never pooled.",
          ""]
    if not pres:
        L += ["  REFUSED: our universe carried none of his names.", ""]
    else:
        hi = max(max(cov["best"], default=0), max(cov["first"], default=0))
        L += ["  rank    best_rank   first_rank", ""]
        for r in range(1, hi + 1):
            mark = "  <- top" if r <= TOP_N else ""
            L.append(f"  {r:>4}    {cov['best'].get(r, 0):>9}   "
                     f"{cov['first'].get(r, 0):>10}{mark}")
        L += ["",
              f"  reached top {TOP_N} (best_rank)    {cov['top_best']:>5} of "
              f"{pres}   {obs:.1f}%",
              f"  top {TOP_N} when first seen        {cov['top_first']:>5} of "
              f"{pres}   {top_rate(cov, 'top_first'):.1f}%",
              f"  a random name from OUR OWN list   "
              f"{ctrl['top']:.1f}%   <- why these three lines settle nothing",
              "",
              "  The top-5 rate was the registered criterion and it was AMENDED",
              "  before this ran. The median session carries 11 names and almost",
              "  all of them touch the top 5 at some tick, so the measure cannot",
              "  discriminate at any threshold. It is printed with its control",
              "  rather than removed, because the superseded figure is the one a",
              "  reader is most likely to have in their head.",
              "",
              f"  over ALL {cov['n_all']:,} mentions   "
              f"{100.0 * cov['top_best'] / cov['n_all'] if cov['n_all'] else 0:.1f}%"
              "  -- a third denominator, listed and", "  not compared to anything.",
              ""]

    L += ["3. THE TEST -- WHERE HIS NAMES SIT IN OUR OWN ORDERING", "",
          "  For each of his names, the chance it outranks a randomly chosen",
          "  OTHER name from our list that day, ties at a half. Immune to where",
          "  a cut falls and to how many names a session carries.", "",
          f"  0.500 is no information. The registered bar is {AUC_MIN:.2f}, and",
          "  it is deliberately low: only a null closes this thread, so a",
          "  generous bar makes the closure worth more.", ""]
    if not aucs or not ctrl["aucs"]:
        L += ["  REFUSED: nothing to order.", ""]
    else:
        mean = sum(aucs) / len(aucs)
        lo = ctrl["aucs"][len(ctrl["aucs"]) // 40]
        hi_ = ctrl["aucs"][-max(1, len(ctrl["aucs"]) // 40)]
        drift = abs(ctrl["auc"] - 0.5)
        L += [f"  his names        rank-AUC {mean:.3f}   (n={len(aucs)})",
              f"  random draw      rank-AUC {ctrl['auc']:.3f}   "
              f"(90% of draws {lo:.3f}-{hi_:.3f})",
              f"  exact form       rank-AUC 0.500   by symmetry",
              f"  draw vs form     {drift:.3f}   "
              + ("OK" if drift < 0.02 else
                 "*** THE DRAW DOES NOT MATCH ITS OWN EXPECTATION -- "
                 "the control is sampling the wrong pool ***"),
              "",
              f"  chance alone reaches his figure "
              f"{beat_rate(mean, ctrl['aucs']):.1%} of the time", ""]
        if mean >= AUC_MIN:
            L += [f"  *** PASSES the registered {AUC_MIN:.2f} bar. ***", "",
                  "  Note what this does NOT say: that his names are better.",
                  "  It says OUR ranking already puts them near the top, which",
                  "  is an argument that our LIST is not the problem.", ""]
        else:
            L += [f"  DOES NOT pass the registered {AUC_MIN:.2f} bar.", "",
                  "  On the registered reading our ranking orders his names no",
                  "  better than a draw from our own list, and item 1c is",
                  "  CLOSED: name selection is not where the gap is.", ""]

    L += ["4. BOTH HALVES", ""]
    for name, a, k in (("early", auc_e, ctrl_e), ("late", auc_l, ctrl_l)):
        if not a:
            L.append(f"  {name:<6} REFUSED: no present mentions")
        else:
            m = sum(a) / len(a)
            L.append(f"  {name:<6} rank-AUC {m:.3f}   random {k['auc']:.3f}   "
                     f"(n={len(a)})   "
                     + ("passes" if m >= AUC_MIN else "does not pass"))
    if auc_e and auc_l:
        me, ml = sum(auc_e) / len(auc_e), sum(auc_l) / len(auc_l)
        if (me >= AUC_MIN) != (ml >= AUC_MIN):
            L += ["", "  *** THE HALVES DISAGREE about the bar. "
                  "No verdict. ***"]
        elif (me > 0.5) != (ml > 0.5):
            L += ["", "  *** THE HALVES DISAGREE in direction. No verdict. ***"]
        else:
            L += ["", "  the halves agree."]
    else:
        L += ["", "  one half cannot carry the comparison. UNCONFIRMED."]
    L.append("")

    if causes is not None:
        L += ["5. WHY WE DECLINED THE REST", "",
              "  Our screen's own clauses, tested simultaneously tick by tick,",
              "  via screen_miss.diagnose. These are not missing rows -- they",
              "  are our screen turning down a name he traded.", ""]
        tot = sum(causes.values()) or 1
        for why, n in causes.most_common():
            L.append(f"  {why:<22} {n:>5}   {100.0 * n / tot:5.1f}%")
        L.append("")

    if pnl is not None:
        L += ["6. THE CONTAMINATED ARM  (read section 1 before this table)", "",
              "  Same rule both arms: enter at max(04:30, first_seen), hold to",
              "  the regular close, 100 shares, via pit_h0.run_day.", ""]
        dates = [t["date"] for arm in pnl.values() for t in arm]
        split = halves_split(dates)
        for label, fr in FRICTIONS:
            L.append(f"  friction {label}")
            L.append(f"    {'arm':<6}{'n':>7}{'net':>12}{'per':>9}"
                     f"{'win%':>8}{'drop-top-' + str(DROP):>12}"
                     f"{'early':>9}{'late':>9}")
            for arm in ("HIS", "OURS"):
                s = score(pnl[arm], split, fr)
                drop = ("n/a" if s["syms"] <= DROP else f"{s['dropped']:,.0f}")
                L.append(f"    {arm:<6}{s['n']:>7,}{s['net']:>12,.0f}"
                         f"{s['per']:>9.2f}{s['win']:>8.1f}{drop:>12}"
                         f"{s['early']:>9.2f}{s['late']:>9.2f}")
            L.append("")
        L += ["  The per-symbol-day denominator is the `n` column divided by",
              "  the distinct symbols in each arm; the two denominators are",
              "  printed rather than reconciled, and a disagreement between",
              "  them is a refusal, not a result.", "",
              "  AND: whatever this table says, his arm was picked after the",
              "  close. Section 3 is the registered reading.", ""]

    L += ["WHAT THIS CANNOT SETTLE", "",
          "  Nothing here uses his P/L, which is self-reported on a channel",
          "  that sells a course. It measures whether our screen's ordering",
          "  finds the names he names -- not whether his entries were good,",
          "  which is entry_place's question.",
          "",
          "  var/state/holdout.json is untouched and remains unspent."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--census", default=CENSUS)
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC")
    p.add_argument("--draws", type=int, default=CONTROL_DRAWS)
    p.add_argument("--seed", type=int, default=CONTROL_SEED)
    p.add_argument("--coverage-only", action="store_true",
                   help="skip the clause diagnosis and the P/L arms, which "
                        "are the parts that read the bar slices")
    p.add_argument("--out", default="var/reports/cameron_names.txt")
    return p


def main(argv=None) -> int:
    import time

    a = build_parser().parse_args(argv)
    t0 = time.time()
    census = Path(a.census)
    if not census.exists():
        sys.exit(f"no census at {census}. It is in git -- check the merge.")
    pairs = Path(a.pairs)
    if not pairs.exists():
        sys.exit(f"no point-in-time universe at {pairs}. Build it with "
                 "`python -m common.screen_sim`.")

    pit = load_pairs(pairs)
    sessions = set(pit)
    ment, dropped = mentions(census)
    sym_days, unmapped, dupes = to_symbol_days(ment, sessions)
    if not sym_days:
        sys.exit("no mention maps to a session in the universe -- nothing to "
                 "measure. Check that the census and the universe cover the "
                 "same dates.")

    cov = coverage(sym_days, pit)
    # best_rank throughout: it is the field the registration names, and the
    # amendment changed the STATISTIC, not which column it reads.
    FIELD = "best_rank"
    ctrl = control(sym_days, pit, FIELD, a.draws, a.seed)
    aucs = observed_auc(cov["present"], pit, FIELD)
    e_days, l_days = halves(sym_days)
    early, late = coverage(e_days, pit), coverage(l_days, pit)
    auc_e = observed_auc(early["present"], pit, FIELD)
    auc_l = observed_auc(late["present"], pit, FIELD)
    # A separate seed per half, or both halves draw the same sequence and
    # "the halves agree" would be partly an artefact of the random stream.
    ctrl_e = control(e_days, pit, FIELD, a.draws, a.seed + 1)
    ctrl_l = control(l_days, pit, FIELD, a.draws, a.seed + 2)

    causes, pnl = None, None
    if not a.coverage_only:
        from common.databento_fetch import default_archive
        from common.dbn_io import daily_frame
        from common.screen_sim import window_slices, date_of
        from strategy.premkt import hypotheses as H

        archive = Path(a.archive) if a.archive else default_archive()
        slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
        print(f"  {len(slices):,} window slices; diagnosing "
              f"{len(cov['absent']):,} declined names", flush=True)
        daily = daily_frame(archive, a.daily_dataset)
        causes = diagnose_absent(cov["absent"], slices, daily, 60)
        his_u, ours_u = arm_universes(sym_days, pit)
        print(f"  scoring both arms over {len(his_u):,} sessions", flush=True)
        got, unread = pnl_arms(his_u, ours_u, slices, H.TRAIL_PRIMARY)
        if unread:
            print(f"  {len(unread)} session(s) unread: {unread[:5]}", flush=True)
        pnl = got

    text = render(cov, ctrl, aucs, auc_e, auc_l, ctrl_e, ctrl_l, dropped,
                  unmapped, dupes, causes, pnl,
                  len({sd["date"] for sd in sym_days}), time.time() - t0)
    emit("\n".join(text), a.out,
         header=f"common.cameron_names  census={census.name} "
                f"seed={a.seed} draws={a.draws}"
                + ("  COVERAGE ONLY" if a.coverage_only else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
