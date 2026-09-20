# Handover — the BandWidth squeeze as a volatility regime, PRE-FLIGHT (2026-09-18)

Paste the block below into the new chat.

---

## Message to the new chat

**This is a pre-flight measurement, not a strategy.** It has no P&L, no entry
rule and no parameters to fit. Its only job is to answer whether the Bollinger
BandWidth squeeze carries information on this project's candidate universes,
before anyone spends a registration on it. Read §3 before §2 — the prior is
poor and the reason is specific.

### 1. Where it comes from

`source_videos_20260907.md` §2.2, John Bollinger presenting his own indicator —
the only primary source in that file and the only one making no performance
claim of any kind. Two constructions:

```
BandWidth = (upper − lower) / middle          # SMA20 ± 2σ20, middle = SMA20
squeeze   = BandWidth at its lowest over a trailing 125-bar window
bulge     = BandWidth at its highest over the same window
```

> *"A squeeze is where trends are born and a bulge is where trends go to die."*

**And the constraint that decides how it can ever be used:** the squeeze is
**direction-agnostic**, by his own statement and his own examples, one of which
precedes a downtrend. It forecasts *volatility*, not *sign*. So it can only be a
**gate or a sizing input on a signal that already has direction** — never an
entry in its own right. Anyone who builds a directional strategy from it has
misread the source.

It was logged in `source_videos` §3 as *"Yes / Yes, from daily bars"* — new to
this project and testable on data already held — and has sat untested since
2026-09-07.

### 2. What to measure

For each bar on which the squeeze fires, does realised volatility over the next
*k* bars exceed the unconditional baseline?

```
RV(k, t) = stdev of log returns over bars t+1 … t+k, annualised
report    RV(k | squeeze)  against  RV(k | all bars)
for k in {5, 10, 21}
```

Report the ratio and the distribution, not just the mean. **No P&L anywhere in
this study.** If a P&L figure appears, the scope has been exceeded.

**Universes — all daily bars, all already on disk, no new data and no new
subscription:**

- the **120 liquid US large caps** from `factor_correlation_result_20260911.md`
  §1 — 2006-10 → 2026-09, 4,743 factor days, integrity already verified
  (0 NaN closes, 0 duplicate dates, split adjustment checked across AAPL's 7:1
  and 4:1);
- **SPY, QQQ, IWM** daily, already fetched for the SPY intraday study.

Do **not** start on the small-cap PIT universe. Its daily bars are not
split-adjusted (a 1-for-10 prints as a ~900% gain — `HANDOVER_20260911.md` §4
item 2), and that defect lands directly on a volatility measurement.

### 3. Three controls, and the second is the one that will decide it

**(a) Date-level, never pooled (name, day).** This is the same trap that
inverted the Bollinger dip-buy: pooled it read **+0.286% per trade**, date-level
it read **(0.010%), t = (0.18)** — the entire result. Squeezes are *more*
clustered than dip-buys, because low volatility is market-wide: that study saw
up to **105 of 120 names** fire on a single day. Pooling here would be worse,
not better. Report the daily count distribution alongside the result.

**(b) The σ20 null — this is the mechanism test and it is the crux.**
BandWidth is a deterministic function of trailing σ20 divided by the SMA20. Low
BandWidth therefore *means* σ20 is low, and volatility mean-reversion is one of
the most robust facts in finance. **So "volatility rises after a squeeze" is
very likely true and very likely uninformative.**

The real question: does the 125-bar percentile framing add anything over simply
conditioning on **σ20 in its own bottom decile**? Run both arms and compare.

This is `source_videos` §8.3's construction — *add the explicit version of what
the proxy claims to capture, and if the result barely moves, the proxy was not
doing the job*. It is also the shape of the finding that closed %b: RSI(14) vs
Bollinger %b measured **ρ = +0.911**, median 0.912 across 120 names, 5th–95th
percentile 0.902–0.920 — *"a structural identity, not an average."* Expect
BandWidth-vs-σ20 to look similar. **If it does, the line closes here.**

**(c) Direction, checked rather than assumed.** Bollinger says direction-
agnostic. Verify it: the sign of the forward return after a squeeze should be
indistinguishable from a coin flip. If it is not, that is a finding in its own
right and needs its own registration — do not fold it into this one.

### 4. The prior, stated honestly

**The volatility-gate family has now failed three times on this project's data,
and once overnight:**

| study | gate | result |
|---|---|---|
| `luck_vs_edge_RESULT_20260917` | hot / mixed / cold sessions | per-trade flat across all three |
| `cold_veto_RESULT_20260917` | cold-session veto | NOTHING |
| **`spy_intraday_RESULT_20260918` H-S2** | **realised vol of the first 30 min ≥ trailing 67th pctile** | **NOTHING — 0 of 5 gates, (0.271) bps gross** |

H-S2 is the closest analogue and it is worth reading in full. It gated a
published, peer-reviewed directional effect on exactly this kind of volatility
condition, and moved gross from **(0.308) to (0.271) bps** — i.e. the gate
did almost nothing, on the cell where the literature said the effect lived.

**Two reasons this is still a different test, and they are the only reasons:**

1. **Opposite conditioning.** H-S2 gated on volatility being *high*. The squeeze
   gates on volatility being *low*, as a predictor of subsequent expansion.
   Those are different claims about different states.
2. **Different object.** H-S2's `sigma1` was a contemporaneous *level*. BandWidth
   is *compression relative to its own recent history* — a second derivative,
   normalised by price.

That is enough to justify a measurement. It is not enough to justify a strategy.

### 5. The structural problem you should raise before building anything

**A gate needs a host, and this project does not currently have one.**

A direction-agnostic volatility signal can only condition a directional strategy
with positive gross. As of today:

| | gross | status |
|---|---:|---|
| MCL (PIT book) | **(6.26)/trade** | loses before any cost |
| MC5 | negative | loses before any cost |
| VW9 | negative | loses before any cost |
| SPY intraday H-S1 / H-S2 | **(0.308) / (0.271) bps** | **closed 2026-09-18** |
| ORB on liquid stocks in play | +0.003R registered reading | **does not pass, 1 of 7 criteria** |
| TSMOM | in progress | no result yet |

Gating a book that loses gross cannot help — `spy_intraday_AMENDMENT_A` §A.5 and
`friction_reconciliation_20260911` §3 both make this argument, and it applies
here unchanged.

**So the honest framing is: this measurement produces a component in search of a
host.** That is a legitimate thing to produce — cheaply, once, so it is on the
shelf when a host exists — but it should be scoped that way from the start, and
nobody should be surprised when it does not rescue anything.

### 6. Registered prediction, recorded before the run

- **The expansion result PASSES and is uninformative.** RV after a squeeze will
  exceed baseline, by a comfortable margin, on every universe. High confidence.
  This is volatility clustering, not a Bollinger finding.
- **The σ20 null is where it dies.** Conditioning on σ20's bottom decile will
  produce materially the same forward-volatility lift as the 125-bar squeeze.
  Moderate-to-high confidence, by analogy with %b vs RSI(14) at ρ = 0.911.
- **Direction is a coin flip**, as the source states. High confidence.
- **Therefore: NOT ADOPTABLE**, and the line closes on §3(b).

Registering the expected *pass* on §2 explicitly is deliberate: it stops a
true-but-empty result being reported as a success.

### 7. Go / no-go

**Proceed to a gate specification only if** the squeeze beats the σ20 null on
forward volatility by a margin that survives date-level clustering — and even
then, park it until a host strategy with positive gross exists.

**Close the line if** §3(b) shows BandWidth and σ20 carry the same information.
That is a complete answer, it costs a few hours on data already held, and it
retires an item that has been open in `source_videos` §3 since 2026-09-07.

**Deliverables:** `claude/bandwidth_squeeze_PREFLIGHT_RESULT_<date>.md`, raw
`.txt` to `D:\Trading\Claude outputs`, and an artifact page with negatives
bracketed and red.

### 8. Also worth taking from the same source, and cheaper

`source_videos` §6 item 4 has been open just as long and is one line: Bollinger
deliberately separates the buy *alert* from the buy *signal* by one bar —
*"we then wait one day… this first day up after the tag low is actually our buy
signal."* Adding a **wait-one-bar** cell to any strategy grid is a single
parameter and a single cell. It may do nothing. It costs almost nothing to find
out, and it can ride along with any run rather than needing its own.

---

*(End of message to the new chat.)*
