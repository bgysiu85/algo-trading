#!/usr/bin/env python3
"""G2 -- HTF-Ben v2 pre-flight (training side only, NO EXIT PRICES, NO P&L,
NO TRADE SIMULATION). W15-0021, REGISTERED_htf_ben_v2.md sec 5.1 (gate G2),
sec 5.2.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.v2_preflight

WHAT THIS ANSWERS, AND WHY IT IS v1's OWN NUMBERS, RELABELLED
------------------------------------------------------------------
v2's entries are v1's, unchanged (sec 2.1: "Nothing about the entry side is
re-opened, re-tuned, or re-derived for v2"), and q_h/q_e are inherited from
v1 Amendment C, not recomputed (sec 2.1). v1_preflight.detect_v1 -- the one
function that produces the pre-E5 candidate list G2 is allowed to look at
-- reads no exit rule at all (v0/v1's own preflight modules' shared
convention: "E5 is NOT APPLIED HERE ... needs exit simulation, which this
gate is forbidden from doing"). Calling detect_v1 with v2's inherited
q_h/q_e and v1's own registered defaults (cross_window=3, swing_LR=2) is
therefore BYTE-FOR-BYTE the same call v1_preflight.py's own G2 already
made -- there is nothing for a separate v2 entry-detection pass to
discover that v1's G2 didn't already report (proved, not just claimed, by
tests/strategy/htf/test_v2_preflight.py's own equality check against a
direct v1_preflight.detect_v1 call).

This module exists anyway (rather than pointing Ben at v1_preflight.py's
own report) for two reasons: (1) it is where the 150-entries-on-B stop rule
(sec 5.2) is checked for v2 BY NAME, so a v2 run's own gate history doesn't
depend on remembering v1's; (2) sec 5.2's own text flags that v2's
REALIZED TRADE COUNT (after v0's longer-holding exits interact with E5) is
expected to land close to, but not necessarily equal to, 286 -- that number
is exit-dependent and cannot be read off this gate (this gate reads no
exit price, so it cannot run E5 for real); it is only checked once
v2_report.py runs the full engine (see that module's
originating_trade_count_check).

WHAT THIS DOES NOT DO
----------------------
No exit simulation, no E5, no P&L -- identical restriction to
preflight.py's and v1_preflight.py's own G2 modules. It does not tell you
whether v2 clears its bar; only v2_report.py does that.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy.htf import bars as B
from strategy.htf import preflight as P
from strategy.htf import v1_preflight as V1P

SCENARIO = "B"                 # sec 2.3: "Scenario B ... is the sole scenario in scope"
MIN_ENTRIES = P.MIN_ENTRIES    # 150 -- sec 5.2's stop rule, same threshold as v0/v1

# REGISTERED_htf_ben_v2.md sec 2.1: inherited unchanged from
# REGISTERED_htf_ben_v1.md Amendment C -- NOT recomputed here or anywhere
# in v2 (module docstring).
Q_H = 0.190280
Q_E = 0.501239


def run(archive_1h) -> dict:
    """v2's entries on B, training side -- identical call to v1's own G2
    (module docstring): same detect_v1, same q_h/q_e, same defaults. Kept
    as its own function (not a re-export of v1_preflight.run) so the stop
    rule below is checked and reported under v2's own name."""
    df_1h = B.load_1h(archive_1h)
    grids, daily_adj = P.prepare_grids(df_1h)
    entry_adj = grids[P.SCENARIO_GRID[SCENARIO]]
    four_h_adj = grids["4H"]

    entries, counts = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario=SCENARIO,
                                    q_h=Q_H, q_e=Q_E)
    summary = P.summarize(entries, counts, scenario=SCENARIO)
    entries_training = summary["totals"]["entries_training"]
    underpowered = entries_training < MIN_ENTRIES
    return {
        "note": ("v2's entries are v1's, unchanged, with q_h/q_e inherited "
                "from v1 Amendment C -- this is BYTE-FOR-BYTE the same "
                "detect_v1 call v1_preflight.py's own G2 already made "
                "(module docstring). The 286-trade figure this hypothesis "
                "is built from (REGISTERED sec 0.2) is a realized, "
                "post-E5 TRADE count under v0's exits, not an entries "
                "count -- it cannot be read off this gate and is only "
                "checked by v2_report.py's full run."),
        "q_h": Q_H, "q_e": Q_E, "scenario": SCENARIO,
        "counts_full_history": counts,
        **summary,
        "stop_rule": {
            "v2_B_entries_training": entries_training,
            "min_required": MIN_ENTRIES,
            "underpowered": underpowered,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G2: HTF-Ben v2 pre-flight (no P&L).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run(archive)
    t = report["totals"]
    sr = report["stop_rule"]
    print("G2 -- HTF-Ben v2 pre-flight (training side, no P&L, no exit prices, no E5)\n")
    print(f"q_h={report['q_h']:.6f}  q_e={report['q_e']:.6f}  (inherited from v1 Amendment C)\n")
    print(f"B  cross={t['triggers_cross']:5d}  curl={t['triggers_curl']:5d}  "
          f"curl_fail_T={t['curl_failing_t']:5d}  lapsed={t['lapsed']:5d}  "
          f"f1_blk={t['blocked_f1']:5d}  f2_blk={t['blocked_f2']:5d}  "
          f"e3_blk={t['blocked_e3']:5d}  eos_blk={t['blocked_end_of_session']:5d}  "
          f"voided={t['voided']:4d}  entries(training)={t['entries_training']:5d}")
    print(f"\nstop rule (sec 5.2): v2 B entries(training)={sr['v2_B_entries_training']} "
          f"(need >= {sr['min_required']}) -> "
          f"{'UNDERPOWERED' if sr['underpowered'] else 'OK'}")
    print(f"\n{report['note']}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    return 1 if sr["underpowered"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
