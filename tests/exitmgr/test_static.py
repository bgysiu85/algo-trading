"""Static guards on the live exit manager's code (W15-0053 sub 4a)."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "exitmgr"
ORDER_CALLS = {"placeOrder", "cancelOrder", "reqGlobalCancel", "whatIfOrder", "bracketOrder", "oneCancelsAll"}

# exitmgr/rules.py and symbols.py are the sub 2 code the backtest ran; the manager imports them UNCHANGED (registration
# sec 16: one code path). Line endings are normalised so the pin holds on Windows and on the NAS.
PINNED = {
    "rules.py": "da6307bd95003b50adc9168b07ac645dd9106a99c91c00d17109b7716e7c8d5e",
    "symbols.py": "a46ef9d1e21dc217abeadc6d84191e080766b79c4a4980bb5d3cdb5fefaed6e7",
}


def _trees():
    for p in sorted(PKG.glob("*.py")):
        yield p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def test_only_the_gateway_can_send_or_cancel_orders():
    offenders = []
    for p, tree in _trees():
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Attribute) and node.attr in ORDER_CALLS:
                name = node.attr
            elif isinstance(node, ast.Name) and node.id in ORDER_CALLS:
                name = node.id
            if name and p.name != "gateway.py":
                offenders.append(f"{p.name}:{node.lineno} {name}")
    assert offenders == [], offenders


def test_the_guard_can_fail():
    tree = ast.parse("ib.placeOrder(c, o)")
    assert any(isinstance(n, ast.Attribute) and n.attr in ORDER_CALLS for n in ast.walk(tree))


def test_no_exitmgr_module_imports_strategy():
    bad = []
    for p, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bad += [f"{p.name}: {a.name}" for a in node.names if a.name.split(".")[0] == "strategy"]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "strategy":
                bad.append(f"{p.name}: {node.module}")
    assert bad == [], bad


def test_rules_and_symbols_are_unchanged():
    for name, want in PINNED.items():
        got = hashlib.sha256((PKG / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert got == want, f"exitmgr/{name} changed; the manager must import the sub 2 rule engine unchanged"


def test_no_module_writes_into_var():
    for p, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value.replace("\\", "/")
                assert not v.startswith(("var/", "/volume1/trader-data")), f"{p.name}:{node.lineno} {node.value!r}"


def test_env_example_defaults_to_dry():
    lines = (PKG / "env.example").read_text(encoding="utf-8").splitlines()
    kv = dict(l.split("=", 1) for l in lines if l and not l.startswith("#"))
    assert kv["XM_MODE"] == "dry" and kv["XM_ACCOUNT"] == "" and kv["XM_CLIENT_ID"] == "31"
    assert kv["XM_PORT"] in ("4002", "4004") and kv["XM_CAPS"] == "MCL:8,MNQ:2" and kv["XM_FLAT_MODE"] == "FLAT"
