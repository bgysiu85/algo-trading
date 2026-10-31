import importlib.util
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "cutover_preflight.py"
_spec = importlib.util.spec_from_file_location("cutover_preflight", PATH)
cp = importlib.util.module_from_spec(_spec)
sys.modules["cutover_preflight"] = cp
_spec.loader.exec_module(cp)


def test_go_only_when_every_check_passes():
    assert cp.decide([("a", True, ""), ("b", True, "")])
    assert not cp.decide([("a", True, ""), ("b", False, "")])
    assert not cp.decide([])


def test_verdict_is_read_from_shadow_check_output():
    assert cp.parse_verdict("x\nVERDICT: PASS\n") == "PASS"
    assert cp.parse_verdict("VERDICT: NOT YET") == "NOT YET"
    assert cp.parse_verdict("nothing") == "UNKNOWN"


def test_the_script_never_writes_to_the_nas_or_logs_in():
    src = PATH.read_text(encoding="utf-8")
    for bad in ("sudo", "docker ", "sed -i", "tee ", " rm ", "chmod ", "IB("):
        assert bad not in src.split('"""', 2)[2], bad
