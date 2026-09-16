# REGISTERED — MCL-PB v3: the break must close on volume; profit is banked in N bars

Supersedes v2 (`REGISTERED_pullback_break_v2.md`, NOTHING —
`claude/pullback_break_v2_RESULT_20260916.md`). Ben inspected v2's ten most recent
trades on 2026-09-11, named six he would not have taken and eight he would, and
sent a chart of a Bollinger squeeze resolving on volume. Every rule below was
checked against those fourteen bars before this was written; the checks are in
§4. **Committed before `common/pullback_break` runs v3 on the universe.**

## 1. The rule, exactly

Unchanged from v2 unless named: session state walked through trades, swing high
= a bar that out-highs its predecessor, red = `close < open`, armed after ≥ 2
red bars since the peak bar (peak bar counts if red), 60-bar expiry from the
peak bar, no depth cancel, MCL's engine for exits, `first_seen` floor, $2–20.

| step | rule | chosen by |
|---|---|---|
| **Level** | once armed, the level is the **highest high printed since the arming bar**; until a bar has printed it is the peak. A bar that exceeds the level but does not qualify (below) simply raises it | Ben's TNON 07:35 (7.36 = the 07:31 bounce high, not the 7.43 peak) and 06:47 |
| **Break** | a bar whose high reaches `level + $0.01` | Ben |
| **Qualify** (all, on the break bar, at its close) | `close > level` · `volume > SMA20(volume of the 20 bars before it)` · `macd > macd_sig` on this bar | Ben: "at entry, volume above volume MA20"; "on the break bar" for MACD |
| **Fill** | the break bar's close + 1 tick, MCL's convention | Ben: "enter at the bar's close" |
| **Consolidation** | **no filter** — on the fourteen examples band width before the break does not separate good from bad (§4) | Ben, after seeing §4 |
| **Green hold** | at the bar N after entry, if `close > entry_px`, exit at that close − 1 tick (`green_hold`); otherwise keep holding on the trail. Tested after the trail, before the window close | Ben: "if in the green, not held more than 3–5 bars" |

Only the lowest live level of a bar can be entered on; all levels the entry bar
crossed are consumed. Nothing fires while a position is open, before
`first_seen`, or on the final in-session bar.

## 2. Cells

| cell | green hold |
|---|---|
| **PB3-g3** (primary) | 3 bars |
| PB3-g5 | 5 bars |
| PB3-g0 | none — the ablation, so the exit's own effect can be read |

No cents target: v2 showed neither 10c nor 25c changes the sign. The verdict
(v1 §3, unchanged) is read on **PB3-g3**; g5 and g0 are reported.

## 3. Control and reading

MCL as published, same run. Frequency printed as in v2. `holdout.json` untouched.

## 4. What the fourteen examples said

Break-bar volume over the prior-20 average: good entries 0.72, 5.21, 2.10, 2.39,
3.74, 2.13, 5.73, 6.89; bad entries 0.10, 1.67, 0.47, 0.24, 0.97, 0.96. At
Ben's threshold of 1.0× the rule keeps 7 of 8 good and removes 5 of 6 bad. The
bar **before** the break separates nothing (good 0.32–2.01, bad 0.07–1.75).

Bollinger width (20 EMA, 2σ) on the bar before the break, as a percentile of
the previous 60 bars: good 28, 8, 98, 97, 7, 67, 98, 0; bad 8, 18, 20, 83, 5,
27. No threshold separates them. The 20-bar-high test drops five of the eight
good entries. Hence no consolidation filter.

MACD on the bar before: TNON 08:31 and FTFT 09:13 (both good) read closed; on
the break bar both read open. All six bad entries read open either way.

Under this rule on this tape, of Ben's eight: TNON 06:48 (7.41, one bar after
his 06:47 because 06:47's volume was 0.72×), 07:35 (7.49), 08:31 (8.27) and
FTFT 09:13 (2.48) enter; 07:42, 07:46, LBGJ 05:38 and FTFT 07:16 depend on the
green-hold exit having freed the position first, which is what the cells test.
The entry prices are the cost of waiting for the close, which Ben accepted.

Tuning set: one session, 2026-09-11. It is inside the 551 and is not excluded;
one day in 551 cannot carry a verdict, and the halves rule still applies.
