# W11-0024 · Step 3 — Mean-reversion cross-check (video 4) — RESULT

2026-09-23 · Sonnet/Low session on W11-0024 (Project management chat) · Documentation cross-check only, no backtest run.

## In plain terms

Video 4 ("Claude Tested Over 9,000 Trading Strategies") claims that of 524 strategies surviving its filters, 64% were mean-reversion, and that mean reversion was the only category net positive on average. That points in the same direction as Ben's own mean-reversion line of work (RSI/MFI confluence, `/areas/mean-reversion-strategy.md`), but it isn't independent evidence for it. The video gives no strategy definitions, no per-category numbers, no data range, no code — the same self-reported, unfalsifiable style that step 1 already found didn't hold up when the Markov claims from the same collation batch were actually run. On top of that, **Ben's own mean-reversion strategy (MR-60) hasn't been coded or run anywhere in this project yet** — gate G3 in `REGISTERED_h60_v0.md` is still open, waiting on Ben to supply the Pine file's defaults (W14-0005). So there is nothing on the board yet to actually compare numbers against.

## Verdict: what Ben must decide

- **Weak corroboration only — a category-label match, not a performance match.** Nothing to act on beyond noting it.
- No change of plan. MR-60 stays exactly where it already is: gated on Ben supplying the Pine source (G3, W14-0005). This finding doesn't move it up or down the queue.
- Not a reason to skip running MR-60 properly, and not a reason to speed it up either — the video is not evidence of anything measurable.

## Comparison

| | Video 4's "mean reversion" category | Ben's MR-60 |
| --- | --- | --- |
| Strategy definition | Never stated — no indicators, thresholds, or entry/exit rules given for any of the 524 survivors | RSI + MFI confluence, ATR-based stop, optional 200-EMA trend filter, Pine v5 (`mean-reversion-strategy.md`) |
| Universe / timeframe | 30 assets, 15 years, bar size unstated | S&P 500 + S&P 400 point-in-time universe, 60-minute bars, 1–5 day holds (`REGISTERED_h60_v0.md` §2) |
| Stated validation | Walk-forward → Sharpe > 0.5 → max DD 35% → bootstrap (500 reshuffles) → out-of-sample — but no numbers, no code, and the sixth filter it claims to have isn't even named | Project's own H60 gates G1–G7: hindsight guards, cost-checked fills, a mutation-tested holdout cut, a positive control, benchmarked against holding the universe and against random entries |
| Track record shown | None — a single aggregate percentage ("64% of survivors"), no per-strategy Sharpe/DD/P&L | None yet — MR-60 has not been run |
| Independently reproducible? | No — same presenter family (AI Pathways) whose Markov-claim channel-mates (videos 2–3, same collation batch) were checked in step 1 and did not reproduce | N/A — nothing to reproduce yet |

## Method

Read the Video 4 section of `claude/yt_collation_ai_claude_trading_methods_20260923.md`, `/areas/mean-reversion-strategy.md`, and `REGISTERED_h60_v0.md` §3.6 and its gate table (§0). Checked the board and `PROGRAM_INDEX.md` for any prior MR-60 run — none exists; G3 is open, waiting on Ben.

## Caveats

- This step is a documentation/methodology comparison only, as scoped (Sonnet/Low, "read-and-compare"). No code was written and no numbers were computed.
- Video 4's claim could still be directionally right — mean-reversion edges are a well-studied, plausible category — but this document can't say so with evidence; it can only say the video doesn't supply any, and that MR-60's own test is still ahead of it, not behind it.
- If Ben wants an actual side-by-side, that requires MR-60 to run first, which requires Ben to supply the Pine file's saved defaults (G3, W14-0005) — unrelated to this cross-check.

## Sources

- `claude/yt_collation_ai_claude_trading_methods_20260923.md` (Video 4 section)
- `/areas/mean-reversion-strategy.md`
- `REGISTERED_h60_v0.md` §0, §3.6
- `PROGRAM_INDEX.md` (no MR-60 entry)
