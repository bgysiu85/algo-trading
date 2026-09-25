"""tests/common/test_news_swing_study.py

W07-0011 subitem 4 -- the Step-1 bucket report and §11.4 pass bar. Synthetic
tagged-picks fixtures throughout (no real SWING-v0 picks exist yet).
"""
from __future__ import annotations

from common import news_swing_study as S
from common import news_swing_tag as T


def _tagged(symbol, entry_date, net, tag, mkt_rel_net=None, net_2x_stress=None):
    return {"symbol": symbol, "entry_date": entry_date, "entry_et": "11:30",
           "drop_start_date": entry_date, "k": 5, "bucket": "midday",
           "gross": net + 5, "cost": 5.0, "net": net,
           "net_2x_stress": net_2x_stress if net_2x_stress is not None else net - 2,
           "mkt_rel_net": mkt_rel_net if mkt_rel_net is not None else net,
           "news_tag": tag, "news_trigger": ""}


# --- money formatting: negatives bracketed -----------------------------------

def test_money_negative_is_bracketed():
    assert S.money(-12.5) == "(12.50)"
    assert S.money(12.5) == "12.50"
    assert S.money(0) == "0.00"


# --- bucket split / lopsided rule ---------------------------------------------

def test_bucket_split_partitions_news_and_no_news():
    rows = [_tagged("A", "2026-05-01", 10, T.NEWS), _tagged("B", "2026-05-02", 20, T.NO_NEWS)]
    b = S.bucket_split(rows)
    assert len(b["ALL"]) == 2 and len(b[T.NEWS]) == 1 and len(b[T.NO_NEWS]) == 1


def test_lopsided_true_when_news_bucket_under_10pct():
    rows = ([_tagged("A", "2026-05-01", 10, T.NEWS)]
           + [_tagged("B", f"2026-05-{i:02d}", 10, T.NO_NEWS) for i in range(2, 21)])
    assert S.lopsided(rows) is True


def test_lopsided_false_on_balanced_split():
    rows = ([_tagged("A", f"2026-05-{i:02d}", 10, T.NEWS) for i in range(1, 11)]
           + [_tagged("B", f"2026-06-{i:02d}", 10, T.NO_NEWS) for i in range(1, 11)])
    assert S.lopsided(rows) is False


def test_lopsided_true_on_empty():
    assert S.lopsided([]) is True


# --- halves --------------------------------------------------------------------

def test_median_cut_and_halves():
    rows = [_tagged("A", d, 10, T.NEWS) for d in
           ("2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04")]
    cut = S.median_cut(rows)
    assert cut == "2026-05-03"
    early, late = S.halves(rows, cut)
    assert [r["entry_date"] for r in early] == ["2026-05-01", "2026-05-02"]
    assert [r["entry_date"] for r in late] == ["2026-05-03", "2026-05-04"]


# --- bucket stats ---------------------------------------------------------------

def test_bucket_stats_totals_and_per_trade():
    rows = [_tagged("A", "2026-05-01", 10, T.NEWS), _tagged("B", "2026-05-02", -4, T.NEWS)]
    s = S.bucket_stats(rows)
    assert s["n"] == 2
    assert s["winners"] == 1
    assert s["net"] == 6
    assert s["net_per_trade"] == 3


def test_bucket_stats_empty():
    s = S.bucket_stats([])
    assert s["n"] == 0 and s["net_per_trade"] is None


# --- §11.4 pass bar -------------------------------------------------------------

def test_pass_bar_passes_when_no_news_beats_all_in_both_halves_and_keeps_share():
    # NO NEWS trades net well (20/trade); NEWS trades net poorly (-10/trade);
    # interleaved across two months so BOTH halves contain a mix of the two
    # (a half made of one tag only would make NO-NEWS == ALL there, trivially
    # not ">"), NO NEWS is 50% of the population.
    rows = ([_tagged("N", "2026-05-01", 20, T.NO_NEWS), _tagged("W", "2026-05-02", -10, T.NEWS),
            _tagged("N", "2026-05-03", 20, T.NO_NEWS), _tagged("W", "2026-05-04", -10, T.NEWS),
            _tagged("N", "2026-06-01", 20, T.NO_NEWS), _tagged("W", "2026-06-02", -10, T.NEWS),
            _tagged("N", "2026-06-03", 20, T.NO_NEWS), _tagged("W", "2026-06-04", -10, T.NEWS)])
    buckets = S.bucket_split(rows)
    cut = S.median_cut(rows)
    verdict, lines = S.pass_bar(buckets, cut)
    assert verdict == "PASSES STEP 1"
    assert any("item 2" not in l and "1. NO-NEWS" in l for l in lines)


def test_pass_bar_fails_when_no_news_does_not_beat_all():
    rows = [_tagged("N", "2026-05-01", 5, T.NO_NEWS), _tagged("N", "2026-05-02", 5, T.NO_NEWS),
           _tagged("W", "2026-06-01", 50, T.NEWS), _tagged("W", "2026-06-02", 50, T.NEWS)]
    buckets = S.bucket_split(rows)
    cut = S.median_cut(rows)
    verdict, _lines = S.pass_bar(buckets, cut)
    assert verdict == "FAILS STEP 1"


def test_pass_bar_fails_when_no_news_share_under_40pct():
    rows = ([_tagged("N", "2026-05-01", 100, T.NO_NEWS)]
           + [_tagged("W", f"2026-06-{i:02d}", 1, T.NEWS) for i in range(1, 6)])
    buckets = S.bucket_split(rows)
    cut = S.median_cut(rows)
    verdict, lines = S.pass_bar(buckets, cut)
    assert verdict == "FAILS STEP 1"
    assert any("3. NO-NEWS keeps" in l and "FAILS" in l for l in lines)


def test_pass_bar_item2_always_reported_not_evaluated():
    rows = [_tagged("N", "2026-05-01", 10, T.NO_NEWS)]
    buckets = S.bucket_split(rows)
    _verdict, lines = S.pass_bar(buckets, "2026-05-01")
    assert any("NOT EVALUATED HERE" in l for l in lines)


# --- render smoke tests ---------------------------------------------------------

def test_render_lopsided_path_does_not_crash():
    rows = ([_tagged("A", "2026-05-01", 10, T.NEWS)]
           + [_tagged("B", f"2026-05-{i:02d}", 10, T.NO_NEWS) for i in range(2, 21)])
    text = "\n".join(S.render(rows, S.median_cut(rows)))
    assert "TOO LOPSIDED TO READ" in text
    assert "§11.4 PASS BAR" not in text   # the pass-bar SECTION is skipped when lopsided


def test_render_normal_path_includes_pass_bar():
    rows = ([_tagged("N", f"2026-05-{i:02d}", 20, T.NO_NEWS) for i in range(1, 7)]
           + [_tagged("W", f"2026-06-{i:02d}", -10, T.NEWS) for i in range(1, 5)])
    text = "\n".join(S.render(rows, S.median_cut(rows)))
    assert "§11.4 PASS BAR" in text
    assert "EARLY HALF" in text and "LATE HALF" in text
