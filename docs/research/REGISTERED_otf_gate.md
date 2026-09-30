# REGISTERED — OTF-G v1: one-time-framing regime gate (monthly + weekly + daily all stepping the trade's way) on two existing futures trade books

**Written before any one-time-framing state has been computed on any bar, and before any host trade has been joined
to a state.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0025** (sub 1 = this file; sub 2 = Ben reviews + commits; sub 3 = build + free gates; sub 4 = count-only
pre-flight; sub 5 = training run + Result doc). Companion registration, same item: `REGISTERED_va80.md` (the "80%
value-area rule" on ES). Source: `claude/w11_0034_iqcapital_review_RESULT_20260928.md` shortlist #7 and
`claude/raw/w11_0034_iqcapital_extracts_20260928.txt` (batch 6, video 1 — Imre, IQ Capital, SQZjXXNSlcU, after
Jim Dalton, *Mind Over Markets*). Ben chose it on W11-0035 (option D).

**Ben's decisions, 2026-09-30, his multiple-choice picks:**
- Scored gate: **"Strict: all 3 agree (Recommended)"** — keep a trade only when month, week and day all step its way.
- Hosts: **"Donchian + ES/NQ ORB (Recommended)"** — two scored hosts, each against 97.5% of random removals.
- 80% rule: **"Yes, register it now (Recommended)"** — in `REGISTERED_va80.md`, not here.
- Costs: IBKR (W15-0033, Ben 2026-09-30: *"please use the IBKR costs as that will be the broker i'm using"*;
  levels = all-in fee + 0 / 1 / 2 ticks per side).

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is a new
hypothesis (§9).

---

## In plain terms

Imre's rule: look at the monthly, weekly and daily candles. A candle "steps up" when it makes a higher high, a higher
low **and closes above the previous candle's high** (mirror for down). Anything else is "balance" (a range). Only buy
when all three timeframes are stepping up, only sell when all three are stepping down, otherwise stand aside.

We don't have a strategy of our own that passed, so we test the rule as a **filter on two trade books we already
have**: the 20/10 Donchian channel on 12 futures markets (daily) and the ES/NQ opening-range breakout (1-minute). Both
lost money on their own. The question is **not** whether the filter turns them into winners. It is whether the trades
the filter keeps are better than the same number of trades kept **at random**. If the answer is yes, the filter
becomes a component we can add to any future strategy that passes its own test. It never reopens a closed one.

---

## 0. Where this sits, stated plainly

- **The claim.** Imre (rules 1–7, 11): the one-time-framing (OTF) read is mechanical; in a three-timeframe-aligned
  trend, breakout/continuation setups outperform; when timeframes disagree, stand aside. Stated performance: none
  (anecdotal). Balance "about 70% of the time" (claim — measured in §3, not scored).
- **Hosts, not chosen on a result of this gate.** Both are breakout rules, which is what rule 11 says the gate helps:
  - **H-A · C1 Donchian 20/10**, 12 markets, daily, as built in TL-v0 and re-run in W15-0020
    (`strategy/tl_v1/engine.py`, "same code as TL-v0's C1"). Training books on disk:
    `Claude outputs/tl_v1_backtest_trades_20260929.csv`, spec `C1`, sizing `frac`, **1,175 trades**, net **($847)**
    at the old mid friction. Same host MFLAG-v1 used (closed FAIL, W15-0023).
  - **H-B · W16 SB-v0 B1 ORB**, ES + NQ, 1-minute, long + short, 2:1 (`REGISTERED_w16_session_baselines.md` §3.1),
    **3,443 + 3,427 trades**, nets **($14,617)** / **($2,384)** at NinjaTrader L2 (W16-0003, closed). Per-trade books
    were not saved; the build re-runs the frozen engine (`strategy/w16/`) on the training side (G5 proves it
    reproduces the counts).
- **Not a rescue.** The gate may never be applied to a failed or closed strategy to change its verdict (C1 is a
  control, B1 is closed, and TL-v1, HTF-Ben v2, CHARTMARK-v1/v2, CHARTMARK-S v1, MFLAG-v1 are closed). On other books
  it is **reported only** (§2.5).
- **Removing trades from a losing book "helps" on its own.** That is why the headline is always versus random removal
  (C-R), never versus zero or versus the host.
- **What has been seen.** No OTF state on any bar. The host books' total P&L and by-year/by-market splits (published
  Result docs) have been seen — they cannot tell us how a state split would come out, but they are known.

---

## 1. The hypothesis, in one sentence

**Keeping only the host entries whose direction matches a one-time-framing state that is the same on the last
completed monthly, weekly and daily bars (up for longs, down for shorts) gives a kept book whose net after IBKR costs
is above zero and above the 97.5th percentile of keeping the same number of randomly chosen trades per market and
direction — on the Donchian 20/10 daily book, on the ES/NQ opening-range-breakout book, or both.**

---

## 2. The rules

**Every number is fixed here, before any state is computed. None is tuned.**

### 2.1 The one-time-framing state of one timeframe (bar series b[0..n])

State ∈ {UP, DOWN, BAL}, with a reference bar `ref` while in BAL. Read at the **close** of bar t:

| Test at bar t | Definition |
|---|---|
| **OTF-up(t)** | H[t] > H[t−1] **and** L[t] > L[t−1] **and** C[t] > H[t−1] |
| **OTF-down(t)** | L[t] < L[t−1] **and** H[t] < H[t−1] **and** C[t] < L[t−1] |

| State before t | Transition at t |
|---|---|
| UP | OTF-up → stay UP. Else OTF-down → DOWN. Else → **BAL, ref = bar t**. |
| DOWN | OTF-down → stay DOWN. Else OTF-up → UP. Else → **BAL, ref = bar t**. |
| BAL (ref r) | C[t] > H[r] → **UP**. C[t] < L[r] → **DOWN**. Else stay BAL, **ref unchanged** (Imre rule 4: a bar inside a balance that looks bullish or bearish on its own does not end it unless it closes past the reference bar). |

- Strict inequalities; equal prices do not step. Initial state: BAL with ref = the first bar of the series.
- "The candle that starts a balance period" (Imre rule 4) is read as **the first bar that fails to continue the
  step** — the bar at which the state leaves UP/DOWN. Written here because the transcript does not say it exactly.
- Prices: the **back-adjusted signal series** of each host (§2.3). OTF compares neighbouring bars and a reference bar,
  so an additive back-adjustment leaves every comparison inside one contract unchanged.

### 2.2 The stack and the gate (primary: strict)

For a host trade with entry fill at time τ and direction d ∈ {long, short}:

- **Daily state** = the state after the **last daily bar completed before τ**.
- **Weekly state** = the state after the **last week completed before τ** (a week still in progress at τ is not
  used).
- **Monthly state** = the state after the **last calendar month completed before τ**.
- **KEEP** the trade if all three states are UP and d = long, or all three are DOWN and d = short.
  **REMOVE** it otherwise (any BAL, any disagreement, or aligned against the trade).

The action is **skip**: a removed trade is simply not in the kept book (flat from its entry to its recorded exit).
Whether the host would have re-entered in that span is not modelled (it would need an engine re-run and adds a free
choice) — same convention as MFLAG-v1 §2.3.

**Delta** = net(kept book) − net(host book) = − Σ net of removed trades.

### 2.3 Bars per host

| Host | Daily bars | Weeks | Months |
|---|---|---|---|
| **H-A C1** | The host's own daily rows: `strategy.tl_v0.bars.load_market` (UTC days, Sunday rows folded, TSMOM roll rule, difference back-adjustment on the roll session), training rows only | ISO week of the session date (Mon–Fri sessions of one ISO week form one bar) | Calendar month of the session date |
| **H-B B1** | **Rebuilt from the owned ES.v.0 / NQ.v.0 `ohlcv-1m`** (W16 archive) by CME trading date: 18:00 ET of the prior day → 17:00 ET, matching the TradingView ES1!/NQ1! daily candle Imre reads. Back-adjusted additively at each change of `instrument_id`: gap = open of the first 1-min bar of the new id − close of the last 1-min bar of the old id (must be ≤ 5 minutes apart; else stop and report) | CME week (Sunday 18:00 ET → Friday 17:00 ET) | Calendar month of the CME trading date |

Weekly and monthly bars are aggregated from the daily bars of the same series (open = first open, high/low =
extremes, close = last close). A week or month is "completed" when its last session's close is ≤ τ.

For H-A, C1 enters at the open of session s after a signal on s−1, so the daily state is the state after bar s−1.
For H-B, B1 enters at 10:01 ET or later on session s, so the daily state is the state after the CME trading day
ending 17:00 ET the evening before.

### 2.4 Costs, sizing, books

- **Costs: IBKR**, all-in per contract per side (commission + exchange + regulatory), read from IBKR's published
  pages by **W15-0033** for all 12 C1 markets and ES, NQ, MES, MNQ, and written into this file as a **PRE-RUN
  amendment before any P&L is read** (G5). Levels per side: **low** = fee + 0 ticks, **mid (headline)** = fee +
  1 tick, **high** = fee + 2 ticks. H-A: ticks apply to every side (C1's entries, stops and rolls are all market or
  stop fills). H-B: ticks on every market or stop fill; B1's target limit fills 0 ticks (`REGISTERED_w16_session_
  baselines.md` §4 convention).
- **H-A re-costing:** each trade's IBKR net = `gross` − (fee + k × tick value) × `qty` × `sides`, from the books'
  own columns. G5 first proves the old net is reproduced from the same columns (($847) at the old $1.25 mid).
- **Sizing:** the hosts', unchanged. H-A fractional on $22,129; H-B 1 MES / 1 MNQ per trade (headline), 1 ES /
  1 NQ reported.

### 2.5 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| **Soft (no-contra)** | remove only trades where at least one timeframe is OTF *against* d; keep BAL | the looser reading Ben didn't choose |
| **Day + week only** | drop the monthly leg | whether the slow leg carries it |
| **Live candle** | weekly/monthly states also read the bar in progress (week-to-date / month-to-date through the last completed day) | what a chart reader sees intraday |
| **Dalton classic** | OTF-up = L[t] > L[t−1] only (no close test), mirror for down | Dalton's own definition vs Imre's stricter one |
| **C-N naive alignment** | keep if C > prior C on the completed month, week and day all agree with d | whether OTF's specific form adds anything over "any trend alignment" |
| **Opposite gate** | keep only trades aligned *against* d | the mirror should do worse |
| **Other books** | the strict gate on TL-v1 ensemble and TL-v0-rev (W15-0020 / W15-0014 books), HTF-Ben v2 CL 4H (regenerated), B1 long-only, B2 overnight long (kept when M/W/D all UP), CHARTMARK-v1 and CHARTMARK-S v1 base books (CL 1H) | whether it travels; **never changes those studies' verdicts** |
| **Integer sizing** | H-A integer books at $22,129 | whether it survives whole contracts |

**Not coded (known departures):** Imre's balance-regime trade (fade value-area edges — that is `REGISTERED_va80.md`);
the "pullback to value then resume" entry; any volume-profile reading; options.

---

## 3. What every run must emit

- **State census (claim check, not scored):** per host series and timeframe, share of bars in UP / DOWN / BAL, mean
  run length of each, by year. Imre's "balance ≈ 70%" is reported beside it.
- **Counts:** host trades; kept / removed by market × direction × year; removed split by reason (any BAL; disagree;
  aligned against d); trades before the monthly state is first defined (counted, removed).
- **Books, per host, at low / mid / high:** host net, kept net, removed net, delta; trades, wins, losses, win %,
  mean win, mean loss, mean net per trade for kept vs removed; worst drawdown of the kept book; by year and by market.
- **Sample trades:** the ten largest kept winners and losers and removed winners and losers (market, date, side,
  states M/W/D, net $).
- **C-R random keep (the control):** per host, for each market × direction cell keep the same number of trades as the
  gate keeps, drawn at random from that cell's host trades; 1,000 seeded draws
  (`np.random.default_rng([zlib.crc32(str(draw)), zlib.crc32(cell), 25])`); kept-net p5 / p50 / p95 / p97.5 / p99
  and the gate's percentile (share of draws strictly below, plus half the ties).
- Every §2.5 variant with its own C-R percentile. **Nothing is ranked. No best-variant table.**

---

## 4. The bar to clear — per host, strict gate, IBKR mid, training side

A host **passes** only if all hold:

1. **Kept net > $0** at mid.
2. **Kept net > the p97.5 of C-R** (97.5, not 95, because two hosts are scored).
3. **Both halves:** mean net per kept trade > mean net per removed trade in each half (split at the median entry
   date of the host book).
4. **Kept net > $0 at high** friction.
5. **No single market and no single year** supplies more than 50% of kept net (H-B: no single year, and neither ES
   nor NQ alone supplies more than 75%).
6. **Enough kept trades:** H-A ≥ **60**, H-B ≥ **150** (ES + NQ). Fewer → **NOT READ** for that host, not failed. No
   loosening to the soft gate, no adding hosts to rescue the count.

**Failing 2 closes that host's reading, whatever else passes.** The gate **passes the training side** if at least one
host passes all six.

---

## 5. Before the run — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | **Data.** H-A: host books + the TL-v0 loader's daily rows (owned). H-B: ES.v.0 / NQ.v.0 `ohlcv-1m` from the W16 archive (owned). No new pull. | Open (sub 3) |
| G2 | **Count-only pre-flight** (sub 4): state census (§3) and kept / removed counts per host × market × direction × year. Reads host columns `market, spec, sizing, equity, direction, entry_date, entry_j` (H-A) and B1's entry times and sides (H-B) only; a test proves no gross / net / exit column is loaded. | Open |
| G3 | **Holdout ledger** `holdout_otf_gate.json` (§6), own lock, refused by name from every other ledger; refuses `--limit` and date-narrowing flags; mutation-tested. | Open |
| G4 | **Look-ahead guards**, each proven by a test that a one-bar shift breaks: (a) the state used for a trade comes only from bars completed before τ; (b) a week/month in progress is never used by the primary; (c) BAL's reference bar is fixed when BAL starts; (d) H-B's daily bar for session s ends 17:00 ET before s. Plus a hand-worked synthetic series with known states for every row of the §2.1 table. | Open |
| G5 | **Books reproduce, then IBKR.** H-A: C1 frac from the CSV = 1,175 trades, ($847) at the old mid. H-B: the re-run B1 = 3,443 ES / 3,427 NQ trades and ($14,617) / ($2,384) at NinjaTrader L2. Only then are IBKR costs (W15-0033, PRE-RUN amendment here) applied. | Open (blocked by W15-0033 for the fee table) |
| G6 | **H-B daily bar check:** rebuilt sessions per year vs XNYS trading days (missing > 1% → stop); roll gaps listed; ES OTF daily-state agreement with the H-A ES series reported (different day boundaries, so not a stop). | Open |

**Stop rule, fixed now:** if the pre-flight shows fewer than 60 kept H-A trades **and** fewer than 150 kept H-B
trades, the study stops there and the counts are the finding — back to Ben before any P&L is read.

---

## 6. The holdout

- **H-A:** training 2010-06 → 2021-12-31; holdout **2022-01-03 → 2025-09-22** (C1 re-run on holdout bars with the
  same code, same sizing, IBKR costs). **H-B:** training 2010-06-06 → 2023-12-29; holdout **2024-01-02 → the end of
  the owned 1-min data** (B1 re-run in holdout mode).
- Ledger **`holdout_otf_gate.json`** (keys per host). **Spent once per host, only by a host that passes all six §4
  criteria.** Holdout pass = kept net > $0 at mid **and** ≥ p90 of C-R on the holdout, reported with the kept count.
- **Overlap:** the same windows are held out by TL-v1, TL-v2, MFLAG-v1, CRUDELE-3S, BREIT-CAP (H-A) and W16 SB-v0 /
  bar-batch (H-B) for different hypotheses. None has been spent. If more than one ever is, all holdout results are
  reported together.
- **Seen window:** 2025-09-23 onward (H-A markets) — never scored.

**What a pass buys:** OTF-G becomes a registered, available filter. It is applied to a strategy only inside that
strategy's own registration, and only a strategy that has passed its own training bar (candidates today: TL-v2,
CRUDELE-3S, BREIT-CAP, CHARTMARK-S v2 — none has yet).

---

## 7. Registered as NOT to be done

- Changing the OTF definition, the reference-bar reading, the timeframes or the gate after a result.
- Swapping a §2.5 variant (soft, D+W, live candle, Dalton classic) in as the primary after a result.
- Applying the gate to change the verdict of any closed or failed strategy.
- Quoting a variant, a single market, gross, or "versus the host" as the headline.
- Spending the holdout on anything but a six-of-six pass.

---

## 8. Ways this could go wrong

- **Few kept trades.** Three strict tests at once, with balance claimed ≈ 70% per timeframe, may keep only 5–15% of
  trades. The pre-flight decides before any P&L; a thin count is NOT READ.
- **The gate is just a trend filter on a trend host.** Donchian already trades with the trend, so alignment may add
  little; C-N (naive alignment) shows whether OTF's form matters.
- **Monthly bars are slow.** About 139 monthly bars in H-A's training window; the monthly leg changes state a few times a
  year. Month-to-month autocorrelation means kept trades cluster in a few trending spells — criterion 5 guards it.
- **Intraday host, daily gate.** B1 is a same-day trade; M/W/D alignment may carry no information about the next
  six hours. That would be a fair answer.
- **Day boundaries.** H-A uses UTC days (the host's own), H-B uses CME trading days. Both are stated; neither is
  chosen on a result.
- **Friction saved by skipping is not an edge.** C-R saves it too.

---

## 9. Multiplicity budget

One primary (strict, §2.2), two scored hosts at p97.5 each, one variant family (§2.5, unranked), one holdout spend per
host. A second OTF registration needs a reason that does not begin with this result.

---

## 10. A prediction, written down now

**H-A keeps about 100–200 of 1,175 trades, and H-B keeps about 10–20% of its ~6,900. Balance comes in near 50–60% per
timeframe on daily bars (below Imre's 70%) and higher on monthly. On H-A the kept trades do better than the removed
ones, but only at about the 80th–95th percentile of C-R — criterion 2 fails. On H-B the gate sits near the middle of
C-R (a daily-and-up regime says little about a six-hour breakout). Most likely reading: *three-timeframe alignment is
a mild trend filter on a trend host and nothing on an intraday breakout.*** I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0025 sub 2** (Ben): review, then commit this file and `REGISTERED_va80.md` (commands on the board).
- **W15-0025 sub 3** (Build & test chat, Sonnet · High): OTF state engine, H-B daily rebuild, guards G3/G4/G6, host
  book loaders, G5 reproduction; handover `claude/handover_w15_0025_build_20260930.md`.
- **W15-0025 sub 4** (Ben runs, Build & test chat reads): count-only pre-flight.
- **W15-0025 sub 5** (Build & test chat, Sonnet · Medium): training run → Result doc.
- **W15-0033** (High timeframe chat): IBKR fee table for the 12 markets + ES/NQ/MES/MNQ (blocks G5).


---

## Amendment 1 (PRE-RUN, 2026-09-30, W15-0025 sub 3) -- implementation details fixed before any real-data run

No rule, threshold, variant, criterion or ledger date above is changed. These are choices the code had to make where the text was silent. They are written down before the first real-data pre-flight so none can be chosen on a result.

1. **H-B daily rebuild.** The trading-date label is the bar's ET time plus 6 hours (18:00 ET opens the next label); bars from 17:00 to 17:59 ET (the maintenance hour) are dropped. Daily open/high/low/close are the first open, max high, min low and last close of each label.
2. **H-B roll join.** At an `instrument_id` switch the later contract is shifted by (last close of the old contract minus first open of the new one) -- additive back-adjustment on every earlier bar. If the two 1-minute bars are more than 5 minutes apart the run STOPS (`RollGapError`); nothing is patched.
3. **G6 session check.** Each year's rebuilt sessions are compared with the XNYS days; more than 1% missing in any year = STOP. The training cut (`<= 2023-12-29`) is applied before the daily bars are built, so no holdout bar is in the rebuild.
4. **Random-keep control (C-R) seed layout.** `np.random.default_rng([crc32(str(draw)), crc32(cell), 25])`, 1,000 draws, p97.5; the keep count per cell is the gate's kept count in that cell. Pinned by a test.
5. **Pre-flight reads no P&L.** The book loaders read key columns only (market, spec, share, sizing, equity, direction, entry date/time); a test spies on `usecols` and fails if a P&L column is requested. H-B pre-flight uses an entry-only mirror of the B1 rule (no fill, exit or outcome bar is read; tests poison every bar after the entry and the result does not change).
6. **`--run`.** Refuses unless a pre-flight `.json` on disk carries the same SHA-256 of every input as the current run and did not stop. Until the study module (G5 costs, C-R, sec 4 criteria) exists it stops with "study module not built (sub 5, blocked by W15-0033)".
7. **Ledger.** `strategy/otf_gate/ledger.py` refuses every other line's ledger by name, including `holdout_va80.json`. **The reverse refusals were NOT added to the frozen ledger modules of other lines** (futbt, w16, macro_flag, ...): this file did not authorise editing them. Whether to add `holdout_otf_gate.json` and `holdout_va80.json` to their refusal lists is a decision for Ben (board item opened in sub 3).
8. **Test status at delivery.** 93 unit tests on synthetic data pass (both packages); a mutation run of 47 deliberate code breaks was caught by the tests in 44 cases, the other 3 being provably equivalent changes.
