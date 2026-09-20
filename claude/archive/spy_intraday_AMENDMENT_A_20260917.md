# AMENDMENT A to `spy_intraday_spec_20260917.md` — the venue assumption (PRE-RUN)

**Status: PRE-RUN.** Nothing in the SPY study has been built or run. This amends
the registration before any result exists, which is the only time a registration
may be amended.

**It amends §5 (friction) and §11 (sizing) only.** The rule (§3), the cells (§7),
the gates (§8), the holdout (§9) and the registered prediction (§10) are
**unchanged**.

Filed as a separate document rather than appended to the spec, per the
convention `REGISTERED_profit_floor_20260917.md` already uses for its own
amendment A.

---

## A.1 What prompted it

A tooling source (Miles Deutscher, `me5uegV7vOU`, 2026-09-16, a roundup of seven
GitHub repos — assessed in full, six of seven rejected) named the **Alpaca MCP**
as an execution layer. Chasing it down surfaced a defect in §5 of the spec that
is not about Alpaca at all:

**At Ben's account size, SPY friction is dominated by a fixed per-order minimum,
not by anything to do with the strategy.**

§5 already recorded this — *"the commission minimum is a small-account tax"* —
but treated it as an observation. It is a **venue-dependent parameter**, and the
spec fixed it silently by assuming IBKR.

---

## A.2 The arithmetic

SPY 754.05 (2026-09-16 close). A USD 10,000 account is **13 shares = $9,802.65**
notional. Regulatory fees (SEC + FINRA TAF on the sell) and the spread are
unavoidable at any venue; only the commission differs.

| venue | commission | reg fees | spread | total | **bps RT** |
|---|---:|---:|---:|---:|---:|
| **IBKR tiered** | $0.70 | $0.28 | $0.13 | $1.11 | **1.13** |
| **Alpaca (commission-free)** | $0.00 | $0.28 | $0.13 | $0.41 | **0.42** |

13 shares × $0.0035 is $0.046 of marginal commission; IBKR's $0.35 order minimum
charges **7.6× that**. It stops binding at 100 shares — **$75,405 of notional** —
so this is purely a small-account effect and disappears entirely as the account
grows.

**Effect on the strategy, same rule, same trades:**

| cell | IBKR | Alpaca |
|---|---:|---:|
| unconditional, net per trade | 1.52 bps | **2.23 bps** |
| unconditional, annualised | 3.82% | **5.62%** |
| high-vol tercile, annualised | 4.93% | 5.53% |
| unconditional, $/yr on $9,803 | $374 | **$551** |

**+47% on the unconditional cell, from a fee schedule.** Which is also the
warning: *a result that swings 47% on the venue assumption was never a robust
result.* That is what A.4 is for.

---

## A.3 What Alpaca is, verified

- Accepts **Australian residents**; $0 minimum; commission-free on US equities.
- **Has a genuine paper-trading API** — unlike Schwab, whose sandbox is synthetic
  data and whose API is live-accounts-only (`broker_api_comparison.md`, confirmed
  again 2026-09-17).
- SIPC-style protection, $500k securities / $250k cash.
- US securities only. Support is community forums.

**Unverified and load-bearing: execution quality.** Commission-free brokers
monetise order flow. For retail marketable orders in SPY, wholesalers frequently
give **price improvement**, which would make the effective spread *better* than
the displayed penny — or the routing could be worse. **Nothing here measures it
in either direction**, and the spread is 0.13 bps of a 0.42 bps total, so it is
not a large lever either way. Do not assume the improvement; do not assume the
harm.

---

## A.4 What changes in the registration

**§5's friction ladder gains a venue dimension, and the primary reading does not
move.**

| level | bps RT | venue assumption |
|---|---:|---|
| optimistic | 0.55 | ≥100 shares, passive/mid fills |
| **realistic (PRIMARY, unchanged)** | **1.15** | **IBKR, Ben's account today, crossing the spread** |
| pessimistic | 2.50 | wide 15:30 spread, partials, slippage |
| **reported, not scored** | **0.42** | **Alpaca, commission-free, same account** |

**The primary stays IBKR.** Three reasons, and the first is the one that matters:

1. **A cell that passes only at Alpaca's friction is a NOTHING.** This is the
   same rule §5 already applies to the optimistic level. A strategy whose verdict
   depends on a fee schedule we have not traded on has not been demonstrated.
2. IBKR is where the account, the data, `ib_async` and the paper trader are. It
   is the venue the study would actually be validated on.
3. Alpaca's execution quality is unmeasured (A.3).

**Report both columns on every cell.** It costs one column and it makes the
venue's contribution visible rather than baked in — the same reasoning
`friction_reconciliation_20260911.md` §6 gives for reporting all three levels.

**§11 gains one line.** If the strategy is ever taken live, the venue decision is
made *then*, on measured fills, not now on a fee schedule.

---

## A.5 What this does NOT apply to

**It does not help MCL, MC5 or VW9, and no one should propose it for them.**

Those books lose money **gross**. `friction_reconciliation_20260911.md` gives
break-even friction as **−$0.96/RT** for MCL on the screened universe and
**−$4.67/RT** for MC5 — they would have to be *paid* to break even. On the
point-in-time book MCL is (10.52)/trade at $4.26, i.e. **(6.26) gross**.
Removing every cent of commission moves that to about (5.9). Venue choice cannot
rescue a negative gross, and this amendment must not be read as reopening the
broker question settled in `broker_api_comparison.md`.

Separately, commission-free brokers commonly restrict low-float small caps, so
Alpaca is unlikely to be a candidate for that universe even if it helped.

**The distinction is the point:** friction matters for SPY because SPY's gross is
*positive and thin* — 43% of gross goes to friction at IBKR. It does not matter
for the small-cap books because their gross is negative. Same fee schedule,
opposite relevance.

---

## A.6 What settles the open question

When the SPY study reaches paper trading (months 3–9 of the schedule), run the
**same rule on both venues simultaneously** for one month and compare realised
fills against the reference price at 15:30 and 16:00. That is a direct
measurement of the thing A.3 cannot resolve from documentation, it costs nothing
but two paper accounts, and it also feeds the standing
quote-logging recommendation in `friction_reconciliation_20260911.md` §5 item 1.

Until then, Alpaca is **a reported column and a decision deferred**, not a
migration.

---

### Sources

- Alpaca, non-US residents: https://alpaca.markets/learn/live-trading-account-non-us · https://alpaca.markets/international
- Alpaca availability for Australian residents: https://brokerchooser.com/broker-reviews/alpaca-trading-review/alpaca-trading-australia
- Schwab sandbox is not paper trading: https://mylinedchart.com/resources/articles/schwab-api-for-technical-traders-workflow-fit-checklist
- Tooling source assessed: https://www.youtube.com/watch?v=me5uegV7vOU (read in full 2026-09-17)
