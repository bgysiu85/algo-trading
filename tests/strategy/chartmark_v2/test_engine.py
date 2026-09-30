import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import data as D
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import holdout as HO
from strategy.chartmark_v2 import parity as PA
from strategy.chartmark_v2 import preflight as PF
from strategy.chartmark_v2 import spec as S
from strategy.htf.signals import ema_seeded
from tests.strategy.chartmark.synth import cut, walk

SEEN = Path(__file__).resolve().parents[3] / "Claude outputs" / "w15_0032_cl1_1h_bars_indicators.csv"
needs_seen = pytest.mark.skipif(not SEEN.exists(), reason="seen-window CSV not present")
ALL = {"K1": S.K1, "K2": S.K2, "K3": S.K3, "K4": S.K4, **S.variants_of(S.K1)}


def sim(fr, p=S.K1, **kw):
    ind = D.indicators(fr)
    return E.simulate(fr, ind, p, **kw)


def key(t):
    return (t.entry_j, t.exit_j, round(t.entry_px, 6), round(t.exit_px, 6), t.reason)


# ---- registered constants -------------------------------------------------------
def test_registered_constants():
    assert (S.K1.prev_high, S.K1.theta) == (True, 0.05) and (S.K2.prev_high, S.K2.theta) == (True, 0.03)
    assert (S.K3.prev_high, S.K3.theta) == (False, 0.05) and (S.K4.prev_high, S.K4.theta) == (False, 0.03)
    assert S.K1.backstop == 0.60 and S.K1.par_bars == 6 and S.K1.ema_window == 4 and not S.K1.session
    assert S.NEAR_MACD == 0.05 and S.NEAR_GAP == 0.10 and S.RED_LOOK == 10 and S.MIN_TRADES_WINDOW == 75
    assert S.per_side("MCL", "mid") == pytest.approx(1.77) and S.per_side("CL", "high") == pytest.approx(22.37)
    assert set(S.variants_of(S.K1)) == {"V-THETA03", "V-WICK", "V-STOP20", "V-STOPATR", "V-SESSION", "V-CONFIRMED",
                                        "V-AVOID", "V-REDTOP", "V-WICKGATE"}
    assert S.variants_of(S.K1)["V-STOP20"].backstop == 0.20


# ---- the live-level maths (Amendment 1.1) is exact --------------------------------
def _recompute(fr, t, price):
    """Real recursion: append a bar t+1 closing at `price` and recompute EMA9/21, MACD, signal from scratch."""
    c = np.append(fr.c[: t + 1], price)
    s = pd.Series(c)
    e9, e21 = ema_seeded(s, 9).to_numpy(), ema_seeded(s, 21).to_numpy()
    e12, e26 = ema_seeded(s, 12).to_numpy(), ema_seeded(s, 26).to_numpy()
    sig = ema_seeded(pd.Series(e12 - e26), 9).to_numpy()
    return e9, e21, (e12 - e26) - sig


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_live_level_satisfies_conditions_and_is_minimal(seed):
    fr = walk(3000, seed, drift=0.01)
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    checked = {"A-early": 0, "A-fresh": 0, "B": 0}
    for t in range(40, fr.n - 2):
        k = E._arm_kind(fr, ind, pre, S.K3, t)
        if k is None:
            continue
        lvl, why = E._level(fr, ind, pre, S.K3, t, k)
        if lvl is None:
            continue
        red = E._red_level(fr, t)
        e9, e21, hist = _recompute(fr, t, lvl)
        assert e9[-1] > e21[-1]
        if k == "B":
            assert hist[-1] >= S.K3.theta * ind.atr[t] - 1e-9
            assert (e9[-1] - e21[-1]) > (ind.e9[t] - ind.e21[t])
        else:
            assert hist[-1] > ind.hist[t]
        assert lvl >= red - 1e-9 and lvl > fr.c[t]
        checked[k] += 1
    assert sum(checked.values()) > 20


# ---- G4 look-ahead guards ------------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("name", list(ALL))
def test_truncation_invariance(seed, name):
    """Nothing decided before bar k depends on bars from k on: trades closed well before the cut are identical."""
    fr = walk(2500, seed, drift=0.01)
    p = ALL[name]
    full, _ = sim(fr, p)
    for k in (900, 1500, 2100):
        part, _ = sim(cut(fr, k), p)
        a = [key(t) for t in full if t.exit_j < k - 2]
        b = [key(t) for t in part if t.exit_j < k - 2]
        assert a == b and len(a) > 0, (name, seed, k)


def stream_diff(fr, ks, p=S.K1):
    """Number of decisions at t <= k-1 that differ between the full frame and its truncation to k bars, over all cuts k."""
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    full = E.decisions(fr, ind, p, pre)
    bad = 0
    for k in ks:
        part_fr = cut(fr, k)
        part = E.decisions(part_fr, D.indicators(part_fr), p)
        bad += sum(1 for a, b in zip(full[: k - 3], part) if a != b)
    return bad


CUTS = range(1000, 1080)


@pytest.mark.parametrize("name", list(ALL))
def test_decision_stream_truncation_invariance(name):
    """The decision at the close of t (arm kind + level) is identical with or without bars after t -- for EVERY t up to the cut."""
    fr = walk(2500, 2, drift=0.01)
    assert stream_diff(fr, CUTS, ALL[name]) == 0


def test_mutation_lookahead_is_caught(monkeypatch):
    """A one-bar shift of the arming decision (reads bar t+1) must break the stream test."""
    real = E._arm_kind

    def leaky(fr, ind, pre, p, t):
        return real(fr, ind, pre, p, min(t + 1, fr.n - 1))

    fr = walk(2500, 1, drift=0.01)
    monkeypatch.setattr(E, "_arm_kind", leaky)
    assert stream_diff(fr, CUTS) > 0


def test_mutation_level_lookahead_is_caught(monkeypatch):
    """Using bar t+1's high in the level must also be caught."""
    real = E._level

    def leaky(fr, ind, pre, p, t, kind):
        lvl, why = real(fr, ind, pre, p, t, kind)
        return (None if lvl is None else min(lvl, fr.h[min(t + 1, fr.n - 1)] + 0.01)), why

    fr = walk(2500, 2, drift=0.01)
    monkeypatch.setattr(E, "_level", leaky)
    assert stream_diff(fr, CUTS) > 0


def test_decisions_use_bars_le_t():
    fr = walk(1500, 4)
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    k0 = [E._arm_kind(fr, ind, pre, S.K1, t) for t in range(1000)]
    fr2 = walk(1500, 4)
    for x in (fr2.o, fr2.h, fr2.l, fr2.c):
        x[1000:] += 5.0
    ind2 = D.indicators(fr2)
    pre2 = E.precompute(fr2, ind2)
    k1 = [E._arm_kind(fr2, ind2, pre2, S.K1, t) for t in range(1000)]
    assert k0 == k1


# ---- order / fill / exit invariants --------------------------------------------------------
@pytest.mark.parametrize("name", ["K1", "K3", "V-STOP20", "V-WICK", "V-REDTOP", "V-CONFIRMED", "V-WICKGATE", "V-STOPATR"])
def test_trade_invariants(name):
    p = ALL[name]
    seen_reasons = set()
    for seed in (1, 2, 3, 4):
        fr = walk(4000, seed, drift=0.01, vol=0.2, roll_every=700)
        ind = D.indicators(fr)
        trades, cnt = E.simulate(fr, ind, p)
        prev_exit = -1
        for t in trades:
            assert t.entry_j == t.placed_j + 1 and t.entry_j > prev_exit
            assert t.entry_px == pytest.approx(max(t.level, fr.o[t.entry_j])) and t.level > fr.c[t.placed_j]
            assert fr.h[t.entry_j] >= t.level
            assert not fr.roll_after[t.placed_j]
            assert t.exit_j >= t.entry_j
            if t.reason == "BACKSTOP-fillbar":
                assert t.exit_j == t.entry_j and t.exit_px == pytest.approx(t.entry_px - t.dist)
                assert fr.l[t.entry_j] <= t.entry_px - t.dist + 1e-9
            if t.reason == "BACKSTOP":
                assert t.exit_j > t.entry_j and t.exit_px <= t.entry_px - t.dist + 1e-9 or fr.o[t.exit_j] <= t.entry_px - t.dist
            if t.reason == "EMA21":
                assert t.clauses
            if t.reason == "UNCONFIRMED":
                assert t.exit_j == t.entry_j + 1 and t.exit_px == pytest.approx(fr.o[t.exit_j])
            assert t.n_rolls == int(fr.roll_after[t.entry_j:t.exit_j].sum())
            prev_exit = t.exit_j
            seen_reasons.add(t.reason)
        assert cnt["fills"] == len(trades) and sum(cnt["exits"].values()) == len(trades)
        assert cnt["orders"] >= cnt["fills"]
    assert seen_reasons


def oracle_exit(fr, ind, e, stop, p):
    """Independent, brute-force sec 2.5 for the close-breach base (no wick), used to check the engine's exit walk."""
    n = fr.n
    breaches = []
    for j in range(e + 1, n):
        if fr.o[j] <= stop:
            return j, fr.o[j], "BACKSTOP"
        if fr.l[j] <= stop:
            return j, stop, "BACKSTOP"
        if fr.c[j] < ind.e21[j]:
            c1 = any(0 < j - b <= p.ema_window - 1 for b in breaches)
            below = 0
            while j - below >= 0 and ind.hist[j - below] < 0:
                below += 1
            c2 = below >= 5
            d = [(-ind.hist[j - i]) - (-ind.hist[j - i - 1]) for i in range(3)]
            c3 = below >= 3 and all(x > 0 for x in d) and d[0] > d[1] > d[2]
            breaches.append(j)
            if c1 or c2 or c3:
                return (j + 1, fr.o[j + 1], "EMA21") if j + 1 < n else (j, fr.c[j], "data_end")
    return n - 1, fr.c[-1], "data_end"


@pytest.mark.parametrize("seed", [1, 2, 3, 5])
def test_exit_walk_matches_oracle(seed):
    fr = walk(5000, seed, drift=0.01, vol=0.2)
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind, S.K3)
    n_ema = 0
    for t in trades:
        if t.reason == "BACKSTOP-fillbar":
            continue
        x, px, why = oracle_exit(fr, ind, t.entry_j, t.entry_px - t.dist, S.K3)
        assert (x, round(px, 6), why) == (t.exit_j, round(t.exit_px, 6), t.reason)
        n_ema += t.reason == "EMA21"
    assert n_ema > 5


# ---- variants do what they say -----------------------------------------------------------------
def test_session_variant_only_fills_in_session_and_stop20_stops_more():
    fr = walk(6000, 3, drift=0.01, vol=0.2, start="2015-01-05 00:00")
    ind = D.indicators(fr)
    ts, _ = E.simulate(fr, ind, S.variants_of(S.K1)["V-SESSION"])
    assert ts and all(S.SESSION_FIRST <= ind.hour[t.entry_j] <= S.SESSION_LAST for t in ts)
    b, _ = E.simulate(fr, ind, S.K1)
    s20, _ = E.simulate(fr, ind, S.variants_of(S.K1)["V-STOP20"])
    fb = lambda tr: sum(t.reason == "BACKSTOP-fillbar" for t in tr) / max(1, len(tr))
    assert fb(s20) > fb(b)


def test_prev_high_on_never_lowers_level():
    fr = walk(3000, 2, drift=0.01)
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    n = 0
    for t in range(40, fr.n - 2):
        k = E._arm_kind(fr, ind, pre, S.K1, t)
        if k:
            a = E._level(fr, ind, pre, S.K1, t, k)[0]
            b = E._level(fr, ind, pre, S.K3, t, k)[0]
            if a is not None and b is not None:
                assert a >= b - 1e-9 and a >= fr.h[t] + S.TICK - 1e-9
                n += 1
    assert n > 10


def test_wickgate_only_adds_prev_high_after_long_wicks():
    o = np.array([10, 10, 10]); c = np.array([10.4, 10.4, 10.4]); h = np.array([11.0, 11.0, 10.5]); l = np.array([10.0, 10.0, 10.0])
    fr = D.make_frame(pd.date_range("2015-01-05", periods=3, freq="h", tz="UTC"), o, h, l, c, np.ones(3))
    assert E._wick_gate(fr, 2) is True          # wicks 0.6/1.0=60%, 60%, 0.1/0.5=20% -> two long
    fr.h[:] = 10.5
    assert E._wick_gate(fr, 2) is False


def test_refused_flags_and_window_split():
    for f in ("--pnl", "--backtest", "--holdout", "--limit=10", "--net"):
        with pytest.raises(SystemExit):
            PF.main([f])
    assert PF.window_of("2015-12-31") == "dev" and PF.window_of("2016-01-01") == "conf"
    assert PF.window_of("2010-06-05") is None and PF.window_of("2022-01-03") is None


def test_preflight_counts_and_render_have_no_pnl():
    fr = walk(9000, 3, drift=0.01, vol=0.2, start="2010-06-07 00:00")
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    blocks = {}
    for name, p in S.CANDIDATES.items():
        trades, cnt = E.simulate(fr, ind, p, pre=pre)
        blocks[name] = PF.counts_block(fr, trades, cnt)
        assert blocks[name]["windows"]["dev"]["fills"] + blocks[name]["windows"]["conf"]["fills"] <= blocks[name]["n"]
    text = PF.render(blocks, "20260930", fr.label, fr.n, fr.ny[0], fr.ny[-1])
    for bad in ("gross", "net ", "P&L $", "pnl"):
        assert bad not in text.replace("no price or P&L is reported here", "")
    assert "SELECTION POOL" in text and "Registered prediction" in text


def test_preflight_reads_training_only():
    src = Path(PF.__file__).read_text(encoding="utf-8")
    assert "load_training_frame" in src and "load_seen_frame" not in src


# ---- G3 holdout ledger -------------------------------------------------------------------------
@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "holdout_chartmark_v2.json")
    return HO.H.ledger_path


def test_ledger_refusals(ledger):
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], limit=100)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], head=5)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="K3", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-v2", verdict="FAIL")
    for other in ("holdout_chartmark_v1.json", "holdout_chartmark_short_v1.json", "holdout_htf_ben_v2.json",
                  "holdout_macro_flag.json", "holdout_h60.json"):
        with pytest.raises(HO.HoldoutRefused):
            HO.load_for(other)
    HO.load_for("holdout_chartmark_v2.json")


def test_other_lines_refuse_the_v2_ledger():
    from strategy.chartmark import holdout as H1
    from strategy.chartmark_s import holdout as HS
    for mod in (H1, HS):
        with pytest.raises(mod.HoldoutRefused):
            mod.load_for("holdout_chartmark_v2.json")


def test_ledger_spends_once_and_records_windows(ledger):
    keep, aside, side = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-05", "2025-09-08"],
                                       spend=True, candidate="CHARTMARK-v2", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-05"]
    rec = json.loads(ledger.read_text())
    assert rec["excluded_entry_windows"] == [["2025-02-19", "2025-03-04"], ["2025-06-22", "2025-07-03"]]
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-v2", verdict="PASS")


def test_training_split_and_windows():
    keep, aside, _ = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-08"])
    assert keep == ["2021-12-30"] and aside == 2
    assert HO.excluded("2025-02-19") and not HO.excluded("2025-03-05") and HO.is_seen("2025-09-08")


def test_no_ledger_file_in_repo():
    assert not (Path(__file__).resolve().parents[3] / "holdout_chartmark_v2.json").exists()


# ---- seen-window regression against the registration's own numbers (not evidence) ---------------
@needs_seen
def test_seen_window_matches_registered_counts():
    from strategy.chartmark.data import load_seen_frame
    fr = load_seen_frame(SEEN)
    ind = D.indicators(fr)
    pre = E.precompute(fr, ind)
    m = ~np.isnan(ind.hist)
    assert np.allclose((pre.e12 - pre.e26 - pre.sig)[m], ind.hist[m])
    tr, c = E.simulate(fr, ind, S.K1, pre=pre)            # Amendment 3.5
    assert (len(tr), sum(t.exit_px > t.entry_px for t in tr)) == (71, 14)
    assert sum(t.exit_px - t.entry_px for t in tr) == pytest.approx(-5.05, abs=0.006)
    assert c["exits"] == {"EMA21": 27, "BACKSTOP": 27, "BACKSTOP-fillbar": 17}
    tr, c = E.simulate(fr, ind, S.K3, pre=pre)            # Amendment 2.3
    assert (len(tr), sum(t.exit_px > t.entry_px for t in tr)) == (86, 20)
    assert sum(t.exit_px - t.entry_px for t in tr) == pytest.approx(5.40, abs=0.006)
    assert c["exits"] == {"EMA21": 36, "BACKSTOP": 35, "BACKSTOP-fillbar": 15}


@needs_seen
def test_g6_parity_only_the_documented_conflict_fails():
    for p in (S.K1, S.K3):
        bad = [c["name"] for c in PA.checks(SEEN, p) if not c["ok"]]
        assert len(bad) == 1 and "CONFLICT" in bad[0], bad


def test_preflight_run_writes_counts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "load_training_frame", lambda archive: walk(9000, 5, drift=0.01, vol=0.2, start="2010-06-07 00:00"))
    path = PF.run("ignored", tmp_path, "20260930", log=lambda *_: None)
    assert path.exists() and path.name == "w15_0036_v2_preflight_20260930.txt"
    js = json.loads((tmp_path / "w15_0036_v2_preflight_20260930.json").read_text())
    assert set(js) == {"K1", "K2", "K3", "K4"}
    assert "exit_px" not in json.dumps(js) and "gross" not in json.dumps(js)
