# Handover — MC5's gradient-reversal exit is OFF in the backtest and ON live

**From:** research chat, 2026-09-17. **Read-only finding; no code changed.**

## What Ben saw

Trader portal, 2026-09-17, "Closed today", MC5: 4 of 11 round trips closed by
`gradient_reversal` (MEDS 06:11, MEDS 04:46, RETO 04:50, MEDS 04:15). Yet
`claude/apex_and_ladder_20260911.md` §1 records the rule as **TURNED OFF**
(`USE_APEX_EXIT = False` in `strategy/mc5/mc5.py`, shipped `20260910t` + flip).

## Where the split is

`strategy/mc5/mc5.py`:

- line 136 — `USE_APEX_EXIT = False`
- line 468 — `backtest_session` reads it: `apex = USE_APEX_EXIT if use_apex is None else use_apex`
- line 561 — `elif apex and bool(row["exit_sig"])` — **backtest is gated**
- line 378 — `evaluate_last_bar` returns `exit_signal=bool(row["exit_sig"])` — **live path is NOT gated**

`brokers/ibkr/trader.py` line 1845 acts on `sig.exit_signal` as delivered, and
line 1849 labels it `st.strategy.exit_signal_reason` = `gradient_reversal`.

So: the constant governs every published MC5 figure since 2026-09-11, and the
live trader has never read it.

## This is the same defect MCL had, already diagnosed

`strategy/mcl/mcl.py` lines 266–286, docstring of `evaluate_last_bar`:

> USE_APEX_EXIT IS APPLIED HERE, not left to the caller. It was, until
> 2026-09-08, and the result was a live/backtest split on the one rule that
> changed … Routing through the same function was necessary and was not
> sufficient: the flag is read in backtest_session, which the live path never
> calls.

MCL's fix (2026-09-08): `exit_signal=bool(row["exit_sig"]) and use_apex`.
MC5's `evaluate_last_bar` was not given the same line when its constant was
flipped on 2026-09-11.

## Evidence it has been firing all along

- `var/fills/mcl_fills_20260911..17.csv`: **25 MC5 `gradient_reversal` rows**
  after the switch was flipped.
- `claude/session_review_20260914_15.md` §4 already tabulated
  `gradient_reversal n=9` for those two live days — the label was visible,
  the contradiction with §1 of the 09-11 doc was not noticed.

## What this means for the live record

Every MC5 live session from 2026-09-10 onward has been running apex **ON** —
the configuration measured at −$12.23 per signal exit (138 exits, −$1,687 in
the 09-11 study). The live MC5 record and the published MC5 backtest are
**different strategies**. The live-vs-backtest comparison in
`session_review_20260914_15.md` §6 is therefore not a like-for-like comparison
for MC5.

## Ask of the build chat

1. Gate `strategy/mc5/mc5.py::evaluate_last_bar` on `USE_APEX_EXIT` exactly as
   MCL does (line 378, add `and use_apex`, with a `use_apex=None` parameter
   defaulting to the constant, mirroring `mcl.evaluate_last_bar`).
2. Add the test MCL presumably got on 2026-09-08: with the constant False,
   `evaluate_last_bar` must return `exit_signal=False` on a bar where
   `signals()` says `exit_sig=True`. If no such test exists for MCL either,
   add it for both.
3. Tag live MC5 rows 2026-09-10 → fix date as **apex ON** in whatever joins
   `paper_fill` to `backtest_trade`, so they are not read as the apex-OFF
   strategy.
4. Note it in `PROGRAM_INDEX` under the "two implementations drifted" family —
   this is the third instance (harness literal, MCL evaluate, MC5 evaluate).

Nothing here changes any verdict: MC5 is (13.50)/trade in the PIT book with apex
OFF and would be worse with it ON. It changes only what the live sessions were
measuring.
