# Fixed-cent stops vs the percentage trail — measured, 2026-09-10

Ben's handover names this **the single largest decision in the Warrior set**:
every stop in our engines is a percentage, every stop Ross Cameron states is
10–20 cents, and targets, share count and the 2:1 ratio all scale from
whichever wins.

**Measured. The cent stop is worse at every value tested, in both halves, and
the direction points away from cents entirely rather than toward a better cent
value.**

Report: `var/reports/cent_stop.txt`. Tool: `common/cent_stop_study.py`.
No Databento dependency — this runs on `bar_cache`, which was already on disk.

---

## 1. What was pinned, before running

15c is the primary: it is what he says he uses most often (V-SCALP 34:03), and
it was chosen for that reason and not because it won. 10c and 20c are a
**boundary check** on the ends of his stated range, not a menu.

The whole argument in one line:

> **15c is 7.50% at $2, 3.00% at $5, 1.50% at $10, 0.75% at $20.**

## 2. The result

373 sessions, MCL live config, 100 shares flat, after tiered commission and the
measured $4.26/RT.

| variant | trades | net | per trade | win% | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|---:|
| **5% trail** | 485 | **+$161** | +$0.33 | 34.0% | −$923 | −$248 | +$410 |
| 10c stop | 546 | −$2,171 | −$3.98 | 23.8% | −$2,900 | −$749 | −$1,422 |
| **15c stop** | 525 | **−$917** | −$1.75 | 28.4% | −$1,709 | −$413 | −$503 |
| 20c stop | 512 | −$411 | −$0.80 | 31.4% | −$1,198 | −$92 | −$318 |

15c against the trail: **−$1,078 net, worse in both halves**, win rate 28.4%
against 34.0%.

**It is monotone, and that is the finding.** Tighter is worse at every step, and
20c — the loosest cent value, and the closest to what 5% is on this universe —
is the least bad. The gradient points at the percentage rule, not at a cent
value we have not tried. The study's boundary check fires on exactly this: the
best cell sits at an edge of his stated range, so the range is in the wrong
place and none of the three is adoptable.

Trade count *rises* as the stop tightens (485 → 546) because stopping out
sooner frees the slot to re-enter. More trades, worse result.

## 3. Where it actually diverges — the table that matters

A fixed distance and a percentage of price separate across the band by
construction, so a single total describes nothing.

| entry price | 5% trail | 15c stop |
|---|---:|---:|
| $2–4 | −$3.89/trade | −$5.18 |
| $4–7 | −$1.67 | −$1.88 |
| $7–12 | **+$5.40** | −$0.63 |
| $12–20 | **+$8.70** | +$4.73 |

At $2–4 the two rules are nearly the same thing (15c ≈ 5% at $3), and they
perform nearly the same. The gap opens exactly where the arithmetic says it
must: above $7, where 15c is under 2% and stops the trade out of moves the
percentage trail rides.

**A finding about MCL, not about Cameron, falls out of the same table:** the 5%
trail makes all of its money above $7 and loses below it. −$665 in $2–4, −$253
in $4–7, +$540 and +$539 in the two upper bands. Nothing in this project has
looked at MCL by price bucket before, and the price band is $2–20.

## 4. What this does not settle

**It is not his stop.** His is `min(pullback low, 10–20c)` — a structure stop
with a cents cap, and it **does not trail**. This swaps one variable inside
MCL's trailing stop and holds everything else constant, which is the only way
to attribute a difference to cents-versus-percent rather than to four changes
at once. A faithful implementation of his rule is a different measurement.

**Nothing here is out of sample.** MCL's parameters were fitted on these
sessions. A cent stop that had won would not have been shown to generalise —
only to beat a rule tuned on the same data.

## 5. Consequence for the rest of the Warrior set

Warrior 1 §6 open question 2 asked whether the fixed-cent stop survives the
price band. **It does not, and the band is why.** Everything downstream in
`warrior_0_universe_and_risk.md` §5.2–5.4 that scales from a 10–20c stop — the
2:1 target, the 15–20c first target, the risk ÷ stop-distance share count —
inherits that, and has to be re-read against a percentage stop before any of it
is built.

His own numbers are consistent with this being a universe difference rather
than a mistake on his part: he trades an average of 10,000 shares with a 14c
average winner. On that size a 15c stop is a $1,500 risk unit. At our 100
shares it is $15, which the $4.26 round-trip friction eats 28% of.

## 6. A note on how the measurement was validated

Three mutations of the new trail arithmetic survived the first test pass — the
cents branch removed, the sign flipped, `is not None` weakened to a truth test
— because the synthetic fixture exited on `window_close` either way. The
arithmetic moved to `MCL.stop_level()` and is now asserted directly, and the
fixture that hid it has its own guard asserting it stops out at all.
