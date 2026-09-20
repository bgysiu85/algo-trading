# Short-selling feasibility for this universe

2026-09-08. Task #12. This is the **mechanical and regulatory** question — can
these names be shorted at all, at what cost, under what constraints. It is not
about whether a short setup has an edge, and it does not depend on one.

`short_selling_source_comparison.md` is the companion and answers a different
question: what the six source methodologies claim about shorting. Nothing here
rests on those claims.

**Verdict: not feasible as the project stands, and three of the five obstacles
are structural rather than a matter of tuning.** The ranking below is by how
hard each is to get around, not by size.

| | Obstacle | Can it be worked around? |
|---|---|---|
| 1 | IBKR refuses opening trades in this universe | Only by changing broker |
| 2 | Locate fees are sunk at the moment of the locate, not the fill | No — it is how the market prices HTB borrow |
| 3 | SSR forbids hitting the bid, and turns on precisely when we would short | No |
| 4 | No LULD brake pre-market, no exchange-native stop at IBKR | Partly, by trading RTH only |
| 5 | Short margin on sub-$5 names is 2× the equivalent long | Yes, with capital |

---

## 1. The broker gate, which is already answered

On 2026-09-02 IBKR rejected three **long** entries in JLHL on the paper account:

```
Error 201: Order rejected - reason:No Trading Permission, Customer Ineligible;
Ineligibility reasons: No Opening Trades: Small Cap, Subject to Compliance Restriction
```

A short is an opening trade in the same security. IBKR will not accept an
opening trade in that name in either direction, so at IBKR the short question
never reaches the borrow desk. See `ibkr_small_cap_restriction.md`; the block is
account-dependent, unpublished, and was enforced in paper.

TradeZero accepted an opening order in the same name (`tradezero_hybrid_probe.md`),
but on `route: "PAPER"`, and whether their paper router enforces compliance at
all is still unasked. **Every cost in the rest of this document is a cost at a
broker this project does not currently trade through.**

## 2. Borrow — availability and, more importantly, when you pay for it

Two different cost models, and the difference decides this.

**At IBKR**, short availability comes from the SLB pool and the borrow fee is an
annualised rate applied to collateral and charged daily on the position. IBKR
publishes indicative rates only; its own documentation says rates are "subject to
change" and the SLB tool carries no guarantee of availability. *Inference, not
documented:* a short opened and closed within the session never reaches a
settled position, so it should accrue no borrow fee. I could not find IBKR
documentation stating that explicitly and it should not be relied on without
asking them.

**At a small-cap broker (TradeZero and peers)**, hard-to-borrow shares are
locates you buy: a per-share fee, "payable when you accept the quoted locate,
rather than when your short order fills", valid for that day only and expiring
at 20:00 ET. Their own worked example is 500 shares × $0.08 = $40.

That is the number that matters, and it lands badly here:

- The fee is sunk **before** the signal. Our screen produces a watchlist at
  04:30; the entry may or may not fire. Locating 20 candidates at 100 shares and
  $0.08 costs **$160 for the day** whether or not a single trade happens.
- Measured friction on the long side is **$4.26 per round trip**, and the best
  training result this project has ever produced was **+$4.72 per trade** — and
  that one failed its leak cut. A locate fee of $8 on a 100-share position is
  roughly twice the entire measured edge, on top of the friction.
- At 100 shares the arithmetic never improves by trading better. It improves
  only by trading larger, which is task #11 and unresolved.

**Rate levels on this population.** IBKR's own writing gives BYND at 54% and a
move from 34% to 195% in three days, and SBET at 1,000% (≈3% per day) during a
$3→$124 run. Those are the names our screen selects for. For a same-day flat
short the annualised rate is close to irrelevant; the **locate fee is the cost**,
and it scales with exactly the scarcity that makes the rate high.

## 3. Rule 201 (SSR) — it turns on when we would want to be short

Mechanics, from the SEC's Rule 201 FAQ:

- **Trigger:** the price falls 10% or more from the prior day's regular-hours
  close. Only regular-hours trades count toward the trigger.
- **Duration:** the remainder of that day **and the whole of the following day**.
- **The restriction:** a short sale may not be executed or displayed at a price
  at or below the current national best bid. You must post *above* the bid.
- **Hours:** the trigger only fires during RTH, but once on, the price test
  applies whenever an NBB is being disseminated — **including pre-market**.

Three consequences for this strategy specifically.

**A short entry becomes passive-only.** Under SSR you cannot take liquidity on
the offer side of a falling market; you rest above the bid and wait to be lifted.
The entry-latency measurement already found MCL fills sitting at p50 **0.86** of
the signal bar and MC5 at **0.78** — late, on the long side, where we *can* cross
the spread. SSR removes that option on the short side. Fills get later, or do not
happen, and the ones that do happen select for the moments the price came back up
to you — which is adverse selection by construction.

**The exit is also a short sale problem in reverse — but only the entry is
restricted.** Covering is a buy; Rule 201 does not restrict it. That asymmetry is
in our favour and is the one genuinely good news item here.

**The day-2 fade is the SSR day.** The setup a short would want in this universe
is the second-day dump after a first-day gap-and-run. A name that fell 10% intraday
on day 1 is restricted for the rest of day 1 *and all of day 2* — the exact
session we would be shorting into. This is not a rare edge case; it is the
central case, and it is measurable (see §8).

## 4. LULD, and its absence pre-market

LULD price bands operate **9:30–16:00 ET only** — no bands before 9:30 or after
16:00. Tier 2 parameters (our names are Tier 2): **10%** for a prior close above
$3.00, **20%** for $0.75–$3.00, doubled in the last 25 minutes.

For a short, this cuts both ways and both directions are bad:

- **In RTH:** a limit-up halt on a squeezing name freezes the position for a
  minimum of five minutes with no possible exit, and it reopens at an auction
  price set by whoever wanted in. The software-managed trailing stop cannot fire
  during a halt; it fires after, at the new price. On a 10% band that is a
  bounded-per-halt but repeatable loss, and halts can chain in 5-minute
  increments.
- **Pre-market:** no bands, no halts, and therefore no brake at all. A short in
  a thin 04:30 book has unlimited adverse excursion between one poll and the next.

## 5. Pre-market execution at IBKR — the three constraints compound

Outside RTH, IBKR takes **Day Limit orders only**; every stop in this system is
software-managed on a 1-second poll. Stack that with §3 and §4 and a pre-market
short has:

- no exchange-native stop (software poll only), and
- no LULD circuit breaker to cap a squeeze, and
- if SSR is on from yesterday — the central case — an entry that may only rest
  above the bid.

The one exit this project has evidence for is the trailing stop, and this is the
worst environment in which to run one. **Pre-market shorting should be treated as
closed at IBKR** regardless of how the borrow question resolves.

## 6. Capital: short margin on low-priced stock

FINRA Rule 4210(c) maintenance margin on short stock:

- under $5.00: **the greater of $2.50 per share or 100% of market value**
- $5.00 and above: **the greater of $5.00 per share or 30% of market value**

Our band is $2–25. Worked, 100 shares:

| Price | Short maintenance | Long Reg T initial (50%) |
|---:|---:|---:|
| $3 | $300 (100% of value) | $150 |
| $8 | $500 ($5/share) | $400 |
| $20 | $600 (30% of value) | $1,000 |

Between $2.50 and $5.00 a short ties up **exactly twice** the capital of the
same-size long (100% against 50%); from $5 to $10 the multiple falls from 2× to
1× as the $5/share floor binds; above $10 the short is the cheaper of the two.
Brokers routinely add house requirements on volatile small caps on top of this. It is the least of the five obstacles — it costs capital, not viability —
but it means any capacity or sizing work under task #11 cannot reuse the long
side's numbers.

## 7. What the source material says, for completeness

From `short_selling_source_comparison.md`: only four of six sources have a short
methodology at all, all four are mirror inversions of their long setups, and the
**two sources closest to this universe short neither of them** — S5 says on
camera that the method "wasn't really designed for traders who are trading to the
short side." That is weak evidence and is treated as such: these are hypothesis
generators, not results. It is noted only because it points the same way as the
mechanics.

## 8. Verdict, and the one measurement that would sharpen it

**Short selling this universe is not feasible at IBKR at any cost**, because the
broker refuses opening trades in these names. At a small-cap broker it is
mechanically possible and **economically implausible at 100 shares**, because the
locate fee is sunk before the signal and is of the same order as the entire
measured edge on the long side.

Nothing in this document depends on a short edge existing. If one were found
tomorrow, these constraints would still apply to it.

**What would change the verdict**, in order of cheapness:

1. **The TradeZero paper-parity question** (`tradezero_hybrid_probe.md` item 4) —
   a support email, still unsent, and it gates the whole broker branch.
2. **Real locate quotes on real candidates.** One morning of quoted per-share
   locate prices on the day's screen output, recorded and not traded, converts
   §2 from an example into a distribution. This is the single cheapest piece of
   evidence available and needs no code.
3. **Size.** Every per-trade figure here is a fixed cost against 100 shares. Task
   #11 decides whether the strategy is ever run larger; if it is not, §2 alone
   ends this.

**The measurement worth doing, if any of the above survive:** how often SSR would
actually be in force on the sessions we would want to short. Definition — for
each survivor symbol-day, the stock is SSR-restricted if the day's low is ≤ 90%
of the prior regular-session close (restricted from that print onward), or if the
*prior* day met that test (restricted all day). Inputs are prior close, day low
and the session calendar, all of which are in `bar_daily` on the SQL Server. I
have not run this — the daily bars are on your machine, not in this workspace —
and I have not written the query, because it should be built and tested rather
than pasted. It is small; say the word and it becomes a task.

**My reading:** the honest answer is that this was worth checking and the answer
is no. Item 2 above — one morning of locate quotes — is the only thing I would
spend time on before dropping the short side entirely, and it costs nothing but
attention.

---

Sources: SEC Division of Trading and Markets, Rule 201 FAQ; FINRA Rule 4210(c);
Nasdaq LULD FAQ; IBKR Short Sale Cost and SLB Availability documentation; IBKR
Traders' Insight, "The Risks of Shorting, Part II: Borrow Fees"; TradeZero,
"What Is a Short Locate?" and its short-selling product page. Project sources:
`ibkr_small_cap_restriction.md`, `tradezero_hybrid_probe.md`,
`short_selling_source_comparison.md`, `execution_cost_measured.md`,
`entry_latency_20260908.md`, `premarket_hypotheses_results_20260908.md`.
