"""Safety rules for deploy/nas_edge/compose.yaml (W10-0013 sub 15), checked on the text like the trader's compose tests."""
from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "nas_edge"
COMPOSE = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (DEPLOY / ".env.example").read_text(encoding="utf-8")
GUIDE = (DEPLOY / "NAS-EDGE-SETUP.md").read_text(encoding="utf-8")


def code_lines(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"\s+#.*$", "", ln)
        if ln.strip() and not ln.lstrip().startswith("#"):
            out.append(ln)
    return out


CODE = "\n".join(code_lines(COMPOSE))


def service_block(name: str) -> str:
    out, inside = [], False
    for ln in code_lines(COMPOSE):
        if re.match(r"^  [a-z][a-z0-9-]*:\s*$", ln):
            inside = ln.strip() == f"{name}:"
            continue
        if re.match(r"^\S", ln):
            inside = False
        if inside:
            out.append(ln)
    return "\n".join(out)


TUNNEL, POCKET = service_block("tunnel"), service_block("pocket-id")


def test_project_is_called_edge_and_only_has_the_tunnel_and_pocket_id():
    assert re.search(r"^name: edge\s*$", CODE, re.M)
    names = re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", CODE.split("\nnetworks:")[0], re.M)
    assert names == ["services", "tunnel", "pocket-id"][1:] or set(names) <= {"tunnel", "pocket-id"}, names


def test_nothing_is_published_and_nothing_uses_the_host_network():
    assert not re.search(r"^\s+(ports|expose):", CODE, re.M)
    assert "network_mode" not in CODE and "privileged" not in CODE and "cap_add" not in CODE
    assert "0.0.0.0" not in CODE


def test_the_network_is_created_here_with_the_journals_name_and_fixed_subnet():
    top = CODE.split("\nnetworks:\n", 1)[1]
    assert re.search(r"^    name: thesiuz-edge\s*$", top, re.M)
    assert "external" not in top                      # edge OWNS the network; the other projects declare it external
    assert "subnet: ${TJ_EDGE_SUBNET:-172.30.250.0/24}" in top      # journal-login trusts X-Forwarded-* from this range only


def test_the_tunnel_has_the_old_pin_the_same_token_name_and_sits_on_edge_only():
    assert "${CLOUDFLARED_IMAGE:-cloudflare/cloudflared:2026.10.3}" in TUNNEL
    assert "TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN:?" in TUNNEL        # required: an empty token must stop the project
    assert re.search(r"^\s+networks:\n\s+- edge\s*$", TUNNEL, re.M)
    assert re.search(r'^\s+restart: always\s*$', TUNNEL, re.M)
    assert re.search(r"^\s+container_name: edge-tunnel\s*$", TUNNEL, re.M)
    assert not re.search(r"^\s+profiles:", TUNNEL, re.M)             # a plain "up" starts the tunnel


def test_pocket_id_is_a_profile_pinned_by_digest_on_the_fixed_hostname_and_only_on_edge():
    assert re.search(r'^\s+profiles: \["id"\]\s*$', POCKET, re.M)
    assert re.search(r"@sha256:[0-9a-f]{64}\}", POCKET)               # digest, never :latest
    assert "latest" not in POCKET
    assert re.search(r"^\s+APP_URL: https://id\.thesiuz\.com\s*$", POCKET, re.M)   # a passkey is bound to this hostname
    assert re.search(r"^\s+networks:\n\s+- edge\s*$", POCKET, re.M)
    assert "ENCRYPTION_KEY: ${POCKET_ID_ENCRYPTION_KEY:-}" in POCKET   # no ":?": it would stop the tunnel project from starting
    assert re.search(r"-\s+\$\{POCKET_ID_DATA_DIR:-[^}]+\}:/app/data\s*$", POCKET, re.M)


def test_the_gateways_and_the_paper_api_are_never_part_of_this_project():
    assert not re.search(r"ib-gateway|gnzsnz|\b(4001|4002|4003|4004|7496|7497)\b", CODE)


def test_env_example_declares_every_variable_and_holds_no_secret():
    needed = set(re.findall(r"\$\{([A-Z_]+)[:}-]", COMPOSE))
    declared = {m.group(1) for m in re.finditer(r"^([A-Z_]+)=", ENV_EXAMPLE, re.M)}
    assert needed <= declared, sorted(needed - declared)
    assert re.search(r"^CLOUDFLARE_TUNNEL_TOKEN=\s*$", ENV_EXAMPLE, re.M)
    assert re.search(r"^POCKET_ID_ENCRYPTION_KEY=\s*$", ENV_EXAMPLE, re.M)


# ---------------------------------------------------------------- the guide's order of steps
def blocks() -> list[str]:
    return re.findall(r"```\n(.*?)```", GUIDE, re.S)


def test_the_swap_stops_the_old_tunnel_before_the_new_one_starts():
    swap = [b for b in blocks() if "rm -f tunnel journal-login" in b]
    assert len(swap) == 1, "the swap must be ONE block, in order"
    b = swap[0]
    assert b.index("stop tunnel journal-login") < b.index("docker network rm thesiuz-edge")
    assert b.index("docker network rm thesiuz-edge") < b.index("/volume1/docker/edge")
    assert "--no-deps journal-login" in b
    for forbidden in ("recorder", "ib-gateway", "journal-db", "trader-trader", "trader-ib-gateway"):
        assert forbidden not in b, forbidden


def test_the_guide_gives_the_quiet_window_and_protects_the_env_files():
    assert "04:00" in GUIDE and "09:30" in GUIDE and "New York" in GUIDE
    assert "chmod 600 /volume1/docker/edge/.env" in GUIDE
    assert "same time" in GUIDE.lower()                   # the two-tunnels warning


def test_no_required_variable_outside_the_tunnel():
    """Compose interpolates every service, profile or not: a ":?" on a profile service stops the whole project (found on the NAS)."""
    assert "${POCKET_ID_ENCRYPTION_KEY:?" not in COMPOSE
    assert not re.search(r"\$\{[A-Z_]+:\?", POCKET)
