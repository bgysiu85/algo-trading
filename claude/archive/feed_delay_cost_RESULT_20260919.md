# What the live feed's 900 seconds cost — result, 2026-09-19: not the shape of the live book, and almost nothing per trade

Registered in `docs/research/REGISTERED_feed_delay_cost.md` (H-D1, da5a00d)
before `common/feed_delay.py` existed. Run by Ben on 2026-09-19 from
`D:\Trading`: Arm A `python -m common.feed_delay --jobs 8` on
`screen_pairs_pit_itch_v2.json` (550 sessions, 6,411 symbol-days, 105 s);
Arm B on `screen_pairs_pit_itch_ext.json` (the eight live sessions 09-08 →
09-17, 76 symbol-days). Reports `var/reports/feed_delay.txt`,
`feed_delay_live.txt`, trades CSVs beside them. Cost $0.00. Artifact page
"Fifteen Minutes Late". Board item AT-34.

**Headline. Moving the entry floor from `first_seen` to `first_seen + 15 min`
— what every live session before 2026-09-18 actually traded — changes MCL by
+$0.09 a trade and MC5 by ($1.03), moves win rate by under a point and R by
under a quarter on both books, and closes none of the distance to the live
book. The registration's three words come out as NOT IT, on both arms.** The
+0 books reproduce the published baselines to the trade (MCL 3,908 at (8.97),
MC5 6,462 at (8.57)). And the gap the study existed to explain has largely
closed on its own: over the eight live sessions MCL is 50 round trips at 34%
win / R 1.15 against the simulation's 30% / 1.47 — the 47% / 0.72 that
started this was seventeen trades.

## 1. Arm A — the population (§2 readings 1–3, 5)

| | MCL +0 | +5 | **+15** | +30 | MC5 +0 | +5 | **+15** | +30 |
|---|---|---|---|---|---|---|---|---|
| trades | 3,908 | 3,712 | **3,513** | 3,364 | 6,462 | 5,146 | **4,604** | 3,864 |
| per trade, $4.26 | (8.97) | (8.98) | **(8.89)** | (8.75) | (8.57) | (9.03) | **(9.60)** | (9.80) |
| per symbol-day | (5.47) | (5.20) | **(4.87)** | (4.59) | (8.64) | (7.24) | **(6.89)** | (5.91) |
| win rate | 23.0% | 23.0% | **22.8%** | 22.8% | 23.0% | 22.9% | **22.9%** | 22.4% |
| R | 1.62 | 1.62 | **1.65** | 1.67 | 1.92 | 1.82 | **1.70** | 1.70 |
| one-bar share | 13% | 12% | **11%** | 11% | 37% | 35% | **33%** | 31% |
| median `ret_5m` at entry | 5.33% | 5.18% | **5.14%** | 5.09% | 2.69% | 2.24% | **2.13%** | 2.13% |
| marginal trade vs +0 | — | (8.78) | **(9.74)** | (10.36) | — | (6.78) | **(6.01)** | (6.73) |

Both halves stay negative in every book at every friction. Per symbol-day
"improves" for both because fewer trades are taken on a losing book — the
abstention arithmetic, not a finding. The marginal trade says which way the
selection ran: the 395 MCL trades the delay removes were worth (9.74) each,
slightly *worse* than the book, so the delayed MCL book is a hair better per
trade; the 1,858 MC5 trades it removes were worth (6.01), *better* than the
book, so the delayed MC5 book is worse. **MC5 loses 29% of its entries to a
15-minute floor** — far more than the 5–15% predicted — because its
five-minute signals cluster in the first three bars after a name qualifies.

## 2. Arm B — the live sessions (§2 reading 4)

| 2026-09-08 → 09-17 | n | per trade | win | R | median hold (min) | holds ≤ 2 min |
|---|---|---|---|---|---|---|
| **MCL live** | 50 | (7.13) | **34.0%** | **1.15** | 12 | 14% |
| MCL sim +0 | 67 | (4.63) | 29.9% | 1.47 | 5 | 31% |
| MCL sim +15 | 58 | (3.62) | 31.0% | 1.54 | 4 | 31% |
| MC5 live (apex-ON rows, not classified) | 123 | (3.73) | 18.7% | 2.85 | 5 | 31% |
| MC5 sim +0 | 93 | (3.51) | 31.2% | 1.72 | 10 | 0% |
| MC5 sim +15 | 71 | (4.13) | 31.0% | 1.57 | 15 | 0% |

MCL's classification, the registration's rule: win-rate gap at +0 is 4.1
points and at +15 is 3.0 (closed 0.29 of the way — under half); R gap at +0
is −0.32 and at +15 is −0.39 (moved away). **NOT IT.** Arm A's own live
block (six of the eight sessions fall inside the v2 file) reads the same:
gaps of 6.4 points and −0.94, both widened by +15.

What the live column says on its own matters more than the classification.
At 17 trades (2026-09-12) live MCL read 47% / R 0.72 and the simulation
21.7% / 1.67, which is what made the feed's delay a candidate. At 50 trades
the live book reads 34% / 1.15 and the simulation on the same sessions 30% /
1.47. Most of the "shape gap" was sample size. What remains — a third of a
point of R, and a live hold twice the simulated one — is not the feed,
because the delayed floor moves both the wrong way.

## 3. Predictions scored

- **P1 (binding)** — MCL 10.1% of trades removed at +15: **held** (10–25%).
  MC5 28.8%: **failed** (5–15%). The five-minute engine signals early after
  qualification, so a floor that looks small on 1-minute bars is three
  signal bars on MC5.
- **P2 (per trade)** — MC5 ($1.03): **held** ((0.30)–(1.50)). MCL +$0.09:
  **failed on sign**, predicted (0.20)–(1.00); the magnitude is nine cents
  either way, and the marginal trade explains the sign — MCL's earliest
  entries are marginally its worst, not its best.
- **P3 (shape)** — win rate moves 0.2 / 0.1 points, R 0.03 / 0.22: **held**,
  and the classification is "not it" as predicted.
- **P4 (Arm B)** — the +15 MCL total lands 32% from the +0 total (edge of
  ±30%: **narrowly failed**); MC5 10% (held). "Live MCL win rate stays ≥ 15
  points above both": **failed** — it is 3–4 points above, because the live
  book grew from 17 to 50 trades and its win rate fell from 47% to 34%. The
  prediction assumed the 09-12 live shape would persist; it did not.
- **P5 (mechanism)** — median `ret_5m` at entry **falls** with the floor
  (MCL 5.33% → 5.09%, MC5 2.69% → 2.13%): **failed, informatively.** The
  bar that qualifies a name for the screen — the +20% crossing — is the
  extension, and the entries taken in the minutes right after it are the
  most extended ones. Waiting lets the spike subside. This is H-P1's finding
  seen from the clock rather than the feature: the chase is concentrated in
  the first quarter-hour after qualification.

Three of five held; the two that failed both point the same way — the early
window after qualification is where MC5's better trades and MCL's most
extended entries both live.

## 4. What this decides

- **The live record before 2026-09-18 is evidence about the published
  strategies.** It traded a screen 900 seconds behind the tape, and that
  floor costs MCL nothing per trade and MC5 about a dollar. The shape it
  shows is the strategies' shape, at the sample size it has. Item 1d(a)
  closes.
- **The remaining live-vs-sim differences are not the feed.** Live MCL holds
  twice as long as simulated (12 min against 5) and its R is a third lower.
  The candidates left are the ones the index already lists: the concurrency
  cap (29% of live buys refused; AT-25), fills and the trailing-stop
  mechanics (`stop_fill`), and IB's bars against the tape. The cap is next.
- **The MC5 number is worth carrying:** a 15-minute delay removes 29% of its
  entries and its better ones. Going forward the feed is real-time (once
  promoted, AT-28), so this is a description of the past, not a lever — but
  it says that MC5's live book to date under-represents its own early
  entries, and any live-vs-backtest reconciliation for MC5 (AT-14) should
  compare against the +15 book, not the +0 one.
- **The +15 books are on disk** (`feed_delay_trades.csv`, `book` column) for
  exactly that reconciliation. No new run is needed.
- Nothing about a strategy, no threshold, no live change. `holdout.json`
  stays shut. $0.00.

## 5. Notes on the run

Arm B ran on the ext universe as it stood (09-08 → 09-17); the 09-18 session
(AT-95) was not yet pulled. Adding it would change the live column by one
session and nothing in the reading. Arm A's live block matched six sessions
because the v2 file ends at 2026-09-15; it agrees with Arm B. The two arms
took 105 s and 3 s.
