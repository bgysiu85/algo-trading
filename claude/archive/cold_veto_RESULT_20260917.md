# H-B4 — the 07:00 cold veto: NOTHING, by four cents

2026-09-17. Registered `docs/research/REGISTERED_cold_veto.md` (committed before the
reading existed), run on the point-in-time universe: 551 sessions, 6,170 symbol-days,
XNAS.BASIC, flat 100, `first_seen` floor, two passes, 76 s on 8 workers. Raw:
`D:\Trading\Claude outputs\cold_veto_20260917.txt`; the per-session readings in
`cold_veto_readings_20260917.csv`. MCL's book counts **3,955** — matches. All figures at
**$4.26** friction unless the line says otherwise.

---

## 0. The one-paragraph verdict

**MCL: NOTHING. MC5: NOTHING.** Both fail reading 1 (the $4.26 margin) and reading 5
(the abstention control) — and reading 5 is the closest call of the four B-series
gates, as the registration said it would be: the veto moved MCL's per trade by
**+$0.70** against random removal's 95th percentile of **+$0.74**; MC5 +$0.89 against
+$1.03. The veto fired on **363 of 551 sessions (66%)**, refused **1,236 of MCL's 3,955
trades** and 2,332 of MC5's 6,883, and the trades it refused lose **$12.06 each** for MCL
against $11.09 for the after-07:00 trades it let through on warm sessions — a
separation of $0.97 a trade, in the direction the daily composite's ceiling pointed, and
not distinguishable from picking the same number of after-07:00 trades at random. The
cascade is zero, as a clock gate's must be. Losses avoided / winners lost: MCL −$23,843 /
+$8,938; MC5 −$55,025 / +$19,512. Two of each strategy's ten best trades are gone.

---

## 1. What the 07:00 reading said

| sessions | 551 |
|---|---:|
| vetoed (cold) | **363 (65.9%)** |
| — cold by count: fewer than 5 names visible at 07:00 | **297** |
| — cold by composite: at or below the prior sessions' lower tercile | 66 |
| warm | 127 |
| inert (rated, fewer than 60 prior composites) | 61 |
| names visible at 07:00 | median **4**, p10 2, p90 9 |

The reading is dominated by its count rule. The point-in-time watchlist has a median of
four names by 07:00, so "fewer than five" — `regime.MIN_NAMES`, the daily composite's
own floor, registered as cold-without-rating — vetoed more than half of all sessions on
its own. The composite cut decided 66 sessions of the 193 it could rate. That is the
rule as registered and it ran as written; it is also a heavier veto than the daily
composite's tercile, and §4 says what that means.

## 2. The books

| book | trades | net | per trade | per symbol-day | halves (per trade) | drop-top-3 | win |
|---|---:|---:|---:|---:|---|---:|---:|
| MCL | 3,955 | (41,598.92) | (10.52) | (6.74) | (10.68) / (10.40) | (43,469.18) | 22.2% |
| **MCL-veto** | 2,719 | (26,694.34) | (9.82) | (4.33) | (8.96) / (10.37) | (28,564.60) | 22.8% |
| MC5 | 6,883 | (92,903.63) | (13.50) | (15.06) | (14.89) / (12.44) | (99,624.56) | 21.2% |
| **MC5-veto** | 4,551 | (57,390.53) | (12.61) | (9.30) | (13.80) / (11.83) | (64,111.46) | 21.0% |

Sign stable at $1.00 / $4.26 / $8.92 in every book.

## 3. The five registered readings

| reading | MCL-veto vs MCL | MC5-veto vs MC5 |
|---|---|---|
| 1. Δ per trade ≥ 4.26 · Δ per symbol-day > 0 | **+0.70** · +2.42 — fails the margin | **+0.89** · +5.76 — fails the margin |
| 2. both halves, both denominators | early +1.72 / +1.34; late **+0.03** / +1.08 — holds | early +1.09 / +3.15; late +0.61 / +2.60 — holds |
| 3. drop-top-3 level · delta | (28,565) vs (43,469) · +14,115 — holds | (64,111) vs (99,625) · +34,145 — holds |
| 4. cluster bootstrap on the delta | P = 1.000 [+11,955, +17,837] — holds | P = 1.000 [+30,411, +40,562] — holds |
| 5. abstention control (2,000 draws) | random per trade p05 −0.78 · p50 +0.02 · **p95 +0.74**; the gate **+0.70** — **fails, by $0.04** | random p05 −1.21 · p50 +0.13 · **p95 +1.03**; the gate **+0.89** — fails |
| **verdict** | **NOTHING: fails 1, 5** | **NOTHING: fails 1, 5** |

Per symbol-day tells the same story as H-B3's: the gate +2.42, random removal's median
+2.12 and p95 +2.43. The whole headline is abstention, as it was for the range gate; the
difference is that this gate's per-trade number sits at the top of random's band instead
of in the middle of it.

## 4. The mechanism, read back

The daily composite's same-day ceiling (`ladder_and_regime_20260911.md` §4) separated
MCL's trades by +$5.86 between hot and cold sessions. The 07:00 proxy built here — the
same three quantities over the watchlist instead of the market, cut point-in-time —
separates the after-07:00 trades it vetoes from the ones it admits by **$0.97**. Two
readings of that gap:

- **The proxy is a poor stand-in for the composite.** 82% of its vetoes come from the
  count rule, not from the ranked reading, and "fewer than five names by 07:00" is a
  description of this universe's typical morning rather than a cold one. The composite
  part of the reading cut 66 sessions; whether *those* 66 carry the ceiling is a
  question this run's report does not split out, and the readings file makes it
  answerable without a re-run.
- **Or the ceiling was what caveat 1 said it might be** — a test added after seeing a
  monotone table — and $0.97 is what a real but small same-day effect looks like once it
  has to be read at 07:00 rather than at the close.

Neither is decided here, and the registration says a NOTHING does not retire the
ceiling. What is decided: **a veto a live trader could act on at 07:00, built from the
data it would have, does not beat declining the same number of trades at random.**

## 5. Where this leaves the B-series

| hypothesis | verdict | the gate's per trade | random p95 |
|---|---|---:|---:|
| H-B1 skip the first entry | NOTHING / REFUSED | +0.03 / −1.05 | — (control added after) |
| H-B3 top-3 by session range | NOTHING / NOTHING | +0.86 / +0.96 | +1.27 / +1.34 |
| H-B4 cold veto at 07:00 | NOTHING / NOTHING | +0.70 / +0.89 | +0.74 / +1.03 |
| H-B2 one position per name | blocked on the concurrency cap | | |

Three registered gates, three NOTHINGs, and a monotone ordering in how close they came:
the one with a mechanism came closest. None of them is a rule, and **B5 — the
combination — has nothing to combine**: three gates that each read as random removal do
not sum to selection. The handover's "fewer losing entries" question is answered for the
levers it named: on these books the losing trades are not marked by ordinal, by relative
range, or by the morning's breadth, and every gate that removes them removes the winners
at the same rate.

What that leaves is Part A. The question is not which entries to skip but whether the
books make enough on the sessions that pay to cover the ones that do not — and the
readings file from this run is a point-in-time session classifier that A2 can use
alongside `regime_labels`.

## 6. What this is not

Not out of sample. Not the daily composite — a proxy from the watchlist, named as such.
Not a size response: what Cameron changes on a cold day is not a veto. Not a cap model.

## Commands already run

```
python -m common.cold_veto --jobs 8
```
