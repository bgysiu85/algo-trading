# W02-0014 · CRML short left open after the 2026-09-21 session — RESULT (2026-09-23, Live analysis chat)

## Finding (Ben confirmed: CRML, 100 shares)
On 09-21 at 09:30 ET, MCL and MC5 each held 100 CRML, so the account held 200. MCL's window_close SELL at 09:30:02 got no terminal status within CANCEL_CONFIRM_S (3 s) and was logged ORDER_UNKNOWN with 0 filled, but it filled after the wait. The re-send guard in `manage_position` asked `_ib_held()`, which returns the **account** position, and got 100. Those shares were MC5's, so MCL re-sent at 09:30:06 and it filled. MC5's own exit at 09:30:07 was a first attempt, which never checks IB, so it sold 100 as well. Result: 300 sold against 200 bought, and the account was left short 100 CRML. The next start's not-flat guard refused to run, and Ben covered by hand on 09-22.

Control case: 09-18 BIAF hit the same ORDER_UNKNOWN with a single strategy holding it, and the account ended flat. Only 2 of the 14 fill logs contain an ORDER_UNKNOWN.

## Fix: built 2026-09-23, commit f166099 (tag prod-20260923b)
- **S1:** `SymbolState.unknown_trade` keeps the ORDER_UNKNOWN Trade. Before any re-send, `_resolve_unknown_exit()` reads its fills and books a late fill as the exit (FILLED row, ref_kind `late_fill`). Nothing is re-sent.
- **S2:** `_ib_held_for()` = the account position less the other strategies' booked shares. It is used for re-sends and in `_adopt_unknown_entry`. `_reconcile_flat` caps the shares it books at the position's own qty.
- **S3:** in `manage_position`, no SELL goes out for more than `_sell_room()` = the account position less SELLs still working (`ib.openTrades`). This applies to first attempts too, except within POSITION_PUSH_LAG_S (15 s) of the entry. A refusal is logged as REFUSED_WOULD_SHORT and counts as an attempt.
- **Session end:** `shorts_at_broker()` puts any short in the session summary and sends it as a forced Telegram alert.
- **Tests:** `tests/brokers/ibkr/test_double_sell_short.py` (10). The replay ends flat, and the control with S1–S3 off ends at −100. `test_the_first_attempt_trusts_local_state` now uses a 2 s-old entry; the `test_pacing_and_trail` fake now holds the shares. tests/brokers + guards: 329 passed. The one failure is the pre-existing encoding guard on strategy/swing/pit_validate.py, unrelated.
- **Numbering:** commit 480619d's message says W02-0014, but that cap-scope work is W02-0015 on the board.

## Next steps (board)
- W02-0014 subitem 3: Ben runs `pytest tests\brokers`, pushes main plus the prod-20260923b tag, then runs a two-strategy session. The commands are on the item.

Sources: var/fills/mcl_fills_20260921.csv, var/fills/mcl_fills_20260918.csv, brokers/ibkr/trader.py, D:\Trading\Claude outputs\w02_0014_crml_short_20260921.txt, monday Result Doc on W02-0014.
