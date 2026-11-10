#!/usr/bin/env python3
"""W15-0069 sub 1: PRICE-ONLY check that the Databento account can still price the two forward tests' pulls. Buys nothing.

    D:\\Trading\\.venv\\Scripts\\python.exe -m common.forward_price_check

For the latest complete weekday UTC day it asks Databento for the COST and billable size (metadata only -- there is no get_range
call anywhere in this file) of exactly the requests the scorers make: GLBX.MDP3 CL.c.0 ohlcv-1h (W15-0037) and NQ.v.0 ohlcv-1m +
ohlcv-1d (W16-0014). Prints the dollars and this month's spend against the US$5 cap, writes
`Claude outputs\\w15_0069_price_check_<date>.txt`, and returns 0 (all priced), 4 (STOP AND ASK BEN: an access refusal, logged in the
spend ledger) or 1 (any other failure). Asked for by Ben's W15-0070 decision: check before relying on pay-as-you-go.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common import forward_spend as FS

ROOT = Path(__file__).resolve().parents[1]


def latest_complete_weekday(end_dt: datetime) -> str:
    """The latest Mon-Fri UTC day D with D+1 00:00Z <= the dataset end."""
    d = end_dt.date() - timedelta(days=1)
    if datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1) > end_dt:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def probes(day: str) -> list[tuple[str, str, dict]]:
    from strategy.chartmark_v2 import forward as CM
    from strategy.w16 import dvp_forward as DV
    return [("W15-0037", "CL.c.0 ohlcv-1h", CM.day_request(day, "ohlcv-1h")),
            ("W16-0014", "NQ.v.0 ohlcv-1m", DV.request(day, "ohlcv-1m")),
            ("W16-0014", "NQ.v.0 ohlcv-1d", DV.request(day, "ohlcv-1d"))]


def run(client, *, out: Path | None = None, now: datetime | None = None) -> int:
    from common.tsmom_fetch import _price, _retry, _scrub
    lines = [f"=== W15-0069 price-only check, {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z -- nothing was bought ==="]
    try:
        rng = client.metadata.get_dataset_range(dataset="GLBX.MDP3")
        end = datetime.fromisoformat(str(rng.get("end") or rng.get("end_date")).replace("Z", "+00:00"))
    except Exception as e:                                                  # noqa: BLE001
        msg = _scrub(e)
        lines.append(f"dataset range lookup FAILED: {msg}")
        rc = FS.EXIT_CODE if FS.is_access_refusal(msg) else 1
        if rc == FS.EXIT_CODE:
            FS.log_refusal("W15-0069", f"{FS.REFUSAL_PREFIX}: Databento refused the dataset range lookup: {msg[:200]}", now=now)
            lines.append(FS.REFUSAL_PREFIX + ": Databento refused the account (see above).")
        return _finish(lines, out, rc)
    day = latest_complete_weekday(end if end.tzinfo else end.replace(tzinfo=timezone.utc))
    lines.append(f"dataset GLBX.MDP3 ends {end:%Y-%m-%d %H:%M}Z; probe day = latest complete weekday UTC day {day}")
    total, rc = 0.0, 0
    for test, label, kw in probes(day):
        try:
            usd, nbytes = _retry(lambda kw=kw: _price(client, kw))
            total += usd
            lines.append(f"  OK      {test}  {label}  ${usd:.4f}  {nbytes:,} bytes")
        except Exception as e:                                              # noqa: BLE001
            msg = _scrub(e)
            if FS.is_access_refusal(msg):
                FS.log_refusal(test, f"{FS.REFUSAL_PREFIX}: Databento refused pricing {label}: {msg[:200]}", now=now)
                lines.append(f"  REFUSED {test}  {label}  {msg[:160]}")
                rc = FS.EXIT_CODE
            else:
                lines.append(f"  FAILED  {test}  {label}  {msg[:160]}")
                rc = rc or 1
    st = FS.status(now=now)
    lines.append(f"one day of all three pulls would cost ${total:.4f}; this month ({st['month']}) already ${st['spent_usd']:.2f} of the ${st['cap_usd']:.2f} cap.")
    lines.append({0: "RESULT: the account can still price both tests' pulls.",
                  FS.EXIT_CODE: FS.REFUSAL_PREFIX + ": Databento refused pricing (see REFUSED above). Report this line.",
                  1: "RESULT: a pricing request failed for a non-access reason (see FAILED above)."}[rc])
    return _finish(lines, out, rc)


def _finish(lines: list[str], out: Path | None, rc: int) -> int:
    txt = "\n".join(lines) + "\n"
    print(txt)
    p = out or ROOT / "Claude outputs" / f"w15_0069_price_check_{date.today().isoformat()}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    print(f"report: {p}")
    return rc


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(description="Price-only Databento check for the two forward tests. Buys nothing.")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if client is None:
        from common.tsmom_data_price import require_databento
        from common.tsmom_fetch import _key
        client = require_databento().Historical(_key())
    return run(client, out=a.out)


if __name__ == "__main__":
    raise SystemExit(main())
