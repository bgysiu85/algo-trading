#!/usr/bin/env python3
"""H60 controls. W14-0003, REGISTERED_h60_v0.md §4.

§4.1 RANDOM ENTRIES, SAME EXIT (the selection control)
------------------------------------------------------
For each book: on each session, the same number of entries it took, on
random eligible names at random bars of that session, exited by THAT book's
own exit; 1,000 draws, seeded with zlib.crc32 (never hash(), PROGRAM_INDEX
§5). A rule set must beat the draws' 95th percentile of market-relative net
per trade (L2).

How, so that 1,000 draws cost seconds rather than days: every eligible
(symbol, bar) pair of the training side is priced ONCE through the same
engine.candidates filters and the same exits.simulate the book used, with
the rule's `stop_any` in place of its setup-specific stop (a random bar has
no setup: ORB's range low is that session's, VW9's structure is the lowest
low of the session's last six bars, TL's is the support line or its
fallback). A draw is then only an index sample. Pairs a real entry could not
have taken (no fill bar, not a member, under $5, no stop, opened beyond its
stop, zero shares) are never drawn.

    name first, then bar: each session, a name is drawn uniformly from the
    names with at least one valid bar, then a bar uniformly from that name's
    valid bars -- "random eligible names at random bars of that session".

    A property of that literal reading, recorded rather than changed: the
    draws use all seven bars, while ORB-60 and VW9-60 can only signal on some
    of them. Random fills therefore include 09:30 opens (7.98 bps spread
    against ~3 later) and overnight gaps those rules never take, which drags
    the draws down and makes criterion 6 slightly EASIER for them. The report
    prints each book's entries by bar beside the control so this is visible.

§4.3 POSITIVE CONTROL (gate G7)
-------------------------------
On a copy of the bars: a seeded 1% of eligible symbol-days is flagged; on
those, every price AFTER the 10:30 open is raised by exactly 20 bps (the
10:30 bar's high, low and close, and every later bar). A rule that buys the
flagged names at the 10:30 open and sells at the 16:00 close must show a
market-relative GROSS of +$20.00 +/- $2.00 per trade; on the unaltered bars
the same rule must show $0.00 +/- $2.00. The 10:30 open itself is left
alone: raising it too would hand the planted step to the entry price and the
rule could not capture it. On the fallback grid the second bar opens at
10:00 and plays the 10:30 bar's role.

The tolerance is the registration's. With ~1% of ~900 names over ~1,700
training sessions the standard error of the mean is about $1, so +/-$2 is
roughly two standard errors: a correct harness fails it about one run in
twenty by chance alone. That is written here so a failure is read as
"investigate", and not re-cut into a pass.
"""
from __future__ import annotations

import dataclasses
import zlib
from collections import Counter

import numpy as np
import pandas as pd

from strategy.h60 import costs as C
from strategy.h60 import engine as E
from strategy.h60 import exits as X
from strategy.h60.basket import Basket
from strategy.h60.panel import Panel, slice_arrays
from strategy.h60.rules import Book, RuleOut, RULES

N_DRAWS = 1000
PC_RATE = 0.01
PC_BPS = 20.0
PC_SLOT = 1              # the 10:30 bar (primary) / the 10:00 bar (fallback)
PC_TARGET = 20.0
PC_TOL = 2.0


def seed(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in ("H60",) + parts).encode("utf-8"))


# --------------------------------------------------------------------------
# §4.1 random entries
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Pairs:
    """Every drawable (symbol, signal bar) of one book, already priced."""
    sym: np.ndarray        # symbol id
    s_sig: np.ndarray      # session index of the signal bar
    mr_net: np.ndarray     # market-relative net $ at L2
    names: list


def _hits(days_by_sym: dict, sym: str, lo, hi, *, open_lo: bool) -> np.ndarray:
    """Per pair: does any listed session fall in (lo, hi] (open_lo) or [lo, hi]?"""
    d = days_by_sym.get(sym)
    if d is None or len(d) == 0:
        return np.zeros(len(lo), bool)
    upto_hi = np.searchsorted(d, hi, side="right")
    upto_lo = np.searchsorted(d, lo, side="right" if open_lo else "left")
    return upto_hi > upto_lo


def _by_sym(days) -> dict:
    out: dict = {}
    for sym, s in (days or ()):
        out.setdefault(sym, []).append(int(s))
    return {k: np.array(sorted(v)) for k, v in out.items()}


def price_pairs(panel: Panel, book: Book, basket: Basket, rule_fn=None,
                symbols=None, *, split_days=None, excluded_days=None) -> Pairs:
    """split_days / excluded_days: the §5.1 sets the rule's own trades were
    filtered by (run.apply_xcheck). A pair spanning a split or touching an
    excluded day is not drawable -- the null must face the same data the
    rule did, or a split read as -50% lands in the control."""
    fn = rule_fn or RULES[book.rule]
    syms, ss, mrs = [], [], []
    names = list(symbols or panel.symbols)
    spl, exc = _by_sym(split_days), _by_sym(excluded_days)
    for k, sym in enumerate(names):
        full = panel.arrays(sym)
        for st, en in panel.segment_bounds(sym):
            a = full if (st, en) == (0, full.n) else slice_arrays(full, st, en)
            got = _segment_pairs(panel, a, book, fn, basket, spl, exc)
            if got is None:
                continue
            mr, s_sig = got
            mrs.append(mr)
            ss.append(s_sig)
            syms.append(np.full(len(mr), k, dtype=np.int64))
    if not mrs:
        return Pairs(np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0), names)
    return Pairs(np.concatenate(syms), np.concatenate(ss), np.concatenate(mrs), names)


def _segment_pairs(panel, a, book, fn, basket, spl, exc):
    sym = a.symbol
    out = fn(a, book.variant)
    anyrule = dataclasses.replace(out, entry=np.ones(a.n, bool), stop=out.stop_any)
    cand = E.candidates(a, anyrule, Counter(), notional=book.notional)
    fill = cand["fill"]
    if len(fill) == 0:
        return None
    res = X.simulate(a, fill, out.spec, fixed_stop=cand["stop"], xsig=out.xsig,
                     ratchet=out.ratchet, atr_prev=out.atr_prev)
    qty = np.floor(book.notional / res.fill_px)
    s_e = a.s[res.fill_idx]
    s_sig = a.s[cand["sig"]]
    s_x = a.s[np.where(res.exit_idx < 0, res.fill_idx, res.exit_idx)]
    ok = (~res.void & (qty > 0)
          & ~_hits(spl, sym, s_e, s_x, open_lo=True)
          & ~_hits(exc, sym, s_sig, s_x, open_lo=False))
    if not ok.any():
        return None
    idx = np.flatnonzero(ok)
    sub = X.ExitResult(res.fill_idx[idx], res.fill_px[idx], res.exit_idx[idx],
                       res.exit_px[idx], res.phase[idx], res.reason[idx],
                       res.void[idx])
    q = qty[idx].astype(np.int64)
    gross = q * (sub.exit_px - sub.fill_px)
    cost = C.trade_costs(q, sub.fill_px, sub.exit_px, a.bar[sub.fill_idx],
                         a.bar[sub.exit_idx], sub.phase, sub.stop_fill,
                         panel.grid)["L2"]
    br = basket.ret(X.entry_mark(a, sub), X.exit_mark(a, sub))
    return (gross - cost - q * sub.fill_px * br).astype(np.float64), s_sig[idx]


def random_control(pairs: Pairs, entries_per_session: dict, name: str,
                   n_draws: int = N_DRAWS) -> dict:
    """entries_per_session: {signal session index: entries the book took}.
    Returns the draws' per-trade means and their 95th percentile."""
    if len(pairs.mr_net) == 0:
        return {"draws": np.zeros(0), "p95": None, "unmatched": sum(entries_per_session.values())}
    order = np.lexsort((pairs.sym, pairs.s_sig))
    s = pairs.s_sig[order]
    y = pairs.sym[order]
    v = pairs.mr_net[order]
    # weight = 1 / (names in session x that name's bars in session)
    base = int(y.max()) + 1
    key = s * base + y
    uk, inv, cnt_name = np.unique(key, return_inverse=True, return_counts=True)
    per_name = cnt_name[inv]
    names_in = np.bincount(uk // base, minlength=int(s.max()) + 1)
    w = 1.0 / (per_name * names_in[s])
    cs = np.cumsum(w)
    first = np.r_[True, s[1:] != s[:-1]]
    start_cs = np.maximum.accumulate(np.where(first, cs - w, 0.0))
    cum = cs - start_cs
    last = np.r_[s[1:] != s[:-1], True]
    cum = np.where(last, 1.0, np.minimum(cum, 1.0))
    cdf = s + cum                              # session s's block is (s, s + 1]
    ses_u = np.unique(s)
    want = []
    unmatched = 0
    have = set(ses_u.tolist())
    for sess, n in sorted(entries_per_session.items()):
        if int(sess) in have:
            want.append(np.full(int(n), int(sess)))
        else:
            unmatched += int(n)
    if not want:
        return {"draws": np.zeros(0), "p95": None, "unmatched": unmatched}
    target_s = np.concatenate(want)
    rng = np.random.default_rng(seed("random-entry", name))
    means = np.empty(n_draws)
    for d in range(n_draws):
        u = rng.random(len(target_s))
        pos = np.searchsorted(cdf, target_s + u, side="right")
        if d == 0 and not np.array_equal(s[pos], target_s):     # pragma: no cover
            raise AssertionError("a random entry landed outside its session")
        means[d] = v[pos].mean()
    return {"draws": means, "p95": float(np.percentile(means, 95)),
            "unmatched": unmatched, "n_per_draw": int(len(target_s))}


# --------------------------------------------------------------------------
# §4.3 positive control
# --------------------------------------------------------------------------

def flagged(panel: Panel, rate: float | None = None) -> set:
    """A seeded `rate` of ELIGIBLE symbol-days: {(symbol, session index)}.
    Seeded per symbol-day with crc32, so the set does not depend on the order
    anything is iterated in."""
    cut = int(round((PC_RATE if rate is None else rate) * 1_000_000))
    out = set()
    for sym in panel.symbols:
        m = panel.elig[sym]
        present = np.unique(panel.arrays(sym).s)
        for s in present:
            if m[s] and seed("pc", sym, panel.sessions[s]) % 1_000_000 < cut:
                out.add((sym, int(s)))
    return out


def plant(panel: Panel, flags: set, bps: float = PC_BPS, slot: int = PC_SLOT) -> Panel:
    b = panel.bars.copy()
    fl = pd.DataFrame(sorted(flags), columns=["symbol", "s"]).assign(_f=True)
    f = b[["symbol", "s"]].merge(fl, on=["symbol", "s"], how="left")["_f"]
    f = f.notna().to_numpy()
    k = 1.0 + bps / 1e4
    later = f & (b["bar"].to_numpy() > slot)
    at = f & (b["bar"].to_numpy() == slot)
    for c in ("open", "high", "low", "close"):
        b.loc[later, c] = b.loc[later, c] * k
    for c in ("high", "low", "close"):
        b.loc[at, c] = b.loc[at, c] * k
    b.loc[at, "high"] = np.maximum(b.loc[at, "high"], b.loc[at, "open"])
    b.loc[at, "low"] = np.minimum(b.loc[at, "low"], b.loc[at, "open"])
    return Panel.build(b.drop(columns=["s", "g"]), panel.universe, panel.grid)


def pc_rule(flags: set, slot: int = PC_SLOT):
    """Buy a flagged name at the open of `slot` (signal on the bar before it),
    sell at the entry session's close."""
    def fn(a, variant=None):
        e = np.zeros(a.n, bool)
        prev = np.flatnonzero(a.bar == slot - 1)
        for j in prev:
            if (a.symbol, int(a.s[j])) in flags and j + 1 < a.n and a.bar[j + 1] == slot \
                    and a.s[j + 1] == a.s[j]:
                e[j] = True
        return RuleOut(entry=e, spec=X.ExitSpec(cap_sessions=0))
    return fn


def positive_control(panel: Panel, build_basket, *, flags: set | None = None,
                     excluded_days: set | None = None) -> dict:
    """G7. `build_basket(panel) -> Basket` so the SAME basket construction
    the scoring path uses is the one tested. Symbol-days §5.1 excluded are
    never flagged: every book is kept off them, and so is the control."""
    from strategy.h60.score import score
    flags = flagged(panel) if flags is None else flags
    if excluded_days:
        flags = set(flags) - set(excluded_days)
    book = Book("PC", "PC", "pc", False)
    res = {}
    for label, p in (("planted", plant(panel, flags)), ("null", panel)):
        t, counts = E.run_book(p, book, rule_fn=pc_rule(flags))
        sc = score(t, build_basket(p), p.grid)
        res[label] = {"trades": len(sc),
                      "mr_gross_per_trade": float(sc["mr_gross"].mean()) if len(sc) else float("nan"),
                      "gross_per_trade": float(sc["gross"].mean()) if len(sc) else float("nan")}
    ok_p = abs(res["planted"]["mr_gross_per_trade"] - PC_TARGET) <= PC_TOL
    ok_n = abs(res["null"]["mr_gross_per_trade"]) <= PC_TOL
    res["flags"] = len(flags)
    res["pass"] = bool(ok_p and ok_n)
    return res
