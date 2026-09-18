# Handover — the MC5 exit line and the full-day question, 2026-09-17..18

One chat. Everything below is committed on `main`; nothing is live and the trader is
unchanged. Written at Ben's request before close of day.

## 0. What was asked and what came back

Ben, in order: extend MC5 to 04:00-20:00; make MC5 "more robust" against bad trades;
add a profit floor beside the trail; then try that floor five ticks lower. Four
registrations, four results, **all NOTHING or REFUSED**.

| # | question | registered | result | verdict |
|---|---|---|---|---|
| H-C2 | exit at max(5% trail, entry + 10 ticks) once up 15 ticks | `REGISTERED_profit_floor.md` (`2b1620a`, amdt A) | `profit_floor_RESULT.md` (`4bd3a5d`) | MCL **REFUSED**, MC5 **NOTHING** |
| H-C3 | the same floor at entry + 5 ticks | `REGISTERED_profit_floor_v2.md` (`aa03148`) | `profit_floor_v2_RESULT.md` (`d227422`) | MCL **REFUSED**, MC5 **NOTHING** |
| — | MC5 04:00-20:00, screen running all day | `REGISTERED_mc5_full_day.md` (`5a52b9c`, amdts A-D) | `mc5_full_day_RESULT.md` (`88343c8`) | **NOTHING**, 5 of 5 readings fail |
| H-C1 | MC5 re-arms only after its entry signal switches off | `REGISTERED_mc5_rearm.md` (`1d521e4`) | — | **REGISTERED, NOT BUILT** |

## 1. The profit floor (H-C2, H-C3)

**It is not Cameron's rejected breakeven stop.** That one REPLACED the trail after a
target and widened the exit (−$27,260). This one sits beside the trail and exits at
whichever level is higher, so it can only tighten.

**It works exactly as intended on losers and gives the money back on winners.** Paired
floor exits against the same trade in the baseline, at $4.26, (15, 10):

| | MCL | MC5 |
|---|---:|---:|
| losers rescued | 829, **+12,343** | 839, **+8,332** |
| winners > $20 cut | 147, (9,988) | 125, (9,514) |
| small winners cut | 205, (792) | 192, (639) |
| re-entries and knock-on | (1,656) | (2,103) |
| **whole book** | **(93)** | **(3,923)** |

MCL +0.28/trade and (0.01)/symbol-day — denominators disagree, REFUSED, bootstrap
P = 0.470. MC5 (0.36)/trade, P = 0.003 with the interval wholly below zero: the floor
makes MC5 **worse**, not merely no better.

**(15, 5) changes nothing:** MCL (0.00)/trade and MC5 (0.05)/trade against (15, 10).
Fewer floor exits (1,243 → 985, 1,212 → 937) and fewer runners cut (148 → 88, 154 → 88),
each exit booking less, and the two cancel.

**The arithmetic fact worth keeping: a floor below about 7 ticks cannot pay for the round
trip it triggers.** At +5 ticks, 0.0% of floor exits clear $4.26 (at +10 ticks, 71.6% on
MCL). The registration predicted 10-30% and was simply wrong — that was knowable before
the run. MCL's win rate ROSE 23.3 → 36.0% at (15, 10) with the P/L unchanged: a rescued
loser becomes a scratch, not a win.

**On 5-minute bars the floor gaps through:** 675 of 1,212 MC5 floor exits opened below
the level, 353 of them below the entry price.

**Closed at two cells.** A third tick pair needs a reason that is not "try another
number".

## 2. MC5 full day — the answer is not close

**NOTHING, 5 of 5 readings fail.** Arm C's added trades (entries at or after 09:30):
**38,503 trades, (8.27)/trade, net (318,377)**; halves (8.52)/(8.04); drop-top-5 symbols
(332,319); cluster bootstrap **P = 0.000**; session median (616.80).

| block | trades | GROSS | @ $4.26 | @ $8.92 | win | bars |
|---|---:|---:|---:|---:|---:|---:|
| PRE 04:00-09:30 | 8,572 | (5.05) | (8.31) | (12.97) | 23.3% | 4.2 |
| RTH 09:30-16:00 | 30,155 | (4.42) | (7.68) | (12.34) | 25.7% | 10.5 |
| POST 16:00-20:00 | 8,348 | (7.13) | (10.39) | (15.05) | 21.0% | 5.9 |

**Every hour of entry loses at $4.26 and every block loses GROSS.** Best hour 10:00
(5.55)/trade over 5,162 trades; worst 16:00 (11.39) and 15:00 (11.09). RTH loses $4.42 a
trade before any cost at all, so this is not a friction result and no friction assumption
rescues it.

**More opportunity, same edge.** The running screen found 23,235 symbol-days against the
pre-market list's 6,378 (27.6% PRE, 63.2% RTH, 9.2% POST, median 40 names a session).
Trading ~7x as often multiplies the loss ~7x.

**Holding past 09:30 does nothing:** 773 pre-market entries exited at a different time
once the flatten was removed, moving P/L by **+343** in total.

## 3. What was built (all tested, all on `main`)

- **`common/screen_day.py`** — the live screen run 04:00-20:00 in three blocks: PRE and
  RTH against the prior regular close, POST against TODAY's regular close; volume
  accumulating from each block's own start; one top-40 list all day and a name never
  dropped. **Its control is that the PRE block reproduces `screen_sim` tick for tick** —
  the run EXITS if it does not (330 ticks, 0 disagreements on the session checked). 14
  cases, 8 mutations caught, including one showing the control can fail.
- **`strategy/mc5/mc5.py`: `session_end`** — `None` is bit-identical; the study passes
  20:00. Also **`profit_floor=(arm, floor)`** on MCL and MC5, one implementation
  (`mcl.check_profit_floor / reaches_arm / floor_level`), 42 cases, 8 mutations caught.
- **`common/profit_floor_study.py`** — four books, the five gate readings, the mechanism
  lines; `--floor` selects a REGISTERED cell only, each with its own report path, and the
  family bootstrap bar is 0.975 for the second cell.
- **`common/mc5_full_day.py`** — arms A (published frames), A' (full-day frames, the
  scored control), B (frozen universe to 20:00), C (running screen to 20:00).
- **`common/pairs_restrict.py`** — cuts a published universe to the sessions a study could
  run. Subset only, rows unchanged; 7 cases.

## 4. Traps this line paid for — worth carrying

- **A short-window arm silently drops a last-bar entry.** An entry on the final in-session
  bar has no bar left to be managed on, so the 09:30 arm books NOTHING for it while a
  20:00 arm books an ordinary trade: 226 such entries, (1,955). Without naming them they
  read as the extension producing pre-market trades out of nothing.
- **A published baseline and a like-for-like control are different arms.** Full-day frames
  warm up on the prior whole day, pre-market frames on the prior pre-market. Worth
  +0.28/trade. Amendment C exists for this; every scored comparison is against A'.
- **A reconciliation must compare populations, not just books.** Arm A first read DOES NOT
  MATCH (6,425/(8.62) against 6,462/(8.57)) purely because four dates have no RTH pull.
  Fixed by re-scoring the published rule over the same 546 sessions, not by loosening the
  check (amendment D).
- **Win rate is not P/L.** The floor raised MCL's win rate 13pp and moved the book by $93.

## 5. Data pulled this session (all $0.00 on the Databento subscription)

`E:\Databento\XNAS.ITCH\ohlcv-1m`, 550 sessions each, symbology sidecars present:
**`<date>_0930_1600.dbn.zst` (14 GB on disk)** and **`<date>_1600_2000.dbn.zst`
(265 MB)**, 2024-07-01 → 2026-09-09. One-day probe first (RTH 136.7 MB billable, POST
11.0 MB, both $0.0000); full estimates before `--confirm`.

**Four dates cannot be run full-day at all:** 2026-09-10, 09-11, 09-14, 09-15 (and 09-16,
09-17 in the screen) have a pre-market pull and no RTH one.

## 6. What is open

1. **H-C1 (MC5 re-arm) is registered and unbuilt** — `REGISTERED_mc5_rearm.md`. Counts
   known: 3,152 of 6,883 MC5 trades were re-entries on the BASIC book, only 379 on the
   very next bar. Prediction on file: binds 15-35%, reads NOTHING.
2. **The RTH/POST volume threshold is carried from 09:30, not measured** (amendment B).
   Too easy, so the after-open universe is too big — conservative here, but a measured
   `itch_capture` ladder past 09:30 would be its own registration and would shrink RTH.
3. **No concurrency cap is modelled anywhere.** 47,075 trades a year is far past a 3-slot
   book; live, 29% of buy attempts were refused.
4. **The live trader is untouched** by all of this: still 04:00-09:30, no RTH/POST screen,
   no floor, no re-arm.

## 7. For PROGRAM_INDEX — the lines this chat owes it

`PROGRAM_INDEX.md` lives in the claude.ai project, not in the repo, and several chats
edited it today, so this chat did not rewrite it. Paste-ready:

**§0 (the dated summary):**

> **2026-09-18 — MC5's exits and its window are both closed.** A profit floor beside the
> 5% trail (arm at +15 ticks, floor at +10) is **REFUSED for MCL (+0.28/trade, (0.01) per
> symbol-day, bootstrap 0.470) and NOTHING for MC5 ((0.36)/trade, P = 0.003)**: it rescues
> ~830 losers a book (+12,343 MCL, +8,332 MC5) and hands the same money back in cut
> winners and re-entries. At +5 ticks the family reads the same way to within a nickel a
> trade, and **no floor exit below ~7 ticks can clear a $4.26 round trip** — 0% do at +5.
> **Extending MC5 to 04:00–20:00 with the screen running all day reads NOTHING on all five
> criteria: 38,503 added trades at (8.27), P = 0.000.** Every hour of entry loses at $4.26
> and **every block loses GROSS** — RTH (4.42)/trade before any cost. The running screen
> finds 23,235 symbol-days against the pre-market list's 6,378; trading ~7× as often
> multiplies the loss ~7×. See `profit_floor_RESULT.md`, `profit_floor_v2_RESULT.md`,
> `mc5_full_day_RESULT.md`, `handover_mc5_exits_and_full_day_20260918.md`.

**§2 roster, MC5 row:** add — *2026-09-18: the profit floor (both cells) and the full-day
window are both closed on it; 04:00–20:00 reads NOTHING with every block negative gross.*

**§4 standards — one new row:**

> **An exit rule cheaper than a round trip is not an exit rule** | Added 2026-09-18. A
> floor at entry + 5 ticks books $4.00 gross on 100 shares before commission, so 0% of its
> exits clear $4.26 and the win rate FALLS while P/L does not move. Price the rule's own
> payout against friction before registering it.

**§5 traps:**

> - **A short-window arm silently drops a last-bar entry.** An entry on the final
>   in-session bar has no bar left to be managed on, so a 09:30 arm books nothing for it
>   while a 20:00 arm books a trade: 226 entries, (1,955), which read as the extension
>   inventing pre-market trades until they were counted separately.
> - **A reconciliation compares populations, not just books.** `mc5_full_day`'s arm A read
>   DOES NOT MATCH purely because four dates have no regular-hours pull;
>   `common/pairs_restrict` re-scores the published rule on the same sessions.

**§7 open items:** H-C1 (MC5 re-arm) registered and unbuilt; a measured RTH/POST capture
ladder past 09:30; the concurrency cap still unmodelled.

**§3 infrastructure — new modules:** `common/screen_day.py`, `common/mc5_full_day.py`,
`common/profit_floor_study.py`, `common/pairs_restrict.py`; `profit_floor` and
`session_end` parameters on the MC5/MCL engines.
