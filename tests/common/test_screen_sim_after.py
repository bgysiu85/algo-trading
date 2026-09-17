#!/usr/bin/env python3
"""`screen_sim --after`: extend the universe over new slices without touching
the file every point-in-time result was decided on."""
from __future__ import annotations

import pytest

from common import screen_sim as S


def test_after_refuses_the_deciding_output_path():
    assert S.after_refusal("2026-09-05", "var/state/screen_pairs_pit.json")
    assert S.after_refusal("2026-09-05", "var\\state\\screen_pairs_pit.json")
    assert S.after_refusal("2026-09-05", "var/state/screen_pairs_pit_ext.json") is None
    assert S.after_refusal(None, "var/state/screen_pairs_pit.json") is None


def test_after_filters_slices_by_date_in_the_cli(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(S, "window_slices",
                        lambda archive, ds: [tmp_path / f"{d}_0400_0930.dbn.zst"
                                             for d in ("2026-09-03", "2026-09-05", "2026-09-08")])

    def fake_daily_frame(archive, ds):
        seen["daily"] = True
        raise SystemExit("stop here")            # past the filter, before any reading

    monkeypatch.setattr("common.dbn_io.daily_frame", fake_daily_frame)
    with pytest.raises(SystemExit) as e:
        S.main(["--after", "2026-09-05", "--out", str(tmp_path / "ext.json"), "--archive", str(tmp_path)])
    assert "stop here" in str(e.value) and seen.get("daily")
    with pytest.raises(SystemExit) as e:
        S.main(["--after", "2026-09-05", "--archive", str(tmp_path)])
    assert "decided on" in str(e.value)
