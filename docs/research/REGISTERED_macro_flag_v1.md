# REGISTERED — MFLAG-v1: skip trend entries that touch a supported macro-event day (HTF futures, daily)

**Written before any P&L has been split by event day.** No trade in any books file has been joined to the
event calendar. `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0023** step 3 (this registration), step 4 (count-only pre-flight, then training run, then
holdout if earned). Inputs: `claude/w15_0023_impact_map` Result doc, REVISED section (run 2b,
`w15_0023_impact_map_20260929_2b.csv`, commit 7caade4); `strategy/macro_events/macro_event_calendar.csv`.

Ben's scope decision, 2026-09-29: macro-event effects as a wide net across HTF futures, scheduled calendar
first; "entry-flag test only on supported market/event pairs"; unscheduled headlines (e.g. Iran-US) later.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after a result is a new hypothesis.

---

## 0. Where this sits, stated plainly

- **What the map found (range, not direction).** On 2010-06 → 2021-12 daily bars, 12 of 38 market/event
  cells show a wider event-day range than weekday-matched quiet days (Holm p < 0.05, ≥ 30 clean days).
  The map says nothing about which way price moves or whether any strategy gains.
- **The economic idea.** A trend entry with an ATR-sized stop that is made on, or filled into, a
  release day is exposed to a range about 1.2–1.4× normal that carries no trend information. The
  hypothesis is that those entries are worse than the host's other entries, so skipping them helps.
- **The map is not clean evidence.** Run 2b changed two design choices after run 1 was read (relevant-
  events rule, weekday matching). The 12 cells were therefore chosen on the same training bars that the
  flag is now scored on. The guards here are: a random-removal control, a placebo flag on the *unsupported* cells, and a
  **holdout that is the only evidence that counts** (§6).
- **No host of its own.** The flag is tested on a trend host that already exists and was not chosen on
  a result: **C1, Donchian 20/10**, as built in TL-v0 and re-run in W15-0020 (`strategy/tl_v1/engine.py`,
  "same code as TL-v0's C1"). Its training books are on disk: 1,175 trades, fractional sizing on
  $22,129, net **($847)** at mid. The question is whether the flag changes the host, not whether the host is good.
- **Why not "CL 4H first" (the original step 4).** No CL 4H strategy with real trades survives:
  HTF-Ben is closed, TL-v1 failed (W15-0020) and its CL 4H variant is being dropped (W15-0027). CL enters
  here through C1 on the CL daily series, flagged on **NFP only** (its one supported cell).
- **Not a rescue.** The flag may never be applied to a failed or closed strategy to change its verdict
  (TL-v1, HTF-Ben, CRUDELE-3S, BREIT-CAP, CHARTMARK-v1). On those books it is *reported only* (§2.4).

---

## 1. The hypothesis, in one sentence

**Skipping the Donchian 20/10 entries whose signal bar or entry bar falls on a supported event day for
that market improves the host's net after measured costs by more than the 95th percentile of removing
the same number of random entries, and by more per skipped trade than the same rule on unsupported
market/event pairs.**

---

## 2. The rules

**Every number is fixed here, before any flagged count or P&L. None is tuned.**

### 2.1 The flag cells (from run 2b, exactly; nothing added or dropped)

| Market | Flag events |
|---|---|
| ES | NFP |
| CL | NFP |
| 6A | NFP, FOMC |
| 6E | FOMC |
| 6J | NFP, FOMC |
| GC | NFP, FOMC |
| SI | NFP, FOMC |
| MTN | NFP |
| RTY, NG, 6B, HG | none (no supported cell) |

MTN FOMC (Holm 0.0504) is **not** a flag cell. CL EIA is not a flag cell. Event dates = `date` column of
`macro_event_calendar.csv`, events `NFP` and `FOMC` (the decision day), as committed at 7caade4.

### 2.2 The flag window

For a flag event on session date **d** in market m, a host trade in m is **flagged** if either:

| Part | Rule | Why |
|---|---|---|
| **W1 Into the event** | its entry fill is at the open of session d | the position is open through the release |
| **W2 Made by the event** | its signal bar is session d (entry at the open of the next session d+1) | the channel break was made on the widened bar |

With the host's next-open entry rule this is: **entry_date ∈ {d, next session after d}**, where
entry_date is the session whose open fills the entry, as the host books record it. (A test in the build
must confirm this convention; §5 G4.) Sessions = the TL-v0 loader's daily rows (Sunday rows folded).

### 2.3 The action — skip (primary)

A flagged entry is not taken. The strategy **sits out that trade**: flat from its entry to its recorded
exit, then resumes the host's book unchanged. This makes the flagged book = the host's book minus the
flagged trades, exactly computable from the books file. (Whether the host would have re-entered during
that span is deliberately not modelled; it would need the engine re-run and adds a second free choice.)

**Delta** = net(host with flagged trades removed) − net(host) = −Σ net of flagged trades.

Sizing, friction (low $0.625 / mid $1.25 / high $2.50 per side, as in the books), rolls, stops: the host's, unchanged.
Skipping always saves that trade's friction. The random control removes trades too, so it saves friction on the same basis.

### 2.4 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| **W1 only** | entry fill on d | exposure to the release itself |
| **W2 only** | signal bar = d | whether event-made breaks are the problem |
| **Half size** | flagged trades kept at 50% (delta = −½ Σ net) | the softer action Ben could trade |
| **Per event** | NFP cells alone; FOMC cells alone | which release carries it |
| **No map** | flag every market on NFP + FOMC + CPI (+ EIA for CL, NG) | whether the map's selection adds anything |
| **Wide window** | entry_date ∈ {d−1, d, d+1} | sensitivity to the window |
| **Other books** (reported only) | same flag on the TL-v1 "v1 ens" books (W15-0020), and on CRUDELE-3S, BREIT-CAP (daily) and CHARTMARK-v1 once their training books exist | whether it travels; never changes those studies' verdicts |
| **Integer sizing** | C1 integer books at $100k and $500k | whether it survives whole contracts |

**Known departures, not coded:** intraday timing (a 1H or 4H flag around 08:30 / 14:00 ET is a separate
registration once CHARTMARK-v1 has training books); unscheduled headlines; OPEC; direction of the event
move; exit-side rules (flatten before a release).

---

## 3. What every run must emit

- **Counts:** host trades; flagged trades by market × event × window part (W1/W2) × year; flagged share.
- **Books:** host net, flagged-book net and delta at low/mid/high friction; wins/losses and mean net of
  flagged vs unflagged trades; ten largest flagged winners and losers (date, market, event, net).
- **Controls, same books, same friction:**
  - **C-R Random removal:** per market, remove the same number of trades as the flag removes, drawn at
    random from that market's host trades; 1,000 seeded draws
    (`np.random.default_rng([crc32(str(d)), crc32(market), 23])`); delta p5 / p50 / p95 / p99, and the
    flag's percentile.
  - **C-P Placebo:** the §2.2 window on every tested but **unsupported** CPI / NFP / FOMC cell of run 2b
    (the 24 cells of the 36 CPI/NFP/FOMC cells not in §2.1). EIA is left out because it would flag every
    Wednesday and Thursday for CL and NG. Reports delta and delta per skipped trade.
- **Seen window** (2025-09-23 →), reported only, labelled "seen — not evidence".

**Nothing is ranked. No best-variant table.**

---

## 4. The bar to clear — C1 host, fractional @ $22,129, mid friction, training side

Passes only if all hold:

1. **Delta > $0** at mid.
2. **Delta beats the p95 of C-R.**
3. Both halves delta > $0 (split at the median entry date of the flagged trades).
4. Delta > $0 at high friction.
5. No single market and no single year supplies more than 50% of delta.
6. **Delta per skipped trade (flag) > delta per skipped trade (C-P placebo).**
7. Mean net of flagged trades < mean net of unflagged trades in the same 8 markets, one-sided permutation p < 0.05
   (labels shuffled within market, 5,000 seeded draws).
8. **At least 60 flagged trades.** Fewer → **NOT READ**, not failed. No widening of the window, no adding cells,
   no second host to rescue the count.

**Failing 2 or 6 closes the study, whatever else passes.**

---

## 5. Before the run — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | Data: host books `tl_v1_backtest_trades_20260929.csv` (spec C1) and the calendar; no new bars for the training side | Reused |
| G2 | **Count-only pre-flight:** reads only `market, spec, sizing, equity, entry_date` columns (a test proves no P&L column is loaded); prints flagged counts per market × event × W1/W2 × year | Open (step 4) |
| G3 | **Holdout ledger** `holdout_macro_flag.json`, own lock, refuses `--limit` and narrowing flags; mutation-tested | Open (step 4) |
| G4 | **Convention and look-ahead tests:** entry_date = session whose open fills; W2 uses the signal bar's date only (a one-session shift must break the test); calendar dates only (release dates are published in advance, so knowing them at entry is legitimate) | Open (step 4) |
| G5 | Books reproduce: C1 frac net recomputed from the CSV = ($847) mid, 1,175 trades, before any flag is applied | Open (step 4) |

**Stop rule, fixed now:** fewer than **60 flagged C1 trades** on the training side → stop, report the
counts as the finding, back to Ben before any P&L is read.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31. **Holdout:** 2022-01-03 → 2025-09-22, ledger `holdout_macro_flag.json`,
  **spent once**, only if all eight criteria pass.
- **What is spent:** C1 run on holdout bars (same code, same sizing) with the §2.1 flag. Holdout pass =
  delta > $0 at mid **and** ≥ p90 of C-R on the holdout, reported with the flagged count. The impact map's 12 cells
  are re-measured on the holdout in the same run (range multiple > 1 in at least 8 of 12), reported beside it.
- **Overlap:** the TL-v1, TL-v2, CRUDELE-3S and BREIT-CAP ledgers cover the same window for different
  hypotheses. None has been spent. If more than one ever is, all holdout results are reported together.
- **Seen window:** 2025-09-23 onward. Never scored.

---

## 7. Registered as NOT to be done

- Adding, dropping or re-thresholding flag cells after a result; re-running the map to change §2.1.
- Choosing a window, action or host variant after a result.
- Applying the flag to change the verdict of any closed or failed strategy.
- Quoting a variant, a single market, or gross as the headline.
- Spending the holdout on anything but an eight-of-eight pass.

---

## 8. Ways this could go wrong

- **Selection on the same bars.** The cells came from training data with two post-result amendments; the placebo and
  holdout are the guards, not a cure.
- **Few trades.** Roughly 8 markets × ~100 entries each, with about 1 in 10 sessions in a window → the
  flagged set may be near the 60-trade floor. The pre-flight decides before any P&L.
- **Sit-out is an approximation.** A skipped Donchian entry might have re-entered a day later; this is not modelled (§2.3).
- **Breakouts on news may be the good ones.** A widened event bar could carry real information; then
  the flag hurts and the study says so.
- **Host is a losing strategy.** Removing trades from a book that loses on average tends to "help" on its own. C-R
  controls for exactly that; the headline is always versus C-R, never versus zero alone.
- **Friction saved** by skipping is not an edge; C-R saves it too.

---

## 9. Multiplicity budget

One primary (skip, §2.2 window, C1 host), one variant family (§2.4, unranked), one holdout spend. A
second macro registration (intraday timing, or unscheduled headlines) needs its own reason that
does not begin with this result.

---

## 10. A prediction, written down now

**About 70–110 flagged C1 trades. Delta is small and inside the random-removal band (roughly the
40th–80th percentile of C-R): criterion 2 fails and the study closes. Most likely reading: *a wider
event-day range raises noise for both good and bad breakouts about equally, so skipping them is a coin flip
that saves some friction.*** The W2-only variant is the one most likely to look better. I'd be glad to be wrong.

---

## 11. For Ben to approve (defaults as drafted)

1. **Host:** Donchian 20/10 C1, existing training books (default), or wait for CRUDELE-3S / BREIT-CAP books.
2. **Action:** skip (default) or half size as the primary.
3. **Bar:** criterion 2 at p95 (default) or p99.
4. **Window:** event day plus the next session (W1 ∪ W2, default).

---

## Next steps (board)

- **W15-0023 step 3b** (Ben): approve §11 and commit this registration (commands on the board).
- **W15-0023 step 4** (Build & test chat, Sonnet / Medium): G2–G5, then the training run → Result doc. It is no longer blocked by
  W15-0020 (Done): the host books already exist.
