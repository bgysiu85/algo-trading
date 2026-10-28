"""The desk's order of play, in one place.

The /desk skill, the status command and the tests all read this, so a file name
cannot drift between the prompt that writes it and the script that looks for it.
"""
from __future__ import annotations

MACRO_AGENT = "desk-macro-analyst"
MACRO_FILE = "_macro.md"            # once per day, in the day folder, not per ticker

# Step 1: these four run in parallel (one message, four Agent calls).
ANALYSTS = (
    ("desk-market-analyst", "market_report.md"),
    ("desk-fundamentals-analyst", "fundamentals_report.md"),
    ("desk-news-analyst", "news_report.md"),
    ("desk-sentiment-analyst", "sentiment_report.md"),
)

# Steps 2-7: strictly in this order, each reads what came before.
SEQUENCE = (
    ("desk-bull", "bull.md"),
    ("desk-bear", "bear.md"),
    ("desk-research-manager", "research_plan.md"),
    ("desk-trader", "trader_plan.md"),
    ("desk-risk-aggressive", "risk_aggressive.md"),
    ("desk-risk-conservative", "risk_conservative.md"),
    ("desk-risk-neutral", "risk_neutral.md"),
    ("desk-portfolio-manager", "final_report.md"),
)

FINAL_REPORT = "final_report.md"
DECISION_JSON = "decision.json"
DECISIONS_CSV = "decisions.csv"     # in runs_dir, all days, one row per ticker-day

# Written by `desk.prepare` before any agent runs.
PREPARED_FILES = ("bars.csv", "snapshot.json", "market_data.md", "fundamentals_data.md", "status.json")

AGENT_NAMES = (MACRO_AGENT,) + tuple(n for n, _ in ANALYSTS) + tuple(n for n, _ in SEQUENCE)
