> **ARCHIVED 2026-09-08.** E15 is dormant: spec only, no code, and VW9's result lowered the prior considerably.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

# E15 — 15-minute EMA pullback strategy, full session (04:00–20:00 ET)

Spec written 2026-09-03. **Code not yet written.** Source of the rules:
`youtube.com/watch?v=b3QPY08kxOc` (Trading Data, 25 Jul 2026), adapted to the
MCL universe and to this repo's conventions.

Decisions taken by Ben before drafting:

| | |
|---|---|
| Universe | Same small-cap runners as MCL — $2–$20, RVOL(1D) ≥ 5×, float < 20m, top-2 pre-market gainer |
| Direction | **Long only** |
| Timeframe | 15-minute |
| Session | 04:00–20:00 ET, continuous |
| EMA continuity | One continuous series across the whole day, reset each session |
| Deliverable | This spec first; Python module after review |

---

## 0. Read this before anything else — the warm-up problem

**A 9/20 EMA on 15-minute bars cannot produce a signal before ~09:00 ET, and
cannot produce a completed setup before ~10:30 ET. On this universe that removes
the entire window where the edge has so far been measured.**

The arithmetic is not arguable:

```
04:00 ET  bar 1 opens
          15 min per bar, 64 bars in a 04:00–20:00 session
09:00 ET  bar 20 closes  ← first bar at which EMA20 is defined at all
```

Add the sequence the strategy requires after that first defined EMA20 —
a crossover, 2–3 bars of slope-and-separation confirmation, an impulse leg, a
pullback of 2–8 bars, then a trigger bar — and the earliest plausible entry is
**10:00–10:30 ET**, with the realistic median later still.

Against that, `claude/momentum_confluence_session_window_test.md` found that
moving the MCL window from 04:00–09:30 to 06:30–09:30 took net P/L from **+$924
to +$66** — 93% of the profit lived in **04:00–06:30**. E15 cannot trade that
window. Not "trades it poorly": cannot see it.

So the honest framing is that **the request was for a full-day strategy and what
this specification can actually deliver is an RTH-and-later strategy**, on a
universe whose demonstrated behaviour is a pre-market catalyst move. That is a
finding, not a blocker — it is worth testing precisely because it is a different
part of the day from everything tested so far, and because 10:00–20:00 has a
functioning book where the fill assumptions are believable for the first time in
this project. But it should not be built under the belief that it covers
04:00–09:30.

### Three ways to reach earlier, and why each is rejected as the default

| Option | Effect | Verdict |
|---|---|---|
| **Seed EMAs from the prior session's 15m bars** | EMA20 defined from bar 1 | **Rejected.** These names gap 100–800% on the qualifying day. A prior-day EMA20 sits far below the open, so EMA9 starts already above it — the crossover has effectively happened off-chart and never fires again, or fires once at 04:00 on a stale reference. Several names also have near-zero prior-day liquidity, so the seed is built from 2–3 real bars. |
| **Shorten the EMAs to fit the window** (e.g. 5/13) | First signal ~07:15 ET | **Rejected as default.** Defensible, but it is no longer this strategy, and there is no basis yet for those lengths. Keep as a variant to test *after* the 9/20 baseline exists. |
| **Run 9/20 on 5-minute bars** | First signal ~05:40 ET | **Rejected here.** That is MC5's timeframe and would be a change to MC5, not a new strategy. Worth doing separately. |

**Default: no seeding. EMAs start from the first bar of the session and the
strategy simply has no opinion before ~09:00 ET.** Build it with
`WARMUP_MODE` as a parameter (`none` | `prior_session` | `continuous`) so the
alternatives can be measured rather than argued about.

### The 1-hour trend filter is dropped

The source specifies that 15-minute setups should only be taken in the direction
of the 1-hour trend. A 9/20 EMA on 1-hour bars needs 20 hours of data —
approximately 80 fifteen-minute bars, more than a full 64-bar session. It is not
computable on a single-session series. Approximating it in-session
(e.g. 36/80 EMA on 15m bars) has the same problem.

**The filter is therefore not implemented.** Recorded here as a known deviation
from the source, and as a reason to expect more marginal signals than the source
video's examples show.

---

## 1. Data

**Bars.** 15-minute, aligned to :00 / :15 / :30 / :45 ET, extended hours
included, 04:00 through 20:00 ET. 64 intervals per session.

**Missing bars are skipped, not synthesised.** A 15-minute interval in which a
$3 low-float name never trades returns no bar from IB. Two ways to handle it:

- Synthesise a flat bar (`O=H=L=C=` prior close, volume 0). This drags both EMAs
  toward a single price and manufactures crossovers out of silence. **Do not.**
- Advance the series only on bars that exist. **This is the rule.**

The consequence must be stated in every report: **"20 bars" is not "5 hours".**
On a thin name, bar 20 may close at 11:00 ET rather than 09:00. Report the
wall-clock timestamp of bar 20 per pair, not just the bar index.

**Liquidity gate.** One rule, applied at the only point where it changes what
gets executed: the **trigger bar must have traded ≥ `MIN_TRIGGER_DOLLAR_VOL`
(default $20,000)**. Dollar volume, not share count — per
`claude/momentum_confluence_strategy.md`, a share-count floor across a universe
spanning a 340× range in per-bar volume filters out entire names rather than
thin bars, and the names it removed were disproportionately the winners.

**Pairs.** Reuse the existing 407 ticker/date pairs so E15 is comparable to
V7/MC5 on the same tape. Selection bias is inherited and remains unfixed —
see §8.

---

## 2. Indicators

| | Definition |
|---|---|
| `ema9` | `ta.ema(close, 9)`, undefined until 9 completed bars |
| `ema20` | `ta.ema(close, 20)`, undefined until 20 completed bars |
| `sep` | `ema9 − ema20` |
| `atr14` | `ta.rma`-based ATR, 14 bars — the volatility unit for every threshold below |

Every threshold in this spec is expressed in **ATR multiples or percentages, not
dollars.** A universe of $2–$20 names moving 20–800% in a session has no stable
dollar scale.

Implement to Pine's definitions and verify against independent loop
implementations, as was done for RSI/MFI/MACD in `mcl_paper_trader.py`.

---

## 3. The state machine

The source's central claim is that the crossover is not the entry — the market
must be given a chance to prove the cross was real before any risk is taken.
That maps to five states.

```
IDLE ──cross──> ARMED ──confirm──> IMPULSE ──turn──> PULLBACK ──trigger──> IN_POSITION
  ^               │                   │                 │                      │
  └───────────────┴───────────────────┴─────────────────┴──────────exit────────┘
```

### 3.1 IDLE → ARMED (the crossover)

```
ema9[t] > ema20[t]  AND  ema9[t-1] <= ema20[t-1]
```

Both EMAs must be defined. Price trading above the EMAs is **not** a crossover —
the two lines must cross each other. Record `cross_bar = t`.

### 3.2 ARMED → IMPULSE (slope and separation)

Within `CONFIRM_BARS` (default 3) bars of the cross, all of:

| Condition | Expression |
|---|---|
| Fast EMA rising | `ema9[t] > ema9[t-2]` |
| Slow EMA rising | `ema20[t] > ema20[t-2]` |
| Separation expanding | `sep[t] > sep[t-1] > sep[t-2]` |
| Separation meaningful | `sep[t] / atr14[t] >= MIN_SEP_ATR` (default 0.25) |

Fails to confirm within the window, or `ema9` crosses back below `ema20` at any
point → **IDLE**. This is the fake-crossover rejection, and it is the whole
point of the strategy: the trade that never arms is the trade that never loses.

### 3.3 IMPULSE → PULLBACK (the turn)

While in IMPULSE, track:

- `impulse_high_close` — the highest close since `cross_bar`
- `swing_body_high` — same value, frozen at the moment the pullback starts

The pullback starts at the first bar where `close[t] < close[t-1]` and
`close[t] < impulse_high_close`.

`swing_body_high` is the **highest close** of the impulse leg, not the highest
high. The source is explicit that the level is drawn at the candle body: a wick
shows where price was rejected, a close records where it was accepted. On
these names the distinction is large — a 15m bar on a low-float runner routinely
prints a wick 8–15% above its close, and using the wick would push the trigger
level beyond where price will realistically close, converting most setups into
no-trades.

### 3.4 PULLBACK — the four conditions

All four must hold, evaluated each bar:

| # | Condition | Default | Fails → |
|---|---|---|---|
| 1 | **Reaches the zone** — some bar's `low <= ema9` | — | stays in PULLBACK until bar 8 |
| 2 | **Zone holds** — no bar `close < ema20` | — | IDLE |
| 3 | **Controlled** — no bar with `(close[t-1] − close[t]) > PULLBACK_CTRL_ATR × atr14` | 1.5 | IDLE |
| 4 | **Prompt** — pullback length ≤ `MAX_PULLBACK_BARS` | 8 | IDLE |

Plus, at all times: `ema9` crossing back below `ema20` → IDLE.

Condition 3 is the mechanical form of "small candles, no strong selling against
the trend". Condition 1 permits a touch of the 9 or a deeper move into the 9/20
zone — both are acceptable; what is not acceptable is a pullback that never
reaches the EMAs (no test = no proof) or one that closes through the 20.

Record `pullback_low` = lowest low observed during the pullback.

### 3.5 PULLBACK → IN_POSITION (the trigger)

Entry is the **first bar that closes above `swing_body_high`**, subject to the
dollar-volume gate in §1. It may take one bar or several — the close is what
matters, not how many bars it took.

If no trigger occurs within `MAX_TRIGGER_BARS` (default 6) after the pullback
low → **IDLE**.

An EMA touch is not an entry. A bullish candle is not an entry. Only the close
beyond the level.

### 3.6 Exits

| Exit | Rule |
|---|---|
| **Stop** | `pullback_low − STOP_BUFFER_ATR × atr14` (default 0.10) |
| **Target** | `entry + 2R`, where `R = entry − stop` |
| **Session** | Flat at 20:00 ET, at the 19:45–20:00 bar's close |

**Intrabar ambiguity: if one bar's range contains both the stop and the
target, assume the stop filled first.** 15-minute bars on these names are wide
enough that this will happen, and the assumption must be conservative and
recorded — the count of ambiguous bars belongs in the report.

**Re-entry:** one position per name at a time. After an exit the state returns
to IDLE and only a *new* crossover can re-arm. `ALLOW_REARM_SAME_TREND`
(default `False`) exists to test taking the second and third pullback in one
trend, but the source specifies the first pullback and that is the baseline.

### 3.7 Exit variants to test after the baseline

The MCL work found fixed stops inferior to trailing on this universe (V3 → V4,
6% fixed → 5% trailing, +$339 → +$931). A fixed 1:2 target has the mirror-image
problem: it caps exactly the runners this universe is screened to find. Test as
variants, not as the baseline:

- `EXIT_MODE = trail_atr` — trail at `k × atr14` off the high since entry
- `EXIT_MODE = ema20_close` — exit on the first close below `ema20`
- `EXIT_MODE = partial` — half at 2R, remainder trailed

Baseline stays the fixed 1:2 so the first result is a faithful test of the
source rules.

---

## 4. Parameters

| Name | Default | Basis | Calibrated? |
|---|---|---|---|
| `EMA_FAST` | 9 | source | n/a |
| `EMA_SLOW` | 20 | source | n/a |
| `BAR_MINUTES` | 15 | Ben | n/a |
| `SESSION` | 04:00–20:00 ET | Ben | n/a |
| `WARMUP_MODE` | `none` | §0 | n/a |
| `CONFIRM_BARS` | 3 | **guess** | **NO** |
| `MIN_SEP_ATR` | 0.25 | **guess** | **NO** |
| `PULLBACK_CTRL_ATR` | 1.5 | **guess** | **NO** |
| `MAX_PULLBACK_BARS` | 8 | **guess** | **NO** |
| `MAX_TRIGGER_BARS` | 6 | **guess** | **NO** |
| `STOP_BUFFER_ATR` | 0.10 | **guess** | **NO** |
| `MIN_TRIGGER_DOLLAR_VOL` | $20,000 | volume-floor finding | partially |
| `TARGET_R` | 2.0 | source | n/a |

**Six of thirteen parameters are uncalibrated guesses.** That is the same
condition MC5 shipped in (`ENTRY_RSI_ROC_PCT = 5.0`, noted in
`claude/repo_reorg_and_github_plan.md` as never having been run on real data).
Calibrate from measured distributions on real 15m bars — §7 — before reading any
P/L number as meaningful.

Note also the lesson from `claude/mcl_arming_window_backtest.md`: relaxing a
restrictive rule produced 75% more trades and *less* money. **Restrictiveness
was doing real work.** Expect the same here, and calibrate toward the tight end
of each measured distribution rather than the loose end.

---

## 5. Execution model

Outside RTH, IBKR accepts **Day Limit orders only** for US stocks — no market
orders, no native stop or trailing-stop orders, since those fire market orders.
This governs 04:00–09:30 and 16:00–20:00, which is 38 of the 64 bars. Stop and
target must be software-managed and breached with marketable limits, exactly as
`mcl_paper_trader.py` already does.

Model and log **both** prices on every fill, so the number is comparable to the
paper trader's `slippage_vs_ref` column:

| Field | Meaning |
|---|---|
| `ref_price` | Trigger bar close — what the source rules assume |
| `fill_price` | Next bar's open + modelled slippage |
| `slippage_vs_ref` | The difference, per share |
| `session_block` | `PRE` / `RTH` / `POST` — slippage must be reported per block |

Entering at the signal bar's close, as every backtest in this project has so
far, is a market-order assumption that IBKR will not accept for 38 of 64 bars.
**Next-bar-open is the baseline fill for E15.** Commission $0.005/share.
Sizing `min(100 shares, 40% of equity / price)` — unchanged from MCL so the
results are comparable.

---

## 6. What the report must contain

Standing rule from `claude/momentum_confluence_strategy.md`: the verification
table reports its own data coverage in the same pass as the P/L. For E15:

**Coverage, per pair**

- bars loaded; first and last bar timestamp
- **wall-clock time of bar 20** (the EMA20 warm-up point)
- count of the 64 intervals with no bar
- open-position-at-session-end flag

**Results**

- per-ticker trades / net / win rate, as in every prior table
- **drop-top-N concentration table** (N = 1, 2, 3). This is the number that
  matters most: V7 was +$890 but negative once its three best names were
  removed, and that concentration — not entry timing — was identified as the
  real problem
- **histogram of entry timestamps.** Directly tests §0. If the earliest entry
  across 407 pairs is after 10:00 ET, the warm-up finding is confirmed
  empirically and the "full day" framing should be retired
- trades and P/L **split by session block** (PRE / RTH / POST)
- count of bars where stop and target were both inside the same bar's range

---

## 7. Pre-flight measurements — do these before writing strategy code

None of the parameter defaults are trustworthy and the sample size is unknown.
Four cheap measurements on the existing 407 pairs settle both:

1. **Bar availability.** Per session block, what fraction of the 64 intervals
   produce a bar? If pre-market is 30% populated, §1's "20 bars ≠ 5 hours"
   caveat is the dominant effect and belongs in the headline.
2. **Dollar volume per 15m bar**, median and 10th percentile, by block.
   Confirms or moves the $20,000 gate.
3. **Crossover count.** How many 9/20 crossovers occur per name per session,
   and how many survive the §3.2 confirmation? This sets the sample size.
   At roughly 0.3 completed setups per pair, 407 pairs yields ~120 trades —
   comparable to V7's 51 and workable. At 0.05, the study is not viable at this
   timeframe and that is worth knowing before building it.
4. **Distributions** for `sep/atr14` at cross+3, pullback depth in ATR, pullback
   length in bars, and bars-to-trigger. These replace six guesses with measured
   values.

Measurement 3 is the gate. Run it first.

---

## 8. Known limitations, stated up front

- **The pre-market window is unreachable.** §0. The strategy as specified cannot
  trade 04:00–09:30 on a same-session EMA series.
- **The 1-hour trend filter from the source is not implemented.** §0.
- **Selection bias is inherited and unfixed.** The 407 pairs are names chosen
  because they ran. Every P/L number E15 produces carries the same defect as
  every MCL number. Only forward testing on contemporaneous scanner picks fixes
  it, and the paper pipeline is the prerequisite.
- **Long-only on a universe that also collapses.** These names give back most of
  the move; a long-only 15m strategy will spend much of the day in a downtrend
  it cannot trade. Expect long flat stretches, and do not read them as failure.
- **Six uncalibrated parameters.** §4.

---

## 9. Next, in order

1. **Pre-flight measurement 3** (crossover and completed-setup counts across the
   407 pairs). If the sample is too small, stop here and reconsider the
   timeframe rather than building the module.
2. Pre-flight measurements 1, 2 and 4; set the six guessed parameters from the
   measured distributions.
3. Write `strategies/e15.py` to the `DataSource` / `ExecutionVenue` shape from
   step 2 of `claude/repo_reorg_and_github_plan.md` — final name from the start,
   so step 3 is a pure `git mv`.
4. Unit-test the state machine against hand-built bar sequences: a clean setup,
   a fake cross that re-crosses during the pullback, a pullback that closes
   below the 20, an uncontrolled pullback, a trigger that never comes, and a bar
   containing both stop and target.
5. Backtest with `--strategy e15` on the 407 pairs. Report per §6.
6. Only then compare to V7 and MC5 — and compare on the RTH subset, since that
   is the only window all three can trade.

---

*Rules adapted from a publicly posted educational video; the video presents
curated chart examples rather than a logged track record, and states no win
rate, sample size, or drawdown. Nothing above is validated until step 5.*
