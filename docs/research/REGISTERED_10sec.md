# REGISTERED — the 10-second trigger (H-X1) and top-of-book imbalance at the trigger (H-Q1), on ORB's stocks-in-play setup

2026-09-23, **PRE-RUN, PRE-DATA.** No 10-second bar, no trigger and no order-book record for this study has been
built, pulled or read. No code for it exists. This document is committed to git before any of that; git's
ordering is the claim (`PROGRAM_INDEX` §1: a hypothesis is registered before it is run).

Board: **W05-0003** (monday "Algo Trading", group W05 - Small-cap strategy research). Steps are its subitems (§11).
Parents: `claude/session_close_20260918.md` §5 items 2–3 and §6; `PROGRAM_INDEX` §7 items 10d and 10e;
`claude/archive/second_bars_PRICE_20260918.md`; `docs/research/REGISTERED_orb_sip.md` (amendments A–F in the
repo; G–I in `Claude outputs\orb-20260919d.bundle`, merge pending as W12-0003); `claude/orb_sip_RESOLVED_20260918.md`,
`orb_sip_EXCURSION_20260919.md`, `orb_sip_CARRIER_20260919.md`, `orb_sip_CONTEXT_20260919.md`,
`orb_sip_VOLUME_20260919.md`. Where this document and `PROGRAM_INDEX` §4 disagree, §4 wins and this file is the bug.

---

## In plain terms

ORB — "buy when price breaks above the first five minutes' high on one of the day's 20 busiest stocks" — is the one
strategy here whose trades make money *before* costs (+0.351R a trade, where R is the trade's own risk from entry to
stop), and costs take all of it. Its stop was checked and is not the problem: the winners barely go against you and
the losers run away, so **the entry is what separates them**. This registration tests two new entry ideas on exactly
the same stocks and days. **H-X1:** instead of a resting buy-stop that fills the instant price touches the level,
wait for a 10-second bar to *close* beyond it. **H-Q1:** at that moment, only buy if more shares are queued to buy
than to sell at Nasdaq's best price (order-book imbalance — the first entry idea in this project that uses
information the price bars do not already contain). I expect both to fail the bar, and say why in §9; the point is
to settle them with one pass each, for $0 of data.

---

## 0. PRE-RUN GATES — nothing is scored until each is cleared, in order

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **The 1-second pull is priced, then landed.** XNAS.ITCH `ohlcv-1s`, whole days, for every symbol-day in the primary ORB cell (§2) outside the holdout that is not already on disk. 2,888 of the 7,239 are (the entry-minute resolution set, `var/state/orb_sip_entrybar_pairs.json`); ~4,350 are not. Estimated ~1 GB by scaling the 698.1 MB of the first pull — **the vendor's number governs.** Run without `--confirm` first; if it is not $0.00 it stops for Ben. | Both arms are simulated on seconds; the trigger cannot exist without them. |
| **G2** | **The 1-second engine reproduces the published ledger (B0 parity).** B0 (§3.1) re-simulated on 1-second bars must give (a) the same symbol-days and sides as the primary cell of `var/cache/orb_sip/trades/` for ≥ 99% of its 7,239 trades, (b) the same entry price wherever the ledger's entry did not gap, (c) every 18-Sep entry-minute-tie ground-truth trade reproduced exactly, (d) every genuine intra-minute gap trade clears a bad-tick screen or a reviewed allowlist, and (e) every exit-reason disagreement is accounted for by (c) or (d). **Criterion (c) was redesigned 2026-09-23 — see §0.1**; it no longer reads any aggregate R figure. Every symbol-day whose exit reason differs is listed with its cause. | Every comparison in this study is B0 against something. If B0 on seconds is not the ledger, the engine is wrong or the ledger is, and neither result means anything. Amendment D is the precedent: the fill model once decided a result by itself. |

### 0.1 Amendment — G2 criterion (c) redesigned, 2026-09-23 (W12-0005)

G2's criterion (c) was written as "mean net R within ±0.02R of the resolved figure of record **+0.001R**"
(`claude/orb_sip_RESOLVED_20260918.md`). Building G2 (step 4) surfaced a real divergence between that figure and
B0-on-seconds' own reading. **W12-0005** (2026-09-23) traced it, cross-validated it against an independent ground
truth (`var/cache/orb_sip/entrybar_resolved.csv.gz`, the 18-Sep study's own separately-computed answer for 2,888
entry-minute-ambiguous trades — matched exactly, 100%), and hand-spot-checked the remaining 67 genuine intra-minute
gap trades for bad ticks (none found). **The +0.001R figure of record was wrong** — it undercounted ORB SIP's true
cost because it only ever resolved entry-minute stop-order ties, never a genuine intra-minute price move a 1-minute
bar cannot see at all. The corrected figure is **−0.098R**, accepted as ORB SIP's revised figure of record.

Comparing B0-on-seconds against a number it has itself disproven is not a test of the engine — it is now comparing
the more correct reading against the less correct one. Ben's decision, 2026-09-23: **redesign G2**, not retarget it
to the corrected number, so the gate depends on no aggregate R figure at all — retargeting would still leave G2
hostage to whichever figure is currently believed, exactly the failure mode that produced this amendment.

**Criterion (c) is retired** and replaced by three checks, none of which reads an aggregate R figure:

- **(c) every trade in the 18-Sep entry-minute-tie ground truth** (`entrybar_resolved.csv.gz`) **must have its entry
  AND exit price reproduced exactly by B0-on-seconds**, at ≥ 99% rate and ≥ 99% coverage. This ground truth was built
  by a separate, earlier study and does not depend on ORB SIP's figure of record in either direction.
- **(d) every "genuine intra-minute gap" trade** (entry price disagrees with the ledger, not covered by (c)) **must
  clear an automated bad-tick screen** (an isolated print that reverts within 5 seconds, on volume under 20% of the
  preceding 30 seconds' average) **or sit on a small, dated, hand-reviewed allowlist**. Two trades are on that
  allowlist today, both reviewed 2026-09-23: MBB (2025-03-12, a real 322-share print) and PPG (2025-04-09, a real
  but thin 2-share print) — see `claude/w12_0005_orb_sip_recheck_RESULT_20260923.md`. Anything the screen flags that
  is not already on the list fails the gate until someone looks at it.
- **(e) every exit-reason disagreement between the ledger and B0-on-seconds must be accounted for by (c) or (d)** —
  zero unexplained divergences. A trade that disagrees for some third, unrecognised reason is a gate failure, not a
  rounding error.

**Criteria (a) and (b) are unchanged.** This amendment touches the QA gate only — it does not touch B0's trigger or
fill rule (§3.1), T1's rule (§3.2), or any of §7's scientific pass/fail criteria for H-X1/H-Q1, so it is not the kind
of after-the-fact rule change §10 refuses: §10 bars changing the *arms'* rules after seeing a result; G2 is the
engineering precondition that must pass before any arm is scored at all, and its broken reference is what this fixes.
`strategy/orb/tensec_g2.py` implements the redesign; `tests/strategy/test_orb_tensec_g2.py` is its mutation-checked
test (pure logic, synthetic data, no market data needed).
| **G3** | **Engine tests, mutation-checked.** Hand-built cases for: the trigger needs a *completed* 10-second close strictly beyond the level; the fill is the next printed second's open, never the trigger bar's own prices; the stop is placed off the executed fill; inside the fill second the stop fills at the stop price, never at that second's open; after it, stops gap through; one entry per symbol-day; no entry at or after 15:59:00. Reverting any one of these must fail a test. | The same shape of defect has been found by tests twice here (amendment D; the MC5 four-minute window shift). |
| **G4** | **The MBP-1 pull is priced, then landed — for H-Q1 only, after H-X1's trigger list exists.** XNAS.ITCH `mbp-1`, one window per H-X1 trade inside the MBP-1 plan window (§6.1): from 60 s before the trigger bar starts to 60 s after it ends. Run without `--confirm` first; if not $0.00 it stops for Ben. | H-Q1 reads the book at H-X1's trigger instants, which do not exist until H-X1 has run. Windowing keeps the pull to minutes per trade instead of whole days of a liquid name's quote stream. |
| **G5** | **H-Q1's positive control passes** (§5.3). | If imbalance does not even predict the next 10 seconds of the Nasdaq mid-price at these instants, the signal as built carries nothing and the gate result is uninterpretable. |

---

## 1. Why this, and why now

1. **The entry is what separates ORB's winners from its losers — measured, not argued.** Amendment F: from the
   entry bar to the close, winners' median adverse excursion is **0.63R**, losers' **5.51R**; the stop is not
   cutting winners short. `orb_sip_EXCURSION_20260919.md`'s standing fact: *"A stop is not what separates them — the
   entry is."* Both mechanisms tested here act on the entry and nothing else.
2. **ORB SIP is the only line here with a positive gross** — +0.351R against BASE friction of 0.350R
   (`orb_sip_RESOLVED_20260918.md`). On MCL and MC5 the gross is negative and friction break-even is already below
   zero (−$0.96 and −$4.67 a round trip), so **no entry timing inside a bar can rescue them**
   (`second_bars_PRICE_20260918.md`). A change at the entry can only matter where there is gross to keep.
3. **The ORB line closed with an explicit condition for reopening:** *"Any future ORB work needs a new mechanism and
   new data, not another cut of this book"* (`orb_sip_VOLUME_20260919.md`). H-X1 is new data (seconds for every
   primary symbol-day) and a new mechanism (confirmation at sub-minute resolution). H-Q1 is new data (Nasdaq
   top-of-book with sizes) and **the first entry idea in this project built on information the price bars do not
   contain** — every gate tested so far rearranged bar features and read as random removal
   (`session_close_20260918.md` §5 item 3).
4. **Data is free.** The 1-second tier (L0) priced at $0.00 for every request made so far (`price_1s.txt`,
   `price_1s_orb.txt`); XNAS.ITCH MBP-1 sampled at $0.00 inside the 12-month plan
   (`var/reports/quote_price.txt` — on small-cap windows; the ORB windows are priced afresh at G4).

**The prior against, stated first.** Two source-derived ORB filters in a row (market context, amendment H;
volume confirmation, amendment I) measured *no effect at all*, not a weak one, and my "real but insufficient"
secondary prediction was wrong both times. The regime-gate family is 0 for 5 here. The binding failure of ORB is
**concentration** (drop the single best symbol: (52.1)R), and *"any proposal that improves the mean without improving
drop-top-N has not addressed the failure"* (`handover_orb_build_chat_20260918.md` §2). That test is criterion 1 below.

---

## 2. Host — ORB's primary cell, unchanged

**Everything except the entry is ORB SIP's registered primary cell, as resolved**, and is not re-decided here:
universe (open > $5, 14-day ADV ≥ 1M, ATR(14) > $0.50), selection (top 20 by 5-minute opening-range RVOL,
RVOL ≥ 1.00, ties by symbol), direction (the 5-minute opening-range candle: up → long only, down → short only,
doji → nothing), the stop distance **r = 10% × ATR(14)** (from the ledger's `atr`, so r is the same number in every
arm for a given symbol-day), the exit (the stop, or the 15:59 close), one entry per symbol-day, the two tapes
(prices from XNAS.ITCH, RVOL from XNAS.BASIC), friction levels, and **the holdout: every session from 2026-05-01 is
locked** and is not read by anything in this study except under §8.

**The in-sample population is fixed now:** the 7,239 primary-cell trades over 446 sessions, 2024-07-22 →
2026-04-30, 1,990 symbols (`var/cache/orb_sip/trades/*.csv.gz`, `range == 5`, `rank <= 20`). Median r is
**$0.141** (p10 $0.062, p90 $0.504); median entry price $46.26; 68% of entries by 09:40, 15% after 10:00.

**Why "1-minute setup, 10-second trigger" maps onto this host.** The setup — universe, range, direction — is read
on minute bars exactly as registered. Only the trigger drops to 10 seconds.

**Why not the small-cap books** (the item sits in W05 because the idea is Cameron's, from small-cap practice):
their gross is negative, so a better entry inside the bar has a measured ceiling below zero (§1.2); and pre-market
depth is the thinnest version of the imbalance signal, where displayed size means least. A 10-second strategy on the
small-cap universe with **its own** setup (e.g. the micro-pullback on 10-second bars) is not ruled out by anything
here; it is a separate registration.

---

## 3. The arms, exactly

All three arms run on the same 1-second engine (XNAS.ITCH `ohlcv-1s`, exchange prints only — the same tape
amendment B chose for ORB's prices). Seconds are stamped with their start. A 10-second bar is the clock-aligned
interval [hh:mm:s0, s0+10) for s0 in {00, 10, …, 50}; its close is its last print; a 10-second interval with no
print is not a bar and cannot trigger.

### 3.1 B0 — the baseline: the registered resting stop, on seconds

A buy stop at the opening-range high (sell stop at the low), live from 09:35:00. It fills in the first second whose
high reaches the trigger (low, for a short): at the trigger, or at that second's open if the second opened beyond it.
**B0 is the published strategy at finer resolution, not a new arm** — G2 checks exactly that.

### 3.2 T1 — H-X1: the 10-second confirmation trigger

- **Trigger:** the first 10-second bar starting at or after 09:35:00 whose **close is strictly above the opening-range
  high** (long) or **strictly below the low** (short). No other condition.
- **Fill:** the **open of the first printed second at or after the trigger bar ends** — a marketable order sent when
  the bar completes, arriving within the next printed second. Never a price from inside the trigger bar.
- **No entry** from a trigger bar ending after 15:59:00.
- **Stop:** r from the executed fill. Inside the fill second, if that second's range reaches the stop, the stop fills
  **at the stop price** (amendment D, one resolution down; the `same_second` convention of amendment E.2 — the
  conservative side). From the next second on, a second opening beyond the stop fills at its open.
- **Exit:** the stop, or the last print at or before 15:59:59.

Every T1 symbol-day is a B0 symbol-day (a 10-second close beyond the level implies a touch of it), so T1 is B0's
symbol-days, some dropped and the rest entered later at a different price.

### 3.3 T2 — H-Q1: T1, kept only when Nasdaq's top of book leans the trade's way

- **Signal:** on XNAS.ITCH `mbp-1`, the top-of-book imbalance
  **I(t) = (bid size − ask size) / (bid size + ask size)**, at Nasdaq's best bid and offer, taken **time-weighted over
  the trigger bar itself** — the same 10 seconds that decided the trigger. Signed by side: **I_s = I** for a long,
  **−I** for a short.
- **Rule:** **keep the T1 trade if I_s > 0, discard if I_s < 0.** A sign, one bit per trade, no threshold — the same
  parameter-free form as amendments H and I, for the same reason: a threshold makes it a grid, and a grid on a book
  this concentrated is a search.
- **I_s == 0 exactly** → bucket `FLAT`, reported, in neither side.
- **No usable book** (no two-sided Nasdaq quote at any point in the bar, or locked/crossed for the whole bar) →
  bucket `NO_BOOK`, reported with its count and P/L, in neither side. If `NO_BOOK` exceeds 5% of T1 trades in the
  window, the report says so at the top.
- **Population:** T1 trades inside the MBP-1 in-sample window (§6.1) only.

---

## 4. Friction and fills

BASE friction, as registered for ORB (1¢ entry, 2¢ stop exit, 1¢ close exit, IBKR tiered commission), is the level
every criterion is read at; PAPER and HARSH are reported beside it. T1's entry is a marketable order after the bar,
not a resting stop, so its 1¢ is charged on top of the next-second open.

**Fill check (T1, inside the MBP-1 window, reported):** each T1 entry re-priced at the Nasdaq ask (long) or bid
(short) standing at the fill instant, no added slippage, against the modelled fill. **If the median quote-based fill is
worse than the modelled fill, a T1 pass is suspended** and the report says the fill model understated T1's entry
cost; a pass on a fill model that fails its own check is not a pass.

---

## 5. Controls and readings

### 5.1 H-X1 (T1 against B0), full in-sample, 446 sessions

1. **Paired delta, both denominators:** per trade (each book's own mean R) and **per symbol-day** (total R over the
   7,239 B0 symbol-days, T1 counting 0 where it did not trade). A sign disagreement between them is a refusal.
2. **drop-top-N on the delta** by symbol, N = 1, 3, 5.
3. **Random-removal control:** B0 with the same number of symbol-days T1 skipped removed at random, 2,000 draws,
   seed 20260916. T1 must beat the control's 95th percentile on mean net R **and** on drop-top-5.
4. **Decomposition, reported:** the abstention part (B0's R on the symbol-days T1 skipped) and the price part (T1 R
   − B0 R on shared symbol-days); the confirmation premium, (T1 fill − level) / r, as a distribution; the entry
   delay in seconds; how many of B0's entry-minute stop-outs T1 avoids, and how many of B0's top-50 trades it keeps.

### 5.2 H-Q1 (T2 kept against discarded), MBP-1 in-sample window

1. **Bucket table**, VOLUME/CONTEXT format: KEPT / DISCARDED / FLAT / NO_BOOK — trades, mean net, gross, total,
   drop-top-5, win rate, bootstrap.
2. **Shuffled-label null:** the KEPT/DISCARDED labels dealt at random to the same trades, proportion preserved,
   2,000 draws, seed 20260916. KEPT must beat the null's 95th percentile on mean net R **and** on drop-top-5.
3. **Two denominators**, per trade and per symbol-day, KEPT against DISCARDED; a sign disagreement is a refusal.
4. **Composition, reported, never scored** — the time-of-day proxy lesson of amendment I: KEPT share by entry-time
   bucket, by side, by spread in ticks at the trigger (one-tick names are where imbalance is known to mean most),
   and by listing venue (Nasdaq-listed against the rest, §7.2).

### 5.3 H-Q1 positive control (G5) — must pass for §5.2 to be scored

At each T1 trigger instant (the trigger bar's end), take the Nasdaq mid-price m0 and the mid 10 seconds later, m1.
Among triggers where m1 ≠ m0, the share where the mid moved **the way I_s pointed** must exceed 50% with a one-sided
binomial p < 0.01. This is the most replicated short-horizon fact in market microstructure; if it does not hold here,
the construction or the tape is broken and T2 is not scored — the report says so and stops.

---

## 6. Samples

### 6.1 The MBP-1 window is rolling and shrinking — fixed by rule, recorded by the run

The MBP-1 entitlement is the **last 365 days** (`quote_price.txt`: plan edge 2025-09-19 on 2026-09-19). Its start
moves forward one day per day. **H-Q1's in-sample window is every in-sample session from the plan edge on the day the
G4 pull runs through 2026-04-30**; the report prints the first date. Today that is 2025-09-23 → 2026-04-30:
**152 sessions, 2,489 B0 trades** — about a third of the ORB sample, and it loses roughly one session a day until the
pull lands. The holdout sessions (2026-05-01 → 2026-09-16) stay inside the plan until 2027-05 and are not pulled now.

### 6.2 Halves

Split at the median session date of each hypothesis's own sample, derived once, never swept: 446 sessions for H-X1,
the §6.1 window for H-Q1.

---

## 7. The bar — all of it, or the hypothesis is not carried forward

ORB's criteria as restated in amendment C.2, in R at BASE friction, on the arm's **kept book** (T1 for H-X1; T2 KEPT
for H-Q1), on its own sample:

1. **drop-top-3 and drop-top-5 by symbol both > 0** — the concentration test, and the one ORB failed;
2. symbol-cluster bootstrap P(total > 0) ≥ 0.95 (`common/breadth.py`, same seed and resamples);
3. mean net ≥ **+0.05R** a trade;
4. trades ≥ 100;
5. both halves > 0;
6. both sides (long, short) > 0;
7. *boundary rule* — **not applicable, by construction**: this registration has no ordered parameter family (10
   seconds is fixed; the imbalance rule is a sign).

**Plus, for H-X1:** §5.1 items 1–3 all met, and the §4 fill check not failed.
**Plus, for H-Q1:** G5 passed, and §5.2 items 2–3 met.

### 7.1 Retirement clauses, fixed now

- **If H-X1 fails, the sub-minute confirmation family is retired for ORB:** no 5-, 15- or 30-second variant, no "two
  closes beyond", no "close beyond by k cents". Those are this hypothesis with a knob.
- **If H-Q1 fails, top-of-book imbalance is retired as an entry selector on this project:** no threshold on |I|, no
  snapshot-instead-of-time-weighted, no deeper book (MBP-10), no longer window, no second venue. If G5 fails, the
  signal as built is recorded as uninformative at these instants and nothing further is registered on it without a
  stated reason why the construction, not the idea, was at fault.

### 7.2 What this registration does not claim — the four required disclosures, and three more

1. **Priced before bought.** G1 and G4 each run without `--confirm` and report the vendor's number first. A non-zero
   number stops the step for Ben; the study does not silently switch tapes or windows.
2. **XNAS.ITCH and IBKR's Nasdaq TotalView are both Nasdaq's book, not the consolidated market.** For a
   Nasdaq-listed name, Nasdaq's best quote is usually the market's best; for an NYSE-listed name (four of ORB's top
   five carriers — MWA, TD, NYT, THC — are NYSE-listed) it is one venue among many. The report splits H-Q1 by listing
   venue, reported and never scored. **The live signal would be the same Nasdaq-only book**, so backtest and live read
   the same thing — which is why the consolidated tapes that also priced at $0 (EQUS.MINI, XNAS.BASIC) are not used.
3. **Displayed size is not committed size.** Hidden and reserve orders do not show; fleeting quotes and cancels do.
   Time-weighting over 10 seconds damps a fleeting quote; nothing here models intent.
4. **Pre-market depth is the thinnest version of the signal** — the reason this host is RTH-only (entries from 09:35).
   Nothing measured here transfers to the pre-market books.
5. **H-Q1's sample is about a third of ORB's** (§6.1), so its bootstrap and halves are weaker than H-X1's by
   construction.
6. **Live parity is not tested.** IBKR's depth stream is not tick-by-tick, and there is no live ORB trader. A pass
   earns a live-parity registration, not a deployment.
7. **Shorting** carries ORB's §6.2 limits unchanged (no borrow fee, locate or SSR modelled); the short side is
   reported separately.

---

## 8. What a pass would buy

The locked holdout (2026-05-01 → 2026-09-16, both tapes pulled only then) is spent **once**, by the one passing
configuration, exactly as registered here. Then Ben decides (§11 step 8): register live parity, keep as study-only, or
close. Nothing here commits to any of them.

---

## 9. Predictions, scored either way

- **H-X1: NOT ADOPTABLE — fails criterion 1 and does not beat the random-removal control's 95th percentile.**
  Mechanism: confirmation filters only fakeouts measured in seconds, while ORB's losers are real reversals over
  minutes to hours (median adverse excursion 5.51R; 81.2% of trades freed from an entry-minute stop re-reached it
  within a minute or two anyway, amendment E). Meanwhile the confirmation premium comes off every winner, and the
  stop moves with the fill so it saves nothing on a loser. **Secondary: the per-symbol-day delta against B0 is
  negative.**
- **H-Q1 positive control (G5): PASSES.** High confidence.
- **H-Q1: NOT ADOPTABLE — KEPT sits inside the shuffled null (p > 0.05) on both mean R and drop-top-5.** Mechanism:
  the imbalance forecasts the next few seconds — about a tick — while an ORB trade is decided over minutes to hours
  at a scale of several R. **No secondary "real but insufficient" prediction is made**: that form was wrong twice in
  a row on this book (amendments H and I).

If all three hold, the finding is that **the information exists at the trigger and does not reach the trade's
horizon** — which would point imbalance at execution (when to cross the spread versus rest a limit), not at selection.

---

## 10. What would make this run wrong

- Running any arm, or pulling any MBP-1 record, before this document is committed.
- Scoring anything before G2 (B0 parity) has passed.
- Reading a criterion at PAPER friction, or quoting T1 without B0 and the random-removal control beside it, or T2
  KEPT without the shuffled null.
- Changing 10 seconds, the strict-beyond rule, the fill rule, the time-weighting, the sign rule or the window after
  seeing any result. Each is a new registration, and §7.1 has already refused the obvious ones.
- Scoring H-Q1 after a failed positive control.
- Touching the holdout for anything but §8.

---

## 11. Timeline — board item W05-0003, one subitem per step

| # | Step | Who | Rec. model / effort |
|---|---|---|---|
| 1 | Register (this document) | Build & test chat | Opus / High — done 2026-09-23 |
| 2 | Commit this document to git, before any code | Ben (commands on the subitem) | — |
| 3 | G1: list the missing primary symbol-days; price the 1-second pull; Ben runs the confirm | Build & test chat → Ben | Sonnet / Low |
| 4 | G2 + G3: the 1-second engine (B0, T1), B0 parity, mutation-checked tests. Merge W12-0003 (`orb-20260919d.bundle`) first so `strategy/orb/` is current | Build & test chat | Sonnet / High |
| 5 | Run H-X1 with §5.1; Result doc, raw `.txt`, artifact page | Build & test chat | Sonnet / Medium |
| 6 | G4: price and pull MBP-1 windows at T1's in-window triggers — **promptly: the window loses a session a day** | Build & test chat → Ben | Sonnet / Low |
| 7 | G5, then H-Q1 with §5.2 and the §4 fill check; Result doc, raw `.txt`, artifact page | Build & test chat | Sonnet / High |
| 8 | Decide, per §8 | Ben | — |

**No dependency on W03-0002** (the small-cap spread gate): different universe, different tape (`cbbo-1s` around
MCL/MC5 entries), different pull.
