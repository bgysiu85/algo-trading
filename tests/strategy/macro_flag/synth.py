"""Synthetic sessions and books for the MFLAG-v1 tests."""
import numpy as np
import pandas as pd

from strategy.macro_flag import spec as S

SESSIONS = pd.bdate_range("2012-01-02", "2021-12-31")


def sessions_all():
    return {m: SESSIONS for m in S.MARKETS}


def calendar(days_by_event=None):
    cal = {e: pd.DatetimeIndex([]) for e in S.ALL_EVENTS}
    for e, d in (days_by_event or {}).items():
        cal[e] = pd.DatetimeIndex(sorted(pd.to_datetime(d)))
    return cal


def nfp_fridays():
    fr = SESSIONS[SESSIONS.dayofweek == 4]
    return list(fr[::4])


def books(n_per_market=60, seed=3, planted=0.0, event_days=None, markets=None):
    """C1 frac + C1 int + TL ens rows. `planted` shifts the net of trades whose entry_date is in event_days'
    W1/W2 window (negative = flagged trades are worse)."""
    rng = np.random.default_rng(seed)
    rows = []
    special = set()
    for d in (event_days or []):
        i = SESSIONS.get_loc(d)
        special |= {SESSIONS[i], SESSIONS[i + 1]}
    for m in (markets or S.MARKETS):
        js = np.sort(rng.choice(np.arange(5, len(SESSIONS) - 5), n_per_market, replace=False))
        for spec, share, sizing, eq in (("C1", "single", "frac", 22129.0), ("C1", "single", "int", 100000.0),
                                        ("C1", "single", "int", 500000.0), ("v1", "sleeve", "frac", 22129.0)):
            for j in js:
                ed = SESSIONS[j]
                net = float(rng.normal(-1, 60)) + (planted if ed in special else 0.0)
                rows.append(dict(market=m, spec=spec, share=share, sizing=sizing, equity=eq, entry_date=ed,
                                 entry_j=int(j), net_low=net + 1, net_mid=net, net_high=net - 2))
    return pd.DataFrame(rows)
