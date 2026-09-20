# Handover — two live-trader defects found in the 2026-09-16 paper session

From: live paper-trade analysis chat (read-only on production).
To: strategy build and test chat.
Written 2026-09-16 ~04:20 ET, while the session was running.

**Production was only read, never changed.** Analysed tree: `D:\TradingProd` at tag
`prod-20260916b` (commit `31b7184`), clean. Line numbers below refer to that commit.
A throwaway read-only probe script was briefly written to `D:\Trading\var\probe\` and
has been deleted, along with its `__pycache__`. Nothing else was written.

**All fixes belong in `D:\Trading`, with tests, and are promoted after the close — never
mid-session.**

---

## Defect 1 — entries fire on a bar from before 04:00 (HIGH)

### What happened

    04:00:10  MCL  VEEA  BUY  ref_close 5.8709  bid 5.60 / ask 5.70  fill 5.70
    04:00:11  MC5  VEEA  BUY  ref_close 5.8709  bid 5.60 / ask 5.70  fill 5.70
    04:00:28  both SELL trailing_stop @ 5.35   (36.37) each, (72.74) total, hold 0.4 min

Ben checked the chart: no indicator condition was met at 04:00. Ten seconds after the
open, IB had no closed 04:00 bar yet, so the signal bar can only have come from before
04:00 (last night's extended hours or IB's overnight session). Supporting evidence:
yesterday's RTH close was 5.70, not 5.8709. The 4-decimal price looks like an
off-exchange print. Live bid was 3.76% below the reference (`ref_drift_pct` −3.76).

**Not yet confirmed: which bar it was.** The IBKR connector and TradingView weren't
reachable. Confirming that is the first task (see "Verify first").

### Root cause (code-confirmed)

- **Live gate checks the clock, not the bar.** `brokers/ibkr/trader.py`
  `in_session()` (~L1070) tests `now_et.time()` only. The entry path (~L1640–1660)
  calls it with `now_et` and never compares `sig.bar_ts` with the session window or
  with today's date.
- **The backtest gates on the bar's own timestamp.** `strategy/mcl/mcl.py` ~L520:
  `in_sess = (local.date == session_date) & (local.time >= SESSION_START) & (local.time < SESSION_END)`,
  and `mc5.py` ~L453 does the same. The backtest cannot produce these trades, so this is
  a live/backtest divergence.
- **History includes pre-04:00 bars.** `_fetch_bars` (~L1127) uses `durationStr="2 D"`,
  `useRTH=False`. Then `drop_forming_bar` (~L389) unconditionally drops the last row. At
  04:00:10 that row is itself a pre-04:00 bar, so the signal may be one bar older still.
- **MC5 has the same gap.** At 04:00:11 its last "complete" 5-minute bucket is 03:55.
- **First-evaluation dedupe doesn't help.** `st.last_bar_ts` starts as `None`, so the
  first evaluation of any symbol always acts on whatever the last bar is.

### It recurs at session open

| date | trade | ref_close | bid / ask | result |
|---|---|---:|---|---:|
| 09-11 | MC5 TNON 04:00:08 | 5.84 | 6.20 / 6.30 | (21.37) |
| 09-14 | MC5 LBGJ 04:00:18 | 2.35 | 2.18 / 2.43 | 2.63 |
| 09-16 | MCL VEEA 04:00:10 | 5.8709 | 5.60 / 5.70 | (36.37) |
| 09-16 | MC5 VEEA 04:00:11 | 5.8709 | 5.60 / 5.70 | (36.37) |

Four entries, net (91.48), none of which any backtest contains.

### Fix to build

1. In the entry path, **refuse an entry unless `sig.bar_ts` (converted to ET) is today
   AND inside `[session_start, session_end)`** for that strategy. That's the same rule
   the backtest applies. Put it next to the existing dedupe, after `st.last_bar_ts` is
   set, so the bar stays marked as evaluated.
2. **Write a fill-log row** for the declined entry (e.g. `status=SKIPPED_STALE_BAR`,
   `reject_reason` with the bar timestamp). Silence reads as "strategy never fired", per
   the portal-bridge invariant. Add the new status everywhere `SKIPPED_*` is treated as a
   non-fill (session reviews, parity checks, `ui_bridge`).
3. Consider a general freshness guard: the signal bar must close within ~2 bar
   intervals of `now_et`. That also catches a stalled data feed mid-session.
4. Check `drop_forming_bar`'s unconditional `iloc[:-1]`. It should only drop a row whose
   bar hasn't closed yet (`common/bar_freshness.py` already measures this).

### Tests to add

- A frame whose last closed bar is 19:59 the previous day, evaluated at 04:00:10 → no
  order, one `SKIPPED_STALE_BAR` row. Same for a 03:59 overnight bar.
- The MC5 adapter at 04:00:11 with a 03:55 bucket → declined.
- The first valid bar (04:00 closed, evaluated at 04:01:0x) → still allowed.
- A parity test: for any frame, the live gate and `backtest_session`'s `in_sess` agree on
  whether the signal bar is enterable.

---

## Defect 2 — trailing-stop peak starts from the signal close, not the fill (HIGH)

### Root cause (code-confirmed)

`trader.py` ~L1747, on entry:

    st.position = Position(..., entry_price=avg, ..., peak=max(avg, sig.close), ...)

Pine seeds the peak from the fill: `MCL.pine` L256
`math.max(high, strategy.position_avg_price)`, and `MC5.pine` L171 / `VW9.pine` L344
`strategy.position_avg_price`. When the live fill is **below** the signal close, the stop
is set closer than 5% under the actual entry.

VEEA: seed 5.8709 → level 5.5774, **2.15% below the 5.70 fill** instead of 5%. Ask 5.55
tripped it 18 s after entry. Seeded from the fill, the level would have been 5.415 and
that tick would not have triggered.

This is the same shape as the 2026-09-02 "peak seeded from pre-entry bar highs" bug:
the trail is set from a price the position never traded at.

### Size across all sessions (09-02 → 09-16, 140 round trips)

- 66 round trips filled below their signal close.
- **28** were exited by `trailing_stop` with the peak never rising above the inflated
  seed, meaning the seed alone set the level. Net **(443.36)**.
- CRBP 09-14 is (241.37) of that and would probably have stopped anyway in the collapse.
  Ex-CRBP: (202) over 27.
- Most of the 28 held 0.0–0.4 minutes. Earlier examples are MC5 TNON/LBGJ/FTFT on 09-10/11
  (pre-dedupe-fix re-entries) and BDRX/NAMI on 09-15.
- These are counterfactual limits, not a result. Without tick data we can't say which of
  them would have survived with a correct seed.

### Fix to build

- `peak=avg` on entry. Post-entry bar highs are already fed only from bars that closed
  after `entry_time` (~L1618), which matches Pine.
- Check the adoption path (~L986, `peak = max(entry_price, …)`) uses the same rule.
- **Test:** fill 5.70 with signal close 5.8709 → `trail_level() == 5.415`, and an ask of
  5.55 doesn't exit.
- Check whether the backtest engine fills at the signal close. If so, backtest and live
  only coincide when fill == close. Pin the equivalence with a parity test.

---

## Related observations (no action asked, context only)

- **Both strategies can hold the same symbol at once.** VEEA was 200 shares across MCL and
  MC5 in the same second. That may be intended (the cap counts across strategies), but
  it doubles single-name exposure. Worth an explicit decision.
- **Scoring by `slippage_vs_ref` stays misleading.** Both VEEA buys logged +0.1709
  ("better than reference") into a stale reference. Same point as `session_review_20260914_15.md` §7.3.
- **Today's watchlist at 04:09 ET** was three names (VEEA, MYSZ, PSNYW). PSNYW (a warrant)
  was refused with "no Stock security definition".

## Verify first (read-only, in the build chat — not against production)

Confirm which bar produced close 5.8709. Pull VEEA 1-minute TRADES bars, `useRTH=False`,
`2 D`, on a spare client id against paper Gateway 4002. Print 15:55 ET 09-15 → 04:05 ET
09-16, flag close 5.8709, and show the bar the trader would have acted on at 04:00:10
after `drop_forming_bar`. The result decides whether the overnight session is in IB's
history. That matters for the fix in point 3 and for the indicator warm-up in both
strategies.

## Source files

- `D:\Trading\var\fills\mcl_fills_20260916.csv` (plus 20260902–20260915 for the
  cross-session counts)
- `D:\Trading\var\watchlist.txt`, `watchlist_blocked.txt`
- `D:\TradingProd` @ `prod-20260916b`: `brokers/ibkr/trader.py`, `strategy/mcl/mcl.py`,
  `strategy/mc5/mc5.py`, `pine/MCL.pine`, `pine/MC5.pine`
