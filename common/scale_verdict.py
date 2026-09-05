#!/usr/bin/env python3
"""The go/no-go on the scale-out mechanic, run to the project's usual bar.

    python -m common.scale_verdict

common/scale_regimes.py separates the mechanic from the leverage. This applies
the standards of evidence to whatever survived that: drop-top-N on the DELTA
(not just the level), a paired-by-symbol bootstrap, and a temporal holdout --
always against the SAME trail with no scale-out, so what is measured is the
mechanic and not the trail.

Only the size-NEUTRAL form is judged here. The growth forms are a decision
about position size, which this account cannot fund at the sizes the grid
wants and which should be settled by the sizing study, not smuggled in as an
exit rule.
"""
from __future__ import annotations

import random
from pathlib import Path

from common.analysis import load_sessions
from common.scale_grid import prepare, _simulate, SLIP_PER_SHARE
from common.trail_study import paired_bootstrap

RESAMPLES = 10_000

# (trail, partial, portion) -- the size-neutral cells worth judging: the best
# at the shipped trail, and the best at the trail the grid preferred.
CASES = [
    (5.0, 0.5, 20.0),
    (5.0, 0.5, 75.0),
    (15.0, 0.5, 75.0),
    (15.0, 1.0, 75.0),
    (10.0, 0.5, 75.0),
]


def by_symbol(prepared, trail, partial, portion, rebuy):
    """Real (after measured slippage) net per symbol, and the trade count."""
    out, n = {}, 0
    for sess in prepared:
        sym = sess[0]
        for tnet, shares, _mq, _cyc in _simulate(
                sess, trail, partial, portion, rebuy):
            out[sym] = out.get(sym, 0.0) + tnet - shares * SLIP_PER_SHARE
            n += 1
    return out, n


def drop_top(d, k):
    return sum(sorted(d.values(), reverse=True)[k:])


def main() -> int:
    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    prepared = prepare(sessions)
    early = prepare([s for s in sessions if s[1] < split])
    late = prepare([s for s in sessions if s[1] >= split])
    print(f"{len(prepared)} sessions, holdout split {split}, "
          f"{RESAMPLES:,} bootstrap resamples\n")

    for trail, partial, portion in CASES:
        # portion=0 makes the mechanic inert -- sell_q rounds to 0 shares.
        base, nb = by_symbol(prepared, trail, partial, 0.0, None)
        cand, nc = by_symbol(prepared, trail, partial, portion, None)
        syms = sorted(set(base) | set(cand))
        base = {s: base.get(s, 0.0) for s in syms}
        cand = {s: cand.get(s, 0.0) for s in syms}

        tot, lo, hi, p = paired_bootstrap(base, cand, RESAMPLES)
        delta = {s: cand[s] - base[s] for s in syms}

        print(f"TRAIL {trail:g}%  sell {portion:g}% at -{partial:g}%, "
              f"size held CONSTANT   ({nb} -> {nc} trades)")
        print(f"  base ${sum(base.values()):>9,.0f}   "
              f"cand ${sum(cand.values()):>9,.0f}   "
              f"delta ${tot:>+9,.0f}")
        print(f"  95% CI [${lo:>+8,.0f}, ${hi:>+8,.0f}]   P(delta>0) = {p:.1f}%")
        print(f"  delta after dropping the best  1 symbol: ${drop_top(delta,1):>+9,.0f}")
        print(f"  delta after dropping the best  3 symbols: ${drop_top(delta,3):>+9,.0f}")
        print(f"  delta after dropping the best  5 symbols: ${drop_top(delta,5):>+9,.0f}")
        eb, _ = by_symbol(early, trail, partial, 0.0, None)
        ec, _ = by_symbol(early, trail, partial, portion, None)
        lb, _ = by_symbol(late, trail, partial, 0.0, None)
        lc, _ = by_symbol(late, trail, partial, portion, None)
        de = sum(ec.values()) - sum(eb.values())
        dl = sum(lc.values()) - sum(lb.values())
        print(f"  early half ${de:>+9,.0f}     late half ${dl:>+9,.0f}"
              f"     {'both positive' if de > 0 and dl > 0 else 'SIGN FLIPS'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
