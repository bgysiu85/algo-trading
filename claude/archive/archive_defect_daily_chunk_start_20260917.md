# Archive defect: the September daily chunk lost 2026-09-01..04 (found by the ORB chat, 2026-09-17)

**For the chat that owns `common/`.** Nothing in `common/` was changed by the ORB chat.

## What happened

`E:\Databento\XNAS.BASIC\ohlcv-1d\2026-09.dbn.zst` was re-pulled on 2026-09-17 with `--start 2026-09-05` (the archive extension). The manifest row now reads `start 2026-09-05, end 2026-09-17`. Read with `common.dbn_io.read_dbn`, the file now holds sessions 2026-09-08 to 09-16 only. **The bars for 09-01, 09-02, 09-03 and 09-04 are gone.**

## Cause

`databento_universe.month_chunks` sets the chunk's start to `max(month_start, --start)`. A pull that starts mid-month therefore writes a month-labelled file beginning mid-month, and it replaces the full-month file that was there. `chunk_ends_before` (`--refresh-partial`) only checks the chunk's end, so neither the re-pull nor any later run notices the missing start.

## Consequences

- `bar_cache_build.trading_calendar` reads `ohlcv-1d`, so 09-01..04 are no longer trading sessions for any cache build. On the ORB PIT build that gave 16 "no window" symbol-days plus 17 "short" ones.
- Anything that reads the prior regular close or the daily bars for those four sessions (`screen_sim`, `pit_*`) will skip them or fail on them now, even though it read them fine before today.

## Repair (Ben runs it from `D:\Trading`)

1. `Rename-Item "E:\Databento\XNAS.BASIC\ohlcv-1d\2026-09.dbn.zst" "2026-09.from0905.dbn.zst.bak"` (the symbology file can stay)
2. `python -m common.databento_universe --dataset XNAS.BASIC --schema ohlcv-1d --start 2026-09-01 --end 2026-09-17` (estimate), then add `--confirm`.

## Suggested fix in code

Label a month chunk only when it covers from the 1st, or refuse to overwrite an existing month chunk whose first bar is earlier than the new request's start.
