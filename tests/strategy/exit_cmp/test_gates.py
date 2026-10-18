"""G3 (entry set, no outcome columns), G6 (count-only pre-flight), and the end-to-end shape of the outcome run on synthetic bars."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from strategy.exit_cmp import entries as EN
from strategy.exit_cmp import preflight as PF
from strategy.exit_cmp import run as RUN
from strategy.exit_cmp import spec as S
from tests.strategy.exit_cmp.helpers import world

ROOT = Path(__file__).resolve().parents[3]
SOURCES = sorted(list((ROOT / "exitmgr").glob("*.py")) + list((ROOT / "strategy" / "exit_cmp").glob("*.py")))


# ---- G3 ----
def test_entry_set_check_stops_on_a_wrong_count():
    fr, ind, trades, entries, st = world(seed=3, n=6000)
    with pytest.raises(EN.EntryError, match="registered"):
        EN.check_registered(fr, entries)


def test_entries_carry_no_outcome_field():
    fields = set(EN.Entry.__dataclass_fields__)
    assert not fields & {"exit_j", "exit_px", "reason", "gross", "net", "cost", "phase"}


def test_only_parity_reads_the_v1_trades_file_and_entries_never_touches_a_v1_exit():
    for p in SOURCES:
        txt = p.read_text(encoding="utf-8")
        if p.name not in ("spec.py", "parity.py"):
            assert "TRADES_CSV_NAME" not in txt and "chartmark_trades_base" not in txt, p.name
        if p.name == "entries.py":
            code = re.sub(r'""".*?"""', "", txt, flags=re.S)
            for forbidden in (".exit_px", ".exit_j", ".reason", ".phase", "read_csv"):
                assert forbidden not in code, (p.name, forbidden)
    assert "usecols" in (ROOT / "strategy/exit_cmp/run.py").read_text(encoding="utf-8")      # labels: ids / label / seq only


def test_no_text_open_without_an_encoding():
    import ast
    for p in SOURCES:
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("read_text", "write_text"):
                assert any(k.arg == "encoding" for k in node.keywords), (p.name, node.lineno)


# ---- G6 ----
def test_preflight_prints_counts_and_no_price_or_pnl():
    fr, ind, trades, entries, st = world(seed=3, n=6000)
    text = PF.counts_report(st, entries, EN.per_year(fr, entries), "20260101")
    assert "triggers reached" in text and "trades reaching the trigger" in text and "emergency distance" in text
    assert text.count("$") == 1                      # only the $0.60 emergency distance, never a price or a P&L
    low = text.lower()
    for word in ("gross", "net ", "p&l:", "profit", "cost"):
        assert word not in low, word


@pytest.mark.parametrize("flag", ["--pnl", "--backtest", "--holdout", "--limit=5", "--net", "--spend"])
def test_preflight_and_parity_refuse_pnl_flags(flag):
    from strategy.exit_cmp import parity as PA
    for main in (PF.main, PA.main, RUN.main):
        with pytest.raises(SystemExit) as e:
            main([flag])
        assert e.value.code == 2


# ---- the outcome run, shape only ----
def test_outcome_run_end_to_end_on_synthetic_bars(tmp_path):
    fr, ind, trades, entries, st = world(seed=3, n=7000)
    res = RUN.compute(st, set(), log=lambda *a: None)
    led = dict(created_utc="2026-01-01T00:00:00Z", git_commit="x" * 40, registration_sha256="y" * 64)
    text = RUN.render(res, st, led, "20260101")
    assert "THE PASS TEST" in text and "FLAT vs HOLD" in text and "20 REAL TRADES" in text
    for rid in S.SCORED:
        assert res["rules"][rid]["test"]["criteria"]["verdict"].split()[0] in ("PASS", "FAIL", "NOT")
        assert len(res["rules"][rid]["test"]["grid"]) == 9
    assert len(res["rules"]["X-ALERT-touch"]["test"]["grid_also"]) == 9
    j = RUN.to_json(res)
    json.dumps(j, default=str)
    # the baseline is its own D = 0
    assert res["rules"][S.BASELINE]["FLAT"]["MCL-mid"]["D"] == 0
    # negatives are bracketed
    assert RUN.money(-1234.4) == "($1,234)" and RUN.money(99.6) == "$100"


def test_ben_takes_from_a_label_file(tmp_path):
    p = tmp_path / "labels.csv"
    pd.DataFrame([
        ("a", "TAKE", "0", "0"), ("b", "SKIP", "0", "1"), ("c", "TAKE", "0", "2"), ("c", "UNDO", "0", "2"),
        ("d", "TAKE", "1", "3"), ("e", "SKIP", "0", "4"), ("e", "TAKE", "0", "5"),
    ], columns=["candidate_id", "label", "is_repeat", "seq"]).to_csv(p, index=False)
    assert RUN.ben_takes(p) == {"a"}                # c undone, d is a repeat, e's first label was a skip


# ---- the three commands, chained, on synthetic bars (archive load and the registered counts patched out) ----
def test_preflight_parity_run_chain_and_the_one_run_lock(tmp_path, monkeypatch):
    from strategy.chartmark import book as BK
    from strategy.exit_cmp import ledger as LG
    from strategy.exit_cmp import parity as PA
    fr, ind, trades, entries, st = world(seed=3, n=7000)
    for mod in (PF, PA, RUN):
        monkeypatch.setattr(mod, "load_training_frame", lambda archive: fr)
    monkeypatch.setattr(EN, "check_registered", lambda f, e: EN.per_year(f, e))
    out = tmp_path / "out"
    out.mkdir()
    # an outcome run before the pre-flight / parity is refused
    with pytest.raises(LG.LedgerError):
        RUN.main(["--out", str(out)])
    assert PF.main(["--out", str(out)]) == 0
    led = LG.read(out)
    assert led["preflight_done"] and not led["parity_ok"] and led["n_entries"] == len(entries)
    with pytest.raises(LG.LedgerError, match="parity"):
        RUN.main(["--out", str(out)])
    # parity against a recorded-trades file made from the v1 engine itself
    df = BK.trade_frame(trades, fr, "MCL", "mid")
    df.to_csv(out / S.TRADES_CSV_NAME, index=False)
    monkeypatch.setattr(PA, "REGISTERED_NET", round(float(df["net"].sum())))
    assert PA.main(["--out", str(out)]) == 0
    assert LG.read(out)["parity_ok"]
    # a recorded file that disagrees by one cent stops the study
    bad = df.copy()
    bad.loc[3, "net"] += 0.02
    bad.to_csv(out / "bad.csv", index=False)
    assert PA.main(["--out", str(out), "--trades-csv", str(out / "bad.csv")]) == 1
    # the outcome run: once
    assert RUN.main(["--out", str(out)]) == 0
    files = {p.name for p in out.iterdir()}
    assert any(f.startswith("w15_0053_exit_cmp_outcome_") and f.endswith(".txt") for f in files)
    assert any(f.endswith("_trades.csv") for f in files)
    assert LG.read(out)["outcome_done"]
    with pytest.raises(LG.LedgerError, match="done"):
        RUN.main(["--out", str(out)])
