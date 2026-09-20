# MCL paper session — 2026-09-08

First session on the corrected config: apex OFF (gated in the live path too),
price band on, trailing stop 5%, tiered commission. Two round trips, both
losses, **net −$63.74**.

The P/L is not the finding. Two losses at MCL's ~32% backtest win rate is an
unremarkable draw. Three other things in this session are not.

Source: `var/fills/mcl_fills_20260908.csv`,
`var/archive/watchlist_20260908.txt`, `var/archive/watchlist_blocked_20260908.txt`.

---

## What happened

| | entry | exit | hold | net |
|---|---|---|---|---:|
| WYHG | 08:11:03 @ 5.82 | 08:14:29 @ 5.43, trailing_stop | 3.5 min | **−$40.37** |
| WYHG | 09:16:03 @ 5.58 | 09:21:25 @ 5.36, trailing_stop | 5.4 min | **−$23.37** |

The screen produced 6 names (`BNC WYHG QCML HCWB SLE ISPC`, hot=2 warm=0
cold=4). Three entry signals fired; two filled, one was refused by IBKR.

**Both of 09-08's live-path fixes are confirmed working in production.** Every
exit was `trailing_stop` — no `apex_reversal`, so `evaluate_last_bar` is
honouring `USE_APEX_EXIT = False`. Both entries were inside $2–20. And the
watchlist the trader read is the one `tv_feed` wrote, which is the other
defect found yesterday.

## 1. The entry slippage is 2–4× the friction the whole project charges

This is the important one, and it is the first *live* measurement of the thing
Ben described on 09-08.

| | signal-bar close | backtest models | actually filled | unmodelled |
|---|---:|---:|---:|---:|
| trade 1 | 5.66 | 5.67 | **5.82** | **+15c/share, 2.65% of price** |
| trade 2 | 5.50 | 5.51 | **5.58** | +7c/share, 1.27% |

On 100 shares that is **$22 across two trades, on the entry leg alone**. The
project charges **$4.26 per round trip**, both legs — $8.52 for these two.

Look at where the money went, because it is not where you would guess:

- The order was **not** filled badly. Limit sent 5.84, the ask was 5.82, filled
  at 5.82 in **0.5 seconds**. The trader crossed the spread and got the quote.
- The spread was **tight** — 2c, 0.34% — against the 83 bps median measured for
  pre-market. Nothing unusual there either.
- The entire 16c is the gap between **the bar's close and the market when the
  order was placed**. The 08:10 bar closed at 5.66; the order went out at
  08:11:03 with the market at 5.80/5.82. **The price moved 2.6% in the three
  seconds it took to receive the completed bar and act on it.**

So this is not slippage in the execution sense and no amount of better order
placement recovers it. It is the signal being stale on arrival. `entry_latency`
measured how late the fill sits *within* the signal bar; this measures the
part that happens *after* the bar has already closed, which that study could
not see at all and which no backtest here models.

**What it does to the numbers.** Every result in this project charges $4.26 a
round trip. If 7–15c/share on the entry leg is typical rather than a property
of one very fast name, the true figure is several times that, and every
strategy's per-trade line moves down by the difference. MCL's screened-universe
−$0.53/trade and H0's +$4.72/trade are both inside that margin.

**What stops this being a conclusion: n = 2, one symbol, one session.** WYHG was
moving 2.6% in three seconds; that is not the median name. The project's own
rule — an n = 1 measurement is not a constant — applies with full force. This is
a second reading pointing the same way as the first, not a replacement for it.

## 2. The exit half of the friction log is recording the wrong thing

`var/fills/*.csv` has `ref_close  # what the backtest would have filled at` and
`slippage_vs_ref  # fill - ref_close`. On the entry rows both are correct.

On the exit rows they are not. Both exits fired from the fast path in the main
loop, which runs the trailing stop off the streaming quote every second and
passes `ref_close=st.position.entry_price` (`brokers/ibkr/trader.py:1077`). So
on a trailing-stop exit:

- `ref_close` is the **entry price**, not what the backtest would have filled at
  — which is the trail level, gap-adjusted.
- `slippage_vs_ref` is therefore the trade's **whole per-share P/L**. Both rows
  show it exactly: −0.39 = 5.43 − 5.82, and −0.22 = 5.36 − 5.58.

It is wrong in the way that is hardest to catch: −0.39 is a perfectly plausible
slippage figure on a stop exit in a falling market, so nothing in the file looks
broken. The bar-path exit (`trader.py:936`, `ref_close=sig.close`) is closer but
still not the trail level.

**Why this matters now rather than later.** PROGRAM_INDEX §7 item 6 is "log the
quote with every order, so friction is a standing measurement rather than a
study — this is what stops n = 2 recurring." The logging exists and the entry
half works. The exit half will accumulate confident, wrong numbers for as long
as paper sessions keep running, and §1 above is precisely the question it is
supposed to answer.

The right reference is `pos.trail_level()`, which the code already computes one
line earlier for its `TRAIL HIT` log message and then discards.

## 3. A leveraged ETP got into the universe

QCML fired an entry signal at 09:20:19 and IBKR refused it:

```
Error 201: Order rejected - reason:No Trading Permission, Customer Ineligible;
Ineligibility reasons: Restricted: Must request Complex or Leveraged
Exchange-Traded Product permissions to trade.
```

This is **not** the small-cap block from `ibkr_small_cap_restriction.md`. It is a
different restriction, and it says IBKR classifies QCML as a complex or
leveraged exchange-traded product.

Neither screen has a security-type filter. The live one is three conditions:

```
premarket_change   >= 20
premarket_close    in [2, 25]
premarket_volume   >= 100,000
```

A leveraged ETP clears all three trivially — a 3× fund gaps 20% on a 7% move in
its underlying, which is what it is built to do. `screen.is_test_symbol()`
excludes exchange TEST symbols; nothing excludes funds, in either
`common/screen.py` or `common/tv_screener.py`.

**So they are in the historical universe too, and I checked rather than assumed.**
Against a hand-list of 58 well-known leveraged and inverse ETPs:

| | symbols | known ETPs found |
|---|---:|---:|
| `screen_pairs.json` | 3,878 | **26** |
| `screen_pairs_consolidated.json` | 4,554 | 13 |
| `traded_pairs.json` (Ben's own days) | 302 | 0 |

AMDL, BITX, CONL, ETHU, FNGU, GDXD, GDXU, HIBL, HIBS, LABU, MSTU, MSTX, MSTZ,
NVDU, PLTU, SCO, SOXL, SRTY, SVIX, TSLQ, URTY, UVIX, UVXY, WEBS, YANG, ZSL. That
is 26 hits from 58 guesses, so the true count of funds in the universe is
certainly higher — this is a lower bound, not a census.

**But it did not move any published number.** The strategies barely traded them:

| | trades from known ETPs | their net | total net |
|---|---:|---:|---:|
| MCL | 1 of 2,413 (0.0%) | −$5 | −$1,270 |
| MC5 | 18 of 7,495 (0.2%) | −$226 | +$7,545 |
| VW9 5m | 12 of 1,527 (0.8%) | −$0 | −$7,633 |

So this is a real universe-definition defect and **not** a retraction. It costs
live signals and watchlist slots on names this account cannot trade, and it
means the universe is not what its description says it is — which matters more
for the screener simulation now ranked first in §7 than for anything already
published.

## What I would do, in order

1. **Fix the exit reference** (§2). Small, and every day it waits is a paper
   session whose exit-slippage data cannot be used.
2. **Add a security-type filter to both screens** (§3). Confirmed present in the
   historical universe, confirmed immaterial to published P/L — so this is
   cheap hygiene, not a correction, and it should be done before the screener
   simulation defines the universe it will be judged on.
3. **Keep running paper sessions and let §1 accumulate.** The entry-side number
   is already trustworthy per-trade; what it needs is trades. Ten sessions of
   entry slippage would settle whether $4.26 is the right allowance or a third
   of it, and that single number moves every strategy's verdict.

## Housekeeping

- `var/watchlist.txt`'s header still describes the **old** screen: "$2-20 price,
  RVOL(1D) >= 5x, float < 20m, top pre-market gainer". RVOL and float were
  removed on 09-08. Anyone reading that file is told the universe is
  float-filtered when it is not.
- `var/archive/watchlist_blocked_20260908.txt` opens with "Cleared after the
  2026-09-03 session" — the rotation copies the live file's stale header into
  the dated archive, so the 09-08 archive misdates itself.

Both cosmetic; both the kind of thing that gets quoted as fact six weeks later.
