#!/usr/bin/env python3
"""Judge the pyramid against its flat-size control to the project's standard.

    python -m common.pyramid_verdict

common/pyramid_study.py showed the pyramid earns more per dollar of capital
than starting at the size it builds to. That is a ratio, and a ratio can
improve simply by deploying less. So this compares the two AT THE SAME PEAK
POSITION SIZE -- 100 shares plus one 100-share add versus a flat 200 from the
entry, both peaking at 200 -- and applies the usual tests to the DELTA:

  * paired-by-symbol bootstrap, 10,000 resamples, on the delta
  * drop-top-N applied to the delta, not the level
  * temporal holdout, both halves

It also settles a definitional inconsistency worth knowing about: drop-top-N
in common/scale_grid.py is computed BEFORE measured slippage, while this
module and pyramid_study.py compute it AFTER. Both are printed here so the
earlier published figures can be reconciled rather than silently contradicted.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from common.trail_study import paired_bootstrap
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")
SLIP_PER_SHARE = (0.0590 - 0.0164) / 2
REBUY_SLIP_BPS = 40.0
RESAMPLES = 10_000

FLAT = dict(entry_shares=200)
PYRA = dict(entry_shares=100, pyramid_qty=100, pyramid_pullback_pct=2.0,
            max_adds=1)


def by_symbol(sessions, **kw):
    """Returns (real-by-symbol, net-by-symbol, trade count)."""
    real, net, n = {}, {}, 0
    for symbol, date_str, df in sessions:
        for t in S.backtest_session(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET,
                **LIVE, rebuy_slip_bps=REBUY_SLIP_BPS, **kw):
            real[symbol] = real.get(symbol, 0.0) + \
                t.net - t.shares_traded * SLIP_PER_SHARE
            net[symbol] = net.get(symbol, 0.0) + t.net
            n += 1
    return real, net, n


def drop_top(d, k):
    return sum(sorted(d.values(), reverse=True)[k:])


def main() -> int:
    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]

    fr, fn, f_n = by_symbol(sessions, **FLAT)
    pr, pn, p_n = by_symbol(sessions, **PYRA)
    syms = sorted(set(fr) | set(pr))
    for d in (fr, fn, pr, pn):
        for s in syms:
            d.setdefault(s, 0.0)

    print("PYRAMID (100 + one 100-share add on a recovered -2% dip)")
    print("   vs FLAT 200 from entry. Both peak at 200 shares.\n")
    print(f"  {'':<26} {'flat 200':>12} {'pyramid':>12}")
    print(f"  {'trades':<26} {f_n:>12} {p_n:>12}")
    print(f"  {'net, after slippage':<26} ${sum(fr.values()):>11,.0f} "
          f"${sum(pr.values()):>11,.0f}")
    print(f"  {'net, before slippage':<26} ${sum(fn.values()):>11,.0f} "
          f"${sum(pn.values()):>11,.0f}")
    print(f"  {'drop5, after slippage':<26} ${drop_top(fr,5):>11,.0f} "
          f"${drop_top(pr,5):>11,.0f}")
    print(f"  {'drop5, before slippage':<26} ${drop_top(fn,5):>11,.0f} "
          f"${drop_top(pn,5):>11,.0f}")

    tot, lo, hi, p = paired_bootstrap(fr, pr, RESAMPLES)
    delta = {s: pr[s] - fr[s] for s in syms}
    print(f"\n  DELTA (pyramid - flat), after slippage: ${tot:>+,.0f}")
    print(f"  95% CI [${lo:>+,.0f}, ${hi:>+,.0f}]   P(delta > 0) = {p:.1f}%")
    for k in (1, 3, 5):
        print(f"  delta after dropping the best {k} symbol(s): "
              f"${drop_top(delta, k):>+,.0f}")

    early = [s for s in sessions if s[1] < split]
    late = [s for s in sessions if s[1] >= split]
    print(f"\n  holdout split {split}")
    for label, subset in (("early", early), ("late", late)):
        f, _, _ = by_symbol(subset, **FLAT)
        q, _, _ = by_symbol(subset, **PYRA)
        d = sum(q.values()) - sum(f.values())
        print(f"    {label:<6} flat ${sum(f.values()):>8,.0f}   "
              f"pyramid ${sum(q.values()):>8,.0f}   delta ${d:>+8,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
