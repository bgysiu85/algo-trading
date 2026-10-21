# REGISTERED — WICK-REV: does a long upper (lower) wick predict a reversal in the next 1–3 bars? MCL and MNQ, 30m / 1H / 4H

**Written 2026-10-21, before any code exists and before any bar has been read for wick ratio or
reversal.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run. **Must be committed to the
repo before any WICK-REV code is written** (W15-0063 subitem 2a).

Board: **W15-0063** (Research & spec chat raised it; Ben's question). Source: chat 2026-10-21.

**Ben's words, 2026-10-21:**
- *"find if there is any correlation between the highest/lowest point of the candle and the closing price
  and the reversal of the price in the next 1-3 candles … work out what is the probability of the price
  will change from upward trend to downward based on the gap between the highest point of the candle and
  the closing"*
- Scope: *"let's focus on futures for now. MCL: 4H/1H/30m, MNQ: 4H/1H/30m"*
- Reversal: *"Ok, the 1x ATR seems reasonable."*
- Added: *"after a shooting star candle (or the opposite for a red candle), what is the typical number of
  candles until a reversal. correlate it with the ratio"*
- Trend filter: *"EMA20 sounds good"*

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is
a new hypothesis.

**Amendment A — PRE-RUN, 2026-10-21, before any code or data read.** Databento has ceased, so no CL
1-minute purchase. MCL 30m now comes from IBKR history (about 2 years), which is too short for the
training window, so it is **reported only**. Primary tests go from 12 to **10**, with the Bonferroni CI at
99.5%. Changed: §2 table, §3.1, §5, §6, G1b, §9, §11, next steps. The first commit (13d9516) holds the
text before this amendment.

---

## 0. What this is

A **measurement study**, not a strategy. It asks whether a candle's close location within its range
changes the odds of a 1× ATR move against the prior trend. A trade-shaped translation (§4) puts the
answer into dollars per contract after IBKR costs so that "real but too small to trade" can be told
apart from "tradeable".

The base rate is the control. Every number is quoted against the same race run from **every** bar in
the same trend context, whatever its wick.

---

## 1. The hypothesis, in one sentence

**After an up-trend bar (prior close above EMA20) whose close sits in the bottom 40% of its range
(upper-wick ratio ≥ 0.6), price reaches close − 1×ATR before close + 1×ATR within 3 bars more often than
it does after up-trend bars in general — and the mirror holds after down-trend bars with a lower-wick
ratio ≥ 0.6 — on MCL and MNQ at 30m, 1H and 4H.**

---

## 2. Data and bars

| Market | Signal series | Dollar value | Tick | Source (owned unless stated) |
|---|---|---|---|---|
| **MNQ** | NQ.v.0 `ohlcv-1m` → 30m / 1H / 4H | $2 per index point | 0.25 pt = $0.50 | W16 archive, GLBX.MDP3, 2010-06-06 → |
| **MCL** | CL.c.0 `ohlcv-1h` → 1H / 4H | $100 per $1.00 | $0.01 = $1.00 | HTF archive, GLBX.MDP3, 2010-06-06 → |
| **MCL 30m** | IBKR 30-min bars (MCL/CL continuous) | as above | as above | **IBKR history only (≈ 2 years). Reported only, see G1b** |

- **Databento has ceased (Ben, 2026-10-21); IBKR is the only data source from now on.** The owned
  Databento files already on disk are still used. No new Databento purchase.
- NQ prices are used for MNQ (the same index; MNQ = 1/10 of NQ in dollars). CL prices are used for MCL
  the same way.
- **Session:** 18:00 New York open (`strategy.htf.bars` conventions). 4H bars start 18:00, 22:00,
  02:00, 06:00, 10:00, 14:00. The 14:00 bar ends at the 17:00 close and is shorter; it is kept and
  flagged in the counts. 30m and 1H bars are clock-aligned within the session. Bars with no trades are
  not made up.
- **Rolls:** difference back-adjusted series for EMA, ATR and the race lines. A signal bar on a roll
  session, or one whose 20-bar look-ahead crosses a roll, is dropped and counted.
- **Warm-up:** 200 bars per series.

---

## 3. Definitions (fixed now)

For bar *t*, with High H, Low L, Open O, Close C:

| Name | Formula | Plain meaning |
|---|---|---|
| Range | H − L | Bars with H = L are dropped and counted |
| **UWR** (upper-wick ratio) | (H − C) ÷ (H − L) | 0 = closed at the high, 1 = closed at the low |
| **LWR** (lower-wick ratio) | (C − L) ÷ (H − L) | 0 = closed at the low, 1 = closed at the high |
| ATR | ATR(14), Wilder, at *t* (known at the close of *t*) | typical bar height |
| Size | Range ÷ ATR(14) at *t − 1* | small < 0.75 · normal 0.75–1.25 · large > 1.25 |
| EMA | EMA(20) of close | |
| **Up context** | C[t−1] > EMA20[t−1] | trend **before** the candle; the candle itself does not decide it |
| **Down context** | C[t−1] < EMA20[t−1] | |
| Colour | C > O green, C < O red, C = O doji | reported as a split only |

**Classic shape (reported subset only):** shooting star = up context, upper wick (H − max(O, C)) ≥ 2 ×
body |C − O|, and UWR ≥ 2/3. Hammer = the mirror image.

**Buckets (fixed edges, not fitted):** UWR (LWR) in 0–0.1, 0.1–0.2, …, 0.9–1.0, plus the **primary
group UWR ≥ 0.6**.

### 3.1 The race (primary k = 1)

From the close of the signal bar: down line **D = C − k × ATR** and up line **U = C + k × ATR**. Scan bars
t+1 … t+20. On the first bar where L ≤ D or H ≥ U:

- **D first → reversal** (for an up-context signal; mirror for down context).
- **U first → continuation.**
- **Both lines inside one bar → resolved on 1-minute bars** where owned (all MNQ; MCL 4H uses the 1-hour
  bars). If no finer bars are owned (MCL 1H; MCL 30m unless IBKR 1-minute bars are pulled for it), or the first touch of both falls in the same minute, the bar is
  **ambiguous**. Ambiguous counts **against** the hypothesis (as continuation) in every headline
  number, and the ambiguous count is reported.
- A gap open beyond a line counts as touching it at that bar's open.

k = **1** is the headline. k = 0.5 and 1.5 are reported beside it, fixed now, never ranked.

### 3.2 Outcomes per signal

- **3-bar outcome:** reversal / continuation / neither, judged on bars t+1 … t+3.
- **P(rev)** = reversals ÷ all signals. **P(rev | decided)** = reversals ÷ (reversals + continuations).
  Both are reported; P(rev) is the headline.
- **Bars to reversal τ** = index (1–20) of the bar where D is touched, if D comes first. Continuation or
  no touch by bar 20 = censored.

---

## 4. Trade-shaped translation (dollars)

For each signal in the primary group: **short** (long for the mirror case) **1 contract at the open of
t+1**. Stop = entry + 1 × ATR(t). Target = entry − 1 × ATR(t). Time exit at the **close of t+3** if
neither is hit. A gap through the stop or target fills at the open. A same-bar double touch is resolved on
1-minute bars; otherwise **stop first**. One position at a time per market/timeframe: a signal that comes
while a trade is open is skipped and counted.

**Costs (IBKR, per side, Ben's 2026-09-30 levels):** low = all-in fee; **mid (headline)** = fee + 1 tick;
high = fee + 2 ticks. MCL fee **$0.77** (`strategy.futbt.costs_ibkr`). MNQ fee: **not in that table** —
the build chat writes the IBKR CME micro-equity all-in fee in here as a PRE-RUN amendment before any P&L
(expected ≈ $0.62, the MES rate).

Note that entering at the next open, not the signal close, means the trade can differ from the race.
Both are reported, so that gap is visible.

---

## 5. What every run must emit

For each of the 6 market/timeframe combinations (MCL 30m on its shorter IBKR window, labelled "reported only"), each direction (up→down using UWR,
down→up using LWR), at k = 0.5 / **1** / 1.5:

1. **Counts:** bars, dropped (H = L, roll, warm-up), up/down-context bars, signals per bucket, ambiguous,
   skipped (position open), per year.
2. **Base rate:** P(rev) for **all** bars in that context.
3. **Per bucket:** P(rev), P(rev | decided), **edge = P(rev) − base rate** in percentage points, with a
   95% CI from a **block bootstrap by calendar month** (2,000 resamples, seed = crc32 of the draw number).
   Also split by size (small / normal / large) and by colour.
4. **Bars to reversal:** the share reversed by bar 1, 2, 3, 5, 10 and 20 per bucket (a running total that
   counts censored signals in the denominator); median τ among reversals; **Spearman ρ** between UWR and τ
   among reversals, and between UWR and the reversed-by-bar-3 flag (0/1), each with a bootstrap 95% CI.
5. **Dollars (§4), primary group and every bucket:** trades, wins/losses, gross $, costs $, **net $ at
   low / mid / high**, average net per trade, per year, both halves, and 20 sample trades (date, entry,
   exit, reason, $).
6. **Classic-shape subset** (shooting star / hammer): the same as 3–5.
7. **Seen window** (2025-09-23 → end of data): counts and P(rev) only, labelled "seen — not evidence".

**Nothing is ranked. No "best combination" table.** All 6 combinations are shown in one fixed order:
MCL 30m, 1H, 4H, then MNQ 30m, 1H, 4H.

---

## 6. How the answer is read (training side, 2010-06-06 → 2021-12-31)

**Primary tests: 10** = 5 combinations (MCL 1H/4H, MNQ 30m/1H/4H) × 2 directions, each at k = 1, 3 bars, primary group (ratio ≥ 0.6).

A combination-direction **shows an edge** only if all of these hold:

1. Edge > 0, and its block-bootstrap CI at **99.5%** (95% after Bonferroni correction for 10 tests)
   excludes 0.
2. Edge > 0 in both halves (split at the median signal date).
3. No calendar year supplies more than 25% of the excess reversals.
4. **At least 300 signals** in the primary group. Fewer → NOT READ, not failed.

It is **tradeable as shaped** only if it also has:

5. Net > $0 at mid, and net > $0 at high.
6. Both halves net > $0 at mid.

The bars-to-reversal ρ is **descriptive only**: it is reported with its CI and is not a pass/fail test.

---

## 7. Gates before any result

| # | Gate | Why |
|---|---|---|
| G0 | **This file committed** to the repo (W15-0063 subitem 2a) before any WICK-REV code | register before code |
| G1a | **Read-back** of the owned NQ 1m and CL 1h files: first/last bar, bar count per year, gaps. No spend | same bars as W16 / W15 |
| G1b | **MCL 30m from IBKR:** pull MCL (or CL) 30-min bars via `ib_async`, as far back as IBKR serves (expired contracts ≈ 2 years), back-adjusted the same way. It is too short for the training window, so **MCL 30m is reported only**: same tables, no pass/fail, never spends the holdout. Written to `var/` with a read-back (first/last bar, gaps) before use | Databento ceased |
| G2 | **Count-only pre-flight:** §5 item 1 per combination, training side. **No race outcome and no P&L read**; the runner refuses both in this mode | enough signals? |
| G3 | **Look-ahead guards**, each broken by a one-bar shift in a unit test: context uses t−1; ATR for the size bucket uses t−1; race lines use ATR at t and are scanned from t+1; the trade enters at t+1's open | no hindsight |
| G4 | **Holdout** (§8) cut first, own ledger, mutation-tested | `PROGRAM_INDEX` §1 |
| G5 | **Pine eyeball file (optional):** a .pine indicator that marks primary-group signals and their D/U lines, delivered to `D:\Trading\Claude outputs` for Ben to check a few by eye. Never written into his Pine Editor | sanity check |

---

## 8. The holdout

- **Training:** 2010-06-06 → 2021-12-31.
- **Holdout:** 2022-01-03 → 2025-09-22, own ledger **`holdout_w15_0063.json`**. Spent **once**, only on the
  combination-directions that show an edge (§6, 1–4) on the training side; all of those are scored
  together in one run. It refuses `--limit` and every narrowing flag and is mutation-tested. Every other
  study's holdout file is refused by name.
- **Seen window:** 2025-09-23 onward. Never scored.

---

## 9. Registered as NOT to be done

- Changing the bucket edges, the 0.6 cut, EMA length, ATR length, k, or the 3-bar window after a result.
- Picking the best combination, bucket, size split or colour and quoting it as the headline.
- Adding filters (time of day, volume, news, a higher-timeframe trend) after a result. That would be a
  new registration.
- Quoting gross, or P(rev | decided) without P(rev), as the headline.
- Writing to Ben's TradingView Pine Editor from any chat.
- Buying data (Databento has ceased; IBKR only).

---

## 10. Ways this could go wrong

- **Built-in lean.** A bar that closed near its low has already started falling, and short-term
  autocorrelation (the next bar tending to follow, or undo, the last) can show up as an "edge" that is
  just momentum or mean reversion of returns. The base rate removes the context effect but not this one.
  The size split and the classic-shape subset help tell them apart.
- **Base-rate drift.** Up-context bars in a rising market (NQ 2010–2021) have a built-in upward drift, so
  P(rev) for all bars will sit below 50%. Edge is measured against that, not against 50%.
- **Overlapping signals.** Consecutive long-wick bars share look-ahead windows, so the bootstrap is by
  month, not by signal.
- **The 4H 14:00 short bar** and thin overnight 30m bars have small ranges, which inflate the ratios.
  The size split shows this.
- **Costs vs ATR on 30m.** On MCL 30m a 1× ATR target can be only a few ticks wide, so costs may take
  most of any edge.

---

## 11. A prediction, written down now

**Long-wick bars reverse slightly more often than the base rate: an edge of about +1 to +4 percentage
points on most of the 10 tests, with perhaps 2–4 of them surviving the Bonferroni cut — mostly MNQ 30m and 1H,
where the sample is largest.** Classic shooting stars look no better than the plain UWR ≥ 0.6 group. The
bars-to-reversal ρ is weak (|ρ| < 0.10): bigger wicks reverse a little more often, not much faster. The
trade-shaped version nets near zero or a loss at IBKR mid on 30m, and is closest to break-even on 4H. I'd
be glad to be wrong.

---

## Next steps (board)

- **W15-0063** sub 1 — Ben: definitions confirmed → Done.
- **W15-0063** sub 2 — Research & spec chat: this file → Done.
- **W15-0063** sub 2a — **Ben: commit this file to the repo (G0).** Haiku · Low. Commands on the board.
- **W15-0063** sub 3 — **Build & test chat, Sonnet · Medium:** `strategy/wick_rev/` — loaders (G1a), IBKR
  MCL 30m pull (G1b, Ben runs it with IB Gateway up), count-only pre-flight (G2), guards (G3), holdout ledger (G4), full run, raw
  .txt. Blocked by sub 2a.
- **W15-0063** sub 3a — Build & test chat: IBKR MCL 30m pull + read-back (G1b). Sonnet · Low.
- **W15-0063** sub 4 — Build & test chat, Sonnet · Low: Result doc (monday Doc + raw .txt + artifact page).
