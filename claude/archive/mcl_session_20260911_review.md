# Session review — 2026-09-11, and what it says about today's research

Paper session, 04:00:08 → 09:30:02 ET. 109 order rows, 96 filled, 48 round trips.
Source `var/fills/mcl_fills_20260911.csv`, watchlist
`var/archive/watchlist_20260911.txt`.

## 1. The session

    MC5    43 trades   (203.03)   win 14.0%   avg win 34.79   avg loss (11.13)   hold 2.1m
    MCL     5 trades     +46.12   win 60.0%   avg win 21.62   avg loss  (9.38)   hold 24.3m
    TOTAL  48 trades   (156.91)

Better than 2026-09-10's (224.18). Five symbols all session — ACVA, FTFT, LBGJ,
TNON, XRTX — with TNON carrying 24 of the 48 round trips and (63.99) of the loss.

Watchlist: 8 names, **2 refused outright by IBKR** (PCLA, SXTC — "closing-only
status"), leaving 6 tradeable.

## 2. The running live record — the only look-ahead-free evidence here

| Date | Trades | Net | MCL | MC5 | Cap rejects |
|---|---:|---:|---:|---:|---:|
| 2026-09-02 | 2 | (1.00) | — | — | 0/6 |
| 2026-09-03 | 19 | (163.60) | — | — | 0/19 |
| 2026-09-08 | 2 | (63.74) | — | — | 0/2 |
| 2026-09-09 | 6 | (70.26) | (70.26) | — | 3/9 |
| 2026-09-10 | 22 | (224.18) | (57.24) | (166.94) | 30/62 |
| 2026-09-11 | 48 | (156.91) | **+46.12** | (203.03) | 13/61 |
| **Total** | **99** | **(679.69)** | | | **46/159** |

    MCL   n=17   (81.38)   (4.79)/trade   win 47.1%   R 0.72   needed 1.12
    MC5   n=59  (369.97)   (6.27)/trade   win 11.9%   R 2.71   needed 7.43

## 3. The live record disagrees with today's headline finding

`pit_three_results_20260911.md` §3 concluded from the point-in-time backtest
that **R is fine and the win rate is the defect**. The live record says the
opposite:

| | Win rate | R | R needed |
|---|---:|---:|---:|
| Published, stage-2 universe | 48.7% | 0.58 | 1.05 |
| **MCL live, n=17** | **47.1%** | **0.72** | **1.12** |
| MCL point-in-time backtest, n=2,682 | 21.7% | 1.67 | 3.62 |

**Live looks like the stage-2 shape, not the point-in-time shape**, and it is
the one number here with no look-ahead in it at all.

The obvious escape — that the live watchlist used a different screen — does not
hold. All 17 MCL live trades come from sessions 2026-09-09 onward, which use the
automated `tv_feed` watchlist built from the shipped `FILTERS` the simulation
imports. Same screen specification; different tape, and reality.

So one of these is wrong about the shape of the deficit, and it is not obvious
which. **n=17 is nothing.** But `pit_three_results` §3's line *"this inverts
`win_rate_and_r.md` §2"* is now overstated and should be read as *"the
point-in-time simulation disagrees with both the published figures and the live
record, and that disagreement is itself a finding."*

## 4. The simulation has never been checked against the live screen

`screen_sim`'s only gate was internal — the fast path against `screen_at`, 0
disagreements. That verifies the implementation against itself. It has never
been compared to what TradingView actually surfaced.

The two dates where both exist:

    2026-09-02   live 6 names   sim 7   found 4   missed UPC, KIDZ
                                        sim-only BRNX, EOSU, PSNYW
    2026-09-03   live 7 names   sim 5   found 2   missed TLYS, MIMI, GYGY, NYXH, DLTH
                                        sim-only AEHL, DAIC, DBGI

    6 of 13 = 46%

**This is not a clean test and must not be quoted as one.** Those two watchlists
were hand-synced from TradingView under a *different* screen — their own headers
say "RVOL(1D) >= 5x, float < 20m, top-2 pre-market gainer" — and neither the
float nor the RVOL clause exists in the shipped `FILTERS` the simulation
reproduces. Roughly half disagreement is what two different screens should
produce.

What it does establish is that **the check has never been run**, and the data to
run it properly does not exist yet: every automated `tv_feed` session (09-08
onward) falls past the Databento archive's end at **2026-09-04**.

**Extending the archive past 2026-09-04 is the fix**, and it is cheap next to
what it settles: every point-in-time figure produced today rests on a universe
whose agreement with the live screen is unmeasured.

## 5. Two execution gaps no backtest models

**The concurrency cap rejected 29% of buy attempts** — 46 of 159 across all
sessions, 13 of 61 today, 30 of 62 yesterday. Every backtest takes every signal.
Which signals get dropped is decided by arrival order, not by quality. Today's
rejects arrived in bursts: six consecutive minutes 07:51–07:56, five more
08:46–08:50, 11 of 13 from MC5.

**IBKR refuses some screened names outright.** 2 of today's 8 (25%), both
"closing-only status". A name on the watchlist is not necessarily a name that
can be bought.

## 6. The exit mechanic decides the friction

Today's sell-side slippage against reference, per share:

    trailing_stop        n=36   median (0.0563)   mean (0.0750)
    gradient_reversal    n=11   median  0.0000    mean (0.0065)
    window_close         n= 1   median (0.0100)

**A signal-based exit fills at the reference; a stop fills through it.** This is
a direct, independent confirmation of `stop_fill_20260911.md` — and it connects
to the MFE result, where **2,400 of MCL's 2,682 point-in-time exits are trailing
stops**. Changing the exit mechanic has a friction benefit separate from
anything it does to the P&L path.

Round-trip slippage today: BUY +0.0416, SELL (0.0580), **net (0.0164)/share =
$1.64 per 100-share round trip** — well below both the shipped $4.26 and the
$8.92 central case. The SELL leg (0.0580) is almost identical to the 2026-09-03
measurement (0.0590); the difference is entirely that buys filled favourably.
One session, and the friction question stays open.

Other execution facts: median time to fill **0.52s** (p90 1.41s); median spread
at order **0.404%** (p90 0.971%).

## 7. What to do about it

1. **Extend the Databento archive past 2026-09-04** so the simulated screen can
   be checked against the automated watchlists. This now outranks the exit queue
   — every point-in-time figure depends on it.
2. **Model the concurrency cap** in the backtests, or state on every figure that
   29% of live signals never become trades.
3. Pull back `pit_three_results` §3's inversion claim to a disagreement.
