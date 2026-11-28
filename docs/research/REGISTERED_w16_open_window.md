# REGISTERED — W16 OWA-v0: overnight MNQ open-window algo (EMA9/21 on 5-min; triggers A/B/C × 1H and 15-min trend filters; two-sided; trailing exit, flat 15:55 NY)

**Written before any code for these rules exists, and before any return from them has been seen on our data.**
`PROGRAM_INDEX` §2.4: a hypothesis is registered before it is run. Amendments are marked **PRE-RUN** or
**POST-RUN**. A rule or threshold changed after seeing a result is a new hypothesis and spends from §11.

**Board:** Algo Trading `5031413876`, item **W16-0040** (`2923031118`). Subitems on `5031415830`: 1 = Pine draft
(Done); 2 = Ben loads it (Done); **3 = this file**; 4 = build; 5 = Ben runs; 6 = Result doc; 7 = NAS paper deploy only
if it passes.
**Source:** Ben's own idea, 2026-11-28 (`claude/handover_w16_0040_open_window_algo_20261128.md`, revised 12:50
Sydney). Trigger C is his 4H crude trigger (W15, HTF-Ben) scaled down to 5-min.
**Engine:** the W16 engine (`strategy/w16/`), with the extensions §2 and §4 list. It uses the same data and the same
XNYS calendar and early closes as `REGISTERED_w16_session_baselines.md` (SB-v0) §2. **Costs are not SB-v0's:** this
line uses the IBKR table (§5), as for all futures studies since W15-0033.
**Chat:** Scalping chat. **Indicator:** `D:\Trading\Claude outputs\w16_0040_open_window_signals_v0.pine`,
re-synced to this file as **v1.0** (§14).

**Ben's decisions, 2026-11-28 (his multiple-choice picks and words):**
- Entry trigger: **"Test all three"**. A, B and C are each scored separately.
- Timeframe: **"5-min (Recommended)"**.
- Exit: **"Trail, hold to 08:00"**: a trailing stop, with anything still open closed before the 16:00 NY close
  (flat 15:55 NY = 07:55 Sydney in AEDT).
- TradingView: **"Yes, signals only (Recommended)"**: the indicator shows no P&L, so the 2024+ holdout stays clean.
- Direction: **"for futures, it's ok to go short as well"**. Both sides are scored together and each side is also
  reported.
- Window start: **"start at Sydney midnight"** → **08:00 New York** (anchored to NY, so it is 22:00 Sydney when
  Sydney is on standard time).
- Window end: **"04:00 Sydney (Recommended)"** → entries until **12:00 NY**.
- Trend filter: **"Test 1H and 15-min (Recommended)"**. 1H EMA9/21 is the main version; 15-min is a scored variant.

**Caution (from the handover):** Ben's example nights (19–24 Nov 2026) fall in the locked holdout period (and after
the end of our pulled data, 2026-10-27). The window and filter changes they prompted are registered here before any
run and are judged on 2010–2023 only. Nothing is tuned on those charts.

---

## In plain terms

The big Nasdaq futures moves happen between midnight and 4 am Sydney time, while Ben is asleep. This rule watches
5-minute micro Nasdaq (MNQ) bars from 08:00 to 12:00 New York time and trades only in the direction of the hourly
trend (or, in the variant, the 15-minute trend). It tests three ways of getting in: **A** a fresh EMA9/21 cross plus an
unusually big bar; **B** a big bar, then a pullback to the EMA9, then a bar that breaks out again; **C** Ben's MACD
trigger with the EMA9 turning back toward the EMA21. Every trade has a stop below the recent swing that then trails
2.5 "normal bar sizes" (ATR) behind the best price, and anything still open is closed at 15:55 New York. At most two
trades a day. We charge IBKR's real fees plus a tick of slippage on every fill and test 1 MNQ on mid-2010 to 2023 data.
Each version must beat the same trades taken at random later times in the same window. If one passes everything it
gets a single look at the locked 2024-onward data.

---

## 0. PRE-RUN GATES — no P&L is computed until every row is true

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Data**: NQ `ohlcv-1m`, full Globex hours, as SB-v0 G1 (passed 2026-09-27). No new data. Extended hours are already in the archive (used by BB-v0's NR4). | Same bars. |
| **G2** | **Pre-flight, no P&L** (§7.1): counts per cell and year, side mix, pre-open vs RTH split, stop distance in $ per MNQ, skipped sessions, big-bar rate. The runner refuses P&L in this mode. | Shows whether there is enough to read before any profit is seen. |
| **G3** | **Holdout cut and enforced in code** (§9): own ledger `holdout_w16_owa.json`, mutation-tested. | `PROGRAM_INDEX` §2.5. |
| **G4** | **Look-ahead guards tested** (§7.2), each by a test that a one-bar shift breaks. | Three timeframes (5-min, 15-min, 1H) plus a cross-session slot average. |
| **G5** | **Costs**: the IBKR MNQ row of W15-0033 (`REGISTERED_va80.md` Amendment 2) added to `strategy/w16/costs.py` as a separate table (`IBKR_ALL_IN`), with a test that the NinjaTrader table used by SB/DVP/BB is unchanged. | The W16 engine still prices NinjaTrader. Old lines must not move. |

---

## 1. The hypothesis, in one sentence

**On NQ 5-minute bars between 08:00 and 12:00 New York, at least one of triggers A, B or C, traded both ways in the
direction of the 1H (or 15-min) EMA9/21 trend with a swing stop that trails 2.5 × ATR and a 15:55 flat, makes money
on 1 MNQ after IBKR fees plus one tick per fill on 2010-06 → 2023-12, and beats the same trades placed at random later
times in the same window.**

---

## 2. Market, bars, sessions

| Element | Registered rule |
|---|---|
| Market | **NQ** (`NQ.v.0`, GLBX.MDP3), the SB-v0 series. Scored vehicle **1 MNQ ($2/pt)**; 1 NQ ($20/pt) reported. Before May 2019, micro = full ÷ 10 (SB-v0 §2). |
| Clock | All times **America/New_York** (DST-aware), converted from the archive's UTC stamps. |
| Bars | 1-min archive resampled over **all Globex hours** into clock-anchored **5-min** (:00, :05, …), **15-min** (:00, :15, :30, :45) and **1H** (top of the hour) bars; OHLC = first / max / min / last. A period with no 1-min bars has no bar. A bar is knowable at its close (start + 5, 15 or 60 min). |
| Roll handling (new) | Indicators run on a **difference back-adjusted** series: at each change of held `instrument_id`, all earlier bars are shifted by (new contract's first price − old contract's last price). Only rolls at or before a bar's time are applied to it. EMA crosses, EMA gaps, MACD and bar ranges are unchanged by a shift, so this only stops roll gaps from creating false crosses or a false true-range. **Trade prices are always the held contract's real prices.** A trade whose entry and exit 1-min bars carry different `instrument_id`s is voided and counted (not expected: 08:00–15:55 NY never spans the 00:00 UTC roll). |
| Trading days | XNYS trading days only (SB-v0 calendar). Early-close days: flat 12:55 instead of 15:55; the entry window is unchanged (ends 12:00). Non-XNYS days with Globex trading still feed the indicators and the slot average but are never traded. |
| Skipped sessions | A trading day with a gap > 15 min between consecutive 1-min bars anywhere in **07:00–15:55 NY** (12:55 on early closes) is skipped and counted. Shorter gaps just mean missing bars. |
| Warm-up | A day is tradable only once every indicator has its full history (§3.1): ≥ 21 1H bars, ≥ 21 15-min bars, ≥ 35 5-min bars and ≥ 20 prior observations for the slot average. Days before that are counted as warm-up, not skipped. |
| Account | $22,129 (W16 convention), fixed 1 MNQ per trade, no compounding. |

---

## 3. The rule

"Bar *j*" is a 5-min bar; it closes at τ_j. "Long" rules are given; shorts are the exact mirror (swap above/below,
high/low, green/red, up/down).

### 3.1 Indicators (all on the back-adjusted series, all Globex bars, standard definitions)

| Name | Definition |
|---|---|
| EMA9, EMA21 | exponential average of close, weight 2 ÷ (n + 1), seeded with the first close. On 5-min bars for the triggers; on 1H or 15-min bars for the filter. |
| ATR(14) | Wilder average (weight 1/14) of true range on 5-min bars (as Pine `ta.atr`). |
| MACD(12,26,9) | EMA12 − EMA26 of the 5-min close; signal = EMA9 of the MACD line. |
| Cross up at bar *i* | EMA9_i > EMA21_i and EMA9_(i−1) ≤ EMA21_(i−1). MACD cross up: MACD_i > signal_i and MACD_(i−1) ≤ signal_(i−1). |
| Slot average | For each 5-min clock slot *s* (its start time), an exponential average of the bar range (high − low) over **every earlier day that has a bar at slot s**, weight 2 ÷ 21 (≈ 20 days), updated **after** the day's bar at *s* is judged. Valid once it has ≥ 20 observations. |
| **Big bar** | bar *j* at slot *s* with range_j ≥ **1.5 ×** slot average_s (valid). Green = close > open; red = close < open. |

### 3.2 Trend filter — the scored dimension

At the start of bar *j* (time τ_j − 5 min), the filter state is read from **the last filter-timeframe bar that closed
at or before that time**: **UP** if its EMA9 > EMA21, **DOWN** if EMA9 < EMA21, else NONE. Longs only when UP, shorts
only when DOWN.

- **F1 (main): 1H bars.** **F15 (variant): 15-min bars.**
- This is the conservative reading the Pine draft already uses (`[1]` with `lookahead_on`): on the last 5-min bar of
  an hour, the hour that is just closing is not yet used.

### 3.3 The window

- A **signal bar** must start between **08:00 and 11:55** NY (so it closes by 12:00). The fill is the next bar's open
  (§3.5), so the latest fill is 12:00.
- No position exists before 08:00 (all trades are flat by 15:55 the day before).

### 3.4 The triggers (long; mirror for short)

**A · EMA cross + big bar.** Bar *j* fires when all hold: filter UP; EMA9_j > EMA21_j; a 5-min EMA cross up happened
at bar *j − k* for some **k ∈ {0, 1, 2, 3}**; bar *j* is a **big green** bar.

**B · Pullback after a big bar.**
- *Arming:* a **big green** bar *i* starting 08:00–11:55 with the filter UP at bar *i* arms B for bars *j* with
  **1 ≤ j − i ≤ 12**. A later big green bar re-arms (and resets the touch). Arming ends at NY midnight and when a B
  long fills.
- *Touch:* some armed bar *m* with i < m ≤ j has low_m ≤ EMA9_m (bar *j* itself counts).
- *Fire* at bar *j*: armed and touched; filter UP; EMA9_j > EMA21_j; **close_j > high_(j−1)**; **close_j > EMA9_j**.
  (The last condition is in the Pine draft Ben checked; the handover text omits it. Registered as in the Pine.)

**C · MACD + EMA9 gap (Ben's 4H trigger on 5-min).** Bar *j* fires when all hold: filter UP; a MACD cross up happened
at bar *j − k*, **k ∈ {0, 1, 2, 3}**; EMA9_j > EMA9_(j−1) (EMA9 rising); and **either** EMA9_j ≤ EMA21_j and the gap
(EMA21 − EMA9) narrowed (gap_j < gap_(j−1)), **or** an EMA cross up happened at bar *j*. (C can fire while EMA9 is
still below EMA21; that is the point of Ben's trigger.)

### 3.5 Entry

| # | Rule |
|---|---|
| Fill | **Market at the open of bar j + 1** = the open of the first 1-min bar starting at τ_j. If there is no 1-min bar starting in [τ_j, τ_j + 5 min), the signal is dropped and counted. |
| One at a time | Only while flat. Signals while in a position are ignored. |
| Re-entry | After an exit at time *x*, the next signal bar must **start at or after x** (no entry from the bar the exit happened in). |
| Daily cap | **At most 2 fills a day** per book. |
| Books | Each scored cell (§6) is its own book: one trigger, one filter, both sides. |

### 3.6 Exit

| # | Rule |
|---|---|
| Initial stop | Long: swing = lowest low of the **6** 5-min bars ending at bar *j*, minus 1 tick. Distance d = F − swing (F = fill), then **clamped to [0.5, 2.0] × ATR_j**; stop = F − d, rounded to the nearest 0.25 tick, at least 1 tick from F. (If F opens below the swing, d is negative and the clamp makes it 0.5 × ATR.) |
| Trail | At the close of each 5-min bar *k* from the fill bar onward, if still open: best = max(best, high_k) (best starts at F); stop = max(stop, best − **2.5 × ATR_k**), rounded down to a tick. The stop never loosens. During bar *k* the stop is the level set at the close of bar *k − 1* (the initial stop during the fill bar). |
| Stop fill | Walked on **1-min bars** from the fill minute: a 1-min bar that opens through the stop fills at its open; otherwise a bar whose low ≤ stop (long) fills at the stop. |
| Time exit | **Market at the open of the 15:55 1-min bar** (12:55 on early-close days). |
| No target | There is no profit target. |

---

## 4. What the build adds to the W16 engine

`strategy/w16/open_window.py` (new) with: extended-hours resampling and back-adjusted indicator series (§2, §3.1);
filter states F1 and F15; triggers A, B, C; the trailing-stop 1-min walk (a new walker beside
`walk_stop_target_time_exit`, which stays unchanged); the IBKR cost table (G5); controls (§8); grid (§8.3);
pre-flight mode; the `holdout_w16_owa.json` ledger. Reuse `strategy/w16/{sessions,costs,controls,runner}.py`
helpers where they fit. A shared core must produce the same signals as Pine v1.0 on a fixed test fixture (§14).

---

## 5. Costs (IBKR, W15-0033; per side, 1 MNQ)

All-in fee **$0.62** (commission 0.25 + exchange 0.353 + regulatory 0.02), tick $0.50. Every fill here is a market or
stop fill (entry, stop, 15:55 exit), so every side pays the ticks.

| Level | Per side | Round trip | Role |
|---|---|---|---|
| L1 (low) | $0.62 | $1.24 | reported |
| **L2 (mid)** | **$1.12** | **$2.24** | **scoring** |
| L3 (high) | $1.62 | $3.24 | criterion 6 |

1 NQ (reported): $2.26 fee, $5.00 tick → $7.26 per side at L2. L0 (no costs) is printed for reference only.

---

## 6. Scored cells

**Six scored cells**, each two-sided (long + short in one book):

| | F1 · 1H filter (main) | F15 · 15-min filter (variant) |
|---|---|---|
| A · EMA cross + big bar | **A-1H** | **A-15** |
| B · Pullback after big bar | **B-1H** | **B-15** |
| C · MACD + EMA9 gap | **C-1H** | **C-15** |

Reported, never scored: the long book and short book of each cell; the **"All" book** (A or B or C, first in that
order, long before short, 1H and 15-min); signals filled at the **signal bar's close** (the Pine view); no daily cap;
fills split **08:00–09:25 (pre-open)** vs **09:30–12:00**.

---

## 7. Before the backtest — no P&L in this section

### 7.1 Pre-flight (G2), training side only

Per year and per cell: trading days, skipped, warm-up; signals and fills (long / short); fills before vs after 09:30;
days at the 2-fill cap; dropped signals (no fill bar); big bars per day in 08:00–12:00 (expected around 1 in 10 bars
or fewer); filter share UP / DOWN / NONE for F1 and F15; initial stop distance in $ per MNQ (median, p90, max) in 2010,
2016 and 2023; voids. **No exit price is read.** The 2-fill cap and re-entry both depend on exits, so the pre-flight
counts **signals and first fills per day** and flags that the real count will differ.
**Stop rule:** a cell with fewer than **300** training trades is NOT READ (reported, not failed).

### 7.2 Look-ahead guards (G4) — each proven by a test that a one-bar shift breaks

- The filter at bar *j* reads only filter bars that **closed at or before bar j's start**. A test moves a 1H close one
  minute later and the state at that bar must change.
- The slot average used at bar *j* contains no bar from day *j*'s own slot (updated after judging).
- Back-adjustment at time τ uses only rolls at or before τ. A test adds a later roll and the earlier signals must not
  change.
- A signal at bar *j* fills at bar *j+1*'s open, never at bar *j*'s close.
- The trailing stop used during bar *k* is set at the close of bar *k − 1*. A test that uses bar *k*'s own high to
  move its stop must break.
- The exit walk starts at the fill minute.
- Re-entry and the 2-fill cap count only trades that closed before the signal bar starts.
- Holdout refusal (§9) mutation-tested, incl. `--limit` and every narrowing flag.

---

## 8. Controls and grid

### 8.1 Scored control — C-1 random later timing (1,000 seeded draws, seed = `zlib.crc32` of the draw number)

For each real trade: same day, same side, same initial stop distance in points, **entry at the open of a uniformly
random 5-min bar starting at or after the real fill time and no later than 12:00** (the W16-0011 rule: random entries
are drawn only at or after the real signal time), then the same trail and 15:55 exit. Draws are independent per
trade (overlap allowed; cap and one-at-a-time not re-applied), so the count matches the real book. Report p5 / p50 /
p95 of net at L2. A cell must beat **p95**. *Known weakness: a real fill at 12:00 has only itself to draw, so late
trades contribute nothing to the contrast. The pre-flight shows how many fills are at 11:30 or later.*

### 8.2 Reported controls

- **C-2 random long:** on each day the cell traded, the same number of **long** entries at uniformly random 5-min bar
  opens 08:00–12:00, 0.5–2 × ATR initial stop drawn as the real distribution's median in ATR units, same trail and
  exit. Shows what pure upward drift earns in this window (the W16-0008 TMB lesson).
- **C-3 random side:** the real entry times and exits with the side chosen by a seeded coin (stop distance kept).
  Does the trend filter's direction add anything?

### 8.3 Neighbour grid — 9 cells per scored cell, net at L2, training side

| Cell | Dimension 1 | Dimension 2 |
|---|---|---|
| A, B | big-bar multiple {1.25, **1.5**, 1.75} | trail × ATR {2.0, **2.5**, 3.0} |
| C | MACD-cross window k ≤ {2, **3**, 4} | trail × ATR {2.0, **2.5**, 3.0} |

Registered values in bold. The grid is a robustness check, not a search. No grid cell can replace a registered cell.

---

## 9. The holdout

- **Training: 2010-06-06 → 2023-12-29.** **Holdout: 2024-01-02 → end of pulled data (2026-10-27).** Own ledger
  **`holdout_w16_owa.json`**, refused by name from every other line's ledger (SB, DVP, BB) and vice versa.
- **Spent once, in one run, for every cell that passes §10.** No cell is re-read, and no failed cell is ever read.
- **Holdout bar** (each passing cell, L2, 1 MNQ): net > $0; net per trade ≥ one third of its training net per trade;
  beats the p95 of C-1 re-run on the holdout; net > $0 at L3.
- If more than one cell clears the holdout bar, Ben chooses which one goes to forward test (sub 7). Nothing is ranked.
- **Disclosed:** Ben's 19–24 Nov 2026 example charts sit after the end of our data, inside the holdout period. No NQ
  intraday bar from 2024 on has been read by this project's research code.

---

## 10. The bar to clear — each scored cell, training side, 1 MNQ, L2

A cell **passes** only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. **Bootstrap by calendar month** (2,000 seeded resamples): net > 0 in **≥ 99%** *(six cells: 0.05 ÷ 6 ≈ 0.0083, as
   BB-v0)*.
5. Net > **C-1 p95** (§8.1).
6. Net > $0 at **L3**.
7. Net > $0 after dropping the best **1%** of trades.
8. At least **6 of 9** neighbour cells (§8.3) net > $0 at L2.
9. At least **300** trades. Fewer → NOT READ, not failed.

Long-only or short-only books cannot pass on their own; only the two-sided cell is judged. **Profit-factor alarm**
(W11-0034): a training profit factor above 3 over 1,000+ trades is treated as a likely bug and audited before the
Result doc.

---

## 11. Multiplicity budget

**Six scored cells.** Everything else is reported. After the result, this line may register **two** further
hypotheses (for example, one side only on a cell whose sides diverge, a different window, or a daily loss stop). A
third needs a reason that does not begin with a result. Its own budget (Ben's idea, W16-0040), not charged to SB, DVP,
BB or W16-0039.

---

## 12. What every run must emit — in dollars and actual trades

For each scored cell, at L1 / L2 / L3, per 1 MNQ (1 NQ beside it): trades, wins / losses, win rate, gross, costs, net,
average win, average loss, largest loss, worst losing run, worst day, worst month, max drawdown $ (and % of $22,129);
every calendar year; both halves; long vs short; pre-open vs RTH fills; exit reasons (stop before any trail move /
trailed stop / 15:55); average holding time; C-1 p5/p50/p95; C-2 and C-3; the 9-cell grid; bootstrap share; the
best-1%-dropped net; 20 sample trades (every 1/20th: date, side, trigger, signal bar, fill time and price, initial
stop, exit time and price, reason, net $). Negatives in brackets. Plus the reported books (§6). **Nothing is ranked.**

---

## 13. Ways this could go wrong — and a prediction

- **Prior NQ record on these engines is poor:** W16-0003 (ORB, overnight hold, VWAP flip) 0/6 passed, BB-v0 0/6
  (TMB's profit was beaten by a random long in 95% of draws), DVP-v0 was net ($24) on 7,794 trades; the DVP line
  later passed 5/6 out of sample (W16-0012) and is in forward test (W16-0014). Simple
  EMA/MACD triggers on 5-min NQ have no published edge after costs.
- **Trend-filter lag.** A 1H EMA9/21 flips hours after a reversal (the 20 Nov drop Ben pointed at). F15 flips faster
  but chops more. That is why both are scored.
- **Pre-open thinness, especially 2010–2013.** The 08:00–09:30 slots trade much less. The slot average copes with
  quiet normals, but 1-min gaps may skip sessions. The pre-flight shows this per year.
- **Trailing on 5-min ATR with 1-min fills.** Gaps through the stop fill at the next 1-min open (adverse). The
  trail does not see moves inside a 5-min bar until its close.
- **Long drift 2010–2023.** C-1 keeps the side, so drift cannot pass criterion 5. C-2 shows the drift baseline.
- **Late fills weaken C-1** (§8.1).
- **Pine vs Python differences that remain:** TradingView's continuous MNQ1! is not back-adjusted unless the chart
  setting is on, and the Pine flat time ignores early-close days. Signals only, so neither touches the scored test.

**Prediction, written now:** all six cells fail. A fires rarely and enters after the move (a big bar plus a fresh
cross is late by construction); C fires often and chops; B is the most likely to be net positive at L1 but not to beat
C-1's p95. If anything shows a pulse it will be on the short side under F15, where moves are faster. I'd be glad to be
wrong.

---

## 14. Pine indicator v1.0 — what the re-sync changed

The Pine file is signals only and draws no P&L. Synced to this file:
- Slot average needs **20** prior observations (was 5).
- Filter: DOWN only when EMA9 < EMA21 (equality is neither; was "not UP").
- Trail "best price" starts at the entry price (was the signal bar's high/low).
- Header states the registration, the remaining differences (§13) and recommends turning on TradingView's
  back-adjustment for continuous futures.
Everything else (window, triggers, 6-bar swing stop, 0.5–2 × ATR clamp, 2.5 × ATR trail, 2 fills a day, 15:55 flat,
1H default with 15-min setting) already matched. The Pine marks entries at the signal close; the backtest fills at the
next bar's open (§3.5).

---

## 15. Registered as NOT to be done

- Promoting a reported book (long-only, short-only, All, signal-close fills, no cap) or a grid cell after a result.
- Changing 08:00–12:00, 1.5×, 20-day slot average, k ≤ 3, 12-bar B window, 6-bar swing, 0.5–2 × ATR, 2.5 × ATR,
  2 fills, or 15:55 after a result, or because of recent example charts.
- Adding a filter (day of week, news days, volatility, VWAP) after a result. That spends from §11.
- Quoting gross, L1, per-NQ, profit factor or win rate alone as the headline.
- Reading the holdout for a failed cell, twice, or with `--limit` or any narrowing flag.

---

## Next steps (board, W16-0040)

- **Sub 3 — Scalping chat (Opus · Medium):** this file. Done 2026-11-28. Pine re-synced to v1.0.
- **Sub 4 — Build & test chat (Sonnet · High):** `strategy/w16/open_window.py` per §4, IBKR cost table (G5),
  controls C-1–C-3, grid, pre-flight mode, `holdout_w16_owa.json`, tests for every §7.2 guard, a Pine-parity fixture.
  Ben commits this file with the build.
- **Sub 5 — Ben (PC):** run tests, then the pre-flight (G2); then the training backtest once the Scalping chat has
  read the pre-flight.
- **Sub 6 — Scalping chat (Opus · Medium):** Result doc against §10.
- **Sub 7 — Build & test chat:** NAS paper deploy only if a cell passes the holdout; needs Ben's decision on extending
  the NAS trader window past 09:30 NY.
- Related: W16-0014 (DVP forward), W16-0039 (Zarattini noise band), W16-0038 (busy slots).

---

## Amendment 1 (PRE-RUN, 2026-11-28, sub 4 build) — choices the code had to make, fixed before any P&L is read

No rule, threshold, cell, criterion or ledger date above is changed. No exit price or P&L from real bars had been
computed when this was written. Files: `strategy/w16/open_window.py` (rules, book, walk), `owa_controls.py`,
`owa_preflight.py`, `owa_runner.py` (pricing, criteria, report, command line), `owa_holdout.py`, and the IBKR table
in `costs.py`. The nine criteria are `strategy/w16/runner.score_cell`, unchanged.

1. **Roll adjustment (§2)** is computed in its causal form: at a roll every *later* bar is shifted by minus the gap.
   It differs from shifting the earlier bars up only by a constant, which cancels in every registered comparison, and
   a bar's value depends only on rolls at or before it. The stop's swing level is converted to the fill contract's
   prices.
2. **Skipped sessions (§2):** the two edges count. No bar until after 07:15, or none after 15 minutes before the flat
   time, is a gap.
3. **Warm-up (§2):** the bar counts are read at 08:00, and the slot average must be valid (≥ 20 earlier days) for
   every 08:00–11:55 bar of that day. Warm-up is decided before the skip rule.
4. **Re-entry (§3.5):** the signal bar must start after the start of the exit's 1-minute bar, so the 5-minute bar that
   holds the exit is excluded even when the exit is in its first minute.
5. **Time exit (§3.6):** the first 1-minute bar at or after the flat time. If the date has none, the last bar's close
   (counted and printed).
6. **Reported books (§6):** long-only and short-only are separate one-sided simulations; the long/short split of the
   two-sided book is printed too. Signal-close fills are walked from the first minute at or after the bar's close.
7. **Criterion 3 (§10)** as the W16 engine computes it: the largest single year by size ÷ total net ≤ 50%, so a losing
   year bigger than half the net also fails it. Drawdown counts the start ($0) as a peak.
8. **C-1 (§8.1):** candidates are the same day's 5-minute bars starting by 12:00 whose first minute is at or after the
   real fill. Each is walked once and a draw picks one per trade (the same result as walking every draw). A void
   control trade counts $0. **C-2 (§8.2):** stop = median(real stop ÷ ATR at the signal) × ATR of the last completed
   bar before the random entry, to the tick, at least one tick; entries 08:00–12:00, drawn with replacement.
9. **Training cut (§9):** pre-flight and training drop every bar dated 2024-01-01 New York or later before anything is
   computed.
10. **Holdout (§9):** only through `owa_runner --spend-holdout "<cells>"`. The list must be exactly the cells that
    pass in that same run (full controls and grid); no narrowing flag is accepted; the ledger is written before any
    locked bar is used. `owa_holdout` has no `--spend` of its own.
11. **Pre-flight (§7.1):** days at the 2-fill cap depend on exits, so it prints days with 2 or more fillable signals
    (an upper bound) and lower and upper trade counts. B's arming is reset by the day's first fill only. "Voids" is
    shown as days with a contract change inside 08:00–flat. Stop distances are those of the first fills.
12. **Pine parity (§4, §14):** Pine cannot run in the test suite, so the core is compared with a line-by-line Python
    transcription of v1.0 on made-up bars (big bar, filter, A, C, and B without fills), and the indicator's input
    numbers are checked against the constants.
