"""W15-0053 sub 4a: the 16:55 flat (REGISTERED sec 15) and the remaining plan section 5 flows on the fake IB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from exitmgr import state as S
from tests.exitmgr.fake_ib import build, fut

MCL = fut("MCL")
NY_1655 = datetime(2026, 11, 16, 21, 55, tzinfo=timezone.utc)       # Monday 16:55 New York (EST)


def opened(tmp_path, start, qty=2, px=70.0, side="BOT", **kw):
    h = build(tmp_path, start=start, **kw)
    h.ib.manual_fill(MCL, side, qty, px)
    h.step(2)
    return h, h.stop(MCL)


class TestFlat1655:
    def test_exit_working_before_the_stop_is_cancelled(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=30))
        h.ib.ack_status = "PendingSubmit"                    # the exit order is not acknowledged at once
        h.run_until(NY_1655 + timedelta(seconds=1))
        mk = [t for t in h.ib.trades if t.order.orderType == "MKT"]
        assert len(mk) == 1 and mk[0].order.action == "SELL" and mk[0].order.totalQuantity == 2
        assert mk[0].order.ocaGroup == st.order.ocaGroup
        assert st.orderStatus.status == "Submitted"         # stop still resting while the exit is not working
        mk[0].orderStatus.status = "Submitted"              # IBKR acknowledges the exit
        h.step(1)
        assert st.orderStatus.status == "Cancelled"
        h.ib.fill_order(mk[0], price=70.2)
        h.step(2)
        assert h.pos(MCL) is None

    def test_not_before_1655(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(minutes=2))
        h.run_until(NY_1655 - timedelta(seconds=1))
        assert not any(p["type"] == "MKT" for p in h.ib.placed)

    def test_short_flat_buys(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=5), side="SLD")
        h.run_until(NY_1655 + timedelta(seconds=1))
        mk = [t for t in h.ib.trades if t.order.orderType == "MKT"][0]
        assert mk.order.action == "BUY" and st.orderStatus.status == "Cancelled"

    def test_hold_mode_does_not_flatten(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=5), XM_FLAT_MODE="HOLD")
        h.run_until(NY_1655 + timedelta(seconds=10))
        assert not any(p["type"] == "MKT" for p in h.ib.placed) and st.orderStatus.status == "Submitted"

    def test_rejected_exit_leaves_the_stop(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=5))
        h.ib.ack_status = "PendingSubmit"
        h.run_until(NY_1655 + timedelta(seconds=1))
        mk = [t for t in h.ib.trades if t.order.orderType == "MKT"][0]
        mk.orderStatus.status = "Inactive"
        h.step(2)
        assert st.orderStatus.status == "Submitted" and h.alerts("EXIT_REJECTED")

    def test_unfilled_at_1700_alerts(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=5))
        h.ib.ack_status = "PendingSubmit"
        h.run_until(NY_1655 + timedelta(minutes=5, seconds=1))
        assert h.alerts("FLAT_NOT_DONE")

    def test_dry_mode_logs_the_flat_and_sends_nothing(self, tmp_path):
        h, st = opened(tmp_path, NY_1655 - timedelta(seconds=5), mode="dry")
        h.run_until(NY_1655 + timedelta(seconds=2))
        assert h.ib.placed == []
        assert [(e["verb"], e["otype"]) for e in h.events("order_would_send")] == [("place", "STP"), ("place", "MKT")]
        assert h.events("order_would_cancel")


class TestPlanSection5:
    def test_two_fills_in_a_row_never_two_stops_even_with_lagging_positions(self, tmp_path):
        h = build(tmp_path)
        h.ib.position_lag = True
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.ib.manual_fill(MCL, "BOT", 2, 70.1)
        h.step(2)
        h.ib.flush_positions()
        h.step(3)
        assert len(h.ib.own_working(MCL.conId)) == 1 and h.stop(MCL).order.totalQuantity == 3

    def test_kill_switch_pause_then_resume(self, tmp_path):
        h = build(tmp_path)
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(2)
        h.ib.tick(MCL)
        h.kill.pause("Ben")
        assert not h.mgr.tighten_stop(MCL.conId, 69.8, "x")
        (h.kill.dir / "PAUSE").unlink()
        assert h.mgr.tighten_stop(MCL.conId, 69.8, "x")

    def test_position_change_under_the_manager_without_fills_is_alert_only(self, tmp_path):
        h = build(tmp_path)
        h.ib.manual_fill(MCL, "BOT", 2, 70.0)
        h.step(2)
        h.ib.set_position(MCL, 5)
        h.step(40)
        assert h.pos(MCL).mode == S.ALERT_ONLY and h.stop(MCL).order.totalQuantity == 2

    def test_brief_mismatch_inside_the_grace_period_is_not_alert_only(self, tmp_path):
        h = build(tmp_path)
        h.ib.manual_fill(MCL, "BOT", 2, 70.0)
        h.step(2)
        h.ib.manual_fill(MCL, "BOT", 1, 70.0, deliver=False)          # event late ...
        h.ib.fills.pop()
        h.step(10)                                                    # 2 s: mismatch seen, inside 5 s grace
        late = h.ib._exec_obj(MCL, "BOT", 1, 70.0, 0)
        h.ib.fills.append(late)
        h.ib.execDetailsEvent.emit(None, late)                         # ... arrives
        h.step(40)
        assert h.pos(MCL).mode == S.MANAGED and not h.alerts("ALERT_ONLY")
        assert h.stop(MCL).order.totalQuantity == 3

    def test_broker_errors_never_crash_the_loop(self, tmp_path):
        h = build(tmp_path)
        h.ib.broken.add("reqPositions")
        h.ib.manual_fill(MCL, "BOT", 1, 70.0)
        h.step(5)
        assert h.ib.placed == [] and h.events("broker_error")
        h.ib.broken.clear()
        h.step(2)
        assert h.stop(MCL) is not None
