# Part A — luck or edge: neither. The books lose more on the sessions that pay

2026-09-17. Registered `docs/research/REGISTERED_luck_vs_edge.md` (committed before the
numbers existed). Inputs: the point-in-time MCL and MC5 books (3,955 / 6,883 trades, 551
sessions, 6,170 symbol-days, XNAS.BASIC), the daily archive's regime over a median
11,324 symbols a session, H-B4's 07:00 readings, and a trend-day flag fixed in advance.
Raw: `D:\Trading\Claude outputs\luck_vs_edge_20260917.txt`; per-session labels in
`luck_vs_edge_labels_20260917.csv`. All figures at **$4.26** friction, flat 100,
commission in. **Per session divides by all sessions in the bucket, traded or not.**

---

## 0. The one-paragraph verdict

**Neither luck nor edge.** MCL loses **$84.74 per session on same-day-hot sessions**
— the most favourable label there is, one that cannot be known before the close —
against $58.82 on cold ones; MC5 loses $211 on hot against $124 on cold. Per trade is
flat across the weather (MCL −$9.66 hot, −$11.42 mixed, −$10.68 cold); what a hot day
changes is how *often* the strategies trade, and every extra trade costs the same ten
dollars. Reading 1 fails on both strategies on both paying labels — hot and trend — in
both halves and after dropping the three best sessions, so the break-even frequency is
not read: there is no hot-day frequency at which these books break even, because they
do not make money on hot days. Ben's question was whether the 09-16 green day was the
opportunity set; over 551 sessions the answer is that **the opportunity set does not
pay these strategies either** — 09-16 was one of 182 hot sessions, and the other 181
lost $87 at the median.

---

## 1. Sessions by label

| labelling | hot / trend | mixed | cold / not | notes |
|---|---:|---:|---:|---|
| same-day regime (the ceiling) | 182 | 182 | 187 | terciles of the market composite, known at the close |
| lagged regime (actionable) | 182 | 182 | 186 | yesterday's label |
| trend day (leader held ≥ +50% into 09:30) | **382** | — | 169 | see §4: the threshold did not select |
| 07:00 reading (H-B4) | warm 127 | cold 66 | count-cold 297 · inert 61 | |

## 2. MCL by label — per session over all sessions in the bucket

| bucket | sessions | trades | net | per trade | **per session** | pos % | median | drop-3 / s | early / late per session |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| same-day hot | 182 | 1,596 | (15,422.27) | (9.66) | **(84.74)** | 16.3 | (87.06) | (94.18) | (70.04) / (94.58) |
| same-day mixed | 182 | 1,329 | (15,177.30) | (11.42) | (83.39) | 12.8 | (74.74) | (88.13) | (66.76) / (103.67) |
| same-day cold | 187 | 1,030 | (10,999.35) | (10.68) | (58.82) | 13.7 | (58.23) | (63.63) | (58.66) / (59.01) |
| lagged hot | 182 | 1,589 | (15,437.51) | (9.72) | (84.82) | 13.5 | (74.25) | (93.97) | (69.91) / (94.81) |
| lagged cold | 186 | 998 | (11,120.21) | (11.14) | (59.79) | 14.4 | (54.85) | (64.53) | (55.17) / (65.27) |
| trend | 382 | 3,023 | (29,185.09) | (9.65) | (76.40) | 15.9 | (68.80) | (80.90) | (63.30) / (91.25) |
| not trend | 169 | 932 | (12,413.83) | (13.32) | (73.45) | 10.4 | (63.27) | (77.89) | (68.36) / (77.23) |
| 07:00 warm | 127 | 1,431 | (14,081.76) | (9.84) | (110.88) | 12.7 | (109.38) | (124.03) | (89.09) / (114.25) |
| 07:00 cold (composite) | 66 | 586 | (5,558.60) | (9.49) | (84.22) | 15.2 | (81.38) | (97.92) | (97.85) / (80.21) |
| 07:00 count-cold | 297 | 1,400 | (16,913.85) | (12.08) | (56.95) | 13.9 | (49.88) | (59.90) | (53.55) / (62.33) |

MC5 has the same shape at twice the size: hot **(211.21)** per session, mixed (171.76),
cold (124.08); trend (176.41) against not-trend (150.97); per trade −$13.38 / −$13.40 /
−$13.83 across the three regimes. Sign stable at $1.00 / $4.26 / $8.92 in every cell of
every table; not one bucket is positive at any friction level for either strategy.

## 3. The registered reading

| | MCL, same-day hot | MCL, trend | MC5, same-day hot | MC5, trend |
|---|---|---|---|---|
| H per session | (84.74) | (76.40) | (211.21) | (176.41) |
| halves | (70.04) / (94.58) | (63.30) / (91.25) | (198.62) / (219.65) | (175.97) / (176.91) |
| drop-top-3 sessions | (94.18) | (80.90) | (217.88) | (192.76) |
| reading 1 | **no edge on the paying sessions** | same | same | same |
| reading 2 (break-even f*) | not read | not read | not read | not read |
| context: L, observed share | (70.94), 33.0% | (73.45), 69.3% | (147.60), 33.0% | (150.97), 69.3% |

**No regime gate, however good, rescues either book.** That is the registered
consequence of reading 1 failing on the same-day label, and it is stronger than any of
the B-series verdicts: a gate can only choose among sessions, and there is no subset
of sessions defined by the weather on which the strategies are paid.

## 4. What the run says about its own inputs

**The trend threshold did not select.** I fixed 50% before looking; the leading
point-in-time name holds a median **+78%** into the open (p25 +44%, p75 +138%, p90
+222%), so 382 of 551 sessions are "trend days". The registration said the choice
would be shown against the distribution and not moved, and it is not moved — but it
is a mis-set threshold and I own it. It also did not matter: the per-trade figure on
the 169 non-trend sessions (−$13.32) is worse than on trend sessions (−$9.65), and
per session both lose; a threshold at p90 would carve out 55 sessions whose per-trade
is already in the table's better half and whose per-session would still be negative.
A re-registration at a higher threshold would be a new hypothesis with no mechanism
behind it, and I do not propose one.

**The ceiling from `ladder_and_regime` §4 does not transfer to the point-in-time
books.** There, on the survivor universe, hot / mixed / cold read −$2.95 / −$6.59 /
−$8.81 a trade, monotone, p = 0.024. Here: −$9.66 / −$11.42 / −$10.68 — mixed is the
worst bucket and the spread hot-to-cold is $1.02. Three things changed between the
two: the universe (survivors → point-in-time), the floor (`first_seen`), and the
calendar (378 → 551 sessions), and this run cannot say which one removed the
ordering. What it can say is that on the books MCL actually trades, the same-day
regime does not separate its trades — which is consistent with H-B4's proxy finding
nothing to act on at 07:00.

**Hot days are more trades, not better trades.** 1,596 MCL trades on 182 hot sessions
(8.8 a session) against 1,030 on 187 cold (5.5 a session), at the same per-trade loss.
Cameron's 16× on the mean day is a size and selection response on days with more to
choose from; these strategies' response to the same days is to fire more often at the
same quality. That is the difference between his record and this book, in one line.

## 5. A1 and A3

**A1 is free.** `databento_fetch` priced the six names' 1-minute bars for 2026-09-16 at
**$0.0000, 0.3 MB** — inside the free window — and bought nothing (dry run). But the
scoped pull writes `<day>.dbn.zst`, not the `_0400_0930` slice `window_slices` reads,
and a replay through the point-in-time machinery also needs the screen simulated for
that day, which needs the daily bars for the prior close. The right pull is therefore
the archive extension itself (§7 item 1), which is also what **A3** needs: the
pre-market 1-minute window for the whole market and the daily bars, 2026-09-05 through
2026-09-17. Both are priced with `databento_universe` without `--confirm` before
anything is bought — commands below. If the estimate is inside the free window, the
extension unblocks A1, A3 and the screen validation together.

## 6. What this is not

Not out of sample. Not a gate — the same-day and trend labels are known after the
fact; the actionable ones (lagged, 07:00) are printed and were read elsewhere. Not A3.
Not a size study: what Cameron changes on a hot day is size and selection, and a size
response on the paying sessions would be the natural next registration *if* reading 1
had passed; it did not, and a size response to a negative expectancy is a faster loss.

## Commands already run

```
python -m common.luck_vs_edge --jobs 8
python -m common.databento_fetch --pairs docs\research\replay_20260916_pairs.json --dataset XNAS.BASIC --schemas ohlcv-1m --lookback 0 --max-cost 0.01
```
