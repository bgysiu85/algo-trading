# Why the simulated screen missed them — 2026-09-12

`python -m common.screen_miss` · raw: `var/reports/screen_miss.txt`
Artifact: "Screen Agreement"

## Headline

**The capture hypothesis is refuted.** On 2026-09-11 I recommended measuring the
tape's capture ratio on the missed names, on the theory that a mis-scaled volume
floor was hiding them. Of 16 missed names, **zero failed the volume clause
alone**. 15 failed CHANGE (3 of those also failed volume); 1 had no prior close.

That recommendation would have spent a session producing a number that could not
have moved any of these names.

## Method

`screen_miss` does not infer a cause from a proxy. The screen is three clauses and
a cap and every input is on disk, so each missed name is asked directly which
clause it failed and by how much.

The clause failure is decided on the **simultaneous** test, tick by tick, exactly
as `screen_accumulated` applies it — a name can reach +25% at 04:10 and the
volume floor at 08:40 and never satisfy both together. Per-clause bests are
printed beside the verdict as context, never as the verdict. `RANK ONLY` (passed
all three, still absent → pushed out by the top-40 cap) is separated out so cap
displacements are never counted as clause failures. There were none.

Clauses as applied: change ≥ 20%, price in [2.00, 25.00], volume ≥ 55,200 on this
tape (100,000 consolidated scaled by measured capture 0.552).

## Per name

| date | symbol | best change | best volume | close | why |
|---|---|---|---|---|---|
| 2026-09-08 | ISPC | 5.97% | 4,019,538 | 2.11 | CHANGE |
| 2026-09-08 | SLE | 11.29% | 118,099 | 4.73 | CHANGE |
| 2026-09-09 | BNC | 6.51% | 761,591 | 5.54 | CHANGE |
| 2026-09-09 | RML | — | — | — | NO PRIOR CLOSE |
| 2026-09-09 | SUNE | 5.79% | 7,379,646 | 3.29 | CHANGE |
| 2026-09-09 | WYHG | **(4.28)%** | 63,362 | 5.37 | CHANGE |
| 2026-09-10 | BIAF | 0.73% | 52,837 | 10.99 | CHANGE+VOLUME |
| 2026-09-10 | CULP | 5.56% | 210,736 | 4.37 | CHANGE |
| 2026-09-10 | IRD | **(1.27)%** | 184,620 | 5.99 | CHANGE |
| 2026-09-10 | ODD | 2.39% | 15,275 | 16.95 | CHANGE+VOLUME |
| 2026-09-10 | RML | **0.00%** | 18,711 | 9.50 | CHANGE+VOLUME |
| 2026-09-10 | SUNE | 9.60% | 1,798,608 | 4.26 | CHANGE |
| 2026-09-10 | TPET | 17.20% | 4,239,007 | 2.18 | CHANGE |
| 2026-09-11 | ACVA | **0.76%** | 23,007,608 | 10.46 | CHANGE |
| 2026-09-11 | LBGJ | 7.69% | 1,978,948 | 2.80 | CHANGE |
| 2026-09-11 | XRTX | 10.48% | 460,493 | 2.70 | CHANGE |

Counted: 12 CHANGE, 3 CHANGE+VOLUME, 1 NO PRIOR CLOSE. Zero RANK ONLY, zero
NOT ON THIS TAPE, zero NEVER SIMULTANEOUS, zero PRICE.

## The live lead: `prior_close`

Four bolded names were on a **premarket gainers watchlist** — names up 20% or
more — and the simulation computes their change as zero or negative. Volume is
abundant on them (ACVA 23.0M), so the tape is not blind. The suspect is the
denominator:

    premarket_change = (premarket_close / prior_close - 1) * 100

**RML at exactly 0.00% is the tell.** A change of precisely zero is what you get
when the "prior" close and the current print are the same bar — the session's own
close used as its own baseline, i.e. an off-by-one in the daily frame's date
alignment. IRD (1.27)% and WYHG (4.28)% are the same defect with the tape having
moved a little since.

This is a **correctness bug, not a threshold**, so testing it needs no
pre-registration: take one of these dates, print the `prior_close` the daily
frame supplies for the symbol and the actual previous regular session's close,
and check whether they are the same row.

External verification was not possible: TV Remix `get_ohlcv` refused both
`NASDAQ:ACVA` and `NASDAQ:TPET` as invalid symbols. The check must run against
the local daily frame.

## What this is not

- Not a measure of the live screen's correctness. TradingView's premarket volume
  is its own consolidation; these names were on the real watchlist by definition
  and are the ground truth here.
- Not a fix. Any change to the simulated screen is pre-registered and
  re-validated, never tuned until the agreement number improves.
- 58% (22/38, Wilson lower bound 42%) still means **a different universe**. Until
  the change clause is right, a backtest on the simulated screen is not a
  backtest of what the live screen trades.

## Standing lesson

Added to the project's recurring-defect list: *an inferential measurement chosen
when a direct question was available*. Every input to the screen was on disk;
asking each name which clause it failed cost 1.7 seconds and refuted the
hypothesis a capture study would have taken a session to half-answer.
