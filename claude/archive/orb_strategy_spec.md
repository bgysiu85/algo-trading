# ORB — Opening Range Break, 09:30 RTH

Spec written 2026-09-06. **Code not yet written.** Synthesised from ten
publicly posted educational videos, each read in full and reported on
independently before any rule was drafted, so the disagreements below are the
sources' and not a summary artifact.

> **Corrections applied 2026-09-07.** Five things changed after this spec was
> written and every one of them touched it. In order of how much they matter:
>
> 1. **§3.2's largest stated risk is largely resolved.** The screener is now
>    simulated and `bar_cache_db` holds 25,769 symbol-days over 548 sessions.
>    ORB no longer has to run on 407 hindsight pairs. §3.2 and §10.2 rewritten.
> 2. **§9's slippage was wrong and sign-reversed.** The buy/sell asymmetry was
>    measured as noise across 18,552 fills. Row replaced.
> 3. **§11 criterion 3 is unblocked.** Friction is measured; the placeholder is
>    now a number.
> 4. **§0 overstated the RTH advantage.** 60 bps against 83, not "tightest of
>    the day". The execution argument survives, smaller.
> 5. **§11's prior changed, and not in ORB's favour.** MC5 cleared criterion 1
>    out-of-sample — the first thing here ever to — and **still fails criterion
>    2**. See §11.

| | |
|---|---|
| Universe | $2–$20, RVOL(1D) ≥ 5×, float < 20m — **screened at 09:30 on RTH columns**, see §3 |
| Direction | **Long only** (§5.4 explains why, and what it costs) |
| Range | **First 15 minutes, 09:30–09:45 ET** — modal choice, 6 of 10 sources |
| Entry | **5-minute candle CLOSE beyond the range**, retest optional and measured |
| Session | 09:45 → 16:00 ET, flat at the close |
| Indicators | **None.** The range, and price. |
| Deliverable | This spec; §11 go/no-go is fixed before any code exists |

---

## 0. Why this one, and why now

Every strategy in this project so far has failed in one of two ways, and ORB
is chosen because it is the first candidate that structurally avoids the more
serious one.

**The fill problem.** `PROGRAM_INDEX` §5: outside RTH, IBKR accepts Day Limit
orders only — no market orders, no native stops, no native trailing stops.
Every stop is software-managed and every fill is a modelling assumption. VW9
was rejected in part because **100% of its profit sat in the pre-market block
and its RTH block lost money** (`vw9.md`). MCL trades 04:00–09:30 exclusively,
so its entire measured edge rests on fills the model cannot support.

ORB does not enter before 09:45. Every order it places is inside RTH: market
orders exist, native stops exist, and `common/friction.py` can measure the
slippage of the exact order types the strategy uses.

**How much cheaper RTH actually is — corrected 2026-09-07.** The original text
here said "the spread is at its tightest of the day", which came from the
EQUS.MINI pass that was later retracted. Measured on XNAS.BASIC across 18,552
fills: **PRE 83 bps, RTH 60 bps, POST 87 bps**. RTH is cheaper by **1.4×**, not
by the structural margin this section originally claimed.

**The argument for ORB therefore stands but is smaller than written.** It is
not that RTH is dramatically cheaper. It is that RTH orders are of a type the
venue actually supports, which removes a known fiction from the model rather
than adding edge. `execution_cost_measured.md` §4 says this explicitly.

**The concentration problem is NOT avoided.** Drop-top-N killed VW9, the
scale-out exit, and every `TRAIL_PCT` candidate. §11 sets the bar accordingly.

**The universe problem is now mostly solved — see §3.2.** When this spec was
written, ORB's need for a 09:30 RTH screen was its largest single risk, because
no backtest here had ever simulated a screener. That changed on 2026-09-07.

---

## 1. What the ten sources actually say

Read before the rules, because the spread is the story. Nothing below is
averaged; where the sources disagree, §4–§7 pick one and say so.

| # | Channel | Range | Entry | Stop | Target | Instrument |
|---|---|---|---|---|---|---|
| V1 | Jdub Trades | first 5-min candle | break with "displacement" → retest → discretionary confirmation candle | "just beyond" — **no number** | fixed 1:2 R | SPY |
| V2 | Peachy Investor | 15-min traditional, 30-min preferred, + a pre-market ORB | **rejects breakouts**; fades failed breaks, scalps the range, or break→retest→higher-low | not stated | 50% of range, then opposite edge | ES/SPY/QQQ/gold |
| V3 | Lance Breitstein | "first 30 minutes or so", wick to wick | break "once price confirms momentum" — unspecified | **not stated** | **not stated** | in-play US stocks |
| V4 | Raghee Horner | **09:30–10:00 exactly** ("clearing range"); also 09:30–10:30 initial balance | breach, then retest of the **38–62% zone** of the range | **not stated** | opposite range boundary | equities/ETFs/futures/FX |
| V5 | Casper Trading | 15-min, traded via the **70% value area** of the first three 5-min candles | 5-min close outside the value area (breakout) or close back inside it (fakeout) | 2 ticks past POC / beyond entry candle | fixed 2R / opposing liquidity | NQ, ES |
| V6 | The Moving Average | 15-min, 09:30–09:45 | candle **close** beyond the range | **opposite side of the range** | fixed 1:1.5 R | gold, NAS100, S&P |
| V7 | Bossupwiththehayes | 15-min, 09:30–09:45 | break **then retest**; no close or buffer spec | **not stated** | not stated for the main setup | US stocks/ETFs via options |
| V8 | Bull Barbie | 15-min from the NY open | **resting stop orders a hair outside both sides**, no retest | a few ticks beyond the opposite side | **1× range width**; BE stop at 0.5× | NQ futures |
| V9 | Hidden Method | 5 / 15 / 30, unspecified | any move beyond; optional FVG / LVN / delta retest | **not stated** | **not stated** | not stated |
| V10 | Jdun Trades | 15-min (three 5-min candles) | **5-min candle CLOSE** beyond the level (mandatory), retest preferred, enter at next candle's open | beyond the trend-setting candle / retest wick / 20–30 pt | trim at 2R, target 3R–4R | NQ/ES futures |

### 1.1 The four facts that matter most

1. **Four of ten videos state no stop loss at all** (V3, V4, V7, V9). A
   breakout method with no stop is not a strategy; it is a chart observation.
   The stop in §6 is therefore taken from the minority who specify one, and it
   is the parameter most likely to be wrong.
2. **Only two give any performance statistics, and both are unusable.** V1
   reports 12 trades over one month and states the profit three mutually
   inconsistent ways ($122k / $112k / $12k). V8 reports 22% stopped /
   22–23% trailed out / 55% target from a **manual visual review with no trade
   count**. There is no logged, verifiable track record anywhere in the set.
3. **One source rejects the premise.** V2 does not trade opening-range
   breakouts. He fades failed ones. That is not a variant of the strategy — it
   is the opposite trade, and it is a live hypothesis, not a rounding error.
   §7.4 keeps it as a measurement rather than discarding it.
4. **Only two of ten trade this project's universe.** V3 (in-play US stocks)
   and V7 (US stocks via options). The rest trade NQ, ES, SPY, QQQ, gold, or
   an unstated instrument. **A 15-minute opening range on NQ and a 15-minute
   opening range on a $4 stock that gapped 300% pre-market are not the same
   object**, and every number below inherits that gap. The videos are
   hypothesis generators, exactly as `PROGRAM_INDEX` §4 says of the EMA set.

### 1.2 Where the spec picks a side

| Question | Sources split | This spec | Why |
|---|---|---|---|
| Range length | 5m (V1), 15m (V2,V5,V6,V7,V8,V10), 30m (V2,V3,V4) | **15m** | Modal, 6 of 10. `ORB_MINUTES` is a parameter and 5/15/30 all run in the same pass — §10.1 |
| Close or touch | close (V5,V6,V10) vs touch/resting order (V8,V9) | **close** | It is also the one point all six EMA-source videos agreed on (`source_comparison.md` C3), and the project has already been burnt by touch-based rules: see `PROGRAM_INDEX` §5, VW9's `vwap_lost` firing on the fill bar |
| Retest required | required (V1,V4,V7,V10-preferred) vs not (V6,V8) | **optional, measured both ways** | This is the single largest fork in the ten videos. §5.3 |
| Stop | opposite side (V6,V8) vs structure (V5,V10) vs unstated (4 videos) | **structure, with opposite-side as the cell to beat** | §6 |
| Target | 1:1.5 (V6), 1× range (V8), 2R (V1,V5), 3–4R (V10), opposite edge (V2,V4) | **all of them, one pass** | §7. The project's own V3→V4 result says fixed targets cap runners; on this universe that matters more than on NQ |

---

## 2. What the strategy is, in one paragraph

At 09:45 ET the high and low of the first fifteen minutes of regular trading
are fixed. If a 5-minute candle closes above that high, buy at the next
candle's open. Risk is the distance from entry to a stop placed beneath the
structure that produced the break. Take profit at a multiple of that risk, or
at a multiple of the range width, or by trailing — whichever the grid says,
measured against a fixed baseline. Be flat by 16:00. Everything else in this
document is either the definition of one of those words or a measurement of
whether the sentence is true.

---

## 3. Universe and session

### 3.1 The screen

Per `screening.md`, the RTH column set:

```
change_from_open      > ORB_MIN_MOVE_PCT      (candidate: 5.0, MEASURE)
relative_volume_10d_calc >= 5.0                (carries across blocks unchanged)
close                 in [2.0, 20.0]           (PROGRAM_INDEX §1 — mandatory)
float_shares_outstanding < 20,000,000
```

`change_from_open`, not `change`. At 09:31 `change` still carries the entire
overnight gap, which would re-select yesterday's pre-market gappers rather
than what is moving now. This is the honest column for "moving during RTH"
and it is the one that matches what ORB is trying to trade.

**Read `ignored_filters` on every response.** The server accepts unknown
clauses, returns a plausible set, and silently does not apply them.
`common/tv_screener.check_response()` exists for this.

**Price band is mandatory and non-negotiable.** `PROGRAM_INDEX` §1 and §5:
VW9 shipped without it and took positions at $4,152/share — an adjustment
factor, not a price. Its headline went from −$31,296 to +$3,942 once the band
was applied. Parity is a hard rule, so ORB enforces it before a single P/L
number is read.

### 3.2 The universe problem — **largely resolved 2026-09-07**

**What this section used to say**, and it was the largest single risk in the
document: every backtest in this project ran on `var/state/traded_pairs.json`,
407 pairs assembled in hindsight, and the screener was not simulated at any
point. For MCL that gap was modest. For ORB it was not, because ORB's universe
is constructed at 09:30 on columns whose values did not exist when the
hindsight list was assembled. Any ORB result on that list would have described
a universe with no live construction mechanism — the same defect that made
VW9's RTH block unbuildable.

**What changed.** `common/screen.py` now simulates the screen over the full
Databento daily archive: **22,882 candidate symbol-days across 548 sessions**
(2024-07-01 → 2026-09-04), plus 4,995 sampled rejects as a control population.
`bar_cache_db/3d_to_2000/` holds three full sessions to 20:00 ET for **25,769**
of those symbol-days — which means every bar between 09:30 and 16:00 is
already on disk for a universe that was selected by rule.

Three consequences, all of which improve ORB's position:

1. **ORB runs on the screened universe, not the 407 hindsight pairs.** The
   selection bias §13 used to list first is materially reduced — not
   eliminated, because the screen's own thresholds were chosen by a person.
2. **The 09:30 RTH screen is computable.** `change_from_open` and
   `relative_volume_10d_calc` are both derivable from the cached 1-minute bars;
   float is static and known per symbol. §10.2 becomes a measurement that can
   actually be made rather than a warning.
3. **The stage-2 leak applies here too, and differently.** The screen's stage 2
   uses the session's own daily bar, so it leaks — `screened_universe_results.md`
   §4 measures the leak for the pre-market strategies and finds it small on the
   entry side. **ORB's exposure is not the same and has not been measured**,
   because ORB selects at 09:30 from within a universe that was itself selected
   using the whole day's bar. Stage 2 knows the day's range; ORB trades a break
   that contributes to it. Measure this before believing any ORB figure.

**What has not changed.** The screen is a pre-market screen — stage 1 on prior
close and trailing dollar volume, stage 2 on today's RVOL and range. It is not
an RTH screen. It supplies a defensible universe to run ORB *over*; §10.2 is
still required to establish whether an RTH screen at 09:30 would have picked
the names ORB's edge lives in.

### 3.3 Session

Range 09:30:00–09:44:59 ET. Trading 09:45:00–15:55. Flat at the 15:55–16:00
bar's close; no position is carried into the closing auction, and none is
carried into post-market where the Day Limit constraint returns.

`MAX_ENTRIES_PER_SESSION` default **1** — see §5.5 and note that this is the
opposite of VW9's "window" model, deliberately.

---

## 4. The opening range

```
orb_high = max(high[t]) for t in [09:30, 09:30 + ORB_MINUTES)
orb_low  = min(low[t])  for t in [09:30, 09:30 + ORB_MINUTES)
orb_width = orb_high - orb_low
```

**Wick to wick**, per V3 and V10, not body to body. No source in the set uses
bodies and one (V3) states wick-to-wick explicitly.

Four definitional traps, each of which returns a plausible wrong answer rather
than an error:

1. **The 09:30 bar must be present.** On a thin small cap it may not be. A
   session whose range is built from fewer than `MIN_RANGE_BARS` (default 10
   of the 15 one-minute bars) is **skipped and reported**, not silently
   traded on a partial range.
2. **The range must have width.** If `orb_width / orb_low < MIN_RANGE_PCT`
   (default 0.5%), the "breakout" is noise and the R denominator explodes.
   Skip and report.
3. **And it must not be absurd.** If `orb_width / orb_low > MAX_RANGE_PCT`
   (default 25%), the first fifteen minutes already contained the day's move
   and a break of it is a late entry into a vertical. Skip and report.
   Note this rule is the one most likely to bind on this universe and least
   likely to bind on V8's NQ — another instance of §1.1 item 4.
4. **The range is fixed at 09:45 and never updated.** Not a trailing 15
   minutes, not re-anchored on a new high. Every source that specifies this
   agrees; it is written down because it is the kind of thing an
   implementation drifts on.

`orb_width` is also the natural risk unit for this strategy, in the same role
ATR plays in VW9 and E15 — with the advantage that it is defined at 09:45
with no warm-up, where ATR14 on 15-minute bars is not defined until 07:30.
**ORB has no indicator warm-up problem at all.** That is worth stating: it is
the only strategy in this project of which that is true.

---

## 5. Entry

### 5.1 The trigger

A **5-minute candle closes above `orb_high`**. Entry is at the **next 5-minute
candle's open**, plus modelled slippage (§9).

Bar size for the trigger is `TRIGGER_BAR_MINUTES`, default 5. This is V10's
rule stated exactly, and V5's and V6's in substance. It is *not* V8's resting
stop order, and the difference is material: a resting order fills on any wick,
a close-based rule requires the market to hold the level for up to five
minutes. On a universe where 15-minute ranges of 10%+ are ordinary, the
resting order fills on far more fakeouts. **`ENTRY_ON_CLOSE = False`
reproduces V8's rule and runs as a comparison cell** — do not assume, measure.

### 5.2 Buffer

`ENTRY_BUFFER_PCT` (default **0.0**) — the close must exceed
`orb_high × (1 + buffer)`. Zero by default because no source specifies a
buffer in percent, and inventing one adds an uncalibrated parameter to defend
against a problem that has not been measured. §10.3 measures how many triggers
close within 0.1% of the level; if that fraction is large, this parameter
earns its place, and if not it stays at zero.

### 5.3 The retest fork — the largest disagreement in the set

Four sources require or prefer a retest (V1, V4, V7, V10); two explicitly do
not (V6, V8). This is not a detail; it is two different strategies.

`RETEST_MODE`, three values, **all three run in the same pass**:

| Value | Rule |
|---|---|
| `none` | Enter on the trigger bar's next open. V6, V8. |
| `required` | After the trigger, price must trade back to `orb_high` (or into the 38–62% zone, per V4 — see below) within `RETEST_MAX_BARS` (default 6) and then produce a 5-minute close back above it. That second close is the entry. Setup is abandoned if price closes below `orb_low` or the window expires. |
| `zone` | V4's version: the retest must reach into the **38–62% retracement of the range** rather than merely touching `orb_high`. Materially deeper, materially fewer trades. |

Two things to hold onto while reading the result:

- **A retest rule can only remove trades, never add them** (the same ordering
  property `test_trail_timing.py` pins for the loose trail variants). So the
  fair comparison is not `required` vs `none` on total P/L — it is per-trade
  P/L, plus drop-top-N on the *delta*, which is what killed every `TRAIL_PCT`
  candidate whose level table looked convincing.
- **The retest fork interacts with the stop.** A retest entry is closer to the
  level, so R is smaller and the same dollar stop is a larger R multiple.
  Never compare a retest cell against a non-retest cell at a different stop
  rule; hold the confound fixed (`PROGRAM_INDEX` §4).

### 5.4 Long only, and what that costs

Long only, consistent with every other strategy here, and for the same
reasons: `source_comparison.md` establishes that borrow availability, cost,
and SSR on sub-20m-float small caps are unresolved feasibility questions, not
strategy questions.

**But the cost is higher for ORB than it was for MCL or VW9.** Six of the ten
videos treat the range as symmetric and take whichever side breaks; V2's
entire method is directional-agnostic. Restricting to longs discards roughly
half the sources' signals by construction. The downside break must therefore
still be **measured and reported** (§12) even though it is not traded — if the
short side is where the edge is, that is a finding worth having before the
feasibility work is done, not after.

### 5.5 One trade per session, by default

`MAX_ENTRIES_PER_SESSION = 1`. Deliberately the opposite of VW9's re-entry
window. The reason is arithmetical rather than aesthetic: ORB has one range
per day, so a second entry is by definition a re-break of a level that already
failed once, which is a different hypothesis and none of the ten sources
specifies it. Run `2` as a cell; do not ship it without a reason.

---

## 6. The stop

Four of ten sources state no stop. Of the six that do, two say the opposite
side of the range (V6, V8) and two say structure (V5's 2 ticks past POC, V10's
"beyond the trend-setting candle"). V1 says "just beyond" without a number.

`STOP_MODE`, three cells:

| Value | Rule | Source |
|---|---|---|
| `structure` (baseline) | Low of the trigger candle (or of the retest candle in retest modes), minus `STOP_BUFFER_PCT` (default 0.10% of price) | V10 |
| `opposite` | `orb_low − buffer` | V6, V8 |
| `range_frac` | `entry − STOP_RANGE_FRAC × orb_width` (default 0.5) | interpolation, flagged as such |

```
R = entry_fill − stop
```

**Expect `opposite` to be structurally enormous on this universe, and check
it.** VW9's open question is precisely this failure: its `structure_low`
spanned a whole bearish stretch and produced a median R of **9.4% of price**,
p90 20.7%. A 15-minute opening range on a $3 stock that gapped 200% can easily
be 15% wide, so `opposite` puts the stop 15% away and one loss erases many
wins. **Report the R distribution as a percentage of price for every stop
mode, in the pre-flight, before any P/L is read** (§10.4). If median R exceeds
`MAX_R_PCT` (default 12%) the trade is skipped and counted — a size cap does
not fix an unusable stop, it just makes the loss smaller and the sample
thinner.

**No native stop is used even though RTH allows one.** The backtest models a
software stop breached with a marketable limit, identically to MCL, so that
backtest and live agree and so that `common/friction.py`'s per-exit-reason
measurements remain comparable. That RTH *permits* a native stop is a live
robustness win (a crash no longer leaves the position naked) and should be
taken advantage of in `trader.py` — but it must not silently become a
different fill model in the backtest.

---

## 7. Exits

### 7.1 Targets, all in one pass

| `EXIT_MODE` | Rule | Source |
|---|---|---|
| `r_2` (baseline) | Exit at `entry + 2R` | V1, V5 |
| `r_1_5` | Exit at `entry + 1.5R` | V6 |
| `r_3_trim` | Trim half at 2R, remainder at 3R | V10 |
| `range_1x` | Exit at `entry + 1 × orb_width`; stop to break-even at 0.5× | V8 |
| `trail_pct` | Trail `TRAIL_PCT` (default 5.0) off the high since entry | MCL's settled config |

`r_2` is the baseline because it is the modal source rule. But the project's
own record — V3→V4, 6% fixed to 5% trailing, +$339 → +$931, and the whole
trail line of work in `mcl_parameter_decisions.md` — says a fixed target caps
exactly the runners this universe is screened to produce. `trail_pct` at 5.0
is included specifically so the comparison is against **the rule this project
actually ships**, not only against the videos.

`r_3_trim` is the only mode that changes position size mid-trade. Note the
finding from the scale-out study: partial exits were rejected on this universe
(P(>0) = 0.0%), and commissions are **per order**, so a trim pays the per-order
minimum twice. At IBKR Tiered that is $0.35 rather than Fixed's $1.00 —
material, and `screened_universe_results.md` §3.2 shows how fast order count
eats a thin edge. Run it, expect it to lose, and if it wins, be suspicious
before being pleased.

### 7.2 Hard exits, in priority order

1. **Stop hit** — with honest gap fills (§9).
2. **Target hit** per `EXIT_MODE`.
3. **Session end** — flat at the 15:55–16:00 close.

**Intrabar ambiguity: if a bar's range contains both stop and target, the stop
filled first.** Report the count. On 5-minute bars on a name moving 20% intraday
this will not be rare, and it is the assumption that keeps the result honest.

### 7.3 A time stop, measured not assumed

`TIME_STOP_BARS` (default `None`). V3's framing is that the opening range
matters because the first half hour is where the day's participation is
decided — which implies a break that has gone nowhere by 11:00 has falsified
its own premise. No source states a time stop, so the default is off.
§10.5 measures time-to-target and time-to-stop; if the winners resolve inside
an hour and the losers grind all afternoon, this parameter earns its place
from data rather than from the paragraph above.

### 7.4 The V2 hypothesis, kept as a measurement

V2 does not trade the breakout. He fades the failed one. Implementing that as
a second strategy is out of scope, but the measurement is nearly free and it
is the only genuine counter-hypothesis in the source set:

For every trigger that fires, record whether price closed back **inside** the
range within `FADE_WINDOW_BARS` (default 3), and if so what a short from that
point to `orb_low` would have returned. This costs one column and answers
whether the breakout premise is right at all on this universe. **It is a
measurement, not a strategy** — nothing is traded from it without its own spec
and its own go/no-go.

---

## 8. Parameters

Every row marked **NO** is a guess until §10 replaces it.

| Name | Default | Basis | Calibrated? |
|---|---|---|---|
| `ORB_MINUTES` | 15 | modal, 6 of 10 sources | **NO** — §10.1 runs 5/15/30 |
| `TRIGGER_BAR_MINUTES` | 5 | V5, V6, V10 | **NO** |
| `ENTRY_ON_CLOSE` | `True` | V5, V6, V10 | **NO** — `False` = V8's rule, runs as a cell |
| `ENTRY_BUFFER_PCT` | 0.0 | no source specifies one | **NO** — §10.3 |
| `RETEST_MODE` | all three | the set's largest disagreement | **NO** — §5.3 |
| `RETEST_MAX_BARS` | 6 | **guess** | **NO** |
| `STOP_MODE` | all three | §6 | **NO** |
| `STOP_BUFFER_PCT` | 0.10% | carried from VW9/E15 | **NO** |
| `STOP_RANGE_FRAC` | 0.5 | **interpolation, no source** | **NO** |
| `MAX_R_PCT` | 12% | **guess**, set from §10.4 | **NO** |
| `EXIT_MODE` | all five | §7.1 | **NO** |
| `TRAIL_PCT` | 5.0 | **measured** — `mcl_parameter_decisions.md` | **yes, elsewhere** |
| `TIME_STOP_BARS` | `None` | off by default | n/a |
| `MIN_RANGE_BARS` | 10 of 15 | **guess** | **NO** |
| `MIN_RANGE_PCT` | 0.5% | **guess** | **NO** |
| `MAX_RANGE_PCT` | 25% | **guess** | **NO** |
| `ORB_MIN_MOVE_PCT` | 5.0 | **guess** | **NO** — §10.2 |
| `MAX_ENTRIES_PER_SESSION` | 1 | §5.5 | **NO** |
| `PRICE_MIN`, `PRICE_MAX` | 2.0, 20.0 | `PROGRAM_INDEX` §1 | **mandatory** |
| `FADE_WINDOW_BARS` | 3 | measurement only | n/a |

**Fifteen of twenty parameters are uncalibrated guesses.** That is worse than
VW9's twelve of eighteen, and it is the honest cost of building from ten
sources that mostly decline to specify numbers — four of them do not even
specify a stop. §10 exists to fix this before any P/L number is read as
meaningful, and §11 is written now so the bar cannot move afterwards.

**Do not sweep these per name.** The `armBars` relaxation and the share-count
floor both failed by re-tuning a rule whose restrictiveness was doing the
work. Same rule here.

---

## 9. Fill model — stated up front, because it is what broke everything else

On 2026-09-05, running MC5 for the first time exposed two assumptions that had
been inflating **every published result in this project**. MC5 reported
+$20,156 and passed every robustness test; honest fills took it to −$400.
Applied to MCL, +$1,567 became +$161. The trades were identical — only the
price they were booked at changed.

ORB is specified with the corrected model from bar one:

| Assumption | Setting | Why |
|---|---|---|
| **Gap-through fills** | `gap_fills=True` | You cannot sell AT a level the market never offered. When a bar OPENS below the stop, the fill is the open, not the level. 48% of MC5's stop exits were affected. |
| **Peak seeding** | from **entry price**, never the entry bar's high | The entry bar's high happened before the close we bought at. Seeding from it prices a move the position never had, and in 53% of MC5's stop exits it put the trail above the market at the instant of entry. |
| **Stop/target same bar** | stop wins | §7.2 |
| **Entry** | next bar's **open** + slippage, never the trigger close | The trigger close is a price that has already gone. |
| **Slippage** | **one figure, both sides** — `SLIPPAGE_TICKS = 1` | **Corrected 2026-09-07.** This row previously read "buys favourable −$0.0164/share, sells adverse +$0.0590/share", from a single session — and with the signs reversed from the document it was copied out of. Measured across **18,552 fills** on XNAS.BASIC the asymmetry is **$0.0009 versus −$0.0009**: symmetric, and indistinguishable from zero. The single-session figure was noise. Do not model the two sides differently. |
| **Commission** | `ibkr_tiered` via `common/commissions.py` | Per **order**, not per share. Fixed/Tiered crossover at exactly 150 shares, price-independent. Tiered settled as the project's plan 2026-09-07. |
| **Marketable limits remove liquidity** | always | Effective cross 37–43 bps on this universe; measured cross vs mid 17.3 bps against `LIMIT_CROSS_BPS = 20`. |

**Modelled slippage is conservative and stays that way.** `SLIPPAGE_TICKS = 1`
charges $2.00 per 100-share round trip against a measured **$1.00** (median,
$0.92 mean). That is the safe direction and it is not to be "corrected" into
the strategy's favour — see §11 criterion 3.

RTH is the one block where these assumptions can be **checked against measured
fills** rather than argued about, which is the whole point of §0.

**Sizing.** Report both:

- **Flat 100 shares** — the comparable number, the one that lines up against
  the screened out-of-sample figures in §11.
- **Capital-based**, via `common/compound_sim.py`. This is the number that
  flipped MCL's sign, because the $2–5 band loses and receives 9× the shares.
  **Expect the same effect here and check the price-decile table before
  concluding anything about ORB from the capital-sized figure.**

---

## 10. Pre-flight — measurements before strategy code

Each of these can kill the strategy on its own, and each is cheap.

**The cache changed on 2026-09-07.** These measurements now run over
`bar_cache_db/3d_to_2000/` — **25,769 symbol-days across 548 sessions**,
selected by the simulated screen — not the 375-file, 374-session hindsight
cache this section originally named. Nothing here touches IB.

**Slice the superset — do not import `backtest.py`.** ORB needs 1 session
ending 16:00, which is a different slice from both MCL (2 sessions to 09:30)
and VW9 (1 session to 20:00). Set `BACKTEST_SESSIONS = 1`,
`BACKTEST_END_HOUR = 16`, `BACKTEST_END_MINUTE = 0` on the strategy module and
let `cache_io` do the slicing. `bar_cache_db` windows end at 20:00, so the
16:00 slice is available; confirm the RTH bars are actually present rather
than assuming, since the cache was built for pre-market strategies.

### 10.1 Range width and shape, by `ORB_MINUTES`
Distribution of `orb_width / orb_low` at 5, 15 and 30 minutes across the
screened symbol-days. Median, p10, p90. What fraction fail `MIN_RANGE_PCT` or
`MAX_RANGE_PCT` at each? **If more than about a third are excluded at 15
minutes, the range filters are doing the strategy's job and their defaults are
wrong.**

### 10.2 The RTH screen overlap — the buildability check
Per §3.2. For each screened symbol-day, compute at 09:30 whether it would pass
the §3.1 RTH screen from cached bars. Report:

- how many of the 22,882 survivors pass the RTH screen at 09:30,
- and — this is the one that matters — the eventual ORB P/L split by whether
  the symbol-day passed.

**If the edge lives in the non-passing population, the strategy is not
tradeable and everything after this point is fiction.** Run this first.

This is no longer a warning that the measurement is impossible; it is a
measurement, and the bars for it are on disk.

### 10.2b ORB's own stage-2 leak — new, and specific to this strategy
Per §3.2 item 3. The screen's stage 2 uses the session's own daily bar, which
includes the day's range — and ORB trades a break that contributes to that
range. Run ORB over the 4,995 sampled **rejects** as well as the survivors and
report the entry rate and per-trade P/L on each, the same two cuts
`screened_universe_results.md` §4 applies. **A strategy that trades the day's
range is more exposed to a filter that read the day's range than a pre-market
strategy is.** This has not been measured for any strategy that trades RTH.

### 10.3 Trigger counts, before any gate
How many symbol-days produce an upside close beyond `orb_high`? A downside
one? Both? Neither? What fraction of upside triggers close within 0.1% of the
level (this sets `ENTRY_BUFFER_PCT`)? What fraction are followed by a
qualifying retest within 6 bars, and within V4's 38–62% zone (this sizes the
three `RETEST_MODE` cells before they are run)?

This is the go/no-go on sample size. With 22,882 candidate symbol-days rather
than 374 sessions, the underpowered-cell risk that motivated this measurement
is much reduced — but `RETEST_MODE = zone` is the deepest filter in the spec
and still needs counting before it is read as a result.

### 10.4 The R distribution, per stop mode
Median and p90 of `R / entry_price` for `structure`, `opposite` and
`range_frac`. This is VW9's open question asked in advance instead of in
hindsight. It sets `MAX_R_PCT`, and it may eliminate `opposite` outright.

### 10.5 Time to resolution
Bars from entry to stop and to each target level, split by outcome. Sets
`TIME_STOP_BARS` if anything sets it.

### 10.6 Session-block sanity
Trivial for ORB — everything is RTH by construction — but report it anyway, as
the standing check that no entry has leaked outside 09:45–15:55. VW9's
pre-market concentration was invisible in its headline for exactly one run
too many.

---

## 11. The go/no-go bar — fixed 2026-09-06, before any code exists

Written before results so it cannot be moved afterwards.

**ORB ships to paper trading only if ALL of the following hold, in the baseline
cell (`ORB_MINUTES=15`, `RETEST_MODE` best-of-three, `STOP_MODE=structure`,
`EXIT_MODE` best-of-five), at flat 100 shares, on honest fills:**

1. **Net positive after drop-top-3 AND drop-top-5.** Not the level alone.
   This is the check that killed VW9, the scale-out exit, and every trail
   candidate.
2. **A majority of symbols with ≥1 trade are profitable.** VW9's Setup B
   managed **18 of 58 (31%)** and was rejected. "More than half" is not a high
   bar; it is the minimum for the phrase "an edge" to mean anything.
   *(Corrected 2026-09-07: this criterion previously cited "20 of 55", which
   does not match `vw9.md`'s own table. See the note below — this criterion
   has a problem.)*
3. **Per-trade net exceeds measured friction with margin.**
   **Unblocked 2026-09-07.** This previously read "break-even is currently
   $7.79/trade, from n=2", which was a placeholder. Measured cost at 100
   shares is now:

   | | per round trip |
   |---|---:|
   | crossing the spread, measured on 18,552 fills (median) | $1.00 |
   | IBKR Tiered commission | $1.37 |
   | **total real cost** | **$2.37** |
   | what the engine charges (`SLIPPAGE_TICKS = 1` + commission) | $3.37 |

   The engine therefore overcharges by $1.00, so **a positive net per trade
   already clears real cost with $1.00 of margin built in.** The criterion is:
   **net ≥ $1.00 per trade at flat 100 shares**, which means gross clears
   measured cost roughly twofold. Stated as a number so it cannot be softened
   later; note that MC5's screened result is +$1.11/trade, so this bar is set
   where a real result actually sits rather than somewhere unreachable.
4. **≥ 100 trades.** Below that, drop-top-5 is removing 5% of the sample and
   the check stops meaning what it says.
5. **Positive in both halves of a temporal holdout**, split at the median date,
   split point not swept.
6. **The §10.2 population split does not reverse the sign.** If ORB only works
   on names an RTH screen would never have selected, it is not a strategy.
7. **No optimum on a grid boundary.** If the best cell sits on the edge of the
   search box, push the box out; a genuine optimum is interior.

**Any single failure is a rejection**, documented in
`claude/orb_first_results.md`. There is no partial pass and no "promising,
worth another sweep" — that phrase is how the scale-out exit survived four
studies before the fill audit killed it.

### 11.1 The prior — updated 2026-09-07, and it cuts both ways

The first out-of-sample run in this project's history landed on 2026-09-07
(`screened_universe_results.md`). Applied to this bar, at flat 100 shares on
the screened universe:

| | net/trade | drop-3 | drop-5 | symbols profitable | trades |
|---|---:|---:|---:|---:|---:|
| **MC5** | **+$1.11** | **+$4,700** | **+$2,537** | **706/1,791 (39.4%)** | 7,403 |
| MCL | −$0.53 | −$3,848 | −$4,829 | 326/890 (36.6%) | 2,408 |
| VW9_5M | −$4.96 | −$10,243 | −$11,775 | 207/699 (29.6%) | 1,477 |

**MC5 is the first strategy here ever to clear criterion 1.** It clears 3, 4
and 7 as well. **It fails criterion 2 at 39.4%** — below the majority this bar
requires, and not far above the 31% that rejected VW9's Setup B. Criteria 5
and 6 have not been tested.

So the base rate for clearing this bar in full is still **zero of four**.

**And criterion 2 has a problem that must be settled BEFORE ORB runs, not
after it.** "A majority of symbols profitable" is confounded with trades per
symbol. VW9's Setup B had 1.7 trades per symbol, where the measure approximates
the trade win rate. MC5 has 4.1, and a strategy with a 31% trade win rate and
right-skewed payoffs will leave most thinly-traded symbols negative even with a
genuinely positive expectancy. The criterion may be measuring sample size
rather than breadth.

It is **not** being relaxed here, because relaxing a pre-registered bar after
seeing a result fail it is precisely the sin this section exists to prevent.
The requirement is to replace it with a sample-size-independent breadth test —
the paired-by-symbol bootstrap this project already uses — **decided and
written down before ORB produces a number**, and applied retroactively to MC5
in the same pass so the two are judged identically.

**Expect rejection; build it to find out cheaply.**

---

## 12. What the report must contain

Standing rule: coverage in the same pass as the P/L.

**Coverage, per symbol-day** — bars loaded, first/last timestamp, count of
missing 1-minute intervals in 09:30–09:45, range-skip reason where applicable
(`too few bars` / `too narrow` / `too wide` / `no 09:30 bar`), open-position
flag at 16:00.

**Results**

- per-ticker trades / net / win rate
- **drop-top-N table (N = 1, 3, 5)** on the level and, for every comparison
  between cells, on the **delta**
- the cell grid: `ORB_MINUTES` × `RETEST_MODE` × `STOP_MODE` × `EXIT_MODE`,
  with the boundary check applied
- **R as a percentage of price**, median and p90, per stop mode
- entry-timestamp histogram — it should be a spike at 09:45–10:15 and a long
  thin tail; anything else means the trigger logic is wrong
- **the §10.2 population split** — P/L on symbol-days the RTH screen would have
  selected vs those it would not
- **the §10.2b leak cut** — entry rate and per-trade P/L on screened rejects
- **the downside break, measured but not traded** (§5.4)
- **the V2 fade measurement** (§7.4)
- count of bars containing both stop and target
- both sizing models (§9), plus the price-decile table
- per-exit-reason friction break-even against the measured live figure

---

## 13. Known limitations

- **Fifteen of twenty parameters are uncalibrated.** §8. Worse than VW9.
- **Only two of ten sources trade this universe.** §1.1. A 15-minute opening
  range on NQ and on a $4 low-float gapper are different objects, and eight of
  the ten videos are about the former.
- **Four of ten sources specify no stop at all**, and the stop is the
  parameter this universe punishes hardest. §6.
- **No source provides usable statistics.** §1.1. Two provide numbers; one is
  internally inconsistent by an order of magnitude and the other is a manual
  visual review with no trade count.
- **ORB's stage-2 leak exposure is unmeasured and is probably larger than the
  pre-market strategies'.** §3.2 item 3, §10.2b. This replaces "the backtest
  universe is the wrong universe", which was the top limitation until
  2026-09-07 and is now largely resolved.
- **Selection bias is reduced, not eliminated.** The universe is now
  rule-selected across 548 sessions rather than 407 hindsight pairs, but the
  screen's own thresholds — RVOL ≥ 5, range ≥ 10%, the 60/day cap — were chosen
  by a person and remain unmeasured guesses.
- **The calendar is not out-of-sample.** The screen covers 2024-07-01 to
  2026-09-04, which overlaps everything else here.
- **Split-adjusted prices do not apply to `bar_cache_db`** — it is built from
  the raw Databento archive, unlike the IB-sourced `bar_cache/`. Do not mix
  the two directories. This is an improvement on the original text, which
  carried the IB adjustment caveat.
- **RTH fills are more believable, not proven.** §0's argument is that ORB's
  orders are of a type the venue actually supports, which removes a known
  fiction. It does not establish that the modelled slippage is right, and only
  live fills settle that. RTH's spread advantage is 1.4×, not structural.
- **Order count is unmodelled and is the live threat to any thin edge.**
  `screened_universe_results.md` §3.2: MC5's edge disappears between three and
  four orders per round trip, and the real report averages eleven. ORB inherits
  this exactly.

---

## 14. Next, in order

1. **§10.2 first** — the RTH-screen overlap. Cheapest measurement here, the
   only one that can invalidate the premise before any entry logic exists, and
   as of 2026-09-07 it is actually runnable.
2. **§10.2b** — ORB's own stage-2 leak. New, and the reason to run it early is
   that a strategy trading the day's range is structurally more exposed to a
   filter that read the day's range.
3. **§10.1 and §10.3** — range distribution and trigger counts. Sets
   `MIN_RANGE_PCT` / `MAX_RANGE_PCT` / `ENTRY_BUFFER_PCT`.
4. **§10.4** — R distribution per stop mode. May eliminate `opposite` before
   it is ever run.
5. **§10.5** — time to resolution.
6. **Settle criterion 2** (§11.1) before any ORB P/L exists, and re-score MC5
   under whatever replaces it.
7. Write `strategy/orb/orb.py` with `STRATEGY_NAME = "ORB"`, the price band
   enforced from the first commit, and `gap_fills` / `seed_peak_with_bar_high`
   defaults matching the corrected model in §9.
8. **Unit-test the state machine on hand-built bars before any backtest**: a
   clean upside close; a wick that exceeds the range but closes inside; a
   session with no 09:30 bar; a range narrower than `MIN_RANGE_PCT`; a retest
   that fails and closes below `orb_low`; a bar containing both stop and
   target; a gap-through stop; a session that ends with the position open.
   The `if trail_confirm_bars > 0:` regression — a test on a *parameter* that
   silently dropped 46 trades — was caught by a test and not by the numbers.
9. Run the grid. Apply §11 exactly as written.
10. Write `claude/orb_first_results.md` with the verdict, whichever way it
    goes, and update `PROGRAM_INDEX` §2 in the same pass.

---

*Rules synthesised from ten publicly posted educational videos, each read in
full and reported independently. Where they disagree, §1.2 records which side
this spec took. None of the ten presents a logged, verifiable track record.
Nothing here is validated until step 9, and §11 says what validation means.
Corrections of 2026-09-07 are marked in place; the go/no-go bar itself was not
relaxed.*
