# W03-0008 — Entry-count cap (H-C1): no 4th+ entry per strategy per symbol-day — RESULT

**Verdict: NOTHING for both strategies.** MCL cap 3 REFUSED (per trade (0.33), per symbol-day +0.14 — MCL's late entries are the *better* trades). MC5 cap 3 NOTHING (per trade +0.20 vs the 4.26 bar; random-removal p95 +0.38; saves +5,921.48 over 550 sessions vs ~+5,193 for a random cut of the same 556 trades). No usable day/sequence-state marker for the paper cuts; nothing for Ben to decide.

- Registration: `docs/research/REGISTERED_entry_cap.md` (commit ecf93a5, PRE-RUN)
- Module + tests: `common/entry_cap.py`, `tests/common/test_entry_cap.py` (commit b26d286; 10 pass)
- Raw report: `D:\Trading\Claude outputs\entry_cap_20260924.txt` (verbatim below)
- monday Result doc: https://ben-siu.monday.com/docs/5031523054 · Styled page: https://claude.ai/artifact/G2kY692yirhRDady2SSaQc
- Live pre-read: `claude/paper_cuts_20260924_RESULT.md`

## Next steps
- W03-0008 — Done (this result). No follow-up registered.
- W02-0019 — give-back cap on MC5 (fewer trades) remains the live lever for the paper cuts.
- W02-0018 — exit replay incl. bid-based stop (cheaper exits) remains the other lever.

## Raw report

```
# generated 2026-09-24 04:15:34 UTC
# common.entry_cap csv=var/reports/dist_from_high_gate_trades.csv registered=docs/research/REGISTERED_entry_cap.md

W03-0008 / H-C1: THE ENTRY-COUNT CAP -- NO 4TH-OR-LATER ENTRY PER STRATEGY PER SYMBOL-DAY

  registered  docs/research/REGISTERED_entry_cap.md (commit ecf93a5, before this module existed)
  books       var/reports/dist_from_high_gate_trades.csv (ungated baselines, no re-simulation -- exact, see §1)
  universe    var/state/screen_pairs_pit_itch_v2.json   bars XNAS.ITCH
  550 sessions   6,411 symbol-days   halves cut at 2025-08-07
  100 shares   commission in, friction per round trip   verdict at $4.26

POPULATION CHECK

  MCL trades here  3,908   registered 3,908   matches
  MC5 trades here  6,462   registered 6,462   matches
  published count     3,908   matches
  MCL ordinals run 1..n in every symbol-day: yes
  MC5 ordinals run 1..n in every symbol-day: yes

THE ORDINAL TABLE (the live pre-read's cut, on the backtest books, $4.26)

  MCL
    entry #1    2,299 trades   net  (20,836.91)   per trade   (9.06)   winners 22.7%
    entry #2      968 trades   net   (9,745.84)   per trade  (10.07)   winners 23.2%
    entry #3      407 trades   net   (3,587.00)   per trade   (8.81)   winners 22.1%
    entry #4      153 trades   net     (992.33)   per trade   (6.49)   winners 25.5%
    entry #5+      81 trades   net        98.96   per trade     1.22   winners 25.9%
    all         3,908 trades   net  (35,063.12)   per trade   (8.97)

  MC5
    entry #1    3,444 trades   net  (24,794.15)   per trade   (7.20)   winners 22.7%
    entry #2    1,687 trades   net  (18,135.20)   per trade  (10.75)   winners 23.3%
    entry #3      775 trades   net   (6,513.24)   per trade   (8.40)   winners 22.6%
    entry #4      318 trades   net   (3,326.68)   per trade  (10.46)   winners 23.6%
    entry #5+      238 trades   net   (2,594.80)   per trade  (10.90)   winners 25.2%
    all         6,462 trades   net  (55,364.07)   per trade   (8.57)

THE BOOKS

  MCL
    at $1.00  trades  3,908   net  (22,323.04)   per trade   (5.71)   per symbol-day  (3.48)
    at $4.26  trades  3,908   net  (35,063.12)   per trade   (8.97)   per symbol-day  (5.47)
    at $8.92  trades  3,908   net  (53,274.40)   per trade  (13.63)   per symbol-day  (8.31)
    halves @ $4.26    early 1,753   (8.94)/t (15,674.95)   late 2,155   (9.00)/t (19,388.17)
    drop top 3 @ $4.26  (37,384.33)   win rate 23.0%

  MCL-cap3
    at $1.00  trades  3,674   net  (22,192.51)   per trade   (6.04)   per symbol-day  (3.46)
    at $4.26  trades  3,674   net  (34,169.75)   per trade   (9.30)   per symbol-day  (5.33)
    at $8.92  trades  3,674   net  (51,290.59)   per trade  (13.96)   per symbol-day  (8.00)
    halves @ $4.26    early 1,638   (8.92)/t (14,613.96)   late 2,036   (9.61)/t (19,555.79)
    drop top 3 @ $4.26  (36,456.96)   win rate 22.8%

  MCL-cap2
    at $1.00  trades  3,267   net  (19,932.33)   per trade   (6.10)   per symbol-day  (3.11)
    at $4.26  trades  3,267   net  (30,582.75)   per trade   (9.36)   per symbol-day  (4.77)
    at $8.92  trades  3,267   net  (45,806.97)   per trade  (14.02)   per symbol-day  (7.15)
    halves @ $4.26    early 1,454   (9.24)/t (13,436.74)   late 1,813   (9.46)/t (17,146.01)
    drop top 3 @ $4.26  (32,869.96)   win rate 22.9%

  MCL-cap4
    at $1.00  trades  3,827   net  (22,686.06)   per trade   (5.93)   per symbol-day  (3.54)
    at $4.26  trades  3,827   net  (35,162.08)   per trade   (9.19)   per symbol-day  (5.48)
    at $8.92  trades  3,827   net  (52,995.90)   per trade  (13.85)   per symbol-day  (8.27)
    halves @ $4.26    early 1,713   (8.98)/t (15,388.46)   late 2,114   (9.35)/t (19,773.62)
    drop top 3 @ $4.26  (37,449.29)   win rate 22.9%

  MCL-cap1
    at $1.00  trades  2,299   net  (13,342.17)   per trade   (5.80)   per symbol-day  (2.08)
    at $4.26  trades  2,299   net  (20,836.91)   per trade   (9.06)   per symbol-day  (3.25)
    at $8.92  trades  2,299   net  (31,550.25)   per trade  (13.72)   per symbol-day  (4.92)
    halves @ $4.26    early 1,030  (10.07)/t (10,375.93)   late 1,269   (8.24)/t (10,460.98)
    drop top 3 @ $4.26  (23,057.14)   win rate 22.7%

  MC5
    at $1.00  trades  6,462   net  (34,297.95)   per trade   (5.31)   per symbol-day  (5.35)
    at $4.26  trades  6,462   net  (55,364.07)   per trade   (8.57)   per symbol-day  (8.64)
    at $8.92  trades  6,462   net  (85,476.99)   per trade  (13.23)   per symbol-day (13.33)
    halves @ $4.26    early 2,901   (8.70)/t (25,247.05)   late 3,561   (8.46)/t (30,117.02)
    drop top 3 @ $4.26  (62,632.98)   win rate 23.0%

  MC5-cap3
    at $1.00  trades  5,906   net  (30,189.03)   per trade   (5.11)   per symbol-day  (4.71)
    at $4.26  trades  5,906   net  (49,442.59)   per trade   (8.37)   per symbol-day  (7.71)
    at $8.92  trades  5,906   net  (76,964.55)   per trade  (13.03)   per symbol-day (12.01)
    halves @ $4.26    early 2,652   (8.52)/t (22,604.18)   late 3,254   (8.25)/t (26,838.41)
    drop top 3 @ $4.26  (56,711.50)   win rate 22.9%

  MC5-cap2
    at $1.00  trades  5,131   net  (26,202.29)   per trade   (5.11)   per symbol-day  (4.09)
    at $4.26  trades  5,131   net  (42,929.35)   per trade   (8.37)   per symbol-day  (6.70)
    at $8.92  trades  5,131   net  (66,839.81)   per trade  (13.03)   per symbol-day (10.43)
    halves @ $4.26    early 2,301   (8.32)/t (19,150.74)   late 2,830   (8.40)/t (23,778.61)
    drop top 3 @ $4.26  (50,198.26)   win rate 22.9%

  MC5-cap4
    at $1.00  trades  6,224   net  (32,479.03)   per trade   (5.22)   per symbol-day  (5.07)
    at $4.26  trades  6,224   net  (52,769.27)   per trade   (8.48)   per symbol-day  (8.23)
    at $8.92  trades  6,224   net  (81,773.11)   per trade  (13.14)   per symbol-day (12.76)
    halves @ $4.26    early 2,793   (8.61)/t (24,039.68)   late 3,431   (8.37)/t (28,729.59)
    drop top 3 @ $4.26  (60,038.18)   win rate 22.9%

  MC5-cap1
    at $1.00  trades  3,444   net  (13,566.71)   per trade   (3.94)   per symbol-day  (2.12)
    at $4.26  trades  3,444   net  (24,794.15)   per trade   (7.20)   per symbol-day  (3.87)
    at $8.92  trades  3,444   net  (40,843.19)   per trade  (11.86)   per symbol-day  (6.37)
    halves @ $4.26    early 1,547   (7.36)/t (11,386.61)   late 1,897   (7.07)/t (13,407.54)
    drop top 3 @ $4.26  (32,042.08)   win rate 22.7%

====================================================================================================
MCL
====================================================================================================

--- MCL-cap3 (PRIMARY) ---

THE VERDICT: MCL-cap3 against MCL (registered readings 1-5, $4.26)

  1. per trade -0.33 (margin 4.26)   per symbol-day +0.14
  2. early half  per trade +0.02  per symbol-day +0.17     late half  per trade -0.61  per symbol-day -0.03
  3. drop-top-3 level  MCL-cap3 (36,456.96)  MCL (37,384.33)     drop-top-3 delta 567.17
  4. cluster bootstrap on the delta  P(total > 0) = 0.841  [(1,114.65), 2,519.87]  over 1,177 symbols
  5. abstention control: 234 of 3,908 trades removed at random, 2000 draws
       per trade      random p05 -0.32  p50 +0.02  p95 +0.26   the gate -0.33
       per symbol-day random p05 +0.14  p50 +0.34  p95 +0.48   the gate +0.14

  REFUSED: the two denominators disagree: per trade -0.33, per symbol-day +0.14

  cost: 1 of MCL's top-10 trades at $4.26 are absent from MCL-cap3
    OCTO   2025-09-08  08:33 ET      502.34
  cascade: 0 MCL-cap3 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 234 of 3,908 trades removed (6.0%) in 153 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed   234 per trade   (0.56)   kept 3,674 per trade   (6.04)   gap +5.48
    at $4.26  removed   234 per trade   (3.82)   kept 3,674 per trade   (9.30)   gap +5.48
    at $8.92  removed   234 per trade   (8.48)   kept 3,674 per trade  (13.96)   gap +5.48

  POSITIONAL CONTROL (reported, not scored): same 153 symbol-days, same 234 trades removed, random positions, 2000 draws
    per trade  random p05 -0.41  p50 -0.20  p95 +0.02   the cap -0.33   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 08:25, 63% at/after 08:00   kept median 07:18, 38% at/after 08:00
    before 08:00: removed    87     0.87/t   kept 2,263   (8.91)/t
    from   08:00: removed   147   (6.59)/t   kept 1,411   (9.93)/t

--- MCL-cap2 (BOUNDARY) ---

THE VERDICT: MCL-cap2 against MCL (registered readings 1-5, $4.26)

  1. per trade -0.39 (margin 4.26)   per symbol-day +0.70
  2. early half  per trade -0.30  per symbol-day +0.35     late half  per trade -0.46  per symbol-day +0.35
  3. drop-top-3 level  MCL-cap2 (32,869.96)  MCL (37,384.33)     drop-top-3 delta 4,081.71
  4. cluster bootstrap on the delta  P(total > 0) = 1.000  [2,188.68, 6,546.69]  over 1,177 symbols
  5. abstention control: 641 of 3,908 trades removed at random, 2000 draws
       per trade      random p05 -0.55  p50 +0.02  p95 +0.47   the gate -0.39
       per symbol-day random p05 +0.62  p50 +0.91  p95 +1.14   the gate +0.70

  REFUSED: the two denominators disagree: per trade -0.39, per symbol-day +0.70

  cost: 1 of MCL's top-10 trades at $4.26 are absent from MCL-cap2
    OCTO   2025-09-08  08:33 ET      502.34
  cascade: 0 MCL-cap2 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 641 of 3,908 trades removed (16.4%) in 407 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed   641 per trade   (3.73)   kept 3,267 per trade   (6.10)   gap +2.37
    at $4.26  removed   641 per trade   (6.99)   kept 3,267 per trade   (9.36)   gap +2.37
    at $8.92  removed   641 per trade  (11.65)   kept 3,267 per trade  (14.02)   gap +2.37

  POSITIONAL CONTROL (reported, not scored): same 407 symbol-days, same 641 trades removed, random positions, 2000 draws
    per trade  random p05 -0.52  p50 -0.15  p95 +0.17   the cap -0.39   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 08:13, 55% at/after 08:00   kept median 07:12, 37% at/after 08:00
    before 08:00: removed   288   (4.18)/t   kept 2,062   (9.16)/t
    from   08:00: removed   353   (9.29)/t   kept 1,205   (9.71)/t

--- MCL-cap4 (BOUNDARY) ---

THE VERDICT: MCL-cap4 against MCL (registered readings 1-5, $4.26)

  1. per trade -0.22 (margin 4.26)   per symbol-day -0.02
  2. early half  per trade -0.04  per symbol-day +0.04     late half  per trade -0.36  per symbol-day -0.06
  3. drop-top-3 level  MCL-cap4 (37,449.29)  MCL (37,384.33)     drop-top-3 delta (392.66)
  4. cluster bootstrap on the delta  P(total > 0) = 0.496  [(1,803.17), 1,187.13]  over 1,177 symbols
  5. abstention control: 81 of 3,908 trades removed at random, 2000 draws
       per trade      random p05 -0.18  p50 +0.01  p95 +0.14   the gate -0.22
       per symbol-day random p05 +0.00  p50 +0.12  p95 +0.20   the gate -0.02

  NOTHING: fails 1 (per trade >= 4.26 and per symbol-day > 0); 2 (both halves, both denominators); 3 (drop-top-3 on the level and on the delta); 4 (cluster bootstrap on the delta, P=0.496 < 0.95); 5 (abstention control: per trade -0.22 does not beat random removal's p95 +0.14)

  cost: 1 of MCL's top-10 trades at $4.26 are absent from MCL-cap4
    OCTO   2025-09-08  08:33 ET      502.34
  cascade: 0 MCL-cap4 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 81 of 3,908 trades removed (2.1%) in 59 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed    81 per trade     4.48   kept 3,827 per trade   (5.93)   gap +10.41
    at $4.26  removed    81 per trade     1.22   kept 3,827 per trade   (9.19)   gap +10.41
    at $8.92  removed    81 per trade   (3.44)   kept 3,827 per trade  (13.85)   gap +10.41

  POSITIONAL CONTROL (reported, not scored): same 59 symbol-days, same 81 trades removed, random positions, 2000 draws
    per trade  random p05 -0.32  p50 -0.15  p95 +0.01   the cap -0.22   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 08:28, 68% at/after 08:00   kept median 07:22, 39% at/after 08:00
    before 08:00: removed    26     4.69/t   kept 2,324   (8.69)/t
    from   08:00: removed    55   (0.42)/t   kept 1,503   (9.95)/t

REPORTED, NOT SCORED: MCL-cap1 against MCL

  would read REFUSED: the two denominators disagree: per trade -0.09, per symbol-day +2.22
  per trade -0.09   per symbol-day +2.22   boot P 1.000

  WHAT THE CAP TOUCHED: 1,609 of 3,908 trades removed (41.2%) in 968 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed 1,609 per trade   (5.58)   kept 2,299 per trade   (5.80)   gap +0.22
    at $4.26  removed 1,609 per trade   (8.84)   kept 2,299 per trade   (9.06)   gap +0.22
    at $8.92  removed 1,609 per trade  (13.50)   kept 2,299 per trade  (13.72)   gap +0.22

  POSITIONAL CONTROL (reported, not scored): same 968 symbol-days, same 1,609 trades removed, random positions, 2000 draws
    per trade  random p05 -0.26  p50 +0.38  p95 +1.05   the cap -0.09   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 07:48, 47% at/after 08:00   kept median 07:06, 35% at/after 08:00
    before 08:00: removed   857   (7.47)/t   kept 1,493   (9.16)/t
    from   08:00: removed   752  (10.41)/t   kept   806   (8.88)/t

====================================================================================================
MC5
====================================================================================================

--- MC5-cap3 (PRIMARY) ---

THE VERDICT: MC5-cap3 against MC5 (registered readings 1-5, $4.26)

  1. per trade +0.20 (margin 4.26)   per symbol-day +0.92
  2. early half  per trade +0.18  per symbol-day +0.41     late half  per trade +0.21  per symbol-day +0.51
  3. drop-top-3 level  MC5-cap3 (56,711.50)  MC5 (62,632.98)     drop-top-3 delta 5,398.99
  4. cluster bootstrap on the delta  P(total > 0) = 1.000  [4,069.32, 7,805.31]  over 1,447 symbols
  5. abstention control: 556 of 6,462 trades removed at random, 2000 draws
       per trade      random p05 -0.78  p50 +0.07  p95 +0.38   the gate +0.20
       per symbol-day random p05 +0.02  p50 +0.81  p95 +1.10   the gate +0.92

  NOTHING: fails 1 (per trade >= 4.26 and per symbol-day > 0); 5 (abstention control: per trade +0.20 does not beat random removal's p95 +0.38)

  cost: 0 of MC5's top-10 trades at $4.26 are absent from MC5-cap3
  cascade: 0 MC5-cap3 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 556 of 6,462 trades removed (8.6%) in 318 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed   556 per trade   (7.39)   kept 5,906 per trade   (5.11)   gap -2.28
    at $4.26  removed   556 per trade  (10.65)   kept 5,906 per trade   (8.37)   gap -2.28
    at $8.92  removed   556 per trade  (15.31)   kept 5,906 per trade  (13.03)   gap -2.28

  POSITIONAL CONTROL (reported, not scored): same 318 symbol-days, same 556 trades removed, random positions, 2000 draws
    per trade  random p05 -0.02  p50 +0.18  p95 +0.39   the cap +0.20   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 07:50, 47% at/after 08:00   kept median 07:20, 38% at/after 08:00
    before 08:00: removed   297  (11.02)/t   kept 3,658   (7.28)/t
    from   08:00: removed   259  (10.23)/t   kept 2,248  (10.15)/t

--- MC5-cap2 (BOUNDARY) ---

THE VERDICT: MC5-cap2 against MC5 (registered readings 1-5, $4.26)

  1. per trade +0.20 (margin 4.26)   per symbol-day +1.94
  2. early half  per trade +0.38  per symbol-day +0.95     late half  per trade +0.06  per symbol-day +0.99
  3. drop-top-3 level  MC5-cap2 (50,198.26)  MC5 (62,632.98)     drop-top-3 delta 11,810.29
  4. cluster bootstrap on the delta  P(total > 0) = 1.000  [9,079.44, 15,538.03]  over 1,447 symbols
  5. abstention control: 1,331 of 6,462 trades removed at random, 2000 draws
       per trade      random p05 -1.07  p50 +0.13  p95 +0.70   the gate +0.20
       per symbol-day random p05 +0.92  p50 +1.89  p95 +2.34   the gate +1.94

  NOTHING: fails 1 (per trade >= 4.26 and per symbol-day > 0); 5 (abstention control: per trade +0.20 does not beat random removal's p95 +0.70)

  cost: 1 of MC5's top-10 trades at $4.26 are absent from MC5-cap2
    WVVIP  2026-08-25  05:35 ET      534.33
  cascade: 0 MC5-cap2 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 1,331 of 6,462 trades removed (20.6%) in 775 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed 1,331 per trade   (6.08)   kept 5,131 per trade   (5.11)   gap -0.98
    at $4.26  removed 1,331 per trade   (9.34)   kept 5,131 per trade   (8.37)   gap -0.98
    at $8.92  removed 1,331 per trade  (14.00)   kept 5,131 per trade  (13.03)   gap -0.98

  POSITIONAL CONTROL (reported, not scored): same 775 symbol-days, same 1,331 trades removed, random positions, 2000 draws
    per trade  random p05 +0.11  p50 +0.47  p95 +0.85   the cap +0.20   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 07:45, 44% at/after 08:00   kept median 07:20, 37% at/after 08:00
    before 08:00: removed   740   (8.29)/t   kept 3,215   (7.39)/t
    from   08:00: removed   591  (10.67)/t   kept 1,916  (10.00)/t

--- MC5-cap4 (BOUNDARY) ---

THE VERDICT: MC5-cap4 against MC5 (registered readings 1-5, $4.26)

  1. per trade +0.09 (margin 4.26)   per symbol-day +0.40
  2. early half  per trade +0.10  per symbol-day +0.19     late half  per trade +0.08  per symbol-day +0.22
  3. drop-top-3 level  MC5-cap4 (60,038.18)  MC5 (62,632.98)     drop-top-3 delta 2,065.34
  4. cluster bootstrap on the delta  P(total > 0) = 1.000  [1,233.26, 3,964.06]  over 1,447 symbols
  5. abstention control: 238 of 6,462 trades removed at random, 2000 draws
       per trade      random p05 -0.28  p50 +0.04  p95 +0.21   the gate +0.09
       per symbol-day random p05 +0.04  p50 +0.36  p95 +0.53   the gate +0.40

  NOTHING: fails 1 (per trade >= 4.26 and per symbol-day > 0); 5 (abstention control: per trade +0.09 does not beat random removal's p95 +0.21)

  cost: 0 of MC5's top-10 trades at $4.26 are absent from MC5-cap4
  cascade: 0 MC5-cap4 entries the baseline does not contain

  WHAT THE CAP TOUCHED: 238 of 6,462 trades removed (3.7%) in 144 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed   238 per trade   (7.64)   kept 6,224 per trade   (5.22)   gap -2.42
    at $4.26  removed   238 per trade  (10.90)   kept 6,224 per trade   (8.48)   gap -2.42
    at $8.92  removed   238 per trade  (15.56)   kept 6,224 per trade  (13.14)   gap -2.42

  POSITIONAL CONTROL (reported, not scored): same 144 symbol-days, same 238 trades removed, random positions, 2000 draws
    per trade  random p05 -0.05  p50 +0.09  p95 +0.22   the cap +0.09   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 08:05, 54% at/after 08:00   kept median 07:25, 38% at/after 08:00
    before 08:00: removed   109  (11.79)/t   kept 3,846   (7.44)/t
    from   08:00: removed   129  (10.16)/t   kept 2,378  (10.16)/t

REPORTED, NOT SCORED: MC5-cap1 against MC5

  would read NOTHING: fails 1 (per trade >= 4.26 and per symbol-day > 0); 5 (abstention control: per trade +1.37 does not beat random removal's p95 +1.42)
  per trade +1.37   per symbol-day +4.77   boot P 1.000

  WHAT THE CAP TOUCHED: 3,018 of 6,462 trades removed (46.7%) in 1,687 of 6,411 symbol-days

  REMOVED vs KEPT (the whole mechanism in one row)
    at $1.00  removed 3,018 per trade   (6.87)   kept 3,444 per trade   (3.94)   gap -2.93
    at $4.26  removed 3,018 per trade  (10.13)   kept 3,444 per trade   (7.20)   gap -2.93
    at $8.92  removed 3,018 per trade  (14.79)   kept 3,444 per trade  (11.86)   gap -2.93

  POSITIONAL CONTROL (reported, not scored): same 1,687 symbol-days, same 3,018 trades removed, random positions, 2000 draws
    per trade  random p05 +0.63  p50 +1.33  p95 +2.07   the cap +1.37   -> does NOT beat p95: no evidence late entries differ from other entries in the same name-days

  TIME OF DAY (ET): removed median 07:40, 42% at/after 08:00   kept median 07:15, 36% at/after 08:00
    before 08:00: removed 1,748  (10.22)/t   kept 2,207   (5.45)/t
    from   08:00: removed 1,270  (10.00)/t   kept 1,237  (10.32)/t

====================================================================================================
SUMMARY ($4.26)
====================================================================================================

  MCL-cap3  REFUSED  d/trade  -0.33  d/symday  +0.14  removed   234  removed   (3.82)/t vs kept   (9.30)/t  random p95 +0.26
  MCL-cap2  REFUSED  d/trade  -0.39  d/symday  +0.70  removed   641  removed   (6.99)/t vs kept   (9.36)/t  random p95 +0.47
  MCL-cap4  NOTHING  d/trade  -0.22  d/symday  -0.02  removed    81  removed     1.22/t vs kept   (9.19)/t  random p95 +0.14
  MCL-cap1  REFUSED  d/trade  -0.09  d/symday  +2.22  removed 1,609  removed   (8.84)/t vs kept   (9.06)/t  random p95 +0.95
  MC5-cap3  NOTHING  d/trade  +0.20  d/symday  +0.92  removed   556  removed  (10.65)/t vs kept   (8.37)/t  random p95 +0.38
  MC5-cap2  NOTHING  d/trade  +0.20  d/symday  +1.94  removed 1,331  removed   (9.34)/t vs kept   (8.37)/t  random p95 +0.70
  MC5-cap4  NOTHING  d/trade  +0.09  d/symday  +0.40  removed   238  removed  (10.90)/t vs kept   (8.48)/t  random p95 +0.21
  MC5-cap1  NOTHING  d/trade  +1.37  d/symday  +4.77  removed 3,018  removed  (10.13)/t vs kept   (7.20)/t  random p95 +1.42

WHAT THIS IS NOT

  NOT OUT OF SAMPLE. holdout.json has not been touched.
  NOT A CAP MODEL. Each symbol-day ran alone in the source books.
  NOT A SEARCH. CAP-3 decides; CAP-2 and CAP-4 are boundaries; CAP-1 is reported only.

```
