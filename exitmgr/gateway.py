#!/usr/bin/env python3
"""The order gateway: the ONLY code in the exit manager that can send, modify or cancel an order (W15-0053 sub 4a).
tests/exitmgr/test_static.py fails if any other exitmgr module calls placeOrder / cancelOrder.

Every send is checked here, in code, immediately before it goes out (REGISTERED_exit_cmp.md sec 14):
  rail 1  REDUCE-ONLY. Fresh broker position fetched (reqPositions) right before the send. The order's side must be opposite
          the live position (no position = refused: the manager never opens one), and its quantity plus every other working
          exit-side order on that contract (any client) must be <= the position. Orders in one OCA group count once, at the
          largest member (IBKR OCA type 1 = cancel the rest, with overfill protection).
  rail 2  ONE EXIT PER POSITION. orderRef XM:<localSymbol>:<fill-id>; all of the manager's orders on a contract sit in one OCA
          group XMOCA:<localSymbol>:<fill-id>. A second stop is refused (modify the first). The only second order allowed is
          one market exit (the 16:55 flat or FLATTEN) in the SAME OCA group, so stop and exit can never both fill.
  rail 4  NEVER LOOSENS. A stop-level change must be protective: up for a long (sell stop), down for a short (buy stop).
  rail 5  OTHER APPS' EXITS. If any other app (not this manager, not an ignored client such as the NAS trader, id 17) has a
          working exit-side order on the contract, nothing is sent.
  rail 9  PAUSE blocks rule actions and stop-level changes; the runaway guard (latched) blocks every counted send.
          Cancels are never blocked and never counted: a cancel can only remove exposure.
  dry     mode 'dry' runs every check and LOGS the order it would send. It never calls the broker's order functions.

A refusal raises RailRefused (logged as kind 'refused'); the caller decides what to do (usually: alert, leave the resting stop).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from exitmgr import symbols
from exitmgr.timeutil import iso

WORKING = frozenset({"PendingSubmit", "ApiPending", "PreSubmitted", "Submitted", "PendingCancel"})
ACKED = frozenset({"PreSubmitted", "Submitted"})
DONE = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive", "Gone"})
EPS = 1e-9

# action kinds: what a send is FOR (decides what PAUSE / the runaway guard allow)
PROTECT = "protect"        # place the protective stop, or raise its quantity to follow the position
SAFETY = "safety"          # lower the stop quantity because the position shrank (never blocked by PAUSE)
LEVEL = "level"            # change the stop level (protective direction only)
RULE = "rule"              # a rule exit (the 16:55 flat; 4b rule exits)
KILL = "kill"              # FLATTEN kill switch


class RailRefused(Exception):
    def __init__(self, rail: str, msg: str):
        super().__init__(f"rail {rail}: {msg}")
        self.rail, self.msg = rail, msg


@dataclass
class OrderRec:
    ref: str
    con_id: int
    local_symbol: str
    kind: str                  # "STP" | "MKT"
    action: str                # "BUY" | "SELL"
    qty: int                   # total quantity of the order (including any filled part)
    price: float | None
    oca: str
    fill_id: str
    status: str = "PendingSubmit"
    filled: int = 0
    order_id: int | None = None
    perm_id: int | None = None
    virtual: bool = False      # dry mode: never sent
    sent_at: str | None = None
    trade: object = field(default=None, repr=False, compare=False)
    contract: object = field(default=None, repr=False, compare=False)

    @property
    def remaining(self) -> int:
        return max(0, int(self.qty) - int(self.filled))

    @property
    def working(self) -> bool:
        return self.status in WORKING

    def brief(self) -> dict:
        return {"ref": self.ref, "otype": self.kind, "action": self.action, "qty": self.qty, "filled": self.filled,
                "price": self.price, "oca": self.oca, "status": self.status, "order_id": self.order_id, "virtual": self.virtual}


def exit_side(broker_qty: int) -> str | None:
    """The only side the manager may send for this position (rail 1). None when flat."""
    if broker_qty > 0:
        return "SELL"
    if broker_qty < 0:
        return "BUY"
    return None


def round_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 10)


def exit_load(items) -> int:
    """Total quantity that working exit orders could take out: non-OCA orders add up, an OCA group counts its largest member."""
    groups: dict[str, int] = {}
    total = 0
    for oca, qty in items:
        if oca:
            groups[oca] = max(groups.get(oca, 0), qty)
        else:
            total += qty
    return total + sum(groups.values())


@dataclass
class Snapshot:
    broker_qty: int
    foreign: list              # other clients' working orders on the contract (Trade objects)


class Gateway:
    def __init__(self, ib, cfg, log, kill, guard, account: str):
        self.ib, self.cfg, self.log, self.kill, self.guard, self.account = ib, cfg, log, kill, guard, account
        self.book: dict[str, OrderRec] = {}
        self.dry = cfg.mode != "paper"

    # ---------------------------------------------------------------- broker reads (fresh)
    def _is_own(self, trade) -> bool:
        o = trade.order
        return int(getattr(o, "clientId", -1)) == self.cfg.client_id and str(getattr(o, "orderRef", "") or "").startswith("XM:")

    @staticmethod
    def _t_status(trade) -> str:
        return str(getattr(trade.orderStatus, "status", "") or "")

    @staticmethod
    def _t_remaining(trade) -> int:
        return max(0, int(round(float(trade.order.totalQuantity or 0) - float(trade.orderStatus.filled or 0))))

    def broker_positions(self) -> dict:
        """conId -> (contract, signed qty) for this account, fresh from the broker."""
        out: dict = {}
        for p in self.ib.reqPositions():
            if self.account and getattr(p, "account", "") and p.account != self.account:
                continue
            c = p.contract
            q = int(round(float(p.position)))
            cid = int(c.conId)
            prev = out.get(cid, (c, 0))[1]
            out[cid] = (c, prev + q)
        return out

    def open_trades(self) -> list:
        """All working orders in the account (every client), fresh: reqAllOpenOrders, then the library's open-trade list."""
        self.ib.reqAllOpenOrders()
        trades = list(self.ib.openTrades())
        self._sync_own(trades)
        return trades

    def foreign_exits(self, trades, con_id: int, broker_qty: int, include_ignored: bool = True) -> list:
        side = exit_side(broker_qty)
        out = []
        for t in trades:
            if int(t.contract.conId) != int(con_id) or self._is_own(t) or self._t_status(t) not in WORKING:
                continue
            if side is None or t.order.action != side:
                continue
            if not include_ignored and int(getattr(t.order, "clientId", -1)) in self.cfg.ignore_client_ids:
                continue
            out.append(t)
        return out

    def snapshot(self, con_id: int) -> Snapshot:
        pos = self.broker_positions()
        bq = pos.get(int(con_id), (None, 0))[1]
        trades = self.open_trades()
        return Snapshot(bq, self.foreign_exits(trades, con_id, bq))

    # ---------------------------------------------------------------- own-order book
    def _refresh(self, rec: OrderRec) -> None:
        if rec.virtual or rec.trade is None:
            return
        st = self._t_status(rec.trade)
        if st:
            rec.status = st
        rec.filled = int(round(float(rec.trade.orderStatus.filled or 0)))
        rec.order_id = getattr(rec.trade.order, "orderId", rec.order_id)
        rec.perm_id = getattr(rec.trade.order, "permId", rec.perm_id) or rec.perm_id

    def _sync_own(self, trades) -> list:
        """Re-bind the book to the broker's open orders (after a reconnect the library makes new Trade objects). An own
        order the book does not know is adopted (orphan from an earlier run). A book order that is working but no longer
        open at the broker is marked Gone. Returns the Gone recs."""
        if self.dry:
            return []
        open_refs = set()
        for t in trades:
            if not self._is_own(t):
                continue
            ref = t.order.orderRef
            open_refs.add(ref)
            rec = self.book.get(ref)
            if rec is None:
                o = t.order
                rec = OrderRec(ref=ref, con_id=int(t.contract.conId), local_symbol=t.contract.localSymbol,
                               kind="MKT" if o.orderType == "MKT" else "STP", action=o.action,
                               qty=int(round(float(o.totalQuantity))), price=(None if o.orderType == "MKT" else float(o.auxPrice)),
                               oca=o.ocaGroup or "", fill_id=ref.split(":")[2] if ref.count(":") >= 2 else "")
                self.book[ref] = rec
                self.log.write("order_adopted", **rec.brief(), con_id=rec.con_id)
            rec.trade, rec.contract = t, t.contract
            self._refresh(rec)
        gone = []
        for rec in self.book.values():
            self._refresh(rec)
            if rec.working and rec.ref not in open_refs and not rec.virtual:
                rec.status = "Gone"
                gone.append(rec)
                self.log.write("order_gone", **rec.brief(), con_id=rec.con_id)
        return gone

    def own(self, con_id: int, working_only: bool = True) -> list[OrderRec]:
        out = []
        for r in self.book.values():
            self._refresh(r)
            if r.con_id == int(con_id) and (r.working or not working_only):
                out.append(r)
        return out

    def stop_for(self, con_id: int, action: str | None = None) -> OrderRec | None:
        """The manager's working stop on the contract (on `action`'s side when given: after a reversal the old side's stop
        may still be pending cancel)."""
        for r in self.own(con_id):
            if r.kind == "STP" and (action is None or r.action == action):
                return r
        return None

    def exit_for(self, con_id: int, action: str | None = None, oca: str | None = None) -> OrderRec | None:
        """The latest market exit the manager sent on the contract (any status, so a rejection can be seen)."""
        found = None
        for r in self.own(con_id, working_only=False):
            if r.kind == "MKT" and (action is None or r.action == action) and (oca is None or r.oca == oca):
                found = r
        return found

    def own_load(self, con_id: int, action: str, exclude_ref: str | None = None, oca: str | None = None) -> int:
        """Exit quantity of the manager's own working orders on `action`'s side; with `oca`, that group is left out (the
        caller's order will be counted inside it)."""
        return exit_load((r.oca, r.remaining) for r in self.own(con_id)
                         if r.ref != exclude_ref and r.action == action and (oca is None or r.oca != oca))

    def capacity(self, con_id: int, side_long: bool, oca: str) -> tuple[int, Snapshot]:
        """How many contracts an order in OCA group `oca` may cover now (rail 1): the position less every exit-side order
        outside that group. (Inside one OCA group only one order can fill, so the group's own members do not reduce it.)"""
        snap = self.snapshot(con_id)
        bq = snap.broker_qty
        if bq == 0 or (bq > 0) != side_long:
            return 0, snap
        action = exit_side(bq)
        fl = exit_load((t.order.ocaGroup or "", self._t_remaining(t)) for t in snap.foreign)
        return max(0, abs(bq) - fl - self.own_load(con_id, action, oca=oca)), snap

    # ---------------------------------------------------------------- checks
    def _refuse(self, rail: str, msg: str, **ctx):
        self.log.write("refused", rail=rail, msg=msg, **ctx)
        raise RailRefused(rail, msg)

    def _gate(self, kind: str, ctx: dict) -> None:
        if kind in (LEVEL, RULE) and self.kill.paused():
            self._refuse("9", "PAUSED: no rule actions or stop-level changes", **ctx)

    def _rails_1_5(self, snap: Snapshot, con_id: int, action: str, new_qty: int, new_oca: str, exclude_ref: str | None,
                   ctx: dict) -> None:
        bq = snap.broker_qty
        side = exit_side(bq)
        ctx = dict(ctx, broker_qty=bq)
        if side is None:
            self._refuse("1", "no position at the broker: the manager never opens one", **ctx)
        if action != side:
            self._refuse("1", f"{action} would add to a {'long' if bq > 0 else 'short'} position", **ctx)
        mine = [t for t in snap.foreign if int(getattr(t.order, "clientId", -1)) not in self.cfg.ignore_client_ids]
        if mine:
            self._refuse("5", f"another app has {len(mine)} working exit order(s) on this contract", **ctx,
                         foreign=[{"client_id": t.order.clientId, "type": t.order.orderType, "qty": t.order.totalQuantity}
                                  for t in mine])
        items = [(r.oca, r.remaining) for r in self.own(con_id) if r.ref != exclude_ref and r.action == action]
        items += [(t.order.ocaGroup or "", self._t_remaining(t)) for t in snap.foreign]
        items.append((new_oca, int(new_qty)))
        load = exit_load(items)
        if load > abs(bq):
            self._refuse("1", f"exit quantity {load} would exceed the position {abs(bq)}", **ctx, exit_load=load)

    def _count(self, ctx: dict) -> None:
        if not self.guard.check_and_record():
            self._refuse("9d", f"runaway guard latched ({self.guard.tripped}); restart the manager to resume", **ctx)

    # ---------------------------------------------------------------- sends
    def _send(self, rec: OrderRec, contract, order_kw: dict, modify: bool, ctx: dict) -> OrderRec:
        verb = "modify" if modify else "place"
        if self.dry:
            rec.virtual = True
            rec.status = "Submitted"
            rec.sent_at = iso(self.log.clock())
            self.log.write("order_would_send", verb=verb, **rec.brief(), con_id=rec.con_id, **ctx)
            return rec
        if modify:
            order = rec.trade.order
            order.totalQuantity = rec.qty
            if rec.kind == "STP":
                order.auxPrice = rec.price
        else:
            from ib_async import MarketOrder, StopOrder        # imported here: dry mode never needs the order classes
            common = dict(orderRef=rec.ref, ocaGroup=rec.oca, ocaType=1, account=self.account, transmit=True)
            if rec.kind == "STP":
                order = StopOrder(rec.action, rec.qty, rec.price, tif=self.cfg.stop_tif, outsideRth=self.cfg.outside_rth,
                                  **common)
            else:
                order = MarketOrder(rec.action, rec.qty, tif="DAY", **common)
        trade = self.ib.placeOrder(contract, order)
        rec.trade, rec.contract = trade, contract
        rec.sent_at = iso(self.log.clock())
        self._refresh(rec)
        self.log.write("order_sent", verb=verb, **rec.brief(), con_id=rec.con_id, **ctx)
        return rec

    def place_stop(self, contract, pos, qty: int, price: float, kind: str = PROTECT, reason: str = "") -> OrderRec:
        con_id = int(contract.conId)
        tick = symbols.get(pos.root).tick
        price = round_tick(price, tick)
        action = "SELL" if pos.qty > 0 else "BUY"
        ref, oca = f"XM:{pos.local_symbol}:{pos.fill_id}", f"XMOCA:{pos.local_symbol}:{pos.fill_id}"
        ctx = {"reason": reason, "action_kind": kind, "local_symbol": pos.local_symbol}
        self._gate(kind, ctx)
        if self.stop_for(con_id, action) is not None:
            self._refuse("2", "a working stop already exists for this position: modify it, never stack a second", **ctx)
        others = [r for r in self.own(con_id) if r.oca != oca and r.action == action]
        if others:
            self._refuse("2", f"the manager already has working orders in another OCA group on this contract", **ctx)
        if qty <= 0:
            self._refuse("1", "quantity must be positive", **ctx)
        snap = self.snapshot(con_id)
        self._rails_1_5(snap, con_id, action, qty, oca, None, ctx)
        self._count(ctx)
        rec = OrderRec(ref=ref, con_id=con_id, local_symbol=pos.local_symbol, kind="STP", action=action, qty=int(qty),
                       price=price, oca=oca, fill_id=pos.fill_id)
        self.book[ref] = rec
        return self._send(rec, contract, {}, False, dict(ctx, broker_qty=snap.broker_qty))

    def modify_stop(self, contract, pos, qty: int | None = None, price: float | None = None, reason: str = "") -> OrderRec:
        con_id = int(contract.conId)
        rec = self.stop_for(con_id, "SELL" if pos.qty > 0 else "BUY")
        ctx = {"reason": reason, "local_symbol": pos.local_symbol}
        if rec is None:
            self._refuse("2", "no working stop to modify", **ctx)
        new_rem = rec.remaining if qty is None else int(qty)
        new_px = rec.price if price is None else round_tick(price, symbols.get(pos.root).tick)
        is_long_stop = rec.action == "SELL"
        if new_px is not None and rec.price is not None and abs(new_px - rec.price) > EPS:
            loosens = new_px < rec.price - EPS if is_long_stop else new_px > rec.price + EPS
            if loosens:
                self._refuse("4", f"stop {rec.price} -> {new_px} would LOOSEN a {'long' if is_long_stop else 'short'}",
                             **ctx, old=rec.price, new=new_px)
            kind = LEVEL
        elif new_rem < rec.remaining:
            kind = SAFETY
        else:
            kind = PROTECT
        ctx["action_kind"] = kind
        if new_px == rec.price and new_rem == rec.remaining:
            return rec
        if new_rem <= 0:
            self._refuse("1", "a stop quantity of 0: cancel instead", **ctx)
        self._gate(kind, ctx)
        snap = self.snapshot(con_id)
        self._rails_1_5(snap, con_id, rec.action, new_rem, rec.oca, rec.ref, ctx)
        self._count(ctx)
        old = rec.brief()
        rec.qty, rec.price = rec.filled + new_rem, new_px
        self._send(rec, contract, {}, True, dict(ctx, broker_qty=snap.broker_qty, old_qty=old["qty"], old_price=old["price"]))
        return rec

    def place_market_exit(self, contract, pos, qty: int, kind: str = RULE, reason: str = "") -> OrderRec:
        con_id = int(contract.conId)
        action = "SELL" if pos.qty > 0 else "BUY"
        stop = self.stop_for(con_id, action)
        oca = stop.oca if stop is not None else f"XMOCA:{pos.local_symbol}:{pos.fill_id}"
        ref = (stop.ref if stop is not None else f"XM:{pos.local_symbol}:{pos.fill_id}") + ":X"
        ctx = {"reason": reason, "action_kind": kind, "local_symbol": pos.local_symbol}
        self._gate(kind, ctx)
        if any(r.kind == "MKT" and r.action == action for r in self.own(con_id)):
            self._refuse("2", "a market exit is already working for this position", **ctx)
        if any(r.oca != oca and r.action == action for r in self.own(con_id)):
            self._refuse("2", "the manager's orders on this contract are in another OCA group", **ctx)
        snap = self.snapshot(con_id)
        self._rails_1_5(snap, con_id, action, qty, oca, None, ctx)
        self._count(ctx)
        rec = OrderRec(ref=ref, con_id=con_id, local_symbol=pos.local_symbol, kind="MKT", action=action, qty=int(qty),
                       price=None, oca=oca, fill_id=pos.fill_id)
        self.book[ref] = rec
        return self._send(rec, contract, {}, False, dict(ctx, broker_qty=snap.broker_qty))

    def cancel(self, rec: OrderRec, reason: str) -> None:
        """Never blocked, never counted (a cancel can only remove exposure)."""
        if not rec.working:
            return
        if rec.virtual or self.dry:
            rec.status = "Cancelled"
            self.log.write("order_would_cancel", **rec.brief(), con_id=rec.con_id, reason=reason)
            return
        self.ib.cancelOrder(rec.trade.order)
        self._refresh(rec)
        self.log.write("order_cancel_sent", **rec.brief(), con_id=rec.con_id, reason=reason)

    def cancel_all(self, con_id: int, reason: str) -> int:
        recs = self.own(con_id)
        for r in recs:
            self.cancel(r, reason)
        return len(recs)
