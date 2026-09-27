# Session review — 2026-09-18 paper session (final)

Live paper-trade analysis chat, read-only. `prod-20260918`. Raw: `D:\Trading\Claude outputs\session_review_20260918.txt`; artifact page published. **Supersedes the partial figures in `live_chat_close_20260918.md` §1.**

## The day
**15 round trips, (14.59).** MCL 3 trades +12.89 (2 winners); MC5 12 trades (27.48) (4 winners). Exits: trailing_stop 12 **(120.47)**, window_close 3 **+105.88**, gradient_reversal **0**.
By symbol: BIAF +80.62, USDE +39.62, AEMD +25.26 (2), SSM +8.63, IMCC (5.74) (2), TCRT (26.85) (5), DAIC (27.37), **AEHL (108.76) (2)**.
Decomposition $/trade: market +5.36, entry +4.75, **exit (9.70)** — the worst exit leg on record outside CRBP — commission (1.37).

## Reconciled against IB — first exact match
IB: 30 executions, every symbol flat, no open orders, NetLiquidation 21,172.41. Ledger: 30 fills, 15 round trips, pairs one-for-one.

**BIAF** (the position that looked open in the portal): `09:00:02 BUY 100 @ 10.18` → `09:30:08 SELL ORDER_UNKNOWN` (cancel sent, no terminal status in 3 s) → `09:30:14 NO_FILL_ABANDONED` → `09:30:26 FILLED 11.00, +80.62`. IB shows one buy and one sell: **the unknown order did not fill**, and D1/D2 refused to send blindly after an unknown outcome. The MEDS failure mode arrived again and was handled.

## Where the loss came from
**AEHL, (108.76) over two trades — 7.5× the day's net loss.** The 04:06 entry: signal close 12.45, bid 10.52 / ask 11.75, **spread 10.47%**. Ask vs close (5.6%) → inside the 6.0% drift guard; mid vs close (10.6%). Filled at the ask. Its exit then took **13 consecutive `NO_FILL_CANCELLED`** (04:09:01→04:14:35, limit 11.24 vs quoted bid 11.27) before filling 11.52. The 06:31 entry held 154 minutes for (84.38).

Median entry spread today was 0.49%, so this is a tail. It is the **spread gate at entry** (`PROGRAM_INDEX` §7 item 20), now with a case; the drift guard's ask-side measurement is correct for its own question and is not the fix.

## The four fixes, all confirmed live
`NO_FILL_*` 16 rows / 0 REJECTED · `SKIPPED_BAR_BEFORE_EXIT` 5, 0 instant re-entries (7 yesterday, (82.62)) · `SKIPPED_DRIFT` 3 · MC5 `gradient_reversal` 0 (10 yesterday, (150.74)) · `ORDER_UNKNOWN` 1, handled.

**What the refused entries did next** (descriptive, n=3): CPOP — no later entry; **TCRT — went on to trade five times for (26.85), so the refusal skipped a sixth at a worse price**; AKAN — no position all session.

## The cap
45 refusals, 07:00:00→09:27:01, 13 names, while three positions held every slot; AEHL held one for 154 minutes while losing 84.38. Two of the three winners only opened after a slot freed at 09:00.

## Display defects (no trading impact)
1. `show_trades` prints IB execution times in **UTC** while the ledger is ET (13:00:01 UTC = 09:00:01 ET), and its header prints the local Sydney clock — three timezones on one screen. `common/report_trades.py`.
2. Realized P/L and commission read 0.00 on every IB row: IB paper does not populate `commissionReport`. The viewer should say the fill log is the P/L source rather than print a zero that reads as a result.
3. **The portal showed BIAF open after the session** — handed to the portal chat (`handover_portal_stale_position_20260918.md`).

## Running live record
194 trades through 09-17 (980.02) + 15 today (14.59) = **209 trades, (994.61), (4.76)/trade**. Today is the first MC5 session that is like-for-like with the backtest.
