# HOWTO — the rebound census (H-R1)

**Date:** 2026-09-18 · **Registration:** `docs/research/REGISTERED_rebound.md`
(committed `9881f6d`, before any code existed) · **Code:** `common/rebound.py` (`4580b06`)
**Amendment A:** PRE-RUN, entries per symbol-day.

---

## The question

Ben, 2026-09-17, in his own words:

> *"How often does an open position drop below the entry price and rebound to a profitable
> position? I have watched a profitable trade become a loss because of the stop trailing rule
> allowing the position to drop below entry price."*

It became load-bearing on 2026-09-18. H-P1 measured, on 2,904 one-bar trades, that **94% of
MC5's instant deaths and 82% of MCL's are the trailing stop firing** — filling at a median
−5.23% against a stop set at −5%, with under 1% landing more than half a point below it. They
are stop-hits, not gaps and not reversals running away.

Which means the deficit may be a **stop-width** problem rather than an entry problem. And
nothing in this project measures what the price did **after** the stop fired.

## Running it

From `D:\Trading`, after merging `build-20260918l.bundle`:

```
python -m common.rebound --jobs 8
```
```
echo $LASTEXITCODE
```

Five sessions first, if you want a smoke run — a few seconds:

```
python -m common.rebound --limit 5 --jobs 4
```

Reads 550 sessions of XNAS.ITCH 1-minute bars off `E:\Databento`. Roughly three minutes on
eight workers, the same as the chase gate. Spends nothing.

**Outputs**

| | |
|---|---|
| `var\reports\rebound.txt` | the report — copy to `D:\Trading\Claude outputs` |
| `var\reports\rebound_trades.csv` | one row per trade, so follow-up questions need no re-run |

## What it reads

Every trade in both published baselines on `screen_pairs_pit_itch_v2.json` — MCL 3,908, MC5
6,462 — against the same bars the engines traded, bounded by `mfe_exit.session_bars` rather
than a window of its own.

**Inside the trade (§2.1).** Did the low fall below entry; how far under (MAE, percent of
entry); after it *first* went under, did it trade above entry again; and did it clear entry
plus the measured friction, which is not the same question. Split by whether the trade
ultimately won or lost, descriptively.

**After the exit (§2.2).** From the bar after the exit to the session's last bar: the highest
price reached, **the lowest**, both against entry and against the exit; whether price returned
to entry and to entry plus friction; and how long that took.

The low is the half `mfe_exit` never measured, and it is the half that decides the question. A
stop that fires before a further fall **saved** money; one that fires before a recovery **cost**
it.

**The cut it exists for (§2.3).** The same blocks restricted to one-bar exits whose reason is
`trailing_stop` — 406 on MCL and 2,283 on MC5. That is the population H-P1 identified.

**Entries per symbol-day (Amendment A).** How many of the 6,411 symbol-days each book touched,
and how many entries it took on the days it traded — separating "reaches more days" from
"re-enters on the same day". Added because MC5 runs on 5-minute bars, 66 in a session against
MCL's 330, and still takes 65% more trades.

## What it cannot do, stated before it ran

**It cannot price a wider stop.** Two reasons, both in §3 of the registration:

1. **A wider trail changes the path, not just the exit.** The trail tracks a peak, so widening
   it changes when it arms and where it sits at every later bar. The counterfactual exit is not
   "the same trade, exited later".
2. **Signal-ordinal, again.** A position held longer consumes bars the strategy would otherwise
   have re-entered on, so the gated book is not the baseline with one exit moved.

Only a `TRAIL_PCT` re-run converts this to dollars, and that is a separate registration. **The
census's entire job is to decide whether that re-run is worth registering.**

## Reading the report

- **Boundary check (§5) first.** A `window_close` exit has nothing after it by construction. If
  the report says WINDOW MISMATCH, every post-exit number is measured over the wrong window and
  nothing below it is worth reading. If it says the check did not run at all, treat §2.2 as
  unverified — both books close out at the window every session, so an absence is itself wrong.
- **The §2.3 block is the one that decides what happens next.** If a clear majority of one-bar
  stop-outs recover past entry within the session, the 5% trail is harvesting noise on exactly
  the most volatile names, and a volatility-scaled trail becomes the best-founded registration
  this project has had in weeks. If the recoveries and the further falls are roughly symmetric,
  a wider stop trades a certain small loss for an uncertain larger one and the trail is doing
  its job.
- **Percent excursions are the subject matter; money is not.** Unlike the Running Up pre-flight,
  which barred money outright, this one is about price. What stays barred is strategy P&L, book
  comparison and verdict vocabulary — a test asserts no dollar figure reaches the report except
  the friction offset that defines "back to a profit".
- **Nothing here may become a rule without its own registration.** Every quantity in it is
  outcome-dependent by construction, which is exactly what a census is for and exactly what
  disqualifies a gate.

## My predictions, on the record before the run

**Inside the trade:** most trades that go under do *not* come back — under 40% on both books,
because the trail is what ends most trades and it ends them on the way down. Low-to-moderate
confidence. Ben's observation is about a different population (trades that were *up* first),
which the win/lose split shows separately.

**After the exit, the one that matters:** the one-bar stop-outs are roughly symmetric, with
recoveries smaller than the further falls. Genuinely uncertain — these are names selected for
having just moved 20% pre-market, and high volatility cuts both ways.

**What would make me wrong, and it is the interesting outcome:** a clear majority of one-bar
stop-outs recovering past entry within the session.

## Nothing ships

`holdout.json` untouched. No strategy constant read, written or swept; no engine parameter
changed. The census reads the published books and the tape, and writes a report and a CSV.
