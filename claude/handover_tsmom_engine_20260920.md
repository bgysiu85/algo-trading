# Handover: TSMOM engine build (AT-41 + AT-42), 2026-09-20

**From:** the TSMOM chat that registered, priced and bought the data (2026-09-17 → 09-20).
**For:** a fresh TSMOM chat (Opus, high effort) that builds the engine.
**Board:** AT-41 (roll cross-check) and AT-42 (engine), both *Next up*, both TSMOM chat. AT-43 (the run) is blocked by these two.

This doc **replaces** `claude/handover_tsmom_20260918.md` as the starting point.
That doc is the history; this one is the job.

---

## 0. State in one paragraph

Every gate is cleared (G1 paper verified, G2 cost, G3 rates arm = **MTN**, signal
from **TN**, G4 holdout in code). The data is bought, complete and read back
(`REGISTERED_tsmom_fetch.md` §1.6–1.8). The roll rule has been amended once, pre-run
(**amendment C**, `REGISTERED_tsmom.md` §0.2). **No strategy code exists and no
return has been computed.** The engine is the next and only build step before a result.

## 1. Read, in this order

1. `docs/research/REGISTERED_tsmom.md`: **all of it**. §0.2 (amendment C) and §2
   (the spec table) are the rules the engine implements; §3 lists what every run must
   emit; §7–8 cover what must not be done.
2. `claude/tsmom_spec_20260917.md` §1 (signal, vol estimator, sizing, from the paper)
   and §4 (roll rule and back-adjustment).
3. `docs/research/REGISTERED_tsmom_fetch.md` §1.6–1.8: what is on disk and its known
   quirks.
4. `common/tsmom_holdout.py`: `split_months` is **the one implementation** of the
   train/holdout cut; every runner calls it.

## 2. The data (on Ben's machine, `E:\Databento\GLBX.MDP3`, also `.databento_archive`)

| Path | What | Range |
|---|---|---|
| `ohlcv-1d/<ROOT>.dbn.zst` | continuous `c.0` + `c.1` daily bars, 13 roots + MTN | 2010-06-07 → 2026-09-17/18 (RTY 2017-07, TN 2016-01-11, MTN 2024-03-25) |
| `ohlcv-1d/{GC,SI,HG}.c2-c4.dbn.zst` | `c.2`, `c.3`, `c.4` for the metals (amendment C) | 2010-06-07 → 2026-09-18 |
| `definition/<ROOT>/<YYYY-MM-DD>.dbn.zst` | roll calendar: one `parent` snapshot per month (15th, or the Friday before) | 196 per root; RTY 112, TN 129 |
| `manifest_tsmom.json` | two pulls, `late_listings` (RTY 2017-06-15) | — |

Roots: ES, RTY, GC, SI, HG, CL, NG, 6E, 6A, 6B, 6J, ZN, **TN** (+ MTN bars only).
The bars carry `instrument_id`. The definitions map `instrument_id` →
`maturity_year/month`, `raw_symbol`, `expiration`, `min_price_increment`,
multiplier. **Every instrument id in the bars maps: 0.0% unmapped** (checked 09-20).

`databento` 0.86.0 reads these: `db.DBNStore.from_file(p).to_df()`. The files are
small (about 3.6 MB of bars, 50 MB of definitions), so the whole archive fits in memory.

**How to get at it.** The cloud workspace cannot see `E:\`. The last session asked
for folder access to `E:\Databento\GLBX.MDP3` through the device bridge (Ben
approves a prompt) and either ran Python there (`pip install databento` works) or
staged files into the container. Tests must NOT need the archive: build synthetic
fixtures, and keep any real-data check as a separate, skippable test.

## 3. AT-41: the roll cross-check (the engine's first step)

Registered in `REGISTERED_tsmom_fetch.md` §5, threshold fixed before the numbers:

> **More than 2% of rolls disagreeing by more than one session, on any single root,
> stops the run.** Below that, every disagreement is listed in the report and the
> registered `definition` date is used.

- **Two readings of the calendar:** (a) each contract's `expiration` from the
  definition snapshots; (b) the dates `c.0` changes `instrument_id` in the bars.
- It checks the **calendar data**, not which contract is held. Amendment C changes
  the held contract for 5 roots but not this check (§0.2, last paragraph).
- **A late-listed root counts only rolls inside its own history** (RTY from 2017-06,
  TN from 2016-01). A missing pre-listing year is not a disagreement.
- **Known edge:** the first pull's bars end 2026-09-17, and the top-up files
  2026-09-18. Don't count that boundary as a roll.
- Output: per root, rolls compared, disagreements >1 session, the %, pass/stop, and
  every disagreement with dates. This goes in the run report and gates AT-43.

## 4. AT-42: the engine, with hand-built tests

The spec is `REGISTERED_tsmom.md` §2. The parts most likely to be wrong, and the test
each one needs, **were written down before any code** (old handover §5.4):

| Part | Rule | Test that must exist |
|---|---|---|
| **Held contract** | front month, rolled 5 trading days before expiry; **GC/SI/HG/ZN/TN**: nearest contract in the active cycle (GC Feb/Apr/Jun/Aug/Oct/Dec; SI and HG Mar/May/Jul/Sep/Dec; ZN and TN quarterly), rolled 5 trading days before the first business day of its delivery month (§0.2) | synthetic calendar: the held contract on the days around each roll, including an HG late-August roll straight to December (`c.4`) |
| **Signal series** | difference back-adjusted continuous series, built from the **held** sequence | a synthetic two-contract series in which the continuous series and the held-contract book differ by **exactly the gap** |
| **Signal** | sign of the trailing k-month return, t−k−1 … t−1, no skip month; ensemble k ∈ {3, 6, 9, 12} | hand-computed sign on a toy series; an assertion that there is no skip month (the paper's footnote 10 covers cross-sectional momentum, not TSMOM) |
| **Vol estimator** | EWMA, δ = 60/61 (centre of mass 60), variance about the EW mean, ×261, **lagged one day** | pandas path against a hand-built weighted sum. `bias=True` vs `bias=False` is a one-flag difference that still yields a plausible number, so the test must tell them apart |
| **Sizing** | 40% ex-ante vol per position, equal weight across live signals; **integer contracts** | rounding cases, including a target of 0.4 contracts rounding to 0 (at $22k most markets round to 0 or 1; that's the capacity finding, spec §3) |
| **Rebalance** | monthly, five tranches on trading days 1/5/9/13/17 | a tranche calendar on a month with a holiday |
| **P/L** | on the **actual held contract**, with a roll cost; three friction levels ($0.50 / $1.25 / $2.50 per contract per side) | a roll day's P/L equals held-contract P/L plus the roll cost, not the continuous-series change |
| **Rates arm** | the signal and P/L of arm (b) come from TN (MTN = TN/10 notional); arms (a) ZN and (c) none are reported alongside, **unranked** | all three appear in the output and nothing ranks them |
| **Holdout** | every date passes through `split_months`; training is before 2022-01-01 | a test that the runner calls `split_months` (mirrors `holdout.split_sessions`) |
| **Warm-up** | a root enters when it has 261 returns | RTY enters around 2018, TN around 2017 |

**Mutation-test every guard** (this line's practice): break the code on purpose and
make sure a test fails. Run with `python -B -p no:cacheprovider` (a stale
`__pycache__` once made the verdicts meaningless). **Commit before a mutation sweep:**
`git checkout --` has already thrown away uncommitted work once.

## 5. Where the code goes

- `strategy/tsmom/` (new), with tests in `tests/strategy/tsmom/`. **Don't touch
  `strategy/orb/`.**
- Reuse `common/tsmom_holdout.py`. `common/tsmom_fetch.py` is the only module that
  can spend money; the engine never imports it.
- Bundles are named `tsmom-YYYYMMDD[a-z].bundle`, delivered to
  `D:\Trading\Claude outputs`, built from Ben's current tip (check it with the
  bridge: `git log -1` in `D:\Trading`). Ben's tip at handover: `8315be4`.

## 6. Standing constraints

- No API key in chat; `DATABENTO_API_KEY` goes through `common.secrets_util.resolve`
  only. The engine needs no key.
- The connected IBKR account is **live and read-only**: no orders, ever.
- Nothing is spent without Ben confirming the figure (none should be needed).
- Results follow Project rule 8: a monday Result doc on the item, plus the project
  doc and a raw `.txt`. Commands for Ben go on the board (rule 7).
- At $22k this is a **measurement, not a trading decision** (spec §3: 8 of 13 markets
  can't reach half a micro contract). MTN trades a median of 282 contracts a day,
  which matters for slippage later, not for the backtest.

## 7. Next steps (board)

1. **AT-42**: engine plus the tests in §4. Subitems as steps.
2. **AT-41**: cross-check, run as the engine's first step on the real archive.
3. **AT-43**: the training-side run, once AT-41 passes and AT-42 is green. The result
   goes in a Result doc; the holdout stays locked.

Suggested split (Project rule 9): **Opus/high** for the engine and tests (AT-42) and
the result's interpretation (AT-43). **Sonnet/medium** for running AT-41 on the
archive, bundling, and board updates.
