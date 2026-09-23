# Is MC5 really better than MCL? Result, 2026-09-23 (W02-0002, H-L1): no. Per trade they cannot be told apart; per day MC5 loses more, because it trades more

Registered in `docs/research/REGISTERED_mcl_vs_mc5_live.md` (9e4dddf), before
`common/live_vs_sim.py` existed (7657660, 16 tests). Run 2026-09-23 on
2026-09-08 → 09-22: 11 sessions, 111 symbol-days, XNAS.ITCH. The 21–22 Sep
tape was pulled by Ben ($0.00) and screened into `screen_pairs_pit_itch_ext3.json`.
Raw report: `var/reports/live_vs_sim.txt` (copy in `Claude outputs\live_vs_sim_20260923.txt`).
All six controls pass (C1 289/289 rows against feed_delay's Arm B; C2 9 overlapping
sessions identical; C3; C4; C5 3,908/(8.97), 6,462/(8.57); C6 48 rows).

## In plain terms

- **MC5 is not better than MCL.** Over two years of backtest (550 sessions),
  each strategy loses about the same per trade after costs: MCL $8.97, MC5 $8.57.
  The difference is inside the noise.
- **MC5 loses more per day, because it takes 1.65 trades for every one MCL
  takes.** Per session MCL is better by about $37, and that holds with the
  shared cap of 3 and with a per-strategy cap.
- **"Paper trading shows MCL losing more" came from comparing different
  days.** MCL traded four sessions on its own (2–9 Sep) and lost $298.60 on
  them. On the nine sessions both strategies ran (10–22 Sep), live MCL is
  **+$18.64** over 60 trades and live MC5 is **($595.14)** over 156.
  That is the backtest's answer too, within noise.
- **Neither strategy makes money**, live or backtest. This result ranks two
  losing books. It does not rescue either one.
- **The biggest open fact is not in the question:** the live trader and the
  backtest mostly take *different trades*. Only 9 of 68 live MCL trades have a
  backtest entry within 2 minutes (15 of 33 for MC5 since 18 Sep). Live-vs-backtest
  P/L gaps are mostly "different trades", not execution.

## What Ben must decide

Nothing is forced. W02-0002 closes with the answer above. **Decision (new
W02-0016):** chase why live and sim take different trades (IB bars against
the ITCH tape, the leading suspect), or leave it. Recommended: yes, as a
descriptive study before any further live-vs-backtest comparison. Every
future comparison of this kind is weak until the match rate is understood.

## 1. The answer, per denominator (MCL − MC5; 90% session-bootstrap interval)

| Book | Sessions | MCL trades · net | MC5 trades · net | per trade | per session | Word |
|---|---|---|---|---|---|---|
| Live, both running | 9 | 60 · 18.64 | 156 · (595.14) | 4.13 [(6.20), 13.67] | 68.20 [(19.08), 148.32] | can't tell |
| Live, with IBKR tiered commission | 9 | 60 · (63.65) | 156 · (809.12) | 4.13 | 82.83 [(8.53), 168.01] | can't tell |
| Live, MC5 apex-OFF sessions (18–22 Sep) | 3 | 18 · 241.28 | 33 · (136.36) | 17.54 | 125.88 | *3 sessions: not a verdict* |
| Live, MC5 apex-ON sessions (10–17 Sep) | 6 | 42 · (222.64) | 123 · (458.78) | (1.57) [(14.76), 9.45] | 39.36 | can't tell |
| Sim, feed-matched, uncapped ($4.26) | 9 | 78 · (329.04) | 98 · (189.21) | (2.29) [(14.29), 9.03] | (15.54) | can't tell |
| Sim, feed-matched, shared cap 3 | 9 | 66 · (201.81) | 86 · (478.69) | 2.51 [(8.79), 12.01] | 30.76 | can't tell |
| **Population, uncapped (published)** | 550 | 3,908 · (35,063.12) | 6,462 · (55,364.07) | (0.40) [(2.49), 1.45] | **36.91 [14.01, 56.34]** | per trade can't tell · **per session / symbol-day MCL better** |
| Population, shared cap 3 | 550 | 3,337 · (30,061.76) | 5,809 · (49,120.53) | (0.55) | 34.65 [12.33, 54.02] | same |
| Population, cap 3 per strategy | 550 | 3,863 · (34,902.26) | 6,139 · (52,897.02) | (0.42) | 32.72 [10.30, 51.90] | same |

Per symbol-day on the population: MCL (5.47), MC5 (8.64), difference 3.17
[1.20, 4.82]. The shared-cap rows show the MCL-first tie order; the MC5-first
order gives the same words (raw report §3–4).

## 2. Where live and sim part company (live − sim, gross, feed-matched)

| | Sessions | live | sim | live − sim | matched (execution) | live-only | sim-only removed |
|---|---|---|---|---|---|---|---|
| MCL | 11 | 68 · (115.36) | 86 · 75.71 | (191.07) | 9 · +19.99 (+2.22/trade) | 59 · (206.99) | 77 · (4.07) |
| MC5 apex-ON vs apex-ON book | 6 | 123 · (458.78) | 66 · (2.67) | (456.11) | 23 · +192.75 | 100 · (651.20) | 43 · 2.34 |
| MC5 apex-OFF | 3 | 33 · (136.36) | 44 · 84.78 | (221.14) | 15 · (245.74) | 18 · 0.23 | 29 · 24.37 |

- **Live-only trades carry the gap on both strategies.** Of MCL's 59, 48 are
  on names the sim screened but with no sim entry within 2 minutes, and 11 on
  names the sim never screened.
- **MC5 apex-OFF "execution" (245.74) is one trade.** VEEE 21 Sep: live
  bought 10.91 at 08:35 and lost (45.38); the sim bought 11.69 at 08:40 and
  made 231.61. Those are almost certainly different signal bars. Without VEEE,
  execution is about +31 over 14 matches.
- **The sim-only trades the live cap refused:** MCL 11 worth 57.82 and MC5
  apex-OFF 13 worth 1.90 (gross). Live refused 36% of both strategies' buy
  attempts, 38 of 106 MCL and 116 of 316 MC5. So the cap hit the two
  strategies at the same rate live.

## 3. Predictions scored

- **P1** (live per trade MCL − MC5 negative, "can't tell"): word **held**,
  sign **failed**. It is +4.13, MCL better, because 21–22 Sep went MCL's way.
- **P2** (sim, same sessions, "can't tell" on both, capped or not): **held**.
- **P3** (population: per trade can't tell, per symbol-day MCL better, the cap
  flips nothing): **held**, on all six cap variants.
- **P4** (the shared cap refuses more of MCL than of MC5 and moves per trade
  by less than $1): **held**. 14.6–16.4% of MCL against 9.3–10.1% of MC5;
  per-trade moves of $0.04–0.14.
- **P5** (matched execution negative, (1)–(8) a trade): **failed**. MCL
  +2.22, MC5 apex-ON +8.38, MC5 apex-OFF (16.38) on one trade. With 9–23
  matches, execution is not measurable here.
- **P6** (the disagreement is denominator plus noise): **held**. No book with
  the sample to speak says MC5 is better on any denominator.

## 4. Post-run, not scored: under today's real-time feed

Amendment A. With the +0 book on every session (what the now signed-in feed
would have traded), MC5 reads +239.53 over 119 trades against MCL (453.41)
over 87. That is (7.22) a trade MCL − MC5, interval [(16.24), 2.16]:
**can't tell**. It rests on MC5's best days: AEMD 17 Sep +308.63, VEEE 21 Sep
+231.61, TNMG 18 Sep +220.63. Drop MC5's top 3 and it is (4.38) a trade.
This is the same fact `feed_delay_cost_RESULT` §1 found on the population:
the delayed feed removed MC5's early entries, and those are its better ones.
Whether the real-time feed lifts live MC5 is something the next sessions will
show. Eleven sessions cannot.

## 5. Caveats

- Live P/L is price-only as logged; the IBKR-tiered row adds commission. The
  MEDS 16 Sep exit fill is missing (W02-0008). CRML 21 Sep is used as logged
  (W02-0014).
- The cap replay can only remove sim trades. It does not free the later
  entries that a refused trade would have allowed.
- A session bootstrap on 3 sessions has about 10 distinct resamples, so the
  apex-OFF live row is printed without a verdict.
- 23 Sep is excluded: it ran `cap_scope=strategy` (W02-0015).
- Sessions up to 18 Sep are compared with the +15 book, 21–22 Sep with +0.

## 6. Files

`common/live_vs_sim.py`, `tests/common/test_live_vs_sim.py`,
`var/reports/live_vs_sim.txt`, `live_vs_sim_trades.csv` (every matched,
live-only and sim-only trade), `live_vs_sim_books.csv`, `live_vs_sim.json`,
`var/state/screen_pairs_pit_itch_ext3.json`, `var/reports/screen_sim_itch_ext3.txt`.

## Next steps (board)

- W02-0002: Done.
- **W02-0016** (new, Ben): whether to study why live and sim take different
  trades.
