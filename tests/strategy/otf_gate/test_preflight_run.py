"""OTF-G: G2 pre-flight end to end on synthetic data (counts only), the stop rule, the runner's refusals,
C-R, and the holdout ledger (G3)."""
import json

import numpy as np
import pandas as pd
import pytest

from strategy.otf_gate import books as BK
from strategy.otf_gate import controls as K
from strategy.otf_gate import holdout as HO
from strategy.otf_gate import ledger as L
from strategy.otf_gate import preflight as PF
from strategy.otf_gate import run as RUN
from strategy.otf_gate import spec as S
from strategy.w16.preflight import session_frames
from tests.strategy.otf_gate import synth as Y


def _inputs(tmp_path, n=40, weeks_b=14):
    d = Y.daily_frame()
    p = tmp_path / "books.csv"
    Y.books_csv(p, d, n=n)
    hb = {"ES": Y.cme_minutes("2020-01-06", weeks_b, seed=11), "NQ": Y.cme_minutes("2020-01-06", weeks_b, seed=12, base=9000)}
    return d, p, hb


def _pf(tmp_path, n=40, weeks_b=14):
    d, p, hb = _inputs(tmp_path, n, weeks_b)
    return RUN.build_and_run_preflight(p, ha_loader=lambda m: d, hb_loader=lambda r: hb[r], hb_train_frames=session_frames,
                                       hb_hashes={"ES": "x", "NQ": "y"}, expected_trades=n), d, p, hb


def test_preflight_counts_add_up_and_variants_are_counts(tmp_path):
    (a, b, agree, inputs), *_ = _pf(tmp_path)
    assert a["trades"] == 40 and a["kept"] + sum(a["reasons"].values()) == 40
    assert set(a["variants"]) == set(PF.VARIANT_COLS)
    assert a["variants"]["keep_soft"] >= a["kept"] and a["variants"]["keep_live"] >= 0
    assert b["trades"] == b["kept"] + sum(b["reasons"].values())
    assert sum(c["entries"] for c in b["b1_counts"].values()) == b["trades"] > 0
    assert all(cen["D"]["bars"] > 0 for cen in a["census"].values())
    assert set(inputs) == {"books", "h_a_daily_rows", "h_b_ES_1m", "h_b_NQ_1m"}
    assert a["counts"]["n"].sum() == 40 and a["counts"]["kept"].sum() == a["kept"]


def test_preflight_output_does_not_change_when_the_pnl_columns_do(tmp_path):
    d, p, hb = _inputs(tmp_path)
    loaders = dict(ha_loader=lambda m: d, hb_loader=lambda r: hb[r], hb_train_frames=session_frames, expected_trades=40)
    a1, b1, ag1, _ = RUN.build_and_run_preflight(p, **loaders)
    df = pd.read_csv(p)
    for c in ("gross", "qty", "sides", "net_low", "net_mid", "net_high", "exit_date", "exit_j"):
        df[c] = df[c] * 1000 if df[c].dtype.kind == "f" else df[c]
    df.to_csv(p, index=False)
    a2, b2, ag2, _ = RUN.build_and_run_preflight(p, **loaders)
    assert PF.render(a1, b1, agree=ag1) == PF.render(a2, b2, agree=ag2)


def test_preflight_h_b_entries_do_not_depend_on_bars_after_the_fill(tmp_path):
    d, p, hb = _inputs(tmp_path)
    frames = session_frames(hb["ES"])
    day = next(k for k in sorted(frames))
    e, _ = BK.run_b1_entries({day: frames[day]}, "ES", [day])
    if len(e):
        fill = e["fill_time"].iloc[0]
        poisoned = frames[day].copy()
        poisoned.loc[poisoned.index > fill, ["open", "high", "low", "close"]] = np.nan
        e2, _ = BK.run_b1_entries({day: poisoned}, "ES", [day])
        assert e2.equals(e)


def test_stop_rule_needs_both_hosts_below_their_floor(tmp_path):
    (a, b, agree, inputs), *_ = _pf(tmp_path)
    assert a["kept"] < S.MIN_KEPT_A and b["kept"] < S.MIN_KEPT_B          # tiny synthetic sample
    assert PF.stop(a, b) is True and "STOP" in PF.render(a, b, agree=agree)
    fake_b = dict(b, kept=S.MIN_KEPT_B)
    assert PF.stop(a, fake_b) is False
    fake_a = dict(a, kept=S.MIN_KEPT_A)
    assert PF.stop(fake_a, b) is False


def test_g4_holdout_days_are_refused_in_the_h_a_book(tmp_path):
    d = Y.daily_frame(start="2020-06-01", weeks=140)              # runs past 2021-12-31
    p = tmp_path / "b.csv"
    df = Y.books_csv(p, d, n=60)
    late = d[d["date"] > "2021-12-31"].index[3]
    df.loc[df.index[-1], ["entry_date", "entry_j"]] = [d["date"].iloc[late].strftime("%Y-%m-%d"), int(late)]
    df.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="after the training end"):
        PF.run_ha(BK.read_books(p, with_pnl=False), {"ES": d}, {"ES": pd.DatetimeIndex(d["date"])}, expected_trades=60)


def test_write_and_require_preflight(tmp_path):
    (a, b, agree, inputs), d, p, hb = _pf(tmp_path)
    out = tmp_path / "w15_0025_otf_preflight_20260930.txt"
    RUN.write_preflight(out, a, b, agree, inputs)
    js = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert js["inputs_sha256"] == inputs and js["stop"] is True
    with pytest.raises(SystemExit, match="pre-flight stopped"):
        RUN.require_preflight(tmp_path, inputs)
    with pytest.raises(SystemExit, match="different inputs"):
        RUN.require_preflight(tmp_path, dict(inputs, books="other"))
    with pytest.raises(SystemExit, match="no pre-flight"):
        RUN.require_preflight(tmp_path / "empty", inputs)
    js2 = dict(js, stop=False, data_stop=False)
    out.with_suffix(".json").write_text(json.dumps(js2), encoding="utf-8")
    assert RUN.require_preflight(tmp_path, inputs)["kept_a"] == js["kept_a"]


def test_g6_data_stop_on_missing_sessions_and_on_a_wide_roll_gap(tmp_path):
    d = Y.daily_frame()
    p = tmp_path / "books.csv"
    Y.books_csv(p, d, n=40)
    clean = {"ES": Y.cme_minutes("2020-01-06", 8, seed=11), "NQ": Y.cme_minutes("2020-01-06", 8, seed=12, base=9000)}
    kw = dict(ha_loader=lambda m: d, hb_train_frames=session_frames, expected_trades=40)
    a, b, ag, inp = RUN.build_and_run_preflight(p, hb_loader=lambda r: clean[r], **kw)
    assert RUN.data_stop(b) is False
    holes = {"ES": Y.cme_minutes("2020-01-06", 8, seed=11, skip_dates=("2020-01-15", "2020-01-16")), "NQ": clean["NQ"]}
    a, b, ag, inp = RUN.build_and_run_preflight(p, hb_loader=lambda r: holes[r], **kw)
    assert RUN.data_stop(b) is True and b["checks"]["ES"]["sessions"]["years"][2020]["missing"] == 2
    out = tmp_path / "pf.txt"
    assert RUN.write_preflight(out, a, b, ag, inp).startswith("*** G6 DATA STOP")
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["data_stop"] is True
    wide = Y.cme_minutes("2020-01-06", 8, seed=11, roll_at=("2020-01-15", "09:00"))
    k = int(np.flatnonzero(wide["held_id"].to_numpy()[1:] != wide["held_id"].to_numpy()[:-1])[0]) + 1
    wide = pd.concat([wide.iloc[:k - 10], wide.iloc[k:]])
    a, b, ag, inp = RUN.build_and_run_preflight(p, hb_loader=lambda r: wide if r == "ES" else clean[r], **kw)
    assert RUN.data_stop(b) is True and not b["checks"]["ES"]["switches"]["ok"].all()


def test_runner_refuses_narrowing_flags(capsys):
    for flag in ("--holdout", "--limit=5", "--spend", "--seen", "--markets=ES", "--window", "--hosts", "--variant=soft"):
        assert RUN.main(["--preflight", flag]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_runner_has_no_narrowing_option_in_its_parser():
    src = open(RUN.__file__, encoding="utf-8").read()
    for flag in ("--holdout", "--spend", "--limit"):
        assert f'add_argument("{flag}"' not in src


# ------------------------------------------------------------------ C-R
def _cr_sample(n=60, seed=0):
    rng = np.random.default_rng(seed)
    mk = np.array(["ES", "NQ"] * (n // 2))
    dr = np.array([1, -1, 1, 1] * (n // 4))
    return rng.normal(0, 100, (n, 3)), K.cell_keys(mk, dr)


def test_cr_keeps_exactly_k_per_cell_and_is_seeded():
    nets, cells = _cr_sample()
    keep = np.zeros(len(cells), dtype=bool)
    keep[:12] = True
    kc = K.k_by_cell(cells, keep)
    d1 = K.random_keep(nets, cells, kc, draws=50)
    d2 = K.random_keep(nets, cells, kc, draws=50)
    assert d1.shape == (50, 3) and np.array_equal(d1, d2)
    assert d1.std() > 0
    # keeping everything in every cell makes every draw equal the total
    allk = K.k_by_cell(cells, np.ones(len(cells), dtype=bool))
    d = K.random_keep(nets, cells, allk, draws=5)
    assert np.allclose(d, nets.sum(axis=0))
    with pytest.raises(ValueError):
        K.random_keep(nets, cells, {cells[0]: 999}, draws=1)


def test_cr_seed_layout_is_the_registered_one():
    import zlib
    rng = K._rng(7, "ES|1")
    ref = np.random.default_rng([zlib.crc32(b"7"), zlib.crc32(b"ES|1"), 25])
    assert rng.integers(0, 10**9) == ref.integers(0, 10**9)
    assert S.CR_SEED_TAG == 25 and S.CR_DRAWS == 1000 and S.CR_PCT == 97.5


def test_cr_percentile_counts_half_of_ties():
    assert K.percentile_of(5.0, np.array([1, 2, 5, 5, 9.0])) == 100 * (2 / 5 + 0.5 * 2 / 5)
    s = K.cr_summary(np.arange(1001.0))
    assert s["p97.5"] == pytest.approx(975.0) and s["p50"] == 500.0


# ------------------------------------------------------------------ G3 ledger
def _ledger(tmp_path):
    return L.Ledger("OTF-G", "holdout_otf_gate.json", "REGISTERED_otf_gate.md", HO.H.hosts, root=tmp_path)


def test_windows_train_gap_holdout_seen(tmp_path):
    Ld = _ledger(tmp_path)
    assert Ld.classify("H-A", "2021-12-31") == "train" and Ld.classify("H-A", "2022-01-01") == "gap"
    assert Ld.classify("H-A", "2022-01-03") == "holdout" and Ld.classify("H-A", "2025-09-22") == "holdout"
    assert Ld.classify("H-A", "2025-09-23") == "seen"
    assert Ld.classify("H-B", "2023-12-29") == "train" and Ld.classify("H-B", "2023-12-30") == "gap"
    assert Ld.classify("H-B", "2024-01-01") == "gap" and Ld.classify("H-B", "2024-01-02") == "holdout"
    assert Ld.classify("H-B", "2031-01-01") == "holdout"           # no end date: the end of the owned data
    days = ["2021-12-30", "2021-12-31", "2022-01-03", "2025-09-22", "2025-09-23"]
    keep, n_set_aside, label = Ld.split_dates("H-A", days)
    assert keep == days[:2] and n_set_aside == 3 and "training" in label
    assert Ld.seen_dates("H-A", days)[0] == ["2025-09-23"]
    with pytest.raises(L.HoldoutRefused):
        Ld.split_dates("H-C", days)


def test_limit_and_narrowing_are_refused(tmp_path):
    Ld = _ledger(tmp_path)
    for kw in ({"limit": 5}, {"markets": ["ES"]}, {"start": "2015-01-01"}):
        with pytest.raises(L.HoldoutRefused):
            Ld.split_dates("H-A", ["2020-01-02"], **kw)


def test_every_other_ledger_is_refused_by_name_and_the_own_one_is_not(tmp_path):
    Ld = _ledger(tmp_path)
    for name in ("holdout_va80.json", "holdout_w16_sb.json", "holdout_w16_dvp.json", "holdout_w16_bb.json",
                 "holdout_macro_flag.json", "holdout_crudele_3s.json", "holdout_breit_cap.json", "holdout.json",
                 "holdout_h60.json", "holdout_htf_ben_v2.json", "tl_v1_holdout_spent.json"):
        with pytest.raises(L.HoldoutRefused):
            Ld.load_for(tmp_path / name)
    Ld.load_for(tmp_path / "holdout_otf_gate.json")
    from strategy.va80 import holdout as VH
    with pytest.raises(L.HoldoutRefused):
        VH.H.load_for("holdout_otf_gate.json")
    with pytest.raises(L.HoldoutRefused):
        VH.H.load_for("holdout_w16_sb.json")
    VH.H.load_for("holdout_va80.json")


def test_spend_is_once_per_host_and_only_with_pass(tmp_path):
    Ld = _ledger(tmp_path)
    days = ["2021-12-31", "2022-01-03", "2023-05-05", "2025-09-22", "2025-09-23"]
    for bad in ({"candidate": "OTF-G/H-B", "verdict": "PASS"}, {"candidate": "OTF-G/H-A"},
                {"candidate": "OTF-G/H-A", "verdict": "FAIL"}, {"candidate": None, "verdict": "PASS"}):
        with pytest.raises(L.HoldoutRefused):
            Ld.split_dates("H-A", days, spend=True, **bad)
    assert not Ld.ledger_path.exists()
    keep, _, label = Ld.split_dates("H-A", days, spend=True, candidate="OTF-G/H-A", verdict="PASS")
    assert keep == days[1:4] and "LOCKED" in label
    led = json.loads(Ld.ledger_path.read_text(encoding="utf-8"))
    assert list(led) == ["H-A"] and led["H-A"]["verdict"] == "PASS" and led["H-A"]["n_locked_days"] == 3
    with pytest.raises(L.HoldoutRefused, match="already spent"):
        Ld.split_dates("H-A", days, spend=True, candidate="OTF-G/H-A", verdict="PASS")
    Ld.split_dates("H-B", ["2024-02-01"], spend=True, candidate="OTF-G/H-B", verdict="PASS")     # its own key
    assert sorted(json.loads(Ld.ledger_path.read_text(encoding="utf-8"))) == ["H-A", "H-B"]


def test_cli_spend_needs_the_training_passed_flag(tmp_path, capsys):
    Ld = _ledger(tmp_path)
    assert Ld.main(["--spend", "H-A"]) == 2
    assert Ld.main(["--spend", "H-Z", "--training-passed"]) == 2
    assert not Ld.ledger_path.exists()
    assert Ld.main(["--spend", "H-A", "--training-passed"]) == 0 and Ld.ledger_path.exists()
    assert Ld.main(["--status"]) == 0 and "SPENT" in capsys.readouterr().out


def test_builders_cut_through_the_one_split_implementation():
    from strategy.otf_gate import bars_ha, bars_hb
    assert bars_ha.HOLD is HO.H and bars_hb.HOLD is HO.H
