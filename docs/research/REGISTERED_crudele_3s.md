# REGISTERED — CRUDELE-3S: Anthony Crudele's Bollinger 3-state regime system, coded, on CME futures, daily

**Written before any CRUDELE-3S code exists and before any bar of any market has been read for this
study.** `PROGRAM_INDEX` §1 says a hypothesis is registered before it is run.

Board: **W15-0022** (registration), subitem 5 (build + count-only pre-flight), later subitems
(backtest, Result doc). Source: Chart Fanatics video `EZ_L7zovyrw` (46 min), read in full
2026-09-29. Extract: `claude/raw/w15_0022_crudele_extract_20260929.txt`, with quotes, timestamps
and STATED/VAGUE tags. First screened in `claude/w05_0020_chart_fanatics_review_RESULT_20260927.md`
(option C).

Ben's decision, 2026-09-29, in his words: *"Standalone 3-state system"*. All three of Crudele's
modes are coded as a new method of their own. It is not an HTF-Ben variant, because that line was
closed after v2 (W15-0021), and it is not merged into the Dalton gate (W15-0025).

Amendments are marked **PRE-RUN** or **POST-RUN**. If a rule or threshold is changed after a result
has been seen, that is a new hypothesis, and it spends from §9.

---

## 0. Where this sits

- **New line, new budget.** No earlier registration covers this method, and it inherits nothing
  from HTF-Ben, TL or TL-bounce except the program plumbing listed in §2.1.
- **What he gave, and what we chose.** Crudele is a discretionary index-futures swing trader. He
  states the skeleton: Bollinger 20 / 3 SD on **daily** bars, and three exclusive states (two-way
  "consolidation", one-way "trend", counter-trend "mean reversion"). He also states the
  mean-reversion trade exactly: a Fib drawn on the bands, entry on a daily close beyond 30%, target
  50%, exit on a daily close back beyond 30%, small size. He gives **no numbers** for when the
  bands are "flat" or "expanding", for the consolidation edges, or for trend stops and exits.
  Every such number below is **our coding**, fixed here before any data is read, and is marked
  **(choice)**. Ben reviews the list of choices in §11 before build.
- **Fib anchors are his.** His indicator ("Beacon", open source on TradingView,
  script `av4XyaCS`) describes its levels as "a retracement from the peak high of the BB to the
  peak low", at 70% / 50% / 30%. So the Fib is drawn on **band values**, from the upper band's
  peak to the lower band's trough, not on price. §2.5 codes exactly that.
- **Scope extension, stated plainly.** He trades ES / NQ / RTY on daily bars only. Running the
  method on 12 diversified markets is our extension, and so is the CL 4-hour variant. His
  3 SD setting was chosen for index volatility. §2.7 reports the index-only slice separately.
- **What has been seen.** Only the video. No bar of any market has been read by this study.

---

## 1. The hypothesis, in one sentence

**Classifying each market every day into consolidation, trend or mean reversion by Bollinger(20,
3 SD) band width and band peaks, then trading only that state's setup, makes money after measured
costs on the owned GLBX daily history of the TSMOM markets. The setups are: range-edge fades in
consolidation; one direction only in a trend, entered on the breakout; and a small counter-trend
fade from the Fib 30% line to 50% after the bands come back in. It also beats a 20/10 Donchian
channel on the same markets, sizing and costs, and beats random entries matched on count, side,
arm and holding time.**

---

## 2. The rules

### 2.1 Program plumbing, inherited unchanged (from TL-v0 / TL-v1)

These are the same as TL-v1: the execution chart is **daily**; the markets are the TSMOM archive
roots (ES, RTY, CL, NG, 6A, 6B, 6E, 6J, GC, SI, HG, MTN). Signals run on the difference-back-adjusted
series, and P&L is taken on the held contract with the TSMOM roll rule, including Amendment C.
ATR(14) is Wilder's. Fills are at the stated level, or at the open if price gaps through it. When a
stop and a target fall in the same bar, the stop is assumed to have been hit first. Friction is
**$0.50 / $1.25 / $2.50** per contract per side, plus one tick on every stop fill. Sizing is by
risk fraction, **zero contracts = skip, counted**, and the verdict is read on the fractional book at
**$22,129**, with the whole-contract (integer) book reported beside it. One position per market at a
time.

Difference back-adjustment leaves price *differences* unchanged, so band width in points (below) is
the same as the held contract's width.

### 2.2 Indicators (computed at the close of bar t, used from bar t + 1)

| Symbol | Definition | Source |
|---|---|---|
| M, U, L | SMA(20) of close; U/L = M ± **3.0** × population SD(20) of close | **STATED** ("20 period three standard deviation") |
| BW | U − L, in points | (choice) |
| BWR | percentile rank of BW[t] among BW over the last **250** bars (0–1) | (choice) |
| SMA8 | SMA(8) of close | his 8/21/34 "help me with exits"; SMA type is our choice |

### 2.3 The state machine

At each close there is exactly one state per market. The states are checked in this priority
order: **MR > T > C > N**. This order is our choice; he implies that mean reversion overrides trend
("I no longer want to be long") and that an unclear state means flat ("hands in the pocket").

| State | Enters when (at close t) | Leaves when |
|---|---|---|
| **C — consolidation** | Squeeze: BWR ≤ **0.25** on at least **5 of the last 10** bars, and the market is not in T or MR (choice). Range box: **R_hi / R_lo = highest high / lowest low of the last 20 bars**, frozen at the bar C is entered and extended while C lasts (choice; he draws the box through the recent highs and lows) | T fires, or squeeze lost (fewer than 5 of 10) → N |
| **T — trend, long** (short = mirror) | While in C, or within **5 bars** of leaving it: BW has risen on each of the last **3** bars, **and** U[t] > U[t−1], **and** close[t] > R_hi (close-through). **STATED:** "bands go from flat, start pointing outward… takes out these previous highs… long only. Period." The counts and the close-through test are our choice | Bands come in (below) → MR-armed; or T times out after **60** bars with no band peak (choice) → N |
| **Band peak / "bands come in"** | In T: track **U\* = max U** and **L\* = min L** since T began. The bands come in when BW falls on **2 consecutive** bars (choice) | — |
| **MR — mean reversion, short after a long trend** (long after a short trend = mirror) | The bands have come in; the Fib is frozen on U\*, L\* (§2.5); armed for **20 bars** (choice) | Trade done, 20 bars pass, or a new T fires → N / T |
| **N — none** | Anything else | — |

### 2.4 The three setups

**T setup: trend, one direction only.**
- Entry: at the **open of t + 1** after T fires. He gives no entry rule, but says a programmed
  version "would trigger a buy right here with a stop below this recent swing low" (44:54), and this
  codes that.
- Initial stop: **R_lo − 1 tick**, the consolidation low, which is his "recent swing low" (choice).
- Target: the **previous band-peak price extreme**. That is the high of the bar on which U\* was set
  in the most recent completed T-long episode in this market; the mirror applies for shorts. It is
  used only if it lies above the fill; otherwise there is no target. **STATED** as a concept
  ("that previous peak becomes a target"); the price-vs-band choice is ours.
- Exit, whichever comes first: the stop, the target, the **first close below SMA8** (next open)
  (his "couldn't hold the 8-day moving average… closes below it"; SMA type is our choice), or
  **bands come in** (next open) ("I'm no longer long").
- One trade per T episode (choice).
- Risk: **1%**.

**MR setup: counter-trend, small.**
- The Fib is on band values: **H = U\* − L\***. After a long trend, the levels are measured down
  from U\*: **line30 = U\* − 0.30 H**, **line50 = U\* − 0.50 H**, and line0 = U\*. The mirror
  applies after a short trend, measured up from L\*. **STATED** ("a fib on volatility", "from the
  peak high of the BB to the peak low", 30 / 50 / 70).
- Entry: the **daily close crosses line30** (close < line30 after a long trend) → enter at the next
  open. **STATED** ("once we get a daily close below 30%").
- Target: **line50**, as a limit order. **STATED** ("once it hits 50%, I'm done").
- Exit on a **daily close back beyond line30**, at the next open. **STATED** ("once a daily closes
  above there, I no longer want to be in it").
- Hard protective stop at **line0 (U\*)**, which also sets the size. This is our choice: he uses
  only the close rule, but a stop is needed to define risk and to cap gaps.
- Time stop: **10 bars** (choice; his hold is 1–5 days).
- Risk: **0.5%**. **STATED** "short small"; the 0.5 multiple is our choice.
- After line50 is hit or the trade exits, the market goes to N: "hands in the pocket. We got to wait."

**C setup: range-edge fade (coder extension; he says he mostly stays out).**
- Trigger: a **stop-run** on bar t, meaning high[t] > R_hi and close[t] < R_hi → short at the next
  open. The mirror (low below R_lo, close back inside) → long. **STATED** as a concept ("stop runs
  above recent highs or lows and just come back into the range"); the bar test is our choice.
- Stop: the extreme of the poke bar **+ 0.10 × ATR**.
- Target: **M**, the middle band, taken at the limit level current when each bar opens (choice;
  "stay out of the middle").
- Time stop: **5 bars** (choice).
- Risk: **1%**.
- If T fires while a C trade is open, the C trade exits at the next open.

**Not coded (known departures):** his intraday refinements (60 / 30 / 3-min); options instead of
futures; the VIX / macro size cut (we don't own VIX, so it is not coded); RSI as confirmation;
anchored VWAP and others' levels as targets; scaling out; discretion on "in-between" phases.

### 2.5 Fib check (G6)

The Beacon Pine source is to be read by the Build & test chat and compared with §2.4's Fib: the
same anchors (upper-band peak to lower-band trough) and the same 30 / 50 / 70 levels. If Beacon
differs in how it finds the peaks (for example a pivot lookback on the band), that difference is
**written in here as a PRE-RUN amendment before the pre-flight**, choosing one coding and reporting
the other as a variant. This check needs the source only, not data.

### 2.6 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | What it tells us |
|---|---|---|
| Each arm alone (T only, MR only, C only) | the other arms switched off | which arm earns, or loses, the money |
| No-C | T and MR only | the system without our extension arm |
| T without squeeze | T fires on any 3-bar expansion plus a close-through of the 20-bar high, with no prior C | whether the "from flat" condition matters |
| SD 2.5 | bands at 2.5 SD, and every threshold recomputed the same way | the SD choice outside indexes |
| Index slice | ES and RTY only | his stated scope (NQ is not in the archive) |
| **CL 4-hour** | CL only, 4-hour bars from `ohlcv-1h` on the 18:00 New York session (as `REGISTERED_tl_bounce.md` §2.1), same rules in bars; costs as HTF-Ben v0 Amendment A, per 1 MCL | Ben's market, on a shorter chart |

---

## 3. What every run must emit

In dollars and actual trades, for the system and every §2.6 variant, at all three friction levels,
with mid friction as the headline:
1. Trades, wins / losses, gross, costs, net, average win, average loss, largest loss, worst run of
   losses, for the fractional book (the verdict) and the integer book.
2. Per market, per calendar year, and both halves split at the median entry date.
3. **By arm (T / MR / C) and by side.**
4. Exit reasons per arm (stop / target / SMA8 / bands-in / close-back-beyond-30 / time), and the
   median hold in bars.
5. **Counts:** bars in each state per market per year; state transitions; T episodes; T episodes
   with no usable target; MR arms; MR arms that trigger; C stop-runs; skipped for size.
6. **Controls (same markets, bars, sizing, costs):**
   - **C1:** Donchian 20/10, as TL-v0.
   - **C2: random entries matched to CRUDELE-3S's own trades.** For each market and year, the same
     number of trades per arm and side, on random bars, each held for the same number of bars as a
     randomly chosen real trade of that arm, with the same risk fraction and a stop at the same ATR
     distance. 1,000 seeded draws (crc32 of the draw number). Report p5 / p50 / p95 of net.
7. **Neighbour grid (27 cells, unranked):** squeeze BWR threshold {0.20, 0.25, 0.33} × expansion
   bars {2, 3, 4} × trend exit MA {SMA8, SMA21, SMA34}. Report net at mid friction per cell and the
   share of cells positive.
8. **20 sample trades** (every 1/20th of the list), with state, arm, fill, stop, target, exit and
   net $.
9. **Seen window** (2025-09-23 → end of data), labelled "seen — not evidence".

**Nothing is ranked, and there is no "best cell" table.**

---

## 4. The bar to clear: CRUDELE-3S, all three arms, daily, 12 markets, mid friction, training side

It passes only if all of these hold:

1. Net > $0 at mid friction ($1.25 / side).
2. Both halves net > $0.
3. Dropping the top 1 and the top 2 markets still leaves net > $0.
4. Bootstrap by market and by calendar year (2,000 seeded resamples each): net > 0 in ≥ 95% of
   resamples, for each.
5. **Beats C1 (Donchian)** on net and on net per unit of realised volatility.
6. **Beats the p95 of C2** (matched random entries) on net.
7. No single year and no single market supplies more than 50% of net.
8. Still net > $0 at high friction ($2.50 / side).
9. At least **18 of 27** neighbour cells net > $0.
10. At least **150 trades**. Fewer means NOT READ, not failed.

**Failing criterion 5 or 6 closes the study, whatever else passes.** The per-arm results are
reported and not scored: the hypothesis is the whole 3-state system.

---

## 5. Before the backtest (no P&L in this section)

### 5.1 Gates

| # | Gate | Why |
|---|---|---|
| G1 | Data: the TL-v0 daily archive; CL 1-hour for the 4-hour variant (HTF-Ben v0 G1, passed). No new data | Same bars |
| G2 | Pre-flight (5.2) run and read | Enough trades in each arm? |
| G3 | Holdout (§6) cut and ledger in code, mutation-tested | `PROGRAM_INDEX` §1 |
| G4 | Look-ahead guards, each broken by a one-bar shift in a test: BWR uses bars ≤ t; U\*/L\* and the Fib use only closed bars; MR levels are frozen at "bands come in" and never move afterwards; R_hi / R_lo use bars ≤ t; the target uses a *completed* earlier T episode only | His examples are drawn on finished charts |
| G5 | State-machine unit tests on synthetic bars: one hand-built path through C → T → MR → N, and its mirror, with every transition at the bar expected | New logic |
| G6 | Beacon source read (§2.5); any difference written in PRE-RUN | Anchors are his |

### 5.2 G2 pre-flight (training side only: 2010-06 → 2021-12)

Per market per year: the share of bars in each state; T episodes; MR arms and triggers; C
stop-runs; entries by arm and side; initial stop distance in $ per micro where a micro exists,
otherwise per full contract; and the share of signals sizeable at 0.5%, 1% and 2% of $22,129. **The
runner refuses to read any exit price or compute any P&L in this mode.**

**Stop rules, fixed now:**
- Fewer than **150 entries** in total → stop as underpowered, report that as the finding, and go
  back to Ben before any P&L.
- Any one arm with fewer than **30 entries** is reported as "too few to read" in the per-arm table
  (this does not stop the study).

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31.
- **Holdout:** 2022-01-03 → 2025-09-22, with its own cut file and ledger,
  **`holdout_crudele_3s.json`**. It is **spent once**, by the system (daily, 12 markets, mid
  friction, the ten criteria). The code refuses `--limit` and every narrowing flag, and this is
  mutation-tested. Every other line's holdout file is refused by name.
- **Seen window:** 2025-09-23 onward. It is reported only and never scored.

---

## 7. Registered as NOT to be done

- Tuning any threshold (BWR, the 5-of-10 count, expansion bars, the 60 / 20 / 10 / 5-bar clocks,
  Fib levels, SMA length, risk fractions) to a result.
- Substituting a variant, an arm or a grid cell for the system after a result.
- Quoting gross, a single arm, the index slice or the 4-hour variant as the headline.
- Adding VIX, RSI, VWAP or scale-outs after a result.

---

## 8. Ways this could go wrong

- **"Flat" and "expanding" are ours, not his.** The result tests our reading of his eye. The
  27-cell grid shows how much that reading matters.
- **The trend arm is close to a breakout system.** C1 (Donchian) is the right bar for it; the
  variant "T without squeeze" shows whether "from flat" adds anything.
- **The MR arm has a poor payoff on futures, and he says so himself.** He buys options instead
  because the futures stop is too wide for the 50% target (43:22). The hard stop at line0 makes
  that visible rather than hiding it.
- **The C arm is our extension.** He says he gets "chopped up" there. It is reported alone, and the
  No-C variant shows the system without it.
- **3 SD outside indexes.** On NG or SI, 3 SD bands may seldom squeeze or expand the way they do on
  ES. The index slice and the SD 2.5 variant show this; neither can replace the headline.
- **Rolls:** difference back-adjustment keeps widths exact, but a roll-day gap can look like a
  stop-run. The existing roll-leg guards apply unchanged.

---

## 9. Multiplicity budget

The families are: the system (one fixed rule set, with its arms and variants reported), the grid
(robustness only), and friction (not a search). There is one holdout spend. **Two further registered
hypotheses** are allowed on this line; a third needs a reason that does not begin with a result.

---

## 10. A prediction, written down now

**CRUDELE-3S nets about zero on the training side and fails criterion 5.** The trend arm behaves
like a slower, pickier Donchian breakout: fewer trades and similar net per trade, so it doesn't beat
Donchian. The MR arm has a high win rate but a poor payoff after the line0 stop, and roughly breaks
even. The C arm loses money after costs, as he warns. The index slice looks better than the other
markets. If that is what happens, the reading is: *his three states describe markets well, but the
edge he gets is in the discretion and the options structure, not in the state rules.* I'd be glad to
be wrong.

---

## 11. For Ben's review before build (the choices that matter most)

1. **Squeeze = BW in its lowest 25% of the last 250 bars, on at least 5 of the last 10 bars.**
2. **Trend start = BW rising for 3 bars, the upper (or lower) band rising, and a close beyond the
   20-bar range high (or low).**
3. **Trend exit = first close below SMA8**, or the bands coming in, or the stop at the range low, or
   the previous band-peak high as a target.
4. **MR = the Fib on the band peak and trough; enter on a close through 30%, target 50%, exit on a
   close back through 30%, hard stop at the band peak, 0.5% risk.**
5. **Our consolidation arm (stop-run fade to the middle band) is included in the system.** The
   alternative is to register T + MR only, with C reported.
6. **Headline = 12 markets daily.** ES + RTY and CL 4H are reported only.

---

## Next steps (board, W15-0022)

- **Subitem 4:** Ben reviews §11 (and BREIT-CAP §11) → "go", or changes written in PRE-RUN.
- **Subitem 5:** build (state machine, three arms, controls, grid, guards, holdout) plus the
  count-only pre-flight. Build & test chat, Sonnet · High; runs on Ben's PC.
- Backtest and Result doc: new items after G2 is read.


---

## 12. Amendments

### Amendment A — PRE-RUN, 2026-09-29, gate G6 (Beacon source read)

**Written before any bar of any market has been read and before any pre-flight.** It is the G6 / §2.5 write-up.
Source read: TradingView script `av4XyaCS` (Pine v4, defaults length 20 / SD 3), saved unchanged as
`claude/raw/w15_0022_beacon_source_20260929.pine`.

**What Beacon does.**
- Minor peak = a local maximum of the upper band, `U[1] > U[2]` and `U < U[1]`, taking the value `U[1]`
  (confirmed one bar late, so nothing looks ahead). Minor valley = the mirror on the lower band.
- Major peak / valley = a running pair. A minor peak above the previous major peak becomes the major
  peak; a minor valley below the previous major valley becomes the major valley. When a new extreme
  forms on one side, the *other* side is reset to its latest minor value.
- Lines: `line_70 = valley + 0.7 H`, `line_50` = midpoint, `line_30 = valley + 0.3 H`, with H = major
  peak − major valley. The Fib is on **band values**, as §0 and §2.4 say.

**Where it agrees with §2.4.** Band values, not price; the anchors are the upper-band peak and the
lower-band trough; levels at 30 / 50 / 70. Bollinger 20 / 3 SD with a population SD.

**Where it differs, and what is decided.**
1. **Labelling, not a rule.** Beacon counts levels *up from the valley*. §2.4 counts *down from the
   peak* after an up-trend. So §2.4's `line30 = U* − 0.30 H` is Beacon's **"70 Line"**, §2.4's `line50`
   is Beacon's "50 Line", and §2.4's `line0` is Beacon's peak. Crudele's spoken "close below 30%, target
   50%" for a short after an up-trend is only consistent with §2.4's orientation (Beacon's "30 Line"
   sits below the 50 line, so a short whose target is the 50 line would have to trade *up*). No change.
2. **Anchors.** Beacon's peak and valley are always-on pivot anchors on the band history, with the
   cross-reset above. §2.3 / §2.4 anchor on `U*` = max U and `L*` = min L **since the T episode began**,
   frozen when the bands come in. These can differ (for example, Beacon's peak can be a lower minor peak
   after a new valley forms).

**Decision (made before any data, without reference to any result).** The **primary is unchanged**:
`U* / L*` since T began, frozen at "bands come in". Reason: Ben approved §11 as drafted; the MR arm is
defined as *the fade after a T episode*, and Beacon's pair has no notion of a T episode, so adopting it
as the primary would mean re-registering how the arm is armed. The Beacon coding is added as a reported
variant instead, which §2.5 allows.

**New reported variant (added to §2.6, never ranked, cannot spend the holdout): "MR-Beacon".**
Same arming trigger as the primary (a completed T episode, then the bands come in). At the bar the
bands come in, the Fib anchors are Beacon's **major peak and major valley as of that close**, computed
from the band history of that market with the exact rules above (initial values as in the Pine source;
segment start = first bar with a full 20-bar window). H = peak − valley, and everything else is as
§2.4 (entry on a close through the 30% line counted down from the peak, target 50%, close-back exit, hard
stop at the peak, 10-bar time stop, 0.5% risk). If H is not positive, or the Beacon peak is not above the
current close, the arm is skipped and counted. Nothing else in the study changes.

**Test added to G4.** The Beacon pair is coded once, from the Pine semantics above, and one-bar-shift
guarded like the other indicators.

### Amendment B — PRE-RUN, 2026-09-29 (readings made while coding; before any pre-flight or P&L is read)
These are clarifications of how ambiguous wording was coded. None was chosen by looking at data (none has been run).
1. **MR trigger on the arm close.** The MR arm arms at the bar the bands come in and may trigger on a close through the 30% line from that bar onward, so a trigger can fire almost immediately after "bands in". Coded literally; the pre-flight reports MR arms, triggers and expiries so Ben can see how often this happens. Not changed after seeing counts unless re-registered.
2. **State priority MR > T > C > N**, exclusive, one state per bar.
3. **Population SD (ddof=0)** for the Bollinger bands, matching Pine.
4. **T target = earlier-episode target only when it lies beyond the fill**; otherwise no target (counted as "T signals with no target").
5. **Risk per trade**: T 1%, MR 0.5%, C 1% of the $22,129 fractional book; one position per market.
6. **Look-ahead (G4)** is tested by truncation invariance and mutation-tested.

### Amendment C — PRE-RUN, 2026-09-30 (W15-0033 cost basis; W15-0034 report readings; before any P&L is read)

Reason: Ben's instruction to use IBKR costs, and the wording of §4 that admits more than one reading. Neither follows a result: the G2 pre-flight read no exit price and no P&L (1,356 entries).

**Costs — IBKR (W15-0033), replacing the flat $0.50 / $1.25 / $2.50 per side.** Ben, 2026-09-30: *"please use the IBKR costs as that will be the broker i'm using"*; levels chosen by Ben (multiple choice, same day): **fee + 0 / 1 / 2 ticks per side**. Per contract per side, all-in = IBKR Pro commission (Fixed, or Tiered ≤ 1,000 contracts a month) + exchange fee (non-member) + regulatory ≈ $0.02, read 2026-09-30 from interactivebrokers.com (`/en/pricing/commissions-futures.php`, `/en/accounts/fees/{CME,CBOT,COMEX,NYMEX}.php`):

| Vehicle | Commission | Exchange | All-in / side | Tick $ | low / mid / high per side |
|---|---|---|---|---|---|
| MES (ES) | 0.25 | 0.353 | **0.62** | 1.25 | 0.62 / 1.87 / 3.12 |
| M2K (RTY) | 0.25 | 0.353 | **0.62** | 0.50 | 0.62 / 1.12 / 1.62 |
| MCL (CL; also CL 4H) | 0.25 | 0.50 | **0.77** | 1.00 | 0.77 / 1.77 / 2.77 |
| NG (full) | 0.85 | 1.60 | **2.47** | 10.00 | 2.47 / 12.47 / 22.47 |
| M6A, M6E, M6B | 0.25 | 0.24 | **0.51** | 1.00 / 1.25 / 0.625 | 0.51 / 1.51 / 2.51; 0.51 / 1.76 / 3.01; 0.51 / 1.135 / 1.76 |
| 6J (full) | 0.85 | 1.60 | **2.47** | 6.25 | 2.47 / 8.72 / 14.97 |
| MGC (GC) | 0.25 | 0.70 | **0.97** | 1.00 | 0.97 / 1.97 / 2.97 |
| SIL (SI) | 0.25 | 0.70 **(assumed)** | **0.97** | 5.00 | 0.97 / 5.97 / 10.97 |
| MHG (HG) | 0.25 | 0.70 | **0.97** | 1.25 | 0.97 / 2.22 / 3.47 |
| MTN | 0.25 | 0.30 | **0.57** | 1.5625 | 0.57 / 2.13 / 3.69 |

SIL is not on IBKR's COMEX fee page; its exchange fee is assumed equal to the other COMEX micros (flagged in every report). Slippage is inside the mid and high levels on **every** fill, so the old separate "1 tick on stop fills" is dropped (no double count). Roll legs: two sides per contract, as before. MCL round trip $1.54 / $3.54 / $5.54, as the CHARTMARK registrations. Wherever this file says "$1.25 / side" (mid) or "$2.50 / side" (high) it now means these levels. Code: `strategy/futbt/costs_ibkr.py`. **PRE-RUN check (G5):** if Ben's first IBKR futures fills show a different all-in fee, it is amended here before any P&L is read.

**Coding notes for §4 wording (fixed now, before any P&L):** criterion 2 splits at the median ENTRY date of the verdict book's trades (each half = sum of net at mid of the trades that entered in it; an empty half fails); criterion 4 uses TL-v0's `cluster_boot` (2,000 resamples, seed 20260927); criterion 5 is net AND net per unit of realised volatility (TL-v0's measure); criterion 7 is NOT READ when net ≤ 0; criterion 9 counts grid cells with net > $0 at mid (the grid is the fractional book at $22,129); criterion 10 NOT READ under 150 trades. The report layer is `strategy/futbt/report_common.py`; the backtest runners are `strategy.crudele_3s.backtest` and `strategy.breit_cap.backtest` (training side only; `--holdout`, `--limit`, `--seen`, `--spend` are refused).

**CRUDELE-specific:** C2's matched random entries and the CL 4H reported variant are priced on the same IBKR levels (CL 4H as one MCL). The CL 4H variant stays reported-only.
