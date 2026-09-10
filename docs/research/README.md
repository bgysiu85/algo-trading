# `docs/research/` — source-analysis datasets

Research data from the Ross Cameron / Warrior Trading source analysis,
2026-09-10. **Data only — nothing here is imported by any module.**

Tracked deliberately: `var/` is gitignored, so anything left there never reaches
a bundle and never reaches the build chat.

| file | rows | what it is |
|---|---:|---|
| `warrior_census.csv` | 401 | One row per video — every recap and watchlist on `@DaytradeWarrior` from 2026-09-10 back to ~2025-07-01, each read in full |
| `warrior_video_index.csv` | 800 | The channel's uploads playlist, position-ordered newest first, used to build the census |

## Schema — `warrior_census.csv`

`pos` · `videoId` · `kind` · `day_result` · `pnl_usd` · `account` · `trades_n` ·
`symbols` · `setups` · `mistakes` · `market` · `first_et` · `last_et` ·
`max_loss_hit` · `notable`

- `kind` — recap · watchlist · training · interview · promo · news · other
- `day_result` — green · red · flat · notrade
- `market` — hot · mixed · cold, **as he labels it**, not as inferred
- `setups` and `mistakes` use closed vocabularies so they aggregate; both are
  semicolon-separated
- **`?` means not stated and is never a guess**

`setups`: micro_pullback · first_pullback · bull_flag · flat_top · gap_and_go ·
abcd · vwap_break · dip_buy · reversal · half_whole_dollar · red_to_green ·
halt_resumption · other

`mistakes`: chased_extended · back_side · added_to_loser · reentry_after_stop ·
oversized · no_cushion · ignored_own_filter · traded_low_quality ·
broke_ice_boredom · didnt_bank_green · stop_widened · outside_window ·
divided_attention · slippage · none

## Known limits

- **No calendar dates.** The playlist endpoint returns none, so the census is
  position-ordered and **cannot be joined to `flex_round_trips.csv` by date.**
  Fixing that is one metadata call per video — 401, free.
- `trades_n` is stated on 175 of 317 recaps and `market` on 234. Real
  denominators, not complete ones.
- Figures are **self-reported by the source**, narrated on camera, on a channel
  that sells a course. The census removes selection bias — it is a census, not a
  title-picked sample — but not source bias. Per `PROGRAM_INDEX.md` §4 every
  number here is a **hypothesis needing its own registration**.

## Where the analysis lives

In project Context, not in this repo:

- **`HANDOVER_TO_BUILD_20260910.md`** — start here; reading order, what is
  settled, what to build and in what order
- `warrior_census_20260910.md` — what this dataset says
- `execution_gap_20260910.md` — census vs MCL vs Ben's real round trips
- `CENSUS_SPEC.md` — the worker spec, so the census is reproducible
- `warrior_0`–`warrior_5` — the strategy spec set
