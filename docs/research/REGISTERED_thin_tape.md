# REGISTERED — H-T1: does the signal bar's ABSOLUTE volume separate anything?

**Written and committed 2026-09-19, before any code exists.** A pre-flight, in the
shape that worked for `running_up_preflight`: descriptive, no threshold, no
verdict, no P&L. It exists to decide whether a volume gate is worth registering
at all.

Ben, on the two MC5 AEHL trades of 2026-09-18: *"simply should not have
happened. there were no volume to support any trades."* Signal-bar volume
**2,003** shares (04:06) and **634** (06:31), on five-minute bars — about two
shares a second. Together **(108.76)**, against a day that netted (14.59).

---

## 1. Why this question has never been asked of the data

**Every volume feature this project has measured is a RATIO.**

`common/running_up.py`, the separation pass of 2026-09-18:

```python
out["rvol_1m"] = vol[-1] / med            # med = the session's own median
out["rvol_5m"] = vol[-5:].sum() / (5*med)
```

`strategy/mcl/mcl.py`, the only strategy with a volume condition at all:

```python
c_vol   = (v >= prev_vol * VOL_MULTIPLE) & (prev_vol > 0)     # 3x the previous bar
c_floor = (trail_avg > 0) & (prev_vol >= trail_avg * FLOOR_FRACTION)
```

And `strategy/mc5/mc5.py` has none: `entry = c_rsi & c_ema & c_macd`.

So the pre-flight and the strategy share a blind spot. **Three times nothing is
nothing** — DAIC on 2026-09-18 entered on 2,037 shares against a previous bar of
593, passing both of MCL's clauses, and lost (27.37) over 45 minutes
(`handover_holds_misses_levers_20260919.md` §1). A ratio cannot see an empty
tape, because the denominator is empty too.

**The screen gates the DAY; nothing gates the BAR.** Every symbol-day in the
published books cleared pre-market volume ≥ 100,000 scaled by the capture
ladder, so these are not dead names — AEHL passed the screen. What was dead was
the individual bar the signal was read on. **That quantity has never been
measured here.**

## 2. Why a pre-flight and not the gate the handover asks for

`handover_thin_tape_entries_20260918.md` §3 gives a live cut over 180 round
trips: spread ≥ 2% or signal bar < 2,000 shares = 21 trades carrying (656.85),
against (39.16) over the other 159. **It says so itself: the cuts were chosen
after seeing which trades lost.** Two trades dominate, one of them (CRBP, a
winner) sits inside the cut, and n = 180.

And its own table is **not monotone**:

| signal-bar volume | n | per trade |
|---|---:|---:|
| < 2,000 | 12 | (17.87) |
| 2k–10k | 15 | (7.44) |
| 10k–50k | 28 | **+2.63** |
| ≥ 50k | 124 | (3.10) |

**A gate is a threshold, and a threshold can only express a monotone
relationship.** If the 550-session version is shaped like this one, no floor
captures it and the line closes before anything is built. That is the whole
point of asking first: the Running Up pre-flight came back inverted and saved a
gate that would have kept more losers than it removed.

## 3. What is measured

For every trade in both published baselines on
`screen_pairs_pit_itch_v2.json` — MCL 3,908, MC5 6,462 — at the entry bar,
from that session's **closed bars only**.

### 3.1 The new features, and they are absolute

- **`vol_bar`** — the volume of the signal bar itself, in shares.
- **`vol_5bar`** — the volume of the five signal bars up to and including it.

Both in shares, neither divided by anything. They join `running_up.FEATURES` so
there is one implementation of "features at entry", and the existing ratio
features are unchanged — per-feature AUC does not depend on the other features,
so no published number moves.

### 3.2 The grain is read off the engine, per symbol-day

**H-R1's lesson, one day old, and this pass would repeat the defect exactly.**
`running_up_preflight.run_day` builds a **1-minute** frame and calls
`features(df, ts)` for both books, so `vol[-1]` is one minute of tape. MC5 acts
on **five-minute** bars: the figures Ben quoted — 2,003 and 634 — are
five-minute figures, and read at the wrong grain they would come back about five
times too small with nothing looking wrong.

So `bar_minutes` comes from `common.rebound.engine_bar_minutes(mod, df)`, which
reads `mc5`'s own constant and `mc5`'s own `_looks_5m`, and `vol_bar` sums the
tape over the engine's own bar. **A 1-minute engine is bit-identical.** The same
scored check applies: a trade measured at N-minute grain must sit on an N-minute
boundary.

### 3.3 The readings

Against the label **`bars_held <= 1`**, the same outcome the Running Up
pre-flight scored, so the AUCs are directly comparable to its published ones
(`ret_5m` 0.751 / 0.636; `rand` 0.526 / 0.505; the clock control 0.528).

1. **AUC per book**, beside the crc32-seeded `rand` null and the
   `minutes_since_0400` clock control, both already in the module.
2. **Decile table**: the one-bar share in each `vol_bar` decile, per book. This
   is where §5's rule applies — *look at the distribution of the thing a
   threshold will cut before registering the threshold* — and it is what says
   whether the relationship is monotone.
3. **The absolute distribution**: p1 / p5 / p10 / p25 / p50 of `vol_bar` in
   shares, per book, so a later registration has a distribution to choose from
   rather than a number fitted to 21 live trades.
4. **Reported, never scored:** the same AUC against the sharper H-R1 population
   (`bars_held <= 1` **and** `reason == "trailing_stop"`). Sharper, but a
   different label from the one the comparison above rests on, so it is printed
   and not read into the decision.
5. **The MCL clause reading, and it is the DAIC question generalised:** of MCL's
   3,908 entries — every one of which passed `c_vol` and `c_floor` — the share
   whose `vol_bar` fell below each decile boundary of the pooled distribution.
   A count of how often "three times nothing" happens. No threshold is named.

## 4. The decision rule, fixed before the numbers exist

**A volume gate is registered only if BOTH hold:**

- **AUC ≥ 0.60 on at least one book**, with the other book not inverted (i.e.
  not below its own `rand` control). The bar is set against what this project
  has already seen: `rand` reads 0.505–0.526, the clock 0.528, and the one
  feature that genuinely separated read 0.751. 0.60 is comfortably clear of
  noise and well short of the only real separation measured here.
- **AND the one-bar share falls monotonically across at least the bottom five
  deciles.** Not across all ten — the live table's non-monotonicity is at the
  top, where a floor does not operate anyway. A floor only has to be right about
  the bottom.

**If either fails, no volume gate is registered**, and the answer to Ben's
objection is recorded as: the live cases are real, they are rare, and the thing
they have in common is not something a volume floor can express — which points
at the spread clause of `handover_thin_tape_entries_20260918.md` §4(b) instead,
and that one has a measurement problem of its own (there are no quotes in
`ohlcv-1m`, so it cannot be scored on these books at all).

**Nothing here may be promoted regardless of the outcome.** A pre-flight that
clears its bar produces a registration, not a rule.

## 5. What this cannot do

**It cannot price a gate.** Separation is not money, and a feature that
separates can still refuse the better half of a bad book — which is exactly what
H-P1 found on 2026-09-18, where the chase gate removed two thirds of the one-bar
deaths and paid $0.29 a trade. **The money comes later, once, in a registered
gate study scored against `gate_study.abstention`** like every other gate here.

**It is outcome-dependent by construction** — `bars_held` is not knowable at
entry — which is fine for a separation pass and disqualifying for a rule. The
feature it scores, `vol_bar`, IS knowable at entry; the label is not. That is
the only honest form of the question, and it is the form the Running Up
pre-flight used.

**A test enforces the bar**, as it does for the pre-flight: no money reaches the
report and no scoring vocabulary does either.

## 6. My prediction, on the record

**AUC lands between 0.52 and 0.60 on both books — weak, above the null, short of
the bar — and the decile shape is not monotone.** So I expect this to close the
volume line.

The reasoning: the bottom tail is real (634 shares in five minutes is not a
market, and no amount of statistics makes it one), but it is a *tail*, not a
gradient. The live table already shows the middle behaving better than the top,
and the published books are drawn from a screen that requires 100,000 pre-market
shares, so the truly dead bars are a small fraction of a population that is
already filtered.

**What would make me wrong, and it is the interesting outcome:** a monotone
bottom half with AUC clearing 0.60. That would mean the tape's thickness at the
moment of entry is a genuine discriminator that both strategies are blind to,
and a floor becomes the best-founded entry rule this project has had — because
unlike every gate tested so far it would be reading something the price does not
already contain.

**A second thing I expect to be wrong about, stated separately:** I expect
MCL's §3.3(5) reading to show that "three times nothing" is common rather than
exceptional — that a material share of MCL's entries sit in the bottom deciles
despite passing both ratio clauses. If that is *not* what it shows, DAIC was a
one-off and the handover's case is weaker than it reads.

## 7. Nothing ships

`holdout.json` untouched. No strategy constant is read, written or swept; no
engine parameter changes; no live path is touched. The pass reads the published
books and the tape, and writes a report and a CSV.
