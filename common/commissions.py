#!/usr/bin/env python3
"""
IBKR Australia commission model: Fixed vs Tiered, US stocks.

    python -m common.commissions                  # the comparison and crossover
    python -m common.commissions --applied        # against the real MCL trades
    python -m common.commissions --shares 200 --price 6.25

Source (fetched 2026-09-05):
  https://www.interactivebrokers.com.au/en/pricing/commissions-stocks.php?region=americas
  https://www.interactivebrokers.com/en/accounts/fees/INETstkfee.php
  https://www.interactivebrokers.com/en/accounts/fees/ARCAstkfee.php

WHY THIS MATTERS MORE THAN IT LOOKS
-----------------------------------
The backtest charges COMMISSION_PER_SHARE = 0.005 doubled for a round trip --
$1.00 on 100 shares. The live trader charges a flat COMMISSION_RT = 2.00. Both
are approximations of the Fixed plan and neither is right, and the gap between
them was already flagged as an unresolved inconsistency in
claude/repo_reorg_and_github_plan.md. This module replaces both guesses with
the published schedule.

It matters because MCL's edge is +$7.79/trade before friction and +$3.53 after.
A commission difference of even $0.50 per round trip is 14% of that margin.

THE DECISIVE FACT: MCL ALWAYS REMOVES LIQUIDITY
-----------------------------------------------
Tiered looks cheaper on the headline rate ($0.0035 vs $0.0050 per share) but
Tiered passes exchange fees through and Fixed absorbs them. This strategy sends
MARKETABLE limits -- priced through the touch by LIMIT_CROSS_BPS -- so it is
always TAKING liquidity and always pays the removal fee (~$0.0030/share on
NASDAQ and ARCA), never the add rebate. That single fact is what flips the
comparison as size grows:

    Fixed  all-in per share above the minimum:  $0.0050
    Tiered all-in per share (removing):         $0.0035 + $0.0030 + $0.0002
                                              = $0.0067

Tiered wins only while the Fixed $1.00 ORDER MINIMUM dominates -- i.e. at small
share counts. Above the crossover, Fixed is structurally cheaper for a
liquidity-taking strategy. A strategy that posted passive limits and earned the
add rebate would get the opposite answer.

SUB-DOLLAR STOCKS ARE CHEAPER ON TIERED, NOT A CLIFF
----------------------------------------------------
I expected a penalty here and the arithmetic says the opposite, so it is worth
stating plainly. Below USD 1.00 the exchange removal fee stops being $0.0030
per share and becomes 0.30% of TRADE VALUE. Those are identical at exactly
$1.00 (0.003 x $1.00 = $0.0030) and the percentage is SMALLER below it: at
$0.50 the fee is $0.0015/share, half the per-share rate.

The Fixed plan meanwhile runs into its own 1%-of-trade-value maximum on
low-value orders, which caps it but only after the $1.00 minimum has already
made it expensive relative to the position.

So on cheap stock Tiered's advantage widens rather than narrows. What sub-dollar
names actually cost you is spread, not commission -- GELS traded on 2026-09-03
at $0.935 with a 0.021% spread, but the universe median is 0.491%.

(Separately: GELS is outside the $2-20 band the backtest enforces, so the live
watchlist is not applying the same universe filter the backtest does. That is a
parity gap worth closing, and it is not a commission question.)
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass

# --- Fixed plan --------------------------------------------------------------
FIXED_PER_SHARE = 0.005
FIXED_MIN_ORDER = 1.00
FIXED_MAX_PCT = 0.01          # 1% of trade value
# Fixed includes exchange and clearing fees; only regulatory fees are extra.

# --- Tiered plan, <= 300,000 shares/month ------------------------------------
TIERED_PER_SHARE = 0.0035
TIERED_MIN_ORDER = 0.35
TIERED_MAX_PCT = 0.01
TIERED_CLEARING_PER_SHARE = 0.00020
# Exchange fee, REMOVING liquidity, >= $1.00. NASDAQ and ARCA both 0.0030.
TIERED_REMOVE_PER_SHARE = 0.0030
# Below $1.00 the removal fee becomes a percentage of trade value.
TIERED_REMOVE_SUB_DOLLAR_PCT = 0.0030
# Adding liquidity earns a rebate instead -- NASDAQ 0.0013, ARCA 0.0020.
# Not used by this strategy; kept so the alternative can be modelled.
TIERED_ADD_REBATE_PER_SHARE = 0.0013
TIERED_PASSTHROUGH = 0.000175 + 0.000563     # NYSE + FINRA, on commission

# --- Regulatory fees, charged under BOTH plans -------------------------------
SEC_FEE_PCT_OF_SALES = 0.0000206      # sells only
FINRA_TAF_PER_SHARE_SOLD = 0.000195   # sells only
CAT_FEE_PER_SHARE = 0.000003


@dataclass
class Cost:
    commission: float
    exchange: float
    clearing: float
    passthrough: float
    regulatory: float

    @property
    def total(self) -> float:
        return (self.commission + self.exchange + self.clearing
                + self.passthrough + self.regulatory)


def regulatory(qty: int, price: float, is_sell: bool) -> float:
    fee = CAT_FEE_PER_SHARE * qty
    if is_sell:
        fee += SEC_FEE_PCT_OF_SALES * qty * price
        fee += FINRA_TAF_PER_SHARE_SOLD * qty
    return fee


def fixed_cost(qty: int, price: float, is_sell: bool) -> Cost:
    value = qty * price
    comm = min(max(FIXED_PER_SHARE * qty, FIXED_MIN_ORDER), FIXED_MAX_PCT * value)
    return Cost(commission=comm, exchange=0.0, clearing=0.0, passthrough=0.0,
                regulatory=regulatory(qty, price, is_sell))


def tiered_cost(qty: int, price: float, is_sell: bool,
                removing: bool = True) -> Cost:
    value = qty * price
    comm = min(max(TIERED_PER_SHARE * qty, TIERED_MIN_ORDER), TIERED_MAX_PCT * value)
    if removing:
        exch = (TIERED_REMOVE_PER_SHARE * qty if price >= 1.0
                else TIERED_REMOVE_SUB_DOLLAR_PCT * value)
    else:
        exch = -TIERED_ADD_REBATE_PER_SHARE * qty if price >= 1.0 else 0.0
    return Cost(commission=comm, exchange=exch,
                clearing=TIERED_CLEARING_PER_SHARE * qty,
                passthrough=comm * TIERED_PASSTHROUGH,
                regulatory=regulatory(qty, price, is_sell))


# Legacy model: what every backtest charged before 2026-09-05 and what every
# published P/L in claude/*.md was computed with. Kept so those numbers stay
# reproducible -- a result that cannot be regenerated cannot be checked.
LEGACY_PER_SHARE = 0.005

# --- TradeZero America, US equities ------------------------------------------
# Sources fetched 2026-09-05:
#   https://tradezero.com/pricing-and-fees
#   https://tradezero.com/documents/bd95224babc94795a60119f543a15ca1bca36b87.pdf
#
# TWO SOURCES DISAGREE ON WHAT IS FREE, AND IT IS WORTH REAL MONEY.
#   the pricing PAGE says "Non-marketable limit orders only", NYSE/NASDAQ/AMEX,
#     above $1.00
#   the fee-schedule PDF says "All order types on NYSE, AMEX and NASDAQ stocks
#     above $1 from 7 AM to 8 PM ET"
# Those are very different for this project: MCL sends MARKETABLE limits, so
# under the page's wording nothing it does is ever free. TZ_FREE_REQUIRES_
# NON_MARKETABLE selects which reading to model. Default is the strict one,
# because assuming the favourable reading of an ambiguous fee schedule is how
# a backtest ends up optimistic. CONFIRM WITH TRADEZERO BEFORE RELYING ON IT.
TZ_FREE_REQUIRES_NON_MARKETABLE = True

TZ_PER_SHARE = 0.005
TZ_MIN_SUB_DOLLAR = 0.99
TZ_MAX_SUB_DOLLAR = 7.95
TZ_FREE_WINDOW = (7 * 60, 20 * 60)      # 07:00-20:00 ET, in minutes
TZ_FREE_MIN_PRICE = 1.00
# Charged whether or not the commission is free -- "free" is the commission,
# not the trade. Removing liquidity costs the ECN fee plus routing.
TZ_ECN_REMOVE_PER_SHARE = 0.0030
TZ_ROUTING_PER_SHARE = 0.0002
TZ_ADD_REBATE_PER_SHARE = 0.0032        # ARCA/NYSE; NASDAQ 0.00325, BATS 0.0016
TZ_TAF_PER_SHARE_SOLD = 0.000166
TZ_SEC_FEE_PCT = 0.0                    # $0 since 2025-05-14 per TZ's schedule

PLANS = ("ibkr_tiered", "ibkr_fixed", "tradezero", "legacy")


def tradezero_cost(qty: int, price: float, is_sell: bool,
                   minutes_et: int | None = None, removing: bool = True,
                   free_requires_non_marketable: bool | None = None) -> Cost:
    """One order on TradeZero America.

    minutes_et is the order time as minutes past midnight ET. It matters: the
    free window starts at 07:00, and MCL trades from 04:00, so a large part of
    what this strategy does falls in the PAID pre-market band regardless of
    listing venue or price.
    """
    if free_requires_non_marketable is None:
        free_requires_non_marketable = TZ_FREE_REQUIRES_NON_MARKETABLE
    value = qty * price
    in_window = (minutes_et is None
                 or TZ_FREE_WINDOW[0] <= minutes_et < TZ_FREE_WINDOW[1])
    # A marketable order can never qualify under the strict reading.
    qualifies = (price >= TZ_FREE_MIN_PRICE and in_window
                 and not (free_requires_non_marketable and removing))
    if qualifies:
        comm = 0.0
    elif price < TZ_FREE_MIN_PRICE:
        comm = min(max(TZ_PER_SHARE * qty, TZ_MIN_SUB_DOLLAR), TZ_MAX_SUB_DOLLAR)
    else:
        comm = TZ_PER_SHARE * qty
    exch = ((TZ_ECN_REMOVE_PER_SHARE + TZ_ROUTING_PER_SHARE) * qty if removing
            else -TZ_ADD_REBATE_PER_SHARE * qty)
    reg = TZ_TAF_PER_SHARE_SOLD * qty if is_sell else 0.0
    reg += TZ_SEC_FEE_PCT * value if is_sell else 0.0
    return Cost(commission=comm, exchange=exch, clearing=0.0,
                passthrough=0.0, regulatory=reg)


def order_cost(qty: int, price: float, is_sell: bool,
               plan: str = "ibkr_tiered", removing: bool = True,
               minutes_et: int | None = None) -> float:
    """Commission for ONE order, in dollars.

    This is the function backtests should call per transaction rather than
    multiplying a per-share constant at the end. It matters for two reasons:
    the plans have per-ORDER minimums, so cost is not linear in quantity, and
    the scale-out mechanic issues many orders per trade, where a per-trade
    approximation is badly wrong in a direction that flatters the strategy.
    """
    if qty <= 0:
        return 0.0
    if plan == "legacy":
        return LEGACY_PER_SHARE * qty
    if plan == "ibkr_fixed":
        return fixed_cost(qty, price, is_sell).total
    if plan == "ibkr_tiered":
        return tiered_cost(qty, price, is_sell, removing).total
    if plan == "tradezero":
        return tradezero_cost(qty, price, is_sell, minutes_et, removing).total
    raise ValueError(f"unknown commission plan {plan!r}; must be one of {PLANS}")


def round_trip(qty: int, price: float, plan: str, removing: bool = True) -> float:
    """Buy then sell the same quantity at the same price. The sell carries the
    SEC and FINRA charges, the buy does not."""
    plan = {"fixed": "ibkr_fixed", "tiered": "ibkr_tiered"}.get(plan, plan)
    return (order_cost(qty, price, False, plan, removing)
            + order_cost(qty, price, True, plan, removing))


def crossover(price: float, removing: bool = True, hi: int = 2000) -> int | None:
    """Smallest share count at which Fixed becomes cheaper than Tiered."""
    prev = None
    for q in range(1, hi + 1):
        cheaper = round_trip(q, price, "fixed", removing) <= round_trip(q, price, "tiered", removing)
        if prev is False and cheaper:
            return q
        prev = cheaper
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="IBKR AU Fixed vs Tiered, US stocks")
    ap.add_argument("--shares", type=int)
    ap.add_argument("--price", type=float)
    ap.add_argument("--applied", action="store_true",
                    help="score both plans against the real MCL trade set")
    ap.add_argument("--adding", action="store_true",
                    help="model posting passive liquidity instead of taking it")
    a = ap.parse_args()
    removing = not a.adding

    if a.shares and a.price:
        for plan in ("fixed", "tiered"):
            c = (fixed_cost(a.shares, a.price, False) if plan == "fixed"
                 else tiered_cost(a.shares, a.price, False, removing))
            s = (fixed_cost(a.shares, a.price, True) if plan == "fixed"
                 else tiered_cost(a.shares, a.price, True, removing))
            print(f"\n  {plan.upper()} — {a.shares} sh @ ${a.price:.2f} "
                  f"(${a.shares*a.price:,.2f} per side)")
            for lbl, cc in (("buy", c), ("sell", s)):
                print(f"    {lbl:<5} commission {cc.commission:>6.3f}  exch {cc.exchange:>6.3f}  "
                      f"clear {cc.clearing:>6.3f}  pass {cc.passthrough:>6.4f}  "
                      f"reg {cc.regulatory:>6.4f}   = {cc.total:>6.3f}")
            print(f"    ROUND TRIP {c.total + s.total:>6.3f}")
        return 0

    print(f"\n{'='*86}")
    print(f"  IBKR AU, US stocks — round-trip cost, "
          f"{'REMOVING' if removing else 'ADDING'} liquidity")
    print(f"{'='*86}")
    print(f"  {'shares':>7} " + "".join(f"{f'${p:g}':>17}" for p in (2, 5, 10, 20)))
    print(f"  {'':>7} " + "".join(f"{'fixed':>8}{'tiered':>9}" for _ in range(4)))
    print("  " + "-"*80)
    for q in (50, 100, 150, 200, 300, 500, 1000):
        row = f"  {q:>7} "
        for p in (2, 5, 10, 20):
            fx = round_trip(q, p, "fixed", removing)
            td = round_trip(q, p, "tiered", removing)
            mark = "*" if td < fx else " "
            row += f"{fx:>8.2f}{td:>8.2f}{mark}"
        print(row)
    print("\n  * = Tiered cheaper. Crossover share count, by price:")
    for p in (2, 5, 10, 20):
        x = crossover(p, removing)
        if x:
            print(f"      ${p:>2g}: Fixed becomes cheaper at {x} shares")
        else:
            # No crossover found. Which side wins is NOT implied by that --
            # disambiguate rather than print a default that could be backwards.
            who = ("Tiered" if round_trip(100, p, "tiered", removing)
                   < round_trip(100, p, "fixed", removing) else "Fixed")
            print(f"      ${p:>2g}: {who} cheaper at every size tested")

    print(f"\n  Per-share all-in above the order minimum:")
    print(f"    Fixed                        ${FIXED_PER_SHARE:.4f}")
    if removing:
        t = TIERED_PER_SHARE + TIERED_REMOVE_PER_SHARE + TIERED_CLEARING_PER_SHARE
        print(f"    Tiered (removing liquidity)  ${t:.4f}"
              f"  = {TIERED_PER_SHARE} comm + {TIERED_REMOVE_PER_SHARE} exch "
              f"+ {TIERED_CLEARING_PER_SHARE} clearing")
    else:
        t = TIERED_PER_SHARE - TIERED_ADD_REBATE_PER_SHARE + TIERED_CLEARING_PER_SHARE
        print(f"    Tiered (adding liquidity)    ${t:.4f}  — the rebate flips it")

    print(f"\n  SUB-DOLLAR: below $1.00 the Tiered removal fee becomes")
    print(f"  {TIERED_REMOVE_SUB_DOLLAR_PCT:.2%} of TRADE VALUE rather than $0.0030/share --")
    print(f"  equal at exactly $1.00 and SMALLER below it, so Tiered's edge widens.")
    for p in (0.50, 0.95, 1.00):
        print(f"    100 sh @ ${p:.2f}: fixed {round_trip(100,p,'fixed'):.2f}  "
              f"tiered {round_trip(100,p,'tiered'):.2f}")

    if a.applied:
        from pathlib import Path
        from common.analysis import load_sessions, run, LIVE
        sess = load_sessions(Path("bar_cache"))
        trades = run(sess, LIVE)
        modelled = sum(t.commission for t in trades)
        fx = sum(round_trip(t.qty, t.entry_price, "fixed") for t in trades)
        td = sum(round_trip(t.qty, t.entry_price, "tiered", removing) for t in trades)
        n = len(trades)
        print(f"\n{'='*86}")
        print(f"  APPLIED TO THE REAL MCL TRADE SET ({n} trades, 373 sessions)")
        print(f"{'='*86}")
        print(f"  {'model':<34} {'total':>12} {'per trade':>12}")
        print("  " + "-"*60)
        print(f"  {'backtest assumption (0.005 x 2)':<34} {modelled:>12,.2f} {modelled/n:>12.4f}")
        print(f"  {'IBKR Fixed':<34} {fx:>12,.2f} {fx/n:>12.4f}")
        print(f"  {'IBKR Tiered (removing)':<34} {td:>12,.2f} {td/n:>12.4f}")
        print(f"\n  Fixed vs Tiered: {td-fx:+,.2f} over the set "
              f"({(td-fx)/n:+.4f}/trade) — {'Tiered' if td<fx else 'Fixed'} is cheaper")
        print(f"  The backtest UNDERSTATES the true cost by "
              f"${min(fx,td)-modelled:,.2f} (${(min(fx,td)-modelled)/n:.4f}/trade).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
