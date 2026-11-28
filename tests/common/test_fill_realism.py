#!/usr/bin/env python3
r"""tests/common/test_fill_realism.py

Synthetic bars and synthetic logs only -- no tape. Checks the arithmetic and
the definitions fixed in common/fill_realism.py, not any real result.
"""
from __future__ import annotations

import csv
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from common import fill_realism as F

ET = ZoneInfo("America/New_York")


def _bars(rows):
    """rows: (hh, mm, open, high, low, close, volume) on 2026-09-11, ET."""
    idx = [pd.Timestamp(datetime(2026, 9, 11, h, m, tzinfo=ET)) for h, m, *_ in rows]
    return pd.DataFrame([r[2:] for r in rows], index=idx,
                        columns=["open", "high", "low", "close", "volume"])


def _row(book="MCL", et="05:40", px=2.00, xpx=2.20, net=18.0, reason="trailing_stop"):
    return {"book": book, "symbol": "ABC", "date": "2026-09-11", "entry_et": et,
            "entry_px": px, "exit_px": xpx, "net": net, "reason": reason, "exit_et": "05:50"}


def test_gap_buckets_edges():
    assert F.gap_bucket(None) == "no print"
    assert F.gap_bucket(-0.02) == "open <= trigger"
    assert F.gap_bucket(0.0) == "open <= trigger"
    assert F.gap_bucket(0.0001) == "0-1% above"
    assert F.gap_bucket(0.01) == "0-1% above"
    assert F.gap_bucket(0.0101) == "1-3% above"
    assert F.gap_bucket(0.03) == "1-3% above"
    assert F.gap_bucket(0.0301) == ">3% above"


def test_entry_bar_is_the_bar_after_the_signal_close_mcl():
    bars = _bars([(5, 39, 1.9, 2.0, 1.9, 1.99, 5000),
                  (5, 40, 1.99, 2.01, 1.98, 2.00, 5000),       # signal bar, closes 05:41
                  (5, 41, 2.10, 2.15, 2.05, 2.12, 5000)])      # entry bar
    m = F.measure_trade(bars, _row(), None)
    assert abs(m["gap"] - (2.10 / 2.00 - 1)) < 1e-9
    assert m["bucket"] == ">3% above"
    assert m["missed"] is True                                 # low 2.05 > 2.00*1.002
    assert m["depth_ok"] is False


def test_mc5_signal_bar_is_five_minutes_long():
    bars = _bars([(5, 40, 2.0, 2.0, 2.0, 2.0, 100),
                  (5, 44, 2.0, 2.0, 2.0, 2.0, 100),
                  (5, 45, 1.99, 2.01, 1.98, 2.00, 5000)])      # entry bar for a 05:40 MC5 signal
    m = F.measure_trade(bars, _row(book="MC5"), None)
    assert m["bucket"] == "open <= trigger"
    assert m["missed"] is False
    assert m["depth_ok"] is True


def test_no_print_when_nothing_trades_soon_after():
    bars = _bars([(5, 40, 1.99, 2.01, 1.98, 2.00, 5000),
                  (5, 50, 2.00, 2.01, 1.98, 2.00, 5000)])
    m = F.measure_trade(bars, _row(), None)
    assert m["bucket"] == "no print" and m["missed"] is True and m["gap"] is None


def test_over10_uses_bar_before_signal_bar():
    bars = _bars([(5, 39, 1.50, 1.50, 1.50, 1.50, 100),        # previous bar close 1.50
                  (5, 40, 1.50, 2.02, 1.50, 2.00, 9000),
                  (5, 41, 2.00, 2.00, 2.00, 2.00, 9000)])
    assert F.measure_trade(bars, _row(), None)["over10"] is True
    bars2 = _bars([(5, 39, 1.95, 1.95, 1.95, 1.95, 100),
                   (5, 40, 1.95, 2.02, 1.95, 2.00, 9000),
                   (5, 41, 2.00, 2.00, 2.00, 2.00, 9000)])
    assert F.measure_trade(bars2, _row(), None)["over10"] is False


def test_spike_window_and_depth():
    # first +10% bar starts 05:36 -> window for a signal CLOSE is 05:37..05:40
    bars = _bars([(5, 35, 1.00, 1.00, 1.00, 1.00, 100),
                  (5, 36, 1.00, 1.30, 1.00, 1.25, 9000),
                  (5, 39, 1.9, 2.0, 1.9, 1.99, 5000),
                  (5, 40, 1.99, 2.01, 1.98, 2.00, 5000),       # signal bar closes 05:41: outside
                  (5, 41, 2.00, 2.01, 1.99, 2.00, 5000)])
    assert F.measure_trade(bars, _row(et="05:40"), None)["spike3"] is False
    assert F.measure_trade(bars, _row(et="05:39"), None)["spike3"] is True    # closes 05:40
    thin = _bars([(5, 36, 1.00, 1.30, 1.00, 1.25, 9000),
                  (5, 38, 1.9, 2.0, 1.9, 1.99, 5000),
                  (5, 39, 1.99, 2.01, 1.98, 2.00, 400)])        # entry bar volume 400 < 1000
    m = F.measure_trade(thin, _row(et="05:38"), None)
    assert m["spike3"] is True and m["depth_ok"] is False


def test_luld_tiers_and_distance():
    assert abs(F.luld_upper(4.00) - 4.40) < 1e-9
    assert abs(F.luld_upper(2.00) - 2.40) < 1e-9
    assert abs(F.luld_upper(0.50) - 0.65) < 1e-9
    bars = _bars([(9, 40, 4.30, 4.40, 4.30, 4.38, 5000),
                  (9, 41, 4.38, 4.40, 4.35, 4.39, 5000)])
    m = F.measure_trade(bars, _row(et="09:40", px=4.38, xpx=4.20), 4.00)
    assert abs(m["luld_dist"] - (4.40 - 4.38) / 4.38) < 1e-9
    pre = F.measure_trade(_bars([(5, 40, 2, 2, 2, 2, 100), (5, 41, 2, 2, 2, 2, 100)]),
                          _row(), 1.00)
    assert pre["luld_dist"] is None                            # pre-market: no LULD


def test_cost_fields_and_buckets_add_up():
    r1 = lambda e, x, q, leg: 1.0 if leg == "TRAIL" else 2.0          # noqa: E731
    c = F.cost_fields(_row(), r1)
    assert abs(c["gross"] - 20.0) < 1e-9 and abs(c["commission"] - 2.0) < 1e-9
    assert abs(c["net_r1"] - 17.0) < 1e-9
    assert F.cost_fields(_row(reason="window_close"), r1)["r1"] == 2.0
    rows = [{**_row(), **c, "bucket": "0-1% above"}, {**_row(net=-5.0), **F.cost_fields(_row(net=-5.0), r1),
                                                      "bucket": ">3% above"}]
    a = F.agg(rows)
    assert a["n"] == 2 and a["wins"] == 1 and a["losses"] == 1
    assert abs(a["net_r1"] - (17.0 + -6.0)) < 1e-9             # (5) engine net less R1 of 1


def test_live_join(tmp_path):
    fills = tmp_path / "mcl_fills_20260911.csv"
    cols = ["ts_et", "strategy", "symbol", "action", "reason", "status", "reject_reason"]
    with fills.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerow(["2026-09-11 05:41:02", "MCL", "ABC", "BUY", "entry_signal", "NO_FILL_ABANDONED", ""])
        w.writerow(["2026-09-11 06:10:02", "MCL", "XYZ", "BUY", "entry_signal", "SKIPPED_DRIFT", ""])
        w.writerow(["2026-09-11 06:20:02", "MCL", "ABC", "SELL", "trailing_stop", "NO_FILL_ABANDONED", ""])
        w.writerow(["2026-09-30 06:20:02", "MCL", "ABC", "BUY", "entry_signal", "NO_FILL_CANCELLED", ""])
        w.writerow(["2026-09-08 06:20:02", "MCL", "ABC", "BUY", "entry_signal", "NO_FILL_CANCELLED", ""])
    sims = tmp_path / "live_vs_sim_trades.csv"
    with sims.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "strategy", "group", "symbol", "date", "live_entry", "sim_entry", "live_pnl",
                    "sim_net", "dt_min", "live_entry_px", "sim_entry_px", "live_exit_px", "sim_exit_px",
                    "live_reason", "sim_reason", "class"])
        w.writerow(["sim-only", "mcl", "all", "ABC", "2026-09-11", "", "05:40", "", "12.5", "", "", "2.0", "", "2.2",
                    "", "trailing_stop", ""])
        w.writerow(["live-only", "mcl", "all", "XYZ", "2026-09-11", "06:10:01", "", "1", "", "", "", "", "", "", "", "", ""])
    sig, counts = F.read_live_signals(str(tmp_path / "*_fills_*.csv"), "2026-09-10")
    assert len(sig) == 3                                       # 09-08 dropped, SELL counted apart
    assert counts[("SELL", "NO_FILL_ABANDONED")] == 1
    sim, last = F.read_sim(str(sims))
    assert last == "2026-09-11" and len(sim) == 1               # live-only is not a sim trade
    j = F.join_live(sig, sim, last)
    assert len(j["booked"]) == 1 and j["booked"][0][1]["sim_net"] == 12.5
    assert len(j["unbooked"]) == 1 and len(j["outside"]) == 1
    text = "\n".join(F.live_block(sig, counts, j, last, "2026-09-10"))
    assert "12.50" in text and "OUTSIDE COVERAGE" in text


# --- two fill folders: the PC's and the NAS mirror ---------------------------

COLS = ["ts_et", "strategy", "symbol", "action", "reason", "status", "reject_reason"]


def _log(folder, day, rows):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"mcl_fills_{day.replace('-', '')}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for clock, symbol, action, status in rows:
            w.writerow([f"{day} {clock}", "MCL", symbol, action, "entry_signal", status, ""])


def _two(tmp_path):
    pc, nas = tmp_path / "fills", tmp_path / "nas_mirror" / "fills"
    globs = [str(pc / "*_fills_*.csv"), str(nas / "*_fills_*.csv")]
    return pc, nas, globs


def test_both_folders_are_the_default():
    fills = F.build_parser().parse_args([]).fills
    assert [f.replace("\\", "/") for f in fills] == [
        "var/fills/*_fills_*.csv", "var/nas_mirror/fills/*_fills_*.csv"]
    assert F.build_parser().parse_args(["--fills", "a", "b"]).fills == ["a", "b"]


def test_nas_only_days_count_and_a_promoted_copy_counts_once(tmp_path):
    pc, nas, globs = _two(tmp_path)
    day = [("05:41:02", "ABC", "BUY", "NO_FILL_CANCELLED"),
           ("05:55:00", "ABC", "SELL", "NO_FILL_ABANDONED")]
    _log(pc, "2026-11-09", day)
    _log(nas, "2026-11-09", day)                                  # identical, promoted copy
    _log(nas, "2026-11-12", [("06:10:00", "XYZ", "BUY", "SKIPPED_DRIFT")])
    info: dict = {}
    sig, counts = F.read_live_signals(globs, "2026-09-10", info=info)
    assert [(s["date"], s["symbol"]) for s in sig] == [("2026-11-09", "ABC"), ("2026-11-12", "XYZ")]
    assert counts[("SELL", "NO_FILL_ABANDONED")] == 1
    assert info["days"] == 2 and info["merged"] == [] and info["left_out"] == []
    assert list(info["matched"].values()) == [1, 2]


def test_dry_sessions_are_left_out_and_the_paper_copy_stays(tmp_path):
    pc, nas, globs = _two(tmp_path)
    _log(nas, "2026-11-04", [("06:00:00", "DRY1", "BUY", "SKIPPED_DRIFT"),
                             ("06:01:00", "DRY1", "BUY", "DRY_RUN")])
    _log(pc, "2026-10-30", [("06:00:00", "PCX", "BUY", "NO_FILL_CANCELLED")])
    _log(nas, "2026-10-30", [("06:00:03", "PCX", "BUY", "DRY_RUN"),      # shadow run
                             ("06:00:05", "PCX", "BUY", "SKIPPED_DRIFT")])
    info: dict = {}
    sig, _ = F.read_live_signals(globs, "2026-09-10", info=info)
    assert [s["symbol"] for s in sig] == ["PCX"] and sig[0]["tag"] == "NO_FILL_CANCELLED"
    assert len(info["left_out"]) == 2 and all(x.endswith("(dry)") for x in info["left_out"])
    assert info["days"] == 1 and info["merged"] == []
    assert any("Left out (2" in line for line in F.source_lines(info))


def test_differing_copies_are_merged_once_per_row_and_named(tmp_path):
    pc, nas, globs = _two(tmp_path)
    first = ("05:41:02", "ABC", "BUY", "NO_FILL_CANCELLED")
    later = ("07:00:00", "DEF", "BUY", "SKIPPED_DRIFT")
    _log(pc, "2026-11-12", [first])                               # copied mid-session
    _log(nas, "2026-11-12", [first, later, later])                # a repeated row is kept twice
    info: dict = {}
    sig, counts = F.read_live_signals(globs, "2026-09-10", info=info)
    assert [s["symbol"] for s in sig] == ["ABC", "DEF", "DEF"]
    assert counts[("BUY", "NO_FILL_CANCELLED")] == 1
    assert info["merged"] == ["mcl_fills_20261112.csv"]
    assert any("CHECK" in line for line in F.source_lines(info))


def test_a_folder_with_no_files_is_said_out_loud(tmp_path):
    pc, _, globs = _two(tmp_path)
    _log(pc, "2026-11-09", [("05:41:02", "ABC", "BUY", "NO_FILL_CANCELLED")])
    info: dict = {}
    F.read_live_signals(globs, "2026-09-10", info=info)
    assert any("NO FILES match" in line and "nas_mirror" in line for line in F.source_lines(info))


def test_live_only_run_prints_the_sources(tmp_path):
    pc, nas, globs = _two(tmp_path)
    _log(pc, "2026-11-09", [("05:41:02", "ABC", "BUY", "NO_FILL_CANCELLED")])
    _log(nas, "2026-11-12", [("06:10:00", "XYZ", "BUY", "SKIPPED_DRIFT")])
    out = tmp_path / "r.txt"
    assert F.main(["--live-only", "--fills", *globs, "--out", str(out),
                   "--live-sim", str(tmp_path / "none.csv")]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Day files used: 2." in text and "total 2" in text
