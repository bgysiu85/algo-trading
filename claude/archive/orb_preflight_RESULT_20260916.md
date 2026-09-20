# ORB pre-flight, reconciled and re-run on the tape we trade

`python -m strategy.orb.preflight --cache bar_cache_xnas` · raw:
`var/reports/orb_preflight_xnas.txt` and `_equs.txt`, 2026-09-16.
Commit `cd712d7`.

## The reconciliation

Three figures were in circulation for "usable 15-minute range". All three were
correct and all three measured different things:

| figure | what it is |
|---|---|
| **57.2%** | XNAS.BASIC, 15-min, usable — 15,886 / 27,777 |
| **27.4%** | EQUS.MINI, 15-min, usable — 7,049 / 25,769 |
| **31.8%** | EQUS.MINI, 15-min, ≥10 opening bars **before** the width guards — 8,201, and 8,201 − 60 narrow − 1,092 wide = 7,049 exactly |

None was labelled with its cache or its pairs files, so none could be compared
with another. Fixed: the report now prints cache, tape, window, pairs,
symbol-day count and `--limit` **at the top of the page**, not only in the
header a reader strips when they quote a table.

**Reproducibility, incidentally confirmed.** Today's EQUS re-run is
byte-identical to the 2026-09-07 file — same size, same 77,307 rows. The 27.4%
was never wrong, only unlabelled.

## A correction

Earlier on 2026-09-16 I said *"most of this universe cannot support an opening
range of any length"*, quoting the EQUS table. **That is false on the tape we
trade.**

EQUS.MINI captures a median **4.8%** of the consolidated tape at 16:00 and
1.5% by 09:30 — a name trading every minute appears with roughly 19 bars of
390. "Few bars" there was a feed artifact, not liquidity. On XNAS.BASIC, which
carries the FINRA TRF prints, **69.3% of symbol-days have a usable 5-minute
range and 57.2% a usable 15-minute one.**

## The grid — §10.6, new

| mins | usable | width p50 | RTH screen | up trig | zone retest |
|---:|---:|---:|---:|---:|---:|
| 5 | 19,260 (69%) | 6.38% | 1,541 (8%) | 12,998 | 5,037 |
| 15 | 15,886 (57%) | 9.46% | 1,831 (12%) | 9,684 | 2,618 |
| 30 | 14,089 (51%) | 11.11% | 1,884 (13%) | 7,971 | 1,715 |

| mins | R struct p50/p90 | R opp p50/p90 | R frac p50/p90 |
|---:|---:|---:|---:|
| 5 | 3.46 / 10.28 | 7.22 / 16.12 | **2.61 / 5.94** |
| 15 | 2.98 / 8.62 | 9.26 / 17.72 | 3.82 / 7.34 |
| 30 | **2.65 / 7.82** | 10.38 / 18.37 | 4.47 / 7.91 |

Until this run the module measured all three lengths and printed one —
`by_min.get(15, [])` hard-coded in four places. A parameter §8 marks
uncalibrated was represented by whichever column happened to be on the page.

## What the grid settles

**`STOP_MODE = opposite` is eliminated, at every length.** Median R of
7.2–10.4% of price against `MAX_R_PCT` of 12%, p90 16–18%. That is VW9's shape
(9.4% / 20.7%) — which was discovered *after* that study cost a month. Two of
the ten source videos' stop rule, gone on measurement before a line of entry
logic exists.

**The range guards are not doing the strategy's job.** 7.1% excluded at 15
minutes against the spec's "worry above a third".

**The leak cut passes.** Rejected symbol-days trigger at 52.2% against
survivors' 62.1% — 84%. Stage 2 barely selects on the event ORB trades, which
was §13's top limitation.

**`MIN_RANGE_BARS` is the choice, not a detail.** 89.8% usable at ≥3 of 15
bars, 64.3% at ≥10, 56.2% at ≥12. The curve is steep across the span, so the
threshold decides how much of the universe ORB gives up, and it is still a
guess.

## What the grid does NOT settle, and the coupling it exposes

**It cannot pick `ORB_MINUTES`,** because it contains no P/L. Shorter is more
often usable and triggers more; longer gives the RTH screen more time to see a
move. Both directions are live.

**And the length and the stop are coupled**, which is the finding:

- the **structure** stop *tightens* as the range lengthens (3.46 → 2.98 →
  2.65) — it is the trigger candle's low and does not scale with the range; a
  later trigger is a calmer candle;
- the **range-fraction** stop *widens* (2.61 → 3.82 → 4.47) — it is a fraction
  *of* the range and scales with it directly.

So at 5 minutes `rangefrac` is the better stop (p90 5.94% against structure's
10.28%) and at 30 minutes `structure` is (7.82% against 7.91%). **Picking a
length first and a stop second would fix the wrong confound** — the same
mistake §5.3 warns about for retest-vs-stop. The grid in §14 step 9 must be run
as `ORB_MINUTES × STOP_MODE` jointly.

## The number that can still kill it

**§10.2: only 8–13% of usable symbol-days pass even three of the four RTH
screen rules** — 1,541 at 5 minutes, 1,831 at 15. Over ~548 sessions that is
about three names a session.

And the fourth rule, `relative_volume_10d_calc`, is **still not computable**:
it needs ten sessions of intraday volume by time of day and each cache file
holds three. It is reported as NOT COMPUTABLE rather than approximated from
two sessions — a screen simulated on three of its four rules is not the
screen.

That matters more here than anywhere else, because
`largecap_evidence_20260911.md` finds **100% of the stocks-ORB paper's claimed
edge came from ranking on first-5-minute relative volume**, not from the
trigger. The unmeasurable rule is the one the outside literature says carries
everything.

**Next candidate: `bar_minute` holds 21.0M XNAS rows.** If its coverage
includes the ten sessions before each screened symbol-day, RVOL becomes a
query rather than a Databento pull. Worth checking before anything is spent.

## §10.5, a warning not a result

Stops resolve faster and more often than targets: 6,001 triggers touched the
structure stop at a median of 4 bars, 5,787 reached 2R at a median of 6. With
§7.2's "stop wins on the same bar", `EXIT_MODE = r_2` starts at a
disadvantage, and the intrabar-ambiguity count will be large.

## State

Nothing here is a P/L and nothing here is an edge. Five of ORB's twenty
uncalibrated parameters are now set from data rather than from a result. The
go/no-go in §11 is unchanged and unmet, and `var/state/holdout.json` remains
unspent.
