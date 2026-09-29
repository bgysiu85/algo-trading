# REGISTERED — W16 BB-v0: bar-only entry batch on ES/NQ (ATR-band dip buy, shooting-star short, Trader Math breakout, CRT 3-candle, NR4 squeeze)

**Committed before any code for these five rules exists, and before any return of any of them has been seen on our
data.** `PROGRAM_INDEX` §2.4: a hypothesis is registered before it is run. Amendments are marked **PRE-RUN** or
**POST-RUN**. A rule or threshold changed after seeing a result is a new hypothesis and spends from §11.

**Board:** W16-0008 (subitem 1 = Ben's decisions; 2 = this file; 3 = build; 4 = Ben runs; 5 = Result doc). Decision:
W11-0035 option C.
**Sources:** IQCapital YouTube, shortlist #2–#6 in `claude/w11_0034_iqcapital_review_RESULT_20260928.md`.
**Transcripts read by this chat on 2026-09-28:** `snaP5117MxI` (Trader MNQ, 23,533 characters, 100%),
`O4ASr0fh7O8` (Trader Math, 20,454 characters, 100%) and `rfWVz2yLozk` (Trader X / NR4, 14 min, 100%).
`z1Z72VJGt08` (Mike Babayan, CRT, 88,785 characters) was read in full up to 45,000 characters (the whole rule
explanation). The rest was keyword-searched for rule changes and cross-checked against the helper extract in
`claude/raw/w11_0034_iqcapital_extracts_20260928.txt`.
**Engine:** the W16-0003 engine (`strategy/w16/`): same data, sessions, costs and exit-walk code as
`REGISTERED_w16_session_baselines.md` (SB-v0). Anything this file does not restate is inherited from SB-v0 §2
(markets, series, sessions, early closes, contract sizing) and SB-v0 Amendment A (NinjaTrader Free fees).
**Chat:** Scalping chat.

**Ben's decisions, 2026-09-28 (his multiple-choice picks):**
- Scored set: **"Source market only (Recommended)"**. Six scored cells: ATR-band dip buy, shooting-star short,
  Trader Math breakout and CRT on **NQ**; NR4 squeeze on **ES and NQ**. The ES versions of the first four are
  reported only.
- Hours: **"Day session; NR4 overnight (Recommended)"**. The 5-min, 15-min and CRT rules trade 09:30–16:00 ET and are
  flat by 15:55. NR4 runs on the full Globex session and holds overnight.
- NR4 exit: **"3×ATR chandelier (Recommended)"**. The stop starts 3 × ATR(14, 1-hour) from entry, then trails
  3 × ATR behind the best price since entry. No target.
- Trader Math sides: **"Long only (Recommended)"**. The mirrored short is reported, not scored.

---

## In plain terms

Five simple chart rules from a prop firm's YouTube channel, each run on its own:

1. **ATR dip buy (Nasdaq, 5-min bars).** Buy with a limit order when price drops 3.1 "normal bar sizes" (ATR) below
   the last close. Target 2 ATR above, stop 1.5 ATR below.
2. **Shooting-star short (Nasdaq, 5-min).** After a candle with a long upper wick and almost no lower wick, sell at
   the next bar's open and buy back one bar later. No stop and no target.
3. **Trader Math breakout (Nasdaq, 15-min, long only).** When a "trendiness" score is above 50 and the last 20 bars
   show a slight back-and-forth rhythm, buy when a bar closes above the previous 5 bars' high. Target 5 ATR, with a
   4 ATR trailing stop.
4. **CRT 3-candle (Nasdaq, 15/30/60-min, 09:30–12:00).** A candle pokes below the previous candle's low but closes
   back inside it. Buy when the next candle breaks its high, aiming for the first candle's high, with the stop set so
   the target is 1.5 times the risk (mirror for shorts). First trade of the morning only; no Mondays.
5. **NR4 squeeze (S&P and Nasdaq, 1-hour, day and night).** Four hourly candles, each no wider than the one before.
   Buy a break above the last one's high or sell a break below its low, whichever comes first. Exit on a trailing
   stop 3 ATR behind the best price. Hold overnight if needed; one trade a day per market.

Each is charged NinjaTrader's real fees plus a tick of slippage, 1 micro contract a trade, on mid-2010 to 2023 data.
Each is compared with the same trades made at random times or in a random direction. A rule that passes every test
gets one look at the locked 2024-onward data.

---

## 0. PRE-RUN GATES — no P&L is computed until every row is true

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Data**: SB-v0's G1 stands (passed 2026-09-27: ES and NQ `ohlcv-1m`, full Globex hours, 100.0000% daily agreement). No new data. | Same bars. |
| **G2** | **Pre-flight, no P&L** (§6.1): counts per rule, market and year; trades per day; stop/target distances in $ per micro; Trader Math score distributions; CRT setups by timeframe; NR4 setups and pending-order lifetimes. The runner refuses P&L in this mode. | Shows whether there is enough to read, and what a stop costs, before any profit is seen. Also carries the one allowed calibration (§3.3, HP). |
| **G3** | **Holdout cut and enforced in code** (§8): own ledger `holdout_w16_bb.json`, mutation-tested. | `PROGRAM_INDEX` §2.5. |
| **G4** | **Look-ahead guards tested** (§6.2), each by a test that a one-bar shift breaks. | Three bar sizes are mixed with 1-minute exit walks. That is where look-ahead creeps in. |
| **G5** | **Costs**: SB-v0 Amendment A (NinjaTrader Free, MNQ/MES $0.94 per side all-in, NQ/ES $2.87) applies unchanged. | Already priced before any W16 P&L. |

---

## 1. The hypothesis, in one sentence

**At least one of these five bar-only rules, in its six registered cells, makes money on 1 micro contract after
NinjaTrader Free fees plus one tick of slippage on every market or stop fill, on 2010-06-06 → 2023-12-29 training data,
and beats the same trades placed at random times (or, for the two-sided rules, in a random direction).**

Each cell is judged on its own. The five rules are never netted into one book.

---

## 2. Common rules (all five)

| Element | Registered rule |
|---|---|
| Markets / series | ES and NQ, `ES.v.0` / `NQ.v.0`, GLBX.MDP3 `ohlcv-1m`, as SB-v0 §2. Every bar keeps its `instrument_id`. |
| Contract | **1 MNQ ($2/pt) or 1 MES ($5/pt)** headline; per 1 NQ / 1 ES beside it. Before May 2019, micro = full ÷ 10 (SB-v0 §2). Tick 0.25 pt. |
| Account | $22,129, fixed 1 micro a trade, no compounding. ATR-scaled sizing (as the traders use for prop-firm loss caps) is **not** tested: every trade is 1 micro. |
| Day session (rules A–D) | 09:30–16:00 ET on XNYS trading days; early closes end at 13:00 and every "15:55" below becomes 12:55 (SB-v0 §2). |
| Resampling (rules A–D) | 1-minute bars resampled **inside each day session** into 5-, 15-, 30- or 60-min bars **anchored at 09:30 ET**. OHLCV = first / max / min / last / sum. A bar is knowable at its close. A period with no 1-minute bars has no bar. |
| Indicator history (rules A, C) | ATR and the Trader Math scores run on the **continuous series of day-session bars across days**, as a chart set to regular hours would. True range = max(H, prior close) − min(L, prior close). **If a bar's `instrument_id` differs from the prior bar's (a roll), its true range is H − L** and its 1-bar return is missing. ATR is Wilder's (RMA). |
| Skipped sessions (rules A–D) | A session missing its 09:30 1-minute bar, or with a gap of more than 5 minutes between 1-minute bars inside 09:30–16:00, is skipped and counted. |
| Exits | Walked on **1-minute bars** from the fill minute onward, with SB-v0 §3.1's conventions (`strategy.w16.signals`). A bar that opens through the stop fills at its open. A target (limit) fills only when a bar trades **through** it by ≥ 1 tick. **If one bar reaches both, the stop wins.** The fill minute's own range can hit the stop but never the target. |
| Limit entries (rule A) | A resting buy limit fills only when a 1-minute bar trades **through** it by ≥ 1 tick (the same convention as targets). It fills at the limit price, or at the bar's open if the bar opens below it. |
| Stop entries (rules D, E) | A buy stop at level X fills at the first 1-minute bar whose high ≥ X, at max(open, X). Sell stops mirror this. |
| Flat | Rules A–D: **flat at 15:55** (market at the open of the 15:55 1-minute bar). Rule E has no daily flat (§3.5). |
| Costs | SB-v0 §4 + Amendment A. **L2 (scoring) = L1 + 1 tick on every market or stop fill** (market entries, stop entries, stop exits, time exits, roll exits). Limit fills (rule A's entry, all targets) add 0 ticks. L3 = L1 + 2 ticks. L0 = none (replication only). |
| One at a time | One position per cell at a time. After an exit, the next signal must come from a bar that **starts at or after the exit time**. |

---

## 3. The rules

### 3.1 Rule A — ABD: ATR-band dip buy (Trader MNQ, `snaP5117MxI`). Scored: **NQ**. Long only.

| # | Rule |
|---|---|
| Bars | 5-min day-session bars. ATR = ATR(14), Wilder. |
| Band | For 5-min bar *j*: **band_j = close_(j−1) − 3.1 × ATR_(j−1)**, rounded **down** to the tick. *(Source: "you always calculate the distance of the ATR bands based on the previous candle's closing price"; the ATR multiple is 3.1. ATR is read at bar j−1's close, because the live value moves inside the bar and the source says to use "the previous bar's ATR measurement for everything".)* |
| Entry | A resting buy limit at band_j during bar *j*'s five minutes. It fills per §2 (through by ≥ 1 tick). **The 09:30 bar is never traded** (source: "He never trades the opening candle"). Eligible bars: 09:35 … 15:50. |
| Exits | **Target = fill + 2 × ATR_(j−1). Stop = fill − 1.5 × ATR_(j−1).** Both are rounded to the nearest tick (minimum 1 tick) and fixed at entry. Then flat at 15:55. |
| Limits | None stated by the source. One position at a time (§2). |

Reported, never scored: **ES**; **touch fills** (limit fills on a touch, not a trade-through); **mirrored upper-band
short** (the host says it "completely fell apart", and it is reported to check that).

### 3.2 Rule B — SSS: shooting-star short, one-bar hold (Trader MNQ, host's objective version). Scored: **NQ**. Short only.

| # | Rule |
|---|---|
| Bars | 5-min day-session bars. |
| Pattern | On bar *j*: upper wick U = H − max(O, C), lower wick D = min(O, C) − L, body B = \|C − O\|. **Pattern if U ≥ 2 × B, D ≤ 0.1 × U, and U ≥ 1 tick.** The candle may be green or red. *(These are the host's objective thresholds, which he says he invented. The trader eyeballs the pattern.)* |
| Entry | While flat: **sell at the open of bar *j*+1** (market). Pattern bars 09:30 … 15:45. |
| Exit | **Buy back at the open of bar *j*+2** (market), whatever the price. No stop, no target. |
| Overlap | A pattern on the bar being held (*j*+1) is ignored. The position exits at *j*+2's open, and a pattern on *j*+2 may enter at *j*+3's open. |

Reported, never scored: **ES**; the host's **prior-day-red filter** (short only when the prior XNYS session's 16:00
close is below the one before it). The host added it after seeing his own result (60 trades), so it is reported here.

### 3.3 Rule C — TMB: Trader Math breakout (`O4ASr0fh7O8`). Scored: **NQ**. Long only.

| # | Rule |
|---|---|
| Bars | 15-min day-session bars (26 a full day). ATR = **ATR(20)**, Wilder (source: "a 20 period ATR"). |
| HP | **Hurst proxy** (source: "a Hurst proxy … that compares the price range to volatility", scaled 0–100, formula undisclosed). **Our version:** over the last N = 20 bars k−19 … k, R_k = max(H) − min(L). **HP_k = 100 × ln(R_k ÷ ATR20_k) ÷ ln(20).** If price moves like a random walk, the 20-bar range grows about like √20 bar-ranges, giving roughly 50. A steady trend's range grows like 20 bar-ranges, giving roughly 100. Chop gives less than 50. **This is our construction and not his formula.** The Result doc says so first. |
| AC | **Autocorrelation at lag 5 over 20 bars** (source: "comparing price direction now with price direction five bars ago … across the last 20 bars"): the Pearson correlation of r_t and r_(t−5) for t = k−19 … k, with r_t = ln(C_t ÷ C_(t−1)) on the 15-min series. It needs 20 valid pairs, otherwise the bar has no signal (for example, near a roll). |
| Signal | At bar *k*'s close: **HP_k > 50 AND AC_k ≤ −0.10 AND C_k > max(H_(k−5) … H_(k−1))** (the prior 5 bars, current bar excluded). Signal bars 09:30 … 15:30. |
| Entry | **Market at the open of bar *k*+1** (source: "right at the close or the open of the very next bar"). |
| Exits | **Target = fill + 5 × ATR20_k** (fixed). **Stop = fill − 4 × ATR20_k at entry, trailing: after each completed 1-minute bar, stop = max(stop, highest high since entry − 4 × ATR20_k)**, where ATR20_k stays fixed at entry (source: "both calculated right when the entry is taken … the stop-loss will move up with price by the highest high reached"). A minute's stop uses only highs from earlier minutes. Then flat at 15:55. |
| HP calibration (PRE-RUN only) | The G2 pre-flight reports the share of training bars with HP > 50 (no P&L). **If that share is below 10% or above 90%, the threshold is a PRE-RUN amendment: HP is re-centred so that the training median maps to 50 (HP' = HP − median + 50),** written in before any P&L exists. Otherwise nothing changes. This is the only allowed calibration, because our proxy's centre is approximate. |

Reported, never scored: **ES**; **mirrored short** (HP > 50, AC ≤ −0.10, close below the prior 5 bars' low; target
5 ATR below, 4 ATR trailing stop above); **full Globex hours** (15-min bars on the Globex session, holding across the
16:00–09:30 gap, "hybrid swing").

### 3.4 Rule D — CRT: Candle Range Theory 3-candle (Mike Babayan, `z1Z72VJGt08`). Scored: **NQ**. Both sides.

| # | Rule |
|---|---|
| Bars | Three separate series of day-session bars anchored at 09:30: **15-min** (09:30, 09:45, …), **30-min** (09:30, 10:00, …), **60-min** (09:30, 10:30, 11:30). *(Source: "one of three time frames, the 1 hour, the 30 minute, or the 15 minute … I just care which one's the first one".)* |
| Setup | On one series, consecutive bars C1 = bar *i*, C2 = bar *i*+1, with C1 starting at or after 09:30. **Bullish:** L2 < L1 (C2 sweeps C1's low) **and** L1 ≤ close2 ≤ H1 (C2 closes back inside C1's range). **Bearish:** H2 > H1 and L1 ≤ close2 ≤ H1. A C2 that sweeps **both** sides is not a setup (counted). *(C1 "rolls forward" in the source: any bar can be C1, so every consecutive pair is checked.)* |
| Entry | **C3 = bar *i*+2.** Bullish: a buy stop at **H2 + 1 tick**, live only during C3's time window. Bearish: sell stop at L2 − 1 tick. **If C3 does not trigger, the setup is dead**, and a later bar breaking the level does not count (source: "the third candle will not do it, but the fourth one will come in … now we're done"). |
| Window | **Fills only before 12:00 ET** (source: "9:30 to about like 12:00 p.m. … If I don't see anything until 12:00, I'm good to go"). **No trades on Mondays** (source: "Mondays are the days that I usually skip"). If Monday is a holiday, Tuesday is traded. |
| One a day | **The first filled entry of the day across all three series is the trade, and the day ends.** If two series fill in the same 1-minute bar, the shorter timeframe's setup is taken. |
| Target | **C1's opposite extreme**: long target = H1, short target = L1 (source: "I'm going to take profits exactly at that high"). |
| Stop | **Back-solved to 1.5R**: long stop = fill − (H1 − fill) ÷ 1.5; short stop = fill + (fill − L1) ÷ 1.5. Rounded to the nearest tick, minimum 1 tick (source: "I will drag my stop loss … until I see that it is a 1.5 R for every single trade"). If the fill is at or beyond the target (reward ≤ 0), the trade is **voided and counted**. |
| Hold | Target or stop only. Then flat at 15:55, which the source does not state; our day session requires it. |
| Not tested | His **higher-timeframe bias filter** ("extreme" swing levels) and **chop filter** are discretionary. He says the plain version (first setup of the day, direct break) runs about **60–65%** win and the filters lift it to 70–80%. We test the plain version. |

Reported, never scored: **ES**; **re-break entry** (after C3 first trades through the level, wait for a 1-minute close
back on the other side of it, then enter on the next trade-through, still inside C3's window); **each timeframe
alone** (15, 30 and 60-min, first setup of the day on that series); **Mondays included**.

### 3.5 Rule E — NRS: NR4 compression squeeze (Trader X, `rfWVz2yLozk`). Scored: **ES and NQ**. Both sides. Full Globex.

| # | Rule |
|---|---|
| Bars | **1-hour Globex bars anchored at 18:00 ET**: 18:00, 19:00, …, 16:00 (the last closes at the 17:00 pause). 23 a day, with no bar for the pause. The Sunday 18:00 open starts Monday's CME trading day. A period with no 1-minute bars has no bar. ATR = ATR(14), Wilder, on this series. Roll bars as §2. |
| Compression | A completed bar *k* is a **squeeze bar** if **range(k−3) ≥ range(k−2) ≥ range(k−1) ≥ range(k)**, range = H − L (source: "four consecutive candles must each have a range equal to or smaller than the candle before them"). The four bars must share one `instrument_id`. |
| Orders | After a squeeze bar *k* closes, and while flat and allowed to trade: **buy stop at H_k + 1 tick and sell stop at L_k − 1 tick**, live during bar *k*+1. **Whichever fills first is the trade; the other is cancelled.** If bar *k*+1 triggers neither, it lies inside bar *k*, so it is itself a squeeze bar (its range ≤ range(k)). The orders move to its high and low. A 1-minute bar that reaches both levels is **voided and counted**. |
| One a day | **At most one entry per market per CME trading day** (18:00 → 17:00 ET) (source: "never more than one on a single asset in the same session"). No re-entry after a stop-out on that setup. |
| Stop | **Chandelier, 3 × ATR(14):** initial stop = fill ∓ 3 × ATR_k (ATR at the squeeze bar's close). At each later completed 1-hour bar *m*: **long stop = max(stop, highest high since entry − 3 × ATR_m)**, and the mirror for shorts. It never loosens. The stop is walked on 1-minute bars; within an hour it does not move. |
| Target | None (source: no fixed reward-to-risk; winners held for days). His scale-outs are discretionary and not tested. |
| Hold | Overnight and over weekends, until the stop is hit. **Roll exit:** if the next 1-minute bar carries a different `instrument_id`, the trade exits at the close of the last bar on the old contract (market, +1 tick at L2) and is counted. **Training-end exit:** a trade still open at the last training bar exits at its close (counted). |
| News | Trader X "avoided certain major news events, not all of them". This is not codeable and not tested. |

Reported, never scored: the **5-candle reading** (four comparisons: range(k−4) ≥ … ≥ range(k)); **day session only**
(1-hour day-session bars, flat at 15:55); **squeeze-bar stop** (initial stop at the other side of bar *k*, then the
3 ATR trail once it is tighter); long and short books separately.

---

## 4. What every run must emit — in dollars and actual trades

For each scored cell and each reported variant, as SB-v0 §5:

1. Per 1 micro (and per 1 full contract): trades, wins/losses, **win rate**, gross, costs, net, average win, average
   loss, largest loss, worst losing run, worst day, worst month, max drawdown in $, at L1, L2 and L3. L2 is the
   headline.
2. Every calendar year of the training side; both halves split at the median trade date.
3. Exit reasons (target / stop / trailing stop / 15:55 / time / roll / training-end) and counts: sessions skipped,
   voids, same-bar stop-and-target ties, CRT both-side sweeps, NRS double-level minutes.
4. **Break-even win rate** at L2 from the realised average win and loss, beside the actual win rate.
5. Trades per day (median, p90, max); long/short split; holding time (median, p90, max); stop distance in $ per micro
   (median, p90, max).
6. Controls (§7.1–7.2), run fresh on the same bars, costs and period.
7. Neighbour grid (§7.3): net at L2 per cell and the share net-positive.
8. Account view at $22,129: equity curve, max drawdown in $ and as % of the account. For NRS, the NinjaTrader
   overnight maintenance margin (MES $2,619.42, MNQ $4,329.42; SB-v0 Amendment A) against the account.
9. 20 sample trades per cell (every 1/20th of the list): date, side, signal bar, fill time and price, stop, target,
   exit time and price, exit reason, net $ per micro.
10. The source-claims block (§7.4) beside the verdict.

**Nothing is ranked. No "best rule" table.** Holdout numbers appear nowhere until §8's spend.

---

## 5. Why these could pass, and why they probably won't

For them: every rule is simple, fixed in advance by someone else, and uses a different idea (buy a volatility dip,
short a failed push, buy a pullback breakout in a persistent trend, fade a failed sweep, break out of a squeeze).
The sources' own TradingView tests (A, B, C) report profit factors of about 1.4–1.5.

Against them: the TradingView tests cover only a few months of 5- and 15-min history (about 2025–26, inside our
holdout), state no costs, and use 4 contracts. The shooting-star's whole average move is one 5-min bar. A round trip
at L2 costs $2.88 per MNQ, about 1.4 NQ points, and a 5-min NQ bar in 2012 moved only a few points. CRT's 1.5R stop is
back-solved from a range that can be a handful of ticks, so costs weigh heavily on tight setups. The Hurst proxy is
ours. NR4 without its trader's discretionary scale-outs and news filter is a plain breakout, and SB-v0's plain
opening-range breakout is the closest prior evidence.

---

## 6. Before the backtest — no P&L in this section

### 6.1 Pre-flight (G2) — training side only

Per cell and year: sessions, sessions skipped, signals, entries (long/short), voids; trades per day (median, p90, max).
Plus:
- **ABD:** ATR(14) of 5-min bars and the stop/target distance in $ per MNQ (median, p90, max) in 2010, 2016, 2023; band
  touches vs trade-through fills.
- **SSS:** patterns per day; the median 5-min bar range in $ per MNQ by year beside the L2 round-trip cost.
- **TMB:** the distributions of HP and AC (p5/p25/p50/p75/p95); **the share of bars with HP > 50 (the §3.3
  calibration check)**; the share with AC ≤ −0.10; signals per year.
- **CRT:** setups per day by timeframe; which timeframe supplies the day's trade; share of days with no trade; reward
  (target distance) in $ per MNQ (median, p10, p90), and the share of trades whose stop is ≤ 4 ticks.
- **NRS:** squeeze bars per day; fills per year; share of fills in the day session vs overnight; initial stop in $ per
  micro.
- **No exit price is read and no P&L is computed.** Where a rule needs trade outcomes to decide the next entry (one at
  a time), the pre-flight counts signals and first entries only and flags that real counts will be lower.
- **Stop rule:** a scored cell with fewer than **300 training trades** is NOT READ (reported, not failed).

### 6.2 Look-ahead guards (G4) — each proven by a test that a one-bar shift breaks

- ABD's band for bar *j* uses only close_(j−1) and ATR_(j−1). A test that moves the band to ATR_j must fail.
- SSS enters at *j*+1's open and exits at *j*+2's open, never *j*'s close.
- TMB's HP, AC and 5-bar high at *k* use bars ≤ *k*; the 5-bar high excludes *k*; fill at *k*+1's open. The trailing
  stop in minute *m* uses highs from minutes before *m* only.
- CRT's C2 condition is read at C2's close. The entry stop is live only inside C3's window, and the target and stop
  come from C1/C2 values known at C2's close.
- NRS's squeeze test at *k* uses ranges of bars ≤ *k*. Orders are live only after *k* closes, and the chandelier at
  hour *m* uses bars ≤ *m*.
- Resampled bars: a 5/15/30/60-min bar is not usable before its last minute has closed. Tested for each size.
- Exit walks start at the fill minute. The fill minute's range can hit the stop (tested) but not the target.
- The holdout refusal (§8) is mutation-tested.

---

## 7. Controls, grid and source claims

### 7.1 Scored controls — one per cell, 1,000 seeded draws (seed = `zlib.crc32` of the draw number)

Each draw keeps the real trade count exactly: one control trade per real trade, same session, independent draws,
overlap allowed, daily limits not re-applied. Report p5 / p50 / p95 of net at L2. **The cell must beat p95.**

| Cell | Control | Definition |
|---|---|---|
| ABD-NQ | **C-A1 random timing** | Long at the open of a uniformly random 1-minute bar in 09:35 … 15:54 of that session. Target 2 × ATR and stop 1.5 × ATR from the 5-min ATR(14) of the last completed 5-min bar before the fill. Same walk, flat 15:55. Market entry at L2 (+1 tick). This favours the rule: its real entries are limit fills with no slippage. |
| SSS-NQ | **C-S1 random timing** | Short at the open of a uniformly random 5-min bar 09:35 … 15:50, cover at the next 5-min bar's open. |
| TMB-NQ | **C-T1 random timing** | Long at the open of a uniformly random 15-min bar 09:45 … 15:45. Same 5 × ATR20 target and 4 × ATR20 trailing stop from the ATR20 of the prior 15-min bar. Flat 15:55. |
| CRT-NQ | **C-C1 random side** | The **real entry minute, fill price, target distance and stop distance**, with the side chosen by a seeded coin. |
| NRS-ES, NRS-NQ | **C-N1 random side** | The **real entry minute and fill**, a seeded coin for the side, the same 3 × ATR chandelier from that fill, the same roll and training-end exits. |

**Why random side for the two-sided rules** (W16-0011): a random entry time with the real trade's side "borrows" a
direction the market had not shown yet whenever the random time falls before the signal. That made DVP-v0's C-D1
uninformative. The long-only and short-only rules have a fixed side, so random timing leaks nothing. For CRT and NRS,
the claim is that the pattern tells you *which way*, and a coin at the same moment tests exactly that.

### 7.2 Reported controls

- **C-C2 / C-N2 random timing at or after the signal:** same side, entry at a uniformly random minute from the real
  fill to the end of the window (CRT: 12:00; NRS: the end of that CME trading day). Same exits.
- **C-T2 random direction for TMB:** the real entry times and a seeded coin for the side (the short uses the mirrored
  exits).

### 7.3 Neighbour grid — 9 cells per scored cell, net at L2, training side

| Cell | Dimension 1 | Dimension 2 |
|---|---|---|
| ABD | band multiple {2.6, **3.1**, 3.6} × ATR | target and stop scaled together × {0.75, **1.00**, 1.25} |
| SSS | upper wick ≥ {1.5, **2**, 3} × body | hold {**1**, 2, 3} bars |
| TMB | HP threshold {45, **50**, 55} | AC threshold {−0.05, **−0.10**, −0.15} |
| CRT | reward ÷ risk {1.2, **1.5**, 1.8} | entry window ends {11:00, **12:00**, 13:00} |
| NRS | chandelier {2, **3**, 4} × ATR | squeeze length {3, **4**, 5} bars |

Registered values in bold. The grid is a robustness check, not a search: no cell can replace the registered rule.

### 7.4 Source claims — reported beside the verdict

| Rule | Source claim | Their sample | What we show |
|---|---|---|---|
| ABD | PF 1.527, "slightly more than 50%" win, max DD $2,614 at 4 MNQ | TradingView 5-min MNQ, a few months to 2026, costs unstated | Training PF and win rate at L0 and L2 |
| SSS | PF 1.413, 52% win, max DD $1,142 at 4 MNQ | same | same |
| TMB | 486 trades, 44% win, PF 1.381, max DD $4,172 | TradingView 15-min MNQ, period unstated | same |
| CRT | 60–65% win at 1.5R, first setup, direct break | self-reported, since 2023 | same |
| NRS | account-level only (25 days, PF 6.84, 61.9% win); no rule-level test | firm data | same (no claim to compare) |

These are **not replication checks**. Their samples lie in or near our holdout, which we cannot read. A mismatch on
2010–2023 says the rule behaves differently over a longer history, not that our harness is wrong. To guard the
harness, the build reproduces at least one worked example per rule from the videos where the numbers are given (ABD:
ATR 17.85 → target 35.75 pts, stop 26.75 pts; TMB: HP 59.40 and AC −0.2 on an entry bar, as structure only).

---

## 8. The holdout

- **Training: 2010-06-06 → 2023-12-29.** **Holdout: 2024-01-02 → the end of the pulled data.** Same dates as SB-v0
  and DVP, but **its own ledger, `holdout_w16_bb.json`**. It is refused by name from every other ledger
  (`holdout_w16_sb.json`, `holdout_w16_dvp.json`, and the rest), and it refuses `--limit` and every narrowing flag.
  Mutation-tested (G3).
- **Spent once, by one cell.** If exactly one scored cell passes §9, it spends the holdout. If more than one passes,
  **Ben chooses which** (a decision item on the board). If he leaves it to Claude, the cell with the highest training
  net per trade at L2 spends it. If none passes, the holdout stays unspent.
- **Holdout bar** (the spending cell, L2, 1 micro): net > $0; net per trade ≥ one third of its training net per trade;
  beats the p95 of its own §7.1 control re-run on the holdout; net > $0 at L3.
- **Disclosed:** the sources' TradingView tests (A, B, C) and the traders' live results cover 2025–2026, inside our
  holdout. They are public claims, not readings of our data.

---

## 9. The bar to clear — each scored cell, training side, 1 micro, L2

Six scored cells: ABD-NQ, SSS-NQ, TMB-NQ, CRT-NQ, NRS-ES, NRS-NQ. A cell **passes** only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. **Bootstrap by calendar month** (2,000 seeded resamples with replacement): net > 0 in **≥ 99%**. *(Raised from 95%
   because six cells are scored: 0.05 ÷ 6 ≈ 0.0083, as SB-v0.)*
5. Net > its **§7.1 control's p95**.
6. Net > $0 at **L3**.
7. Net > $0 after dropping the best **1%** of trades.
8. At least **6 of the 9** neighbour cells (§7.3) net > $0 at L2.
9. At least **300** trades. Fewer → NOT READ, not failed.

Source claims (§7.4) and reported variants sit beside the verdict, not in it. Holding also to the profit-factor alarm
from W11-0034: a training profit factor above 3 over 1,000+ trades is treated as a likely bug and audited before the
Result doc is written.

---

## 10. Ways this could go wrong

- **Our Hurst proxy is not his.** TMB tests "our closest version". A fail does not prove his indicator fails. §3.3's
  calibration only stops the filter from being all-on or all-off.
- **NR4's exit is a stand-in.** Trader X's stop formula and scale-outs are secret. We test a standard chandelier and a
  grid around it.
- **Costs on small moves.** SSS and tight CRT setups risk only a few ticks, so a tick of slippage is a large share of
  the move. The pre-flight shows the stop-size distribution before any P&L.
- **1-minute resolution.** ABD's stop is 1.5 ATR of a 5-min bar away, and the fill minute is often a volatile one. The
  same-bar tie count will show how often the stop-wins rule decides a trade.
- **Limit fills.** ABD requires a trade-through for its entry, which is conservative and misses touch-only fills. Touch
  fills are reported.
- **Micro pricing before May 2019** = full ÷ 10 (SB-v0).
- **Long drift.** 2010–2023 is a strong bull market. ABD and TMB are long only, and their random-timing controls keep
  the same long exposure, so drift alone cannot pass criterion 5. SSS is short only and fights the drift. Its control
  fights it equally.
- **Overnight NRS** spans the 17:00–18:00 pause, weekends and rolls. Gaps through the stop fill at the next open
  (SB-v0). Rolls exit the trade.
- **Prior evidence:** SB-v0's B1 (plain ORB) and DVP-v0 (VWAP pullback, net ($24) on 7,794 trades) show how thin
  intraday edges on these markets are once costs are in.

---

## 11. Multiplicity budget

This registration scores **six cells**. Every other number it prints is reported only. After it reports, this line may
register **two** further hypotheses on these rules (for example, a daily-stop overlay from W16-0007 on a cell that
passes, or the CRT re-break entry). A third needs a reason that does not begin with a result. It is not charged to
SB-v0's or DVP's §11 budgets: it comes from a different decision (W11-0035 C) and has its own ledger.

---

## 12. Registered as NOT to be done

- Promoting a reported variant (ES, touch fills, prior-day-red filter, TMB short, full-Globex TMB, CRT re-break,
  single timeframes, Mondays, NR4 5-candle, day-only NR4, squeeze-bar stop) or a grid cell to scored after seeing a
  result.
- Re-fitting 3.1, 2 / 1.5, the wick ratios, 50 / −0.10, 5 / 4 ATR, 1.5R, 12:00, or 3 × ATR to our data. The HP
  re-centring in §3.3 happens only from the no-P&L pre-flight, only if the share is outside 10–90%.
- Adding a filter (time of day, day of week, volatility, trend, news) after a result.
- Sizing by ATR or risk after a result. Every trade is 1 micro.
- Netting the five rules into one book or reporting a "portfolio" of them.
- Quoting gross, L1, per-full-contract, profit factor or win rate alone as the headline.
- Reading the holdout for more than one cell, or with `--limit` or any narrowing flag.

---

## 13. A prediction, written down now

**None of the six cells passes.** In more detail:
- **SSS loses clearly after costs.** Gross is near zero, and 1.4 NQ points of costs per trade on a one-bar hold swamp
  whatever is there.
- **ABD** shows a high win rate (≈ 45–55%) and small positive gross, then fails the random-timing control, because
  any long entry with a 2 : 1.5 exit in a bull market wins about as often.
- **TMB** makes few trades per year. It is near zero net, and a single strong year dominates it (criterion 3).
- **CRT** wins close to 40%, the break-even rate at 1.5R, before costs, and loses after them. The coin-flip control is
  about as good.
- **NRS** is the likeliest to show positive net on NQ, with long trend-following holds in a bull market, but it will
  not beat its random-side control at p95 on both markets, and the 99% month bootstrap will stop it.

I'd be glad to be wrong.

---

## Next steps (board, W16-0008)

- **Subitem 1 — Ben (done 2026-09-28):** the four design decisions above.
- **Subitem 2 — Scalping chat (Opus · High):** this file. Ben commits it with the build (commands on subitem 4).
- **Subitem 3 — build (Sonnet · High), Scalping chat with a helper or Build & test chat:** `strategy/w16/bar_batch.py`
  (five signal/exit modules on the W16-0003 engine; 1-hour Globex resampler for NRS), `bb_holdout.py`
  (`holdout_w16_bb.json`), `bb_runner.py` (pre-flight, backtest, controls C-A1/C-S1/C-T1/C-C1/C-N1 + reported ones,
  grids, source-claims block, worked-example checks), and tests including every §6.2 guard. Reuse
  `strategy/w16/{sessions,signals,costs,controls,grid}.py`.
- **Subitem 4 — Ben (Haiku · Low):** commit, run tests, run the pre-flight. The Scalping chat writes any §3.3
  amendment, then Ben runs the training backtest.
- **Subitem 5 — Scalping chat (Sonnet · Medium):** Result doc against §9.
