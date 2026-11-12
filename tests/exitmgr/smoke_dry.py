"""Dry-mode smoke run of the whole exit manager (run_manager.main) against the fake IB (W15-0053 sub 4a).

    D:\\Trading\\.venv\\Scripts\\python.exe -m tests.exitmgr.smoke_dry --out "D:\\Trading\\Claude outputs\\xm_smoke"

Script, Monday 16:50 NY: Ben buys 2 MCL, adds 1, a CL fill (switched off), a NAS trader MNQ fill (client 17), the Gateway
drops and comes back, Ben sells 1, then 16:55 flat. Dry mode: every order is logged as "would send"; the fake broker must
receive none. Prints a summary and exits 0 only if that holds.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from exitmgr import run_manager
from exitmgr.eventlog import read_events
from tests.exitmgr.fake_ib import FakeClock, FakeIB, fut

START = datetime(2026, 11, 16, 21, 50, tzinfo=timezone.utc)          # Monday 16:50 New York


def run(out_dir: Path, echo=print) -> dict:
    clock = FakeClock(START)
    ib = FakeIB(clock)
    mcl, cl, mnq = fut("MCL"), fut("CL"), fut("MNQ")
    for s in range(0, 400):
        ib.at(s + 0.5, lambda: ib.tick(mcl))
    ib.at(2, lambda: ib.manual_fill(mcl, "BOT", 2, 70.00))
    ib.at(5, lambda: ib.manual_fill(mcl, "BOT", 1, 70.10))
    ib.at(10, lambda: ib.manual_fill(cl, "BOT", 1, 70.05))
    ib.at(15, lambda: ib.manual_fill(mnq, "BOT", 1, 20000.0, client_id=17))
    ib.at(20, ib.drop)
    ib.at(60, lambda: ib.manual_fill(mcl, "SLD", 1, 70.20))
    env = {"XM_MODE": "dry", "XM_OUT_DIR": str(out_dir), "XM_LOOP_S": "0.2"}
    lines: list[str] = []

    def out(s):
        lines.append(s)
        echo(s)
    rc = run_manager.main([], env=env, ib_factory=lambda: ib, clock=clock.now, out=out, max_steps=1950)
    ev = read_events(out_dir / "events.jsonl")
    kinds = Counter(e["kind"] for e in ev)
    would = [(e["verb"], e["otype"], e["action"], e["qty"], e.get("price"), e["reason"]) for e in ev
             if e["kind"] == "order_would_send"]
    alerts = [(e["code"], e["msg"]) for e in ev if e["kind"] == "alert"]
    return {"rc": rc, "placed": list(ib.placed), "cancelled": list(ib.cancelled), "kinds": dict(kinds), "would": would,
            "alerts": alerts, "connects": len(ib.connect_calls), "end": clock.now(), "events": len(ev)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = run(Path(a.out), echo=lambda s: None)
    print(f"exit code {r['rc']}; {r['events']} events; connects {r['connects']}; ended {r['end'].isoformat()}")
    print("orders the fake broker received:", r["placed"] or "NONE", "| cancels:", r["cancelled"] or "NONE")
    print("orders the manager WOULD have sent:")
    for w in r["would"]:
        print("   ", w)
    print("alerts:")
    for code, msg in r["alerts"]:
        print(f"    {code}: {msg}")
    print("event counts:", r["kinds"])
    ok = r["rc"] == 0 and not r["placed"] and not r["cancelled"]
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
