"""Controls for MFLAG-v1 (sec 3): C-R random removal, the criterion-7 permutation. Seeded, no clock."""
from __future__ import annotations

import zlib

import numpy as np

from strategy.macro_flag import spec as S


def _rng(draw: int, key: str, tag: int):
    return np.random.default_rng([zlib.crc32(str(draw).encode()), zlib.crc32(key.encode()), tag])


def random_removal(nets: np.ndarray, markets: np.ndarray, k_by_market: dict, draws: int = S.CR_DRAWS) -> np.ndarray:
    """C-R. nets is (n, 3) for low/mid/high. For each draw and market remove k_m random trades of that market
    (k_m = what the flag removes there). Returns (draws, 3): delta = -sum(net of removed), summed over markets."""
    idx = {m: np.flatnonzero(markets == m) for m in k_by_market if k_by_market[m] > 0}
    out = np.zeros((draws, nets.shape[1]))
    for d in range(draws):
        for m, ix in idx.items():
            pick = _rng(d, m, S.CR_SEED_TAG).choice(ix, size=k_by_market[m], replace=False)
            out[d] -= nets[pick].sum(axis=0)
    return out


def percentile_of(value: float, draws: np.ndarray) -> float:
    return float(100.0 * ((draws < value).mean() + 0.5 * (draws == value).mean()))


def cr_summary(draws: np.ndarray) -> dict:
    return {f"p{q}": float(np.percentile(draws, q)) for q in (5, 50, 95, 99)}


def label_permutation_p(flag: np.ndarray, net: np.ndarray, markets: np.ndarray, draws: int = S.PERM_DRAWS) -> tuple:
    """Criterion 7. Statistic = mean(unflagged) - mean(flagged) over the pooled trades of the flag markets;
    the flagged/unflagged labels are shuffled within market. One-sided p = (1 + #{perm >= observed}) / (draws + 1)."""
    keep = np.isin(markets, S.FLAG_MARKETS)
    f, x, mk = flag[keep], net[keep], markets[keep]
    if f.sum() == 0 or (~f).sum() == 0:
        return float("nan"), float("nan"), float("nan")
    obs = x[~f].mean() - x[f].mean()
    groups = [np.flatnonzero(mk == m) for m in S.FLAG_MARKETS if (mk == m).any()]
    nf = int(f.sum())
    ge = 0
    for d in range(draws):
        lab = np.zeros(len(f), dtype=bool)
        for m, g in zip([m for m in S.FLAG_MARKETS if (mk == m).any()], groups):
            k = int(f[g].sum())
            if k:
                lab[_rng(d, m, S.PERM_SEED_TAG).choice(g, size=k, replace=False)] = True
        stat = x[~lab].mean() - x[lab].mean()
        ge += stat >= obs
    return float(obs), float((1 + ge) / (draws + 1)), float(nf)
