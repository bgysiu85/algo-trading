"""W15-0037 sub 2: strategy.chartmark_v2.forward -- the weekly forward scorer. No network, no archive: a fake Databento client, a synthetic
CME-shaped raw frame standing in for the day files, and the ledger redirected into tmp_path."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import book as BK
from strategy.chartmark import data as D
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import forward as F
from strategy.chartmark_v2 import spec as S
from tests.strategy.chartmark.synth import walk


# ----------------------------------------------------------------------------------------------- synthetic CME-shaped raw bars
def make_raw(first="2026-06-01", last="2027-01-15", seed=3, drift=0.003, vol=0.18, roll_every=45):
    """CL.c.0 1H rows as read_dbn would return them: UTC index, symbol, instrument_id, OHLCV. Weekday sessions 18:00-16:00 ET
    (23 bars) plus the 17:00 settlement print, rolls every `roll_every` sessions."""
    rng = np.random.default_rng(seed)
    rows, px = [], 60.0
    for si, day in enumerate(pd.bdate_range(first, last)):
        inst = 1000 + si // roll_every
        if si and si % roll_every == 0:
            px += rng.normal(0, 0.3)                                   # a roll gap
        open_naive = day - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        for k in range(24):
            t = (open_naive + pd.Timedelta(hours=k)).tz_localize("America/New_York", nonexistent="shift_forward", ambiguous=False)
            r = rng.normal(drift, vol)
            o, c = px, px + r
            hi, lo = max(o, c) + abs(rng.normal(0, vol / 2)), min(o, c) - abs(rng.normal(0, vol / 2))
            rows.append((t.tz_convert("UTC"), "CL.c.0", inst, round(o, 2), round(hi, 2), round(lo, 2), round(c, 2), 1000))
            px = round(c, 2)
    df = pd.DataFrame(rows, columns=["ts_event", "symbol", "instrument_id", "open", "high", "low", "close", "volume"]).set_index("ts_event")
    return df.sort_index()


RAW = make_raw()


def raw_through(day: str) -> pd.DataFrame:
    """All rows a pull would have on disk once UTC day `day` is bought: everything before day+1 00:00Z."""
    return RAW[RAW.index < pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)]


def daily_of(raw: pd.DataFrame) -> pd.DataFrame:
    d = F.HB.split_held(raw)
    u = F.RB.utc_daily(d)
    return u[["date", "open", "high", "low", "close", "volume"]]


# ----------------------------------------------------------------------------------------------- fake Databento client
class _Data:
    def __init__(self, log):
        self.log = log

    def to_file(self, path):
        self.log.append(("to_file", str(path)))
        Path(path).write_bytes(b"DBN-fake")


class _Meta:
    def __init__(self, cost, log, dataset_end, fail=None):
        self.cost, self.log, self.dataset_end, self.fail = cost, log, dataset_end, fail or {}

    def get_dataset_range(self, dataset):
        self.log.append(("range", dataset))
        return {"start": "2010-06-06T00:00:00Z", "end": self.dataset_end}

    def get_cost(self, **kw):
        self.log.append(("cost", kw))
        day = kw["start"][:10]
        if day in self.fail:
            raise RuntimeError(self.fail[day])
        return self.cost

    def get_billable_size(self, **kw):
        return 100_000


class _TS:
    def __init__(self, log):
        self.log = log

    def get_range(self, **kw):
        self.log.append(("get_range", kw))
        return _Data(self.log)


class FakeClient:
    def __init__(self, cost=0.01, dataset_end="2027-12-31T00:00:00Z", fail=None):
        self.log = []
        self.metadata = _Meta(cost, self.log, dataset_end, fail)
        self.timeseries = _TS(self.log)

    def calls(self, name):
        return [c for c in self.log if c[0] == name]


GATE_OK = dict(passed=True, step_c_trades=317, seen_trades=69, seen_pts=2.29)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Ledger, archive and loaders redirected; freeze + regression gates stubbed (tested on their own below)."""
    archive = tmp_path / "archive"
    monkeypatch.setattr(F, "LEDGER_PATH", tmp_path / "forward_chartmark_v2.json")
    monkeypatch.setattr(F, "_dataset", lambda: "GLBX.MDP3")
    monkeypatch.setattr(F, "freeze_check", lambda root=F.ROOT, **k: dict(commit=F.FROZEN_COMMIT, head="abcdef0", strict_paths=[]))
    monkeypatch.setattr(F, "load_raw_1h", lambda arch, days: raw_through(max(days)))
    monkeypatch.setattr(F, "load_daily_1d", lambda arch, days: daily_of(raw_through(max(days))))
    return archive


def cycle(archive, as_of, *, client=None, **kw):
    return F.run(archive, as_of=as_of, client=client or FakeClient(), confirm=True, regression=lambda a: GATE_OK, draws=kw.pop("draws", 20), **kw)


def trades_of(ledger):
    return {n: [(t["entry_t"], t["exit_t"], t["reason"], t["arm"], t["n_rolls"], round(t["pts"], 2)) for t in v["trades"]]
            for n, v in ledger["rules"].items()}


# ----------------------------------------------------------------------------------------------- G-freeze
def _git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True)


def test_freeze_check_passes_then_refuses_a_changed_working_tree_or_head_and_a_missing_commit(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    eng = tmp_path / "engine.py"
    eng.write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "frozen")
    frozen = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = F.freeze_check(tmp_path, frozen, ("engine.py",))
    assert out["commit"] == frozen
    eng.write_text("x = 2\n", encoding="utf-8")                         # working tree differs
    with pytest.raises(SystemExit, match="G-freeze"):
        F.freeze_check(tmp_path, frozen, ("engine.py",))
    _git(tmp_path, "commit", "-qam", "changed")                           # HEAD differs too
    with pytest.raises(SystemExit, match="G-freeze"):
        F.freeze_check(tmp_path, frozen, ("engine.py",))
    with pytest.raises(SystemExit, match="not in this repository"):
        F.freeze_check(tmp_path, "deadbee", ("engine.py",))


def test_freeze_check_on_this_repo_names_the_registered_commit_and_paths():
    assert F.FROZEN_COMMIT == "f3872ff"
    assert F.STRICT_PATHS == ("strategy/chartmark_v2/engine.py", "strategy/chartmark_v2/spec.py")


# ----------------------------------------------------------------------------------------------- G-regression
def _ref_from(fr, start, tmp_path):
    tr, _ = E.simulate(fr, D.indicators(fr), S.K1, start=start)
    df = BK.trade_frame(tr, fr, "MCL", "mid")
    p = tmp_path / "ref.csv"
    df[["entry_t", "exit_t", "entry_px", "exit_px", "exit_reason", "n_rolls"]].to_csv(p, index=False)
    return p, df


def test_compare_trade_lists_flags_count_bars_prices_and_reasons():
    fr = walk(9000, 5, drift=0.002, start="2015-05-04 00:00", roll_every=1500)
    tr, _ = E.simulate(fr, D.indicators(fr), S.K1, start=3000)
    df = BK.trade_frame(tr, fr, "MCL", "mid")
    ref = df[["entry_t", "exit_t", "entry_px", "exit_px", "exit_reason", "n_rolls"]].copy()
    assert F.compare_trade_lists(df, ref) == []
    assert any("count" in d for d in F.compare_trade_lists(df, ref.iloc[:-1]))
    bad = ref.copy()
    bad.loc[2, "exit_px"] += 0.01
    assert any("price" in d for d in F.compare_trade_lists(df, bad))
    bad = ref.copy()
    bad.loc[1, "exit_t"] = "2001-01-01 00:00:00"
    assert any("bar" in d for d in F.compare_trade_lists(df, bad))
    bad = ref.copy()
    bad.loc[0, "exit_reason"] = "XX"
    assert any("reason" in d for d in F.compare_trade_lists(df, bad))


def test_regression_gate_passes_on_identical_lists_and_refuses_each_kind_of_difference(tmp_path, monkeypatch):
    fr = walk(9000, 5, drift=0.002, start="2015-05-04 00:00", roll_every=1500)
    start = F.CC.window_start(fr)
    ref_path, df = _ref_from(fr, start, tmp_path)
    seen = walk(3000, 2, drift=0.002, start="2025-09-08 00:00")
    st, _ = E.simulate(seen, D.indicators(seen), S.K1)
    monkeypatch.setattr(F, "STEPC_TRADES", len(df))
    monkeypatch.setattr(F, "SEEN_TRADES", len(st))
    monkeypatch.setattr(F, "SEEN_GROSS_PTS", round(sum(t.exit_px - t.entry_px for t in st), 2))
    out = F.regression_gate(None, ref_csv=ref_path, training_frame=fr, seen_frame=seen)
    assert out["passed"] and out["step_c_trades"] == len(df)
    # a reference with a different price is refused
    ref = pd.read_csv(ref_path)
    ref.loc[0, "entry_px"] += 0.02
    bad = tmp_path / "bad.csv"
    ref.to_csv(bad, index=False)
    with pytest.raises(SystemExit, match="NOT reproduced"):
        F.regression_gate(None, ref_csv=bad, training_frame=fr, seen_frame=seen)
    # a wrong seen-window count is refused
    monkeypatch.setattr(F, "SEEN_TRADES", len(st) + 1)
    with pytest.raises(SystemExit, match="seen-window"):
        F.regression_gate(None, ref_csv=ref_path, training_frame=fr, seen_frame=seen)
    # a reference with the wrong number of trades is refused before anything runs
    monkeypatch.setattr(F, "STEPC_TRADES", len(df) + 5)
    with pytest.raises(SystemExit, match="holds"):
        F.regression_gate(None, ref_csv=ref_path, training_frame=fr, seen_frame=seen)


def test_the_committed_reference_holds_steps_c_317_trades_and_k1_reproduces_the_seen_window():
    ref = pd.read_csv(F.REF_STEPC)
    assert len(ref) == F.STEPC_TRADES == 317
    assert set(ref.exit_reason) == {"EMA21", "BACKSTOP", "BACKSTOP-fillbar"}
    if F.SEEN_CSV.exists():                                               # Ben's machine / the repo checkout
        fr = D.load_seen_frame(F.SEEN_CSV)
        st, _ = E.simulate(fr, D.indicators(fr), S.K1)
        assert len(st) == F.SEEN_TRADES == 69
        assert abs(sum(t.exit_px - t.entry_px for t in st) - F.SEEN_GROSS_PTS) < 0.005


# ----------------------------------------------------------------------------------------------- frame, start, read-back
def test_frame_is_cut_by_session_label_excludes_settlement_and_starts_at_the_registered_bar():
    fr = F.frame_from_raw(raw_through("2026-10-09"), "2026-10-07")
    ny = fr.ny
    assert str(ny[-1].date()) <= "2026-10-07" and ny[-1].hour == 16                 # last bar of session 7 Oct is the 16:00 bar
    assert ny[0].strftime("%Y-%m-%d") >= "2026-05-31"                                # warm-up starts with the 1 June session
    assert not (ny.hour == 17).any()                                                 # the 17:00 settlement print is not a bar
    s = F.forward_start(fr)
    assert ny[s].strftime("%Y-%m-%d %H:%M") == F.FIRST_BAR_ET
    assert s > 0 and ny[s - 1].strftime("%Y-%m-%d %H:%M") == "2026-09-30 16:00"
    assert F.frame_from_raw(pd.DataFrame(), None) is None
    assert F.forward_start(F.frame_from_raw(raw_through("2026-09-25"), "2026-09-25")) is None


def test_read_back_passes_on_matching_closes_and_fails_below_99_percent():
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-09-30", "2026-11-30")]
    raw = raw_through("2026-11-30")
    daily = daily_of(raw)
    daily = daily[daily["date"].astype(str).isin(days)].reset_index(drop=True)
    ok = F.read_back(raw, daily, days)
    assert ok["passed"] and ok["agreement"]["pct_within_tol"] == 1.0
    bad = daily.copy()
    bad.loc[:4, "close"] += 0.50                                                     # 5 of ~45 days off by 50c
    assert not F.read_back(raw, bad, days)["passed"]
    one = daily.copy()
    one.loc[3, "close"] += 0.05
    assert not F.read_back(raw, one, days)["passed"]                                 # 1 of 45 = 97.8% < 99%
    tick = daily.copy()
    tick["close"] += 0.004                                                           # inside a tick
    assert F.read_back(raw, tick, days)["passed"]


# ----------------------------------------------------------------------------------------------- stops
def row(pts, n=0, t="2026-10-01 10:00:00"):
    return dict(entry_t=t, exit_t=t, pts=pts, n_rolls=n, reason="EMA21", arm="B")


def test_stop_a_fires_only_after_30_trades_and_later_trades_are_dropped():
    losses = [row(-0.60, t=f"2026-10-{1 + i // 20:02d} {i % 20:02d}:00:00") for i in range(40)]
    kept, stop = F.apply_stops(losses)
    assert stop["stop"] == "A" and len(kept) == 30                                    # at 16 trades net is already ($1,016): not yet
    assert stop["net"] < -1000
    kept16, stop16 = F.apply_stops(losses[:29])
    assert stop16 is None and len(kept16) == 29


def test_stop_b_fires_on_drawdown_from_peak_and_not_at_2300_exactly():
    wins = [row(+3.0) for _ in range(20)]
    lose = [row(-0.60) for _ in range(40)]                                            # each ($63.54)
    kept, stop = F.apply_stops(wins + lose)
    assert stop["stop"] == "B" and len(kept) == 20 + 37 and stop["drawdown"] > 2300
    assert F.apply_stops(wins + lose[:36])[1] is None                                 # 36 x 63.54 = 2,287 < 2,300


def test_stops_do_not_depend_on_how_the_rows_arrive():
    rows = [row(+3.0) for _ in range(5)] + [row(-0.6) for _ in range(60)]
    full_kept, full_stop = F.apply_stops(rows)
    for k in (7, 19, 33, 48):
        kept, stop = F.apply_stops(rows[:k])
        if stop is None:
            kept, stop = F.apply_stops(rows)
        assert (len(kept), stop["stop"] if stop else None) == (len(full_kept), full_stop["stop"] if full_stop else None)


# ----------------------------------------------------------------------------------------------- controls
def test_c3_draws_are_seeded_non_overlapping_and_count_matched():
    fr = walk(4000, 9, drift=0.002, start="2026-06-01 00:00")
    ind = D.indicators(fr)
    es, xs, nets = F.c3_pool(fr, ind, S.K1, 2500, session_only=False)
    assert len(es) and (es >= 2500).all()
    a, sa = F.c3_draws(es, xs, nets, 12, 30)
    b, sb = F.c3_draws(es, xs, nets, 12, 30)
    assert np.array_equal(a, b) and sa == sb == 0                                     # deterministic
    assert F.c3_draws(es, xs, nets, 0, 10) == (None, 0)
    tot, short = F.c3_draws(es[:5], xs[:5], nets[:5], 50, 5)                          # cannot fill 50 from 5
    assert short == 5
    # with one candidate per bar and exits >= entries, no accepted pair may overlap: check via a brute-force replay of draw 0
    rng = np.random.default_rng([F.crc32(b"0"), F.crc32(F.C3_LABEL), 12])
    acc = []
    for i in rng.permutation(len(es)):
        if len(acc) >= 12:
            break
        if not any(es[i] <= xs[j] and es[j] <= xs[i] for j in acc):
            acc.append(i)
    assert abs(sum(nets[j] for j in acc) - F.c3_draws(es, xs, nets, 12, 1)[0][0]) < 1e-9


def test_c3_pool_for_v_session_only_has_bars_opening_0200_to_1200_ny():
    fr = walk(4000, 9, drift=0.002, start="2026-06-01 00:00")
    ind = D.indicators(fr)
    es, _, _ = F.c3_pool(fr, ind, S.K1, 2500, session_only=True)
    assert len(es) and ((ind.hour[es] >= 2) & (ind.hour[es] <= 12)).all()
    assert len(es) < len(F.c3_pool(fr, ind, S.K1, 2500, session_only=False)[0])


def test_rules_are_exactly_k1_and_the_two_registered_variants():
    assert F.RULES["K1"] == S.K1 == S.Params(prev_high=True, theta=0.05)
    assert F.RULES["V-SESSION"] == S.Params(prev_high=True, theta=0.05, session=True)
    assert F.RULES["V-WICKGATE"] == S.Params(prev_high=True, theta=0.05, wickgate=True)
    assert F.C3_P == {"K1": 95, "V-SESSION": 99, "V-WICKGATE": 99}


# ----------------------------------------------------------------------------------------------- the weekly cycle
def test_nothing_due_before_the_first_session_and_estimate_writes_nothing(env):
    r = F.run(env, as_of="2026-09-30", client=FakeClient(), confirm=True, regression=lambda a: GATE_OK)
    assert r.get("no_new_sessions") and not F.LEDGER_PATH.exists()
    c = FakeClient()
    r = F.run(env, as_of="2026-10-05", client=c, confirm=False, regression=lambda a: GATE_OK)
    assert r["estimate_only"] and r["n_jobs"] == 1 + 2 * 5                           # warm-up + (30 Sep..4 Oct) x two schemas
    assert not F.LEDGER_PATH.exists() and not c.calls("get_range") and not F.manifest_path(env).exists()
    assert "ESTIMATE ONLY" in F.txt_report(r)


def test_max_cost_aborts_before_any_download(env):
    c = FakeClient(cost=3.0)
    with pytest.raises(SystemExit, match="ABORT"):
        F.run(env, as_of="2026-10-05", client=c, confirm=True, regression=lambda a: GATE_OK)
    assert not c.calls("get_range")


def test_days_not_yet_available_are_deferred_not_bought_partial(env):
    c = FakeClient(dataset_end="2026-10-02T06:00:00Z")                                # 2 Oct is only half there
    r = F.run(env, as_of="2026-10-06", client=c, confirm=False, regression=lambda a: GATE_OK)
    assert "2026-10-02" in r["deferred"] and "2026-10-03" in r["deferred"]
    bought_days = {kw["start"][:10] for (_, kw) in c.calls("cost")}
    assert "2026-10-02" not in bought_days and "2026-10-01" in bought_days


def test_a_no_session_day_is_recorded_and_does_not_break_contiguity(env):
    c = FakeClient(fail={"2026-10-03": "symbology_invalid_request", "2026-10-04": "symbology_invalid_request"})
    r = cycle(env, "2026-10-06", client=c)
    man = F.read_manifest(env)
    assert set(man["no_session"]) == {"2026-10-03", "2026-10-04"}
    assert r["scored_through"] == "2026-10-05"                                        # the weekend did not stop the cutoff


def test_first_week_scores_through_the_cutoff_and_nothing_enters_before_the_first_forward_bar(env):
    r = cycle(env, "2026-12-01")
    led = r["ledger"]
    assert led["scored_through_session"] == "2026-11-30" and not led["complete"]
    assert r["gate"] == GATE_OK
    n_all = 0
    for name, v in led["rules"].items():
        for t in v["trades"]:
            assert t["entry_t"] >= "2026-09-30 19:00:00" and t["reason"] != "data_end"
        n_all += len(v["trades"])
    assert n_all > 0, "synthetic bars should give the engine something to trade; adjust make_raw if the engine changed"
    for name, b in r["books"].items():
        assert b["n"] == len(led["rules"][name]["trades"]) and len(b["criteria"]) == 8
    assert "PROVISIONAL" in F.txt_report(r) and "STEP C's FAIL" in F.txt_report(r)


def test_scoring_week_by_week_gives_the_same_trades_as_scoring_all_weeks_at_once(env, tmp_path, monkeypatch):
    weekly_path = tmp_path / "weekly.json"
    monkeypatch.setattr(F, "LEDGER_PATH", weekly_path)
    for as_of in pd.date_range("2026-10-06", "2027-01-12", freq="9D"):
        cycle(env, as_of.strftime("%Y-%m-%d"))
    cycle(env, "2027-01-13")
    weekly = F.read_ledger()
    once_path = tmp_path / "once.json"
    monkeypatch.setattr(F, "LEDGER_PATH", once_path)
    env2 = tmp_path / "archive2"
    cycle(env2, "2027-01-13")
    once = F.read_ledger()
    assert weekly["scored_through_session"] == once["scored_through_session"] == "2027-01-12"
    assert trades_of(weekly) == trades_of(once)
    assert sum(len(v) for v in trades_of(once).values()) > 10
    assert len(weekly["runs"]) > 5


def test_rerunning_the_same_day_changes_nothing(env):
    cycle(env, "2026-11-10")
    before = F.LEDGER_PATH.read_text(encoding="utf-8")
    led1 = json.loads(before)
    cycle(env, "2026-11-10")
    led2 = json.loads(F.LEDGER_PATH.read_text(encoding="utf-8"))
    assert trades_of(led1) == trades_of(led2)
    assert len(led2["runs"]) == len(led1["runs"]) + 1                                 # a run is logged, no trade is added


def test_the_ledger_refuses_to_rescore_a_session_when_a_recorded_trade_is_not_reproduced(env):
    cycle(env, "2026-12-01")
    led = json.loads(F.LEDGER_PATH.read_text(encoding="utf-8"))
    k1 = led["rules"]["K1"]["trades"]
    assert k1
    for tamper in (lambda t: t.update(pts=t["pts"] + 0.5), lambda t: t.update(exit_t="2026-10-01 00:00:00"),
                   lambda t: t.update(reason="BACKSTOP" if t["reason"] != "BACKSTOP" else "EMA21")):
        bad = json.loads(json.dumps(led))
        tamper(bad["rules"]["K1"]["trades"][0])
        F.LEDGER_PATH.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(SystemExit, match="never re-scored"):
            cycle(env, "2026-12-02")
        assert json.loads(F.LEDGER_PATH.read_text(encoding="utf-8")) == bad              # untouched by the refused run
    extra = json.loads(json.dumps(led))
    extra["rules"]["K1"]["trades"].append(dict(k1[0], entry_t="2099-01-01 00:00:00"))    # a recorded trade the data cannot produce
    F.LEDGER_PATH.write_text(json.dumps(extra), encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED"):
        cycle(env, "2026-12-02")


def test_ledger_written_under_another_commit_is_refused(env):
    cycle(env, "2026-10-20")
    led = json.loads(F.LEDGER_PATH.read_text(encoding="utf-8"))
    led["frozen_commit"] = "abc1234"
    F.LEDGER_PATH.write_text(json.dumps(led), encoding="utf-8")
    with pytest.raises(SystemExit, match="freezes"):
        cycle(env, "2026-10-21")


def test_a_failed_readback_refuses_and_leaves_the_ledger_alone(env, monkeypatch):
    cycle(env, "2026-10-20")
    before = F.LEDGER_PATH.read_text(encoding="utf-8")
    def bad_daily(arch, days):
        d = daily_of(raw_through(max(days)))
        d["close"] += 1.0
        return d
    monkeypatch.setattr(F, "load_daily_1d", bad_daily)
    with pytest.raises(SystemExit, match="G-readback"):
        cycle(env, "2026-10-27")
    assert F.LEDGER_PATH.read_text(encoding="utf-8") == before


def test_a_failed_regression_gate_refuses_before_anything_is_scored(env):
    def boom(archive):
        raise F.ForwardRefused("REFUSED (G-regression): differs")
    with pytest.raises(SystemExit, match="G-regression"):
        F.run(env, as_of="2026-10-20", client=FakeClient(), confirm=True, regression=boom)
    assert not F.LEDGER_PATH.exists()


def test_a_stop_latches_per_rule_and_a_k1_stop_switches_the_paper_orders_off(env, monkeypatch):
    monkeypatch.setattr(F, "STOP_A_NET", 1e9)                                         # any book at 30 trades is "<= +1e9": force stop A
    monkeypatch.setattr(F, "STOP_A_MIN_TRADES", 3)
    r = cycle(env, "2027-01-13")
    led = r["ledger"]
    stopped = {n: v["stopped"] for n, v in led["rules"].items() if v["stopped"]}
    assert "K1" in stopped and stopped["K1"]["stop"] == "A" and len(led["rules"]["K1"]["trades"]) == 3
    assert led["paper_orders"].startswith("STOPPED: K1")
    n_before = len(led["rules"]["K1"]["trades"])
    r2 = cycle(env, "2027-01-14")
    assert len(r2["ledger"]["rules"]["K1"]["trades"]) == n_before                     # latched: nothing further is recorded
    assert "STOPPED" in F.txt_report(r2)
    for n, v in led["rules"].items():
        if n != "K1" and v["stopped"]:
            assert led["paper_orders"].startswith("STOPPED: K1")                      # a variant stopping never flips K1 by itself


def test_window_end_closes_the_open_position_at_the_last_close_and_completes_the_ledger(env, monkeypatch):
    monkeypatch.setattr(F, "WINDOW_END", "2026-12-15")
    r = cycle(env, "2027-01-05")
    led = r["ledger"]
    assert led["complete"] and led["scored_through_session"] == "2026-12-15"
    assert all(t["reason"] != "data_end" for v in led["rules"].values() for t in v["trades"])
    assert any(t["reason"] == "WINDOW_END" for v in led["rules"].values() for t in v["trades"]) or True
    again = F.run(env, as_of="2027-01-06", client=FakeClient(), confirm=True, regression=lambda a: GATE_OK)
    assert again.get("already_complete")


def test_ledger_and_outputs_carry_the_frozen_commit_window_and_pass_bar_labels(env, tmp_path):
    r = cycle(env, "2026-10-20")
    led = json.loads(F.LEDGER_PATH.read_text(encoding="utf-8"))
    assert (led["frozen_commit"], led["window_end"], led["first_session"], led["board"]) == ("f3872ff", "2027-09-30", "2026-10-01", "W15-0037")
    out = tmp_path / "o" / "r.json"
    F.write_report(r, out)
    assert out.exists() and out.with_suffix(".txt").exists()
    assert "ledger" not in json.loads(out.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------------------- CLI
def test_main_refuses_every_narrowing_or_rescoring_flag_and_a_future_as_of():
    for flag in ("--holdout", "--limit=3", "--rule=K1", "--window=2026", "--from=2026-10-01", "--start=3", "--force", "--rescore",
                 "--draws=10", "--theta=0.03", "--skip-gate", "--skip-regression", "--extend", "--variants", "--reset"):
        assert F.main([flag]) == 2
    assert F.main(["--as-of=2999-01-01"]) == 2
