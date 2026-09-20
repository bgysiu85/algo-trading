# A sentinel that is also a legal value

**2026-09-16.** Commit `2f5b76f`, bundle `20260916i`. A new entry for the
recurring-defect list in `PROGRAM_INDEX.md` §4.

## What happened

`tests/brokers/ibkr/test_pacing_and_trail.py` forced a bar-cache miss with

```python
st.bars_minute = (0, 0)
```

and treated that as an impossible value. It is midnight ET. `bars()` compares
the stamp against `(now.hour, now.minute)`, so for one minute a day the cache
read as fresh, no history was re-requested, and the check failed.

**Midnight ET is early afternoon in Australia** — which is when this suite
actually gets run.

## Why it survived

One failure a day out of 1,440 minutes is the worst rate available: seen often
enough to be noticed, rarely enough to be re-run and forgotten. The suite was
green on every Linux run because nothing there sits at midnight ET either.

Confirmed rather than assumed. With the clock held at a chosen time, the old
sentinel produces:

| clock (ET) | history requests | expected |
|---|---:|---:|
| 00:00 | 1 | 2 |
| 12:34 | 2 | 2 |
| 14:00 | 2 | 2 |

## The trader was not at fault

`SymbolState.bars_minute` defaults to `None`, which cannot equal a wall-clock
minute at any instant, and production never writes `(0, 0)`. But nothing in
the suite pinned the cache's behaviour at a **named hour**, so nothing could
have said which of the two was wrong. A test that only ever runs at whatever
time someone typed the command is not testing a clock-dependent branch — it is
sampling it.

## The fix

The sentinel is derived from the clock rather than chosen, so it cannot
collide at any hour. `tests/brokers/ibkr/test_bars_cache_clock.py` supplies
the time instead of observing it: the refresh case runs at 00:00, 00:01,
09:30, 12:34 and 23:59 as **the same assertion at a chosen moment**.

Six tests, five mutations killed on `bars()` — including both over-corrections
in opposite directions:

- dropping the minute stamp → the cache never expires, the strategy trades on
  stale bars;
- dropping the freshness check → 60 requests per 10 minutes, after which IB
  refuses and the strategy goes blind without saying so.

## The shape, stated generally

> **A sentinel that is also a legal value is not a sentinel.**

Same family as the one already on the list — *a control whose output is
indistinguishable from the failure it detects*. Here the "impossible" marker
and a real reading were the same bytes, so the code could not tell "never
fetched" from "fetched at midnight".

The same session produced a second instance in `tests/test_artefact_guard.py`
(commit `450fb35`): `'\\\\'` in a non-raw literal is two backslashes, so a
Windows path normalisation normalised nothing and the whole suite refused to
collect. A normalisation that only runs correctly on the platform that does
not need it is not a normalisation.
