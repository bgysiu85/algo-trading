# Session review — 2026-09-14 and 2026-09-15

Paper sessions, 04:00–09:30 ET. Sources `var/fills/mcl_fills_2026091[45].csv`,
`var/archive/watchlist_2026091[45].txt`, `watchlist_blocked_20260914.txt`, and
`E:\Databento\XNAS.BASIC\ohlcv-1m\2026-09-14_0400_0930.dbn.zst`.

**Every figure here is a real fill.** Spread and slippage are inside the fill
prices and a $1.37 round-trip commission is already deducted from `trade_pnl`.
No friction assumption is used anywhere — the live book is the only evidence in
this project that does not depend on one.

---

## 1. The two sessions

| | orders | filled | round trips | net |
|---|---:|---:|---:|---:|
| 2026-09-14 | 64 | 40 | 20 | **(338.43)** |
| 2026-09-15 | 39 | 38 | 19 | **(185.01)** |
| **two days** | | | **39** | **(523.44)** = (13.42)/trade |

    2026-09-14  MCL  n= 8  (294.97)  per (36.87)  win 12%  hold 12.2m
                MC5  n=12   (43.46)  per  (3.62)  win 25%  hold 20.1m
    2026-09-15  MCL  n= 7   (51.58)  per  (7.37)  win 14%  hold 13.2m
                MC5  n=12  (133.43)  per (11.12)  win  0%  hold  5.5m

5 winners, 34 losers.

> **This is not a regime change.** Remove one fill and the two days are
> **(282.07) over 38 trips = (7.42)/trade**, against a **(6.87)** baseline over
> the previous six sessions.

## 2. CRBP — 46% of the two-day loss, in 42 seconds

Bought 9.16 at 07:02:08, sold 6.76 at 07:02:40. **(241.37).**

    07:02:05  BUY   entry_signal   ref 9.75    bid 9.11 / ask 9.35   spr  2.57%
              limit 9.37 -> FILLED 9.16 in 3.15s   slippage_vs_ref +0.59
    07:02:10  SELL  trailing_stop  ref 9.2625  bid 9.08 / ask 9.16   spr  0.87%
              limit 9.06 -> NO_FILL_CANCELLED
    07:02:31  SELL  trailing_stop              bid 5.28 / ask 6.87   spr 23.14%
              limit 5.26 -> REJECTED  "…more aggressive than 6.31944"
    07:02:32  SELL  trailing_stop              bid 5.54 / ask 6.61   spr 16.19%
              limit 5.52 -> REJECTED  "…more aggressive than 6.26316"
    07:02:33  SELL  trailing_stop              bid 6.06 / ask 6.61   spr  8.32%
              limit 6.04 -> REJECTED
    07:02:34  SELL  trailing_stop              bid 6.29 / ask 6.61   spr  4.84%
              limit 6.27 -> FILLED 6.76   pnl (241.37)   hold 0.7m

The tape:

    06:59   8.8200  9.0825  8.8200  8.9800    10,354
    07:00   8.9800  9.9100  8.9800  9.7500   116,100   <- signal bar
    07:01   9.7500  9.8000  9.0700  9.2000   103,250
    07:02   9.2000  9.4700  5.5678  6.9795   129,658   <- bought AND sold here
    07:03   6.9900  8.1300  6.8151  7.9900    83,486
    07:06   8.6100  9.6100  8.5610  9.5600    93,614

Opened near the top of the flush, closed near its bottom, **inside the same
minute**, which closed at 6.98. Four minutes later CRBP traded above the entry.

### Three mechanical failures, none of them a strategy question

**A. The order was sent into a quote that had already left the reference.**
Priced off 9.75; the bid on the same log row was 9.11 — 6.6% lower. The system
had that number in hand and nothing looked at it. Worse, the fill is *recorded
as good*: `slippage_vs_ref = +0.59`. **The execution-quality metric scored the
worst trade in the book as one of the best fills of the day** — a control whose
output is indistinguishable from the failure it exists to detect.

**B. The trailing stop cannot chase a collapse.** It is a *limit* order priced
just under the current bid. In a fast fall the bid outruns the loop: attempt one
stale, attempts two–four below IBKR's acceptable band. Five attempts, 24
seconds, during a 42% drop. **All fifty other exits across these two days filled
on the first attempt.**

**C. The broker's rejection message is not read.** IBKR states the acceptable
bound in the rejection text. Three round trips to the broker were spent
re-learning a number it had already supplied.

**The cap saved money by accident.** CRBP signalled again at 07:15 and 07:33;
both were blocked by the concurrency cap — by arrival order, not judgement.

## 3. Drift as an entry filter — tested, and NO

`drift = (mid at order / signal close − 1)`, 138 paired round trips, all sessions.

| | drift | n | net | per | win |
|---|---|---:|---:|---:|---:|
| Q1 | (8.59%) … (1.91%) | 34 | (414.47) | (12.19) | 12% |
| Q2 | (1.63%) … (0.24%) | 35 | **23.40** | **0.67** | 26% |
| Q3 | (0.24%) … 0.44% | 34 | (321.94) | (9.47) | 15% |
| Q4 | 0.46% … 10.54% | 35 | (490.12) | (14.00) | 14% |

Not monotone; the only positive bucket is interior. Dropping CRBP takes Q1 from
(12.19) to (5.54) — nearly the whole Q1 effect *is* that trade.

> Drift belongs as a **risk control on order placement** (do not send a buy into
> a quote 6% below its reference), **not** as an entry condition. Different
> claims; only the first is supported.

## 4. 2026-09-15 was the cleanest execution session on record

| | 09-15 | 09-14 | 09-11 |
|---|---:|---:|---:|
| cap rejects | **0** | 12 | 13 |
| broker rejections | **0** | 3 | 0 |
| exits needing a 2nd attempt | **0** | 2 | 0 |
| median spread at order | **0.289%** | 0.755% | 0.404% |
| median seconds to fill | 0.52 | 0.52 | 0.52 |
| trailing-stop slippage, median | (0.0150) | (0.0200) | (0.0563) |

All 19 round trips filled first time. MC5 went 0 for 12. **Nothing about
execution explains (185.01); the entries were simply wrong.**

Exit mechanic, both days, per share vs reference:

    gradient_reversal  n= 9  median  0.0000   mean (0.0025)
    trailing_stop      n=26  median (0.0190)  mean (0.1235)
    window_close       n= 4  median (0.0850)  mean (0.0975)

The gap between the trailing stop's median and mean **is CRBP on its own**: the
stop's typical cost is small and its tail is not, which is what a median alone
conceals. A signal exit still fills at the reference — third confirmation.

## 5. Ben's labelled samples meet the algorithm, same morning

Nine of the 21 screenshots are 2026-09-14. **All five symbols were on that
morning's 16-name watchlist** — the screen found every name he was watching.

| sample | his label | the algorithm | result |
|---|---|---|---:|
| SCNI 06:57 | took and lost | signalled 07:00, **cap-blocked**; entered 08:58 | (5.37) |
| CRBP 07:03 | took | entered 07:02:05, out 07:02:34 | **(241.37)** |
| CRBP 07:19 | pass | signalled 07:15, **cap-blocked** | — |
| DRCT 07:22 | pass | no signal | — |
| DRCT 07:28 | took and lost | no signal | — |
| CRBP 07:32 | took and lost, "bought at peak" | signalled 07:33, **cap-blocked** | — |
| ARMP 07:57 | pass | **no signal — agreement** | — |
| BMGL 08:15 / 08:21 | took | entered 09:02 | (15.38) |

**On the two CRBP bars Ben marked as bad — one an explicit pass, one "bought at
peak" — the algorithm wanted to buy**, and only the concurrency cap stopped it.
Same name, same direction of error, twenty minutes apart. On ARMP 07:57 (his
pass on a vertical move, MFI 100) the strategy produced no signal at all.

One session and nine bars settles nothing. What it establishes is that the
labelled set is about the **same decisions the live system is making**, on the
same names, at the same minutes — which is what makes `entry_place` worth
running.

## 6. The running live record

| date | trades | net | MCL | MC5 | cap | rej |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09-02 | 2 | (1.00) | — | — | 0 | 4 |
| 2026-09-03 | 19 | (163.60) | — | — | 0 | 2 |
| 2026-09-08 | 2 | (63.74) | — | — | 0 | 0 |
| 2026-09-09 | 6 | (70.26) | (70.26) | — | 3 | 0 |
| 2026-09-10 | 22 | (224.18) | (57.24) | (166.94) | 30 | 10 |
| 2026-09-11 | 48 | (156.91) | **46.12** | (203.03) | 13 | 0 |
| 2026-09-14 | 20 | (338.43) | (294.97) | (43.46) | 12 | 8 |
| 2026-09-15 | 19 | (185.01) | (51.58) | (133.43) | 0 | 0 |
| **total** | **138** | **(1,203.13)** | | | **58** | **24** |

Per trade **(8.72)**, win rate **16.7%**. First six sessions (6.87)/trade at
18.2%; last two (13.42) at 12.8%.

**The cap has now rejected 58 buy attempts against 138 completed round trips.
No backtest in this project models that at all.**

## 7. What to do

1. **Read IBKR's price band out of the rejection and use it.** Three of the
   14th's eight failed orders were re-sends that ignored a bound the broker had
   already given. Mechanical, cheap, no strategy question.
2. **A stop that cannot fill is not a stop.** Either the stop leg becomes
   marketable once price is through the level by some margin, or the trail's
   measured cost carries the tail it currently hides. **Not a `TRAIL_PCT`
   question** — that lever is closed. This is order type, already ranked as §2.5
   of `intraday_candidates_20260915.md`.
3. **Stop scoring fills by `slippage_vs_ref` alone.** It called (241.37) a
   59-cent favourable fill. A buy filling far *below* its reference is a warning
   that the reference is stale, not a bargain. Report drift beside it.
4. **Rank; do not let arrival order decide.** 58 cap rejections, and on the 14th
   the cap's accidental choices beat the strategy's deliberate ones. Item 3 of
   the proposed `PROGRAM_INDEX` §7 insert.
5. **Run `entry_place`.** §5 establishes the labelled set is about the same
   decisions the live system is making.

### What this does not support

- Not a regime-change reading — ex-CRBP, (7.42) against a (6.87) baseline.
- Not a drift entry filter — §3, explicitly tested and null.
- n = 39 over two sessions; 16.7% win over 138 trades. **The sample is sessions,
  and there are eight.**

## Also observed

The portal CONFIG audit row is live: `2026-09-14 03:40:37 CONFIG session_open
trail_pct=5.0 paused=False max_positions=3 enabled=True portal=http://127.0.0.1:8000`.
Two rows on the 14th, none on the 15th.

Price-band skips (2.00–20.00): ELMT ×3 at ~23.0–23.2, DRCT ×1 at 1.9255.
IBKR closing-only refusals on the 14th: PCLA, RAYA.
