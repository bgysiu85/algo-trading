# The pullback cell — result, 2026-09-19: the gate selects exactly the cell it was built for, and the cell loses more per trade than the book it was cut from

Registered in `docs/research/REGISTERED_pullback_cell.md` (H-P2, f77a59f)
before `common/pullback_cell.py` existed. Run by Ben on 2026-09-19:
`python -m common.pullback_cell --jobs 8` on `screen_pairs_pit_itch_v2.json`,
XNAS.ITCH bars, 550 sessions, 6,411 symbol-days, 173 s. Report
`var/reports/pullback_cell.txt` (copy `Claude outputs\pullback_cell_20260919.txt`),
trades CSV beside it. Cost $0.00. Artifact page "The Calm Cell". Board item
AT-32.

**Headline. REFUSED on both books.** The deployed gate — within 5% of the
session high AND five-minute return ≤ +3% — kept 409 of MCL's 3,908 entries
and 855 of MC5's 6,462, and the kept books die on the next bar **2.9%** and
**16.3%** of the time against 12.6% and 37.3%: the mechanism held, the
gate selected the cell the pre-flight measured. **And the kept books lose
more per trade than the books they were cut from — MCL (9.40) against
(8.97), MC5 (10.18) against (8.57).** Per symbol-day "improves" by +4.87 and
+7.28 only because nine trades in ten are gone; the two denominators
disagree, and the standing rule refuses the verdict. Win rate rose (MCL 23%
→ 28%) while the money fell: the cell keeps the calm trades, and the calm
trades are the small ones. **All ten of MCL's ten best trades and nine of
MC5's are absent from the cell.** The +0 books reproduce the published
baselines to the trade.

## 1. The verdict, both books (§2)

| | MCL | MCL-cell | MC5 | MC5-cell |
|---|---|---|---|---|
| trades | 3,908 | 409 | 6,462 | 855 |
| per trade, $4.26 | (8.97) | **(9.40)** | (8.57) | **(10.18)** |
| per trade, $1.00 / $8.92 | (5.71) / (13.63) | (6.14) / (14.06) | (5.31) / (13.23) | (6.92) / (14.84) |
| per symbol-day | (5.47) | (0.60) | (8.64) | (1.36) |
| win rate | 23.0% | 28.1% | 23.0% | 24.8% |
| one-bar deaths | 12.6% | **2.9%** | 37.3% | **16.3%** |
| halves per trade | (8.94) / (9.00) | (9.93) / (9.07) | (8.70) / (8.46) | (9.36) / (10.74) |
| trades per session | 7.1 | 0.74 | 11.8 | 1.55 |
| sessions with a trade | 540 | 253 | 546 | 381 |

Reading 1: per trade **(0.43)** / **(1.61)** against a +$4.26 margin, per
symbol-day +4.87 / +7.28 — the signs disagree → **REFUSED**. Reading 5, for
the record: random removal of the same 3,499 / 5,607 trades gives a
per-trade band of −3.05 to +3.40 (MCL) and −3.31 to +5.73 (MC5); the gate
sits inside both, below the median on MCL. Readings 3 and 4 pass, as every
total-based reading does for any rule that removes trades from a losing
book (§4 of the index). NaN-only refusals: 0.1% / 0.4% — the gate bound on
the state, not on thin history.

**What the gate refused** (book-ordinal, exact, not scored): MCL 3,546
baseline entries worth (9.02) each — 2,755 losses avoided ($61,662) and 791
winners lost ($29,675); MC5 5,858 worth (8.47). The refused trades are the
book's average. The gate is not separating good from bad; it is separating
loud from quiet.

## 2. Why a quarter of the death rate is worth less than nothing (§2, the mechanism)

The pre-flight named the cell because its one-bar rate was a quarter of the
base. Deployed, it is: 2.9% and 16.3%, under the 6% / 22% bars fixed in the
registration. So this is not a gate that failed to operate. It operated and
the premise was wrong: **the one-bar death rate is not where the money is.**

The top-10 lists say why. MCL's best trade in 550 sessions — QMMM, +1,341 on
2025-09-09 at 09:17 — was entered extended, after a run; so were OCTO,
UPC, SQFT, WBUY, TTRX, WSHP, XCUR and GLTO: all ten absent from the cell.
MC5's UVIX +5,437 at 04:20, NKTR +1,191, AEHL +640: nine of ten absent. The
extension that produces the next-bar stop-outs is the same extension that
produces the trades that pay for a week of them. A cell that removes the
first removes the second, and the arithmetic of a fat right tail on a
losing book is that removing both leaves the average worse.

The `dist_from_high` half alone tells the same story from the other side:
it keeps 1,562 MCL trades at (8.43), the best per-trade figure in the run,
and its one-bar share is *higher* than the base (13.1%). The trades that
do slightly better are at the high **and** extended; calm is what costs.

## 3. The parts, and the neighbours (P6, reported never scored)

| MCL | n | per trade vs base | random p95 | | MC5 | n | vs base | random p95 |
|---|---|---|---|---|---|---|---|---|
| dist ≥ −5% alone | 1,562 | **+0.55** | +1.38 | | dist alone | 2,188 | (0.03) | +2.63 |
| ret_5m ≤ +3% alone | 1,140 | (0.02) | +1.93 | | calm alone | 3,881 | (0.62) | +1.26 |
| **cell (5%, +3%)** | 409 | **(0.43)** | +3.40 | | **cell** | 855 | **(1.61)** | +5.73 |
| tight (3%, +1%) | 89 | +2.48 | +8.70 | | tight | 270 | +2.09 | +6.85 |
| loose (10%, +5%) | 1,010 | (0.39) | +1.99 | | loose | 2,120 | +0.05 | +2.58 |

Nothing beats its abstention band. The conjunction is worse than either of
its halves on both books — adding "not extended" to "at the high" subtracts.
The tight neighbour's +2.48 / +2.09 on 89 and 270 trades sits well inside a
random band of +8.70 / +6.85 and is the small-n artefact the fence exists
for; it is printed, and it is not a direction.

## 4. Predictions scored

- **P1 (binding)** — MCL keeps 10.5%: **held** (7–13%). MC5 keeps 13.2%:
  **failed** (5–10%). NaN-only under 3%: held (0.1–0.4%).
- **P2 (mechanism)** — MCL 2.9% (bar 6%, band 3–6%), MC5 16.3% (band
  14–22%): **held** — the deployed gate is the pre-flight's cell.
- **P3 (per trade +$2–7 MCL, +$4–12 MC5)** — **failed on sign**: (0.43) and
  (1.61). The largest miss in this registration and the one that matters.
- **P4 (MCL NOTHING; MC5 clears readings 1 and 5)** — **failed**: REFUSED
  on both, and MC5 clears neither. The alternative named in the registration
  (MC5 PASSES) is further away than the prediction was.
- **P5 (absolute)** — both kept books negative at $8.92: held. MC5's kept
  book positive at $1.00: **failed** ((6.92)). MCL negative everywhere: held.
- **P6 (parts)** — distance beats calm on MCL: **held** (+0.55 vs (0.02)).
  The conjunction beats either part: **failed** on both books, and by more
  than "adds nothing" — it subtracts. The registration's own reading of
  that outcome applies: the calm condition is not carrying the effect;
  neither is the pair.

Three held, four failed, and the failures agree with each other.

## 5. What this decides

- **Item 10b closes: the pullback cell is not a selective gate.** By the
  same five readings that closed H-B1, H-B3, H-B4 and H-P1, and with the
  mechanism confirmed rather than doubted, so there is no "the gate did not
  run" escape. The pre-flight's 3.3% was real and it was the wrong thing to
  look at.
- **The one-bar death rate closes as an entry-selection target.** Four
  studies now agree from four directions: the chase gate (refuse extension),
  the delay cost (a later floor enters less extended), the pullback cell
  (select calm), and the pre-flight that started them. Every rule that
  lowers the next-bar death rate lowers per trade or leaves it inside
  random removal. The instant deaths are the price of the fat tail, not a
  separable defect. This is a §4 standard now: **a lower failure rate is
  not a better book.**
- **What it leaves.** The "fewer losing entries" line — B-series, chase,
  pullback — is read on both tapes in both directions and is closed. What
  is not an entry rule remains: the concurrency cap (AT-25, 29% of live buys
  refused, and the only thing that could make a 1.5-trades-a-session book
  matter), the stop mechanics (`stop_fill`, the rebound census), and the
  10-second strategy as a new strategy rather than a repair (AT-33).
- No threshold, no live change, nothing promoted. `holdout.json` stays
  shut. $0.00.
