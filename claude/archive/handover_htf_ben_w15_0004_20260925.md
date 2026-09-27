# Handover — HTF-Ben v0: data in, backtest build next (W15-0004), 2026-09-25

**From:** High timeframe chat · **To:** Build & test chat (Sonnet · Medium) · **Workstream:** W15 - High-timeframe futures (1h–1d)

## Paste-in note for the new chat

> You are the Build & test chat working W15-0004 on the monday board (Algo Trading, 5031413876). Read
> `docs/research/REGISTERED_htf_ben_v0.md` (committed ad31938; its Amendment 0 is part of it) and this
> handover, `claude/handover_htf_ben_w15_0004_20260925.md`. Build the G1–G5 gates, then the runner, in
> `strategy/htf/`, test in the cloud against the mounted repo, and hand Ben the commands. Runs go on Ben's PC.
> Report in dollars and actual trades (Ben's standing rule), with a monday Result doc, an artifact page and a raw .txt.

## Where things stand

- **Rules:** Ben's 4H crude method, confirmed 2026-09-25 (`claude/htf_ben_rules_20260925.md`, the Revised section).
- **Registration:** `docs/research/REGISTERED_htf_ben_v0.md`, committed as **ad31938**, with Amendment 0 included.
  - **Scored:** B (multi-day, 4H) and A-2H (intraday, 2H).
  - **Reported only:** A-1H and A-4H.
  - **Variants:** v0-TL and v0-1H.
  - **Controls:** C1 MACD cross alone, C2 Donchian 20/10 on the same chart, C3 random entries.
  - **Holdout:** 2022-01-01 onward, own ledger, spent once by v0 on B and A-2H together.
- **Data on disk** (Ben, 2026-09-25):
  - Bars: `E:\Databento\GLBX.MDP3\ohlcv-1h\CL.dbn.zst`, 3,783,434 bytes. Symbols `CL.c.0,CL.c.1`, continuous, 2010-06-06 → the dataset's end on 2026-09-25.
  - Manifest: `E:\Databento\GLBX.MDP3\manifest_htf.json`.
  - Cost US$1.92.
  - Pulled by `strategy/htf/fetch.py`; the archive root is resolved by `common.tsmom_fetch.default_archive()`.
- **Nothing has read a bar yet.**

## Build order (the registration's §0 gates, then §3)

Each step should be a module plus tests. Every guard gets mutation-checked; this repo does that by writing the specific bug as a test.

1. **Bars module**
   - Reads `CL.dbn.zst` with `common.dbn_io.read_dbn`.
   - Splits c.0 from c.1.
   - Resamples to 2H and 4H **in America/New_York** on the 18:00 session grid (§2.1).
   - Builds daily bars from the same session.
   - Builds the difference-back-adjusted signal series, reusing `common.tl_v0_data.back_adjust`'s approach.
   - **Tests:**
     - bar-start labelling;
     - a DST crossing;
     - the 16:00 (2H) and 14:00 (4H) last bars;
     - an early-close session.
2. **G1 read-back (§5.1)**
   - Rebuilt daily close vs the owned `ohlcv-1d` CL.c.0 close: at least 99% within $0.05, with every miss listed.
   - Gaps longer than 3 hours inside a session.
   - Roll sessions.
   - No indicators, no P&L.
3. **Signals (§2.2)**
   - MACD/EMA confirmation within 2 bars.
   - The daily filter reads the last *completed* session only.
   - 2-bar swing pivots, usable from the confirming bar.
   - **G4 tests:** a one-bar shift must break each of these.
4. **G2 pre-flight (§5.2)**
   - Counts and stop distances only; the runner refuses to compute P&L in this mode.
   - Stop rule: fewer than 150 v0 entries in both B and A-2H means stop.
5. **G3 holdout** (`holdout_htf_ben.json`)
   - Mirror `common/tl_v0_holdout.py`'s pattern but with its own ledger.
   - Refuse the TSMOM, TL-v0, H60 and equity holdout files by name.
   - Refuse `--limit` and any narrowing flag.
6. **G5 costs (amendment A)**
   - Ben's plan fees from NinjaTrader's published schedule, written into the registration as a PRE-RUN amendment before the run.
   - Margins are already recorded: MCL $884.53 initial, CL $8,823.20.
7. **Exits and the run (§2.3–§3)**
   - Stops tested on 1H bars; the stop is checked before the trail moves.
   - Half-profit trail from +$0.20/bbl.
   - The 17:00 flat for A.
   - Roll legs charged a full round trip.
   - Emit everything in §3: B, A-2H, A-1H and A-4H side by side; controls; the neighbour grid; the $10k account view with the overnight-margin count; 20 sample trades.
   - Score §4 for B and A-2H.

## Traps already known

- **`ts_event` is the bar start.** A 4H bar labelled 18:00 closes at 22:00.
- **Front-month negative print.** CL.c.0 went to −$37.63 on 2020-04-20. Back-adjust by differences, never by ratios.
- **The fetcher never re-buys.** A second pull of the same file is a no-op, which is by design.
- **Git lock files.** This chat's sandbox left `.git/index.lock.stale-claude-*` files: renamed locks, harmless. Don't run `git status` from the device sandbox, because it creates a new `index.lock` it can't delete. If you must, rename the lock afterwards.
- **Ben's September NinjaTrader trades are inside the holdout.** W15-0005 may read signal timing only (§6.1).

## Next steps (board)

- **W15-0004** (Build & test chat, Sonnet · Medium): steps 1–7 above. Ben runs the heavy parts on his PC.
- **W15-0001** (Ben): screenshots and the Ninja_Trader_Paper connector, which W15-0005 needs.
- **W15-0005** (Sonnet · Medium): fidelity replay once W15-0001 subitem 3 is done.
