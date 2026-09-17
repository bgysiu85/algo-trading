# RESULT — H-C3 profit floor at +5 ticks: MCL REFUSED again, MC5 NOTHING again

Run 2026-09-18 09:02 AEST: `python -m common.profit_floor_study --floor 15,5 --jobs 8`,
code `fe9cdbd`, XNAS.ITCH, `screen_pairs_pit_itch_p50.json` (sha256 1db006ca23d20065, the
same file H-C2 ran on), 551 sessions, 6,564 symbol-days. Report
`var/reports/profit_floor_15_5.txt`. Registered `REGISTERED_profit_floor_v2.md` (`aa03148`).
Both baselines reproduced: MCL 3,960 / (8.81), MC5 6,630 / (8.49). Holdout untouched.

## Verdicts (§3, family bar 0.975)

| | Δ/trade | Δ/symday @ $4.26 | Δ/symday @ $8.92 | halves (trade) | drop-3 symbols Δ | bootstrap P | floor exits | verdict |
|---|---:|---:|---:|---|---:|---:|---:|---|
| MCL | +0.28 | +0.04 | (0.04) | +0.10 / +0.42 | (112.83) | 0.599 | 24.3% | **REFUSED** (denominators disagree at $8.92) |
| MC5 | (0.41) | (0.58) | (0.67) | (0.82) / (0.06) | (4,175.30) | 0.003 | 13.9% | **NOTHING** (fails 1–4) |

Whole book: MCL +239.12, MC5 (3,827.86).

## Against (15, 10) — reported, not scored

MCL per trade (0.00), per symbol-day +0.05 (4,061 trades against 4,100).
MC5 per trade (0.05), per symbol-day +0.01 (6,754 against 6,800).
**Ten ticks of floor changes the book by five cents a trade.** Floor exits fall 1,243 → 985
and 1,212 → 937; runners cut fall 148 → 88 and 154 → 88.

## The mechanism

| | MCL | MC5 |
|---|---:|---:|
| armed | 44.3% | 35.8% |
| floor exits net > $0 at $1.00 / $4.26 | 72.5% / **0.0%** | 57.7% / **0.0%** |
| filled at floor / gapped below / below entry | 684 / 301 / 201 | 518 / 419 / 319 |
| runners cut, P/L forgone | 88, (5,889.02) | 88, (6,370.24) |
| win rate, scratch rate | 23.3 → 18.7%, 8.4 → 23.6% | 23.1 → 20.7%, 7.0 → 13.5% |

**No floor exit at +5 ticks clears $4.26.** Five ticks less the slippage tick is $4.00 gross
on 100 shares, and commission takes about $2. The win rate FALLS because a rescued loser
becomes a scratch rather than a win. That is arithmetic and was knowable before the run;
the registration predicted 10–30% (MCL) and 5–25% (MC5) positive and was simply wrong.
**A floor below about 7 ticks cannot pay for the round trip it triggers.**

Decomposition (descriptive, from the trades CSV, $4.26): MCL losers rescued 765, +9,816;
winners > $20 cut 109, (7,532); small winners 69, (721); re-entries and knock-on (1,324).
MC5: 739, +6,565; 94, (8,306); 63, (736); (1,351).

## What it closes

The family is two cells and both read the same way: the floor's level barely matters, because
what it gives back on winners scales with what it saves on losers. **Closed.** A third pair
needs a reason that is not "try another number", and this result is the prior against it.

**Known defect, cosmetic:** the report's title line prints "H-C2" for both cells; only the
`registered` line distinguishes them. Fix with the next change to the module.
