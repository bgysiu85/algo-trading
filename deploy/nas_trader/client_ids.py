"""IBKR API client ids on the NAS paper Gateway (W10-0022). One id per process: two sessions with the same id make IBKR
drop the first. Add a row here BEFORE a new container or script uses an id; tests/deploy/test_nas_extra_clients.py fails
on a duplicate, and on a compose service whose IB_CLIENT_ID differs from its row here.

Every process below shares the one paper login (the Gateway's, container trader-ib-gateway). No process makes its own login.
"""
from __future__ import annotations

# id -> (owner, state)   state: "in use" | "reserved" (id set aside for a container not yet built)
CLIENT_IDS: dict[int, tuple[str, str]] = {
    17: ("trader (run_trader.py, W02 / W10-0013)", "in use"),
    31: ("exit manager (W15-0053, exitmgr/run_manager.py)", "in use"),
    32: ("paper runner, chartmark v2 forward test (W15-0037 sub 4)", "reserved"),
    33: ("paper runner, DVP forward test (W16-0014 sub 3)", "reserved"),
    55: ("scanner (brokers/ibkr/scanner.py)", "in use"),
    62: ("trade-alerts", "in use"),
    63: ("backfill", "in use"),
    77: ("viewer (common/report_trades.py, tools/mnq_swing.py)", "in use"),
    88: ("params dump (brokers/ibkr/scan_params.py)", "in use"),
    91: ("desk (W18)", "in use"),
    92: ("desk bridge, read-only (desk/bridge.py)", "in use"),
    93: ("probe_gateway.py, read-only session", "in use"),
    94: ("probe_gateway.py, what-if session", "in use"),
    95: ("api_precheck.py (pre-session check)", "in use"),
    96: ("borrow and fee probe (W05-0022, borrow_probe.py)", "in use"),
}

# Containers that must carry their registry id in compose (service name -> id).
COMPOSE_CLIENTS: dict[str, int] = {"borrow-probe": 96, "exit-manager": 31}
