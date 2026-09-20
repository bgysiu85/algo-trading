# Time of day — measured, and it is three to five symbols

**Research chat, 2026-09-16. Read-only: no program logic touched.**
Raw report: `D:\Trading\Claude outputs\time_of_day_20260916.txt`.

> **Finding.** There is a time-of-day concentration in MCL — **07:00–08:00 ET,
> sharpest at 07:45–08:00**. It survives the temporal split. **It fails
> drop-top-3 in every block.** At session level the median session inside the
> window loses money and five symbols are worth more than the whole hour.
>
> **And the recaps cannot answer the question at all.** Cameron anchors entries
> to chart position and price, never to the clock.

This finally measures the item registered as `execution_gap_20260910.md` §7
item 4 / `HANDOVER_TO_BUILD_20260910.md` item 6 — *"register the 07:00 window
for MCL"*. The published hour table there had never had drop-top-N, a temporal
split, a friction ladder, or a session-level denominator applied to it.

---

## 1. A data trap, recorded first

**`entry_time` in `var/reports/screened/backtest_trades_mcl.csv` is UTC, not
ET.** ET = UTC − 4. Verified against `execution_gap`'s published hour counts
(288 / 189 / 287 / 424 / 662 / 451), which reconcile exactly once shifted.

Reading those blocks as ET would have moved every conclusion four hours and
produced a coherent-looking wrong answer. Another instance of §5's shape.

---

## 2. The recaps do not contain the data — probe, not assumption

Twelve recaps read in full before committing to a 317-video pass.

| | |
|---|---:|
| clock times stated | **31** (23 hour-level, 8 minute-level) |
| times attributable to a trade with a known outcome | **0** |
| videos yielding one usable time+outcome pair | **0 of 12** |

The minute-level times attach to **scanner hits**, to moves he explicitly did
not trade, or to his desk sit-down time. In one recap he is asked the time of
his own trade and cannot recall it.

> **A second trap, and it would have been silent.** Auto-generated transcripts
> render dollar prices as clock times — `6:20`, `8:81`, `9:50`, `7:05`, `5:30`
> are all *prices* in these recaps. **A regex harvest of `H:MM` across 317
> videos would have returned a large, clean-looking table of fictional
> timestamps.** Excluding them was decisive in the probe.

**Do not commission an extraction pass over the recaps for trade times.**

---

## 3. The census day-level pattern is the regime

`warrior_census_dated.csv` states a first-trade time on **88 of 401** rows; 87
also carry green/red. Raw, the pattern looks strong — earlier start, higher
green rate, far larger day (06:30 block mean $69,663 against 09:00's $2,035).

**It does not survive the control.**

- **He starts earlier on hot days.** Median first trade **07:00** hot, **07:30**
  cold.
- **The regime label alone moves the mean day 14×** — hot $46,481 (94.3% green,
  n=53), mixed $24,951 (97.2%, n=36), cold $3,258 (76.9%, n=121).
- **Within cold days only the curve dissolves**: 100% / 85% / **50%** / 100% /
  67% / 67% across 06:30→09:00, on cells of 1, 20, 4, 5, 3 and 9. The 07:30
  block is the *worst* and 08:00 the best. Non-monotone noise.
- **Selection on top**: he states a time on days with a median |P/L| of
  **$10,855** against **$7,550** when he does not.

This is the same error the census already caught once with trade count —
*a symptom of opportunity, not an input*. Start time is the same shape.

---

## 4. MCL by ET block — the measurement

2,413 trades, 505 sessions, screened universe. Full tables in the raw report and
the artifact page.

**30-minute blocks.** Four are positive — 06:30 (+461), 07:00 (+763), 07:30
(+1,315), 10:00 (+224). **Not one survives drop-top-3.** Only 07:30 clears
$4.26 friction (+3.66) and it dies at $8.92 (−1.00). Every block before 06:30
loses at every friction level — the window Cameron refuses to trade and MCL
arms in.

**15-minute blocks.** `07:45–08:00 ET` is the most striking cell in the project:
**+$20.98/trade** on 80 trades over 69 sessions, positive in both halves, and
the only block anywhere still positive at $8.92 friction (**+12.06**). Its win
rate is **26.2%**, the lowest in the table. **Drop-top-3 takes it from +1,678 to
−537.**

**Session level, 07:00–08:00 ET** — the standing rule that the sample is
sessions, not trades:

| | |
|---|---:|
| sessions with a trade in the window | 259 |
| **positive sessions** | **92 (35.5%)** |
| mean per session | +8.02 |
| **median per session** | **−9.42** |

Top five symbols: MBX +1,181, IMCC +737, SQFT +451, WSHP +298, BOXL +263 =
**+3,930 against a block total of +2,078.** Five names out of 191 are worth more
than the entire hour.

**So the window is not a window.** A rule saying "trade 07:00–08:00" would have
traded 259 sessions to capture five names.

---

## 5. Caveats

- **In-sample.** MCL was fitted on this data. The holdout is untouched.
- **This is the superseded trade list.** It books MCL at **−$0.53/trade**; the
  repaired point-in-time universe books it at **−$10.52**
  (`pit_strategy_result_20260914.md`). **The block table must be re-run on the
  PIT trade list before any level above is quoted.** The *concentration* finding
  should survive — it is about shape, not level — but the levels are stale.
- **Ben's own 1,657 round trips show the identical trap.** The 06:30 block reads
  +$33,059 and falls to **−$5,994** after removing one symbol. After drop-top-1
  no hour of his day is profitable.
- **Cameron's own stated curve disagrees with ours.** *"Seven and eight is
  building the cushion, eight and nine is really stepping it up, nine and ten is
  cooling off, and then I'm losing money consistently after 10:00."* Our
  08:00–09:00 blocks are the worst on the board. One of the two is wrong, and
  his is self-reported.

---

## 6. What to run

1. **Re-run the block table on the point-in-time trade list**, keeping
   drop-top-N, both halves, the friction ladder and the session-level
   denominator. One script, no new data.
2. **If 07:45 survives all four there**, it becomes a registerable hypothesis
   with a pre-committed window. **If it fails drop-top-3 again, the time-of-day
   question closes** and the 07:00-window item comes off the backlog — which is
   a result worth having either way.
3. **Do not** re-open the recaps for trade times, and do not regex `H:MM` out of
   any transcript corpus without a price filter.
