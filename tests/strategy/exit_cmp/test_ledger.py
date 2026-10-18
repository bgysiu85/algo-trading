import pytest

from strategy.exit_cmp import ledger as LG
from strategy.exit_cmp import spec as S
from tests.strategy.exit_cmp.helpers import world


@pytest.fixture
def root(tmp_path):
    for d in ("docs/research", "exitmgr", "strategy/exit_cmp"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / S.REGISTRATION).write_text("registration v1\n", encoding="utf-8")
    (tmp_path / "exitmgr" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "strategy/exit_cmp" / "b.py").write_text("y = 2\n", encoding="utf-8")
    return tmp_path


def made(root, tmp_path):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    fr = world(n=800)[0]
    LG.create(out, fr=fr, per_year={2010: 1}, n_entries=1, preflight_file="p.txt", root=root)
    return out, fr


def test_the_one_run_lock(root, tmp_path):
    out, fr = made(root, tmp_path)
    with pytest.raises(LG.LedgerError, match="parity"):
        LG.begin_outcome(out)
    LG.mark_parity(out)
    LG.begin_outcome(out)
    with pytest.raises(LG.LedgerError, match="did not finish"):
        LG.begin_outcome(out)                                     # a second run is refused
    LG.begin_outcome(out, retry_after_crash=True)                 # only a crash may be retried, and it is recorded
    assert len(LG.read(out)["crashes"]) == 1
    LG.finish_outcome(out, ["r.txt"])
    with pytest.raises(LG.LedgerError, match="done"):
        LG.begin_outcome(out, retry_after_crash=True)


def test_changed_registration_code_or_frame_is_refused(root, tmp_path):
    out, fr = made(root, tmp_path)
    LG.verify(out, fr, root)
    (root / "exitmgr" / "a.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(LG.LedgerError, match="changed since the pre-flight"):
        LG.verify(out, fr, root)
    (root / "exitmgr" / "a.py").write_text("x = 1\n", encoding="utf-8")
    LG.verify(out, fr, root)
    (root / S.REGISTRATION).write_text("amended\n", encoding="utf-8")
    with pytest.raises(LG.LedgerError, match="REGISTERED_exit_cmp"):
        LG.verify(out, fr, root)
    (root / S.REGISTRATION).write_text("registration v1\n", encoding="utf-8")
    other = world(seed=9, n=800)[0]
    with pytest.raises(LG.LedgerError, match="frame"):
        LG.verify(out, other, root)


def test_line_endings_do_not_change_the_code_hash(root):
    a = LG.code_sha256(root)
    (root / "exitmgr" / "a.py").write_bytes(b"x = 1\r\n")
    assert LG.code_sha256(root) == a


def test_ledger_is_rewritten_only_before_the_outcome_run(root, tmp_path):
    out, fr = made(root, tmp_path)
    with pytest.raises(LG.LedgerError, match="already exists"):
        LG.create(out, fr=fr, per_year={}, n_entries=1, preflight_file="p", root=root)
    LG.create(out, fr=fr, per_year={}, n_entries=1, preflight_file="p", root=root, rewrite=True)
    LG.mark_parity(out)
    LG.begin_outcome(out)
    with pytest.raises(LG.LedgerError, match="never rewritten"):
        LG.create(out, fr=fr, per_year={}, n_entries=1, preflight_file="p", root=root, rewrite=True)
