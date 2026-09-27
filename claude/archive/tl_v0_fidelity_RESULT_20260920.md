AT-105 step 1 — TL-v0 Pine build + fidelity check vs Tori Trades' shown trades
2026-09-20 · Futures Trading Viability Analysis chat · NO P&L computed (by design)

SCRIPT
  TradingView: "Futures - Trend-line method" (TL-v0), own script, save 1.0 (saved by Ben)
  File: D:\Trading\Claude outputs\TL_v0.pine  (327 lines, Pine v6, indicator)
  Defaults: pivot L=R 5, ATR14, break buffer 0.10xATR, stop buffer 0.25xATR, HTF filter on (auto), sizing $100/pt (MCL)

COUNTS (NYMEX_DL:CL1!, UNADJUSTED continuous - B-ADJ off)
  timeframe  HTF  span      entries L/S   per yr  HTF-blocked  in-pos  median stop/micro  unsizeable 1% / 2% of $22k
  1D         W    43.5 yrs  69 / 86       3.6     220          35      $284               96 (62%) / 52 (34%)
  60m        4H   3.7 yrs   143 / 130     73.6    382          80      $116               44 (16%) /  7 (3%)

FIDELITY — her trade 1: "$51,843" CL short, May 2026, executed on 1H
  Hers (transcript): short 3 then +1 contract on a second break; avg entry ~$102.0 (derived: $51,850 / 4,000 bbl + $89.07);
                     stops logged 105.51 / 104.85; safety line = higher-TF downtrend line; held through 2 pullbacks;
                     exit 89.07 Thu 2026-05-28, discretionary (86.85 resistance + ceasefire news).
  TL-v0 on 60m (NY time):
    2026-05-15 12:00  LONG 100.92  stop 96.96
    2026-05-19 14:00  exit long 103.28          <- support break while long: opposite signal ignored (v0 rule)
    2026-05-21 14:00  SHORT 96.34  stop 100.49 ($415/micro: 0 @1%, 1 @2%)
    2026-05-26 03:00  exit short 92.92          <- nearest line hit; she held (her line was the HTF line)
    2026-05-28 11:00  SHORT 89.51  stop 92.80
    2026-05-29 10:00  exit short 88.63
  Direction: match. Entry within 1-2 bars: NO (~2 days late, ~$5.7/bbl below her entry). Exit: earlier, different reason.
  Fidelity on the registered criterion: 0 / 1.

FIDELITY — her trade 2: "This boring trading strategy made me $526,454"
  Not checkable: the walkthrough is Bitcoin at 78,015 with no dated fill; the $629 micro-crude example is not dated.

WHERE v0 DIFFERS FROM HOW SHE DRAWS/TRADES (from the two transcripts)
  1. She reverses on the break; v0 ignores opposite breaks while in a position.
  2. Her safety line on this trade was the higher-timeframe line (wide); v0 trails the nearest line.
  3. Lines: she chains them ("previous point B is new point A") and maximises touch points without closes through;
     v0 uses the two latest confirmed pivots.
  4. She pyramids on a second break (3 -> 4 contracts); v0 takes one position.
  5. Exit was discretionary (S/R + news) — not codeable, excluded by design.

CAVEATS
  n = 1 checkable trade. Unadjusted continuous series (roll gaps can create fake breaks). Daily history includes decades at
  far lower prices, so the daily stop/sizing numbers are not today's; step 2 pre-flight on the owned GLBX bars is the proper
  measurement. Label reads cap at the 500 most recent labels (the 60m set spans 2023-05 -> 2026-09).
