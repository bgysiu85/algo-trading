# Churn across the whole live record — and a headline I have to withdraw

`python -m common.churn_count` · raw: `var/reports/churn_count.txt`
Run here on the six staged fill logs, 2026-09-12.

## The correction

I told Ben the MC5 dedupe bug was where the money went, on the strength of one
session. Over all six sessions it is not.

**99 round trips, net −$679.69** (matches the known live record).

| entry reused an already-traded signal bar | n | net | per trade | win | med hold |
|---|---:|---:|---:|---:|---:|
| yes | 23 | (147.52) | **(6.41)** | 4% | 0.2m |
| no | 76 | (532.17) | **(7.00)** | 22% | 5.1m |

**Reused-signal trades are not worse per trade than the rest** — they are
slightly better. The bug cost $147.52 across six sessions: 22% of the loss on
23% of the trades. Proportional.

Same for the consequence measure:

| held under one minute | n | net | per trade | win |
|---|---:|---:|---:|---:|
| yes | 23 | (155.78) | (6.77) | 17% |
| no | 76 | (523.91) | (6.89) | 18% |

**2026-09-11 was the outlier, not the pattern.** On that day sub-minute trades
carried 88% of the loss; pooled they carry 23% on 23% of the trades. The
statement "the loss is concentrated in sub-minute churn" was true of one
session and is false of the record.

The one measure that still separates:

| entry within 5s of exiting the same name | n | net | per trade |
|---|---:|---:|---:|
| yes | 15 | (196.59) | **(13.11)** |
| no | 84 | (483.10) | (5.75) |

Instant re-entries are genuinely worse — more than twice the loss per trade —
but they are 15 trades. That is a lead, not a finding.

## Per session

```
session       trades        net   reused  instant  <1 min    net <1m   by strategy
2026-09-02         2     (1.00)        0        0       1       1.00   MCL:(1.00)
2026-09-03        19   (163.60)        0        0       1       1.00   MCL:(163.60)
2026-09-08         2    (63.74)        0        0       0       0.00   MCL:(63.74)
2026-09-09         6    (70.26)        0        0       0       0.00   MCL:(70.26)
2026-09-10        22   (224.18)        4        3       3    (20.11)   MC5:(166.94), MCL:(57.24)
2026-09-11        48   (156.91)       19       12      18   (137.67)   MC5:(203.03), MCL:46.12
```

## The control passed

The four MCL-only sessions (09-02, -03, -08, -09) show **zero reused signal
bars**. That is exactly what the diagnosis predicts: MCL's signal bar *is* the
frame's last row, so the old guard worked for it. Reuse appears only on 09-10
and 09-11 — the two sessions MC5 ran. The fingerprint is measuring the thing it
claims to measure.

By strategy, pooled:

| strategy | trades | net | reused | med hold | win |
|---|---:|---:|---:|---:|---:|
| MC5 | 59 | (369.97) | 23 | 4.1m | 12% |
| MCL | 40 | (309.72) | 0 | 3.1m | 28% |

**MCL loses $309.72 over 40 trades with no bug at all.** The deficit is not the
dedupe defect. Fixing it removes a real cost and does not make either strategy
profitable — which is consistent with every backtest, since `backtest_session`
evaluates each bucket once and never had this bug.

## What the run also fixed

`churn_count` crashed on the first three logs: they predate the `strategy`
column. Required columns are now checked up front, a log missing one is a
**named refusal** printed in the report (a log that was never counted must not
read like a clean one), and where `strategy` is absent the label comes from the
filename prefix with the affected sessions listed — a derived label that prints
identically to a recorded one being the mistake this project keeps making. The
prefix is never used when the column exists: `mcl_fills_20260911.csv` is named
MCL and is full of MC5 rows.

Bundle `20260912l`, 1,822 passed.

## What this does not say

- **Not what the fix earns.** Every session ran the broken guard; the trades
  that would have happened instead have no prices. This is what the affected
  trades cost, not what their absence returns.
- **Not a fill-quality claim.** Slippage, the concurrency cap and the exit
  mechanic are all live in these numbers and none is held constant.
- **n = 99 trades over 6 sessions.** The instant-re-entry lead rests on 15.
