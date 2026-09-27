# W02-0012 — spread effect vs hold-time effect in the live book — RESULT (2026-09-23)

Live analysis chat. Board item W02-0012 (was AT-96). monday Result doc: https://ben-siu.monday.com/docs/5031515583 · Artifact page: https://claude.ai/artifact/52X1uygjHuQ8CvRDPWgCkr
Raw: `D:\Trading\Claude outputs\w02_0012_spread_vs_hold_20260923.txt`, `w02_0012_round_trips_20260923.csv`, script `w02_0012_spread_vs_hold.py` (reads `var\fills`, writes only to Claude outputs; no repo files touched).

Question (from `handover_holds_misses_levers_20260919.md` §4.2, §5): the live hold-time table (0–2 min holds lose most) and the spread table (≥2% spread loses most) might be the same trades, which would confound the trail-widen, time-cap and spread-gate levers. Split them.

## In plain terms

They are **not the same trades**. Only 3 of 14 wide-spread (≥2%) entries were out inside 5 minutes; the typical one was held ~19 minutes. There are two separate leaks: the 14 wide-spread entries lost **(612.25)**; 54 tight-spread entries stopped out inside 2 minutes lost **(510.01)**, of which 46 trades / **(526.04)** are MC5 (MCL's fast exits: 8 trades, +16.03). The fast stop-outs are not a spread cost — priced at the mid both ways they still lose **(385.51)**. Remove the wide-spread entries and the book goes from **(576.50)** to **+35.75**, and 60+ minute holds turn positive (**+83.88**, 11 trades, 64% win): "long holds lose" was the wide-spread trades.

## Book: 216 round trips, 2026-09-10 → 09-22 (09-23 excluded, still trading)

Both cuts (net $ / trades):

| Spread | 0–2 min | 2–5 | 5–15 | 15–60 | 60+ | All |
|---|---:|---:|---:|---:|---:|---:|
| < 1% | (345.04) / 46 | 98.84 / 38 | (192.78) / 45 | 594.75 / 38 | 25.63 / 9 | 181.40 / 176 |
| 1–2% | (164.97) / 8 | (33.74) / 2 | (86.86) / 5 | 81.67 / 9 | 58.25 / 2 | (145.65) / 26 |
| ≥ 2% | (238.74) / 2 | (10.38) / 1 | (93.50) / 4 | (110.13) / 3 | (159.50) / 4 | (612.25) / 14 |
| All | (748.75) / 56 | 54.72 / 41 | (373.14) / 54 | 566.29 / 50 | (75.62) / 15 | (576.50) / 216 |

Tight-spread (<2%) trades by strategy: MCL 54 trades **+395.88**; MC5 148 trades **(360.13)**, of which 0–2 min (526.04).

Spread cost (distance of fill from mid × shares, both legs): (634.50) across the book; wide-spread bucket (170.00) of its (612.25) loss — most of that bucket's loss is post-entry price action on thin names, not the toll. At the mid both ways the whole book is +58.00.

Sensitivity — same reading on: the handover's 09-10→09-18 book (180 trades; reproduces its tables to the cent), the book without 09-16 (defect session) and MC5 apex exits (161 trades), and without the 3 worst trades.

## What it means for each lever (no Ben decision needed now)

- **W03-0002 spread gate (2%)** — live evidence holds; it is not a hold-time effect in disguise. Registration unchanged; the full-quote backtest study remains the test.
- **W05-0007 trail widen (H-E3)** — the fast stop-out loss is real and survives removing wide spreads, but it is MC5-shaped (5-min signal, 1-s stop). The study should report MCL and MC5 separately.
- **W03-0004 time cap** — live motivation gone: tight-spread long holds made money; AEHL's 154-min loser was a wide-spread entry. Only the freed-slot argument (arm 2, cap modelled) is left.

## Caveats

Descriptive, after-the-fact cuts on 216 IB paper fills (14 wide-spread; CRBP (241.37) is a big share — without it the other 13 still lose (370.88)). The 2% line was registered before this ran; the 5-minute line and hold buckets come from the 09-19 handover. No minute bars needed (the old AT-23 dependency belongs to W03-0001).

## Next steps / board

- W02-0012 — Done (this result).
- W03-0002, W05-0007, W03-0004 — each got an Update pointing here; no status changes.
