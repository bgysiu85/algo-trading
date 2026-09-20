# The 401 census dates — recovered, checked, and what they unblock

**2026-09-16.** Bundles `20260916e` (execution layer) and `20260916f` (dates).
Commits `9fa812a` and `80d84d9`. 2,629 passed, 4 skipped.

---

## 1. Done: 401 of 401

`warrior_census_20260910.md` §8 named this *"the obvious next step"* on
2026-09-10. It sat for six days. Without dates, 401 structured rows about
Cameron's trading days could be **ordered and joined to nothing**.

Cost: 401 credits of 4,876, all in nine batched calls. `docs/research/` now
carries `warrior_census_dates.txt` and `warrior_census_dated.csv`, both in git.

## 2. Why the dates can be trusted

**`pos` is the census's own playlist ordering**, assigned when the playlist was
walked months ago and entirely independent of the metadata endpoint queried
today.

> **Zero order breaks in 400 adjacent pairs.** A mistaken date does not survive
> that.

## 3. The mapping, measured rather than assumed

A recap could be published the same evening or the next morning. The two give
different joins, and guessing would have put a whole day's labels on the wrong
session. Against the archive's own 554 session dates:

| offset | labelled recaps landing on a session |
|---|---|
| **0 days** | **233 of 277 (84%)** |
| −1 day | 194 (70%) |
| −2 days | 179 (65%) |
| −3 days | 170 (61%) |

Offset 0 dominates, and the residual is a **weekend tail** — 41 of the 277
publish on a Saturday or Sunday, mapping back to Friday.

**So the rule is the nearest session at or before the publish date, not a fixed
shift.** The weekday spread (Mon 41, Tue 51, Wed 51, Thu 47, Fri 46) is flat,
which is what same-day publishing looks like and is not what a one-day lag
looks like.

## 4. The labelled sample is bigger than the figure in circulation

**277 labelled days, not 234.**

| label | n | share |
|---|---:|---:|
| hot | 63 | 22.7% |
| mixed | 46 | 16.6% |
| **cold** | **168** | **60.6%** |

Cold is still the majority, which is the premise of the whole regime case: *a
strategy validated on the hot share is not validated.* A stale denominator
understates the sample every later figure rests on, so the count is now asserted
in a test rather than quoted in a doc.

## 5. What this unblocks — and the next step is the good one

Every census row now joins to Ben's 134 trading days, to the Databento archive,
and to MCL's backtest trades.

> **The first real step is a supervised check on a classifier this project
> already built.** `common/regime.py` produces hot / mixed / cold from the daily
> archive, unsupervised, with a deliberately no-look-ahead `lagged()` path. It
> has never been compared to anything external.
>
> **Does it agree with 277 human labels?** That is the first external validation
> available for any classifier in this project, and it is now one run away.

Three outcomes, all useful:

- **It agrees** — the gate is trustworthy and can be applied, and the 16×
  hot/cold spread becomes actionable rather than anecdotal.
- **It disagrees** — the 277 labels become a supervised target, and the
  candidate inputs are already enumerated in `execution_gap_20260910.md` §5
  (count of stocks up >100%, magnitude of the leading gainer, round-trip rate
  among top gappers, share of movers under $1 vs $2–20).
- **It agrees only on the extremes** — which is itself the answer, because the
  gate only ever needed to identify cold.

**This needs Ben's machine**: the daily archive is 205 MB on `E:` and the venv
is Windows. The Linux side of the workspace cannot import `databento`.

## 6. What is still not claimed

Nothing here uses his **P/L**. The census fixed **selection** bias — the
35-video pass had `back_side` as a top-four failure mode and it censuses at
1.1× — but it could not fix **source** bias, on a channel that sells a course.

The regime label is a claim about **the tape**, independently checkable against
our own daily bars. That is the half being used, and it is the only half that
can be audited.

## 7. Also shipped today — the execution layer

Not MCL. ORB and every future candidate inherits this order path.

- **An exit no longer waits out the 20-second timeout when its limit cannot
  fill.** CRBP's stop fired at 07:02:10 and sat for the full timeout while the
  stock fell 42%; the next attempt left at 07:02:31. Entries are unchanged —
  patience is how a buy gets a good fill.
- **IB's price band is read out of its own rejection text** and consumed once by
  the next order. CRBP took three consecutive 202s while the broker was telling
  it the acceptable price.
- **`ref_drift_pct` sits beside `slippage_vs_ref`**, which alone scored the
  worst trade in the book as a 59-cent favourable fill.
- **The CONFIG row comes from the trader**, not the bridge, and names the bridge
  state so `off` and `configured-but-unattached` stop being indistinguishable.

The `trail_pct` guard fired on my own change when `ref_drift_pct` reached
`trader.FIELDS` but not `db.py` and `db_load.py` — which is the guard working.

Adding a field rolls the fill log aside on the next live session.
