# A1 and A3 — the 09-16 replay agrees, and the fixed code loses what the live trader lost

2026-09-17. Under `docs/research/REGISTERED_luck_vs_edge.md` §4. The archive was extended
through 2026-09-17 at $0.00 (daily bars, the 04:00–09:30 slices, the 15:55–16:05 closing
slices), the repaired closes re-emitted, the screen simulated forward over the new
sessions only (`screen_sim --after 2026-09-05`, into `screen_pairs_pit_ext.json`, 7
sessions, 52 symbol-days, 0 of 52 against an unrepaired close), and the published MCL and
MC5 engines run over them through the same runner as every point-in-time study. Raw:
`D:\Trading\Claude outputs\screen_sim_ext_20260917.txt`, `pit_ext_books_20260917.txt`.
Live figures are the paper fill logs' `trade_pnl` (`var/fills/mcl_fills_*.csv`), the
same basis as the analysis chat's 134-round-trip headline; backtest figures are engine
net (commission in) less friction, at **$4.26** unless stated. These September sessions
are after the 2026-03-30 TRF change, so the XNAS.BASIC 08:00 defect does not touch them.

---

## 0. In one paragraph

**A1: the replay is green.** On 2026-09-16 the simulated screen surfaces FTFT, MEDS,
NAMI, RETO (and ZTG), and the backtest books **MCL +$36.54 over 11 trades, MC5 +$12.41
over 11** — the market reading is confirmed without relying on live fills, as the
handover asked. Live that day: MCL +$39.66, MC5 +$173.29. **A3: over 09-09..09-16 the
fixed code loses $783 where the live trader lost $762.** MCL −$498.95 (52 trades) and
MC5 −$284.33 (61) in the backtest against −$388.27 (41) and −$373.57 (93) live. The
three defects fixed on `main` this week — the stale bar at 04:00, the trail seeded from
the signal close, the ghost position — account for **none of the six-session loss in
aggregate**: a trader that never had them, on a simulated version of the same
watchlist, loses the same money. The loss is the strategies.

---

## 1. A1 — 2026-09-16, session by session detail

| | trades | net at $1.00 / $4.26 / $8.92 | names |
|---|---:|---|---|
| MCL backtest | 11 | +$72.40 / **+$36.54** / −$14.72 | FTFT +49.25 (window close), MEDS +30.53, RETO +25.38, NAMI +18.47, seven small stops |
| MC5 backtest | 11 | +$48.27 / **+$12.41** / −$38.85 | MEDS +91.41, RETO +54.60, FTFT +28.50, seven stops |
| MCL live | 9 closes | +$39.66 | FTFT +100.62, NAMI +23.63, MEDS +21.63, VEEA −36.37 at 04:00 (the stale-bar trade) |
| MC5 live | 10 closes | +$173.29 | MEDS +85.63, FTFT +86.62, NAMI +43.63, VEEA −36.37 at 04:00 |

Same names, same shape, same sign. The backtest is smaller than the live day for MC5
because live MC5 re-armed into MEDS four times between 06:00 and 06:12 and caught the
+$85 leg; the backtest took MEDS twice in that hour for +$91 and −$18. The VEEA −$36.37 at
04:00 on both strategies is the stale-bar defect (`session_open_defects_FIXED`), and the
backtest has no such trade — that single pair is the only place in this session where a
fix is visible, worth +$72.74 across the two books.

## 2. A3 — 09-09..09-16, the backtest with the fixes against the live record

| session | MCL backtest | MCL live | MC5 backtest | MC5 live | names in common |
|---|---:|---:|---:|---:|---|
| 09-09 | (45.41) · 6 | (70.26) · 6 | (82.20) · 11 | — | SUNE |
| 09-10 | (145.70) · 7 | (57.24) · 6 | (94.61) · 6 | (166.94) · 16 | TNON, SUNE / TNON |
| 09-11 | (16.47) · 13 | +46.12 · 5 | +8.89 · 14 | (203.03) · 43 | LBGJ, TNON / FTFT, LBGJ, TNON, XRTX |
| 09-14 | (237.98) · 8 | (294.97) · 8 | (49.78) · 6 | (43.46) · 12 | BMM, CRBP, SCNI / BMM |
| 09-15 | (89.93) · 7 | (51.58) · 7 | (79.04) · 13 | (133.43) · 12 | BDRX, MYSZ, NAMI, TNON, VEEA / BDRX, NAMI, TNON, VEEA, VRA |
| 09-16 | +36.54 · 11 | +39.66 · 9 | +12.41 · 11 | +173.29 · 10 | FTFT, MEDS, NAMI, RETO |
| **total** | **(498.95) · 52** | **(388.27) · 41** | **(284.33) · 61** | **(373.57) · 93** | |

Both books: backtest **(783.28)** over 113 trades, live **(761.84)** over 134. At $1.00
friction the backtest is (414.90); at $8.92, (1,309.86). The live basis sits between the
first two.

**Read this the right way round.** The question was how much of the live loss the three
defects explain. The answer is that a trader without them, on the same six mornings,
loses the same amount. What differs is *where*: the backtest's MCL is worse on 09-10 and
09-14, its MC5 is far better on 09-11 (+$9 against −$203 over 43 live closes — the MC5
re-arm behaviour the analysis chat has registered separately), and 09-16 matches. Those
are differences in the watchlist and in how often MC5 re-enters, not in the three fixes.

## 3. The two things that limit the comparison

- **The universes are not the same.** The simulated screen and the live `tv_feed` list
  share some names each morning (09-16: all four; 09-09: SUNE only) and not others. That
  is §7 item 1 — the screen validation — and it is now runnable, because the archive
  reaches the live sessions; it needs the per-session live watchlists, which
  `archive_watchlist` stamps a day late (`prior_close_check_20260912.md`), so the
  pairing has to be done carefully and belongs with the chat that owns the screen line.
- **The bases differ by a few dollars a trade.** Backtest net carries tiered commission
  and a modelled $4.26 round trip; live `trade_pnl` carries real fills and IB's actual
  commission. The three friction levels bracket it.

## 4. What the seven-session extension must not be read as

`pit_ext_books_20260917.txt` also prints H-B1's four books over these 52 symbol-days,
because the same runner writes them, and its verdict line says **PASSES** for MCL-skip1
on 59 trades over 7 sessions. That is not a reading. The population check on the same
page says the book is not the published one; the sample is sessions, not trades, and
seven of them is a week; the registered verdict on 6,170 symbol-days is NOTHING. Printed
here so it is not found later and quoted.

## 5. Where this leaves the 09-17 handover

| ask | answer |
|---|---|
| A1 replay 09-16 | **green in the backtest** (+$36.54 MCL, +$12.41 MC5); same names, same shape as live |
| A2 luck or edge | **neither**; no regime bucket pays either strategy |
| A3 the three fixes | **explain none of the six-session loss** in aggregate; the loss is the strategies |
| H-B1 / H-B3 / H-B4 | NOTHING × 3, each reading as random removal of the same trade count |
| H-B2 | blocked on the concurrency cap |
| B5 | nothing to combine |

Every B-series and Part A figure above was measured on the XNAS.BASIC point-in-time books
(6,170 symbol-days). The tape work in `screen_itch_RESULT_20260917.md` has since moved the
published baselines to XNAS.ITCH (6,564 symbol-days; MCL −$8.81). None of the verdicts
depends on the 08:00 hour before 2026-03-30 in direction, but none is a baseline on the
tape of record either. All four runners take `--pairs` and `--dataset`, so re-basing
them is four commands under the same registrations — a re-baselining, not a new
hypothesis — and I would do that before anything is built on top of them.

## Commands already run

```
python -m common.databento_universe --dataset XNAS.BASIC --schema ohlcv-1d --start 2026-09-05 --end 2026-09-17 --confirm
python -m common.databento_universe --dataset XNAS.BASIC --schema ohlcv-1m --window 04:00-09:30 --start 2026-09-05 --end 2026-09-17 --confirm
python -m common.databento_universe --dataset XNAS.BASIC --schema ohlcv-1m --window 15:55-16:05 --start 2026-09-04 --end 2026-09-16 --confirm
python -m common.regular_close --emit --accept auction_else_last --jobs 8
python -m common.screen_sim --after 2026-09-05 --out var\state\screen_pairs_pit_ext.json --report var\reports\screen_sim_ext.txt
python -m common.first_entry_skip --pairs var\state\screen_pairs_pit_ext.json --out var\reports\pit_ext_books.txt --csv var\reports\pit_ext_trades.csv --jobs 8
```
