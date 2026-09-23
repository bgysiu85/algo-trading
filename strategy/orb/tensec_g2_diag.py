#!/usr/bin/env python3
r"""G2 diagnostic -- does ohlcv-1m disagree with ohlcv-1s about what traded?

    python -m strategy.orb.tensec_g2_diag

W05-0003's G2 run found large divergences between the published (ohlcv-1m)
ORB SIP ledger and a full 1-second resimulation -- some turning a +28R
"session_end" winner into a same-day "stop" loser. Two explanations are
possible, and only one is cheap to tell apart without buying anything new:

  (1) the price genuinely, briefly touched the stop within a minute whose
      OWN low (from ohlcv-1m) should show the same touch -- real intraday
      path, not a data artifact; or
  (2) Databento's ohlcv-1m and ohlcv-1s schemas do not aggregate the exact
      same set of prints (different trade-condition filtering, corrections
      applied to one and not the other, etc.) -- in which case the two
      "ledgers" are not comparable minute-for-minute at all, and G2 as
      specified cannot pass no matter how correct the engine is.

THIS SCRIPT SETTLES IT DIRECTLY: for every symbol-day where G2's own run
disagreed with the published ledger (`tensec_g2_trades.csv.gz`), pull that
day's ohlcv-1m bars AND ohlcv-1s bars (both already on disk from G1 -- $0,
nothing new to buy), reconstruct each minute's low/high by folding the
1-second bars into the same clock-aligned minute, and compare against the
ohlcv-1m schema's own published low/high for that same minute. If they
disagree even once, the two schemas are not the same tape at finer
resolution -- explanation (2) -- and that is reported minute-by-minute.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATASET = "XNAS.ITCH"
TRADES_CSV = Path("var/cache/orb_sip/tensec_g2_trades.csv.gz")
OUT_DEFAULT = Path("var/reports/tensec_g2_diag.txt")


def minute_bars_from_seconds(sec: pd.DataFrame) -> pd.DataFrame:
    """Fold 1-second bars into clock-aligned minute OHLC, symbol-by-symbol."""
    m = (sec["minute_of_day"]).to_numpy()
    df = pd.DataFrame({"minute": m, "symbol": sec["symbol"].to_numpy(),
                        "o": sec["open"].to_numpy(float), "h": sec["high"].to_numpy(float),
                        "l": sec["low"].to_numpy(float), "c": sec["close"].to_numpy(float)})
    g = df.groupby(["symbol", "minute"], sort=True)
    out = pd.DataFrame({"open": g["o"].first(), "high": g["h"].max(),
                         "low": g["l"].min(), "close": g["c"].last()})
    return out.reset_index()


def check_day(archive: Path, day: str, symbols: list[str]) -> list[dict]:
    from common.dbn_io import read_dbn
    m1_path = archive / DATASET / "ohlcv-1m" / f"{day}_0930_1600.dbn.zst"
    s1_path = archive / DATASET / "ohlcv-1s" / f"{day}.dbn.zst"
    rows = []
    if not m1_path.exists() or not s1_path.exists():
        return [dict(symbol=s, date=day, minute=None, note=f"MISSING_FILE "
                      f"(1m={m1_path.exists()}, 1s={s1_path.exists()})") for s in symbols]

    m1 = read_dbn(m1_path)
    s1 = read_dbn(s1_path)
    et_m1 = m1.index.tz_convert("America/New_York")
    et_s1 = s1.index.tz_convert("America/New_York")
    m1 = m1.assign(minute=(et_m1.hour * 60 + et_m1.minute), symbol=m1["symbol"])
    s1 = s1.assign(minute_of_day=(et_s1.hour * 60 + et_s1.minute), symbol=s1["symbol"])

    recon = minute_bars_from_seconds(s1[s1["symbol"].isin(symbols)])

    for sym in symbols:
        official = m1[m1["symbol"] == sym][["minute", "open", "high", "low", "close"]]
        mine = recon[recon["symbol"] == sym][["minute", "open", "high", "low", "close"]]
        merged = official.merge(mine, on="minute", how="outer", suffixes=("_1m", "_1srecon"),
                                 indicator=True)
        only_1m = merged[merged["_merge"] == "left_only"]
        only_1s = merged[merged["_merge"] == "right_only"]
        both = merged[merged["_merge"] == "both"]
        for _, r in only_1m.iterrows():
            rows.append(dict(symbol=sym, date=day, minute=int(r["minute"]),
                              note="MINUTE_IN_1M_ONLY -- no seconds printed this minute at all"))
        for _, r in only_1s.iterrows():
            rows.append(dict(symbol=sym, date=day, minute=int(r["minute"]),
                              note="MINUTE_IN_1S_ONLY -- seconds printed a minute ohlcv-1m has no bar for"))
        for _, r in both.iterrows():
            lo_diff = abs(r["low_1m"] - r["low_1srecon"])
            hi_diff = abs(r["high_1m"] - r["high_1srecon"])
            if lo_diff > 1e-6 or hi_diff > 1e-6:
                rows.append(dict(symbol=sym, date=day, minute=int(r["minute"]),
                                  note=f"LOW/HIGH DISAGREE: 1m low={r['low_1m']:.4f} "
                                       f"1s-recon low={r['low_1srecon']:.4f} (diff {lo_diff:.4f}); "
                                       f"1m high={r['high_1m']:.4f} 1s-recon high={r['high_1srecon']:.4f} "
                                       f"(diff {hi_diff:.4f})"))
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--top-n", type=int, default=40,
                    help="how many of the largest R-divergent symbol-days to check "
                         "(ranked by |sec_R_BASE - ledger_R_BASE|)")
    a = p.parse_args(argv)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()

    from strategy.orb import sip_report as P
    trades = pd.read_csv(TRADES_CSV)
    led = pd.DataFrame({"side": trades["side"], "entry_px": trades["ledger_entry_px"],
                         "exit_px": trades["ledger_exit_px"], "exit_reason": trades["ledger_exit_reason"],
                         "r": trades["ledger_r"]})
    sec = pd.DataFrame({"side": trades["side"], "entry_px": trades["sec_entry_px"],
                         "exit_px": trades["sec_exit_px"], "exit_reason": trades["sec_exit_reason"],
                         "r": trades["ledger_r"]})
    trades["ledger_R_BASE"] = P.add_net(led)["R_BASE"]
    trades["sec_R_BASE"] = P.add_net(sec)["R_BASE"]
    trades["abs_delta"] = (trades["sec_R_BASE"] - trades["ledger_R_BASE"]).abs()

    disagree = trades[trades["ledger_exit_reason"] != trades["sec_exit_reason"]]
    pick = disagree.reindex(disagree["abs_delta"].sort_values(ascending=False).index).head(a.top_n)
    print(f"checking the {len(pick)} largest-divergence symbol-days "
          f"(of {len(disagree)} exit-reason disagreements total)")

    all_rows = []
    for day, g in pick.groupby("date"):
        all_rows += check_day(archive, day, sorted(g["symbol"].unique()))

    out = pd.DataFrame(all_rows)
    lines = ["G2 DIAGNOSTIC -- does ohlcv-1m disagree with ohlcv-1s?", "",
             f"Checked {len(pick)} symbol-days (the largest R divergences).", ""]
    if out.empty:
        lines.append("No disagreements found between ohlcv-1m and a fold-up of ohlcv-1s "
                      "for any checked symbol-day/minute. The divergence is a real, "
                      "same-underlying-tape price-path finding, not a data-schema artifact.")
    else:
        n_disagree_minutes = (out["note"].str.startswith("LOW/HIGH DISAGREE")).sum()
        n_missing = (~out["note"].str.startswith("LOW/HIGH DISAGREE")).sum()
        lines.append(f"{n_disagree_minutes} minute(s) where ohlcv-1m's own low/high does NOT "
                     f"match a fold-up of ohlcv-1s for the same minute -- the two schemas do "
                     f"NOT agree on what traded. {n_missing} minute-coverage mismatch(es) "
                     f"(a minute with a bar in one schema and none in the other).")
        lines.append("")
        for _, r in out.iterrows():
            lines.append(f"  {r['symbol']:<8} {r['date']}  minute={r['minute']}  {r['note']}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
