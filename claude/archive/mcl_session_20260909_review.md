# MCL paper session review — 2026-09-09

Six round trips, **−$70.26**, two up and four down. Source:
`var/fills/mcl_fills_20260909.csv`. TV comparison read over CDP from Ben's own
chart with the symbol pinned and re-verified after each read.

| symbol | in | out | entry | exit | net | hold | exit |
|---|---|---|---:|---:|---:|---:|---|
| SUNE | 05:33 | 06:27 | 3.03 | 3.13 | **+8.63** | 55m | trail |
| FGL | 06:14 | 06:15 | 10.23 | 9.69 | **−55.38** | 2m | trail |
| BNC | 06:23 | 07:45 | 5.41 | 5.26 | **−16.37** | 83m | trail |
| ACCL | 06:31 | 08:13 | 3.03 | 2.88 | **−16.37** | 103m | trail |
| ODD | 08:29 | 09:30 | 17.57 | 17.71 | **+12.60** | 62m | window |
| SUNE | 08:48 | 09:30 | 3.04 | 3.02 | **−3.37** | 42m | window |

---

## 1. Three quarters of the loss is the gap between the rule's price and ours

| | |
|---|---:|
| entry slippage vs the signal bar's close | **−$16.02** |
| exit slippage vs the trail level / quote | **−$37.50** |
| **total against reference** | **−$53.52** |
| session result | −$70.26 |
| | **76%** |

The strategy is not mainly losing on being wrong about direction. It is losing
on the difference between the price the rule fired at and the price actually
obtained. `execution_cost_measured.md` put that allowance at $4.26 a round trip;
tonight it was **$8.92 a round trip**, more than double.

The exit half is the larger and has never been examined. Two rows carry it:

- **ODD, window close, −$0.17/share.** The quote was 17.75 / 17.88 — a 13c
  spread — and the market sell went out at 17.71, *four cents below the bid*.
- **FGL, trailing stop, −$0.152/share.** Trail level 9.842, filled 9.69.

The entry half is almost entirely one trade: **BNC −$19.00, everything else
together +$2.98.**

## 2. Every signal is acted on one minute later than it needs to be

Ben's original observation — *"TV bought at 6:21, IBKR bought at 6:23"* — was
right, and the fill log proves the mechanism without needing the probe. For the
three signals whose bars could be checked against TradingView:

| signal | bar that produced `ref_close` | bar closed | order sent | delay past close |
|---|---|---|---|---:|
| WYHG `ref 5.21` | 07:26 | 07:27:00 | 07:28:00 | **+60s** |
| LABT `ref 2.05` | 08:59 | 09:00:00 | 09:01:00 | **+60s** |
| LABT `ref 2.11` | 09:25 | 09:26:00 | 09:27:00 | **+60s** |

Three for three. The order goes out **two minutes after the signal bar's
label** — one minute is the bar closing and is unavoidable, the second is ours.
That second minute is what `common/bar_freshness.py` was built to attribute,
and it now has three independent confirmations that it exists.

It is not systematically expensive; it is *variance we are not paid for*. On
BNC it cost 20c (ref 5.22, ask 5.42 by the time the order went out). On WYHG it
would have *saved* about 14c, since the price fell from 5.21 to ~5.05 in that
minute.

## 3. TV vs broker on BNC

TradingView's strategy tester for NASDAQ:BNC, symbol verified:

| | entry | exit | result |
|---|---:|---:|---:|
| TradingView | 5.10 | 5.29 (trail) | ≈ **+$17** |
| Live | 5.41 | 5.26 (trail) | **−$16.37** |

**The exits agree.** Our trail level was 5.301, TV's stop filled at 5.29 — the
same level, three cents apart. The entire ~$33 swing is the entry: 5.10 against
5.41.

That is not $33 TradingView "made". Its 5.10 is a model fill at the signal
bar's close, not a price anyone transacted with size, and one minute of the gap
is the unavoidable bar-close wait. The honest reading is that an idealised
fill and a real one, two minutes apart on a moving name, differ by 6% of
price — against a 5% trail.

**Caveat that applies to every TV number here:** the Strategy Tester recomputes
from current bar history after the fact. It is a backtest of the day, not a
recording. `data_get_trades` also returns no timestamps, only a `time_index`,
so today's trade could only be identified by price — which Ben independently
reported as 5.10.

## 4. Opportunity cost of the three capped entries

The cap turned away three signals: WYHG 07:28, and LABT twice (09:01, 09:27 —
the second only reachable because the first was not taken). Simulated with
MCL's own exit semantics: trail from the peak as of the *previous* bar, 5%,
gap-through fills at `min(trail, open) − 1 tick`, window close at 09:30, tiered
commission both legs plus the $4.26 friction allowance.

| | entry | exit | out | reason | hold | net | after friction |
|---|---:|---:|---|---|---:|---:|---:|
| WYHG, backtest fill (close +1 tick) | 5.22 | 4.94 | 08:41 | trail | 69m | −29.37 | **−33.63** |
| WYHG, realistic fill at 07:28 | 5.08 | 5.06 | 09:30 | window | 118m | −3.37 | **−7.63** |
| LABT 09:01, backtest fill | 2.06 | 2.20 | 09:30 | window | 28m | +12.13 | **+7.87** |
| LABT 09:01, realistic fill | 2.04 | 2.20 | 09:30 | window | 28m | +14.13 | **+9.87** |
| LABT 09:27, backtest fill | 2.12 | 2.20 | 09:30 | window | 2m | +6.13 | **+1.87** |
| LABT 09:27, realistic fill | 2.13 | 2.20 | 09:30 | window | 2m | +5.13 | **+0.87** |

**Net opportunity cost: between +$2 and −$24 depending on the fill model — and
the sign is not even stable.**

Taking WYHG would have lost money on either fill model. Taking LABT at 09:01
would have made about $8–10. Since only one slot would have freed at a time,
the realistic counterfactual is roughly:

- **WYHG instead of holding BNC or ACCL:** −$8 to −$34, i.e. *worse*.
- **LABT at 09:01 instead of the second SUNE (−$3.37):** about **+$11 to +$13
  better**.

So the cap cost real money on exactly one of the three, and it saved money on
another. That is consistent with `consolidation_filter_test.md` §1 — over 373
sessions the cap denied 9 of 479 entries and *lifting it made the year worse*
(+$270 → +$162). Tonight is a fair sample of that: three denials, mixed signs,
small totals.

**Two caveats on these figures, both material:**

1. **The bars are TradingView's, not IB's.** The trader ran on IB bars, and
   this project has measured that tapes differ (`consolidated_volume_gap.md`;
   XNAS.BASIC carries a median 55% of the consolidated tape). A trail that is
   hit on one tape and not the other changes the answer. Re-running on IB bars
   is one command once today's session is cached.
2. **The entry price is assumed.** The skipped rows carry no bid/ask — the
   trader never quoted them — so the "realistic fill" column is read off the
   next bar's prints, not off a book we saw.

## 5. What this session says to do next

1. **Look at the exit, not the entry.** −$37.50 of exit slippage against
   −$16.02 of entry slippage, and the exit has never been measured. The ODD
   row — selling 4c through a 13c spread on a window-close market order — is a
   concrete, fixable defect: a marketable limit at the bid would have done
   better, and the window-close exit has no urgency that justifies crossing.
2. **Run `common.bar_freshness` inside tomorrow's session.** Three signals now
   show the same +60s. The probe attributes it to the history trim or to the
   loop cadence, and only one of those is a one-line fix.
3. **Log the quote on skipped rows too.** Every capped signal is a
   counterfactual we cannot price properly, because we recorded the reason and
   not the market. One field, and this analysis stops being an estimate.
4. Not the concurrency cap. Tonight it cost about $11 on one trade and saved
   about $8–34 on another; the year says lifting it is worse. It stays.
