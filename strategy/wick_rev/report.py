#!/usr/bin/env python3
"""WICK-REV plain-text report. W15-0063. Dollars in brackets when negative; percentages as plain points.

Fixed order, never ranked: MCL 30m, 1H, 4H, then MNQ 30m, 1H, 4H.
"""
from __future__ import annotations

import math

from strategy.wick_rev import spec as S
from strategy.wick_rev.study import SIDE_NAME


def usd(x: float) -> str:
    if x != x:
        return "n/a"
    return f"${x:,.0f}" if x >= 0 else f"(${-x:,.0f})"


def usd2(x: float) -> str:
    if x != x:
        return "n/a"
    return f"${x:,.2f}" if x >= 0 else f"(${-x:,.2f})"


def pc(x: float, d: int = 1) -> str:
    return "n/a" if x != x else f"{100 * x:.{d}f}%"


def pts(x: float, d: int = 2) -> str:
    """Percentage POINTS (edge); negatives bracketed."""
    if x != x:
        return "n/a"
    return f"+{100 * x:.{d}f}" if x >= 0 else f"({100 * -x:.{d}f})"


def _row(g: dict, with_ci: bool = True) -> str:
    e = g["edge"]
    ci = f"[{pts(e['lo95'])} .. {pts(e['hi95'])}]" if with_ci else ""
    cum = " ".join(pc(g["cum"][m], 0).rjust(4) for m in S.CUM_BARS)
    return (f"  {g['name'][:30]:<30} {g['n']:>7} {pc(g['p_rev']):>7} {pc(g['p_rev_decided']):>7} "
            f"{pc(g['base_p']):>7} {pts(e['edge']):>8} {ci:<22} {g['amb3']:>5} | {cum} | "
            f"{g['median_tau'] if g['median_tau'] == g['median_tau'] else float('nan'):>4.0f}")


HEAD = (f"  {'group':<30} {'n':>7} {'P(rev)':>7} {'P|dec':>7} {'base':>7} {'edge pp':>8} {'95% CI (pp)':<22} {'ambig':>5} "
        f"| reversed by bar {' '.join(str(m).rjust(4) for m in S.CUM_BARS)} | med tau")


def _money_block(m: dict, title: str) -> list[str]:
    out = [f"  {title}: {m['trades']} trades ({m['skipped']} skipped, position open), "
           f"{m['wins']} wins / {m['losses']} losses at mid",
           f"    gross {usd(m['gross'])} | costs low {usd(m['cost']['low'])} mid {usd(m['cost']['mid'])} "
           f"high {usd(m['cost']['high'])}",
           f"    NET low {usd(m['net']['low'])} | mid {usd(m['net']['mid'])} | high {usd(m['net']['high'])} | "
           f"avg per trade at mid {usd2(m['avg_net_mid'])}",
           f"    exits: " + ", ".join(f"{k} {v}" for k, v in m["by_reason"].items())]
    if "net_mid_halves" in m:
        a, b = m["net_mid_halves"]
        out.append(f"    net at mid by half: first {usd(a)} | second {usd(b)}")
    if m["by_year"]:
        out.append("    net at mid by year: " + ", ".join(f"{y} {usd(v)}" for y, v in m["by_year"].items()))
    return out


def combo_report(res: dict, *, window: str) -> str:
    L = []
    tag = "REPORTED ONLY (no pass/fail)" if res["reported_only"] else "scored"
    L.append("=" * 118)
    L.append(f"{res['market']} {res['tf']}   {tag}   window: {window}")
    L.append("=" * 118)
    c = res["counts"]
    L.append(f"bars {c['bars']}  dropped: H=L {c['dropped_hl']}, warm-up {c['dropped_warmup']}, roll {c['dropped_roll']}, "
             f"tail {c['dropped_tail']}  | valid {c['valid']}  up-context {c['up_ctx']}  down-context {c['down_ctx']}")
    for side, sd in res["sides"].items():
        name = SIDE_NAME[side]
        L.append("")
        L.append("-" * 118)
        L.append(f"{res['market']} {res['tf']} - {name}: {sd['n_base_bars']} context bars")
        L.append("-" * 118)
        rd = sd.get("reading", {})
        L.append(f"READING: {rd.get('verdict')}")
        for k_, v_ in rd.get("checks", {}).items():
            L.append(f"   check {k_}: {'yes' if v_ else 'NO'}")
        for r_ in rd.get("reasons", []):
            L.append(f"   {r_}")
        if not sd["by_k"]:
            continue
        for k, blk in sd["by_k"].items():
            head = "  <-- HEADLINE" if abs(k - S.K_HEADLINE) < 1e-9 else "  (side check, fixed in advance, never ranked)"
            L.append("")
            L.append(f"k = {k} x ATR, judged on the next {S.WINDOW} bars{head}")
            L.append(HEAD)
            L.append(_row(blk["all"], with_ci=False))
            L.append(_row(blk["primary"]))
            for g in blk["buckets"]:
                L.append(_row(g))
            L.append("  primary group split by bar size (edge vs the base rate of that size) and colour:")
            for g in blk["size"] + blk["colour"]:
                L.append(_row(g))
            L.append(_row(blk["classic"]))
            L.append("  Spearman rho (descriptive only, month-block 95% CI):")
            for key, lab in (("rho_tau_all", "ratio vs bars-to-reversal, all reversals"),
                             ("rho_tau_primary", "ratio vs bars-to-reversal, primary group"),
                             ("rho_flag_all", "ratio vs reversed-by-bar-3 flag, all bars"),
                             ("rho_flag_primary", "ratio vs reversed-by-bar-3 flag, primary group")):
                r = blk[key]
                L.append(f"    {lab:<46} rho {r['rho']:+.3f}  [{r['lo95']:+.3f} .. {r['hi95']:+.3f}]  n={r['n']}")
            if "halves" in blk:
                h = blk["halves"]
                L.append(f"  halves (split at {h['cut']}): edge first {pts(h['edge'][0])} (n={h['n'][0]}) | "
                         f"second {pts(h['edge'][1])} (n={h['n'][1]})")
                if blk["primary"]["edge"]["lo995"] == blk["primary"]["edge"]["lo995"]:
                    e = blk["primary"]["edge"]
                    L.append(f"  99.5% CI (Bonferroni, 10 tests): [{pts(e['lo995'])} .. {pts(e['hi995'])}] pp")
                L.append("  excess reversals by year: " + ", ".join(f"{y} {v:+.0f}" for y, v in blk["year_excess"].items())
                         + f" | largest year share {pc(blk['max_year_share'], 0)}")
        L.append("")
        L.append(f"DOLLARS, 1 contract, entry at the open of t+1, stop/target 1 x ATR, time exit at the close of t+{S.WINDOW}")
        mi = sd["money"]
        L.extend(_money_block(mi["primary"], "primary group"))
        L.extend(_money_block(mi["classic"], "classic shape"))
        L.append("  by bucket (net at mid):")
        for i, b in enumerate(mi["buckets"]):
            L.append(f"    {i/10:.1f}-{(i+1)/10:.1f}: {b['trades']:>6} trades, net low {usd(b['net']['low'])}, "
                     f"mid {usd(b['net']['mid'])}, high {usd(b['net']['high'])}")
        if mi["primary"]["samples"]:
            L.append("  sample trades (primary group): date, entry, exit, reason, net at mid")
            for d, en, ex, rs, nt in mi["primary"]["samples"]:
                L.append(f"    {d}  {en:>12.2f} {ex:>12.2f}  {rs:<10} {usd2(nt)}")
    return "\n".join(L)


def counts_report(res_counts: list[tuple[str, str, dict]], window: str) -> str:
    L = [f"G2 COUNT-ONLY PRE-FLIGHT - window {window}", "No race outcome and no P&L has been read.", ""]
    for market, tf, c in res_counts:
        L.append(f"{market} {tf}: bars {c['bars']}, dropped H=L {c['dropped_hl']}, warm-up {c['dropped_warmup']}, "
                 f"roll {c['dropped_roll']}, tail {c['dropped_tail']}, valid {c['valid']}, "
                 f"up-context {c['up_ctx']}, down-context {c['down_ctx']}")
        for name in ("up", "down"):
            L.append(f"   {name}: primary group (ratio >= 0.6) {c[name + '_primary']} signals "
                     f"({'ENOUGH' if c[name + '_primary'] >= S.MIN_SIGNALS else 'NOT ENOUGH'} for {S.MIN_SIGNALS}); "
                     f"classic shape {c[name + '_classic']}")
            L.append("     per bucket 0.0..1.0: " + " ".join(str(x) for x in c[name + "_bucket"]))
            by = c[name + "_primary_by_year"]
            L.append("     primary per year: " + ", ".join(f"{y}:{n}" for y, n in by.items()))
        L.append("")
    return "\n".join(L)


def header(mode: str, extra: str = "") -> str:
    return (f"WICK-REV (W15-0063) - {mode}\nRegistered: {S.REGISTRATION} (13d9516 + Amendment A 1418297 + Amendment B)\n"
            f"Costs, IBKR per side: MCL fee {S.MARKETS['MCL']['fee']}, MNQ fee {S.MARKETS['MNQ']['fee']} + 0/1/2 ticks "
            f"(low/mid/high). Headline = mid.\n{extra}")
