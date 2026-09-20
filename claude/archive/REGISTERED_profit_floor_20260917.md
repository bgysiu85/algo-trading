# H-C2: profit floor beside the 5% trail, MCL and MC5 — BUILT, not yet run

Registration: `docs/research/REGISTERED_profit_floor.md`, commit `2b1620a`, plus
amendment A (PRE-RUN), which covers two things:
- halves are cut at the median session, as every PIT study does;
- drop-top-3 removes 3 SYMBOLS, not 3 symbol-days.

Build: bundle `profit-floor-20260917a` (commit `114779f`, on top of `d796640`).

**Rule.** Once a bar after entry trades at or above entry + 15 ticks, the stop is
max(5% trail, entry + 10 ticks) from the next bar. Fill is min(level, open) − 1 tick;
label `profit_floor`.

**Engines.** `profit_floor=(arm, floor)` on `mcl.backtest_session` and
`mc5.backtest_session`. None is bit-identical. There is one implementation
(`mcl.check_profit_floor / reaches_arm / floor_level`), and mc5 imports it.
- `tests/strategy/test_profit_floor.py`: 42 cases across both engines, 8 mutations caught.

**Study.** `python -m common.profit_floor_study --jobs 8`, output
`var/reports/profit_floor.txt` plus a trades CSV.
- Four books; refuses any tape but XNAS.ITCH.
- NO VERDICT unless each baseline reproduces its published figure: v1 p50 MCL 3,960 /
  (8.81), MC5 6,630 / (8.49), keyed by pairs file. A different universe needs `--expect`.
- `--limit` disables that check.
- `tests/common/test_profit_floor_study.py`: 17 cases, 8 mutations caught.

**Suite.** 3,114 passed. 6 failures, all a missing `sqlalchemy` in the cloud sandbox.

**Readings, per strategy.**
1. Δ per trade and per symbol-day > 0 at $4.26 and $8.92.
2. Both halves.
3. Drop-top-3 symbols on the delta.
4. Cluster bootstrap ≥ 0.95.
5. Floor exits ≥ 5%.

**Printed.** Share of floor exits net > $0 at each friction; gap fills and fills below
entry; runners cut; cascade.

**Prediction.** NOTHING for both. Δ per trade (1.50) to +1.00. 40–65% of floor exits
positive at $4.26.
