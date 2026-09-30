"""MFLAG-v1: G2 pre-flight (counts only), G5, the stop rule, the runner's refusals, the holdout ledger."""
import json

import numpy as np
import pandas as pd
import pytest

from strategy.macro_flag import books as BK
from strategy.macro_flag import controls as K
from strategy.macro_flag import holdout as HO
from strategy.macro_flag import preflight as PF
from strategy.macro_flag import run as RUN
from strategy.macro_flag import spec as S
from strategy.macro_flag import study as ST
from tests.strategy.macro_flag import synth as Y


def _csv(tmp_path, **kw):
    b = Y.books(**kw)
    p = tmp_path / "books.csv"
    b.to_csv(p, index=False, encoding="utf-8")
    return p, b


def test_preflight_never_loads_a_pnl_column(tmp_path, monkeypatch):
    p, _ = _csv(tmp_path, markets=["ES"])
    seen = {}
    real = pd.read_csv

    def spy(*a, **k):
        seen["usecols"] = k.get("usecols")
        return real(*a, **k)
    monkeypatch.setattr(pd, "read_csv", spy)
    df = BK.read_books(p, with_pnl=False)
    assert not set(BK.PNL_COLS) & set(df.columns)
    assert seen["usecols"] is not None and not set(BK.PNL_COLS) & set(seen["usecols"])
    assert set(BK.PNL_COLS) <= set(BK.read_books(p, with_pnl=True).columns)


def test_preflight_counts_and_stop_rule():
    days = Y.nfp_fridays()
    many = Y.books(n_per_market=300, markets=["ES", "CL"])
    rep = PF.run(many, Y.sessions_all(), Y.calendar({"NFP": days}))
    assert rep["flagged"] > 0 and rep["stop"] == (rep["flagged"] < S.MIN_FLAGGED)
    none = PF.run(Y.books(n_per_market=5, markets=["RTY"]), Y.sessions_all(), Y.calendar({"NFP": days}))
    assert none["flagged"] == 0 and none["stop"] is True        # RTY has no flag cell
    assert "STOP" in PF.render(none)


def test_run_refuses_without_or_after_a_stopped_preflight(tmp_path):
    p, b = _csv(tmp_path, markets=["ES"])
    cal = tmp_path / "cal.csv"
    cal.write_text("date,time_et,event,kind,note\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.require_preflight(tmp_path, p, cal)                 # none on disk
    rec = dict(stop=True, flagged=3, books_sha256=PF.sha256(p), calendar_sha256=PF.sha256(cal))
    (tmp_path / "w15_0023_mflag_preflight_20260930.json").write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.require_preflight(tmp_path, p, cal)                 # stopped
    rec.update(stop=False, flagged=80)
    (tmp_path / "w15_0023_mflag_preflight_20260930.json").write_text(json.dumps(rec), encoding="utf-8")
    assert RUN.require_preflight(tmp_path, p, cal)["flagged"] == 80
    rec["books_sha256"] = "0" * 64                              # different books
    (tmp_path / "w15_0023_mflag_preflight_20260930.json").write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.require_preflight(tmp_path, p, cal)


@pytest.mark.parametrize("flag", ["--holdout", "--limit=5", "--spend", "--seen", "--markets", "--window", "--cells"])
def test_runner_refuses_narrowing_and_holdout_flags(flag):
    assert RUN.main(["--preflight", flag]) == 2


def test_g5_books_reproduce_fails_loudly():
    with pytest.raises(SystemExit):
        BK.check_books_reproduce(Y.books(markets=["ES"]).query("spec == 'C1' and sizing == 'frac'"))


def test_holdout_ledger_is_own_and_spent_once(tmp_path):
    h = HO.H
    h.ledger_path = tmp_path / "ledger.json"
    d = ["2021-12-30", "2022-01-03", "2025-09-22", "2025-09-23"]
    assert h.split_dates(d)[0] == d[:1]
    with pytest.raises(HO.HoldoutRefused):
        h.split_dates(d, limit=3)
    with pytest.raises(HO.HoldoutRefused):
        h.split_dates(d, markets=["CL"])
    with pytest.raises(HO.HoldoutRefused):
        h.split_dates(d, spend=True, candidate="CRUDELE-3S", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        h.split_dates(d, spend=True, candidate="MFLAG-v1")               # no PASS
    keep, _, _ = h.split_dates(d, spend=True, candidate="MFLAG-v1", verdict="PASS")
    assert keep == d[1:3]
    with pytest.raises(HO.HoldoutRefused):
        h.split_dates(d, spend=True, candidate="MFLAG-v1", verdict="PASS")   # spent once
    for other in ("holdout_crudele_3s.json", "holdout_breit_cap.json", "holdout.json"):
        with pytest.raises(HO.HoldoutRefused):
            h.load_for(other)
    from strategy.crudele_3s import holdout as CH
    with pytest.raises(HO.HoldoutRefused):
        CH.H.load_for("holdout_macro_flag.json")                              # and it refuses ours


def test_random_removal_is_seeded_and_counts_right():
    nets = np.arange(30, dtype=float).reshape(10, 3)
    mk = np.array(["ES"] * 10)
    a = K.random_removal(nets, mk, {"ES": 4}, 50)
    assert np.array_equal(a, K.random_removal(nets, mk, {"ES": 4}, 50))
    assert (a < 0).all() and K.random_removal(nets, mk, {"ES": 0}, 5).sum() == 0
    assert K.percentile_of(0.0, np.array([-1.0, 1.0])) == 50.0


def test_label_permutation_detects_planted_and_null():
    rng = np.random.default_rng(1)
    mk = np.array(["ES", "CL"] * 200)
    x = rng.normal(0, 1, 400)
    f = np.zeros(400, bool)
    f[rng.choice(400, 60, replace=False)] = True
    _, p_null, _ = K.label_permutation_p(f, x, mk, 300)
    x2 = x - 2.0 * f
    _, p_plant, _ = K.label_permutation_p(f, x2, mk, 300)
    assert p_plant < 0.01 and p_null > 0.05


def test_end_to_end_verdicts_on_synthetic_books(monkeypatch):
    monkeypatch.setattr(BK, "check_books_reproduce", lambda h: (len(h), float(h["net_mid"].sum())))
    days = Y.nfp_fridays()
    cal = Y.calendar({"NFP": days, "FOMC": days[1::3], "CPI": days[2::3]})
    bad = Y.books(n_per_market=400, planted=-80.0, event_days=days, markets=list(S.FLAG_MARKETS))
    R = ST.analyse(bad, Y.sessions_all(), cal, cr_draws=60, perm_draws=100, log=lambda *_: None)
    assert R["primary"]["n"] >= S.MIN_FLAGGED and R["crit"][1][1] and R["crit"][2][1]     # planted worse -> skipping helps
    assert "VERDICT" in ST.render(R)
    few = Y.books(n_per_market=3, markets=list(S.FLAG_MARKETS))
    R2 = ST.analyse(few, Y.sessions_all(), cal, cr_draws=20, perm_draws=20, log=lambda *_: None)
    assert R2["verdict"].startswith("NOT READ")
    assert ST.money(-846.87) == "($847)" and ST.money(5) == "$5"
    late = Y.books(markets=["ES"]).copy()
    late.loc[late.index[0], "entry_date"] = pd.Timestamp("2022-01-03")
    with pytest.raises(SystemExit):
        ST.analyse(late, Y.sessions_all(), cal, cr_draws=5, perm_draws=5, log=lambda *_: None)
