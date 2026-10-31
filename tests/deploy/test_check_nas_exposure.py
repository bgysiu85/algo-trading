"""deploy/nas_trader/check_nas_exposure.py (W10-0013 sub 7), with a fake port probe: no network."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "check_nas_exposure.py"
spec = importlib.util.spec_from_file_location("check_nas_exposure", SCRIPT)
cne = importlib.util.module_from_spec(spec)
sys.modules["check_nas_exposure"] = cne          # dataclasses looks the module up while the file runs
spec.loader.exec_module(cne)


def probe_open(open_ports: set[tuple[str, int]]):
    return lambda ip, port: (ip, port) in open_ports


def test_all_closed_except_the_expected_ones_passes():
    opened = {(ip, p) for ip in ("192.168.1.109", "100.79.212.23") for p, _ in cne.EXPECTED_OPEN}
    assert cne.main(["--out", ""], probe=probe_open(opened)) == 0


def test_a_loopback_only_port_answering_over_the_tailnet_fails():
    """The 2026-10-31 state before Tailscale was removed: userspace mode handed the tailnet the NAS's 127.0.0.1."""
    assert cne.main(["--tailnet", "100.79.212.23"], probe=probe_open({("100.79.212.23", 5901)})) == 1


def test_the_tailnet_is_skipped_by_default_since_tailscale_left_the_nas():
    assert cne.main([], probe=probe_open({("100.79.212.23", 5901)})) == 0


def test_the_paper_api_answering_anywhere_fails():
    for port in (4002, 4004):
        assert cne.main(["--tailnet", ""], probe=probe_open({("192.168.1.109", port)})) == 1


def test_every_gateway_api_port_and_both_vnc_screens_are_must_be_closed():
    closed = {p for p, _ in cne.MUST_BE_CLOSED}
    assert {4001, 4002, 4003, 4004, 7496, 7497, 5900, 5901, 5432} <= closed
    assert not closed & {p for p, _ in cne.EXPECTED_OPEN}


def test_report_names_the_open_port():
    res = cne.check("tailnet", "100.79.212.23", probe_open({("100.79.212.23", 5432)}))
    text = cne.report(res)
    assert "FAIL  tailnet 100.79.212.23:5432" in text and "1 failed" in text
