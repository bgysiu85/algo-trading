SPY INTRADAY MOMENTUM -- DATA PASS AND THE REGISTERED STOP
==========================================================================

  Spec        claude/spy_intraday_spec_20260917.md
  Registered  docs/research/REGISTERED_spy_intraday_data.md (amendments A-L)
              claude/spy_intraday_AMENDMENT_A_20260917.md (the venue column)
  Code        954b18f

  NO P/L EXISTS. No cell has been run. No directional statistic has been
  computed -- not a hit rate, not a sign agreement, nothing. Every figure
  below is either a count, a volatility measurement, or arithmetic done
  with the PAPER'S published hit rate. Spec section 12 step 2 stops here,
  and amendment H says when.

--------------------------------------------------------------------------
1. THE DATA
--------------------------------------------------------------------------

  symbol   cached   first        last         usable   usable 2015+
  SPY       5694   2004-01-23   2026-09-16     5642     2920
  QQQ       5482   2004-12-01   2026-09-16     5427     2912
  IWM       5694   2004-01-23   2026-09-16     5643     2920

  IN THE SCORED WINDOW (2015-01-01 onward), all three checks:

  symbol   sessions-not-starting-09:30   unexplained-gaps   incomplete
  SPY                               0                  0            0
  QQQ                               4                  0            4
  IWM                               0                  0            0

  SPY and IWM are clean in the window. QQQ carries 4 anomalous sessions;
  they are excluded from its usable set and QQQ is the BREADTH CONTROL
  (spec 8.4), not a scored cell.

  Outside the window, and not in any scored cell:
    7 sessions do not start at 09:30 -- 2004-02-10, 2008-03-31, 2008-04-01,
      2008-07-03, 2008-12-24, 2009-07-27, 2013-12-23. Each is IB returning
      pre-market bars despite useRTH=True, or missing the morning. NOT a
      timestamp conversion defect: that shape hits EVERY session, as the
      planted-defect test shows (782 of 782).
    1 genuine hole -- 2004-01-29 and 2004-01-30 are absent from IB.
    QQQ history starts 2004-12-01, 213 sessions later than SPY. That is
      the 1 SHORT chunk the pull reported, and it is entirely in 2004.

  CROSS-CACHE CONTROL: the 10:00 price read from the 30-minute cache
  against the 09:59 close from the independently pulled 1-minute cache --
  5,476 sessions, maximum difference 0.0000. Two pulls, two caches, one
  number.

  DST: 46 transitions checked, all clean. Overlapping chunks: 7,744
  duplicate rows, 0 disagreeing on price. Half-days: 35, excluded and
  named. sigma1 from 1-minute bars: 5,476 sessions, no zeros.

--------------------------------------------------------------------------
2. TWO DEFECTS FOUND, BOTH IN THE CHECKS THEMSELVES
--------------------------------------------------------------------------

  Neither was a data defect. Both were alarms with nothing behind them,
  which is the worse failure: three alarms for one real defect is how the
  real one stops being read.

  cross_cache hard-coded the 09:55 bar -- the FIVE-minute convention --
  and so compared the 10:00 price against one five minutes earlier once
  the fine cache became 1-minute. It reported $4.96. Fixed: last bar
  strictly before 10:00, any bar size. Same data now reads 0.0000.

  The gap check counted calendar days and flagged three gaps. Two were the
  market being SHUT -- President Ford's day of mourning (2007-01-02) and
  Hurricane Sandy (2012-10-29/30). Fixed: it names the weekdays actually
  missing and checks them against the NYSE calendar (federal holidays as
  the exchange keeps them -- it trades Columbus Day and Veterans Day and
  closes Good Friday -- plus five unscheduled closures).

--------------------------------------------------------------------------
3. |r13| BY YEAR -- AND THE REGISTERED STOP
--------------------------------------------------------------------------

    year      n   mean|r13]%  median|r13|%
    2004    232      0.1429       0.1181
    2005    252      0.1433       0.1244
    2006    251      0.1145       0.0860
    2007    246      0.2158       0.1278
    2008    246      0.5642       0.3069
    2009    249      0.3334       0.2190
    2010    251      0.2005       0.1379
    2011    251      0.2627       0.1579
    2012    247      0.1452       0.1074
    2013    248      0.1312       0.0906
    2014    249      0.1154       0.0812
    2015    250      0.1495       0.0936
    2016    251      0.1227       0.0887
    2017    249      0.0815       0.0660
    2018    248      0.1998       0.1124
    2019    249      0.1364       0.0998
    2020    251      0.3862       0.2211
    2021    251      0.1655       0.1242
    2022    250      0.2758       0.2063
    2023    248      0.1463       0.1101
    2024    249      0.1486       0.1008
    2025    247      0.1690       0.1185
    2026    177      0.1179       0.0958

    registered scored window 2015+             0.1765%   n=2920
    replication leg 2005-2013 (amendment K)    0.2340%   n=2241
    2022+, the 0DTE era                        0.1749%   n=1171

    H-S2 gated sessions (sigma1 >= trailing p67)   0.2728%   n=971

  AMENDMENT H, registered before this number was known:
    'If the whole-window mean |r13| is below 0.18%, the study STOPS and
     section 6's table is recomputed at the measured figure before H0 runs.'

    The scored window reads 0.1765%.  THE STOP FIRES.

  The replication leg reads 0.2340% -- inside the 0.20-0.30% the spec
  assumed. The last half-hour has shrunk by about a quarter between the
  paper's era and the one being traded. That is not itself evidence the
  effect is gone; it is evidence the ARITHMETIC the study was registered
  on no longer holds.

--------------------------------------------------------------------------
4. SECTION 6 RECOMPUTED AT THE MEASURED FIGURE
--------------------------------------------------------------------------

  The hit rate below is the PAPER'S 54.37%. It has NOT been measured on
  this data and must not be -- that is the study's result, and running it
  before the re-registration is the thing amendment H exists to prevent.

  H-S1 unconditional: |r13| = 0.1765%, 252 trades/yr, gross 1.542 bps

    friction level              bps    net bps      %/yr     $/yr     fric%  b/e hit
    optimistic                0.55      0.992      2.50       245    35.7%   51.56%
    realistic (IBKR)          1.15      0.392      0.99        97    74.6%   53.26%
    pessimistic               2.50    (0.958)    (2.41)     (237)   162.1%   57.08%
    Alpaca (reported)         0.42      1.122      2.83       277    27.2%   51.19%

  H-S2 high-vol gate: |r13| = 0.2728%, 84 trades/yr, gross 2.384 bps

    friction level              bps    net bps      %/yr     $/yr     fric%  b/e hit
    optimistic                0.55      1.834      1.54       151    23.1%   51.01%
    realistic (IBKR)          1.15      1.234      1.03       101    48.2%   52.11%
    pessimistic               2.50    (0.116)    (0.10)      (10)   104.9%   54.58%
    Alpaca (reported)         0.42      1.964      1.65       161    17.6%   50.77%

  Section 6 worked from 2.65 bps gross, 1.51 net, 3.81%/yr, $373/yr.

  What actually changed is not the dollars, which the spec already argued
  were small by arithmetic. It is the MARGIN:

    friction as a share of gross    43%  registered  ->  74.6%  measured
    break-even hit rate          ~52.2%  implied     ->  53.26%  measured
    margin over the published 54.37%                     1.11 pp

  At the pessimistic level the break-even is 57.08%, which the published
  hit rate does not reach at all.

  H-S2 is the better-conditioned cell on this arithmetic: the gate does
  concentrate the move (0.2728% against 0.1765%), friction falls to 48.2% of
  gross and the margin widens to 2.26 pp -- and 84 trades/yr is inside the
  80-90 the spec predicted. Its annualised figure is small because it is
  in the market a third as often.

--------------------------------------------------------------------------
5. WHAT HAPPENS NEXT IS A DECISION, NOT A RUN
--------------------------------------------------------------------------

  Amendment H requires the study to stop here and be re-registered on the
  measured economics before H0 runs. Nothing directional has been computed
  and nothing will be until that is settled.
