# Four live-path defects from the 09-17 session, fixed on `main` — not yet promoted

2026-09-17, build chat. Items A–C from `session_review_20260917.md` (live paper-trade
analysis chat); item D from `handover_mc5_apex_live_split_20260917.md` (research chat).
Commits `f127b8f` (the drift-guard registration, before the code), `0951dd5` (A–C) and
`0c50036` (D); bundle **`build-20260917k`** carries all of them (it supersedes `j`,
same base). **Nothing is promoted; `D:\TradingProd` stays at `prod-20260916c`.**
Promote after the close, together, or not at all.

## A. A cancel the trader sends itself is a no-fill, not a rejection

After `_settle` began waiting for IB's terminal status (the ghost fix), a cancel the
trader sent came back as `Cancelled` plus `Error 202: Order Canceled - reason:` with a
blank reason, and the "IB never worked it" branch recorded it as REJECTED. Six rows on
09-17 — four abandoned exits whose next attempt filled in 1–3 s, two timed-out entries
— and `NO_FILL_ABANDONED` / `NO_FILL_CANCELLED` vanished from the ledger, so the
fill-rate and rejection counts were wrong from 09-17.

`_settle` now records the order id it cancelled; `marketable_limit` reads and clears
it. A blank 202 on an id the trader cancelled is the no-fill it always was (abandoned
or timed out, as before). A 202 that carries a reason — the "more aggressive than"
band message — is a rejection whoever sent the cancel, and the band is still consumed
for the next attempt. A blank reason on an id the trader never cancelled (an order dead
at IB before any cancel) stays REJECTED.

**Why the tests missed it:** the fakes in three test files left the order status at
`Submitted` after a cancel, which IB never does. They now set `Cancelled` and push the
202 echo through the trader's own `_on_error`, so the defect is reproducible and its
absence is asserted (`test_self_cancel.py`, 6 tests).

## B. An entry needs a bar that opened after the strategy's own exit

While a position is open the entry path is never reached, so bars that close during it
are never marked evaluated. The first poll after the release evaluated the last closed
bar — one the position was open through — and bought it at the current quote. Seven
re-entries within five seconds of the same strategy's exit on 09-17, (82.62); MC5 RETO
sold 3.30 at 08:24:24 and bought 3.29 at 08:24:25 on a bar that closed at 2.45.

The engine reads each bar once, in order: a signal on a bar it holds a position through
is consumed, the bar the exit is booked on is never an entry bar, and the earliest
re-entry is the next bar's own signal. Live, the exit fires on a quote *inside* a bar;
that bar is the engine's exit bar. So the live rule is on the bar's **open**, not its
close: `bar_after_exit` admits an entry signal only from a bar that opened at or after
`SymbolState.last_exit_et`, stamped by both release paths (the ordinary close and the
reconciled-flat release) from the clock the trader was given. Recorded as
`SKIPPED_BAR_BEFORE_EXIT`, once per bar; per (strategy, symbol), so MC5 releasing a
name says nothing about MCL's next bar on it.

A first version compared the bar's *close* to the exit — which would have admitted the
08:20–08:25 bucket the 08:24:24 exit fell inside. The engine parity test in
`test_bar_after_exit.py` (signals on every bar; the exit bar is never an entry bar) is
what caught it. 12 tests.

## C. A BUY is not sent into a quote 6% from its reference

Registered first in `docs/research/REGISTERED_drift_guard.md`: `DRIFT_GUARD_PCT` =
**6.0**, absolute, on the **ask** (the side a marketable BUY crosses) against the
signal close, BUY entries only. The threshold is the 09-14/15 review's ("do not send a
buy into a quote 6%+ below the reference"), written before the 09-17 trades existed;
the 3% at which the 09-17 count was taken was a descriptive cut after seeing which
trades lost, and is not used. On the 138 trades measured then (p10 (5.39%), p90
+2.13%) the guard binds on roughly one entry in ten.

The guard runs last, on a fresh quote, immediately before the order; at the threshold
it admits (5.30 / 5.00 is 6.000000000000005 in float and is rounded before the
compare); a missing quote goes to `marketable_limit`'s `NO_QUOTE` rather than being
refused under the wrong name; an exit is never guarded. Recorded as `SKIPPED_DRIFT`
with the drift and the threshold. Not an entry filter — drift did not separate outcomes
over 138 trades — and nothing here is scored on P/L; the analysis chat reports what the
refused entries did, descriptively.

The live-path fakes quote 10.00/10.02 whatever frame the trader was handed, so
`tests/brokers/ibkr/conftest.py` switches the guard off for every module but its own,
which scales its frame to the quote. 12 tests.

## D. MC5's apex exit was OFF in the backtest and ON live since 2026-09-10

The same split MCL had from 09-05 to 09-08, one module later. When `USE_APEX_EXIT`
was flipped off on 09-11, `mc5.backtest_session` read it and `mc5.evaluate_last_bar`
kept returning the raw `exit_sig`; the trader acted on it and labelled the exit
`gradient_reversal`. 25 such rows in `var/fills` over 09-11..09-17, ten on 09-17 alone
for (150.74). Every live MC5 session in that window ran a strategy the published MC5
figures do not describe, and the live-vs-backtest comparisons for MC5 over those
sessions are not like for like.

`evaluate_last_bar` now takes `use_apex=None`, defaults to the constant and gates the
exit on it, exactly as MCL's does. The test that should have caught it — "the live
evaluation agrees with backtest_session on the same bar" — compared the live value to
the *raw* `exit_sig`, so it pinned the defect; it now compares to the gated rule, and
`tests/strategy/mc5/test_live_backtest_apex_parity.py` mirrors MCL's suite on a frame
where the apex condition actually fires (the ungated version fails four of its five).

**For the live record:** MC5 rows from 2026-09-10 up to the promotion of this commit
are **apex-ON** rows. The analysis chat owns that join and should tag them; the end
date is the promotion date, so it cannot be written into the code today.

## What to watch on the first session after promotion

- No MC5 `gradient_reversal` exits at all; MC5 exits are trailing_stop and
  window_close only, as in the backtest.
- `NO_FILL_ABANDONED` and `NO_FILL_CANCELLED` rows are back; `REJECTED` rows carry a
  reason.
- `SKIPPED_BAR_BEFORE_EXIT` appears after exits where it would have re-entered; the
  next bar after each exit is still taken when it signals.
- `SKIPPED_DRIFT` at roughly one entry signal in ten; materially more means the quote
  is routinely far from the signal close at placement, and the latency is the question
  before the threshold is.

## Commands

From `D:\Trading`, one line at a time:

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260917k.bundle" main
```

```
python -m pytest tests\ -q
```

Promotion after the close, when you say so — the tag and the `D:\TradingProd` update
are the same two commands as `prod-20260916c`, and I will give them then.
