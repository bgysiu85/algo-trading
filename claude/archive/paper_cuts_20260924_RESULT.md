# Paper cuts in the live book — descriptive pre-read (W03-0008)

Decision: Ben 2026-09-24, "Both, give-back cap on MC5" → W02-0019. Artifact: https://claude.ai/artifact/LqtwchZa8n8TcdxQiXZws2

```
ALGO TRADING - PAPER CUTS: WHERE THE SMALL LOSSES COME FROM (live paper book)
Sessions: 10 (2026-09-10 to 2026-09-23 ET). 256 round trips, 100 shares each. Source: D:\Trading\var\fills\mcl_fills_*.csv
Generated 2026-09-24 by Live analysis chat for W03-0008. DESCRIPTIVE ONLY: every cut below was chosen after seeing the trades,
so none of it is a tested rule. Negatives in brackets.

==============================================================================
IN PLAIN TERMS
==============================================================================
A 'paper cut' here = a losing trade that lost less than $40. There were 167 of them in 256 trades,
totalling (2,257.07). The 70 winners made +2,619.76 and the 19 bigger losses cost (1,477.22).
Every trade starts about $8.70 behind before the stock moves: $1.37 commission plus, on average,
$7.33 lost because stops sell below their stop price. 256 trades x $8.70 = about $2,228 - almost
exactly the paper-cut total. The paper cuts are mostly the cost of trading, paid 256 times.
So the two levers that are sure to work are: take fewer trades that have no edge, and make each exit cheaper.
Entry filters have been tried many times on this strategy line and none has passed its test.
Be clear on one thing: live, MCL and MC5 lose about the same per trade ((4.60) vs (4.25)). Running MCL only
slows the bleed because MC5 trades 2.4x as often. It does not make MCL profitable; its backtest loses
before costs too.

==============================================================================
THE SHAPE OF THE BOOK
==============================================================================
  loss $0-15        102 trades    (676.89)
  loss $15-30        52 trades  (1,145.33)
  loss $30-45        17 trades    (598.35)
  loss $45-70        11 trades    (649.18)
  loss over $70       4 trades    (664.54)
  winners            70 trades   +2,619.76   (median winner +20.63)
  TOTAL             256 trades  (1,114.53)

==============================================================================
WHAT EVERY TRADE COSTS BEFORE THE STOCK MOVES
==============================================================================
  Gross, fill to fill                        (763.00)
  Commission                                 (351.53)   ((1.37) a trade)
  Net                                      (1,114.53)
  Stops sold below their stop price        (1,876.12)   ((7.33) a trade; 195 stop exits)
  Entries vs the signal price                 +302.85   (entries are slightly BETTER than the signal on average)
  If every stop had sold at its stop price    +761.59

  Where the (1,876.13) of stop misses goes (195 trailing-stop exits):
    price already past the stop when the sell went out   (1,268.13)  median (1.75)  - fast drops, the 1-second check, retries
    the spread: the stop watches the ASK but sells at the BID  (779.00)  median (2.00)
    fill vs the bid when sent                                +171.00  median 0.00

==============================================================================
BY STRATEGY
==============================================================================
  MCL                                76 trades  net   (349.38)  per trade   (4.60)  winners  36%
  MCL - paper cuts only              43 trades  net   (649.98)  per trade  (15.12)  winners   0%
  MC5                               180 trades  net   (765.15)  per trade   (4.25)  winners  24%
  MC5 - paper cuts only             124 trades  net (1,607.09)  per trade  (12.96)  winners   0%
  MC5 is 180 of 256 trades (70%) and 124 of 167 paper cuts (74%). MC5 has been CLOSED as a candidate since
  2026-09-08 (backtest (8.57) a trade, 6,462 trades); it runs on paper only to collect fill data.

==============================================================================
THE CUTS BEN ASKED ABOUT (descriptive, chosen after seeing the trades)
==============================================================================
 Entry number, same strategy + same symbol, same day:
  entry #1                          109 trades  net   (733.69)  per trade   (6.73)  winners  30%
  entry #2                           58 trades  net    +156.33  per trade    +2.70  winners  33%
  entry #3                           31 trades  net   (327.58)  per trade  (10.57)  winners  26%
  entry #4 or later                  58 trades  net   (209.59)  per trade   (3.61)  winners  17%
 What the previous trade in that strategy + symbol did:
  first trade of the day            109 trades  net   (733.69)  per trade   (6.73)  winners  30%
  after a WIN                        39 trades  net   (255.61)  per trade   (6.55)  winners  28%
  after a LOSS                      108 trades  net   (125.23)  per trade   (1.16)  winners  24%
  -> 'Re-entering after a win' is NOT worse than a first entry in the live book. The 4th-or-later entry is the weak spot.
 Spread at entry:
  under 0.5%                        136 trades  net   (143.75)  per trade   (1.06)  winners  27%
  0.5-1%                             62 trades  net   (228.12)  per trade   (3.68)  winners  24%
  1-2%                               38 trades  net   (144.19)  per trade   (3.79)  winners  37%
  2% or wider                        20 trades  net   (598.47)  per trade  (29.92)  winners  20%
  -> 20 wide-spread entries cost (598.47). This is W03-0002's spread gate, waiting on the quote-data pull.
 How long the trade was held (a symptom, not something known at entry):
  under 1 min                        48 trades  net   (988.81)  per trade  (20.60)  winners  15%
  1-3 min                            41 trades  net   (505.29)  per trade  (12.32)  winners  20%
  3-10 min                           70 trades  net    +190.91  per trade    +2.73  winners  31%
  10-30 min                          58 trades  net   (294.72)  per trade   (5.08)  winners  19%
  30 min +                           39 trades  net    +483.38  per trade   +12.39  winners  56%
 Day's running P&L when the trade was entered:
  day at (100) or worse              95 trades  net    (13.47)  per trade   (0.14)  winners  36%
  day (100) to 0                    122 trades  net   (929.46)  per trade   (7.62)  winners  22%
  day 0 to +100                      20 trades  net     +56.50  per trade    +2.82  winners  25%
  day above +100                     19 trades  net   (228.10)  per trade  (12.01)  winners  21%

==============================================================================
WHAT HAS ALREADY BEEN TRIED ON THIS LINE (PROGRAM_INDEX)
==============================================================================
  Closed, no pass: first-entry skip, cold-session veto, range rank, chase gate, entry sweep, thin-tape volume gate,
  Running Up scanner gate, Running Up universe (0 of 18), time-of-day blocks, $5 price floor, pullback cell,
  flat daily loss stop. MCL's backtest loses before costs ((6.26) a trade gross), so a filter can only reduce a loss.
  One rule passed all its readings: the 50% session give-back cap - for MC5 only (+0.78 a trade), not MCL.

==============================================================================
WHAT TO DO, RANKED BY HOW SURE IT IS
==============================================================================
  1. Take fewer trades with no edge: run MCL only on paper (MC5 off). Removes about 70% of trades and 74% of the
     paper cuts seen so far. Costs: no more MC5 fill data. -> W02-0019 (Ben's decision).
  2. Make exits cheaper: W02-0018's replay (already approved, option A) also tests the stop watching the BID
     instead of the ASK, which is where (779.00) of spread cost comes from.
  3. Stop the wide-spread entries: W03-0002 spread gate - needs Ben's quote pull (command on its subitem 5).
  4. Cap repeat entries: W03-0008 should test 'no 4th+ entry per strategy per symbol per day' on the backtest
     book with the five readings - the live book points there, not at 'after a win'.

Items: W03-0008 (pre-read Result doc), W02-0018 (bid-trigger arm added), W02-0019 (new, Ben).
```

## Next steps
- W02-0019 — Build & test chat: give-back cap on MC5 (registered H-S4), then promotion
- W02-0018 — Build & test chat: exit replay, retry ladder + bid-based stop arm
- W03-0002 — Ben: quote pull (subitem 5), then spread gate run
- W03-0008 — Research & spec chat: register entry-count cap (no 4th+ entry) and test on backtest books
