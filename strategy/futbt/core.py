#!/usr/bin/env python3
"""Shared plumbing for the two W15-0022 methods (CRUDELE-3S and BREIT-CAP).

Both registrations inherit the TL-v0 / TL-v1 program plumbing "unchanged" (REGISTERED_crudele_3s.md
sec 2.1, REGISTERED_breit_cap.md sec 2.1): daily bars from the difference-back-adjusted held
contract, ATR(14) Wilder, fills at the stated level or at the open if price gaps through it, a
stop and a target in one bar -> the stop first, $0.50 / $1.25 / $2.50 per contract per side plus
one tick on every stop fill, fractional book at $22,129 (the verdict) with the integer book
beside it, one position per market.

What this module adds (and why it does not simply call strategy.tl_v0.pnl):
  * a Frame: plain arrays for one market, built either from a TL-v0 MarketBars (daily) or from a
    htf CL 4-hour entry frame, so the two engines run on either without knowing which;
  * Trade2: tl_v0.sim.Trade plus tags (arm / grade / risk fraction) the reports slice on;
  * booking straight from the ADJUSTED fills. tl_v0.pnl.book proves the raw held-contract legs sum
    to the adjusted move, so gross = direction x qty x mult x (exit - entry) exactly; only the
    NUMBER of rolls in the trade is needed (two extra sides each). tl_v0.pnl.book also insists an
    entry is at the bar's open; a BREIT-CAP buy-stop fills inside the bar, so it cannot be used.
    A test pins this booking to tl_v0.pnl.book on trades that do fill at the open;
  * a daily mark-to-market on the adjusted closes (equals the trade list to the cent; tested).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14
from strategy.tl_v0.sim import Trade
from strategy.tl_v0.spec import EQUITY, FRICTION, LEVELS, Market

ATR_LEN = 14
FRAC_SIZING = ("frac", EQUITY)
INT_SIZING = ("int", EQUITY)
VERDICT_SIZINGS = (FRAC_SIZING, INT_SIZING)


@dataclass(frozen=True)
class Venue:
    """What is charged. `stop_slip_ticks` = one tick of the vehicle on every stop fill (daily
    TSMOM friction). The CL 4-hour friction (HTF-Ben v0 Amendment A) already includes the tick
    in its mid / high levels, so there it is 0."""
    friction: dict
    stop_slip_ticks: float = 1.0


DAILY_VENUE = Venue(dict(FRICTION), 1.0)


def cl4h_venue() -> Venue:
    from strategy.htf import costs as C
    return Venue({lv: C.per_side("MCL", lv) for lv in LEVELS}, 0.0)


@dataclass
class Frame:
    market: str
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    vol: np.ndarray                 # held-contract volume (NaN where unknown)
    rc: np.ndarray                  # raw held-contract close (price scale for ratios)
    roll_after: np.ndarray          # bool: position is moved to the next contract at j's close
    dates: pd.DatetimeIndex
    mult: float                     # $ per 1.00 of price, ONE vehicle contract
    tick_usd: float                 # $ per tick, ONE vehicle contract
    venue: Venue = DAILY_VENUE
    chart: str = "1D"

    @property
    def n(self) -> int:
        return len(self.c)

    @property
    def tick(self) -> float:
        return self.tick_usd / self.mult          # one tick in price units

    def atr(self) -> np.ndarray:
        a = atr14(self.h, self.l, self.c).astype(float)
        a[: ATR_LEN - 1] = np.nan                 # unknown for the first 13 bars (TL-v0 rule)
        return a


def attach_volume(frame_df: pd.DataFrame, rows: pd.DataFrame) -> np.ndarray:
    """Volume of the TRADED contract on each session of a TL-v0 bar frame. `rows` are the folded
    weekday rows (date, contract, volume). NaN where that contract printed no bar."""
    piv = rows.pivot(index="date", columns="contract", values="volume")
    out = np.full(len(frame_df), np.nan)
    cols = {c: i for i, c in enumerate(piv.columns)}
    arr = piv.reindex(pd.DatetimeIndex(frame_df["date"])).to_numpy(dtype=float)
    for j, c in enumerate(frame_df["contract"].to_numpy()):
        i = cols.get(c)
        if i is not None:
            out[j] = arr[j, i]
    return out


def frame_from_daily(mb, m: Market, vol: np.ndarray | None = None) -> Frame:
    f = mb.frame
    vol = np.full(len(f), np.nan) if vol is None else vol
    return Frame(m.name, f["open"].to_numpy(float), f["high"].to_numpy(float),
                 f["low"].to_numpy(float), f["close"].to_numpy(float), vol,
                 f["rc"].to_numpy(float), f["roll_after"].to_numpy(bool),
                 pd.DatetimeIndex(f["date"]), m.mult, m.tick_usd, DAILY_VENUE, "1D")


def load_market_v(archive, m: Market):
    """(Frame, MarketBars, notes): the TL-v0 daily loader (holdout cut first) plus volume. Ben's
    machine only (reads the archive)."""
    from strategy.tl_v0 import bars as B
    rows, contracts, _c0, note = B.load_rows(archive, m.signal_root)
    mb = B.build_bars(rows, contracts, m.root, m.name)
    mb.notes.update(note)
    vol = attach_volume(mb.frame, rows)
    return frame_from_daily(mb, m, vol), mb, mb.notes


def frame_from_4h(entry_frame: pd.DataFrame, m: Market) -> Frame:
    """A htf.bars.back_adjust()-ed 4H frame (CL, held contract) as a Frame. The position is
    carried through a roll when held_id changes between bar j and j+1."""
    e = entry_frame.reset_index(drop=True)
    held = e["held_id"].to_numpy()
    roll_after = np.zeros(len(e), bool)
    roll_after[:-1] = held[1:] != held[:-1]
    return Frame(m.name, e["open_adj"].to_numpy(float), e["high_adj"].to_numpy(float),
                 e["low_adj"].to_numpy(float), e["close_adj"].to_numpy(float),
                 e["volume"].to_numpy(float), e["close"].to_numpy(float), roll_after,
                 pd.DatetimeIndex(pd.to_datetime(e["t_open"])), m.mult, m.tick_usd,
                 cl4h_venue(), "4H")


# ---------------------------------------------------------------------------
# trades
# ---------------------------------------------------------------------------

@dataclass
class Trade2(Trade):
    arm: str = ""                 # CRUDELE: T / MR / C ; BREIT: B (or control tag)
    grade: int = -1
    risk_frac: float = 0.0
    k: int = 0                    # BREIT run length at entry
    d_atr: float = np.nan         # BREIT D / ATR[O]
    signal_j: int = -1
    atr_dist: float = np.nan      # stop distance in ATR units at the fill (random-entry controls)
    ep: int = -1                  # episode id (CRUDELE T episode / BREIT run id)


def size(risk_usd: float, dist: float, mult: float, integer: bool) -> float:
    if not (dist > 0) or not np.isfinite(dist):
        return 0.0
    q = risk_usd / (dist * mult)
    return float(np.floor(q + 1e-12)) if integer else float(q)


def book_trade(t: Trade, fr: Frame) -> dict:
    """gross / slip / sides and the three nets for one trade, from adjusted fills."""
    e, x = t.entry_j, t.exit_j
    rolls = int(fr.roll_after[e:x].sum()) if x > e else 0
    gross = t.direction * t.qty * fr.mult * (t.exit_px - t.entry_px)
    slip = fr.venue.stop_slip_ticks * fr.tick_usd * t.qty if t.stop_fill else 0.0
    sides = 2 + 2 * rolls
    out = dict(gross=gross, slip=slip, sides=sides, n_rolls=rolls)
    for lv in LEVELS:
        out["net_" + lv] = gross - slip - fr.venue.friction[lv] * t.qty * sides
    return out


def trade_rows(trades: list, fr: Frame, key: dict, risk_usd_of=None) -> list[dict]:
    d = fr.dates.to_numpy()
    rows = []
    for t in trades:
        b = book_trade(t, fr)
        row = dict(key)
        row.update(direction=t.direction, entry_date=d[t.entry_j], exit_date=d[t.exit_j],
                   entry_j=t.entry_j, exit_j=t.exit_j, hold=t.exit_j - t.entry_j,
                   entry_px=t.entry_px, exit_px=t.exit_px, stop_init=t.stop_init, qty=t.qty,
                   reason=t.reason, stop_fill=t.stop_fill, **b)
        for a in ("arm", "grade", "risk_frac", "k", "d_atr", "signal_j", "atr_dist", "ep"):
            if hasattr(t, a):
                row[a] = getattr(t, a)
        rows.append(row)
    return rows


def daily_marks(trades: list, fr: Frame) -> np.ndarray:
    """(n, 3) daily net at low/mid/high: each trade's P&L spread over the sessions it was open on
    the adjusted closes (equal to the raw held-contract marks: the adjustment offset is constant
    inside a contract and steps by exactly the roll gap). Costs land on the session they are paid."""
    c = fr.c
    n = fr.n
    gross = np.zeros(n)
    sides = np.zeros(n)
    slip = np.zeros(n)
    for t in trades:
        e, x, k = t.entry_j, t.exit_j, t.direction * t.qty * fr.mult
        if x == e:
            gross[e] += k * (t.exit_px - t.entry_px)
        else:
            gross[e] += k * (c[e] - t.entry_px)
            if x - e > 1:
                gross[e + 1:x] += k * (c[e + 1:x] - c[e:x - 1])
            gross[x] += k * (t.exit_px - c[x - 1])
        sides[e] += t.qty
        sides[x] += t.qty
        rl = np.nonzero(fr.roll_after[e:x])[0] + e
        for r in rl:
            sides[r] += 2 * t.qty
        if t.stop_fill:
            slip[x] += fr.venue.stop_slip_ticks * fr.tick_usd * t.qty
    out = np.empty((n, len(LEVELS)))
    for i, lv in enumerate(LEVELS):
        out[:, i] = gross - slip - fr.venue.friction[lv] * sides
    return out


def net_mid(trades: list, fr: Frame) -> float:
    return float(sum(book_trade(t, fr)["net_mid"] for t in trades))


# ---------------------------------------------------------------------------
# simple rolling helpers (all causal: value at j uses bars <= j)
# ---------------------------------------------------------------------------

def sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def bollinger(c: np.ndarray, n: int, sd: float):
    """Pine bb(): SMA(n) +/- sd x POPULATION standard deviation (ddof=0)."""
    s = pd.Series(c)
    m = s.rolling(n, min_periods=n).mean()
    d = s.rolling(n, min_periods=n).std(ddof=0)
    return m.to_numpy(), (m + sd * d).to_numpy(), (m - sd * d).to_numpy()


def stop_fill_long(o: float, stop: float) -> float:
    return min(o, stop)


def stop_fill_short(o: float, stop: float) -> float:
    return max(o, stop)
