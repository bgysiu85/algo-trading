# The freshness probe answered its question, and its own rows answered a second one

2026-09-16, BNC, 06:03–06:06 ET, 12 samples. `var/reports/bar_freshness.txt`.

---

## 1. The question it was built for — refused

> Is `_fetch_bars`'s `df.iloc[:-1]` throwing away a closed bar, making every
> entry a minute late?

**No.** IB does include the minute in progress: ten of eleven countable
samples. The suspect named in `common/bar_freshness.py`'s own header is wrong,
and the trim must stay. Removing it would hand partial bars to strategies,
which is H1.

That also closes the BNC question from 2026-09-09: of the two minutes between
TradingView's 06:21 signal and the 06:23 fill, one is the unavoidable cost of
waiting for a bar to close, and the trim is not the other.

---

## 2. What the same rows show that the verdict did not

```
06:04:05  raw last 06:03  -> acts on 06:02   (closed, raw 65s, acted 125s)
```

At 06:04:05 the response ended with the **06:03 bar, already closed five
seconds earlier**. The trim dropped it anyway; the strategy acted on 06:02, a
full extra minute late. `classify()`'s own docstring already said what that
means — *'closed' … the trim throws away a good bar, and every signal is a
minute late* — and the verdict printed "the trim is correct" over the top of it.

**The report answered a yes/no question about a quantity that is a
distribution.** "Does IB include the forming minute" is not a property of IB.
It is a property of the moment you ask: a minute with no print produces no bar
— the mechanism `mc5.last_closed_bucket` already documents — and BNC is thin.
The majority answer was true and the minority was the expensive one.

New entry for the catalogue, beside *a sentinel that is also a legal value* and
*a second condition that cannot fail independently of the first*:

> **A yes/no verdict over a quantity that is actually a distribution.**

I wrote that report this morning and read the verdict off the mode. It took
running the thing to see it.

### On the number

9.1% is one symbol, three minutes, eleven countable samples. It says the case
is real and not a rounding error. **It is not a rate**, and the change below
removes the case rather than estimating it.

---

## 3. What changed

`drop_forming_bar(df, now, minutes=1)` keeps the last bar when the clock says
it has closed:

```
keep  iff  now >= last_label + minutes + BAR_CLOSE_SKEW_S
```

Registered in `docs/research/REGISTERED_bar_trim.md` **before** the edit.

- **The assumption became a measurement.** Whether IB sends the forming bar was
  never checkable from inside the function. Whether a bar labelled 06:03 has
  closed *is*, given the time.
- **`now` is required, no default.** A default that preserved the old behaviour
  would let a caller who forgot it get the defect back in silence.
- **`now` is the caller's reading from BEFORE the request.** A slow response
  makes it stale, and stale errs toward dropping — the safe direction, and the
  one the old code always took. Re-reading the clock afterwards would spend
  flight time as evidence that a bar had closed.
- **In the 90.9% case the behaviour is bit-identical.**

### The margin, and what settles it

`BAR_CLOSE_SKEW_S = 2.0`. It guards one direction only: a **fast local clock**
calls a bar closed with time still to run and hands a partial bar to a
strategy. Two seconds is a floor chosen in a comment, not a proof.

So the probe now reads IB's own clock (`reqCurrentTimeAsync`, measured either
side so the round trip is visible) and prints the offset against ours, with the
dangerous sign named and an explicit warning if the offset exceeds the margin.
The next run sets the constant from that figure instead of from my paragraph.

### And the report changed too

The already-closed share now gets **its own line**, printed whether it is 9% or
0% — an absent line and a line reading zero are different claims, and only the
second says the probe looked. Both majority verdicts now tell the reader to
read that count *with* them rather than instead of them.

---

## 4. Measured

`tests/brokers/ibkr/test_forming_bar_trim.py` (20) and four new clock cases in
`tests/common/test_bar_freshness.py`. Full suite **2,966 passed, 4 skipped**;
all script-style broker suites pass.

**Eight mutations, eight caught:**

| mutation | |
|---|---|
| trim unconditional again | caught |
| trim never drops | caught |
| skew margin to zero | caught |
| skew applied the wrong way | caught |
| bar length hard-coded to a minute | caught |
| naive `now` silently allowed | caught |
| closed-share line removed | caught |
| clock section always claims zero | caught |

The boundary cases are the point of that file: 06:03:59 drops, 06:04:00 and
06:04:01 drop (inside the margin), 06:04:02 keeps. The error is always a minute
of lag and never a partial bar.

---

## 5. Still open, and not addressed here

Median **acted lag was 98 s**, of which 60 s is the unavoidable wait for a bar
to close. The remainder is fetch cadence: `bars()` refreshes at most once per
wall-clock minute with a `BAR_MIN_INTERVAL_S = 20.0` floor, so a bar that
closed at 06:04:00 may not be requested until 06:04:38. That is a separate
question and this change does not touch it.

---

## Commands

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\20260916t.bundle" main
```

```
python -m pytest tests/ -q
```

Then, next time the tape is open with Gateway on the paper port:

```
python -m common.bar_freshness --symbols BNC --seconds 180
```

The new run prints the clock offset and the already-closed count. Send me
`var\reports\bar_freshness.txt` and I will either confirm the margin or set it
from the measurement.

**Promotion to `D:\TradingProd` after the close, together with the two
session-open fixes.**
