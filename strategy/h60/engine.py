#!/usr/bin/env python3
"""H60 book construction: signals -> entries -> exits -> trades.
W14-0003, REGISTERED_h60_v0.md §2.1-§2.3.

WHAT DECIDES WHETHER A SIGNAL BECOMES A TRADE, IN ORDER
-------------------------------------------------------
    warm-up      no signal in the first WARMUP_SESSIONS sessions of the
                 symbol's own series (§2.2: 30 sessions; a name that joins the
                 index later has no bars before it joined, so its warm-up
                 starts there too)
    fill exists  the next bar exists (a signal on the symbol's last bar is
                 dropped)
    membership   a member on the SIGNAL session and on the FILL session
                 (Spell.covers, §2.1)
    $5 floor     the fill price (§2.1)
    stop         a rule that needs a resting stop and has none is dropped;
                 a fill at or below its own stop is VOID (never holdable)
    one at a time one position per symbol per book; a new entry needs a bar
                 that OPENED AFTER the last exit -- fill index > exit index
    session cap  VW9-60 only: at most 4 entries per signal session
    shares       floor(notional / fill price); zero shares is a skip

Every reason a signal did not become a trade is counted.

The exits of all candidates are computed in one vectorised call BEFORE the
one-at-a-time walk. That is exact, not an approximation: an exit depends only
on its own entry bar and the prices after it, never on another trade.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from strategy.h60 import exits as X
from strategy.h60.panel import Panel, SymArrays, slice_arrays
from strategy.h60.rules import Book, RuleOut, RULES

WARMUP_SESSIONS = 30
PRICE_FLOOR = 5.0

TRADE_COLUMNS = [
    "book", "rule", "symbol", "code", "sig_idx", "fill_idx", "exit_idx",
    "s_signal", "s_entry", "s_exit", "entry_session", "exit_session",
    "entry_t", "exit_t", "entry_slot", "exit_slot", "entry_px", "exit_px",
    "qty", "notional", "gross", "reason", "phase", "stop_fill", "bars_held",
    "sessions_held", "nights", "entry_mark", "exit_mark",
]


def warm(a: SymArrays, sessions: int = WARMUP_SESSIONS) -> np.ndarray:
    """True on bars AFTER the symbol's first `sessions` sessions."""
    first = np.r_[True, a.s[1:] != a.s[:-1]]
    rank = np.cumsum(first) - 1
    return rank >= sessions


def candidates(a: SymArrays, out: RuleOut, counts: Counter,
               notional: float | None = None) -> dict:
    """Signal bars that survive every per-bar filter, with fill and stop.
    With `notional`, a fill price that buys zero shares is dropped HERE,
    before the one-at-a-time walk -- a trade that cannot be placed must not
    block the next one (the first draft dropped it after the walk)."""
    sig = np.flatnonzero(out.entry)
    counts["signals"] += len(sig)
    w = warm(a)
    keep = w[sig]
    counts["warmup"] += int((~keep).sum())
    sig = sig[keep]
    has_fill = sig + 1 < a.n
    counts["no_fill_bar"] += int((~has_fill).sum())
    sig = sig[has_fill]
    fill = sig + 1
    member = a.eligible[sig] & a.eligible[fill]
    counts["not_member"] += int((~member).sum())
    sig, fill = sig[member], fill[member]
    px = a.o[fill]
    floor_ok = px >= PRICE_FLOOR
    counts["below_floor"] += int((~floor_ok).sum())
    sig, fill, px = sig[floor_ok], fill[floor_ok], px[floor_ok]
    if notional is not None:
        can = np.floor(notional / px) >= 1
        counts["zero_shares"] += int((~can).sum())
        sig, fill, px = sig[can], fill[can], px[can]
    stop = None
    if out.spec.fixed_stop:
        stop = np.asarray(out.stop(sig, px), float) if len(sig) else np.zeros(0)
        ok = np.isfinite(stop)
        counts["no_stop"] += int((~ok).sum())
        sig, fill, px, stop = sig[ok], fill[ok], px[ok], stop[ok]
    return {"sig": sig, "fill": fill, "stop": stop}


def walk(sig, fill, res: X.ExitResult, session_of_sig, session_cap, counts: Counter):
    """The one-at-a-time selection. Returns positions (into the candidate
    arrays) of the entries taken."""
    taken = []
    last_exit = -1
    per_session: Counter = Counter()
    for i in range(len(sig)):
        if res.void[i]:
            counts["void_beyond_stop"] += 1
            continue
        if fill[i] <= last_exit:
            counts["in_position"] += 1
            continue
        s = int(session_of_sig[i])
        if session_cap is not None and per_session[s] >= session_cap:
            counts["session_cap"] += 1
            continue
        taken.append(i)
        per_session[s] += 1
        last_exit = int(res.exit_idx[i])
    return np.array(taken, dtype=np.int64)


def trades_for_symbol(panel: Panel, sym: str, book: Book, rule_fn=None,
                      counts: Counter | None = None) -> pd.DataFrame:
    """One symbol's trades, one SEGMENT at a time (panel.SEGMENT_GAP). Trade
    indices (sig_idx, fill_idx, exit_idx) are returned in the symbol's FULL
    bar numbering, so panel.arrays(sym) reads them back."""
    counts = Counter() if counts is None else counts
    full = panel.arrays(sym)
    fn = rule_fn or RULES[book.rule]
    parts = []
    for st, en in panel.segment_bounds(sym):
        a = full if (st, en) == (0, full.n) else slice_arrays(full, st, en)
        df = _segment_trades(panel, a, book, fn, counts)
        if len(df):
            for c in ("sig_idx", "fill_idx", "exit_idx"):
                df[c] = df[c] + st
            if en < full.n:
                seg = (df["reason"] == X.REASONS[X.R_DATA_END]) & (df["exit_idx"] == en - 1)
                df.loc[seg, "reason"] = X.SEGMENT_END
            parts.append(df)
    if not parts:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    counts["trades"] += len(df)
    return df


def _segment_trades(panel: Panel, a: SymArrays, book: Book, fn, counts: Counter) -> pd.DataFrame:
    out = fn(a, book.variant)
    cand = candidates(a, out, counts, notional=book.notional)
    sig, fill = cand["sig"], cand["fill"]
    if len(sig) == 0:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    res = X.simulate(a, fill, out.spec, fixed_stop=cand["stop"], xsig=out.xsig,
                     ratchet=out.ratchet, atr_prev=out.atr_prev)
    pick = walk(sig, fill, res, a.s[sig], out.session_cap, counts)
    if len(pick) == 0:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    return frame(panel, a, book, sig[pick], res, pick)


def frame(panel: Panel, a: SymArrays, book: Book, sig, res: X.ExitResult,
          pick) -> pd.DataFrame:
    fill = res.fill_idx[pick]
    ex = res.exit_idx[pick]
    epx = res.fill_px[pick]
    xpx = res.exit_px[pick]
    qty = np.floor(book.notional / epx).astype(np.int64)
    s_e, s_x = a.s[fill], a.s[ex]
    ses = panel.sessions
    ent_day = [ses[i] for i in s_e]
    ex_day = [ses[i] for i in s_x]
    sub = X.ExitResult(fill, epx, ex, xpx, res.phase[pick], res.reason[pick],
                       res.void[pick])
    return pd.DataFrame({
        "book": book.name, "rule": book.rule, "symbol": a.symbol,
        "code": [panel.universe.code_on(a.symbol, d) for d in ent_day],
        "sig_idx": sig, "fill_idx": fill, "exit_idx": ex,
        "s_signal": a.s[sig], "s_entry": s_e, "s_exit": s_x,
        "entry_session": ent_day, "exit_session": ex_day,
        "entry_t": a.t[fill], "exit_t": a.t[ex],
        "entry_slot": a.bar[fill], "exit_slot": a.bar[ex],
        "entry_px": epx, "exit_px": xpx, "qty": qty,
        "notional": qty * epx, "gross": qty * (xpx - epx),
        "reason": [X.REASONS[r] for r in sub.reason],
        "phase": sub.phase, "stop_fill": sub.stop_fill,
        "bars_held": ex - fill, "sessions_held": s_x - s_e,
        "nights": [(x - e).days for e, x in zip(ent_day, ex_day)],
        "entry_mark": X.entry_mark(a, sub), "exit_mark": X.exit_mark(a, sub),
    }, columns=TRADE_COLUMNS)


def run_book(panel: Panel, book: Book, symbols=None, rule_fn=None):
    """All trades of one book over the panel. Returns (trades, counts)."""
    counts: Counter = Counter()
    parts = []
    for sym in (symbols or panel.symbols):
        df = trades_for_symbol(panel, sym, book, rule_fn, counts)
        if len(df):
            parts.append(df)
    trades = (pd.concat(parts, ignore_index=True) if parts
              else pd.DataFrame(columns=TRADE_COLUMNS))
    return trades, counts


def run_books(panel: Panel, books, symbols=None, *, progress=None) -> dict:
    """Several books in one pass, SYMBOL BY SYMBOL: every book of one rule set
    sees a symbol back to back, so the rule's cached core (rules._memo) is
    computed once per symbol rather than once per exit variant. Returns
    {book name: (trades, counts)} or {name: ("not run", reason)} for a rule
    whose registration is incomplete (rules.NotRegistered)."""
    from strategy.h60.rules import NotRegistered
    books = list(books)
    parts: dict = {b.name: [] for b in books}
    counts: dict = {b.name: Counter() for b in books}
    refused: dict = {}
    syms = list(symbols or panel.symbols)
    for i, sym in enumerate(syms):
        for bk in books:
            if bk.name in refused:
                continue
            try:
                df = trades_for_symbol(panel, sym, bk, None, counts[bk.name])
            except NotRegistered as e:
                refused[bk.name] = str(e).split(".")[0]
                continue
            if len(df):
                parts[bk.name].append(df)
        if progress and (i + 1) % progress == 0:
            print(f"  {i + 1}/{len(syms)} symbols", flush=True)
    out = {}
    for bk in books:
        if bk.name in refused:
            out[bk.name] = ("not run", refused[bk.name])
        else:
            out[bk.name] = ((pd.concat(parts[bk.name], ignore_index=True)
                             if parts[bk.name] else pd.DataFrame(columns=TRADE_COLUMNS)),
                            counts[bk.name])
    return out


# --------------------------------------------------------------------------
# concurrency (§2.3) -- reported, never scored
# --------------------------------------------------------------------------

def concurrency(trades: pd.DataFrame) -> dict:
    """Max concurrent positions and the capital they tied up. A position
    occupies [entry mark, exit mark]; an exit and an entry at the same mark
    count the exit first."""
    if trades.empty:
        return {"max_concurrent": 0, "max_capital": 0.0}
    ev = np.concatenate([
        np.stack([trades["entry_mark"].to_numpy(), np.ones(len(trades)),
                  trades["notional"].to_numpy()], 1),
        np.stack([trades["exit_mark"].to_numpy(), -np.ones(len(trades)),
                  -trades["notional"].to_numpy()], 1)])
    order = np.lexsort((ev[:, 1], ev[:, 0]))   # exits (-1) before entries
    ev = ev[order]
    n = np.cumsum(ev[:, 1])
    cap = np.cumsum(ev[:, 2])
    return {"max_concurrent": int(n.max()), "max_capital": float(cap.max())}


def capped_book(trades: pd.DataFrame, cap: int = 2) -> pd.DataFrame:
    """§2.3's reported-never-scored book: at most `cap` positions at once,
    first come first served. Ties at the same entry mark are broken by a
    crc32 of (symbol, session) -- not alphabetically, which would favour
    early-alphabet names."""
    import zlib
    if trades.empty:
        return trades
    key = [zlib.crc32(f"{s}|{d}".encode("utf-8"))
           for s, d in zip(trades["symbol"], trades["entry_session"])]
    t = trades.assign(_k=key).sort_values(["entry_mark", "_k"], kind="mergesort")
    open_exits: list[int] = []
    keep = []
    for i, (em, xm) in enumerate(zip(t["entry_mark"], t["exit_mark"])):
        open_exits = [x for x in open_exits if x > em]
        if len(open_exits) < cap:
            keep.append(i)
            open_exits.append(xm)
    return t.iloc[keep].drop(columns="_k").reset_index(drop=True)


def voids_from_splits(trades: pd.DataFrame, split_days: set) -> np.ndarray:
    """§2.3: a trade whose hold spans a split date is voided and counted.
    split_days: {(symbol, session_index)} -- the first session on the new
    share basis."""
    if trades.empty or not split_days:
        return np.zeros(len(trades), bool)
    by: dict = {}
    for sym, s in split_days:
        by.setdefault(sym, []).append(s)
    out = np.zeros(len(trades), bool)
    for i, (sym, se, sx) in enumerate(zip(trades["symbol"], trades["s_entry"],
                                          trades["s_exit"])):
        for s in by.get(sym, ()):
            if se < s <= sx:
                out[i] = True
                break
    return out


def touches_days(trades: pd.DataFrame, days: set) -> np.ndarray:
    """Trades whose SIGNAL session or any held session is one of
    {(symbol, session_index)} -- a 15:30 signal read off a bad day is as bad
    as a hold across one, though its fill is the next session."""
    if trades.empty or not days:
        return np.zeros(len(trades), bool)
    by: dict = {}
    for sym, s in days:
        by.setdefault(sym, set()).add(s)
    return np.array([any(s in by.get(sym, ()) for s in range(int(sg), int(sx) + 1))
                     for sym, sg, sx in zip(trades["symbol"], trades["s_signal"],
                                            trades["s_exit"])], dtype=bool)


def qty_for(notional: float, px: float) -> int:
    return int(math.floor(notional / px)) if px > 0 else 0
