# The close construction — where it lands, and the decision left open

2026-09-12 · `var/reports/regular_close_XNAS_BASIC.txt` · bundle `20260912w`

## Final scores, 27 truth rows, 24 discriminating

| candidate | pooled | AMEX | NASDAQ | NYSE |
|---|---:|---:|---:|---:|
| **`auction_else_last`** | **19/24** | 0/3 | **17/19** | **2/2** |
| `open_at_1600` | 19/24 | 0/3 | 17/19 | 2/2 |
| `stats_close_price` | 17/24 | 0/3 | 17/19 | **0/2** |
| `last_bar_before_1600` | 13/24 | 1/3 | 10/19 | 2/2 |
| `bar_at_1600` | 11/24 | 2/3 | 8/19 | 1/2 |
| `stats_uncrossing` | **n/a** | — | — | — |

`UNCROSSING_PRICE` is **absent** from XNAS.BASIC — the census shows only
stat_type 1 and 11 — so its zero means not-carried, not wrong.

## The statistics shortcut does not hold

It looked like the cheap route: 2.3 MB against `trades`' 14.7 GB, and a
published number instead of an inferred one. It is **weaker** than the minute
route:

- **0/2 on NYSE-listed rows.** Nasdaq's CLOSE_PRICE for a NYSE-listed name is a
  Nasdaq-venue close, not the official one.
- **XRTX 2026-09-10 gives 2.18**, an after-hours print, where the last
  continuous print before 16:00 gives **2.11 exactly**.

So `stat_type 11` is not reliably the official regular-session close.

## The two-method flag fired once, and resolved against us

XRTX 09-10: both `auction_else_last` and `stats_close_price` said 2.18 against a
truth of 2.11, which put the truth row in question. **TradingView's own
30-minute series settles it** — the 15:30–16:00 ET bar closes at 2.11, matching
its daily close. The truth is corroborated; the flag was a false alarm, raised
correctly and resolved against the extraction. That row is a real miss, and
`THIRD_SOURCE` now records the check with its provenance so it is not re-opened.

## Where this leaves the repair

`auction_else_last` is the construction: **17/19 on Nasdaq-listed names, 2/2 on
NYSE, 0/3 on AMEX.** The pre-registered bar was *every* discriminating row, and
it is not met.

Residual errors are **1–7 cents** (1–3.5%) on two Nasdaq rows, against a status
quo that is wrong on 24 of 27 rows by up to 44%.

The screen's clause is `change >= 20%`, so a 1–3.5% divisor error still flips a
name sitting within ~3pp of the line — which is exactly how TPET was lost. The
repair moves the archive from **systematically wrong** to **occasionally
marginal**. That is a large improvement and it is not exactness.

## The decision, unchanged and now better evidenced

1. **Accept `auction_else_last`, record the relaxed bar, pull.** ~2 GB of
   minutes across 552 sessions. Non-Nasdaq listings are a known gap; the 1–3.5%
   residual is stated wherever the repaired closes are used.
2. **Keep chasing exactness.** The remaining route is `trades` with condition
   codes — 14.7 GB for five sessions, ~1.6 TB for 552. Not proportionate.

Option 2 has effectively been priced out. My recommendation is **option 1**,
with the relaxation recorded here rather than slipped through.

## What is settled, and what is not

**Settled:** the defect (extended-hours close in `prior_close`), the dataset
(XNAS.BASIC; EQUS.MINI rejected 2/8), the construction (`auction_else_last`),
the statistics route (rejected), the cross-listed gap (real and bounded).

**Not settled:** whether the residual matters in practice. That is answerable
only after the pull, by re-running `screen_sim` and `screen_validate` and seeing
where the agreement lands.

**Still on hold:** `pit_strategy --strategy mcl` / `mc5`, because they run on a
universe this defect selected. **Do not cancel Databento.**

## Also fixed today, unrelated to the close

- MC5 entry-dedupe bug (`20260912j`) — one signal could open five positions.
- tv_feed watchlist carry-over (`20260912k`) — yesterday's names armed today.
- `churn_count` correction: pooled over six sessions the dedupe bug is
  **proportional**, not the explanation for the deficit. MCL loses $309.72 over
  40 trades with no bug at all.
