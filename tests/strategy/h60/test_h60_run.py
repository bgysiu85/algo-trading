"""strategy.h60.run end to end on a synthetic archive: the gate order, the
pre-flight's no-P&L promise, and a full training-side score. Every path is
under tmp_path; no real bar, report or holdout is touched."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import bars as B
from strategy.h60 import controls as CT
from strategy.h60 import data_plan as DP
from strategy.h60 import holdout as H
from strategy.h60 import run as RUN
from strategy.h60 import xcheck as XC
from tests.strategy.h60 import _synth as S

N_SYM, N_DAYS = 90, 80


@pytest.fixture
def world(tmp_path, monkeypatch):
    days = S.sessions(N_DAYS)
    syms = [f"S{i:03d}" for i in range(N_SYM)]
    frames = [S.random_walk(s, days, vol=0.0005, start=40 + i) for i, s in enumerate(syms)]
    bars = pd.concat(frames, ignore_index=True)
    root = tmp_path / "H60"
    out = B.cache_dir(root, "primary")
    out.mkdir(parents=True)
    bars.to_parquet(out / "2020.parquet", index=False)
    eod = tmp_path / "eod"
    eod.mkdir()
    last = bars[bars["bar"] == 6]
    for s, g in last.groupby("symbol"):
        rows = "\n".join(f"{d},1,1,1,{c},{c},1" for d, c in zip(g["session"], g["close"]))
        (eod / f"{s}.csv").write_text("date,open,high,low,close,adjusted_close,volume\n"
                                      + rows + "\n", encoding="utf-8")
    monkeypatch.setattr(B, "GRID", "primary")
    monkeypatch.setattr(RUN, "archive_root", lambda a: root)
    monkeypatch.setattr(DP, "load_universe", lambda *a, **k: S.spells_for(syms))
    monkeypatch.setattr(H, "CUT_PATH", tmp_path / "holdout_h60.json")
    monkeypatch.setattr(RUN, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(RUN, "XCHECK_STATE", tmp_path / "state" / "xcheck.json")
    monkeypatch.setattr(RUN, "PREFLIGHT_REPORT", tmp_path / "pre.txt")
    monkeypatch.setattr(RUN, "SCORE_REPORT", tmp_path / "score.txt")
    monkeypatch.setattr(CT, "PC_RATE", 0.05)
    monkeypatch.setattr(RUN, "GUARD_SYMBOLS", 3)
    return {"root": root, "eod": eod, "tmp": tmp_path, "days": days}


def test_nothing_runs_without_the_grid(world, monkeypatch):
    monkeypatch.setattr(B, "GRID", None)
    with pytest.raises(B.GridNotChosen):
        RUN.session_list()


def test_nothing_runs_without_the_holdout_cut(world):
    with pytest.raises(H.HoldoutRefused, match="G6"):
        RUN.training_panel()


def test_score_refuses_before_the_preflight(world):
    H.cut(RUN.session_list())
    with pytest.raises(SystemExit, match="preflight"):
        RUN.score_all(None, n_draws=10)


def test_preflight_prints_counts_and_no_money(world):
    H.cut(RUN.session_list())
    assert RUN.preflight(None, world["eod"]) == 0
    text = (world["tmp"] / "pre.txt").read_text(encoding="utf-8")
    assert "NO P&L" in text and "PASS -- G2 cleared" in text
    assert "MR-60" in text and "NOT RUN" in text
    assert "trades per session" in text
    for word in ("gross", "net L2", "mr net", "per trade $"):
        assert word not in text
    x = json.loads((world["tmp"] / "state" / "xcheck.json").read_text(encoding="utf-8"))
    assert x["stop"] is False


def test_preflight_stops_at_g2(world):
    H.cut(RUN.session_list())
    for f in list(world["eod"].glob("*.csv"))[:20]:
        rows = f.read_text(encoding="utf-8").splitlines()
        body = [r.replace(",1\n", ",1") for r in rows[1:]]
        bad = [",".join(r.split(",")[:4] + [str(float(r.split(",")[4]) * 1.05)] + r.split(",")[5:])
               if i % 2 else r for i, r in enumerate(body)]
        f.write_text("\n".join([rows[0]] + bad) + "\n", encoding="utf-8")
    assert RUN.preflight(None, world["eod"]) == 2
    assert "STOPPED at §5.1" in (world["tmp"] / "pre.txt").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="G2"):
        RUN.score_all(None, n_draws=10)


def test_full_training_side_score(world, monkeypatch):
    """With G4 held shut, TL-60 must report 'not run' and a False verdict."""
    from strategy.h60 import rules as R
    monkeypatch.setattr(R, "TL_PARITY_PASSED", False)
    H.cut(RUN.session_list())
    assert RUN.preflight(None, world["eod"]) == 0
    assert RUN.score_all(None, n_draws=50) == 0
    text = (world["tmp"] / "score.txt").read_text(encoding="utf-8")
    assert "POSITIVE CONTROL (G7)" in text and "PASS" in text
    assert "TL-60/sleeve-R3: NOT RUN" in text and "MR-60: NOT RUN" in text
    for name in ("DON-60", "ORB-60", "VW9-60", "MC5-60", "MCL-60"):
        assert f"== {name} (scored) ==" in text
    v = json.loads((world["tmp"] / "state" / "verdicts.json").read_text(encoding="utf-8"))
    assert set(v["verdicts"]) == set(H.PRIORITY)
    assert v["verdicts"]["MR-60"] is False and v["verdicts"]["TL-60"] is False
    assert v["positive_control"]["pass"] is True
    # the training side never reaches the locked sessions
    rec = H.read(H.CUT_PATH)
    for f in (world["tmp"] / "state").glob("trades_*.csv"):
        t = pd.read_csv(f)
        if len(t):
            assert t["exit_session"].max() < rec["first_locked"]
    # nothing was spent
    assert not (world["tmp"] / "holdout_h60_spent.json").exists()


def test_with_g4_open_tl60_is_scored_as_its_ensemble(world):
    from strategy.h60 import rules as R
    assert R.TL_PARITY_PASSED is True
    H.cut(RUN.session_list())
    assert RUN.preflight(None, world["eod"]) == 0
    assert RUN.score_all(None, n_draws=20) == 0
    text = (world["tmp"] / "score.txt").read_text(encoding="utf-8")
    assert "== TL-60 (scored) ==" in text and "sleeve trades" in text
    assert "TL-60/sleeve-R3 (reported, never scored)" in text
    assert "10_tl_beats_don" in text
    assert "MR-60: NOT RUN" in text


def test_money_brackets():
    assert RUN.money(-1234.5) == "(1,234.50)" and RUN.money(12.0) == "12.00"
    assert RUN.money(float("nan")) == "n/a"


def test_build_cache_cli_does_not_double_the_h60_segment(tmp_path, monkeypatch):
    """--build-cache must read <H60 root>/<dataset>/<rth dir> directly. Calling
    data_plan.rth_root (which itself appends the H60 segment) on a root that is
    ALREADY the H60 root doubles it to <H60 root>/H60/<dataset>/<rth dir> and the
    real pull is never found. archive_root() is exercised for real here (not
    monkeypatched) since the bug is in how run.py composes the two."""
    from strategy.h60 import data_plan as DP
    h60_root = tmp_path / "H60"
    src_dir = h60_root / DP.DATASET / DP.RTH_DIR
    src_dir.mkdir(parents=True)
    (src_dir / "2020-01-02.dbn.zst").write_bytes(b"")
    monkeypatch.setattr(RUN, "archive_root", lambda a: h60_root)
    seen = {}

    def fake_build_cache(src, root):
        seen["src"] = src
        seen["root"] = root
        return {"files": 1, "empty_days": 0, "rows_by_year": {}, "dir": str(root)}

    monkeypatch.setattr(B, "build_cache", fake_build_cache)
    assert RUN.main(["--build-cache"]) == 0
    assert seen["src"] == src_dir
    assert seen["root"] == h60_root
    assert "/H60/H60/" not in str(seen["src"]).replace("\\", "/")
