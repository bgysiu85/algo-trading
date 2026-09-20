# Did following the rules make money? Not answerable — but three things are

**Measured 2026-09-07** on 587 traded symbol-days against consolidated daily
bars (`EQUS.SUMMARY`), the first time this comparison has been possible on a
tape that isn't 95% missing.

The headline question — do rule-conforming trades beat discretionary ones —
**cannot be answered from this sample**. Three narrower things can.

---

## 1. The split

| | conforming | non-conforming | too new to evaluate |
|---|---:|---:|---:|
| symbol-days | 367 | 213 | 7 |
| net P/L | −44,501.62 | −56,329.83 | −14,151.47 |
| mean per symbol-day | −121.26 | −264.46 | — |
| median | −67.79 | −80.14 | — |
| profitable share | 35.4% | 28.6% | — |

Conformance is judged on the four thresholds, **not** on membership of the
capped 60-a-day candidate list. The cap is a minute-bar budget, not a trading
rule; a trade it excluded still followed the rules.

## 2. The verdict reverses on one trade — so there is no verdict

| | conforming lead |
|---|---:|
| on the total | **+$11,828.21** |
| drop top 1 | **−$26,139.78** |
| drop top 3 | −$29,672.71 |

**One symbol-day is worth $39,053 to the conforming half — 34% of the
account's entire loss.** Remove it and rule-following becomes the worse half.
The level comparison is a fact about that trade.

What survives the removal is thin but consistent in direction: median −$67.79
vs −$80.14, profitable share 35.4% vs 28.6%. Not enough to move a threshold on.

**And both halves lose heavily.** Conforming trades lost $44,501.62 over 367
symbol-days, −$121.26 each. "Better half" is a ranking, not a case for the
rules being profitable.

### The error this document exists partly to record

The first version of the report printed *"THE RULES LOOK LIKE THE BETTER HALF,
on both the mean and the total"* — computed from the level alone, three lines
below its own drop-top rows showing the reversal. Worse, the "check the
drop-top rows" caution was attached **only to the unfavourable branch**, so the
answer that flattered the rules was the one that escaped scrutiny.
PROGRAM_INDEX §4 puts drop-top-N first precisely to prevent this. The verdict
now compares level, drop-1 and drop-3 and refuses to rank when the sign flips.

## 3. RVOL is excluding losers — the one robust signal

| rule | rejected | their net P/L | mean |
|---|---:|---:|---:|
| RVOL ≥ 5 | 168 | −42,671.60 | −254.00 |
| prior-close sanity | 35 | −8,648.10 | −247.09 |
| liquidity floor | 13 | −3,710.69 | −285.44 |
| day range ≥ 10% | 12 | −3,076.24 | −256.35 |

Rules evaluated independently, so a symbol-day can appear on several rows.

**168 observations all pointing one way**: the trades RVOL rejects lost money,
at a worse average than the sample as a whole. That is the strongest
outlier-free evidence in the analysis, and it says keep the rule. Every other
rule rejects too few symbol-days to read.

This matters because Ben's own view is that a portion of his selection falls
outside his stated rules — so **recall is a diagnostic, not a target.** A screen
tuned until it reproduced all 587 of these would be tuned to reproduce a
$114,982.92 loss.

## 4. The new-listing blind spot — the actionable finding

Seven traded symbol-days could not be evaluated at all. Not a coverage gap:

| symbol | traded | net P/L | prior sessions | first bar |
|---|---|---:|---:|---|
| SLBT | 2026-06-16 | −13,241.28 | 1 | 2026-06-15 |
| PMA | 2026-07-10 | −530.12 | 1 | 2026-07-09 |
| BRNX | 2026-08-17 | −495.59 | 1 | 2026-08-14 |
| VHUB | 2026-02-02 | −209.06 | 1 | 2026-01-30 |
| AIB | 2026-03-18 | −1.44 | 1 | 2026-03-17 |
| GFUZ | 2026-07-13 | +142.96 | 0 | 2026-07-13 |
| XLAB | 2026-08-28 | +183.07 | 0 | 2026-08-28 |

**All present in the data. Every one traded on its first or second session of
existence.** The screen cannot evaluate them: RVOL is a ratio to a prior
average that does not exist yet, and the 10-day rolling mean needs three prior
sessions. This is permanent and structural, not a data problem.

**−$14,151 net, 12% of the account's total loss, five of seven losing.** SLBT
alone is −$13,241 on its second day of trading.

A system built from these rules needs an **explicit policy on new listings**.
Right now the answer is "no, accidentally" — and an accidental silence is
indistinguishable from a decision until someone checks. The report originally
described these as "no daily bar, most likely before the dataset's start date",
which was wrong on every count.

## 5. What this does and does not license

**Does:**
- Keep `min_rvol = 5.0`. Its rejects lost money across 168 symbol-days.
- Decide a new-listing policy explicitly, and state it in the screen.

**Does not:**
- Change any threshold on the conforming-vs-non-conforming comparison. It
  reverses on one trade.
- Treat 63% recall as a number to improve. It is a diagnostic against a losing
  sample.
- Conclude the rules are profitable. Both halves lost money.

## 6. Still open

- **Stage-2 leakage.** The screen's RVOL and range read *today's* bar, so a
  backtest on survivors describes "days that turned out active". Every
  downstream P/L figure remains an upper bound until rejected symbol-days are
  sampled and shown to produce (almost) no entries.
- **The dollar-volume floor.** `min_avg_dollar_vol = $25,000` now passes 88% of
  all rows and rejects 13 of 587 traded symbol-days — near-inert on consolidated
  data. p10 of the traded names is $83,007, which is where a real sanity floor
  would sit. Not yet changed.
- **The 60/day cap binds on 53 sessions** and is now shaping the universe
  rather than guarding against a runaway day.
- **2023-03 → 2024-06 has no consolidated volume.** EQUS.SUMMARY starts
  2024-07-01, so fourteen months of the backtest period cannot be rebuilt, and
  cannot be bought once the subscription lapses.

Tools: `common/rules_vs_pnl.py` (this analysis, writes a per-symbol-day CSV),
`common/screen.py --dataset EQUS.SUMMARY --validate`,
`claude/consolidated_volume_gap.md` (why the partial tape made this
unmeasurable before).
