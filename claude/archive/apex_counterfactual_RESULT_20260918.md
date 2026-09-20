# RESULT — what MC5's apex exit cost on 2026-09-17: essentially nothing

**2026-09-18.** Registered `docs/research/REGISTERED_apex_counterfactual.md`
(PRE-RUN, `78801cf`); code `a85b24b`. Raw report:
`D:\Trading\Claude outputs\apex_counterfactual_RESULT_20260918.txt`.

> **Removing the apex exit does not turn 2026-09-17 green.** Two MC5 arms,
> identical but for `use_apex`, on the same universe, tape, dates, entry rule
> and fills: **apex ON 23 trades (97); apex OFF 21 trades (100)** at the $4.26
> friction level. The delta is **(3)** — about zero, and it does not hold its
> sign across the friction range.
>
> **Over the window the direction is the published one.** 09-08..09-16 on both
> tapes: apex-off is worth **+2.32/trade on BASIC and +2.39 on ITCH**, agreeing
> to seven cents, consistent with the full-sample +$1,702 at a 5% trail.

---

## 1. Why this was measured and not computed

MC5 lost **(85.21)** live on 09-17. Ten exits were `gradient_reversal` — the
apex exit, ON live since 09-10 because `evaluate_last_bar` never read the
constant — and those ten booked **(150.74)**. Subtracting gives **+65.53**, a
green day.

That subtraction assumes the ten positions produce **zero**. They do not.
Removing an exit does not remove the trade: the position runs on to the 5%
trailing stop or the 09:30 window close. **Nine of the ten were already 2–4%
underwater when apex fired**, which is close to that stop — so the later exit
was always as likely to be worse as better. And the ten are not independent:
MEDS appears five times as sequential re-entries on one name, so killing the
04:31 exit kills the 05:31 entry too.

## 2. The control

The two arms differ in trade count and net in every window below. A run whose
arms came out identical would have measured nothing and had to say so rather
than print a 0.00 delta — §4's *a variant that equals its base*. A test asserts
the `--use-apex` flag reaches the engine's kwargs, because an inert flag is
exactly how that failure would arrive.

## 3. 09-17 alone — the answer

XNAS.BASIC, 15 symbol-days, point-in-time arm.

| arm | trades | net @ $4.26 | per trade |
|---|---:|---:|---:|
| apex ON | 23 | (97) | (4.20) |
| apex OFF | 21 | (100) | (4.74) |
| **delta** | −2 | **(3)** | **(0.54)** |

And across the friction range the sign does not hold:

| friction | apex ON | apex OFF | delta |
|---|---:|---:|---|
| $1.00 | (22) | (31) | apex off **$9 worse** |
| $4.26 | (97) | (100) | apex off **$3 worse** |
| $8.92 | (204) | (197) | apex off $7 better |

**Live MC5 on 09-17 was 30 trades, (85.21); the apex-ON arm is 23 trades, (97)**
— close enough that the simulation is describing the same session, which is
what makes the delta readable at all.

## 4. The window, and the tape check

The ITCH extension universe stops at 09-16, so 09-17 ran on BASIC. The
registered check on that deviation is whether the two tapes agree where both
exist. At $4.26, 09-08..09-16:

| tape | arm | trades | net | per trade |
|---|---|---:|---:|---:|
| BASIC | apex ON | 77 | (632) | (8.20) |
| BASIC | apex OFF | 71 | (417) | (5.88) |
| BASIC | **delta** | | **+215** | **+2.32** |
| ITCH | apex ON | 107 | (631) | (5.90) |
| ITCH | apex OFF | 93 | (326) | (3.51) |
| ITCH | **delta** | | **+305** | **+2.39** |

**+2.32 against +2.39 — the tape check passes**, and the BASIC-only reading for
09-17 stands.

Over 09-08..09-17 on BASIC: ON 99 trades (667); OFF 92 trades (423); delta
**+244 total, +2.14 per trade**.

## 5. The registered prediction, and where it was wrong

Recorded pre-run: *"the delta on 09-17 is positive but smaller than +150.74 …
whether it exceeds +85.21 is genuinely uncertain."*

Right that it is far smaller than +150.74. **Wrong on the sign** — the delta is
about zero and slightly negative at the primary friction level.

## 6. What this is not

**One session is not a reading**, registered before the number existed. The
sign flipping across the friction range on 09-17 is what n=1 noise looks like.
Nothing here changes the full-sample figure, and nothing here can promote MC5 —
it is CLOSED as a candidate at (8.57) per trade over 6,462 point-in-time trades.

**What promoting `prod-20260918` buys is not a better 09-17.** It is that live
MC5 now runs the configuration its published figures describe, so from tonight
its fills are comparable to the backtest at all — which they have not been
since 10 September.
