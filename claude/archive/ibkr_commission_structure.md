# IBKR Australia commissions — Fixed vs Tiered, US stocks

Worked 2026-09-05. Model and tool: `common/commissions.py`
(`python -m common.commissions [--applied] [--adding] [--shares N --price P]`).

**Answer: use Tiered at the current 100-share size. It saves $0.66 per round
trip, which is 21% of MCL's surviving margin. Switch to Fixed above 150
shares.**

Sources, fetched 2026-09-05:
[IBKR AU commissions — stocks](https://www.interactivebrokers.com.au/en/pricing/commissions-stocks.php?region=americas),
[NASDAQ/Island fees](https://www.interactivebrokers.com/en/accounts/fees/INETstkfee.php),
[NYSE ARCA fees](https://www.interactivebrokers.com/en/accounts/fees/ARCAstkfee.php).

---

## 1. The two schedules

| | **Fixed** | **Tiered** (≤300k shares/month) |
|---|---|---|
| commission | $0.005/share | $0.0035/share |
| minimum per order | **$1.00** | **$0.35** |
| maximum per order | 1% of trade value | 1% of trade value |
| exchange fees | **included** | **passed through** |
| clearing | included | $0.00020/share |
| pass-through | — | commission × 0.000738 |
| regulatory | extra | extra |

Tiered volume tiers below $0.0035 need >300,000 shares/month. At ~500 trades a
year × 100 shares that is not remotely in reach, so **$0.0035 is the rate** and
the other tiers are irrelevant.

Regulatory fees are identical on both plans and small: SEC $0.0000206 × sale
value, FINRA TAF $0.000195/share sold, CAT $0.000003/share. About $0.03 per
100-share round trip.

## 2. The fact that decides it

**MCL always removes liquidity.** `marketable_limit()` prices through the touch
by `LIMIT_CROSS_BPS`, so every order takes liquidity and pays the exchange
removal fee — **$0.0030/share** on both NASDAQ and ARCA. It never earns the add
rebate ($0.0013 NASDAQ, $0.0020 ARCA).

That inverts the headline comparison:

| all-in per share, above the order minimum | |
|---|---:|
| Fixed | **$0.0050** |
| Tiered, **removing** liquidity | $0.0035 + $0.0030 + $0.0002 = **$0.0067** |
| Tiered, *adding* liquidity (not this strategy) | $0.0035 − $0.0013 + $0.0002 = **$0.0024** |

So Tiered's cheaper headline rate is more than undone by the exchange fee.
**Tiered only wins while Fixed's $1.00 order minimum dominates** — i.e. at small
share counts.

## 3. Round-trip cost, and the crossover

Buy + sell, same size, both plans, removing liquidity:

| shares | $2 | | $5 | | $10 | | $20 | |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| | fixed | tiered | fixed | tiered | fixed | tiered | fixed | tiered |
| 50 | 2.01 | **1.03** | 2.02 | **1.04** | 2.02 | **1.04** | 2.03 | **1.05** |
| **100** | 2.02 | **1.36** | 2.03 | **1.37** | 2.04 | **1.38** | 2.06 | **1.40** |
| 150 | 2.04 | 2.05 | 2.05 | 2.06 | 2.06 | 2.07 | 2.09 | 2.10 |
| 200 | **2.05** | 2.73 | **2.06** | 2.74 | **2.08** | 2.76 | **2.12** | 2.80 |
| 300 | **3.07** | 4.09 | **3.09** | 4.11 | **3.12** | 4.14 | **3.18** | 4.21 |
| 500 | **5.12** | 6.82 | **5.15** | 6.85 | **5.20** | 6.91 | **5.31** | 7.01 |
| 1000 | **10.24** | 13.65 | **10.30** | 13.71 | **10.41** | 13.81 | **10.61** | 14.02 |

**The crossover is 150 shares, and it is the same at every price in the band.**
That is not a coincidence — both plans are per-share above their minimums, so
the crossing point depends only on the minimums and the per-share rates, not on
price. Price only matters through the 1% cap, which binds on low-value orders.

## 4. Applied to the real trade set

496 MCL trades over 373 cached sessions, priced at their actual entries:

| model | total | per trade |
|---|---:|---:|
| what the backtest assumes (0.005 × 2) | $496.00 | $1.0000 |
| **IBKR Tiered (removing)** | **$681.54** | **$1.3741** |
| IBKR Fixed | $1,008.65 | $2.0336 |

**Tiered saves $327.10 over the set, $0.66/trade.**

And the backtest understates true commission by **$0.374/trade** even on the
cheaper plan. Carried through to the edge:

| | commission/trade | net edge after $4.26 slippage |
|---|---:|---:|
| backtest assumption | $1.0000 | +$3.53 |
| **IBKR Tiered** | $1.3741 | **+$3.16** |
| IBKR Fixed | $2.0336 | +$2.50 |

The Fixed→Tiered switch is worth **+$0.66/trade against a $3.16 margin — 21% of
what survives.** That is a larger, more certain improvement than any strategy
parameter tested in this project, and it requires no backtest to believe.

## 5. Two things this interacts with

**The pyramiding idea crosses the boundary.** The scale-out mechanic with
`rebuy_qty=100` grows the position toward ~200 shares, which is past the 150
crossover. If that is ever shipped, the plan question reopens — and because the
mechanic also multiplies the number of *orders*, each of which pays the $0.35
Tiered minimum or $1.00 Fixed minimum, the per-order minimum starts to dominate
everything. Model it with `common/commissions.py` before, not after.

**Posting passive limits would flip the answer entirely.** At the add rebate
Tiered costs $0.0024/share all-in against Fixed's $0.0050 — Tiered wins at
every size tested. This strategy cannot do that (it needs to take liquidity to
get filled on a signal), but any future variant that rests orders should
re-derive this. `--adding` models it.

## 6. A correction worth recording

I expected sub-dollar stocks to be a Tiered penalty and the arithmetic says the
opposite. Below $1.00 the removal fee stops being $0.0030/share and becomes
**0.30% of trade value** — identical at exactly $1.00 (0.003 × $1.00 = $0.0030)
and *smaller* below it. At $0.50 it is $0.0015/share, half the per-share rate.
So Tiered's advantage widens on cheap stock rather than narrowing.

What sub-dollar names actually cost is spread, not commission.

## 7. Unrelated finding, flagged here because it surfaced here

**GELS traded live on 2026-09-03 at $0.935 — outside the $2–20 band the
backtest enforces.** So the live watchlist is not applying the same universe
filter as the backtest. That is a parity gap of the same kind as VW9's missing
price band, and it means live and backtest are not trading the same universe.
Worth closing before the next session.

---

## What to change in the code

- `strategy/mcl/mcl.py`: `COMMISSION_PER_SHARE = 0.005` understates Tiered by
  ~37%. Either use `common.commissions.round_trip()` or raise the constant.
- `brokers/ibkr/trader.py`: `COMMISSION_RT = 2.00` flat is roughly the Fixed
  cost at 100 shares and about 46% too high for Tiered. It also does not scale
  with quantity, which the scale-out mechanic would break badly.
- These two disagreeing with each other was already a known open item in
  `repo_reorg_and_github_plan.md`; this doc supplies the number that settles it.
