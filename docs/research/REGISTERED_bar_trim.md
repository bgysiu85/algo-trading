# REGISTERED — the forming-bar trim becomes conditional

Written **before** `drop_forming_bar` changes, and after the measurement that
justifies it. `var/reports/bar_freshness.txt`, BNC, 2026-09-16 06:03–06:06 ET,
12 samples.

---

## 1. The question the probe was built to answer, and its answer

> Does IB's historical response INCLUDE the minute in progress?

**Yes.** Ten of the eleven countable samples ended with the forming minute. So
the trim must not be removed: without it the trader would act on a partial bar,
which is H1 in `claude/multi_strategy_trader_spec.md`.

The original hypothesis — that the trim was costing a minute on *every* entry —
is **refused**. That was the suspect named in `common/bar_freshness.py`'s own
header, and it is wrong.

---

## 2. What the same rows show that the verdict does not

One sample in eleven:

```
06:04:05  raw last 06:03  -> acts on 06:02   (closed, raw 65s, acted 125s)
```

At 06:04:05 the response ended with the **06:03 bar, already closed**. The trim
dropped it anyway and the strategy acted on 06:02 — a full extra minute late.
`classify()`'s own docstring says exactly this: *'closed' … the trim throws away
a good bar, and every signal is a minute late.*

**The verdict reported the mode of a distribution as though it were a property
of IB.** "Does IB include the forming bar" is not a fact about IB; it is a fact
about the moment you ask. A minute with no print produces no bar — the thing
`mc5.last_closed_bucket` already documents — so on a thin name the response
often ends with a closed bar, and BNC is a thin name.

> **New entry for the defect catalogue: a yes/no verdict over a quantity that
> is actually a distribution.** The majority answer was true and the minority
> was the expensive one, and reporting the majority hid it.

9.1% is the figure from this one run on one symbol over three minutes. It is
not a rate to rely on. It is enough to say the case is real and not a rounding
error, and the change below removes it entirely rather than estimating it.

---

## 3. The change

`drop_forming_bar(df, now, minutes)` keeps the last bar when it has **closed by
the clock**, and drops it otherwise:

```
keep  iff  now >= last_label + minutes + BAR_CLOSE_SKEW_S
```

The assumption the function was built around ("IB includes the forming minute")
was never checkable from inside the function. Whether a bar labelled 06:03 has
closed **is** checkable from inside the function, given the time. So this
replaces an assumption with a measurement — the same move `provenance()` made
in the ORB pre-flight.

`now` is **required**, not defaulted. A default that preserved the old
behaviour would mean a caller that forgot it silently got the defect back, and
the whole point is that the trim can no longer be wrong without saying so.

### 3.1 The margin, and which way it errs

`BAR_CLOSE_SKEW_S = 2.0`.

The dangerous direction is a **fast local clock**: at true 06:03:59 a clock two
seconds ahead reads 06:04:01 and would judge the 06:03 bar closed with a second
still to run. The margin buys exactly that many seconds and no more, so it is
not a proof — it is a floor, and it costs almost nothing, because the observed
'closed' sample sat 65 s past its label, five seconds clear of the margin.

What settles it is a measurement, not a constant: the probe now records IB's
own clock (`reqCurrentTimeAsync`) against the local one and prints the offset.
If the next run shows an offset near zero the margin is comfortable; if it
shows seconds, the margin is set from that figure instead of from this
paragraph.

### 3.2 This does not touch what a bar IS

A bar that has not closed is still never handed to a strategy. The change moves
**which** bars are judged forming, from "always the last one" to "the ones that
have not ended yet". In the 90.9% case the behaviour is bit-identical.

---

## 4. What would make this run wrong

- **Removing the trim** rather than conditioning it. §1 refuses that.
- **Defaulting `now`.** §3.
- **Quoting 9.1% as the rate.** One symbol, three minutes, eleven countable
  samples. It says the case exists; it does not size it.
- **Reading a re-run's majority as the verdict again.** The probe now reports
  the 'closed' share as its own line, because that share — not the majority —
  is the number this change is about.
- **Treating a thin name and a liquid one as one population.** The mechanism is
  "no print, no bar", so the rate is a function of how thinly the name trades.
  Any future rate is reported per symbol.

---

## 5. What this cannot settle

The probe's own closing note stands: it measures how stale the DATA is when the
trader reads it, not the order round trip. The median *acted* lag was 98 s, of
which 60 s is the unavoidable cost of waiting for a bar to close. The remainder
is the fetch cadence — `bars()` refreshes at most once per wall-clock minute
with a `BAR_MIN_INTERVAL_S = 20.0` floor — and **that is a separate question
this change does not address.**
