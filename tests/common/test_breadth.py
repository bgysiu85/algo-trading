#!/usr/bin/env python3
"""Criterion 2, and the ways a breadth test could measure the wrong thing.

The criterion being replaced -- "a majority of symbols with >= 1 trade are
profitable" -- is confounded twice. `orb_strategy_spec.md` §11.1 records the
first: it moves with trades per symbol. The second decides the design: with
right-skewed payoffs MOST symbols are negative at a genuinely positive
expectancy, so no better estimator of the same quantity escapes it.

These assertions pin the parts that would let the replacement inherit the same
faults quietly:

  * resampling trades instead of symbols, which understates the interval and
    passes things it should not;
  * a "sample-size-independent" restatement that is the old test in new words;
  * a shuffled control that does not hold trade count fixed, so it differs
    from the observation in two ways at once;
  * condition (a) read without (b), which a large sample makes easy;
  * a verdict that quietly drops the old criterion when the evidence says to
    keep it.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

from common import breadth as B

REPO = Path(__file__).resolve().parents[2]
REGISTRATION = REPO / "docs" / "research" / "REGISTERED_breadth.md"


def skewed(n_sym=120, per=4, win_rate=0.10, win=120.0, loss=-10.0, seed=3):
    """A right-skewed book with a POSITIVE expectancy and most symbols under
    water. 0.10 * 120 + 0.90 * -10 = +$3.00 a trade, and only about a third
    of symbols see a win in four trades.

    This is the shape the old criterion mismeasures, and every test that
    claims the replacement is different needs it to exist.
    """
    import random
    rng = random.Random(seed)
    out = {}
    for i in range(n_sym):
        out[f"S{i:04d}"] = [win if rng.random() < win_rate else loss
                            for _ in range(per)]
    return out


def flat(n_sym=100, per=4, net=1.0):
    return {f"F{i:04d}": [net] * per for i in range(n_sym)}


# ==========================================================================
# THE SHAPE THE OLD CRITERION MISMEASURES
# ==========================================================================
def test_a_positive_expectancy_book_still_leaves_most_symbols_negative():
    """THE PREMISE OF THE WHOLE REGISTRATION. If this were false the old
    criterion would have been fine and none of this was needed."""
    bs = skewed()
    per_trade = sum(sum(v) for v in bs.values()) / sum(len(v) for v in bs.values())
    _, _, share = B.share_profitable(bs)
    assert per_trade > 0, "the book must genuinely make money"
    assert share < 0.5, "and still fail the old criterion"


def test_the_median_restatement_is_the_SAME_TEST_and_not_a_fix():
    """'Median across symbols of per-symbol mean net >= 0' looks like a
    sample-size-independent version. A median is non-negative exactly when
    half the symbols are profitable, so it is the old test in new words. This
    pins the equivalence so nobody re-proposes it."""
    for bs in (skewed(), skewed(win_rate=0.6), flat()):
        med = statistics.median(statistics.mean(v) for v in bs.values())
        _, _, share = B.share_profitable(bs)
        assert (med >= 0) == (share >= 0.5)


# ==========================================================================
# THE CLUSTER BOOTSTRAP
# ==========================================================================
def test_the_skewed_book_PASSES_the_replacement_it_failed_before():
    """The point of the change: a genuinely profitable book with most symbols
    negative is not rejected for having the wrong payoff shape.

    At MC5's symbol count -- 1,791 -- rather than at a token one, because the
    replacement is deliberately sample-size aware and the test below pins that
    separately.
    """
    bs = skewed(n_sym=1500)
    _, _, share = B.share_profitable(bs)
    assert share < 0.5, "it must still fail the OLD criterion"
    ok, p, lo = B.verdict(B.cluster_bootstrap(bs, resamples=400, seed=1))
    assert ok and p >= B.BOOT_MIN_P


def test_the_replacement_is_sample_size_AWARE_and_the_old_one_is_not():
    """The registration's central claim, made concrete.

    The SAME payoff shape at 120 symbols cannot be told from zero and fails;
    at 1,500 it passes. The old criterion sits near a third either way, because
    it is reading the payoff shape and not the evidence.

    That is the right direction: few clusters SHOULD fail. A breadth test that
    returned the same verdict on 120 symbols and on 1,500 would not be
    measuring whether the result survives a different draw.
    """
    thin, thick = skewed(n_sym=120), skewed(n_sym=1500)
    ok_thin, _, _ = B.verdict(B.cluster_bootstrap(thin, resamples=400, seed=1))
    ok_thick, _, _ = B.verdict(B.cluster_bootstrap(thick, resamples=400, seed=1))
    assert not ok_thin and ok_thick
    _, _, s_thin = B.share_profitable(thin)
    _, _, s_thick = B.share_profitable(thick)
    assert abs(s_thin - s_thick) < 0.06, \
        "the old criterion barely moves between the two"


def test_a_losing_book_still_fails():
    losing = {f"L{i}": [-5.0] * 4 for i in range(80)}
    ok, p, _ = B.verdict(B.cluster_bootstrap(losing, resamples=300, seed=1))
    assert not ok and p == 0.0


def test_an_edge_carried_by_ONE_symbol_fails():
    """The intent behind criterion 2. One name making all the money must not
    survive a draw that can leave it out."""
    bs = {f"S{i}": [-1.0] * 5 for i in range(60)}
    bs["HERO"] = [5000.0]
    ok, p, _ = B.verdict(B.cluster_bootstrap(bs, resamples=500, seed=2))
    assert not ok, f"one-symbol edge passed at p={p:.3f}"


def test_SYMBOLS_are_resampled_and_not_trades():
    """Resampling trades treats many sessions on the same ticker as
    independent draws, which narrows the interval and passes things it should
    not.

    The difference only shows when a symbol carries SEVERAL correlated trades
    -- with one trade each the two resamples are the same object, which is why
    an earlier version of this test compared a one-trade HERO and found no
    difference. Here HERO's twenty trades are all-or-nothing under the symbol
    draw and self-averaging under the trade draw.
    """
    bs = {f"S{i}": [-1.0] * 5 for i in range(60)}
    bs["HERO"] = [250.0] * 20
    by_sym = B.cluster_bootstrap(bs, resamples=800, seed=2)
    flatp = [x for v in bs.values() for x in v]
    as_trades = B.cluster_bootstrap({f"T{i}": [x] for i, x in enumerate(flatp)},
                                    resamples=800, seed=2)
    p_sym = B.share_above_zero(by_sym["totals"])
    p_tr = B.share_above_zero(as_trades["totals"])
    assert p_sym < p_tr - 0.15, (
        f"symbol {p_sym:.3f} vs trade {p_tr:.3f}: the trade-level resample "
        "must be materially the more permissive one")


def test_a_drawn_symbols_trades_travel_with_it():
    """The per-trade statistic divides by the drawn trade count. If counts did
    not travel, the denominator would be the ORIGINAL sample's and the
    per-trade figure would be of a book that was never drawn."""
    bs = {"A": [10.0] * 10, "B": [10.0]}
    boot = B.cluster_bootstrap(bs, resamples=200, seed=5)
    assert all(abs(v - 10.0) < 1e-9 for v in boot["per_trade"]), \
        "every trade is +10, so every resample's per-trade must be exactly 10"


def test_the_bootstrap_is_reproducible_from_its_seed():
    bs = skewed(n_sym=40)
    a = B.cluster_bootstrap(bs, resamples=100, seed=9)
    b = B.cluster_bootstrap(bs, resamples=100, seed=9)
    assert a["totals"] == b["totals"]
    assert B.cluster_bootstrap(bs, resamples=100, seed=10)["totals"] != a["totals"]


def test_an_empty_sample_refuses_rather_than_returning_zero():
    boot = B.cluster_bootstrap({}, resamples=50, seed=1)
    assert boot["totals"] == [] and boot["n_syms"] == 0


# ==========================================================================
# THE WITHDRAWN SECOND CONDITION
#
# A floor on the 2.5th percentile of per-trade net was registered and then
# withdrawn, before ORB had a number, because it cannot fail independently.
# These pin WHY, so nobody re-adds it.
# ==========================================================================
def test_per_trade_carries_the_same_sign_as_total_in_every_resample():
    """THE REASON (b) WAS WITHDRAWN. per_trade = total / count and count > 0,
    so a floor at zero on one is a significance level on the other -- not a
    magnitude check, which is what the registration claimed it was."""
    bs = skewed(n_sym=200, seed=6)
    boot = B.cluster_bootstrap(bs, resamples=500, seed=3)
    for t, pt in zip(boot["totals"], boot["per_trade"]):
        assert (t > 0) == (pt > 0)


def test_a_book_with_NO_edge_at_all_satisfies_the_withdrawn_floor():
    """4,000 symbols at a hundredth of a cent a trade. The registration said
    the floor would catch exactly this and, set at $0, it does not."""
    tiny = {f"S{i:05d}": [0.0001] * 4 for i in range(4000)}
    boot = B.cluster_bootstrap(tiny, resamples=200, seed=1)
    assert B.share_above_zero(boot["totals"]) >= B.BOOT_MIN_P
    assert B.pct(boot["per_trade"], 0.025) > 0, \
        "the withdrawn floor is satisfied by a book with no edge"


def test_the_per_trade_figure_is_reported_and_takes_no_part_in_the_verdict():
    bs = skewed(n_sym=1500)
    boot = B.cluster_bootstrap(bs, resamples=300, seed=1)
    ok, p, lo = B.verdict(boot)
    assert ok == (p >= B.BOOT_MIN_P), "the verdict is the bootstrap bar alone"
    assert lo == B.pct(boot["per_trade"], 0.025), "and lo is still returned"


def test_the_module_no_longer_carries_a_second_threshold():
    """A withdrawn condition left in the code as a constant is one somebody
    wires back up."""
    assert not hasattr(B, "PER_TRADE_FLOOR")


def test_the_dollar_bar_lives_in_criterion_3_and_the_registration_says_so():
    txt = REGISTRATION.read_text(encoding="utf-8")
    assert "criterion 3" in txt
    assert "$1.00" in txt


# ==========================================================================
# THE NULL FOR THE OLD CRITERION
# ==========================================================================
def test_the_shuffle_holds_each_symbols_trade_count_fixed():
    """Shuffled without it, the control differs from the observation in two
    ways at once and cannot say which mattered."""
    bs = {"A": [1.0, 1.0, 1.0], "B": [-1.0], "C": [5.0, -5.0]}
    counts = sorted(len(v) for v in bs.values())
    # every shuffled share must be k/3 for some integer k, since there are
    # exactly three symbols however the pool is dealt
    for s in B.shuffled_shares(bs, resamples=50, seed=1):
        assert abs(s * 3 - round(s * 3)) < 1e-9
    assert counts == [1, 2, 3]


def test_a_skewed_book_with_no_symbol_effect_sits_INSIDE_its_own_null():
    """Every symbol here is drawn from one common distribution, so there is no
    symbol-specific breadth to find and the observed share must look ordinary
    against the shuffle. That is the evidence that retires the old criterion."""
    bs = skewed(n_sym=200, per=4, seed=11)
    _, _, obs = B.share_profitable(bs)
    shuf = B.shuffled_shares(bs, resamples=400, seed=11)
    assert B.pct(shuf, 0.05) <= obs <= B.pct(shuf, 0.95)


def test_a_book_with_a_REAL_symbol_effect_sits_outside_its_null():
    """The other half. If the old criterion ever does carry information, the
    control has to be able to say so -- otherwise it always licenses the
    retirement it was asked to justify."""
    bs = {f"G{i}": [3.0] * 4 for i in range(60)}      # all good
    bs.update({f"B{i}": [-3.0] * 4 for i in range(60)})   # all bad
    _, _, obs = B.share_profitable(bs)
    shuf = B.shuffled_shares(bs, resamples=400, seed=2)
    assert not (B.pct(shuf, 0.05) <= obs <= B.pct(shuf, 0.95))


def test_the_shuffle_is_reproducible_from_its_seed():
    bs = skewed(n_sym=50)
    assert B.shuffled_shares(bs, resamples=60, seed=7) == \
        B.shuffled_shares(bs, resamples=60, seed=7)


# ==========================================================================
# BUCKETS
# ==========================================================================
def test_the_buckets_partition_the_symbols_with_none_lost_and_none_doubled():
    """A confound table that loses rows is describing a different sample than
    the one above it."""
    bs = {f"S{i}": [1.0] * ((i % 14) + 1) for i in range(120)}
    total = sum(B.share_profitable(bs, lo, hi)[1] for lo, hi, _ in B.BUCKETS)
    assert total == len(bs)


def test_a_single_trade_symbol_is_kept_and_not_floored_away():
    """They are the thin part of the distribution the old criterion was
    mismeasuring. A floor would remove exactly the rows that motivated the
    change."""
    bs = {"ONE": [5.0], "MANY": [1.0] * 9}
    assert B.share_profitable(bs)[1] == 2
    assert B.share_profitable(bs, 1, 1)[1] == 1


# ==========================================================================
# THE REPORT
# ==========================================================================
def report(bs, resamples=200, seed=1, label="X"):
    rows = [{"symbol": s, "net": n} for s, v in bs.items() for n in v]
    return "\n".join(B.render(
        label, rows, bs,
        B.cluster_bootstrap(bs, resamples=resamples, seed=seed),
        B.shuffled_shares(bs, resamples=resamples, seed=seed), 1.0))


def test_the_report_says_why_it_failed_and_not_merely_that_it_did():
    """'Does not pass' without the number is a verdict a reader cannot
    check."""
    txt = report({f"L{i}": [-5.0] * 4 for i in range(80)})
    assert "DOES NOT pass" in txt and "is under 95%" in txt


def test_the_report_prints_the_old_criterion_beside_its_null_not_alone():
    """Printed alone it is the number a reader already has in their head, and
    it is the misleading one."""
    txt = report(skewed(n_sym=150, seed=4), resamples=300)
    assert "profitable =" in txt
    assert "shuffled" in txt
    assert "INSIDE its own null" in txt


def test_the_report_KEEPS_the_old_criterion_when_the_null_says_to():
    """The registration's escape clause. A surprising result must not quietly
    become a reason to drop it."""
    bs = {f"G{i}": [3.0] * 4 for i in range(60)}
    bs.update({f"B{i}": [-3.0] * 4 for i in range(60)})
    txt = report(bs, resamples=300, seed=2)
    assert "OUTSIDE its own null" in txt
    assert "it is KEPT" in txt


def test_the_report_prints_every_trade_count_bucket():
    bs = {f"S{i}": [1.0] * ((i % 14) + 1) for i in range(150)}
    txt = report(bs, resamples=100)
    body = txt.split("THE TRADE-COUNT CONFOUND")[1]
    for _, _, name in B.BUCKETS:
        assert f"  {name:<16}" in body


def test_the_report_says_criterion_1_is_not_implied_by_this():
    txt = report(skewed(), resamples=100)
    assert "drop-top-3" in txt and "Both are required" in txt


def test_the_report_names_the_registration():
    """So a reader can check the thresholds against the document that fixed
    them rather than against the code that applies them."""
    txt = report(skewed(), resamples=100)
    assert "REGISTERED_breadth.md" in txt


def test_the_registration_was_committed_BEFORE_the_module():
    """THE CLAIM, CHECKED AGAINST GIT RATHER THAN QUOTED AS A HASH.

    "Registered first" is the whole basis for trusting the thresholds, and for
    one afternoon this was asserted by naming a commit in prose. A rebase onto
    another chat's work rewrote that hash the same day. A hash in prose is a
    second source of truth that goes stale in silence: the reader looks it up,
    finds nothing, and cannot tell whether the registration moved or the
    reference did.

    So the property is asserted directly. The commit that ADDED the
    registration must be an ancestor of the commit that added the module.
    """
    import subprocess

    def added(path):
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", path],
            cwd=REPO, capture_output=True, text=True)
        if out.returncode != 0 or not out.stdout.strip():
            pytest.skip(f"no git history for {path} in this checkout")
        return out.stdout.split()[0]

    reg = added("docs/research/REGISTERED_breadth.md")
    mod = added("common/breadth.py")
    if reg == mod:
        pytest.fail("the registration and the module landed in one commit, so "
                    "nothing says which was decided first")
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", reg, mod],
                         cwd=REPO, capture_output=True)
    assert anc.returncode == 0, (
        "the registration must be an ancestor of the module -- a bar written "
        "after the instrument is not a bar")


def test_the_report_says_the_holdout_is_untouched():
    assert "remains unspent" in report(skewed(), resamples=100)


# ==========================================================================
# THE REGISTRATION AND THE CODE AGREE
# ==========================================================================
def test_the_thresholds_match_the_registration():
    """A threshold that drifts between the plan and the code is a threshold
    chosen after seeing the data."""
    txt = REGISTRATION.read_text(encoding="utf-8")
    assert f"**{int(B.BOOT_MIN_P * 100)}%**" in txt
    assert "2.5th percentile of per-trade net ≥ $0" in txt
    assert f"{B.RESAMPLES:,}" in txt


def test_the_thresholds_are_not_command_line_flags():
    """A threshold that can be passed in is a threshold that gets swept."""
    dests = {a.dest for a in B.build_parser()._actions}
    for forbidden in ("resamples", "seed", "min_p", "floor", "bar"):
        assert forbidden not in dests


# ==========================================================================
# LOADING
# ==========================================================================
def test_a_csv_row_without_a_net_is_skipped_rather_than_read_as_zero(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("symbol,net\nAAA,5\nBBB,\nCCC,-2\n", encoding="utf-8")
    rows = B.load_csv(p)
    assert [r["symbol"] for r in rows] == ["AAA", "CCC"]


def test_symbols_are_normalised_so_one_name_is_one_cluster(tmp_path):
    """'aaa' and 'AAA' resampled as two symbols would halve the correlation
    the cluster bootstrap exists to respect."""
    p = tmp_path / "t.csv"
    p.write_text("symbol,net\naaa,5\n AAA ,-2\n", encoding="utf-8")
    assert list(B.by_symbol(B.load_csv(p))) == ["AAA"]


def test_giving_both_or_neither_source_is_refused():
    with pytest.raises(SystemExit) as e:
        B.main([])
    assert "exactly one" in str(e.value)
    with pytest.raises(SystemExit):
        B.main(["--run-id", "x", "--csv", "y"])


def test_an_empty_sample_refuses_instead_of_rendering_a_clean_result(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("symbol,net\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        B.main(["--csv", str(p)])
    assert "Nothing to score" in str(e.value)


def test_the_report_marks_the_per_trade_interval_as_NOT_a_condition():
    """A figure printed beside a verdict it cannot change has to say so, or
    the next reader takes it for one."""
    txt = report(skewed(n_sym=300), resamples=200)
    assert "per trade over the same resamples" in txt
    assert "CONTEXT, NOT A CONDITION" in txt


def test_list_runs_writes_a_file(tmp_path, monkeypatch):
    """Every result here goes to a file. A listing that exists only in a
    terminal has to be copied by hand to be used, and a figure copied by hand
    is a figure nobody can check later. This one printed to stdout for exactly
    one afternoon."""
    monkeypatch.setattr(B, "list_runs",
                        lambda: [("mc5_screened_2026", 7403, 1791, 8217.3),
                                 ("mcl_screened_2026", 2408, 890, -1276.2)])
    out = tmp_path / "runs.txt"
    assert B.main(["--list-runs", "--runs-out", str(out)]) == 0
    txt = out.read_text(encoding="utf-8")
    assert "mc5_screened_2026" in txt and "7,403" in txt and "1,791" in txt
    assert "--run-id" in txt, "and it must say how to score one"


def test_an_empty_run_list_is_still_written_down(tmp_path, monkeypatch):
    """No file and an empty file are the same thing tomorrow, and only one of
    them means the command ran."""
    monkeypatch.setattr(B, "list_runs", lambda: [])
    out = tmp_path / "runs.txt"
    assert B.main(["--list-runs", "--runs-out", str(out)]) == 0
    assert "backtest_trade is empty" in out.read_text(encoding="utf-8")


def test_the_runs_listing_has_a_default_path_under_var_reports():
    assert B.build_parser().parse_args([]).runs_out.startswith("var/reports/")
