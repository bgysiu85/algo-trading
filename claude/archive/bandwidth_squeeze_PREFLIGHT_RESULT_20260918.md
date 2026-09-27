# The BandWidth squeeze as a volatility regime — PRE-FLIGHT RESULT

**Run:** 2026-09-18
**Status:** MEASURED. **NOT ADOPTABLE.** The line closes on §3(b), as registered.
**Spec:** `claude/handover_bandwidth_squeeze_20260918.md`
**Scope:** measurement only. No P&L anywhere in this run, no entry rule, no fitted parameter.
**Raw:** `D:\Trading\Claude outputs\bandwidth_squeeze_20260918.txt` (+ `_src\` for reproduction)

---

## 0. Findings, in order of importance

1. **The squeeze is dominated by plain trailing σ20, which is the registered kill criterion.**
   σ20 alone explains log forward realised vol with **R² = 0.248 / 0.318 / 0.342** at
   k = 5 / 10 / 21. Adding log BandWidth moves R² by **+0.0015 / +0.0017 / +0.0023**.
   Adding σ20 to BandWidth alone moves it by **+0.088 / +0.115 / +0.121** — about
   **fifty times larger**. §7 required the squeeze to *beat* the σ20 null. It loses to it.

2. **The registered §6 prediction is falsified as worded, and in the direction nobody
   registered.** Forward RV after a squeeze is **0.905 / 0.913 / 0.928** of the
   unconditional baseline (t = (4.93) / (4.48) / (3.38)). A squeeze is followed by a
   **calmer** tape than average, not a more volatile one. Mean reversion out of a
   compressed state is only partial, so a low-vol state stays below average.

3. **Measured against its own σ20 the expansion is real and uninformative** — ratio
   **1.267 / 1.259 / 1.257**, t = 8.79 / 9.44 / 10.55. This is volatility clustering,
   restated. Registering the expected pass in advance did its job: it stopped this
   being reported as a success.

4. **Cross-sectionally there is nothing at all.** Against all names *on the same date*,
   the squeeze gives ratio **1.006 / 0.998 / 1.007, |t| < 0.45**. Everything both arms
   appear to know is the market-wide volatility regime, which every name already shares.

5. **Direction is a coin flip**, as Bollinger states — 52.1% / 52.3% / 55.2% up, forward
   return *below* baseline (t = (1.54) / (1.65) / (0.67)). Nothing to register separately.

6. **BandWidth is NOT the structural identity that %b turned out to be.** ρ(BandWidth,
   σ20) = **+0.727** pooled, per-name median +0.627 — nothing like %b vs RSI(14) at
   +0.911. It is a genuinely different object. It is just a **worse** one.

---

## 1. The deciding test (§3(b), §8.3 construction)

Dependent variable log RV(k). Standard errors clustered on date. n = 230,147 at k = 21.

| model | R² k=5 | R² k=10 | R² k=21 |
|---|---:|---:|---:|
| log σ20 alone | 0.2482 | 0.3177 | 0.3420 |
| log BandWidth alone | 0.1616 | 0.2045 | 0.2235 |
| σ20 + BandWidth | 0.2498 | 0.3193 | 0.3443 |
| **ΔR² from adding BandWidth** | **+0.0015** | **+0.0017** | **+0.0023** |
| **ΔR² from adding σ20 to BandWidth** | **+0.0882** | **+0.1148** | **+0.1208** |

The squeeze dummy *is* statistically significant with σ20 present (t = +14.5 / +16.6 /
+16.9, coefficient +0.13 / +0.12 / +0.11). With 230,147 observations that is what a
0.1%-of-R² effect looks like. **Significant and economically irrelevant.**

## 2. Levels and expansion, all arms (120 large caps, date-level)

| arm | k | base | signal | ratio | t |
|---|---:|---:|---:|---:|---:|
| **Level** SQUEEZE | 5 / 10 / 21 | .276/.289/.298 | .250/.264/.276 | **.905/.913/.928** | **(4.93)/(4.48)/(3.38)** |
| **Level** SIG-MIN *[null]* | 5 / 10 / 21 | .276/.289/.298 | .245/.260/.267 | .888/.899/.896 | (4.94)/(4.22)/(4.19) |
| **Expansion** SQUEEZE | 5 / 10 / 21 | .999/1.053/1.099 | 1.266/1.326/1.381 | **1.267/1.259/1.257** | 8.79/9.44/10.55 |
| **Expansion** SIG-MIN *[null]* | 5 / 10 / 21 | .999/1.053/1.099 | 1.494/1.577/1.616 | **1.495/1.497/1.471** | 14.11/14.82/14.78 |
| **Expansion** BULGE | 5 / 10 / 21 | .999/1.053/1.099 | .811/.834/.860 | **.811/.792/.783** | **(9.31)/(8.98)/(7.20)** |

The bulge behaves exactly as the source says it should — volatility *contracts* after it.
That is the one Bollinger claim in this run that survives intact, and it is also the one
with no strategic use.

### How not to read the expansion column

The raw expansion ratios make the null look like it **wins** (1.495 vs 1.267, and it wins
in **every year 2019–2026** at matched fire rate). That comparison is **partly mechanical**:
expansion = RV / σ20(t) carries σ20 in its denominator, so any selector that picks the
smallest σ20 maximises the metric by construction. It is reported because it was
registered. **It is not the argument.** The argument is §1 above, which has no such artifact.
This was caught by an independent verification pass, not by the run that produced it.

## 3. The three controls

**(a) Date-level, never pooled.** Applied throughout. Pooled says ratio 0.903, date-level
says 0.928 — the trap is present but does not flip this result, unlike the dip-buy where it
was the entire finding. Clustering is also *milder* than feared: the squeeze fires on a
median of **3** names, p90 8, **max 25 of 120 (21%)** — against the dip-buy's 105 of 120.
The σ20 decile is the clustered one, at **max 80 of 120 (67%)**.

**(b) The σ20 null.** §1. This is where it dies, as registered.

**(c) Direction.** Coin flip, confirmed. §0 item 5.

## 4. What is not zero, stated honestly

Conditional on σ20 *already* being in its bottom decile, a squeeze still adds about
**5–8% more expansion (t = 2.28 / 2.28 / 2.52)**, and the squeeze dummy survives σ20 in
the regression. **The squeeze is not literally empty.** It is *dominated* — which is a
different and sufficient reason to stop, because §7 set the bar at beating the null, not
at surviving it.

## 5. Data — and an honest deviation from the spec

The spec pointed at the **120 liquid large caps from `factor_correlation_result_20260911` §1**.
That dataset was fetched from TradingView at run time, **never persisted, and its ticker
list was never recorded** — §10 of that doc names the scripts but not the names. It could
not be reused.

| | |
|---|---|
| Source | **Databento XNAS.ITCH `ohlcv-1d`**, local archive `E:\Databento` |
| Span | 2018-05-01 → 2026-09-04; eligible 2018-11-21 → 2026-09-04 after warm-up |
| Size | 256,124 daily bars, 123 symbols; **232,667 eligible large-cap name-days** |
| Universe | a rebuilt sector-spread 120 + SPY/QQQ/IWM — **ticker list recorded in the raw .txt** |
| Integrity | 0 NaN closes, 0 non-positive, 0 duplicate (date, symbol) |

**This is 8.4 years, not the 19.8 the spec implied.** Re-fetching two decades of daily bars
for 123 names through the TradingView MCP would have cost several million tokens of
context; the local archive was free. 232,667 name-days is far more than this comparison
needs, but the 2008 and 2010–2017 regimes are **absent**, and that is a real limitation.

**Split adjustment.** Databento prices are raw. Factors came from Alpha Vantage `SPLITS`
and were applied to 20 names. This mattered more than a jump detector would suggest: three
of the GE entries are **spinoff** price adjustments (GE HealthCare, GE Vernova) and
**MRK 1.048** (Organon) is a 4.8% adjustment a >15% detector would have missed entirely.
**META bars before 2022-06-09 were dropped** — that ticker belonged to another issuer
before Facebook took it, and it prints as a +1,404% day.

After adjustment, **53 bars across 34 names** still move >20% in a day, and **none** is
within 2% of a clean rational ratio either way — i.e. **no unadjusted split survives**.
The largest are real events (OXY (47.2%) 2020-03-09, QCOM +31.8% 2019-04-16 Apple
settlement, ORCL +28.8% 2025-09-09).

**Venue.** XNAS.ITCH daily closes are the last *Nasdaq* print, not the official
consolidated close. Against EQUS.MINI over 106,272 paired rows: median difference
**0.077%**, p90 0.385%, p99 1.06%. Small, real, and larger for NYSE-listed names.

**Survivorship.** 120 *current* large caps over 2018–2026 is forward-looking constituent
selection. It flatters the absolute volatility baselines. It does not touch the ordering
of the arms, which is the deliverable.

## 6. Verification

An independent agent reimplemented the measurement from the adjusted bars without using
the production code and reproduced **all eight headline claims exactly**. It additionally
hardened the crux by pairing arms **by date** (SIG-MIN − squeeze expansion = +0.187 /
+0.220 / +0.206, HAC t = +6.78 / +9.06 / +10.05) and confirmed no look-ahead in the
forward RV construction, correct NaN handling, an inclusive 125-bar window, and no
residual splits. It also raised the denominator-artifact objection in §2, which changed
how this result is argued — the regression in §1 became the headline because of it.

## 7. §8 wait-one-bar, the cheap ride-along

Waiting one bar after the squeeze before measuring moves the expansion ratio from
**1.257 to 1.273** (t 10.55 → 11.54). Directionally consistent with Bollinger separating
the alert from the signal. Immaterial here. It costs one cell on any future grid and this
run is not a reason to add it.

## 8. What this changes

| Item | Change |
|---|---|
| `source_videos` §3, BandWidth squeeze | **CLOSED.** Open since 2026-09-07. Dominated by σ20; not adoptable. |
| `source_videos` §6 item 4, wait-one-bar | **MEASURED in passing.** +0.016 on the expansion ratio. Still a one-cell add-on, still not independently motivated. |
| Volatility-gate family | **Fourth failure.** After `luck_vs_edge`, `cold_veto` and `spy_intraday` H-S2. The opposite-conditioning argument in §4 of the handover was a fair reason to look; it did not change the outcome. |
| §5 structural point | **Unchanged.** Still a component in search of a host, and there is still no directional book with positive gross to gate. |

**Do not re-open this on a longer history without a specific reason.** The failure is not
marginal and not a power problem: σ20 wins by a factor of fifty on incremental R², in
every year, on every horizon, and the cross-sectional test is flat at |t| < 0.45.
