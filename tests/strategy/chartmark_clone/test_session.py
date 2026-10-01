"""The key flow (no window) and the headless matplotlib window, on a synthetic pool built by the real builder."""
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pytest

from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import build as B
from strategy.chartmark_clone import gui
from strategy.chartmark_clone import render as R
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.label import load_app
from strategy.chartmark_clone.session import Session
from tests.strategy.chartmark_clone.helpers import built, pool, write_trades_csv


def keys(ses, *ks):
    return [ses.key(k) for k in ks]


# ------------------------------------------------------------------ ledger (G7)
def test_the_ledger_records_the_queue_hash_before_any_label_exists(tmp_path):
    res, fr, out, cache = built(tmp_path)
    led = LG.read_ledger(out)
    assert led["queue_sha256"] == LG.sha256_file(out / S.QUEUE_FILE)
    assert led["manifest_sha256"] == LG.sha256_file(out / S.MANIFEST_FILE)
    assert led["frame_content_sha256"] == LG.frame_content_sha256(fr) == LG.frame_content_sha256(LG.load_frame_cache(cache))
    assert led["first_label_written"] is False and not (out / S.LABELS_FILE).exists()
    assert led["n_candidates"] == len(res["queue"]) and led["n_presentations"] == len(res["items"])


def test_the_builder_refuses_a_second_run(tmp_path):
    res, fr, out, cache = built(tmp_path)
    fr2, ind2, trades2 = pool(1)
    csv_path = write_trades_csv(tmp_path / "t2.csv", fr2, trades2)
    with pytest.raises(LG.LedgerError, match="already built"):
        B.build(fr2, ind2, trades2, out, cache, csv_path, repo_root=tmp_path, check_registered=False, log=lambda *_: None)


def test_the_tool_refuses_to_start_on_a_changed_queue_manifest_or_frame(tmp_path):
    res, fr, out, cache = built(tmp_path)
    load_app(out, cache)
    q = out / S.QUEUE_FILE
    original = q.read_bytes()
    q.write_bytes(original.replace(b"0.0", b"0.1", 1))
    with pytest.raises(LG.LedgerError, match="queue"):
        load_app(out, cache)
    q.write_bytes(original)
    m = out / S.MANIFEST_FILE
    mo = m.read_bytes()
    m.write_bytes(mo + b" ")
    with pytest.raises(LG.LedgerError, match="manifest"):
        load_app(out, cache)
    m.write_bytes(mo)
    z = np.load(cache)
    arrs = {k: z[k] for k in z.files}
    arrs["c"] = arrs["c"] + 0.01
    np.savez_compressed(cache, **arrs)
    with pytest.raises(LG.LedgerError, match="frame"):
        load_app(out, cache)


def test_a_missing_ledger_is_refused(tmp_path):
    res, fr, out, cache = built(tmp_path)
    (out / S.LEDGER_FILE).unlink()
    with pytest.raises(LG.LedgerError, match="missing"):
        load_app(out, cache)


# ------------------------------------------------------------------ key flow
def test_key_flow_records_labels_undoes_once_and_resumes(tmp_path):
    res, fr, out, cache = built(tmp_path)
    app = load_app(out, cache, "S1")
    ses = Session(app)
    assert keys(ses, "enter") == ["updated"] and "Press T or S" in ses.status_line() or ses.message
    assert not (out / S.LABELS_FILE).exists()
    assert keys(ses, "s", "enter")[-1] == "updated" and "reason" in ses.status_line()          # skip needs a reason
    assert not (out / S.LABELS_FILE).exists()
    assert keys(ses, "3", "enter") == ["updated", "committed"]
    assert LG.read_ledger(out)["first_label_written"] is True
    assert app.store.progress()["unique"] == 1
    assert keys(ses, "t", "b", "k", "2", "enter") == ["updated"] * 4 + ["committed"]
    assert app.store.progress()["takes"] == 1
    assert keys(ses, "u") == ["undone"] and app.store.progress()["takes"] == 0
    assert keys(ses, "u") == ["updated"] and ses.message                                         # undo only once
    keys(ses, "s", "7")
    assert ses.mode == "note"
    keys(ses, "e", "v", "space", "x")
    assert keys(ses, "enter") == ["committed"]
    app2 = load_app(out, cache, "S2")
    assert app2.store.next_seq == 2 and app2.store.progress()["unique"] == 2
    lab = (out / S.LABELS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lab) == 1 + 4 and "ev x" in lab[-1]


def test_the_last_candidate_ends_the_session_cleanly(tmp_path):
    res, fr, out, cache = built(tmp_path)
    app = load_app(out, cache, "S1")
    ses = Session(app)
    for _ in range(len(app.store.items)):
        keys(ses, "s", "1", "enter")
    assert app.store.done and app.current() is None
    assert keys(ses, "t") == ["ignored"]
    assert "close this window" in ses.status_line()


# ------------------------------------------------------------------ the window, headless
class Ev:
    def __init__(self, key):
        self.key = key


def test_the_window_draws_reacts_to_keys_and_leaks_nothing(tmp_path):
    res, fr, out, cache = built(tmp_path)
    app = load_app(out, cache, "S1")
    fig = R.new_figure()
    win = gui.LabelWindow(fig, app)
    before = R.figure_texts(fig)
    for k in ("s", "2", "enter"):
        win.on_key(Ev(k))
    assert app.store.progress()["unique"] == 1
    ids = [i.candidate_id for i in res["items"]]
    blob = " ".join(R.figure_texts(fig))
    for cid in ids[:50]:
        assert cid not in blob and cid[:10] not in blob
    assert "Labelled 1 of" in blob
    win.on_key(Ev("u"))
    assert app.store.progress()["unique"] == 0
    win.on_key(Ev(None))                                                                          # harmless
