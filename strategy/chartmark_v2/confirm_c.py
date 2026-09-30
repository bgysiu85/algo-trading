#!/usr/bin/env python3
"""CHARTMARK-v2 step C -- confirmation of the step-S winner on 2016-01-01 .. 2021-12-31 (Amendment 4.3). W15-0036 step 4.

    python -m strategy.chartmark_v2.confirm_c

Needs selection_chartmark_v2.json (written by step S). Runs ONLY the winner named there: there is no candidate flag, and any
flag that could narrow the window, pick another candidate, or touch the holdout is refused. Indicators are computed over the
whole training frame (EMAs and ATR are causal, so the 2010-2015 bars only supply warm-up); the ENGINE is flat until the first
bar of 2016 (simulate(start=...)), so every trade, control and grid cell is a 2016-2021 trade.

Produces: the nine criteria of Amendment 4.3; C1 Donchian 20/10 (no session filter) and C3 random entries (same count per year,
same exits, 1,000 seeded draws) on the window; the 27-cell grid around the winner; then the Amendment 4.5 variants, reported and
never selectable. The 2022-2025 holdout is NOT read here: the frame loader cuts the archive before 2022 and this module has no
holdout path. A full nine-of-nine pass makes the winner ELIGIBLE for the holdout (Amendment 4.6); spending it is a separate step.
Writes confirmation_chartmark_v2.json in the repo root as the once-only ledger: a second run is refused.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from zlib import crc32

import numpy as np
import pandas as pd

from strategy.chartmark import book as BK
from strategy.chartmark.data import Frame, Ind, indicators, load_training_frame
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S
from strategy.htf import book as HBK

ROOT = Path(__file__).resolve().parents[2]
SELECTION_PATH = ROOT / "selection_chartmark_v2.json"
LEDGER_PATH = ROOT / "confirmation_chartmark_v2.json"
OUT = Path(r"D:\Trading\Claude outputs")
GUARDED = ("strategy/chartmark_v2", "docs/research/REGISTERED_chartmark_v2.md")
DRAWS = 1000                              # registered (Amendment 4.3 item 6)
BOOT_N = 2000                             # registered (Amendment 4.3 item 4)
REFUSED = ("--holdout", "--limit", "--seen", "--pnl", "--backtest", "--spend", "--variants", "--grid", "--controls", "--from",
           "--to", "--first", "--last", "--markets", "--candidate", "--winner", "--window", "--draws", "--start", "--end",
           "--k1", "--k2", "--k3", "--k4", "--select", "--reselect", "--force", "--dev")


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


# ----------------------------------------------------------------------- selection file
def load_selection(path: Path = SELECTION_PATH) -> tuple[str, S.Params, dict]:
    """The winner and its registered parameters. Refuses a missing file, no winner, an unknown candidate, parameters that do not
    match the registered candidate, or a selection that looked at a bar after the development window."""
    if not path.exists():
        raise SystemExit(f"REFUSED: {path.name} is missing -- step C runs only after step S has written it.")
    sel = json.loads(path.read_text(encoding="utf-8"))
    w = sel.get("winner")
    if w not in S.CANDIDATES:
        raise SystemExit(f"REFUSED: selection winner {w!r} is not one of the registered candidates {list(S.CANDIDATES)}.")
    reg = S.CANDIDATES[w]
    got = sel.get("params", {}).get(w, {})
    if got.get("prev_high") != reg.prev_high or abs(float(got.get("theta", -1)) - reg.theta) > 1e-12:
        raise SystemExit(f"REFUSED: the selection file's parameters for {w} ({got}) differ from the registered candidate.")
    if sel.get("window") != [S.DEV_FIRST, S.DEV_LAST] or str(sel.get("last_bar_used", ""))[:10] > S.DEV_LAST:
        raise SystemExit("REFUSED: the selection file does not describe a development-window-only selection.")
    return w, reg, sel


# ----------------------------------------------------------------------- window
def window_start(fr: Frame) -> int:
    """Index of the first bar whose NY date is on/after CONF_FIRST. Refuses a frame with a bar after CONF_LAST."""
    days = np.asarray(fr.ny.strftime("%Y-%m-%d"))
    if days[-1] > S.CONF_LAST:
        raise SystemExit(f"REFUSED: the frame has a bar dated {days[-1]}, after the confirmation window ({S.CONF_LAST}).")
    ok = np.nonzero(days >= S.CONF_FIRST)[0]
    if len(ok) == 0:
        raise SystemExit("frame has no bar in the confirmation window")
    return int(ok[0])


# ----------------------------------------------------------------------- controls
def donchian_c1(fr: Frame, start: int, N_in: int = 20, N_out: int = 10) -> list:
    """C1 (Amendment 4.3 item 5; CHARTMARK-v1's C1 code without the session filter). Buy-stop at the highest high of the last
    20 bars + 1 tick placed at the close of t, one-bar life; exit sell-stop at the lowest low of the last 10 bars (prior close).
    Fills min/max(level, open). Flat until `start`. Same friction, costs and roll rule as the base."""
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    trades = []
    t = max(N_in, N_out, start)
    while t < n - 1:
        if not fr.roll_after[t]:
            level = float(h[t - N_in + 1: t + 1].max()) + S.TICK
            j = t + 1
            if h[j] >= level:
                fill = max(level, o[j])
                x, px, why = None, None, "S"
                for k in range(j + 1, n):
                    lvl = float(l[k - N_out: k].min())
                    if o[k] <= lvl:
                        x, px = k, o[k]
                        break
                    if l[k] <= lvl:
                        x, px = k, lvl
                        break
                if x is None:
                    x, px, why = n - 1, float(c[n - 1]), "data_end"
                rolls = int(fr.roll_after[j:x].sum()) if x > j else 0
                trades.append(E.Trade(j, x, float(fill), float(px), why, "C1", t, level, 0.0, rolls))
                t = x
        t += 1
    return trades


def c3_candidates(fr: Frame, ind: Ind, p: S.Params, start: int) -> tuple[np.ndarray, np.ndarray]:
    """Every bar of the window as a standalone random entry: in at its open, backstop = open - p.backstop, exit by the base's
    backstop / EMA21 walk (Amendment 4.3 item 6: same exits, no confirmation step). The low of the entry bar is taken as after
    the fill (the entry is the open). Returns (bar indices, net at mid per 1 MCL)."""
    idx, nets = [], []
    n = fr.n
    per = S.per_side("MCL", "mid")
    for e in range(max(start, 3), n - 1):
        if np.isnan(ind.e21[e - 1]) or np.isnan(ind.atr[e - 1]):
            continue
        fill = float(fr.o[e])
        stop = fill - p.backstop
        if fr.l[e] <= stop:
            x, px = e, stop
        else:
            x, px, _, _ = E._walk(fr, ind, p, e, fill, stop)
        rolls = int(fr.roll_after[e:x].sum()) if x > e else 0
        idx.append(e)
        nets.append((px - fill) * S.MULT["MCL"] - per * (2 + 2 * rolls))
    return np.array(idx), np.array(nets)


def c3_draws(fr: Frame, cand_idx: np.ndarray, cand_net: np.ndarray, per_year: dict, draws: int = DRAWS) -> np.ndarray:
    """Per year, the base's number of entries sampled from that year's candidates. Seed
    default_rng([crc32(str(d)), crc32("CL-v2"), N]) with N the base's total entries (registered, sec 3)."""
    years = np.asarray(fr.ny.year)[cand_idx]
    N = int(sum(per_year.values()))
    pools = {y: cand_net[years == y] for y in per_year}
    tot = np.empty(draws)
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(b"CL-v2"), N])
        s = 0.0
        for y in sorted(per_year):
            k, pool = per_year[y], pools[y]
            if k and len(pool):
                s += float(pool[rng.integers(0, len(pool), size=k)].sum())
        tot[d] = s
    return tot


# ----------------------------------------------------------------------- scoring
def summarize(trades: list, fr: Frame, sym: str = "MCL", level: str = "mid") -> dict:
    df = BK.trade_frame(trades, fr, sym, level)
    s = HBK.summarize(df) if len(df) else None
    yn = HBK.year_table(df) if len(df) else {}
    h1, h2 = HBK.split_halves(df) if len(df) else (0.0, 0.0)
    return dict(df=df, n=len(df), wins=s.wins if s else 0, losses=s.losses if s else 0,
                gross=s.gross if s else 0.0, cost=s.cost if s else 0.0, net=s.net if s else 0.0,
                avg_win=s.avg_win if s else None, avg_loss=s.avg_loss if s else None,
                largest_loss=s.largest_loss if s else None, streak=s.worst_loss_streak if s else 0,
                year_net=yn, h1=h1, h2=h2, dd=BK.max_drawdown(df))


def evaluate(mid: pd.DataFrame, high: pd.DataFrame, c1_mid: pd.DataFrame, c3_p99: float, n_grid_pos: int) -> list[dict]:
    """The nine criteria of Amendment 4.3, on the confirmation window. ok=None never occurs: every input is supplied."""
    n = len(mid)
    yn = HBK.year_table(mid) if n else {}
    net = float(mid["net"].sum()) if n else 0.0
    hn = float(high["net"].sum()) if len(high) else 0.0
    d1 = BK.drop_top(yn, 1) if yn else 0.0
    boot = HBK.bootstrap_by_year(yn, n=BOOT_N, seed=0) if n else float("nan")
    _, share = HBK.top_year_share(yn)
    c1net = float(c1_mid["net"].sum()) if len(c1_mid) else 0.0
    r_base = BK.daily_vol_ratio(mid, S.CONF_FIRST, S.CONF_LAST)
    r_c1 = BK.daily_vol_ratio(c1_mid, S.CONF_FIRST, S.CONF_LAST)
    return [
        dict(n=1, name="Net > $0 at mid", value=net, ok=net > 0),
        dict(n=2, name="Net > $0 at high friction", value=hn, ok=hn > 0),
        dict(n=3, name="Drop-top-1 calendar year still > $0", value=d1, ok=d1 > 0),
        dict(n=4, name=f"Bootstrap by year ({BOOT_N:,} resamples): net > 0 in >= 90%", value=boot, ok=bool(boot >= 0.90)),
        dict(n=5, name="Beats C1 on net AND on net / std of daily net", value=(net, c1net, r_base, r_c1),
             ok=bool(net > c1net and r_base > r_c1)),
        dict(n=6, name="Beats the p99 of C3 (random entries) on net", value=(net, c3_p99), ok=bool(net > c3_p99)),
        dict(n=7, name="No single year > 50% of net", value=share, ok=bool(net > 0 and share <= 0.5)),
        dict(n=8, name="At least 18 of 27 grid cells net > $0", value=n_grid_pos, ok=n_grid_pos >= 18),
        dict(n=9, name="At least 75 trades", value=n, ok=n >= S.MIN_TRADES_WINDOW),
    ]


def verdict(rows: list[dict]) -> str:
    by = {r["n"]: r["ok"] for r in rows}
    if by[9] is False:
        return "NOT READ (fewer than 75 trades)"
    if by[5] is False or by[6] is False:
        return "FAIL -- criterion 5 or 6 closes the study"
    return "PASS (nine of nine) -- holdout eligible, not spent" if all(by.values()) else "FAIL"


def exits(trades: list) -> dict:
    d: dict = {}
    for t in trades:
        d[t.reason] = d.get(t.reason, 0) + 1
    return d


def grid_cells(base: S.Params) -> list[tuple[int, float, int]]:
    return [(pb, bs, ew) for pb in S.GRID_PAR for bs in S.GRID_STOP for ew in S.GRID_EMA]


# ----------------------------------------------------------------------- git
def _git(*args) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


# ----------------------------------------------------------------------- run
def run(archive, out_dir: Path, stamp: str, *, selection_path: Path = SELECTION_PATH, ledger_path: Path = LEDGER_PATH,
        draws: int = DRAWS, frame: Frame | None = None, log=print) -> dict:
    if ledger_path.exists():
        raise SystemExit(f"REFUSED: {ledger_path.name} exists -- step C has been run once. A re-run after a result is a new "
                         "registration; tell Ben, do not delete the file.")
    winner, base, sel = load_selection(selection_path)
    fr = frame if frame is not None else load_training_frame(archive)
    start = window_start(fr)
    ind = indicators(fr)
    pre = E.precompute(fr, ind)
    log(f"winner {winner} {base}; frame {fr.n} bars {fr.ny[0]} .. {fr.ny[-1]}; window starts at bar {start} ({fr.ny[start]})")

    # ---- base on the window
    trades, cnt = E.simulate(fr, ind, base, start=start, pre=pre)
    B = {(sym, lv): summarize(trades, fr, sym, lv) for sym in ("MCL", "CL") for lv in S.LEVELS}
    per_year = pd.Series(np.asarray(fr.ny.year)[[t.entry_j for t in trades]]).value_counts().sort_index()
    per_year = {int(k): int(v) for k, v in per_year.items()}

    # ---- controls on the same window
    c1_tr = donchian_c1(fr, start)
    C1 = {(sym, lv): summarize(c1_tr, fr, sym, lv) for sym in ("MCL", "CL") for lv in S.LEVELS}
    cidx, cnet = c3_candidates(fr, ind, base, start)
    c3 = c3_draws(fr, cidx, cnet, per_year, draws)
    c3p = {k: float(np.percentile(c3, q)) for k, q in (("p5", 5), ("p50", 50), ("p95", 95), ("p99", 99))}
    base_net = B[("MCL", "mid")]["net"]
    c3_rank = float((c3 < base_net).mean())

    # ---- grid around the winner (prev_high and theta fixed at the winner's)
    grid = []
    for pb, bs, ew in grid_cells(base):
        tr, _ = E.simulate(fr, ind, replace(base, par_bars=pb, backstop=bs, ema_window=ew), start=start, pre=pre)
        grid.append(dict(par_bars=pb, backstop=bs, ema_window=ew, n=len(tr), net=summarize(tr, fr)["net"]))
    n_pos = sum(g["net"] > 0 for g in grid)

    crit = evaluate(B[("MCL", "mid")]["df"], B[("MCL", "high")]["df"], C1[("MCL", "mid")]["df"], c3p["p99"], n_pos)
    verd = verdict(crit)

    # ---- variants (Amendment 4.5): after step C, on the same window, reported, never selectable
    V = {}
    for name, p in S.variants_of(base).items():
        tr, vc = E.simulate(fr, ind, p, start=start, pre=pre)
        V[name] = dict(trades=tr, cnt=vc, **{f"{sym}_{lv}": summarize(tr, fr, sym, lv) for sym in ("MCL", "CL") for lv in S.LEVELS})

    # ---- consistency check with step S (development data only; information already in the selection file)
    dev_trades = [t for t in E.simulate(fr, ind, base, pre=pre)[0] if str(fr.ny[t.entry_j].date()) <= S.DEV_LAST]
    dev_df = BK.trade_frame(dev_trades, fr, "MCL", "mid")
    dev_check = dict(trades=len(dev_df), net=float(dev_df["net"].sum()),
                     sel_trades=int(sel["trades"][winner]), sel_net=float(sel["nets_mid_1mcl"][winner]))

    res = dict(stamp=stamp, winner=winner, params=repr(base), window=[S.CONF_FIRST, S.CONF_LAST], n_bars=fr.n,
               start=str(fr.ny[start]), last_bar=str(fr.ny[-1]), counts=cnt, B=B, C1=C1, c3=c3p, c3_rank=c3_rank, c3_draws=draws,
               grid=grid, n_pos=n_pos, crit=crit, verdict=verd, per_year_entries=per_year, V=V, sel=sel, dev_check=dev_check,
               trades=trades, git=dict(commit=_git("rev-parse", "HEAD") or "unknown",
                                       dirty=[x for x in _git("status", "--porcelain", "--", *GUARDED).splitlines() if x.strip()]))
    text = report(res)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"w15_0036_v2_stepC_{stamp}.txt").write_text(text, encoding="utf-8")
    B[("MCL", "mid")]["df"].to_csv(out_dir / f"w15_0036_v2_stepC_trades_{stamp}.csv", index=False)
    js = payload(res)
    (out_dir / f"w15_0036_v2_stepC_{stamp}.json").write_text(json.dumps(js, indent=1, default=str), encoding="utf-8")
    ledger_path.write_text(json.dumps(dict(winner=winner, verdict=verd, timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                           git_commit=res["git"]["commit"], net_mid_1mcl=round(base_net, 2), trades=len(trades),
                                           criteria={c["n"]: bool(c["ok"]) for c in crit},
                                           holdout="NOT spent by step C; eligible only on a nine-of-nine pass (Amendment 4.6)"), indent=2) + "\n",
                           encoding="utf-8")
    log(text)
    return res


def _js(x):
    if isinstance(x, tuple):
        return [float(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def payload(r: dict) -> dict:
    def blk(d):
        return {q: _js(d[q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "h1", "h2", "dd")}
    return dict(stamp=r["stamp"], winner=r["winner"], verdict=r["verdict"], window=r["window"],
                criteria=[{**c, "value": _js(c["value"])} for c in r["crit"]], c3=r["c3"], c3_rank=r["c3_rank"],
                grid=r["grid"], n_pos=r["n_pos"], dev_check=r["dev_check"], exits=exits(r["trades"]), counts=r["counts"],
                base={f"{s}_{l}": blk(v) for (s, l), v in r["B"].items()},
                base_year={int(y): float(v) for y, v in r["B"][("MCL", "mid")]["year_net"].items()},
                c1={f"{s}_{l}": blk(v) for (s, l), v in r["C1"].items()},
                c1_year={int(y): float(v) for y, v in r["C1"][("MCL", "mid")]["year_net"].items()},
                variants={k: dict(fills=v["cnt"]["fills"], exits=exits(v["trades"]),
                                  **{m: blk(v[m]) for m in ("MCL_mid", "MCL_high", "CL_mid")}) for k, v in r["V"].items()},
                dev_nets_mid_1mcl=r["sel"]["nets_mid_1mcl"], git=r["git"])


def _fmt(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(money(x) if abs(x) > 5 else f"{x:.3f}" for x in v) + ")"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 5 else money(v)
    return str(v)


def report(r: dict) -> str:
    m, h, cl = r["B"][("MCL", "mid")], r["B"][("MCL", "high")], r["B"][("CL", "mid")]
    C1 = r["C1"][("MCL", "mid")]
    L = [f"W15-0036 CHARTMARK-v2 step C -- confirmation of {r['winner']} on {r['window'][0]} .. {r['window'][1]}, run {r['stamp']}",
         "Registered: REGISTERED_chartmark_v2.md Amendments 4.3, 4.5, 5. 1 MCL, IBKR costs (MCL $0.77 per side + 0/1/2 ticks). "
         "Negatives in brackets.",
         f"Frame {r['n_bars']} bars to {r['last_bar']}; engine flat until {r['start']}. No bar from 2022 on was read.",
         f"Candidate {r['winner']}: {r['params']}", "", f"VERDICT: {r['verdict']}", ""]
    L += ["HEADLINE (base, 1 MCL, mid):",
          f"  trades {m['n']}  wins {m['wins']}  losses {m['losses']}  gross {money(m['gross'])}  costs {money(m['cost'])}  net {money(m['net'])}",
          f"  avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  worst losing run {m['streak']}  max drawdown {money(m['dd'])}",
          f"  net at low / mid / high friction: {money(r['B'][('MCL','low')]['net'])} / {money(m['net'])} / {money(h['net'])}   1 CL mid net {money(cl['net'])}",
          f"  halves (median trade date) {money(m['h1'])} / {money(m['h2'])}", ""]
    L += ["AMENDMENT 4.3 CRITERIA:"]
    for c in r["crit"]:
        L.append(f"  {c['n']}. {c['name']:<62s} {'PASS' if c['ok'] else 'FAIL':5s} {_fmt(c['value'])}")
    L += ["", "  (criterion 5 value = base net, C1 net, base net/std, C1 net/std; criterion 6 value = base net, C3 p99)", ""]
    L += ["BASE per year (1 MCL, mid):", f"  {'year':>5} {'trades':>7} {'W/L':>9} {'gross':>10} {'cost':>9} {'net':>10}   C1 net"]
    df = m["df"]
    c1y = C1["year_net"]
    for y, g in df.groupby("year"):
        L.append(f"  {y:>5} {len(g):>7} {int((g.net>0).sum()):>4}/{int((g.net<0).sum()):<4} {money(g.gross.sum()):>10} "
                 f"{money(g.cost.sum()):>9} {money(g.net.sum()):>10}   {money(c1y.get(int(y), 0.0))}")
    L += ["", "EXITS BY TYPE (base): " + str(exits(r["trades"])),
          f"arms {r['counts']['fills_by_arm']}  orders {r['counts']['orders']}  fills {r['counts']['fills']}  unfilled {r['counts']['unfilled']}  "
          f"positions cut at the window end (data_end) {exits(r['trades']).get('data_end', 0)}", ""]
    L += ["CONTROLS (1 MCL, mid, same window):",
          f"  C1 Donchian 20/10 long, no session filter: trades {C1['n']}  net {money(C1['net'])}  (high {money(r['C1'][('MCL','high')]['net'])})  "
          f"halves {money(C1['h1'])} / {money(C1['h2'])}",
          f"  C3 random entries, same count per year ({r['c3_draws']:,} seeded draws): p5 {money(r['c3']['p5'])}  p50 {money(r['c3']['p50'])}  "
          f"p95 {money(r['c3']['p95'])}  p99 {money(r['c3']['p99'])}; the base beats {100*r['c3_rank']:.1f}% of draws", ""]
    L += [f"NEIGHBOUR GRID (27 cells around {r['winner']}, unranked): {r['n_pos']} of 27 net > $0 at mid.",
          "  cells (parallel bars, backstop, EMA21 window -> trades, net):"]
    for g in r["grid"]:
        L.append(f"   par={g['par_bars']} stop=${g['backstop']:.2f} ema={g['ema_window']} -> {g['n']:5d}  {money(g['net'])}")
    L += ["", "VARIANTS (Amendment 4.5; reported, never selectable, cannot spend the holdout; 1 MCL mid): "
          "trades / W-L / gross / net / net at high / max DD"]
    for k, v in r["V"].items():
        x = v["MCL_mid"]
        L.append(f"  {k:<12s} {x['n']:5d}  {x['wins']}/{x['losses']}  {money(x['gross']):>10}  {money(x['net']):>10}  "
                 f"{money(v['MCL_high']['net']):>10}  DD {money(x['dd'])}  exits {exits(v['trades'])}")
    d = r["dev_check"]
    L += ["", "DEVELOPMENT WINDOW, for the record (2010-06 .. 2015-12, from step S): "
          + "  ".join(f"{k} {money(v)}" for k, v in r["sel"]["nets_mid_1mcl"].items()),
          f"  Consistency check: {r['winner']} re-run on the full frame gives {d['trades']} trades / net {money(d['net'])} on 2010-2015 entries; "
          f"step S recorded {d['sel_trades']} / {money(d['sel_net'])} (the last position is cut at 2015-12-31 there, carried here).",
          "", "CAVEATS:",
          "  * Six years, not twelve (Amendment 4.8): criteria 4 (bootstrap by year, 6 resamplable years) and 8 (grid) rest on half the data.",
          "  * C3 draws are independent single-trade outcomes (overlap allowed), as CHARTMARK-v1's C3 was; the entry bar's low is taken as after the entry.",
          "  * Prices are difference-back-adjusted over the whole training archive; decisions are relative to nearby bars.",
          "  * The K1-K4 selection (a multiplicity of four) and the exploratory numbers of sec 0.2 are disclosed costs of this design; the confirmation window was never read by step S.",
          f"  * Git: {r['git']['commit']}" + (f"  UNCOMMITTED under the registered paths: {r['git']['dirty']}" if r["git"]["dirty"] else ""), ""]
    return "\n".join(L)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- step C runs the step-S winner on 2016-2021, nothing else (Amendment 4.3).\n")
        return 2
    ap = argparse.ArgumentParser(description="CHARTMARK-v2 step C (confirmation window, step-S winner only).")
    ap.add_argument("--archive", help="archive path (default: the program's futures archive)")
    ap.add_argument("--out", default=str(OUT), help="output folder")
    a = ap.parse_args(argv)
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
