# REGISTERED — HTF-Ben v0: Ben's 4-hour crude-oil method, coded (CL, MACD/EMA trigger, half-profit trail)

**Committed before any 1-hour CL bar is read, before any backtest code exists, and before any
return of any rule set here has been seen.** `PROGRAM_INDEX` §1: a hypothesis is registered
before it is run.

Board: **W15-0003** (this registration), W15-0001 (rules capture), W15-0002 (data),
W15-0004 (build + run), W15-0005 (fidelity check against Ben's NinjaTrader trades).
Source: `claude/htf_ben_rules_20260925.md` (project) = monday Doc "W15-0001 · HTF-Ben v0 — your
4H crude method as exact rules", including its **Revised 2026-09-25** section (Ben's
confirmations). Ben's decisions, in his words, are quoted where they fix a rule.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a
result is a new hypothesis and spends from the budget in §9.

### Amendment 0 — PRE-RUN, 2026-09-25 (before this file's first commit; no bar read)

Ben: *"if we stick with 4h for intraday trading, would that not be too long? Should we scale
down to 1h or 2h timeframes for intraday trading? for multi-day, we should stick with 4h"*.
Decision, in his words: *"Both 1H and 2H, 2H primary"*, and keep the 4-hour intraday version
as a comparison: *"Yes"*.

So **scenario A (intraday) runs on the 2-hour chart (A-2H, primary)**, with **A-1H** and
**A-4H** reported beside it; **scenario B (multi-day) stays on the 4-hour chart**. Every rule
in §2 applies unchanged on each chart ("4-hour bar" below means "the scenario's entry-chart
bar"); the daily filter stays daily. Reason: a 4-hour signal uses 2–4 of a session's ~6 bars
before it can even enter, so a same-day exit leaves it almost no room. Also added: NinjaTrader's
overnight margin as a reported check on B's account view (§2.5).

### Amendment B — PRE-RUN, 2026-09-25 (G1 had run as a data check only; no indicator, signal or P&L computed)

G1 as first written compared daily closes rebuilt from the 1-hour bars on the
18:00–17:00 New York session against the owned GLBX.MDP3 ohlcv-1d CL.c.0, which
Databento stamps on UTC calendar days (common/dbn_io.py). Different day boundaries
gave 45.58% agreement (1,910/4,190): a convention mismatch, not a data fault
(roll dates and instrument_ids match). Board W15-0006.
Ben's decision, in his words: *"Like-for-like UTC days (Recommended)"*.

§5.1 now reads: the CL.c.0 1-hour bars re-aggregated on UTC calendar days
(ts_event in [D 00:00, D+1 00:00) UTC; close = close of the last bar in the day)
vs the owned ohlcv-1d CL.c.0 close: ≥ 99% of days within $0.05, every miss listed
with its date and whether it is a roll day. High, low and volume are reported beside
it (volume is expected to match exactly). The 18:00 New York session grid is
verified by the bars-module tests (DST crossings, 16:00/14:00 last bars, early
close), not by G1. Stop rule unchanged.

### Amendment A — PRE-RUN, 2026-09-25 (G5 costs; before section 3 computes any P&L — G2's pre-flight read no exit prices and no P&L, so this does not follow a result)

Ben confirmed his NinjaTrader account plan: **Free** (no subscription). Rates read live from
`ninjatrader.com/pricing/commissions/` (page dated "as of August 14, 2026 ... updated
quarterly", re-read 2026-09-25), which lists itemized exchange+NFA, clearing and commission
fees per contract, and an "all-in" figure that is their sum:

| Symbol | Product | Exch+NFA | Clearing | Commission (Free) | **All-in (Free), per side** |
|---|---|---|---|---|---|
| **MCL** | Micro Crude Oil | $0.51 | $0.19 | $0.39 | **$1.09** |
| **CL** | Crude Oil | $1.51 | $0.19 | $1.29 | **$2.99** |

So **§2.5's "low" friction level (NinjaTrader all-in fee, 0 ticks) is $1.09/side for MCL and
$2.99/side for CL.** Mid and high add 1 and 2 ticks respectively, already registered ($1 MCL /
$10 CL per tick). This is a plan choice Ben makes independent of any backtest result, and moving
to a paid plan later (Lifetime $0.79/$2.29, Monthly $0.99/$2.69) is a live-trading decision, not
a re-registration of this study — the training-side result is reported at the Free-plan cost
that applies today, with mid/high giving the same margin of safety either way.

---

## 0. PRE-RUN GATES — the backtest (§3) does not start until all five are cleared

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Data read-back** (§5.1): CL 1-hour bars on disk for 2010-06-06 → the pull date; bars per year, gaps > 3 hours inside a session listed, roll dates listed; **daily closes rebuilt from the 1-hour bars agree with the owned `ohlcv-1d` CL.c.0 closes** on ≥ 99% of sessions within $0.05, every miss listed. No indicator, no signal, no P&L. | The whole study runs on bars nobody in this project has read yet. |
| **G2** | **Pre-flight run and read** (§5.2), training side only, **no P&L**. | Tells us whether there are enough trades to read anything, and what a stop costs in dollars, before a single profit is seen. |
| **G3** | **Holdout cut and enforced in code** (§6), mutation-tested. | `PROGRAM_INDEX` §1. |
| **G4** | **No-look-ahead guards tested** (§8): swing pivots, the daily filter, and the 4-hour indicators each proven not to use a bar before it closes, each by a test that a one-bar shift breaks. | Every rule here reads a completed bar; the classic leak is using the forming one. |
| **G5** | **Costs priced** (amendment A, PRE-RUN): NinjaTrader's published per-side commission + exchange + NFA fees for MCL and CL on Ben's plan, written into §2.5 before the run. | A cost chosen after the result is a cost chosen to fit it. |

W15-0005 (the fidelity replay of Ben's own trades) is **reported, not a gate**: it can only run
when his trade history is available, and it must not hold the study up. Its limits are in §6.1.

---

## 1. The hypothesis, in one sentence

**Ben's 4-hour crude method, coded (daily-EMA trend filter, MACD cross confirmed by EMA9 turning
toward EMA21, stop beyond the last swing, then a stop that always protects half the open
profit), makes money after measured costs on 2010–2021 CL, in the multi-day version on the
4-hour chart and in the flat-by-17:00 intraday version on the 2-hour chart, and beats both a
plain MACD cross and a plain Donchian channel on the same bars, sizing and costs.**

The last part is the one that matters. A MACD cross with a trailing stop is ordinary trend
following. If the daily filter and the EMA confirmation don't beat the plain versions, they are
decoration.

---

## 2. The rules, fixed here

Every parameter below comes from Ben's own answers (2026-09-25) or, where he left it open, is
chosen here **before any data is read** and marked *(assumed)*.

### 2.1 Bars, sessions, series

| Element | Registered rule |
|---|---|
| Market | CL (NYMEX WTI crude), GLBX.MDP3. Results per **1 MCL** ($100 per $1/bbl) and per **1 CL** ($1,000 per $1/bbl). Before MCL listed (2021-07-12), MCL = CL ÷ 10 *(convention, as TSMOM's micros)* |
| Source bars | Databento `ohlcv-1h`, `CL.c.0` (held) and `CL.c.1` (for the roll gap). `ts_event` = bar **start** (`common/dbn_io.py` convention 1). Hours with no trade have no bar; nothing is filled in |
| Session | CME Globex: Sunday–Thursday 18:00 → next day 17:00 **America/New_York**. Resampling is done in New York time, so daylight-saving shifts are handled by the clock, not by a fixed UTC offset |
| Entry charts | **4-hour** (B, and A-4H): 18:00, 22:00, 02:00, 06:00, 10:00, 14:00 New York; the 14:00 bar runs to 17:00 (3 hours). Ben: *"18:00 New York"*. **2-hour** (A-2H, primary intraday): 18:00, 20:00 … 14:00, 16:00; the 16:00 bar runs to 17:00 (1 hour). **1-hour** (A-1H): the source bars. A resampled bar exists if at least one 1-hour bar falls in it; OHLC = first open, max high, min low, last close |
| Daily bars | Built from the same 1-hour bars on the same session (18:00 → 17:00, labelled by the session's end date). Sunday evening joins Monday's session. G1 checks them against the owned `ohlcv-1d` |
| Signal series | **Difference-back-adjusted** continuous from `CL.c.0` (never ratio-adjusted: CL printed negative on 2020-04-20). Roll gap = c.0 vs the previous c.0 on the roll session, as `common/tl_v0_data.back_adjust` does. All indicators, swings and trail levels are computed on this series |
| P&L series | The **actual held contract** (raw `CL.c.0`). A position open over a roll is closed at the last 1-hour close of the old contract and reopened at the first 1-hour open of the new one, **with a full round-trip cost charged**, and its stop moved by the same roll gap so its distance is unchanged |
| Holidays / early closes | The session ends at its last 1-hour bar. Intraday flattening (§2.4) uses that bar, whatever time it is |

### 2.2 Entry (long; short is the mirror image)

| # | Rule | Ben's words |
|---|---|---|
| E1 | **Trigger bar t:** on the close of 4-hour bar t, MACD(12, 26, 9) line crosses **above** its signal line (MACD[t−1] ≤ signal[t−1] and MACD[t] > signal[t]) | *"When MACD crosses above signal line"* · settings *"Standard 12, 26, 9"* |
| E2 | **Confirmation bar c ∈ {t+1, t+2}**: the first of those bars where **EMA9[c] > EMA9[c−1]** (EMA9 rising) **and** \|EMA9[c] − EMA21[c]\| < \|EMA9[c−1] − EMA21[c−1]\| (gap closing), **and** MACD[c] > signal[c] still *(assumed: a cross that has already reversed is no longer a cross)*. If neither bar confirms, the trigger lapses | *"the next candle i can see EMA9 trending upwards and closing gap with EMA21"* · *"Within the next 2 bars"* |
| E3 | **Daily filter, read at c:** the last **completed** daily close (the session that ended at or before bar c's close) is **above both** daily EMA9 and daily EMA21 → longs allowed; **below both** → shorts allowed; **between them** → no trade *(exact form assumed; Ben may veto PRE-RUN)* | *"Daily must agree, weekly as context"* · *"Price vs daily EMAs"* |
| E4 | **Fill:** market at the **open of bar c+1** | — |
| E5 | **One position at a time.** A trigger while in a position is ignored (counted). A new trigger may fire on any bar after the exit bar | Ben does not add: *"No"* |
| E6 | Weekly trend: computed and **reported** per trade (with / against), **never used as a filter** in v0 | *"weekly as context"* |
| E7 | EMAs and MACD are standard exponential (α = 2/(n+1)), seeded on the first n bars' simple average, and need **200 four-hour bars / 60 daily bars of warm-up** before any signal | — |

### 2.3 Stop and trail

| # | Rule | Ben's words |
|---|---|---|
| S1 | **Initial stop:** the most recent **confirmed** 4-hour swing low before the fill, minus 1 tick ($0.01). Swing low = a bar whose low is the lowest of the 2 bars on each side; it becomes known only on the close of the 2nd bar after it (**L = R = 2**) *(assumed number for "obvious turning point")*. If that level is at or above the fill price, use the lowest low of the last 5 completed 4-hour bars minus 1 tick; if that is also at or above the fill, **the trade is voided** (counted, not taken) | *"Beyond last swing"* · *"Obvious turning point"* |
| S2 | **Half-profit trail:** once the highest high since entry reaches **fill + $0.20/bbl**, the stop becomes **max(current stop, fill + (highest high − fill) ÷ 2)**, and is recomputed every time a new highest high is made. It never loosens | *"once it is approximately $2000 in the green… move the stop loss to mid point… always protecting at least 50% of profit"* · confirmed *"$0.20/bbl price move"* |
| S3 | **When the trail is checked (v0):** on each completed 4-hour bar; a new stop takes effect from the next bar. Within a bar the existing stop is tested against the bar's low **before** that bar's high can move it *(the conservative order)* | — |
| S4 | **Fills:** a resting stop fills at the stop price, or at the bar's open if the bar opens through it (gaps, weekends), plus slippage (§2.5). Stops are tested on **1-hour bars** so the time of the exit is known to the hour | — |
| S5 | **No targets.** The stop is the only exit in scenario B; the stop or the 17:00 flat in scenario A | *"I use the trailing stop"* |

### 2.4 The two scenarios (both run on the same entries)

| | **A — Intraday** | **B — Multi-day** |
|---|---|---|
| Entry chart | **2-hour (A-2H, primary)**; A-1H and A-4H reported beside it (Amendment 0) | **4-hour** |
| Held over the 17:00 close? | **No.** Flat at the close of the session's last 1-hour bar (normally 16:00–17:00), at that close plus slippage | **Yes**, overnight and over weekends; gaps fill at the open |
| Entries allowed | Not if the fill bar (c+1) is the session's last bar on the entry chart (16:00 on 1H and 2H, 14:00 on 4H) — too little time, and Ben's rule is to be flat by 17:00. Counted as "blocked: end of session" | Any bar |
| Ben's words | *"close position by end of day due to margin requirements for holding over night"* · *"Flat before CME close"* | *"Once my capital is large enough, i will start holding overnight"* |

### 2.5 Sizing, account, costs

| Element | Registered rule |
|---|---|
| Primary report | **Per 1 MCL and per 1 CL**, in dollars and actual trades (Ben's standing preference) |
| Account view | **$10,000** start, separately for A and B. Fixed whole MCL contracts n = 1, 2, 3, … and 1 CL. **Max size** = the largest n whose worst peak-to-trough drawdown on the training side stays under **$7,000 (70%)**. An account whose equity touches **$3,000** is **ruined**: it stops trading and the date is reported. Ben: *"Assume a $10k account size… both have full account size and can draw up to 70% of account"* |
| Friction | Three levels, per contract per side: **low** = NinjaTrader all-in fee, **Free plan** (amendment A) + 0 ticks = **$1.09 MCL / $2.99 CL**; **mid** = fee + **1 tick** ($1 MCL / $10 CL) on every entry, stop fill, flat and roll leg = **$2.09 MCL / $12.99 CL**; **high** = fee + **2 ticks** = **$3.09 MCL / $22.99 CL**. Mid is the headline |
| Overnight margin (B, reported) | NinjaTrader's listed margins on 2026-09-25 (ninjatrader.com/pricing/margins): **MCL** day $100, initial $884.53, maintenance $804.11; **CL** day $1,000, initial $8,823.20, maintenance $8,021.09. For each n in B's account view: the number of held nights on which n × initial margin exceeded equity (0 = the size could have been held). Reported, not scored; today's figures applied to all years, which is a simplification, stated |
| Amendment A (PRE-RUN, G5) | **Cleared 2026-09-25.** NinjaTrader Free-plan published fees for MCL ($1.09/side all-in) and CL ($2.99/side all-in), read from ninjatrader.com/pricing/commissions/ (page dated 2026-08-14, updated quarterly). Full detail and the itemized breakdown are in Amendment A above |

### 2.6 Variants — fixed now, run beside v0, never ranked

| Variant | Change from v0 | Why |
|---|---|---|
| **v0-TL** | E1–E4 **plus**: within the 6 four-hour bars before t, a 4-hour trend-line break in the trade's direction followed by a retest (a bar whose low comes within 0.25 × ATR(14) of the broken line and closes back beyond it). Lines from `common/tl_v0_lines.py` (L = R = 5), on the back-adjusted 4-hour series | Ben's earlier answers: *"Break, then retest"*, *"Touch + rejection candle"*; later: *"I use trendline as the visual aid"* — so the line is tested as an add-on, not the default |
| **v0-1H** | S2/S3 checked on each completed **1-hour** bar instead of the entry-chart bar (identical to v0 on A-1H, so not run there) | Ben moves the stop by hand during the bar, not only at the bar's close |

**Holdout candidates: v0 on B (4-hour) and v0 on A-2H** (§6). v0-TL, v0-1H, A-1H and A-4H are
reported neighbours and cannot spend the holdout in this registration.

### 2.7 Known departures from how Ben trades — deliberately not coded

Discretion over which setups to take; the visual trend line in v0; the weekly chart as
context; news. His paper size (10 CL on $50,000). Recorded so the result is read as
*the method*, not *Ben*.

---

## 3. What every run must emit (B, A-2H, A-1H, A-4H side by side, every variant)

1. **In dollars and actual trades, per 1 MCL and per 1 CL:** trades, wins/losses, gross, costs,
   **net**, average win, average loss, largest loss, and the worst run of consecutive losses —
   at all three friction levels, mid as the headline. Gross is never the headline.
2. **Every calendar year** of the training side, none omitted.
3. **Both halves**, split at the median trade date of the training side (split, not swept).
4. **Exit reasons:** initial stop / trailed stop / 17:00 flat (A) / data end; share of trades
   where the trail ever started.
5. **Counts:** triggers, lapsed (no confirmation), blocked by the daily filter, blocked
   end-of-session (A), ignored while in position, voided (S1), roll legs, median hold in hours.
6. **Weekly context:** net of trades with vs against the weekly trend (E6), reported only.
7. **Controls, same bars, fills, sizing, costs and both scenarios:**
   - **C1** MACD(12,26,9) cross alone: no EMA confirmation, no daily filter, same stop and trail.
   - **C2** Donchian on the same entry chart: buy a 20-bar high / sell a 20-bar low, exit on the
     opposite 10-bar channel, same flat-by-17:00 rule in A.
   - **C3** Random entries: 1,000 draws, same number of trades and same long/short mix as v0,
     entry bars drawn uniformly from bars where v0 could have been flat, same stop and trail;
     seeds fixed (crc32 of draw number). Report the p5 / p50 / p95 of net.
8. **Neighbour grid (reported, unranked):** trail trigger ∈ {$0.10, $0.20, $0.40}, confirmation
   window ∈ {1, 2, 3} bars, swing size L = R ∈ {2, 3} — 18 cells per scenario, net at mid
   friction, and the share of cells that are net positive.
9. **Account view (§2.5):** equity curve and worst drawdown in $ for n = 1 … max size + 1 MCL
   and for 1 CL; max size; ruin date if any; for B, the overnight-margin count per n.
10. **20 sample trades** per scenario (every 1/20th of the list, not the best): entry and exit
    time (New York), side, fill, stop, exit, exit reason, net $ per MCL.
11. **Coverage in the same pass:** bars per year, gaps, roll dates, first and last bar.

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — v0, per scenario, 1 MCL, mid friction, training side

Scored for **B (4-hour)** and **A-2H**. A-1H and A-4H are scored against the same bar and
reported, but cannot spend the holdout. A scenario **passes** only if all of these hold:

1. **Net > $0.**
2. **Both halves net > $0.**
3. **No single calendar year supplies more than 50% of net.**
4. **Bootstrap by calendar year** (2,000 resamples, seeded): total net > 0 in **≥ 95%**.
5. **Beats C1 and C2** on net.
6. **Beats the p95 of C3** (random entries) on net.
7. **Still net > $0 at high friction.**
8. **At least 12 of the 18 neighbour cells (§3.8) are net > $0.** A spec that works only at its
   own settings is fitted, not found.
9. **At least 150 trades** on the training side. Fewer → **NOT READ**, not failed.

B and A-2H are scored separately and reported side by side. A scenario that fails
criterion 5 is closed, whatever else passes: the added rules would not be earning their place.

Account view (§2.5) is **reported, not scored** — Ben chooses the live size after seeing it.

---

## 5. Before the backtest — no P&L anywhere in this section

### 5.1 G1 data read-back

Bars per year; first and last bar; hours missing inside sessions (excluding the 17:00–18:00
break and weekends) listed if > 3 in a row; roll sessions from `CL.c.0` symbol changes; the
rebuilt daily close vs owned `ohlcv-1d` `CL.c.0` close, share within $0.05 and every miss.
**Stop rule:** below 99% agreement, the study stops until the mismatch is explained.

### 5.2 G2 pre-flight (training side only: 2010-06-06 → 2021-12-31)

For v0, v0-TL, v0-1H and C1, on B, A-2H, A-1H and A-4H, per year: triggers, confirmations,
daily-filter blocks, end-of-session blocks (A), voided; the **initial stop distance** at entry
in $ per MCL and per CL (median, p90, max); for A, the median hours left before 17:00 at entry. It reads **no exit prices** and computes **no P&L**; the runner refuses to in this mode.

**Stop rule (registered now):** if v0 has **fewer than 150 entries** on the training side in
**both** B and A-2H, the study stops as underpowered, reported as the finding.

---

## 6. The holdout

**2022-01-01 onward is locked** (training = 2010-06-06 → 2021-12-31, the same cut as TSMOM and
TL-v0), with **its own cut file and ledger** (`holdout_htf_ben.json`); the TSMOM, TL-v0, H60 and
equity holdout files are refused by name. **Spent once, by v0, B (4-hour) and A-2H together in
that one spend, 1 MCL, mid friction, the same nine criteria.** Refuses `--limit` and every
narrowing flag; a mutation-checked test asserts each refusal fires.

### 6.1 Ben's own trades sit inside the holdout

Ben's NinjaTrader paper trades (September 2026) fall in the locked window. W15-0005 may read
**signal timing only** for those weeks: same bar, same side, same initial stop, same exit bar.
It computes **no P&L** for the window and reads nothing outside the days of his trades. A
mismatch can lead to only two things: (a) fixing code that disagrees with the rules as written
here, recorded as a POST-RUN bug-fix note; or (b) a new registered variant that spends from §9.
Never a silent change to a rule.

---

## 7. Registered as NOT to be done

- Tuning any parameter to Ben's paper trades, or to anything in 2022+.
- Swapping a neighbour cell (§3.8) or a variant in for v0 after a result.
- Quoting the 1 CL or 10 CL figures as the result; per-MCL at mid friction is the headline.
- Quoting gross.
- Adding the weekly filter, targets, news or setup selection as "improvements" after a result.
  Each is a new registration.
- Reporting P&L from the back-adjusted series.
- Reading any 1-hour bar before G1's module exists and this file is committed.

---

## 8. Ways this could go wrong, given this project's history

- **Bar-start vs bar-end.** Databento stamps the start. A 4-hour bar labelled 18:00 closes at
  22:00; a signal on it can be traded at the 22:00 open, not the 18:00 one. Test pins it.
- **The daily filter peeking** at the session still forming. The daily close used at bar c must
  come from a session that ended at or before c's close. Test: a daily close that flips after
  c's close must not change the decision at c.
- **Swings known too early.** A swing low is usable only from its 2nd right-hand bar's close.
  Test with a one-bar shift, as TL-v0's G5.
- **The trail seeing the bar that stops it out.** S3's order is tested with a bar whose low hits
  the old stop and whose high would have raised it.
- **Roll gaps read as signals.** Indicators run on the back-adjusted series; the pre-flight
  counts triggers within one session of a roll as a diagnostic.
- **2020-04-20.** CL.c.0 (May 2020) settled at −$37.63. The back-adjusted series stays
  continuous; the held-contract P&L is booked as it happened. Reported, not excluded.
- **Daylight saving.** Resampling in UTC with a fixed offset puts one of the six bars an hour
  wrong for half the year. Resample in America/New_York; a test crosses a DST change.
- **A guard that cannot fail.** Every guard is mutation-tested before commit.

---

## 9. Multiplicity budget

Families: **variant** (v0 / v0-TL / v0-1H, fixed, holdout candidate named), **scenario**
(A / B, both pre-named, one holdout spend), **intraday chart** (2H primary; 1H and 4H reported,
fixed by Amendment 0 before any bar was read), **friction** (not a search), **neighbour grid**
(reported only, criterion 8 uses it as a robustness check, never as a menu). Budget: **two
further registered hypotheses** on this line before it closes (e.g. the weekly filter as a hard
rule, or a different trail). A third needs a reason that doesn't begin with a result.

---

## 10. A prediction, written down now

**The intraday versions lose after costs, A-1H most, A-4H nearly as much, A-2H least.** On
1-hour bars the moves are small against costs; on 4-hour bars there is no time before 17:00;
2-hour is the least bad but still negative at mid friction. **Scenario B (multi-day) is
positive gross and roughly flat to slightly positive at mid friction**, fails criterion 5 (C2
Donchian does about as well), and makes most of its money in two or three trending years (2014,
2020). The daily filter helps a little; the EMA confirmation does almost nothing over C1. If
that is what happens, the reading is: *the method is ordinary trend following on crude; what
made Ben's paper account grow was size and a trending month, not the rules.* I would be glad to
be wrong.

---

## Next steps (board)

- **W15-0002** — price, then pull CL `ohlcv-1h` (`python -m strategy.htf.fetch`), then G1.
- **W15-0004** — G2–G5, then the run. Build & test chat, Sonnet · Medium; runs on Ben's PC.
- **W15-0005** — fidelity replay (§6.1), when Ben's trades are available.
