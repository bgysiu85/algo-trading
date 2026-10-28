"""Safety rules for deploy/nas_trader/compose.yaml (W10-0013 sub 4), checked on the text so no YAML library is needed.

The paper Gateway's API is unauthenticated and can place orders. These tests fail if a later edit puts it on the home
network, turns on Read-Only API (every order would be rejected), or points the Gateway at anything but paper.
"""
from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader"
COMPOSE = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (DEPLOY / ".env.example").read_text(encoding="utf-8")


def code_lines(text: str) -> list[str]:
    """Non-comment lines, with trailing '# ...' comments removed."""
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"\s+#.*$", "", ln)
        if ln.strip() and not ln.lstrip().startswith("#"):
            out.append(ln)
    return out


def published_ports(text: str) -> list[str]:
    """Entries of the `ports:` list(s): lines like  - "127.0.0.1:4002:4004"."""
    ports, in_ports = [], False
    for ln in code_lines(text):
        if re.match(r"^\s+ports:\s*$", ln):
            in_ports = True
            continue
        if in_ports:
            m = re.match(r'^\s+-\s*"?([^"\s]+)"?\s*$', ln)
            if m:
                ports.append(m.group(1))
            else:
                in_ports = False
    return ports


def test_the_only_published_port_is_the_vnc_login_screen_on_the_loopback():
    ports = published_ports(COMPOSE)
    assert ports == ["127.0.0.1:${VNC_HOST_PORT:-5901}:5900"], ports


def test_the_api_is_never_published_on_any_address():
    """Tailscale (userspace mode) hands tailnet connections to the NAS's 127.0.0.1, so even a loopback publish of the
    API would be open to every tailnet device (W17-0024 step 4). Only containers sharing the network may reach it."""
    for p in published_ports(COMPOSE):
        target = p.rsplit(":", 1)[-1]
        assert target not in {"4001", "4002", "4003", "4004", "7496", "7497", "7498", "7499"}, p
        assert not re.search(r":(4001|4002|4003|4004|7496|7497|7498|7499):", p), p


def test_nothing_is_bound_to_all_interfaces_or_the_host_network():
    code = "\n".join(code_lines(COMPOSE))
    assert "0.0.0.0" not in code
    assert "network_mode: host" not in code and 'network_mode: "host"' not in code
    assert "privileged" not in code


def test_paper_mode_and_orders_allowed():
    code = "\n".join(code_lines(COMPOSE))
    assert re.search(r"^\s+TRADING_MODE: paper\s*$", code, re.M)
    assert re.search(r'^\s+READ_ONLY_API: "no"\s*$', code, re.M)


def test_no_live_mode_anywhere():
    assert not re.search(r"TRADING_MODE:\s*(live|both)", "\n".join(code_lines(COMPOSE)))


def test_synology_seccomp_workaround_and_fixed_container_name():
    code = "\n".join(code_lines(COMPOSE))
    assert "seccomp:unconfined" in code
    assert re.search(r"^\s+container_name: trader-ib-gateway\s*$", code, re.M)


def test_credentials_come_from_env_and_are_required():
    code = "\n".join(code_lines(COMPOSE))
    for var in ("TWS_USERID", "TWS_PASSWORD", "VNC_SERVER_PASSWORD"):
        assert "${%s:?" % var in code, var


def test_vnc_does_not_take_the_recorders_port():
    assert not any(":5900:" in p for p in published_ports(COMPOSE))
    assert any(p.startswith("127.0.0.1:${VNC_HOST_PORT:-5901}") for p in published_ports(COMPOSE))


def test_env_example_has_every_variable_the_compose_file_needs_and_no_real_secrets():
    needed = set(re.findall(r"\$\{([A-Z_]+)[:}-]", COMPOSE))
    declared = {m.group(1) for m in re.finditer(r"^([A-Z_]+)=", ENV_EXAMPLE, re.M)}
    assert needed <= declared, sorted(needed - declared)
    assert "your_paper_password" in ENV_EXAMPLE and "choose_a_vnc_password" in ENV_EXAMPLE
    assert not re.search(r"sha256:[0-9a-f]{64}", ENV_EXAMPLE.split("IB_GATEWAY_IMAGE=")[-1].splitlines()[0])


# ---------------------------------------------------------------- the trader service (W10-0013 sub 5)
def service_block(name: str) -> str:
    """The code lines of one service: from '  name:' to the next service (2-space indent) or the end."""
    lines, out, inside = code_lines(COMPOSE), [], False
    for ln in lines:
        if re.match(r"^  [a-z][a-z0-9-]*:\s*$", ln):
            inside = ln.strip() == f"{name}:"
            continue
        if inside:
            out.append(ln)
    return "\n".join(out)


TRADER = service_block("trader")


def test_the_trader_service_exists_and_the_gateway_service_is_still_found():
    assert TRADER and service_block("ib-gateway")
    assert "network_mode" not in service_block("ib-gateway")          # the Gateway owns the network; the trader joins it


def test_the_trader_shares_the_gateways_network_and_publishes_nothing_itself():
    assert re.search(r'^\s+network_mode: "container:trader-ib-gateway"\s*$', TRADER, re.M)
    assert "service:ib-gateway" not in TRADER.replace("depends_on", "")          # failed on the NAS with --no-deps
    assert re.search(r"^\s+container_name: trader-ib-gateway\s*$", service_block("ib-gateway"), re.M)   # the name it joins
    assert not re.search(r"^\s+ports:\s*$", TRADER, re.M)
    assert not re.search(r"^\s+expose:", TRADER, re.M)
    assert not re.search(r"^\s+networks:", TRADER, re.M)          # one network, the Gateway's


def test_the_trader_never_starts_with_the_project_and_never_restarts_itself():
    assert re.search(r'^\s+profiles: \["trade"\]\s*$', TRADER, re.M)
    assert re.search(r'^\s+restart: "no"\s*$', TRADER, re.M)
    assert "ib-gateway:" in TRADER and "condition: service_healthy" in TRADER


def test_the_trader_defaults_to_a_dry_run_in_compose_and_in_env_example():
    assert "TRADER_MODE: ${TRADER_MODE:-dry}" in TRADER
    assert re.search(r"^TRADER_MODE=dry\s*$", ENV_EXAMPLE, re.M)


def test_the_trader_mounts_code_and_packages_read_only_and_var_writable():
    assert re.search(r"-\s+\$\{TRADER_APP_DIR:-[^}]+\}:/app:ro\s*$", TRADER, re.M)
    assert re.search(r"-\s+\$\{TRADER_DEPS_DIR:-[^}]+\}:/deps:ro\s*$", TRADER, re.M)
    assert re.search(r"-\s+\$\{TRADER_VAR_DIR:-[^}]+\}:/app/var\s*$", TRADER, re.M)
    assert "trade-journal" not in "\n".join(code_lines(COMPOSE))     # the recorder's folders are never mounted here


def test_the_trader_runs_unprivileged_with_the_synology_seccomp_workaround():
    assert re.search(r'^\s+user: "1000:1000"\s*$', TRADER, re.M)
    assert "seccomp:unconfined" in TRADER
    assert "privileged" not in TRADER and "cap_add" not in TRADER


def test_the_trader_runs_the_launcher_and_cannot_be_pointed_at_a_live_port_from_compose():
    assert re.search(r'^\s+command: \["python", "/app/run_trader.py"\]\s*$', TRADER, re.M)
    assert "TRADER_PORT" not in COMPOSE                           # not configurable here; the launcher also refuses live ports
    assert not re.search(r"\b(4001|4003|7496|7498)\b", TRADER)


def test_trader_secrets_are_optional_env_references_never_literals():
    secrets = ("TV_SESSIONID", "TV_SESSIONID_SIGN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "UI_RELAY_URL",
               "UI_AGENT_TOKEN")
    for name in secrets:
        assert re.search(rf"^\s+{name}: \$\{{{name}:-\}}\s*$", TRADER, re.M), name
        assert re.search(rf"^{name}=\s*$", ENV_EXAMPLE, re.M), f"{name} must be empty in .env.example"


def test_the_agent_id_is_set_explicitly_so_the_portal_can_tell_the_nas_from_the_proart():
    assert "UI_AGENT_ID: ${UI_AGENT_ID:-nas-trader}" in TRADER
