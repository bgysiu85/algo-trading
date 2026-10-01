"""G4: the label file is append-only, one row per decision, resumable, undo-able once, and tied to the queue."""
import csv

import pytest

from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.labels import LabelError, LabelStore
from strategy.chartmark_clone.qorder import Item


def items(n=40, repeat_at=None):
    out = [Item(i, i, False, f"c{i:04d}") for i in range(n)]
    if repeat_at is not None:
        out.append(Item(n, repeat_at, True, f"c{repeat_at:04d}"))
    return out


def rows(path):
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_header_then_one_row_per_decision_and_the_file_only_grows(tmp_path):
    p = tmp_path / "labels.csv"
    st = LabelStore(p, items(), "S1")
    prev = b""
    for i in range(6):
        if i % 2:
            st.add(i, "SKIP", skip_reason=str(1 + i % 6), ms=1200 + i)
        else:
            st.add(i, "TAKE", take_reason="A", confidence="2", ms=900)
        cur = p.read_bytes()
        assert cur.startswith(prev) and len(cur) > len(prev)                    # append-only: earlier bytes never change
        prev = cur
    r = rows(p)
    assert len(r) == 6 and list(r[0].keys()) == S.LABEL_COLUMNS
    assert S.LABEL_COLUMNS[:11] == ["candidate_id", "queue_pos", "is_repeat", "label", "skip_reason", "take_reason", "note",
                                    "confidence", "ms_to_decide", "sitting_id", "labelled_at_utc"]
    assert [x["seq"] for x in r] == [str(i) for i in range(6)]
    assert {x["sitting_id"] for x in r} == {"S1"} and r[0]["label"] == "TAKE" and r[1]["label"] == "SKIP"
    assert p.read_text(encoding="utf-8").count("candidate_id,queue_pos") == 1     # header once


def test_validation_of_reasons_notes_and_order(tmp_path):
    st = LabelStore(tmp_path / "l.csv", items(), "S1")
    with pytest.raises(LabelError, match="reason"):
        st.add(0, "SKIP")
    with pytest.raises(LabelError, match="Other"):
        st.add(0, "SKIP", skip_reason="7", note="  ")
    with pytest.raises(LabelError):
        st.add(0, "SKIP", skip_reason="9")
    with pytest.raises(LabelError):
        st.add(0, "TAKE", skip_reason="1")
    with pytest.raises(LabelError):
        st.add(0, "TAKE", take_reason="Z")
    with pytest.raises(LabelError):
        st.add(0, "TAKE", confidence="5")
    with pytest.raises(LabelError, match="on screen"):
        st.add(1, "TAKE")                                                       # not the candidate on screen
    with pytest.raises(LabelError):
        st.add(0, "MAYBE")
    assert not (tmp_path / "l.csv").exists()                                    # nothing was written by any refusal
    st.add(0, "SKIP", skip_reason="7", note="  wed   report  ")
    assert rows(tmp_path / "l.csv")[0]["note"] == "wed report"


def test_undo_appends_a_row_once_and_only_for_the_decision_just_made(tmp_path):
    p = tmp_path / "l.csv"
    st = LabelStore(p, items(), "S1")
    with pytest.raises(LabelError):
        st.undo()                                                               # nothing yet
    st.add(0, "TAKE")
    st.add(1, "SKIP", skip_reason="1")
    assert st.can_undo
    row = st.undo()
    assert row["label"] == "UNDO" and row["seq"] == 1 and st.next_seq == 1
    with pytest.raises(LabelError):
        st.undo()                                                               # no chain of undos
    st.add(1, "SKIP", skip_reason="3")                                          # the same candidate again
    st.add(2, "TAKE")
    assert [x["label"] for x in rows(p)] == ["TAKE", "SKIP", "UNDO", "SKIP", "TAKE"]
    assert st.can_undo
    st.add(3, "TAKE")
    st.undo()                                                                   # only the newest decision is undoable ...
    with pytest.raises(LabelError):
        st.undo()                                                               # ... never the one before it
    assert st.next_seq == 3
    st.add(3, "SKIP", skip_reason="4")
    fresh = LabelStore(p, items(), "S2")                                        # a new sitting cannot undo an old decision
    assert not fresh.can_undo and fresh.next_seq == 4
    with pytest.raises(LabelError):
        fresh.undo()


def test_resume_picks_up_at_the_right_place_and_uses_the_last_non_undo_row(tmp_path):
    p = tmp_path / "l.csv"
    a = LabelStore(p, items(), "S1")
    a.add(0, "TAKE")
    a.add(1, "SKIP", skip_reason="2")
    a.undo()
    a.add(1, "SKIP", skip_reason="5")
    b = LabelStore(p, items(), "S2")
    assert b.next_seq == 2
    assert [e["skip_reason"] for e in b.effective] == ["", "5"]
    b.add(2, "TAKE")
    assert LabelStore(p, items(), "S3").next_seq == 3


def test_the_file_is_tied_to_the_queue(tmp_path):
    p = tmp_path / "l.csv"
    LabelStore(p, items(), "S1").add(0, "TAKE")
    changed = items()
    changed[0] = Item(0, 0, False, "c9999")
    with pytest.raises(LabelError, match="queue"):
        LabelStore(p, changed, "S2")
    p2 = tmp_path / "l2.csv"
    p2.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(LabelError, match="header"):
        LabelStore(p2, items(), "S1")


def test_progress_counts_first_labels_only_and_the_stop_rule_uses_counts(tmp_path):
    n = S.MAX_UNIQUE + 5
    its = items(n, repeat_at=3)
    st = LabelStore(tmp_path / "l.csv", its, "S1")
    for i in range(S.MIN_UNIQUE):
        st.add(i, "TAKE" if i < S.MIN_TAKES - 1 else "SKIP", skip_reason="" if i < S.MIN_TAKES - 1 else "3")
    p = st.progress()
    assert p["unique"] == S.MIN_UNIQUE and p["takes"] == S.MIN_TAKES - 1 and not p["enough"]      # 500 labels, 59 takes
    st.add(S.MIN_UNIQUE, "TAKE")
    p = st.progress()
    assert p["takes"] == S.MIN_TAKES and p["enough"]                                             # 501 labels, 60 takes
    st2 = LabelStore(tmp_path / "l2.csv", its, "S1")
    for i in range(S.MAX_UNIQUE - 1):
        st2.add(i, "SKIP", skip_reason="1")
    assert not st2.progress()["enough"]
    st2.add(S.MAX_UNIQUE - 1, "SKIP", skip_reason="1")
    assert st2.progress()["enough"] and st2.progress()["takes"] == 0


def test_repeats_are_recorded_but_do_not_count_as_unique(tmp_path):
    its = items(12, repeat_at=3)                       # seq 12 = a repeat of queue position 3
    st = LabelStore(tmp_path / "l.csv", its, "S1")
    for i in range(12):
        st.add(i, "TAKE" if i == 3 else "SKIP", skip_reason="" if i == 3 else "1")
    st.add(12, "SKIP", skip_reason="2")                # Ben changes his mind on the repeat
    r = rows(tmp_path / "l.csv")
    assert r[-1]["is_repeat"] == "1" and r[-1]["queue_pos"] == "3" and r[-1]["candidate_id"] == "c0003"
    p = st.progress()
    assert p["unique"] == 12 and p["takes"] == 1 and p["repeats"] == 1 and p["done"]
    with pytest.raises(LabelError):
        st.add(13, "TAKE")
