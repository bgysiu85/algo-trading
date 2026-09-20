# ORB on the point-in-time universe — RESULT (2026-09-17)

Registration: `docs/research/REGISTERED_orb_pit.md` (D.0–D.7 and E, all PRE-RUN). Tape: XNAS.BASIC, RTH bars.

Raw reports:
- `var\reports\orb_grid_pit.txt` / `_cells.csv`: BASIC-screened PIT. 6,151 of 6,170 read (18 with no file, 1 with no RTH bars, 83 from the D.7 fallback). Split 2025-08-07.
- `var\reports\orb_grid_pit_itch.txt` / `_cells.csv`: ITCH-screened PIT (amendment E). 6,544 of 6,564 read (19 with no file, 1 with no RTH bars, 103 from the fallback). Split 2025-08-07.
- `var\reports\orb_grid_survivor_v2.txt` / `_cells.csv`: the control. Same code, 27,758 read, no fallback.

## Verdict

**D.4 row 1 on both PIT universes: the baseline fails criteria 1, 2, 3, 5 and 6. The survivor edge was the stage-2 leak. ORB is closed at baseline on this design.** Grid leads are not rescued, there is no paper trading, and `holdout.json` stays unspent. **Predictions D.5 and E.3 both held.**

## Baseline (15 · structure · none · r_2)

| criterion | BASIC-screened PIT | ITCH-screened PIT (E) | verdict (both) | survivor re-run |
|---|---|---|---|---|
| 1 drop-top-3 / -5 | −$10,092 / −$10,829 | −$11,574 / −$12,310 | FAIL | +$14,381 / +$13,571 |
| 2 bootstrap P(total>0) | 0.001 | 0.000 [−14,751, −6,015] | FAIL | 1.000 |
| 3 per trade | **−$4.58** (net −$8,826, 1,926 trades) | **−$5.01** (net −$10,308, 2,057 trades) | FAIL | +$3.33 (net +$16,218) |
| 4 trades | 1,926 | 2,057 | pass | 4,875 |
| 5 halves | −$3,084 / −$5,742 | −$4,301 / −$6,006 | FAIL | +$7,050 / +$9,168 |
| 6 §10.2 split (D.2 fixed, 3 rules) | pass +$594 (402 d) / fail −$9,420 | pass +$534 (420 d) / fail −$10,842 | FAIL (sign reverses) | pass +$8,795 / fail +$9,027 |
| 7 boundary (C.1) | wins 15, −$4.03: interior | wins 15, −$4.60: interior | met, moot | wins 45: NOT MET |

**Win rate:** 31.2% BASIC-screened, 30.9% ITCH-screened, 43.7% survivor.

**Exits (both PIT runs):** about 65% stop, 27% target, 8% session end.

**Grid:** 0 of 110 readable cells are positive on either PIT run. The best is −$2.54 on BASIC-screened and −$1.87 on ITCH-screened (5 · structure · zone · trail_pct, 599 trades). The survivor run has 101 of 120 positive.

**Pre-run tape check (E.1):** 90 spike bars in 2,233,659 RTH bars (0.40 per 10k), with no hot bucket. ORB's RTH window does not carry the pre-market TRF defect.

## The leak, priced (BASIC-screened PIT vs survivor; baseline-only replay that reproduces both totals)

- **Survivor − PIT:** +$7.91/trade. Delta drop-top-5: +$22,530.
- **In both universes:** 1,083 trades at −$2.35/trade, with identical trades in both runs.
- **PIT only:** 843 trades at −$7.46/trade.
- **Survivor only** (names that needed the day's own bar to be selected): 3,792 trades at **+$4.95/trade**. This is the only profitable group.

## Confirmations

- **D.2 stands.** With the screen at 09:45, the survivor criterion-6 split moves from +$31,103 / −$13,281 to +$8,795 / +$9,027.
- **Criterion 7 was never passable on the survivors.** With 45 in the grid, the best length is the upper edge.

## Leads, not results

- **The 09:45-screen pass arm:** +$594 / +$534 on the two PIT runs, on 3 of the 4 rules.
- **`relative_volume_10d_calc` is untested.**

Neither lead is pursued without its own registration and fresh data.

## For PROGRAM_INDEX §7

- **Items 2 and 3: done.** ORB is closed at baseline on both PIT universes (−$4.58 BASIC-screened, −$5.01 ITCH-screened; leak +$7.91/trade).
- **Item 4:** moot.
- **Item 5:** not started, and should not be.
- **Archive defect** for the owner of `common/`: `claude/archive_defect_daily_chunk_start_20260917.md`.
