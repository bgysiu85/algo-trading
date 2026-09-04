#!/usr/bin/env python3
"""Thin entry point — kept at this filename deliberately.

The real implementation is trader.py: strategy logic split into
mcl_strategy.py (see claude/repo_reorg_and_github_plan.md STEP 2). This
file stays named mcl_paper_trader.py, and still lives here flat, because
two things depend on the literal name and path:

  * run_dry.ps1 / run_paper.ps1 invoke `.\\mcl_paper_trader.py` directly.
  * run_backtest_after_session.ps1 detects a running live session by
    matching the literal string "mcl_paper_trader" in the process command
    line, to avoid throttling IB's shared request budget against a live
    session. Renaming or removing this file breaks that guard silently.

Both move to `main.py` with a proper lock-file guard in Step 3/4 of the
reorg plan. Until then, this file is the whole of what changes.
"""

from brokers.ibkr.trader import main

if __name__ == "__main__":
    main()
