# CONFIRMED: `prior_close` is the EXTENDED close, not the regular close

2026-09-12 · `var/reports/prior_close_check.txt` · bundle `20260912n`

## The proof, and why the LOW is what proves it

ACVA, 2026-09-10:

| | high | low | close |
|---|---:|---:|---:|
| ours (`ohlcv-1d`) | **11.31** | **7.00** | **10.38** |
| the market (TradingView regular session) | 7.39 | 7.00 | 7.22 |

The low agrees **to the cent** and the high is 53% higher. A wrong bar does not
reproduce one endpoint exactly. A bar covering **extra hours** does — the
regular session set the low, and the after-hours session set the high and the
close.

Databento's `ohlcv-1d` aggregates the whole feed, so its close is the last print
of the extended day (20:00 ET). TradingView's `premarket_change` — the clause
the live screen actually applies — divides by the official **16:00** close. Two
closes that look comparable and are not: the project's signature defect, in the
divisor of every change the simulated screen computes.

Corroborating rows in the same report: IRD 09-09 `h 7.07 l 4.01 c 6.07`, RML
09-09 `h 40.73 l 9.20 c 9.50` — daily bars whose ranges are far wider than a
regular session.

## Why it produces exactly the signature we saw

The error is **one-directional**. A name that runs after hours gets an inflated
divisor, which *deflates* its computed premarket change, so the simulation
under-produces. `screen_validate` found 16 missed against 2 sim-only. It also
explains why ACVA's 09-08 and 09-09 closes matched TradingView to the cent: on
quiet after-hours days the two closes coincide, and only the day it ran
diverges.

## The full chain, for the record

Five hypotheses, four of them mine and wrong:

1. **Capture ratio mis-scaled** (my recommendation, 09-11) — refuted by
   `screen_miss`: zero names failed volume alone.
2. **`prior_close` off-by-one row** — refuted by `prior_close_check`: every
   baseline was the correct previous daily row.
3. **Watchlist date lag** — refuted by `screen_lag`: offset 0 won 58% to 24%.
4. **Minute slices vs daily bars corrupt** — refuted by `tape_conflict`: zero
   conflicts over 3,406,462 symbol-days. That zero was the decisive step, since
   it ruled out a corrupt file and left one source wrong the same way
   everywhere.
5. **Extended-hours close** — confirmed.

Two real defects were found on the way and both are fixed: the MC5 entry-dedupe
bug (`20260912j`) and the tv_feed watchlist carry-over (`20260912k`).

## The repair, and the gate in front of it

The archive carries no 16:00 close anywhere — window slices stop at 09:30, daily
bars are whole-feed — so this needs a Databento pull. `databento_universe`
already supports it:

    python -m common.databento_universe --schema ohlcv-1m --window 15:55-16:05 \
        --start 2026-09-08 --end 2026-09-12

It prints the cost and does nothing without `--confirm`.

**`common/regular_close.py` gates the full pull.** Three readings of "the close"
are scored against eleven TradingView rows read by hand:

- `last_bar_before_1600` — the last continuous print, excluding the closing cross
- `bar_at_1600` — where a 16:00:00.000 auction print lands under `[start, start+1m)`
- `last_bar_at_or_before_1600` — the auction when present, the fallback otherwise

The closing cross is usually the largest trade of the day, so guessing here
would put a small, plausible, systematic error into every close.

**Its guard:** a row counts only when our own daily close *already* disagrees
with the truth. On a quiet after-hours day the two closes are the same number,
every candidate matches, and a scorer counting those rows would report
near-perfect for whichever construction it tried first.

**A second degeneracy the tests found:** `bar_at_1600` and
`last_bar_at_or_before_1600` are *identical by construction* whenever a 16:00
bar exists. A tie between them says every name in the sample traded at the
close, not that either is right. The report now names that reason and asks for a
thin name, rather than leaving someone to hunt for a data problem that is not
there.

## Order of operations

1. Small pull (5 sessions) → `python -m common.regular_close`
2. Only on a single-construction verdict: full pull across the 552 sessions
3. `regular_close --emit` → rebuild `prior_closes()` on it
4. Re-run `screen_sim`, then `screen_validate`

**Every screen figure — including the 58% — gets re-stated after step 4, not
adjusted.** And `pit_strategy --strategy mcl` / `mc5` stay on hold: they run on
a universe this defect selected.

**Do not cancel Databento.**
