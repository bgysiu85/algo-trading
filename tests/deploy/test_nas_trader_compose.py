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
