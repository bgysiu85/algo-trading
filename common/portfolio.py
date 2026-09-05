#!/usr/bin/env python3
"""Portfolio backtest: one account, shared buying power, a concurrency cap.

    python -m common.portfolio --capital 5000 --per-trade-pct 60
    python -m common.portfolio --verify        # equivalence vs the per-session engine

WHY THIS EXISTS, AND WHAT IT SAYS ABOUT EVERY EARLIER NUMBER
------------------------------------------------------------
Every backtest in this project until now ran ONE symbol-date at a time, in
isolation. Three things follow, and none of them were visible in the output:

  * Capital was infinite. A session with four simultaneous signals took all
    four, at 100 shares each, whatever the account could actually fund.
  * Concurrency was unlimited. brokers/ibkr/trader.py has enforced
    MAX_CONCURRENT_POSITIONS = 2 since 2026-09-05; the backtest never has.
  * Size was flat. MAX_SHARES = 100 regardless of price, so a $2 stock and a
    $19 stock committed $200 and $1,900 of the same account.

So the published trade counts are not achievable on a real account, and this
module is the first thing here that says what IS.

THE SIZING RULE (Ben, 2026-09-05)
---------------------------------
    capital            $5,000
    per trade          up to 60% of capital
    while a position is open, whatever buying power REMAINS caps the next one

So the per-trade cap is min(60% x capital, buying power available now) -- not
60% of what remains, which would let position three take 60% of a shrunken
number and quietly re-lever. Two trades can be open at 60% and 40%; a third
cannot open at all, which is the cap doing its job rather than a bug.

HOW THE WALK WORKS
------------------
Sessions are grouped by DATE and stepped in timestamp order. At each timestamp
exits are processed before entries, so capital freed by a close is available to
an open in the same minute. That is the optimistic reading of a tie and it is
flagged rather than hidden -- live, the exit fill and the entry decision are
seconds apart, not simultaneous.

WHAT THIS STILL CANNOT SEE
--------------------------
  * CAPACITY. Sizing from capital means 1,500 shares of a $2 stock where the
    old model bought 100. The fill model prices all of them identically, which
    is false for a sub-20m-float small cap in pre-market. Every capital-sized
    number below is optimistic by an unmeasured amount that GROWS with size.
  * RUIN. The book never goes bankrupt. A run that loses more than the
    starting capital keeps trading; a real account would be flat and closed.

When several symbols signal at the same timestamp and capital cannot fund them
all, they are taken in a deterministic order (see ENTRY_ORDER). Which one wins
is arbitrary in the backtest and is NOT arbitrary live, where common/tv_feed.py
ranks the watchlist and the trader walks it in order. Sensitivity to that
choice is reported, because if it matters a lot then the result depends on
something the backtest is inventing.
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from common.commissions import order_cost
from strategy.mcl import mcl as MCL
from strategy.mc5 import mc5 as MC5

ET = ZoneInfo("America/New_York")

# Measured live 2026-09-03, charged per share transacted.
SLIP_PER_SHARE = (0.0590 - 0.0164) / 2

# Deterministic tie-break when capital cannot fund every simultaneous signal.
# Alphabetical is arbitrary; that is the point, and its impact is measured.
ENTRY_ORDER = "symbol"


class Book:
    """One account across all symbols on one date."""

    def __init__(self, capital: float, per_trade_pct: float,
                 max_positions: int, compound: bool, fixed_qty: int = 0):
        self.start = capital
        self.cash = capital
        self.per_trade_pct = per_trade_pct
        self.max_positions = max_positions
        self.compound = compound
        # Equivalence mode: reproduce the per-session engine's flat MAX_SHARES
        # instead of sizing from capital. Needed because "unlimited capital"
        # cannot be expressed as a huge number -- at 100% per trade the first
        # entry takes the whole balance and starves every later one, which is
        # what made the first verification run report 459 trades against 485.
        self.fixed_qty = fixed_qty
        self.open: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.rejected_capital = 0
        self.rejected_slots = 0

    @property
    def equity_base(self) -> float:
        """What 60% is 60% OF. Fixed at the starting capital unless compounding
        -- letting the cap grow with profits is a second, separate decision
        from position sizing, and mixing them makes neither measurable."""
        return self.cash if self.compound else self.start

    def can_open(self) -> bool:
        return len(self.open) < self.max_positions

    def size(self, price: float) -> int:
        if self.fixed_qty:
            return self.fixed_qty
        cap = min(self.per_trade_pct / 100.0 * self.equity_base, self.cash)
        return max(0, math.floor(cap / price)) if price > 0 else 0

    def enter(self, symbol, ts, price, qty, plan):
        cost = price * qty
        comm = order_cost(qty, price, False, plan)
        self.cash -= cost + comm
        self.open[symbol] = dict(ts=ts, price=price, qty=qty, commission=comm,
                                 peak=price, cost=cost)

    def exit(self, symbol, ts, price, reason, plan):
        p = self.open.pop(symbol)
        proceeds = price * p["qty"]
        comm = order_cost(p["qty"], price, True, plan)
        self.cash += proceeds - comm
        gross = (price - p["price"]) * p["qty"]
        total_comm = p["commission"] + comm
        self.trades.append(dict(
            symbol=symbol, entry_ts=p["ts"], exit_ts=ts, qty=p["qty"],
            entry=p["price"], exit=price, reason=reason,
            gross=gross, commission=total_comm, net=gross - total_comm,
            real=gross - total_comm - 2 * p["qty"] * SLIP_PER_SHARE,
            notional=p["cost"]))


def prepare_date(sessions_for_date, strat, band):
    """Per symbol: its in-session bars with signals, keyed by timestamp."""
    out = {}
    for symbol, date_str, df in sessions_for_date:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        try:
            if strat is MC5:
                frame = df if MC5._looks_5m(df) else MC5.to_5m(df)
                sig = MC5.signals(frame)
            else:
                sig = MCL.signals(df, require_macd_pos=LIVE.get("require_macd_pos"))
        except Exception:
            continue
        local = sig.index.tz_convert(ET)
        keep = [i for i, (dt, t) in enumerate(zip(local.date, local.time))
                if dt == d and strat.SESSION_START <= t < strat.SESSION_END]
        if not keep:
            continue
        rows = sig.reset_index()
        tcol = rows.columns[0]
        out[symbol] = {rows.iloc[i][tcol]: rows.iloc[i] for i in keep}
    return out


def run_date(by_symbol, book: Book, strat, band, trail_pct, plan):
    """Step every symbol on this date together, in timestamp order."""
    stamps = sorted({ts for m in by_symbol.values() for ts in m})
    # PER-SYMBOL last bar, not the date's last bar. Symbols on the same date do
    # not all have the same number of bars -- a thin name's session ends
    # earlier -- and the per-session engine closes each position at ITS OWN
    # final bar. Using the date-wide last timestamp closed short sessions late
    # and broke equivalence (459 trades against 485).
    last_of = {sym: max(m) for sym, m in by_symbol.items() if m}

    for ts in stamps:
        # --- exits first, so freed capital can fund an entry this bar -------
        # A symbol that exits here may NOT re-enter at the same timestamp. The
        # per-session engine cannot do it (it tests `pos is None` at the top of
        # the bar, so an exit is only visible from the next one), and neither
        # can a live trader that has just sent a sell. Allowing it added 14
        # MCL trades and 167 MC5 ones out of nowhere.
        exited_now: set[str] = set()
        for symbol in list(book.open):
            row = by_symbol.get(symbol, {}).get(ts)
            if row is None:
                continue
            pos = book.open[symbol]
            trail = pos["peak"] * (1.0 - trail_pct / 100.0)
            exit_px = reason = None
            if float(row["low"]) <= trail:
                # Gap-through: cannot sell at a level the bar never offered.
                fill = min(trail, float(row["open"]))
                exit_px, reason = fill - strat.SLIPPAGE_TICKS * strat.TICK, "trailing_stop"
            elif ts == last_of.get(symbol):
                exit_px, reason = (float(row["close"]) - strat.SLIPPAGE_TICKS * strat.TICK,
                                   "window_close")
            elif strat is MC5 and bool(row.get("exit_sig", False)):
                exit_px, reason = (float(row["close"]) - strat.SLIPPAGE_TICKS * strat.TICK,
                                   "gradient_reversal")
            if exit_px is not None:
                book.exit(symbol, ts, exit_px, reason, plan)
                exited_now.add(symbol)
            else:
                pos["peak"] = max(pos["peak"], float(row["high"]))

        # --- then entries ---------------------------------------------------
        # No entry on a symbol's LAST bar. Buying at 09:29 to be flat at 09:30
        # is a guaranteed loss of spread and two commissions, and there is no
        # bar left to manage the position on.
        #
        # It also happens to be what the per-session engine does, though by
        # accident rather than design: it CREATES the position on the final bar
        # and then the loop ends, so the position is never exited and the trade
        # is silently dropped from the output. Worth recording as a latent
        # issue in that engine -- a position that opens and vanishes -- but
        # matching it here is both equivalent and correct.
        firing = sorted(sym for sym, m in by_symbol.items()
                        if sym not in book.open and sym not in exited_now
                        and ts in m and ts != last_of.get(sym)
                        and bool(m[ts]["entry"]))
        for symbol in firing:
            if not book.can_open():
                book.rejected_slots += 1
                continue
            row = by_symbol[symbol][ts]
            px = float(row["close"]) + strat.SLIPPAGE_TICKS * strat.TICK
            if band and not (strat.PRICE_MIN <= px <= strat.PRICE_MAX):
                continue
            qty = book.size(px)
            if qty < 1:
                book.rejected_capital += 1
                continue
            book.enter(symbol, ts, px, qty, plan)

    # Anything still open at the end of the date is closed at its last bar.
    for symbol in list(book.open):
        m = by_symbol.get(symbol, {})
        if not m:
            book.open.pop(symbol)
            continue
        ts = max(m)
        px = float(m[ts]["close"]) - strat.SLIPPAGE_TICKS * strat.TICK
        book.exit(symbol, ts, px, "window_close", plan)


def simulate(sessions, strat, capital, per_trade_pct, max_positions,
             compound=False, trail_pct=None, band=True, fixed_qty=0):
    by_date = defaultdict(list)
    for s in sessions:
        by_date[s[1]].append(s)
    trail_pct = trail_pct if trail_pct is not None else strat.TRAIL_PCT
    plan = strat.COMMISSION_PLAN

    cash = capital
    all_trades, rej_cap, rej_slot = [], 0, 0
    for date_str in sorted(by_date):
        book = Book(cash if compound else capital, per_trade_pct,
                    max_positions, compound, fixed_qty)
        run_date(prepare_date(by_date[date_str], strat, band), book,
                 strat, band, trail_pct, plan)
        all_trades.extend(book.trades)
        rej_cap += book.rejected_capital
        rej_slot += book.rejected_slots
        if compound:
            cash = book.cash
    return all_trades, rej_cap, rej_slot, cash


# --- reporting ---------------------------------------------------------------

def summarise(tag, trades, rej_cap, rej_slot, capital, final=None):
    if not trades:
        print(f"  {tag:<30} no trades")
        return
    by_sym = defaultdict(float)
    for t in trades:
        by_sym[t["symbol"]] += t["real"]
    net = sum(by_sym.values())
    top = sorted(by_sym.values(), reverse=True)
    qty = [t["qty"] for t in trades]
    notional = [t["notional"] for t in trades]
    win = sum(1 for v in by_sym.values() if v > 0)
    print(f"  {tag:<30}{len(trades):>5}${net:>9,.0f}"
          f"${net/len(trades):>8.2f}${net-sum(top[:3]):>9,.0f}"
          f"${net-sum(top[:5]):>9,.0f}{win:>4}/{len(by_sym):<4}"
          f"{min(qty):>5}-{max(qty):<6}${max(notional):>8,.0f}"
          f"{100*net/capital:>8.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="Portfolio backtest")
    ap.add_argument("--capital", type=float, default=5000.0)
    ap.add_argument("--per-trade-pct", type=float, default=60.0)
    ap.add_argument("--max-positions", type=int, default=2)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    sessions = load_sessions(Path("bar_cache"))
    print(f"{len(sessions)} sessions. Honest fills, peak from entry price, "
          f"measured friction.\n")

    if a.verify:
        # Unlimited capital and unlimited slots must reproduce the per-session
        # engine. Without this the sizing numbers below are unanchored.
        for strat, name in ((MCL, "MCL"), (MC5, "MC5")):
            tr, _c, _s, _f = simulate(sessions, strat, 1e12, 100.0, 10_000,
                                      fixed_qty=strat.MAX_SHARES)
            kw = dict(**LIVE) if strat is MCL else dict(enforce_price_band=True)
            ref = []
            for sym, d, df in sessions:
                try:
                    ref += strat.backtest_session(
                        df, datetime.strptime(d, "%Y-%m-%d").date(), ET, **kw)
                except Exception:
                    pass
            same = len(tr) == len(ref)
            pn = sum(t["net"] for t in tr)
            rn = sum(t.net for t in ref)
            same = same and abs(pn - rn) < 0.5
            print(f"  {name}: portfolio {len(tr)} trades ${pn:,.2f} vs "
                  f"per-session {len(ref)} ${rn:,.2f} — "
                  f"{'MATCH' if same else 'DIFFER'}")
        return 0

    hdr = (f"  {'configuration':<30}{'tr':>5}{'real':>10}{'per':>9}"
           f"{'drop3':>10}{'drop5':>10}{'syms':>9}{'shares':>12}"
           f"{'max notl':>9}{'ret':>9}")
    for strat, name in ((MCL, "MCL"), (MC5, "MC5")):
        print(f"{name}  —  capital ${a.capital:,.0f}, "
              f"{a.per_trade_pct:.0f}% per trade, max {a.max_positions} open")
        print(hdr)
        tr, rc, rs, _f = simulate(sessions, strat, 1e12, 100.0, 10_000,
                                  fixed_qty=strat.MAX_SHARES)
        summarise("flat 100sh, no cap (old)", tr, rc, rs, a.capital)
        for mp in (1, 2, 3):
            tr, rc, rs, _f = simulate(sessions, strat, a.capital,
                                      a.per_trade_pct, mp)
            summarise(f"${a.capital:,.0f}, max {mp} position(s)",
                      tr, rc, rs, a.capital)
            if mp == a.max_positions:
                print(f"    rejected: {rc} for capital, {rs} for the position cap")
        # Compounding is reported but should not be read as a projection: it
        # multiplies a hindsight-selected universe by itself, and the
        # simulation never goes bankrupt -- a drawdown past the starting
        # capital keeps trading where a real account would be flat and closed.
        tr, rc, rs, fin = simulate(sessions, strat, a.capital, a.per_trade_pct,
                                   a.max_positions, compound=True)
        summarise("...compounding (see caveat)", tr, rc, rs, a.capital)
        print(f"    final equity ${fin:,.0f} from ${a.capital:,.0f} — "
              f"NOT a projection, see the module docstring\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
