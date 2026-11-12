"""Config (rail 10 paper lock, dry default, caps), state file, event log, kill switch and runaway guard units."""
from __future__ import annotations

from datetime import timedelta

import pytest

from exitmgr import config as C
from exitmgr import state as S
from exitmgr.eventlog import EventLog, code_hash, read_events
from exitmgr.killswitch import KillSwitch, RunawayGuard
from exitmgr.timeutil import globex_open, in_maintenance, trading_days_until
from tests.exitmgr.fake_ib import T0, FakeClock


def env(tmp_path, **kw):
    e = {"XM_OUT_DIR": str(tmp_path / "o")}
    e.update(kw)
    return e


class TestConfig:
    def test_default_is_dry(self, tmp_path):
        cfg = C.load(env(tmp_path))
        assert cfg.mode == "dry" and cfg.client_id == 31 and cfg.flat_mode == "FLAT" and cfg.flat_hhmm == (16, 55)
        assert cfg.caps == {"MCL": 8, "MNQ": 2}
        assert [cfg.cap(r) for r in ("CL", "ES", "MES", "NQ")] == [0, 0, 0, 0]
        assert cfg.ignore_client_ids == (17,) and cfg.emergency_mode == "A"

    @pytest.mark.parametrize("mode", ["live", "LIVE", "real", "prod"])
    def test_no_live_mode(self, tmp_path, mode):
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_MODE=mode))

    def test_paper_needs_a_du_account(self, tmp_path):
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_MODE="paper"))
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_MODE="paper", XM_ACCOUNT="U1234567"))
        assert C.load(env(tmp_path, XM_MODE="paper", XM_ACCOUNT="du1234567")).account == "DU1234567"

    @pytest.mark.parametrize("port", sorted(C.LIVE_PORTS) + [5000, 7499])
    def test_live_and_unknown_ports_refused(self, tmp_path, port):
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_PORT=str(port)))

    def test_client_id_must_be_31(self, tmp_path):
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_CLIENT_ID="17"))

    def test_out_dir_never_in_var(self, tmp_path):
        with pytest.raises(C.Refused):
            C.load(env(tmp_path, XM_OUT_DIR=str(tmp_path / "var" / "xm")))
        with pytest.raises(C.Refused):
            C.load({"XM_OUT_DIR": str(tmp_path / "tv" / "x"), "TRADER_VAR_DIR": str(tmp_path / "tv")})

    def test_bad_values_refused(self, tmp_path):
        for kw in ({"XM_CAPS": "XYZ:2"}, {"XM_CAPS": "MCL:-1"}, {"XM_CAPS": "MCL"}, {"XM_FLAT_MODE": "MAYBE"},
                   {"XM_FLAT_TIME": "17:30"}, {"XM_RECONCILE_S": "45"}, {"XM_EMERGENCY_MODE": "D"},
                   {"XM_IGNORE_CLIENT_IDS": "17 31"}):
            with pytest.raises(C.Refused):
                C.load(env(tmp_path, **kw))

    def test_paper_lock_accounts(self, tmp_path):
        cfg = C.load(env(tmp_path, XM_MODE="paper", XM_ACCOUNT="DU1"))
        assert C.check_accounts(cfg, ["DU1"]) == "DU1"
        for accs in (["U1"], ["DU1", "U2"], ["DU2"], []):
            with pytest.raises(C.Refused):
                C.check_accounts(cfg, accs)
        dry = C.load(env(tmp_path))
        assert C.check_accounts(dry, ["DU5"]) == "DU5"
        with pytest.raises(C.Refused):
            C.check_accounts(dry, ["U5"])

    def test_config_hash_changes_with_settings(self, tmp_path):
        assert C.load(env(tmp_path)).hash() != C.load(env(tmp_path, XM_CAPS="MCL:1")).hash()


class TestTime:
    def test_sessions(self):
        from datetime import datetime, timezone
        u = lambda *a: datetime(*a, tzinfo=timezone.utc)
        assert globex_open(u(2026, 11, 16, 15, 0))              # Mon 10:00 NY
        assert not globex_open(u(2026, 11, 16, 22, 30))         # Mon 17:30 NY maintenance
        assert in_maintenance(u(2026, 11, 16, 22, 30))
        assert not globex_open(u(2026, 11, 21, 15, 0))          # Saturday
        assert not globex_open(u(2026, 11, 22, 22, 0))          # Sun 17:00 NY
        assert globex_open(u(2026, 11, 22, 23, 30))             # Sun 18:30 NY
        assert not globex_open(u(2026, 11, 20, 22, 30))         # Fri 17:30 NY

    def test_trading_days(self):
        from datetime import date
        assert trading_days_until(date(2026, 11, 16), date(2026, 11, 18)) == 2
        assert trading_days_until(date(2026, 11, 20), date(2026, 11, 23)) == 1   # Fri -> Mon
        assert trading_days_until(date(2026, 11, 20), date(2026, 11, 19)) == 0


class TestStateAndLog:
    def test_atomic_round_trip(self, tmp_path):
        st = S.ManagerState()
        st.positions["1"] = S.PosState(con_id=1, local_symbol="MCLF7", root="MCL", qty=-2, mode=S.MANAGED, stop_px=70.6,
                                       alerts=["RAIL8"])
        p = tmp_path / "s" / "state.json"
        S.save_atomic(p, st.to_dict())
        back = S.load(p)
        assert back.positions["1"] == st.positions["1"] and not list(p.parent.glob("*.tmp*"))

    def test_unreadable_state_raises(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("[1, 2", encoding="utf-8")
        with pytest.raises(S.StateError):
            S.load(p)
        assert S.load(tmp_path / "none.json") is None

    def test_event_log_appends_and_has_no_rewrite(self, tmp_path):
        clock = FakeClock(T0)
        p = tmp_path / "e.jsonl"
        EventLog(p, clock.now).write("a", x=1)
        EventLog(p, clock.now).write("b", x=2)
        assert [e["kind"] for e in read_events(p)] == ["a", "b"]
        assert not any(hasattr(EventLog, m) for m in ("truncate", "rewrite", "clear", "reset"))
        assert len(code_hash()) == 16


class TestKillSwitch:
    def test_files(self, tmp_path):
        k = KillSwitch(tmp_path / "c", FakeClock(T0).now)
        assert not k.paused() and not k.flatten_requested() and not k.stop_requested()
        k.pause("why")
        assert k.paused() and "why" in (tmp_path / "c" / "PAUSE").read_text(encoding="utf-8")
        (tmp_path / "c" / "FLATTEN").write_text("", encoding="utf-8")
        assert k.flatten_requested()
        k.consume_flatten()
        assert not k.flatten_requested() and list((tmp_path / "c").glob("FLATTEN.done-*"))

    def test_runaway_per_minute_latches(self):
        clock = FakeClock(T0)
        trips = []
        g = RunawayGuard(20, 200, clock.now, on_trip=trips.append)
        assert all(g.check_and_record() for _ in range(20))
        assert not g.check_and_record() and trips
        clock.advance(3600)
        assert not g.check_and_record()                       # latched until restart

    def test_runaway_per_day(self):
        clock = FakeClock(T0)
        g = RunawayGuard(20, 200, clock.now)
        for _ in range(200):
            assert g.check_and_record()
            clock.advance(4)
        assert not g.check_and_record() and "today" in g.tripped

    def test_day_count_resumes_from_state(self):
        clock = FakeClock(T0)
        g = RunawayGuard(20, 200, clock.now, day="2026-11-16", day_count=200)
        assert not g.check_and_record()
        g2 = RunawayGuard(20, 200, clock.now, day="2026-11-15", day_count=200)      # yesterday's count resets
        assert g2.check_and_record()
