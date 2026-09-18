# REGISTERED — ORB on liquid "Stocks in Play", out of sample

2026-09-18, **PRE-RUN**. No P/L exists for this strategy on any universe. The data
(XNAS.BASIC `ohlcv-1m`, 09:30–16:00, all symbols, 2024-07-01 → 2026-09-16, 555
sessions, 34 GB) is on disk and has not been read by any strategy code. This
document is committed before the runner exists; git's ordering is the claim.

Parents: `claude/orb_sip_preflight_20260917.md` (tape choice, measured),
`claude/orb_pit_RESULT_20260917.md` (why the small-cap ORB line is closed),
`PROGRAM_INDEX.md` §1 and §4. Where this document and §4 disagree, §4 wins and
this file is the bug.

---

## 1. What is being tested, and why it is worth a test

Zarattini, Barbon & Aziz, *A Profitable Day Trading Strategy for the U.S. Equity
Market* (SSRN 4729284), full paper read. On ~7,000 US stocks, 2016-01-01 →
2023-12-31, a 5-minute opening-range breakout on the **top 20 stocks by
opening-range relative volume** returned 1,637% (IRR 41.6%, Sharpe 2.81, MDD
12%), against the same trigger on all qualifying stocks at IRR 3.2% / Sharpe
0.48. **The selection rule, not the breakout, carries the whole claimed edge**
(`largecap_evidence_20260911.md` §1.5).

Three reasons this is the strongest design this project has had:

1. **Our sample starts after theirs ends.** 2024-07 → 2026-09 is out of sample
   for the published rule. Nothing here was fitted by us.
2. **The rules are published in full** — filters, ranking, stop, exit, sizing —
   so there is nothing for us to choose and therefore nothing to overfit.
3. **Costs are an order of magnitude smaller than on small caps** ($4–9 per
   100-share round trip there; a cent or two of spread here).

And one reason to expect failure: **the paper charges $0.0035/share commission
and nothing else** — no spread, no slippage, no impact — while its stop sits
**10% of ATR** from entry, which is $0.05–$0.30 on these names. Two cents of
round-trip friction is a material fraction of the risk taken.

---

## 2. The rules, as published. Nothing here is ours.

**Universe, per session, from data knowable before 09:35 ET:**
- the session's 09:30 open **> $5.00**;
- average daily volume over the **prior 14 sessions ≥ 1,000,000 shares**;
- **ATR(14) > $0.50** over the prior 14 sessions.

**Selection:** `RVOL = OR volume today / mean(OR volume, prior 14 sessions)`,
where OR volume is the stock's volume in the opening range. **RVOL ≥ 1.00**, then
the **top 20 by RVOL**. Ties broken by symbol, ascending, so the tie rule cannot
be a choice made later.

**Direction and entry:** the opening-range candle decides. Close > open → a buy
stop at the range **high**. Close < open → a sell stop at the range **low**.
**Open == close (doji) → no order.** One entry per symbol-day; the order is live
until 15:59.

**Stop:** **10% × ATR(14)** from the executed entry price.

**Exit:** the stop, or the **15:59 bar's close** (the last minute our data
holds; the paper says 16:00).

**Range length:** **5 minutes is the primary.** 15 minutes is a registered
secondary (§5). 30 and 60 are not run: the paper reports them at Sharpe 0.21 and
0.40, and running them would buy multiplicity for nothing.

---

## 3. What we must supply, because the paper does not

Each of these is a decision, made now, once.

**3.1 Tape.** XNAS.BASIC minute bars (measured in the pre-flight: daily-RVOL
rank correlation 0.95 against consolidated volume, top-20 overlap 16 of 20;
ITCH and MINI overlap 12). Daily volume for the liquidity filter from
**EQUS.SUMMARY** (consolidated). ATR(14) from **BASIC's own RTH minute bars**
(daily bars include extended hours, which would widen every stop —
`prior_close_defect_CONFIRMED_20260912.md`). A report that cannot name its tape
is refused, as in `strategy/orb/grid.py`.

**3.2 Fill model**, identical in shape to ORB's §9 and not re-derived:
- an entry stop **gaps through**: if the next bar opens beyond the trigger, the
  fill is that open; otherwise the fill is the trigger price;
- **the stop-loss gaps through too**, and a bar holding both the stop and the
  15:59 close belongs to the stop;
- the trigger can first fire on the bar **after** the opening range closes;
- slippage and commission per §3.3, charged on both legs.

**3.3 Friction — three levels, reported side by side.** §4's standing rule.
| level | entry | stop exit | close exit | commission |
|---|---|---|---|---|
| **PAPER** | 0¢ | 0¢ | 0¢ | $0.0035/share |
| **BASE** (the one the criteria are read at) | 1¢ | 2¢ | 1¢ | IBKR tiered |
| **HARSH** | 2¢ | 4¢ | 2¢ | IBKR tiered |
A stop fills through the level and a signal exit fills at it
(`execution_cost_measured.md`), which is why the stop leg is charged double.

**3.4 Sizing.** Two books from one trade list:
- **flat 100 shares** — the project's unit of account, comparable to every other
  strategy here, and what the §11 criteria are read on;
- **the paper's book** — $25,000 start, 1% of capital risked per position, 4×
  leverage cap, at most 20 positions, equal-weight cap per position. Reported
  for comparability with the paper, never used to pass a criterion.

**3.5 The price band.** `PROGRAM_INDEX` §1 mandates $2–20 at entry. That rule
exists because IB history is split-adjusted and VW9 once traded a $4,152
"price". This universe is the opposite by construction (raw Databento prices,
liquid names above $5), so the band is replaced **for this strategy only** by:
a **$5.00 floor** (the paper's) and an **adjustment-artefact guard** — a
symbol-day is refused if its 09:30 open is not within 0.2×–5× of its prior
session's close. The guard is a rule, not a filter on returns, and it is counted
in the report.

**3.6 Halts.** `PROGRAM_INDEX` §7 item 24: 36.4% of Tier 2 LULD pauses fall
09:45–09:50, and ORB enters near the open. The `status` schema is not in the
archive, so a halt is not modelled. A halted name shows as a minute gap; the
report counts symbol-days with a gap of ≥ 5 minutes inside the session and
states their share of trades, so the exposure is measured rather than assumed.

---

## 4. How it is read

**§11 criteria, on the primary cell (5 minutes, top 20, BASE friction, flat
100), and nowhere else:**
1. drop-top-3 and drop-top-5 by **symbol** both > 0;
2. symbol-cluster bootstrap P(total > 0) ≥ 0.95 — `common/breadth.py`, same seed
   and resamples as everything else here;
3. **per trade ≥ $1.00** (1¢/share at 100 shares), with per **symbol-day**
   reported beside it; a sign disagreement between the two denominators in any
   comparison is a refusal, not a tie;
4. trades ≥ 100;
5. both halves > 0, split at the **median session date of the sample**, derived
   once and never swept;
6. **both sides > 0** — long and short arms reported and both positive. This
   replaces ORB's §10.2 population split: here the universe *is* the screen, so
   the analogous question is whether the result depends on one side. A short-only
   or long-only result is reported as a lead, not a pass (and see §6 on
   shortability);
7. **no optimum on a boundary** in the two families that have an order: range
   length (5 primary, 15 secondary) and top-N (§5).

**Two controls, both registered, both required to interpret a pass:**

- **The unfiltered arm.** The same trigger on every qualifying symbol-day, no
  RVOL rank. The paper says this is worth Sharpe 0.48 against 2.81. If our
  top-20 arm and our unfiltered arm are indistinguishable, the selection rule
  did not transfer and a positive result is the breakout, not "stocks in play".
- **Random-20, the abstention control** (§4's rule, as `gate_study` applies it):
  2,000 seeded draws of 20 symbol-days per session from the qualifying set, same
  trigger, same friction. **The top-20 arm must beat the 95th percentile of that
  distribution on per-trade net.** Trading fewer, better-chosen names on a book
  that loses per trade improves nothing, and this is the check that says so.

**Holdout, cut now and enforced in code:** every session from **2026-05-01**
onward (about the last 20%) is **locked**. The primary run, both controls and
every reading above use 2024-07-01 → 2026-04-30 only. The locked slice is spent
once, by one configuration, only if the primary passes criteria 1–7. The
existing `var/state/holdout.json` covers the small-cap universe and is untouched
by this line.

---

## 5. The secondary readings, and what they are worth

Reported, never used to pass anything:
- **15-minute range**, the same cells. The paper's own table falls from Sharpe
  2.81 (5 min) to 1.43 (15) to 0.21 (30). A genuine microstructural effect
  decays smoothly; that collapse is the warning
  (`largecap_evidence_20260911.md` §1.6). If 15 minutes reads far worse here
  too, the 5-minute result is a spike, and the write-up says so.
- **Top-N at 10, 20 and 40**, for the boundary rule only. 20 is the registered
  cell. If 10 or 40 wins, criterion 7 is not met and a push needs its own
  registration.
- **RVOL deciles** across the qualifying set: per-trade net by decile. If
  selection is real, this should be monotone-ish. It is a shape, not a threshold
  to move to.
- **Per-exit-reason friction break-even**, and the number of bars that held both
  the stop and the close.
- **Entry-minute histogram**, which must spike in the minutes after the range
  closes. Anything else means the trigger logic is wrong.

---

## 6. Limits recorded now, not discovered later

1. **First-5-minute RVOL is not validated against consolidated volume.** The
   pre-flight's 0.95 rank correlation is on *daily* volume. BASIC also lacks the
   **NYSE opening auction**, so NYSE-listed names' OR volume is understated in
   both the numerator and the 14-day denominator; the ratio mostly survives that,
   and "mostly" is not "provably".
2. **Shorting is assumed frictionless beyond the spread.** No borrow fee, no
   locate, no short-sale price test (SSR after a 10% decline). On liquid names
   borrow is usually cheap, but `short_selling_feasibility.md` says the answer
   for this project's small caps was no. The short arm is therefore reported
   separately and treated as the weaker half of any pass.
3. **No survivorship correction is needed** — EQUS.SUMMARY and BASIC carry
   delisted and renamed tickers point in time — but **no corporate-action
   handling exists either**: a reverse split prints as a gap and is caught by
   §3.5's guard rather than adjusted.
4. **2024-07 → 2026-09 is 26 months.** Trend and volatility regimes inside it
   are few. The halves test is a split of one sample, not a second sample.
5. **The paper's authors have a commercial interest** (Bear Bull Traders,
   Concretum) and the paper is not peer-reviewed. That is a reason to test it,
   not a reason to believe it.

---

## 7. Prediction, scored either way

**The primary cell fails criterion 3 at BASE friction: per trade below $1.00.**
My reasoning: the strategy's whole risk per trade is 10% of ATR, so BASE friction
of 3¢ per round trip is roughly 10–25% of R, and the paper's own gross edge is
0.38R per trade at a ~17% win rate. I expect the PAPER-friction arm to be
positive and the BASE arm to be at or below zero — i.e. the published result
reproduces out of sample **gross**, and the costs it omitted are what remove it.

**A second prediction, weaker:** the unfiltered arm will be much worse than the
top-20 arm, so the selection rule does transfer even if the net result does not.

If both predictions hold, the honest conclusion is that this is a real but
uncapturable effect at retail friction, and the next question is execution
(posted limits at the trigger, not stop orders), not a new strategy.

---

## 8. What would make this run wrong

- Running before this document is committed.
- Reading any criterion at PAPER friction.
- Touching the 2026-05-01 → 2026-09-16 holdout for anything but a single
  post-pass confirmation.
- Quoting the top-20 arm without the random-20 control beside it.
- Substituting a secondary reading (15 minutes, top-10, a decile) for the
  primary cell.
- Changing the tie-break, the friction levels, the filters or the stop after
  seeing a result. Each is a new hypothesis with its own registration.
- Reporting a portfolio return from §3.4's paper book as this project's result.

Expect rejection. §11.1's base rate for clearing this bar in full is zero of
five.

---

# AMENDMENT A — 2026-09-18, PRE-RUN. No trade has been simulated.

Building the engine exposed one rule the paper does not state and §3.2 did not
cover. It is decided here, before the runner has read a single archive file.

## A.1 Can the protective stop be hit on the ENTRY bar?

The entry is a stop order filled inside a minute bar; the protective stop sits
10% of ATR away, which on this universe is $0.05–$0.30 — often inside the same
bar's range. A minute bar does not record whether its low came before or after
the entry print, so either answer is an assumption and the choice is worth real
money on a stop this tight.

**Registered primary: the stop is live on the entry bar** (`STOP_ON_ENTRY_BAR =
True`). It assumes the unfavourable ordering, which is the direction this
project's fill model already takes everywhere else: stops gap through, a bar
holding both stop and target is the stop's, and the entry bar's own high does
not raise a trail.

**Reported beside it, never as the result:** the same run with the stop live
only from the next bar. The gap between them prices the assumption. If the
strategy passes on one and fails on the other, the write-up says the result is
undecided on a rule the paper never specified, and that is a failure to pass,
not a choice of arm.

## A.2 Two counts that come with it

- symbol-days whose stop was hit on the entry bar (both the share and their P/L);
- symbol-days where the entry bar gapped past the trigger, since a gapped entry
  starts the trade further from the range and closer to nothing.

## A.3 What A does not do

It does not touch the universe, the ranking, the friction levels, the criteria,
the controls or the holdout. The primary cell is unchanged.

---

# AMENDMENT B — 2026-09-18, PRE-RUN. Still no trade simulated.

Building the universe table exposed a defect in the tape §3.1 chose, and one
plain bug. Both are fixed here, before any P/L exists.

## B.1 XNAS.BASIC's RTH minute bars carry off-exchange prints that are not the
## session's range

The first universe build read ATR(14) of **$11.79 for AAPL** against a real
daily range of $3–4. The cause, on 2024-09-12:

| | low | high |
|---|---|---|
| XNAS.BASIC minute bars | **209.27** | 229.35 |
| XNAS.ITCH minute bars | 219.82 | 223.54 |
| EQUS.SUMMARY daily (consolidated) | 219.82 | 223.55 |

The BASIC low is a single 13:38 bar printing 209.27 with its own open and close
at 223.0x. NVDA the same day: BASIC 104.95 against a true 115.38. **ITCH agrees
with the consolidated daily bar to the cent.**

Measured over the 1,343 liquid names on that session, BASIC's session low is
more than 0.5% below the consolidated low on **11.3%** of them and more than 2%
below on **7.7%**; the high is overstated by more than 0.5% on 7.2%. ITCH
differs from consolidated by more than 0.5% on 0.8–1.9% of names, and those
differences are the opposite sign — an extreme that printed off-exchange only.

The pre-market TRF defect (`tape_spikes_RESULT_20260917.md`) was about *when*
prints land. This is a different thing: prints that are in the right minute and
are not the exchange's range. ORB's earlier RTH spike census did not catch it
because its threshold was 25%, and these are 3–7% dislocations. **They would
have set every opening range, every ATR and every stop trigger in this
strategy.**

**The decision: two tapes, by column.**
- **Prices — the opening range, ATR, the entry trigger, the stop and the exit —
  come from XNAS.ITCH RTH minute bars.**
- **Opening-range volume, and therefore the RVOL ranking, stays on
  XNAS.BASIC**, whose 56% capture ranks like consolidated (rank correlation
  0.95, top-20 overlap 16 of 20) where ITCH's 12% does not (0.81, 12 of 20).
- EQUS.SUMMARY still supplies the 14-day average daily volume.

This is a tape correction, not a threshold change: no filter, criterion,
control or the holdout moves. The §3.1 sentence "minute bars on XNAS.BASIC" is
superseded by this amendment.

**What it costs, stated now:** entries and stops are decided by exchange prints
only, so a break that traded only off-exchange does not trigger. That is the
conservative direction, and it is the same direction as the live path, where a
stop order rests on an exchange.

**Coverage:** the ITCH 09:30–16:00 pull holds 550 of the 555 sessions;
2026-09-10, -11, -14, -15 and -16 are missing and all five sit inside the
locked holdout, so the primary run is unaffected. They are pulled before the
holdout is ever opened.

## B.2 The daily-volume merge was a day out

`ohlcv-1d` bars are stamped 00:00 UTC **on** their session date. The first
build converted that to ET, which moved every bar to 19:00 the previous
evening, and merged each session's volume onto the day before. 78% of rows
still matched, so nothing raised; the liquidity filter was simply reading the
wrong day. Fixed, with a test.

## B.3 What B does not change

The rules in §2, the friction levels in §3.3, the sizing in §3.4, the criteria
and controls in §4, the secondary readings in §5, the holdout, and amendment A.

---

# AMENDMENT C — 2026-09-18. The unit of account, and a disclosed peek.

## C.0 What was seen, before anything below is read

The engine was smoke-tested on **one session, 2025-03-05**, to check it produced
trades at all. That run is not a result and no arm, control, friction sweep or
criterion was computed from it, but it did put four figures in front of me and
they are disclosed here rather than used silently:

- 2,316 trades across both range lengths; 87% of exits are the stop, 13% the
  close — the paper's ~17% win rate has the same shape;
- stop exits average **−1.04R**, and −1.29R when the stop is hit on the entry
  bar (amendment A's pessimistic reading, working as intended);
- mean **−0.26R** per trade over every qualifying name, with the close exits
  averaging +4.91R;
- at flat 100 shares the same trades read **−$16 to −$20 per trade**.

The change below is driven by the last line's *unit*, not its sign: it is
negative in both units, and C is registered before any arm exists.

## C.1 Flat 100 shares is the wrong unit for this universe

§3.4 made flat 100 shares the book the criteria are read on, copied from the
small-cap work where every name sits in a $2–$20 band. This universe does not:
the median entry price on that session was **$49.68** and the risk per share
(10% of ATR) ran from **$0.067 at the 10th percentile to $0.719 at the 90th**.
At a fixed 100 shares, one trade in a $400 name with a $1.00 stop carries
fifteen times the risk of a trade in an $8 name with a $0.07 stop, so a
per-trade dollar average is a price-weighted average of unlike bets, and
criterion 3's "$1.00 per trade" means something different for every row.

The paper does not have this problem because it risks a fixed **1% of the
position's capital**, which is equal risk per trade. So:

**The primary unit becomes R — the trade's P/L divided by its own registered
risk (entry to stop), net of friction.** Equal risk per trade is what the
published strategy does, and it is the unit its 0.38R-per-trade gross edge is
quoted in.

**The risk-normalised book** is R × $100, i.e. every trade sized to risk $100
(shares = $100 / r, rounded down, and a trade needing more than 10,000 shares
is reported and excluded as unsizeable). Reported in dollars for readability;
it is the same number as R.

**Flat 100 shares stays in the report** as context, and the paper's own
$25,000 / 1% / 4× book stays exactly as §3.4 registered it.

## C.2 The criteria, restated in the new unit

Unchanged in spirit, unchanged thresholds where the unit did not change:

1. **drop-top-3 and drop-top-5 by symbol, on the risk-normalised book, both > 0**;
2. **symbol-cluster bootstrap P(total > 0) ≥ 0.95** on the same book;
3. **mean net ≥ +0.05R per trade at BASE friction** (was "$1.00 per trade").
   0.05R is one eighth of the paper's claimed gross 0.38R and it is the level
   below which the strategy cannot survive a doubling of friction;
4. trades ≥ 100 — unchanged;
5. both halves > 0 in R — unchanged;
6. both sides > 0 in R — unchanged;
7. the boundary rule — unchanged.

The random-20 control and the unfiltered arm are compared **in R**, for the
same reason.

## C.3 The friction ratio, and why it is now a headline number

BASE friction is 3¢ per round trip (1¢ entry, 2¢ stop). Measured on that one
session, that is **17% of R for the median qualifying name and 32% of R for the
median top-20 name** — the top 20 are the fast movers, whose 10%-ATR stop is
tightest in cents. So the report states, per arm: friction as a share of R at
each level, and the gross-minus-net gap. A strategy whose entire edge is 0.38R
gross cannot be judged without that ratio in view, and §7's prediction is
precisely that this is what removes it.

## C.4 What C does not change

The universe, the ranking, the two tapes, the fill model, the friction levels
themselves, the controls, the secondary readings, the holdout, and amendments A
and B.
