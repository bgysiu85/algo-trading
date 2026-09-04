#!/usr/bin/env python3
"""
TradeZero API connection check -- PAPER ONLY.

    .\\.venv\\Scripts\\python.exe -m brokers.tradezero.client

CREDENTIALS - resolved by secrets_util.py, shared with the Databento tooling
----------------------------------------------------------------------------
1. 1Password references (best). The secret is never written to disk:
       setx TZ_API_KEY_ID     "op://Trading/TradeZero Paper/key id"
       setx TZ_API_SECRET_KEY "op://Trading/TradeZero Paper/secret"
   Run `python op_list.py --vault Trading` to get the exact reference rather
   than guessing the item and field names.

   With OP_SERVICE_ACCOUNT_TOKEN set these resolve with no unlock prompt.
   Note a service account cannot read the Private vault at all -- if these
   references still point at op://Private/... they will fail.

2. Environment variables holding the values directly:
       setx TZ_API_KEY_ID     "<paper public key>"
       setx TZ_API_SECRET_KEY "<paper secret>"

3. A local file beside this script, tz_credentials.json:
       {"key_id": "...", "secret": "..."}
   Either field may instead hold an op:// reference. Keep this file out of any
   repository and off shared drives.

Never paste these values into a chat, and never commit them.

WHY THE PAPER GUARD IS DIFFERENT HERE
-------------------------------------
IBKR could be made safe by port: 4002 simply cannot reach the live account.
TradeZero serves live and paper from ONE base URL and the KEY PAIR alone selects
the environment. A live key pair in these variables would place LIVE orders.

So this script refuses to do anything beyond reading until it has confirmed
`accountType == "Paper"` on every account the keys can see, which is what
TradeZero's own documentation says to drive paper-vs-live behaviour from.

By default this only READS. --probe places one far-from-market limit order to
test whether a symbol can be opened, then cancels it; it is opt-in for that
reason and refuses outside a paper account.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from common import secrets_util as S

BASE = "https://webapi.tradezero.com"
KEY_ID_VAR = "TZ_API_KEY_ID"
SECRET_VAR = "TZ_API_SECRET_KEY"
TIMEOUT = 20


CRED_FILE = Path(__file__).with_name("tz_credentials.json")


def creds() -> tuple[str, str]:
    """Resolve once, through the shared resolver.

    tz_credentials.json is still honoured for backward compatibility: its
    values are seeded into the environment first, so the precedence order
    (environment beats file) is unchanged.

    Resolution happens HERE and only here. See secrets_util for why nothing
    downstream is allowed to re-resolve: a lazy fetch can block a live session
    on a 1Password unlock prompt with a position open.
    """
    if CRED_FILE.exists():
        try:
            blob = json.loads(CRED_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"could not read {CRED_FILE.name}: {e}")
        for var, key in ((KEY_ID_VAR, "key_id"), (SECRET_VAR, "secret")):
            if not os.environ.get(var, "").strip() and blob.get(key):
                os.environ[var] = str(blob[key]).strip()

    S.preload({KEY_ID_VAR: "TradeZero paper key id",
               SECRET_VAR: "TradeZero paper secret"})
    print(S.report())
    return S.get(KEY_ID_VAR), S.get(SECRET_VAR)


def _decode(raw: bytes, headers) -> str:
    """Decompress if the server encoded the body.

    urllib does no content decoding, so a gzipped error page comes back as
    binary and prints as mojibake -- hiding the actual message.
    """
    enc = (headers.get("Content-Encoding") or "").lower().strip()
    try:
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc in ("deflate", "zlib"):
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)   # raw deflate
        elif enc == "br":
            try:
                import brotli
                raw = brotli.decompress(raw)
            except ImportError:
                return ("<brotli-compressed response; run "
                        "`pip install brotli` to read it>")
    except Exception as e:  # noqa: BLE001
        return f"<could not decode {enc!r} body: {e}>"
    return raw.decode("utf-8", "replace")


def call(method: str, path: str, kid: str, sec: str, body: dict | None = None):
    """Returns (status, parsed_json_or_text). Never raises on HTTP error."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("TZ-API-KEY-ID", kid)
    req.add_header("TZ-API-SECRET-KEY", sec)
    req.add_header("Accept", "application/json")
    # Ask for an uncompressed body; _decode handles it anyway if compressed.
    req.add_header("Accept-Encoding", "identity")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = _decode(r.read(), r.headers)
            try:
                return r.status, json.loads(text)
            except json.JSONDecodeError:
                return r.status, text
    except urllib.error.HTTPError as e:
        text = _decode(e.read(), e.headers)
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text
    except urllib.error.URLError as e:
        return 0, f"connection failed: {e.reason}"


def accounts_of(payload):
    """The list endpoint may return a bare list or wrap it -- handle both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("accounts", "data", "items", "results"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="TradeZero paper connection check")
    ap.add_argument("--probe", metavar="SYMBOL",
                    help="test whether a symbol can be OPENED by placing one "
                         "far-from-market limit order and cancelling it. "
                         "Paper accounts only.")
    ap.add_argument("--probe-price", type=float, default=0.01,
                    help="limit price for the probe order (default 0.01, far "
                         "below any market so it cannot fill)")
    args = ap.parse_args()

    kid, sec = creds()
    print(f"key id ...{kid[-4:]}  ->  {BASE}\n")

    status, payload = call("GET", "/v1/api/accounts", kid, sec)
    if status == 0:
        print(f"FAILED: {payload}")
        return 1
    if status in (401, 403):
        print(f"AUTH REJECTED ({status}). Check the key pair and that API "
              f"trading is enabled on this account.\n{payload}")
        return 1
    if status != 200:
        print(f"HTTP {status}\n{json.dumps(payload, indent=2)[:2000]}")
        return 1

    rows = accounts_of(payload)

    # An empty list from a key that has worked before is usually transient --
    # paper environments rebuild accounts on a nightly cycle, and the list can
    # be briefly empty. Retry a couple of times before blaming the setup.
    for attempt in (1, 2):
        if rows:
            break
        print(f"accounts list came back empty -- retrying ({attempt}/2)...")
        time.sleep(5)
        status, payload = call("GET", "/v1/api/accounts", kid, sec)
        rows = accounts_of(payload) if status == 200 else []

    if not rows:
        print("\nConnected and authenticated, but no accounts were returned.")
        print(json.dumps(payload, indent=2)[:600])
        print("\nA bad key gives 401, so the credentials themselves are fine.")
        print("Possible reasons, and I genuinely cannot tell which from here:")
        print("  * TRANSIENT. Paper environments commonly rebuild accounts")
        print("    overnight; the list can be empty during that window. If this")
        print("    key pair has worked before, this is the likeliest cause --")
        print("    wait and run it again before changing anything.")
        print("  * The keys belong to an environment with no API-enabled")
        print("    account attached (e.g. live keys, live API not enabled).")
        print("  * The keys were regenerated, invalidating the previous pair.")
        print(f"\nkey id ...{kid[-4:]} -- compare with the PAPER portal's API Key")
        print("Management page if repeated retries keep failing.")
        return 1

    print("=== accounts ===")
    types = []
    for a in rows:
        acct = a.get("accountId") or a.get("account") or a.get("id") or "?"
        atype = a.get("accountType", "?")
        types.append(atype)
        print(f"  {acct:16s} accountType={atype}")

    paper = bool(types) and all(t == "Paper" for t in types)
    print()
    if paper:
        print("PAPER ACCOUNT CONFIRMED (accountType == 'Paper' on every row)")
    else:
        print("*** WARNING: at least one account is NOT accountType 'Paper'.")
        print("*** These keys can reach a LIVE account. Stop and regenerate")
        print("*** paper keys from the PAPER portal before going further.")

    if not args.probe:
        print("\nRead-only check complete. No orders placed.")
        print("Add --probe SYMBOL to test whether a name can be opened.")
        return 0 if paper else 2

    if not paper:
        print("\nREFUSING to probe: not a confirmed paper account.")
        return 2

    sym = args.probe.upper()
    acct = rows[0].get("accountId") or rows[0].get("account") or rows[0].get("id")
    print(f"\n=== probing {sym} on {acct} ===")
    print(f"placing BUY 1 @ {args.probe_price:.2f} (far below market, will not "
          f"fill), then cancelling")

    order = {
        "accountId": acct,
        "symbol": sym,
        "securityType": "Stock",       # 'Stock' | 'Option' | 'Mleg'
        "side": "Buy",
        "orderQuantity": 1,
        "orderType": "Limit",
        "limitPrice": args.probe_price,
        "timeInForce": "Day_Plus",     # extended-hours eligible
        # This is the whole point: IBKR's block is specifically on OPENING a
        # position in these names, so the probe must be an opening order.
        "openClose": "Open",
    }
    print(f"request body: {json.dumps(order)}")
    status, resp = call("POST", f"/v1/api/accounts/{acct}/order", kid, sec, order)
    text = json.dumps(resp, indent=2) if not isinstance(resp, str) else resp
    print(f"HTTP {status}:\n{text[:1500]}")

    low = text.lower()
    if status in (200, 201) and "reject" not in low:
        cid = (resp.get("clientOrderId") if isinstance(resp, dict) else None)

        # An initial 200 is not the whole story. At IBKR the compliance
        # rejection arrived ~0.5s AFTER the order was first accepted
        # (PendingSubmit -> Inactive). Watch the status for a few seconds
        # before cancelling, or a late refusal is invisible.
        if cid:
            print("\nwatching order status for late rejections...")
            last = None
            for _ in range(12):                       # ~6 seconds
                time.sleep(0.5)
                s3, r3 = call("GET", f"/v1/api/accounts/{acct}/order/{cid}",
                              kid, sec)
                st_now = r3.get("orderStatus") if isinstance(r3, dict) else None
                txt = r3.get("text") if isinstance(r3, dict) else None
                if st_now and st_now != last:
                    print(f"  {st_now}" + (f" -- {txt}" if txt else ""))
                    last = st_now
                if st_now in ("Rejected", "Canceled", "Cancelled", "Expired"):
                    break
            if last in ("Rejected", "Expired"):
                print(f"\n{sym} was REJECTED after acceptance -- same pattern as "
                      f"IBKR. This is a real block, not a pass.")
                return 0

        print(f"\n{sym} APPEARS TRADABLE -- TradeZero accepted an OPENING order "
              f"and it stayed live.")
        print("NOTE: route was PAPER. Paper may not enforce the same compliance "
              "rules as live -- confirm with TradeZero support before relying on it.")
        if cid:
            # note: 'orders' plural on cancel, 'order' singular on place
            s2, r2 = call("DELETE", f"/v1/api/accounts/{acct}/orders/{cid}",
                          kid, sec)
            print(f"cancel {cid} -> HTTP {s2}")
            if s2 not in (200, 202, 204):
                print(f"!! CANCEL MAY HAVE FAILED: {r2}")
                print("!! Check the paper account and cancel by hand if needed.")
        else:
            print("!! No clientOrderId returned -- CANCEL THIS ORDER MANUALLY.")
    else:
        print(f"\n{sym} was NOT accepted. Read the response above: a permissions "
              f"or compliance message is the finding we want (compare with "
              f"IBKR's error 201); a 4xx about fields or routes is my bug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
