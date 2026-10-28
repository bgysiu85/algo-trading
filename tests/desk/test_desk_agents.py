"""Lint for the desk's prompt files.

The agents are prompts, so their behaviour cannot be unit-tested here. What CAN
go wrong without any model involved, and does, is drift: a prompt that writes
`bull_case.md` while the next agent reads `bull.md`, an agent granted Bash it
should not have, a skill that calls an agent in the wrong order, a JSON example
the validator would reject. Those are checked here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from desk import decision, pipeline

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".claude" / "agents"
SKILL = ROOT / ".claude" / "skills" / "desk" / "SKILL.md"

ALLOWED_TOOLS = {"Read", "Write", "WebSearch", "WebFetch"}
WEB_AGENTS = {"desk-macro-analyst", "desk-fundamentals-analyst", "desk-news-analyst", "desk-sentiment-analyst"}
MODELS = {"sonnet", "haiku", "opus"}
PREPARED = {"market_data.md", "fundamentals_data.md", "snapshot.json", "bars.csv", "status.json"}


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, f"{path.name}: no frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, m.group(2)


def outputs():
    out = {pipeline.MACRO_AGENT: pipeline.MACRO_FILE}
    out.update(dict(pipeline.ANALYSTS))
    out.update(dict(pipeline.SEQUENCE))
    return out


def test_agent_files_match_the_pipeline_exactly():
    on_disk = sorted(p.stem for p in AGENTS.glob("*.md"))
    assert on_disk == sorted(pipeline.AGENT_NAMES)


@pytest.mark.parametrize("name", pipeline.AGENT_NAMES)
def test_frontmatter_is_valid_and_least_privilege(name):
    fm, body = frontmatter(AGENTS / f"{name}.md")
    assert fm["name"] == name
    assert len(fm["description"]) > 30
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert tools <= ALLOWED_TOOLS, f"{name} has tools beyond the allowlist: {tools - ALLOWED_TOOLS}"
    assert "Write" in tools and "Read" in tools or name == pipeline.MACRO_AGENT
    if name in WEB_AGENTS:
        assert "WebSearch" in tools
    else:
        assert not tools & {"WebSearch", "WebFetch"}, f"{name} should not reach the web"
    assert fm["model"] in MODELS
    assert 3 <= int(fm["maxTurns"]) <= 20
    assert "Ground rules (every desk agent)" in body and "LONG-ONLY" in body


@pytest.mark.parametrize("name", pipeline.AGENT_NAMES)
def test_each_agent_names_its_own_output_file_and_a_done_line(name):
    _, body = frontmatter(AGENTS / f"{name}.md")
    out = outputs()[name]
    where = "DAY_DIR" if name == pipeline.MACRO_AGENT else "RUN_DIR"
    assert f"{where}/{out}" in body, f"{name} never says to write {where}/{out}"
    assert f"DONE {out}" in body, f"{name} has no 'DONE {out}' reply format"


def test_no_agent_reads_a_file_that_has_not_been_written_yet():
    order = [pipeline.MACRO_AGENT] + [n for n, _ in pipeline.ANALYSTS] + [n for n, _ in pipeline.SEQUENCE]
    out = outputs()
    analyst_files = {f for _, f in pipeline.ANALYSTS}
    known = set(out.values())
    for i, name in enumerate(order):
        _, body = frontmatter(AGENTS / f"{name}.md")
        mentioned = set(re.findall(r"\b([a-z_]+\.(?:md|json|csv))\b", body)) & (known | PREPARED)
        if name in {n for n, _ in pipeline.ANALYSTS}:
            allowed = {out[name], pipeline.MACRO_FILE} | PREPARED         # parallel: not each other
        else:
            allowed = {out[n] for n in order[:i + 1]} | PREPARED
        bad = mentioned - allowed - {"decision.json"}
        assert not bad, f"{name} refers to {sorted(bad)} which is not available at its step"
    # the debaters and the manager actually consume what upstream wrote
    _, bear = frontmatter(AGENTS / "desk-bear.md")
    assert "bull.md" in bear
    _, pm = frontmatter(AGENTS / "desk-portfolio-manager.md")
    for f in ("research_plan.md", "trader_plan.md", "risk_aggressive.md", "risk_conservative.md", "risk_neutral.md"):
        assert f in pm
    _, bull = frontmatter(AGENTS / "desk-bull.md")
    for f in analyst_files:
        assert f in bull


def test_portfolio_manager_example_json_has_the_validators_keys_and_is_valid_in_shape():
    _, body = frontmatter(AGENTS / "desk-portfolio-manager.md")
    block = re.search(r"```json\s*(.*?)```", body, re.DOTALL).group(1)
    ex = json.loads(block)
    assert set(ex) == {"ticker", "run_date", "rating", "conviction", "entry", "stop", "target",
                       "horizon_days", "size_shares", "thesis", "key_risks"}
    ex.update(rating="Buy", ticker="MPC", run_date="2026-10-28")
    errors, _, _ = decision.validate(ex, "MPC", "2026-10-28", None,
                                     {"shares_per_symbol": 1, "max_hold_days": 180})
    assert errors == []
    for r in decision.RATINGS:
        assert r in body


def test_the_skill_is_manual_only_and_calls_every_agent_in_pipeline_order():
    fm, body = frontmatter(SKILL)
    assert fm["name"] == "desk" and fm["disable-model-invocation"] == "true"
    assert "$ARGUMENTS" in body
    names = [m for m in re.findall(r"desk-[a-z]+(?:-[a-z]+)?", body) if m in pipeline.AGENT_NAMES]
    first_seen = list(dict.fromkeys(names))
    expected = [pipeline.MACRO_AGENT] + [n for n, _ in pipeline.ANALYSTS] + [n for n, _ in pipeline.SEQUENCE]
    assert first_seen == expected
    assert "ONE message" in body and "IN PARALLEL" in body


def test_every_helper_command_the_skill_mentions_exists():
    _, body = frontmatter(SKILL)
    mods = set(re.findall(r"-m desk\.([a-z_]+)", body))
    assert mods == {"status", "prepare", "decision", "summary"}
    for m in mods:
        src = (ROOT / "desk" / f"{m}.py").read_text(encoding="utf-8")
        for flag in re.findall(r"desk\.%s [^\n`]*?(--[a-z\-]+)" % m, body):
            assert f'"{flag}"' in src, f"skill uses {flag} but desk/{m}.py has no such option"


def test_skill_forbids_orders_and_prod_and_report_reading():
    _, body = frontmatter(SKILL)
    assert "Never place" in body and "TradingProd" in body and "Do NOT read the agents' report files" in body
