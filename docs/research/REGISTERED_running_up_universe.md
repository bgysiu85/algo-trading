# REGISTERED — Running Up as a NAME SELECTOR, not a gate: preflight before any threshold

**W05-0006.** Written before `common/running_up_universe_preflight.py`'s
output has been read on real bars (the module exists, is tested on synthetic
frames, and has not yet run against `E:\Databento` — that step is Ben's,
below). Cost so far: $0.00, no engine run, no live change, `holdout.json`
untouched.

## 0. What this reopens, and what it does not

`running_up_preflight_RESULT_20260918.md` closed Running Up **as a gate**:
every momentum feature separates the trades that die in one bar from the
rest in the WRONG direction (MCL `ret_5m` AUC 0.751), so filtering individual
*entries* on it keeps more losers. That result is not reopened here.

Untested is Ben's original framing from before the gate study existed
(`PROGRAM_INDEX` §7 item 10, `session_close_20260918.md` §5 item 6): Running
Up as a **UNIVERSE** signal — would it have picked this *name* for today's
watchlist, before the strategy's own entry condition ever looked at it? That
is a different question from the gate's. The gate asked "given a trade the
strategy is about to take, does this feature say don't." A name selector
asks "before any trade exists, does this feature say look here." An entry
gate reads at the moment of a signal that already happened; a name selector
would have to read *earlier* than that, off closed bars with no signal yet.

## 1. The universe gap — measured before any code, and it caps what this
   registration can answer

`var/state/screen_pairs_pit_itch_v2.json` is the point-in-time SCANNED
universe: **6,411 symbol-days**. Cross-referenced against
`session_scenarios_trades.csv` (2026-09-23): **3,903 were ever traded, 2,508
were scanned and never traded.** `bar_cache_xnas` — built to feed the two
engines that traded — holds bars for none of the 2,508 (checked directly:
`ZAPP`/`IFBD` 2024-07-02, both in the universe file that day, have no
`bar_cache_xnas` file). **A true name-selector test — would the alert have
picked out names among ones the strategy never even looked at — needs bars
for those 2,508 symbol-days, which is a priced pull not yet made (§6).**

This registration therefore has two tiers, priced separately:

- **Tier 1 (this registration, $0 — bars already on disk).** Restricted to
  the 3,903 traded symbol-days. Asks: would the proxy alert have fired
  *before* the strategy's own first entry that day, early enough to be a
  usable pre-trade filter, and does keeping only the symbol-days that
  alerted change the book's economics at the symbol-day level (as opposed
  to the entry level, which is what the closed gate study already read).
- **Tier 2 (a later registration, priced first).** Pull bars for the 2,508
  never-traded symbol-days and ask whether the alert would have surfaced
  names the strategy's screen carried but never traded, and whether those
  names would have been worth trading. Not run here; see §6.

## 2. The proxy — a computable stand-in for "would this name have alerted"

Day Trade Dash's Running Up is proprietary and reverse-engineering it from
its JavaScript stays declined (`PROGRAM_INDEX` §7 item 10). The stand-in is
`ret_5m` — the five-minute return, computed the same point-in-time-safe way
as the closed gate study (`common.running_up.ret_series`: closed bars only,
the session's own history from 04:00 ET, no lookahead) — chosen because it
is the one feature already measured with a large, clean separation (AUC
0.751 on MCL, `running_up_preflight_RESULT_20260918.md`), even though that
separation runs the wrong way *for a gate*. Whether it runs the right way
*for a selector* is exactly what is untested and what this registration
measures.

**Deferred, named so it is not smuggled in later:** `rvol_5m` (the
volume-burst half of "climbing fast on a burst of volume") is not in this
proxy. Warrior's scanner is volume-and-price; this is price only. If Tier 1
looks promising, `rvol_5m` is the first thing to add, on its own
distribution, before being combined.

**NO THRESHOLD IS CHOSEN IN THIS DOCUMENT.** Per `PROGRAM_INDEX` §5, the
preflight prints the population's own deciles of the pre-entry peak of
`ret_5m` and, at each decile, the coverage and lead time it would have
bought — the threshold for any Tier-1 scored study is picked from that
printed distribution, not from this text.

## 3. What the preflight measures (descriptive, no P&L, no rule — mirrors
   `running_up_preflight`'s own bar on itself)

For every traded symbol-day, using only bars strictly before the earliest
entry that day (across both books — the watchlist question is per NAME, not
per book):

1. **How many closed bars existed at all before the first entry** (`pre_bars`).
   If a name is bought on sight, no alert computed from closed bars could
   ever have fired first, whatever the feature. This is measured before
   anything else because it caps every number that follows.
2. **The pre-entry PEAK of `ret_5m`**, and its deciles across the population
   that had at least one pre-entry bar.
3. **At each decile cut: coverage** — the share of that eligible population
   that would have cleared it — reported **two ways**: against the eligible
   population alone, and against the FULL traded population (the honest
   ceiling, since §3.1 may leave most symbol-days ineligible from the
   start), **and the median minutes of lead time** for the ones that clear
   it.

`common/running_up_universe_preflight.py`, tested on synthetic frames
(`tests/common/test_running_up_universe_preflight.py`: the pre-entry-only
window, the zero-pre-bar case, the no-hindsight-leak case, the earliest-
across-books selection). Not yet run on real bars — the archive
(`E:\Databento`) is not reachable from this chat's environment; §5 has the
command for Ben.

## 4. What a Tier-1 SCORED study would need, if the preflight looks worth it
   (not registered here — a second document, after §3 is read)

Unlike the closed gate study (which filtered individual *entries* within a
symbol-day), a name selector removes whole *symbol-days*: if the alert never
fires before the first entry, no trade that day is taken by either book,
full stop. That is a coarser, cheaper intervention than the entry gate and
reads on `gate_study`'s existing five criteria (delta per trade, delta per
symbol-day, both halves, drop-top-3, the cluster bootstrap, the abstention
control), adapted to drop by symbol-day rather than by row. A future
registration would fix the threshold from §3's printed deciles, build that
symbol-day mask, and run it through a `gate_study`-shaped comparison before
any of this is scored.

## 5. Commands (Ben — this chat's environment cannot reach `E:\Databento`)

```
Set-Location D:\Trading
.\.venv\Scripts\python.exe -m pytest tests\common\test_running_up_universe_preflight.py -v
.\.venv\Scripts\python.exe -m common.running_up_universe_preflight --jobs 8
```

**What to report back:** the pytest pass/fail count (expect 5 passed), then
paste back (or attach) `var\reports\running_up_universe_preflight.txt` —
that is what §3's numbers come from and what the next registration (§4)
would be built on.

## 6. Tier 2, priced before bought — not run, not committed to

If Tier 1's coverage/lead-time numbers look usable, pricing a pull of the
2,508 never-traded symbol-days (same `XNAS.ITCH` dataset, same point-in-time
universe file, so no new selection question is introduced) is the next
board item, opened after §5 is read — not before, so a small, cheap Tier-1
answer is not skipped past on the strength of the idea alone.

## 7. What this is not

**NOT A RESULT.** No rule, no threshold, no P&L, no verdict — Tier 1's
preflight only, per §3.
**NOT THE FULL UNIVERSE QUESTION.** Restricted to symbol-days that traded;
§1 states why and what Tier 2 would cost.
**NOT MINUTE-FAITHFUL TO THE ALERTS.** 1-minute bars approximate a scanner
that fires on ticks, same caveat as the closed gate study.
**NOT A REOPENING OF THE ENTRY GATE.** `running_up_preflight_RESULT_20260918.md`
stands; this is a different question about the same feature.
