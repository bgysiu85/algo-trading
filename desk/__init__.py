"""W18 AI research desk: the Python half.

The agents (.claude/agents/desk-*.md) do the thinking and the /desk skill
(.claude/skills/desk/SKILL.md) runs them in order. This package does everything
that does NOT need a language model, so it costs no Pro usage:

    prepare   fetch IBKR daily bars, compute indicators, pull SEC fundamentals
    decision  validate the portfolio manager's JSON block and log it
    status    which tickers still need a run
    summary   rank the day's decisions

Run them with the repo venv, from D:\\Trading:   .\\.venv\\Scripts\\python.exe -m desk.<name>
"""
