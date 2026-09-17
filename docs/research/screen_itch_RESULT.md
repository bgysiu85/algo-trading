# The screen rebuilt on XNAS.ITCH — result, 2026-09-17

Registered in `docs/research/REGISTERED_screen_itch.md` (commit a88e321)
before any of it ran. Reports: `var/reports/tape_capture.txt`,
`screen_sim_itch_{p10,p50,p90}.txt`, `pairs_overlap.txt`, `pit_h0_itch.txt`
(+ `.json`), `pit_strategy_mcl_itch.txt`, `pit_strategy_mc5_itch.txt`.
Artifact page: "The Rebuilt Screen".

**Headline.** The stop rule passed exactly; the new published baselines are
**H0 (11.90), MCL (8.81), MC5 (8.49) per trade at $4.26** on a 6,564
symbol-day universe built on the exchange-only tape. Both strategies beat the
control on both denominators and still lose in both halves and after
drop-top-5. One prediction was badly wrong: Nasdaq's own book carries **23%**
of XNAS.BASIC's pre-market shares, not 55–75%, and that leaves one defect in
this run's own method (§4) that is the next registration.

## 1. The diagnosis check (§2.1) — passed

`tape_capture`, 554 sessions, ratio = ITCH ÷ BASIC cumulative volume, bars
closed by the cutoff, band population (BASIC 09:30 volume within 0.5×–5× the
scaled threshold; 221,909–251,632 symbol-days per cutoff):

| cutoff | before 2026-03-30 p10 / p50 / p90 | after p10 / p50 / p90 |
|---|---|---|
| 07:00 | **1.000 / 1.000 / 1.000** (n 160,786) | 0.003 / **0.315** / 0.829 |
| 08:00 | 0.968 / 1.000 / 1.000 | 0.009 / 0.239 / 0.678 |
| 09:00 | 0.006 / 0.228 / 0.707 | 0.010 / 0.217 / 0.619 |
| 09:30 | 0.008 / **0.229** / 0.691 | 0.014 / **0.229** / 0.629 |

Before the cut the two tapes are the same tape until 08:00 — not one name in
the bottom decile differs — and by 09:30 the two regimes read identically.
That is the TRF opening at 08:00 and releasing the queue, as `trf_probe` said.
On the PIT population the 09:30 median is 0.318 (before 0.356, after 0.211);
on every active name 0.227. One ratio above 1.0 in 251,632 (a join defect,
counted, not averaged).

## 2. The chained capture, and the miss

capture_ITCH = 0.552 × 0.229 = **0.126** → threshold **12,600** ITCH shares
(p10 0.005 / p90 0.374). Registered prediction: ratio 0.55–0.75, capture
0.30–0.41. **Missed.** `tape_compare`'s 79% was a *bar* count; most of the
pre-market shares in these names print off-exchange.

The dispersion is the more important number. XNAS.BASIC's capture band was
0.458–0.656; XNAS.ITCH's runs 0.009–0.677. An absolute volume threshold on
this tape is partly a test of which names route through Nasdaq's matching
engine before the open. The prices are clean; the volume column is a weaker
proxy for the live screen than BASIC's was. Stated as a limitation; not a
reason to go back to bars carrying hours-old prints.

## 3. The universe (§2.2)

| universe | capture | threshold | symbol-days | median/session | knowable by 04:30 | first seen in 08:00 hour |
|---|---|---|---|---|---|---|
| XNAS.BASIC (old) | 0.552 | 55,200 | 6,170 | 11 | 1,394 | 28.7% |
| ITCH p10 | 0.005 | 500 | 8,907 | 15 | 3,028 | 19.0% |
| **ITCH p50 (scored)** | 0.126 | 12,600 | **6,564** | 11 | 1,810 | 20.3% |
| ITCH p90 | 0.374 | 37,400 | 5,555 | 10 | 1,795 | 21.6% |

Fast path vs `screen_at`: 0 disagreements on all three runs. Three sessions
skipped for no prior close (2024-07-01, 2026-09-14, 2026-09-15), as before.

Overlap, BASIC vs ITCH p50: **5,922 in both**, 248 BASIC-only, 642 ITCH-only,
**Jaccard 0.869** (predicted 0.6–0.8). `first_seen` on the shared names:
median **06:57 on ITCH vs 07:17 on BASIC**; 2,902 earlier on ITCH, 2,634
unchanged, 386 later; p10 shift −43 min. Predicted "mostly unchanged before
08:00". **Missed** — see §4.

The 08:00 hour held 28.7% of BASIC's first sightings and 20.3% of ITCH's: the
TRF release was manufacturing "qualifies at 08:0x" events. That part is the
defect leaving.

## 4. The defect this run found in its own method

The 0.229 ratio is a 09:30 figure. Before 08:00 on every pre-cut session the
ratio was 1.000 — same tape — and the ITCH threshold there is 12,600 against
BASIC's 55,200. A name with 20,000 shares at 06:00 clears the ITCH screen and
did not clear the BASIC one. So the earlier sightings and the rise in
knowable-by-04:30 names (1,394 → 1,810) are **by construction of the chain**,
not because the exchange tape reveals names sooner. (BASIC had the mirror
problem — 0.552 is a daily figure applied to a pre-08:00 window where BASIC
was itself exchange-only — so neither universe has this right; ITCH is looser
where BASIC was tighter.)

The honest threshold is time-varying, and the ladder in §1 measures it at
each cutoff. Applying it changes how the screen is simulated (`screen_at`
holds `capture` constant), so it is the **next registration**, not a patch.
Until it runs, the 1,810 knowable names and the EARLY arms below are upper
bounds.

## 5. The control (§2.3)

`pit_h0` on ITCH p50, $4.26: **AS SCREENED (11.90)/trade, (10.71)/symbol-day
over 5,909 trades**; halves (10.90)/(12.74); drop-top-5 net (74,208) =
(12.56)/trade. **KNOWABLE AT 04:30 (11.58) over 1,611**, sitting **−12%** of
the way from the rejects (9.81) to the survivors +4.72 (was −29%). Late
qualifiers worth (0.31) (was (1.35)). Sign stable $1.00–$8.92. Published BASIC
reference: (15.40)/(13.99) over 5,606; knowable (14.06) over 1,258.
Prediction (12)–(16): held in substance, ten cents outside the range.

Constants written to `var/reports/pit_h0_itch.json`; `pit_strategy --h0`
reads them. The `H0_*` block in `pit_strategy.py` stays the BASIC reference.

## 6. The strategies (§2.4)

| | MCL old | **MCL new** | MC5 old | **MC5 new** |
|---|---|---|---|---|
| point-in-time, floored, per trade | (10.52) | **(8.81)** | (13.50) | **(8.49)** |
| trades | 3,955 | 3,960 | 6,883 | 6,630 |
| per symbol-day | (6.74) | (5.31) | (15.06) | (8.57) |
| vs H0 per trade / per symbol-day | +4.88 / +7.25 | **+3.09 / +5.40** | +1.90 / (1.06) | **+3.41 / +2.14** |
| halves | both negative | (8.71) / (8.89) | both negative | (8.69) / (8.32) |
| drop-top-5 per trade | negative | (9.69) | negative | (9.78) |
| early names, per trade / n | (9.03) / 2,062 | (8.83) / 2,430 | (9.59) / 2,570 | (6.56) / 2,980 |
| floor bit | 24.7% | 13.0% | 68.2% | 50.7% |
| leak: universe / intraday | (0.13) / 4.79 | (0.68) / 3.59 | (2.24) / 9.37 | (1.87) / 10.24 |

Both "beat the control on both denominators and still lose money" — the
module's own sentence. MC5's per-symbol-day verdict flips from losing to the
control to beating it; at (8.49) a trade that is worth nothing. MC5's 2,437
one-bar trades at (32.02) are 139% of its net — the shape the stop-lever study
closed on; not reopened. MC5's leaky stage-2 arm reads (0.12) on this tape
(+3.14 at $1.00): the closest anything here has come to zero, on a universe
chosen with the day known, which is all it is.

Predictions: MCL (7)–(10), negative both halves and drop-5, beats H0 per trade
— **held** ((8.81)). MC5 (10)–(14) — **missed**, better than predicted.

## 7. What this decides

- The published control and the published MCL/MC5 point-in-time figures are
  the `_itch` reports on `screen_pairs_pit_itch_p50.json`. BASIC files stay on
  disk, superseded, so earlier results still reproduce. `PROGRAM_INDEX`
  updated.
- Not a before/after of the fix for the strategies (universe and bars both
  change); `tape_compare` isolated the bars: (10.52) → (8.82) on a fixed
  universe.
- Nothing about any variant. Closed studies stay closed; conclusions resting
  on the 08:00 hour or the BASIC before/after split are withdrawn as
  unmeasured.
- `holdout.json` untouched.

## 8. Next

1. **Register a time-varying capture for the ITCH screen** (§4): per-cutoff
   ratio from `tape_capture.json`, before/after the cut, in place of one 09:30
   figure; re-run `screen_sim`, `pit_h0`, `pit_strategy`. Small code change in
   `screen_at`/`screen_sim`; the measurement already exists.
2. The ORB and swing sessions switch per `handover_tape_switch_20260917.md`.
3. Then the items already queued: Databento `status` (halts) pricing, the
   EDGAR shares pull, FINRA short interest.
