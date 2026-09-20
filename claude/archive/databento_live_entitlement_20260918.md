# Databento live entitlement, measured — only EQUS.MINI

**2026-09-18, 13:50 AEST.** Probe: `D:\Trading\Claude outputs\databento_live_entitlement.py` (opens a live session per dataset, one symbol, 4 s, reads the key through `common.databento_fetch._key`). Read-only; no historical download, no orders.

```
EQUS.MINI      OK        session opened, 2 record(s) in 4s
XNAS.BASIC     REFUSED   A live data license is required to access XNAS.BASIC.
XNAS.ITCH      REFUSED   A live data license is required to access XNAS.ITCH.
DBEQ.BASIC     REFUSED   A live data license is required to access DBEQ.BASIC.
```

**`metadata.list_datasets()` is not an entitlement list.** It returned 29 datasets including XNAS.ITCH and XNAS.BASIC on a key that cannot stream any of them. Historical access never implies live access. Only the live gateway answers this question.

## What it means for live screening

The Standard plan ($199/mo) carries live only for Databento's licence-free products. On this key that is **EQUS.MINI**, which this project has already measured at a **median 4.8% of the consolidated tape** (`PROGRAM_INDEX` §3), against XNAS.BASIC's 55%.

Against the three clauses of the live screen (`common/tv_screener.py`):

| clause | on EQUS.MINI live |
|---|---|
| pre-market change ≥ 20% (vs previous regular close) | plausible — a price ratio, and movers print on enough venues |
| pre-market price $2–25 | plausible |
| **pre-market volume ≥ 100,000 shares** | **breaks.** On ~1/20th of the tape the threshold means ~2M consolidated, and the share varies by name and venue mix |

So Databento live is **not a drop-in** for the TradingView screen, and it does **not** deliver the main prize — the live screen and the backtests reading one tape — because the backtests are on XNAS.ITCH and that is not licensed live here.

## The study that would decide it (build chat, data already on disk)

**Is EQUS.MINI's share of volume stable enough to re-derive the floor?** Per symbol-day over the pre-market window, compute MINI volume ÷ XNAS volume from `bar_cache_db` and `bar_cache_xnas` (or the `ohlcv-1m` archive), and report the distribution, not the median alone: p10/p50/p90, and the dispersion **within** a symbol across days.

- Tight and stable → a scaled floor (~5k on MINI) is defensible, and MINI live can drive the screen.
- Wide → the volume clause cannot be reproduced on MINI, and the choice is the TradingView cookie, IB's scanner, or paying for a live exchange licence.

Register before running; report both denominators and the usual controls.

## Still open

- `tv_delay_probe.py` (same folder) has not been run — whether the anonymous TradingView feed is actually delayed, and by how much, is still unmeasured.
- `main.py --mode scan --preview` has never been run against a live Gateway; whether IB's percent-gain scans compute before 09:30 is unknown and free to find out.
