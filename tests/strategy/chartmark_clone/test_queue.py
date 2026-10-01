"""Queue order (sec 3.2) and repeat schedule (sec 3.3): pure functions of the manifest and the registered seeds."""
import hashlib
from collections import Counter

import pandas as pd

from strategy.chartmark_clone import qorder as QO
from strategy.chartmark_clone import spec as S


def fixed_manifest() -> pd.DataFrame:
    rows, i = [], 0
    for y, n in S.POOL_PER_YEAR.items():
        for k in range(n):
            rows.append(dict(candidate_id=f"{y}-{(k % 12) + 1:02d}-{(k % 27) + 1:02d} {k % 24:02d}:00:00#{i}", year=y,
                             daily_trend=1 if (i * 7) % 5 < 3 else -1))
            i += 1
    return pd.DataFrame(rows)


def test_the_queue_is_a_fixed_permutation_of_the_pool():
    m = fixed_manifest()
    q = QO.build_queue(m)
    assert len(q) == S.POOL_N and set(q["candidate_id"]) == set(m["candidate_id"]) and q["candidate_id"].is_unique
    assert q["queue_pos"].tolist() == list(range(S.POOL_N))
    assert QO.build_queue(m).equals(q)                                       # same input, same queue
    assert QO.build_queue(m.sample(frac=1.0, random_state=3).reset_index(drop=True)).shape == q.shape
    # golden: pins the seed words and the algorithm; a change here is a different queue, i.e. a different study
    assert q["candidate_id"].head(3).tolist() == ["2010-09-09 08:00:00#8", "2013-05-11 16:00:00#666",
                                                  "2014-01-19 12:00:00#1008"]
    assert hashlib.sha256(q.to_csv(index=False, lineterminator="\n").encode()).hexdigest() == \
        "2a5a289eae2b81eb1c796ecdf144acafa23bdd702c9c8aa6e798886a3dc250a9"


def test_the_seed_words_are_the_registered_ones():
    import zlib
    assert S.QUEUE_SEED_WORDS == [zlib.crc32(b"W15-0050"), zlib.crc32(b"CHARTMARK-CLONE")]
    assert S.REPEAT_SEED_WORD == zlib.crc32(b"W15-0050-repeat")


def test_every_prefix_is_close_to_proportional_across_years_and_trend():
    m = fixed_manifest()
    q = QO.build_queue(m).merge(m, on="candidate_id")
    per_year = Counter(m["year"])
    trend_up = (m["daily_trend"] == 1).mean()
    for k in (100, 250, 500, 1000, 2000):
        head = q.head(k)
        for y, n in per_year.items():
            assert abs((head["year"] == y).sum() - k * n / S.POOL_N) <= 4, (k, y)
        assert abs((head["daily_trend"] == 1).mean() - trend_up) < 0.04, k


def test_a_stratum_prefix_is_proportional_within_the_stratum():
    m = fixed_manifest()
    q = QO.build_queue(m).merge(m, on="candidate_id")
    g = q[(q["year"] == 2015) & (q["daily_trend"] == 1)]
    n = len(g)
    for frac in (0.25, 0.5, 0.75):
        upto = int(S.POOL_N * frac)
        got = int((g["queue_pos"] < upto).sum())
        assert abs(got - n * frac) <= 2


def test_repeats_follow_the_registered_rule():
    q = QO.build_queue(fixed_manifest())
    items = QO.schedule(q)
    news = [i for i in items if not i.is_repeat]
    reps = [i for i in items if i.is_repeat]
    assert [i.queue_pos for i in news] == list(range(S.POOL_N))               # new candidates in queue order
    assert [i.seq for i in items] == list(range(len(items)))
    assert len(reps) == S.POOL_N // 10 - 10                                    # slots k = 11 .. 267
    targets = [r.queue_pos for r in reps]
    assert len(set(targets)) == len(targets)                                   # no candidate repeated twice
    n_new_before = 0
    for it in items:
        if not it.is_repeat:
            n_new_before += 1
            continue
        assert n_new_before % 10 == 0                                          # a repeat only after every 10th new one
        last_new_pos = n_new_before - 1
        assert it.queue_pos <= last_new_pos - S.REPEAT_MIN_GAP                # labelled at least 100 positions earlier
        assert it.candidate_id == q.loc[it.queue_pos, "candidate_id"]
    assert not any(i.is_repeat for i in items[:110])                           # none before there is something 100 back
    assert items[110].is_repeat and not items[109].is_repeat


def test_the_schedule_does_not_depend_on_anything_but_the_queue():
    q = QO.build_queue(fixed_manifest())
    a, b = QO.schedule(q), QO.schedule(q.copy())
    assert a == b
    assert QO.repeat_targets(2670) == QO.repeat_targets(2670)
