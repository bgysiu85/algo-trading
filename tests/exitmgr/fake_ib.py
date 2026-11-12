"""A fake Interactive Brokers session for the exit manager tests (W15-0053 sub 4a). It stands in for ib_async.IB and uses
ib_async's own data classes (Future, Execution, Fill, Position, ContractDetails, Trade, OrderStatus, Order) so the manager
code is driven exactly as the library would drive it. Nothing here opens a socket.

What it can script: fills from any client (IBKR Mobile = client 0, the NAS trader = 17, the manager's own = 31), partial
fills, fills whose event never arrives (only reqExecutions shows them), positions that lag the fill or change under the
manager, orders from other client ids, OCA cancel-on-fill, dropped connections and reconnects, market-data ticks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ib_async import CommissionReport, ContractDetails, Execution, Fill, Future, Order, OrderStatus, Position, Ticker, Trade

from exitmgr import config as C
from exitmgr.eventlog import EventLog, read_events
from exitmgr.killswitch import KillSwitch
from exitmgr.manager import Manager

ACCOUNT = "DU1234567"
T0 = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)          # Monday 2026-11-16 10:00 New York
DONE = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self

    def __isub__(self, h):
        self.handlers.remove(h)
        return self

    def emit(self, *a):
        for h in list(self.handlers):
            h(*a)


class FakeClock:
    def __init__(self, start: datetime = T0):
        self.t = start

    def now(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t = self.t + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self.t = t


# ---------------------------------------------------------------- contracts
SPECS = {   # root -> (multiplier, minTick, exchange)
    "MCL": ("100", 0.01, "NYMEX"), "CL": ("1000", 0.01, "NYMEX"), "MNQ": ("2", 0.25, "CME"), "NQ": ("20", 0.25, "CME"),
    "ES": ("50", 0.25, "CME"), "MES": ("5", 0.25, "CME"), "ZZZ": ("1", 0.01, "CME"),
}
_ids = {"MCL": 7001, "CL": 7002, "MNQ": 7003, "NQ": 7004, "ES": 7005, "MES": 7006, "ZZZ": 7007}


def fut(root: str = "MCL", local: str | None = None, ltd: str = "20261217", con_id: int | None = None) -> Future:
    mult, _tick, exch = SPECS[root]
    return Future(conId=con_id or _ids[root], symbol=root, localSymbol=local or f"{root}F7",
                  lastTradeDateOrContractMonth=ltd, multiplier=mult, exchange=exch, currency="USD")


def details(c: Future, multiplier: str | None = None, min_tick: float | None = None) -> ContractDetails:
    mult, tick, _ = SPECS[c.symbol]
    dc = Future(conId=c.conId, symbol=c.symbol, localSymbol=c.localSymbol,
                lastTradeDateOrContractMonth=c.lastTradeDateOrContractMonth, multiplier=multiplier or mult,
                exchange=c.exchange, currency="USD")
    return ContractDetails(contract=dc, minTick=tick if min_tick is None else min_tick)


# ---------------------------------------------------------------- the fake session
class FakeIB:
    def __init__(self, clock: FakeClock, accounts=(ACCOUNT,)):
        self.clock = clock
        self.accounts = list(accounts)
        self.account = self.accounts[0]
        self.execDetailsEvent, self.positionEvent, self.disconnectedEvent = Event(), Event(), Event()
        self.pendingTickersEvent, self.errorEvent, self.orderStatusEvent = Event(), Event(), Event()
        self.connected = False
        self.client_id = None
        self.connect_calls: list = []
        self.fail_connect = 0
        self.pos: dict = {}                      # conId -> [contract, qty]   (the broker's truth)
        self.position_lag = False                # True: position changes wait for flush_positions()
        self._pending_pos: list = []
        self.trades: list = []
        self.fills: list = []
        self.details: dict = {}
        self.placed: list = []                   # every placeOrder call (a dict snapshot)
        self.cancelled: list = []
        self.mkt: list = []
        self.ack_status = "Submitted"            # status a new order gets at once ("PendingSubmit" = not acknowledged yet)
        self.script: list = []                   # (datetime, callable)
        self.broken: set = set()                 # method names that raise ConnectionError
        self._oid = 100
        self._perm = 900000
        self._exec = 1
        for root in SPECS:
            c = fut(root)
            self.details[c.conId] = [details(c)]

    # ---------------- connection
    def connect(self, host, port, clientId=1, timeout=4, readonly=False, **kw):
        self.connect_calls.append({"host": host, "port": port, "clientId": clientId, "readonly": readonly})
        if self.fail_connect:
            self.fail_connect -= 1
            raise ConnectionRefusedError("fake: gateway not up")
        self.connected, self.client_id = True, clientId
        return self

    def isConnected(self) -> bool:
        return self.connected

    def disconnect(self):
        self.connected = False

    def drop(self):
        """The Gateway goes away (daily restart)."""
        self.connected = False
        self.disconnectedEvent.emit()

    def managedAccounts(self):
        return list(self.accounts)

    def sleep(self, seconds: float = 0):
        self.clock.advance(seconds)
        self.run_script()

    def _need(self, name):
        if not self.connected or name in self.broken:
            raise ConnectionError(f"fake: {name} while disconnected")

    # ---------------- reads
    def positions(self, account=""):
        return [Position(self.account, c, float(q), 0.0) for c, q in self.pos.values() if q]

    def reqPositions(self):
        self._need("reqPositions")
        return self.positions()

    def openTrades(self):
        return [t for t in self.trades if t.orderStatus.status not in DONE]

    def reqAllOpenOrders(self):
        self._need("reqAllOpenOrders")
        return [t.order for t in self.openTrades()]

    def reqExecutions(self, execFilter=None):
        self._need("reqExecutions")
        return list(self.fills)

    def reqContractDetails(self, contract):
        self._need("reqContractDetails")
        return list(self.details.get(contract.conId, []))

    def reqMktData(self, contract, genericTickList="", snapshot=False, regulatorySnapshot=False):
        self.mkt.append(contract.conId)
        return Ticker(contract=contract)

    def cancelMktData(self, contract):
        pass

    # ---------------- orders
    def placeOrder(self, contract, order):
        self._need("placeOrder")
        modify = bool(order.orderId)
        if not modify:
            self._oid += 1
            self._perm += 1
            order.orderId, order.clientId, order.permId = self._oid, self.client_id, self._perm
            trade = Trade(contract=contract, order=order,
                          orderStatus=OrderStatus(orderId=order.orderId, status=self.ack_status, permId=order.permId,
                                                  clientId=order.clientId), fills=[], log=[])
            self.trades.append(trade)
        else:
            trade = self.trade_by_id(order.orderId)
        self.placed.append({"verb": "modify" if modify else "place", "type": order.orderType, "action": order.action,
                            "qty": float(order.totalQuantity), "aux": float(order.auxPrice or 0) if order.orderType == "STP"
                            else None, "ref": order.orderRef, "oca": order.ocaGroup, "ocaType": order.ocaType,
                            "tif": order.tif, "orderId": order.orderId, "account": order.account, "t": self.clock.now()})
        return trade

    def cancelOrder(self, order):
        self._need("cancelOrder")
        t = self.trade_by_id(order.orderId)
        if t is not None and t.orderStatus.status not in DONE:
            t.orderStatus.status = "Cancelled"
            self.cancelled.append(order.orderId)
            self.orderStatusEvent.emit(t)
        return t

    def trade_by_id(self, oid):
        for t in self.trades:
            if t.order.orderId == oid:
                return t
        return None

    # ---------------- scripting helpers
    def at(self, when, fn):
        """Run fn when the clock reaches `when` (a datetime, or seconds from now)."""
        if not isinstance(when, datetime):
            when = self.clock.now() + timedelta(seconds=when)
        self.script.append((when, fn))
        self.script.sort(key=lambda x: x[0])

    def run_script(self):
        while self.script and self.script[0][0] <= self.clock.now():
            _, fn = self.script.pop(0)
            fn()

    def _move(self, c, dq: int):
        if self.position_lag:
            self._pending_pos.append((c, dq))
            return
        self._apply(c, dq)

    def _apply(self, c, dq):
        cur = self.pos.get(c.conId, [c, 0])
        cur[1] += dq
        self.pos[c.conId] = cur
        self.positionEvent.emit(Position(self.account, c, float(cur[1]), 0.0))

    def flush_positions(self):
        for c, dq in self._pending_pos:
            self._apply(c, dq)
        self._pending_pos = []

    def set_position(self, c, qty: int):
        """A position that changes under the manager with no fill it can see."""
        self.pos[c.conId] = [c, qty]
        self.positionEvent.emit(Position(self.account, c, float(qty), 0.0))

    def _exec_obj(self, c, side: str, qty: float, price: float, client_id: int, order_id=0, perm_id=0, order_ref="",
                  account=None):
        eid = f"0001f4e4.{self._exec:08x}.01.01"
        self._exec += 1
        ex = Execution(execId=eid, time=self.clock.now(), acctNumber=account or self.account, exchange=c.exchange,
                       side=side, shares=float(qty), price=float(price), permId=perm_id, clientId=client_id,
                       orderId=order_id, cumQty=float(qty), avgPrice=float(price), orderRef=order_ref)
        return Fill(contract=c, execution=ex, commissionReport=CommissionReport(), time=self.clock.now())

    def manual_fill(self, c, side: str, qty: int, price: float, client_id: int = 0, deliver: bool = True,
                    move_position: bool = True, account=None) -> Fill:
        """A fill from another app. side 'BOT' or 'SLD'."""
        f = self._exec_obj(c, side, qty, price, client_id, account=account)
        self.fills.append(f)
        if move_position:
            self._move(c, qty if side == "BOT" else -qty)
        if deliver:
            self.execDetailsEvent.emit(None, f)
        return f

    def fill_order(self, trade, qty: int | None = None, price: float | None = None, deliver: bool = True) -> Fill:
        """One of the working orders (any client) fills, fully or in part; OCA type 1 cancels the rest of its group."""
        o, st = trade.order, trade.orderStatus
        rem = int(o.totalQuantity - st.filled)
        q = rem if qty is None else qty
        px = price if price is not None else (o.auxPrice or 0.0)
        st.filled += q
        st.status = "Filled" if st.filled >= o.totalQuantity else "Submitted"
        f = self._exec_obj(trade.contract, "BOT" if o.action == "BUY" else "SLD", q, px, o.clientId, o.orderId, o.permId,
                           o.orderRef)
        self.fills.append(f)
        self._move(trade.contract, q if o.action == "BUY" else -q)
        if st.status == "Filled" and o.ocaGroup and o.ocaType == 1:
            for t in self.trades:
                if t is not trade and t.order.ocaGroup == o.ocaGroup and t.orderStatus.status not in DONE:
                    t.orderStatus.status = "Cancelled"
        if deliver:
            self.execDetailsEvent.emit(trade, f)
        return f

    def add_foreign_order(self, c, action: str, qty: int, aux: float = 0.0, order_type: str = "STP", client_id: int = 0,
                          oca: str = "") -> Trade:
        self._oid += 1
        self._perm += 1
        o = Order(orderId=self._oid, clientId=client_id, permId=self._perm, action=action, totalQuantity=float(qty),
                  orderType=order_type, auxPrice=aux, ocaGroup=oca, account=self.account)
        t = Trade(contract=c, order=o, orderStatus=OrderStatus(orderId=o.orderId, status="Submitted", permId=o.permId,
                                                               clientId=client_id), fills=[], log=[])
        self.trades.append(t)
        return t

    def tick(self, c):
        self.pendingTickersEvent.emit([Ticker(contract=c)])

    # ---------------- views for tests
    def own_working(self, con_id=None):
        return [t for t in self.openTrades() if t.order.clientId == C.CLIENT_ID
                and (con_id is None or t.contract.conId == con_id)]


# ---------------------------------------------------------------- harness
@dataclass
class H:
    ib: FakeIB
    clock: FakeClock
    cfg: C.Config
    log: EventLog
    kill: KillSwitch
    mgr: Manager

    def step(self, n: int = 1, dt: float = 0.2) -> bool:
        ok = True
        for _ in range(n):
            self.ib.sleep(dt)
            ok = self.mgr.step()
            if not ok:
                break
        return ok

    def run_until(self, when: datetime, dt: float = 0.2) -> None:
        while self.clock.now() < when:
            self.step(1, dt)

    def events(self, kind: str | None = None) -> list:
        ev = read_events(self.cfg.out_dir / "events.jsonl")
        return [e for e in ev if kind is None or e["kind"] == kind]

    def alerts(self, code: str | None = None) -> list:
        return [e for e in self.events("alert") if code is None or e["code"] == code]

    def pos(self, c):
        return self.mgr._pos(c.conId)

    def stop(self, c):
        """The manager's working stop trade at the fake broker (None if none)."""
        st = [t for t in self.ib.own_working(c.conId) if t.order.orderType == "STP"]
        assert len(st) <= 1, f"more than one working stop: {st}"
        return st[0] if st else None


def env_for(tmp_path, mode: str = "paper", **extra) -> dict:
    e = {"XM_MODE": mode, "XM_OUT_DIR": str(tmp_path / "out"), "XM_RECONCILE_S": "15"}
    if mode == "paper":
        e["XM_ACCOUNT"] = ACCOUNT
    e.update({k: str(v) for k, v in extra.items()})
    return e


def build(tmp_path, mode: str = "paper", start: datetime = T0, ib: FakeIB | None = None, clock: FakeClock | None = None,
          atr_provider=None, started: bool = True, **extra) -> H:
    clock = clock or FakeClock(start)
    ib = ib or FakeIB(clock)
    cfg = C.load(env_for(tmp_path, mode, **extra))
    if not ib.connected:
        ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, readonly=(mode != "paper"))
    log = EventLog(cfg.out_dir / "events.jsonl", clock=clock.now)
    kill = KillSwitch(cfg.out_dir / "control", clock=clock.now)
    mgr = Manager(ib, cfg, C.check_accounts(cfg, ib.managedAccounts()), log, kill, clock=clock.now, atr_provider=atr_provider)
    h = H(ib, clock, cfg, log, kill, mgr)
    if started:
        mgr.start()
    return h
