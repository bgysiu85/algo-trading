# VW9 — VWAP + 9 EMA momentum strategy, full session (04:00–20:00 ET)

Spec written 2026-09-03. **Code not yet written.** Sibling to
`claude/ema15_full_day_strategy_spec.md` (E15) and built from the convergent
findings in `claude/ema_source_comparison.md`.

Rules synthesised from the two sources in that set that use VWAP + a single fast
EMA as their whole indicator suite — Humbled Trader (S4) and Jdub Trades (S6) —
with the stock-selection, volume and level discipline from Warrior Trading
(S3/S5), who trade this universe.

| | |
|---|---|
| Universe | Same as MCL — $2–$20, RVOL(1D) ≥ 5×, float < 20m, top-2 pre-market gainer |
| Direction | **Long only** |
| Timeframes | **5-minute and 15-minute, both tested** |
| Session | 04:00–20:00 ET, continuous |
| Indicators | Session VWAP, 9 EMA. Nothing else. |
| Deliverable | This spec; code after review |

---

## 0. Why this exists — the warm-up arithmetic

E15's blocking problem is that a 20-period EMA on 15-minute bars is undefined
until 09:00 ET, which is after the window that has carried every dollar of
measured edge so far. VW9 exists because dropping the slow EMA moves that
boundary a long way earlier.

| Config | Slowest input | First bar it is defined | Binding constraint |
|---|---|---|---|
| E15 (9/20 EMA, 15m) | EMA20 = 20 bars | **09:00 ET** | EMA20 |
| **VW9-15** (VWAP + 9 EMA, 15m) | EMA9 = 9 bars | **06:15 ET** | EMA9 |
| **VW9-5** (VWAP + 9 EMA, 5m) | EMA9 = 9 bars | **04:45 ET** | EMA9 |

VWAP itself has no warm-up in the "undefined" sense — it has a value from bar 1
— but see §2.2: it is *meaningless* for the first two or three bars, because
with one bar of data VWAP simply equals that bar's typical price. Treating it as
usable from 04:05 would manufacture signals out of a single print.

Against `claude/momentum_confluence_session_window_test.md`, which found
04:00–06:30 carried 93% of V7's P/L:

- **VW9-5 reaches into that window with about 105 of its 150 minutes usable.**
- VW9-15 catches only the last 15 minutes of it.
- E15 catches none of it.

That single row is the reason for building VW9, and it is also the reason the
5-minute variant is the one to watch. If the pre-market edge is real, VW9-5
should see it and VW9-15 should not — which makes the pair a test of the
session-window finding as well as a test of the strategy.

**The wall-clock figures above assume every interval prints a bar.** On a thin
name they are lower bounds; report the actual timestamp of bar 9 per pair, as
required in §8.

---

## 1. What the strategy is, in one paragraph

Price above VWAP means buyers control the session; price above the 9 EMA means
they control the last few bars. Trade only when both are true. Enter either when
price reclaims the pair after being below (a reclaim), or when an existing
uptrend pulls back to the 9 EMA and resumes (a retest). Confirm with a candle
close, never a touch. Stop below the structure that defined the entry. Exit at a
fixed 1:2, or by riding the 9 EMA, depending on the variant under test. Losing
VWAP ends the trade regardless.

---

## 2. Indicators

### 2.1 The 9 EMA

`ta.ema(close, 9)`, undefined until 9 completed bars. Implement to Pine's
definition and verify against an independent loop implementation, as was done
for RSI/MFI/MACD in `mcl_paper_trader.py`.

### 2.2 Session VWAP

```
vwap[t] = Σ(typical_price[i] × volume[i]) / Σ(volume[i])   for i = anchor..t
typical_price = (high + low + close) / 3
```

**Anchor: 04:00 ET**, the first bar of the session, carried unbroken through
09:30 and 16:00 to 20:00. This is deliberate and it is the single most
consequential choice in the spec.

On this universe the pre-market move *is* the move. A VWAP re-anchored at 09:30
discards the volume that formed the entire run and produces a line that sits
just under the opening price — meaningful for a large cap, close to useless for
a name that went from $3 to $18 before the bell. Anchoring at 04:00 makes VWAP
the session's true volume-weighted average.

The cost is that the strategy's VWAP is **not** the VWAP most platforms draw by
default during RTH, and therefore not the line other traders are reacting to
after 09:30. Since the S3/S5 argument for these levels is that they work
*because* everyone watches the same one (see D6 in the comparison doc), this is
a genuine trade-off, not a free choice.

`VWAP_ANCHOR` is therefore a parameter — `0400` (default) | `0930` | `both` —
and the `both` mode computes two series and logs the distance to each, so the
question gets answered with data instead of argument.

**VWAP is not usable on bar 1.** With one bar, VWAP equals that bar's typical
price and "price above VWAP" is a coin flip on where the bar closed within its
own range. Require `MIN_VWAP_BARS` (default 3) completed bars *and*
`MIN_VWAP_DOLLAR_VOL` (default $50,000) of cumulative session dollar volume
before any VWAP-dependent condition may evaluate true. Both are uncalibrated —
see §6.

### 2.3 ATR

`ta.rma`-based ATR, 14 bars, as the unit for every threshold. Same reasoning as
E15: a universe of $2–$20 names moving 20–800% in a session has no stable dollar
scale. Note ATR14 is itself undefined until bar 14, which on 15m is 07:30 — so
**any rule expressed in ATR silently inherits a later start than the 9 EMA.**
Where an ATR-based threshold would gate an otherwise valid early signal, fall
back to a percentage-of-price form of the same rule and flag the row. This is
easy to get wrong and would quietly delete the pre-market trades this strategy
exists to capture.

---

## 3. The regime gate

Adapted from S6's four-state ladder, long-only, so two of the four states are
merely "not now".

| State | Condition | Long entries | Open position |
|---|---|---|---|
| **STRONG** | `close > vwap` and `close > ema9` | **Allowed** | Hold |
| **WEAK_BULL** | `close > vwap` and `close <= ema9` | Blocked | Hold |
| **BEARISH** | `close <= vwap` | Blocked | **Exit** |

The hard rule underneath: **never hold a long below VWAP.** S6 states it as a
rule of thumb; here it is the hard exit in §5.3.

Note what this gate does and does not do on this universe, because it is easy to
over-credit it: on a name running +500% intraday, price is above VWAP from
04:30 onward and the gate never blocks anything. It binds on the mediocre and
failing names, not the winners. **Its value is expected to be trade-count
reduction, not signal improvement** — which is exactly the shape of the
6,000-share volume floor and the `armBars` rule, one of which helped and one of
which did not. Measure it: report P/L with the VWAP gate disabled in the same
run.

### 3.1 Optional structure filter

`REQUIRE_HH_HL` (default `False`). When on, requires the last two swing highs
and last two swing lows to be ascending — S2's "1-2-3" confirmation, and S6's
market-structure requirement. Off by default because it adds two more
uncalibrated swing-detection parameters to a spec that already has enough.

---

## 4. Entries

Two setups. Both require state `STRONG` on the trigger bar and both are
confirmed by a **candle close** — the one point on which all six sources agree
(C3 in the comparison doc).

### 4.1 Setup A — VWAP reclaim

The transition trade. Fires when the session flips from bearish to bullish.

1. Price has been in `BEARISH` for at least `MIN_BELOW_BARS` (default 2) bars.
2. A bar closes **above both** VWAP and the 9 EMA.
3. That bar is the entry, subject to §4.3.

`entry_ref` = that bar's close. `structure_low` = the lowest low of the
`BEARISH` stretch, capped at the last `RECLAIM_LOOKBACK` (default 6) bars.

### 4.2 Setup B — 9 EMA retest

The continuation trade, and the one all four momentum sources centre on.

1. State has been `STRONG` and price has made a session high within the last
   `IMPULSE_LOOKBACK` (default 10) bars.
2. Price pulls back: one or more bars close below the 9 EMA, **while still
   closing above VWAP** (state `WEAK_BULL`). A pullback that closes below VWAP
   is not a pullback, it is a failure — abandon the setup.
3. The pullback is controlled: no bar with `(close[t-1] − close[t]) >
   PULLBACK_CTRL_ATR × atr14` (default 1.5).
4. The pullback is prompt: ≤ `MAX_PULLBACK_BARS` (default 6) bars.
5. A bar closes back **above** the 9 EMA. That bar is the entry, subject to
   §4.3.

`entry_ref` = that bar's close. `structure_low` = lowest low of the pullback.

Note that Setup B never requires price to *touch* the 9 EMA on a wick — the
close is what defines the pullback and the close is what defines the resumption.
This follows S4 directly, where an entry was declined for the whole session
because price traded above the indicators repeatedly without ever closing above
them.

### 4.3 Gates applied to every entry

| Gate | Rule | Default |
|---|---|---|
| **Liquidity** | Trigger bar dollar volume ≥ `MIN_TRIGGER_DV_PER_MIN` × bar minutes | see §6 |
| **Pullback volume** | (Setup B) largest down-bar volume in the pullback must not exceed the largest up-bar volume of the impulse | on |
| **Extension** | `(close − ema9) / atr14 <= MAX_EXT_ATR` | 2.0 |
| **Overhead level** | Distance to the nearest level in §4.4 must be ≥ `MIN_HEADROOM_R` × R | 1.0, **off by default** |
| **Re-entry** | ≥ 1 bar since the last exit; ≤ `MAX_ENTRIES_PER_SESSION` | 4 |

The **pullback volume** gate is S3/S5 and S4's shared warning sign — a
high-volume red candle inside a pullback means real selling, and S4 judges a
bounce specifically by comparing its volume against the preceding decline. E15
has no equivalent; this is one of the changes the comparison doc recommended.

The **extension** gate is C4, the one rule every source states independently:
do not enter an extended move; wait for price to come to the 9 or the 9 to come
to price.

**Re-entry is allowed by design.** This is the deliberate difference from E15:
VW9 implements the "window" model (D10) — while the regime is `STRONG`, every
qualifying pullback is tradeable. E15 takes one trade per crossover. Running
both gives the comparison for free.

### 4.4 Context levels

Computed per pair, logged on every trade whether or not the gate is on:

- previous session's high and low
- pre-market high as at 09:30 (for RTH and post-market entries)
- the opening 5-minute range high (09:30–09:35)
- the daily 200 EMA

Four of six sources mark levels like these before entering, and S3's pre-market
routine on a gapping small cap is specifically to find where the daily 200 sits,
because a nearby one is a reason *not* to buy. `MIN_HEADROOM_R` is off by
default so the first run measures whether trades that fired into a level
actually did worse, rather than assuming it.

---

## 5. Exits

### 5.1 Stop

```
stop = structure_low − STOP_BUFFER_ATR × atr14      (default 0.10)
R    = entry − stop
```

### 5.2 Target — three variants, all run in the same pass

| `EXIT_MODE` | Rule | Source |
|---|---|---|
| `fixed_2r` (baseline) | Exit at `entry + 2R` | S1, S6 |
| `ride_ema9` | Exit on the first bar that **closes below** the 9 EMA | S4 |
| `trail_atr` | Trail `TRAIL_ATR` × atr14 (default 2.0) off the high since entry | MCL V4 |

`fixed_2r` is the baseline because it is what the sources specify. But the
comparison doc's D5 and the project's own V3→V4 result (6% fixed → 5% trailing,
+$339 → +$931) both say a fixed target caps exactly the runners this universe is
screened to produce. **All three run in the same pass**, not in a later one.

### 5.3 Hard exits, in priority order

1. **Stop hit.**
2. **VWAP lost** — any bar closing below VWAP exits the position at that close,
   regardless of mode or P/L. This is the rule the whole strategy rests on.
3. **Session end** — flat at the 19:45–20:00 bar's close.

**Intrabar ambiguity: if a bar's range contains both stop and target, assume the
stop filled first.** Report the count of such bars; on 15-minute bars on these
names it will not be rare.

---

## 6. Parameters

| Name | Default | Basis | Calibrated? |
|---|---|---|---|
| `EMA_FAST` | 9 | S1, S3, S5, S6 (S4 uses 8) | n/a |
| `BAR_MINUTES` | **5 and 15** | this test | n/a |
| `SESSION` | 04:00–20:00 ET | Ben | n/a |
| `VWAP_ANCHOR` | `0400` | §2.2 | n/a |
| `MIN_VWAP_BARS` | 3 | **guess** | **NO** |
| `MIN_VWAP_DOLLAR_VOL` | $50,000 | **guess** | **NO** |
| `MIN_BELOW_BARS` | 2 | **guess** | **NO** |
| `RECLAIM_LOOKBACK` | 6 | **guess** | **NO** |
| `IMPULSE_LOOKBACK` | 10 | **guess** | **NO** |
| `PULLBACK_CTRL_ATR` | 1.5 | carried from E15 | **NO** |
| `MAX_PULLBACK_BARS` | 6 | **guess** | **NO** |
| `MAX_EXT_ATR` | 2.0 | **guess** | **NO** |
| `STOP_BUFFER_ATR` | 0.10 | carried from E15 | **NO** |
| `MAX_ENTRIES_PER_SESSION` | 4 | **guess** | **NO** |
| `MIN_TRIGGER_DV_PER_MIN` | **measure first** | see below | **NO** |
| `MIN_HEADROOM_R` | 1.0, gate off | §4.4 | **NO** |
| `TARGET_R` | 2.0 | S1, S6 | n/a |
| `TRAIL_ATR` | 2.0 | **guess** | **NO** |

**Twelve of eighteen parameters are uncalibrated.** That is worse than E15's
six and it is the main cost of this spec. §7 exists to fix it before any P/L
number is read as meaningful.

**On `MIN_TRIGGER_DV_PER_MIN` specifically — do not guess this one.** The
volume-floor analysis recommended ~$20,000 of dollar volume on a *30-second*
bar, which naively scales to $40,000/minute, i.e. $200k per 5-minute bar and
$600k per 15-minute bar. That may be right, or the $20k figure may have been
pitched for a different purpose and not intended to scale linearly. Measure the
actual distribution (§7.2) and set it from that. Getting this wrong in the
strict direction silently deletes the thin low-float names — which is precisely
the failure the volume-floor test documented, where eight of 21 names produced
zero trades and the excluded names held ~$872 of winners against ~$115 of
losers.

**Do not sweep EMA lengths per name.** D6 in the comparison doc, plus this
project's own record: the `armBars` relaxation and the share-count floor both
failed by re-tuning a rule whose restrictiveness was doing the real work. 9 is 9.

---

## 7. The 5 vs 15 minute test — design

The V4→V5 comparison in `claude/momentum_confluence_strategy.md` was
contaminated because two things changed at once: the timeframe halved *and*
every indicator length halved in wall-clock terms, and the write-up correctly
flagged that the comparison was not like-for-like. **Do not repeat that.**

A 9 EMA spans 45 minutes on 5-minute bars and 135 minutes on 15-minute bars.
Those are different strategies wearing the same number. So run four cells, not
two:

| | 5-minute bars | 15-minute bars |
|---|---|---|
| **Same length** (EMA 9) | **A** — VW9-5 baseline | **B** — VW9-15 baseline |
| **Matched wall-clock** | **C** — EMA 27 on 5m (= 135 min) | **D** — EMA 3 on 15m (= 45 min) |

- **A vs B** is the headline question: which timeframe is better as each is
  normally traded?
- **A vs D** and **B vs C** isolate the *bar-size* effect at constant wall-clock
  lookback — i.e. how much is granularity worth, independent of smoothing?
- **A vs C** and **B vs D** isolate the *lookback* effect at constant bar size.

Cell D (EMA 3 on 15m) will be jumpy and may be useless; run it anyway, because
its uselessness is what makes A vs B interpretable. VWAP is anchored to the
session, not to a bar count, so it is comparable across all four cells by
construction — which is a quiet advantage of this strategy over E15 for exactly
this kind of test.

Everything else is held identical: same 407 pairs, same session, same gates,
same fill model.

---

## 8. Pre-flight measurements — before writing strategy code

### 8.1 Bar availability, per timeframe and session block

What fraction of intervals produce a bar? Report the wall-clock timestamp of
bar 9 per pair for both timeframes. If the median bar 9 on 5-minute data lands
at 06:00 rather than 04:45, the headline claim in §0 is wrong and this document
needs correcting before anything is built.

### 8.2 Dollar volume per bar

Median and 10th percentile, by session block and timeframe. Sets
`MIN_TRIGGER_DV_PER_MIN`. Explicitly check what fraction of *names* would be
eliminated entirely at each candidate threshold — the volume-floor failure mode.

### 8.3 Setup counts

How many Setup A and Setup B triggers fire per pair per session at each
timeframe, before gates? This sets the sample size and is the go/no-go. E15's
equivalent gate was ~0.3 completed setups per pair; VW9 should produce
considerably more, since it re-enters and requires no crossover. If VW9-5
produces more than ~5 triggers per pair per session the gates are too loose and
the strategy is closer to noise-trading than to the sources' intent.

### 8.4 Distributions

`(close − ema9)/atr14` at trigger, pullback depth and length, bars below VWAP
before a reclaim, and time-to-target. These replace the twelve guesses.

### 8.5 VWAP degeneracy check

For each pair, the bar at which |close − vwap| / close first exceeds 1%. If that
is routinely bar 5 or later, `MIN_VWAP_BARS = 3` is too permissive and the early
pre-market signals VW9 exists to capture are being generated against a VWAP that
is still just the opening print.

---

## 9. Execution model

Identical to E15, and unchanged for good reason: outside RTH, IBKR accepts **Day
Limit orders only** for US stocks — no market orders, no native stops, no native
trailing stops. That governs 04:00–09:30 and 16:00–20:00. Every stop, target and
trail is software-managed and breached with a marketable limit, as
`mcl_paper_trader.py` already does.

| Field | Meaning |
|---|---|
| `ref_price` | Trigger bar close — what the source rules assume |
| `fill_price` | Next bar's open + modelled slippage |
| `slippage_vs_ref` | Difference per share; comparable to the paper trader's column |
| `session_block` | `PRE` / `RTH` / `POST` — slippage reported per block |

Commission $0.005/share. Sizing `min(100 shares, 40% of equity / price)`,
unchanged from MCL so results are comparable across strategies.

**The pre-market fill problem is worse for VW9 than for E15, precisely because
VW9 succeeds at reaching pre-market.** The session-window test's honest reading
was that V7's +$924 was largely an artifact of trading hours the backtest cannot
model realistically. VW9-5 goes back into those hours deliberately. Any P/L it
reports from 04:00–06:30 carries that same warning, in bold, and the paper
trader's measured slippage is what settles it.

---

## 10. What the report must contain

Standing rule: data coverage in the same pass as the P/L.

**Coverage, per pair and timeframe** — bars loaded; first/last timestamp;
**wall-clock time of bar 9**; count of intervals with no bar; open-position flag.

**Results**

- per-ticker trades / net / win rate
- **drop-top-N concentration table** (N = 1, 2, 3) — the number that matters
  most, given V7 was +$890 and negative once its three best names were removed
- **histogram of entry timestamps**, which is the direct test of §0
- trades and P/L split by `PRE` / `RTH` / `POST`
- **the four-cell table from §7**
- Setup A vs Setup B broken out separately — they are different trades and may
  well have opposite signs
- the three `EXIT_MODE` variants side by side
- **P/L with the VWAP gate disabled**, per §3, so the gate's contribution is
  measured rather than assumed
- count of bars containing both stop and target

---

## 11. Known limitations

- **The VWAP gate is non-binding on the biggest winners.** §3. On a name that
  runs 500% it is above VWAP all day and the gate filters nothing. Expect its
  contribution to be trade-count reduction on mediocre names.
- **The 04:00 VWAP anchor is not what other traders see after 09:30.** §2.2. If
  the mechanism is that these levels work because everyone watches them, the
  chosen anchor partly opts out of that mechanism for 26 of the 64 RTH bars.
- **Twelve uncalibrated parameters.** §6.
- **Pre-market fills remain fictional until measured.** §9. This is the binding
  constraint on the whole project, not just on VW9.
- **Selection bias is inherited and unfixed.** The 407 pairs are names chosen
  because they ran. Only forward testing on contemporaneous scanner picks fixes
  it.
- **ATR-based thresholds start later than the 9 EMA.** §2.3. Easy to get wrong
  in a way that silently removes the pre-market trades.
- **The sources are hypothesis generators, not evidence.** None of the six
  presents a logged, verifiable track record with sample size and drawdown, and
  all of them sell something.

---

## 12. Next, in order

1. **§8.3 setup counts** at both timeframes. Go/no-go, and it is cheap.
2. **§8.1, §8.2, §8.5** — set `MIN_TRIGGER_DV_PER_MIN`, `MIN_VWAP_BARS`,
   `MIN_VWAP_DOLLAR_VOL` from measurement. §8.5 in particular can invalidate the
   §0 claim that this strategy reaches 04:45.
3. **§8.4** — set the remaining nine parameters from distributions.
4. Write `strategies/vw9.py` against the `DataSource` / `ExecutionVenue` shape
   from step 2 of `claude/repo_reorg_and_github_plan.md`, final name from the
   start so step 3 is a pure `git mv`.
5. Unit-test the state machine on hand-built bar sequences: a clean reclaim; a
   reclaim that closes back below VWAP next bar; a pullback that breaches VWAP
   mid-pullback; an uncontrolled pullback; an extended-move rejection; a bar
   containing both stop and target; and a session where VWAP is degenerate for
   the first four bars.
6. Backtest all four cells of §7 × three exit modes on the 407 pairs.
7. Compare against E15 and V7 **on the RTH subset only** first — it is the one
   window all three can trade and the only one where fills are believable — then
   report the pre-market block separately with the §9 warning attached.

---

*Rules synthesised from six publicly posted educational videos, compared in
`claude/ema_source_comparison.md`. Nothing here is validated until step 6.*
