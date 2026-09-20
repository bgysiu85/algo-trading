# Large-cap strategy specs — L1 (intraday momentum) and L2 (diversifier)

**Created:** 2026-09-11
**Status:** SPECIFICATION ONLY. Nothing here has been built, backtested or measured.
**Evidence base:** `largecap_evidence_20260911.md`. Read that first — it is the reason this
spec looks the way it does rather than the way Ben's question implied.
**Governing standards:** `PROGRAM_INDEX.md` §4.
**Scope note:** this chat writes specs only. No program logic under `D:\Trading` is touched here.

> ### UPDATED 2026-09-11 — parts of this spec have now been MEASURED
>
> `factor_correlation_result_20260911.md` ran the §3.4 check and several others on 120 liquid
> US large caps, 2007–2026. What changed:
>
> - **§3.4 is ANSWERED.** Momentum vs short-term reversal correlation is **−0.12** (mean rolling
>   252-day), negative on 77% of days. A 50/50 blend cuts volatility **35%**. **The
>   diversification premise holds.** Both legs are flat over 19 years before costs, so the
>   *return* premise does not.
> - **§3.3 is SOFTENED.** No tail dependence, no excess joint drawdown, and correlation stays
>   negative in **every** VIX quartile including the most stressed. One genuine joint blow-up in
>   19 years (week of 2009-05-10, both legs ≈ −7%). Size for that week, not for the average.
> - **§3.1 arms A/B/C: use RSI(2), not RSI(14).** RSI(14) vs Bollinger %b measures **ρ = +0.911**
>   on our own universe (per-name median 0.912) — that arm is already settled. RSI(2) vs %b is
>   only **+0.696** and does carry independent information.
> - **§3.1's expected outcome is STRENGTHENED.** The raw Bollinger dip-buy shows **no edge**:
>   −0.010% excess per trade, t = −0.18 Newey-West, −0.064% after costs, and what edge appeared
>   was **2008 alone** (2016–2026 is −0.078%).
> - **NEW MANDATORY REQUIREMENT — see §3.1.** Up to **105 of 120** names trigger the Bollinger
>   entry on a single day. Concurrency must be capped and clustering measured, or the equity
>   curve is a leveraged long market bet in disguise.
> - **§3.2 (L2a) is DOWNGRADED** pending a proper share-turnover test — Medhat & Schmeling could
>   not be reproduced with an abnormal-turnover proxy.
> - **Method note for every backtest below:** use **date-level** observations, not pooled
>   (name, day) pairs. On the dip-buy test those two differ by the entire result.

**Design parameters set by Ben, 2026-09-11:**
liquid US large caps · 5-minute bars for the intraday strategy · 2–10 day holds for the
diversifier · long and short · US stocks only.

---

## 0. The honest summary

Ben asked about a Bollinger + RSI strategy. Three research passes say:

- **Bollinger and RSI are the same signal** (Spearman ρ = 0.95 on 66 years of S&P 500 data).
  Requiring both is threshold tuning across two correlated parameters, not confirmation.
- **Raw short-horizon mean reversion on liquid large caps is the configuration the literature
  most clearly rejects**: net −1.28%/month after institutional costs (Novy-Marx & Velikov,
  *RFS* 2016); break-even round-trip cost of 10 bps (Blitz et al.) against a realistic
  retail round trip of ~5 bps *before* commission.
- **In high-turnover large caps the documented short-horizon effect is momentum, not
  reversal** (Medhat & Schmeling, *RFS* 2022: univariate reversal t = −1.68, not significant;
  high-turnover momentum t = 4.74; largest-500 net of costs **+0.77%/month, t = 3.90**).

So this spec does three things:

1. **L1** builds the intraday momentum strategy, but around the **relative-volume selection
   effect** rather than the opening-range trigger — because the source paper's own numbers
   show the trigger is worth Sharpe 0.48 and the selection filter carries everything else.
2. **L2a** offers the diversifier with the best evidence, which is not mean reversion.
3. **L2b** specifies the Bollinger/RSI strategy Ben actually asked for, as a **pre-registered
   measurement expected to fail**, with the one modification (a VIX gate) that has
   peer-reviewed support — and with the redundancy test built in, because
   "Bollinger alone vs Bollinger + RSI on the same data" is the cheapest and most directly
   informative test available and it answers his original question with his own numbers.

**Build order: L1 → L2b (cheap, decisive, answers the actual question) → L2a (expensive, needs
a resolved margin answer).**

---

## 1. Blocking questions — resolve before any build

| # | Question | Why it blocks |
|---|---|---|
| **B1** | **Is Ben classified retail or wholesale at IBKR Australia?** | Retail clients face an **AUD 50,000 margin-borrowing cap**. A dollar-neutral long/short book of 40–100 names (L2a) is not constructible under it. This determines whether L2a is even possible. |
| **B2** | **Current day-trade status in Client Portal.** | PDT was eliminated **4 June 2026** (FINRA Notice 26-10), but IBKR's AU pages still carry legacy $25k text. Confirm rather than assume. |
| **B3** | **Fixed or Tiered commissions?** | Fixed is cheaper when crossing the spread (L1); Tiered ~40% cheaper when posting (L2). One structure per account. If both strategies share an account, Fixed. |
| **B4** | **Historical 5-minute bar source.** | IBKR caps 5-min requests at one week each, 60 requests per 10 min (≈15 days of pulling for an S&P 500 universe) and serves **no delisted securities** — a survivorship trap. Alpha Vantage `TIME_SERIES_INTRADAY` is already connected; Polygon/Databento are the paid options. |
| **B5** | **Non-professional market-data status confirmed?** | NBBO is $4.50/month non-pro, **$125/month pro**. The free Cboe One/IEX feed is not the NBBO and will make live costs diverge from the model. |

---

## 2. L1 — Intraday momentum, liquid large caps

### 2.1 What it is, and what it deliberately is not

It is **not** an opening range breakout, despite using an opening range. The source paper's
own table gives unfiltered ORB a **Sharpe of 0.48** and the top-20-relative-volume version a
Sharpe of 2.81 — **the selection filter carries 100% of the result.** L1 therefore treats
relative volume as the signal and the range break as one of several pre-registered triggers.

This also matches what this project already found: `warrior_5_selection_in_practice.md` and
`warrior_census_20260910.md` both concluded Cameron's edge sits in which names he picks, not
in the trigger he uses.

### 2.2 Universe filter (computed pre-open, daily)

```
country      = US
type         = common stock, NYSE / Nasdaq / AMEX
index        = Russell 1000 constituent AS OF THAT DATE   # point-in-time, not today's list
price        > $10.00                                     # avoids the per-share commission trap
adv_14d      >= 1,000,000 shares
atr_14d_pct  >= 0.80%  of price                           # NOT a dollar ATR — see note
```

**Note on the ATR floor.** The source paper uses `ATR > $0.50`, which is meaningless on a $500
stock and binding on a $20 one. A percentage floor is the correct construction and is a
deliberate departure. `0.80%` is a placeholder and must be **registered before the first run**,
with a boundary check at 0.4 / 0.8 / 1.2 / 1.6%.

**Point-in-time index membership is mandatory.** Using today's Russell 1000 list on 2019 data
is survivorship bias and will manufacture an edge on its own.

### 2.3 Selection — the actual signal

```
rvol_open = volume(09:30-09:35 ET) / mean(volume(09:30-09:35 ET) over prior 14 sessions)

require   rvol_open >= 1.00
rank      descending by rvol_open
take      top N                    # N = 20 registered; boundary check 5 / 10 / 20 / 40
```

### 2.4 Entry — three pre-registered triggers, all reported

Register all three **before the first run**. Report all three. Do not pick one after seeing
results — that is the leak PROGRAM_INDEX §4 exists to prevent.

| | Trigger |
|---|---|
| **T1** (primary — the published rule) | Stop order at the 09:30–09:35 range high (long) or low (short). Direction = sign of the first 5-minute candle. **No trade if that candle is a doji** (define: \|close − open\| < 10% of the candle's range). |
| **T2** (the QQQ paper's apparent mechanic) | Market order at the open of the second 5-minute bar, direction = sign of bar 1. |
| **T3** (control) | Random direction, same universe, same selection, same sizing. **If T1 does not beat T3 after costs, the trigger contributes nothing and the whole construction is a volume-selection study.** |

T3 is not padding. Given §2.1, it is the single most informative comparison in the spec.

### 2.5 Stop

```
stop_distance = max(
    0.10 * atr_14d,                      # the published rule
    3.0 * current_quoted_spread          # MANDATORY FLOOR - see note
)
```

**The floor is not optional.** Brusco's replication showed the published QQQ edge breaks even
at ~2.2¢/share slippage against a ~1¢ spread. A stop narrower than a few spreads is not a
stop — it is a guaranteed round trip paid to the market maker. Any backtest that lets the stop
go inside the spread is measuring nothing.

### 2.6 Exit

- **EOD flat at 16:00 ET via MOC/LOC.** No profit target.
- MOC is also the cheapest execution available: $0.0016/share under Tiered versus $0.0030 to
  remove liquidity intraday, and no spread to cross.

### 2.7 Sizing

```
risk_per_position  = 0.50% of capital on the stop distance
max_concurrent     = 4                  # NOT 20 - see B1
gross_exposure_cap = per B1 answer
```

The paper's 4× leverage and 20 concurrent positions are not available under an AUD 50,000
retail borrowing cap. **Concurrent-position count must be set from B1, not from the paper.**

### 2.8 Cost model — non-negotiable

| Component | Value |
|---|---|
| Commission | Fixed: $0.005/share each side, $1.00 order minimum |
| SEC fee | $0.0000206 × sale value, **sell side only** |
| FINRA TAF | $0.000195/share sold (2026 rate; escalates to $0.000232 in 2027) |
| **Entry slippage** | **3 bps** (S&P 500) / **5 bps** (Russell 1000 ex-S&P), per side |
| **Stop-exit slippage** | **2× the entry figure.** Stops fill on the wrong side of a fast move. |
| MOC exit slippage | 0 bps (auction clears at one price), MOC fee $0.0016/share under Tiered |

### 2.9 SSR screen — mandatory on the short side

```
skip short entry if  low(today) <= 0.90 * close(prior_day)
                  or low(prior_day) <= 0.90 * close(prior_day - 1)
```

Rule 201 forbids a short sale at or below the national best bid for the rest of the trigger
day **and all of the next**. Without this screen the short-side backtest assumes fills that
were legally impossible — and the exclusions cluster exactly in the high-volatility days where
a short strategy expects its best results.

### 2.10 Pre-registered validation

All of these before looking at any headline number:

1. **Unfiltered vs top-N.** If top-20 RVOL does not beat unfiltered by a wide margin, the
   premise is wrong and L1 should stop.
2. **T1 vs T3 (random direction).** If T1 does not beat random after costs, there is no trigger
   edge — report that plainly.
3. **Opening-range boundary check: 5 / 15 / 30 / 60 min.** The source paper's Sharpe collapses
   2.81 → 0.21 between 5 and 30 minutes. **If 5 minutes is the only length that works, treat
   that as the paper's overfit reproducing, not as a finding.**
4. **Drop-top-N on both symbol and day**, on level and delta.
5. **Temporal holdout:** build on data through 2022, hold out 2023 – present, untouched.
6. **Paired-by-symbol bootstrap** for the headline comparison.
7. **Leak cut on both rate and quality.**
8. **Report average win, average loss and R.** A win rate without a paired reward figure is
   not a result.

### 2.11 Kill criteria — written down in advance

Stop work on L1 if **any** of these holds:

- After-cost Sharpe < 0.5 on the temporal holdout
- The 5-minute opening range is the only length that works
- T1 does not beat T3 after costs
- Results survive only when stop distance is allowed inside 3× the spread
- More than 50% of total P&L comes from a single calendar year

### 2.12 What to expect

The honest prior, given §1 of the evidence doc: the peer-reviewed benchmark
(Heston, Korajczyk & Sadka, *JF* 2010) found intraday cross-sectional continuation in US
equities goes **negative for every size bucket at every time of day** once the spread is
subtracted. L1 is worth running because the *selection* component has not been tested that way
and because the cost environment in 2026 is better than 2001–2005. But it should be entered
expecting a null result, and the value of the exercise is a clean, cheap, well-instrumented
null rather than another unmeasured strategy in production.

---

## 3. L2 — the diversifier

### 3.1 L2b (build first): Bollinger mean reversion, VIX-gated, with the redundancy test

This is the strategy Ben asked for, specified so that running it actually settles something.

**Universe**

```
Russell 1000 constituent, point-in-time
price     > $10
adv_14d   >= 1,000,000 shares
```

**Signal — daily bars, evaluated at the close**

```
bb_mid   = SMA(close, 20)
bb_sd    = STDEV(close, 20)
bb_lower = bb_mid - 2.0 * bb_sd
bb_upper = bb_mid + 2.0 * bb_sd

LONG  entry:  close < bb_lower  AND  close > SMA(close, 200)
SHORT entry:  close > bb_upper  AND  close < SMA(close, 200)
exit:         close crosses bb_mid   OR   holding period reaches 10 trading days
```

**The VIX gate** — the one modification with peer-reviewed support. Nagel (*RFS* 2012) finds
large-cap reversal returns are *"very close to zero"* unconditionally and reach only
~0.10%/day at the 95th percentile of VIX. So:

```
require  vix_percentile_rank(252d) >= 0.70      # registered; boundary check 0.5 / 0.6 / 0.7 / 0.8
```

**The redundancy test — the reason to run this at all**

Run three arms on identical data, identical costs, identical dates:

| Arm | Entry condition |
|---|---|
| **A** | Bollinger alone (as above) |
| **B** | Bollinger **AND** RSI(2) < 10 (long) / > 90 (short) — **use RSI(2); the RSI(14) version is already settled at ρ=0.911** |
| **C** | RSI(2) alone, no band |

If the ρ = 0.95 finding holds, **arm B will differ from arm A almost entirely in trade count
and barely at all in per-trade expectancy**, and arm C will look like a noisier version of A.
That single table answers Ben's original question — "is Bollinger + RSI a thing?" — with his
own data, at the cost of one backtest run.

**Stop.** Connors publishes no stop and states stops hurt performance. That is exactly why
every replication reports an uninterpretable win rate with an unbounded left tail. **This spec
requires a stop:** `2.5 × ATR(14)` from entry, registered, boundary-checked at 1.5 / 2.5 / 3.5
/ none. Report the "none" arm too — if the strategy only works without a stop, that is a
finding about tail risk, not a licence to run it unstopped.

**Concurrency cap — mandatory, added 2026-09-11.** Measured: the median signal day triggers
3 names, the 90th percentile 17, and the maximum **105 of 120** (2015-08-24). Cap concurrent
positions (registered, boundary-checked) and **report the distribution of concurrent positions
alongside every equity curve**. Without this the strategy is a leveraged long market bet on
exactly the days it is most active.

**Sizing and carry.** Long and short carry differently and it matters at this horizon:
financing a $75,000 long for 5 days on 50% margin costs **≈ $36.65** at the retail
~7.13% USD rate — about **5× the round-trip commission**. Shorts earn proceeds interest less a
~0.25–0.50% general-collateral borrow. **Model carry per position per calendar day, including
weekends.** Ignoring it will overstate long-side results by more than the commission.

**Pre-registered expectation.** On the evidence, this should fail after costs. Registering that
expectation in advance is what makes the result informative either way.

**Cost model:** as §2.8, but entries and exits can be posted rather than taken — model both a
marketable arm (3 / 5 bps per side) and a limit-at-close arm (MOC, 0 bps spread,
$0.0016/share). The gap between them is itself worth knowing.

**Kill criteria:** after-cost return < 0 on the temporal holdout; or arm B does not
meaningfully differ from arm A (which confirms redundancy and closes the question); or results
depend on the no-stop arm.

### 3.2 L2a: the diversifier with the best evidence — DOWNGRADED 2026-09-11, see §7 of the results doc

Stated plainly because the evidence is unusually clear. **Medhat & Schmeling (2022), *RFS*
35(3)** is peer-reviewed, cost-tested, and net positive in exactly Ben's chosen universe:

| Portfolio | Monthly | t |
|---|---:|---:|
| Short-term momentum, largest 500, **net of costs, ex end-of-month** | **+0.77%** | **3.90** |

**Construction:** monthly rebalance. Conditional double sort — first on prior-month share
turnover, then on prior-month return. **Long the high-turnover winners, short the
high-turnover losers.** Dollar-neutral, value-weighted, NYSE breakpoints.

**Why it diversifies L1** — on three axes, not one:

| | L1 | L2a |
|---|---|---|
| Horizon | intraday | monthly |
| Exposure | directional | dollar-neutral |
| Signal type | time-series | cross-sectional |

**Why it is second in build order:**

- It needs **40–100 simultaneous positions** to be the strategy that was tested. Under an AUD
  50,000 retail margin cap (**B1**) that is not constructible, and a cut-down 10-name version
  is a different strategy with no evidence behind it.
- Monthly rebalancing sits outside the 2–10 day window Ben specified.
- It is not what he asked for, and L2b answers his actual question more cheaply.

If B1 comes back **wholesale**, L2a moves ahead of L2b. If **retail**, L2a is parked until the
account structure changes.

### 3.2b Momentum-rotation candidates — added 2026-09-11

`diversifier_candidates_20260911.md` verified the three names that came out of the
r/algotrading thread. **All three are unlevered and cash- or futures-funded, so the AUD 50,000
retail margin cap (B1) does not bind on any of them** — which is the constraint that parks L2a.

| Candidate | Verdict |
|---|---|
| **Antonacci GEM (Dual Momentum)** | **REJECTED.** 2014–2026 out of sample: **8.4%/yr vs SPY's 13.6%** — twelve years, −5.2pp/yr, and the drawdown edge went too (−20% vs −24%). Its edge depends on ex-US beating the US, which has been absent since ~2010. Also the worst of the three for Australian tax: ~27% of gains realised inside 12 months, forfeiting the 50% CGT discount, while losses are quarantined. |
| **Time Series Momentum** (Moskowitz/Ooi/Pedersen, *JFE* 2012) | **Best remaining candidate.** Peer-reviewed, heavily replicated, documented crisis alpha, ~8–12 micro futures monthly. MCL is already traded here. |
| **Faber Asset Class Trend-Following** | **Lowest-effort candidate.** 5 ETFs, 10-month SMA, long-or-cash. Weaker evidence and underperforming since ~2009. |

> **Registration requirement for either survivor — from §4 of that doc.** Do **not** test
> Faber's 10-month SMA or TSMOM's 12-month lookback as *the* specification. ReSolve built 1,226
> GEM variants and found the published spec beat **only 61%** of them, with a 64-percentage-point
> average gap between the 95th and 5th percentile specs. Newfound found a 9-month lookback
> returning 43.1% where a 10-month returned 146.1% on identical data — **permanent artifacts,
> not noise that mean-reverts.**
>
> So: test the **grid**, report **where the published value sits in the distribution**, report
> the **ensemble**, and run the **rebalance-day grid** before committing. This applies to MCL's
> own `TRAIL_PCT` too — see §4 of the diversifier doc.

### 3.3 When the diversification fails — state it in the spec

Momentum and mean reversion decorrelate in normal conditions and **correlate to 1 in
deleveraging events.** Khandani & Lo document the daily contrarian losing **−1.16%, −2.83%,
−2.86%** on consecutive days in the week of 6–10 August 2007 — roughly −25% of assets at 8:1
leverage — while long/short equity and quant long-only funds took correlated losses
simultaneously, caused by managers with common factor exposures unwinding at once.

**Implication for risk sizing:** do not size the pair on their historical correlation.
Size each on the assumption that both can have their worst week at the same time.

### 3.4 One cheap thing worth doing first — DONE 2026-09-11, see `factor_correlation_result_20260911.md`

The correlation between short-term reversal and momentum factors could not be verified from
published sources. It is directly computable from Ken French's `ST_Rev` and `Mom` daily factor
files in about ten lines of pandas. **That is a ten-minute answer to whether the diversification
premise holds at all**, and it should be run before either L2 arm is built.

---

## 4. What the build chat needs

Read in this order:

1. `largecap_evidence_20260911.md` — the evidence, including everything that argues against
2. This document
3. `PROGRAM_INDEX.md` §4 — the evidence standards every measurement above refers to

Then, in order:

1. Answer **B1–B5** (§1). B1 and B4 are genuinely blocking.
2. Run the French-factor correlation check (§3.4) — ten minutes.
3. Build **L1** with all of §2.10 registered before the first run.
4. Build **L2b** with arms A/B/C registered before the first run.
5. Revisit **L2a** only if B1 returns wholesale.

**Nothing in this document is a result.** Every number quoted belongs to someone else's study,
and the ones that matter most are the negative ones.
