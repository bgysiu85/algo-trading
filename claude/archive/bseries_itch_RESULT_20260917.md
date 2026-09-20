# The B-series and Part A, re-based on the ITCH v2 universe — nothing moves

2026-09-17. Under the PRE-RUN amendments to `REGISTERED_first_entry_skip.md` (B),
`REGISTERED_range_rank.md` (A), `REGISTERED_cold_veto.md` (A) and
`REGISTERED_luck_vs_edge.md` (A): the same four runners, the same rules, seed and
thresholds, on `screen_pairs_pit_itch_v2.json` (6,411 symbol-days, 550 sessions) with
XNAS.ITCH bars, the published universe since `screen_itch_v2_RESULT_20260917.md`. Raw:
`first_entry_skip_itch_20260917.txt`, `range_rank_itch_20260917.txt`,
`cold_veto_itch_20260917.txt`, `luck_vs_edge_itch_20260917.txt`,
`time_of_day_itch_20260917.txt` in `Claude outputs`. The population check matches the
published MCL count (3,908) on every report. All figures at **$4.26** unless stated.

---

## 0. In one paragraph

**Every verdict stands.** On the tape of record, none of the three "fewer losing
entries" gates beats removing the same number of trades at random, and Part A's
reading 1 fails on every paying label for both strategies. What changed is the
direction of the per-trade deltas: on BASIC the gates were worth a few tens of cents a
trade, inside random removal's band; on ITCH v2 three of the six gated cells are
*negative* per trade — skipping the first entry costs MCL $0.41 and MC5 $0.78 a trade,
the 07:00 veto costs MCL $0.16, the top-3 range gate costs MC5 $0.18 — so those cells
now read REFUSED (the denominators disagree) rather than NOTHING. Either word is "not a
pass". The B-series is closed on the published universe, and the time-of-day question
stays closed: every MCL block is negative at every friction and the named 07:45 cell
fails all four checks.

---

## 1. The gates, BASIC against ITCH v2

Per trade Δ is gated minus baseline at $4.26; the control is random removal of the same
trade count (2,000 draws, seed 20260916), p95 of the per-trade Δ; reading 1 also asks
for a $4.26 margin.

| gate | strategy | BASIC Δ/trade · p95 | BASIC verdict | **ITCH v2 Δ/trade · Δ/sym-day** | **p95** | **ITCH v2 verdict** |
|---|---|---|---|---|---|---|
| H-B1 skip first entry | MCL | +0.03 | NOTHING | **(0.41) · +2.46** | — | **REFUSED** |
| | MC5 | (1.05) / +4.71 | REFUSED | **(0.78) · +2.35** | — | **REFUSED** |
| H-B3 top-3 by range | MCL | +0.86 · +1.27 | NOTHING | **+0.67 · +3.35** | +1.37 | **NOTHING** |
| | MC5 | +0.96 · +1.34 | NOTHING | **(0.18) · +3.73** | +1.40 | **REFUSED** |
| H-B3 top-1 (reported) | MCL | +2.03 · +2.88 | would be NOTHING | +1.99 · +4.92 | +3.25 | would be NOTHING |
| | MC5 | +2.74 · +3.02 | would be NOTHING | +1.61 · +6.80 | +3.23 | would be NOTHING |
| H-B4 07:00 cold veto | MCL | +0.70 · +0.74 | NOTHING | **(0.16) · +1.46** | +0.67 | **REFUSED** |
| | MC5 | +0.89 · +1.03 | NOTHING | **+0.36 · +2.78** | +0.94 | **NOTHING** |

H-B1 has no abstention control (amendment A left it as registered); its readings 3 and
4 still "pass" at P = 1.000 for MCL and 0.981 for MC5, for the reason catalogued in §4
of the index — they measure trades less — and reading 1 refuses both. The cascade is
larger on ITCH than on BASIC (453 MCL-skip1 entries the baseline never took, 1,438 for
MC5) because the cleaner tape signals more often once a position is not in the way.

**Where the gates bind.** H-B3 could refuse 88.6% of MCL's entries (85% on BASIC) with a
median of ten to twelve names visible at signal time; H-B4 vetoed 341 of 550 sessions
(62.0%; 66% on BASIC), 240 by the count rule and 101 by the composite, with a median of
five names visible at 07:00. The veto's vetoed trades run (8.55)/t for MCL against
(9.14)/t admitted — on ITCH the cold-session trades are marginally *better* than the
ones the veto keeps, which is what the negative per-trade delta says.

**What the gates cost.** Top-3 removes five of MCL's ten best trades and five of MC5's;
the first-entry skip removes six and eight (QMMM +1,341 on 2025-09-09, UVIX +5,437 on
2026-07-01 among them). A losing book with its best trades removed is a more losing
book that happens to have fewer trades.

## 2. Part A2 — luck or edge, per session over all sessions in the bucket

| label | bucket | MCL BASIC /session | **MCL ITCH v2 /session** | ITCH v2 /trade | MC5 BASIC /session | **MC5 ITCH v2 /session** | ITCH v2 /trade |
|---|---|---|---|---|---|---|---|
| same-day regime | hot (181) | (84.74) | **(66.23)** | (7.64) | (211.21) | **(120.66)** | (8.25) |
| | mixed (182) | (83.39) | **(78.43)** | (10.78) | (171.76) | **(83.77)** | (7.00) |
| | cold (187) | (58.82) | **(47.07)** | (8.68) | (124.08) | **(97.75)** | (11.16) |
| trend day (leader ≥ 50%) | trend (379) | negative | **(63.16)** | (8.14) | negative | **(102.37)** | (7.67) |
| | not (171) | negative | **(65.07)** | (11.52) | negative | **(96.87)** | (11.82) |
| 07:00 reading | warm (148) | negative | **(100.50)** | (9.54) | negative | **(136.85)** | (7.77) |
| | cold (101) | negative | **(72.67)** | (9.81) | negative | **(102.37)** | (8.48) |

Reading 1 (a positive per-session H on the paying bucket, both halves, drop-top-3
sessions) **fails on every label for both strategies**; reading 2 is not read. The
shape is the BASIC shape: the same-day-hot bucket is not the best per session for MCL
(mixed is worst, cold is least bad because it trades least — 1,014 trades against
1,570 hot), per trade is flat across the weather, and a hot day is more trades at the
same loss. The trend-day flag at 50% again catches 69% of sessions (379 of 550), so it
is a description of the universe rather than a partition of it. The regime labels are
the BASIC daily archive's on both runs, by design, so the only thing that moved between
the two tables is the books.

## 3. Time of day, descriptive

Every MCL block is negative at $1.00, $4.26 and $8.92; the best is 06:30–07:00 at
(6.54)/t, the worst 05:30–06:00 at (13.13)/t. The named 07:45–08:00 cell: 150 trades,
(944.02), (6.29)/t, **fails** positive-at-all-frictions, both-halves, drop-top-3 and
session-median. The 08:00–08:30 block that read (16.83)/t on the BASIC table reads (9.95)/t
here, and 07:30–08:00 goes from (16.01) to (8.27) — the withdrawn BASIC rows were the
TRF prints, as the tape work said — and nothing paying is underneath them. MC5's 04:00–04:30 block shows +2,007 at $1.00 and (167) at $4.26 over
667 trades; its drop-top-3 is (6,761), i.e. the block is UVIX's single +5,437 trade and
nothing else. Not a cell, not a reading.

## 4. What this closes and what it does not

- **Closes the B-series on the published universe.** H-B1, H-B3, H-B4: not a pass on
  BASIC, not a pass on ITCH v2, in the same direction, by the same control. B5 has
  nothing to combine. H-B2 still waits on the concurrency cap (§7 item 15).
- **Closes Part A2 on the published universe.** No regime bucket, actionable or
  after-the-fact, pays either strategy.
- **Keeps the time-of-day question closed.**
- **Does not** re-open any BASIC result doc; those stand as BASIC results and are not
  edited. **Does not** touch `holdout.json` or `D:\TradingProd`.
- The tooling change that made this readable: the population check now keys on the
  universe file (3,955 / 3,960 / 3,908 for BASIC / ITCH p50 / ITCH v2, "none" for an
  unlisted file), and `luck_vs_edge` takes `--daily-dataset` for the regime and refuses
  a trades CSV, universe file or readings file from different runs.

## Commands run

```
python -m common.first_entry_skip --pairs var\state\screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH --out var\reports\first_entry_skip_itch.txt --csv var\reports\first_entry_skip_itch_trades.csv --jobs 8
python -m common.range_rank --pairs var\state\screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH --out var\reports\range_rank_itch.txt --csv var\reports\range_rank_itch_trades.csv --jobs 8
python -m common.cold_veto --pairs var\state\screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH --out var\reports\cold_veto_itch.txt --csv var\reports\cold_veto_itch_trades.csv --readings var\reports\cold_veto_readings_itch.csv --jobs 8
python -m common.luck_vs_edge --trades var\reports\first_entry_skip_itch_trades.csv --readings var\reports\cold_veto_readings_itch.csv --pairs var\state\screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH --daily-dataset XNAS.BASIC --out var\reports\luck_vs_edge_itch.txt --labels-csv var\reports\luck_vs_edge_labels_itch.csv --jobs 8
python -m common.time_of_day --csv var\reports\first_entry_skip_itch_trades.csv --out var\reports\time_of_day_itch.txt
```
