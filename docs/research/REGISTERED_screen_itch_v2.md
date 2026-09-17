# REGISTERED — screen_itch v2: the capture measured against the consolidated tape, by the clock

`screen_itch_RESULT_20260917.md` §4 found the one defect in its own method:
XNAS.ITCH's capture was chained (0.552 × 0.229 = 0.126) from a single 09:30
ratio and applied at every tick, while before 2026-03-30 the two tapes were
identical until 08:00. The threshold before 08:00 was therefore a fifth of
BASIC's on the same bars, 2,902 shared names surfaced "earlier" by
construction, and the knowable-by-04:30 count rose 1,394 → 1,810 for no
reason in the market.

**Committed before `common/itch_capture`, the ladder `screen_sim` run, and
`pit_h0` / `pit_strategy` on the resulting universe have run.** Like v1 this
is a re-baselining; its output replaces the v1 (p50) baselines whichever way
it moves them. The stop rules are §2.1 and §2.2.

## 1. What changes, and what is run

**The chain is gone.** The archive holds `EQUS.SUMMARY` `statistics` for
every session, and `CLEARED_VOLUME` (stat_type 6) is the consolidated
cumulative volume *at a time* — `capture_intraday` already used it as a
ladder for EQUS.MINI. So the capture is measured directly, with no BASIC in
the loop, and by the clock:

    capture(t) = XNAS.ITCH bars closed by t  /  consolidated cleared volume published by t

for t every 30 minutes, 04:30 → 09:30, on each side of 2026-03-30.
Consolidated cleared volume at 07:00 before the cut does not contain the
off-exchange trades the TRF had not yet reported — the SIP had not seen them,
and neither had TradingView's `premarket_volume`. That is the quantity the
live screen compared 100,000 against at that minute on that date.

0. **Extend the statistics archive to the point-in-time universes.** The
   `EQUS.SUMMARY` statistics were pulled scoped to `screen_pairs.json` ∪
   `screen_pairs_consolidated.json` (the stage-2 candidate lists); the PIT
   universes overlap those by roughly a sixth. `databento_fetch` is run with
   all four pairs files (union; the manifest re-fetches only dates where the
   union adds symbols), **estimate first**, confirmed only under **$1.00**. If
   it prices above that, the run proceeds on the existing archive and the
   PIT population's coverage is reported as what it is.
1. **`common/itch_capture`** — the ladder, on three populations: the **band**
   (names whose consolidated cleared volume by 09:30 lies within 0.5×–5× of
   the live 100,000 — the clause's own units, the headline), the PIT
   universe, every active name (≥ 10,000 consolidated). Reports the
   statistic's age at each cutoff (minutes between the cutoff and the
   cleared-volume row used). Writes `ladder[before|after]` keyed by ET
   minute to `var/reports/itch_capture.json`.
2. **`common/screen_sim --dataset XNAS.ITCH --capture-ladder var/reports/itch_capture.json`**
   → `var/state/screen_pairs_pit_itch_v2.json`. `ScreenConfig.ladder` is a
   step function held from the left (a tick before the first measured step
   takes that step — the highest capture, the tightest threshold, the
   conservative side); `screen_at`, `screen_accumulated` and `sweep` all read
   `volume_min_at(t)`, and the fast-path agreement check runs with the ladder
   in place. `ladder=None` is bit-identical to the screen as it was.
3. **`common/pairs_overlap`** v1-p50 vs v2, and BASIC vs v2.
4. **`pit_h0 --dataset XNAS.ITCH --pairs <v2>`** → `pit_h0_itch_v2.{txt,json}`.
5. **`pit_strategy --strategy mcl|mc5 --dataset XNAS.ITCH --pairs <v2> --h0 pit_h0_itch_v2.json`**.

The v1 p50 files are kept; nothing is overwritten.

## 2. What is read, fixed now

### 2.1 Stop rule: the statistic is fresh enough for the ladder

At every cutoff, the p90 age of the cleared-volume row used must be **under
15 minutes**. If a cutoff reads staler than that, the ladder is coarsened to
the resolution the statistic supports before anything downstream runs, and
that is recorded as a PRE-RUN amendment, not a result.

### 2.2 Stop rule: the shape, in consolidated units

Before the cut: capture **high early** (Nasdaq's share of exchange-only
pre-market volume) and **falling from 08:00** as the TRF queue reaches the
SIP; 09:30 lower than 07:00 by a clear margin. After the cut: **flat** through
the morning within the band's noise. If the before-ladder does not fall
across 08:00, the account of the defect is wrong and the rebuild stops.

### 2.3 The universe

Symbol-days and sessions vs v1-p50's 6,564; overlap and `first_seen` shift
vs v1-p50 and vs BASIC's 6,170; knowable by 04:30 (v1-p50 1,810, BASIC
1,394); the 08:00-hour share of first sightings; the agreement check.

### 2.4 The control and the strategies

Exactly as v1 §2.3–2.4: H0 as screened / knowable at $4.26, both
denominators, halves, drop-top-5; MCL and MC5 vs their own H0 on both
denominators, halves, drop-top-5, EARLY vs ALL, the floor's bite. v1 p50
figures: H0 (11.90) over 5,909 / knowable (11.58) over 1,611; MCL (8.81) over
3,960, +3.09 / +5.40; MC5 (8.49) over 6,630, +3.41 / +2.14.

## 3. Predictions

- Statistic age p90 **< 5 min** at every cutoff (the stat is updated
  continuously; `capture_intraday` ran hourly cutoffs without noting lag).
- Before the cut, band median capture at **07:00: 0.30–0.55**; at **09:30:
  0.10–0.16** (v1's chain gave 0.126 there). After the cut: **0.10–0.16 at
  every cutoff**.
- So the pre-08:00 threshold before the cut is **30k–55k** ITCH shares
  against v1's 12,600, and the earlier-sighting artefact largely reverses:
  knowable by 04:30 **1,300–1,600**; `first_seen` median on shared names
  back near BASIC's 07:17 (**07:05–07:25**); v2 universe **6,000–6,600**
  symbol-days; Jaccard vs v1-p50 **≥ 0.85**.
- Baselines move little, because the bars are the same and most of the
  universe is shared: **H0 (10.5)–(13.5)**, **MCL (7.5)–(10)**, **MC5
  (7.5)–(10)** per trade; both strategies still beat H0 per trade, still
  negative in both halves and after drop-top-5.
- The PIT population's coverage in the statistics archive, if step 0 does
  not run: **15–30%** of PIT symbol-days.

## 4. What this decides, and what it does not

- Decides: the published control and MCL/MC5 baselines become the v2
  reports; v1-p50 is superseded and kept. The `H0_*` block stays BASIC.
- The selection in the denominator is stated, not hidden: the consolidated
  figure exists only for names in the stage-2 candidate lists (plus the PIT
  universes if step 0 runs). The band is drawn from those names. That is a
  population selected on daily activity, not on Nasdaq routing share, and it
  is the population the live screen's names come from; it is not the whole
  market.
- Does not decide anything about a strategy variant; closed studies stay
  closed; `holdout.json` stays shut.
