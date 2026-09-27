#!/usr/bin/env python3
r"""W03-0005 Part B -- where Ben's real trading money went: commission, the
spread, the first minute after each fill, and the rest of the hold.

    python -m common.fill_markout
    python -m common.fill_markout --flex-dir var/flex --archive E:\Databento

Registered in docs/research/REGISTERED_exec_cost.md (Part B), committed before
this file existed. Reads data already on disk: the IBKR Flex exports and the
XNAS.BASIC tcbbo archive. Costs $0 and makes no network call.

THE IDENTITY
------------
For each execution, d = +1 buy / -1 sell, q shares, p price, m_t the mid of the
last tcbbo record at or before the fill (at most 60 s old, else unpriced --
common.friction_quotes' own rule), m_{t+D} the mid of the last record at or
before t + D. Per position (flat to flat, common.flex's grouping):

    gross G = -sum d*p*q                      spread S = sum d*(p - m_t)*q
    mid   M = -sum d*m_t*q  (so G = M - S exactly)
    D_in  = sum over ENTRY fills d*(m_{t+D} - m_t)*q   (+ = went his way)
    D_out = sum over EXIT  fills d*(m_{t+D} - m_t)*q
    R     = M - D_in - D_out                          (the rest of the hold)
    C     = commission paid (positive)
    net   = D_in + D_out + R - S - C

An ENTRY fill grows the absolute position, an EXIT fill shrinks it, so shorts
are covered as well as longs. A position enters the identity only if EVERY
fill in it is priced; coverage is printed.

A tcbbo record exists only where a trade printed, so on a quiet stretch
m_{t+D} can be the same record as m_t. That is counted and reported, never
imputed: "nothing printed" is itself what the tape says.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import flex
from common.report_fmt import acct
from common.report_io import emit

REGISTERED = "docs/research/REGISTERED_exec_cost.md"
DATASET, SCHEMA = "XNAS.BASIC", "tcbbo"
TOLERANCE_S = 60
HORIZONS = (5, 60, 300)
PRIMARY = 60
SEED = 20260927
NBOOT = 2_000
PUBLISHED_EXECS, PUBLISHED_POSITIONS = 18_621, 1_658
UTC = ZoneInfo("UTC")


# --- positions ------------------------------------------------------------------

def assign_positions(execs: list) -> tuple[dict, list[dict]]:
    """Each execution's position id and ENTRY/EXIT role, using exactly
    common.flex.round_trips' grouping and order (symbol-day, flat to flat,
    sorted on (time_known, dt_raw)). Returns ({trade_id: (pos_id, is_entry)},
    positions)."""
    grouped = defaultdict(list)
    for e in execs:
        grouped[(e.symbol, e.trade_date)].append(e)
    role, positions = {}, []
    for (sym, day), rows in sorted(grouped.items()):
        pos, cur = 0.0, None
        for e in sorted(rows, key=lambda x: (x.time_known, x.dt_raw)):
            if cur is None:
                cur = {"pos_id": len(positions), "symbol": sym, "date": day,
                       "entry_minute": e.et_minute, "fills": 0, "peak": 0.0,
                       "open_at_end": False, "all_timed": True}
                positions.append(cur)
            was, pos = pos, pos + e.qty
            role[e.trade_id] = (cur["pos_id"], abs(pos) > abs(was) + 1e-9)
            cur["fills"] += 1
            cur["peak"] = max(cur["peak"], abs(pos))
            cur["all_timed"] = cur["all_timed"] and e.time_known and e.et_minute is not None
            if round(was, 6) != 0.0 and round(pos, 6) == 0.0:
                cur = None
                pos = 0.0
        if cur is not None:
            cur["open_at_end"] = True
    return role, positions


def fills_frame(execs: list, zone: str, role: dict) -> pd.DataFrame:
    """Every timed execution as a UTC-stamped row with its position and role."""
    rows = []
    for e in execs:
        if not e.time_known or e.et_minute is None:
            continue
        ts = e.dt_raw.replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)
        pid, is_entry = role[e.trade_id]
        rows.append((e.trade_id, e.symbol, e.trade_date, pd.Timestamp(ts),
                     1.0 if e.qty > 0 else -1.0, abs(e.qty), abs(e.price),
                     -e.commission, e.fifo_pnl, pid, is_entry, e.et_minute))
    df = pd.DataFrame(rows, columns=["trade_id", "symbol", "date", "ts", "d", "q", "p",
                                     "comm", "fifo", "pos_id", "entry", "et_minute"])
    if not df.empty:
        df["ts"] = df["ts"].astype("datetime64[ns, UTC]")
    return df


# --- quotes -----------------------------------------------------------------------

def asof(left: pd.DataFrame, quotes: pd.DataFrame, key: str,
         tolerance_s: int | None) -> pd.DataFrame:
    """The last quote at or before left[key], per symbol. Returns left's index
    with bid, ask and the quote's own timestamp (qts); NaN where none."""
    if left.empty:
        return pd.DataFrame(index=left.index, columns=["bid", "ask", "qts"])
    l = left[["symbol", key]].copy()
    l["_row"] = l.index
    l[key] = l[key].astype("datetime64[ns, UTC]")
    q = quotes[["ts", "symbol", "bid", "ask"]].copy()
    q["ts"] = q["ts"].astype("datetime64[ns, UTC]")
    q["qts"] = q["ts"]
    q = q.rename(columns={"ts": key}).sort_values(key, kind="mergesort")
    m = pd.merge_asof(l.sort_values(key, kind="mergesort"), q, on=key, by="symbol",
                      direction="backward",
                      tolerance=(pd.Timedelta(seconds=tolerance_s) if tolerance_s else None))
    return m.set_index("_row")[["bid", "ask", "qts"]].reindex(left.index)


def price_fills(fills: pd.DataFrame, quotes: pd.DataFrame,
                horizons=HORIZONS, tolerance_s: int = TOLERANCE_S) -> pd.DataFrame:
    """m_t and m_{t+D} for each fill of one date. Unpriced fills keep NaN."""
    out = fills.copy()
    if out.empty:
        return out
    if quotes.empty:
        out["bid"] = out["ask"] = np.nan
        out["q0ts"] = pd.NaT
        out["m0"] = np.nan
        for h in horizons:
            out[f"m{h}"] = np.nan
            out[f"same{h}"] = False
        return out
    at = asof(out, quotes, "ts", tolerance_s)
    out["bid"], out["ask"], out["q0ts"] = at["bid"], at["ask"], at["qts"]
    out["m0"] = (out["bid"] + out["ask"]) / 2.0
    for h in horizons:
        k = f"_t{h}"
        out[k] = out["ts"] + pd.Timedelta(seconds=h)
        later = asof(out, quotes, k, None)
        # At worst the same record as m_t -- never older, since the backward
        # search from t + D passes t first.
        out[f"m{h}"] = np.where(out["m0"].notna(), (later["bid"] + later["ask"]) / 2.0, np.nan)
        out[f"same{h}"] = out["m0"].notna() & (later["qts"] == out["q0ts"])
        out = out.drop(columns=[k])
    return out


# --- the identity -------------------------------------------------------------------

def components(priced: pd.DataFrame, positions: list[dict], horizon: int) -> pd.DataFrame:
    """One row per position that qualifies (every fill priced, returned to
    flat), with G, S (entries/exits), M, D_in, D_out, R, C, net."""
    f = priced
    ok_pos = {p["pos_id"] for p in positions if not p["open_at_end"] and p["all_timed"]}
    f = f[f["pos_id"].isin(ok_pos)]
    unpriced = set(f.loc[f["m0"].isna(), "pos_id"])
    counts = f.groupby("pos_id").size()
    want = {p["pos_id"]: p["fills"] for p in positions}
    whole = {pid for pid, n in counts.items() if n == want[pid]}
    keep = (ok_pos & whole) - unpriced
    f = f[f["pos_id"].isin(keep)].copy()
    mh = f"m{horizon}"
    f["G"] = -f["d"] * f["p"] * f["q"]
    f["S"] = f["d"] * (f["p"] - f["m0"]) * f["q"]
    f["M"] = -f["d"] * f["m0"] * f["q"]
    f["D"] = f["d"] * (f[mh] - f["m0"]) * f["q"]
    f["S_in"] = np.where(f["entry"], f["S"], 0.0)
    f["S_out"] = np.where(f["entry"], 0.0, f["S"])
    f["D_in"] = np.where(f["entry"], f["D"], 0.0)
    f["D_out"] = np.where(f["entry"], 0.0, f["D"])
    f["q_in"] = np.where(f["entry"], f["q"], 0.0)
    f["same"] = f[f"same{horizon}"].astype(float)
    g = f.groupby("pos_id").agg(G=("G", "sum"), S=("S", "sum"), S_in=("S_in", "sum"),
                                S_out=("S_out", "sum"), M=("M", "sum"), D_in=("D_in", "sum"),
                                D_out=("D_out", "sum"), C=("comm", "sum"), fifo=("fifo", "sum"),
                                q_in=("q_in", "sum"), fills=("G", "size"), same=("same", "sum"))
    g["R"] = g["M"] - g["D_in"] - g["D_out"]
    g["net"] = g["G"] - g["C"]
    meta = {p["pos_id"]: p for p in positions}
    g["symbol"] = [meta[i]["symbol"] for i in g.index]
    g["date"] = [meta[i]["date"] for i in g.index]
    g["peak"] = [meta[i]["peak"] for i in g.index]
    g["block"] = [flex.block(meta[i]["entry_minute"]) for i in g.index]
    # The average ENTRY price, for the $2-20 band split.
    f["pq_in"] = np.where(f["entry"], f["p"] * f["q"], 0.0)
    pq = f.groupby("pos_id")["pq_in"].sum()
    g["entry_px"] = (pq.reindex(g.index) / g["q_in"].replace(0.0, np.nan)).astype(float)
    return g


def boot_din(g: pd.DataFrame, nboot: int = NBOOT, seed: int = SEED) -> tuple[float, float, float]:
    """D_in per 100 entry shares, symbol-day-cluster bootstrap."""
    if g.empty or g["q_in"].sum() <= 0:
        return float("nan"), float("nan"), float("nan")
    sd = g.groupby(["symbol", "date"]).agg(D=("D_in", "sum"), Q=("q_in", "sum"))
    D, Q = sd["D"].to_numpy(), sd["Q"].to_numpy()
    point = float(D.sum() / Q.sum() * 100)
    rng = np.random.default_rng(seed)
    draws = np.empty(nboot)
    for k in range(nboot):
        i = rng.integers(0, len(D), len(D))
        qs = Q[i].sum()
        draws[k] = D[i].sum() / qs * 100 if qs > 0 else np.nan
    return point, float(np.nanquantile(draws, 0.025)), float(np.nanquantile(draws, 0.975))


def din_word(lo: float, hi: float) -> str:
    if not (lo == lo and hi == hi):
        return "n/a"
    if hi < 0:
        return "PICKED OFF"
    if lo > 0:
        return "MOMENTUM ON HIS SIDE"
    return "NO RELIABLE FIRST-MINUTE MOVE"


DRAG_NAMES = {"C": "commission", "S": "the spread", "D_in": "the first minute after buying in",
              "D_out": "the first minute after getting out", "R": "the rest of the hold"}


def drags(tot: dict) -> list[tuple[str, float]]:
    """Each component's drag in $ (positive = cost), largest first. C and S
    are costs as they stand; D_in, D_out and R drag only when negative."""
    d = {"C": tot["C"], "S": tot["S"]}
    for k in ("D_in", "D_out", "R"):
        d[k] = -tot[k] if tot[k] < 0 else 0.0
    return sorted(d.items(), key=lambda kv: -kv[1])


# --- report ---------------------------------------------------------------------------

def _tot(g: pd.DataFrame) -> dict:
    keys = ("G", "S", "S_in", "S_out", "M", "D_in", "D_out", "R", "C", "net", "fifo", "peak")
    return {k: float(g[k].sum()) for k in keys} | {"n": int(len(g))}


def money_table(g: pd.DataFrame, label: str) -> list[str]:
    t = _tot(g)
    n, peak = max(t["n"], 1), max(t["peak"], 1.0)
    L = [f"  {label}: {t['n']:,} positions",
         f"    {'':<40}{'total $':>14}{'per position':>14}{'per 100 sh':>12}"]

    def row(name, v):
        L.append(f"    {name:<40}{acct(v, 14)}{acct(v / n, 14)}{acct(v / peak * 100, 12)}")

    row("what the fills made (gross)", t["G"])
    row("  - commission", -t["C"])
    row("  = net", t["net"])
    L.append("    gross, taken apart:")
    row("  spread paid getting in", -t["S_in"])
    row("  spread paid getting out", -t["S_out"])
    row("  first minute after getting in", t["D_in"])
    row("  first minute after getting out", t["D_out"])
    row("  the rest of the hold", t["R"])
    row("  (sum of the five = gross)", -t["S"] + t["D_in"] + t["D_out"] + t["R"])
    return L


def render(g_by: dict, priced: pd.DataFrame, positions: list[dict], execs: list, tz: dict,
           nboot: int, coverage: dict) -> tuple[str, dict]:
    g = g_by[PRIMARY]
    t = _tot(g)
    words = {}
    pt, lo, hi = boot_din(g, nboot)
    words["first_minute"] = din_word(lo, hi)
    rank = drags(t)
    words["main_source"] = DRAG_NAMES[rank[0][0]]

    head = []
    n_exec, n_pos = len(execs), len(positions)
    if (n_exec, n_pos) != (PUBLISHED_EXECS, PUBLISHED_POSITIONS):
        head.append(f"*** C1: {n_exec:,} executions / {n_pos:,} positions on disk against the "
                    f"published {PUBLISHED_EXECS:,} / {PUBLISHED_POSITIONS:,} -- a different "
                    "history from the one registered ***")
    ident = abs((g["M"] - g["S"]).sum() - g["G"].sum())
    if ident >= 0.005:
        head.append(f"*** C2 FAILED: M - S differs from gross by {ident:.4f} -- NOT A RESULT ***")

    P = ["IN PLAIN TERMS", "-" * 78,
         f"Across {t['n']:,} of your real positions (the ones with a quote on every fill), the "
         f"fills made {acct(t['G'], 12).strip()} before commission and {acct(t['net'], 12).strip()} "
         f"after {acct(-t['C'], 12).strip()} of commission.",
         f"Crossing the spread cost {acct(-t['S'], 12).strip()} ({acct(-t['S_in'], 12).strip()} getting in, "
         f"{acct(-t['S_out'], 12).strip()} getting out).",
         f"The price move in the minute after you got in was worth {acct(t['D_in'], 12).strip()} "
         f"to you ({acct(pt, 8).strip()} per 100 shares bought, 95% CI "
         f"[{acct(lo, 8).strip()}, {acct(hi, 8).strip()}]) -> {words['first_minute']}.",
         f"The move in the minute after you got out was worth {acct(t['D_out'], 12).strip()} to you "
         f"(positive = you got out before it fell further).",
         f"Everything else during the hold came to {acct(t['R'], 12).strip()}.",
         f"Biggest drag: {words['main_source']} ({acct(-rank[0][1], 12).strip()}). Ranked: "
         + ", ".join(f"{DRAG_NAMES[k]} {acct(-v, 12).strip()}" for k, v in rank if v > 0) + ".", ""]

    same = float(g["same"].sum() / max(g["fills"].sum(), 1) * 100)
    slip = priced.loc[priced["m0"].notna()]
    half = ((slip["ask"] - slip["bid"]) / ((slip["ask"] + slip["bid"]) / 2) * 1e4 / 2).median() \
        if not slip.empty else float("nan")
    cross = (slip["d"] * (slip["p"] - slip["m0"]) / slip["m0"] * 1e4).median() \
        if not slip.empty else float("nan")
    fifo_diff = t["fifo"] - t["G"]
    S1 = ["1. COVERAGE AND CONTROLS",
          f"   executions {n_exec:,}   positions {n_pos:,}   (published {PUBLISHED_EXECS:,} / "
          f"{PUBLISHED_POSITIONS:,})",
          f"   report timezone {tz['chosen']}{' (AMBIGUOUS)' if tz.get('ambiguous') else ''}; "
          f"unresolved times {tz['unresolved']:,}",
          f"   fills priced against a quote <= {TOLERANCE_S}s old   {coverage['priced']:,} of "
          f"{coverage['timed']:,} ({100 * coverage['priced'] / max(coverage['timed'], 1):.1f}%)",
          f"   positions in the identity   {t['n']:,} of {n_pos:,}   (open at end "
          f"{sum(p['open_at_end'] for p in positions):,}; gross covered "
          f"{acct(t['G'], 12).strip()} of {acct(coverage['gross_all'], 12).strip()})",
          f"   C2 identity  sum(M - S) - sum(G) = {ident:.6f}  {'OK' if ident < 0.005 else 'FAILED'}",
          f"   IBKR FifoPnlRealized over the same positions minus gross {acct(fifo_diff, 10).strip()}, "
          f"minus net {acct(t['fifo'] - t['net'], 10).strip()} (reported, not a stop)",
          f"   quote at t+{PRIMARY}s was the same record as at t on {same:.1f}% of fills "
          "(nothing printed in the minute)",
          f"   spread check: median half-spread {half:.1f} bps, median cross vs mid {cross:.1f} bps "
          "(2026-09-06: 40-41 and 17.3)", ""]

    S2 = [f"2. WHERE THE MONEY WENT (primary: {PRIMARY}-second horizon)", *money_table(g, "all"), ""]
    S3 = ["3. THE SAME AT OTHER HORIZONS (reported only)"]
    for h in HORIZONS:
        th = _tot(g_by[h])
        S3.append(f"   {h:>4}s   after getting in {acct(th['D_in'], 12)}   after getting out "
                  f"{acct(th['D_out'], 12)}   rest of hold {acct(th['R'], 12)}   "
                  f"({th['n']:,} positions)")
    S3.append("")
    S4 = [f"4. SPLITS ({PRIMARY}s)"]
    for lab, mask in (("pre-market entries", g["block"] == "PRE"),
                      ("regular-hours entries", g["block"] == "RTH"),
                      ("after-hours entries", g["block"] == "POST"),
                      ("winning positions", g["net"] > 0),
                      ("losing positions", g["net"] <= 0),
                      ("entry price inside $2-20", g["entry_px"].between(2.0, 20.0)),
                      ("entry price outside $2-20", ~g["entry_px"].between(2.0, 20.0))):
        sub = g[mask]
        if len(sub):
            S4 += money_table(sub, lab)
    S4.append("")
    S5 = ["5. DECISION WORDS (REGISTERED_exec_cost.md B.6)",
          f"   first minute after buying in  {words['first_minute']}   "
          f"({acct(pt, 8).strip()} per 100 sh, 95% CI [{acct(lo, 8).strip()}, {acct(hi, 8).strip()}])",
          f"   where the money went          {words['main_source']}", "",
          "CAVEATS: discretionary hotkey orders at moments he chose -- they bound what is",
          "achievable here and do not measure MCL's orders; XNAS.BASIC's BBO is not the NBBO;",
          "Flex stamps to the second; tcbbo quotes only where a trade printed."]
    L = (head + [""] if head else []) + P + S1 + S2 + S3 + S4 + S5
    return "\n".join(L), words


# --- main ---------------------------------------------------------------------------------

def flex_paths(flex_dir: str, explicit: list[str] | None) -> list[str]:
    """PowerShell does not expand wildcards for a native program, so the glob
    happens here."""
    if explicit:
        out = []
        for p in explicit:
            out += sorted(glob.glob(p)) or [p]
        return out
    return sorted(glob.glob(str(Path(flex_dir) / "*.csv")))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--flex-dir", default="var/flex")
    p.add_argument("--flex", nargs="*", default=None, help="explicit Flex CSV path(s) or glob(s)")
    p.add_argument("--archive", default=None)
    p.add_argument("--tz", default=None, help="force the Flex report timezone")
    p.add_argument("--nboot", type=int, default=NBOOT)
    p.add_argument("--out", default="var/reports/fill_markout.txt")
    p.add_argument("--csv-fills", default="var/reports/fill_markout_fills.csv")
    p.add_argument("--csv-positions", default="var/reports/fill_markout_positions.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.friction_quotes import quotes_for_date

    a = build_parser().parse_args(argv)
    paths = flex_paths(a.flex_dir, a.flex)
    if not paths:
        raise SystemExit(f"no Flex CSVs found in {a.flex_dir}")
    execs = flex.load_many(paths)
    tz = flex.measure_offsets(execs, force=a.tz)
    role, positions = assign_positions(execs)
    rt = flex.round_trips(execs)
    if len(rt) != len(positions):
        raise SystemExit(f"STOPPED: {len(positions)} positions here against {len(rt)} from "
                         "common.flex.round_trips -- the grouping has drifted")
    fills = fills_frame(execs, tz["chosen"], role)
    archive = Path(a.archive) if a.archive else default_archive()

    parts, missing_dates = [], []
    for date, grp in fills.groupby("date", sort=True):
        q = quotes_for_date(archive, DATASET, date, SCHEMA)
        if q.empty:
            missing_dates.append(date)
        parts.append(price_fills(grp, q))
    priced = pd.concat(parts) if parts else fills
    g_by = {h: components(priced, positions, h) for h in HORIZONS}
    gross_all = float((-priced["d"] * priced["p"] * priced["q"]).sum())
    coverage = {"timed": len(fills), "priced": int(priced["m0"].notna().sum()),
                "gross_all": gross_all, "missing_dates": missing_dates}

    text, words = render(g_by, priced, positions, execs, tz, a.nboot, coverage)
    if missing_dates:
        text = (f"*** {len(missing_dates)} date(s) with no {DATASET} {SCHEMA} file: "
                f"{', '.join(missing_dates[:8])}{' ...' if len(missing_dates) > 8 else ''} ***\n\n"
                + text)
    ok = "C2 FAILED" not in text
    emit(text, a.out, header=f"common.fill_markout flex={len(paths)} file(s) archive={archive} "
                             f"dataset={DATASET} schema={SCHEMA} tolerance={TOLERANCE_S}s "
                             f"horizons={HORIZONS} primary={PRIMARY}s nboot={a.nboot} seed={SEED} "
                             f"registered={REGISTERED}" + ("" if ok else "  STOPPED"))
    Path(a.csv_fills).parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in priced.columns if not c.startswith("_")]
    priced[cols].to_csv(a.csv_fills, index=False, encoding="utf-8")
    g_by[PRIMARY].to_csv(a.csv_positions, encoding="utf-8")
    print(f"wrote {a.csv_fills} ({len(priced):,} fills) and {a.csv_positions} "
          f"({len(g_by[PRIMARY]):,} positions)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
