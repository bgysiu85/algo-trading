"""strategy.h60.data_plan -- W14-0002, REGISTERED_h60_v0.md §2.1, §2.2, §6.

Everything here runs against a fake Databento client: no network, no key.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from strategy.h60 import data_plan as P
from strategy.swing.pit_universe import Spell

D = dt.date


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------

class FakeMeta:
    """Cost and size are linear in (symbols x seconds), so the RTH share of a
    day is exactly 6.5 / 24 and every figure is predictable."""

    def __init__(self, usd_per_sym_day=0.01, bytes_per_sym_day=1000,
                 rng=("2018-05-01", "2026-09-22")):
        self.usd = usd_per_sym_day
        self.b = bytes_per_sym_day
        self.rng = rng
        self.calls = []

    def _days(self, kw):
        a = dt.datetime.fromisoformat(kw["start"])
        b = dt.datetime.fromisoformat(kw["end"])
        return (b - a).total_seconds() / 86400

    def get_cost(self, **kw):
        self.calls.append(("cost", kw))
        assert kw["stype_in"] == "raw_symbol"
        assert len(kw["symbols"]) <= P.MAX_SYMBOLS_PER_REQUEST
        return self.usd * len(kw["symbols"]) * self._days(kw)

    def get_billable_size(self, **kw):
        return int(self.b * len(kw["symbols"]) * self._days(kw))

    def get_dataset_range(self, dataset):
        return {"start": self.rng[0] + "T00:00:00.000000000Z",
                "end": self.rng[1] + "T00:00:00.000000000Z"}


class FakeSymbology:
    def __init__(self, missing=()):
        self.missing = set(missing)

    def resolve(self, **kw):
        return {"not_found": [s for s in kw["symbols"] if s in self.missing],
                "result": {}}


class FakeTS:
    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.calls = []

    def get_range(self, **kw):
        self.calls.append(kw)
        day = kw["start"][:10]
        if day in self.fail_on:
            raise RuntimeError("boom db-ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        Path(kw["path"]).write_bytes(b"x" * 10)


class FakeClient:
    def __init__(self, **kw):
        self.metadata = FakeMeta(**{k: v for k, v in kw.items()
                                    if k in ("usd_per_sym_day", "bytes_per_sym_day", "rng")})
        self.symbology = FakeSymbology(kw.get("missing", ()))
        self.timeseries = FakeTS(kw.get("fail_on", ()))


def sp(code, start=None, end=None, index="sp500"):
    return Spell(index, code, code, start, end, end is None, False)


# --------------------------------------------------------------------------
# symbol mapping -- §2.1
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code,raw", [
    ("AAPL", "AAPL"), ("BRK-B", "BRK.B"), ("BF-B", "BF.B"),
    ("SNDK_OLD", "SNDK"), ("AHL_OLD2", "AHL"), ("CNL_OLD1", "CNL"),
    ("--", None), ("", None), (" msft ", "MSFT"),
])
def test_to_raw_symbol(code, raw):
    assert P.to_raw_symbol(code) == raw


# --------------------------------------------------------------------------
# universe -- suspects excluded, hindsight guard by date
# --------------------------------------------------------------------------

def _write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


MEM = ("index,code,name,start,end,is_active_now,is_delisted\n"
       "sp500,AAA,A,2018-01-01,,1,0\n"
       "sp500,BBB,B,2018-01-01,2019-06-30,0,1\n"
       "sp400,BBB,B,2020-01-01,,1,0\n"
       "sp400,--,Temp,2018-01-01,2018-02-01,0,1\n")
SUS = ("index,code,name,start,end,is_delisted,verdict,in_window_rows,expected_rows\n"
       "sp500,BBB,B,2018-01-01,2019-06-30,1,none,0,10\n")


def test_load_universe_drops_exactly_the_suspect_spell(tmp_path):
    kept = P.load_universe(_write(tmp_path, "m.csv", MEM), _write(tmp_path, "s.csv", SUS))
    assert len(kept) == 3
    # BBB keeps its good spell
    assert [s.index for s in kept if s.code == "BBB"] == ["sp400"]


def test_load_universe_refuses_missing_suspects_file(tmp_path):
    with pytest.raises(P.Refused):
        P.load_universe(_write(tmp_path, "m.csv", MEM), tmp_path / "nope.csv")


def test_load_universe_refuses_files_from_different_runs(tmp_path):
    bad = SUS + "sp500,ZZZ,Z,2018-01-01,2019-01-01,1,none,0,1\n"
    with pytest.raises(P.Refused):
        P.load_universe(_write(tmp_path, "m.csv", MEM), _write(tmp_path, "s.csv", bad))


def test_symbols_on_respects_spell_dates():
    spells = [sp("AAA", D(2018, 1, 1)), sp("BBB", D(2020, 1, 1)),
              sp("CCC", None, D(2019, 3, 1)), sp("--")]
    assert P.symbols_on(spells, D(2019, 3, 1)) == ["AAA", "CCC"]
    assert P.symbols_on(spells, D(2019, 3, 2)) == ["AAA"]
    assert P.symbols_on(spells, D(2020, 1, 1)) == ["AAA", "BBB"]


def test_symbols_on_mutation_one_day_early_is_excluded():
    """The guard must bite at the boundary: a name is NOT eligible the day
    before its start (a guard shifted by one day would include it)."""
    spells = [sp("NEW", D(2021, 6, 21))]
    assert P.symbols_on(spells, D(2021, 6, 20)) == []
    assert P.symbols_on(spells, D(2021, 6, 21)) == ["NEW"]


def test_symbols_between_overlap():
    spells = [sp("A", D(2018, 1, 1), D(2018, 12, 31)), sp("B", D(2019, 6, 1)),
              sp("C", D(2020, 1, 1))]
    assert P.symbols_between(spells, D(2019, 1, 1), D(2019, 12, 31)) == ["B"]


def test_real_membership_file_loads():
    """The staged repo files: 35 suspects removed, and the mapped symbols are
    all plausible raw tickers."""
    m, s = Path("var/swing_pit/membership.csv"), Path("var/swing_pit/suspects.csv")
    if not (m.exists() and s.exists()):
        pytest.skip("repo var/ files not present")
    kept = P.load_universe(m, s)
    raws = P.symbols_between(kept, D(2018, 5, 1), D(2026, 9, 22))
    assert 900 < len(raws) < 1600
    assert all(r.replace(".", "").isalpha() for r in raws)


# --------------------------------------------------------------------------
# clock -- ET, DST, weekdays
# --------------------------------------------------------------------------

def test_rth_bounds_winter_and_summer():
    assert P.rth_bounds(D(2024, 1, 10)) == ("2024-01-10T14:30:00", "2024-01-10T21:00:00")
    assert P.rth_bounds(D(2024, 7, 10)) == ("2024-07-10T13:30:00", "2024-07-10T20:00:00")


def test_weekdays_and_sample_day():
    days = P.weekdays(D(2024, 9, 20), D(2024, 9, 24))   # Fri..Tue
    assert [d.isoformat() for d in days] == ["2024-09-20", "2024-09-23", "2024-09-24"]
    d = P.sample_day(D(2024, 1, 1), D(2024, 12, 31))
    assert d.weekday() == 2 and D(2024, 1, 1) <= d <= D(2024, 12, 31)
    d = P.sample_day(D(2026, 9, 1), D(2026, 9, 4))
    assert D(2026, 9, 1) <= d <= D(2026, 9, 4)


def test_chunks_respects_request_limit():
    xs = [f"S{i}" for i in range(4500)]
    parts = P.chunks(xs)
    assert [len(p) for p in parts] == [2000, 2000, 500]


# --------------------------------------------------------------------------
# pricing
# --------------------------------------------------------------------------

def test_plan_year_scales_by_measured_rth_share():
    c = FakeClient(usd_per_sym_day=0.01, bytes_per_sym_day=1000, missing={"BBB"})
    spells = [sp("AAA", D(2018, 1, 1)), sp("BBB", D(2018, 1, 1))]
    p = P.plan_year(c, "XNAS.ITCH", spells, D(2019, 1, 1), D(2019, 12, 31))
    assert p.symbols == 2 and p.not_found == ["BBB"]
    assert p.full_usd == pytest.approx(0.01 * 2 * 365)
    assert p.rth_share == pytest.approx(6.5 / 24, rel=1e-2)   # sizes are ints
    assert p.rth_usd == pytest.approx(0.01 * 2 * 365 * 6.5 / 24, rel=1e-2)


def test_plan_all_splits_by_calendar_year_and_clips():
    c = FakeClient()
    spells = [sp("AAA", D(2018, 1, 1))]
    plans = P.plan_all(c, "XNAS.ITCH", spells, D(2018, 5, 1), D(2020, 3, 31))
    assert [(p.year, p.first, p.last) for p in plans] == [
        (2018, D(2018, 5, 1), D(2018, 12, 31)),
        (2019, D(2019, 1, 1), D(2019, 12, 31)),
        (2020, D(2020, 1, 1), D(2020, 3, 31))]


def test_grid_verdict_thresholds():
    def yp(usd, nb):
        return P.YearPlan(2020, D(2020, 1, 1), D(2020, 12, 31), 1, [], usd, nb,
                          1.0, 0.0, 0)
    assert P.grid_verdict([yp(0.0, 1e9)]).startswith("PRIMARY")
    assert P.grid_verdict([yp(50.01, 1e9)]).startswith("FALLBACK")
    assert P.grid_verdict([yp(0.0, 25.1e9)]).startswith("FALLBACK")
    assert P.grid_verdict([yp(50.0, 25e9)]).startswith("PRIMARY")


def test_dataset_range_both_shapes_and_refusal():
    class M:
        def __init__(self, r): self.r = r
        def get_dataset_range(self, dataset): return self.r

    class C:
        def __init__(self, r): self.metadata = M(r)
    assert P.dataset_range(C({"start_date": "2018-05-01", "end_date": "2026-09-22"}),
                           "X") == (D(2018, 5, 1), D(2026, 9, 22))
    with pytest.raises(P.Refused):
        P.dataset_range(C({}), "X")


def test_report_mentions_totals_and_grid():
    c = FakeClient()
    plans = P.plan_all(c, "XNAS.ITCH", [sp("AAA", D(2018, 1, 1))],
                       D(2019, 1, 1), D(2019, 12, 31))
    txt = P.report("XNAS.ITCH", (D(2018, 5, 1), D(2026, 9, 22)), D(2019, 1, 1),
                   D(2019, 12, 31), plans, 1)
    assert "TOTAL" in txt and "GRID: PRIMARY" in txt
    assert "Nothing has been downloaded" in txt


# --------------------------------------------------------------------------
# the archive guard -- §6.3
# --------------------------------------------------------------------------

def test_guard_refuses_the_shared_root(tmp_path):
    shared = tmp_path / "Databento"
    shared.mkdir()
    with pytest.raises(P.Refused):
        P.guard_archive(shared, shared)
    with pytest.raises(P.Refused):
        P.guard_archive(shared / "XNAS.ITCH", shared)
    assert P.guard_archive(shared / "H60", shared) == (shared / "H60").resolve()


def test_rth_root_never_uses_the_shared_schema_folder(tmp_path):
    r = P.rth_root(tmp_path / "Databento" / "H60")
    assert r.name == "ohlcv-1m-rth" and r.parent.name == "XNAS.ITCH"
    assert "H60" in r.parts


def test_rth_root_does_not_double_the_h60_segment(tmp_path):
    """rth_root() takes the H60 root directly (as guard_archive() and
    run.py's archive_root() both return, and as --archive is documented on
    both CLIs) -- it must not append another H60_SUBDIR on top. This is the
    defect W14-0004 hit: 2192 real sessions were pulled to
    <H60 root>/H60/<dataset>/<rth dir> before it was caught."""
    h60_root = tmp_path / "Databento" / "H60"
    r = P.rth_root(h60_root)
    assert r == h60_root / P.DATASET / P.RTH_DIR
    assert r.parts.count("H60") == 1


def test_main_pull_and_run_build_cache_agree_on_where_files_land(tmp_path, monkeypatch):
    """Cross-check the two real call sites that write/read the RTH directory:
    data_plan.main()'s --pull (via pull() -> rth_root()) and run.py's
    --build-cache (via archive_root() + rth_root()) must land on the exact
    same directory for the same shared archive, with no double H60."""
    from strategy.h60 import run as RUN
    shared = tmp_path / "Databento"
    shared.mkdir()
    monkeypatch.setattr("common.databento_fetch.default_archive", lambda: str(shared))
    pull_root = P.guard_archive(shared / P.H60_SUBDIR, shared)
    pull_dir = P.rth_root(pull_root)
    build_cache_root = RUN.archive_root(None)
    build_cache_dir = build_cache_root / P.DATASET / P.RTH_DIR
    assert pull_dir == build_cache_dir
    assert str(pull_dir).count("H60") == 1


# --------------------------------------------------------------------------
# pulling
# --------------------------------------------------------------------------

def test_pull_writes_skips_and_retries(tmp_path, capsys):
    root = tmp_path / "H60"
    spells = [sp("AAA", D(2018, 1, 1)), sp("BBB", D(2018, 1, 1))]
    days = P.weekdays(D(2024, 7, 8), D(2024, 7, 12))        # Mon..Fri
    c = FakeClient(fail_on={"2024-07-10"})
    res = P.pull(c, "XNAS.ITCH", spells, days, root)
    assert (res["written"], res["skipped"], res["failed"]) == (4, 0, 1)
    out = P.rth_root(root)
    assert not list(out.glob("*.partial"))
    assert not (out / "2024-07-10.dbn.zst").exists()
    # the key never reaches the log
    assert "ABCDEFGHIJ" not in capsys.readouterr().out
    # every request is RTH only, members only
    kw = c.timeseries.calls[0]
    assert kw["start"].endswith("13:30:00") and kw["end"].endswith("20:00:00")
    assert kw["symbols"] == ["AAA", "BBB"] and kw["schema"] == "ohlcv-1m"
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(man) == ["2024-07-08", "2024-07-09", "2024-07-11", "2024-07-12"]

    c2 = FakeClient()
    res2 = P.pull(c2, "XNAS.ITCH", spells, days, root)
    assert (res2["written"], res2["skipped"], res2["failed"]) == (1, 4, 0)
    assert [k["start"][:10] for k in c2.timeseries.calls] == ["2024-07-10"]


def test_pull_asks_only_for_that_days_members(tmp_path):
    spells = [sp("OLD", None, D(2024, 7, 9)), sp("NEW", D(2024, 7, 10))]
    c = FakeClient()
    P.pull(c, "XNAS.ITCH", spells, [D(2024, 7, 9), D(2024, 7, 10)], tmp_path / "H60")
    assert [k["symbols"] for k in c.timeseries.calls] == [["OLD"], ["NEW"]]
