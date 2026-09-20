# MCL-PB v5 result — the decisive close, and where the pullback line ends

`python -m common.pullback_break --jobs 8` · raw `var/reports/pullback_break_mcl.txt`,
trades `pullback_break_trades.csv` · registration `REGISTERED_pullback_break_v5_20260916.md`
· bundle `mcl-pb-20260916g` · artifact "The Decisive Close". 551 sessions, 6,170
symbol-days, MCL 3,955 = published.

## Verdict: NOTHING vs MCL; NOTHING vs v3 (both definitions)

| @ $4.26 | trades | per trade | net | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|
| MCL | 3,955 | (10.52) | (41,599) | (10.68) | (10.40) | 22.2% |
| PB5-atr-g3 (primary: close ≥ 1 ATR10 over level) | 11,238 | (10.96) | (123,193) | (11.25) | (10.75) | 22.1% |
| PB5-rsi-g3 (RSI14 ≥ 64 on break bar) | 10,048 | (11.13) | (111,880) | (10.79) | (11.39) | 25.0% |
| PB5-atr-g0 | 9,925 | (12.78) | (126,890) | (12.78) | (12.79) | 20.2% |
| PB3-g3 (control) | 20,132 | (10.08) | (202,858) | (10.53) | (9.76) | 22.8% |

Second reading margins vs v3: ATR (0.72)/(0.99), RSI (0.26)/(1.63) — under the registered
$4.26 and negative. Pre-07 "holds" by $1.40/$2.20, under friction.

**The finding:** classify v3's own 20,132 trades by whether each rule would have accepted
the entry bar — ATR kept 8,563 at **(11.58)**, dropped 11,569 at **(8.96)**; RSI kept 6,915
at (11.40), dropped 13,217 at (9.39). Both definitions of "decisive" select the worse half.
A big close on volume with high RSI is the bar where the move already happened; consistent
with `entry_fill` / `entry_place` (losses sit in entries that paid the top tick, "the
confirmation itself is the cost"). The 15-example fit from 2026-09-11 did not generalise.

## The pullback line, closed

v1 (11.07) · v2 (16.11) · v3 (10.06) · v4 (9.90) · v5 (10.96) per trade; MCL (10.52).
Five registrations, five NOTHINGs. Entry moved earlier/later/bounce top/close, gated by
volume, MACD, ATR, RSI; exits: 5% trail, cents target, 3-bar green hold, structure stop.
Every version lands at (10)–(11)/trade on this tape. Reproduces `stop_lever_closed_20260914`
§4 from the entry side. Open: 08:00 interleaved-price defect (undiagnosed). Holdout unspent.
