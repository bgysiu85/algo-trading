# ORB on liquid "Stocks in Play" — RESULT (2026-09-18)

> **SUPERSEDED IN PART — see `claude/orb_sip_RESOLVED_20260918.md`.** The two-readings table below was the honest statement while the entry-minute ordering was unknown. One-second XNAS.ITCH bars have since resolved it (amendment E): **55.5% of entry-minute stops never happened**, and the figure of record is **+0.001R net / +0.351R gross at BASE, 1 of 7 criteria**. The verdict is unchanged. Everything in this doc other than the two-readings table still stands.

Registration: `docs/research/REGISTERED_orb_sip.md` and amendments A–D (A and B PRE-RUN, C at the unit change, D POST-RUN). Prices XNAS.ITCH RTH minute bars; opening-range volume XNAS.BASIC; daily volume EQUS.SUMMARY.

Raw: `var\reports\orb_sip.txt`, `var\reports\orb_sip_arms.csv`, ledger `var\cache\orb_sip\trades` (917,628 trades over both range lengths). 446 sessions, 2024-07-22 → 2026-04-30; **sessions from 2026-05-01 withheld and still locked**. Unit: R = P/L ÷ the trade's own 10%-ATR risk (amendment C).

## Verdict

**The strategy does not pass, in either reading of the entry-bar rule.** No paper trading, holdout unspent.

**But the paper's gross edge reproduces out of sample.** Under the optimistic intra-minute assumption the top-20 arm makes **+0.405R gross per trade** against the paper's claimed +0.38R. Realistic costs and the pessimistic assumption each remove it. This is the first outside result this project has reproduced. *(Resolved: gross is +0.351R, and friction at BASE is 0.350R.)*

## The assumption that decides it (amendments A and D) — now resolved

The stop sits 10% of ATR from entry — about 9¢ — so entry and stop often fall in the same minute. **39.9% of top-20 trades have the stop touched during the entry minute**, and a minute bar cannot say whether that low came before or after the entry print.

| reading | gross | net, paper's costs | net, BASE costs | criteria met |
|---|---:|---:|---:|---:|
| stop live in the entry minute (registered) | +0.003R | −0.054R | **−0.350R** | 1 of 7 |
| stop live from the next minute | +0.405R | +0.348R | **+0.055R** | 5 of 7 |
| **RESOLVED (amendment E, one-second bars)** | **+0.351R** | — | **+0.001R** | **1 of 7** |

Entry-minute stops average **−1.35R** in the registered reading. Amendment A.1 fixed in advance that a pass on one reading and a failure on the other is not a pass; both readings fail regardless, on different criteria. The resolved figure sits near the optimistic end — 55.5% of those stops never fired — but fails anyway, on concentration (criterion 1) and the bootstrap (criterion 2).

## The seven criteria (primary cell: 5 min, top 20, BASE)

| criterion | registered | other reading | RESOLVED |
|---|---|---|---|
| 1 drop-top-3 / -5 > 0 | −2,691R / −2,783R FAIL | +182R / +70R pass | −155R / −258R FAIL |
| 2 bootstrap P(total>0) ≥ 0.95 | 0.000 FAIL | 0.834 FAIL | 0.496 FAIL |
| 3 mean ≥ +0.05R | −0.350R FAIL | +0.055R pass | +0.001R FAIL |
| 4 trades ≥ 100 | 7,239 pass | 7,239 pass | 7,239 pass |
| 5 both halves > 0 | −1,494R / −1,038R FAIL | +66R / +335R pass | −199R / +203R FAIL |
| 6 both sides > 0 | −0.339R / −0.360R FAIL | +0.021R / +0.089R pass | −0.028R / +0.029R FAIL |
| 7 no optimum on a boundary | best top-40 FAIL | best top-10 FAIL | not re-scored — see resolved doc |

## Does the ranking select? It depends on the same assumption

Net at BASE, by arm:

| arm | trades | registered | other reading |
|---|---:|---:|---:|
| top 10 | 3,572 | −0.392R | +0.068R |
| **top 20** | 7,239 | −0.350R | +0.055R |
| top 40 | 14,657 | −0.335R | −0.006R |
| eligible (RVOL ≥ 1) | 156,017 | −0.235R | −0.084R |
| unfiltered (no ranking) | 471,788 | −0.224R | −0.139R |
| random 20 a session, 2,000 draws, p95 | — | −0.181R | −0.023R |

Registered reading: the top 20 is **worse** than no ranking and worse than random, and the RVOL deciles fall monotonically (−0.227R in decile 1 to −0.312R in decile 10). Other reading: the top 20 beats both controls and the deciles rise (−0.144R to +0.032R). The selection rule either works or anti-selects depending on one unstated convention. *(Resolved: the top-20 arm at +0.001R beats a random-20 p95 of −0.161R, but the control's population is unresolved, so this is not a clean like-for-like margin.)*

## Costs, as a share of risk (amendment C.3)

| level | friction | mean net R |
|---|---:|---:|
| PAPER (commission only) | 5.7% of R | −0.054R |
| BASE (1¢ entry, 2¢ stop) | **35.2% of R** | −0.350R |
| HARSH (2¢ / 4¢) | 58.6% of R | −0.584R |

Gross is +0.003R in the registered reading, so at every level the result is friction. The paper's book ($25,000, 1% risk, 4×, 20 positions) ends at **−76.3%** on the registered reading.

## Secondary readings

- 15-minute range: −0.437R registered, −0.002R other. Worse than 5 minutes in both, as the paper's own table implies.
- Coverage: 87.2% of exits are the stop, 18.7% of entries gapped past the trigger, 49.7% long.

## What would decide the open question — DONE

Trade-level or one-second data on a sample of entry-minute stops would settle whether the low preceded or followed the entry print. It changes which reading is honest; it does not change the verdict, since neither passes all seven. **Executed as amendment E on 2026-09-18 for $0.00 — see `claude/orb_sip_RESOLVED_20260918.md`. Both predictions held.**

## For PROGRAM_INDEX

- New line, closed at the first pass: ORB on liquid stocks in play (SSRN 4729284), out of sample 2024-07 → 2026-04. Does not pass; holdout unspent.
- New standing fact: **the entry bar's open cannot be a stop's fill** (amendment D) — the same class as "the entry bar's high happened before the close you bought at", worth 0.69R a trade here.
- New standing fact: **XNAS.BASIC RTH minute bars carry off-exchange prints that are not the session's range** (amendment B) — AAPL 2024-09-12 low 209.27 against a true 219.82; 11.3% of liquid names that session were more than 0.5% out. XNAS.ITCH matches consolidated to the cent.
- New standing fact (amendment E): **a minute bar's high and low have no order**, and where a stop sits inside typical one-bar range that ambiguity was worth 0.35R a trade. One-second bars settle it, here for $0.00.
