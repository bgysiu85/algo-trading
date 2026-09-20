# A maximum hold time — measured and rejected, 2026-09-10

Ben, 2026-09-10: *"an addition to the exit strategy where the position should
not be held for more than 5 mins."* For MCL.

**Rejected. The 5-bar cap costs $2,245 over 373 sessions — MCL's entire +$161
result fourteen times over — and the boundary check fails, so none of the
tested caps should be adopted either.**

Tool: `common/hold_cap_study.py`. Reports: `var/reports/hold_cap.txt` and
`hold_cap_delayed.txt`. Mechanism: `max_hold_bars` on `MCL.backtest_session`,
shipped in `20260910l` and **not enabled anywhere**.

---

## 1. The result

373 sessions, 100 shares flat, after tiered commission and $4.26/RT.

| variant | trades | net | per trade | win% | avg bars | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **no cap** | 485 | **+$161** | **+$0.33** | 34.0% | 9.9 | −$923 | −$248 | +$410 |
| 3 bars | 558 | −$1,878 | −$3.36 | 29.7% | 2.3 | −$2,883 | −$615 | −$1,263 |
| **5 bars** | 546 | **−$2,084** | **−$3.82** | 29.7% | 3.1 | −$3,089 | −$701 | −$1,383 |
| 10 bars | 519 | −$946 | −$1.82 | 31.8% | 4.3 | −$1,951 | −$279 | −$667 |
| 15 bars | 512 | −$795 | −$1.55 | 31.4% | 5.1 | −$1,801 | −$188 | −$607 |
| 30 bars | 502 | −$585 | −$1.17 | 33.1% | 6.7 | −$1,635 | −$396 | −$188 |

Every cap loses money, in both halves, and the loss shrinks monotonically as
the cap loosens. **The boundary check failed**: the best cell is 30 bars, the
loosest tested, so the range is in the wrong place and the trend points at *no
cap at all* rather than at some cap between the tested values.

The prediction registered in the module docstring before the run — that a cap
would truncate the right tail while leaving the left tail alone — holds on
direction. The mechanism is more specific than predicted; see §3.

## 2. Both runs agree, so this is not an artefact of the entry model

Live entries land a minute after the signal bar closes, so a 5-bar cap in the
backtest is a 4-bar cap on the position actually held. Re-run with
`--entry-delay 1`:

| | no cap | 5 bars | delta |
|---|---:|---:|---:|
| entry at signal close | +$161 | −$2,084 | **−$2,245** |
| entry one bar later | +$13 | −$2,509 | **−$2,522** |

Same sign, same order of magnitude, slightly worse on delayed entries. The cap
is not interacting with the entry latency; it is losing money on its own terms.

(The delayed baseline falling from +$161 to +$13 is the entry-latency finding
reproducing itself, unchanged.)

## 3. Where the money went — two separate costs

### Truncated winners: −$1,929

Pairing on the entry, so both variants score the same trade:

| | |
|---|---:|
| trades in both | 485 |
| total | **−$1,929** |
| median | **$0.00** |
| worse / better / unchanged | 67 / 74 / **344** |

**On 344 of 485 trades the cap does nothing at all, and among the 141 it
touches, more got BETTER (74) than worse (67).** The median paired trade is
exactly zero. Yet the total is −$1,929 — so this is not a broad tax, it is a
handful of large truncations. The cap wins small and often and loses big and
rarely, which is the exact inverse of the payoff MCL depends on.

### Extra trades from freed slots: −$316

Capping releases the position slot earlier, so the capped run takes **61 more
trades** (546 vs 485). Those extra trades are net −$316. Small, but it is why
the variant totals could never have been compared directly without pairing.

## 4. The finding that is worth more than the question

The baseline's own P/L, bucketed by how long the trade ran. This needed no cap
to compute and it says the premise was wrong:

| bars held | n | net | per trade |
|---|---:|---:|---:|
| **1** | **107** | **−$3,924** | **−$36.68** |
| 2 | 140 | +$1,452 | +$10.37 |
| 3–4 | 72 | +$473 | +$6.57 |
| 5–9 | 81 | +$1,133 | +$13.99 |
| 10–19 | 29 | +$214 | +$7.37 |
| 20–59 | 39 | +$196 | +$5.02 |
| 60+ | 17 | +$618 | +$36.33 |

**Every bucket is profitable except one-bar holds, and that one bucket loses
more than the entire book.** Long holds are not MCL's problem — the 60+ bucket
is its best, at +$36.33 a trade.

Drop the 1-bar trades and MCL is **+$4,086 over 378 trades, +$10.81 each**,
against +$161 over 485. 22.1% of trades destroy 96% of the gross result.

A one-bar hold means price gave back 5% of its peak within the minute after
entry — buying into a spike that immediately reverses. A time cap cannot touch
these: a trade that ends in one bar never reaches any cap.

**This is a post-hoc bucket and must be treated as one.** It was found by
looking at a table, not by prediction, and the worst bucket of any partition is
low by construction. It is a *lead*, not a result. Any rule aimed at it has to
be pre-registered, stated as an ENTRY filter (the only place it can act), and
run against both halves and drop-top-N before it means anything — and the
obvious candidates are already-measured dead ends: the consolidation filter was
rejected on 2026-09-09 and the cent stop on 2026-09-10.

## 5. What changed in the code

`max_hold_bars` on `MCL.backtest_session`, defaulting to `None`. **Not enabled
in the live path, the Pine script, or any config.** It exists so the question
can be re-asked cheaply if the universe changes.

It is **last** in the exit order: the trail wins when both fire on the same bar
(a stop that was hit must not be recorded as a time exit), and `window_close`
wins on the session's final bar (the session forcing you flat is not a decision
this rule gets to relabel). Both priorities are tested behaviourally, the
`window_close` one at `cap=29`, where the second trade reaches the cap exactly
on the last bar.

Tested against `None`, never truthiness, so `max_hold_bars=0` means the tightest
cap rather than no cap — the same trap that was live in `trail_cents`, where a
zero falling back to the default would have made the tightest cell of a sweep
secretly the loosest. 19 tests.

## 6. Caveats

- **In sample.** MCL was fitted on these 373 sessions. That cuts against the
  cap here — a rule tuned on this tape is being defended on this tape — but
  the rejection is so large and so consistent across halves and both entry
  models that out-of-sample data is unlikely to reverse it.
- **1-minute bars.** A cap measured on 1-minute bars is a cap on 1-minute
  decisions. Nothing here says anything about a 5-minute-bar strategy.
- **Not the screened universe.** `bar_cache`, not `bar_cache_xnas`, where MCL
  loses −$5.22/trade on every subset. The §4 lead in particular should be
  re-checked there before anyone builds on it.
