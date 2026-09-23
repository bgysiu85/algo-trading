# REGISTERED — H60-v0: seven rule sets on 60-minute bars, US large/mid caps, 1–5 day holds

**Committed before any 60-minute data has been pulled, before any engine code exists, and
before any return of any of these rules on 60-minute bars has been seen.** `PROGRAM_INDEX` §1:
a hypothesis is registered before it is run.

**Board:** W14-0001 (this doc) · W14-0002 (data) · W14-0003 (engine) · W14-0004 (run) ·
W14-0005 (Ben's Pine source for MR-60). **Chat:** 60-min chat.
**Ben's request, 2026-09-23, in his words:** *"I would like to consider trying a equities
trading strategy that uses the 60min timeframe. We can start with all the strategies mechanics
we used before to backtest it first."* **His choices the same day (multiple choice):**
mechanics = all four offered (the testing discipline, port MCL/MC5, port his RSI/MFI setup,
port ORB / trend-line); universe = large/mid caps; holding = 1–5 days; data = Databento
hourly bars, priced first. **Then, before anything was committed or run:** *"how about the vw9
strategy? was that also included?"* — it was not (it was missing from the options offered);
Ben chose to add it. See amendment A0 at the end.

Amendments are marked **PRE-RUN** or **POST-RUN**. A threshold changed after seeing a result
is a new hypothesis and spends from the budget in §10.

---

## In plain terms

We take seven trading rules this project already knows — the two pre-market momentum rules
(MCL, MC5), the VWAP + 9 EMA rule (VW9), the opening-range breakout (ORB), a plain 20-bar
breakout (Donchian), Tori's trend-line method, and Ben's own RSI/MFI dip-buying setup —
and run each one, unchanged, on 60-minute charts of the S&P 500 and S&P 400 stocks as they were on each day (including the
companies that later left the index). Each trade can last from an hour up to five trading
days. Every rule is judged the same way: dollars made per trade on a $10,000 position after
spread and commission, compared with simply holding the whole list over the same hours, and
compared with buying random stocks at random times and exiting the same way. A rule has to
pass every check on the older 80% of the data before the newest 20% is looked at, and only one
rule gets to look at it.

---

## 0. PRE-RUN GATES — no P&L is computed until every row is true

| # | Gate | Status |
|---|---|---|
| **G1** | **Data priced, then pulled** (W14-0002): XNAS.ITCH `ohlcv-1m`, 09:30–16:00 ET, every eligible symbol-day in §2.1, into an archive root **separate from `E:\Databento\XNAS.ITCH\`** (§6.3 — the existing pre-market archive must not be touched). | Open. `strategy/h60/data_plan.py` prices it; nothing is bought without Ben's go-ahead. |
| **G2** | **Cross-source price check passes** (§5.1): the 16:00 close built from our bars against EODHD's daily close, per symbol. | Open. Runs in the pre-flight. |
| **G3** | **MR-60's rules fixed from Ben's Pine source** by PRE-RUN amendment A, committed before any MR-60 code exists (W14-0005). | Open — waiting on Ben. The other six rule sets do not wait for this. |
| **G4** | **TL-60 runs only if the TL-v0 Python engine has passed its Pine parity check** (W01-0006, `REGISTERED_tl_v0.md` G3). If it has not by the time W14-0004 starts, TL-60 is reported **"not run"** and DON-60 carries the trend family alone. | Open, owned by the W01 line. |
| **G5** | **Hindsight guards tested and mutation-checked** (§6.1): membership by date, bar knowable only at its close, entry only at the next bar's open. | Open (W14-0003). |
| **G6** | **Holdout cut and enforced in code** (§8), `holdout_h60.json`, mutation-tested. | Open (W14-0003). |
| **G7** | **Positive control passes** (§4.3): the harness recovers a planted effect of known size. If it does not, nothing in §7 is scored. | Open (W14-0004). |

---

## 1. The hypothesis, in one sentence

**At least one of seven existing rule sets — MCL-60, MC5-60, VW9-60, ORB-60, DON-60, TL-60, MR-60 —
run unchanged on 60-minute bars of the point-in-time S&P 500 + S&P 400, long only, held at
most five sessions, makes money per trade after measured costs, beats holding the universe
over the same hours, and beats random entries with the same exit.**

Why these seven and not a new rule: Ben asked to start from the mechanics already built. A port
fixed at its source parameters cannot be fitted to 60-minute data, which is the reason to
start here rather than with a new rule. The price of that is a weak prior for five of the seven
(§11).

---

## 2. Common to all seven rule sets — fixed here

### 2.1 Universe

- Point-in-time S&P 500 + S&P 400 constituents, `var/swing_pit/membership.csv`, **excluding
  the 35 spells in `var/swing_pit/suspects.csv`** — the G8 residual Ben accepted on W07-0002.
- A name is eligible on session *t* only if a membership spell covers *t* (`Spell.covers`,
  `strategy/swing/pit_universe.py`). The hindsight guard is the swing chat's, reused, not
  rewritten.
- **Ticker mapping to Databento raw symbols, fixed now:** strip an `_OLD`, `_OLD1`, `_OLD2`
  suffix; replace `-` with `.` (`BRK-B` → `BRK.B`). The placeholder code `--` is dropped.
  Renames and ticker reuse (a code that belonged to a different company in 2018) are **not
  solved by the mapping** — they are caught by the cross-source check (§5.1), which excludes
  and counts them.
- **The `$2–20` price band (`PROGRAM_INDEX` §1) does not apply to this line, and this is the
  reason, stated once:** the band exists because IB returns split-adjusted history and VW9
  traded the adjustment factor ($4,152 a share). These bars are Databento raw prints, and a
  large-cap universe trades from ~$10 to over $1,000. The job the band did is done here by
  §5.1's per-symbol ratio check against EODHD, which catches a wrong-scale price directly. A
  floor of **$5 at entry** is enforced (sub-$5 S&P 400 names are distressed and quote in
  wide ticks).

### 2.2 Bars

- **60-minute bars aligned to 09:30 ET, regular hours only:** 09:30, 10:30, 11:30, 12:30,
  13:30, 14:30 (60 minutes each) and **15:30–16:00 (30 minutes)** — the grid TradingView shows
  on a US stock's 60-minute chart. Built by resampling XNAS.ITCH `ohlcv-1m`; no pre-market or
  after-hours bar exists in this study.
- **A bar is knowable only when it closes.** `ts_event` is the interval START (`PROGRAM_INDEX`
  §5). The first price at which a decision taken on a bar can be acted on is the NEXT bar's
  open.
- Indicators run on the continuous hourly series across sessions, as a TradingView chart does.
  **Warm-up:** the first 30 sessions of the sample produce no signals (a 200-bar EMA needs 29).
- **Volume is Nasdaq's book only** (ITCH). Every volume rule in these ports is a ratio of
  volume to earlier volume on the same tape, which survives a single-venue tape
  (`PROGRAM_INDEX` §5, "ratio conditions survive the switch").
- **Fallback grid, fixed now (PRE-RUN, decided by size, not by return):** if the pricing in
  G1 puts the RTH 1-minute pull above **$50 or 25 GB billable**, the grid becomes 09:30–10:00
  (from 1-minute) + clock-hour bars 10:00–16:00 (from `ohlcv-1h`). The switch is recorded as
  amendment B with the pricing report attached, before any bar is read.

### 2.3 Entry, position and exit plumbing

| Element | Rule |
|---|---|
| Side | **Long only**, all seven (MCL/MC5/VW9/MR are long-only rules; ORB/DON/TL shorts are §9) |
| Signal | on a bar's close |
| Fill | **the next bar's open** — which for a 15:30 signal is the next session's 09:30 open (overnight gap included) |
| Size | **$10,000 notional** per trade, `floor(10000 / entry price)` shares |
| Positions per symbol | one per rule set at a time; a new entry needs a bar that **opened after** the last exit (`PROGRAM_INDEX` §1) |
| Stops | resting; **gap fills**: a bar that opens through a stop fills at its open, never at the level (`gap_fills=True`) |
| Trailing stops | peak seeded from the fill price; the level from the peak as of the PREVIOUS bar, tested against this bar's low (MCL's exit modelling, unchanged) |
| Same bar has stop and target | stop wins |
| **Time cap** | **exit at the 16:00 close of the fifth session after the entry session.** A 10:30 Monday entry exits no later than the following Monday's close |
| Concurrency | **every signal is taken** (no cap) for the scored book; max concurrent positions and capital tied up are reported, and a book capped at **2 concurrent positions ($20k), first-come-first-served**, is reported and never scored — the live cap refused 29% of MCL's buys (`PROGRAM_INDEX` §4) |
| Splits | a trade whose hold spans a split date found by §5.1 is **voided and counted** |
| Dividends | not added back (raw prices); caveat §12. Market-relative scoring mostly cancels it |

### 2.4 Friction — three levels, in dollars on the $10,000 position

The swing universe's own measured costs (`swing_g2_RESULT_20260919.md`), not MCL's $4.26:

| Level | What is charged | ≈ $ per round trip |
|---|---|---:|
| **L1 flat** | the measured all-in median, **5.46 bps** round trip | $5.46 |
| **L2 by time of day — the scoring level** | **half the quoted spread of the half-hour the fill is in, each leg** (§3 table of the G2 result: 09:30 7.98 bps … 15:30 2.96), **plus IBKR tiered commission and fees per order** (`common.commissions.order_cost`), **plus one extra half-spread on every stop fill** (a stop sells through the bid) | ~$4–8 |
| **L3 stress** | L2 with the spread part doubled — a volatile session G2 has not yet seen | ~$6–13 |

Cash-funded: **no financing** in the headline. A 2:1 levered line at 7.13%/yr, charged per
night held, is reported beside it and never scored.

### 2.5 Scoring — two numbers per trade, both in dollars

1. **Net $** — what the account made after L2 costs.
2. **Market-relative net $** — net $ minus what $10,000 in an equal-weight basket of every
   eligible name would have made **from the same entry bar's open to the same exit time**,
   built from the same bars. This is the swing line's G1 construction, carried over: a long
   rule tested over 2018–2024 must show it did more than own stocks in a rising market.

---

## 3. The seven rule sets — each at its source's parameters, nothing re-fitted

"Imported" means the signal function is **called from its existing module**, not copied, so a
60-minute run and a 1-minute run cannot drift apart (`PROGRAM_INDEX` §1, the parity rule). No
sweep parameter is passed; the published constants are read.

### 3.1 MCL-60 — `strategy/mcl/mcl.py` `signals()`, imported

- **Entry:** MACD(12,26,9) above its signal AND above zero; MFI(14) above MFI 3 bars ago;
  RSI(14) above RSI 3 bars ago; volume ≥ 3× the previous bar; previous bar's volume ≥ 50% of
  its trailing 60-bar average.
- **Exit:** 5% below the highest price since entry (apex exit OFF, as published), or the time
  cap.
- **Registered expectation, to be checked in the pre-flight, not tuned:** the 3× volume clause
  compares each hour with the one before it, and the 09:30 hour's volume dwarfs the previous
  day's 15:30 half-hour. Expect entries to pile onto the 10:30 open.

### 3.2 MC5-60 — `strategy/mc5/mc5.py` `signals()`, imported

- **Entry:** RSI(14) rate of change ≥ +5% over the last 3 bars (least-squares, as the module
  defines it); EMA 9 above EMA 21; MACD above its signal.
- **Exit:** 5% trailing stop (gradient-reversal exit OFF, as published), or the time cap.

### 3.3 ORB-60 — the opening-range break, one 60-minute range

- **Range:** the 09:30–10:30 bar's high and low.
- **Entry signal:** the **first** bar of the session from 10:30 to 14:30 that **closes above
  the range high**; one entry per symbol per session. Fill at the next bar's open.
- **Initial stop:** the range low (ORB's `structure` stop), resting, never loosened.
- **Exit:** the stop, a 5% trail from the peak (the exit that beat every fixed target on ORB,
  `PROGRAM_INDEX` §2), or the time cap — whichever comes first.
- Not imported: `strategy/orb/orb.py` is a one-session state machine on a 15-minute range with
  the $2–20 band built in (§2.1). ORB-60 reuses its fill conventions, written fresh.

### 3.4 DON-60 — 20/10 Donchian, the control `REGISTERED_tl_v0.md` registered for TL

- **Entry:** a close above the highest high of the previous 20 bars. Fill at the next open.
- **Exit:** a close below the lowest low of the previous 10 bars (fill at the next open), or
  the time cap. No other stop.

### 3.5 TL-60 — TL-v0 (not v0-rev), long side, on 60-minute bars

- `REGISTERED_tl_v0.md` §2.1–2.2, unchanged except: timeframe 60-minute; **top-down filter on
  completed DAILY bars** (one timeframe step up, as weekly is from daily); size per §2.3 (not
  1% risk — this is an equity study at flat notional); time cap per §2.3; long side only.
- Pivot ensemble L = R ∈ {3, 5, 8}, each sleeve a third of the $10,000; each size reported
  alone.
- **Gate G4:** runs only on the W01 engine after its parity check passes.

### 3.6 MR-60 — Ben's RSI/MFI mean-reversion confluence

- What is known today: RSI + MFI confluence, ATR-based stop, optional 200-EMA trend filter,
  Pine v5, grown from a five-filter predecessor.
- **Every parameter — thresholds, lengths, the ATR multiple, whether the 200-EMA filter is on,
  and the exit — is taken from the Pine file's defaults as Ben has it saved, by PRE-RUN
  amendment A, committed before any MR-60 code exists (gate G3).** Nothing is chosen by this
  chat. If the Pine file has a take-profit or signal exit, it is ported; the time cap is
  added on top.

### 3.7 VW9-60 — VWAP + 9 EMA, both setups (amendment A0)

`strategy/vw9/vw9.py` (`apply_indicators` and the two setup trackers), **imported**, at the
spec's defaults (`claude/archive/vw9_strategy_spec.md` §4, §6). What changes, and why — each
forced by the data or by §2, none chosen from a result:

| Element | Spec (small caps, 5/15-min) | VW9-60 |
|---|---|---|
| Session VWAP anchor | 04:00 ET | **09:30 ET** — there are no pre-market bars in this study (§2.2) |
| VWAP maturity | 3 bars and $50,000 | 3 bars (so the first possible trigger is the 11:30 bar's close); the $ clause at its default |
| 9 EMA, ATR(14) | within the session | **continuous across sessions**, like every other port here |
| Setup A (VWAP reclaim), Setup B (9 EMA retest) | as specified | unchanged |
| Extension gate | ≤ 2.0 ATR | unchanged |
| Pullback-volume gate | on | unchanged (a ratio on one tape) |
| Liquidity gate | $40,000 a minute | **off** — set for thin small caps on another tape; §2.1's universe and $5 floor replace it |
| Headroom gate | off | off |
| Entries per session | ≤ 4 | unchanged |
| Stop | structure low − 0.10 × ATR | unchanged |
| **Exit — deployed** | `fixed_2r`, the spec's baseline | **`fixed_2r`**: entry + 2R, or the stop |
| Exit — reported, never scored | `ride_ema9`, `trail_atr`, `trail_pct` | each reported alone |
| VWAP-lost hard exit | any bar closing below VWAP | unchanged, against **that session's** VWAP |
| Session end | flat at 20:00 | replaced by §2.3's five-session cap (Ben's 1–5 day choice) |

VW9 was rejected on small caps: (4.96) a trade on the screened universe, break-even friction
(0.70) — it lost before costs. That is its prior here.

---

## 4. Controls

### 4.1 Random entries, same exit (the selection control)

For each rule set: on each session, the same number of entries it took, placed on **random
eligible names at random bars of that session** (seeded with `zlib.crc32`, never `hash()` —
`PROGRAM_INDEX` §5), exited by **that rule set's own exit**. **1,000 draws.** A rule set must
beat the draws' 95th percentile on market-relative net $ per trade. Failing this means the
entry picks nothing that random names would not have.

### 4.2 Holding the universe (the market control)

Built into every trade by §2.5's market-relative number. Reported in total as well: what the
equal-weight basket made over the union of the rule set's holding windows.

### 4.3 Positive control — can the harness find an effect of known size? (gate G7)

`PROGRAM_INDEX` §4: a harness that measures nothing passes every null. So, on a copy of the
bars: flag a seeded random 1% of eligible symbol-days; on those, raise every price from 10:30
onward by exactly **+20 bps**; a rule that buys flagged names at the 10:30 open and exits at the
16:00 close must report a market-relative gross of **+$20.00 ± $2.00 per trade** on $10,000,
and the same rule on the unaltered bars must report **$0.00 ± $2.00**. If either fails, the
booking or the market-relative subtraction is wrong and nothing in §7 is scored.

### 4.4 A second source, reported, never scored

If the G1 pricing shows XNAS.BASIC `ohlcv-1m` for the same window is free, the two deployed
cells with the most trades are re-run on it: trade counts and signs side by side. Agreement
between two sources that share most of their prints is not replication (`PROGRAM_INDEX` §4) —
it checks the tool, not the result.

---

## 5. Pre-flight — no P&L, training side only, run and read before §7

### 5.1 The cross-source price check (gate G2) — and the split finder

Per symbol, the ratio of our 16:00 close to EODHD's daily `close` (which is split-adjusted) is
piecewise constant, stepping only at splits. Fixed now:

- a step is a day-over-day change in the ratio of more than **20%** — those dates are the
  splits, and a hold spanning one is voided (§2.3);
- between steps, a symbol-day whose ratio sits more than **1%** from its segment's median is a
  **bad symbol-day**, excluded from every book and counted;
- a symbol with bad days on more than **20%** of its eligible sessions is a mapping failure
  (wrong company under that ticker, §2.1) and is excluded whole, and named.

**Stop rule, fixed now:** if bad symbol-days exceed **2%** of all eligible symbol-days, the
study stops and the data path is diagnosed before any P&L exists. A price path that disagrees
with a second source that often is not a price path.

### 5.2 What the pre-flight prints

Per rule set, training side: signals per year; trades per session; entries by bar of day
(§3.1's expectation); median hold in bars; share of trades exited by the time cap; max
concurrent positions; voided split trades; and for the universe: eligible names per session,
bars per symbol-day, symbol-days excluded by §5.1, unresolved tickers per year.

**Stop rule, fixed now:** a rule set with **fewer than 300 training trades** is reported as
too thin to judge and is not scored.

---

## 6. Data

### 6.1 Hindsight guards (gate G5), each mutation-tested before any real run

1. Membership by date — a name is not eligible before its spell's start or after its end
   (shift a date by a day; the test must fail).
2. A bar's values are unavailable to any rule before the bar's close (shift the index by one
   bar; the test must fail).
3. An entry fills at the open of the bar after the signal, never the signal bar's close.

### 6.2 What is pulled

XNAS.ITCH `ohlcv-1m`, **09:30–16:00 ET**, every symbol eligible on that session under §2.1,
from the dataset's first date (expected 2018-05-01; the probe confirms) to the last complete
session. Priced by `python -m strategy.h60.data_plan` (per-year cost and billable size, the
RTH share measured on a sample day per year, symbols Databento cannot resolve per year) before
anything is bought.

### 6.3 Where it goes — NOT the existing archive

`common.databento_fetch` writes one file per dataset/schema/day under `E:\Databento\` and a
fetch scoped to a new list **replaces** that day's file. `E:\Databento\XNAS.ITCH\ohlcv-1m\`
holds the pre-market archive every small-cap result stands on. **This study's bars go under
`E:\Databento\H60\` and nowhere else**, and `strategy/h60/data_plan.py` refuses an archive
root that is the existing one.

---

## 7. The bar to clear — all of it, per rule set, training side, L2 costs

1. **Market-relative net $ per trade > 0.**
2. **Net $ per trade > 0** (it has to make money, not just lose less than the market).
3. **Both halves** (split at the median session, not swept) market-relative net > 0; an empty
   half fails.
4. **drop-top-5 symbols** still market-relative net > 0.
5. **Calendar-month cluster bootstrap:** total market-relative net > 0 in **≥ 99.3%** of 2,000
   seeded resamples (not 95%, because seven rule sets are tried: 5% ÷ 7 ≈ 0.7%).
6. **Beats the random-entry control's 95th percentile** (§4.1) on market-relative net per
   trade.
7. **No single year and no single symbol supplies more than 50% of net.**
8. **Still market-relative positive at L3.**
9. **≥ 300 trades** (§5.2).
10. **For TL-60 only:** beats DON-60 on market-relative net per trade (TL's own registration
    says a trend line that cannot beat a channel is decoration).

Every rule set is reported whole, every criterion, pass or fail. **Nothing is ranked. No "best
rule" table.**

---

## 8. The holdout — spent once, by one rule set, chosen by an order fixed NOW

`holdout_h60.json`: **the last 20% of sessions in the pulled sample, by date**, computed by rule
from the session list the pull produces (the date is not typed here because the data's first
session is not yet confirmed). Refuses `--limit` and every narrowing flag, like
`holdout.split_sessions`, `holdout_spy.json` and `holdout_swing.json`; no other holdout file
governs this study and this one governs no other.

**Order of priority, fixed before any result, by prior evidence only:**

1. **MR-60** — short-horizon reversal in large caps is the best-documented effect of the seven
   at this horizon (Jegadeesh 1990, Lehmann 1990), and Ben's own design.
2. **DON-60** — plain trend-following; simplest rule, fewest choices.
3. **TL-60** — the same family with more geometry; lower than DON-60 because it must beat it.
4. **ORB-60** — the one intraday rule here that cleared six of seven criteria on its first
   (survivor-universe) run; the later small-cap runs did not hold that up.
5. **VW9-60** — lost before costs on small caps, but its VWAP anchor and trend gate are
   ordinary large-cap tools, closer to this universe than MCL/MC5's pre-market spikes.
6. **MC5-60** and 7. **MCL-60** — both lose money before costs on their home universe
   (break-even friction negative, `PROGRAM_INDEX` 2026-09-11).

**The holdout is spent by the highest-priority rule set that passes every §7 criterion.** The
others that pass are reported as training-side passes and need a registration of their own to
be tested out of sample.

---

## 9. Registered as NOT to be done

- Changing any rule's parameters for 60-minute bars ("the 5% trail is too wide for a large
  cap") after any number exists. A re-scaled rule is a new registration.
- Adding short sides to ORB-60, DON-60 or TL-60 in this registration.
- Scoring VW9-60 on any exit other than `fixed_2r`, or switching to one after the run.
- Ranking the seven after the run, or promoting the best-looking one ahead of §8's order.
- Pulling into, or reading bars from, `E:\Databento\XNAS.ITCH\ohlcv-1m\` for this study.
- Using today's constituent list, or the 35 suspect spells.
- Re-cutting `holdout_h60.json` after a near miss.
- Reporting any headline before the positive control (§4.3) has passed.

---

## 10. Multiplicity budget

**Seven rule sets are one spend** — this registration. They are counted as seven families, which is
why §7 criterion 5 asks for 99.3% rather than 95%. Budget after this: **one** further registered
hypothesis on this line (for example, a 60-minute-specific re-scaling of a rule that passed
here) before any further one needs a reason that does not begin with a result.

---

## 11. A prediction, written down now

- **MCL-60 and MC5-60 fail criterion 2 or 6.** They lose before costs on their home universe
  and nothing about a 60-minute large-cap chart gives them a reason to start working. Their
  entries pile onto the 10:30 open (§3.1).
- **VW9-60 fails criterion 1 or 6** — the VWAP-lost exit cuts most trades inside the first
  session, so it behaves like an intraday rule with an hourly bar, and that lost before costs.
- **ORB-60 clears criterion 2 and fails 6** — a breakout of the first hour in a rising large-cap
  market looks profitable and is mostly the market.
- **DON-60 and TL-60 fail criterion 1** — short-horizon trend in large caps is weak; market
  exposure explains their raw profit.
- **MR-60 has the best chance and clears criteria 1–4, but fails 6 or 8** — reversal at this
  horizon is real but thin, and close to the size of the spread.
- **No rule set passes all of §7.** If that is the result, the reading is: *the rules this
  project already owns do not carry over to a 60-minute large-cap chart; a 60-minute strategy
  would have to be designed for it*, and the data, harness and controls built here are what
  that design is tested on.

---

## 12. Ways this could go wrong

- **Nasdaq-only prints.** ITCH is one venue. For NYSE-listed names the 09:30 bar's open is
  Nasdaq's first trade, not the NYSE opening auction, and the 16:00 close is Nasdaq's last
  trade, not the closing auction. §5.1 bounds the disagreement at 1% per day; a typical gap in
  a large cap is a few cents.
- **Ticker reuse and renames** are only caught, not solved (§2.1, §5.1). The excluded count is
  printed; if it is large, the universe is thinner than the membership file says.
- **Dividends are not added back.** An overnight hold across an ex-date books the drop as a
  loss. Market-relative scoring cancels most of it (the basket loses the same way on average).
- **The G2 cost table is one session.** W07-0001 is collecting two more; if they move the
  by-half-hour spreads materially, L2 is re-read before any number here is called final.
- **Delisting inside a hold** (acquisition, bankruptcy): the last available bar is the exit.
  Optimistic for a bankruptcy; counted and named.
- **A universe this broad and a rule this loose can trade thousands of times a year.** That is
  why the scored book takes every signal but the report prints the capital it needed and a
  capped book beside it.

---

## Next steps (board)

- **W14-0002** (Ben): run the data probe and pricing, report the numbers; then decide the pull.
- **W14-0005** (Ben): save the RSI/MFI Pine source into the repo → amendment A (60-min chat).
- **W14-0003** (60-min chat): engine, guards, controls, holdout cut, tests — no P&L.
- **W14-0004** (60-min chat, runs on Ben's PC): pre-flight, then the training-side run, Result doc.

---

## Amendment A0 — PRE-RUN, 2026-09-23: VW9-60 added

Written the same evening as the registration, **before the registration was committed, before
any data was priced or pulled, and before any engine code existed.** Ben: *"how about the vw9
strategy? was that also included?"* It was not — the multiple-choice question that set the scope
offered MCL/MC5, the RSI/MFI setup and ORB/trend-line, and left VW9 out; that was this chat's
omission, not Ben's choice. Offered the option to add it or leave it out, Ben chose **"Add VW9-60"**.

What moved: a seventh rule set (§3.7); criterion 5's bootstrap bar from 99% to 99.3%; VW9-60 fifth
in §8's holdout order; §9–§11 updated to match. Nothing else changed.
