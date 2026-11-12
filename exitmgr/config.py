#!/usr/bin/env python3
"""Live exit manager configuration, from environment variables (W15-0053 sub 4a).

SAFETY (REGISTERED_exit_cmp.md sec 14 rail 10, plan sec 4):
  * XM_MODE defaults to `dry`: the manager watches fills and LOGS every order it would send, and sends none.
  * `paper` needs XM_MODE=paper AND XM_ACCOUNT=DU... that must equal the account the Gateway reports.
  * There is no live mode. XM_MODE=live (or anything else) is refused; live ports are refused in every mode.
  * Client id is 31 (deploy/nas_trader/client_ids.py, reserved for the exit manager). Anything else is refused.
  * The output dir is the manager's own; a path inside any `var` folder (the NAS trader's var/ share) is refused.

Variables (all optional except XM_ACCOUNT in paper):
  XM_MODE dry|paper            XM_ACCOUNT DU...            XM_HOST 127.0.0.1           XM_PORT 4002
  XM_CAPS "MCL:8,MNQ:2"        (a root not listed, or listed with 0, is OFF: a fill in it is alert-only)
  XM_FLAT_MODE FLAT|HOLD       XM_FLAT_TIME 16:55 (NY)     XM_EMERGENCY_MODE A|B|C     XM_EMERGENCY_FALLBACK B|C
  XM_IGNORE_CLIENT_IDS 17      XM_OUT_DIR exitmgr_out      XM_RECONCILE_S 15 (<= 30)   XM_LOOP_S 0.2
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from exitmgr import symbols

PAPER_PORTS = frozenset({4002, 4004, 7497})          # Gateway paper, the NAS Gateway's paper relay, TWS paper
LIVE_PORTS = frozenset({4001, 4003, 7496, 7498})
CLIENT_ID = 31                                       # registry: deploy/nas_trader/client_ids.py
NAS_TRADER_CLIENT_ID = 17
MODES = ("dry", "paper")
FLAT_MODES = ("FLAT", "HOLD")
DEFAULT_CAPS = "MCL:8,MNQ:2"                         # W15-0059; CL, ES, MES, NQ off
RUNAWAY_PER_MIN = 20                                 # rail 9d
RUNAWAY_PER_DAY = 200


class Refused(Exception):
    """A configuration or environment the manager will not run with."""


@dataclass(frozen=True)
class Config:
    mode: str = "dry"
    account: str = ""
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = CLIENT_ID
    caps: dict = field(default_factory=dict)
    flat_mode: str = "FLAT"
    flat_hhmm: tuple = (16, 55)
    emergency_mode: str = symbols.DEFAULT_EMERGENCY_MODE
    emergency_fallback: str = "B"
    ignore_client_ids: tuple = (NAS_TRADER_CLIENT_ID,)
    out_dir: Path = Path("exitmgr_out")
    reconcile_s: float = 15.0
    loop_s: float = 0.2
    mismatch_grace_s: float = 5.0                    # a broker/tracked mismatch must persist this long before ALERT-ONLY
    stop_alert_s: float = 3.0                        # rail 3: fill -> stop over 3 s alerts
    stale_s: float = 30.0                            # rail 12
    runaway_per_min: int = RUNAWAY_PER_MIN
    runaway_per_day: int = RUNAWAY_PER_DAY
    stop_tif: str = "GTC"                            # a server-side stop must outlive the session and a Gateway restart
    outside_rth: bool = True                         # stops trigger in the overnight Globex session too (NOT verified, sub 5)

    def cap(self, root: str) -> int:
        """Size cap for a root; 0 means the symbol is OFF (never managed)."""
        return int(self.caps.get(root, 0))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["out_dir"] = str(self.out_dir)
        return d

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True, default=str).encode()).hexdigest()[:16]


def check_port(port: int) -> None:
    if port in LIVE_PORTS:
        raise Refused(f"port {port} is a LIVE port. Refused. Paper only: {sorted(PAPER_PORTS)}.")
    if port not in PAPER_PORTS:
        raise Refused(f"port {port} is not a paper port {sorted(PAPER_PORTS)}.")


def check_out_dir(path: Path, env: dict) -> Path:
    """The manager writes only to its own folder, never into var/ (the NAS trader's state; its stale-lock logic assumes
    nothing else writes there)."""
    p = Path(path)
    parts = [x.lower() for x in p.resolve().parts] + [x.lower() for x in p.parts]
    if "var" in parts:
        raise Refused(f"XM_OUT_DIR {p} is inside a var folder. The exit manager never writes to var/; use its own folder.")
    tv = env.get("TRADER_VAR_DIR")
    if tv:
        try:
            p.resolve().relative_to(Path(tv).resolve())
            raise Refused(f"XM_OUT_DIR {p} is inside TRADER_VAR_DIR {tv}. Refused.")
        except ValueError:
            pass
    return p


def parse_caps(s: str) -> dict:
    caps: dict[str, int] = {}
    for item in (s or "").replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise Refused(f"XM_CAPS item {item!r} is not ROOT:N")
        root, n = (x.strip() for x in item.split(":", 1))
        root = root.upper()
        if root not in symbols.SYMBOLS:
            raise Refused(f"XM_CAPS root {root!r} is not in the symbol table (exitmgr/symbols.py)")
        try:
            v = int(n)
        except ValueError:
            raise Refused(f"XM_CAPS {root}: {n!r} is not a whole number") from None
        if v < 0:
            raise Refused(f"XM_CAPS {root}: negative cap")
        caps[root] = v
    return caps


def _float(env, key, default, lo=None, hi=None) -> float:
    raw = env.get(key)
    if raw in (None, ""):
        return default
    try:
        v = float(raw)
    except ValueError:
        raise Refused(f"{key}={raw!r} is not a number") from None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise Refused(f"{key}={v} is outside [{lo}, {hi}]")
    return v


def load(env: dict | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    mode = (env.get("XM_MODE") or "dry").strip().lower()
    if mode not in MODES:
        raise Refused(f"XM_MODE={mode!r}: only 'dry' (default) or 'paper'. Live trading is not enabled by anything in sub 4.")
    account = (env.get("XM_ACCOUNT") or "").strip().upper()
    if mode == "paper":
        if not account:
            raise Refused("XM_MODE=paper needs XM_ACCOUNT=DU... (the paper account id)")
        if not account.startswith("DU"):
            raise Refused(f"XM_ACCOUNT={account!r} is not a paper account (paper ids start with DU)")
    elif account and not account.startswith("D"):
        raise Refused(f"XM_ACCOUNT={account!r} is not a paper account")
    port = int(env.get("XM_PORT") or 4002)
    check_port(port)
    cid = int(env.get("XM_CLIENT_ID") or CLIENT_ID)
    if cid != CLIENT_ID:
        raise Refused(f"XM_CLIENT_ID={cid}: the exit manager's registered client id is {CLIENT_ID} (client_ids.py)")
    flat_mode = (env.get("XM_FLAT_MODE") or "FLAT").strip().upper()
    if flat_mode not in FLAT_MODES:
        raise Refused(f"XM_FLAT_MODE={flat_mode!r} is not one of {FLAT_MODES}")
    hhmm = (env.get("XM_FLAT_TIME") or "16:55").strip()
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except ValueError:
        raise Refused(f"XM_FLAT_TIME={hhmm!r} is not HH:MM") from None
    if h != 16 or not 0 <= m <= 59:
        raise Refused(f"XM_FLAT_TIME={hhmm}: must be 16:00-16:59 NY (before the 17:00 close)")
    em = (env.get("XM_EMERGENCY_MODE") or symbols.DEFAULT_EMERGENCY_MODE).strip().upper()
    if em not in symbols.EMERGENCY_MODES:
        raise Refused(f"XM_EMERGENCY_MODE={em!r} is not one of {symbols.EMERGENCY_MODES}")
    fb = (env.get("XM_EMERGENCY_FALLBACK") or "B").strip().upper()
    if fb not in ("B", "C"):
        raise Refused(f"XM_EMERGENCY_FALLBACK={fb!r}: B or C (a fixed distance, used while mode A has no ATR)")
    ign_raw = env.get("XM_IGNORE_CLIENT_IDS")
    ign = tuple(int(x) for x in (ign_raw if ign_raw is not None else str(NAS_TRADER_CLIENT_ID)).replace(",", " ").split())
    if CLIENT_ID in ign:
        raise Refused("XM_IGNORE_CLIENT_IDS may not contain the manager's own id 31")
    out_dir = check_out_dir(Path(env.get("XM_OUT_DIR") or "exitmgr_out"), env)
    return Config(
        mode=mode, account=account, host=(env.get("XM_HOST") or "127.0.0.1").strip(), port=port, client_id=cid,
        caps=parse_caps(env.get("XM_CAPS", DEFAULT_CAPS)), flat_mode=flat_mode, flat_hhmm=(h, m),
        emergency_mode=em, emergency_fallback=fb, ignore_client_ids=ign, out_dir=out_dir,
        reconcile_s=_float(env, "XM_RECONCILE_S", 15.0, 1.0, 30.0), loop_s=_float(env, "XM_LOOP_S", 0.2, 0.01, 1.0),
    )


def check_accounts(cfg: Config, accounts) -> str:
    """Rail 10, the paper lock: every account the Gateway reports must be a paper account (id starts with D), and in paper
    mode the configured DU... account must be one of them. Returns the account the manager works on."""
    accs = [str(a).strip().upper() for a in (accounts or []) if str(a).strip()]
    if not accs:
        raise Refused("the Gateway reported no account")
    if any(not a.startswith("D") for a in accs):
        raise Refused(f"accounts {accs} are not all paper accounts (ids start with D). Stopping.")
    if cfg.account:
        if cfg.account not in accs:
            raise Refused(f"XM_ACCOUNT={cfg.account} is not the connected account {accs}. Stopping.")
        return cfg.account
    if cfg.mode == "paper":
        raise Refused("paper mode without XM_ACCOUNT")             # load() already refuses this; belt and braces
    if len(accs) != 1:
        raise Refused(f"several accounts {accs}: set XM_ACCOUNT")
    return accs[0]
