# REGISTERED — W16 DVP-v0: Conti "drift VWAP pullback" on NQ (15-min trend filter, 5-min trigger)

**Committed before any code for this rule exists and before any return of this rule has been seen on our data.**
`PROGRAM_INDEX` §2.4: a hypothesis is registered before it is run. Amendments are marked **PRE-RUN** or
**POST-RUN**; a rule or threshold changed after seeing a result is a new hypothesis and spends from §11.

**Board:** W16-0006 (subitem 1 = this file; 2 = build; 3 = Ben runs; 4 = Result doc). Decision: W11-0035 option A.
**Source:** Matteo Conti, *"Ex-Market Maker Shows the Exact VWAP Setup That Gets Traders Funded"*, IQCapital,
YouTube `wm4A6qo0g3I` (44:30). **The full transcript was read by this chat on 2026-09-28** (34,086 characters, 100%),
not only the helper extract in `claude/raw/w11_0034_iqcapital_extracts_20260928.txt`. Shortlist #1 in
`claude/w11_0034_iqcapital_review_RESULT_20260928.md`.
**Engine:** the W16-0003 engine (`strategy/w16/`), same data, sessions, costs and scoring code as
`REGISTERED_w16_session_baselines.md` (SB-v0). Everything this file does not restate is inherited from SB-v0 §2
(markets, series, sessions, early closes, contract sizing) and SB-v0 Amendment A (NinjaTrader Free fees).
**Chat:** Scalping chat.

**Ben's decisions, 2026-09-28, his multiple-choice picks:**
- Trigger bar: **"5-min trigger (Recommended)"**. The three conditions and VWAP use 15-min bars, and the first
  opposite-colour **5-min** candle triggers. The 15-min trigger is reported, not scored.
- Stop size: **"Scale to price (Recommended)"**. Conti's point stop and targets become a fixed fraction of price, set
  from NQ's level in his fitting years (§3.4). His literal point version runs on 2020–2023 as a replication check
  (§7.3).

---

### Amendment A — PRE-RUN, 2026-09-28 (P_ref pinned; one prose correction; one counting fix. No P&L exists yet)

**P_ref, from the G2 pre-flight** (`D:\Trading\Claude outputs\w16_0006_preflight.json`, run 2026-09-28 13:05 UTC on
commit cbbb7cf; median 09:30 1-minute open over XNYS trading sessions 2020-01-02 → 2023-12-29):

| Market | P_ref | Long stop / target | Short stop / target |
|---|---|---|---|
| **NQ** (scored) | **13,034.25** | 0.6138% / 0.3069% of the fill | 0.6138% / 0.3836% of the fill |
| ES (reported only) | **4,082.00** | 80/40/50 × F ÷ 4,082 (§3.6) | |

Pinned in `strategy/w16/drift_vwap.py` as `P_REF_NQ = 13034.25`, `P_REF_ES = 4082.0`. Neither is changed again.

**Pre-flight read (no P&L):** 3,407 NQ training sessions, 3 skipped (all 2020), 3,397 with at least one trigger,
51,059 triggers. The upper bound on entries is 13,540 (3.97 a day, capped at 4 before G-loss and one-at-a-time).
First trigger of the day: 1,848 long, 1,549 short. **Stop / target per MNQ (median): 2010 $23.50 / $13.50, 2016
$55.00 / $30.50, 2023 $181.00 / $95.00.** Well above the 300-trade floor.

**Correction to §3.5's prose (not a rule change):** "costs are about 3% of the target" holds only at 2020s prices.
Because the stop and target scale with price, an L2 round trip on MNQ (~$2.38–$2.88) is **about 20% of the median
target in 2010** and about 9% in 2016. So costs weigh most in the early years, and criterion 2 (both halves) and the
by-year table will show it. This is a consequence of the registered scaling, recorded now, before any result.

**Counting fix (code, before any P&L):** the first pre-flight grouped the Globex archive by ET date and counted
Sundays and exchange holidays as "sessions skipped". Only XNYS trading days now count (SB-v0 §2, inherited by §2
here). The replication block's trades per day is per trading session, which matches how Conti's ~2.8 is computed.
Commit cbbb7cf. P_ref was the same before and after the fix.

---

## In plain terms

Conti's rule waits until Nasdaq futures have a clear intraday drift. On the 15-minute chart, three things must all be
true: price is above the day's VWAP, VWAP itself is rising, and Nasdaq is up at least 0.1% over the past hour (or the
reverse, for a downtrend). It then buys the first red 5-minute candle (sells the first green one in a downtrend) at the
next candle's open. Each trade risks twice what it aims to make: long 80 points to make 40, short 80 to make 50, with
a few daily limits. That only pays if about 60% or more of trades win. He claims 64%. We test it on 1 micro Nasdaq
contract (MNQ) from mid-2010 to 2023, with real NinjaTrader fees plus a tick of slippage. We also compare it with
taking the same trades at random times of the same day. If it passes, it gets one look at the locked 2024-onward data.

---

## 0. PRE-RUN GATES — no P&L is computed until every row is true

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Data**: SB-v0's G1 stands (passed 2026-09-27: ES and NQ `ohlcv-1m`, 100.0000% daily agreement, 4,190 RTH sessions each). No new data. | Same bars. |
| **G2** | **Pre-flight, no P&L** (§6.1): P_ref computed and written in as Amendment A; trade counts per year; trades per day; long/short mix; guardrail stops; stop and target distance in $ per MNQ. The runner refuses P&L in this mode. | Fixes the sizing constant and shows whether there is enough to read before any profit is seen. |
| **G3** | **Holdout cut and enforced in code** (§8): own ledger `holdout_w16_dvp.json`, mutation-tested. | `PROGRAM_INDEX` §2.5. |
| **G4** | **Look-ahead guards tested** (§6.2), each by a test that a one-bar shift breaks. | Two timeframes are mixed here. That is where look-ahead creeps in. |
| **G5** | **Costs**: SB-v0 Amendment A (NinjaTrader Free, MNQ $0.94/side all-in, NQ $2.87/side) applies unchanged. | Already priced before any W16 P&L. |

---

## 1. The hypothesis, in one sentence

**Conti's drift-VWAP pullback on NQ, with its stop and targets scaled to price, makes money on 1 MNQ after
NinjaTrader Free fees plus one tick of slippage per market or stop fill, on 2010-06 → 2023-12 training data, and beats
the same trades placed at random times of the same day.**

The random-timing test is the one that matters most. The rule's stop is twice its target. So a high win rate is partly
built in by the exit geometry: any entry with a far stop and a near target wins often. The question is whether *his*
entry points win often enough to cover the larger losses, and more often than random entries with the same exits.

---

## 2. Market, bars, sessions

| Element | Registered rule |
|---|---|
| Market | **NQ** (`NQ.v.0`, GLBX.MDP3), as SB-v0 §2. **Scored: NQ only** (Conti's market). ES reported only (§3.6). |
| Contract | **1 MNQ ($2/pt)** headline; per 1 NQ ($20/pt) beside it. Before May 2019, micro = full ÷ 10 (SB-v0 §2). |
| Session | 09:30–16:00 ET, XNYS days; early closes end at 13:00 (SB-v0 §2). |
| Bars | 1-minute `ohlcv-1m` archive, **resampled inside each session into 15-min and 5-min bars anchored at 09:30 ET** (09:30–09:44, 09:45–09:59, …; 09:30–09:34, 09:35–09:39, …), OHLCV = first / max / min / last / sum. A bar is knowable at its close (start + 15 or + 5 min). A 5- or 15-min period with no 1-minute bars has no bar. |
| Skipped days | A session missing its 09:30 1-minute bar, or with a gap > 5 min between 1-minute bars inside **09:30–10:30**, is skipped and counted (VWAP and the 1-hour change need the first hour). |
| Account | $22,129, fixed 1 MNQ per trade, no compounding. |
| Rolls | Intraday only. Every trade opens and closes inside one RTH session, so it never spans the 00:00 UTC map change. A trade whose entry and exit 1-minute bars carry different `instrument_id`s is voided and counted (not expected). |

---

## 3. The rule

Times are ET. "Close of a bar" means that bar's last price at its close time.

### 3.1 The drift conditions — evaluated on each completed 15-min bar *k* (k = 0 is the 09:30 bar)

| # | Long drift | Short drift |
|---|---|---|
| V | **VWAP_k** = Σ(typical × volume) ÷ Σ volume over the session's 15-min bars 0…k, typical = (H + L + C) ÷ 3. *(Conti: "a VWAP based on the 15-minute chart", anchored at 09:30.)* | same |
| C1 | close_k **>** VWAP_k | close_k **<** VWAP_k |
| C2 | VWAP_k **>** VWAP_(k−1) ("VWAP rising over the past 15 minutes") | VWAP_k **<** VWAP_(k−1) |
| C3 | close_k ÷ P1h_k − 1 **≥ +0.001** | close_k ÷ P1h_k − 1 **≤ −0.001** |

**P1h_k** is the price one hour before bar k's close: close_(k−4) for k ≥ 4, and the session's 09:30 open for k = 3
(bar 3 closes at 10:30, exactly one hour after the open). For k ≤ 2 the conditions are undefined (and trading is
closed anyway, §3.3).

The **drift state** at any moment τ is the state of the latest 15-min bar whose close time is ≤ τ: LONG if C1–C3 long
all hold, SHORT if C1–C3 short all hold, else NONE.

### 3.2 The trigger and entry — on 5-min bars

| # | Rule |
|---|---|
| T | While flat and allowed to trade (§3.3), a **5-min bar *j* that closes at τ** is a trigger if the drift state at τ is LONG and bar *j* is **red** (close < open), or the drift state at τ is SHORT and bar *j* is **green** (close > open). A bar with close = open is never a trigger. *(Conti: "the trigger for the longs, first red candle towards the VWAP"; "first green candle after all the three conditions have been satisfied"; "it doesn't matter how close it is to the VWAP".)* |
| F | **Fill: market at the open of 5-min bar *j*+1** (= the open of the 1-minute bar starting at τ). *(Conti: "as the candle closes, you send a market order".)* |
| First | After an exit, the next trigger must be a 5-min bar that **starts at or after the exit time**. "First" is read this way: the first qualifying candle while flat. No extra re-arm condition. |

### 3.3 Guardrails (Conti's, as stated)

| # | Rule |
|---|---|
| G-open | **No entries before 10:30.** The earliest fill is the 10:30 open (trigger = the 5-min bar 10:25–10:29, using 15-min bar 3). |
| G-late | **No new trades after 15:30.** The last allowed fill is the 15:30 open. Early-close days: 12:30. |
| G-one | **One position at a time** (by construction). |
| G-four | **At most 4 entries per session.** |
| G-loss | **No entries after the 2nd losing trade of the session.** A losing trade = exit worse than the entry fill in points (gross < 0), which does not depend on the cost level. *(Conti says "max two losses a day" and then "if you have two consecutive trades that are losing trades for the day, we stop". With at most 4 trades these differ only on a loss-win-loss day. The literal "max two losses" reading is scored; "two in a row" is reported, §3.6.)* |
| G-flat | **Flat at 15:55**: market at the open of the 15:55 1-minute bar. Early-close days: 12:55. |

### 3.4 Stop and target — price-scaled (Ben's choice)

Conti's figures in NQ points: **long stop 80, target 40; short stop 80, target 50.** They were fitted on 2020–2024.
Over our training side NQ traded from about 1,700 to about 17,000, so a fixed 80-point stop means about 4% in 2010 and
about 0.5% in 2023. Scaling keeps the rule's shape across the sample.

- **P_ref = the median 09:30 open of NQ over the training sessions 2020-01-02 → 2023-12-29** (Conti's fitting years
  that fall on our training side; 2024 is our holdout and is not read). It is computed by the G2 pre-flight and
  **written into this file as Amendment A (PRE-RUN) before any P&L exists.**
- At each fill price F: **stop distance = 80 × F ÷ P_ref points**, **long target distance = 40 × F ÷ P_ref**,
  **short target distance = 50 × F ÷ P_ref**, each rounded to the nearest 0.25-point tick (minimum 1 tick).
- Stop and target rest from the fill. Exits are walked on **1-minute bars** from the fill minute onward, with SB-v0
  §3.1's conventions (`strategy.w16.signals.walk_stop_target_time_exit`): a bar opening through the stop fills at its
  open; a target fills only when a bar trades **through** it by ≥ 1 tick; **if one bar reaches both, the stop wins**;
  otherwise flat at 15:55 (G-flat).

### 3.5 Costs (SB-v0 §4 and Amendment A, unchanged)

L1 = NinjaTrader Free all-in fee per side (MNQ $0.94, NQ $2.87), 0 ticks. **L2 (scoring) = L1 + 1 tick on every
market or stop fill** (entry, stop, 15:55 exit); target fills 0 ticks. L3 = L1 + 2 ticks. L0 = nothing (replication
only). On MNQ an L2 round trip costs $2.38–$2.88 against a stop of about $160 and a target of about $80–$100. So costs
are about 3% of the target, not the deciding issue they were for SB-v0's B3.

### 3.6 Reported, never scored

- **15-min trigger:** the same rule with the trigger read on 15-min bars (fill at the next 15-min bar's open).
- **Guardrail "two losses in a row"** in place of "two losses a day".
- **No guardrails** (all triggers taken, still one position at a time, still 10:30–15:30 and flat at 15:55).
- **Literal points over the whole training side** (80/40, 80/50, not scaled).
- **ES**, same rules, P_ref from ES's own 2020–2023 median open.
- Long and short books shown separately (a breakdown of the scored cell, not a variant).

---

## 4. What every run must emit — in dollars and actual trades

As SB-v0 §5, for the one scored cell and each reported variant:

1. Per 1 MNQ (and per 1 NQ): trades, wins/losses, **win rate**, gross, costs, net, average win, average loss, largest
   loss, worst losing run, worst day, worst month, max drawdown in $, at L1, L2, L3. L2 is the headline.
2. Every calendar year of the training side; both halves split at the median trade date.
3. Exit reasons (stop / target / 15:55) and counts: sessions skipped, days stopped by G-loss, days capped by G-four,
   same-bar stop-and-target ties, voids.
4. **Break-even win rate** at L2 given the realised average win and average loss, beside the actual win rate.
5. Trades per day (median, p90, max) and the long/short split.
6. Control (§7.1) and reported controls (§7.2), run fresh on the same bars, costs and period.
7. Neighbour grid (§7.4): net at L2 per cell and the share net-positive.
8. Account view at $22,129: equity curve, max drawdown in $ and as % of the account.
9. 20 sample trades (every 1/20th of the list): date, side, trigger bar, fill time and price, stop, target, exit time
   and price, exit reason, net $ per MNQ.
10. The replication block (§7.3) beside Conti's stated figures.

**Nothing is ranked.** Holdout numbers appear nowhere until §8's spend.

---

## 5. Why this can pass, and why it probably won't

For it: VWAP is a real execution benchmark, and there is published evidence that intraday index returns show
momentum after a strong first hour. Conti's rule also has only one fitted threshold (0.1%) plus the stop and target.

Against it: the exit shape makes a high win rate cheap to get. With a 2:1 stop-to-target on the long side, a rule
with no edge at all wins about two-thirds of the time before costs if price wanders randomly, and still loses money.
His 64% sits *below* the long side's 66.7% break-even and above the short side's 61.5%. On his own stated averages
($866 win, $1,300 loss) the break-even is 60.0%, which leaves 4 points of room. Our costs, the tick of slippage on the
stop and time exits, and 2024-on decay each take some of that room.

---

## 6. Before the backtest — no P&L in this section

### 6.1 Pre-flight (G2) — training side only

- **P_ref** (§3.4), printed, then written in as Amendment A before the backtest runs.
- Per year: sessions, sessions skipped, triggers, entries (long/short), days stopped by G-loss, days capped by
  G-four. Trades per day (median, p90, max). Stop and target distance in $ per MNQ (median, p90, max), in 2010, 2016
  and 2023.
- **No exit price is read and no P&L is computed**. Entries are counted as if every trade ran to 15:55, because
  G-loss needs trade outcomes. So the pre-flight counts **triggers and first entries per day** and flags that the
  real entry count (after G-loss) will be lower.
- **Stop rule:** fewer than **300 training trades** in the scored cell → NOT READ (reported, not failed). Not
  expected: about 3,400 sessions, most with at least one trigger.

### 6.2 Look-ahead guards (G4) — each proven by a test that a one-bar shift breaks

- The drift state at τ reads only 15-min bars that **close at or before τ**. A test moves a 15-min bar's close one
  minute past τ and the state at τ must change.
- VWAP_k and P1h_k use bars ≤ k only.
- A trigger at 5-min bar *j* fills at bar *j*+1's open, never *j*'s close.
- The exit walk starts at the fill minute. The fill bar's own high/low can hit the stop (tested) but cannot pre-date
  the fill.
- G-loss counts only trades that have **closed** before the trigger bar starts.
- P_ref reads only 2020-01-02 → 2023-12-29 opens. A test asserts that adding a 2024 bar does not change it.
- The holdout refusal (§8) is mutation-tested.

---

## 7. Controls, replication and grid

### 7.1 Scored control — C-D1 random timing (1,000 seeded draws, seed = `zlib.crc32` of the draw number)

For every real trade: **same session, same direction, same stop and target distances in points, entry at the open
of a uniformly random 5-min bar starting 10:30 … 15:30 of that session, exit by the same walk (stop, target, 15:55).**
Draws are independent per trade: overlap is allowed and the guardrails are not re-applied, so the control keeps the
real trade count exactly. Report p5 / p50 / p95 of net at L2. The rule must beat **p95**.

This is the sharp test: the same exposure, exit shape, days and direction, differing only in *when* in the day it
enters.

### 7.2 Reported controls

- **C-D2 no pullback:** enter at the next 5-min open after the drift state *turns* LONG or SHORT, without waiting for
  an opposite-colour candle; same exits and guardrails. Does waiting for the pullback add anything?
- **C-D3 random direction:** the real entry times and exits with the side chosen by a seeded coin (1,000 draws;
  stop and target distances follow the drawn side). Does the drift filter's *direction* add anything beyond timing?

### 7.3 Replication (`PROGRAM_INDEX` §3) — harness check, reported beside the verdict

**Conti's literal rule** (80/40 long, 80/50 short, in NQ points, 5-min trigger, his guardrails) on **2020-01-02 →
2023-12-29**, per 1 NQ, at L0 and L2. His stated figures: **64% win rate, average win $866, average loss $1,300 per 1
NQ, more than 4,000 trades 2021 → Aug 2026 (about 2.8 a day)**. These years are inside his own fitting window, so this
is not a test of edge. It checks that our reading of his rule behaves like his:

- Win rate within **60–68%**, trades per day within **1.5–4.0**, and average win and average loss each within
  **±25%** of his. If this holds, our harness and our reading match.
- If it misses, the Result doc says so first. It then runs the same block with the **15-min trigger** as a diagnostic,
  because trades per day is the figure most likely to tell the two readings apart. The scored rule does not change.

### 7.4 Neighbour grid — 9 cells, net at L2, training side

| Dimension 1 | Dimension 2 |
|---|---|
| stop and targets × {0.75, **1.00**, 1.25} (all three distances scaled together) | C3 threshold {0.05%, **0.10%**, 0.15%} |

Registered values in bold. The grid is a robustness check, not a search: no cell can replace the registered rule.

---

## 8. The holdout

- **Training: 2010-06-06 → 2023-12-29.** **Holdout: 2024-01-02 → the end of the pulled data.** Same dates as SB-v0,
  but **its own ledger, `holdout_w16_dvp.json`**. It is refused by name from every other line's ledger, including
  SB-v0's `holdout_w16_sb.json`, and refuses `--limit` and every narrowing flag; mutation-tested (G3). Two
  hypotheses on the same dates each get one look through their own ledger (the practice of HTF-Ben v1/v2 and TL-bounce).
- **Spent once, by the scored cell (DVP-NQ), only if it passes §9.**
- **Holdout bar** (L2, 1 MNQ): net > $0; net per trade ≥ one third of its training net per trade; beats the p95 of
  C-D1 re-run on the holdout; net > $0 at L3.
- **Disclosed:** Conti claims his rule kept rising out-of-sample from 2024 to 2 Aug 2026, which covers most of our
  holdout. That claim is public; it is not a reading of our data. No part of this project has read NQ intraday bars
  from 2024 on.

---

## 9. The bar to clear — the scored cell (DVP-NQ), training side, 1 MNQ, L2

A single scored cell, so the project's standard thresholds apply. It **passes** only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. **Bootstrap by calendar month** (2,000 seeded resamples with replacement): net > 0 in **≥ 95%**.
5. Net > **C-D1 p95** (§7.1).
6. Net > $0 at **L3**.
7. Net > $0 after dropping the best **1%** of trades.
8. At least **6 of the 9** neighbour cells (§7.4) net > $0 at L2.
9. At least **300** trades. Fewer → NOT READ, not failed.

Replication (§7.3) and reported variants (§3.6, §7.2) sit beside the verdict and are not part of it.

---

## 10. Ways this could go wrong

- **Which chart triggers.** Conti never says. Ben chose the 5-min chart. The replication block's trades-per-day
  figure is the check: his ~2.8 a day fits a 5-min trigger better than a 15-min one, but it is only a check.
- **VWAP on 15-min bars versus trades.** A bar VWAP approximates the true one. C1 and C2 are sign tests, so errors
  only move trades near the line.
- **1-minute resolution.** A stop about 0.6% away and a target about 0.3% away are rarely both inside one NQ minute.
  The same-bar tie count will show it.
- **Price scaling is our construction, not his.** In the 2020–23 years it is close to his points by design (P_ref is
  their median level). Earlier years test the *shape* of his rule, not his numbers. That is why the replication block
  runs the literal points separately.
- **Long drift.** 2010–2023 is a strong bull market. C-D1 keeps the same long/short mix and exits, so drift alone
  cannot pass criterion 5.
- **Prior evidence:** SPY/QQQ/IWM intraday momentum was negative before costs from 2016 (W13). Small-cap ORB closed
  at a loss (W12). SB-v0 has not reported yet. Its B3 (plain VWAP flip on NQ) and this rule share VWAP but not their
  entry or exit.

---

## 11. Multiplicity budget

This registration scores **one cell** (DVP-NQ). Every other number it prints is reported only. After it reports, this
line may register **two** further hypotheses on this rule (for example, ES as a scored market, or a daily-stop overlay
from W16-0007). A third needs a reason that does not begin with a result. It is not charged to SB-v0's §11 budget: it
comes from a different source (W11-0035) and has its own ledger.

---

## 12. Registered as NOT to be done

- Swapping in the 15-min trigger, the literal-points version, "two losses in a row", no guardrails, or a grid cell
  after seeing a result.
- Re-fitting 0.1%, 80/40 or 80/50 to our data. P_ref is fixed once, by the pre-flight, before any P&L.
- Adding a filter (time of day, day of week, volatility, trend) after a result. That is a new hypothesis (§11).
- Quoting gross, L1, per-NQ or win rate alone as the headline. Win rate means nothing here without average win and
  loss beside it.
- Reading the holdout with `--limit`, any narrowing flag, or for any variant.

---

## 13. A prediction, written down now

**The replication block (2020–23, literal points) shows a win rate near 60–65% and roughly break-even or small
positive gross per NQ**. Those are his fitting years, and the exit shape produces a high win rate on its own. **The
scored cell fails.** Net at L2 over 2010–2023 is near zero or negative. It does **not** beat C-D1's p95, because
random entries with the same far stop and near target win about as often. At least one half and several early years
are negative. I'd be glad to be wrong.

---

## Next steps (board, W16-0006)

- **Subitem 1 — Scalping chat (Opus · High):** this file. Ben commits it with the build (commands on subitem 3).
- **Subitem 2 — Scalping chat with a Sonnet · High helper:** `strategy/w16/drift_vwap.py` (signals, guardrails,
  price scaling), controls C-D1–C-D3, grid, replication block, `holdout_w16_dvp.json` ledger, pre-flight mode, and
  tests incl. every §6.2 guard; reuse `strategy/w16/{sessions,signals,costs,runner}.py`.
- **Subitem 3 — Ben:** commit, run tests, run the pre-flight. The Scalping chat writes Amendment A (P_ref), then Ben
  runs the training backtest.
- **Subitem 4 — Scalping chat (Sonnet · Medium):** Result doc against §9.
