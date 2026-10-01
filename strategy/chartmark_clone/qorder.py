#!/usr/bin/env python3
"""Queue order (sec 3.2) and the repeat schedule (sec 3.3). Both are pure functions of the manifest and fixed seeds:
no label, no price, no outcome is read here."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.chartmark_clone import spec as S


def build_queue(m: pd.DataFrame) -> pd.DataFrame:
    """Strata = year x F1 (24). Every prefix of the queue is close to proportional across strata (I5)."""
    rng = np.random.default_rng(S.QUEUE_SEED_WORDS)
    keys = np.full(len(m), np.nan)
    groups = m.groupby(["year", "daily_trend"], sort=True).indices
    for (_, _), idx in sorted(groups.items()):
        idx = np.asarray(idx)
        n = len(idx)
        perm = rng.permutation(n)
        u = rng.random(n)
        rank = np.empty(n, dtype=np.int64)
        rank[perm] = np.arange(n)
        keys[idx] = (rank + u) / n
    q = pd.DataFrame({"candidate_id": m["candidate_id"].to_numpy(), "key": keys})
    q = q.sort_values(["key", "candidate_id"], kind="mergesort").reset_index(drop=True)
    q.insert(0, "queue_pos", np.arange(len(q)))
    q["key"] = q["key"].map(lambda x: f"{x:.12f}")
    return q[S.QUEUE_COLUMNS]


def repeat_targets(n_queue: int) -> dict[int, int]:
    """slot k (after the 10k-th NEW candidate) -> queue position repeated. Exists iff 10k - 100 >= 1 (I6)."""
    out: dict[int, int] = {}
    used: set[int] = set()
    for k in range(1, n_queue // S.REPEAT_EVERY + 1):
        top = S.REPEAT_EVERY * k - S.REPEAT_MIN_GAP        # eligible positions 0 .. top-1
        if top < 1:
            continue
        pool = [p for p in range(top) if p not in used]
        if not pool:
            continue
        rng = np.random.default_rng([S.REPEAT_SEED_WORD, k])
        pick = pool[int(rng.integers(len(pool)))]
        used.add(pick)
        out[k] = pick
    return out


@dataclass(frozen=True)
class Item:
    seq: int
    queue_pos: int
    is_repeat: bool
    candidate_id: str


def schedule(queue: pd.DataFrame) -> list[Item]:
    """Presentation order: new candidates in queue order, a repeat after every 10th new one once eligible."""
    ids = queue["candidate_id"].tolist()
    reps = repeat_targets(len(ids))
    items: list[Item] = []
    for pos, cid in enumerate(ids):
        items.append(Item(len(items), pos, False, cid))
        if (pos + 1) % S.REPEAT_EVERY == 0:
            k = (pos + 1) // S.REPEAT_EVERY
            if k in reps:
                items.append(Item(len(items), reps[k], True, ids[reps[k]]))
    return items
