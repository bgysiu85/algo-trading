# REGISTERED — W16 SB-v0: ES/NQ session baselines on 1-minute bars (opening-range breakout, overnight hold, VWAP flip)

**Committed before any ES/NQ intraday bar has been pulled or read, before any code for this line exists, and before
any return of any rule here has been seen on futures.** `PROGRAM_INDEX` §2.4: a hypothesis is registered before it is
run. Amendments are marked **PRE-RUN** or **POST-RUN**; a rule or threshold changed after seeing a result is a new
hypothesis and spends from §11.

**Board:** W16-0003 (subitem 1 = this file; 2 = data; 3 = build; 4 = run + Result doc). Decision: W16-0002.
**Source:** `claude/w16_0001_chart_fanatics_scalping_RESULT_20260927.md` (options table, row A) and
`claude/raw/w16_0001_chart_fanatics_scalping_extracts_20260927.txt`, batch 1, video 1 — Matteo Conti,
"4 Institutional Scalping Strategies" (yW6c0K8uGvw), strategies A (ORB), B (VWAP) and D (overnight).
**Chat:** Scalping chat.

**Ben's decisions, 2026-09-27, in his words / his multiple-choice picks:**
- *"W16-0002. Let's start with A"* — the three session baselines go first.
- Holdout: **"2024 onward (Recommended)"** — train 2010-06 → 2023-12; 2024-01 onward locked.
- Costs: **"NinjaTrader Free (Recommended)"** — same basis as W15.
- Scored ORB version: **"Long + short, 2:1 target (Recommended)"**.

---

### Amendment A — PRE-RUN, 2026-09-27 (G5 costs; before §5 computes any P&L — G2's pre-flight reads no exit prices and no P&L, so this does not follow a result)

Rates read live from `ninjatrader.com/pricing/commissions/` (page dated "as of August 14, 2026 ... updated
quarterly" — the same table W15's Amendment A and W16's own H60/HTF lines read on 2026-09-25), which lists itemized
exchange+NFA, clearing and commission fees per contract, and an "all-in" figure that is their sum:

| Symbol | Product | Exch+NFA | Clearing | Commission (Free) | **All-in (Free), per side** |
|---|---|---|---|---|---|
| **MES** | Micro E-mini S&P 500 | $0.36 | $0.19 | $0.39 | **$0.94** |
| **MNQ** | Micro E-mini NASDAQ-100 | $0.36 | $0.19 | $0.39 | **$0.94** |
| **ES** | E-mini S&P 500 | $1.39 | $0.19 | $1.29 | **$2.87** |
| **NQ** | E-mini NASDAQ 100 | $1.39 | $0.19 | $1.29 | **$2.87** |

So **§4's L1 ("low", NinjaTrader all-in fee, 0 ticks) is $0.94/side for MES and MNQ, and $2.87/side for ES and NQ.**
L2 (the scoring level) and L3 add 1 and 2 ticks respectively on every market or stop fill (tick values already
registered in §2: MES $1.25, MNQ $0.50, ES $12.50, NQ $5.00 per tick) — target fills add 0 ticks either way. This is
a plan choice Ben makes independent of any backtest result; moving to a paid plan later (Lifetime/Monthly rates, same
page) is a live-trading decision, not a re-registration of this study.

**Overnight margins** (B2, reported per §5 item 7, never scored), read live 2026-09-27 from
`ninjatrader.com/margin-details/`: **MES** day $50.00 / maintenance $2,619.42 / initial $2,881.37; **MNQ** day
$100.00 / maintenance $4,329.42 / initial $4,762.37.

`strategy/w16/costs.py` pins every figure above as a module-level constant, cross-checked against the tick-value
table by test (`tests/strategy/w16/test_costs.py`).

---

## In plain terms

We test three simple, widely quoted day-trading rules on the S&P 500 and Nasdaq-100 futures, one micro contract at a
time, on 1-minute bars from mid-2010: (1) buy or sell the break of the 9:30–10:00 range with the stop on the other
side and a target twice the risk; (2) buy at the 4 pm close and sell at the next morning's 9:30 open; (3) be long
whenever price is above the day's VWAP (the volume-weighted average price since 9:30) and short whenever it is below.
Each is charged NinjaTrader's real fees plus slippage, judged in dollars per trade, and compared with doing the same
number of trades at random times. They are baselines: if none of them makes money after costs, intraday index futures
are probably not worth building on; if one does, it gets one look at the locked 2024-onward data.

---

## 0. PRE-RUN GATES — no P&L is computed until every row is true

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Data priced, pulled, read back** (§6.1): ES and NQ `ohlcv-1m` from GLBX.MDP3, 2010-06-06 → pull date. Priced first and the dollar figure stated before `--confirm` (`PROGRAM_INDEX` §2.12). Read-back: bars per session, gaps > 5 min inside 09:30–16:00 ET listed, roll dates listed, daily closes rebuilt from 1-min bars (UTC days, as W15 Amendment B) vs `ohlcv-1d` on the same symbols: ≥ 99% of days within 1 tick, volume equal, every miss listed. No indicator, signal or P&L. | Nobody in this project has read ES/NQ intraday bars. |
| **G2** | **Pre-flight, no P&L** (§6.2): trade counts per baseline, per market, per year; ORB range width and stop distance in $ per micro; VWAP flips per day. The runner refuses P&L in this mode. | Tells us whether there is enough to read, and what a stop costs, before any profit is seen. |
| **G3** | **Holdout cut and enforced in code** (§8): `holdout_w16_sb.json`, mutation-tested. | `PROGRAM_INDEX` §2.5. |
| **G4** | **Look-ahead guards tested** (§6.3), each by a test a one-bar shift breaks. | Every rule here reads a completed 1-minute bar. |
| **G5** | **Costs priced** (§4) — NinjaTrader Free all-in per side for MES, MNQ, ES, NQ read from the live commissions page and written in as Amendment A **before** §5 computes any P&L; overnight margins for MES/MNQ recorded beside them. | A cost chosen after the result is a cost chosen to fit it. |

---

## 1. The hypothesis, in one sentence

**At least one of Conti's three session rules — the 30-minute opening-range breakout (long and short, 2:1 target),
the overnight hold (long 16:00 → 09:30 ET) and the VWAP flip (long above, short below, flat at the close) — makes
money on 1 MES or 1 MNQ after NinjaTrader Free fees plus one tick of slippage per market or stop fill, on 2010-06 →
2023-12 training data, and beats the same number of trades placed at random times with the same exits.**

The random-timing part is the one that matters. A long-only rule on a market that went up 5-fold over the sample will
make money by being long; the question is whether *when* it is long is worth anything.

---

## 2. Markets, bars, sessions

| Element | Registered rule |
|---|---|
| Markets | ES (E-mini S&P 500) and NQ (E-mini Nasdaq-100), GLBX.MDP3 |
| Series | Databento continuous **`ES.v.0` / `NQ.v.0`** (the highest-volume contract), `stype_in = continuous`. Volume-led rather than calendar-led because index futures move to the next quarter ~8 days before expiry; a calendar front would trade the thin expiring contract in roll week. Every bar keeps its `instrument_id`. |
| Bars | `ohlcv-1m`; `ts_event` = bar **start** (`common/dbn_io.py` convention 1). A bar is knowable at its close. Minutes with no trade have no bar; nothing is filled in. |
| Session | **Regular hours 09:30–16:00 America/New_York**, on New York Stock Exchange trading days (XNYS calendar). DST is handled by the clock, not a fixed UTC offset. "The 09:30 open" = open of the bar starting 09:30; "the 16:00 close" = close of the bar starting 15:59. |
| Early closes | On XNYS early-close days the session ends at the XNYS close (13:00): every "16:00" below means that close, and ORB's 15:30 time exit means 30 minutes before it. |
| Days that don't count | Days the XNYS calendar lists as closed (Good Friday, etc.), even if Globex trades. A session missing its 09:30 bar or with a gap > 5 min inside 09:30–10:00 is skipped by ORB and VWAP and counted. |
| Contract per trade | **1 MES ($5 a point) or 1 MNQ ($2 a point)** — the headline. Per 1 ES ($50) / 1 NQ ($20) reported beside it. Before the micros listed (May 2019), micro = full ÷ 10 *(convention, as TSMOM and W15)*. Prices always come from the ES/NQ bars. Tick = 0.25 pt: MES $1.25, MNQ $0.50, ES $12.50, NQ $5.00. |
| Account | $22,129 (the project's standard). Fixed 1 micro per trade, no compounding, no leverage scaling. |
| Rolls | A trade whose entry and exit bars carry different `instrument_id`s is **voided and counted** (overnight holds only — the continuous map changes at 00:00 UTC, inside the overnight session; ORB and VWAP trades never span it). Expected ~4 a year per market. |

---

## 3. The rules

Signals are read on a bar's close; fills are at **the next bar's open** unless stated. One position per baseline per
market at a time. Baselines run independently (three separate books per market, never netted).

### 3.1 B1 — Opening-range breakout (Conti strategy A) — scored version: long + short, 2:1

| # | Rule |
|---|---|
| R | **Range** = high H and low L of the 30 bars starting 09:30 … 09:59. Width W = H − L. |
| E | **Entry**: the first bar starting 10:00 … 15:28 that **closes above H** → long; **closes below L** → short. Fill at the next bar's open. **At most one ORB trade per market per day** (the first trigger; no re-entry after a stop). |
| S | **Stop** at the other side of the range (L for a long, H for a short), resting. A bar that opens through the stop fills at its open (`gap_fills=True`). |
| T | **Target** = fill ± 2 × (distance from fill to stop), resting limit. Filled only if a later bar trades **through** it by ≥ 1 tick (a touch is not a fill). |
| X | **Time exit**: market at the open of the 15:30 bar if neither stop nor target has filled. |
| Both | If one bar reaches both stop and target, **the stop wins**. |
| Void | If the fill is already beyond the stop (a gap through the whole range on the entry bar), the trade is voided and counted. |

Reported, never scored: **long-only 2:1**; **long + short 1:1**; **gap-inclusive range** (H' = max(H, prior 16:00
close), L' = min(L, prior close) — one reading of Conti's "overnight gap + first 30 minutes").

### 3.2 B2 — Overnight hold (Conti strategy D)

| # | Rule |
|---|---|
| E | **Buy 1 micro at the 16:00 close** (close of the 15:59 bar, plus entry slippage) on every XNYS trading day. |
| X | **Sell at the next XNYS trading day's 09:30 open** (open of the 09:30 bar, plus exit slippage). Friday → Monday and holiday spans are included as they fall. |
| — | No stop, no target. Long only (Conti's rule). |

Reported, never scored: the **intraday complement** (long 09:30 open → 16:00 close the same day) — also used as
control C-O2.

### 3.3 B3 — VWAP flip (Conti strategy B; Zarattini & Aziz, SSRN 4631351)

| # | Rule |
|---|---|
| V | **VWAP** from 09:30: cumulative Σ(typical price × volume) ÷ Σ volume over the session's bars so far, typical price = (H + L + C) ÷ 3. *(Assumed — a 1-minute-bar approximation of a trade-by-trade VWAP; see §10.)* |
| E | At the close of each bar starting 09:30 … 15:57: close > VWAP and not long → **go long** (reversing a short); close < VWAP and not short → **go short** (reversing a long). Close = VWAP → no change. Fill at the next bar's open. |
| X | **Flat at the 16:00 close** (close of the 15:59 bar). No stop, no target, no overnight. |
| Cost | A reversal is two trades: the exit of one and the entry of the next, each charged its own fees and slippage. |

---

## 4. Costs — three levels, per micro, charged on every trade (G5)

| Level | What is charged | Use |
|---|---|---|
| **L1 low** | NinjaTrader **Free** plan all-in fee per side (exchange + NFA + clearing + commission), both sides, 0 ticks | reported |
| **L2 mid — the scoring level** | L1 **plus 1 tick** on every market or stop fill (entries, stops, time exits, flat-at-close, overnight entry/exit). Target limit fills: 0 ticks. | **headline, all criteria** |
| **L3 high** | L1 **plus 2 ticks** on every market or stop fill; target fills 0 ticks | criterion 6 |
| L0 zero | nothing charged | replication controls only (§7.4) |

The fee figures are filled in by **Amendment A (PRE-RUN)** above, read from `ninjatrader.com/pricing/commissions/`
before any P&L exists (the page loads its table by script; read it in a browser). Per full contract (ES, NQ) the same
levels use the full contract's fee and tick value. Every P&L figure says which level it is at (`PROGRAM_INDEX` §2.6).

---

## 5. What every run must emit — per baseline, per market, in dollars and actual trades

1. Per 1 MES / 1 MNQ (and per 1 ES / 1 NQ): trades, wins/losses, gross, costs, net, average win, average loss, largest
   loss, worst losing run, worst day, worst month, max drawdown in $ — at L1, L2, L3. L2 is the headline.
2. Every calendar year of the training side; both halves split at the median trade date.
3. Exit reasons (B1: stop / target / 15:30; B3: flip / close) and counts: sessions skipped, trades voided (range
   gap-through, roll), same-bar stop-and-target ambiguities (B1).
4. B1: range width and stop distance in $ per micro (median, p90, max). B3: trades per day (median, p90, max).
5. Controls (§7), each run fresh on the same bars, costs and period.
6. Neighbour grid (§7.3): net at L2 for each cell and the share net-positive.
7. Account view at $22,129: equity curve, max drawdown, largest drawdown as % of the account; for B2, the
   NinjaTrader overnight margin per micro (from G5) against the account.
8. 20 sample trades per cell (every 1/20th of the list): date, side, entry time and fill, stop, exit time and price,
   exit reason, net $ per micro.
9. Reported-only variants (§3), clearly labelled "reported — not scored".

**Nothing is ranked. No "best cell" table.** Holdout numbers appear nowhere until §8's spend.

---

## 6. Before the backtest — no P&L in this section

### 6.1 Data (G1)

- Dataset `GLBX.MDP3`, schema `ohlcv-1m`, symbols `ES.v.0`, `NQ.v.0`, `stype_in=continuous`, 2010-06-06 → the pull
  date; plus `ohlcv-1d` on the same symbols for the read-back. Stored under `E:\Databento\GLBX.MDP3\` in a folder of
  its own (`w16_session\`) — the TSMOM and W15 files are not touched.
- **Priced first** with Databento's cost query; the dollar figure and GiB are stated on the board before `--confirm`.
  **If the price is above $50, stop and go back to Ben** (W10-0001: the $199/month plan is kept until a strategy is
  settled; the pull may be covered by it — the pricing says).
- Read-back as in G1 (§0). **Stop rule:** < 99% agreement → report, no signal code runs.

### 6.2 Pre-flight (G2) — training side only, no P&L

Per baseline, market and year: sessions, sessions skipped, entries, voids, and the distributions in §5.4.
**Stop rule:** any scored cell with **fewer than 300 training trades** is NOT READ (reported, not failed) — not
expected for any cell (≈ 3,400 sessions).

### 6.3 Look-ahead guards (G4) — each proven by a test that a one-bar shift breaks

- ORB: H and L use only bars starting 09:30 … 09:59; no entry can fill before the 10:01 bar's open.
- VWAP at bar *t* uses bars ≤ *t* only; a signal at bar *t* fills at bar *t*+1's open.
- Overnight: the exit price is the next session's 09:30 **open**, never a later bar.
- Stops and targets are tested only on bars **after** the fill bar opened (the fill bar's own high/low can hit the
  stop — tested — but cannot pre-date the fill).
- The holdout refusal (§8) is mutation-tested: removing it makes a test fail.

---

## 7. Controls, grid and replication

### 7.1 Controls — matched to each cell's own trades, 1,000 seeded draws each (seed = `zlib.crc32` of draw number)

| Cell | Control | Definition |
|---|---|---|
| B1 | **C-B1 random entry** | Same days traded and same long/short mix as B1; entry at a uniformly random bar start in 10:01 … 15:29; same stop distance in points as that day's real trade (placed from the random fill), same 2:1 target, same 15:30 exit. Report p5 / p50 / p95 of net. |
| B2 | **C-O2 intraday complement** | Long 09:30 open → 16:00 close each day (the §3.2 reported variant), same costs. |
| B2 | **C-O3 random window** | Same number of trades, each a long hold of **exactly the same length** as a real B2 trade (17.5 h on a weekday, longer across weekends/holidays), starting at a uniformly random minute of the training period such that both the start and the end minute have a bar (holds may span the daily 17:00–18:00 pause, as B2's own holds do). Report p5 / p50 / p95. |
| B3 | **C-B3 random flips** | Each day, the same number of position changes as B3 had that day, at uniformly random bar closes 09:31 … 15:57, starting long or short at random, flat at 16:00. Report p5 / p50 / p95. |

### 7.2 Why these controls

C-B1 and C-B3 ask whether the *signal* beats the same exposure placed at random. C-O3 asks whether holding
*overnight* beats holding for the same length at any other time — the market's upward drift is in both. C-O2 is
Conti's own comparison (overnight vs daytime).

### 7.3 Neighbour grid — 9 cells per baseline per market, net at L2, training side

| Baseline | Dimension 1 | Dimension 2 |
|---|---|---|
| B1 | range length {15, **30**, 60 min} | target {1.5, **2**, 3} × risk |
| B2 | entry {15:45, **16:00**, 16:15} | exit {09:15, **09:30**, 09:45} |
| B3 | bar size {**1**, 2, 5 min} | flip only after {**1**, 2, 3} consecutive closes on the new side |

Registered values in bold. The grid is a robustness check, not a search: no cell can replace the registered rule.

### 7.4 Replication controls (`PROGRAM_INDEX` §3 — a published mechanism is re-run over its source's own sample)

| Cell | Source sample | Must show |
|---|---|---|
| B3 on NQ | Zarattini & Aziz: QQQ, 2018-01-02 → 2023-09-28, 1-minute, commissions $0 | **gross (L0) > $0** on NQ over the same dates |
| B2 on NQ and ES | Conti: "confirmed 2015 – June 2026"; overnight-vs-daytime literature | **B2 gross (L0) > C-O2 gross (L0)** over 2015-01-02 → 2023-12-29 |
| B1 | none — Conti's 30-minute, 2:1 version has no published sample | — (controls only) |

If a replication control fails, the reading is "the effect does not show on the futures even in the source's own
years" — the cell is still scored, and the Result doc says so first. For B3, a failed replication also triggers a
harness check: the same engine on whatever QQQ intraday bars the W13 archive holds, at their native resolution,
reported only.

---

## 8. The holdout

- **Training: 2010-06-06 → 2023-12-29.** **Holdout: 2024-01-02 → the end of the pulled data** (Ben's choice). The
  holdout lies after both source papers' samples (ORB paper 2016–2023, VWAP paper 2018–2023), so it is a fresh test of
  their claims as well as of ours.
- Its own ledger, **`holdout_w16_sb.json`**, refused by name from every other line's ledger (`holdout.json`,
  `holdout_spy.json`, `holdout_h60.json`, TSMOM's, `holdout_htf_ben_v*.json`, TL's), refusing `--limit` and every
  narrowing flag; mutation-tested (G3).
- **Spent once, by one cell.** If exactly one scored cell passes §9 on the training side, it spends the holdout. If
  more than one passes, **Ben chooses which** from the Result doc (a decision item on the board); if he leaves it to
  Claude, the cell with the highest training net per trade at L2 spends it. If none passes, the holdout stays unspent.
- **Holdout bar** (the spending cell, L2, 1 micro): net > $0; net per trade ≥ one third of its training net per trade;
  beats the p95 of its own random-timing control re-run on the holdout (C-B1, C-O3 or C-B3); net > $0 at L3.
- No part of this project has read ES/NQ intraday bars, so there is no "seen" window. (Conti's claim that the overnight
  effect held to June 2026 is public and is disclosed here; it is not a reading of our data.)

---

## 9. The bar to clear — each scored cell, training side, 1 micro, L2

Six scored cells: B1, B2, B3 × ES, NQ. A cell **passes** only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. **Bootstrap by calendar month** (2,000 seeded resamples of the training months with replacement): net > 0 in
   **≥ 99%**. *(Raised from the project's 95% because six cells are scored: 0.05 ÷ 6 ≈ 0.0083.)*
5. Beats its controls on net: B1 > C-B1 p95; B2 > C-O2 **and** > C-O3 p95; B3 > C-B3 p95.
6. Net > $0 at **L3** high friction.
7. Net > $0 after dropping the best **1%** of its trades.
8. At least **6 of the 9** neighbour cells (§7.3) net > $0 at L2.
9. At least **300** trades. Fewer → NOT READ, not failed.

Replication results (§7.4) are reported beside the verdict, not part of it.

---

## 10. Ways this could go wrong

- **Costs versus move size.** B3 may change sides many times a day. On MNQ one round trip at L2 costs roughly the
  fee plus 2 ticks ($1.00), so each flip must average more than about a point just to pay for itself. W11-0026 (Velez) and
  W13 (SPY intraday momentum) both died on exactly this. Expected to be decisive for B3.
- **1-minute resolution.** When one bar spans both B1's stop and target, the stop wins (conservative). The count is
  reported. On small caps (W12) 55% of entry-minute stops never happened at 1-second resolution; ES/NQ bars are far
  tighter relative to the range, so this should matter much less — the count will say.
- **VWAP from bars, not trades.** Typical-price × bar-volume approximates the true VWAP; errors are largest early in
  the session. The flip is a sign test against VWAP, so small errors only move flips near the line — and the 2- and
  3-close grid cells show whether that matters.
- **Micro pricing before May 2019** is ES/NQ ÷ 10 — fine for P&L, but it ignores the micros' own (then non-existent)
  liquidity. Reported per full contract too.
- **Long drift.** 2010–2023 is a strong bull market in both indices. B2 is long only; C-O3 is there so that drift
  alone cannot pass it.
- **Volume-led roll.** `v.0` can in principle switch back and forth near a roll; G1 lists every switch, and more than
  two per roll is a PRE-RUN amendment before any signal code runs.
- **Prior evidence is against B1 and B3.** ORB on small caps closed at (70,830) over 7,239 trades (W12); SPY/QQQ/IWM
  intraday momentum was negative *before* costs from 2016 (W13). A different market is a fair reason to look again,
  not a reason to expect a different answer.

---

## 11. Multiplicity budget

This registration scores **six cells** (three rules × two markets). Every other number it prints is reported only.
After it reports, this line may register **two** further hypotheses on these session rules (for example B2 with a
filter, or B1 on another market); a third needs a reason that doesn't begin with a result. Options B–E of W16-0002 are
separate lines and are not charged to this budget.

---

## 12. Registered as NOT to be done

- Picking a grid cell, bar size, range length, target or entry time because it did better — the grid never replaces
  the registered rule.
- Adding a stop, a filter, a trend filter or a news filter to any baseline after seeing a result — that is a new
  hypothesis (§11).
- Quoting gross, L1, or per-full-contract figures as the headline.
- Reading the holdout for more than one cell, or with `--limit` or any narrowing flag.
- Netting the three baselines into one book or reporting a "portfolio" of them.

---

## 13. A prediction, written down now

**B2 (overnight hold) is the only baseline I expect to be net positive on both markets**, and I expect it to beat the
daytime complement (C-O2) comfortably — the overnight/daytime split is one of the best-documented patterns in index
returns. I doubt it clears the random-window control at p95 or the 99% month bootstrap: much of what it earns is the
same upward drift any long hold of that length collects. **B1 (ORB) nets near zero or below** at L2 on both markets,
losing to its own random-entry control about as often as it beats it. **B3 (VWAP flip) shows positive gross on NQ in
the 2018–2023 replication window and loses money after costs over the full training side on both markets**, because
it pays for several round trips a day. I'd be glad to be wrong on any of them.

---

## Next steps (board, W16-0003)

- **Subitem 1 — Ben:** read this file, then copy it into the repo and commit it (commands on the subitem). Any rule
  change before the commit is folded in; after the commit, changes are PRE-RUN amendments.
- **Subitem 2 — Build & test chat, Sonnet · Medium:** price and pull the data (§6.1), reusing the W15 CL puller; Ben
  runs the commands; the read-back report goes on the board.
- **Subitem 3 — Build & test chat, Sonnet · High:** engine, costs (Amendment A from the live NinjaTrader table first),
  holdout ledger, look-ahead tests, pre-flight (G2–G5). **Done 2026-09-27** — `strategy/w16/{costs,sessions,signals,
  controls,holdout,preflight,runner}.py` plus 103 passing tests under `tests/strategy/w16/`; see the handover doc for
  what §9 criteria 5 and 8 still need (control/grid wiring, left to subitem 4/5).
- **Subitem 4 — Ben runs the training backtest locally; Scalping chat, Sonnet · Medium, writes the Result doc**
  against §9.
