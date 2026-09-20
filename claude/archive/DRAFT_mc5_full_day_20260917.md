# MC5 full day (04:00–20:00) — REGISTERED 2026-09-17, not yet run

Registration: `docs/research/REGISTERED_mc5_full_day.md`. Commits on `main`, not pushed:
- `5a52b9c` — the registration;
- `725c16c` — amendment A, PRE-RUN.

**Amendment A changes the tape to XNAS.ITCH** in every window (see
`handover_tape_switch_20260917.md`). It also changes:
- the pre-market universe, to `screen_pairs_pit_itch_p50.json`;
- the volume thresholds, to the chained ITCH capture from `tape_capture`.

The study waits for the ITCH baselines from `REGISTERED_screen_itch.md`.

Ben's decisions:
- backtest first, live trader untouched;
- the screen runs all day, one top-40 cap, names never dropped;
- RTH: up ≥ 20% vs the prior regular close, $2–25, volume from 09:30 ≥ 100k (scaled);
- POST: up ≥ 20% vs today's 16:00 close, $2–25, volume from 16:00 ≥ 100k (scaled);
- pull both blocks for all symbols.

Arms:
- A — control, 04:00–09:30;
- B — frozen, runs to 20:00 on names found by 09:30;
- C — running screen, primary.

PASS needs all five on C's entries at or after 09:30:
- more than $0 per trade at $4.26;
- both halves positive;
- still positive after dropping the top 5 symbols;
- cluster bootstrap positive in ≥ 95% of resamples;
- session median above 0.

Size probe, XNAS.BASIC only (2026-08-04, ALL_SYMBOLS, billable), all at $0.0000:

| window | MB |
|---|---|
| PRE | 11.0 |
| RTH | 136.7 |
| POST | 11.0 |

E: has 7,918 GB free.

Next:
1. Price the XNAS.ITCH 09:30–16:00 and 16:00–20:00 pulls; the BASIC estimate was cancelled.
2. `--confirm`.
3. Extend `screen_sim` to 20:00.
4. Wait for the ITCH p50 universe.
5. Run.
