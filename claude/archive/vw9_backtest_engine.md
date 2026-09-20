> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it. Applied to VW9 that correction cost roughly 73% of its
> headline; MCL went +$1,567 → +$161 and MC5 +$20,156 → −$400, on identical
> trades.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# VW9 backtest engine — delivered and test-verified locally, not yet run against real data

Built 2026-09-05, on branch `feature/vw9-backtest` (commit `03f82db`) of the
`bgysiu85/algo-trading` repo. **Update 2026-09-05, same day:** the bundle was
fetched and pushed to GitHub by Ben, and the full suite —
**64/64 tests passing** — was confirmed directly on bens-proart (not just in
the build sandbox). The branch exists on GitHub now; merge to `main` whenever
ready. The backtest itself has **not** been run against real IB data yet —
see "Next" below. Supersedes `claude/vw9_setup_count_measurement.md` as the
"what's built" record for VW9 — that doc's own step 4 ("only after [§8
calibration]: write the real strategy") was explicitly skipped at Ben's
request, in favor of getting a full backtest with P/L now, on the
understanding that 12 of 18 parameters are still uncalibrated guesses (see
below).

## What this is

`claude/vw9_strategy_spec.md`'s §4.3 entry gates, §5 exits, and §9 execution
model, implemented against the real, **post-reorg** repo layout (`common/`,
`strategy/vw9/`, `common/backtest.py`'s `Runner`) rather than the pre-reorg
standalone scripts the earlier setup-count build targeted. Entries themselves
(§3 regime gate, §4.1 Setup A, §4.2 Setup B) were already built in
`strategy/vw9/vw9.py` for the §8.3 measurement; this build adds gating,
position simulation, fills, and wires it into the same CLI MCL and MC5
already use.

## What was built

- **`strategy/vw9/vw9.py`** — `find_setups()`'s Setup B branch now populates
  three fields added to the `Setup` dataclass (`pullback_start_idx`,
  `impulse_max_up_vol`, `pullback_max_down_vol`), needed by the §4.3
  pullback-volume gate. These fields existed on the dataclass from the prior
  session but were never populated — a running max of up-bar volume during
  the STRONG impulse is frozen the instant a pullback opens (since the
  running value itself resets to 0 the same bar, regime having left STRONG),
  and a running max of down-bar volume accumulates for the pullback's
  lifetime.
- **`strategy/vw9/backtest.py`** — the engine itself:
  - `_passes_entry_gates()` — liquidity (trigger-bar dollar volume vs.
    `MIN_TRIGGER_DV_PER_MIN * bar_minutes`), extension
    (`(close-ema9)/atr14 <= MAX_EXT_ATR`), and Setup B's pullback-volume gate.
    Re-entry is handled by the caller (`backtest_session_tf`), since it's the
    only gate needing state across trades.
  - `_simulate_trade()` — fills at the bar **after** the trigger bar's open
    plus slippage (§9 — not MCL's trigger-bar-close, since extended hours
    takes Day Limit orders only), then manages to whichever of the §5.3 hard
    exits (stop > VWAP-lost > session-end, checked in that order so "stop
    wins" on intrabar stop/target ambiguity falls out for free) or the
    `exit_mode`'s target comes first. All three §5.2 variants
    (`fixed_2r`/`ride_ema9`/`trail_atr`) are implemented; a call picks one.
  - `backtest_session_tf()` — the per-session driver: slices to the
    04:00–20:00 session, resamples to the requested timeframe, runs
    `find_setups()`, applies the entry gates plus the re-entry cap
    (`MAX_ENTRIES_PER_SESSION=4`, ≥1 bar gap — enforced with one
    `blocked_until` check that also prevents overlapping positions), and
    simulates each surviving trigger.
  - `Trade` dataclass mirrors `strategy/mcl/mcl.py`'s shape (same
    `asdict()`-ability `common/backtest.py`'s `Runner` depends on) plus VW9-
    specific fields: `timeframe`, `setup_kind`, `exit_mode`, `r_multiple`,
    `session_block` (PRE/RTH/POST, per §9's own report requirement).
- **`strategy/vw9/vw9_5m.py` / `vw9_15m.py`** — thin adapters registering the
  two timeframes (§7 cells A and B) with the `Runner`. Each exposes
  `SESSION_START`/`SESSION_END`, `BACKTEST_SESSIONS=1` /
  `BACKTEST_END_HOUR=20` / `BACKTEST_END_MINUTE=0` (VW9 needs one session
  ending 20:00, not MCL/MC5's two sessions ending 09:30), and a
  `backtest_session(df, session_date, tz, exit_mode=...)` wrapper.
- **`common/backtest.py`** — generalized. The `Runner` previously read
  module-level `HIST_SESSIONS`/`HIST_END_HOUR`/`HIST_END_MINUTE` constants
  hardcoded for MCL/MC5; it now reads
  `getattr(self.S, "BACKTEST_SESSIONS", HIST_SESSIONS)` (and the two END_*
  equivalents) per strategy, falling back to the MCL/MC5 defaults when a
  module doesn't define them — so MCL/MC5 behavior is unchanged, and both
  windows still slice from the one shared "3 D" superset fetch. Also added a
  `--exit-mode` CLI flag, threaded through to
  `self.S.backtest_session(df, target, ET, exit_mode=...)` with a
  `try/except TypeError` fallback to the plain 3-arg call for strategies
  (MCL/MC5) that don't accept one — so the three VW9 target variants can be
  run and compared per §10's report requirement without a separate code path.
  `STRATEGY_MODULES` now includes `"vw9_5m"` and `"vw9_15m"`.
- **`main.py`** — `BACKTEST_STRATEGIES` now includes `vw9_5m`/`vw9_15m`
  (`LIVE_STRATEGIES` unchanged — VW9 has no live/streaming interface).
- **`tests/strategy/vw9/test_vw9_backtest.py`** — 13 new tests, each
  scenario verified interactively (indicator columns and resulting trades
  printed and checked) before being pinned, matching this repo's existing
  practice: the fill model, all three entry gates (with a positive control
  proving the pullback-volume gate is a real comparison, not a blanket Setup
  B rejection), all three hard exits, intrabar stop/target ambiguity, all
  three exit modes, and the re-entry cap (a 5-raw-trigger session correctly
  yields exactly 4 trades, each opening strictly after the previous one's
  exit). Full suite: **64/64 passing** (51 pre-existing + 13 new) — verified
  in the build sandbox AND independently on bens-proart's own venv
  (2026-09-05), which is the run that actually counts per this project's own
  "green in one environment is not a baseline for another" rule.

Also smoke-tested end-to-end offline in the build sandbox: a synthetic
3-session gzip superset in the shared cache layout, confirming `Runner`
slices 960 bars (one session ending 20:00) for `vw9_5m`/`vw9_15m` and 1290
bars (two sessions ending 09:30, matching the documented IB session-counting
arithmetic) for `mcl` — from the *same* cached file, no extra fetch. What was
**not** exercised, anywhere: a real IB connection or real market data — same
caveat as the setup-count build.

## Two documented scope cuts

- **§4.4 context levels (and the `MIN_HEADROOM_R` gate that depends on
  them) are not implemented at all** — not stubbed to always-pass, simply
  absent. This pipeline has no daily-bar source to compute the daily 200 EMA
  or prior-session high/low from, and the gate is off by default per §4.3's
  own table regardless, so nothing is silently skipped that would otherwise
  run.
- **`MIN_TRIGGER_DV_PER_MIN` uses the spec's own naive placeholder scaling**
  ($20k/30s → $40k/minute → $200k per 5m bar, $600k per 15m bar). §6 says
  outright "do not guess this one — measure the actual distribution (§8.2)
  and set it from that." That measurement has not been run. This constant
  is flagged in the module docstring as a placeholder, not a calibrated
  value, and should be the first thing revisited once real data is pulled.

Everything else uncalibrated (`MIN_VWAP_BARS`, `MIN_VWAP_DOLLAR_VOL`,
`MIN_BELOW_BARS`, `RECLAIM_LOOKBACK`, `IMPULSE_LOOKBACK`,
`PULLBACK_CTRL_ATR`, `MAX_PULLBACK_BARS`, `MAX_EXT_ATR`, `STOP_BUFFER_ATR`,
`MAX_ENTRIES_PER_SESSION`, `TRAIL_ATR` — 12 of 18 per §6's own count) keeps
its spec-default value, each one a starting point for a sweep, not a claim.

## How to run it (on bens-proart)

Requires `data_ib.py` to have already populated the shared bar cache
(`bar_cache/3d_to_2000/`) for the pairs of interest — same prerequisite as
the setup-count measurement. **Not yet done as of this update** — this is
the next real step, not a formality.

```
python -m common.data_ib                                      # once, populates bar_cache/
python main.py --mode backtest --strategy vw9_5m
python main.py --mode backtest --strategy vw9_5m --exit-mode ride_ema9
python main.py --mode backtest --strategy vw9_5m --exit-mode trail_atr
python main.py --mode backtest --strategy vw9_15m   # §7 cell B, same three exit modes
```

Trades land in `var/reports/backtest_trades_vw9_5m.csv` /
`backtest_trades_vw9_15m.csv` (one file per strategy name, so running a
second `--exit-mode` pass overwrites the first — copy the CSV out, or add
`--out-dir`, between runs if comparing exit modes side by side per §10).

**If `python -m pytest` reports "No module named pytest" despite a `(.venv)`
prompt:** the shell's `PATH` isn't actually pointing at the venv (stale
activation, or a fresh terminal opened before the venv existed). Call the
interpreter directly rather than trusting the prompt:
`D:\Trading\.venv\Scripts\python.exe -m pytest -q` (same pattern for `main.py`
commands above). See `claude/PROGRAM_INDEX.md` §5 for the general version of
this trap.

## Delivery

Work is on branch `feature/vw9-backtest`, one commit (`03f82db`) on top of
`8d53347` (the reorg-complete commit). Delivered as `vw9-backtest.bundle`
via the chat (the build sandbox can clone `bgysiu85/algo-trading` but cannot
push to it — the git proxy refuses by name). **Fetched and pushed by Ben,
2026-09-05** — the branch now exists on GitHub. For reference, the fetch
command used:

```
git fetch <path-to-bundle> feature/vw9-backtest:feature/vw9-backtest
git push origin feature/vw9-backtest
```

Note for next time: the delivered file is a chat attachment, not something
already present on disk — it has to be explicitly downloaded/saved to a real
path before `git fetch`/`git bundle verify` can reference it. And `D:\Trading`
is the repo root itself (no `D:\Trading\algo-trading` subfolder) — both of
these caused a wasted round-trip this time and are now in
`claude/PROGRAM_INDEX.md` §3/§5 so they don't repeat.

## Next

1. **Run `python -m common.data_ib`, then the backtest commands above,
   against real IB paper data.** This is the actual next step — everything
   before this point has only ever run against synthetic bars. Even with 12
   uncalibrated parameters, real P/L numbers plus
   `var/reports/backtest_trades_vw9_5m.csv`'s per-trade detail are the
   fastest way to sanity-check the engine before spending more effort
   calibrating.
2. `claude/vw9_setup_count_measurement.md`'s own next-steps (§8.1/§8.2/§8.5
   pre-flight measurements, then §8.4 distributions) still apply and would
   let every uncalibrated constant above be replaced with a measured one —
   `MIN_TRIGGER_DV_PER_MIN` most urgently, since §6 explicitly warns against
   guessing it.
3. Compare the three `EXIT_MODE` variants and the four §7 cells (5m vs 15m
   × same-length vs matched-wall-clock EMA) once real trades exist — this
   build only wires 5m/15m at EMA9; the matched-wall-clock cells (EMA27 on
   5m, EMA3 on 15m) would need `ema_fast` passed through `--strategy`
   selection or two more thin adapters, not yet built.
4. Merge `feature/vw9-backtest` into `main` once the above has been sanity
   checked — it's sitting pushed-but-unmerged on GitHub as of this update.
