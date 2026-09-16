#!/usr/bin/env python3
"""Does our regime reading agree with 277 days a human labelled?

    python -m common.regime_labels --archive E:\\Databento --dataset XNAS.BASIC

THE FIRST EXTERNAL VALIDATION AVAILABLE FOR ANYTHING IN THIS PROJECT
---------------------------------------------------------------------
`common/regime.py` reads hot / mixed / cold off the daily archive, unsupervised
-- terciles of a rank composite over movers, leading gainer and round-trip
rate. It has never been compared to anything outside itself.

`docs/research/warrior_census_dated.csv` now carries 277 sessions Ross Cameron
labelled hot / mixed / cold in his own recaps, dated 2026-09-16 by recovering
every video's publish date. Those labels were made by someone watching the same
tape, with no knowledge of this project, years before it existed.

So for once there is a right answer to check against.

WHY HIS LABELS AND NOT HIS P/L
------------------------------
The census fixed SELECTION bias -- a 35-video pass had `back_side` as a
top-four failure mode and it censuses at 1.1x across all 317 recaps -- but it
could not fix SOURCE bias, on a channel that sells a course. His P/L is
self-reported and cannot be audited.

**The regime label is a claim about the TAPE**, and the tape is in the archive.
That is the half that can be checked, so it is the only half used here.

THE TEST IS NOT THREE-WAY AGREEMENT, AND THAT MATTERS
------------------------------------------------------
`regime.classify` cuts TERCILES, so it is one-third hot by construction. His
sample is 61% cold. Two classifiers with different marginals disagree heavily
even when they measure the same thing perfectly, so a raw agreement rate would
understate the match and a kappa would be dominated by the marginal mismatch.

So the headline is a RANK COMPARISON, which has no buckets in it at all:

    on the days HE called hot, where does OUR composite sit?
    on the days HE called cold, where does OUR composite sit?

If the two are measuring the same thing, his hot days carry a higher composite
than his cold days. That is a statement about ordering and it is immune to
where either side draws its lines. The three-way table is printed underneath
because it is what a reader will want, not because it is the test.

THE MAPPING IS TESTED, NOT ASSUMED
-----------------------------------
A recap is published on the session it describes -- 233 of 277 land directly on
an archive session, against 194 at a one-day lag -- with a weekend tail that
maps back to the Friday. That was measured against the session calendar in
`tests/docs/test_warrior_census_dates.py`.

This module re-tests it a second way, against the DATA rather than the
calendar: the separation is computed at offset 0 and at offset -1, and if the
lag separates better then the mapping is wrong and the headline is void. A
mapping that only ever agrees with itself is not checked.

BOTH HALVES, AS EVERYWHERE ELSE
--------------------------------
Split by date, derived from the labelled set. A separation that holds on one
half and not the other is noise, and this module says so rather than pooling.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

from common.report_io import emit

CENSUS = "docs/research/warrior_census_dated.csv"
LABELS = ("hot", "mixed", "cold")
# Below this the halves cannot carry a comparison and the module refuses a
# verdict rather than printing one on a handful of days per side.
MIN_PER_SIDE = 15
# How far the lagged mapping has to beat offset 0 before it is evidence the
# mapping is wrong rather than noise. Without a margin a 0.001 lead prints a
# catastrophic verdict on a coin flip -- and regimes persist, so the lagged
# mapping separates SOMEWHAT no matter which day is the right one.
LAG_MARGIN = 0.02


def load_labels(path: Path) -> list[tuple[str, str]]:
    """[(publish_date, label)] for the rows a human actually labelled.

    Rows whose `market` is "?" are DROPPED here and counted by the caller.
    They are not evidence of anything -- he simply did not say -- and a
    default would invent 124 opinions.
    """
    out = []
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        if r.get("market") in LABELS and r.get("publish_date"):
            out.append((r["publish_date"], r["market"]))
    return out


def map_to_session(publish: str, sessions: set[str], offset: int = 0,
                   max_back: int = 5) -> str | None:
    """The session a recap describes: the nearest one at or before
    `publish + offset`.

    NOT a fixed shift. He publishes on the session day, and the residual is a
    weekend -- a Friday session written up on Sunday. A constant -2 would be
    right for those and wrong for the 233 that are not.
    """
    d = dt.date.fromisoformat(publish) + dt.timedelta(days=offset)
    for back in range(max_back + 1):
        c = (d - dt.timedelta(days=back)).isoformat()
        if c in sessions:
            return c
    return None


def composite(feats: dict) -> dict[str, float]:
    """Each session's percentile on the SAME composite `classify` cuts.

    `regime.composite` IS that construction -- it was extracted out of
    `classify` for this caller rather than copied into it, so there is exactly
    one definition of the scale and the classifier and this module move
    together when it changes. A copy here would agree with itself forever, and
    an agreement with a copy of the thing under test is not evidence about the
    thing under test.

    Days too thin to rate get 0.0 -- the coldest reading available, and the
    same decision `classify` makes when it calls them cold. Dropping them
    would remove the coldest days from a cold sample and then report that cold
    days are rare.
    """
    from common import regime as RG

    out = {d: 0.0 for d, f in feats.items() if not f.usable}
    out.update(RG.composite(feats))
    return out


def separation(pairs: list[tuple[str, str]], comp: dict[str, float]) -> dict:
    """Median composite on his HOT days against his COLD days.

    The whole test, and it has no buckets in it. Returns None counts rather
    than a verdict when a side is too thin -- see MIN_PER_SIDE.
    """
    import statistics as st

    hot = [comp[d] for d, lab in pairs if lab == "hot" and d in comp]
    cold = [comp[d] for d, lab in pairs if lab == "cold" and d in comp]
    mixed = [comp[d] for d, lab in pairs if lab == "mixed" and d in comp]
    if not hot or not cold:
        return {"n_hot": len(hot), "n_cold": len(cold), "n_mixed": len(mixed),
                "gap": None, "hot": None, "cold": None, "mixed": None,
                "auc": None}
    # AUC: the chance a randomly chosen hot day outranks a randomly chosen
    # cold one. 0.50 is no information. Reported because a gap in medians says
    # nothing about overlap and this does.
    wins = sum(1 for h in hot for c in cold if h > c)
    ties = sum(1 for h in hot for c in cold if h == c)
    auc = (wins + 0.5 * ties) / (len(hot) * len(cold))
    return {"n_hot": len(hot), "n_cold": len(cold), "n_mixed": len(mixed),
            "hot": st.median(hot), "cold": st.median(cold),
            "mixed": st.median(mixed) if mixed else None,
            "gap": st.median(hot) - st.median(cold), "auc": auc}


def usable_half(s: dict) -> bool:
    """Whether a half is thick enough to be read at all.

    ONE predicate, because the printed line and the agree/disagree verdict
    have to mean the same thing by it. When they were written separately the
    report could print "early REFUSED" and then declare the halves in
    agreement on the strength of it -- a verdict resting on a number the same
    page had just declined to report.
    """
    return (s["gap"] is not None
            and min(s["n_hot"], s["n_cold"]) >= MIN_PER_SIDE)


def confusion(pairs: list[tuple[str, str]],
              ours: dict[str, str]) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for d, his in pairs:
        mine = ours.get(d)
        if mine is None:
            continue
        out[(his, mine)] = out.get((his, mine), 0) + 1
    return out


def halves(pairs: list[tuple[str, str]]) -> tuple[list, list]:
    """Early and late, split at the median LABELLED date.

    `regime_study.halves_split` is the cut used everywhere else in this
    project and is called rather than restated, so a change to how the split
    is derived reaches this module too instead of leaving it on an older rule
    that still looks like the current one.
    """
    from common.regime_study import halves_split

    dates = sorted({d for d, _ in pairs})
    if len(dates) < 2:
        return pairs, []
    cut = halves_split(dates)
    return ([p for p in pairs if p[0] < cut],
            [p for p in pairs if p[0] >= cut])


def render(mapped, unmapped, n_unlabelled, ours, sep, sep_lag,
           early, late, sessions, elapsed) -> list[str]:
    L = ["DOES OUR REGIME READING AGREE WITH A HUMAN'S?", "",
         f"  {len(mapped)} labelled recaps mapped to sessions "
         f"({unmapped} could not be)",
         f"  {n_unlabelled} census rows carry no label and are not counted",
         f"  {len(sessions):,} sessions in the daily archive",
         f"  elapsed {elapsed:.1f}s", "",
         "  His labels came from watching the same tape, with no knowledge of",
         "  this project. Nothing else here has an external answer to check",
         "  against.", ""]

    L += ["THE TEST: WHERE DO HIS DAYS SIT ON OUR COMPOSITE?", "",
          "  Not three-way agreement. `classify` cuts TERCILES, so it is a",
          "  third hot by construction, and his sample is 61% cold -- two",
          "  classifiers with different marginals disagree heavily even when",
          "  they measure the same thing. This compares ORDERING, which has",
          "  no buckets in it.", ""]
    if sep["gap"] is None:
        L += ["  REFUSED: one side has no mapped days.", ""]
    else:
        L += [f"  his HOT days   n={sep['n_hot']:>3}   our composite median "
              f"{sep['hot']:.3f}",
              f"  his MIXED days n={sep['n_mixed']:>3}   "
              + (f"our composite median {sep['mixed']:.3f}"
                 if sep["mixed"] is not None else "none mapped"),
              f"  his COLD days  n={sep['n_cold']:>3}   our composite median "
              f"{sep['cold']:.3f}",
              "",
              f"  gap  {sep['gap']:+.3f}",
              f"  AUC  {sep['auc']:.3f}   "
              "(the chance a random hot day outranks a random cold one; "
              "0.500 is no information)", ""]

    L += ["THE MAPPING, CHECKED AGAINST THE DATA AND NOT ONLY THE CALENDAR",
          "", "  A recap is taken to describe the nearest session at or before",
          "  its publish date. If a one-day lag separated BETTER, that rule is",
          "  wrong and everything above is void.", ""]
    if sep_lag["gap"] is None or sep["auc"] is None:
        L += ["  the lagged mapping has no usable side", ""]
    else:
        L += [f"  offset  0   gap {sep['gap']:+.3f}   AUC {sep['auc']:.3f}",
              f"  offset -1   gap {sep_lag['gap']:+.3f}   "
              f"AUC {sep_lag['auc']:.3f}", ""]
        margin = sep_lag["auc"] - sep["auc"]
        if margin > LAG_MARGIN:
            L += [f"  *** THE LAG SEPARATES BETTER, by {margin:.3f}. The "
                  "mapping is wrong", "  and no conclusion above stands. ***",
                  ""]
        elif margin > 0:
            L += [f"  offset -1 is ahead by {margin:.3f}, inside the "
                  f"{LAG_MARGIN:.2f} margin where these two",
                  "  cannot be told apart. The calendar breaks the tie and it "
                  "said offset 0", "  (233 direct hits against 194).", ""]
        else:
            L += ["  offset 0 separates at least as well, as the calendar "
                  "said.", ""]
        L += ["  Neither is a clean test on its own: regimes persist, so "
              "yesterday's",
              "  reading resembles today's and the lag will separate somewhat "
              "whatever",
              "  the mapping is. `regime_study` prints that autocorrelation, "
              "which is the",
              "  floor this comparison sits on.", ""]

    L += ["BOTH HALVES", "",
          "  Split by date from the labelled set. A separation on one half and",
          "  not the other is noise.", ""]
    for name, s in (("early", early), ("late", late)):
        if not usable_half(s):
            L.append(f"  {name:<6} REFUSED: hot n={s['n_hot']}, "
                     f"cold n={s['n_cold']} -- under {MIN_PER_SIDE} a side")
        else:
            L.append(f"  {name:<6} gap {s['gap']:+.3f}  AUC {s['auc']:.3f}  "
                     f"(hot {s['n_hot']}, cold {s['n_cold']})")
    if usable_half(early) and usable_half(late):
        if (early["gap"] > 0) == (late["gap"] > 0):
            L += ["", "  the halves AGREE in direction."]
        else:
            L += ["", "  *** THE HALVES DISAGREE. No verdict, whatever the "
                  "pooled number. ***"]
    else:
        L += ["", "  one half cannot carry the comparison, so the halves say "
              "nothing either",
              "  way. The pooled figure above is UNCONFIRMED."]
    L.append("")

    L += ["THE THREE-WAY TABLE  (what a reader wants, not the test)", "",
          "  " + "his \\ ours".ljust(14)
          + "".join(f"{m:>8}" for m in LABELS), ""]
    cm = confusion(mapped, ours)
    for his in LABELS:
        row = "".join(f"{cm.get((his, m), 0):>8}" for m in LABELS)
        L.append(f"  {his:<14}{row}")
    tot = sum(cm.values())
    same = sum(v for (a, b), v in cm.items() if a == b)
    L += ["", f"  raw agreement {same}/{tot} = "
              f"{(same / tot * 100 if tot else 0):.0f}%",
          "  and it is depressed by the marginals -- see the header. Read the",
          "  AUC above instead.", ""]

    L += ["WHAT A RESULT HERE WOULD MEAN", "",
          "  AUC well above 0.5   our unsupervised reading tracks a human's,",
          "                       and the regime gate can be built on it.",
          "  AUC near 0.5         it does not, and the 277 labels become a",
          "                       SUPERVISED TARGET instead -- the candidate",
          "                       inputs are listed in execution_gap_20260910",
          "                       section 5.",
          "  halves disagreeing   no verdict, whatever the pooled number.",
          "",
          "  NONE OF THESE licenses trading on it. A same-day label cannot be",
          "  acted on at 04:00; only `regime.lagged` is a gate, and its",
          "  ceiling is the label's day-to-day autocorrelation, which",
          "  regime_study prints separately.",
          "",
          "  And nothing here uses his P/L. The label is a claim about the",
          "  tape and is checkable; his earnings are self-reported on a",
          "  channel that sells a course."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--census", default=CENSUS)
    p.add_argument("--archive", default=None,
                   help="the Databento archive holding ohlcv-1d")
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--out", default="var/reports/regime_labels.txt")
    return p


def main(argv=None) -> int:
    import time

    from common import regime as RG
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame
    from common.regime_study import check_universe

    a = build_parser().parse_args(argv)
    t0 = time.time()
    census = Path(a.census)
    if not census.exists():
        sys.exit(f"no census at {census}. It is in git -- check the merge.")
    rows = list(csv.DictReader(census.open(encoding="utf-8-sig")))
    pairs_raw = load_labels(census)
    n_unlabelled = len(rows) - len(pairs_raw)

    archive = Path(a.archive) if a.archive else default_archive()
    daily = daily_frame(archive, a.dataset)
    _, refusal = check_universe(daily)
    if refusal:
        sys.exit("REFUSING TO RUN\n\n"
                 f"  {refusal}.\n\n"
                 "  A regime is a property of the market. Point --archive at a\n"
                 "  daily archive covering it, not at bar_cache.\n")

    feats = RG.series(daily)
    sessions = set(feats)
    ours = RG.classify(feats)
    comp = composite(feats)

    def mapped_at(off):
        out, lost = [], 0
        for pub, lab in pairs_raw:
            s = map_to_session(pub, sessions, off)
            if s is None:
                lost += 1
            else:
                out.append((s, lab))
        return out, lost

    mapped, unmapped = mapped_at(0)
    lagged_map, _ = mapped_at(-1)

    sep = separation(mapped, comp)
    sep_lag = separation(lagged_map, comp)
    e, l = halves(mapped)
    text = render(mapped, unmapped, n_unlabelled, ours, sep, sep_lag,
                  separation(e, comp), separation(l, comp), sessions,
                  time.time() - t0)
    emit("\n".join(text), a.out,
         header=f"common.regime_labels  census={census.name} "
                f"dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
