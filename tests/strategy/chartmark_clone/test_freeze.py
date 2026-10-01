"""Sub 4 freeze: the ledger records the label hash once, the labelling tool then refuses, the fit refuses a second freeze,
and no fit module opens an outcome file."""
import json

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import fit as FI
from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import spec as S
from tests.strategy.chartmark_clone.test_clone import synth


def ledger(tmp_path):
    rec = dict(study=S.STUDY, queue_sha256="q", manifest_sha256="m", frame_content_sha256="f",
               first_label_written=True, labels_sha256=None, clone_frozen_sha256=None, outcome_run_done=False)
    (tmp_path / S.LEDGER_FILE).write_text(json.dumps(rec), encoding="utf-8")
    return tmp_path


def test_mark_frozen_is_once_and_closes_the_labels(tmp_path):
    out = ledger(tmp_path)
    LG.check_labels_open(out)                                       # open before the freeze
    LG.mark_frozen(out, "abc", "def")
    led = LG.read_ledger(out)
    assert led["labels_sha256"] == "abc" and led["clone_frozen_sha256"] == "def" and led["frozen_utc"]
    with pytest.raises(LG.LedgerError):
        LG.check_labels_open(out)
    with pytest.raises(LG.LedgerError):
        LG.mark_frozen(out, "x", "y")


def test_the_labelling_tool_checks_the_labels_are_still_open():
    from pathlib import Path
    src = (Path(FI.__file__).with_name("label.py")).read_text(encoding="utf-8")
    assert "check_labels_open" in src


def test_choose_follows_the_registered_order():
    ok = dict(meets_bar=True)
    no = dict(meets_bar=False)
    assert FI.choose({"R": ok, "M": no, "M-GB": no}) == ("R", True)
    assert FI.choose({"R": no, "M": ok, "M-GB": no}) == ("M", True)
    assert FI.choose({"R": no, "M": no, "M-GB": ok}) == ("M", False)        # M-GB can never become the clone


def test_brackets_for_negatives_and_percent():
    assert FI.br(-0.123) == "(0.123)" and FI.br(0.5) == "0.500" and FI.pct(-0.05) == "(5.0%)" and FI.pct(0.538) == "53.8%"


def test_fit_and_report_run_end_to_end_on_synthetic_labels():
    df = synth(300)
    cv = {n: dict(CL.summarise(df, p), catch_by_reason=CL.reason_catch(df, p)) for n, p in CL.cv_predictions(df, repeats=2).items()}
    for v in cv.values():
        v["meets_bar"] = CL.meets_bar(v["mean"]["recall"], v["mean"]["precision"], 0.54)
    d = df.copy()
    d["candidate_id"] = [str(x) for x in pd.date_range("2015-01-05 09:00", periods=len(d), freq="D")]
    d["label"] = np.where(d["y"] == 1, "TAKE", "SKIP")
    d["year"] = 2015
    d["seq"] = np.arange(len(d)).astype(str)
    d["ms_to_decide"] = "3000"
    d["sitting_id"] = "S1"
    d["note"] = ""
    d["take_reason"] = np.where(d["y"] == 1, "A", "")
    stats = FI.label_stats(d, pd.DataFrame({"candidate_id": [], "label": []}))
    stats["consistency"] = dict(n_repeats=40, n_first_take=13, take_again=7, take_consistency=7 / 13, take_ci=(0.29, 0.77),
                                n_first_skip=27, skip_again=26, skip_consistency=26 / 27, agreement=0.825)
    which, met = FI.choose(cv)
    rules, notes = CL.fit_rules(d)
    text = FI.report(stats, cv, which, met, rules, notes)
    assert "FIDELITY" in text and "RULE 3" in text and "no price outcome" in text


def test_the_feature_table_round_trips_exactly_so_the_gb_refit_is_reproducible(tmp_path):
    rng = np.random.default_rng(0)
    t = pd.DataFrame({"F5": rng.normal(size=50) / 3.0, "F9": rng.integers(0, 12, 50).astype(float)})
    t.loc[3, "F5"] = np.nan
    p = tmp_path / "t.csv"
    t.to_csv(p, index=False, lineterminator="\n", encoding="utf-8", float_format="%.17g")
    back = pd.read_csv(p, float_precision="round_trip")
    assert np.array_equal(t.to_numpy(float), back.to_numpy(float), equal_nan=True)
    import re
    from pathlib import Path
    assert re.search(r'float_format="%\.17g"', Path(FI.__file__).read_text(encoding="utf-8"))
