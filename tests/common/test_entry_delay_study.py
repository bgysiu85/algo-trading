#!/usr/bin/env python3
"""The A/B that priced the live entry minute.

The module's whole job is a difference between two runs, so what is tested is
the pairing, the signing, and the guards that stop a small unstable number
being read as a finding.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import entry_delay_study as E


def t(net, exit_time="2026-03-02 05:00:00"):
    return SimpleNamespace(net=net, exit_time=exit_time)


def rows(nets, date="2026-01-01", sym="AAA", exits=None):
    exits = exits or [f"2026-03-02 05:{i:02d}:00" for i in range(len(nets))]
    return [(sym, date, t(n, e)) for n, e in zip(nets, exits)]


# --- the summary -------------------------------------------------------------

def test_friction_is_charged_on_every_trade():
    """Comparing two fill assumptions while ignoring fill cost compares two
    fictions."""
    s = E.summarise("x", rows([10.0, 10.0]))
    assert s["net"] == pytest.approx(20.0 - 2 * E.MEASURED_FRICTION)


def test_drop_top_three_removes_this_variants_own_winners():
    s = E.summarise("x", rows([100.0, 50.0, 20.0, -5.0, -5.0]))
    assert s["dropped"] == pytest.approx(
        s["net"] - sum(sorted([100.0, 50.0, 20.0, -5.0, -5.0],
                              reverse=True)[:3]) + 3 * E.MEASURED_FRICTION)


def test_the_halves_split_is_a_fixed_date():
    """A split at the median of the TRADES moves when the entry rule moves,
    which makes the control a function of the thing under test."""
    early = E.summarise("x", rows([10.0], date="2020-01-01"))
    late = E.summarise("x", rows([10.0], date="2030-01-01"))
    assert early["early"] != 0 and early["late"] == 0
    assert late["late"] != 0 and late["early"] == 0
    assert E.SPLIT == "2026-03-20"


# --- pairing -----------------------------------------------------------------

def test_only_trades_that_exited_on_the_same_bar_are_paired():
    """A delayed entry that changes the EXIT is a different trade, not a worse
    fill on the same one. Averaging the two kinds answers neither question."""
    base = rows([10.0, 20.0], exits=["A", "B"])
    late = rows([8.0, 99.0], exits=["A", "Z"])
    got = E.pair(base, late)
    assert len(got) == 1
    assert (got[0][0].net, got[0][1].net) == (10.0, 8.0)


def test_a_base_trade_is_consumed_once():
    """Two delayed trades must not both claim the same baseline, or a symbol
    that traded twice reports a doubled difference."""
    base = rows([10.0], exits=["A"])
    late = rows([8.0, 7.0], exits=["A", "A"])
    assert len(E.pair(base, late)) == 1


def test_pairing_does_not_cross_symbols_or_dates():
    base = [("AAA", "2026-01-01", t(10.0, "A"))]
    late = [("BBB", "2026-01-01", t(8.0, "A")),
            ("AAA", "2026-01-02", t(8.0, "A"))]
    assert E.pair(base, late) == []


# --- the report --------------------------------------------------------------

def report(base_nets, late_nets, **kw):
    base = rows(base_nets, **kw)
    late = rows(late_nets, **kw)
    return "\n".join(E.render(base, late, 373))


def test_a_sign_flip_between_halves_is_called_out():
    """A total that hides an effect helping one half and hurting the other is
    the kind of number this project has acted on before and should not."""
    base = rows([10.0], date="2020-01-01") + rows([10.0], date="2030-01-01")
    late = rows([30.0], date="2020-01-01") + rows([-30.0], date="2030-01-01")
    text = "\n".join(E.render(base, late, 373))
    assert "SIGN FLIPS" in text


def test_no_flip_claim_when_both_halves_agree():
    base = rows([10.0], date="2020-01-01") + rows([10.0], date="2030-01-01")
    late = rows([5.0], date="2020-01-01") + rows([5.0], date="2030-01-01")
    assert "SIGN FLIPS" not in "\n".join(E.render(base, late, 373))


def test_a_negative_drop_top_three_is_stated_plainly():
    """Both variants failing drop-top-3 means this is an optimisation inside
    something with no demonstrated edge, and the report must say so rather
    than let the headline be quoted."""
    text = report([100.0, 1.0, 1.0, 1.0], [90.0, 1.0, 1.0, 1.0])
    assert "no" in text and "demonstrated edge" in text


def test_the_report_gives_the_median_not_just_the_total():
    """The total is dominated by a few trades where a minute landed well or
    badly on a fast bar; the median is the per-trade truth."""
    text = report([10.0] * 5, [8.0] * 5)
    assert "median" in text
    assert "dominated by a handful" in text


def test_the_report_says_an_earlier_entry_is_not_a_longer_ride():
    """The peak is set by the market, so the trade exits in the same place
    having paid less. Without this a reader sizes the prize as the whole move."""
    text = report([10.0], [8.0])
    assert "not the move" in text


def test_the_report_states_the_measured_delay_it_is_pricing():
    text = report([10.0], [8.0])
    assert "60s" in text and "three signals out of three" in text
