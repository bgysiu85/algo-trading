"""W15-0053 sub 4a: one test group per safety rail of REGISTERED_exit_cmp.md sec 14 (rails 1-14), all on the fake IB.
Rail 12 (stale data) is tested here at the tick level; the bar-level stale check is sub 4b."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from exitmgr import state as S
from exitmgr.gateway import RailRefused
from exitmgr.killswitch import FLATTEN, PAUSE, STOP
from tests.exitmgr.fake_ib import ACCOUNT, T0, FakeClock, FakeIB, build, details, fut

MCL = fut("MCL")
MNQ = fut("MNQ")
NY_1655 = datetime(2026, 11, 16, 21, 55, tzinfo=timezone.utc)       # Monday 16:55 New York (EST)


def open_long(h, qty=2, px=70.00, c=MCL, steps=2):
    h.ib.manual_fill(c, "BOT", qty, px)
    h.step(steps)
    return h.stop(c)


def open_short(h, qty=2, px=70.00, c=MCL, steps=2):
    h.ib.manual_fill(c, "SLD", qty, px)
    h.step(steps)
    return h.stop(c)


# ======================================================================= rail 1: reduce-only
class TestRail01ReduceOnly:
    def test_stop_is_opposite_the_position_long_and_short(self, tmp_path):
        h = build(tmp_path)
        assert open_long(h).order.action == "SELL"
        h2 = build(tmp_path / "b")
        assert open_short(h2).order.action == "BUY"

    def test_gateway_refuses_an_order_on_the_same_side_as_the_position(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        pos = h.pos(MCL)
        wrong = S.PosState(con_id=MCL.conId, local_symbol=pos.local_symbol, root="MCL", qty=-2, fill_id="X")
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.place_market_exit(h.mgr.contracts[MCL.conId], wrong, 1, kind="kill", reason="test")
        assert e.value.rail == "1"
        assert h.events("refused")[-1]["rail"] == "1"

    def test_gateway_refuses_any_order_when_flat_never_opens(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        h.ib.set_position(MCL, 0)                     # flat under the manager, before it notices
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.place_market_exit(h.mgr.contracts[MCL.conId], h.pos(MCL), 2, kind="kill", reason="test")
        assert e.value.rail == "1" and "never opens" in e.value.msg

    def test_exit_quantity_may_not_exceed_the_position(self, tmp_path):
        h = build(tmp_path)
        open_long(h, qty=2)
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.modify_stop(h.mgr.contracts[MCL.conId], h.pos(MCL), qty=3, reason="test")
        assert e.value.rail == "1"
        assert h.stop(MCL).order.totalQuantity == 2

    def test_other_clients_exit_orders_count_against_the_position(self, tmp_path):
        h = build(tmp_path)
        h.ib.set_position(MCL, 0)
        h.ib.add_foreign_order(MCL, "SELL", 1, aux=60.0, client_id=17)      # NAS trader order (ignored client)
        h.ib.manual_fill(MCL, "BOT", 2, 70.00)
        h.step(2)
        st = h.stop(MCL)
        assert st.order.totalQuantity == 1            # 2 - the other client's 1: never more than the position
        assert h.pos(MCL).pending_since is not None

    def test_stop_waits_for_a_fresh_broker_position(self, tmp_path):
        h = build(tmp_path)
        h.ib.position_lag = True
        h.ib.manual_fill(MCL, "BOT", 2, 70.00)
        h.step(3)
        assert h.ib.placed == []                       # broker still says 0: nothing can be reduce-only yet
        h.ib.flush_positions()
        h.step(1)
        assert h.stop(MCL).order.totalQuantity == 2


# ======================================================================= rail 2: one exit per position
class TestRail02OneExit:
    def test_order_ref_and_oca_group(self, tmp_path):
        h = build(tmp_path)
        f = h.ib.manual_fill(MCL, "BOT", 2, 70.00)
        h.step(2)
        o = h.stop(MCL).order
        eid = f.execution.execId
        assert o.orderRef == f"XM:MCLF7:{eid}" and o.ocaGroup == f"XMOCA:MCLF7:{eid}" and o.ocaType == 1
        assert o.tif == "GTC" and o.account == ACCOUNT

    def test_two_fills_in_a_row_never_two_stops(self, tmp_path):
        h = build(tmp_path)
        h.ib.manual_fill(MCL, "BOT", 1, 70.00)
        h.ib.manual_fill(MCL, "BOT", 1, 70.05)
        h.step(3)
        assert [p["verb"] for p in h.ib.placed] == ["place", "modify"]
        assert len(h.ib.own_working(MCL.conId)) == 1
        assert h.stop(MCL).order.totalQuantity == 2

    def test_gateway_refuses_a_second_stop(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.place_stop(h.mgr.contracts[MCL.conId], h.pos(MCL), 1, 69.0, reason="test")
        assert e.value.rail == "2"

    def test_market_exit_joins_the_stop_oca_group(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.mgr.gw.place_market_exit(h.mgr.contracts[MCL.conId], h.pos(MCL), 2, kind="kill", reason="test")
        mk = [t for t in h.ib.own_working(MCL.conId) if t.order.orderType == "MKT"][0]
        assert mk.order.ocaGroup == st.order.ocaGroup
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.place_market_exit(h.mgr.contracts[MCL.conId], h.pos(MCL), 2, kind="kill", reason="again")
        assert e.value.rail == "2"


# ======================================================================= rail 3: stop first, emergency level, latency
class TestRail03StopFirst:
    def test_first_order_is_the_emergency_stop_long(self, tmp_path):
        h = build(tmp_path)
        open_long(h, px=70.00)
        assert h.ib.placed[0]["type"] == "STP" and h.ib.placed[0]["aux"] == pytest.approx(69.40)

    def test_short_emergency_stop_is_above(self, tmp_path):
        h = build(tmp_path)
        open_short(h, px=70.00)
        assert h.ib.placed[0]["action"] == "BUY" and h.ib.placed[0]["aux"] == pytest.approx(70.60)

    def test_latency_logged_and_slow_stop_alerts(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        assert h.events("stop_latency")[0]["ms"] <= 1000
        assert not h.alerts("RAIL3")
        h2 = build(tmp_path / "b")
        h2.ib.position_lag = True
        h2.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h2.step(20)                                    # 4 s with the broker not showing the position
        h2.ib.flush_positions()
        h2.step(1)
        assert h2.events("stop_latency")[0]["ms"] > 3000
        assert h2.alerts("RAIL3") and h2.alerts("UNPROTECTED")

    def test_mnq_mode_a_without_atr_falls_back_to_fixed_mode_b(self, tmp_path):
        h = build(tmp_path)
        open_long(h, qty=1, px=20000.00, c=MNQ)
        assert h.ib.placed[0]["aux"] == pytest.approx(19750.00)
        assert h.alerts("EMERGENCY_FALLBACK")

    def test_mnq_mode_a_with_atr_from_4b(self, tmp_path):
        h = build(tmp_path, atr_provider=lambda cid, root: (40.0, 0.30))   # 0.60 / 0.30 x 40 = 80 points
        open_long(h, qty=1, px=20000.00, c=MNQ)
        assert h.ib.placed[0]["aux"] == pytest.approx(19920.00)
        assert not h.alerts("EMERGENCY_FALLBACK")


# ======================================================================= rail 4: never loosens
class TestRail04NeverLoosens:
    def test_long_tighten_up_ok_loosen_refused(self, tmp_path):
        h = build(tmp_path)
        open_long(h, px=70.00)
        h.ib.tick(MCL)
        assert h.mgr.tighten_stop(MCL.conId, 69.70, "test")
        assert h.stop(MCL).order.auxPrice == pytest.approx(69.70)
        assert not h.mgr.tighten_stop(MCL.conId, 69.50, "test")
        assert h.stop(MCL).order.auxPrice == pytest.approx(69.70)
        r = h.events("refused")[-1]
        assert r["rail"] == "4" and r["old"] == pytest.approx(69.70) and r["new"] == pytest.approx(69.50)

    def test_short_tighten_down_ok_loosen_refused(self, tmp_path):
        h = build(tmp_path)
        open_short(h, px=70.00)
        h.ib.tick(MCL)
        assert h.mgr.tighten_stop(MCL.conId, 70.30, "test")
        assert not h.mgr.tighten_stop(MCL.conId, 70.45, "test")
        assert h.stop(MCL).order.auxPrice == pytest.approx(70.30)
        assert h.events("refused")[-1]["rail"] == "4"


# ======================================================================= rail 5: other apps' exit orders
class TestRail05OtherApps:
    def test_existing_stop_from_another_app_means_observe_only(self, tmp_path):
        h = build(tmp_path)
        h.ib.add_foreign_order(MCL, "SELL", 2, aux=69.00, client_id=0)       # Ben's own stop from IBKR Mobile
        h.ib.manual_fill(MCL, "BOT", 2, 70.00)
        h.step(3)
        assert h.ib.placed == []
        assert h.pos(MCL).mode == S.OBSERVE_ONLY and h.alerts("RAIL5")
        h.ib.cancelOrder(h.ib.trades[0].order)                               # Ben cancels his own stop
        h.clock.advance(16)
        h.step(1)
        assert h.alerts("OBSERVE_UNPROTECTED") and h.ib.placed == []        # loud, but still places nothing

    def test_another_app_stop_appearing_later_cancels_ours(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.ib.add_foreign_order(MCL, "SELL", 2, aux=69.00, client_id=0)
        h.clock.advance(16)
        h.step(1)
        assert st.orderStatus.status == "Cancelled"
        assert h.pos(MCL).mode == S.OBSERVE_ONLY and h.alerts("RAIL5")

    def test_gateway_refuses_while_another_app_exit_is_working(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        h.ib.add_foreign_order(MCL, "SELL", 1, aux=69.00, client_id=0)
        with pytest.raises(RailRefused) as e:
            h.mgr.gw.modify_stop(h.mgr.contracts[MCL.conId], h.pos(MCL), price=69.8, reason="test")
        assert e.value.rail == "5"

    def test_nas_trader_orders_do_not_trigger_observe_only(self, tmp_path):
        h = build(tmp_path)
        h.ib.add_foreign_order(MCL, "BUY", 1, aux=75.00, client_id=17)       # trader entry order, not an exit
        assert open_long(h) is not None
        assert h.pos(MCL).mode == S.MANAGED


# ======================================================================= rail 6: partial fills, scale-ins, reconcile
class TestRail06PartialsAndReconcile:
    def test_stop_follows_cumulative_fills_up_and_down(self, tmp_path):
        h = build(tmp_path)
        open_long(h, qty=1)
        h.ib.manual_fill(MCL, "BOT", 2, 70.10)
        h.step(2)
        assert h.stop(MCL).order.totalQuantity == 3
        h.ib.manual_fill(MCL, "SLD", 2, 70.30)
        h.step(2)
        assert h.stop(MCL).order.totalQuantity == 1
        assert h.stop(MCL).order.auxPrice == pytest.approx(69.40)          # level from the first fill, unchanged

    def test_own_partial_stop_fill(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h, qty=3)
        h.ib.fill_order(st, qty=1, price=69.40)
        h.step(2)
        assert h.pos(MCL).qty == 2 and st.orderStatus.status == "Submitted"
        assert sum(1 for p in h.ib.placed if p["verb"] == "place") == 1
        h.ib.fill_order(st, price=69.40)
        h.step(2)
        assert h.pos(MCL) is None

    def test_reconcile_runs_at_least_every_30_s(self, tmp_path):
        h = build(tmp_path)
        n0 = len(h.events("reconcile"))
        h.step(300, dt=0.2)                            # 60 s
        assert len(h.events("reconcile")) - n0 >= 2
        assert h.cfg.reconcile_s <= 30

    def test_fill_whose_event_never_arrives_is_found_by_reconcile(self, tmp_path):
        h = build(tmp_path)
        h.ib.manual_fill(MCL, "BOT", 2, 70.00, deliver=False)
        h.step(1)
        h.clock.advance(15)
        h.step(2)
        assert h.stop(MCL).order.totalQuantity == 2
        assert any(e.get("via") == "reqExecutions" for e in h.events("fill_seen"))

    def test_reconnect_reconciles_and_never_duplicates_the_stop(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.ib.drop()
        h.step(2)
        assert not h.mgr.connected and h.alerts("DISCONNECTED")
        h.ib.manual_fill(MCL, "BOT", 1, 70.2, deliver=False)                  # scale-in while the manager was away
        h.ib.connect("127.0.0.1", 4002, clientId=31)
        h.mgr.on_reconnect()
        h.step(2)
        assert len(h.ib.own_working(MCL.conId)) == 1
        assert h.stop(MCL) is st and st.order.totalQuantity == 3


# ======================================================================= rail 7: unknown or unsafe contract
class TestRail07UnsafeContract:
    @pytest.mark.parametrize("root", ["CL", "ES", "NQ", "MES", "ZZZ"])
    def test_switched_off_or_unknown_symbol_places_nothing(self, tmp_path, root):
        h = build(tmp_path)
        c = fut(root)
        h.ib.manual_fill(c, "BOT", 1, 100.0)
        h.step(3)
        assert h.ib.placed == []
        assert h.pos(c).mode == S.UNSAFE and h.alerts("RAIL7")

    def test_near_expiry_contract_places_nothing(self, tmp_path):
        h = build(tmp_path)
        c = fut("MCL", local="MCLZ6", ltd="20261118", con_id=7101)            # Wed: 2 trading days after Mon 16 Nov
        h.ib.details[c.conId] = [details(c)]
        h.ib.manual_fill(c, "BOT", 1, 70.0)
        h.step(3)
        assert h.ib.placed == [] and "within 2 trading days" in h.alerts("RAIL7")[0]["msg"]

    def test_contract_details_differing_from_the_table_place_nothing(self, tmp_path):
        h = build(tmp_path)
        h.ib.details[MCL.conId] = [details(MCL, multiplier="1000")]
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(3)
        assert h.ib.placed == [] and "multiplier" in h.alerts("RAIL7")[0]["msg"]

    def test_non_futures_fill_is_ignored(self, tmp_path):
        from ib_async import Stock
        h = build(tmp_path)
        s = Stock("AAPL", "SMART", "USD")
        s.conId = 265598
        h.ib.manual_fill(s, "BOT", 10, 200.0, move_position=False)
        h.step(2)
        assert h.ib.placed == [] and "not a futures fill" in h.events("fill_seen")[-1]["action"]


# ======================================================================= rail 8: size cap
class TestRail08OverCap:
    def test_over_cap_still_protected_alerted_not_flattened(self, tmp_path):
        h = build(tmp_path, start=NY_1655 - timedelta(minutes=1))
        open_long(h, qty=3, px=20000.0, c=MNQ)                                # MNQ cap 2
        assert h.stop(MNQ).order.totalQuantity == 3
        assert h.alerts("RAIL8") and h.pos(MNQ).over_cap
        h.run_until(NY_1655 + timedelta(seconds=10))
        assert not any(p["type"] == "MKT" for p in h.ib.placed)
        assert h.alerts("RAIL8_NO_FLAT") and h.stop(MNQ) is not None

    def test_caps_are_config(self, tmp_path):
        h = build(tmp_path, XM_CAPS="MCL:1")
        open_long(h, qty=2)
        assert h.alerts("RAIL8")
        h2 = build(tmp_path / "b", XM_CAPS="MCL:8")
        h2.ib.manual_fill(MNQ, "BOT", 1, 20000.0)
        h2.step(2)
        assert h2.ib.placed == [] and h2.alerts("RAIL7")                     # MNQ switched off by config


# ======================================================================= rail 9: kill switches + runaway guard
class TestRail09KillSwitches:
    def test_pause_stops_rule_actions_and_leaves_the_stop(self, tmp_path):
        h = build(tmp_path, start=NY_1655 - timedelta(minutes=1))
        st = open_long(h)
        h.ib.tick(MCL)
        h.kill.pause("Ben")
        assert not h.mgr.tighten_stop(MCL.conId, 69.8, "test")
        h.run_until(NY_1655 + timedelta(seconds=5))
        assert st.orderStatus.status == "Submitted" and st.order.auxPrice == pytest.approx(69.40)
        assert not any(p["type"] == "MKT" for p in h.ib.placed)
        assert h.alerts("PAUSED_NO_FLAT")

    def test_pause_never_leaves_a_new_fill_unprotected(self, tmp_path):
        h = build(tmp_path)
        h.kill.pause("Ben")
        assert open_long(h) is not None

    def test_flatten_exits_then_cancels_stop_then_pauses(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        (h.kill.dir / FLATTEN).write_text("", encoding="utf-8")
        h.step(2)
        mk = [t for t in h.ib.trades if t.order.orderType == "MKT"][0]
        assert mk.order.ocaGroup == st.order.ocaGroup and mk.order.totalQuantity == 2
        kinds = [(e["kind"], e.get("otype")) for e in h.events()]
        assert kinds.index(("order_sent", "MKT")) < kinds.index(("order_cancel_sent", "STP"))     # exit first, then cancel
        assert st.orderStatus.status == "Cancelled"
        assert (h.kill.dir / PAUSE).exists() and not (h.kill.dir / FLATTEN).exists()
        assert list(h.kill.dir.glob("FLATTEN.done-*"))
        h.ib.fill_order(mk, price=70.1)
        h.step(2)
        assert h.pos(MCL) is None

    def test_stop_manager_flag_exits_and_leaves_the_stop(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        (h.kill.dir / STOP).write_text("", encoding="utf-8")
        assert h.step(1) is False
        assert st.orderStatus.status == "Submitted"
        assert h.events("stop")[-1]["note"].startswith("resting stops left")

    def test_runaway_guard_latches_after_20_in_a_minute(self, tmp_path):
        h = build(tmp_path, XM_CAPS="MCL:100")
        open_long(h, qty=1)
        for _ in range(25):
            h.ib.manual_fill(MCL, "BOT", 1, 70.0)
            h.step(1)
        sent = [p for p in h.ib.placed]
        assert len(sent) == 20
        assert h.alerts("RAIL9D") and (h.kill.dir / PAUSE).exists()
        h.clock.advance(120)
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(2)
        assert len(h.ib.placed) == 20                                        # latched until restart
        assert h.alerts("UNPROTECTED")                                       # 27 held, stop stuck at 20: said loudly
        h.ib.manual_fill(MCL, "SLD", 27, 70.0)                              # flat by hand: the cancel still goes out
        h.step(2)
        assert h.stop(MCL) is None and h.pos(MCL) is None and h.ib.cancelled


# ======================================================================= rail 10: paper lock (more in test_run_manager.py)
class TestRail10PaperLock:
    def test_dry_mode_sends_nothing_but_logs_every_order(self, tmp_path):
        h = build(tmp_path, mode="dry")
        h.ib.manual_fill(MCL, "BOT", 2, 70.0)
        h.step(2)
        h.ib.manual_fill(MCL, "BOT", 1, 70.1)
        h.step(2)
        h.ib.manual_fill(MCL, "SLD", 3, 70.2)
        h.step(2)
        assert h.ib.placed == [] and h.ib.cancelled == []
        would = h.events("order_would_send")
        assert [w["verb"] for w in would] == ["place", "modify"] and would[0]["price"] == pytest.approx(69.40)
        assert h.events("order_would_cancel")

    def test_live_account_refused(self, tmp_path):
        from exitmgr import config as C
        cfg = C.load({"XM_MODE": "paper", "XM_ACCOUNT": ACCOUNT, "XM_OUT_DIR": str(tmp_path)})
        with pytest.raises(C.Refused):
            C.check_accounts(cfg, ["U7654321"])
        with pytest.raises(C.Refused):
            C.check_accounts(cfg, ["DU9999999"])


# ======================================================================= rail 11: flat position cancels the stop
class TestRail11FlatCancels:
    def test_manual_flatten_cancels_at_once(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.ib.manual_fill(MCL, "SLD", 2, 70.5)
        h.step(1)
        assert st.orderStatus.status == "Cancelled" and h.pos(MCL) is None

    def test_flat_seen_only_in_positions_is_caught_by_reconcile(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.ib.manual_fill(MCL, "SLD", 2, 70.5, deliver=False)
        h.ib.fills.pop()                                                     # and not even in reqExecutions
        h.step(10)                                                           # position event -> recheck within 1 s
        assert st.orderStatus.status == "Cancelled" and h.alerts("FLAT_UNSEEN")

    def test_reversal_cancels_old_stop_and_protects_the_new_side(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h, qty=2, px=70.0)
        h.ib.manual_fill(MCL, "SLD", 3, 70.2)
        h.step(2)
        assert st.orderStatus.status == "Cancelled"
        new = h.stop(MCL)
        assert new.order.action == "BUY" and new.order.totalQuantity == 1 and new.order.auxPrice == pytest.approx(70.80)

    def test_stop_never_exceeds_a_shrinking_position(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h, qty=3)
        h.ib.set_position(MCL, 1)                                            # shrank with no fill the manager saw
        h.step(10)
        assert st.order.totalQuantity == 1
        assert h.pos(MCL).mode == S.MANAGED or h.pos(MCL).mode == S.ALERT_ONLY


# ======================================================================= rail 12: stale data
class TestRail12StaleData:
    def test_no_tick_for_30s_alerts_and_blocks_rule_actions_stop_stays(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.ib.tick(MCL)
        h.step(160)                                                          # 32 s without a tick
        assert h.alerts("RAIL12")
        assert h.mgr.rule_actions_allowed(MCL.conId) == (False, "stale market data (rail 12)")
        assert not h.mgr.tighten_stop(MCL.conId, 69.8, "test")
        assert st.orderStatus.status == "Submitted"
        h.ib.tick(MCL)
        h.step(1)
        assert h.mgr.rule_actions_allowed(MCL.conId)[0] and h.events("data_resumed")


# ======================================================================= rail 13: maintenance, weekends, restarts
class TestRail13MaintenanceAndRestart:
    def test_no_rule_action_in_the_maintenance_hour(self, tmp_path):
        h = build(tmp_path, start=datetime(2026, 11, 16, 22, 10, tzinfo=timezone.utc), XM_FLAT_MODE="HOLD")   # 17:10 NY
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(2)
        st = h.stop(MCL)
        assert st is not None                                                # protection still placed
        ok, why = h.mgr.rule_actions_allowed(MCL.conId)
        assert not ok and "rail 13" in why
        assert not h.mgr.tighten_stop(MCL.conId, 69.8, "test") and h.events("rule_action_skipped")

    def test_no_rule_action_at_the_weekend(self, tmp_path):
        h = build(tmp_path, start=datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc))      # Saturday
        h.mgr.st.positions[str(MCL.conId)] = S.PosState(con_id=MCL.conId, local_symbol="MCLF7", root="MCL", qty=1,
                                                        mode=S.MANAGED, fill_id="x")
        assert h.mgr.rule_actions_allowed(MCL.conId)[1] == "maintenance hour or weekend (rail 13)"

    def test_restart_resumes_from_state_and_adopts_its_own_stop(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h)
        h.mgr.stop("test restart")
        h2 = build(tmp_path, ib=h.ib, clock=h.clock)
        h2.step(2)
        assert h2.pos(MCL).mode == S.MANAGED
        assert len(h2.ib.own_working(MCL.conId)) == 1 and h2.stop(MCL) is st
        assert h2.events("order_adopted")
        h2.ib.manual_fill(MCL, "BOT", 1, 70.1)
        h2.step(2)
        assert st.order.totalQuantity == 3 and sum(p["verb"] == "place" for p in h2.ib.placed) == 1

    def test_position_held_before_start_is_alert_only(self, tmp_path):
        clock = FakeClock(T0)
        ib = FakeIB(clock)
        ib.set_position(MCL, 2)
        h = build(tmp_path, ib=ib, clock=clock)
        assert h.pos(MCL).mode == S.ALERT_ONLY and h.alerts("ALERT_ONLY")
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(3)
        assert h.ib.placed == []

    def test_nas_trader_fill_on_a_managed_symbol_makes_it_alert_only(self, tmp_path):
        h = build(tmp_path)
        st = open_long(h, qty=2)
        h.ib.manual_fill(MCL, "BOT", 1, 70.3, client_id=17)
        h.step(40)                                                           # past the 5 s grace
        assert h.pos(MCL).mode == S.ALERT_ONLY and h.alerts("ALERT_ONLY")
        assert st.orderStatus.status == "Submitted" and st.order.totalQuantity == 2      # resting stop stays
        h.ib.manual_fill(MCL, "BOT", 1, 70.4)                               # Ben adds: no new orders now
        h.step(5)
        assert st.order.totalQuantity == 2 and len(h.ib.placed) == 1

    def test_corrupt_state_file_starts_fresh_with_alert(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        (out / "state.json").write_text("{not json", encoding="utf-8")
        h = build(tmp_path)
        assert h.alerts("STATE") and list(out.glob("state.json.corrupt-*"))


# ======================================================================= rail 14: append-only log of everything
class TestRail14Log:
    def test_log_has_version_fills_orders_reasons_latency(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        h.mgr.tighten_stop(MCL.conId, 60.0, "loosen-test")
        start = h.events("start")[0]
        assert len(start["code_hash"]) == 16 and len(start["config_hash"]) == 16 and start["config"]["mode"] == "paper"
        assert h.events("fill_seen")[0]["price"] == 70.0
        sent = h.events("order_sent")[0]
        assert sent["reason"] == "emergency stop" and sent["price"] == pytest.approx(69.4) and sent["broker_qty"] == 2
        assert h.events("stop_latency") and h.events("refused")

    def test_log_is_append_only_across_restarts(self, tmp_path):
        h = build(tmp_path)
        open_long(h)
        path = h.cfg.out_dir / "events.jsonl"
        before = path.read_bytes()
        h.mgr.stop("restart")
        h2 = build(tmp_path, ib=h.ib, clock=h.clock)
        h2.step(2)
        after = path.read_bytes()
        assert after.startswith(before) and len(after) > len(before)
