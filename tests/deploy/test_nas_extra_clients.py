"""W10-0022: rules for extra paper-session processes on the NAS (client-id registry + the compose pattern)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from tests.deploy.test_nas_trader_compose import COMPOSE, ENV_EXAMPLE, code_lines, published_ports, service_block

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader"
_spec = importlib.util.spec_from_file_location("client_ids", DEPLOY / "client_ids.py")
client_ids = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(client_ids)

# Every service that is a paper-session client of the Gateway (joins its network). The Gateway itself is not one.
CLIENT_SERVICES = [n for n in re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", "\n".join(code_lines(COMPOSE)), re.M)
                   if 'network_mode: "container:trader-ib-gateway"' in service_block(n)]


def test_registry_ids_are_unique_ints_with_an_owner():
    ids = list(client_ids.CLIENT_IDS)
    assert len(ids) == len(set(ids))
    for i, (owner, state) in client_ids.CLIENT_IDS.items():
        assert isinstance(i, int) and 0 < i < 1000 and owner.strip() and state in {"in use", "reserved"}


def test_ids_already_in_use_elsewhere_are_still_registered():
    for i in (17, 55, 62, 63, 77, 88, 91, 92, 93, 94, 95):
        assert i in client_ids.CLIENT_IDS, i


def test_the_reserved_ids_for_the_named_users_exist():
    owners = " ".join(o for o, s in client_ids.CLIENT_IDS.values() if s == "reserved")
    for needle in ("W15-0053", "W15-0037", "W16-0014"):
        assert needle in owners, needle


def test_every_gateway_client_service_follows_the_pattern():
    assert "trader" in CLIENT_SERVICES and "borrow-probe" in CLIENT_SERVICES
    for name in CLIENT_SERVICES:
        block = service_block(name)
        assert 'network_mode: "container:trader-ib-gateway"' in block, name
        assert "service:ib-gateway" not in block.replace("depends_on", ""), name
        assert not re.search(r"^\s+(ports|expose|networks):", block, re.M), name
        assert re.search(r'^\s+restart: "no"\s*$', block, re.M), name
        assert re.search(r"^\s+profiles: \[", block, re.M), name           # never starts with the project
        assert "privileged" not in block and "cap_add" not in block, name
        assert not re.search(r"\b(4001|4003|7496|7498)\b", block), name
        assert not re.search(r"TWS_USERID|TWS_PASSWORD", block), name     # no second login, no IBKR password


def test_no_second_gateway_and_no_published_api():
    assert len(re.findall(r"^\s+TWS_USERID:", COMPOSE, re.M)) == 1
    assert published_ports(COMPOSE) == ["127.0.0.1:${VNC_HOST_PORT:-5901}:5900"]


def test_compose_client_ids_match_the_registry_and_are_unique():
    seen = {}
    for name, cid in client_ids.COMPOSE_CLIENTS.items():
        block = service_block(name)
        m = re.search(r'^\s+IB_CLIENT_ID: "(\d+)"', block, re.M)
        assert m and int(m.group(1)) == cid, name
        assert cid in client_ids.CLIENT_IDS and client_ids.CLIENT_IDS[cid][1] == "in use", name
        assert cid not in seen.values()
        seen[name] = cid
    # every non-trader client service has to be registered here
    assert set(CLIENT_SERVICES) - {"trader"} <= set(client_ids.COMPOSE_CLIENTS)


def test_extra_clients_never_write_into_the_traders_var_folder():
    """var/ is read by the ProArt and cleared of a stale lock by the trader at start: only the trader may write there."""
    for name in set(CLIENT_SERVICES) - {"trader"}:
        assert "TRADER_VAR_DIR" not in service_block(name) and "/app/var" not in service_block(name), name


def test_borrow_probe_is_read_only_and_mounts_code_read_only():
    block = service_block("borrow-probe")
    assert re.search(r"^\s+read_only: true\s*$", block, re.M)
    assert re.search(r"-\s+\$\{EXTRAS_DIR:-[^}]+\}:/extras:ro\s*$", block, re.M)
    assert re.search(r"-\s+\$\{EXTRAS_OUT_DIR:-[^}]+\}:/out\s*$", block, re.M)
    assert re.search(r'^\s+user: "1000:1000"\s*$', block, re.M)


def test_env_example_declares_the_extras_folders():
    for v in ("EXTRAS_DIR", "EXTRAS_OUT_DIR"):
        assert re.search(rf"^{v}=\S+", ENV_EXAMPLE, re.M), v
