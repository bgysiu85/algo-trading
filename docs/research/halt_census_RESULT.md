# Trading halts on the exchange tape — result, 2026-09-17

Registered in `docs/research/REGISTERED_halt_census.md` (ed76c17) before the
pull. Archive: `E:\Databento\XNAS.ITCH\status\`, 27 monthly chunks,
2024-07-01 → 2026-09-17, $0.00. Reports: `var/reports/halt_census.txt`,
`halt_census.csv` (every halt with a universe flag), `halt_census.json`;
trades from `first_entry_skip_itch_v2.txt` / `first_entry_skip_trades_itch_v2.csv`.
Artifact page: "Halted".

**Headline.** 555 sessions, 47,586 halts on the tape, 4,144 on the v2
universe's names. **Two trades in 10,370** had a halt begin inside them. No
LULD pause exists before 09:30. Halts are an ORB fact, not a pre-market one:
**17.2% of universe symbol-days are paused after the open, 37% of those
pauses start 09:30–10:00** — 2.7 per session across the watchlist.

## 1. What the schema holds (§2.1)

| action | reason | records | reading |
|---|---|---|---|
| PAUSE | LULD_PAUSE | 26,406 | the 5-minute limit-up/limit-down pause; regular hours only |
| HALT | NONE | 19,304 | halts with no reason code; 858 start at 04:00 on the whole tape — carried over from a prior day |
| HALT | NEWS_PENDING | 1,989 | the regulatory news halt — the pre-market kind |
| QUOTING | NEWS_AND_RESUMPTION_TIMES | 2,359 | the quote-only window before a news halt resumes |
| HALT | NEW_SECURITY_OFFERING / ADDITIONAL_INFORMATION_REQUESTED / ETF / NEWS_RELEASED | 529 | corporate and listing events |
| TRADING / SSR_CHANGE / PRE_OPEN / CLOSE | NONE | 26.5M | state transitions |

## 2. How often, and where (§2.2)

| window | universe halts | universe symbol-days | share of 6,411 | duration p10/p50/p90 | whole tape |
|---|---|---|---|---|---|
| 04:00–09:30 | 111 (96 NEWS_PENDING, 15 NONE) | 111 | **1.73%** | 20 / 30 / 35 min | 2,075 |
| 09:30–16:00 | 4,033 (3,838 LULD, 193 NONE, 2 NEWS) | 1,102 | **17.19%** | 5 / 5 / 10 min | 30,287 |
| of which 09:30–10:00 | 1,492 (37.0%) | | | | 7,909 (26.1%) |

Universe halt starts by half hour: 06:30 39 · 07:00 15 · 07:30 30 · 08:00 22
· 08:30 5 · 09:30 **1,492** · 10:00 691 · 10:30 371 · 11:00 265 · 11:30 202 ·
12:00 189 · then ~100–155 per half hour to the close. None before 06:30 on a
universe name; the pre-market halts are news halts at the hours releases land.
A paused universe name is paused 3.7 times that day on average. Halts open at
09:30: 1,496 on the whole tape across the sessions, **0** on universe names —
a halted name has no pre-market bars and never clears the screen.

## 3. The books (§2.3)

| | trades | halt began inside | share | per trade, halted | rest | exit on resumption bar |
|---|---|---|---|---|---|---|
| MCL | 3,908 | 1 | 0.03% | (21.13) | (8.97) | 0 |
| MC5 | 6,462 | 1 | 0.02% | +1,191.33 | (8.75) | 0 |

Both halts were NEWS_PENDING; both trades exited on the trailing stop. MC5's
one halted trade is NKTR 2025-06-24, its best trade of the year.

## 4. Predictions scored

Held: no LULD before 09:30 (0 of 26,406); RTH halt on 10–25% of universe
symbol-days (17.19%); ≥ 30% of RTH halts in the first half hour (37.0%);
news halts median ≥ 30 min (30), LULD median 5–10 (5); MCL trades spanning a
halt under 1% (0.03%), losing $10+ more than the book on a stop ((21.13) vs
(8.97), trailing stop — one trade, so held, not tested). Missed: pre-market
halts on 2–6% of universe symbol-days (1.73%).

## 5. What this decides

- Nothing about a strategy. For MCL and MC5 the unmodelled halt risk is two
  trades in 10,370; a halt-aware exit would have nothing to act on. The
  universal caveat is retired for the pre-market books.
- For ORB (item 24): on the tape of record, the watchlist's names carry 2.7
  LULD pauses per session in 09:30–10:00 and 17% of their symbol-days are
  paused at least once. A rule entering at 09:45 enters into that. Handed
  over as a fact; the ORB chat decides what to do with it.
- The status archive stays; nothing further is pulled.

## 6. Also from this run — H-B1 re-based on the v2 universe (index item 1c)

`first_entry_skip --pairs screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH`:
MCL 3,908 trades at (8.97) — reconciles with the published v2 baseline.
**MCL-skip1 REFUSED** (per trade −0.41, per symbol-day +2.46), **MC5-skip1
REFUSED** (−0.78 / +2.35); 6 of MCL's and 8 of MC5's top-10 trades absent
from the skip books. On BASIC it read NOTHING / REFUSED. Skipping the first
entry does not help on either tape.

## 7. EDGAR, already in hand

The EDGAR shares-outstanding pull ran on 2026-09-14 on the BASIC universe
(`edgar_coverage.txt`, `edgar_pull.txt`, `edgar_asof.txt`): SEC's current
ticker map covers 75% of symbols / 80% of symbol-days; the point-in-time join
knows shares outstanding on 57.3% of symbol-days (19.8% no CIK, 13.8% stale
> 200 days, 5.5% no facts, 3.7% before first filing); filing lag median 65
days. Of the covered symbol-days, 28% have under 5M shares outstanding, 54%
under 20M, and 28.5% have 50M or more — the last a ceiling test that says
"cannot be low float". It is not float and is not loaded as float. The v2
join (`--asof --pairs <v2>`) is a seconds-long re-run if a study needs it;
nothing queued does.
