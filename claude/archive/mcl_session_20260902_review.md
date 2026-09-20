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

# MCL paper session review — 2026-09-02

First session with real orders. **Two complete round trips filled**, four orders
rejected, and the fill log exposed a trailing-stop bug that would have wrecked
every trade.

Watchlist: SGLD, UPC, CANF, PPBT, KIDZ active; JLHL blocked mid-session.

## The eight logged events

| Time ET | Sym | Action | Reason | Status | ref | bid/ask | limit | fill |
|---|---|---|---|---|---|---|---|---|
| 05:55:01 | UPC | BUY | entry_signal | REJECTED | 5.31 | 5.27/5.31 | 5.3206 | — |
| 06:34:01 | JLHL | BUY | entry_signal | REJECTED | 7.72 | 7.72/7.76 | 7.78 | — |
| 06:42:01 | JLHL | BUY | entry_signal | REJECTED | 7.81 | 7.81/7.83 | 7.85 | — |
| 07:02:02 | JLHL | BUY | entry_signal | REJECTED | 7.52 | 7.26/7.28 | 7.30 | — |
| 08:44:03 | UPC | BUY | entry_signal | **FILLED** | 5.09 | 5.01/5.03 | 5.05 | **5.02** |
| 08:47:03 | UPC | SELL | apex_reversal | **FILLED** | 4.99 | 5.02/5.10 | 5.00 | **5.02** |
| 08:51:02 | PPBT | BUY | entry_signal | **FILLED** | 2.6485 | 2.70/2.71 | 2.72 | **2.72** |
| 08:51:10 | PPBT | SELL | trailing_stop | **FILLED** | 2.72 | 2.67/2.68 | 2.66 | **2.75** |

**Round trips:** UPC 5.02 → 5.02, held 3.1 min, **−$2.00** (commission only).
PPBT 2.72 → 2.75, held **0.2 min**, **+$1.00**. Net **−$1.00** on 2 trades.

**Rejections:** all four were configuration/eligibility, not liquidity. One tick-size
bug (UPC 5.3206), three IBKR compliance blocks (JLHL). **Zero `NO_FILL_CANCELLED`.**

## Finding 1 — the trailing stop was seeded from PRE-ENTRY bar highs (fixed)

PPBT entered 08:51:02 at 2.72 and stopped out **8 seconds later**.

`manage_position` set `pos.peak = max(pos.peak, bar_high, last_price)` where
`bar_high` came from `df["high"].iloc[-1]` — the last *closed* bar, which is
normally the bar **before** the fill. PPBT's pre-entry high was ≈2.95, so:

    peak 2.95 -> trail 2.95 x 0.95 = 2.8025 -> ask 2.68 <= 2.8025 -> STOP

The position was stopped out against a high it never traded at while held. Pine's
`peakSinceEntry` only ever sees bars from the entry onward.

**Fixed:** a bar high is only fed to the peak when the bar closed *after*
`entry_time`. Verified three ways, including a reproduction of this exact case.

This is not cosmetic. Every trade would have carried a trailing stop set from
pre-entry price action — systematically far too tight, exiting in seconds, and
producing a fill log that looked like the strategy had no edge.

## Finding 2 — IBKR's compliance block cost 3 of 7 entry signals

JLHL rejected three times with error 201, *No Opening Trades: Small Cap, Subject
to Compliance Restriction*. See `claude/ibkr_small_cap_restriction.md`.

**43% of this session's entry signals (3/7) were on a name IBKR would not let the
account open.** One session is not a rate, but if it holds, IBKR cannot host this
strategy and the broker question becomes primary. `watchlist_blocked.txt` now
accumulates the evidence.

Blocking works: JLHL was commented out of `watchlist.txt` with the reason, and no
further signals were wasted on it.

## Finding 3 — slippage vs the backtest assumption, first real numbers

| Trade | ref_close | fill | slippage |
|---|---|---|---|
| UPC buy | 5.09 | 5.02 | **+0.07** (better) |
| UPC sell | 4.99 | 5.02 | **+0.03** (better) |
| PPBT buy | 2.6485 | 2.72 | **−0.0715** (worse) |
| PPBT sell | 2.72 | 2.75 | **+0.03** (better) |

Mean ≈ **+$0.0146/share**, i.e. slightly *better* than the bar-close assumption.
n=4 — not a result, but it does not yet support the fear that pre-market friction
destroys the edge.

**Spreads were tight:** 0.26%–1.57%, mostly ~0.4%. Fill times 0.51–3.81s. **No
no-fills at all.** The 60-second bar-close lag cut both ways: UPC drifted down
after the signal bar (helping the buy), PPBT ran up 2.3% (hurting it).

**Caveat that limits all of this:** the PPBT sell was limit 2.66 with a recorded
bid of 2.67 and **filled at 2.75** — above the ask. On a name doing 2.5M
shares/minute the book can move that far in 1.79s, but IB's paper fill engine may
also be more generous than a live venue. Paper slippage should be treated as a
floor on realism, not a measurement.

## Finding 4 — the IB scanner CAN express the whole screen

`scan_params.py` output: **495 scan codes, 1153 filter tags.**

I predicted float filtering almost certainly would not exist. **It does:**

- `floatSharesAbove` / `floatSharesBelow` — the float < 20m criterion
- `changePercAbove` / `changePercBelow` — the gainer criterion
- `avgVolumeAbove`, `avgUsdVolumeAbove` — volume
- `marketCapAbove1e6` / `marketCapBelow1e6`
- Scan codes: `TOP_PERC_GAIN`, `TOP_OPEN_PERC_GAIN`, `HIGH_OPEN_GAP`,
  `HOT_BY_VOLUME`, `MOST_ACTIVE`

So the scanner can run the full screen unattended, not merely narrow the field.
**Still open:** there is no explicitly pre-market scan code (only
`TOP_AFTER_HOURS_PERC_GAIN` for the other side), so whether `TOP_PERC_GAIN`
computes during pre-market is unresolved. `mcl_scanner.py --preview` answers it in
one run.

## Bugs found and fixed during the session

1. **Tick size ignored** — limit 5.3206 on a $5 stock, IB error 110. Round to a
   legal tick, direction-aware.
2. **`minTick` trusted over SEC Rule 612** — PPBT reports `minTick` 0.0001 but
   trades above $1, where $0.01 applies. Now takes the coarser of the two. Caught
   by Ben reading the log line, before it cost a trade.
3. **Rejection reason lost** — real message arrives on `ib.errorEvent`, not
   `trade.log`; previously logged only `"Inactive"`.
4. **Ineligible names retried forever** — now probed at subscribe time with a
   `whatIf` order and blocked on rejection.
5. **`whatIf` probe burned 10s per symbol** — `Trade` has no `orderState`
   attribute, so success was undetectable. Uses `whatIfOrderAsync`, <1s.
6. **Trailing-stop peak seeded pre-entry** — Finding 1.
7. **Encoding** — em dash mangled in `watchlist_blocked.txt`; ASCII + explicit
   utf-8.

## What the next session must answer

- [ ] **Re-run with the peak fix.** Every hold time in this session is invalid;
      PPBT's 8-second trade tells us nothing about the exit logic.
- [ ] **Blocked-name rate.** 3/7 signals here. Two or three more sessions decide
      whether IBKR is viable at all.
- [ ] **`mcl_scanner.py --preview`** — does `TOP_PERC_GAIN` return anything
      pre-market? If yes, selection becomes automatic and unbiased.
- [ ] **The entry-condition review Ben asked for** — see below.

## Entry conditions: the JLHL diagnosis

Separately analysed on JLHL 04:00–06:30 (131 bars, zero entries):

| Condition | Held |
|---|---|
| MACD > signal & > 0 | 39.7% |
| MFI rising | 49.6% |
| RSI rising | 48.9% |
| Floor | 52.7% |
| **Volume ≥ 3× previous** | **7.6%** |

**The volume rule and the trend conditions are structurally anti-correlated.** A 3×
jump requires the *previous* bar to be small, so it only fires on the ignition bar
of a burst — but MACD lags and confirms several bars later, by which time the
ratio has collapsed to ~1×. Twelve bars had everything *except* the volume rule;
their ratios ranged 0.29×–2.67×.

At 06:18 volume fired at **6.78×** while MACD and the floor were false. By 06:22
MACD/MFI/RSI/floor were all true and volume was **0.59×**.

**Proposed fix:** decouple ignition from confirmation. A 3× burst *arms* the setup
for N bars; entry fires when MACD/MFI/RSI confirm within that window. On JLHL that
arms at 06:18 and enters ~06:22 near 7.25.

**Must be validated across all 21 backtest names before adoption** — otherwise it
is curve-fitting to one name on one day.
