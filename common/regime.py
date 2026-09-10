#!/usr/bin/env python3
"""Market regime — hot / mixed / cold — from the daily archive.

    from common.regime import day_features, series, lagged, classify

WHY THIS OUTRANKS EVERY ENTRY RULE IN THE PROJECT
--------------------------------------------------
`warrior_census_20260910.md` §4, over 234 recaps he labelled himself:

    | his label | n   | green rate | mean day  | median trades | no-trade days |
    | hot       |  53 |      94.3% |  $46,481  |             4 |             0 |
    | mixed     |  38 |      97.2% |  $24,172  |             2 |             2 |
    | cold      | 143 |      76.9% |   $2,835  |             2 |            22 |

**16x on the mean day, and cold is 61% of the sample.** His win rate barely
moves -- 94% to 77% -- so this is not a rule that makes him wrong more often.
It is the size of the win collapsing. Nothing else measured in this project
moves an outcome 16-fold, and a strategy validated on the hot 23% is not
validated.

WHERE THE FEATURES COME FROM
----------------------------
`execution_gap_20260910.md` §5 lists what he says he watches, and every item is
computable from daily bars:

    count of stocks up >100% on the day
    magnitude of the leading gainer   (58% = cold, 300-500% = hot)
    round-trip rate                    -- top gappers giving the move back
    float of the leaders               (a 160M-float leader is a cold tell)
    share of movers under $1 vs $2-20

Four of those five are in here. **Float is not**, because the daily archive
does not carry it, and a float proxy invented here would be a fifth feature
whose only property is that it exists.

THE TWO THINGS THAT DECIDE WHETHER THIS IS HONEST
--------------------------------------------------
**1. THE UNIVERSE MUST BE THE MARKET, NOT OUR TRADES.**

`bar_cache/` holds 375 symbol-days over 91 sessions, and its universe is
`var/state/traded_pairs.json` -- **the symbol-days Ben actually traded**, a
median of 3 names a day. Computing "count of >100% gainers" over that is not a
thin version of the market measure. It is a measure of BEN: the census already
established that his trade count tracks his outcome (his worst month is one of
his highest-count months, in the best conditions of the sample). A regime gate
fitted to it would rediscover his own overtrading and label it weather.

So this module takes a MARKET-WIDE daily frame -- `dbn_io.daily_frame`, the
same archive `prior_spike` uses -- and `regime_study.py` refuses to run without
one. That refusal is the point. A study that cheerfully ran on bar_cache and
printed a regime table would be this project's recurring defect exactly: a
control whose output is indistinguishable from the failure it detects.

**2. THE GATE MUST NOT KNOW TODAY.**

You decide at 04:00 whether to trade. You cannot know at 04:00 how many stocks
will close up 100% today. So a same-day regime split is not a gate -- it is a
description of days that were already good, and it will look spectacular for
that reason alone.

`lagged()` is therefore the ONLY actionable form, and `regime_study` leads with
it. The same-day split is computed too, and reported as a CEILING: the most
this feature set could ever be worth if you had tomorrow's paper. If the lagged
form is worth nothing and the same-day form is worth a lot, the finding is
"regime is real and not predictable from yesterday", which is a different and
much less useful sentence than "the gate works".

The persistence measure (`autocorr`) is what says whether the lag can work at
all, and it is printed before either verdict. Cameron's own claim is that it
can, and that it is asymmetric: *"the shift from hot to cold is much more
subtle than the shift from cold back to hot."* That argues for a slow entry
into cold and a fast exit out of it -- an asymmetric smoother with two
constants. **Not implemented**: it is two fitted parameters, and the base case
has to be measured before there is anything for them to improve.

WHAT THE THRESHOLDS ARE, AND WHY THEY ARE NOT HIS
--------------------------------------------------
His 58%-is-cold / 300%-is-hot numbers are labels on his market in his years,
read off recaps. Importing them as constants would be borrowing a fit. The
buckets here are **terciles of the score over the sessions scored** -- a
ranking, not a fitted parameter, so there is nothing to sweep. What that costs
is transferability: "hot" here means the top third of OUR sample, and if the
whole sample is cold by his account then our "hot" is his "less cold". The
study says so rather than quoting his table as though the labels matched.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy.mcl.mcl import PRICE_MAX, PRICE_MIN

# The move that counts as a "mover" for the breadth measure. Below the >100%
# headline on purpose: a count of names doubling is 0 or 1 on most sessions
# even market-wide, and a feature that is almost always zero cannot rank days.
# The >100% count is kept as its own field because it is the number he states.
MOVER_MIN = 0.30
BIG_MIN = 1.00

# Retained less than this share of the day's peak move = a round trip. Half is
# the same boundary as the hold-50% rule in `warrior_5_selection_in_practice`
# §1, applied market-wide instead of per-name -- deliberately the same number,
# so this is one idea measured at two scales and not two thresholds.
RETAIN_MIN = 0.50

# Below this many qualifying names, the day's rates are noise. A round-trip
# rate over 2 names is 0%, 50% or 100% and would swing the score by itself.
MIN_NAMES = 5

# The bands the strategy actually trades. A regime measured over $200 megacaps
# would be a different market from the one MCL operates in.
BAND = (PRICE_MIN, PRICE_MAX)


@dataclass(frozen=True)
class DayFeatures:
    date: str
    n_names: int          # names in band with a prior close
    n_movers: int         # gained >= MOVER_MIN intraday from prior close
    n_big: int            # gained >= BIG_MIN -- the number he states
    lead: float           # the leading gainer's intraday move, as a fraction
    round_trip: float     # share of movers retaining < RETAIN_MIN into close
    med_price: float      # median prior close of the movers

    @property
    def usable(self) -> bool:
        """Fewer than MIN_NAMES movers and the rates mean nothing.

        Returned as a flag rather than dropping the day, because "the market
        had no movers" is itself the coldest possible reading and throwing it
        away would bias the sample warm."""
        return self.n_movers >= MIN_NAMES


def day_features(rows: pd.DataFrame, date: str) -> DayFeatures:
    """One session's market-wide reading.

    `rows` carries symbol / prior_close / high / close for the names in band on
    that date. Building that frame is `series`'s job, because the prior close
    is a per-symbol shift and doing it per-day would be quadratic and wrong at
    the edges.
    """
    if rows.empty:
        return DayFeatures(date, 0, 0, 0, 0.0, 0.0, 0.0)
    pc = rows["prior_close"].astype(float)
    gain = rows["high"].astype(float) / pc - 1.0
    close_gain = rows["close"].astype(float) / pc - 1.0
    movers = gain >= MOVER_MIN
    n_movers = int(movers.sum())
    if n_movers:
        # Retained share of the day's own move. Guarded against gain == 0,
        # which cannot happen inside the mask but would be a silent inf if
        # this were ever called on an unmasked frame.
        g = gain[movers].where(lambda s: s > 0)
        retained = (close_gain[movers] / g).clip(lower=0.0, upper=1.0)
        rt = float((retained < RETAIN_MIN).mean())
        med = float(pc[movers].median())
    else:
        rt, med = 0.0, 0.0
    return DayFeatures(
        date=date,
        n_names=len(rows),
        n_movers=n_movers,
        n_big=int((gain >= BIG_MIN).sum()),
        lead=float(gain.max()),
        round_trip=rt,
        med_price=med,
    )


def prepare(daily: pd.DataFrame, band: tuple[float, float] = BAND) -> pd.DataFrame:
    """Attach each row's PRIOR close and keep the names in band.

    The band test is applied to the PRIOR close, not to today's. Screening on
    today's price would drop exactly the names that ran out of the band -- the
    biggest gainers -- which is the population the regime measure is about.
    """
    d = daily[["symbol", "date", "high", "low", "close"]].copy()
    d = d.sort_values(["symbol", "date"])
    d["prior_close"] = d.groupby("symbol")["close"].shift(1)
    d = d[d["prior_close"].notna() & (d["prior_close"] > 0)]
    lo, hi = band
    return d[(d["prior_close"] >= lo) & (d["prior_close"] <= hi)]


def series(daily: pd.DataFrame,
           band: tuple[float, float] = BAND) -> dict[str, DayFeatures]:
    """Every session in the archive, keyed by date."""
    prepped = prepare(daily, band)
    return {str(d): day_features(g, str(d))
            for d, g in prepped.groupby("date", sort=True)}


def score(f: DayFeatures) -> float:
    """One number, so the days can be ranked.

    Equal weights on three RANK-FREE quantities would not be comparable --
    a count, a fraction and a multiple do not add. So the composite is built
    from ranks in `classify`, and this is only the piece that has to be a
    single direction: MORE movers and a BIGGER leader are hotter, a HIGHER
    round-trip rate is colder.

    Returned as the raw triple's ordering key only where a caller wants a
    quick sort; the study uses `classify`, which ranks each component
    separately and is not sensitive to their units.
    """
    return f.n_movers * (1.0 + f.lead) * (1.0 - f.round_trip)


def classify(feats: dict[str, DayFeatures]) -> dict[str, str]:
    """hot / mixed / cold by TERCILE of a rank composite.

    Each of the three components is ranked across the sessions independently
    and the ranks are averaged, so a count, a multiple and a fraction never
    get added to each other. Terciles of the result are the buckets.

    Days with too few movers to rate are labelled "cold" and NOT dropped: a
    market with under five names moving 30% is the coldest reading available,
    and dropping those days would remove the coldest third of a cold sample
    and then report that cold days are rare.
    """
    rated = {d: f for d, f in feats.items() if f.usable}
    out = {d: "cold" for d, f in feats.items() if not f.usable}
    if len(rated) < 3:
        # Not enough rated days to cut terciles. Everything unrated rather
        # than a two-bucket split that would read like a three-bucket one.
        out.update({d: "unrated" for d in rated})
        return out
    dates = sorted(rated)
    df = pd.DataFrame({
        "movers": [rated[d].n_movers for d in dates],
        "lead": [rated[d].lead for d in dates],
        # NEGATED, so every column points the same way: bigger is hotter.
        "held": [-rated[d].round_trip for d in dates],
    }, index=dates)
    composite = df.rank(pct=True).mean(axis=1)
    lo, hi = composite.quantile(1 / 3), composite.quantile(2 / 3)
    for d, v in composite.items():
        out[d] = "cold" if v <= lo else ("hot" if v > hi else "mixed")
    return out


def lagged(labels: dict[str, str]) -> dict[str, str]:
    """Each session labelled by the PREVIOUS session's reading.

    This is the only form that is a gate. A same-day label cannot be acted on
    at 04:00 and describes days that were already good.

    The first session has no predecessor and is dropped rather than carried
    forward from itself, which would leak one day of the thing being tested
    into the answer.
    """
    dates = sorted(labels)
    return {d: labels[p] for p, d in zip(dates, dates[1:])}


def autocorr(labels: dict[str, str]) -> float:
    """P(today's label == yesterday's). The gate's ceiling in one number.

    At 1/3 the label carries no information from one day to the next and no
    lagged gate can work, whatever the same-day split shows. Printed before
    either verdict for that reason.
    """
    dates = sorted(labels)
    pairs = [(labels[p], labels[d]) for p, d in zip(dates, dates[1:])]
    if not pairs:
        return 0.0
    return sum(1 for a, b in pairs if a == b) / len(pairs)
