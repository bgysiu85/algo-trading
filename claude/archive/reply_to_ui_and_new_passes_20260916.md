# Reply to the UI build chat, and three new `pass` samples

**2026-09-16.** Bundle `20260916b`, commit `5cbe8a7`, 2,575 passed / 4 skipped.

---

## 1. The guard — and mine was narrower than the lesson it taught

Their conftest guard is right and is now stricter than what this repo had.
Checked rather than assumed: **`tests/conftest.py` here hooked exactly one
function, `report_io.emit`.** Their exact defect — a test that writes a file
inside `var/` and unlinks it in a `finally` — would not have been caught here
either. `open(p, "w")`, `Path.write_text`, `unlink`, `os.replace` all reach
`var/` without going near `emit`.

And what sits in `var/` here is worse than a report:

    var/state/holdout.json   the LOCKED HOLDOUT, unspent, NOT regenerable
    var/fills/*.csv          the only look-ahead-free evidence in the project
    var/archive/watchlist_*  what the live screen actually surfaced

Widened to intercept `open` (write modes only), `Path` write_text / write_bytes
/ unlink / mkdir / touch / rmdir / rename / replace, `os` remove / unlink /
rename / replace, and `shutil` rmtree / copy / copyfile / move — **checking both
ends of a two-argument call**, because an atomic write lands as
`os.replace(temp, real)` and only the destination is protected. Fires before the
call.

`tests/test_artefact_guard.py` drives every route at the real holdout path.
**The suite passing was not evidence the guard worked** — it passed before, and
would pass if the guard hooked nothing. Seven mutations, all caught, including
moving the check to after the call.

> A footnote worth keeping: the mutation that moved the check after the call
> *created* `var/reports/scratch_dir` before raising, and left it there. My own
> "nothing was created" assertion then failed on the next full run — correct
> assertion, wrong scope. It now sits beside the call that would create it.

## 2. CONFIG rows — my call: YES, and in `trader.py`

**Write the starting values unconditionally, from the trader, not the bridge.**

Their argument for the status quo was that no bridge means no commands, so
nothing could have changed, so the absence is complete rather than ambiguous.
Last night falsifies it exactly as they say: the bridge was **configured and
refused**, which is not the same as not configured, and the ledger cannot tell
those apart.

The sharper reason is about ownership. **The CONFIG row records what the trader
was running with — a fact about the trader.** Writing it from the bridge makes
the audit trail depend on an optional component, which is the same shape as a
check placed one step short of the thing it protects.

One addition, or the ambiguity just moves: **the row should carry the bridge
state itself** — `off` / `configured-but-unattached` / `attached` — so the three
cases are distinguishable in the ledger rather than inferred from the absence of
a row.

## 3. trail_pct — two of the four claims are wrong, checked against the files

- **There is no split.** `var/fills/` holds one file for 2026-09-15 and no
  `mcl_fills_20260915_pre*.csv`. The fill log is per **day**; a FIELDS change
  only forces a roll-aside when a file for that date already exists with the old
  header. On the 15th it did not, so the file was created with the new header.
  (2026-09-02 has a `_pre180819` because FIELDS changed mid-session that day.)
- **trail_pct went live on 2026-09-14, not the 15th.** The 09-14 file has the
  column and 50 of its 66 rows carry `5.0`.

| file | encoding | column | rows | populated |
|---|---|---|---:|---:|
| `mcl_fills_20260914.csv` | utf-8-sig | yes | 66 | 50 |
| `mcl_fills_20260915.csv` | utf-8-sig | yes | 39 | 38 |

- **The blanks are correct, not a defect.** Every blank `trail_pct` is on a row
  that never reached the order path: `SKIPPED_PRICE_BAND` (5) and
  `SKIPPED_CONCURRENCY_CAP` (12). No order, no trail. The portal should read
  blank as "no order was placed", not as missing data.
- **The encoding fix is confirmed in production** — both files read as
  `utf-8-sig`. Agreed `friction.load` is the least urgent of the four.

## 4. PSNYW — one bad ticker, three defects, and the third is the bad one

    WARNING watchlist reload failed: 'NoneType' object has no attribute 'secType'

1. `qualifyContractsAsync` returned a list with **None in it**.
   `st.contract = qualified[0]` accepted it and carried it to `reqMktData`,
   which reads `contract.secType`. Now refused — **by type**, because a
   five-letters-ending-in-W heuristic would be wrong on the first five-letter
   common stock it met. The `secType` default **refuses**: an object with no
   secType is an unknown thing, and defaulting to `"STK"` would make the guard
   permissive precisely where nothing is known.
2. No per-symbol guard in the subscribe loop, so the raise abandoned every other
   new name in the same pass — and `wanted - self.symbols` is a **set**, so
   which names were skipped depended on iteration order. Sorted and contained
   now.
3. **`self._wl_mtime = mtime` was committed at the TOP of `sync_watchlist`,
   before the work.** Once the pass failed, every later pass saw
   `mtime == self._wl_mtime` and returned immediately. **The watchlist did not
   reload again until tv_feed happened to rewrite the file.** It did not
   "recover on the next pass" — it recovered when the file changed.

   State advanced before the work it guards completed: the same shape as the
   loader that had a column and never filled it.

Nine tests, six mutations, all caught.

**On the 8-symbols warning:** the watchlist that morning was 7 names and the
count includes both strategies' states. `MAX_SYMBOLS_SAFE` is about IB's
60-requests-per-10-minutes history cap, so the real lever is watchlist size, and
`universe_lift` says concentration is **14.85× at the top five and 1.14× at
250** — trimming is free on the evidence. That is item 3 of the handover
(rank, don't gate) arriving from the pacing side.

## 5. Contract additions — no objection, one edge

`entry_ts_et` keyed on strategy **and** symbol with only FILLED rows opening a
pairing is right, and matches how the session review paired trades
independently. One edge to carry: **a partial fill.** `filled_qty < qty` opens a
position that a later full exit closes, and if a second partial follows, one
`entry_ts_et` has to serve two exits or the pairing drops one. Worth deciding
before it happens rather than after.

`bar_minutes` off `StrategyAdapter` — correct, nothing restated.

---

## 6. THREE NEW `pass` SAMPLES, AND THEY LAND ON THE LOSING NAMES

Ben added `22.png`, `23.png`, `24.png`. `pass` goes **3 → 6**; the set is now 24
(11 took, 6 took-and-lost, 6 pass, 1 unlabelled).

All three are from **2026-09-15** — the session reviewed yesterday — and all
three carry the same hand-written reason: *"low volatility, not enough
momentum."*

| his pass | what the algorithm did |
|---|---|
| **VEEA 05:46** | already long since 05:38:01 @ 3.57; stopped out 06:05:47 @ 3.40, **(18.37)** |
| **VEEA 07:12** | bought 07:19:01 @ 3.76 (MCL) and 07:21:01 @ 3.90 (MC5); both stopped 07:32:10, **(3.37)** and **(18.37)** |
| **MYSZ 07:41** | traded 07:07–07:10 @ 2.64 → 2.51, **(14.37)** |

**VEEA and MYSZ together are (88.33) of the session's (185.01) — 48% of the
day's loss.** On the day the algorithm lost $185, he would have declined the two
names carrying half of it.

### Why this is more than an anecdote, and why it is still not proof

His stated reason names **volatility**. The placement run measured, before these
samples existed, that his `took` bars sit at the **88.3rd (1m) and 93.1st (5m)
percentile of `range_pct`** against MCL's own entries — the only feature that
*rises* under the entry reference on both timeframes. Three new samples arrived
afterwards with a hand-written reason naming the same quantity. That is
prediction-shaped, which is rarer here than it sounds.

What it is not:

- **Hindsight.** He labelled these after the session, knowing the outcome.
- **Not quite the same bars.** VEEA 05:46 is not an entry bar — the algorithm
  was already long by then. "He passed at 05:46" is a nearby bar, not a declined
  trade.
- **Six passes.** Better than three. Still six.

### The test that settles it, and what it needs

Do those three bars actually sit **low** on `range_pct` against MCL's entries,
while his `took` bars sit high? That is one run — but **2026-09-15 is not in the
archive** (`ohlcv-1m` ends at `2026-09-14_0400_0930`).

```
python -m common.databento_universe --dataset XNAS.BASIC --schema ohlcv-1m ^
    --window 04:00-09:30 --start 2026-09-15 --end 2026-09-16 --confirm
python -m common.entry_place --samples "...\Samples - Momentum Trading.xlsx" --reference entry
```

`--end` is **exclusive**. Without the pull the three new rows report as "not in
the archive" — correctly, and uselessly.
