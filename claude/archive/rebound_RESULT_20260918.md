# The rebound census: yes, they come back — and not before the wider stop would have been hit

**2026-09-18.** Under `docs/research/REGISTERED_rebound.md` (H-R1), committed
`9881f6d` before any code existed, with amendments **A (PRE-RUN)**, **B (POST-RUN)**
and **C (PRE-RUN)**. 550 sessions, 6,411 symbol-days, 10,370 trades, 38 seconds.
Population check matches exactly — MCL 3,908, MC5 6,462. Raw:
`rebound_20260918.txt`, `var/reports/rebound_trades.csv`.

---

## 0. In one paragraph

**Ben's question is answered, and the answer is yes, far more often than I
predicted: 97% of all trades go under entry at some point, and about two thirds
of those trade back above it — including 53.6% of MCL's outright losers, which
is his observation of watching a winner become a loss, quantified.** But the
question H-P1 left is answered too, and it goes the other way. On the one-bar
trailing-stop exits, §2.3 reports that 63.4% of MCL's got back to entry within
the session — and §2.4, which asks *in what order*, reports that only **42.3%
got there before falling another 5% below the exit.** Give a stopped-out
position another 2.5% of room and the further fall arrives first **two thirds of
the time**. **The 5% trail is doing its job on the population that looked most
like its victim, and the `TRAIL_PCT` re-run this census existed to decide on is
not worth registering.**

Two checks the registration required caught two real defects on the way, and
neither would have shown up anywhere else.

---

## 1. Ben's question, as he asked it

> *"How often does an open position drop below the entry price and rebound to a
> profitable position? I have watched a profitable trade become a loss because
> of the stop trailing rule allowing the position to drop below entry price."*

Measured from the minute after the entry bar's close to the exit bar's close, on
the 1-minute XNAS.ITCH tape. "Came back" counts only bars **after** the position
first went under — a high that happened before the dip is not a recovery from it.

| | MCL (3,908) | MC5 (6,462) |
|---|---:|---:|
| went under entry at any point | **97.4%** | **97.9%** |
| of those, traded above entry again | **64.7%** | **68.1%** |
| of those, cleared entry + friction | 55.0% | 59.1% |
| minutes to recover | p50 **1**, p90 5 | p50 **1**, p90 5 |
| how far under it went | p50 −3.72%, p10 −6.79% | p50 −5.24%, p10 −11.65% |

Split by how the trade ended:

| | went under | of those, came back |
|---|---:|---:|
| MCL winners (1,092) | 91.2% | **96.1%** |
| MCL **losers** (2,816) | 99.8% | **53.6%** |
| MC5 winners (1,744) | 92.3% | 98.6% |
| MC5 **losers** (4,718) | 99.9% | **57.7%** |

**Essentially every trade in both books spends time under water**, and the
median dip is recovered inside a minute. **More than half of the trades that
ended as losses had a moment when the position was back above entry.** What Ben
described watching is not an unlucky edge case; it is the normal life of these
trades.

## 2. What the one-bar stop-outs looked like — and why it was not enough

The population H-P1 identified: trades held one bar and closed by the trailing
stop. 404 MCL and 2,244 MC5, measured from the minute after the exit to the
session's last minute.

| | MCL | MC5 |
|---|---:|---:|
| price came back to ENTRY | **63.4%** | **59.0%** |
| ... and to entry + friction | 60.1% | 55.4% |
| minutes until it did | p50 3, p90 41 | p50 4, p90 44 |
| highest after the exit, vs exit | p50 **+10.53%**, p90 +64.50% | p50 +8.88%, p90 +51.29% |
| LOWEST after the exit, vs exit | p50 **−14.93%**, p10 −33.53% | p50 −13.50%, p10 −34.38% |
| rose 5%+ after the exit | 66.8% | 62.1% |
| fell 5%+ further after it | **84.7%** | **78.8%** |

Read it and the trouble is obvious: **both columns are large on the same
trades.** The median one-bar stop-out went 10% above its exit *and* 15% below
it. 85% fell at least another 5%; 67% rose at least 5%. **Most of them did
both.** These names move that violently.

A maximum and a minimum say both things happened. They do not say **in what
order**, and the order is the entire question — a position given more room
recovers only if the recovery arrives **before** the further fall does. §2.3
cannot tell those apart, and on its own it reads as encouragement.

## 3. §2.4 — which came first, and it decides the question

Added as **Amendment C, PRE-RUN**: after the exit, did the price trade back above
**entry** before it fell a further W% below the **exit**? Three W's, declared
before the run — half the shipped trail, the trail, double it — all three
reported, none selected among. A single minute bar that does both resolves as
**the fall**, because inside one bar the order is unobservable and a position
with more room would have had its stop hit intrabar.

**The one-bar trailing-stop exits — the cut this census exists for:**

| extra room below the exit | | back to entry first | fell first | neither |
|---|---|---:|---:|---:|
| **+2.5%** | MCL | 30.9% | **67.6%** | 1.5% |
| | MC5 | 32.0% | **66.5%** | 1.4% |
| **+5.0%** | MCL | 42.3% | **54.5%** | 3.2% |
| | MC5 | 40.1% | **55.8%** | 4.1% |
| **+10.0%** | MCL | **54.7%** | 37.1% | 8.2% |
| | MC5 | 48.8% | 40.9% | 10.3% |

**Give a stopped-out position another 2.5% and it is hit again before it gets
back to entry roughly two thirds of the time.** Give it another 5% — doubling
the trail's width in effect — and the further fall still arrives first more
often than not, on both books. Only at **+10%** does the recovery arrive first
more often, and only for MCL; MC5 is still under half.

In stop terms: the exits fill at about −5%, so +2.5% of extra room is roughly a
**7.4%** trail, +5% is roughly **9.75%**, and +10% is roughly **14.5%**. **The
trail would have to nearly triple before holding on is more often right than
wrong, and even then "right" means getting back to entry — break-even, minus a
round trip of friction.**

**The 21-point gap is the whole lesson.** §2.3 says 63.4% of MCL's one-bar
stop-outs came back to entry. §2.4 says 42.3% came back before falling another
5%. **A fifth of the apparent recoveries arrive only after a drawdown the wider
stop would itself have caught** — they are not recoveries a wider stop could
have collected.

**Across all trades** the picture is more balanced (MCL at +5%: 59.3% back
first, 33.5% fell first; MC5 50.7% / 42.6%), but that population is mostly
exits that were not stops at all, and it does not bear on the stop-width
question.

## 4. Scoring the predictions, and one of them was a badly written rule

Registered §6, before the run.

- **"Under 40% of trades that go under come back."** **Wrong, and not
  narrowly** — 64.7% and 68.1%. I reasoned that the trail ends most trades and
  ends them on the way down. It does end them on the way down; it just does so
  after a dip that had usually already been recovered at least once.
- **"The one-bar stop-outs are roughly symmetric, with recoveries smaller than
  the further falls."** **Right**, on both magnitude (median +10.53% against
  −14.93%) and, now, order.
- **"What would make me wrong, and it is the interesting outcome: if a clear
  majority of the one-bar stop-outs recover past entry within the session, the
  5% trail is harvesting noise and a volatility-scaled trail becomes the
  best-founded registration this project has had in weeks."**

**That criterion was met — 63.4% and 59.0% — and the conclusion it pointed at is
not supported.** The criterion was badly written: it never required the recovery
to arrive **first**, so it cannot distinguish "a wider stop would have saved
this trade" from "a wider stop would have been hit even harder on the way to a
recovery that came too late". §2.4 is what separates them, and it says the
second.

**The sequence matters and is recorded:** Amendment C was written after seeing
§2.2 and §2.3's magnitudes — which is what made the ambiguity visible — and
**before a single ordering number existed.** Declaring a pre-registered
criterion underspecified after data has met it is exactly the move a
registration exists to prevent, and the only thing that makes it legitimate here
is that the replacement measurement was fixed, in full, before it was run.

## 5. Amendment A — why MC5 takes 65% more trades on five times fewer bars

Ben asked it reading the two denominators. Counted on the census's own trades:

| | entries | symbol-days touched | share of the universe | per touched day |
|---|---:|---:|---:|---:|
| MCL | 3,908 | 2,299 | 35.9% | mean 1.70, p50 1, p90 3, max 7 |
| MC5 | 6,462 | 3,444 | **53.7%** | mean 1.88, p50 1, p90 3, max 9 |

**It reaches half again as many days, and re-enters only slightly more often on
the days it trades.** The medians are identical at one entry. So MC5's extra
trades are **more opportunities taken, not churn** — which is what the entry
conditions predict: MCL must clear six conditions including a 3× volume surge,
MC5 three, none of them rare. The 5-minute timeframe cuts its chances to fire by
five and the looser filter more than makes it back.

## 6. Two checks, two defects, and neither would have surfaced anywhere else

**The boundary check (§5) found a four-minute shift on every MC5 trade.** It
required `window_close` exits to leave exactly nothing after them. The first run
reported **679 of 1,159** with tape after them, every one MC5. Cause: MC5 acts
on 5-minute bars, the excursions are read on the 1-minute tape, and a bar is
stamped with its **start** — so a trade stamped 09:25 fills at 09:29, and those
four minutes were counted as "after the exit" when they happened before the
fill. The entry side was shifted the same way. **Nothing else in the report
looked wrong.** The check was inherited from `mfe_exit`, where it had caught
nothing in a year, and kept on the stated grounds that a silent window bug would
corrupt every number in §2.2. It was exactly that. (Amendment B.)

**The grain check then found the fix's own blind spot.** The first fix carried
`{"MCL": 1, "MC5": 5}` as a constant here; the check — every trade moved as an
N-minute trade must sit on an N-minute boundary — found **3 of 6,460** MC5
entries off the grid. **The cause is in MC5 itself:** it resamples to five
minutes *unless* `_looks_5m` reports the frame already looks 5-minute, which is
true on a name so thinly traded that its 1-minute bars are more than five
minutes apart on the median. On those symbol-days it trades the frame
**unresampled**, its bars *are* the tape's bars, and the correct offset is zero.
A constant would have been right 99.95% of the time and silently wrong on the
rest — **the same shape as the defect it was introduced to fix.** The grain is
now read from the engine, per symbol-day.

**And that is a fact about MC5 worth recording on its own:** on a sufficiently
thin name the strategy runs its indicators on unevenly spaced bars and calls
them five-minute bars. Six entries in this run. It is documented nowhere else.

## 7. What this closes, and what it does not open

**The stop-width line is closed for widening.** H-P1 established that the
one-bar deaths are the trailing stop firing rather than gaps or reversals
running away, and left open whether a wider stop would have recovered them or
deepened them. It deepens them: at every plausible amount of extra room the
further fall arrives first more often than the recovery. **The `TRAIL_PCT`
re-run this census was built to decide on is not worth registering**, which is
the decision it was built to make, and it is a no.

**It does not close a volatility-scaled trail as an idea**, but it removes the
argument that motivated it. The pre-flight's reading — that these names are
volatile and a fixed percentage is hit by noise — is true about the *volatility*
and false about the *consequence*: the moves that take the stop out are
overwhelmingly followed by more of the same move, not by a bounce. A scaled
trail would hold through them and be hit lower.

**What it leaves standing is what §2.1 says about the rest of the book.** 97% of
trades go under, two thirds come back, the median recovery takes a minute, and
**53.6% of MCL's losers were above entry at some point before they were
closed.** That is not a stop-width finding — those trades were not stopped on
their first bar — and it is not a rule. It is the strongest description this
project has of what the inside of a losing trade looks like, and it belongs to
the exit question rather than the entry question, which is where nothing has
been registered since the ladder and Cameron's partial were rejected on
2026-09-11.

**And the ceiling is unchanged.** Break-even friction is −$0.96 a round trip on
MCL and −$4.67 on MC5; both lose at zero cost. No exit change reaches that, and
this census never claimed one would.

## 8. What this is not

Nothing ships; `holdout.json` untouched. **Not a price on a wider stop** — a
wider trail tracks the peak, so it sits somewhere else at every later bar and
the position's path is not this one, and a position held longer consumes bars
the strategy would otherwise have re-entered on. §2.4 bounds the opportunity's
**shape**; only a `TRAIL_PCT` re-run converts it to dollars, and §7 is the
decision not to run one. **Not a rule** — every quantity here is
outcome-dependent by construction, which is what a census is for and what
disqualifies a gate; nothing in it may become an entry or exit condition without
its own registration. **Not beyond the session** — both books flatten at the
window, so a recovery after 09:30 is not one they could have taken. **No P&L, no
book comparison, no verdict vocabulary**, enforced by a test: the only dollar
figure in the report is the friction offset that defines "back to a profit".

## Commands run

```
python -m common.rebound --jobs 8
```
