"""G2: the manifest reproduces the engine's fills, takes levels from the order state, and never reads outcome columns."""
import ast
from pathlib import Path

import pandas as pd
import pytest

from strategy.chartmark import spec as V1
from strategy.chartmark_clone import manifest as MF
from strategy.chartmark_clone import spec as S
from tests.strategy.chartmark_clone.helpers import built, pool, write_trades_csv

PKG = Path(__file__).resolve().parents[3] / "strategy" / "chartmark_clone"
OUTCOME_COLUMNS = {"exit_t", "exit_j", "exit_px", "gross", "cost", "net", "exit_reason", "phase", "bars_held", "n_rolls",
                   "entry_px"}
OUTCOME_ATTRS = OUTCOME_COLUMNS - {"entry_px"}     # entry_px is used only as the engine's own fill, to prove the level


def test_every_fill_has_the_level_the_engine_held_at_the_decision_bar():
    fr, ind, trades = pool(1)
    m, info = MF.build_manifest(fr, ind, trades)
    assert len(m) == len(trades) > 100 and info["n"] == len(trades)
    for row, tr in zip(m.itertuples(), trades):
        e = tr.entry_j
        assert row.decision_idx == e - 1
        assert fr.h[e] >= row.level - 1e-9                                    # the order was hit in the fill bar
        assert max(row.level, fr.o[e]) == pytest.approx(tr.entry_px)          # and filled where the engine says
        assert row.candidate_id == fr.ny[e].tz_localize(None).strftime(MF.TS_FMT)
        assert row.decision_t == fr.ny[e - 1].tz_localize(None).strftime(MF.TS_FMT)
        assert row.daily_trend in (-1, 1)


def test_a_wrong_level_is_caught(monkeypatch):
    fr, ind, trades = pool(1)
    monkeypatch.setattr(MF, "fill_level", lambda *a: 1e9)
    with pytest.raises(MF.ManifestError, match="level check failed"):
        MF.build_manifest(fr, ind, trades)


def test_timestamp_mismatch_with_the_trades_file_stops(tmp_path):
    fr, ind, trades = pool(1)
    m, _ = MF.build_manifest(fr, ind, trades)
    times = MF.read_entry_times(write_trades_csv(tmp_path / "t.csv", fr, trades))
    MF.check_against_trades_csv(m, times)                                     # the honest case passes
    with pytest.raises(MF.ManifestError, match="disagree"):
        MF.check_against_trades_csv(m, times[:-1])
    with pytest.raises(MF.ManifestError, match="disagree"):
        MF.check_against_trades_csv(m, times + ["2099-01-01 00:00:00"])
    with pytest.raises(MF.ManifestError, match="duplicate"):
        MF.check_against_trades_csv(m, times + times[:1])


def test_registered_pool_counts_are_enforced():
    fr, ind, trades = pool(1)
    _, info = MF.build_manifest(fr, ind, trades)
    with pytest.raises(MF.ManifestError, match="registered"):
        MF.check_registered_counts(info)
    good = dict(n=S.POOL_N, per_year=dict(S.POOL_PER_YEAR))
    MF.check_registered_counts(good)


def test_the_trades_file_is_read_through_its_entry_t_column_only(tmp_path, monkeypatch):
    fr, ind, trades = pool(1)
    p = write_trades_csv(tmp_path / "t.csv", fr, trades)
    header = set(pd.read_csv(p, nrows=0).columns)
    assert OUTCOME_COLUMNS <= header                                          # the file really carries the outcomes
    seen = []
    real = pd.read_csv

    def spy(path, *a, **k):
        seen.append(k.get("usecols"))
        return real(path, *a, **k)

    monkeypatch.setattr(pd, "read_csv", spy)
    MF.read_entry_times(p)
    assert seen == [["entry_t"]]
    p2 = tmp_path / "bad.csv"
    p2.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(MF.ManifestError):
        MF.read_entry_times(p2)


def test_a_full_build_never_reads_an_outcome_column(tmp_path, monkeypatch):
    """G2 at run time: wrap read_csv across a whole build; any file that carries outcome columns must be read with
    usecols that exclude them."""
    real = pd.read_csv
    log = []

    def spy(path, *a, **k):
        cols = set(real(path, nrows=0).columns)
        used = k.get("usecols")
        got = cols if used is None else set(used)
        log.append((Path(path).name, cols & OUTCOME_COLUMNS, got & OUTCOME_COLUMNS))
        return real(path, *a, **k)

    monkeypatch.setattr(pd, "read_csv", spy)
    built(tmp_path)
    assert log, "the build read no csv at all"
    for name, has, got in log:
        assert not got, f"{name} was read with outcome columns {got}"
    assert any(has for _, has, _ in log)           # the spy did see the outcome-bearing file


def test_no_module_in_the_package_reads_an_outcome_column():
    """Static: no string literal names an outcome column, and no attribute access reads an exit-side field."""
    for f in sorted(PKG.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in OUTCOME_COLUMNS, f"{f.name} names outcome column {node.value!r}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in OUTCOME_ATTRS, f"{f.name} reads .{node.attr}"
    users = [f.name for f in PKG.glob("*.py") if "TRADES_CSV_NAME" in f.read_text(encoding="utf-8")]
    assert sorted(users) == ["build.py", "spec.py"]
