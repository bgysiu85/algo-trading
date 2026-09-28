#!/usr/bin/env python3
"""W16-0009 subitem 4 -- the read-back gate for the pulled ES/NQ trades
archive (order flow). Board W16-0009.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.readback_trades
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.readback_trades --out "D:\\Trading\\Claude outputs\\w16_0009_readback_20260928.json"

NO SIGNAL, NO P&L HAPPENS HERE -- same discipline as `strategy.w16.readback`'s
G1 (REGISTERED_w16_session_baselines.md sec 0, gate G1). This module only
answers, per root (ES, NQ), across every day `strategy.w16.fetch_trades`
pulled: can the trades archive be trusted the way the 1-minute bars already
were?

THREE CHECKS, W16-0009's OWN WORDING
--------------------------------------
1. DAY COVERAGE -- every day `fetch_trades`'s manifest says it pulled reads
   back non-empty, and covers the manifest's own date range.
2. AGGRESSOR SIDE PRESENT -- the `side` field (Databento's own aggressor
   flag: 'A' seller-initiated / 'B' buyer-initiated / 'N' unresolved) is
   actually populated on the big majority of prints, not silently all 'N'.
3. PER-MINUTE VOLUME VS THE OWNED ohlcv-1m, >=99% AGREEMENT -- for every
   UTC minute the owned 1-minute bar (`strategy.w16.fetch`) says had a bar,
   summing the trades file's own `size` column into that minute must land
   within a small tolerance of the bar's `volume` -- both are Databento's
   own numbers for the same prints, so this is an internal-consistency
   check, not two different vendors.

WHY THE COMPARISON IS BAR-ANCHORED, NOT TRADES-ANCHORED
------------------------------------------------------------
`common/dbn_io.py`'s own convention: "no bar is emitted for an interval
with no trade." So every minute a 1-minute bar exists for is, by
construction, a minute at least one trade printed in -- comparing trades
summed into exactly those minutes against that bar's `volume` is a
like-for-like check. A minute with trades but somehow no bar would be an
`ohlcv-1m` gap, which is `strategy.w16.readback`'s G1 to catch, not this
one's.

WHY 99%, NOT 100%
--------------------
Same reasoning as G1's own $0.05 daily-close tolerance: Databento can revise
or exclude individual prints (busted trades, late corrections) between when
`trades` and `ohlcv-1m` were each built, and a handful of one-print misses
across ~313 days x ~390 RTH minutes x 2 roots is not evidence the archive is
wrong. Sec 0's stop rule is enforced here the same way: below 99%, the run
exits non-zero rather than printing a warning and continuing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOTS = ("ES", "NQ")
PASS_PCT = 0.99
VOL_TOL_PCT = 0.001     # 0.1% of the bar's own volume ...
VOL_TOL_MIN = 1         # ... or 1 contract, whichever is larger
MAX_MISSES_LISTED = 10


def minute_volume_from_trades(df_trades: pd.DataFrame) -> pd.Series:
    """Every UTC-minute's summed `size`, indexed by the minute's start (the
    same "bar start" convention `common/dbn_io.py` uses for ts_event)."""
    if df_trades.empty:
        return pd.Series(dtype="int64")
    minute = df_trades.index.floor("min")
    return df_trades.groupby(minute)["size"].sum().astype("int64")


def aggressor_side_stats(df_trades: pd.DataFrame) -> dict:
    """How often the `side` field actually resolved to a direction ('A' or
    'B') rather than 'N' (Databento's own "no side" marker)."""
    if df_trades.empty or "side" not in df_trades.columns:
        return {"n": 0, "n_sided": 0, "pct_sided": 0.0, "values": {}}
    n = len(df_trades)
    vc = df_trades["side"].value_counts()
    n_sided = int(vc.drop(labels=["N"], errors="ignore").sum())
    return {"n": int(n), "n_sided": n_sided,
            "pct_sided": (n_sided / n) if n else 0.0,
            "values": {str(k): int(v) for k, v in vc.items()}}


def minute_agreement(trades_vol: pd.Series, bar_vol: pd.Series, *,
                      tol_pct: float = VOL_TOL_PCT, tol_min: int = VOL_TOL_MIN,
                      pass_pct: float = PASS_PCT) -> dict:
    """Compare trades-summed per-minute volume against the owned 1-minute
    bar's own `volume`, for every minute the BAR says exists (bar-anchored;
    see the module docstring). Never raises on a failed comparison -- a
    failed check is itself the finding, enforced by `main()`'s exit code."""
    idx = bar_vol.index
    if len(idx) == 0:
        return {"n_compared": 0, "n_within_tol": 0, "pct_within_tol": 0.0,
                "tol_pct": tol_pct, "tol_min": tol_min, "misses": []}
    tv = trades_vol.reindex(idx).fillna(0).astype("int64")
    bv = bar_vol.astype("int64")
    diff = (tv - bv).abs()
    tol = np.maximum(tol_min, np.round(bv.to_numpy() * tol_pct))
    within = diff.to_numpy() <= tol
    n_compared = len(idx)
    n_within = int(within.sum())
    miss_pos = np.where(~within)[0]
    misses = [{"minute": str(idx[i]), "trades_volume": int(tv.iloc[i]),
              "bar_volume": int(bv.iloc[i]), "diff": int(diff.iloc[i])}
              for i in miss_pos[:MAX_MISSES_LISTED]]
    return {"n_compared": n_compared, "n_within_tol": n_within,
            "pct_within_tol": n_within / n_compared,
            "tol_pct": tol_pct, "tol_min": tol_min,
            "n_misses_total": int(len(miss_pos)), "misses": misses,
            "passed": n_within / n_compared >= pass_pct}


def day_coverage(pulled_days: list[str], readable_days: list[str],
                  empty_days: list[str]) -> dict:
    """Every day the fetch's manifest says it bought reads back and is
    non-empty. `readable_days`/`empty_days` partition `pulled_days` --
    a day the manifest lists but the archive can't open at all is neither
    (a missing/corrupt file), and is reported as such."""
    pulled, readable, empty = set(pulled_days), set(readable_days), set(empty_days)
    missing = sorted(pulled - readable - empty)
    return {"n_pulled": len(pulled), "n_readable_nonempty": len(readable - empty),
            "n_empty": len(sorted(empty)), "n_missing": len(missing),
            "empty_days": sorted(empty), "missing_days": missing,
            "passed": not missing and not empty}


def restrict_to_pulled_days(owned_1m: pd.DataFrame, pulled_days: list[str]) -> pd.DataFrame:
    """Keep only the owned 1-minute bars that fall on a day `fetch_trades`
    actually pulled. The owned `ohlcv-1m` archive spans years; the trades
    pull only covers `pulled_days` (~313 recent days) -- comparing against
    the FULL bar history would count every minute outside the pull window
    as a "miss" (trades_volume=0 vs a real bar_volume), which is not a
    trades/bars disagreement, just bars that were never priced or pulled
    as trades in the first place. Bar-anchored still means "every minute
    the bar says exists" (see the module docstring) -- restricted first to
    the days that are actually comparable."""
    if owned_1m.empty or not pulled_days:
        return owned_1m.iloc[0:0]
    pulled = set(pulled_days)
    days = owned_1m.index.strftime("%Y-%m-%d")
    return owned_1m[days.isin(pulled)]


def run_root(day_frames: dict, owned_1m: pd.DataFrame, root: str,
              pulled_days: list[str]) -> dict:
    """The whole gate for one root, given already-loaded per-day trades
    frames (already filtered to this root's symbol) and the owned 1-minute
    bar frame (already filtered to this root, `strategy.w16.fetch`'s file --
    may still span the bar archive's FULL history; restricted here to
    `pulled_days` before comparison, see `restrict_to_pulled_days`)."""
    readable_days = [d for d, df in day_frames.items() if df is not None]
    empty_days = [d for d, df in day_frames.items() if df is not None and df.empty]
    coverage = day_coverage(pulled_days, readable_days, empty_days)

    non_empty = [df for df in day_frames.values() if df is not None and not df.empty]
    all_trades = pd.concat(non_empty).sort_index() if non_empty else pd.DataFrame()
    side = aggressor_side_stats(all_trades)

    trades_vol = minute_volume_from_trades(all_trades)
    owned_1m = restrict_to_pulled_days(owned_1m, pulled_days)
    bar_vol = owned_1m["volume"] if "volume" in owned_1m.columns else pd.Series(dtype="int64")
    agreement = minute_agreement(trades_vol, bar_vol)

    passed = coverage["passed"] and side["pct_sided"] >= PASS_PCT and agreement.get("passed", False)
    return {"coverage": coverage, "aggressor_side": side,
            "minute_volume_agreement": agreement, "passed": passed}


def _load_and_run(archive: Path, verbose: bool = True) -> dict:
    """Real I/O: read every pulled day's trades file plus the owned 1-minute
    bars, split by root, and run `run_root`. Not exercised by the unit
    tests (those pin the pure functions above on synthetic frames) -- this
    is what Ben's real run on D:\\Trading exercises against the archive."""
    from common.dbn_io import read_dbn
    from common.tsmom_data_price import DATASET
    from strategy.w16 import fetch, fetch_trades

    trades_dir = Path(archive) / DATASET / fetch_trades.ARCHIVE_SUBDIR
    manifest_p = fetch_trades.manifest_path(archive)
    if not manifest_p.exists():
        raise SystemExit(f"missing {manifest_p} -- run strategy.w16.fetch_trades "
                          "--confirm first")
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    pulled_days = sorted({Path(p).stem.split(".")[0]
                          for p in manifest.get("files_pulled", [])})
    if not pulled_days:
        raise SystemExit(f"{manifest_p} lists no pulled days")

    by_root_day: dict[str, dict[str, pd.DataFrame | None]] = {r: {} for r in ROOTS}
    for i, day in enumerate(pulled_days, start=1):
        p = fetch_trades.day_path(archive, day)
        if not p.exists():
            for r in ROOTS:
                by_root_day[r][day] = None
            continue
        df = read_dbn(p)
        for r in ROOTS:
            by_root_day[r][day] = df[df["symbol"] == f"{r}.v.0"].copy() if "symbol" in df.columns else df.iloc[0:0]
        if verbose and (i % 25 == 0 or i == len(pulled_days)):
            print(f"  read {i}/{len(pulled_days)} days", flush=True)

    reports = {}
    for r in ROOTS:
        m1_path = Path(archive) / DATASET / fetch.ARCHIVE_SUBDIR / "ohlcv-1m" / f"{r}.dbn.zst"
        if not m1_path.exists():
            raise SystemExit(f"missing {m1_path} -- run strategy.w16.fetch "
                              "--confirm first (the owned 1-minute bars this "
                              "checks trades against)")
        owned_1m = read_dbn(m1_path)
        if "symbol" in owned_1m.columns:
            owned_1m = owned_1m[owned_1m["symbol"] == f"{r}.v.0"].copy()
        reports[r] = run_root(by_root_day[r], owned_1m, r, pulled_days)
    return reports


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="W16-0009 subitem 4: read-back gate for the ES/NQ trades archive.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None,
                    help="write the full JSON report here as well as stdout")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    print("Reading pulled trades days + owned 1-minute bars ...")
    reports = _load_and_run(archive)

    all_passed = True
    for r in ROOTS:
        rep = reports[r]
        cov, side, ag = rep["coverage"], rep["aggressor_side"], rep["minute_volume_agreement"]
        all_passed = all_passed and rep["passed"]
        print(f"\n=== {r} ===")
        print(f"day coverage: {cov['n_readable_nonempty']}/{cov['n_pulled']} pulled days "
              f"readable and non-empty ({cov['n_missing']} missing, {cov['n_empty']} empty)")
        print(f"aggressor side: {side['pct_sided']:.4%} of {side['n']:,} prints resolved "
              f"('A'/'B'), values={side['values']}")
        print(f"per-minute volume vs owned ohlcv-1m: {ag['n_within_tol']}/{ag['n_compared']} "
              f"({ag['pct_within_tol']:.4%}) within tol "
              f"(max({ag['tol_min']}, {ag['tol_pct']:.1%} of bar volume)), "
              f"{ag.get('n_misses_total', 0)} miss(es) total")
        for m in ag["misses"]:
            print(f"  miss {m['minute']}  trades={m['trades_volume']}  "
                  f"bar={m['bar_volume']}  diff={m['diff']}")
        print(f"{'PASSED' if rep['passed'] else 'FAILED'}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    if all_passed:
        print("\nW16-0009 read-back PASSED for ES and NQ.")
        return 0
    print("\nW16-0009 read-back FAILED for at least one root -- reported above, "
          "same stop rule as strategy.w16.readback's G1.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
