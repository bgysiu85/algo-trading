r"""IBKR PAPER bridge (W18-0002): turn today's Buy / Overweight decisions into bracket orders.

    python -m desk.bridge                      # 1. offline dry-run: rules check + ranking, NO connection
    python -m desk.bridge --check              # 2. read-only look at the paper account: positions, open orders, funds
    python -m desk.bridge --place              # 3. places the orders (paper only)
    python -m desk.bridge --place --ticker MPC # ... for one ticker only

Reads var/desk_runs/decisions.csv, acts ONLY on today's US-date rows with actionable == True and a Buy / Overweight
rating. A Hold's watch plan (watch / plan_* columns) is a reminder, never an order. Every row is re-checked here
(the desk checker already did, but this is the last gate before money, even paper money).

Per accepted decision, one bracket, shares = the paper rule (1):
    BUY   LMT at `entry`   DAY      (an unfilled entry expires at the close and is not re-sent)
    SELL  LMT at `target`  GTC      (take profit)
    SELL  STP at `stop`    GTC      (stop-market; IB treats the two exits as one-cancels-other)
All three carry orderRef  desk:<run_date>:<TICKER>.  `hold_until` (= run_date + horizon_days) is logged in
orders.csv; closing a position when it passes is NOT done here.

Paper only: ports other than 4002 / 7497 are refused, and the connection is dropped unless every managed account
starts with DU. Client id 92 (17 trader, 55 scanner, 77 viewer, 88 params, 91 desk data are taken). In dry-run and
--check nothing can be placed (--check connects read-only). orders.csv is written only by --place.

Exit 0 = ran; 2 = a guard refused (live port, not a paper account, bad usage); 3 = broker error.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from desk import config as cfgmod
from desk import decision, fetch_bars, pipeline, summary

ORDER_COLUMNS = ["logged_at_utc", "run_date", "ticker", "rating", "conviction", "outcome", "reason", "entry", "stop",
                 "target", "shares", "risk_usd", "hold_until", "order_ref", "parent_order_id",
                 "take_profit_order_id", "stop_order_id", "broker_status"]
BRIDGE_DEFAULTS = {"client_id": 92, "max_entry_above_close_pct": 2.0, "status_wait_s": 2}
ORDER_REF_PREFIX = "desk:"
DONE_STATUSES = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}   # an order in one of these is not "open"
BAD_STATUSES = {"Cancelled", "ApiCancelled", "Inactive"}


class BridgeError(RuntimeError):
    def __init__(self, msg, code=3):
        super().__init__(msg)
        self.code = code            # 2 = a safety guard refused, 3 = the broker could not be used


@dataclass
class BrokerState:
    """What the paper account holds. `checked` False = offline: nothing below was looked at."""
    checked: bool = False
    positions: dict = field(default_factory=dict)       # STK symbol -> signed quantity
    entry_orders: set = field(default_factory=set)      # symbols with an active desk entry order
    other_orders: set = field(default_factory=set)      # symbols with any other active order
    funds: float | None = None                          # AvailableFunds in USD


def bridge_cfg(cfg: dict) -> dict:
    return {**BRIDGE_DEFAULTS, **cfg.get("bridge", {})}


def order_ref(run_date: str, ticker: str) -> str:
    return f"{ORDER_REF_PREFIX}{run_date}:{ticker}"


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None                         # NaN -> None


def is_true(x) -> bool:
    return str(x).strip().lower() == "true"


# ------------------------------------------------------------------ the rules

def check_row(row: dict, cfg: dict):
    """-> (errors, parsed). `parsed` has float prices rounded to cents, whole shares and horizon."""
    rules, br = cfg["paper_rules"], bridge_cfg(cfg)
    errs: list[str] = []
    if row.get("ticker") not in cfg["tickers"]:
        errs.append("ticker is not in the desk's list")
    if row.get("rating") not in decision.ACTIONABLE:
        errs.append(f"rating {row.get('rating')!r} is not Buy/Overweight")
    if not rules.get("long_only", True):
        errs.append("config long_only is off; the bridge only knows how to go long")

    entry, stop, target = (_f(row.get(k)) for k in ("entry", "stop", "target"))
    if None in (entry, stop, target) or min(entry, stop, target) <= 0:
        errs.append("entry, stop and target must all be positive prices")
    else:
        entry, stop, target = round(entry, 2), round(stop, 2), round(target, 2)
        if not stop < entry < target:
            errs.append(f"need stop < entry < target (got {stop} / {entry} / {target})")

    shares, want = _f(row.get("size_shares")), rules.get("shares_per_symbol", 1)
    if shares is None or shares != int(shares) or int(shares) != want:
        errs.append(f"size_shares must be {want} (paper rule: {want} share per symbol)")
    hz, maxh = _f(row.get("horizon_days")), rules.get("max_hold_days", 180)
    if hz is None or hz != int(hz) or not 1 <= int(hz) <= maxh:
        errs.append(f"horizon_days must be a whole number 1-{maxh}")

    last = _f(row.get("last_close"))
    if last is None or last <= 0:
        errs.append("no last_close on the row to sanity-check the entry against")
    elif entry and entry > last * (1 + br["max_entry_above_close_pct"] / 100):
        errs.append(f"entry {entry} is more than {br['max_entry_above_close_pct']}% above the last close {last}: "
                    "a limit buy that high would fill at market (breakout entries are not supported)")

    if errs:
        return errs, None
    return [], {"entry": entry, "stop": stop, "target": target, "shares": int(shares), "horizon_days": int(hz)}


def plan(rows: list[dict], cfg: dict, today: str, state: BrokerState, placed_today: set | None = None,
         only: str | None = None) -> list[dict]:
    """One result per row that deserves a line: READY / REJECTED / SKIPPED / IGNORED.
    READY ones are in rank order and already counted against the position cap and funds."""
    rules, placed_today = cfg["paper_rules"], placed_today or set()
    max_open = rules["max_open_positions"]
    todays = [r for r in rows if r.get("run_date") == today and (not only or r.get("ticker") == only)]
    out: list[dict] = []

    def result(r, outcome, reason, parsed=None):
        base = {"ticker": r["ticker"], "rating": r.get("rating", ""), "conviction": r.get("conviction", ""),
                "run_date": r["run_date"], "outcome": outcome, "reason": reason}
        out.append({**base, **(parsed or {})})

    valid = []
    for r in todays:
        if summary.is_watch(r):
            result(r, "IGNORED", f"Hold with a watch plan ({r.get('plan_trigger')}, revisit {r.get('plan_revisit_on')}): "
                                 "no order without a fresh Buy/Overweight")
        elif is_true(r.get("actionable")):
            errs, parsed = check_row(r, cfg)
            if errs:
                result(r, "REJECTED", "; ".join(errs))
            else:
                valid.append((r, parsed))

    # the desk's own ranking decides who gets the free slots (conviction, then reward:risk)
    ranked = {x["ticker"]: x["rank"] for x in summary.rank([r for r, _ in valid], max_open)}
    held = {s for s, q in state.positions.items() if q and s in cfg["tickers"]} | state.entry_orders
    open_count = len(held)
    funds = state.funds
    for r, p in sorted(valid, key=lambda rp: ranked[rp[0]["ticker"]]):
        t = r["ticker"]
        notional = p["entry"] * p["shares"]
        if t in placed_today:
            result(r, "SKIPPED", "already placed today (orders.csv)", p)
        elif state.positions.get(t) or t in state.entry_orders:
            result(r, "SKIPPED", "the account already holds it or has a desk entry order for it", p)
        elif t in state.other_orders:
            result(r, "SKIPPED", "the account has another open order for it", p)
        elif open_count >= max_open:
            result(r, "SKIPPED", f"over the position cap ({open_count} of {max_open} open or pending)", p)
        elif state.checked and (funds is None or funds < notional):
            result(r, "SKIPPED", "available funds unknown" if funds is None
                   else f"available funds ${funds:,.2f} < ${notional:,.2f}", p)
        else:
            open_count += 1
            if funds is not None:
                funds -= notional
            result(r, "READY", "", p)
    return out


# ------------------------------------------------------------------ the orders

def order_specs(res: dict) -> list[dict]:
    """The bracket as plain dicts (keys = ib_async Order fields): parent entry, take profit, stop."""
    ref, q = order_ref(res["run_date"], res["ticker"]), res["shares"]
    common = {"totalQuantity": q, "orderRef": ref, "outsideRth": False}
    return [
        {**common, "action": "BUY", "orderType": "LMT", "lmtPrice": res["entry"], "tif": "DAY", "transmit": False},
        {**common, "action": "SELL", "orderType": "LMT", "lmtPrice": res["target"], "tif": "GTC", "transmit": False},
        {**common, "action": "SELL", "orderType": "STP", "auxPrice": res["stop"], "tif": "GTC", "transmit": True},
    ]


def hold_until(res: dict) -> str:
    return (datetime.strptime(res["run_date"], "%Y-%m-%d") + timedelta(days=res["horizon_days"])).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ the broker

def _connect(cfg: dict, readonly: bool, _ib=None):
    ib_cfg, br = cfg["ibkr"], bridge_cfg(cfg)
    port = ib_cfg["port"]
    if port in fetch_bars.LIVE_PORTS:
        raise BridgeError(f"port {port} is {fetch_bars.LIVE_PORTS[port]}; the bridge is paper only", 2)
    if port not in fetch_bars.PAPER_PORTS:
        raise BridgeError(f"port {port} is not a known paper port {sorted(fetch_bars.PAPER_PORTS)}", 2)
    if _ib is None:
        try:
            from ib_async import IB
        except ImportError as e:
            raise BridgeError("ib_async is not installed in this Python") from e
        _ib = IB()
    try:
        _ib.connect(ib_cfg["host"], port, clientId=br["client_id"], timeout=ib_cfg.get("timeout_s", 15),
                    readonly=readonly)
    except Exception as e:                                   # noqa: BLE001 - broker errors vary
        raise BridgeError(f"cannot connect to {ib_cfg['host']}:{port}: {e}") from e
    accounts = list(_ib.managedAccounts())
    if not accounts or not all(a.startswith("DU") for a in accounts):
        _ib.disconnect()
        raise BridgeError(f"managed accounts {accounts} are not all paper (DU...): refusing to go on", 2)
    return _ib


def read_state(ib) -> BrokerState:
    st = BrokerState(checked=True)
    for p in ib.positions():
        if p.contract.secType == "STK" and p.position:
            st.positions[p.contract.symbol] = st.positions.get(p.contract.symbol, 0) + p.position
    for tr in ib.reqAllOpenOrders():
        if tr.orderStatus.status in DONE_STATUSES:
            continue
        sym = tr.contract.symbol
        if tr.order.orderRef.startswith(ORDER_REF_PREFIX) and tr.order.action == "BUY":
            st.entry_orders.add(sym)
        else:
            st.other_orders.add(sym)
    for v in ib.accountValues():
        if v.tag == "AvailableFunds" and v.currency in ("USD", "BASE"):
            f = _f(v.value)
            if f is not None:
                st.funds = f
                if v.currency == "USD":
                    break
    return st


def place_bracket(ib, res: dict, make_stock, make_order, wait_s: float) -> dict:
    """Send one bracket. -> {"outcome", "reason", "ids", "broker_status"}. Cancels the whole bracket if any leg is
    refused, so a position is never left without its stop."""
    contract = fetch_bars._qualify(ib, res["ticker"], make_stock)
    specs = order_specs(res)
    parent_id = ib.client.getReqId()
    orders = []
    for i, s in enumerate(specs):
        o = make_order(orderId=parent_id if i == 0 else ib.client.getReqId(), **s)
        if i:
            o.parentId = parent_id
        orders.append(o)
    trades = []
    try:
        for o in orders:                                     # the last one carries transmit=True and releases all three
            trades.append(ib.placeOrder(contract, o))
        ib.sleep(wait_s)
    except Exception as e:                                   # noqa: BLE001
        for t in trades:
            try:
                ib.cancelOrder(t.order)
            except Exception:                                # noqa: BLE001
                pass
        return {"outcome": "ERROR", "reason": f"sending the bracket failed: {e}; cancelled what was sent",
                "ids": [o.orderId for o in orders], "broker_status": ""}
    ids = [o.orderId for o in orders]
    statuses = [t.orderStatus.status for t in trades]
    if any(s in BAD_STATUSES for s in statuses):
        for t in trades:
            try:
                ib.cancelOrder(t.order)
            except Exception:                                # noqa: BLE001
                pass
        why = next((e.message for t in trades for e in reversed(t.log) if e.message), "")
        return {"outcome": "REJECTED", "reason": f"broker refused a leg ({'/'.join(statuses)}): {why}; cancelled the bracket",
                "ids": ids, "broker_status": "/".join(statuses)}
    return {"outcome": "PLACED", "reason": "", "ids": ids, "broker_status": statuses[0]}


# ------------------------------------------------------------------ the log

def read_orders(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def log_orders(path: Path, entries: list[dict], now: datetime | None = None) -> None:
    """Insert or replace the (run_date, ticker) rows, atomically. A PLACED row is never replaced."""
    now = now or datetime.now(timezone.utc)
    rows = read_orders(path)
    for e in entries:
        key = (e["run_date"], e["ticker"])
        if any((r["run_date"], r["ticker"]) == key and r["outcome"] == "PLACED" for r in rows) \
                and e["outcome"] != "PLACED":
            continue
        row = {c: "" if e.get(c) is None else e.get(c, "") for c in ORDER_COLUMNS}
        row["logged_at_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [r for r in rows if (r["run_date"], r["ticker"]) != key] + [row]
    rows.sort(key=lambda r: (r["run_date"], r["ticker"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ORDER_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def log_entry(res: dict, done: dict | None = None) -> dict:
    """A plan() result (+ what place_bracket returned) -> an orders.csv row."""
    done = done or {}
    ids = done.get("ids") or ["", "", ""]
    e = {k: res.get(k, "") for k in ("run_date", "ticker", "rating", "conviction", "entry", "stop", "target")}
    e.update(outcome=done.get("outcome", res["outcome"]), reason=done.get("reason", res["reason"]),
             shares=res.get("shares", ""), broker_status=done.get("broker_status", ""),
             order_ref=order_ref(res["run_date"], res["ticker"]) if done else "",
             parent_order_id=ids[0], take_profit_order_id=ids[1], stop_order_id=ids[2])
    if "entry" in res and "stop" in res and "shares" in res:
        e["risk_usd"] = round((res["entry"] - res["stop"]) * res["shares"], 2)
    if "horizon_days" in res:
        e["hold_until"] = hold_until(res)
    return e


# ------------------------------------------------------------------ command line

def _line(r: dict, mode: str) -> str:
    t = f"{r['ticker']} {r['rating']} conv {r['conviction']}"
    if r["outcome"] == "READY":
        verb = "PLACE" if mode == "place" else "WOULD_PLACE"
        return (f"{verb} {t}: BUY {r['shares']} @ {r['entry']:.2f} (day limit), take profit {r['target']:.2f}, "
                f"stop {r['stop']:.2f} (both GTC); risk ${(r['entry'] - r['stop']) * r['shares']:.2f}, "
                f"hold until {hold_until(r)}")
    return f"{r['outcome']} {t}: {r['reason']}"


def main(argv=None, _ib=None, _stock=None, _order=None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="connect read-only and report what --place would do")
    g.add_argument("--place", action="store_true", help="place the orders (paper account only)")
    ap.add_argument("--ticker", default=None, help="act on this ticker only")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    mode = "place" if a.place else "check" if a.check else "offline"
    cfg = cfgmod.load_config(a.config)
    only = cfgmod.norm_ticker(a.ticker) if a.ticker else None
    today = cfgmod.default_run_date(now)
    runs = cfgmod.runs_dir(cfg)
    dec_path, ord_path = runs / pipeline.DECISIONS_CSV, runs / pipeline.ORDERS_CSV

    print(f"MODE {mode}: " + {"offline": "dry-run, no connection, nothing placed; positions, open orders and funds are NOT checked",
                              "check": "read-only paper connection, nothing can be placed",
                              "place": "PAPER orders will be sent"}[mode] + f". US date {today}.")
    if not dec_path.exists():
        print(f"no {dec_path}: run the desk first")
        return 1
    with dec_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    ib = None
    state = BrokerState()
    placed_today = {r["ticker"] for r in read_orders(ord_path) if r["run_date"] == today and r["outcome"] == "PLACED"}
    try:
        if mode != "offline":
            ib = _connect(cfg, readonly=(mode == "check"), _ib=_ib)
            state = read_state(ib)
            print(f"account: {len(state.positions)} stock positions, {len(state.entry_orders)} desk entry orders pending, "
                  f"available funds {'?' if state.funds is None else f'${state.funds:,.2f}'}")
        results = plan(rows, cfg, today, state, placed_today, only)
        if not results:
            print(f"nothing to do: no Buy/Overweight decisions dated {today}" + (f" for {only}" if only else ""))
        log: list[dict] = []
        failed = False
        for r in results:
            if mode == "place" and r["outcome"] == "READY":
                if _stock is None or _order is None:
                    from ib_async import Order, Stock
                    _stock, _order = _stock or Stock, _order or Order
                done = place_bracket(ib, r, _stock, _order, bridge_cfg(cfg)["status_wait_s"])
                failed = failed or done["outcome"] == "ERROR"
                r = {**r, "outcome": done["outcome"], "reason": done["reason"]}
                print(f"{done['outcome']} {r['ticker']}: BUY {r['shares']} @ {r['entry']:.2f}, ids {done['ids']}"
                      + (f" ({done['reason']})" if done["reason"] else f", broker says {done['broker_status']}"))
                log.append(log_entry(r, done))
            else:
                print(_line(r, mode))
                if mode == "place" and r["outcome"] in ("REJECTED", "SKIPPED"):
                    log.append(log_entry(r))
        if mode == "place" and log:
            log_orders(ord_path, log, now)
            print(f"logged {len(log)} row(s) to {ord_path}")
        if mode == "offline" and any(r["outcome"] == "READY" for r in results):
            print("Dry-run only. Next: --check (read-only look at the account), then --place when Ben says so.")
        return 3 if failed else 0
    except BridgeError as e:
        print(f"BRIDGE REFUSED: {e}")
        return e.code
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:                                # noqa: BLE001
                pass


if __name__ == "__main__":
    sys.exit(main())
