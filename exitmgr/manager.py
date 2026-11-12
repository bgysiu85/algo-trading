#!/usr/bin/env python3
"""The live exit manager's event loop (W15-0053 sub 4a). It never sends an order itself: every send goes through
exitmgr.gateway, which checks rails 1, 2, 4, 5 and the kill switches. Rule set: B-STOP-plus (protective stop + flat 16:55 NY).
Bar data, the structural stop S and the shadow exits of the other rule sets are sub 4b; 4b calls `tighten_stop()`.

What happens (REGISTERED_exit_cmp.md sec 14, plan sec 4):
  fill (execDetailsEvent, or found by reqExecutions at every reconcile, so a fill whose event never reached client 31 is
  still seen within one reconcile period)
    * NAS trader (client 17, XM_IGNORE_CLIENT_IDS): ignored; the broker position then differs from the tracked fills and
      reconcile makes that symbol ALERT-ONLY (decision 2026-11-12).
    * own fill (client 31): the tracked quantity follows; at 0 the position is closed and its orders cancelled.
    * any other app (IBKR Mobile / web): opens, adds to, reduces or reverses the tracked position.
  new position -> rail 7 (symbol in the table and switched on, contract details equal the table, not within 2 trading days
  of the last trade date) -> rail 5 (another app's exit order already on it: OBSERVE-ONLY, place nothing) -> rail 3
  emergency stop placed FIRST (CL / MCL fill -/+ $0.60; other symbols mode A needs the 1H ATR from 4b, until then the fixed
  fallback mode B / C), latency fill -> stop logged, over 3 s alerts -> rail 8 over-cap alert (still protected).
  scale-in / partial reduction -> the stop quantity follows the tracked quantity, never above the fresh broker position (rail 6).
  position 0 (any cause, including a flatten by hand in an app) -> cancel the manager's orders at once (rail 11).
  reconcile at least every XM_RECONCILE_S (<= 30 s), on every position event and on reconnect (rails 6, 13): fresh executions,
  open orders and positions. A broker position the tracked fills do not explain (for longer than the grace period, or at
  start) -> ALERT-ONLY for that contract: no new orders; the resting stop stays, trimmed so it can never exceed the position.
  16:55 NY (flat_mode FLAT) -> market exit in the stop's OCA group; only once it is working is the stop cancelled (never
  unprotected). No rule action 17:00-18:00 NY or at the weekend (rail 13). Over-cap positions are not flattened (rail 8).
  stale data: no tick for 30 s in session -> alert; no rule action on that contract; the server stop stays (rail 12).
"""
from __future__ import annotations

from collections import deque
from datetime import timedelta
from pathlib import Path

from exitmgr import symbols
from exitmgr import state as S
from exitmgr.eventlog import code_hash
from exitmgr.gateway import ACKED, DONE, KILL, PROTECT, RULE, Gateway, RailRefused, exit_side, round_tick
from exitmgr.killswitch import RunawayGuard
from exitmgr.timeutil import globex_open, iso, ny, parse_iso, parse_ltd, trading_days_until, utcnow

CATCH_UP_MARGIN = timedelta(minutes=5)    # on a resume, unseen executions newer than (state saved - this) are processed
POSITION_RECHECK = timedelta(seconds=1)


def _side(fill) -> int:
    return 1 if str(fill.execution.side).upper() in ("BOT", "BUY") else -1


class Manager:
    def __init__(self, ib, cfg, account: str, log, kill, clock=utcnow, atr_provider=None, state_path=None, guard=None):
        self.ib, self.cfg, self.account, self.log, self.kill, self.clock = ib, cfg, account, log, kill, clock
        self.atr_provider = atr_provider          # 4b: callable(con_id, root) -> (atr_1h, median_cl_atr) or None
        self.state_path = Path(state_path or (cfg.out_dir / "state.json"))
        st = None
        try:
            st = S.load(self.state_path)
        except S.StateError as e:
            bad = self.state_path.with_name(f"{self.state_path.name}.corrupt-{clock().strftime('%Y%m%dT%H%M%S')}")
            self.state_path.replace(bad)
            log.alert("STATE", f"{e}; moved to {bad.name}; starting fresh (every open position will be ALERT-ONLY)")
        self.fresh = st is None
        self.st = st or S.ManagerState()
        self.guard = guard or RunawayGuard(cfg.runaway_per_min, cfg.runaway_per_day, clock, on_trip=self._on_runaway,
                                           day=self.st.runaway_day, day_count=self.st.runaway_day_count)
        self.gw = Gateway(ib, cfg, log, kill, self.guard, account)
        self.q: deque = deque()
        self.contracts: dict = {}                 # conId -> qualified contract used for orders
        self.checks: dict = {}                    # conId -> (NY date, ok, why, contract)
        self.last_tick: dict = {}
        self.connected = True
        self.next_reconcile = None
        self.recheck_at = None
        self._seen = deque(self.st.seen_exec, maxlen=S.SEEN_MAX)
        self._seen_set = set(self._seen)
        self._catch_up_from = None if self.fresh else (parse_iso(self.st.saved_at) or clock()) - CATCH_UP_MARGIN
        self._last_saved = None
        self._stopped = False
        ib.execDetailsEvent += self._on_exec
        ib.positionEvent += self._on_position
        ib.disconnectedEvent += self._on_disconnect
        ib.pendingTickersEvent += self._on_tickers
        ib.errorEvent += self._on_error

    # ================================================================ events (only enqueue; work happens in step())
    def _on_exec(self, trade, fill):
        self.q.append(("fill", fill, self.clock()))

    def _on_position(self, position):
        self.q.append(("position", position, self.clock()))

    def _on_disconnect(self):
        self.q.append(("disconnect", None, self.clock()))

    def _on_tickers(self, tickers):
        now = self.clock()
        for t in tickers:
            self.last_tick[int(t.contract.conId)] = now

    def _on_error(self, *args):
        self.log.write("ib_error", args=[str(a) for a in args[:3]])

    def _on_runaway(self, why: str):
        self.kill.pause(f"runaway guard: {why}")
        self.log.alert("RAIL9D", f"runaway guard: {why}. Paused and latched; no order is sent until the manager is restarted. "
                                 f"Resting stops stay.")

    # ================================================================ helpers
    def _pos(self, con_id) -> S.PosState | None:
        return self.st.positions.get(str(int(con_id)))

    def _alert(self, pos: S.PosState | None, code: str, msg: str, **kw):
        if pos is not None:
            if code in pos.alerts:
                return
            pos.alerts.append(code)
            kw = dict(con_id=pos.con_id, local_symbol=pos.local_symbol, **kw)
        self.log.alert(code, msg, **kw)

    def _try(self, fn, *a, **kw):
        """Run a gateway call. A rail refusal (already logged by the gateway) or a broker error returns None."""
        try:
            return fn(*a, **kw)
        except RailRefused:
            return None
        except Exception as e:                    # noqa: BLE001 - broker / connection errors vary; never crash the loop
            self.log.write("broker_error", call=getattr(fn, "__name__", str(fn)), error=f"{type(e).__name__}: {e}")
            return None

    def _mark_seen(self, eid: str):
        if eid not in self._seen_set:
            if len(self._seen) == self._seen.maxlen:
                self._seen_set.discard(self._seen[0])
            self._seen.append(eid)
            self._seen_set.add(eid)

    def _exit_action(self, pos) -> str:
        return "SELL" if pos.qty > 0 else "BUY"

    def _oca(self, pos) -> str:
        return f"XMOCA:{pos.local_symbol}:{pos.fill_id}"

    def save(self):
        self.st.seen_exec = list(self._seen)
        self.st.runaway_day, self.st.runaway_day_count = self.guard.day, self.guard.day_count
        body = self.st.to_dict()
        body.pop("saved_at", None)
        if body == self._last_saved:
            return
        self.st.saved_at = iso(self.clock())
        S.save_atomic(self.state_path, self.st.to_dict())
        self._last_saved = body

    # ================================================================ lifecycle
    def start(self):
        self.log.write("start", code_hash=code_hash(), config_hash=self.cfg.hash(), config=self.cfg.as_dict(),
                       account=self.account, mode=self.cfg.mode, fresh=self.fresh, positions_in_state=len(self.st.positions))
        if self.fresh:
            fills = self._try(self.ib.reqExecutions) or []
            for f in fills:
                self._mark_seen(f.execution.execId)
            self.log.write("exec_baseline", count=len(fills), note="executions before this start are not managed")
        self.reconcile("start", startup=True)
        self.save()

    def on_disconnect(self):
        if self.connected:
            self.connected = False
            self.log.alert("DISCONNECTED", "Gateway connection lost. Resting stops stay at IBKR. Reconnecting.")

    def on_reconnect(self):
        self.q = deque(x for x in self.q if x[0] != "disconnect")
        self.connected = True
        self.log.write("reconnected")
        self.reconcile("reconnect", startup=False)
        self.save()

    def stop(self, why: str):
        if not self._stopped:
            self._stopped = True
            self.log.write("stop", reason=why, note="resting stops left in place at IBKR",
                           managed=[p.local_symbol for p in self.st.positions.values() if p.mode == S.MANAGED])
            self.save()

    def step(self) -> bool:
        """One loop pass. False = stop the process (STOP_MANAGER)."""
        now = self.clock()
        while self.q:
            kind, obj, at = self.q.popleft()
            if kind == "fill":
                self._handle_fill(obj, at)
            elif kind == "position":
                cand = now + POSITION_RECHECK
                self.recheck_at = cand if self.recheck_at is None else min(self.recheck_at, cand)
            elif kind == "disconnect" and not self.ib.isConnected():
                self.on_disconnect()                  # (a queued event from before a reconnect is stale: ignored)
        if not self.connected and self.ib.isConnected():
            self.on_reconnect()                       # self-heal if the runner reconnected without telling us
        if self.kill.stop_requested():
            self.stop("STOP_MANAGER file")
            return False
        if self.connected:
            if self.kill.flatten_requested():
                self._flatten()
                self.kill.consume_flatten()
            self._retry_pending(now)
            if self.next_reconcile is None or now >= self.next_reconcile or (self.recheck_at and now >= self.recheck_at):
                self.reconcile("periodic")
            self._follow_exits()
            self._flat_check(now)
            self._stale_check(now)
        self.save()
        return True

    # ================================================================ fills
    def _handle_fill(self, fill, received, via: str = "event"):
        ex, c = fill.execution, fill.contract
        eid = ex.execId
        if eid in self._seen_set:
            return
        self._mark_seen(eid)
        qty = int(round(float(ex.shares)))
        signed = _side(fill) * qty
        cid = int(c.conId)
        own = int(ex.clientId) == self.cfg.client_id
        rec = dict(exec_id=eid, con_id=cid, local_symbol=c.localSymbol, symbol=c.symbol, side=ex.side, qty=qty,
                   price=float(ex.price), client_id=int(ex.clientId), order_id=ex.orderId, order_ref=ex.orderRef,
                   account=ex.acctNumber, exec_time=iso(ex.time) if ex.time else None, received=iso(received), via=via)
        if ex.time:
            rec["delay_ms"] = round((received - ex.time).total_seconds() * 1000, 1)
        if c.secType != "FUT":
            self.log.write("fill_seen", **rec, action="ignored: not a futures fill")
            return
        if self.account and ex.acctNumber and ex.acctNumber != self.account:
            self.log.write("fill_seen", **rec, action="ignored: another account")
            return
        if int(ex.clientId) in self.cfg.ignore_client_ids:
            self.log.write("fill_seen", **rec, action="ignored: NAS trader / ignored client; reconcile will flag the symbol")
            self.recheck_at = received
            return
        pos = self._pos(cid)
        if own:
            self.log.write("fill_seen", **rec, action="own exit fill")
            if pos is None:
                self.log.alert("OWN_FILL_NO_STATE", f"{c.localSymbol}: own fill with no tracked position", **rec)
                self.recheck_at = received
                return
            pos.qty += signed
            if pos.qty == 0:
                self._closed(pos, "own exit filled")
            else:
                self._protect(pos)
            return
        self.log.write("fill_seen", **rec, action="manual fill (another app)")
        if pos is None:
            pos = S.PosState(con_id=cid, local_symbol=c.localSymbol, root=c.symbol, exchange=c.exchange or "")
            self.st.positions[str(cid)] = pos
        q0, q1 = pos.qty, pos.qty + signed
        if pos.mode in S.PASSIVE:
            pos.qty = q1
            if q1 == 0:
                self._closed(pos, "flat (manual fill)")
            else:
                self.recheck_at = received
            return
        if q0 == 0:
            pos.qty = q1
            self._open(pos, fill, received)
            return
        if q1 == 0:
            pos.qty = 0
            self._closed(pos, "flat by a manual fill")
            return
        if (q0 > 0) != (q1 > 0):
            self.log.write("reversal", con_id=cid, local_symbol=pos.local_symbol, old_qty=q0, new_qty=q1)
            self._closed(pos, "reversed by a manual fill")
            pos = S.PosState(con_id=cid, local_symbol=c.localSymbol, root=c.symbol, exchange=c.exchange or "", qty=q1)
            self.st.positions[str(cid)] = pos
            self._open(pos, fill, received)
            return
        pos.qty = q1
        self.log.write("scale_in" if abs(q1) > abs(q0) else "partial_reduce", con_id=cid, local_symbol=pos.local_symbol,
                       old_qty=q0, new_qty=q1)
        if pos.mode == S.MANAGED:
            self._check_cap(pos)
            self._protect(pos)
        elif pos.mode in (S.NEW, S.WATCH):
            self._activate(pos)

    def _open(self, pos, fill, received):
        pos.mode, pos.fill_id = S.NEW, fill.execution.execId
        pos.first_fill_px, pos.first_fill_at = float(fill.execution.price), iso(received)
        pos.mismatch_since = None
        self._activate(pos, fill.contract)

    def _activate(self, pos, contract=None):
        """Checks then protection for a NEW position. Re-run from the pending loop if a broker call failed."""
        c = contract or self.contracts.get(pos.con_id) or self._broker_contract(pos.con_id)
        if c is None:
            pos.pending_since = pos.pending_since or iso(self.clock())
            return
        ok, why, qc = self._contract_check(c)
        if not ok:
            if qc is False:                       # broker error: retry
                pos.pending_since = pos.pending_since or iso(self.clock())
                return
            pos.mode, pos.reason = S.UNSAFE, why
            self._alert(pos, "RAIL7", f"{pos.local_symbol}: {why}. Alert only, no orders.")
            return
        self.contracts[pos.con_id] = qc
        trades = self._try(self.gw.open_trades)
        if trades is None:
            pos.pending_since = pos.pending_since or iso(self.clock())
            return
        foreign = self.gw.foreign_exits(trades, pos.con_id, pos.qty, include_ignored=False)
        if foreign:
            pos.mode, pos.reason = S.OBSERVE_ONLY, "another app's exit order is on this trade"
            self._alert(pos, "RAIL5", f"{pos.local_symbol}: an exit order from another app is already working "
                                      f"({len(foreign)}). OBSERVE-ONLY: the manager places nothing on this trade.")
            return
        dist, how = self._emergency(pos)
        if dist is None:
            pos.mode, pos.reason = S.UNSAFE, how
            self._alert(pos, "RAIL7", f"{pos.local_symbol}: no emergency distance ({how}). Alert only, no orders.")
            return
        tick = symbols.get(pos.root).tick
        pos.emergency_dist = dist
        pos.stop_px = round_tick(pos.first_fill_px - dist if pos.qty > 0 else pos.first_fill_px + dist, tick)
        pos.mode, pos.reason, pos.managed_since = S.MANAGED, f"emergency stop {how}", iso(self.clock())
        self.log.write("position_managed", con_id=pos.con_id, local_symbol=pos.local_symbol, qty=pos.qty,
                       fill_px=pos.first_fill_px, stop_px=pos.stop_px, distance=dist, how=how, fill_id=pos.fill_id)
        self._check_cap(pos)
        self._subscribe_data(qc)
        self._protect(pos)

    def _broker_contract(self, con_id):
        got = self._try(self.gw.broker_positions) or {}
        c = got.get(int(con_id), (None, 0))[0]
        return c

    def _contract_check(self, c):
        """Rail 7. Returns (ok, why, contract-for-orders); contract False = a broker error (retry later)."""
        root = c.symbol
        if c.secType != "FUT":
            return False, "not a futures contract", None
        if root not in symbols.SYMBOLS:
            return False, f"{root} is not in the symbol table", None
        if self.cfg.cap(root) <= 0:
            return False, f"{root} is switched off (no cap in XM_CAPS)", None
        today = ny(self.clock()).date()
        hit = self.checks.get(int(c.conId))
        if hit and hit[0] == today:
            return hit[1], hit[2], hit[3]
        try:
            det = self.ib.reqContractDetails(c)
        except Exception as e:                    # noqa: BLE001
            self.log.write("broker_error", call="reqContractDetails", error=f"{type(e).__name__}: {e}")
            return False, "contract details request failed", False
        res = self._judge_details(root, det, today)
        self.checks[int(c.conId)] = (today,) + res
        self.log.write("contract_check", con_id=int(c.conId), local_symbol=c.localSymbol, ok=res[0], why=res[1])
        return res

    @staticmethod
    def _judge_details(root, det, today):
        if not det:
            return False, "IBKR returned no contract details", None
        d = det[0]
        dc = d.contract
        sym = symbols.get(root)
        try:
            mult = float(dc.multiplier or 0)
        except ValueError:
            mult = 0.0
        tick = float(d.minTick or 0)
        if abs(mult - sym.point_usd) > 1e-6:
            return False, f"multiplier {dc.multiplier} differs from the table ({sym.point_usd:g})", None
        if abs(tick - sym.tick) > 1e-9:
            return False, f"min tick {tick} differs from the table ({sym.tick:g})", None
        ltd = parse_ltd(dc.lastTradeDateOrContractMonth) or parse_ltd(getattr(d, "realExpirationDate", ""))
        if ltd is None:
            return False, f"no exact last trade date ({dc.lastTradeDateOrContractMonth!r})", None
        days = trading_days_until(today, ltd)
        if days <= 2:
            return False, f"last trade date {ltd} is within 2 trading days ({days})", None
        return True, "", dc

    def _emergency(self, pos):
        root = pos.root
        if root in symbols.VALIDATED:
            return symbols.emergency_distance(root), "CL/MCL fixed"
        mode = self.cfg.emergency_mode
        if mode == "A":
            got = self.atr_provider(pos.con_id, root) if self.atr_provider else None
            if got and got[0] and got[1]:
                return symbols.emergency_distance(root, got[0], got[1], "A"), "mode A"
            mode = self.cfg.emergency_fallback
            self._alert(pos, "EMERGENCY_FALLBACK", f"{pos.local_symbol}: mode A needs the 1H ATR (sub 4b); "
                                                   f"used the fixed mode {mode} distance")
        try:
            return symbols.emergency_distance(root, mode=mode), f"mode {mode}"
        except ValueError as e:
            return None, str(e)

    def _check_cap(self, pos):
        cap = self.cfg.cap(pos.root)
        if abs(pos.qty) > cap and not pos.over_cap:
            pos.over_cap = True
            self._alert(pos, "RAIL8", f"OVER-CAP {pos.local_symbol}: {abs(pos.qty)} > cap {cap}. Still protected by the stop; "
                                      f"the manager takes no other action on it (no 16:55 flat).")

    def _subscribe_data(self, c):
        try:
            self.ib.reqMktData(c, "", False, False)
        except Exception as e:                    # noqa: BLE001
            self.log.write("broker_error", call="reqMktData", error=f"{type(e).__name__}: {e}")

    # ================================================================ protection
    def _pending(self, pos, why: str):
        now = self.clock()
        if pos.pending_since is None:
            pos.pending_since = iso(now)
            self.log.write("protect_pending", con_id=pos.con_id, local_symbol=pos.local_symbol, why=why)

    def _protect(self, pos):
        """Make the manager's one stop cover |tracked qty|, never more than the fresh broker position allows (rail 1)."""
        if pos.mode != S.MANAGED:
            return
        c = self.contracts.get(pos.con_id)
        if c is None:
            self._pending(pos, "no contract to send on")
            return
        action = self._exit_action(pos)
        rec = self.gw.stop_for(pos.con_id, action)
        oca = rec.oca if rec is not None else self._oca(pos)
        got = self._try(self.gw.capacity, pos.con_id, pos.qty > 0, oca)
        if got is None:
            self._pending(pos, "broker read failed")
            return
        cap, snap = got
        desired = abs(pos.qty)
        qty = min(desired, cap)
        now = self.clock()
        if rec is None:
            if qty <= 0:
                self._pending(pos, f"broker position {snap.broker_qty}; nothing it can cover yet")
                return
            r = self._try(self.gw.place_stop, c, pos, qty, pos.stop_px, PROTECT,
                          "emergency stop" if pos.stop_latency_ms is None else "stop re-placed")
            if r is None:
                self._pending(pos, "stop refused")
                return
            if pos.stop_latency_ms is None and pos.first_fill_at:
                lat = (now - parse_iso(pos.first_fill_at)).total_seconds() * 1000
                pos.stop_latency_ms = round(lat, 1)
                self.log.write("stop_latency", con_id=pos.con_id, local_symbol=pos.local_symbol, ms=pos.stop_latency_ms)
                if lat > self.cfg.stop_alert_s * 1000:
                    self._alert(pos, "RAIL3", f"{pos.local_symbol}: stop placed {lat:.0f} ms after the fill (> 3 s)")
        elif qty != rec.remaining:
            if qty <= 0:
                self._safety_trim(pos.con_id, snap.broker_qty)
                return
            r = self._try(self.gw.modify_stop, c, pos, qty=qty, reason="stop quantity follows the position")
            if r is None and qty < rec.remaining:
                self.gw.cancel(rec, "safety: the stop could not be shrunk to the position, cancelled instead")
                self._alert(pos, "SAFETY_CANCEL", f"{pos.local_symbol}: stop could not be shrunk; cancelled so it cannot "
                                                  f"over-close. POSITION UNPROTECTED.")
                return
        now_stop = self.gw.stop_for(pos.con_id, action)
        covered = now_stop.remaining if now_stop is not None else 0
        if covered < desired:
            self._pending(pos, f"stop covers {covered} of {desired}")
        elif pos.pending_since is not None:
            self.log.write("protect_done", con_id=pos.con_id, local_symbol=pos.local_symbol, qty=qty)
            pos.pending_since = None

    def _retry_pending(self, now):
        for pos in list(self.st.positions.values()):
            if pos.pending_since is None:
                continue
            if pos.mode == S.NEW:
                self._activate(pos)
            elif pos.mode == S.MANAGED:
                self._protect(pos)
            else:
                pos.pending_since = None
                continue
            if pos.pending_since and (now - parse_iso(pos.pending_since)).total_seconds() > self.cfg.stop_alert_s:
                self._alert(pos, "UNPROTECTED", f"{pos.local_symbol}: fill not fully covered by a stop after "
                                                f"{self.cfg.stop_alert_s:g} s (still retrying)")

    def _safety_trim(self, con_id, broker_qty: int):
        """The manager's own orders may never exceed the position or sit on the wrong side (rails 1 / 11). Runs in every mode,
        PAUSE included: it only ever lowers or cancels."""
        side = exit_side(broker_qty)
        for r in self.gw.own(con_id):
            if side is None or r.action != side:
                self.gw.cancel(r, f"safety: broker position {broker_qty}")
            elif r.remaining > abs(broker_qty):
                done = None
                if r.kind == "STP":
                    pos = self._pos(con_id)
                    c = self.contracts.get(int(con_id)) or r.contract
                    if pos is not None and c is not None:
                        done = self._try(self.gw.modify_stop, c, pos, qty=abs(broker_qty),
                                         reason=f"safety: shrink to broker position {broker_qty}")
                if done is None:
                    self.gw.cancel(r, f"safety: order {r.remaining} > broker position {broker_qty}")

    def _closed(self, pos, why: str):
        n = self.gw.cancel_all(pos.con_id, f"position flat: {why}")
        self.log.write("position_closed", con_id=pos.con_id, local_symbol=pos.local_symbol, mode=pos.mode, why=why,
                       orders_cancelled=n)
        c = self.contracts.get(pos.con_id)
        if c is not None:
            try:
                self.ib.cancelMktData(c)
            except Exception:                     # noqa: BLE001
                pass
        self.st.positions.pop(str(pos.con_id), None)

    # ================================================================ reconcile (rails 6, 11, 13)
    def reconcile(self, reason: str, startup: bool = False):
        now = self.clock()
        self.next_reconcile = now + timedelta(seconds=self.cfg.reconcile_s)
        self.recheck_at = None
        fills = self._try(self.ib.reqExecutions)
        if fills is None:
            return
        for f in sorted(fills, key=lambda f: (f.execution.time is None, f.execution.time or now)):
            eid = f.execution.execId
            if eid in self._seen_set:
                continue
            if self._catch_up_from is not None and f.execution.time and f.execution.time < self._catch_up_from:
                self._mark_seen(eid)
                continue
            self._handle_fill(f, now, via="reqExecutions")
        self._catch_up_from = None
        trades = self._try(self.gw.open_trades)
        broker = self._try(self.gw.broker_positions)
        if trades is None or broker is None:
            return
        keys = {cid for cid, (c, q) in broker.items() if q != 0 and c.secType == "FUT"}
        keys |= {int(k) for k in self.st.positions}
        for r in list(self.gw.book.values()):     # own orders on a contract with nothing tracked (orphans)
            if r.working and r.con_id not in keys:
                self._safety_trim(r.con_id, broker.get(r.con_id, (None, 0))[1])
        summary = []
        for cid in sorted(keys):
            c, b = broker.get(cid, (None, 0))
            pos = self._pos(cid)
            if pos is None:
                pos = S.PosState(con_id=cid, local_symbol=c.localSymbol, root=c.symbol, exchange=c.exchange or "",
                                 mode=S.WATCH)
                self.st.positions[str(cid)] = pos
            self._reconcile_one(pos, c, b, trades, now, startup)
            summary.append({"local_symbol": pos.local_symbol, "broker": b, "tracked": pos.qty, "mode": pos.mode})
        self.log.write("reconcile", reason=reason, positions=summary)

    def _reconcile_one(self, pos, c, b: int, trades, now, startup: bool):
        cid, t = pos.con_id, pos.qty
        if c is not None and pos.mode == S.MANAGED and cid not in self.contracts:
            ok, why, qc = self._contract_check(c)
            if qc:
                self.contracts[cid] = qc
        if b != 0:
            self._safety_trim(cid, b)                 # own orders never above the position, never on the wrong side
        if b == t:
            pos.mismatch_since = None
            if b == 0:
                self._closed(pos, "flat at the broker")
            elif pos.mode == S.MANAGED:
                foreign = self.gw.foreign_exits(trades, cid, b, include_ignored=False)
                if foreign:
                    self.gw.cancel_all(cid, "another app placed an exit order beside the manager's stop")
                    pos.mode, pos.reason = S.OBSERVE_ONLY, "another app's exit order appeared"
                    self._alert(pos, "RAIL5", f"{pos.local_symbol}: another app placed an exit order on this trade. The "
                                              f"manager cancelled its own stop (never two exits) and is OBSERVE-ONLY.")
                    return
                rec = self.gw.stop_for(cid, self._exit_action(pos))
                if rec is None and pos.flat_state is None:
                    if pos.stop_latency_ms is not None and pos.pending_since is None:
                        self._alert(pos, "STOP_MISSING", f"{pos.local_symbol}: the manager's stop is no longer working at "
                                                         f"IBKR; re-placing it")
                    self._protect(pos)
                elif rec is not None and rec.remaining != abs(t):
                    self._protect(pos)
            elif pos.mode == S.NEW:
                self._activate(pos)
            elif pos.mode == S.OBSERVE_ONLY and not self.gw.foreign_exits(trades, cid, b, include_ignored=False):
                self._alert(pos, "OBSERVE_UNPROTECTED", f"{pos.local_symbol}: the other app's exit order is gone and the "
                                                        f"manager is OBSERVE-ONLY on this trade: POSITION UNPROTECTED. "
                                                        f"Put a stop on it in your app or flatten.")
            return
        # broker and tracked fills disagree
        self._safety_trim(cid, b)
        if b == 0:
            self._alert(None, "FLAT_UNSEEN", f"{pos.local_symbol}: broker is flat but the tracked fills say {t}; the "
                                             f"manager's orders on it are cancelled (rail 11)")
            self._closed(pos, "broker flat, closing fills not seen")
            return
        if not startup:
            if pos.mismatch_since is None:
                pos.mismatch_since = iso(now)
                cand = now + timedelta(seconds=self.cfg.mismatch_grace_s)
                self.recheck_at = cand if self.recheck_at is None else min(self.recheck_at, cand)
                return
            due = parse_iso(pos.mismatch_since) + timedelta(seconds=self.cfg.mismatch_grace_s)
            if now < due:
                self.recheck_at = due if self.recheck_at is None else min(self.recheck_at, due)
                return
        if pos.mode in (S.MANAGED, S.NEW, S.WATCH):
            why = ("held before the manager started" if startup and t == 0 else
                   f"broker position {b} is not explained by the tracked fills {t}")
            pos.mode, pos.reason = S.ALERT_ONLY, why
            self._alert(pos, "ALERT_ONLY", f"{pos.local_symbol}: {why} (another app outside the manager's view, or the NAS "
                                           f"trader). ALERT-ONLY: no new orders; any resting stop of the manager stays, "
                                           f"never above the position.")

    # ================================================================ 16:55 flat, FLATTEN, stale data
    def _exit(self, pos, kind: str, reason: str) -> bool:
        c = self.contracts.get(pos.con_id)
        r = None if c is None else self._try(self.gw.place_market_exit, c, pos, abs(pos.qty), kind, reason)
        pos.flat_kind = "flatten" if kind == KILL else "flat"
        if r is None:
            pos.flat_state = "failed"
            self._alert(pos, f"EXIT_FAILED_{pos.flat_kind.upper()}", f"{pos.local_symbol}: {reason}: the exit order was "
                                                                     f"refused or failed. The resting stop stays.")
            return False
        pos.flat_state = "exit_sent"
        return True

    def _follow_exits(self):
        """Cancel the stop only once the exit order is working (never unprotected)."""
        for pos in list(self.st.positions.values()):
            if pos.flat_state != "exit_sent":
                continue
            action = self._exit_action(pos)
            ex = self.gw.exit_for(pos.con_id, action, self._oca(pos))
            if ex is None:
                pos.flat_state = "failed"
                self._alert(pos, "EXIT_LOST", f"{pos.local_symbol}: the exit order is gone; the stop stays")
                continue
            if ex.status in ACKED or ex.status == "Filled" or ex.filled > 0:
                stop = self.gw.stop_for(pos.con_id, action)
                if stop is not None:
                    self.gw.cancel(stop, f"{pos.flat_kind}: exit order {ex.status}; stop cancelled after it")
                pos.flat_state = "stop_cancelled"
            elif ex.status in DONE:
                pos.flat_state = "failed"
                self._alert(pos, "EXIT_REJECTED", f"{pos.local_symbol}: exit order {ex.status}; the stop stays")

    def _flat_check(self, now):
        if self.cfg.flat_mode != "FLAT":
            return
        t = ny(now)
        if t.weekday() >= 5:
            return
        h, m = self.cfg.flat_hhmm
        start = t.replace(hour=h, minute=m, second=0, microsecond=0)
        end = t.replace(hour=17, minute=0, second=0, microsecond=0)
        if t >= end and t.hour == 17:
            for pos in self.st.positions.values():
                if pos.mode == S.MANAGED and pos.flat_state != "stop_cancelled" and not pos.over_cap:
                    self._alert(pos, "FLAT_NOT_DONE", f"{pos.local_symbol}: still open at 17:00 NY; held on the resting stop")
            return
        if not (start <= t < end) or not globex_open(now):
            return
        for pos in list(self.st.positions.values()):
            if pos.mode != S.MANAGED or pos.flat_state is not None:
                continue
            if pos.over_cap:
                self._alert(pos, "RAIL8_NO_FLAT", f"{pos.local_symbol}: over cap, so not flattened at 16:55 (rail 8); "
                                                  f"held on the resting stop")
                continue
            if self.kill.paused():
                self._alert(pos, "PAUSED_NO_FLAT", f"{pos.local_symbol}: PAUSED, so not flattened at 16:55; held on the stop")
                continue
            self._exit(pos, RULE, f"flat {h:02d}:{m:02d} NY")

    def _flatten(self):
        managed = [p for p in self.st.positions.values() if p.mode == S.MANAGED]
        self.log.alert("FLATTEN", f"FLATTEN requested: market out of {len(managed)} managed position(s), then PAUSE")
        for pos in managed:
            if pos.flat_state in (None, "failed"):
                self._exit(pos, KILL, "FLATTEN kill switch")
        self.kill.pause("after FLATTEN")

    def _stale_check(self, now):
        if not globex_open(now):
            return
        for pos in self.st.positions.values():
            if pos.mode != S.MANAGED:
                continue
            last = self.last_tick.get(pos.con_id) or parse_iso(pos.managed_since)
            if last is None:
                continue
            if (now - last).total_seconds() > self.cfg.stale_s:
                if not pos.stale:
                    pos.stale = True
                    self.log.alert("RAIL12", f"{pos.local_symbol}: no market data tick for {self.cfg.stale_s:g} s. No rule "
                                             f"action on it; the server-side stop stays.",
                                   con_id=pos.con_id, local_symbol=pos.local_symbol)
            elif pos.stale:
                pos.stale = False
                self.log.write("data_resumed", con_id=pos.con_id, local_symbol=pos.local_symbol)

    # ================================================================ hooks for sub 4b
    def rule_actions_allowed(self, con_id) -> tuple[bool, str]:
        pos = self._pos(con_id)
        now = self.clock()
        if pos is None or pos.mode != S.MANAGED:
            return False, "not a managed position"
        if pos.over_cap:
            return False, "over cap (rail 8)"
        if not self.connected:
            return False, "disconnected"
        if self.kill.paused():
            return False, "paused (rail 9)"
        if not globex_open(now):
            return False, "maintenance hour or weekend (rail 13)"
        if pos.stale:
            return False, "stale market data (rail 12)"
        if pos.flat_state is not None:
            return False, "exit in progress"
        return True, ""

    def tighten_stop(self, con_id, level: float, rule: str) -> bool:
        """4b entry point: move the stop to `level`. The gateway refuses any loosening (rail 4)."""
        ok, why = self.rule_actions_allowed(con_id)
        pos = self._pos(con_id)
        if not ok:
            self.log.write("rule_action_skipped", con_id=int(con_id), rule=rule, level=level, why=why)
            return False
        c = self.contracts.get(pos.con_id)
        r = self._try(self.gw.modify_stop, c, pos, price=level, reason=f"rule {rule}")
        if r is None:
            return False
        pos.stop_px = r.price
        return True
