# Entry latency — where the fill sits, and what came before it, 2026-09-08

Ben's observation from inspecting MCL's losing trades: the entry fills at the
close of the bar that made the move, and the next bar comes back down. This
measured the same things on every trade — winners and losers side by side —
because the observation was made on losers, and the winners entered the same
way. Tool: `common/entry_latency.py`. Reports: `var/reports/entry_latency_mcl.txt`,
`entry_latency_mc5.txt`. Bars: `bar_cache_db` (EQUS.MINI), the cache these
trades were generated on; measuring against a different tape would put the
fill in the wrong bar.

**MC5 had to be run twice.** The first run measured 5-minute fills against
1-minute bars, reported a third of its signal bars as not found and fill
positions of 7.85× the range, and was wrong in every number. `--bar-minutes 5`
fixed it; a warning now fires above a 5% miss rate.

## The fill is late, for every trade, on both strategies

| median at entry | MCL winners | MCL losers | MC5 winners | MC5 losers |
|---|---:|---:|---:|---:|
| fill position in the bar (0 = low, 1 = high) | 0.86 | 0.85 | 0.78 | 0.78 |
| fills in the top quarter | 63% | 61% | 40% | 47% |
| p90 fill position | 1.11 | 1.10 | 1.11 | 1.07 |

A p90 above 1.0 means the +1 tick put the fill above the bar's own high. The
late fill is a property of the entry rules — five conditions on a completed
bar confirm after the move by construction — and it is identical for winners
and losers. **An earlier fill in the same bar would not change which trades
win. It would lower the cost basis on all of them uniformly.**

How much is in the bar:

| summed over trades | MCL (2,413) | MC5 (7,090) |
|---|---:|---:|
| entry − signal-bar open | $58,211 ($24/tr) | $214,001 ($30/tr) |
| entry − prior bar high, where cleared | $69,643 ($30/tr) | $392,132 ($60/tr) |
| net of the trades | −$1,270 | +$10,779 |

Both are upper bounds twice over: the level is not always offered, and a
resting order at the prior high also fires on bars that break it and never go
on to signal. Those false breaks are the entire question and this measurement
cannot see them.

## MCL: winners and losers are indistinguishable at entry

| median at entry | MCL winners | MCL losers |
|---|---:|---:|
| signal-bar move | 2.8% | 3.0% |
| run-up since 04:00 | 15.0% | 14.0% |

Nothing knowable at the fill separates them. Earlier-in-the-bar is the only
lever this report exposes for MCL.

## MC5: the losers had already moved twice as far

| at entry | MC5 winners | MC5 losers |
|---|---:|---:|
| signal-bar move, median | **1.1%** | **2.9%** |
| signal-bar move, mean / p90 | 4.7% / 14.9% | 8.4% / **23.0%** |
| run-up since 04:00, median | **3.5%** | **7.9%** |
| run-up, mean | 15.6% | 22.4% |

This is the finding. On 5-minute bars, one bar's move is a large enough share
of the whole move for "how far it has already run" to predict the outcome. MC5
is buying exhaustion. The losers' p90 signal bar of 23% is the 60c-to-a-dollar
bar Ben described.

So for MC5 the problem is not only *where in the bar* the fill sits but *how
far into the move* the signal arrives. Earlier in the bar helps both
strategies uniformly; earlier in the move would change which trades MC5 takes.

## A flaw in the tool's own reading rule

The report's decisive line was written as "signal-bar move exceeded post-entry
MFE, for winners and losers." It reads 9% of winners and 66% of losers on MCL,
but the comparison is mostly circular: a loser is by definition a trade whose
MFE stayed small. The outcome-independent features — fill position, bar move,
run-up — are the honest discriminator, and they are what the tables above use.
The rule stays in the report text for now with this note against it.

## What it licenses

Two hypotheses. It proves neither.

1. **Intrabar entry at a level.** A resting order at `session_high + 1 tick`
   (or the prior bar high), filled at the level on the bar whose high crosses
   it, trail seeded from that fill, including every false break the rule
   admits. Needs a harness extension: an entry mode with the same gap-through
   logic the exits have (fill at `max(level, open)`). Applies to both
   strategies.
2. **A "not already extended" gate for MC5.** No entry above a fixed run-up
   or signal-bar move. This is a filter derived from reading these trades and
   will look good on them by construction. It can only be tested as a new
   registered hypothesis with the threshold fixed before any outcome is seen,
   scored on sessions it has never touched — and on XNAS.BASIC, where MC5 is
   −$97,335 before any of this, the bar is high.

Both go into a second registration. Neither is applied to anything live.
