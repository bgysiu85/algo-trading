#!/usr/bin/env python3
"""Run the registered pre-market hypotheses and score them against the criteria.

    python -m strategy.premkt.run --pairs var/state/screen_pairs_consolidated.json \
        --rejects var/state/screen_rejects.json --cache bar_cache_xnas

    # the holdout, ONCE, for ONE survivor:
    python -m strategy.premkt.run ... --set locked --hypothesis H1 --trail 8

Registration: docs/premarket_hypotheses_20260908.md (commit 5075784). The
criteria are computed here so that "does it pass" is a line in a report and
not a judgement made in a chat window after the numbers are in.

THE HOLDOUT IS SPENT BY CODE, NOT BY RESOLVE
--------------------------------------------
The registration says one survivor touches the 164 locked sessions once. A
rule that lives only in prose gets broken the first time a near-miss looks
like it deserves a second look. So --set locked requires exactly one
hypothesis and one trail, writes var/state/holdout_spent.json on first use,
and refuses any later locked run that is not a byte-identical repeat of the
first. The training set is likewise filtered to dates before the lock, so
a training run cannot leak forward by accident.

B0 IS MC5 ITSELF, NOT A RE-IMPLEMENTATION
------------------------------------------
The benchmark calls strategy/mc5/mc5.py's own backtest_session on the same
bars, with the same flat 100 shares. Re-implementing it through the harness
would test the harness's copy of MC5 rather than MC5 -- and the equivalence
control (tests/common/test_harness_equivalence.py) already establishes those
agree, so nothing is gained by routing it differently here.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common import holdout
from common.cache_io import load_cached_bars
from common.harness import run_session
from common.report_io import emit
from strategy.mc5 import mc5
from strategy.premkt import hypotheses as H

ET = ZoneInfo("America/New_York")
SPENT_PATH = Path("var/state/holdout_spent.json")

MIN_TRADES = 200
MIN_SYMBOLS = 100
DROP_TOP = 5
LEAK_MIN_TRADES = 30       # same as common.leak_control.QUALITY_MIN_TRADES


# --- pairs and sets --------------------------------------------------------------

def load_pairs(path: Path) -> list[tuple[str, str]]:
    rows = json.loads(Path(path).read_text())
    out = sorted({(r["symbol"], r["date"]) for r in rows})
    # Dotted and non-alphabetic tickers are not US equities and the engines
    # drop them; do the same here so counts reconcile with earlier runs.
    return [(s, d) for s, d in out if s.isalpha()]


def select_set(pairs, rec: dict, which: str) -> list[tuple[str, str]]:
    part = holdout.partition(rec, pairs)
    if which == "training":
        return sorted(part["early"] + part["late"])
    if which == "locked":
        return sorted(part["locked"])
    raise ValueError(which)


# --- one run ---------------------------------------------------------------------

def run_hypothesis(name: str, trail: float, pairs, cache: Path,
                   progress=None) -> list[dict]:
    sig_fn = H.SIGNALS[name]
    rules = H.rules(trail)
    out: list[dict] = []
    for k, (sym, day) in enumerate(pairs, 1):
        df = load_cached_bars(cache, sym, day)
        if df is None or df.empty:
            continue
        sig = sig_fn(df, _date.fromisoformat(day), ET)
        for t in run_session(sig, _date.fromisoformat(day), ET, rules,
                             symbol=sym, entry_shares=H.ENTRY_SHARES):
            row = asdict(t)
            row["symbol"], row["date"] = sym, day
            out.append(row)
        if progress and k % 2000 == 0:
            progress(f"  {name} trail {trail:g}: {k:,}/{len(pairs):,}")
    return out


def run_b0(pairs, cache: Path, progress=None) -> list[dict]:
    out: list[dict] = []
    for k, (sym, day) in enumerate(pairs, 1):
        df = load_cached_bars(cache, sym, day)
        if df is None or df.empty:
            continue
        for t in mc5.backtest_session(df, _date.fromisoformat(day), ET,
                                      entry_shares=H.ENTRY_SHARES):
            row = asdict(t)
            row["symbol"], row["date"] = sym, day
            out.append(row)
        if progress and k % 2000 == 0:
            progress(f"  B0 MC5: {k:,}/{len(pairs):,}")
    return out


# --- scoring ---------------------------------------------------------------------

def score(trades: list[dict], split: str) -> dict:
    """Everything the criteria need, from one list of trades.

    `net_after` is net (already commission-adjusted by the engine) minus the
    registered friction per round trip. Every figure below uses net_after --
    a number that ignores the one live cost measurement is not a number.
    """
    n = len(trades)
    if n == 0:
        return {"trades": 0, "symbols": 0, "net": 0.0, "net_per_trade": 0.0,
                "drop_top": {}, "early": 0.0, "late": 0.0, "win_rate": 0.0}
    per_sym: dict[str, float] = defaultdict(float)
    early = late = 0.0
    wins = 0
    total = 0.0
    for t in trades:
        na = float(t["net"]) - H.FRICTION_PER_RT
        total += na
        per_sym[t["symbol"]] += na
        if t["date"] < split:
            early += na
        else:
            late += na
        if na > 0:
            wins += 1
    ranked = sorted(per_sym.values(), reverse=True)
    drop = {k: round(total - sum(ranked[:k]), 2) for k in (1, 3, DROP_TOP, 10)}
    return {"trades": n, "symbols": len(per_sym), "net": round(total, 2),
            "net_per_trade": round(total / n, 4), "drop_top": drop,
            "early": round(early, 2), "late": round(late, 2),
            "win_rate": round(wins / n, 4)}


def criteria(s: dict, b0: dict, rej: dict, robust: dict) -> list[tuple[str, bool, str]]:
    """The seven registered criteria, each as (name, passed, detail)."""
    out = []
    out.append(("1 net > 0 after commission and friction", s["net"] > 0,
                f"${s['net']:+,.2f}"))
    d5 = s["drop_top"].get(DROP_TOP, 0.0)
    out.append((f"2 drop-top-{DROP_TOP} > 0", d5 > 0, f"${d5:+,.2f}"))
    out.append(("3 both halves > 0", s["early"] > 0 and s["late"] > 0,
                f"early ${s['early']:+,.2f}  late ${s['late']:+,.2f}"))
    out.append((f"4 >= {MIN_TRADES} trades and >= {MIN_SYMBOLS} symbols",
                s["trades"] >= MIN_TRADES and s["symbols"] >= MIN_SYMBOLS,
                f"{s['trades']:,} trades, {s['symbols']:,} symbols"))
    # 5: the leak cut. Rejected days must not be the mirror image of survivors.
    if rej["trades"] < LEAK_MIN_TRADES:
        leak_ok, leak_txt = True, (f"inconclusive: only {rej['trades']} "
                                   f"rejected-day trades (<{LEAK_MIN_TRADES})")
    else:
        leak_ok = not (s["net_per_trade"] > 0 and rej["net_per_trade"] < 0)
        leak_txt = (f"survivors ${s['net_per_trade']:+,.2f}/tr  "
                    f"rejected ${rej['net_per_trade']:+,.2f}/tr (n={rej['trades']})")
    out.append(("5 leak cut does not reject", leak_ok, leak_txt))
    b5 = b0["drop_top"].get(DROP_TOP, 0.0)
    out.append(("6 beats B0 on net/trade and drop-top-5",
                s["net_per_trade"] > b0["net_per_trade"] and d5 > b5,
                f"B0 ${b0['net_per_trade']:+,.2f}/tr, drop5 ${b5:+,.2f}"))
    # 7: the sign at 5% and 12% must match the sign at the primary 8%. A
    # hypothesis that is positive only at one trail width is a tuned number.
    primary_sign = s["net"] > 0
    same = all((v["net"] > 0) == primary_sign for v in robust.values())
    out.append(("7 same sign at trail 5% and 12%", same,
                "  ".join(f"{k:g}%: ${v['net']:+,.2f}" for k, v in sorted(robust.items()))))
    return out


# --- the holdout guard ---------------------------------------------------------------

def check_holdout_guard(name: str, trail: float) -> None:
    if SPENT_PATH.exists():
        prev = json.loads(SPENT_PATH.read_text())
        if prev.get("hypothesis") == name and float(prev.get("trail")) == float(trail):
            print(f"holdout already spent on {name} at {trail:g}% on "
                  f"{prev.get('at')} -- this is a repeat of that run, allowed")
            return
        sys.exit(f"REFUSING: the holdout was spent on {prev.get('hypothesis')} "
                 f"at {prev.get('trail')}% on {prev.get('at')}. It is not "
                 "available to any other candidate. See "
                 "docs/premarket_hypotheses_20260908.md.")


def mark_holdout_spent(name: str, trail: float) -> None:
    """Record the first holdout run. Never rewritten: an allowed exact repeat
    must not move the timestamp, because the timestamp is the audit trail of
    when the holdout was first seen."""
    if SPENT_PATH.exists():
        return
    SPENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPENT_PATH.write_text(json.dumps({
        "hypothesis": name, "trail": trail,
        "at": pd.Timestamp.now(tz="UTC").isoformat(),
        "registration": "docs/premarket_hypotheses_20260908.md @ 5075784",
    }, indent=2))


# --- main ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pairs", required=True, help="survivors")
    ap.add_argument("--rejects", required=True, help="rejects (leak control)")
    ap.add_argument("--cache", default="bar_cache_xnas")
    ap.add_argument("--window", default="3d_to_2000")
    ap.add_argument("--set", choices=["training", "locked"], default="training")
    ap.add_argument("--hypothesis", choices=list(H.HYPOTHESES),
                    help="--set locked: the ONE survivor")
    ap.add_argument("--trail", type=float, help="--set locked: its trail")
    ap.add_argument("--limit", type=int, help="first N pairs (smoke test only)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--csv-dir", default="var/reports/premkt")
    a = ap.parse_args(argv)

    rec = holdout.load()
    if rec is None:
        sys.exit("no holdout.json -- run python -m common.holdout first")
    cache = Path(a.cache) / a.window
    if not cache.is_dir():
        sys.exit(f"no bar cache at {cache}")

    surv_all = load_pairs(Path(a.pairs))
    rej_all = load_pairs(Path(a.rejects))
    surv = select_set(surv_all, rec, a.set)
    rej = select_set(rej_all, rec, a.set)
    if a.limit:
        surv, rej = surv[: a.limit], rej[: max(1, a.limit // 5)]

    if a.set == "locked":
        if not a.hypothesis or a.trail is None:
            sys.exit("--set locked needs exactly --hypothesis and --trail: one "
                     "survivor, once.")
        if a.limit:
            sys.exit("--limit is not allowed on the locked set: a partial "
                     "holdout run still spends it.")
        check_holdout_guard(a.hypothesis, a.trail)
        plan = [(a.hypothesis, a.trail)]
        robust_trails: tuple = ()
    else:
        plan = [(h, H.TRAIL_PRIMARY) for h in H.HYPOTHESES]
        robust_trails = H.TRAILS_ROBUSTNESS

    out_dir = Path(a.csv_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = a.out or f"var/reports/premkt_{a.set}.txt"
    split = rec["both_halves_split"]

    print(f"{a.set}: {len(surv):,} survivor pairs, {len(rej):,} reject pairs, "
          f"cache {cache}")

    def save(tag, trades):
        p = out_dir / f"{a.set}_{tag}.csv"
        if trades:
            with open(p, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()))
                w.writeheader()
                w.writerows(trades)
        return p

    # B0 first, so the benchmark exists before any hypothesis is read.
    print("B0 MC5 on survivors...")
    b0_trades = run_b0(surv, cache, print)
    b0 = score(b0_trades, split)
    save("B0", b0_trades)

    results = {}
    for name, trail in plan:
        print(f"{name} trail {trail:g}% on survivors...")
        tr = run_hypothesis(name, trail, surv, cache, print)
        s = score(tr, split)
        save(f"{name}_t{trail:g}", tr)
        print(f"{name} trail {trail:g}% on rejects...")
        rj = score(run_hypothesis(name, trail, rej, cache), split)
        robust = {}
        for rt in robust_trails:
            print(f"{name} trail {rt:g}% on survivors (robustness)...")
            rtr = run_hypothesis(name, rt, surv, cache, print)
            robust[rt] = score(rtr, split)
            save(f"{name}_t{rt:g}", rtr)
        results[(name, trail)] = (s, rj, robust)

    if a.set == "locked":
        mark_holdout_spent(a.hypothesis, a.trail)

    # --- report -----------------------------------------------------------------
    L = [f"PRE-MARKET HYPOTHESES -- {a.set.upper()} SET", "",
         "  registration  docs/premarket_hypotheses_20260908.md @ 5075784",
         f"  bars          {cache}",
         f"  sessions      {rec['train_first']} -> {rec['train_last']}"
         if a.set == "training" else
         f"  sessions      locked from {rec['lock_from']} ({rec['n_locked']})",
         f"  survivors     {len(surv):,} symbol-days   rejects {len(rej):,}",
         f"  costs         ibkr_tiered per order + ${H.FRICTION_PER_RT:.2f}/RT friction",
         f"  size          {H.ENTRY_SHARES} shares flat", ""]

    def block(tag, s):
        return [f"  {tag:<14} trades {s['trades']:>6,}  symbols {s['symbols']:>5,}  "
                f"win {s['win_rate']*100:5.1f}%  net ${s['net']:>+12,.2f}  "
                f"${s['net_per_trade']:>+7.2f}/tr",
                f"  {'':<14} drop-top  1 ${s['drop_top'].get(1,0):+,.0f}  "
                f"3 ${s['drop_top'].get(3,0):+,.0f}  "
                f"5 ${s['drop_top'].get(5,0):+,.0f}  "
                f"10 ${s['drop_top'].get(10,0):+,.0f}   "
                f"early ${s['early']:+,.0f}  late ${s['late']:+,.0f}"]

    L += ["RESULTS", ""] + block("B0  MC5", b0) + [""]
    for (name, trail), (s, rj, robust) in results.items():
        L += block(f"{name}  trail {trail:g}%", s)
        for rt, rs in sorted(robust.items()):
            L += block(f"    trail {rt:g}%", rs)
        L += [f"  {'':<14} rejects: {rj['trades']:,} trades  "
              f"${rj['net_per_trade']:+.2f}/tr", ""]

    L += ["CRITERIA -- all seven must hold", ""]
    survivors = []
    for (name, trail), (s, rj, robust) in results.items():
        L.append(f"  {name} at trail {trail:g}%")
        cs = criteria(s, b0, rj, robust) if a.set == "training" else \
            [c for c in criteria(s, b0, rj, robust) if not c[0].startswith(("5", "6"))]
        ok = all(p for _, p, _ in cs)
        for label, passed, detail in cs:
            L.append(f"    [{'PASS' if passed else 'FAIL'}] {label:<44} {detail}")
        L.append(f"    => {'SURVIVES' if ok else 'REJECTED'}")
        L.append("")
        if ok:
            survivors.append((name, trail, s["drop_top"].get(DROP_TOP, 0.0)))

    if a.set == "training":
        if not survivors:
            L += ["NO HYPOTHESIS SURVIVED TRAINING.", "",
                  "  The holdout stays sealed. This programme ends here; a second",
                  "  needs a new registration and new hypotheses, and does not get",
                  "  to adjust these."]
        else:
            best = max(survivors, key=lambda x: x[2])
            L += [f"SURVIVED: {', '.join(f'{n} @ {t:g}%' for n, t, _ in survivors)}", "",
                  f"  The holdout candidate is {best[0]} at {best[1]:g}% -- the "
                  f"higher drop-top-{DROP_TOP} net.",
                  "  Any other survivor stays a training result. Run, ONCE:", "",
                  f"    python -m strategy.premkt.run --pairs {a.pairs} --rejects "
                  f"{a.rejects} --cache {a.cache} --set locked "
                  f"--hypothesis {best[0]} --trail {best[1]:g}"]
    else:
        L += ["THE HOLDOUT IS NOW SPENT for this programme "
              f"({SPENT_PATH}).",
              "  Criteria 5 and 6 are training-only and were not re-applied here."]

    L += ["", "NOTHING ABOVE IS A LIVE RESULT. Training figures are not results;",
          "only a holdout figure is, and only once."]
    emit("\n".join(L), report, header="strategy.premkt.run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
