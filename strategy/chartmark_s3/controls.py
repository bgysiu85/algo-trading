#!/usr/bin/env python3
"""CHARTMARK-S v3 controls (sec 3): C1 Donchian 20/10 short (v1's code, unchanged) and C3 random short entries. C2 (the long
rules mirrored) is not a v3 control. C3 differs from v1 only in its registered seed constant crc32("CL-S3")."""
from __future__ import annotations

from zlib import crc32

import numpy as np

from strategy.chartmark_s.controls import candidate_outcomes, donchian_c1      # noqa: F401  (v1 code, unchanged)
from strategy.chartmark_s3.data import Frame                                     # noqa: F401


def c3_draws(fr, cand_idx: np.ndarray, cand_net: np.ndarray, base_entries_per_year: dict, draws: int = 1000) -> np.ndarray:
    """1,000 seeded draws: per year the same number of entries as the base, sampled from that year's candidates (each a
    standalone random short from the open of a random bar, same exits). Seed default_rng([crc32(str(d)), crc32("CL-S3"), N]),
    N = the base's total entries (registered, v3 sec 3)."""
    years = np.asarray(fr.ny.year)[cand_idx]
    N = int(sum(base_entries_per_year.values()))
    pools = {y: cand_net[years == y] for y in base_entries_per_year}
    tot = np.empty(draws)
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(b"CL-S3"), N])
        s = 0.0
        for y in sorted(base_entries_per_year):
            k, pool = base_entries_per_year[y], pools[y]
            if k and len(pool):
                s += float(pool[rng.integers(0, len(pool), size=k)].sum())
        tot[d] = s
    return tot
