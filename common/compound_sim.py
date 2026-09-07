#!/usr/bin/env python3
"""Replay a trade ledger against a compounding account.

    python -m common.compound_sim --round-trips var/reports/flex_round_trips.csv \
        --strategy mcl mc5 vw9_5m --reports var/reports/matched \
        --capital 10000 --per-trade-pct 60 --total-pct 100 \
        --dollar-volume var/reports/day_dollar_volume.csv --dv-cap-pct 1.0

WHY THIS IS NOT A BACKTEST FLAG
--------------------------------
Every other sizing in this project is decided per symbol-day, up front, and the
engine runs each day independently. Compounding cannot work that way: a trade's
size depends on what earlier trades earned and on what is still open when it
fires. It is path-dependent, and the path runs across symbols, not within one.

So this replays the trades the engine already produced, in time order, against
a capital ledger. That is exact rather than approximate for the strategies,
because with scaling off a trade is one buy and one sell at known prices:
gross = qty x (exit - entry), so re-sizing is arithmetic, not re-simulation.

WHAT IT CANNOT KNOW, AND THEREFORE ASSUMES
-------------------------------------------
1. THAT A BIGGER ORDER FILLS AT THE SAME PRICE. It would not. These are $2-20
   small caps and the account compounds, so position sizes grow without limit
   while the stocks do not. --dv-cap-pct caps a position at a share of that
   symbol-day's dollar volume; run it both ways and the GAP between the two is
   the measurement -- it says at what account size the strategy stops scaling.
   Uncapped alone is arithmetic, not a forecast.

2. THAT EQUITY IS CASH PLUS COST BASIS. Open positions are held at cost, never
   marked to market, because a trade record has an entry and an exit and
   nothing in between. So the account cannot size up on an unrealised gain --
   conservative, and the direction to be wrong in.

3. THAT COMMISSION SCALES. For a strategy it is recomputed exactly with
   common.commissions.order_cost at the new quantity. For Ben's own trades it
   is scaled linearly from what he actually paid, which preserves his real
   execution habit (a median 24 fills a day) rather than pretending he would
   have used one order. Linear is close above IBKR's per-order minimum --
   measured at $0.67 for 100 shares and $6.71 for 1,000 -- and wrong below it.

4. THAT EVERY TRADE THE STRATEGY TOOK WOULD STILL HAVE BEEN TAKEN. Capital can
   only ever make it take FEWER: a trade with no funding is skipped and
   counted, never resized to something the rules did not ask for.

THE ORDER OF EVENTS
--------------------
Positions are opened in entry order and closed when their exit time passes. On
a tie the symbol breaks it, so a run is reproducible. Capital is released at
the exit, which means a strategy that holds through the morning funds fewer
concurrent trades than one that scalps -- that is a real property of the
strategy and it is the main thing this simulation measures.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from common.commissions import order_cost

ET = "America/New_York"

# Every strategy in this project prices at ibkr_tiered. Named here rather than
# passed as None, because order_cost() rejects None and the failure would only
# show up at the first fill of a long run.
COMMISSION_PLAN = "ibkr_tiered"


@dataclass
class Leg:
    """One tradeable opportunity, before it is sized."""
    source: str
    symbol: str
    date: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    pnl_per_share: float
    # Ben's only: what he actually paid, and on how many shares, so the cost
    # can be scaled rather than re-modelled.
    ref_shares: float = 0.0
    ref_cost: float = 0.0
    recompute_cost: bool = True


@dataclass
class Fill:
    """One sized position, after the ledger has decided what it could afford."""
    leg: Leg
    shares: int
    basis: float
    gross: float
    cost: float
    net: float
    capital_before: float
    capital_after: float
    dv_capped: bool = False


@dataclass
class Result:
    fills: list = field(default_factory=list)
    # THREE reasons a signalled trade is not taken, and they mean opposite
    # things. Concurrency says the RULE is too concentrated to hold the
    # strategy's overlapping positions -- a finding about the parameters.
    # Ruined says the account is gone -- a finding about the edge. Rolled into
    # one "skipped" figure, a run that was blocked by concurrency reads exactly
    # like a run that went broke.
    skipped_concurrency: int = 0     # capital committed elsewhere
    skipped_too_small: int = 0       # budget could not buy one share
    skipped_ruined: int = 0          # equity at or below zero
    dv_capped: int = 0
    initial: float = 0.0
    final: float = 0.0
    peak: float = 0.0
    max_drawdown: float = 0.0
    equity: list = field(default_factory=list)   # (timestamp, capital)

    @property
    def taken(self) -> int:
        return len(self.fills)

    @property
    def skipped_no_capital(self) -> int:
        return (self.skipped_concurrency + self.skipped_too_small
                + self.skipped_ruined)

    @property
    def multiple(self) -> float:
        return self.final / self.initial if self.initial else 0.0


def _ts(date_str: str, hhmm: str) -> datetime | None:
    if not hhmm or ":" not in hhmm:
        return None
    try:
        return datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _iso_to_et(stamp: str) -> datetime | None:
    """A strategy entry/exit stamp (UTC, from the engine) as naive ET.

    Naive ET throughout: every leg is converted the same way, so ordering and
    arithmetic are consistent, and no timezone maths happens twice.
    """
    import pandas as pd
    try:
        t = pd.Timestamp(stamp)
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        return None
    return t.tz_convert(ET).tz_localize(None).to_pydatetime()


def strategy_legs(path: Path, source: str) -> list[Leg]:
    out = []
    if not path.exists():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            a, b = _iso_to_et(r.get("entry_time", "")), _iso_to_et(r.get("exit_time", ""))
            if a is None or b is None:
                continue
            ep, xp = float(r["entry_price"]), float(r["exit_price"])
            if ep <= 0:
                continue
            out.append(Leg(source=source, symbol=r["symbol"], date=r["date"],
                           entry_ts=a, exit_ts=max(a, b), entry_price=ep,
                           exit_price=xp, pnl_per_share=xp - ep))
    return out


def my_legs(path: Path) -> list[Leg]:
    """Ben's round trips as legs.

    pnl_per_share divides realised P/L by the PEAK position, because that is
    the quantity the account had to fund and therefore the one a capital rule
    sizes. Where he scaled in and out the money was not all earned on the peak,
    so this is an approximation -- named here rather than buried.
    """
    out = []
    if not path.exists():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            mx = float(r.get("max_position") or 0)
            ep = float(r.get("avg_buy_price") or 0)
            if mx <= 0 or ep <= 0:
                continue
            a = _ts(r["date"], r.get("entry_et", ""))
            b = _ts(r["date"], r.get("exit_et", "")) or a
            if a is None:
                continue
            gross = float(r["gross_pnl"])
            out.append(Leg(source="mine", symbol=r["symbol"], date=r["date"],
                           entry_ts=a, exit_ts=max(a, b), entry_price=ep,
                           exit_price=float(r.get("avg_sell_price") or ep),
                           pnl_per_share=gross / mx,
                           ref_shares=mx,
                           ref_cost=abs(float(r["commission"])),
                           recompute_cost=False))
    return out


def simulate(legs: list[Leg], capital: float, per_trade_pct: float,
             total_pct: float, dollar_volume: dict | None = None,
             dv_cap_pct: float = 1.0,
             commission_plan: str = COMMISSION_PLAN) -> Result:
    """Replay one source's legs against a compounding account.

    per_trade_pct  the most any ONE position may take, as a % of equity
    total_pct      the most that may be deployed at once, as a % of equity

    With 60 and 100 the first position takes 60% and the second 40%. If the
    first only manages 40% -- share rounding, or a dollar-volume cap -- the
    second may take up to its own 60%, limited by the cash actually free. That
    is the "per-trade cap plus total cap" reading, not two fixed slots.
    """
    legs = sorted(legs, key=lambda x: (x.entry_ts, x.symbol, x.exit_ts))
    res = Result(initial=capital, final=capital, peak=capital)
    equity = capital
    open_pos: list[tuple[datetime, float, float]] = []   # (exit, basis, net)
    deployed = 0.0
    res.equity.append((None, equity))

    def close_through(when):
        nonlocal equity, deployed
        open_pos.sort(key=lambda p: p[0])
        while open_pos and (when is None or open_pos[0][0] <= when):
            _x, basis, net = open_pos.pop(0)
            deployed -= basis
            equity += net
            res.peak = max(res.peak, equity)
            res.max_drawdown = max(res.max_drawdown,
                                   (res.peak - equity) / res.peak
                                   if res.peak > 0 else 0.0)
            res.equity.append((_x, equity))

    for leg in legs:
        close_through(leg.entry_ts)
        if equity <= 0:
            res.skipped_ruined += 1
            continue
        budget = min(per_trade_pct / 100.0 * equity,
                     total_pct / 100.0 * equity - deployed,
                     equity - deployed)
        if budget <= 0:
            res.skipped_concurrency += 1
            continue
        shares = math.floor(budget / leg.entry_price)
        capped = False
        if dollar_volume is not None:
            dv = dollar_volume.get((leg.symbol, leg.date))
            if dv:
                lim = math.floor(dv * dv_cap_pct / 100.0 / leg.entry_price)
                if lim < shares:
                    shares, capped = lim, True
        if shares < 1:
            # Distinguish a capped-to-nothing trade from a broke account: the
            # first is a liquidity finding, the second an equity one.
            if capped:
                res.skipped_too_small += 1
            elif deployed > 0:
                res.skipped_concurrency += 1
            else:
                res.skipped_too_small += 1
            continue

        basis = shares * leg.entry_price
        gross = shares * leg.pnl_per_share
        if leg.recompute_cost:
            cost = (order_cost(shares, leg.entry_price, False, commission_plan)
                    + order_cost(shares, leg.exit_price, True, commission_plan))
        else:
            # Scaled from what he actually paid, so his own execution habit
            # travels with the trade rather than being replaced by a model.
            cost = leg.ref_cost * (shares / leg.ref_shares)
        net = gross - cost
        res.fills.append(Fill(leg=leg, shares=shares, basis=basis, gross=gross,
                              cost=cost, net=net, capital_before=equity,
                              capital_after=equity + net, dv_capped=capped))
        if capped:
            res.dv_capped += 1
        deployed += basis
        open_pos.append((leg.exit_ts, basis, net))

    close_through(None)
    res.final = equity
    return res


def sweep(legs, capital, per_grid, total_grid, **kw) -> list[dict]:
    """Every (per-trade, total) pair, so the ratio is measured not guessed."""
    out = []
    for p in per_grid:
        for t in total_grid:
            if t < p:
                continue        # a total below the per-trade cap is the same
                                # experiment as total == per-trade, run twice
            r = simulate(legs, capital, p, t, **kw)
            out.append({"per_trade_pct": p, "total_pct": t,
                        "final": r.final, "multiple": r.multiple,
                        "max_drawdown": r.max_drawdown, "taken": r.taken,
                        "skipped": r.skipped_no_capital,
                        "dv_capped": r.dv_capped})
    return out


def load_dollar_volume(path: Path) -> dict:
    out = {}
    if not path or not Path(path).exists():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                out[(r["symbol"], r["date"])] = float(r["dollar_volume"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def render(results: dict, capital, per_trade_pct, total_pct, capped) -> list[str]:
    L = [f"COMPOUNDING FROM ${capital:,.0f}   "
         f"per-trade {per_trade_pct:.0f}%   total {total_pct:.0f}%"
         + ("   (dollar-volume capped)" if capped else "   (UNCAPPED)"), "",
         f"  {'source':<10} {'taken':>7} {'concur':>7} {'ruined':>7} "
         f"{'tiny':>6} {'dv cap':>7} {'final':>13} {'x':>8} {'max DD':>8}",
         "  " + "-" * 78]
    for src, r in results.items():
        L.append(f"  {src:<10} {r.taken:>7} {r.skipped_concurrency:>7} "
                 f"{r.skipped_ruined:>7} {r.skipped_too_small:>6} "
                 f"{r.dv_capped:>7} {r.final:>13,.0f} {r.multiple:>7.2f}x "
                 f"{r.max_drawdown*100:>7.1f}%")
    L += ["",
          "  concur  the capital was committed to other open positions. This",
          "          is a finding about the RATIO, not about the strategy: it",
          "          says the rule is too concentrated to hold what the",
          "          strategy signals at once.",
          "  ruined  the account was gone. A finding about the edge.",
          "  tiny    the budget could not buy a single share. With nothing",
          "          else open this is practical ruin -- a losing account",
          "          decays geometrically and asymptotes rather than crossing",
          "          zero, so it lands here and not in 'ruined'.",
          "",
          "  Rolled into one number these read identically, and a run blocked",
          "  by concurrency looks exactly like one that went broke.",
          "",
          "  Capital can only ever make a run take FEWER trades. Nothing here",
          "  invents a trade the strategy did not signal.", ""]
    if not capped:
        L += ["  UNCAPPED. Position sizes are pure capital arithmetic and take",
              "  no account of whether a $2-20 small cap could absorb them. As",
              "  the account compounds this stops being a forecast and becomes",
              "  a description of a market that does not exist. Read it beside",
              "  the capped run; the GAP is the finding.", ""]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compounding-capital replay")
    ap.add_argument("--round-trips", default="var/reports/flex_round_trips.csv")
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--reports", default="var/reports")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--per-trade-pct", type=float, default=60.0)
    ap.add_argument("--total-pct", type=float, default=100.0)
    ap.add_argument("--dollar-volume", default="",
                    help="CSV of symbol,date,dollar_volume for the liquidity cap")
    ap.add_argument("--dv-cap-pct", type=float, default=1.0)
    ap.add_argument("--commission-plan", default=COMMISSION_PLAN)
    ap.add_argument("--sweep", action="store_true",
                    help="grid over both percentages instead of one run")
    ap.add_argument("--out", default="var/reports/compound_sim.csv")
    ap.add_argument("--report", default="var/reports/compound_sim.txt")
    a = ap.parse_args(argv)

    legs = {"mine": my_legs(Path(a.round_trips))}
    for n in a.strategy:
        legs[n] = strategy_legs(Path(a.reports) / f"backtest_trades_{n}.csv", n)
    dv = load_dollar_volume(Path(a.dollar_volume)) if a.dollar_volume else None

    lines = []
    if a.sweep:
        grid = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        rows = []
        for src, ls in legs.items():
            for r in sweep(ls, a.capital, grid, grid, dollar_volume=dv,
                           dv_cap_pct=a.dv_cap_pct):
                rows.append({"source": src, **r})
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {a.out}  ({len(rows)} parameter combinations)")
        lines = ["RATIO SWEEP", "",
                 "  Best (per-trade %, total %) by final capital, per source:", ""]
        for src in legs:
            mine = [r for r in rows if r["source"] == src and r["taken"]]
            if not mine:
                continue
            b = max(mine, key=lambda r: r["final"])
            lines.append(f"  {src:<10} {b['per_trade_pct']:>3.0f}% / "
                         f"{b['total_pct']:>3.0f}%   ${b['final']:>12,.0f}   "
                         f"maxDD {b['max_drawdown']*100:.1f}%")
        lines += ["",
                  "  A grid maximum is the most overfit number a sweep can",
                  "  produce. Read the surface, not the peak: if the cells",
                  "  around the best one fall away sharply, the best one is",
                  "  noise. PROGRAM_INDEX section 4."]
    else:
        results = {src: simulate(ls, a.capital, a.per_trade_pct, a.total_pct,
                                 dollar_volume=dv, dv_cap_pct=a.dv_cap_pct,
                                 commission_plan=a.commission_plan)
                   for src, ls in legs.items()}
        lines = render(results, a.capital, a.per_trade_pct, a.total_pct,
                       bool(dv))

    from common.report_io import emit
    emit("\n".join(lines), a.report, header="common.compound_sim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
