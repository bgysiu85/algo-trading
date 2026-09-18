#!/usr/bin/env python3
r"""The arms, the controls and the seven criteria -- read off one ledger.

    python -m strategy.orb.sip_report
    python -m strategy.orb.sip_report --out var/reports/orb_sip.txt \
        --csv var/reports/orb_sip_arms.csv

`REGISTERED_orb_sip.md` sections 4 and 5, with amendment C's unit. Nothing is
simulated here: `sip_run` produced the trades, and every arm below is a
SELECTION over that one ledger, so two arms cannot differ by anything except
which rows they contain.

THE UNIT IS R (amendment C). A trade's P/L divided by its own registered risk
-- entry to the 10%-ATR stop -- because this universe runs from $6 to $600 and
a fixed share count would make a per-trade dollar average a price-weighted
average of unlike bets. Equal risk per trade is also what the paper does.

WHAT DECIDES A PASS, and it is not the headline
-----------------------------------------------
Two controls, both registered before the run:

  UNFILTERED   the same trigger on every qualifying name, no ranking. The
               paper's own base case (Sharpe 0.48 against 2.81). If the
               top-20 arm reads like this one, the selection rule -- which is
               where the paper's edge lives -- did not transfer.

  RANDOM-20    2,000 seeded draws of 20 eligible names per session. The
               top-20 arm must beat this distribution's 95th percentile.
               `first_entry_skip_RESULT_20260917.md` is why: on a book that
               loses per trade, trading fewer names improves every total-based
               reading while changing nothing about selection.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, pct
from strategy.orb import sip as S

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
RISK_DOLLARS = 100.0          # amendment C: R x $100 is the reported book
MAX_SHARES = 10_000
MIN_R_PER_TRADE = 0.05        # criterion 3, amendment C.2
MIN_TRADES = 100              # criterion 4
DROPS = (1, 3, 5)
TOP_NS = (10, 20, 40)
PRIMARY_RANGE = 5
PRIMARY_TOP_N = 20
RANDOM_DRAWS = 2000
HOLDOUT_FROM = "2026-05-01"


def load_ledger(trades_dir: Path, spend_holdout: bool = False) -> pd.DataFrame:
    files = sorted(trades_dir.glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(f"no ledger files under {trades_dir}")
    df = pd.concat([pd.read_csv(f, encoding="utf-8") for f in files],
                   ignore_index=True)
    if not spend_holdout:
        df = df[df["date"] < HOLDOUT_FROM]
    return df


def shares_for(r: np.ndarray) -> np.ndarray:
    """Equal risk per trade: $100 of risk, floored, and never zero."""
    with np.errstate(divide="ignore", invalid="ignore"):
        n = np.floor(RISK_DOLLARS / np.asarray(r, float))
    return np.clip(np.nan_to_num(n, nan=0.0), 1, MAX_SHARES).astype(int)


def add_net(df: pd.DataFrame, alt: bool = False) -> pd.DataFrame:
    """Per-trade net in R at every friction level.

    `alt=True` reads amendment A's other exit (stop live from the next bar)
    on the same entries, which is the registered sensitivity.
    """
    out = df.copy()
    exit_px = out["alt_exit_px"] if alt else out["exit_px"]
    reason = out["alt_exit_reason"] if alt else out["exit_reason"]
    out["shares"] = shares_for(out["r"].to_numpy())
    out["gross_R"] = (exit_px - out["entry_px"]) * out["side"] / out["r"]
    for fr in S.LEVELS:
        cents = np.where(reason.to_numpy() == "stop", fr.stop_cents,
                         fr.close_cents)
        slip = (fr.entry_cents + cents) / out["r"].to_numpy()
        comm = np.array([
            (S.commission(sh, px, False, fr.commission)
             + S.commission(sh, px, True, fr.commission))
            for sh, px in zip(out["shares"], out["entry_px"])])
        comm_R = comm / (out["r"].to_numpy() * out["shares"].to_numpy())
        out[f"R_{fr.name}"] = out["gross_R"] - slip - comm_R
        out[f"fricshare_{fr.name}"] = slip + comm_R
    return out


def arm(df: pd.DataFrame, range_minutes: int, kind: str, top_n: int = 20) -> pd.DataFrame:
    d = df[df["range"] == range_minutes]
    if kind == "top":
        return d[d["rank"].le(top_n)]
    if kind == "eligible":
        return d[d["eligible"].astype(bool)]
    if kind == "unfiltered":
        return d
    raise ValueError(kind)


def read_arm(d: pd.DataFrame, level: str, split_date: str) -> dict:
    col = f"R_{level}"
    n = len(d)
    if not n:
        return {"trades": 0}
    by_sym = d.groupby("symbol")[col].apply(list).to_dict()
    tot = {s: float(np.sum(v)) for s, v in by_sym.items()}
    total = float(sum(tot.values()))
    out = {
        "trades": n,
        "symbols": len(tot),
        "sessions": d["date"].nunique(),
        "mean_R": total / n,
        "total_R": total,
        "book_dollars": total * RISK_DOLLARS,
        "gross_R": float(d["gross_R"].mean()),
        "friction_R": float(d[f"fricshare_{level}"].mean()),
        "win_rate": float((d[col] > 0).mean()),
        "stop_share": float((d["exit_reason"] == "stop").mean()),
        "gapped_share": float(d["gapped_entry"].astype(bool).mean()),
        "long_mean_R": float(d[d["side"] == 1][col].mean()) if (d["side"] == 1).any() else float("nan"),
        "short_mean_R": float(d[d["side"] == -1][col].mean()) if (d["side"] == -1).any() else float("nan"),
        "early_R": float(d[d["date"] < split_date][col].sum()),
        "late_R": float(d[d["date"] >= split_date][col].sum()),
    }
    ranked = sorted(tot.values(), reverse=True)
    for k in DROPS:
        out[f"drop{k}_R"] = float(sum(ranked[k:]))
    boot = cluster_bootstrap(by_sym, RESAMPLES, SEED)
    out["boot_p"] = float(np.mean(np.asarray(boot["totals"]) > 0))
    out["boot_lo"] = float(pct(boot["totals"], 0.025))
    out["boot_hi"] = float(pct(boot["totals"], 0.975))
    return out


def random_control(df: pd.DataFrame, range_minutes: int, level: str,
                   top_n: int = PRIMARY_TOP_N, draws: int = RANDOM_DRAWS,
                   seed: int = SEED) -> dict:
    """`draws` books of `top_n` ELIGIBLE names a session, drawn at random.

    The population is the one the ranking chose from -- eligible names, RVOL
    at least 1 -- so the only difference between this and the real arm is
    whether RVOL decided which 20. Anything the real arm gains by trading
    fewer names is already in here.
    """
    d = arm(df, range_minutes, "eligible")
    col = f"R_{level}"
    per_session = [g[col].to_numpy() for _, g in d.groupby("date", sort=True)]
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for i in range(draws):
        s = 0.0
        n = 0
        for vals in per_session:
            k = min(top_n, len(vals))
            pick = rng.choice(vals, size=k, replace=False) if len(vals) > k else vals
            s += float(pick.sum())
            n += k
        means[i] = s / n if n else 0.0
    return {"draws": draws, "mean": float(means.mean()),
            "p50": float(np.percentile(means, 50)),
            "p95": float(np.percentile(means, 95)),
            "max": float(means.max())}


def paper_book(df: pd.DataFrame, level: str, start_equity: float = 25_000.0,
               positions: int = 20, risk_pct: float = 0.01,
               leverage: float = 4.0) -> dict:
    """Section 3.4's book: 1% of a position's capital at risk, 4x cap.

    Reported for comparability with the paper's 41.6% IRR. It never passes a
    criterion: a portfolio return mixes the trade's edge with a sizing rule.
    """
    d = arm(df, PRIMARY_RANGE, "top", positions).sort_values(["date", "rank"])
    equity = start_equity
    curve, peak, mdd = [], start_equity, 0.0
    for day, g in d.groupby("date", sort=True):
        capital = equity / positions
        pnl = 0.0
        for t in g.itertuples():
            shares = int(min(risk_pct * capital / t.r,
                             leverage * capital / t.entry_px))
            if shares < 1:
                continue
            trade = S.Trade(t.symbol, t.date, int(t.side), int(t.entry_min),
                            t.entry_px, int(t.exit_min), t.exit_px,
                            t.exit_reason, 0.0, t.r, int(t.bars_held),
                            t.or_high, t.or_low)
            fr = {f.name: f for f in S.LEVELS}[level]
            pnl += S.net(trade, shares, fr)
        equity += pnl
        curve.append((day, equity))
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak if peak > 0 else 0.0)
    years = len(curve) / 252.0 if curve else 0.0
    total = equity / start_equity - 1.0
    irr = ((1 + total) ** (1 / years) - 1.0) if years > 0 and total > -1 else float("nan")
    return {"final_equity": equity, "total_return": total, "irr": irr,
            "max_drawdown": mdd, "sessions": len(curve)}


def deciles(df: pd.DataFrame, level: str) -> pd.DataFrame:
    d = arm(df, PRIMARY_RANGE, "eligible").copy()
    d["decile"] = pd.qcut(d["rvol"].rank(method="first"), 10, labels=False) + 1
    return d.groupby("decile").agg(trades=(f"R_{level}", "size"),
                                   mean_R=(f"R_{level}", "mean"),
                                   median_rvol=("rvol", "median"))


def criteria(a: dict, ctrl: dict, unf: dict, boundary: dict) -> list[tuple]:
    """(number, what, value, verdict). Read on the primary cell only."""
    rows = [
        (1, "drop-top-3 and drop-top-5 > 0",
         f"{a['drop3_R']:+.1f}R / {a['drop5_R']:+.1f}R",
         a["drop3_R"] > 0 and a["drop5_R"] > 0),
        (2, f"cluster bootstrap P(total>0) >= {BOOT_MIN_P:.2f}",
         f"{a['boot_p']:.3f}", a["boot_p"] >= BOOT_MIN_P),
        (3, f"mean net >= +{MIN_R_PER_TRADE:.2f}R per trade",
         f"{a['mean_R']:+.3f}R", a["mean_R"] >= MIN_R_PER_TRADE),
        (4, f"trades >= {MIN_TRADES}", f"{a['trades']:,}",
         a["trades"] >= MIN_TRADES),
        (5, "both halves > 0", f"{a['early_R']:+.1f}R / {a['late_R']:+.1f}R",
         a["early_R"] > 0 and a["late_R"] > 0),
        (6, "both sides > 0",
         f"long {a['long_mean_R']:+.3f}R / short {a['short_mean_R']:+.3f}R",
         a["long_mean_R"] > 0 and a["short_mean_R"] > 0),
        (7, "no optimum on a boundary",
         f"range {boundary['best_range']} min, top-{boundary['best_top_n']}",
         boundary["interior"]),
    ]
    return rows


def boundary_read(df: pd.DataFrame, level: str, split_date: str) -> dict:
    """Criterion 7 over the two ordered families: range length and top-N."""
    per_range = {n: read_arm(arm(df, n, "top", PRIMARY_TOP_N), level, split_date)
                 for n in (5, 15)}
    per_top = {n: read_arm(arm(df, PRIMARY_RANGE, "top", n), level, split_date)
               for n in TOP_NS}
    best_range = max(per_range, key=lambda n: per_range[n].get("mean_R", -9e9))
    best_top = max(per_top, key=lambda n: per_top[n].get("mean_R", -9e9))
    return {"per_range": per_range, "per_top": per_top,
            "best_range": best_range, "best_top_n": best_top,
            # 5 is the registered primary and the paper's own edge of the
            # family; 15 is the only other value run, so this family is all
            # boundary and the rule can only be reported (ORB's STOP_MODE
            # precedent). Top-N has an interior value, 20.
            "interior": best_top == PRIMARY_TOP_N}


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------

def _arm_line(label: str, a: dict) -> str:
    if not a.get("trades"):
        return f"  {label:<26} no trades"
    return (f"  {label:<26} {a['trades']:>7,} {a['mean_R']:>+8.3f} "
            f"{a['gross_R']:>+8.3f} {a['friction_R']:>7.3f} "
            f"{a['total_R']:>+9.1f} {a['drop5_R']:>+9.1f} "
            f"{a['win_rate']:>6.1%} {a['boot_p']:>6.3f}")


def render(df: pd.DataFrame, level: str, split_date: str, arms: dict,
           ctrl: dict, boundary: dict, book: dict, dec: pd.DataFrame,
           alt: dict, spend_holdout: bool) -> list[str]:
    a = arms[f"top{PRIMARY_TOP_N}"]
    L = [
        "ORB, STOCKS IN PLAY -- OUT OF SAMPLE", "",
        f"  registration     docs/research/REGISTERED_orb_sip.md (+ A, B, C)",
        f"  prices           XNAS.ITCH RTH minute bars (amendment B)",
        f"  ranking volume   XNAS.BASIC opening-range volume",
        f"  sessions         {df['date'].nunique():,}  "
        f"{df['date'].min()} -> {df['date'].max()}",
        f"  holdout          {'SPENT -- ' + HOLDOUT_FROM + ' onward included' if spend_holdout else HOLDOUT_FROM + ' onward WITHHELD'}",
        f"  unit             R = P/L / the trade's own 10%-ATR risk "
        f"(amendment C); the book is R x ${RISK_DOLLARS:,.0f}",
        f"  friction         criteria read at {level}; "
        + ", ".join(f"{f.name} {f.entry_cents*100:.0f}/{f.stop_cents*100:.0f}c"
                    for f in S.LEVELS),
        f"  halves split     {split_date}  (median session date, not swept)",
        f"  bootstrap        {RESAMPLES:,} symbol-cluster resamples, seed {SEED}",
        "",
        "  A cell that beats the primary is a LEAD, not a result. Nothing here",
        "  ships, and the paper's book below never passes a criterion.", "",
        "THE SEVEN CRITERIA -- PRIMARY CELL ONLY "
        f"(range {PRIMARY_RANGE} min, top {PRIMARY_TOP_N}, {level})", "",
    ]
    for n, what, val, ok in criteria(a, ctrl, arms["unfiltered"], boundary):
        L.append(f"  {n}. {what:<44} {val:>26}   "
                 f"{'pass' if ok else 'FAIL'}")
    passes = sum(1 for *_x, ok in criteria(a, ctrl, arms['unfiltered'], boundary) if ok)
    L += ["", f"  {passes} of 7 met.", ""]

    L += ["EVERY ARM, AT " + level, "",
          "  arm                        trades   mean_R  gross_R  fric_R "
          "  total_R    drop5_R    win  boot_p",
          "  " + "-" * 96]
    for label in (f"top{PRIMARY_TOP_N}", "top10", "top40", "eligible",
                  "unfiltered", "top20_15min"):
        if label in arms:
            L.append(_arm_line(label, arms[label]))
    L += ["",
          "  `unfiltered` is the paper's own base case: the same trigger with no",
          "  ranking, which it reports at Sharpe 0.48 against the top-20's 2.81.",
          "  If the two read alike here, the selection rule did not transfer.", ""]

    L += ["THE RANDOM-20 CONTROL (section 4)", "",
          f"  {ctrl['draws']:,} draws of {PRIMARY_TOP_N} eligible names a session, "
          f"same trigger, same friction", "",
          f"  random mean            {ctrl['mean']:+.3f}R",
          f"  random p50 / p95       {ctrl['p50']:+.3f}R / {ctrl['p95']:+.3f}R",
          f"  RVOL top-{PRIMARY_TOP_N}            {a['mean_R']:+.3f}R",
          f"  verdict                "
          + ("BEATS the control's p95" if a["mean_R"] > ctrl["p95"]
             else "INSIDE the control's band -- the ranking is not selection here"),
          ""]

    L += ["FRICTION, THE NUMBER THAT DECIDES THIS (amendment C.3)", "",
          "  level     mean_R    gross_R   friction_R   friction as % of R", ""]
    for f in S.LEVELS:
        aa = read_arm(arm(df, PRIMARY_RANGE, "top", PRIMARY_TOP_N), f.name, split_date)
        if aa.get("trades"):
            L.append(f"  {f.name:<8} {aa['mean_R']:+8.3f} {aa['gross_R']:+10.3f} "
                     f"{aa['friction_R']:10.3f} {aa['friction_R']*100:15.1f}%")
    L += ["",
          "  The stop sits 10% of ATR from entry, so a cent of slippage is a",
          "  large share of the risk. The paper charged commission only.", ""]

    L += ["THE BOUNDARY RULE (criterion 7)", ""]
    for n, r in boundary["per_range"].items():
        L.append(f"  range {n:>2} min      {r.get('mean_R', float('nan')):+.3f}R "
                 f"over {r.get('trades', 0):,} trades")
    for n, r in boundary["per_top"].items():
        L.append(f"  top-{n:<3}          {r.get('mean_R', float('nan')):+.3f}R "
                 f"over {r.get('trades', 0):,} trades")
    L += ["",
          "  RANGE LENGTH IS ALL BOUNDARY: 5 is the registered primary and the",
          "  paper's own value, 15 is the only other length run, so the rule is",
          "  reported rather than passed on that family (the STOP_MODE",
          "  precedent). Top-N has an interior value and 20 is it.", ""]

    L += ["AMENDMENT A -- THE OTHER READING OF THE ENTRY-BAR STOP", "",
          f"  primary (stop live on the entry bar)   {a['mean_R']:+.3f}R",
          f"  sensitivity (live from the next bar)   {alt['mean_R']:+.3f}R",
          f"  entry-bar stops                        "
          f"{alt.get('entry_bar_stop_share', float('nan')):.1%} of trades",
          "",
          "  A pass on one reading and a failure on the other is a failure: the",
          "  paper does not specify the rule.", ""]

    L += ["THE PAPER'S OWN BOOK (section 3.4), FOR COMPARABILITY ONLY", "",
          f"  $25,000 start, 1% of a position's capital at risk, 4x cap, "
          f"{PRIMARY_TOP_N} positions, {level} friction",
          f"  final equity      ${book['final_equity']:,.0f}",
          f"  total return      {book['total_return']:+.1%}",
          f"  annualised        {book['irr']:+.1%}",
          f"  max drawdown      {book['max_drawdown']:.1%}",
          f"  (the paper: +1,637% total, 41.6% a year, 12% drawdown, "
          "2016-2023, commission only)", ""]

    L += ["RVOL DECILES, ELIGIBLE NAMES (section 5)", "",
          "  decile  median RVOL   trades    mean_R", ""]
    for d, row in dec.iterrows():
        L.append(f"  {int(d):>6}  {row['median_rvol']:>11.2f} "
                 f"{int(row['trades']):>8,} {row['mean_R']:>+9.3f}")
    L += ["",
          "  If selection is real this should rise with the decile. It is a",
          "  shape, not a threshold to move the strategy to.", ""]

    L += ["COVERAGE AND MECHANICS", "",
          f"  gapped entries          {a['gapped_share']:.1%} of top-{PRIMARY_TOP_N} trades",
          f"  stop exits              {a['stop_share']:.1%}",
          f"  long / short            "
          f"{(arm(df, PRIMARY_RANGE, 'top', PRIMARY_TOP_N)['side'] == 1).mean():.1%} long",
          ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--level", default="BASE", choices=[f.name for f in S.LEVELS])
    p.add_argument("--spend-holdout", action="store_true")
    p.add_argument("--out", default="var/reports/orb_sip.txt")
    p.add_argument("--csv", default="var/reports/orb_sip_arms.csv")
    a = p.parse_args(argv)

    raw = load_ledger(Path(a.trades), a.spend_holdout)
    if raw.empty:
        sys.exit("no trades in the ledger for that window")
    df = add_net(raw)
    alt_df = add_net(raw, alt=True)

    dates = sorted(df["date"].unique())
    split_date = dates[len(dates) // 2]

    arms = {
        f"top{PRIMARY_TOP_N}": read_arm(arm(df, PRIMARY_RANGE, "top", PRIMARY_TOP_N), a.level, split_date),
        "top10": read_arm(arm(df, PRIMARY_RANGE, "top", 10), a.level, split_date),
        "top40": read_arm(arm(df, PRIMARY_RANGE, "top", 40), a.level, split_date),
        "eligible": read_arm(arm(df, PRIMARY_RANGE, "eligible"), a.level, split_date),
        "unfiltered": read_arm(arm(df, PRIMARY_RANGE, "unfiltered"), a.level, split_date),
        "top20_15min": read_arm(arm(df, 15, "top", PRIMARY_TOP_N), a.level, split_date),
    }
    ctrl = random_control(df, PRIMARY_RANGE, a.level)
    boundary = boundary_read(df, a.level, split_date)
    book = paper_book(df, a.level)
    dec = deciles(df, a.level)
    alt = read_arm(arm(alt_df, PRIMARY_RANGE, "top", PRIMARY_TOP_N), a.level, split_date)
    primary = arm(df, PRIMARY_RANGE, "top", PRIMARY_TOP_N)
    alt["entry_bar_stop_share"] = float(
        ((primary["exit_reason"] == "stop")
         & (primary["exit_min"] == primary["entry_min"])).mean())

    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(arms).T.to_csv(a.csv, encoding="utf-8")
        print(f"wrote {a.csv}")

    from common.report_io import emit
    emit("\n".join(render(df, a.level, split_date, arms, ctrl, boundary, book,
                          dec, alt, a.spend_holdout)),
         a.out,
         header=(f"strategy.orb.sip_report  level={a.level}  "
                 f"trades={len(df):,}  sessions={df['date'].nunique():,}  "
                 f"split={split_date}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
