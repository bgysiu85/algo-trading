#!/usr/bin/env python3
"""Container launcher for the NAS trader (W10-0013 sub 5). Replaces run_paper.ps1 / run_dry.ps1 on Linux.

    python run_trader.py                 start a session (what the container's command runs)
    python run_trader.py --selfcheck     prove the image works WITHOUT a Gateway: imports, time zone, var/, arguments
    python run_trader.py --print-command show the exact main.py arguments and stop

Everything is set through environment variables (compose.yaml fills them from .env). All are optional:

    TRADER_MODE            dry | paper          default dry. dry logs signals and places NO orders; paper places real
                                                orders against the IBKR PAPER account. Going to paper is a deliberate
                                                edit of .env (sub 9, cutover); it is never the default.
    TRADER_STRATEGY        e.g. mcl or mcl,mc5  default mcl (run_paper.ps1's default). Comma-separated, no spaces.
    TRADER_MAX_POSITIONS   integer              default unset = the trader's own default
    TRADER_CAP_SCOPE       account | strategy   default unset = the trader's own default (account)
    TRADER_TELEGRAM_BATCH_MIN  number           default 0 = send immediately
    TRADER_NO_ARCHIVE      1 = keep the watchlist at session end
    TRADER_FEED            on | off             default on (the TradingView watchlist feed runs inside the process)
    TRADER_PORT            4002                 only the Gateway's PAPER port (4002) or TWS paper (7497) is accepted

What this launcher deliberately does NOT do:
  * It never passes --sleep-on-exit (that suspends a Windows PC; there is no PC to sleep here).
  * It cannot reach a live port. 4001/7496 are refused here and, independently, by the trader itself; every account id
    must also start with 'DU' (checked in trader.main_async). Those two guards are the real protection.
  * paper mode passes --yes to main.py because a container has no terminal to type PAPER on. Choosing
    TRADER_MODE=paper in .env is the explicit decision that prompt exists to force. The banner below is still printed.

Exit codes: 0 session ended normally, 1 refused / environment problem, 2 selfcheck failed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAPER_PORTS = {4002, 7497}
LIVE_PORTS = {4001, 4003, 7496, 7498}
MODES = {"dry", "paper"}
WATCHLIST = "var/watchlist.txt"
SUBDIRS = ("state", "fills", "archive")

# The packages and modules a session really needs, checked by --selfcheck. A module missing from the shipped tree shows
# up here, in front of the person, instead of at 09:25 with a position pending.
IMPORT_CHECK = ("main", "brokers.ibkr.trader", "brokers.ibkr.scanner", "common.tv_feed", "common.ui_bridge",
                "common.notify", "common.session_lock", "common.provenance", "strategy.mcl.mcl", "strategy.mc5.mc5")


class Refused(Exception):
    """A setting that must not be acted on. The message is shown as-is."""


def _env(env, name: str, default: str = "") -> str:
    return (env.get(name) or "").strip() or default


def build_args(env=None) -> list[str]:
    """The argument list for main.run(), from the environment. Raises Refused for anything unsafe or malformed."""
    env = os.environ if env is None else env
    mode = _env(env, "TRADER_MODE", "dry").lower()
    if mode not in MODES:
        raise Refused(f"TRADER_MODE={mode!r} is not one of {sorted(MODES)}. (There is deliberately no live mode here.)")

    strategy = _env(env, "TRADER_STRATEGY", "mcl").lower()
    if " " in strategy or not all(strategy.split(",")):
        raise Refused(f"TRADER_STRATEGY={strategy!r}: use a comma-separated list with no spaces, e.g. mcl,mc5.")

    port_text = _env(env, "TRADER_PORT", "4002")
    try:
        port = int(port_text)
    except ValueError:
        raise Refused(f"TRADER_PORT={port_text!r} is not a number.") from None
    if port in LIVE_PORTS:
        raise Refused(f"TRADER_PORT={port} is a LIVE port. Refused. Paper only: {sorted(PAPER_PORTS)}.")
    if port not in PAPER_PORTS:
        raise Refused(f"TRADER_PORT={port} is not a paper port. Allowed: {sorted(PAPER_PORTS)}.")

    args = ["--mode", mode, "--strategy", strategy, "--watchlist", WATCHLIST, "--port", str(port)]

    mp = _env(env, "TRADER_MAX_POSITIONS")
    if mp:
        if not mp.isdigit() or int(mp) < 1:
            raise Refused(f"TRADER_MAX_POSITIONS={mp!r} must be a whole number of 1 or more (or empty).")
        args += ["--max-positions", mp]

    scope = _env(env, "TRADER_CAP_SCOPE").lower()
    if scope:
        if scope not in {"account", "strategy"}:
            raise Refused(f"TRADER_CAP_SCOPE={scope!r} must be account or strategy (or empty).")
        args += ["--cap-scope", scope]

    batch = _env(env, "TRADER_TELEGRAM_BATCH_MIN", "0")
    try:
        batch_val = float(batch)
    except ValueError:
        raise Refused(f"TRADER_TELEGRAM_BATCH_MIN={batch!r} is not a number.") from None
    if batch_val > 0:
        args += ["--telegram-batch-min", batch]

    if _env(env, "TRADER_NO_ARCHIVE") in {"1", "true", "yes", "on"}:
        args += ["--no-archive"]

    feed = _env(env, "TRADER_FEED", "on").lower()
    if feed not in {"on", "off"}:
        raise Refused(f"TRADER_FEED={feed!r} must be on or off.")
    if feed == "off":
        args += ["--no-feed"]

    if mode == "paper":
        args += ["--yes"]          # no terminal in a container; see the module docstring
    return args


def trader_args(args: list[str]) -> list[str]:
    """What main.run() hands to the trader: its own flags (--mode, --strategy, --no-feed, --yes) are consumed, the
    strategy list is re-issued as separate words (the trader's --strategy takes several), --dry-run is added for dry."""
    own = {"--mode": 1, "--strategy": 1, "--no-feed": 0, "--yes": 0}
    mode = args[args.index("--mode") + 1]
    wanted = args[args.index("--strategy") + 1].split(",")
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in own:
            i += 1 + own[a]
            continue
        out.append(a)
        i += 1
    out += ["--strategy", *wanted]
    if mode == "dry":
        out.append("--dry-run")
    return out


def prepare_var(root: Path = ROOT) -> list[str]:
    """Create var/ and its subfolders, make sure we can write there, make sure a watchlist exists.

    Returns warnings. Raises Refused when var/ cannot be written - the usual cause on the NAS is folder ownership
    (the container runs as user 1000, so the host folder must be owned by 1000:1000).
    """
    var = root / "var"
    warns: list[str] = []
    try:
        for sub in SUBDIRS:
            (var / sub).mkdir(parents=True, exist_ok=True)
        probe = var / "state" / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise Refused(
            f"cannot write to {var} ({e}).\n"
            "  On the NAS the folder must belong to the user the container runs as (1000):\n"
            "    sudo chown -R 1000:1000 /volume1/trader/var && sudo chmod -R u+rwX /volume1/trader/var") from None
    wl = root / WATCHLIST
    if not wl.exists():
        wl.write_text("# one ticker per line; picked up within 5 seconds. Cleared at the end of every session.\n",
                      encoding="utf-8")
    tickers = [ln.split("#")[0].strip() for ln in wl.read_text(encoding="utf-8", errors="replace").splitlines()]
    if not [t for t in tickers if t]:
        warns.append("watchlist is empty - starting with nothing to watch (normal: it is cleared every session).")
    return warns


LOCKS = ("var/state/session.lock", "var/state/watchlist_writer.lock")


def clear_container_locks(root: Path = ROOT, env=None) -> list[str]:
    """Remove locks left by a previous run of THIS container, so an unclean stop cannot block tomorrow's session.

    Why this exists: session_lock decides "is that session alive?" by asking whether the recorded PID exists. In a
    container the PIDs are the same every run (tini is 1, the trader is a small fixed number), so after a kill, an
    out-of-memory stop or a power cut the next run finds a lock whose PID is ITSELF, concludes a session is running, and
    refuses to start for up to 24 hours. A clean stop (including `docker stop`, which the trader handles) removes its own
    lock, so this only ever acts after a crash.

    Safe because the container name is fixed (Docker will not run two) and var/ is private to it. It leaves alone a lock
    whose recorded tree is some OTHER tree (a lock written by the ProArt would say D:\\Trading...). The watchlist-writer lock
    carries no tree; it is removed on the same reasoning, which stops being safe the day var/ is shared with another
    machine - W10-0013 sub 6 replaces the lock before that happens. TRADER_CLEAR_STALE_LOCKS=0 turns this off.
    """
    import json
    env = os.environ if env is None else env
    if _env(env, "TRADER_CLEAR_STALE_LOCKS", "1") == "0":
        return []
    notes: list[str] = []
    for rel in LOCKS:
        path = root / rel
        if not path.exists():
            continue
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        tree = info.get("tree") if isinstance(info, dict) else None
        what = (f"{rel} (pid {info.get('pid')}, started {info.get('started_at')}, "
                f"{info.get('mode')}/{info.get('strategy')})") if isinstance(info, dict) and info else rel
        if tree and tree != str(root):
            notes.append(f"LEFT ALONE {what}: it was written by another tree ({tree}).")
            continue
        try:
            path.unlink()
            notes.append(f"removed {what} left by an earlier run of this container.")
        except OSError as e:
            notes.append(f"could not remove {what}: {e}")
    return notes


def banner(args: list[str], warns: list[str]) -> str:
    mode = args[args.index("--mode") + 1]
    lines = [""]
    if mode == "paper":
        lines += ["  ORDERS WILL BE PLACED  (IBKR PAPER account)", ""]
    else:
        lines += ["  DRY RUN - signals are logged, NO orders are placed", ""]
    lines += [f"  Strategy  : {args[args.index('--strategy') + 1]}",
              f"  Port      : {args[args.index('--port') + 1]}  (paper only - live ports are refused)",
              f"  Watchlist : {WATCHLIST}",
              f"  Command   : main.py {' '.join(args)}", ""]
    if mode == "paper":
        lines += ["  The trailing stop lives in this process, not at IBKR.",
                  "  If the container stops with a position open, that position is unprotected.", ""]
    lines += [f"  NOTE: {w}" for w in warns]
    return "\n".join(lines)


def selfcheck(root: Path = ROOT, env=None, out=print) -> int:
    """Everything that can be proved without a Gateway. Prints one line per check; exit 0 only if all pass."""
    env = os.environ if env is None else env
    results: list[tuple[bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((ok, name))
        out(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))

    out(f"python {sys.version.split()[0]} on {sys.platform}; tree {root}")
    try:
        flags = ""
        for ln in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("flags"):
                flags = ln
                break
        out(f"  info  cpu avx={'avx' in flags.split()} avx2={'avx2' in flags.split()} sse4_2={'sse4_2' in flags.split()}")
    except OSError:
        out("  info  cpu flags not readable here")

    for pkg in ("numpy", "pandas", "ib_async", "tzdata"):
        try:
            mod = __import__(pkg)
            check(f"import {pkg}", True, getattr(mod, "__version__", "") or "")
        except Exception as e:                                     # noqa: BLE001 - any failure is the answer
            check(f"import {pkg}", False, f"{type(e).__name__}: {e}")

    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        now = datetime.now(ZoneInfo("America/New_York"))
        check("time zone America/New_York", True, now.strftime("%H:%M %Z now in New York"))
    except Exception as e:                                         # noqa: BLE001
        check("time zone America/New_York", False, f"{type(e).__name__}: {e} (install tzdata)")

    sys.path.insert(0, str(root))
    for name in IMPORT_CHECK:
        try:
            __import__(name)
            check(f"import {name}", True)
        except (Exception, SystemExit) as e:       # trader.py calls sys.exit("ib_async not installed...") on import
            check(f"import {name}", False, f"{type(e).__name__}: {e}")

    try:
        from common import provenance
        p = provenance.read(root)
        check("release identity", bool(p.commit or p.described), p.as_line())
    except Exception as e:                                         # noqa: BLE001
        check("release identity", False, f"{type(e).__name__}: {e}")

    try:
        warns = prepare_var(root)
        check("var/ writable, watchlist present", True, "; ".join(warns))
    except Refused as e:
        check("var/ writable, watchlist present", False, str(e).splitlines()[0])

    try:
        args = build_args(env)
        check("arguments from the environment", True, " ".join(args))
        from brokers.ibkr import trader
        fwd = trader_args(args)
        trader.build_parser().parse_args(fwd)
        check("trader accepts these arguments", True)
    except Refused as e:
        check("arguments from the environment", False, str(e))
    except SystemExit as e:                                        # argparse rejects with SystemExit
        check("trader accepts these arguments", False, f"argparse exit {e.code}")
    except Exception as e:                                         # noqa: BLE001
        check("trader accepts these arguments", False, f"{type(e).__name__}: {e}")

    bad = [n for ok, n in results if not ok]
    out("")
    out("SELFCHECK PASS" if not bad else f"SELFCHECK FAIL ({len(bad)}): " + "; ".join(bad))
    return 0 if not bad else 2


def main(argv: list[str] | None = None, env=None, run_main=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    os.chdir(ROOT)                                  # var/ is resolved against the working directory (audit item 5)
    if "--selfcheck" in argv:
        return selfcheck(ROOT, env)
    unknown = [a for a in argv if a not in {"--print-command"}]
    if unknown:
        print(f"run_trader: unknown argument(s) {unknown}. Settings come from the environment; see --help text in the "
              "file's docstring.", file=sys.stderr)
        return 1
    try:
        args = build_args(env)
        warns = prepare_var(ROOT)
    except Refused as e:
        print(f"run_trader: REFUSED - {e}", file=sys.stderr)
        return 1
    if "--print-command" not in argv:
        warns += clear_container_locks(ROOT, env)
    print(banner(args, warns))
    if "--print-command" in argv:
        return 0
    if run_main is None:
        sys.path.insert(0, str(ROOT))
        import main as _main
        run_main = _main.run
    return run_main(args) or 0


if __name__ == "__main__":
    sys.exit(main())
