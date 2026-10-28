"""Config + run-folder layout. One place, so the agents, the scripts and the
tests agree on where a run's files live."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).with_name("config.json")

# A ticker ends up in a folder name, so it is validated, not trusted.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_config(path: Path | None = None) -> dict:
    return json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))


def norm_ticker(raw: str) -> str:
    t = str(raw).strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError(f"not a usable ticker: {raw!r}")
    return t


def norm_date(raw: str) -> str:
    d = str(raw).strip()
    if not _DATE_RE.match(d):
        raise ValueError(f"date must be YYYY-MM-DD: {raw!r}")
    datetime.strptime(d, "%Y-%m-%d")        # rejects 2026-13-45
    return d


def default_run_date(now: datetime | None = None) -> str:
    """The US market date. Ben works from Sydney, where the calendar date is
    already tomorrow while the US session is still open, so the local date
    would mislabel the run."""
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:                       # no tz database (Windows without tzdata)
        return now.strftime("%Y-%m-%d")


def runs_dir(cfg: dict, base: Path | None = None) -> Path:
    p = Path(cfg.get("runs_dir", "var/desk_runs"))
    return p if p.is_absolute() else (base or REPO) / p


def day_dir(cfg: dict, date: str, base: Path | None = None) -> Path:
    return runs_dir(cfg, base) / norm_date(date)


def run_dir(cfg: dict, date: str, ticker: str, base: Path | None = None) -> Path:
    return day_dir(cfg, date, base) / norm_ticker(ticker)
