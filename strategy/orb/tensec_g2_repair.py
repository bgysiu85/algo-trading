#!/usr/bin/env python3
r"""Repair the published minute-bar ledger's entry/exit for G2's own use.

`claude/w12_0005_orb_sip_recheck_RESULT_20260923.md`'s diagnostic
(`tensec_g2_diag.py`) proved Databento's official `ohlcv-1m` for XNAS.ITCH is
missing 5,898 real minutes against `ohlcv-1s`, for the 40 symbol-days with the
largest G2 divergence (39/40 affected) -- and never disagrees on a minute
both schemas cover. `strategy/orb/sip.trade_symbol_day` walks whatever minute
bars it is given to find the entry trigger and the stop; a missing minute is
invisible to that walk, so a stop due inside it silently never fires and the
trade rides to session_end instead.

THIS DOES NOT CHANGE THE REGISTERED RULE. Per `tensec_engine.py`'s own
docstring, side / or_high / or_low / r are read on minute bars and are "the
same number in every arm" -- this module takes them AS-IS from the published
ledger (unchanged, the registered host) and re-runs the exact same,
already-registered walk (`tensec_engine.b0_trade` -- gap-through fill,
amendment D's same-bar-stop convention, "the stop, or the last print at or
before 15:59:59") one more resolution down: on minute bars FOLDED FROM
`ohlcv-1s` instead of Databento's gappy `ohlcv-1m`. It is the identical rule
at a repaired resolution, not a new one -- no re-registration needed
(`REGISTERED_10sec.md` section 7.1's refusal is about changing the RULE
after seeing a result; this changes neither the fill rule nor the host, only
which minute bars feed the walk).

    from strategy.orb.tensec_g2_repair import repair_ledger
    cell = repair_ledger(cell, archive)

CORRECTION, same day (W12-0005): checking WHERE the diagnostic's 5,898
missing minutes fall shows all of them outside RTH (4,308 pre-market,
1,590 post-market, 0 within 09:30-15:59) across all 40 checked symbol-days
-- so this repair is a no-op for every trade G2 scores, and it is NOT what
explains G2's divergence. Left here, unwired, as a correct, tested utility
in case a genuine RTH ohlcv-1m coverage gap ever turns up elsewhere; it is
not imported by tensec_g2.py. See the Result doc's second revision for the
actual explanation (entry-bar stop-order ambiguity + genuine intra-minute
entry-price gaps -- both real, resolution-driven findings, not schema bugs).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.orb import tensec_engine as E

DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"


def minute_bars_from_seconds(sec: pd.DataFrame) -> pd.DataFrame:
    """Fold 1-second bars into clock-aligned minute OHLC, symbol-by-symbol.
    Identical fold-up to `tensec_g2_diag.py`'s (proven: 0 disagreements
    against the official ohlcv-1m wherever both schemas have a bar)."""
    m = sec["minute_of_day"].to_numpy()
    df = pd.DataFrame({"minute": m, "symbol": sec["symbol"].to_numpy(),
                        "o": sec["open"].to_numpy(float), "h": sec["high"].to_numpy(float),
                        "l": sec["low"].to_numpy(float), "c": sec["close"].to_numpy(float)})
    g = df.groupby(["symbol", "minute"], sort=True)
    out = pd.DataFrame({"open": g["o"].first(), "high": g["h"].max(),
                         "low": g["l"].min(), "close": g["c"].last()})
    return out.reset_index()


def repair_day(archive: Path, day: str, rows: pd.DataFrame) -> list[dict]:
    """`rows`: this day's primary-cell ledger rows. Needs symbol, side,
    or_high, or_low, r, entry_px, exit_px, exit_reason, gapped_entry (the
    last four are replaced when a repair succeeds; kept as-is otherwise)."""
    from common.dbn_io import read_dbn
    src = archive / DATASET / SCHEMA / f"{day}.dbn.zst"
    out = []
    if not src.exists():
        for r in rows.itertuples():
            out.append(dict(symbol=r.symbol, date=day, repaired=False,
                             entry_px=r.entry_px, exit_px=r.exit_px,
                             exit_reason=r.exit_reason,
                             gapped_entry=bool(r.gapped_entry), why="NO_1S_FILE"))
        return out

    s1 = read_dbn(src)
    et = s1.index.tz_convert("America/New_York")
    s1 = s1.assign(minute_of_day=(et.hour * 60 + et.minute))
    recon = minute_bars_from_seconds(s1[s1["symbol"].isin(rows["symbol"])])

    for r in rows.itertuples():
        m = recon[recon["symbol"] == r.symbol].sort_values("minute")
        if m.empty:
            out.append(dict(symbol=r.symbol, date=day, repaired=False,
                             entry_px=r.entry_px, exit_px=r.exit_px,
                             exit_reason=r.exit_reason,
                             gapped_entry=bool(r.gapped_entry), why="NO_1S_BARS"))
            continue
        sod = (m["minute"].to_numpy() * 60)
        t, why = E.b0_trade(sod, m["open"].to_numpy(float), m["high"].to_numpy(float),
                            m["low"].to_numpy(float), m["close"].to_numpy(float),
                            int(r.side), float(r.or_high), float(r.or_low), float(r.r))
        if t is None:
            out.append(dict(symbol=r.symbol, date=day, repaired=False,
                             entry_px=r.entry_px, exit_px=r.exit_px,
                             exit_reason=r.exit_reason,
                             gapped_entry=bool(r.gapped_entry), why=why))
            continue
        trigger = r.or_high if r.side == E.LONG else r.or_low
        out.append(dict(symbol=r.symbol, date=day, repaired=True,
                         entry_px=t.entry_px, exit_px=t.exit_px,
                         exit_reason=t.exit_reason,
                         gapped_entry=bool(abs(t.entry_px - trigger) > 1e-9), why=why))
    return out


def repair_ledger(cell: pd.DataFrame, archive: Path) -> pd.DataFrame:
    """Returns `cell` with entry_px/exit_px/exit_reason/gapped_entry
    replaced by the repaired-minute-bar walk. side/or_high/or_low/r/atr/
    range are untouched -- the registered host, per tensec_engine.py."""
    parts = []
    for day, g in cell.groupby("date", sort=True):
        parts += repair_day(archive, day, g)
    rep = pd.DataFrame(parts)
    merged = cell.merge(rep, on=["symbol", "date"], how="left", suffixes=("_orig", ""))

    missing = ~merged["repaired"].fillna(False)
    n_bad = int(missing.sum())
    if n_bad:
        print(f"  repair: {n_bad:,} / {len(merged):,} rows could not be repaired "
              "(no 1s file/bars, or no trade at repaired resolution) -- "
              "original ledger values kept for these")
        for col in ("entry_px", "exit_px", "exit_reason", "gapped_entry"):
            merged.loc[missing, col] = merged.loc[missing, f"{col}_orig"]

    n_changed = int(((merged["exit_reason"] != merged["exit_reason_orig"]) |
                     ((merged["entry_px"] - merged["entry_px_orig"]).abs() > 1e-6)).sum())
    print(f"  repair: {n_changed:,} / {len(merged):,} trades changed entry price "
          "or exit reason vs the published ledger")

    drop = [c for c in merged.columns if c.endswith("_orig")] + ["repaired", "why"]
    return merged.drop(columns=drop)
