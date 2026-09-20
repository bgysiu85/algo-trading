# TRF probe — the reported prints are the TRF publisher, and nothing else marks them

`python -m common.trf_probe --confirm` (ALTS 2025-08-11, $0.0218, 81,434 prints 04:00–09:30)
· raw `var/reports/trf_probe_ALTS_2025-08-11.txt` · file
`E:\Databento\XNAS.BASIC\trades\probe_ALTS_2025-08-11.dbn.zst` · bundle `trf-probe-20260917b`.
Follows `tape_spikes_RESULT_20260917.md`.

## What the trades say

- **No execution timestamp.** `ts_event == ts_recv` for every print (lag 0.0 at every
  quantile). A reported print carries its REPORT time as its event time. No lag cut exists.
- **No condition flag.** `flags` ∈ {0, 128}, `side` = N, `action` = T, `depth` = 0 for
  wild and live alike. Databento's XNAS.BASIC `trades` schema does not expose sale conditions.
- **The publisher is the mark.** 1,004 wild prints (>25% from the running median):
  publisher 82 (FINRA/Nasdaq TRF Carteret) 910, 83 (TRF Chicago) 5, 81 (Nasdaq exchange)
  86 — and those 86 are priced 8.51–9.49, i.e. not wild at all, only flagged because the
  TRF junk dragged the running median. **Every genuinely wild print is a TRF print.**
- **Before 08:00 the tape carries zero TRF prints** (share NaN in hours 04–07). Every
  off-exchange trade from 04:00–08:00 is held and released from 08:00, stamped with the
  release minute. ALTS ran 11.70 (04:00) → 18.47 (06:30) → 7.95 (07:30); the 12–20 prints
  at 08:00–08:35 are those earlier trades. The 08:00 bar: 1,080,622 of 1,159,128 shares
  (93%) are TRF.
- **Exchange-only bars are sane.** Rebuilt from publishers 81/88/89 only: 08:00 high 8.93
  low 8.55 vol 70,213 (archive: 10.89 / 6.80 / 1,159,128); 08:07 8.62 / 8.48 / 31,414
  (archive: 20.05 / 6.70 / 404,756). TRF is 33% of the day's volume on this name.

## What that decides

A per-print repair is impossible on this schema. The repair that IS available and exact is
**exchange prints only** — drop publishers 82/83 — which is the definition of a price a
marketable order on Nasdaq could have hit at that minute. Costs: ~1/3 of XNAS.BASIC's volume
(which is ~55% of consolidated), and the live TRF prints after 2026-03-30 too; volume
clauses rescale, ratios survive. Cheapest exact route: **XNAS.ITCH ohlcv-1m** (Nasdaq matching
engine only, no TRF) pulled with the same window tool into a parallel archive, so every study
runs unchanged with `--dataset XNAS.ITCH`. Then a registered side-by-side: MCL as published
on XNAS.BASIC vs XNAS.ITCH, all 551 sessions, and the before/after-2026-03-30 split on both.

Next command (estimate only, refuses over $5 without a higher --max-cost):
`python -m common.databento_universe --dataset XNAS.ITCH --schema ohlcv-1m --window 04:00-09:30 --start 2024-07-01`
