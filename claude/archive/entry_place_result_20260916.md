# The placement runs — and the correction that came from splitting by label

**Runs 2026-09-16.** Module at commit `fe7b8df`.
`--reference all` → 1,193,386 bars (1m) / 275,136 (5m).
`--reference entry` → **8,300 / 1,299**.
Final run: **24 samples, 24 measured** (11 took · 6 took-and-lost · 6 pass · 1
unlabelled), after Ben added three `pass` rows and 2026-09-15 was pulled.

---

## 0. CORRECTION — the first reading of this run was wrong

The earlier version of this document, and the first version of the artifact,
read the **pooled** median of all samples as "where Ben buys". **A quarter of
that population are bars he explicitly declined.**

| feature (1m, vs entry) | pooled (24) | **took (11)** | took-and-lost (6) | pass (6) |
|---|---:|---:|---:|---:|
| `bb_pos` | 12.4% | **68.4%** | 16.6% | 0.7% |
| `rsi` | 12.9% | **74.8%** | 12.9% | 2.0% |
| `extension` | 64.4% | **85.9%** | 72.7% | 15.2% |
| `ema9_dist` | 40.5% | **74.1%** | 40.5% | 9.5% |
| `ma20_dist` | 50.1% | **63.6%** | 43.6% | 2.8% |
| `vwap_dist` | 48.5% | **57.6%** | 63.9% | 16.1% |
| `range_pct` | 86.5% | **88.3%** | 83.7% | 54.2% |
| `bb_width` | 77.3% | **91.3%** | 67.9% | 43.2% |

**"Ben buys lower in the range" was an artefact of pooling his passes into his
picks. He buys higher.** On `bb_pos` the pooled median is 12.4% and his `took`
rows alone are 68.4%.

**Consequence for the dip-buying case:** that claim had four legs, and this run
was the one resting on the pooled `bb_pos`. It no longer supports it. MCL's
pops-then-fades population (70.7% at −$22.73 against a dips-first 29.3% at
+$19.13), Cameron's dip book, and the CRBP sequence stand on their own — as
three legs, not four.

## 1. Both tautologies, named

**`--reference all` is mostly dead minutes.** 22 of 27 features called the
samples unusual, medians at the 80th–94th percentile. LGHL 2026-05-21 carries
1,999 of its 2,770 bars at zero volume. He screenshots bars where something is
happening. *The instrument built to look for this project's signature defect had
it.*

**`--reference entry` is defined by thresholds on six of the columns.**
`vol_multiple`, `vol_over_trail`, `floor_margin`, `rsi_slope`, `mfi_slope`,
`macd_margin` are MCL's own clauses. Their percentiles there restate the gate.
`vol_multiple` reads **0.0% for all three label groups on the 1-minute view** —
which is itself worth one line: **MCL's volume clause does not discriminate at
all between the bars Ben would take and the bars he would pass.**

## 2. What the label split actually shows

Three groups, and on most features they come out **in order**: took above
took-and-lost above pass, on both timeframes. A middle group landing between the
other two repeatedly is a rarer shape than a two-group gap.

**But most of it is one family.** `extension`, `ema9_dist`, `vwap_dist`,
`ma20_dist` and `bb_pos` are all "how far has price run from a recent
reference" — one idea measured five ways, and *"the bars he takes have moved
more than the bars he passes"* is close to a definition of what he is looking
for rather than a discovery about it.

What the entry reference adds is **scale**: his takes sit at the **86th
percentile of extension among MCL's own entry bars**. He is not picking a
different kind of bar so much as a far more extreme subset of the same kind.

**The independent second family is volatility**, which MCL does not gate on:

    range_pct   took 88.3%  vs  pass 54.2%   (1m)    92.3 vs 68.8  (5m)
    bb_width    took 91.3%  vs  pass 43.2%   (1m)

And that is exactly what he wrote by hand on the three new passes — *"low
volatility, not enough momentum"* — on samples collected **after** the
measurement was made.

## 3. The three new passes, and the session they came from

All three are 2026-09-15, the session reviewed in
`session_review_20260914_15.md`.

| his pass | what the algorithm did |
|---|---|
| **VEEA 05:46** | already long since 05:38:01 @ 3.57; stopped 06:05:47 @ 3.40, **(18.37)** |
| **VEEA 07:12** | bought 07:19:01 @ 3.76 (MCL) and 07:21:01 @ 3.90 (MC5); both stopped 07:32:10, **(3.37)** and **(18.37)** |
| **MYSZ 07:41** | traded 07:07–07:10 @ 2.64 → 2.51, **(14.37)** |

**VEEA and MYSZ together are (88.33) of that session's (185.01) — 48%.**

Their own percentiles (1m, vs entry) come back low on `bb_width` (8.2 / 23.9 /
29.4) and high on `trail_over_range` (53.7 / 58.9 / 55.6 — a quiet bar gives the
5% trail many bar-widths), but **middle on `range_pct`** (44.9 / 39.3 / 43.5).
So his phrase "low volatility" reads as band width, not bar range.

Caveats that travel with this: the labels were written after the outcomes were
known; VEEA 05:46 is not an entry bar (the algorithm was already long); and six
passes is six.

## 4. The cut that would matter, and the field that is missing

**Took against took-and-lost** is the same person applying the same criterion
with different outcomes — the only non-tautological comparison available. It
says his losses were lower in the band (**16.6%** against 68.4%), at lower RSI
(12.9% against 74.8%) and wickier (`body_ratio` 16.5% against 68.6%), while
being just as extended and just as volatile.

Three reasons that is not a finding: eleven against six; hindsight labels; and
**`took` does not assert a win** — it means "I would take this", outcome
unstated.

> **The highest-value thing Ben can add is no longer more passes. It is the
> outcome of the takes.** Marking each `took` won or lost turns the one
> non-tautological cut here into something registerable.

## 5. What must not happen

- **No `bb_pos` threshold on MCL.** 27 features × 2 timeframes × 2 references ×
  3 label groups, no halves to disagree — and the sign of that column already
  flipped once when the population was split correctly.
- **The gated six are not evidence.** They belong in the sentence "they are
  looking at different bars" and nowhere else.
- **Volatility is the registerable candidate**, not extension: it is the family
  MCL does not look at, it holds on both timeframes, and the hand-written reason
  on three later samples names it. Register direction and threshold in a commit
  before any backtest. `var/state/holdout.json` stays shut.

## 6. Instrument changes these runs forced

- `--reference {all,signal,entry}`, populations defined by MCL's own columns; an
  unknown name raises rather than defaulting to `all`.
- A **coverage floor** (60% of measured samples) with a `TOO THIN TO PLACE` list;
  the first run had classified a feature measured on 2 of 21 beside features
  measured on all 21.
- The report names its reference in the header and in the output filename.

Still thin: `ema200_dist` 5/24 on 1m and absent on 5m (the archive holds
pre-market slices only); `vol_over_trail` and `floor_margin` on the 5-minute
view.
