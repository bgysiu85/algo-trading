> **ARCHIVED 2026-09-08.** A historical session review, kept for the record.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Friction figures superseded — but mostly CONFIRMED.** The fills recorded
> here are real and remain accurate. The friction figures derived from them were
> each computed on a single session; on 2026-09-06 execution cost was measured
> against **18,552 real quotes** at the moment of real fills.
>
> That measurement **confirmed** the project's existing assumptions rather than
> overturning them: `LIMIT_CROSS_BPS = 20` against a measured 17.3 bps, and the
> documented 37–43 bps effective cross against a measured half-spread of 40–41
> bps — two figures derived by completely different methods landing in the same
> place.
>
> What it did **not** support is the buy/sell asymmetry drawn from these
> sessions. Measured across both sides it is symmetric and indistinguishable
> from zero. A single session was never enough to establish it. See
> `execution_cost_measured.md`.

# Session review 2026-09-03 + backtest post-mortem

First session with the trailing-stop peak fix, so **hold times are valid for the
first time**. They are the most important number here, and they point somewhere
unexpected.

---

## 1. Live paper session

**19 round trips, net -$163.60, 2 winners.** Win rate 10.5%.

| Exit reason | n | net | avg | win |
|---|---:|---:|---:|---:|
| apex_reversal | 16 | -$81.60 | -$5.10 | 12.5% |
| trailing_stop | 1 | -$68.00 | -$68.00 | 0% |
| window_close | 2 | -$14.00 | -$7.00 | 0% |

Per symbol: BIAF -$78, TLYS -$30, GYGY -$28, DLTH -$10, YQ -$9, NYXH -$5,
GELS -$3.60. Nothing profitable.

Mean hold **2.0 minutes**, median 2.0, nine of nineteen under two minutes.
Sixteen of nineteen exits were `apex_reversal`, fourteen of those losses.

### Execution was fine

- Fill rate **38/40 = 95%**. Two `NO_FILL_CANCELLED`, both re-attempted and
  filled seconds later -- the sticky-exit fix working as designed.
- Median time to fill **0.52 s**; worst 9.44 s.
- Median spread **0.508%** (0.021% - 2.979%).
- Slippage vs reference: **BUY +$0.0164/share (favourable)**,
  **SELL -$0.0590/share (unfavourable)**.

Net round-trip slippage about **-$0.043/share = -$4.26 per 100 shares**, against
the backtest's modelled tick-each-way of -$2.00. The model understates friction
by roughly **$2.26/trade** -- material against a $15-17 modelled edge, nowhere
near enough to explain -$8.61.

### IBKR blocking - much better than 2026-09-02

One name refused: **MIMI**, and for a *different* reason than JLHL -- "closing-
only status, margin/risk management" rather than the small-cap compliance
restriction. MIMI produced no entry signals, so **0 of 19 signals were lost to
blocking**, against 3 of 7 on 2026-09-02. One session each way is not a rate,
but it weakens the case that IBKR structurally cannot host this strategy.

### Housekeeping - first live run, all three worked

`archive/watchlist_20260903.txt` and `archive/watchlist_blocked_20260903.txt`
written; both live files cleared. No manual intervention.

---

## 2. Historical backtest - ran to completion, 83% lost to a bug

All 407 pairs attempted. Result: **337 NOT_QUALIFIED, 70 OK** (68 with
pre-market bars). The failures were my bug, not missing history.

### Root cause

`qualify()` was not paced. `_pace()` guarded historical requests at one per
12.5 s, but qualification ran flat out, trying up to five exchanges per symbol
-- ~1500 requests as fast as the loop could issue them. IB throttled, and a
throttled qualification returns an **empty list**, identical to a genuinely
unknown symbol. Each was then cached in `self.unqualified` permanently.

The proof is the ordering: `traded_pairs.json` is sorted alphabetically, and
qualification succeeded for **ABOS through CAMP** -- 47 symbols -- then failed
for nearly everything after. Stocks do not delist in alphabetical order.

Compounding bug: `--retry-failed` only cleared `NO_DATA`, so a rerun would not
have retried one of the 337.

### Fix applied 2026-09-03

- qualification paced at `QUALIFY_INTERVAL_S = 2.0` (~30/min)
- plain `SMART` tried first -- one request instead of up to five
- `QUALIFY_FAIL_STREAK = 5` consecutive failures triggers a 60 s cooldown and
  one retry, because a streak is evidence of throttling, not of five delisted
  symbols in a row
- `--retry-failed` now clears `NOT_QUALIFIED` too
- the report warns when the qualification failure rate exceeds 25%

Rerun (outside a session): `.\.venv\Scripts\python.exe mcl_backtest.py --retry-failed`

### The 70 pairs that did work

**89 trades, +$1,374.53, 40.4% win, +$15.44/trade**, 25 symbols, 14 profitable.

Alphabetical position is unrelated to how a stock behaves, so the 47 symbols
that qualified are effectively a **random ~15% sample** of the contemporaneous
set -- names picked live by a scanner, not with hindsight. On that sample
expectancy held at **+$15.44/trade against the hindsight set's +$17.46**.

Concentration is unchanged as a problem: drop top 1 -> +$850, top 3 -> +$158,
top 5 -> **-$239**. ASST +$524, BIAF +$396, BATL +$296 carry it; APVO -$380.

---

## 3. THE FINDING: the apex exit is not where the money is

Comparing the two directly settles the live-vs-backtest tension.

| | backtest (89 trades) | live (19 trades) |
|---|---|---|
| median hold | 2 bars | 2.0 min |
| exits on apex_reversal | **34%** | **84%** |
| exits on trailing_stop | 66% | 5% |

**Hold times match exactly.** Two-minute holds are inherent to the strategy, not
a live-vs-backtest divergence. What differs is the exit *mix*, and the split of
profit inside the backtest is the thing worth staring at:

| backtest exit | n | net | avg | win |
|---|---:|---:|---:|---:|
| trailing_stop | 59 | **+$1,320.89** | **+$22.39** | 42.4% |
| apex_reversal | 30 | +$53.64 | +$1.79 | 36.7% |

**96% of the backtest's profit comes from trailing stops.** The apex exit
contributes +$53.64 from a third of all exits -- statistically indistinguishable
from zero, and negative once the extra $2.26/trade of real friction is applied.

That reframes the whole exit discussion. A trailing-stop exit means the trade
*ran up first* and then gave back 5% from a higher peak -- the peak did its job.
An apex exit means the position was closed while the trail was still intact.
In the backtest two thirds of trades got to run. Live, 84% were closed by apex
before the trail was ever reached.

### The experiment this implies

**Remove `apex_reversal` entirely** and let the 5% trailing stop and the 09:30
window close do all the work. Single variable, offline, cheap. In the backtest
those 30 apex exits would instead continue to either a trailing stop or the
window close -- and the trailing-stop population averages +$22.39.

This is a better-motivated test than either of the two currently queued
(intrabar entry timing, and `MACD > 0` on its own), because it is pointed at
where the money demonstrably is rather than at a hypothesis about where it
might be.

### What it does not yet prove

The 16 live apex exits might have been correct -- those trades might have kept
falling. Confirming requires the post-exit bars: for each apex exit, did price
subsequently reach a higher peak, or did it keep going down? That is the MFE
analysis, and today's seven symbols are recent enough that IB will still serve
1-minute history for them.

Order of work: MFE on today's apex exits, then the no-apex backtest variant,
then the earlier questions about entry timing and `MACD > 0`.
