#!/usr/bin/env python3
"""Tests for strategy/swing -- the G2 spread measurement pair.

WHAT IS ACTUALLY WORTH TESTING HERE
------------------------------------
The collector's value is a CSV nobody can check after the fact: once a session
is over, a row that was silently wrong is indistinguishable from a row that was
right. So the tests concentrate on the three places where a defect would
produce a number that LOOKS like a measurement:

  1. DELAYED DATA POOLED AS LIVE. A delayed quote populates bid and ask exactly
     like a live one. If md_type filtering broke, every figure downstream would
     be precise and meaningless, and nothing in the output would say so. Tested
     from both sides: delayed rows must be counted AND excluded, and a file of
     nothing but delayed rows must produce a refusal rather than an empty table.

  2. ET BUCKETING ACROSS THE DST CHANGE. US eastern is UTC-4 in summer and
     UTC-5 in winter. A run that straddles the change, bucketed with a fixed
     offset, would relabel half its rows by an hour -- and a mislabelled 09:30
     bucket reads as a real finding about the open. Tested on both sides.

  3. THE GUARDS THAT ONLY FIRE ON A LIVE SOCKET. The port allowlist and the
     DU-prefix account check are the project's standing protections. A guard
     reachable only through a real IB connection is a guard nothing ever
     exercises, which is why check_accounts() was lifted out of run().

Everything else here is ordinary arithmetic coverage.

NOTE ON WRITES. tests/conftest.py exists because tools in this repo default
their --out into var/reports/, and a test that calls main() without overriding
it destroys a real artefact. The collector here does exactly that. So every
test below that calls main() passes an explicit path under tmp_path, and
test_main_writes_exactly_one_file_and_only_where_told and
test_main_without_out_writes_nothing_at_all check the habit in an empty cwd
rather than trusting it. The conftest guard does not cover these two modules,
because they write
with Path.write_text rather than common.report_io.emit -- deliberately, since
they must run with no repo imports.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from strategy.swing import spread_report as R
from strategy.swing import spread_sampler as S


# --------------------------------------------------------------- helpers ----

HEADER = ["ts_utc", "symbol", "bid", "ask", "bid_size", "ask_size",
          "last", "volume", "md_type", "batch"]


def write_csv(path: Path, rows: list[list]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def quote(sym="AAPL", bid=250.00, ask=250.02, bsz=500, asz=600,
          md=1, minute=30, hour=13, date="2026-07-01"):
    return [f"{date}T{hour:02d}:{minute:02d}:00Z", sym, bid, ask, bsz, asz,
            round((bid + ask) / 2, 4), 1_000_000, md, 0]


class Args:
    """Stand-in for the argparse namespace build() reads."""
    csv = ["synthetic"]
    min_obs = 10
    position_usd = 9000.0
    max_rel = 0.10


# ------------------------------------------------------------ arithmetic ----

def test_percentiles_interpolate_and_handle_singletons():
    assert R.pct([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert R.pct([1, 2, 3, 4], 0) == pytest.approx(1)
    assert R.pct([1, 2, 3, 4], 100) == pytest.approx(4)
    assert R.pct([10], 90) == pytest.approx(10)
    assert R.pct([], 50) != R.pct([], 50)          # nan
    # order must not matter
    assert R.pct([4, 1, 3, 2], 50) == pytest.approx(2.5)


def test_negatives_render_in_accounting_brackets():
    """The repo's report convention, and the reason report_fmt exists."""
    assert R.fmt(-4.08, 8, 2).strip() == "(4.08)"
    assert R.fmt(-29.66, 9, 2).strip() == "(29.66)"
    assert R.fmt(3.6, 8, 2).strip() == "3.60"
    assert R.fmt(float("nan"), 8, 2).strip() == "n/a"


def test_bps_and_cents_are_computed_from_the_same_quote(tmp_path):
    # 2c on a 250.01 mid is 0.7999.. bps
    p = write_csv(tmp_path / "s.csv", [quote() for _ in range(20)])
    rows, _, _ = R.load([str(p)], 0.10)
    assert rows[0]["cents"] == pytest.approx(2.0)
    assert rows[0]["bps"] == pytest.approx(0.79997, rel=1e-3)


# ------------------------------------------------------------------ time ----

def test_et_bucketing_survives_both_sides_of_dst():
    """UTC-4 in summer, UTC-5 in winter, derived from the date not assumed."""
    assert R.et_bucket("2026-07-01T13:30:00Z") == "09:30"   # EDT
    assert R.et_bucket("2026-01-05T14:30:00Z") == "09:30"   # EST
    assert R.et_bucket("2026-07-01T20:00:00Z") == "16:00"   # EDT close
    assert R.et_bucket("2026-01-05T21:00:00Z") == "16:00"   # EST close


def test_et_bucketing_rounds_down_to_the_half_hour():
    assert R.et_bucket("2026-07-01T13:59:00Z") == "09:30"
    assert R.et_bucket("2026-07-01T14:00:00Z") == "10:00"
    assert R.et_bucket("2026-07-01T14:29:00Z") == "10:00"


def test_dst_boundary_days_pick_different_offsets():
    """The two days either side of the change must not share an offset."""
    before = R.et_bucket("2026-03-07T14:30:00Z")   # still EST
    after = R.et_bucket("2026-03-10T14:30:00Z")    # EDT
    assert before != after


# ------------------------------------------------- the delayed-data trap ----

def test_delayed_rows_are_counted_and_never_pooled(tmp_path):
    rows_in = [quote(md=1) for _ in range(20)]
    rows_in += [quote(sym="XXX", md=3) for _ in range(5)]
    p = write_csv(tmp_path / "s.csv", rows_in)

    rows, rej, total = R.load([str(p)], 0.10)
    assert total == 25
    assert len(rows) == 20
    assert rej.not_live == 5
    assert {r["sym"] for r in rows} == {"AAPL"}          # XXX never survives
    assert rej.md_types["3"] == 5


def test_report_refuses_when_every_row_is_delayed(tmp_path):
    """An empty table is not an acceptable answer here -- it looks like 'no
    data' when the truth is 'the wrong data'."""
    p = write_csv(tmp_path / "s.csv", [quote(md=3) for _ in range(40)])
    rows, rej, total = R.load([str(p)], 0.10)
    assert rows == []

    txt = R.build(rows, rej, total, Args)
    assert "NO USABLE ROWS" in txt
    assert "market data type" in txt
    assert "delayed" in txt.lower()
    # and it must not quietly suggest accepting them
    assert "do not 'work around'" in txt


def test_frozen_data_is_rejected_too(tmp_path):
    p = write_csv(tmp_path / "s.csv", [quote(md=2) for _ in range(10)])
    rows, rej, _ = R.load([str(p)], 0.10)
    assert rows == []
    assert rej.not_live == 10


# ----------------------------------------------------- bad quote handling ----

def test_missing_crossed_and_stub_quotes_are_rejected_separately(tmp_path):
    rows_in = [quote() for _ in range(10)]
    rows_in.append(["2026-07-01T13:30:00Z", "YYY", "", "", "", "",
                    "", "", 1, 0])                          # missing
    rows_in.append(quote(sym="ZZZ", bid=10.5, ask=10.0))     # crossed
    rows_in.append(quote(sym="WWW", bid=0, ask=0))           # non-positive
    rows_in.append(quote(sym="VVV", bid=10.0, ask=30.0))     # stub, 100% wide
    p = write_csv(tmp_path / "s.csv", rows_in)

    rows, rej, total = R.load([str(p)], 0.10)
    assert total == 14 and len(rows) == 10
    assert rej.missing == 1
    assert rej.crossed == 1
    assert rej.nonpositive == 1
    assert rej.wide == 1
    assert rej.total() == 4


def test_rejects_are_accounted_for_exactly(tmp_path):
    """rows read = rows usable + rows rejected, with no leakage."""
    rows_in = [quote() for _ in range(7)]
    rows_in += [quote(md=3) for _ in range(3)]
    rows_in.append(quote(bid=10.5, ask=10.0))
    p = write_csv(tmp_path / "s.csv", rows_in)
    rows, rej, total = R.load([str(p)], 0.10)
    assert total == len(rows) + rej.total()


# ---------------------------------------------------------------- report ----

def _two_symbol_file(tmp_path):
    rows_in = [quote(sym="AAPL", bid=250.00, ask=250.02, bsz=500, asz=600,
                     minute=30 + i % 20) for i in range(40)]
    rows_in += [quote(sym="CLF", bid=12.00, ask=12.04, bsz=300, asz=200,
                      minute=30 + i % 20) for i in range(40)]
    return write_csv(tmp_path / "s.csv", rows_in)


def test_report_contains_every_required_section(tmp_path):
    p = _two_symbol_file(tmp_path)
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    for section in ("COVERAGE", "POOLED QUOTED SPREAD", "BY SYMBOL",
                    "DEPTH AGAINST", "BY TIME OF DAY", "ALL-IN ROUND TRIP",
                    "WHAT COULD BE WRONG WITH THIS"):
        assert section in txt, f"missing section {section}"


def test_report_is_pure_ascii(tmp_path):
    """A report that reaches a .txt on Windows must not carry anything a
    cp1252 console cannot print."""
    p = _two_symbol_file(tmp_path)
    rows, rej, total = R.load([str(p)], 0.10)
    assert R.build(rows, rej, total, Args).isascii()


def test_report_carries_no_ansi_escapes(tmp_path):
    p = _two_symbol_file(tmp_path)
    rows, rej, total = R.load([str(p)], 0.10)
    assert "\x1b" not in R.build(rows, rej, total, Args)


def test_g2_verdict_follows_the_threshold(tmp_path):
    """A 4c spread on a $12 stock is ~33 bps: under 40, so PASS."""
    p = write_csv(tmp_path / "s.csv",
                  [quote(sym="CLF", bid=12.00, ask=12.04) for _ in range(30)])
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    assert "PASS" in txt

    # a 9% spread is ~900 bps: FAIL, and max_rel must be loose enough to admit
    # it so the failure is reported rather than filtered away
    p2 = write_csv(tmp_path / "s2.csv",
                   [quote(sym="THIN", bid=10.00, ask=10.90) for _ in range(30)])
    rows, rej, total = R.load([str(p2)], 0.10)
    txt2 = R.build(rows, rej, total, Args)
    assert "FAIL" in txt2


def test_depth_flag_fires_when_the_book_is_thinner_than_the_position(tmp_path):
    """100 shares of a $12 stock is $1,200 of depth against a $9,000 order."""
    p = write_csv(tmp_path / "s.csv",
                  [quote(sym="CLF", bid=12.00, ask=12.04, bsz=100, asz=100)
                   for _ in range(30)])
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    assert "SMALLER than the target" in txt
    assert "CLF" in txt


def test_deep_book_does_not_raise_the_depth_flag(tmp_path):
    p = write_csv(tmp_path / "s.csv",
                  [quote(sym="AAPL", bsz=5000, asz=5000) for _ in range(30)])
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    assert "Spread is the binding cost" in txt


def test_symbols_below_min_obs_get_no_percentiles(tmp_path):
    """A spread from nine quotes is not a distribution."""
    rows_in = [quote(sym="AAPL") for _ in range(30)]
    rows_in += [quote(sym="THIN") for _ in range(3)]
    p = write_csv(tmp_path / "s.csv", rows_in)
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    assert "below --min-obs" in txt
    assert "THIN(3)" in txt


def test_time_of_day_table_separates_the_open(tmp_path):
    """The open must land in its own bucket, not be averaged into the day."""
    rows_in = [quote(sym="AAPL", bid=250.00, ask=250.20, hour=13, minute=30)
               for _ in range(20)]                       # wide at the open
    rows_in += [quote(sym="AAPL", bid=250.00, ask=250.02, hour=16, minute=0)
                for _ in range(20)]                      # tight midday
    p = write_csv(tmp_path / "s.csv", rows_in)
    rows, rej, total = R.load([str(p)], 0.10)
    txt = R.build(rows, rej, total, Args)
    assert "09:30" in txt and "12:00" in txt


# ----------------------------------------------------------- the guards ----

def test_live_ports_are_refused_by_name():
    """Refused BY NAME, so the message says what was blocked and why."""
    for port, name in S.PORTS_REFUSED.items():
        with pytest.raises(SystemExit) as e:
            S.check_port(port)
        assert name in str(e.value), f"port {port} refused without naming it"


def test_unknown_ports_are_refused_as_not_allowlisted():
    with pytest.raises(SystemExit) as e:
        S.check_port(1234)
    assert "allowlist" in str(e.value)


def test_paper_ports_are_accepted():
    for port in S.PORTS_ALLOWED:
        S.check_port(port)          # must not raise


def test_the_allowlist_and_the_refusal_list_do_not_overlap():
    """A port in both lists would be accepted or refused by ordering luck."""
    assert not (set(S.PORTS_ALLOWED) & set(S.PORTS_REFUSED))


@pytest.mark.parametrize("accounts,ok", [
    (["DUM215828"], True),
    (["DU111", "DU222"], True),
    (["U1234567"], False),
    (["DUM215828", "U1234567"], False),     # one live account is enough to stop
    ([], False),
])
def test_du_prefix_account_guard(accounts, ok):
    if ok:
        S.check_accounts(accounts)
    else:
        with pytest.raises(SystemExit):
            S.check_accounts(accounts)


def test_the_sampler_places_no_orders():
    """The strongest form of the read-only rule: the capability is absent."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    for forbidden in ("placeOrder", "bracketOrder", "MarketOrder",
                      "LimitOrder", "StopOrder"):
        assert forbidden not in src, f"{forbidden} appears in the collector"


# --------------------------------------------------------------- universe ----

def test_default_universe_matches_the_preflight():
    """36 names plus SPY -- the same names the move sizes were measured on."""
    u = S.load_universe(None)
    assert len(u) == 37
    assert "SPY" in u
    assert len(set(u)) == len(u), "duplicate symbol in the default universe"


def test_universe_file_handles_comments_commas_and_duplicates(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# a comment\nAAPL, MSFT\n\nnvda  # trailing comment\nAAPL\n",
                 encoding="utf-8")
    assert S.load_universe(str(f)) == ["AAPL", "MSFT", "NVDA"]


def test_missing_universe_file_exits_rather_than_falling_back(tmp_path):
    """Silently using the default would measure a universe nobody asked for."""
    with pytest.raises(SystemExit):
        S.load_universe(str(tmp_path / "nope.txt"))


def test_empty_universe_file_exits(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        S.load_universe(str(f))


# -------------------------------------------------------------- batching ----

def test_batching_never_loses_or_duplicates_a_symbol():
    for n, size in ((37, 45), (100, 45), (45, 45), (1, 45), (90, 30)):
        items = list(range(n))
        b = S.batches(items, size)
        flat = [x for grp in b for x in grp]
        assert flat == items
        assert all(len(grp) <= size for grp in b)


def test_a_universe_that_fits_is_a_single_batch():
    assert len(S.batches(list(range(37)), 45)) == 1


# ------------------------------------------------------------------ writer ----

def test_writer_appends_rather_than_truncating(tmp_path):
    """A reconnect mid-session must not discard the morning."""
    p = tmp_path / "s.csv"
    w1 = S.Writer(p)
    w1.write_row(dict(zip(S.FIELDS, ["t", "AAPL", 1, 2, 3, 4, 5, 6, 1, 0])))
    w1.close()
    w2 = S.Writer(p)
    w2.write_row(dict(zip(S.FIELDS, ["t", "MSFT", 1, 2, 3, 4, 5, 6, 1, 0])))
    w2.close()

    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert [r["symbol"] for r in rows] == ["AAPL", "MSFT"]
    assert p.read_text(encoding="utf-8").count("ts_utc") == 1, "header repeated"


def test_nan_and_negative_sizes_become_empty_not_zero():
    """IB serves nan for 'not known yet' and -1 for 'no size'. Writing either
    as 0 would turn an absent quote into a zero spread."""
    assert S._num(float("nan")) == ""
    assert S._num(-1) == ""
    assert S._num(None) == ""
    assert S._num(250.02) == 250.02
    assert S._num(0) == 0


# ----------------------------------------------------------------- writes ----

def test_main_writes_exactly_one_file_and_only_where_told(tmp_path, monkeypatch):
    """conftest.py's lesson: a tool that defaults --out into var/reports will
    overwrite a real artefact if a test forgets to override it. Run in an empty
    cwd so anything written implicitly is visible."""
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)

    src = write_csv(tmp_path / "s.csv", [quote() for _ in range(30)])
    out = tmp_path / "report.txt"
    assert R.main([str(src), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip()
    assert list(work.rglob("*")) == [], "main() wrote outside --out"


def test_main_without_out_writes_nothing_at_all(tmp_path, monkeypatch):
    """The report prints by default. It must not create var/reports/ on its
    own -- the collector owns that path, and a stray write there is how a real
    artefact gets replaced by test output."""
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)

    src = write_csv(tmp_path / "s.csv", [quote() for _ in range(30)])
    assert R.main([str(src)]) == 0
    assert list(work.rglob("*")) == [], "main() created files without --out"


def test_missing_input_exits_rather_than_reporting_on_nothing(tmp_path):
    with pytest.raises(SystemExit):
        R.main([str(tmp_path / "absent.csv")])


# ------------------------------------------------------- the self-tests ----

def test_sampler_self_test_passes(capsys):
    assert S.self_test() == 0
    assert "PASS" in capsys.readouterr().out


def test_report_self_test_passes(capsys):
    assert R.self_test() == 0
    assert "PASS" in capsys.readouterr().out
