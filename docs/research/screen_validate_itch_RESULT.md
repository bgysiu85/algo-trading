# The simulated screen against the live watchlists, on the tape of record — result, 2026-09-17

Registered in `docs/research/REGISTERED_screen_validate_itch.md` (fe9cdbd)
before the XNAS.ITCH extension was screened. Universes:
`var/state/screen_pairs_pit_itch_ext.json` (XNAS.ITCH, v2 ladder, 76
symbol-days) and `screen_pairs_pit_ext2.json` (XNAS.BASIC, capture 0.552, 67),
both 2026-09-08 → 09-17, eight sessions (seven at first; 09-17 added
2026-09-18, §7). Reports:
`var/reports/screen_validate_itch.{txt,json}`, `screen_validate_basic.{txt,json}`,
`screen_sim_itch_ext.txt`, `screen_sim_ext2.txt`. Cost $0.00. Artifact page:
"Screen validated".

**Headline. The simulation reproduces the live screen: 61 of 63 live names
(97%, Wilson 89–99%) on XNAS.ITCH, and the identical 61 of 63 on XNAS.BASIC,
over eight sessions. GOOD on both tapes — §7 item 1 is settled and the
"unmeasured agreement" caveat on the v2 baselines is retired.** The 22 other
live names are the
04:00 carry-over — yesterday's screen, re-served by TradingView at the first
poll — and the two real misses are a name with no prior close (RML) and a
name that peaked at +19.5% on both tapes (TPET). Two facts about the live
feed came with it: **every name IBKR refused was refused 12–27 minutes after
the tape first qualified it (median +15.6, 10 of 10), consistent with the
unauthenticated scanner endpoint serving 15-minute-delayed data**, and the
first poll of every session arms the previous session's names.

## 1. The agreement (§2.3)

| | XNAS.ITCH ext | XNAS.BASIC ext2 |
|---|---|---|
| every live name | 65 / 85 = 76% [66, 84] | 65 / 85 = 76% [66, 84] |
| carry-over set aside | **61 / 63 = 97% [89, 99] → GOOD** | **61 / 63 = 97% [89, 99] → GOOD** |
| clean misses | RML 09-09, TPET 09-10 | the same two |
| sim-only | **11** (best ranks 2–6) | 2 (BRNX 09-08 rank 2, GLOO 09-17 rank 6) |
| symbol-days, 8 sessions | 76 | 67 |

Per session, carry-over set aside (live / sim / found / missed / sim-only):
09-08 6/10/6/0/4 · 09-09 11/11/10/1/1 · 09-10 6/5/5/1/0 · 09-11 8/9/8/0/1 ·
09-14 10/11/10/0/1 · 09-15 6/8/6/0/1 · 09-16 4/6/4/0/1 · 09-17 12/16/12/0/2
(ITCH). Blocked names counted as screened. The seven-session reading
published first was 49 / 51 = 96% [87, 99]; 09-17 (§7) moved it to 61 / 63.

## 2. The 04:00 carry-over (§2.2)

22 of 85 live names were COLD at 09:29 and on the previous session's list:
09-09 BNC WYHG · 09-10 BIAF IRD ODD RML SUNE · 09-14 ACVA AENT FTFT LBGJ PCLA
TNON · 09-15 TNON · 09-16 MYSZ NAMI PSNYW VEEA · 09-17 FTFT MEDS RETO ZTG.
The simulation surfaced 4 of the 22 (TNON 09-15, NAMI 09-16, MEDS and RETO
09-17 — repeat runners the rule also removes). Four sessions carry a blocked
stamp at the first poll for a previous-session name (PCLA 04:00:05 on 09-11
and 04:00:08 on 09-14, PSNYW 04:00:06 on 09-16, ZTG 04:00:26 on 09-17). The tape cannot have put those names there:
no bar has closed at 04:00:05. TradingView's `premarket_*` columns are the
previous session's until today's prints arrive, so the first poll returns
yesterday's screen and the trader arms it — including on 09-11, when PCLA
arrived stale at 04:00 and then qualified for real at 04:07.

## 3. The two clean misses, read off the tape (§2.5)

- **RML 09-09: no prior close** on either tape's daily archive. The
  simulation drops a name before any clause when `premarket_change` is
  undefined; TradingView had a close to divide by. A daily-archive gap, not a
  screen disagreement.
- **TPET 09-10: change never reached 20%** — max **+19.5%** at 08:51 (ITCH)
  / 08:58 (BASIC) against a prior close of 1.82, price 2.18, volume far above
  threshold. TradingView's prior close for TPET differs from the repaired
  16:00 close by enough to cross 20%. A prior-close disagreement of under a
  cent, at the edge of the clause.

Neither read PASSED. Nothing points at the simulation.

## 4. The clocks (§2.4)

**Block stamps, ITCH first_seen:** QCML +16.3 · DPU +15.3 · YMAT +15.8 · GDHG
+13.8 · PCLA +27.0 · SXTC +18.7 · RAYA +11.8 · ZTG +14.9 · KXIN +14.9 · NBIG
+16.8 — **median +15.6, range +11.8 to +27.0, 10 of 10 positive.** On BASIC:
median +14.9, range +13.3 to +16.8. The ITCH values are computed from a different tape and a different
threshold and land in the same place; the outlier (PCLA +27.0) is the
exchange tape qualifying PCLA at 04:02 under the 1,980-share 04:30 step.

**First entry signal:** 39 names, median +57 min, smallest −42.0 (XRTX
09-11), 4 under +10 min on ITCH (three of them stale 04:00 arrivals of the
previous session's names, which the block-stamp clock excludes and this one
cannot). At 04:31:02 on 09-11 the simulation read
XRTX at **+15.1% (ITCH) / +14.2% (BASIC), short of 20%** — TradingView's
prior close for XRTX was lower than the repaired one, the same clause as
TPET in the other direction. The registration's "smallest delta rules out a
fixed delay" reading is withdrawn as too strong: this clock bounds arrival
from above against the *simulation's* first_seen, and XRTX shows TradingView
can qualify a name before the tape does, so a small delta does not contradict
a feed delay. The block-stamp clock is the evidence; it is ten names.

## 5. Predictions scored

Scored on the seven-session run (the registered one); the eight-session
figures are in brackets. Held: P1 (≥ 90%, lower bound ≥ 80%: 96%, 87%
[97%, 89%]); P2 (≤ 4 clean misses, none PASSED, clause `change` or
`volume`: 2, `change` and no-prior-close [unchanged]); P3 (ITCH sim-only
3–12 and symbol-days +10–50%: 9, +15% [11, +13%]); P4 (carry-over found
anyway 2–5: 2 [4 of 22]); P5 (block clock +12 to +18, all positive: median
+15.6, all positive — range +11.8 to +27.0 is wider than stated [10 of 10,
same median]); P6 (at least one live-first name, clause `volume` or
`change`: XRTX, `change`).

## 6. What this decides

- **§7 item 1 closes: GOOD on both tapes.** Every point-in-time figure on the
  v2 universe may be read as describing the live screen's universe, with the
  sample named (8 sessions, 63 names, lower bound 89%). **Item 23 (the
  Databento subscription) is unblocked** — the ITCH extension is on disk.
- **The v2 ladder after the cut is looser than the live screen**: 11 sim-only
  names on ITCH against 2 on BASIC, ranked 2–6 by change, on thresholds
  of 2–11k shares. On post-change sessions BASIC's constant capture is the
  tighter reproduction. This is the universe imprecision v2 named; the
  hybrid (ITCH before 2026-03-30, BASIC after) stays optional and unbuilt.
- **Two live-feed facts, handed over, not acted on here:**
  1. *The live watchlist runs about a quarter of an hour behind the tape.*
     `tv_feed` polls `scanner.tradingview.com` without a session, and
     TradingView serves US equities 15 minutes delayed without a real-time
     exchange subscription. A backtest entering at `first_seen` enters
     trades the live trader could not have seen. The measurement is a
     separate registration: the v2 books with `first_seen + 15 min`. The
     fix is on the feed side — a logged-in session with real-time Nasdaq
     data, or the IB scanner, which is real-time — and is the live chat's.
  2. *The first poll arms yesterday's screen.* The rule that removes it is
     in the feed's hands: ignore a name until its `premarket_volume` has
     changed between two polls.
- Nothing about a strategy. `holdout.json` stays shut.

## 7. 2026-09-17, added 2026-09-18

The largest live session in the archive (16 names) took three attempts to
reach the comparison, none of them the screen's fault: the same-day pulls
came down without symbology sidecars (Databento resolves a day's instrument
ids with a lag; `--resymbolize` filled them next morning), the ITCH minutes
for the day were not yet published at all, and the prior close is looked up
through the daily archive, whose September chunk ended at 09-16 until it was
re-pulled whole (which also restored the 09-01–04 bars the ORB chat's
mid-month pull had dropped).

**The reading: 12 of 12, on both tapes.** Live 16 names; four are the
carry-over (FTFT MEDS RETO ZTG, ZTG stamped 04:00:26; MEDS and RETO were
also on the tape again — repeat runners); the simulation surfaced all twelve
that remain, and 16 (ITCH) / 15 (BASIC) in total. Sim-only: BYAH and RTB on
ITCH (ranks 3 and 6), GLOO on BASIC (rank 6). Two more block stamps: KXIN
04:15:54 against a 04:01 first_seen (+14.9), NBIG 07:15:49 against 06:59
(+16.8) — the tenth and eleventh points on the same quarter-hour. The
eight-session figures are in §1; the seven-session figures the registration
was scored on are kept there beside them.
