# REGISTERED — BREIT-CAP: Lance Breitstein's capitulation reversal (1-bar Donchian), coded, on CME futures

**Committed before any BREIT-CAP code exists and before any bar of any market has been read by this
study.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0022** (registration), subitem 5 (build + count-only pre-flight), later subitems
(backtest, Result doc). Source: Chart Fanatics video `_qeFh1ADss8` (91 min), read in full
2026-09-29. Extract with quotes, timestamps and STATED/VAGUE tags:
`claude/raw/w15_0022_breitstein_extract_20260929.txt`. First screened in
`claude/w05_0020_chart_fanatics_review_RESULT_20260927.md` (option C).

Ben's decision, 2026-09-29, in his words: *"12 mkts daily + CL 4H"*, both sides: long after
capitulation lows, short after blow-off tops.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result
is a new hypothesis and spends from §9.

---

## 0. Where this sits

- **New line, new budget.** Mechanically this is the mirror image of the program's Donchian 20/10
  control: a 1-bar channel break *against* an extreme run, rather than a 20-bar break *with* a trend.
- **What is his and what is ours.** Breitstein is discretionary and says so ("if you're trying to
  just strictly memorize if X do Y, it's never going to work"; "I have no mental rubric"). The parts
  he states firmly are the ones he calls codable himself, including a scanner built on them (1:30:00):
  - a run that keeps **"holding prior bar highs"**;
  - a **buy-stop at the prior bar's high** ("put that order in the market above that daily high");
  - a **stop at the low of the move**;
  - a **trail on the prior bar's low**;
  - the short side as a mirror, **traded smaller**;
  - **any timeframe, daily explicitly**.

  Size, speed, legs and volume are, in his words, "on a spectrum", with no numbers given. Every
  threshold below that is marked **(choice)** is our coding, fixed here before any data is read.
- **Factors he names that cannot be coded from price data are dropped:** news, forced flows,
  sentiment, liquidity (liquidity is roughly constant across these 12 markets anyway).
- **Scope extension, stated plainly.** His examples are stocks and Bitcoin. Futures are never
  mentioned, and neither is crude. He does say boring, liquid, diversified underlyings (index,
  bonds, currencies) suit it best, and that is qualitative support for this universe, not evidence.
- **What has been seen:** only the video. No bar has been read.

---

## 1. The hypothesis, in one sentence

**After an extreme run of at least four bars, each holding the prior bar's high, that has dropped at
least 3 ATR and closed below the lower Bollinger band — or the mirror, for an up-run — buying the
first break of the prior bar's high, with a stop at the low of the move and a trail on each prior
bar's low, sized up with the setup's grade and traded at half size on the short side, makes money
after measured costs on the owned GLBX daily history of the TSMOM markets; beats a 20/10 Donchian
channel; beats the same 1-bar reversal taken after *any* 4-bar run (no capitulation filter); and
beats random entries with the same exits.**

---

## 2. The rules

### 2.1 Program plumbing — inherited unchanged (as TL-v0 / TL-v1)

These are identical to TL-v1 and CRUDELE-3S §2.1:
- **Execution chart and markets.** Daily bars; the TSMOM archive roots (ES, RTY, CL, NG, 6A, 6B,
  6E, 6J, GC, SI, HG, MTN).
- **Price series.** Signals on the difference-back-adjusted series; P&L on the held contract under
  the TSMOM roll rule, including Amendment C.
- **Indicators.** ATR(14) Wilder.
- **Fills.** At the level, or at the open if price gaps through it; a stop that is hit in the same
  bar as the entry counts as hit.
- **Costs.** Friction **$0.50 / $1.25 / $2.50** per contract per side, plus one tick on every stop
  fill.
- **Book.** Verdict read on the fractional book at **$22,129**; the integer book is reported.
  Zero contracts means the trade is skipped, and each skip is counted.
- **Positions.** One per market at a time. A run that sets up while a position is open is counted
  but not taken.

### 2.2 The qualifying run (long setup — short is the mirror throughout)

All evaluated at the close of bar t, from bars ≤ t.

| # | Rule | Source |
|---|---|---|
| **Q1 Run** | k consecutive bars ending at t, each with high[i] ≤ high[i−1] ("holding prior bar highs"), **k ≥ 4**. Run origin O = the bar before the run's first bar | **STATED** (4–9 bars in his examples; "four five six days" for his rare A setups); ≥ 4 is our choice |
| **Q2 Size** | Drop D = high[O] − min(low over the run) ≥ **3.0 × ATR[O]** (ATR measured at the origin, before the move inflates it) | "multiple average trading ranges", with no number given; 3.0 is our choice |
| **Q3 Stretch** | At least one close in the run is below the **lower Bollinger band (20, 2.0)** | **STATED** as his scan ("closes below Bollinger Band"); the 2.0 SD setting is our choice (default) |

A run that meets Q1–Q3 is **qualified**. It stays qualified while it keeps holding prior bar highs.

### 2.3 The grade and the size

He scores variables 0–10 and sums them into tiers, and says size grows "exponentially" with grade;
the numbers he gives are illustrative. We code **five yes/no factors**, measured on the qualified
run at the moment of entry:

| Factor | Yes when | Source |
|---|---|---|
| G-speed | The largest true range of the last 2 run bars ≥ **1.5 × ATR[O]** | "rate of change is one of the most important"; the waterfall |
| G-legs | **≥ 3 down-legs** from the 60-bar high to the run low, counted with a zigzag that uses a **1.0 × ATR** reversal (a leg ends when price bounces ≥ 1 ATR off its low) | "three legs or more" (STATED); the zigzag is our choice |
| G-volume | The highest held-contract volume among the last 3 run bars ≥ **2.0 ×** its 20-bar average | "one of the major ways I define capitulation" (STATED); 2.0 is our choice |
| G-boring | ATR[O] ÷ held-contract price is at or below that market's own median over the prior **250** bars | "something that's normally boring makes an exceptionally large move" |
| G-long-run | k ≥ **6** | "four five six days in a row" |

**Grade = count of yes (0–5). Risk: grade 0–1 → 0.5%; 2–3 → 1.0%; 4–5 → 2.0%. Short side: half
the long-side risk.** These multiples are our coding of "exponential bet sizing" and "way less on
the short side". A flat-1% book is reported beside the graded one (§2.6).

### 2.4 Entry, stop, trail

- **Entry:** at each close where a qualified run is intact, place a **buy-stop at high[t] + 1 tick**
  for bar t + 1. Fill at max(open, stop) plus slippage, as the plumbing sets it. If bar t + 1 does
  not trade above high[t], it has held the prior bar's high, so the run extends by one bar and the
  stop moves to high[t + 1]. **STATED**: "that break is going to be what signifies that break of
  trend"; "the prior day's bar is already defined."
- **Initial stop:** the **lowest low of the run − 1 tick**, known as "the lows of the move"
  (**STATED**). If the entry bar itself trades below that level, the trade counts as stopped in the
  same bar, the conservative reading.
- **Trail:** from the **first bar after the entry bar**, stop = max(current stop, low of the prior
  bar − 1 tick). The stop never loosens. **STATED**: "I just trailed it prior bar lows." Starting
  the trail after the entry bar is our choice; he says the risk "past this first initial day…
  starts to trail".
- **Target:** none. The trade exits on the trail (**STATED**, his practice). The 50% retrace and the
  20-period MA "rough target" are reported variants (§2.6).
- **Re-entry:** allowed on a *new* qualified run after exit. This matches his Bitcoin re-entry.

### 2.5 Books

| Book | Status |
|---|---|
| **Daily, 12 markets, both sides, graded sizing** | **Primary: the §4 verdict and the holdout spend** |
| **CL 4-hour**, both sides, graded sizing: CL only, 4-hour bars from `ohlcv-1h` on the 18:00 New York session (as `REGISTERED_tl_bounce.md` §2.1), the same rules in bars; costs as HTF-Ben v0 Amendment A, per 1 MCL | **Secondary**, Ben's pick: scored on the same §4 criteria (criteria 3 and 7 read by year only, since there is one market). It may spend its own holdout only if it passes, and it is reported together with the primary, never instead of it |

### 2.6 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| Long only / short only | One side switched off | Whether his long-side preference ("$0 floor") shows up |
| Flat 1% | No grade sizing | Whether grading adds anything over plain entries |
| Grade ≥ 2 only | Grades 0–1 skipped | His "no trade" tier |
| + 50% target | Limit at low + 0.5 × D (whole move, origin high to run low) | His "base case" |
| + MA target | Limit at SMA(20) (the Bollinger middle band), current when each bar opens | His "equilibrium" |
| Q1 k ≥ 5 | Stricter run | Selectivity |

**Known departures, not coded:** intra-bar and front-side entries in extreme panics; a daily chart
checked against an intraday trigger; news, forced flows, sentiment and liquidity; discretionary
"audibles" on stops; scaling out.

---

## 3. What every run must emit

In dollars and actual trades, for both books and every variant, at all three friction levels, mid as
the headline:

1. Trades, wins/losses, gross, costs, net, average win, average loss, largest loss and worst losing
   streak, for the fractional (verdict) and integer books.
2. Results per market, per calendar year, and for each half split at the median entry date.
3. **Results by side and by grade (0–5):** trades, win rate, net, and average R (R = the initial
   risk).
4. Exit reasons (initial stop / trailed stop / same-bar stop / data end), median hold in bars, and
   the share of trades exiting within 1 bar.
5. **Counts:** qualified runs, runs failing Q2 and Q3, runs set up while a position was open,
   entries, skipped for size; the distribution of run length k and of D/ATR.
6. **Controls, on the same markets, bars, sizing, costs and exits (§2.4 stop and trail):**
   - **C1:** Donchian 20/10 (as TL-v0).
   - **C2 — the unfiltered reversal:** the same entry/stop/trail after **any** Q1 run (k ≥ 4, no
     Q2/Q3), flat 1% risk. This answers whether the capitulation filter matters.
   - **C3 — random entries:** the same count per market and year and the same side mix as
     BREIT-CAP, on random bars; stop at the lowest low (highest high for shorts) of the prior k bars,
     where k is drawn from BREIT-CAP's own run lengths; same trail. 1,000 seeded draws (crc32 of
     draw number); p5 / p50 / p95 of net.
7. **Neighbour grid (27 cells, unranked):** Q2 size {2.0, 3.0, 4.0} × ATR × Q1 k {3, 4, 5} × Q3
   band {1.5, 2.0, 2.5} SD. Net at mid friction per cell and the share positive.
8. **20 sample trades** (every 1/20th): run start, k, D/ATR, grade, fill, stop, exit, net $.
9. **Seen window** (2025-09-23 → end of data), labelled "seen — not evidence".

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — BREIT-CAP primary (daily, 12 markets, graded), mid friction, training side

Passes only if all hold:

1. Net > $0 at mid friction.
2. Both halves net > $0.
3. Drop-top-1 and drop-top-2 by market still > $0.
4. Bootstrap by market and by calendar year (2,000 seeded resamples each): net > 0 in ≥ 95% of
   resamples, for each.
5. **Beats C1 (Donchian)** on net and on net per unit of realised volatility.
6. **Beats C2 (the unfiltered reversal) on net per trade (R-normalised)**, and **beats the p95 of C3**
   on net.
7. No single year and no single market supplies more than 50% of net.
8. Still net > $0 at high friction.
9. At least **18 of 27** neighbour cells net > $0.
10. At least **150 trades**. Fewer means NOT READ, not failed.

**Failing 5 or 6 closes the study whatever else passes.**

---

## 5. Before the backtest — no P&L in this section

### 5.1 Gates

| # | Gate |
|---|---|
| G1 | **Data:** the TL-v0 daily archive and CL 1-hour (both passed before). **Plus a new check:** held-contract daily **volume** is present and non-zero on ≥ 99% of training bars per market. If it fails for a market, that market's G-volume is scored "no" throughout, and this is written in here as a PRE-RUN amendment before G2 |
| G2 | **Pre-flight** (5.2), run and read |
| G3 | **Holdouts** (§6): cut files and ledgers in code, mutation-tested |
| G4 | **Look-ahead guards**, each broken by a one-bar shift in a test: the run, Q2, Q3 and every grade factor use bars ≤ t; ATR[O] is fixed at the origin; the entry stop for t + 1 uses high[t] only; the trail uses only completed bars; the zigzag uses only confirmed legs |
| G5 | **Order-of-events tests** on synthetic bars: a gap through the buy-stop; an entry bar that also breaks the run low; the trail starting on the bar after entry; a mirror short |

### 5.2 G2 pre-flight (training side only: 2010-06 → 2021-12)

Report, per market per year and per side: Q1 runs, runs failing Q2 and Q3, qualified runs, entries,
the grade distribution, the k and D/ATR distributions, the initial stop distance in $ per micro
(else per full contract), and the share sizeable at each risk tier on $22,129. Report the same for
CL 4H. **No exit price is read and no P&L is computed; the runner refuses both in this mode.**

**Stop rules, fixed now:**
- Fewer than **150 primary entries** → stop as underpowered, report that as the finding, and go
  back to Ben before any P&L.
- If CL 4H has fewer than 150 entries, it is **demoted to reported-only** (not scored) and the
  primary continues.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31.
- **Holdout:** 2022-01-03 → 2025-09-22, with its own cut files and ledgers:
  **`holdout_breit_cap.json`** (primary) and **`holdout_breit_cap_cl4h.json`** (secondary).
- **Spending rules.** Each holdout is spent once, and only by a book that passed §4 on training.
  The code refuses `--limit` and every narrowing flag (mutation-tested), and every other line's
  holdout file is refused by name.
- **Seen window:** 2025-09-23 onward. Reported only, never scored.

---

## 7. Registered as NOT to be done

- Tuning k, the ATR multiples, the band SD, the zigzag reversal, the volume multiple, the grade tiers
  or the side discount to a result.
- Adding a target, time stop, news filter or intra-bar entry after a result.
- Swapping a variant (long only, a target variant, flat sizing) in for the primary after a result.
- Quoting gross, one side, one market or CL 4H alone as the headline.

---

## 8. Ways this could go wrong

- **Too few trades.** A 4-bar run of lower highs with a 3-ATR drop and a close outside the 2 SD band
  may be rare on daily futures. The G2 stop rule decides that before any P&L is seen.
- **A prior-bar-low trail on daily bars is tight.** Many trades may exit within 1–2 bars for about
  1R or less. That is his method on daily charts; the two target variants show the alternative.
- **The short side on commodities.** Blow-off tops in NG, SI and CL can run much further than a
  prior-bar-high trail allows. Half-size limits the damage; the side split in §3 shows it.
- **His grade is a mental tally.** Five yes/no factors test *a* coding of it. The flat-1% variant
  shows whether the coding adds anything.
- **Roll gaps can fake a run or a break.** The existing roll-leg guards apply unchanged.
- **His examples are hand-picked** (stocks, Bitcoin), and his 70–80% win rates are his own estimates.

---

## 9. Multiplicity budget

- **Families:** one fixed rule set with two scored books (primary plus the CL 4H secondary; both are
  reported together, and neither is chosen over the other on a result), plus variants (reported),
  the grid (robustness only) and friction (not a search).
- **Holdout spends:** at most two, one per book.
- **Further hypotheses:** two more registered hypotheses are allowed on this line; a third needs a
  reason that does not begin with a result.

---

## 10. A prediction, written down now

**Roughly 250–600 primary entries.** The long side on ES, RTY and MTN is net positive, with win
rates of 50–60% and small average R. The short side loses money, most of it in NG and SI. The
combined book is slightly positive at low friction, near zero at mid friction, and does not beat the
p95 of C3 (criterion 6), because the prior-bar-low trail takes about 1R on most trades whatever the
entry. It does beat C2, which means the capitulation filter matters, but not by enough. CL 4H is too
noisy to read. If that happens, the reading is: *on daily futures, the capitulation long is real but
small, and the size of his edge comes from intraday and intra-bar entries and discretion, none of
which is in the rules.* I'd be glad to be wrong.

---

## 11. For Ben's review before build (the choices that matter most)

1. **A qualifying run is at least 4 bars holding prior bar highs, with a drop of at least 3 × ATR
   from the origin, and a close below the lower 2 SD Bollinger band.**
2. **Grade uses 5 yes/no factors (speed, 3+ legs, volume spike, boring market, 6+ bars), with risk
   of 0.5% / 1% / 2% by grade band and half size on shorts.**
3. **Exit is the prior-bar-low trail only, with no target.** The alternative is to make his 50%
   retrace the primary exit; both target variants are reported either way.
4. **CL 4H is a scored secondary book** that can spend its own holdout. The alternative is
   reported-only, like TL-v1's 4-hour variant.

---

## Next steps (board, W15-0022)

- **Subitem 4:** Ben reviews §11 here and in CRUDELE-3S → says "go", or changes are written in as
  PRE-RUN amendments.
- **Subitem 5:** Build: run and grade code, entry/stop/trail, controls C1–C3, grid, guards,
  holdouts, and the count-only pre-flight for both methods. Build & test chat, Sonnet · High; runs
  on Ben's PC.
- **Backtest and Result doc:** new items once G2 has been read.

### Amendment — PRE-RUN, 2026-09-29 (readings made while coding; before any pre-flight or P&L is read)
1. Zigzag leg counting uses ATR[O] (the registered ATR) as its threshold.
2. Sizing: the grade sets risk 0.5/1/2%; shorts are half size; the flat-1% variant ignores grade on both sides.
3. A profit target that lies on the wrong side of the fill is dropped (the trade runs on stop/trail only).
4. The trail (prior-bar low/high) is applied at every close including the entry bar; a same-bar stop is taken at the stop.
5. Volume coverage (G1) is scored on held-contract volume > 0 over training bars; a market below 99% has G-volume scored "no" throughout, via a committed amendment before the run (runner exit code 3 otherwise).

### Amendment B — PRE-RUN, 2026-09-30 (W15-0033 cost basis; W15-0034 report readings; before any P&L is read)

Reason: Ben's instruction to use IBKR costs, and the wording of §4 that admits more than one reading. Neither follows a result: the G2 pre-flight read no exit price and no P&L (791 daily primary entries; every market passes the 99% volume check).

**Costs — IBKR (W15-0033), replacing the flat $0.50 / $1.25 / $2.50 per side.** Ben, 2026-09-30: *"please use the IBKR costs as that will be the broker i'm using"*; levels chosen by Ben (multiple choice, same day): **fee + 0 / 1 / 2 ticks per side**. Per contract per side, all-in = IBKR Pro commission (Fixed, or Tiered ≤ 1,000 contracts a month) + exchange fee (non-member) + regulatory ≈ $0.02, read 2026-09-30 from interactivebrokers.com (`/en/pricing/commissions-futures.php`, `/en/accounts/fees/{CME,CBOT,COMEX,NYMEX}.php`):

| Vehicle | Commission | Exchange | All-in / side | Tick $ | low / mid / high per side |
|---|---|---|---|---|---|
| MES (ES) | 0.25 | 0.353 | **0.62** | 1.25 | 0.62 / 1.87 / 3.12 |
| M2K (RTY) | 0.25 | 0.353 | **0.62** | 0.50 | 0.62 / 1.12 / 1.62 |
| MCL (CL; also CL 4H) | 0.25 | 0.50 | **0.77** | 1.00 | 0.77 / 1.77 / 2.77 |
| NG (full) | 0.85 | 1.60 | **2.47** | 10.00 | 2.47 / 12.47 / 22.47 |
| M6A, M6E, M6B | 0.25 | 0.24 | **0.51** | 1.00 / 1.25 / 0.625 | 0.51 / 1.51 / 2.51; 0.51 / 1.76 / 3.01; 0.51 / 1.135 / 1.76 |
| 6J (full) | 0.85 | 1.60 | **2.47** | 6.25 | 2.47 / 8.72 / 14.97 |
| MGC (GC) | 0.25 | 0.70 | **0.97** | 1.00 | 0.97 / 1.97 / 2.97 |
| SIL (SI) | 0.25 | 0.70 **(assumed)** | **0.97** | 5.00 | 0.97 / 5.97 / 10.97 |
| MHG (HG) | 0.25 | 0.70 | **0.97** | 1.25 | 0.97 / 2.22 / 3.47 |
| MTN | 0.25 | 0.30 | **0.57** | 1.5625 | 0.57 / 2.13 / 3.69 |

SIL is not on IBKR's COMEX fee page; its exchange fee is assumed equal to the other COMEX micros (flagged in every report). Slippage is inside the mid and high levels on **every** fill, so the old separate "1 tick on stop fills" is dropped (no double count). Roll legs: two sides per contract, as before. MCL round trip $1.54 / $3.54 / $5.54, as the CHARTMARK registrations. Wherever this file says "$1.25 / side" (mid) or "$2.50 / side" (high) it now means these levels. Code: `strategy/futbt/costs_ibkr.py`. **PRE-RUN check (G5):** if Ben's first IBKR futures fills show a different all-in fee, it is amended here before any P&L is read.

**Coding notes for §4 wording (fixed now, before any P&L):** criterion 2 splits at the median ENTRY date of the verdict book's trades (each half = sum of net at mid of the trades that entered in it; an empty half fails); criterion 4 uses TL-v0's `cluster_boot` (2,000 resamples, seed 20260927); criterion 5 is net AND net per unit of realised volatility (TL-v0's measure); criterion 7 is NOT READ when net ≤ 0; criterion 9 counts grid cells with net > $0 at mid (the grid is the fractional book at $22,129); criterion 10 NOT READ under 150 trades. The report layer is `strategy/futbt/report_common.py`; the backtest runners are `strategy.crudele_3s.backtest` and `strategy.breit_cap.backtest` (training side only; `--holdout`, `--limit`, `--seen`, `--spend` are refused).

**BREIT-CAP-specific:** criterion 6 part one, "beats C2 on net per trade (R-normalised)", is coded as average R per trade = mean of net at mid ÷ (risk fraction × $22,129) on the fractional book; BREIT-CAP's average R must exceed C2's (the unfiltered reversal at flat 1%). Part two: net at mid above the p95 of C3's 1,000 draws. Both must hold. **CL 4H (scored secondary):** one market, so criteria 3, 4 and 7 are read by calendar year (drop the top 1 and top 2 years; bootstrap by year; no year above 50%); its own C1, C2, C3 (random draws on the 4H bars) and 27-cell grid; priced as one MCL; daily P&L for the volatility measure is summed per 18:00-New-York session. If the CL 1-hour file is not found, CL 4H is "not evaluated" and the daily primary runs alone.
