# W03-0015 · Re-run the W03-0002 spread gate on DBEQ.BASIC — RESULT

**Board:** W03-0014 (decision), W03-0015 (this re-run). **Registered:** `docs/research/REGISTERED_spread_gate.md`
(unchanged — this is a quote-source re-run of the same gate, not a new gate). **Commits:** `c505863`
(add EQUS.MAX/DBEQ.BASIC to `quote_price.py` candidates), `4918579` (swap EQUS.MAX → DBEQ.BASIC, EQUS.MAX
doesn't exist), `2dc3fb9` (decouple `entry_gates.py`'s quote source from the engine's own bar tape).
**Source files:** `common/entry_gates.py`, `var/reports/entry_gates_dbeq_basic.csv`,
`claude/raw/w03_0015_dbeq_basic_20260929.txt`.

## In plain terms

W03-0011 found the original spread gate study's quote source (XNAS.BASIC, Nasdaq-only) reads spread about
3x wider than live IB fills on premarket small caps, and misses the quote entirely on 57% of live entries.
W03-0014 asked Ben to decide whether to re-run the study on a better consolidated source. Two named
candidates turned out not to work: EQUS.SUMMARY has no bid/ask data at all, and EQUS.MINI is already
documented in this repo as reading 2.7x wider than XNAS.BASIC with only ~4.8% of consolidated volume.
Databento's only other candidate on this account, DBEQ.BASIC (their free IEX + NYSE Chicago + NYSE
National bundle), was priced (free), pulled (1,861/1,862 windows), and run through the same study.

**The result is worse, not better.** On DBEQ.BASIC, the 2% spread gate refuses **97.6% of MCL's entries
and 97.1% of MC5's** — up from XNAS.BASIC's already-too-high 74–76%, and nowhere near the live 180-trade
sample's ~7% (13 of 180 ≥2%) or W03-0011's live reconciliation (0 of 30 refused on 2026-09-24). DBEQ.BASIC
sees fewer quote updates than XNAS.BASIC per window (0.32 GB vs XNAS.BASIC's 0.47 GB for the same 1,862
windows), consistent with it covering fewer venues, not more — the opposite of what "consolidated" was
supposed to buy here. **No quote source available on this Databento account is a workable proxy for the
live IB SMART-routed spread on this universe.**

## Verdict / what Ben must decide

Neither book clears the project's own $4.26/trade margin on this tape: MCL-spread reads +4.17/trade
(just under margin), MC5-spread +1.87/trade (well under). Both sit below their random-abstention control's
95th percentile, same as the XNAS.BASIC run — most of the apparent improvement is "refuse almost
everything," not the gate picking out bad trades. This re-run does not produce a usable backtest cost
estimate; it produces a stronger version of the same warning W03-0011 already raised.

**Decide one of:**
- **(a) Close the search for a better Databento quote source.** None of XNAS.BASIC / EQUS.MINI /
  DBEQ.BASIC is a workable proxy for live spread on this universe; stop trying named-dataset swaps.
- **(b) Fund reconstructing a real synthetic NBBO** from the individual venue top-of-book feeds
  (XNAS.ITCH, XNYS.PILLAR, ARCX.PILLAR, the four Cboe PITCH feeds, IEXG.TOPS, XASE.PILLAR, XCHI.PILLAR,
  XCIS.TRADESBBO, MEMX.MEMOIR, EPRL.DOM — merged best-of-book) — a real build, not a config change, and
  not started without sign-off.
- **(c) Drop the backtest cost-savings claim entirely** and treat W03-0002 as shipped on live-path logic
  alone (`spread_guard_ok()` in `trader.py` already uses a live-quality quote) — the backtest refusal-rate
  and dollar-saved numbers from any of these three tapes are not trustworthy enough to quote.

## The books, DBEQ.BASIC / mbp-1, at the registered $4.26 margin

| | Trades | Net | Per trade | Win % |
|---|---:|---:|---:|---:|
| MCL (baseline) | 3,941 | (41,318.07) | (10.48) | 22.3% |
| MCL-spread | 99 | (624.86) | (6.31) | 17.2% |
| MC5 (baseline) | 6,755 | (89,918.54) | (13.31) | 21.3% |
| MC5-spread | 247 | (2,824.89) | (11.44) | 19.8% |

Refusal: MCL 3,848 of 3,941 (**97.6%**), MC5 6,561 of 6,755 (**97.1%**) — compare XNAS.BASIC's 74.2%/75.9%
(`w03_0002_spread_gate_RESULT_20260924.md`) and live's ~7% / 0 of 30.

Per-trade margin (registered reading 1, must clear $4.26): MCL **+4.17** (fails, just under), MC5 **+1.87**
(fails). Abstention control (2,000 draws): MCL gate +4.17 vs random p95 +7.87 (gate below top 5% of random
cuts); MC5 gate +1.87 vs random p95 +6.24 (same). Cluster bootstrap P(total>0)=1.000 both books, but that
only says the direction is reliable, not that the effect is real selection rather than "trade almost
never."

Winners lost to the gate: MC5's biggest — UVIX 2026-07-01 04:20 ET $5,461.25 — is refused here exactly as
it was on XNAS.BASIC.

## Method

Same harness as the original W03-0002 run (`common/entry_gates.py`), same universe/entry rule/engine bars
(XNAS.BASIC/ohlcv-1m, unchanged), only the quoted spread's source swapped to DBEQ.BASIC/mbp-1 via the new
`--quote-dataset`/`--quote-schema` flags (commit `2dc3fb9`). Full point-in-time backtest, 551 sessions,
1,861/1,862 quote windows pulled (1 error: 2026-09-14 BMGL, symbology not resolvable on this tape for that
date — excluded, not a gate/mapping bug).

## Caveats

- Same 24-symbol-day drop as the original run (duplicate bar timestamps, 2025-06-09/06-10, W10-0008) — MCL
  count here (3,941) still doesn't match the published 3,955; unrelated to the quote-source swap.
- Not out-of-sample, not a cap model, not a search (same disclosures as the original registration).
- DBEQ.BASIC's smaller per-window file size (fewer quote events for the same symbol-days) than
  XNAS.BASIC's is circumstantial, not a direct venue-coverage measurement — the 97%+ refusal rate is the
  direct evidence.
- EQUS.MAX, named in the original W03-0014 decision, does not exist as a Databento dataset (confirmed via
  `metadata.list_datasets()`); this is the actual current candidate list on Ben's account.
