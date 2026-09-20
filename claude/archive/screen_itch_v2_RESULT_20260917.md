# screen_itch v2 — the capture by the clock, and the baselines on it. Result, 2026-09-17

Registered in `docs/research/REGISTERED_screen_itch_v2.md` (64134cc) with
amendment A (7846b42, pre-run). Reports: `var/reports/itch_capture.txt`
(+ `.json`, `.csv`), `screen_sim_itch_v2.txt`, `pairs_overlap_v1_v2.txt`,
`pairs_overlap_basic_v2.txt`, `pit_h0_itch_v2.txt` (+ `.json`),
`pit_strategy_mcl_itch_v2.txt`, `pit_strategy_mc5_itch_v2.txt`. Artifact
page: "Capture by the Clock".

**Headline.** The published baselines are now **H0 (11.77), MCL (8.97), MC5
(8.57) per trade at $4.26** on `screen_pairs_pit_itch_v2.json` (6,411
symbol-days, 550 sessions). They sit within a few tens of cents of v1. Both
strategies beat the control on both denominators and lose in both halves and
after drop-top-5. The measurement that changed is the early morning: before
30 March 2026 Nasdaq's book carried about a quarter of the volume the live
screen could see; after it, 2% at 04:30 rising to 11% by 09:30. **The tape
line closes here.**

## 1. The ladder (§1 step 1, §2.1–2.2)

Step 0 (statistics extended to both PIT universes) priced and ran at $0.00;
PIT coverage is complete (6,170 of 6,170 at 09:30). Direct measurement,
ITCH ÷ consolidated cleared volume, band = 50k–500k consolidated shares by
09:30:

| cutoff | before p10 / p50 / p90 (n) | after p10 / p50 / p90 (n) |
|---|---|---|
| 04:30 | 0.036 / **0.225** / 0.733 (1,806) | 0.000 / **0.020** / 0.212 (906) |
| 06:00 | 0.055 / 0.247 / 0.675 (2,531) | 0.000 / 0.067 / 0.282 (984) |
| 07:00 | 0.060 / **0.256** / 0.659 (2,909) | 0.000 / **0.090** / 0.327 (1,035) |
| 08:00 | 0.060 / 0.239 / 0.556 (3,495) | 0.001 / 0.090 / 0.257 (1,112) |
| 08:30 | 0.014 / **0.138** / 0.333 (3,918) | 0.012 / 0.097 / 0.264 (1,128) |
| 09:30 | 0.039 / **0.153** / 0.328 (4,084) | 0.032 / **0.111** / 0.275 (1,155) |

(Full 30-minute ladder in the report; PIT and all-active populations sit
lower — 0.19 / 0.13 and 0.20 / 0.13 before, 0.07–0.09 after.)

**Stop rules.** §2.1 as written (row age p90 < 15 min) fails at 04:30–08:00
(23–80 min) and was mis-specified: the statistic is republished on change,
so age is time since the last trade. Rows over 30 min old *while* the
exchange printed inside those 30 min: **0.00% at every cutoff** (17,929
symbol-days). Restated pre-run; passes. §2.2's condition — the before-line
falls across 08:00 — passes (0.239 → 0.138). Its "after: flat" prediction
missed: 0.020 → 0.111, rising all morning.

## 2. The thresholds

| tape / screen | 04:30 | 06:00 | 07:30 | 08:00 | 08:30 | 09:30 |
|---|---|---|---|---|---|---|
| XNAS.BASIC, 0.552 | 55,200 | 55,200 | 55,200 | 55,200 | 55,200 | 55,200 |
| ITCH v1, chained 0.126 | 12,600 | 12,600 | 12,600 | 12,600 | 12,600 | 12,600 |
| ITCH v2 before 30 Mar | 22,490 | 24,710 | 24,400 | 23,900 | 13,800 | 15,340 |
| ITCH v2 after 30 Mar | 1,980 | 6,750 | 8,700 | 8,990 | 9,670 | 11,140 |

Before the change the two tapes were one tape until 08:00 and BASIC's
daily 0.552 demanded 55,200 exchange shares where the honest figure was
~24,000: **the BASIC universe was too tight early by ~2.3×; v1's chain was
too loose by ~2×; v2 sits between.** That is why the early names v1 found
mostly survive, and why the §3 prediction that they would reverse was
wrong (Nasdaq's share of exchange-only pre-market volume is 0.24, not
0.30–0.55).

After the change the early thresholds are tiny and the p10 is zero: on one
name in ten the exchange has printed nothing by 04:30–08:00. A clause scaled
by the median admits above-median-routed names the live screen would not
have and drops below-median ones it would. **On the ~110 post-change
sessions the volume clause on XNAS.ITCH is a weak proxy for the live one.**
The fix, if a study ever needs those sessions' universe precisely, is a
hybrid — ITCH before the change, XNAS.BASIC after (clean once the TRF
reports from 04:00; `tape_compare` post-cut read (8.55) BASIC vs (8.98)
ITCH). Not done here; the baselines below move by cents between universes
and no verdict depends on it.

## 3. The universe (§2.3)

| | symbol-days | sessions | median/session | knowable 04:30 | first_seen median | 08:00-hour share |
|---|---|---|---|---|---|---|
| XNAS.BASIC | 6,170 | 551 | 11 | 1,394 | 07:17 | 28.7% |
| ITCH v1 (p50) | 6,564 | 551 | 11 | 1,810 | 06:57 | 20.3% |
| **ITCH v2** | **6,411** | 550 | 11 | 1,771 | 07:01 | 21.5% |

v2 vs v1: 6,269 shared, 295 v1-only, 142 v2-only, **Jaccard 0.935**;
first_seen on shared names 3,982 same / 1,730 later on v2 / 557 earlier,
p90 +4 min. v2 vs BASIC: 5,842 shared, Jaccard 0.867; 2,805 earlier on v2,
p10 −28 min. Fast path vs `screen_at`: 0 disagreements.

**Confound, named.** Between the v1 and v2 runs the ORB chat's archive
extension re-pulled the September daily chunk from the 5th and dropped the
daily bars for 1–4 September (`archive_defect_daily_chunk_start_20260917.md`);
`regular_close.json` was regenerated 07:36. v2 therefore skipped 2026-09-01,
-02, -03 (no prior close) and gained 09-14, 09-15. Three sessions of 550
swapped; the ladder is unaffected. Repair is on the archive side.

## 4. The control (§2.4)

`pit_h0` on v2, $4.26: **AS SCREENED (11.77)/trade, (10.60)/symbol-day over
5,775**; halves (11.18)/(12.23); drop-top-5 (12.59)/trade. **KNOWABLE AT
04:30 (12.05) over 1,587**, 15% below the stage-2 rejects. Late qualifiers
+0.29. Sign stable across $1.00–$8.92. Constants in `pit_h0_itch_v2.json`;
the `H0_*` block stays BASIC.

## 5. The strategies (§2.4)

| | MCL v1 | **MCL v2** | MC5 v1 | **MC5 v2** |
|---|---|---|---|---|
| point-in-time, per trade | (8.81) | **(8.97)** | (8.49) | **(8.57)** |
| trades | 3,960 | 3,908 | 6,630 | 6,462 |
| per symbol-day | (5.31) | (5.47) | (8.57) | (8.64) |
| vs H0 per trade / symbol-day | +3.09 / +5.40 | **+2.79 / +5.13** | +3.41 / +2.14 | **+3.20 / +1.96** |
| halves | (8.71)/(8.89) | (8.94)/(9.00) | (8.69)/(8.32) | (8.70)/(8.46) |
| drop-top-5 per trade | (9.69) | (9.86) | (9.78) | (9.85) |
| early names per trade / n | (8.83)/2,430 | (8.73)/2,393 | (6.56)/2,980 | (7.48)/2,889 |
| floor bit | 13.0% | 13.7% | 50.7% | 51.6% |
| leak universe / intraday | (0.68)/3.59 | (0.74)/3.83 | (1.87)/10.24 | (2.02)/10.47 |

Both: "beat the control on both denominators and still lose money." MC5's
2,412 one-bar trades at (31.95) are 139% of its net (stop lever, closed).
MC5's leaky stage-2 arm again reads (0.12).

## 6. Predictions scored

Missed: statistic age (mis-specified rule); before 07:00 0.30–0.55 (0.256);
after flat (rises); pre-08:00 threshold 30–55k (22–26k); knowable 1,300–1,600
(1,771); first_seen 07:05–07:25 (07:01). Held: before 09:30 0.10–0.16
(0.153); universe 6,000–6,600 (6,411); Jaccard ≥ 0.85 (0.935); H0
(10.5)–(13.5) (11.77); MCL (7.5)–(10) (8.97); MC5 (7.5)–(10) (8.57); both
beat H0 per trade; halves and drop-5 negative. The misses are all on the
shape of the early morning; the baselines were predicted and landed.

## 7. What this decides

- Published control and MCL/MC5 point-in-time figures: the `_itch_v2`
  reports. v1 and BASIC files kept, superseded. `PROGRAM_INDEX` updated.
- The tape line closes. From BASIC to v1 to v2 the strategy figures moved by
  under a dollar a trade once the bars were clean; what remains imprecise is
  which names the screen admits on post-change sessions, and no verdict
  depends on it.
- Nothing about a variant. Closed studies stay closed. `holdout.json` shut.

## 8. Next (from the queue agreed on 2026-09-17)

1. Price the Databento `status` schema (halts / LULD) — estimate only.
2. Run the built EDGAR shares pull; ceiling test only.
3. Probe FINRA short interest.
4. Optional, only if a study needs it: the hybrid post-change universe (§2).
