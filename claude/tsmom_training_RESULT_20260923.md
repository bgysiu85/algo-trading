# TSMOM training-side run (W06-0005): RESULT, 2026-09-23

**Chat:** TSMOM chat (Opus, high). **Board:** W06-0005 (this run, Done), W06-0008 (Ben's decision, new).
**Code:** `strategy/tsmom/report.py`, `python -m strategy.tsmom.run report`; amendment E
(`REGISTERED_tsmom.md` §0.4) committed before the first run (76084f6, 7b7fa19).
**Bundle:** `tsmom-20260923a.bundle`, built on Ben's tip `f166099`.
**Raw:** `claude/raw/tsmom_report_training_20260923.txt` (= `D:\Trading\Claude outputs\tsmom_report_training_20260923.txt`).

## In plain terms

The registered TSMOM book (futures trend-following: 12 markets, monthly, going long or short in
the direction of each market's past 3–12 month move) made money on the training years,
mid-2011 to 2021: **$9,343 after costs on $22,129**, about **$885 a year (4.0%)**. But
almost all of it came from **2013–2015 ($12,201)**. The other seven and a half years
**lost $2,858** between them. It clears six of the nine registered tests and fails three:
one year (2014) supplies 54% of the profit, and neither bootstrap (a check that resamples
the markets or the years to see how often the total stays positive) reaches the 95% bar.
**Verdict: NOT CARRIED FORWARD.** The 2022+ holdout stays locked and unspent.

## Verdict, section 4

| # | Criterion | Value | Result |
|---|---|---|---|
| 1 | Positive after costs at mid ($1.25/side) | $9,343 | PASS |
| 2 | Both halves positive (split 2016-09) | $8,624 / $719 | PASS (second half barely) |
| 3 | drop-top-1 / drop-top-2 by market positive | $6,240 / $3,260 | PASS |
| 4 | Bootstrap by market ≥ 95% positive | 93.7% | **FAIL** |
| 5 | Bootstrap by year ≥ 95% positive | 88.6% | **FAIL** |
| 6 | Beats buy-and-hold, net and per unit of vol | $9,343 vs ($16,647); 0.28 vs (0.33) | PASS |
| 7 | No year and no market > 50% of net | 2014 = 54%; ES = 33% | **FAIL** |
| 8 | Ensemble ≥ median single-k (common window) | $9,447 vs $7,127 | PASS |
| 9 | Positive at high friction ($2.50/side) | $7,937 | PASS |

§4.1 applies: "a result that clears criteria 1–6 while failing criterion 7 is reported as
FAILED, with the concentration named." Here criteria 4 and 5 fail as well.

## The money (verdict book: arm b MTN, ensemble, fractional sizing at $22,129)

| Year | Gross | Cost (mid) | Net (mid) |
|---|---:|---:|---:|
| 2011 (from Jun) | 326 | 42 | 285 |
| 2012 | (3,039) | 89 | (3,128) |
| 2013 | 3,402 | 100 | 3,302 |
| 2014 | 5,194 | 112 | 5,082 |
| 2015 | 3,931 | 113 | 3,817 |
| 2016 | (1,657) | 104 | (1,761) |
| 2017 | (563) | 153 | (716) |
| 2018 | 216 | 200 | 17 |
| 2019 | (500) | 189 | (689) |
| 2020 | 2,019 | 151 | 1,868 |
| 2021 | 1,420 | 154 | 1,267 |
| **Total** | **10,749** | **1,406** | **9,343** |

Net at low / mid / high friction: $10,187 / $9,343 / $7,937. Realised volatility 14.2% a
year (MOP's book ran ~12%). Worst peak-to-trough **($5,960) = 26.9% of the account**,
bottoming 2020-06-08. Return per unit of volatility 0.28.

**By market (net, mid):** ES 3,103 · NG 2,979 · 6J 2,864 · 6E 2,161 · CL 1,649 · TN 1,231 ·
HG 98 · 6B (195) · GC (224) · 6A (635) · SI (1,583) · RTY (2,106, NOT READ: 42 months < 60).

## The distributions the spec sits in (nothing ranked)

- **Lookback grid** (single-k books, common window from 2012-06-08): k=1 $8,357, k=3 $2,422,
  k=6 $14,840, k=9 $13,470, k=12 $5,897, k=24 $4,373. The ensemble ($9,447) beat 67%.
- **Replication control, k=12 alone** (MOP's headline cell): $6,442 net, $610 a year.
  **k=12 with a one-month skip:** $72, i.e. nothing.
- **Rebalance-day grid** (one sleeve on day d = 1…21): every cell positive, $6,535 to
  $13,083; the tranched spec ($9,343) beat 62%.
- **Three rates arms, unranked:** (a) ZN $9,928, 8/9 criteria (fails only the year
  bootstrap); (b) MTN $9,343, 6/9; (c) none $8,202, 5/9. **Arm (b) is the registered arm
  (G3, chosen before any return) and this table does not move it.** Arm (a) trades
  full-size ZN, which the $22k account can't hold.

## Capacity (§5, measured, not scored)

| Book | Net mid | Net high | Realised vol | Worst drawdown |
|---|---:|---:|---:|---:|
| Fractional @ $22,129 | 9,343 | 7,937 | 14.2% | (5,960) |
| Integer @ $22,129 | 17,626 | 16,346 | 13.5% | (3,920) |
| Integer @ $100,000 | 38,099 | 31,795 | 14.0% | (24,321) |
| Integer @ $500,000 | 219,925 | 188,170 | 14.2% | (132,604) |

**The integer $22k figure must not be quoted as the result.** Whole contracts at $22k
round most targets to 0 or 1. The book held SIL on 0% of sessions and RTY on 4%, while
M6A/M6B were held about 75% of the time. Its extra $8,283 comes from rounding CL, NG, 6E and 6J
**up** to one lot in the years they happened to trend. That's lumpy exposure, not skill.
Its sign agrees with the fractional book, so §5's "sign flip" headline does not apply.

Cap subsets at $22k (spec §3's lists, fixed 2026-09-17): 10% set (MNG, M6E, M6A, M6B, MJY)
nets $12,878 vol-targeted / $5,315 one-lot; 15% set (M2K + four FX) $6,529 / ($199).

## Found while running (before trusting the numbers)

1. **FX holds serial months from March 2017.** The registered FX rule is plain "front month",
   and CME began listing serial months: the book rolls 6E/6A/6B/6J into e.g. 6EQ7
   (August), which trades a few hundred contracts a day against ~140,000 in the quarterly.
   31% of the window's FX sessions are on a serial. The 2026-09-20 engine result's line
   "roll counts match … quarterly … FX" was wrong: 84 FX rolls in the training years, not ~46.
   **Effect:** on the ~300 days where both prices are on file, serial P/L minus quarterly
   P/L = ($138); scaled to all serial days, about **($390)**. The serial closes are noisy
   (correlation 0.96–0.98 with the quarterly) but not biased. Worst case, that's +$390 of net.
   **It cannot flip criterion 5** (88.6% vs 95%), so the verdict holds. A clean quarterly
   FX run needs FX `c.2`/`c.3` bars that weren't bought (under $1, not priced yet).
   Found by amendment C's volume-share diagnostic, which was registered for exactly this.
2. **Gold's October contract is thin.** GC's registered cycle includes Oct (CME card). On
   roll days the held GC contract carries a median 20% of root volume. Registered, not
   revisited; a caveat on the GC line only (GC nets ($224)).

## §10 prediction, checked

Predicted: positive gross, roughly flat after costs, criterion 7 failing on **market**
concentration (gold and crude), currencies contributing close to nothing. **Wrong in the
specifics:** net is positive, not flat; criterion 7 fails on a **year** (2014); gold and
silver lost money; 6J and 6E are among the top four contributors. Right that it would fail.

## Caveats

- Closes are 00:00 UTC prices, not settlements (amendment D).
- Micro sizing before the micros listed (MHG 2022, MNG 2023, MTN 2024) is a convention.
- RTY (2018-07) and TN (2017-01) enter late; the early book is 10–11 markets.
- AT-41's calendar check isn't independent of the vendor (W06-0007 still open).

## Independent check

A separate agent re-derived 21 headline figures from the CSV dumps without the report code
(net at 3 frictions, every year, concentration shares, drop-top, halves, both bootstraps,
buy-and-hold, ratios, vol, drawdown, integer $22k). **21/21 match** within $0.50/0.1pp. P/L is
exactly zero before the window and no date reaches 2022. Largest single-day market P/L:
ES ($605) on 2018-02-05, 2.7% of equity.

## What Ben must decide — W06-0008

- **A (recommended): close TSMOM at this spec.** Record NOT CARRIED FORWARD; holdout stays
  unspent; no rescue by arm (a), k=6 or any grid cell (§7). Close W06-0007 as moot. Items
  that were waiting on this result (W01-0002 TL-v0, W01-0005, W01-0008) proceed on their own.
- **B: spend one of the three §9 hypotheses on a corrected rerun.** FX held quarterly
  (amendment F), registered before rerunning. Needs a small FX data top-up (priced first,
  expected under $1) and a Sonnet/medium session. Expected to move net by about +$400, which
  would not change the verdict. Only worth it if you want a clean record.

## Next steps (board)

1. **W06-0008 subitem 1, Ben:** merge `tsmom-20260923a.bundle` and run the TSMOM tests
   (commands on the board).
2. **W06-0008, Ben:** A or B.
3. **W06-0007:** close as moot if A.

## Source files

`strategy/tsmom/report.py`, `strategy/tsmom/run.py` (`report`), `strategy/tsmom/book.py`
(`skip_months`), `tests/strategy/tsmom/test_report.py` (25 tests; 26/26 mutations caught),
`docs/research/REGISTERED_tsmom.md` §0.4 (amendment E) and §0.5 (post-run note).
