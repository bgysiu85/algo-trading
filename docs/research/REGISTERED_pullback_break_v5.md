# REGISTERED — MCL-PB v5: the decisive close

v4 (`REGISTERED_pullback_break_v4.md`, `claude/pullback_break_v4_RESULT_20260916.md`)
closed the stop lever for the pullback line: +0.18 a trade, worse in total. What
v3's trades still contain, on Ben's own reading of 2026-09-11, is breaks taken
INSIDE a squeeze (TNON 08:15 at 8.10, inside the box he marked) alongside the
break OUT of it (08:31). Volume did not separate those two. v5 adds one
condition to v3's entry and changes nothing else.

## 0. How the definition was chosen, and what that makes it

Fifteen bars from one session — the seven entries Ben would not take, including
the box, and the eight he would — were measured five ways. The one that removed
all seven and kept five of the eight was the **decisive close**: the break bar's
close clears the level by at least one average bar. Reading RSI beside the bands
gave a second, independent-looking separation: the eight good breaks close with
**RSI(14) ≥ 64** after RSI had been falling into the break; the seven bad close at
44–61. Both are **fitted on fifteen bars**. Their thresholds are fixed here; the
other 550 sessions are the test. Neither is evidence yet.

## 1. The rule

Everything as v3 (swing high, two red bars, bounce-top level, break bar closes
above the level on volume > prior-20 average with MACD > signal, entry at that
close + 1 tick, 5% trail, optional 3-bar green hold). No structure stop. Plus
ONE of:

| definition | condition on the break bar `j` | fixed |
|---|---|---|
| **ATR** | `close[j] − level ≥ 1.0 × ATR10`, ATR10 = mean true range of bars `j−10 .. j−1` | 1.0 |
| **RSI** | `RSI14[j] ≥ 64` (MCL's own `rsi` column, Wilder, on closes) | 64 — the lowest of the eight good examples |

A break that fails the condition is refused and the level rises to that bar's
high, as every other refusal.

## 2. Cells

| cell | decisive close | green hold |
|---|---|---|
| **PB5-atr-g3** (primary) | ATR | 3 |
| PB5-rsi-g3 | RSI | 3 |
| PB5-atr-g0 | ATR | none |
| PB3-g3 | none — v3, the control | 3 |

## 3. Readings — with the margin v4 lacked

1. PB5-atr-g3 against MCL: v1 §3 unchanged (CLEARS / IMPROVES / NOTHING).
2. PB5-atr-g3 against PB3-g3: net per trade better in **both halves by at least
   $4.26** (one round trip's friction), AND total net better in both halves.
   Anything less is NOTHING however the letter reads. v4 passed on +0.18 and
   that must not repeat.
3. PB5-rsi-g3 is read the same way against PB3-g3, reported, not registered:
   two definitions of one idea, one of which was chosen as primary before the
   run.

`holdout.json` untouched.
