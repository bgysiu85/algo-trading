# Exit candidates — three registerable experiments

**Created:** 2026-09-11
**Status:** CANDIDATE SPECIFICATIONS. None measured.
**Why this doc exists:** `cameron_exit_result.md` names the exit as the largest untested gap;
`win_rate_and_r.md` §2 shows the deficit is entirely on the **reward** side (R = 0.58 against a
required 1.05). All three candidates below attack that side, and all three arrived from source
reading on 2026-09-11.
**Governing standards:** `PROGRAM_INDEX.md` §4.

---

## 0. Why group them

Everything rejected so far cut the reward side or capped time:

| Already tested | Result |
|---|---|
| Cent stops 10/15/20c | rejected, monotone |
| Max hold 3–30 bars | rejected, boundary check fails |
| Take-profit ladder | +$272 → **−$1,612** on 4,481 trades |
| Cameron's partial at target | +$261 → **−$1,435** |
| Cameron's breakeven stop | **−$27,260** |
| Close targets 2–5% | lower P&L, higher win rate |
| Confirm-N trail | rejected despite +$8,300 |
| Scale-out / pyramid / scale-up | all rejected |

**Not one of them was a rule that lets a winner run longer on a condition.** The three below
are, and they are structurally different from each other. Register all three before running any.

---

## 1. Candidate A — the "QS exit"

**Source:** Quantified Strategies, `Xmk3vLHwbEU`. See `beginner_strategy_sources_20260911.md` §6.1.

```
exit when   close > high[1]          # first close above the previous bar's high
```

A **first-profitable-close** exit. Not a trail, not a target, not a time stop.

**Why it is a candidate.** Measured independently on SPX 2006–2026, swapping only the exit on
an identical RSI(2) mean-reversion entry:

| | CAGR | Max DD | In market |
|---|---:|---:|---:|
| exit RSI(2) > 80 | 5.00% | −34.5% | 27% |
| **exit close > prev high** | **6.22%** | **−22.9%** | 16% |

Better return, one-third less drawdown, 40% less exposure, stable across both halves.

**Expected to fail here, and the reason is specific.** It was measured on a mean-reversion entry
into an index, where the bounce *is* the thesis. MCL is a momentum entry into a low-float
runner, where the thesis is continuation — so a first-profitable-close exit plausibly cuts the
right tail, which is the exact failure mode `cameron_exit_result.md` §4.2 identified for close
targets. **Register that prediction before running.**

---

## 2. Candidate B — the re-entry test, as a codeable exit

**Source:** Brad Goh / Sanjeev Sangar, `cFzxyGRtAis` at 22:53. See §5 below for the channel
assessment.

The stated idea is a discretionary ego check:

> *"if this started going towards our stop loss, I would ask myself, **if I wasn't already in
> this trade, would I want to get in right now? And if the answer is no then why the [f] am I
> still in the trade?** I should be looking to exit. And if the answer is yes then it's a
> better entry."*

**For a discretionary trader that is a self-talk device. For an automated system it is a
genuine, non-trivial rule:**

```
on each bar while in position:
    if NOT entry_condition(bar):   # the full MCL arming + trigger test, evaluated now
        flatten
```

**Why it is the most interesting of the three.**

- It is **not a stop, not a target, not a time cap** — it is the only candidate whose exit
  condition is the *inverse of the entry condition*, so it inherits whatever selectivity the
  entry has.
- It directly attacks the **1-bar problem**: `hold_cap_decision.md` §4 measured 1-bar trades at
  **107 of 485, −$3,924, −$36.68 each**, and removing them takes MCL +$161 → **+$4,086**. A
  trade whose entry condition evaporates on the next bar is exactly the trade that dies in one
  bar. This rule would exit those at the bar's close rather than riding to the 5% trail.
- It is **cheap** — the entry condition is already computed every bar for arming purposes.

**Design decisions that must be registered, not chosen after seeing results:**

| Choice | Options |
|---|---|
| Which condition to re-test | full entry (arming + trigger) / arming only / MACD leg only |
| Confirmation | flatten on first failure, or require N consecutive failures |
| Grace period | allow K bars after entry before the test arms |
| Interaction with the 5% trail | trail stays in force underneath — do not remove a settled control to test a new one |

Boundary-check N and K. Report the ablation (trail only) alongside.

**Honest caveat:** this is the inverse of a known failure. `mcl_rejected_mechanics.md` §4
rejected the confirm-N trailing stop, and `premarket_hypotheses_results_20260908.md` found that
confirmation entries cost money — *"the confirmation itself is the cost."* A condition-based
exit may be the same tax collected at the other end. That is the null to beat.

---

## 3. Candidate C — the MFE gap, as a diagnostic not a rule

**Source:** same video, 30:03. Sanjeev, on how to know whether you are exiting too early:

> *"MFE, the one that you would want to be focusing on is **maximum favorable excursion** — how
> far the trade went in your direction maybe after you already exited… if you see over a large
> sample size that there's a gap between where you're exiting and the potential of the trade,
> that data can start to give you confirmation to say, okay, **this is not just a gut feeling
> anymore**."*

**This is not a strategy — it is the measurement that tells you whether A or B is even worth
running**, and it is the single most directly relevant thing found in either video for a trader
whose R is 0.58 with the entire deficit on the reward side.

```
for every closed trade:  MFE_after_exit = max(high[t_exit .. t_session_end]) - exit_price
```

Then: the distribution of MFE-after-exit, and its share of total MFE. If MCL's exits cluster far
below the eventual session high, the reward side is being left on the table and the exit is the
problem. If they do not, the R = 0.58 deficit is an **entry** problem and every exit candidate
in this document is a distraction.

**The project already has the machinery.** `dip_entry_result.md` and
`ladder_and_regime_20260911.md` §3 both score MFE/MAE — but on *entries*. Turning the same
measurement on *exits* is new and is a few lines.

**Run C first.** It is the cheapest, it is a pure measurement with no parameters to leak, and
its result determines whether A and B are worth the time.

**One borrowed method worth keeping if C says the exits are early** — staged migration rather
than a switch:

> *"this is where I would normally get out but… **I'm only going to take 90% of my profit and
> I'm going to leave 10% to run**… You can start off at 90/10, you can then go 80/20, you can
> then go 50/50."*

Note this is a partial, and partials have been measured and rejected twice here (+$261 →
−$1,435; ladder +$272 → −$1,612). **It should be treated as a rejected family unless C produces
a large MFE gap that changes the prior.**

---

## 4. Anti-pattern — flagged because the same video advocates it

The same source, at 24:28–25:27, recommends **widening a losing stop on discretion**:

> *"80% of the time you should stick to a stop loss… the other 20% of the time requires a little
> bit of discretion… based on my **gut feeling, which is really just like my subconscious
> pattern recognition skill**… I personally would just move the stop loss a little bit."*

**Do not build this.** For a book whose average loss (20.6c) is already 1.7× its average win
(11.9c), a rule that selectively widens losers increases the left tail on exactly the trades
that are already losing. It is a variance increase dressed as skill, offered with no data. His
own co-host declines to endorse it — *"I'm not saying you should or I'm advocating for people to
move their stop loss"* — and only rescues it by noting that if discretion exists it must be
**pre-budgeted inside the max risk, not added on top**. That reframe is the only defensible part
and it is already covered by a fixed stop.

Recorded here so a future reader who encounters this advice knows it was considered and
rejected.

---

## 5. The source, assessed — so nobody re-reads it

**Video:** "10 Years of Trading Knowledge in 60 Minutes", Brad Goh (*The Trading Geek*),
`cFzxyGRtAis`, 2026-09-04, 59:12, 256k views. Full transcript read.

**Channel:** 1.79M subscribers, 1,292 videos, 124M views, started May 2021.

**What it actually is:** ~58 minutes of trading-psychology conversation wrapped around a live
index-CFD trade, with a sponsor read for the host's own app.

| | |
|---|---|
| Instrument | **US30 and NQ via a CFD/spread platform** — sized in *lots*, distances in *pips* |
| US equities content | **zero.** No stock named. No small caps, float, relative volume, gappers, pre-market, halts, borrow, Level 2 |
| Systematic / automated content | **zero.** "Systematic" means "I follow the same discretionary checklist." No backtest, no sample, no code |
| Hard rules in 59 minutes | **~6–8.** The only clean one is "minimum 1:2 R:R" — immediately undercut when he asks his co-host "Is it the same for you?" → **"No."** |
| Expectancy stated | **never**, in 58 minutes |
| Win rate without paired R | yes — the one quantitative argument (50% win rate ⇒ ~9 losers in a row over 500 trades) is correct arithmetic for streak length but is never connected to whether the strategy makes money |

**The live trade, which is the video's proof-of-competence beat, was an admitted coin flip:**

> *"we are just going to enter for like a **random trade**… I'm just going to enter for a buy
> right here because **it looks like it's going to go up**."* — and after polling each other,
> *"we'll flip a coin for it basically."*

The stop was placed **after** entry; the target was then **reverse-engineered** to produce a 1:2
(*"this is not even a one to two. Okay, let's make it one to two"*). It sat flat, went red, and
was rescued when a **CPI print** hit mid-sentence — *"we just made 2.68 [$2.6K]… that's CPI."*
They were trading through a high-impact release that the host's own app exists to block, having
already overridden its trading-window guardrail on camera to make the video.

**The daily loss limit — this project's single best-measured intervention at +$55,083 —
appears once, as a bullet in a product feature list, with no number and no recommendation.**

**Channel sweep: not warranted.** The 30 most recent uploads are lifestyle content (*"Day in the
Life of a MILLIONAIRE Trader"*, *"How A Millionaire Trader Travels To Europe"*, *"I Was
Unprofitable.. Found Reality Transurfing.. Now I Make $10M/Year"*, *"These 7 Bible Verses Made
Me A Profitable Trader"*), ICT/Smart-Money-Concepts forex methodology (*"The ICT Silver Bullet
Strategy"*, *"Liquidity Sweeps, Order Blocks and FVGs"*, *"BEST Gold Scalping Strategy"*), prop-
firm content, and a free psychology course series. **Nothing on US equities, small caps,
automation, or backtesting.** The one title that sounds relevant — *Market Mechanics Ep 27: How
to Improve Your Strategy With Data* — is the only plausible follow-up, and on the base rate of
this channel it is unlikely to clear §4.

**Minor note:** the title claims "10 years." In the video Brad states **~7 years** and Sanjeev
**14**. The headline figure is neither person's.

**Commercial structure**, for the record: a paid mentorship (*1% Club*), his own software
(*EdgeFlo*, with a discount code read on air), and affiliate links to a broker and a prop firm
in the description. Three revenue streams. That does not make the content wrong — it does mean
nothing in it was produced to be falsifiable.

---

## 6. Build order

1. **C — the MFE-after-exit measurement.** Cheapest, no parameters, and it decides whether the
   other two matter. If the gap is small, the R = 0.58 deficit is an entry problem and A and B
   are dropped.
2. **B — the re-entry-condition exit**, with the four design choices registered up front and the
   5% trail left in force underneath. Highest prior value because of the 1-bar finding.
3. **A — the QS exit**, registered with its predicted failure.

All three on `bar_cache_xnas` (4,481 trades), not `bar_cache` — three findings from the 485-trade
cache have now inverted on the larger universe. Report average win, average loss and R alongside
any win rate, per `win_rate_and_r.md` §6.
