# REGISTERED — MCL-PB v2: peak, two red bars, buy the break

Supersedes `REGISTERED_pullback_break.md`, whose rule returned NOTHING
(`claude/pullback_break_RESULT_20260916.md`). Ben inspected the ten most
recent trades and gave five he wanted taken (AEHL 2026-09-03 07:33 / 07:59 /
09:16, WETO 2026-09-04 04:04 / 05:26). Four of the five were reproducible on
the XNAS.BASIC tape and all four share one shape, which v1 could not take
because v1 required MCL's signal BEFORE the pullback — in every example the
signal lands on the break bar or 1–2 bars after it.

**Committed before `common/pullback_break` has run v2.** Every choice is Ben's
from chat on 2026-09-16 or fixed here in advance. A change after a run is a
new registration.

---

## 1. The rule, exactly

Everything not named here is MCL as published (`common.analysis.LIVE`, 5%
trail seeded at the fill, flat at 09:30, 100 shares, $2–20 band, point-in-time
`first_seen` floor). **MCL's five-clause signal is not part of the entry.**

| step | rule | chosen by |
|---|---|---|
| **State** | walked over every in-session bar of the symbol-day from 04:00, in and out of trades; only the trigger is gated on being flat | fixed here |
| **Swing high** | a bar whose high exceeds the previous bar's high starts a candidate; higher highs raise it. A bar with a lower high than its predecessor never starts one, so the lower highs inside a decline are not peaks | fixed here (§5) |
| **Red bar** | `close < open`. The peak bar counts if it is red | Ben, from AEHL 09:16 |
| **Level** | the candidate becomes a live level once ≥ 2 red bars have printed since its peak bar; the candidate then resets. **Several levels can be live at once** (§5) | Ben: "at least 2 red bars from the peak" |
| **Trigger** | buy-stop at `level + $0.01` on the lowest live level; fires on the first bar `j` whose `high ≥ level + 0.01` while flat, if `macd[j-1] > macd_sig[j-1]` | Ben: "stop at peak+1c"; "above signal line only" |
| **Fill** | `max(level + 0.01, open[j]) + 1 tick` | fixed, as v1 |
| **Refused break** | a level crossed while MACD is closed, while in a trade, before `first_seen`, or on the final bar is removed and counted (`refused_macd` / `refused_busy` / `window`) | Ben: "a new peak resets it" |
| **Time limit** | a level expires **60 bars** after its peak bar | Ben chose a limit; **60 is mine, fixed here** (§5) |
| **Gates** | not on the final in-session bar; not before `first_seen`; not on a trade's own exit bar; engine's price band | fixed |
| **Depth** | **no depth cancel** — AEHL 07:59 fell 20% below its peak before breaking and Ben wants it | Ben |
| **Exit** | MCL's engine: 5% trail, 09:30 flatten, **plus** an optional full exit at `entry + target_cents` (resting limit, stop wins ties, no tick) | Ben: "fixed profit in cents/share" |

## 2. Cells

Three, all printed, none chosen from the table:

| cell | target |
|---|---|
| **PB2** (primary) | none |
| PB2-10c | 10 cents |
| PB2-25c | 25 cents |

10 and 25 are the two values Ben named. The registered verdict is read on
**PB2**; the target cells are reported beside it and any claim about them is
a direction, not a result.

## 3. The control and the reading

MCL as published on the same sessions, universe, floor, size and costs, same
process. Verdict rule unchanged from v1 §3 (CLEARS / IMPROVES / NOTHING at
$4.26; PRE-07 line). Frequency must be printed: setups armed, triggered,
refused-on-MACD, expired, per symbol-day — this rule fires without MCL's
filter and is expected to trade far more often.

`holdout.json` untouched.

## 4. What the examples say about the tape

WETO 04:04 is not reproducible here: no red bar after the 04:00 high and MACD
below its signal, four minutes into a session whose indicator still carries the
prior day — and this feed's prior day is the 04:00–09:30 slice, not the full
day Ben's chart shows. Recorded so a miss on that trade is not read as a rule
defect.

## 5. Amendment, before the study ran

The first draft of §1 defined the peak as the session's running highest high.
Checked against Ben's examples before `common/pullback_break` ran v2 on the
universe, it took none of them: at AEHL 07:33 the running high was 6.79
(07:18) and the 6.20 top Ben bought the break of is a bounce inside that
pullback. Both tops are levels to him, and each was bought on its own break
(07:33 and 07:58). So a peak is a **swing high** — a bar that out-highs its
predecessor — and levels **coexist**.

The time limit was 30 bars in that draft. Ben's 07:58 entry breaks a level
whose top is 40 bars earlier. 60 is the smallest round number that takes it;
still mine, still fixed before any universe run.

With this rule and no target, on the tape here: AEHL 07:33 **taken** at 6.22,
AEHL 07:58 **taken** at 6.86, AEHL 09:16 **not taken** (already long from a
09:03 break of 7.28, held to 09:18), WETO 05:26 **not taken** (already long
from a 04:45 break of 4.00). Recorded so those two misses are read as "in a
trade", not as a rule defect.
