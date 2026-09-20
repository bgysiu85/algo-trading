> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it: MCL's headline went +$1,567 → +$161 and MC5's +$20,156 →
> −$400, on identical trades. Only the price they were booked at changed.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# Momentum Confluence Long (MCL) — spec, results & diagnosis

Rules from Ben, 2026-09-01. Pine v6, driven through the TradingView MCP on bens-proart.

## Core idea

Long-only, pre-market only (04:00–09:30 ET), small-cap low-float runners.

**Universe (screened outside the script):** $2–$20 · RVOL(1D) ≥ 5× · float < 20m · top-2 pre-market gainer.
Pine has no float data and no cross-sectional ranking, so the script carries a hardcoded
ticker→qualifying-date map and runs one name at a time.

## Version history

| | TF | Entry | Exit |
|---|---|---|---|
| **V1** | 1m | MACD *crosses* signal & > 0 · BBW↑ · MFI↑ · RSI↑ · vol +5% | MACD **and** BBW **and** MFI past apex and falling; 6% fixed stop |
| **V2** | 1m | MACD > signal & > 0 (state) · BBW↑ · MFI↑ · RSI↑ · vol +5% | same |
| **V3** | 1m | as V2, **BBW removed** | as V2, BBW removed |
| **V4** | 1m | as V3, **volume ≥ 3× previous bar** | **after apex, ANY of MACD/MFI/RSI turning down; 5% trailing stop; no fixed stop** |
| **V5** | **30s** | as V4, **+ previous bar volume ≥ 6,000 shares** | as V4 |

Common: "gradient" = `value > value[3]`; "apex" = the 20-bar high is ≥1 bar behind; sizing
`min(100 shares, 40% equity)`; entry at signal-bar close, $0.005/share, 1 tick slippage;
flat at 09:30.

## Results — 21 tickers, 6 pre-market sessions (Aug 2026)

| Ticker | V2 | V3 | V4 net | V5 trades | **V5 net** | avg 30s bar vol | passes 6k floor |
|---|---|---|---|---|---|---|---|
| WETO | −$87 | −$111 | −$18 | 1 | −$3 | 2,706 | 7% |
| MOVE | +$120 | +$56 | +$60 | 2 | **+$102** | 10,592 | 53% |
| AEHL | +$30 | +$14 | +$71 | 4 | +$57 | 15,573 | 47% |
| XAIR | −$3 | −$3 | +$114 | 1 | +$79 | 31,744 | 43% |
| XPON | −$55 | −$66 | −$17 | 0 | $0 | 1,383 | 4% |
| QNRX | +$115 | +$43 | −$74 | 5 | +$3 | 22,872 | 80% |
| XLAB | +$153 | +$90 | +$166 | 1 | +$99 | 3,969 | 18% |
| PPCB | +$166 | +$166 | +$93 | 3 | +$72 | 228,005 | 98% |
| YMT | −$24 | −$24 | −$2 | 1 | +$44 | 20,923 | 53% |
| VCIG | −$44 | −$45 | −$56 | 3 | +$14 | 96,329 | 82% |
| AMIX | −$122 | −$133 | −$9 | 1 | −$82 | 2,254 | 5% |
| NEXR | −$48 | −$45 | +$48 | 0 | $0 | 10,610 | 19% |
| DAIC | −$83 | −$80 | +$28 | 4 | −$39 | 21,226 | 58% |
| SDOT | −$283 | −$344 | +$94 | 0 | $0 | 849 | 1% |
| WVVIP | +$624 | +$852 | +$458 | **0** | **$0** | 3,080 | 18% |
| USDE | −$81 | −$72 | −$91 | 0 | $0 | 1,526 | 4% |
| OLOX | −$2 | −$13 | −$0.06 | 0 | $0 | 1,112 | 3% |
| SUGP | −$28 | −$82 | −$58 | 10 | −$33 | 15,546 | 48% |
| JUNS | −$64 | −$98 | −$141 | 4 | −$116 | 58,107 | 93% |
| ADXN | −$40 | +$261 | +$272 | **0** | **$0** | 6,575 | 28% |
| SGLY | −$9 | −$27 | −$7 | 0 | $0 | 666 | 0.4% |
| **TOTAL** | **+$235** | **+$339** | **+$931** | **40** | **+$197** | | |
| Trades | 111 | 147 | 103 | | 40 | | |
| Win rate | 26.1% | 21.8% | 27.2% | | **35.0%** | | |
| Profitable / losing / no-trade | | | 10 / 11 / 0 | | 8 / 5 / **8** | | |

### The 6,000-share floor is a liquidity screen, not a bar filter

This is the dominant effect, and it is almost certainly not what was intended.

Average 30-second bar volume across these 21 names spans **666 to 228,005 shares — a 340× range**.
A fixed share-count floor therefore does not filter thin bars *within* a name; it filters out
*entire names*. **Eight of 21 tickers produce zero trades**, because their typical bar never
clears 6,000 shares at all.

The names it excluded were disproportionately the winners:

- **WVVIP** — V4's best result at **+$458**, a +783% session — averages 3,080 shares per 30s bar. Zero trades.
- **ADXN** — **+$272** in V4 on a +193% session — averages 6,575. Zero trades.
- **SDOT** +$94 and **NEXR** +$48 also eliminated.

In total the floor removed roughly **$872 of V4 winners against $115 of V4 losers.**

The cause is structural: a low-float stock runs hundreds of percent on *modest share counts*
precisely because the float is small. WVVIP went $3.14 → $27.73 on ~3k shares per half-minute.
**A share-count threshold penalises exactly the names this strategy is built to find.**

### Separating the two changes

For names that comfortably clear the floor, the 30-second switch alone is roughly neutral:
JUNS (93% pass) went −$141 → −$116; PPCB (98% pass) +$93 → +$72; QNRX (80% pass) −$74 → +$3.
For names that mostly fail it (WETO 7%, XPON 4%, SDOT 1%), the floor is what changed everything.
**So the aggregate drop from +$931 to +$197 is the floor, not the timeframe.**

### What did improve

- **Win rate 35.0%** — the best of any version, up from 27.2%.
- Fewer, more selective trades (40 vs 103).
- But **average $/trade fell** from $9.04 to $4.92, and robustness got worse: V5 turns negative
  after removing just its top two names, where V4 survived removing three.

### Timeframe caveat

Every "bars" input now spans half the wall-clock time it did on 1-minute charts. MACD 12/26/9,
apexLook 20 and trendLen 3 are all twice as fast in real time. The V4→V5 comparison therefore is
not a clean like-for-like even before the floor. Rescaling the indicator lengths (roughly doubling
them) would be needed to isolate the timeframe effect properly.

## Recommended fix for the volume floor

Replace the absolute share count with one of:

1. **Dollar volume** — previous bar ≥ ~$20,000 traded. Scales with price, so a $27 stock and a
   $1 stock are treated comparably. WVVIP at $20 × 3,080 shares = $61k/bar would pass easily.
2. **Relative to the name's own baseline** — previous bar ≥ 50% of that session's median bar
   volume. Filters dead bars within a name without excluding any name outright.

Option 1 is closer to what a share floor was probably meant to express and is a one-line change.

## Why the old exit failed — WETO, 31 Aug (V2 forensics)

Trade #9 ran 7.66 → 8.73 (+$107 on 100 shares), then collapsed to the 6% stop for −$48 — a $155
round trip in five minutes. The apex rule could not fire because **BBW was 17.2 against 9.0 three
bars earlier: it had nearly doubled *because the stock was crashing*.** BandWidth measures
volatility, not direction. Trades #1–8 all exited below 7.40; the session high after every one was
8.74. That diagnosis drove V3 and V4.

## Execution feasibility — the unresolved blocker

**IBKR, US stocks, pre-market.** A standard trailing stop fires a **market order**, and IBKR's
guidance states market orders — including stop losses — cannot be submitted outside regular hours
for US stocks; only Day Limit orders are accepted. The workable variant is a **Trailing Stop
*Limit*** with the Outside RTH attribute, but a limit exit can be skipped in a fast drop, which is
exactly what the trail is for. Confirm with IBKR support and prove it in the paper account.

**TradingView.** Paper trading supports extended hours, but "Outside RTH" is documented for
**limit orders**; other types only get "Outside RTH Take Profit". For live trading TradingView is
not the broker — orders route to the connected broker, so IBKR's rules govern.

**The consequence.** The backtest fills at the signal bar's close, i.e. like a market order. Every
entry and exit in every table above assumes a fill IBKR will not accept pre-market, and V4/V5 lean
on a trailing stop specifically. This is the gate on everything else.

## Script bugs found and fixed

1. **`request.security_lower_tf(..., "10S", volume)`** evaluated on every bar regardless of the
   selected volume mode, forced the chart into 10S resolution and truncated loaded history.
   Symptom: WETO read twice with identical settings gave 9 then 10 trades. **Mode removed.**
2. **Diagnostics gated on `barstate.islast`** never fire reliably with `calc_on_every_tick = false`.
   Now `barstate.islastconfirmedhistory or islast`.
3. **`strategy.closedtrades.profit()` already nets commission** — subtracting it again double-counted.
4. **`ta.highestbars()` inside a short-circuiting `and`** may not run every bar. Hoisted to globals.

Rule for future runs: the verification table must report its own data coverage (bars, session
range, open-position flag) in the same pass as the P/L.

## Next, in order

1. **Change the volume floor to dollar volume** and re-run. This should recover WVVIP, ADXN, SDOT
   and NEXR while keeping the noise reduction that lifted win rate to 35%.
2. **Rescale indicator lengths for 30s** (roughly double) so the timeframe comparison is clean.
3. **Rebuild the execution model** around marketable limit orders with a no-fill assumption.
4. **Only then** test on names chosen *without* hindsight.
