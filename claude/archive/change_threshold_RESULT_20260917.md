# The pre-market change clause at 50% (and 30%) — RESULT, 2026-09-17

Registered: `docs/research/REGISTERED_change_threshold.md` (commit `bc5fcb6`,
amendment A `d796640`). Study module `common/change_threshold.py` (`e095e8c`).
Reports: `var/reports/change_threshold_{50,30}.txt`, combined as
`change_threshold_RESULT.txt`; trades in
`var/reports/change_threshold_{,30_}trades.csv`.

Asked for by Ben: *"Update the change % from 20% to 50% and run backtests on
current strategies to see if it makes them more profitable."*

---

## 0. The answer

**No. Neither 50% nor 30% makes either strategy more profitable, and the live
screen has not been changed.**

| variant | verdict | per trade | random removal's p95 |
|---|---|---:|---:|
| MCL @ 50% | **NOTHING** | +0.12 | +1.08 |
| MC5 @ 50% | **REFUSED** (denominators disagree) | **−1.10** | +1.71 |
| MCL @ 30% | **NOTHING** | +0.27 | +0.61 |
| MC5 @ 30% | **NOTHING** | +0.47 | +0.83 |

Every per-trade delta sits inside the band you get by deleting the same number
of trades **at random**. MC5 at 50% is *worse* than random removal's median
(−0.07). **No book crosses zero at any threshold or any friction level.**

`tv_screener.PREMARKET_CHANGE_MIN` is still **20.0**. The threshold was passed
to the simulation as `--change-min`, and a guard refuses to write a variant
universe over `var/state/screen_pairs_pit.json`.

## 1. Why it fails: selection against the clock

This is the finding worth keeping, and it is not "the filter does nothing".
**The tighter screen picks materially better names. It cannot pick them in
time.**

```
                          50% MCL    50% MC5    30% MCL    30% MC5
  selection /trade          +3.23      +4.82      +1.45      +2.19
  trades lost to floor        384        874        369        763
    they were worth /t      10.92      13.93       3.46       2.37
  new entries created          15        233         40        211
    they are worth /t      (16.49)    (17.82)       1.52    (15.02)
  NET /trade                +0.12      -1.10      +0.27      +0.47
```

Read the 50% MCL column. The symbol-days a 50% screen keeps are worth
**+3.23/trade more** than the whole book — MC5's are worth **+4.82**, which
clears the $4.26 margin on its own. But you only learn a name will reach 50%
by waiting until it does, and by then:

- the **384 trades** you would have taken earlier are gone, and they were worth
  **+10.92 each** — the only positive per-trade bucket anywhere in this study;
- the later floor **manufactures new entries** out of bars the baseline was
  already in a position for, and those lose **(16.49)** each.

+3.23 of real selection arrives as **+0.12**. The effect is monotone in the
threshold: 30% picks less well (+1.45) and pays less for the clock; 50% picks
better and pays more. Raising it further buys more selection at a worse
exchange rate.

> `names the screen keeps` is **NOT A TRADEABLE ARM**. It prices the name list
> at the baseline's entry floor, which requires knowing at 04:10 that a name
> will clear 50% at 07:40. It is printed to attribute the result, never as a
> candidate.

## 2. Why this is a universe study and not a gate study

The three gates of 2026-09-17 (H-B1, H-B3, H-B4) refused entry bars inside a
fixed universe, so the gated book was a subset of the baseline's trades. A
screen threshold is not: a symbol-day that never reaches 50% disappears with
every trade on it, and one that reaches 20% at 05:10 and 50% at 07:40 survives
with a **later entry floor**. The floor moved later on **44.2%** of the
symbol-days both screens keep (median 0, p90 36 minutes, max 313).

What still holds is the reading that killed all three gates: **on a book whose
average trade loses, any rule that removes trades improves every total-based
figure.** Per baseline symbol-day, 50% "improves" MCL by +2.54 and MC5 by
+3.94 — and random removal's *median* is +2.50 and +4.44. MC5's headline
per-symbol-day gain is **below** what deleting the same trades at random
would give.

## 3. The universe

| clause | symbol-days | share | sessions |
|---|---:|---:|---:|
| chg ≥ 20 (rebuilt baseline) | 6,555 | 100.0% | 550 |
| chg ≥ 30 | 4,468 | 68.2% | 550 |
| chg ≥ 50 | 2,722 | 41.5% | 544 |

The books at $4.26, flat 100 shares, XNAS.ITCH:

| book | trades | net | per trade | per baseline symbol-day |
|---|---:|---:|---:|---:|
| MCL@20 | 3,950 | (34,996.28) | (8.86) | (5.34) |
| MCL@30 | 3,092 | (26,551.33) | (8.59) | (4.05) |
| MCL@50 | 2,098 | (18,333.68) | (8.74) | (2.80) |
| MC5@20 | 6,613 | (56,074.32) | (8.48) | (8.55) |
| MC5@30 | 4,915 | (39,380.99) | (8.01) | (6.01) |
| MC5@50 | 3,157 | (30,232.32) | (9.58) | (4.61) |

## 4. The thing this run found that is not about 50% at all

**The published XNAS.ITCH baselines are not reproducible from the inputs now
on disk.** The §5 stop rule fired: 9 symbol-days pass at 50% and are absent
from the published 20% universe, which a tighter screen cannot do.

`screen_pairs_pit_itch_p50.json` was written at **05:47** on 2026-09-17.
`var/state/regular_close.json` was rewritten at **07:36** and
`XNAS.BASIC/ohlcv-1d/2026-09.dbn.zst` at **06:26**, both after it. The prior
closes `premarket_change` is measured against have moved:

```
published p50 run   daily=474,729  repaired=5,812,430  92.4% of 6,287,159
inputs at this run  daily=474,635  repaired=5,812,544  92.5% of 6,287,179
```

Seven of the nine fall on 2026-09-14/15 — sessions the published run skipped
for having no prior close and the extended archive now covers. Two (BIAF,
CHPT on 2026-09-04) sit on a session both runs screened.

Rebuilt from today's inputs, the 20% universe is **6,555 symbol-days over 550
sessions** against the published 6,564 over 551 (22 rebuilt-only, 31
published-only, 3 shared rows whose `first_seen` moved), and the books move
correspondingly:

| | published | rebuilt here |
|---|---|---|
| MCL@20 | 3,955 at (8.81) | 3,950 at (8.86) |
| MC5@20 | 6,630 at (8.49) | 6,613 at (8.48) |

Small — but **H0 (11.90) / MCL (8.81) / MC5 (8.49) were measured on inputs
that no longer exist on disk**, and anything re-run against the current
archive will not land on them. This belongs to whoever owns the archive
extension (open item 1).

**A second provenance check, because it was cheap.** `strategy/mcl/mcl.py` and
`strategy/mc5/mc5.py` were modified at 09:00:19 UTC by the H-C2 `profit_floor`
work, in the middle of this run's baseline arm. The commit claims `None` is
bit-identical; rather than take it, **216 of the 550 cached baseline sessions
were re-run on the engine as it stands and compared row for row: 0
mismatches.** The claim holds for this run.

## 5. Registration deviations, recorded

- **Amendment A (PRE-RUN)** rebuilt the 20% arm; the reproduction check against
  the published 3,955 / 6,630 was demoted from a stop rule to a reported
  comparison (§4 above), because the baseline arm is deliberately not the
  published one.
- **The 40% and 60% rungs of the descriptive ladder were not run.** 30% and 50%
  were, and the decomposition shows the mechanism is monotone in the floor
  delay, so two more rungs would have cost ~25 minutes of wall clock to confirm
  a curve the two rungs already trace. Recorded as a deviation, not presented
  as a result.
- **`pit_h0` / `pit_strategy` on the 50% universe were not run.** The verdict
  does not depend on them — they would say whether MCL and MC5 still beat a
  dumb control *on the tighter universe*, which is a different question from
  the one asked. The commands are in §7 if that is wanted.

## 6. Predictions, scored

| prediction | outcome |
|---|---|
| universe falls to 15–35% of baseline | **missed** — 41.5% |
| under 70% of the variant's trades are also in the baseline's book | **missed, badly** — 99.3% (MCL) and 92.6% (MC5) |
| per-symbol-day strongly positive, mostly abstention | **held** |
| per trade inside random removal's band; NOTHING for both | **held for MCL; MC5 was worse than that — REFUSED** |
| neither book positive after $4.26 | **held** |

The second miss is the informative one. The floor shift was expected to churn
the book; it barely changes *which* trades are taken (99.3% shared for MCL) and
instead removes a small number of unusually good ones. That is why the effect
is small in trade count and large in value.

## 7. Commands

```
python -m common.change_threshold --dataset XNAS.ITCH ^
    --baseline var/state/screen_pairs_pit_itch_chg20.json ^
    --variant var/state/screen_pairs_pit_itch_chg50.json ^
    --out var/reports/change_threshold_50.txt
```

If the H0 control on the tighter universe is wanted:

```
python -m common.pit_h0 --dataset XNAS.ITCH ^
    --pairs var/state/screen_pairs_pit_itch_chg50.json ^
    --out var/reports/pit_h0_itch_chg50.txt --json var/reports/pit_h0_itch_chg50.json
python -m common.pit_strategy --strategy mcl --dataset XNAS.ITCH ^
    --pairs var/state/screen_pairs_pit_itch_chg50.json ^
    --h0 var/reports/pit_h0_itch_chg50.json --out var/reports/pit_strategy_mcl_itch_chg50.txt
```

## 8. PROGRAM_INDEX additions (not applied — another chat is editing it)

Add to the 2026-09-17 banner:

> **2026-09-17 — raising the screen's change clause reads NOTHING, and the
> reason is worth more than the verdict.** 50% and 30% against the shipped 20%
> on XNAS.ITCH: MCL +0.12 and +0.27 a trade, MC5 −1.10 (REFUSED) and +0.47,
> every one inside random removal's band. The tighter screen **does** select —
> the names it keeps are worth +3.23 (MCL) and +4.82 (MC5) a trade more — but
> the selection is **not reachable in time**: waiting for a name to clear 50%
> gives up 384 trades worth +10.92 each and manufactures new entries worth
> (16.49). See `change_threshold_RESULT_20260917.md`. **The same run found the
> published ITCH baselines are no longer reproducible from the inputs on disk**
> — `regular_close.json` (07:36) and the September daily archive (06:26) were
> both rewritten after the 05:47 universe build; the rebuilt 20% arm reads
> MCL 3,950 at (8.86) against the published 3,955 at (8.81).

Add to §5 traps, under "Universe and data":

> - **A universe file is only as reproducible as the inputs under it, and
>   nothing records which they were.** `screen_pairs_pit_itch_p50.json` was
>   built at 05:47; `regular_close.json` and the daily archive were rewritten
>   an hour later, and the file kept its name. The tell was a *tighter* screen
>   surfacing names the looser one had not. A universe file should carry the
>   mtime and row counts of the prior-close inputs it was screened against.

Add to §7, "Closed since the last rewrite":

> | **The pre-market change clause at 50% and 30%** | **NOTHING × 3, REFUSED × 1, 2026-09-17.** Selection is real and unreachable in time; the live screen is unchanged |
