#!/usr/bin/env python3
"""Adding a column to a live table without destroying what is in it.

`create_all` is create-if-not-exists and never ALTERs, so a column added to a
model after its table was made is silently absent. Until now the only sanctioned
repair was `--rebuild-table`: drop the table and reload it from files.

That is right for `bar_minute`, where a backfill would have to GUESS which tape
an existing row came from -- inventing provenance, which is the exact failure
the `dataset` column was added to prevent. It is the wrong trade for
`paper_fill`, which held 260 rows of real fills when `ref_drift_pct` was added
on 2026-09-16, and where the honest value for every one of those rows is NULL:
the measurement did not exist when they were made.

So there is now an additive path, and it is deliberately narrow. These are the
assertions that keep it narrow -- because a migration tool that can be talked
into one more thing is how a database gets edited by accident.
"""
from __future__ import annotations

from sqlalchemy import (Column, Date, Float, Integer, MetaData, String, Table,
                        create_engine, inspect, select)

import pytest

from common import db as D


def eng_at(tmp_path, tables):
    """A live database built from a DIFFERENT metadata than the model.

    That is the situation under test: the disk holds an older shape. Building
    it from `D.META` and then deleting a column would be the tool checking
    itself against itself.
    """
    e = create_engine(f"sqlite:///{tmp_path/'t.db'}", future=True)
    m = MetaData()
    for name, cols in tables.items():
        Table(name, m, *cols)
    m.create_all(e)
    return e


def one_model_table(cols):
    """Swap D.META for a single-table model, restoring it afterwards."""
    m = MetaData()
    Table("t", m, *cols)
    return m


@pytest.fixture
def model(monkeypatch):
    def use(cols):
        monkeypatch.setattr(D, "META", one_model_table(cols))
    return use


# ==========================================================================
# WHAT MAY BE ADDED
# ==========================================================================
def test_a_nullable_column_the_table_lacks_is_addable(tmp_path, model):
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert [c.name for c in addable["t"]] == ["drift"]
    assert refused == {}


def test_a_NOT_NULL_column_is_REFUSED(tmp_path, model):
    """Every existing row would need a value it predates, and any value the
    tool picked would be invented. That is the defect, not the fix."""
    model([Column("id", Integer, primary_key=True),
           Column("must", Float, nullable=False)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert addable == {}
    assert "NOT NULL" in refused["t"][0]


def test_a_PRIMARY_KEY_column_is_REFUSED(tmp_path, model):
    """This is the `dataset` case. Adding to the key changes what a row IS, so
    two rows that were distinct can collide -- it is not an addition at all."""
    model([Column("id", Integer, primary_key=True),
           Column("dataset", String(16), primary_key=True)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert addable == {}
    assert "primary key" in refused["t"][0]


def test_a_SERVER_DEFAULT_column_is_REFUSED(tmp_path, model):
    """A default writes a value into every existing row, which is the one
    thing this path promises not to do."""
    model([Column("id", Integer, primary_key=True),
           Column("d", Integer, server_default="0")])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert addable == {}
    assert "server default" in refused["t"][0]


def test_addable_and_refused_are_reported_TOGETHER_not_one_or_the_other(
        tmp_path, model):
    """A table with one of each must not have its addable column hidden by the
    refusal, or the safe half of a migration silently stops happening."""
    model([Column("id", Integer, primary_key=True),
           Column("ok", Float),
           Column("no", Float, nullable=False)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert [c.name for c in addable["t"]] == ["ok"]
    assert len(refused["t"]) == 1


def test_a_table_that_does_not_exist_yet_is_not_a_migration(tmp_path, model):
    """A missing table is create_all's job. Reporting it here would offer an
    ALTER against nothing."""
    model([Column("id", Integer, primary_key=True), Column("x", Float)])
    e = eng_at(tmp_path, {"other": [Column("id", Integer, primary_key=True)]})
    addable, refused = D.addable_columns(e)
    assert addable == {} and refused == {}


def test_a_column_the_database_has_and_the_model_does_not_is_left_alone(
        tmp_path, model):
    """Usually an older shape rather than a fault, and this tool has no
    business proposing to drop one."""
    model([Column("id", Integer, primary_key=True)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True),
                                Column("legacy", Float)]})
    addable, refused = D.addable_columns(e)
    assert addable == {} and refused == {}


def test_only_columns_the_MODEL_declares_can_ever_be_added(tmp_path, model):
    """There is no path from this tool to arbitrary DDL: the candidate list is
    read from META and nothing else, so it cannot be asked for a column the
    model does not have."""
    model([Column("id", Integer, primary_key=True), Column("known", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable, _ = D.addable_columns(e)
    names = {c.name for cols in addable.values() for c in cols}
    assert names <= {c.name for t in D.META.tables.values() for c in t.columns}


# ==========================================================================
# THE STATEMENT
# ==========================================================================
def test_the_type_is_compiled_for_the_DATABASE_being_altered(tmp_path, model):
    """A type compiled for another dialect is a second source of truth about
    the schema. The column this ALTER makes must be the column create_all
    would have made ON THIS DATABASE."""
    from sqlalchemy import Boolean
    from sqlalchemy.dialects import mssql
    model([Column("id", Integer, primary_key=True), Column("flag", Boolean)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    col = D.addable_columns(e)[0]["t"][0]
    here = D.add_column_sql("t", col, e.dialect)
    there = D.add_column_sql("t", col, mssql.dialect())
    assert col.type.compile(dialect=e.dialect) in here
    # sqlite says BOOLEAN, SQL Server says BIT. Had this compiled for the
    # wrong dialect the ALTER would still have looked plausible.
    assert here != there, f"{here!r} == {there!r}: the dialect is not reaching"


def test_the_statement_is_an_ADD_and_says_NULL(tmp_path, model):
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    stmt = D.add_column_sql("t", D.addable_columns(e)[0]["t"][0], e.dialect)
    assert stmt.startswith("ALTER TABLE t ADD drift ")
    assert stmt.endswith(" NULL")
    for word in ("DROP", "UPDATE", "DELETE", "TRUNCATE"):
        assert word not in stmt.upper()


# ==========================================================================
# RUNNING IT
# ==========================================================================
def test_the_rows_are_still_there_afterwards(tmp_path, model):
    """THE WHOLE POINT. 260 real fills survived the last column addition only
    because nobody ran the rebuild."""
    model([Column("id", Integer, primary_key=True), Column("v", Integer),
           Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True),
                                Column("v", Integer)]})
    with e.begin() as c:
        c.exec_driver_sql("INSERT INTO t (id, v) VALUES (1, 10), (2, 20)")
    D.add_missing_columns(e, D.addable_columns(e)[0])
    with e.connect() as c:
        rows = c.exec_driver_sql("SELECT id, v, drift FROM t ORDER BY id").all()
    assert rows == [(1, 10, None), (2, 20, None)]


def test_the_rows_that_predate_the_column_get_NULL_and_not_a_number(
        tmp_path, model):
    """NULL is the honest value: the measurement did not exist when those rows
    were made. A zero would read as a measured zero."""
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    with e.begin() as c:
        c.exec_driver_sql("INSERT INTO t (id) VALUES (1)")
    D.add_missing_columns(e, D.addable_columns(e)[0])
    with e.connect() as c:
        assert c.exec_driver_sql("SELECT drift FROM t").scalar() is None


def test_the_drift_report_is_empty_once_it_has_run(tmp_path, model):
    """The detector and the fix have to agree, or one of them is wrong about
    what the schema is."""
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    assert D.schema_drift(e) == {"t": ["drift"]}
    D.add_missing_columns(e, D.addable_columns(e)[0])
    assert D.schema_drift(e) == {}


def test_running_it_twice_is_a_no_op(tmp_path, model):
    """A migration that is not idempotent is one Ben cannot safely re-run when
    he loses track of whether it went through."""
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    assert len(D.add_missing_columns(e, D.addable_columns(e)[0])) == 1
    assert D.add_missing_columns(e, D.addable_columns(e)[0]) == []


def test_several_columns_are_added_in_the_MODELS_order(tmp_path, model):
    """So the statements a reader was shown are the statements that run."""
    model([Column("id", Integer, primary_key=True), Column("a", Float),
           Column("b", Float), Column("c", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    done = D.add_missing_columns(e, D.addable_columns(e)[0])
    assert [s.split()[4] for s in done] == ["a", "b", "c"]


def test_each_statement_commits_on_its_own(tmp_path, model):
    """A failure on the fourth column must leave the first three added, not
    roll back into a state matching neither the model nor the plan just
    printed."""
    model([Column("id", Integer, primary_key=True), Column("a", Float),
           Column("b", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    addable = D.addable_columns(e)[0]
    addable["t"].append(Column("a", Float))          # a duplicate: will fail
    with pytest.raises(Exception):
        D.add_missing_columns(e, addable)
    assert "a" in {c["name"] for c in inspect(e).get_columns("t")}
    assert "b" in {c["name"] for c in inspect(e).get_columns("t")}


# ==========================================================================
# THE REAL MODEL — the case this was built for
# ==========================================================================
def test_ref_drift_pct_is_addable_in_place_on_the_real_paper_fill(tmp_path):
    """2026-09-16: `paper_fill` held 260 rows of real fills and the model
    gained `ref_drift_pct`. The tool's own advice was to drop the table."""
    e = create_engine(f"sqlite:///{tmp_path/'real.db'}", future=True)
    live = MetaData()
    cols = [Column(c.name, c.type, primary_key=c.primary_key)
            for c in D.paper_fill.columns if c.name != "ref_drift_pct"]
    Table("paper_fill", live, *cols)
    live.create_all(e)
    addable, refused = D.addable_columns(e)
    assert [c.name for c in addable["paper_fill"]] == ["ref_drift_pct"]
    assert "paper_fill" not in refused


def test_the_session_key_of_paper_fill_could_NOT_be_added_this_way(tmp_path):
    """The guard proving the rule bites on the real model too: drop a key
    column instead and the tool refuses rather than corrupting the key."""
    e = create_engine(f"sqlite:///{tmp_path/'key.db'}", future=True)
    live = MetaData()
    cols = [Column(c.name, c.type, primary_key=c.primary_key)
            for c in D.paper_fill.columns if c.name != "ts_et"]
    Table("paper_fill", live, *cols)
    live.create_all(e)
    addable, refused = D.addable_columns(e)
    assert "paper_fill" not in addable
    assert any("primary key" in r for r in refused["paper_fill"])


def test_paper_fill_is_still_listed_as_rebuildable_from_its_logs():
    """The additive path does not replace the rebuild -- it is the cheaper
    option where it applies, and the rebuild stays for everything else."""
    assert "paper_fill" in D.DERIVED_TABLES
    assert "paper_fill" in D.REBUILD_PRECONDITION


# ==========================================================================
# THE CLI PATHS, EXERCISED — added 2026-09-16.
#
# `emit` was imported at the END of main(), which was correct while the only
# caller was main's last line and a NameError the moment --add-columns started
# emitting from earlier in the same function. Nothing caught it because
# nothing ran the CLI. An import positioned by where its first caller HAPPENED
# to be is a guard placed behind the thing it guards.
#
# And every one of these writes a FILE. A plan that exists only in a terminal
# has to be copied by hand to be used, and the ALTER statements are the record
# of what touched a live table.
# ==========================================================================
def _cli(monkeypatch, tmp_path, engine, argv):
    monkeypatch.setattr(D, "database_url", lambda *a, **k: "sqlite://")
    monkeypatch.setattr(D, "engine", lambda *a, **k: engine)
    out = tmp_path / "migrate.txt"
    rc = D.main(argv + ["--migrate-out", str(out)])
    return rc, (out.read_text(encoding="utf-8") if out.exists() else "")


def test_add_columns_writes_its_plan_to_a_file(tmp_path, model, monkeypatch):
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    rc, txt = _cli(monkeypatch, tmp_path, e, ["--add-columns"])
    assert rc == 0
    assert "ALTER TABLE t ADD drift" in txt
    assert "nothing has run" in txt


def test_the_dry_plan_really_changes_nothing(tmp_path, model, monkeypatch):
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    _cli(monkeypatch, tmp_path, e, ["--add-columns"])
    assert D.schema_drift(e) == {"t": ["drift"]}, "the dry run applied it"


def test_apply_writes_the_statements_it_ran_and_the_result(
        tmp_path, model, monkeypatch):
    model([Column("id", Integer, primary_key=True), Column("drift", Float)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    rc, txt = _cli(monkeypatch, tmp_path, e, ["--add-columns", "--apply"])
    assert rc == 0
    assert "applied 1 statement" in txt
    assert "schema now matches the model" in txt
    assert D.schema_drift(e) == {}


def test_a_refusal_is_written_with_its_reason(tmp_path, model, monkeypatch):
    model([Column("id", Integer, primary_key=True),
           Column("must", Float, nullable=False)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    rc, txt = _cli(monkeypatch, tmp_path, e, ["--add-columns"])
    assert rc == 1
    assert "WILL NOT ADD" in txt and "NOT NULL" in txt


def test_nothing_to_do_is_still_written_down(tmp_path, model, monkeypatch):
    """An empty report and no report are the same file on disk tomorrow, and
    only one of them means the command ran."""
    model([Column("id", Integer, primary_key=True)])
    e = eng_at(tmp_path, {"t": [Column("id", Integer, primary_key=True)]})
    rc, txt = _cli(monkeypatch, tmp_path, e, ["--add-columns"])
    assert rc == 0 and "nothing to add" in txt


def test_check_rebuildable_writes_its_answer(tmp_path, monkeypatch):
    e = create_engine(f"sqlite:///{tmp_path/'r.db'}", future=True)
    rc, txt = _cli(monkeypatch, tmp_path, e,
                   ["--check-rebuildable", "paper_fill",
                    "--fills-dir", str(tmp_path)])
    assert "REBUILD PRECONDITION" in txt
    assert rc in (0, 1)


def test_check_rebuildable_on_a_table_with_no_precondition_says_which_have_one(
        tmp_path, monkeypatch):
    e = create_engine(f"sqlite:///{tmp_path/'r2.db'}", future=True)
    rc, txt = _cli(monkeypatch, tmp_path, e,
                   ["--check-rebuildable", "bar_minute"])
    assert rc == 1
    assert "paper_fill" in txt, "it must name the tables that DO have one"
