#!/usr/bin/env python3
"""Guards on a tool that can spend money.

The reason these exist: the same date range priced at $1,500 with
symbols="ALL_SYMBOLS" and under a cent scoped to the two tickers actually
wanted. Nothing here touches the network -- these pin the filtering, the
archive layout and the spend guards, which is where a mis-specified request
turns into a bill.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import databento_fetch as F


def pairs_file(tmp_path, pairs):
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": s, "date": d} for s, d in pairs], open(p, "w"))
    return p


def test_pairs_load_deduped_and_sorted(tmp_path):
    p = pairs_file(tmp_path, [("B", "2025-06-04"), ("A", "2025-06-04"),
                              ("A", "2025-06-04")])
    assert F.load_pairs(p) == [("A", "2025-06-04"), ("B", "2025-06-04")]


def test_before_and_after_are_half_open_and_do_not_overlap(tmp_path):
    """--before X and --after X must partition, not double-count. Fetching a
    day twice is a real cost, and dropping one is a silent hole."""
    ps = [("A", "2025-09-05"), ("B", "2025-09-06"), ("C", "2025-09-07")]
    before = F.filter_pairs(ps, before="2025-09-06")
    after = F.filter_pairs(ps, after="2025-09-06")
    assert before == [("A", "2025-09-05")]
    assert after == [("B", "2025-09-06"), ("C", "2025-09-07")]
    assert set(before) | set(after) == set(ps)
    assert not (set(before) & set(after))


def test_missing_from_cache_reads_the_real_filenames(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "AAA_2025-06-04.csv.gz").write_bytes(b"")
    got = F.filter_pairs([("AAA", "2025-06-04"), ("BBB", "2025-06-04")],
                         missing_from_cache=str(cache))
    assert got == [("BBB", "2025-06-04")]


def test_symbols_are_grouped_per_date(tmp_path):
    """One request per date carrying every symbol wanted that day. Requesting
    each symbol-day separately multiplies the request count by ~3 for no extra
    data and runs into rate limits."""
    g = F.group_by_date([("B", "2025-06-04"), ("A", "2025-06-04"),
                         ("C", "2025-06-06")])
    assert g == {"2025-06-04": ["A", "B"], "2025-06-06": ["C"]}


def test_archive_path_is_stable(tmp_path):
    """The skip-if-present guard is only as good as this being deterministic.
    If the path ever changes shape, every previously bought file is re-bought."""
    p = F.archive_path(Path("databento"), "EQUS.ALL", "tbbo", "2025-06-04")
    assert p == Path("databento/EQUS.ALL/tbbo/2025-06-04.dbn.zst")


def test_a_key_is_never_echoed(monkeypatch):
    monkeypatch.setenv("DATABENTO_API_KEY", "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    assert F._key().startswith("db-")
    leaked = "HTTP 401 for key db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 at /v0/x"
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in F._scrub(leaked)
    assert "<redacted>" in F._scrub(leaked)


def test_no_key_exits_rather_than_calling_with_an_empty_one(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        F._key()


class FakeMeta:
    def __init__(self, usd, size):
        self.usd, self.size = usd, size

    def get_cost(self, **kw):
        return self.usd

    def get_billable_size(self, **kw):
        return self.size


class FakeClient:
    def __init__(self, usd=0.01, size=60_900):
        self.metadata = FakeMeta(usd, size)


def test_plan_skips_files_already_on_disk_and_charges_nothing_for_them(tmp_path):
    """Re-running must be free. If this regresses, every re-run re-buys the
    whole archive and the bill scales with how often the tool is used."""
    root = tmp_path / "archive"
    got = F.archive_path(root, "EQUS.ALL", "tbbo", "2025-06-04")
    got.parent.mkdir(parents=True)
    got.write_bytes(b"already here")

    groups = {"2025-06-04": ["APLD", "QIPT"], "2025-06-06": ["APLD"]}
    jobs, usd, size = F.plan(FakeClient(), groups, "EQUS.ALL", ["tbbo"], root, 5)

    skipped = [j for j in jobs if j[8]]
    todo = [j for j in jobs if not j[8]]
    assert len(skipped) == 1 and len(todo) == 1
    assert usd == pytest.approx(0.01)      # only the one not on disk
    assert size == 60_900


def test_plan_pulls_warm_up_days_before_the_session(tmp_path):
    """A symbol-day is not one calendar day. MCL needs two sessions ending
    09:30, so a single-day window would return bars the backtest cannot use and
    the error would show up as 'too short for full warm-up' skips, not as a
    fetch failure."""
    jobs, _, _ = F.plan(FakeClient(), {"2025-06-09": ["APLD"]},
                        "EQUS.ALL", ["ohlcv-1m"], tmp_path, 5)
    _day, _syms, _schema, start, end, *_ = jobs[0]
    assert start == "2025-06-04"
    assert end == "2025-06-10"             # end is exclusive, so day + 1


# --- data quality -----------------------------------------------------------

class FakeMetaCond(FakeMeta):
    def __init__(self, usd, size, rows):
        super().__init__(usd, size)
        self.rows = rows

    def get_dataset_condition(self, **kw):
        return self.rows


class FakeClientCond(FakeClient):
    def __init__(self, rows):
        self.metadata = FakeMetaCond(0.01, 100, rows)


def test_degraded_days_are_surfaced_not_just_warned_about(tmp_path):
    """Databento emits a BentoWarning to stderr and hands over the file anyway.

    Two of the first eight days pulled came back 'degraded'. On a 587-day pull
    those warnings scroll past, and afterwards a degraded file is byte-for-byte
    indistinguishable from a clean one -- a thin pre-market session and a
    session that was not properly captured look the same in the bars.
    """
    rows = [{"date": "2025-06-04", "condition": "degraded"},
            {"date": "2025-06-06", "condition": "available"}]
    got = F.conditions(FakeClientCond(rows), "EQUS.MINI",
                       ["2025-06-04", "2025-06-06"])
    assert got == {"2025-06-04": "degraded", "2025-06-06": "available"}
    assert [d for d, c in got.items() if c != "available"] == ["2025-06-04"]


def test_a_condition_lookup_failure_does_not_abort_the_fetch(tmp_path):
    """Quality metadata is a nice-to-have; losing it must not cost the data."""
    class Broken(FakeClient):
        def __init__(self):
            super().__init__()
            self.metadata.get_dataset_condition = self._boom

        @staticmethod
        def _boom(**kw):
            raise RuntimeError("503")

    assert F.conditions(Broken(), "EQUS.MINI", ["2025-06-04"]) == {}


def test_manifest_merges_and_never_drops_earlier_entries(tmp_path):
    """The archive is built incrementally over months. If a later pull
    overwrote the manifest, the record of which days were degraded when they
    were captured would be lost -- and that record is the only thing that makes
    bought data trustworthy after the plan window has rolled past it."""
    root = tmp_path / "arch"
    F.write_manifest(root, "EQUS.MINI",
                     {"tbbo/2025-06-04": {"condition": "degraded"}})
    F.write_manifest(root, "EQUS.MINI",
                     {"tbbo/2025-06-06": {"condition": "available"}})
    m = json.load(open(F.manifest_path(root, "EQUS.MINI")))
    assert set(m) == {"tbbo/2025-06-04", "tbbo/2025-06-06"}
    assert m["tbbo/2025-06-04"]["condition"] == "degraded"


def test_a_corrupt_manifest_is_replaced_not_fatal(tmp_path):
    root = tmp_path / "arch"
    p = F.manifest_path(root, "EQUS.MINI")
    p.parent.mkdir(parents=True)
    p.write_text("{ not json")
    F.write_manifest(root, "EQUS.MINI", {"tbbo/2025-06-04": {"condition": "ok"}})
    assert json.load(open(p))["tbbo/2025-06-04"]["condition"] == "ok"


# --- universe chunking ------------------------------------------------------

def test_month_chunks_are_contiguous_and_never_overlap():
    """Overlapping chunks double-count volume in the daily archive, and
    dbn_io.daily_frame() can only warn about it after the fact. Non-overlap is
    the property that keeps every relative-volume figure downstream honest."""
    from common.databento_universe import month_chunks
    ch = month_chunks("2023-03-28", "2026-09-05")
    assert ch[0][1] == "2023-03-28"          # honours the real start
    assert ch[-1][2] == "2026-09-05"         # and the real end
    for a, b in zip(ch, ch[1:]):
        assert a[2] == b[1], f"gap or overlap between {a} and {b}"


def test_end_is_clamped_to_what_the_dataset_actually_holds():
    """The default --end is today, historical lands T+1, so an unclamped run
    fails its LAST chunk every single time -- 42 of 43 written, exit 0, and a
    month missing. The clamp is reported, never silent."""
    from common.databento_universe import clamp_to_dataset

    class C:
        class metadata:
            @staticmethod
            def get_dataset_range(dataset):
                return {"start": "2023-03-28", "end": "2026-09-05"}

    s, e, notes = clamp_to_dataset(C(), "EQUS.MINI", "2020-01-01", "2026-09-06")
    assert (s, e) == ("2023-03-28", "2026-09-05")
    assert len(notes) == 2 and all(isinstance(n, str) for n in notes)


def test_a_failed_range_lookup_leaves_the_dates_alone():
    from common.databento_universe import clamp_to_dataset

    class C:
        class metadata:
            @staticmethod
            def get_dataset_range(dataset):
                raise RuntimeError("503")

    s, e, notes = clamp_to_dataset(C(), "EQUS.MINI", "2023-03-28", "2026-09-06")
    assert (s, e) == ("2023-03-28", "2026-09-06") and notes


# --- where the archive lives ------------------------------------------------

def test_archive_resolution_order(tmp_path, monkeypatch):
    """The archive is expensive, reusable, general-purpose market data -- not a
    project artefact -- so it lives outside the repo and a second project can
    read the same bytes rather than buying them again.

    Order matters: the env var must beat the config file, and both must beat
    the legacy in-repo default. Getting it wrong means a 60 GB pull silently
    landing somewhere nobody looks.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABENTO_ARCHIVE", raising=False)

    # 4. nothing set -> the old in-repo location, so existing setups still work
    assert F.default_archive() == Path("databento")

    # 3. config file
    Path(".databento_archive").write_text("D:/Databento\n", encoding="utf-8")
    assert F.default_archive() == Path("D:/Databento")

    # 2. env var wins over the file
    monkeypatch.setenv("DATABENTO_ARCHIVE", "E:/Elsewhere")
    assert F.default_archive() == Path("E:/Elsewhere")


def test_an_empty_config_file_falls_through_rather_than_returning_nothing(tmp_path, monkeypatch):
    """A blank or whitespace-only file must not resolve to Path('') -- which is
    the current directory, and would scatter the archive through the repo."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABENTO_ARCHIVE", raising=False)
    Path(".databento_archive").write_text("   \n", encoding="utf-8")
    assert F.default_archive() == Path("databento")


# --- the key, and the 401 that did not mean what it said ---------------------

def test_an_op_reference_is_resolved_not_sent_as_the_key(monkeypatch):
    """The README says `setx DATABENTO_API_KEY "op://Trading/<item>/<field>"`,
    and setx is persistent. Reading the variable raw therefore sent the
    REFERENCE as the key in every shell where a literal had not been exported
    over the top, and Databento answered 401 auth_authentication_failed --
    which reads as an expired subscription, the one explanation that is wrong.
    """
    from common import databento_fetch as FE
    from common import secrets_util as S

    monkeypatch.setenv("DATABENTO_API_KEY", "op://Trading/Databento/credential")
    monkeypatch.setattr(S, "_op_read",
                        lambda ref, label: "db-RESOLVEDFROM1PASSWORD00000000")
    assert FE._key() == "db-RESOLVEDFROM1PASSWORD00000000"


def test_a_literal_key_is_passed_through_untouched(monkeypatch):
    from common import databento_fetch as FE
    monkeypatch.setenv("DATABENTO_API_KEY", "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    assert FE._key() == "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def test_an_unset_key_names_both_ways_to_set_it(monkeypatch, tmp_path):
    from common import databento_fetch as FE
    from common import secrets_util as S
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.setattr(S, "CRED_FILE", tmp_path / "credentials.json")
    with pytest.raises(SystemExit) as e:
        FE._key()
    assert "op://" in str(e.value)


def test_a_wrong_shaped_key_warns_without_printing_any_of_it(monkeypatch, capsys):
    """A key of the wrong shape produces the same opaque 401 as no key at all.
    Say the likely reason first -- but the value never reaches the terminal,
    because PROGRAM_INDEX section 1 is that keys do not appear in chat."""
    from common import databento_fetch as FE
    monkeypatch.setenv("DATABENTO_API_KEY", "SUPERSECRETVALUE1234567890")
    assert FE._key() == "SUPERSECRETVALUE1234567890"
    err = capsys.readouterr().err
    assert "WARNING" in err and "26 characters" in err
    assert "SUPERSECRET" not in err
    assert "SECRET" not in err


def test_a_well_shaped_key_warns_about_nothing(monkeypatch, capsys):
    from common import databento_fetch as FE
    monkeypatch.setenv("DATABENTO_API_KEY", "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    FE._key()
    assert capsys.readouterr().err == ""


# --- progress on a long estimate --------------------------------------------

class _CountingMeta:
    def __init__(self, mb=1.0):
        self.mb, self.calls = mb, 0

    def get_cost(self, **kw):
        self.calls += 1
        return 0.0

    def get_billable_size(self, **kw):
        self.calls += 1
        return int(self.mb * 1e6)


class _C:
    def __init__(self, meta):
        self.metadata = meta


def test_a_long_estimate_reports_progress_and_an_eta(tmp_path, capsys):
    """plan() makes two metadata calls per date and printed nothing unless one
    failed. At 548 dates that is over a thousand sequential round trips of
    silence, which is indistinguishable from a hang -- and was Ctrl-C'd as one.

    The ETA is the part that matters: 'nine more minutes' is a decision,
    'still going' is not.
    """
    from common import databento_fetch as FE
    groups = {f"2025-01-{d:02d}": ["AAA"] for d in range(1, 21)}
    FE.plan(_C(_CountingMeta()), groups, "EQUS.SUMMARY", ["statistics"],
            tmp_path, 0, tick=5)
    out = capsys.readouterr().out
    assert out.count("estimating") == 4          # every 5th of 20
    assert "/20" in out
    assert "min left" in out


def test_the_final_date_always_reports_even_off_the_tick(tmp_path, capsys):
    """Otherwise a run whose count is not a multiple of the tick ends on
    silence, which is exactly the state being fixed."""
    from common import databento_fetch as FE
    groups = {f"2025-01-{d:02d}": ["AAA"] for d in range(1, 8)}   # 7 dates
    FE.plan(_C(_CountingMeta()), groups, "EQUS.SUMMARY", ["statistics"],
            tmp_path, 0, tick=5)
    assert "7/7" in capsys.readouterr().out


def test_progress_can_be_switched_off_for_quiet_callers(tmp_path, capsys):
    from common import databento_fetch as FE
    groups = {"2025-01-02": ["AAA"]}
    FE.plan(_C(_CountingMeta()), groups, "EQUS.SUMMARY", ["statistics"],
            tmp_path, 0, tick=0)
    assert "estimating" not in capsys.readouterr().out


def test_files_already_on_disk_cost_no_metadata_calls(tmp_path):
    """Re-running must be free by construction -- including the estimate. A
    resumed overnight run that re-priced everything already downloaded would
    spend a thousand round trips proving it has nothing to do."""
    from common import databento_fetch as FE
    p = FE.archive_path(tmp_path, "EQUS.SUMMARY", "statistics", "2025-01-02")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    meta = _CountingMeta()
    FE.plan(_C(meta), {"2025-01-02": ["AAA"]}, "EQUS.SUMMARY", ["statistics"],
            tmp_path, 0)
    assert meta.calls == 0


# --- locating the free L1 window --------------------------------------------

def _job(day, cost, skip=False):
    """(day, syms, schema, start, end, out, cost, bytes, skip)"""
    return (day, ["AAA"], "tcbbo", day, day, None, cost, 1000, skip)


def test_the_seam_between_free_and_paid_dates_is_reported():
    """L1 on Standard is ONE ROLLING year and the window moves daily, so the
    date a scoped pull stops being free is not a constant. Writing it into an
    --after flag from memory is how a pull silently starts charging."""
    from common import databento_fetch as FE
    jobs = [_job("2025-08-30", 0.42), _job("2025-09-01", 0.11),
            _job("2025-09-08", 0.0), _job("2026-01-05", 0.0)]
    assert FE.paid_boundary(jobs) == ("2025-09-01", "2025-09-08")


def test_an_entirely_free_plan_reports_no_seam():
    from common import databento_fetch as FE
    assert FE.paid_boundary([_job("2026-01-05", 0.0)]) is None


def test_dates_already_on_disk_do_not_create_a_false_seam():
    """A skipped date has cost 0 because it is not being bought, not because
    it is inside the window. Counting it would move the reported boundary."""
    from common import databento_fetch as FE
    jobs = [_job("2026-01-02", 0.0, skip=True), _job("2025-08-30", 0.42)]
    last_paid, first_free = FE.paid_boundary(jobs)
    assert last_paid == "2025-08-30"
    assert first_free == ""         # nothing free is actually being bought


def test_the_seam_points_at_the_free_side_not_the_paid_side():
    """The first version returned (max free, min paid) and advised
    --after <earliest PAID date> -- the whole paid range, exactly backwards.
    On the real plan that was advice to buy $21.02 of history while claiming
    to stay free. Confident wrong guidance is worse than none: the number
    looks measured."""
    from common import databento_fetch as FE
    jobs = [_job("2025-08-01", 0.82), _job("2025-08-29", 1.10),
            _job("2025-09-22", 0.0), _job("2026-09-04", 0.0)]
    last_paid, first_free = FE.paid_boundary(jobs)
    assert last_paid == "2025-08-29"
    assert first_free == "2025-09-22"


def test_a_plan_that_is_entirely_paid_has_no_free_side_to_point_at():
    from common import databento_fetch as FE
    assert FE.paid_boundary([_job("2025-08-01", 0.82)]) == ("2025-08-01", "")


def test_a_free_date_BEFORE_the_paid_range_does_not_become_the_seam():
    """A gap in the middle -- a date already covered, or a holiday priced at
    zero -- must not be mistaken for the window opening early."""
    from common import databento_fetch as FE
    jobs = [_job("2025-07-04", 0.0), _job("2025-08-29", 1.10),
            _job("2025-09-22", 0.0)]
    assert FE.paid_boundary(jobs) == ("2025-08-29", "2025-09-22")


# --- "already on disk" is a claim about a DATE, not about a symbol set ------

def _archive_with(tmp_path, dataset, schema, day, recorded):
    """A file on disk plus the manifest row that says what went into it.
    recorded=None writes no row, which is the pre-manifest archive."""
    from common import databento_fetch as FE
    p = FE.archive_path(tmp_path, dataset, schema, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    if recorded is not None:
        FE.write_manifest(tmp_path, dataset, {
            f"{schema}/{day}": {"date": day, "schema": schema,
                                "symbols": list(recorded),
                                "condition": "available", "bytes": 1}})
    return p


def test_a_file_fetched_for_fewer_symbols_is_NOT_skipped(tmp_path):
    """THE trap this exists for. The statistics archive was captured for the
    old 8,636-symbol-day EQUS.MINI candidate list; the consolidated screen
    selects 45,404. Every date was already on disk, so a bare out.exists()
    check would have skipped all of them and the pull would have reported
    success having downloaded nothing -- and the analysis underneath would
    have described a fifth of the universe as the whole of it."""
    from common import databento_fetch as FE
    _archive_with(tmp_path, "EQUS.SUMMARY", "statistics", "2025-01-02", ["AAA"])
    jobs, usd, _b = FE.plan(FakeClient(), {"2025-01-02": ["AAA", "BBB"]},
                            "EQUS.SUMMARY", ["statistics"], tmp_path, 0)
    assert [j[8] for j in jobs] == [False]
    assert usd == pytest.approx(0.01)


def test_a_file_that_already_holds_a_superset_is_skipped(tmp_path):
    """The other half: re-running must stay free. A narrower request against a
    wider file has nothing to buy."""
    from common import databento_fetch as FE
    _archive_with(tmp_path, "EQUS.SUMMARY", "statistics", "2025-01-02",
                  ["AAA", "BBB", "CCC"])
    jobs, usd, _b = FE.plan(FakeClient(), {"2025-01-02": ["AAA", "CCC"]},
                            "EQUS.SUMMARY", ["statistics"], tmp_path, 0)
    assert [j[8] for j in jobs] == [True]
    assert usd == 0.0


def test_a_file_with_no_manifest_row_is_still_skipped(tmp_path):
    """Deliberately the conservative direction: an archive captured before
    manifests existed must not be silently re-bought. It is reported instead
    -- see the unverified count."""
    from common import databento_fetch as FE
    _archive_with(tmp_path, "EQUS.SUMMARY", "statistics", "2025-01-02", None)
    jobs, usd, _b = FE.plan(FakeClient(), {"2025-01-02": ["AAA", "BBB"]},
                            "EQUS.SUMMARY", ["statistics"], tmp_path, 0)
    assert [j[8] for j in jobs] == [True]
    assert usd == 0.0


def test_the_symbol_check_is_per_schema_not_per_date(tmp_path):
    """Two schemas share a date and are separate files. A manifest row for one
    must not vouch for the other."""
    from common import databento_fetch as FE
    m = {"statistics/2025-01-02": {"AAA", "BBB"}}
    assert FE.covered(m, "statistics", "2025-01-02", ["AAA"]) is True
    assert FE.covered(m, "ohlcv-1d", "2025-01-02", ["AAA"]) is True   # unknown
    assert FE.covered(m, "statistics", "2025-01-03", ["AAA"]) is True # unknown
    assert FE.covered(m, "statistics", "2025-01-02", ["ZZZ"]) is False


def test_a_corrupt_manifest_does_not_stop_a_pull(tmp_path):
    from common import databento_fetch as FE
    p = FE.manifest_path(tmp_path, "EQUS.SUMMARY")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    assert FE.manifest_symbols(tmp_path, "EQUS.SUMMARY") == {}


def test_a_row_with_no_symbol_list_reads_as_unknown_not_as_empty(tmp_path):
    """An entry recorded as unverified must NOT parse as 'contains nothing',
    which would make every request a non-subset and re-buy the archive."""
    from common import databento_fetch as FE
    FE.write_manifest(tmp_path, "EQUS.SUMMARY", {
        "statistics/2025-01-02": {"date": "2025-01-02", "bytes": 1,
                                  "symbols_unverified": True}})
    m = FE.manifest_symbols(tmp_path, "EQUS.SUMMARY")
    assert m == {}
    assert FE.covered(m, "statistics", "2025-01-02", ["AAA"]) is True


def test_unverified_skips_names_the_assumed_ones_only(tmp_path):
    from common import databento_fetch as FE
    jobs = [("2025-01-02", ["AAA"], "statistics", "s", "e", None, 0.0, 0, True),
            ("2025-01-03", ["AAA"], "statistics", "s", "e", None, 0.0, 0, True),
            ("2025-01-06", ["AAA"], "statistics", "s", "e", None, 0.5, 9, False)]
    m = {"statistics/2025-01-02": {"AAA"}}
    assert FE.unverified_skips(m, jobs) == [("statistics", "2025-01-03")]


# --- the backfill must not invent coverage ----------------------------------

class _Out:
    def __init__(self, n=7):
        self.n = n

    def exists(self):
        return True

    def stat(self):
        return type("S", (), {"st_size": self.n})()


def _have(day, syms, schema="statistics"):
    return (day, syms, schema, "s", "e", _Out(), 0.0, 0, True)


def test_backfilling_an_unknown_file_records_no_symbol_list(tmp_path):
    """A skipped file was never opened, so this run learned nothing about what
    is inside it. Stamping the REQUEST onto it asserts coverage nothing
    established -- and covered() would then believe it, permanently."""
    from common import databento_fetch as FE
    ent = FE.backfill_entries({}, [_have("2025-01-02", ["AAA"])], {})
    row = ent["statistics/2025-01-02"]
    assert "symbols" not in row
    assert row["symbols_unverified"] is True


def test_backfilling_never_shrinks_a_recorded_symbol_list(tmp_path):
    """A file recorded as holding 83 symbols, re-requested for 16, is skipped
    as covered -- and must not be rewritten as holding 16, or the next run
    re-BUYS a date that is already paid for and on disk."""
    from common import databento_fetch as FE
    m = {"statistics/2025-01-02": {"AAA", "BBB", "CCC"}}
    ent = FE.backfill_entries(m, [_have("2025-01-02", ["AAA"])], {})
    assert ent["statistics/2025-01-02"]["symbols"] == ["AAA", "BBB", "CCC"]


def test_the_backfill_still_records_the_condition(tmp_path):
    """The reason the backfill exists at all: a day that was degraded when it
    was captured is unrecoverable once the plan window rolls past it."""
    from common import databento_fetch as FE
    ent = FE.backfill_entries({}, [_have("2025-01-02", ["AAA"])],
                              {"2025-01-02": "degraded"})
    assert ent["statistics/2025-01-02"]["condition"] == "degraded"
    assert ent["statistics/2025-01-02"]["bytes"] == 7
