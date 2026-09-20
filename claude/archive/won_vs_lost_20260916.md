# Ben's winners against his losers — the one cut that is not a tautology

**2026-09-16.** Bundle `20260916c`, commit `3f9bcc4`, 2,584 passed / 4 skipped.
Sheet now carries a won/loss column: **all 11 `took` rows are marked `won`**, 6
are `took-and-lost`, 6 are `pass`, 1 unlabelled.

That resolves the caveat the earlier runs had to carry — `took` meant "I would
take this", outcome unstated. It is now a genuine **won (11) against lost (6)**
split on his own picks, and it is the only comparison in this work that does not
restate his selection criterion back at itself.

---

## 1. The result, under the standing cross-timeframe rule

Median percentile against **MCL's own entry bars**. A feature counts only if the
direction agrees on both timeframes and both gaps are ≥ 20 points.

| feature | 1m won | 1m lost | gap | 5m won | 5m lost | gap | |
|---|---:|---:|---:|---:|---:|---:|---|
| `rsi` | 74.8% | 12.9% | **+61.9** | 37.7% | 11.4% | **+26.3** | agree |
| `price` | 67.9% | 19.6% | **+48.3** | 66.7% | 16.0% | **+50.8** | agree |
| `close_in_bar` | 68.2% | 32.1% | **+36.1** | 50.0% | 26.6% | **+23.4** | agree |
| `ema9_dist` | 74.1% | 40.5% | **+33.6** | 88.2% | 50.4% | **+37.8** | agree |

**Refused — the timeframes disagree in direction:** `mfi`, `tape_density`,
`vwap_dist`, `rsi_slope`, **`range_pct`**, `trail_over_range`.

**Cannot be checked:** `bb_pos` had the second-largest 1-minute gap (+51.8) but
the 5-minute view does not have enough covered `lost` rows to test it. Absence,
not disagreement — so it is 1-minute-only evidence, not a refusal.

### Counted by family, which is what the rule requires

- `rsi` sits in **momentum level** with `mfi` — and `mfi` refused. Family split.
- `ema9_dist` sits in **trend** with `vwap_dist` (refused) and `ma20_dist`.
  Family split.
- `close_in_bar` sits in **bar shape** with `body_ratio` (+52.1 / +18.8, agrees).
  **Whole family agrees.**
- `price` is its own family. Survives.

> **One family survives intact — bar shape. And `price` survives but is the most
> likely confound in the set**: it is not a momentum quantity at all, and reads
> more like which names he happened to screenshot, or a liquidity proxy, than
> anything about the setup.

## 2. The finding that matters most is a separation, not a signal

**`range_pct` separates his TAKES from his PASSES (88.3% vs 54.2%) and does NOT
separate his WINNERS from his LOSERS (88.3% vs 83.7%, and the 5-minute view
disagrees in sign).**

So volatility describes **what he selects**. It does not describe **what works**.

That matters because volatility was the candidate this work was heading toward
registering — it is the family MCL does not gate on, it held take-vs-pass on
both timeframes, and it is what he wrote by hand on three later samples. It is
still the best description of his selection rule. It is **not** evidence that
the rule makes money, and those two claims were one step from being conflated.

## 3. `close_in_bar` points the opposite way to the MCL finding

Earlier instruments read MCL's losses as trades that **paid the top tick** — a
high `close_in_bar`. Here his **winners** have the higher `close_in_bar`
(68.2% against 32.1%, agreeing on both timeframes).

Two readings, and nothing here chooses between them:

- Buying strength inside the bar works for a discretionary trader reading the
  tape and fails for a rule that fires on *every* such bar. The trader is
  selecting among strong-closing bars; the rule takes all of them.
- Or it is noise at n = 17.

It is worth registering as a question precisely because the two instruments
disagree, and a disagreement between measurements is a finding about the
measurements.

## 4. Sensitivity: the self-declared fluke

PLYX 2026-02-17 is marked *"won (but it was honestly a fluke). I wasn't
expecting such a big surge."* One of eleven winners the trader does not endorse.

Dropping it **widens** almost every gap — `rsi` +61.9 → +62.7, `bb_pos` +51.8 →
+55.5, `body_ratio` +52.1 → +53.1. The only material shrink is `mfi`
(+34.5 → +17.3), and `mfi` already refused on cross-timeframe disagreement.

So the result is not carried by the row he flagged. The loader now keeps that
sentence and the report prints it — a win the trader does not endorse is not a
win to fit against.

## 5. What this still cannot support

Eleven against six. Labels written after the outcomes were known. Twenty-seven
features × two timeframes × two references × three label groups. No halves to
disagree, and the locked holdout unspent.

**Nothing here is registerable as a rule.** What it does is narrow the
candidates from "everything on his chart" to one family and one suspected
confound, and it separates a selection description (`range_pct`) from an
outcome claim, which is the mistake this set was one step away from making.

## 6. Instrument changes

- The **outcome column** is read, optional, matched on a prefix (the header in
  the sheet is `wonl/loss`).
- The **qualifying sentence is kept**, not reduced to `won`.
- A **label-against-outcome cross-tab** prints whenever any outcome exists, and
  a `took` marked lost, a `took-and-lost` marked won, or a `pass` with an
  outcome fires a loud block. The report cuts its groups on **label**, so a
  divergence would otherwise put a loser in the winners' group silently.

Two mutation survivors, both mine: the report test set `outcome_note` by hand so
emptying it in the loader stayed green (a check one step short of the thing it
protects, inside the test for a guard against exactly that), and the
label/note exclusion in the outcome search was unreachable and has been removed
rather than left in.

## 7. Open

**The unlabelled row.** RGNT 2026-06-17 04:18 now reads *"missed the move but I
would have taken it"* — that is a `took` with no outcome, and it currently sits
in no group at all. Ben's call whether to label it; it is excluded from
everything above.
