"""C-R random keep for OTF-G (REGISTERED_otf_gate.md sec 3). Seeded, no clock.

For each market x direction cell, keep the SAME number of trades the gate keeps, drawn at random from that
cell's host trades; 1,000 draws, rng = default_rng([crc32(str(draw)), crc32(cell), 25]). The statistic is the
kept-book net; the gate's percentile is the share of draws strictly below it plus half the ties.
"""
from __future__ import annotations

import zlib

import numpy as np

from strategy.otf_gate import spec as S


def cell_keys(markets, direction) -> np.ndarray:
    return np.array([f"{m}|{int(d)}" for m, d in zip(markets, direction)], dtype=object)


def _rng(draw: int, cell: str, tag: int = S.CR_SEED_TAG):
    return np.random.default_rng([zlib.crc32(str(draw).encode()), zlib.crc32(cell.encode()), tag])


def random_keep(nets: np.ndarray, cells: np.ndarray, k_by_cell: dict, draws: int = S.CR_DRAWS) -> np.ndarray:
    """`nets` is (n, 3) for low/mid/high; returns (draws, 3): kept-book net of each random keep."""
    nets = np.asarray(nets, dtype=float)
    if nets.ndim == 1:
        nets = nets[:, None]
    idx = {c: np.flatnonzero(cells == c) for c, k in k_by_cell.items() if k > 0}
    for c, k in k_by_cell.items():
        if k > len(np.flatnonzero(cells == c)):
            raise ValueError(f"cell {c}: asked to keep {k} of {int((cells == c).sum())}")
    out = np.zeros((draws, nets.shape[1]))
    for d in range(draws):
        for c, ix in idx.items():
            pick = _rng(d, c).choice(ix, size=k_by_cell[c], replace=False)
            out[d] += nets[pick].sum(axis=0)
    return out


def percentile_of(value: float, draws: np.ndarray) -> float:
    draws = np.asarray(draws)
    return float(100.0 * ((draws < value).mean() + 0.5 * (draws == value).mean()))


def cr_summary(draws: np.ndarray) -> dict:
    return {f"p{q}": float(np.percentile(draws, q)) for q in (5, 50, 95, 97.5, 99)}


def k_by_cell(cells: np.ndarray, keep: np.ndarray) -> dict:
    """How many trades the gate keeps in each cell (the C-R sample sizes)."""
    out = {}
    for c in np.unique(cells):
        out[str(c)] = int(keep[cells == c].sum())
    return out
