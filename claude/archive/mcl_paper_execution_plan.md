# MCL paper execution — plan & status

Created 2026-09-01. Updated 2026-09-02. Decision on 1 Sep: **skip live paper testing that
day, build the execution layer properly instead.** Rationale below.

## Why not 1 Sep

- The request came at **07:04 ET**. Pre-market opened at 04:00, leaving 2h25m.
- Worse, the window that carried the edge in the backtest is **04:00–06:30**, which had
  already passed. See `claude/momentum_confluence_session_window_test.md`: restricting to
  06:30–09:30 took the strategy from +$924 to +$66.
- Nothing existed that could place an order. Pine cannot.

## Safety finding

The IBKR account currently connected to Claude is Ben's **LIVE** account
(net liquidation ~$4,131.89, flat, no margin). It was confirmed live and is off-limits.
No order has been or will be placed through it.

The execution script therefore carries two independent guards:

1. **Port allowlist** — only 7497 (TWS paper) and 4002 (Gateway paper). 7496 / 4001 are
   rejected by name before any connection work.
2. **Account-id check** — aborts unless every `managedAccounts()` id starts with `DU`
   (IBKR's paper prefix).

**Both verified working on 2 Sep**: the script connected via IB Gateway on port 4002 to a
`DU` account with **$22,290.96** net liquidation.

## What was built

`mcl_paper_trader.py` — mirrors the V7 Pine strategy against IBKR paper using
**marketable limit orders**, the only order type IBKR accepts for US stocks outside RTH.

- Indicators reimplemented in Python to Pine's definitions: `ta.ema`, `ta.rma`-based RSI,
  `ta.mfi(hlc3)`, `value > value[3]` gradients, apex = falling AND the 20-bar high is at
  least one bar behind.
- **Verified against independent loop implementations**: RSI, MFI and MACD all agree to
  <3e-14; apex logic confirmed False while rising and True after a peak; the 3-bar
  gradient lookback confirmed.
- Software-side trailing stop — IBKR's native trailing stop fires a *market* order, which
  is rejected pre-market, so the peak is tracked in the script and breached with a
  marketable limit.
- `watchlist.txt` is **hot-reloaded every 5 seconds**. Adding a ticker mid-session
  subscribes it within ~5s; removing one stops new entries but keeps managing any open
  position through to its exit.
- Every signal writes a row: live bid/ask/spread at signal time, the limit sent, the fill
  or no-fill, `slippage_vs_ref` against what the backtest assumed, and time-to-fill.
  SELL rows additionally carry the completed round trip: `entry_price`, `exit_price`,
  `trade_pnl`, `trade_pct`, `hold_minutes`.

`report_trades.py` / `show_trades.ps1` — **read-only account viewer**. IB Gateway has no
order or trade UI, and IBKR blocks a second Client Portal / TWS / IBKR Desktop session on
the same username. The API accepts multiple simultaneous clients on one Gateway, so this
connects on client id 77 and prints balances, positions, open orders and today's
executions. Places nothing; safe to run alongside the trader.

> IB only shows a client the orders and executions *it* placed. To see the trader's fills
> here, set **Master API client ID = 77** in Gateway → Configure → Settings → API →
> Settings and restart Gateway. Balances and positions are account-wide and always visible.

`run_dry.ps1` — creates the venv, installs deps, and launches the trader in dry-run mode.
`MCL_PAPER_RUNBOOK.md` — setup, daily workflow, safety, and how to read the fill log.

## What a dry run does and does not prove

Dry run simulates the **full round trip**: it opens a virtual position at the
marketable-limit price and runs the trailing stop and apex exit against live quotes, so a
session produces trades and a net P/L, not just a list of signals.

- **Proves:** that signals fire where expected; how they compare to TradingView; what
  crossing the real spread costs (fills are priced off the actual bid/ask + 20bps, so
  `slippage_vs_ref` is a genuine measurement).
- **Cannot prove:** that the size was there. A simulated fill assumes a resting
  counterparty at the touch — precisely the assumption in doubt pre-market on a thin $3
  name. Read dry-run P/L as **the best case**: the strategy where every order fills. Bad
  there means bad. Good there is still unproven.

The gap between dry-run P/L and live paper P/L **is** the fill risk, quantified. That is
the whole reason session 3 onward places real paper orders.

## The verification that matters

**IB's 1-minute bars are not TradingView's.** Different exchange inclusion and
consolidation, so the Python signals will not be identical to the Pine signals. The size
of that gap is itself a finding.

First dry run must be reconciled: compare the CSV's `entry_signal` rows against the
chart's buy/sell markers for the same ticker and session.

## Three questions the fill log answers

1. **Average `slippage_vs_ref`.** Against V7's +$924 over 50 trades, anything worse than
   about **−$18 per trade** erases the entire edge.
2. **No-fill rate.** Every `NO_FILL_CANCELLED` is a backtest trade that would not have
   existed. If the winners are disproportionately the ones that don't fill, the edge is
   an artifact.
3. **Typical spread.** On a $3 stock a 3-cent spread is 1% — a fifth of the whole 5%
   trailing stop.

## Position sizing — resolved, no funding needed

Earlier advice said to fund the paper account to $100k so sizing matched the backtest.
**That was based on the $4.1k live balance and is wrong for the paper account.**

Paper equity is **$22,290.96**. The rule is `min(100 shares, 40% of equity / price)`:

- 40% of $22,290.96 = **$8,916**
- $8,916 / 100 shares = **$89.16/share**

The equity cap only reduces size above $89.16/share. The universe is **$2–20**, so every
trade is a full 100 shares — **identical to the backtest**. No funding required.

## Open items before the next session

- [x] ~~Fund the paper account to $100k~~ — unnecessary, see above.
- [x] Confirm Gateway paper port and API access — **done, port 4002, DU account**.
- [ ] Build `watchlist.txt` from the scanner before 04:00 ET.
- [ ] Run `--dry-run` for a full session; send back the CSV for reconciliation.
- [ ] Optionally set Master API client ID = 77 in Gateway so `show_trades` sees fills.

## Sequence

| When | What |
|---|---|
| Session 1 | `--dry-run` only. Reconcile signals against TradingView. |
| Session 2 | Repeat dry run if session 1 showed mismatches worth chasing. |
| Session 3+ | Live paper orders. Collect 3–5 sessions of fill data. |
| Then | Re-run the backtest substituting measured slippage and no-fill rate for the 1-tick assumption. **That is the first honest estimate of the edge.** |

## Bugs found and fixed

- **Dry run was entry-only.** `marketable_limit()` returned `None` in dry mode, and the
  entry path only opened a position `if res:`. So no virtual position was ever held —
  which meant the exit logic and trailing stop never ran, no round trip was ever
  recorded, and (because nothing suppressed re-entry) an entry signal would have been
  logged on *every* qualifying bar rather than once per trade. A dry-run session would
  have produced an inflated list of entries and no P/L at all. Found on 2 Sep about 40
  minutes before the session, by reading the code rather than assuming. Fixed: dry mode
  now returns a synthetic fill at the limit price and runs the complete state machine.
  Covered by `test_dryrun_roundtrip.py`, which asserts entries are matched by exits and
  that `trade_pnl` is arithmetically correct.
- **Logging format crash.** `LOG.info("account equity: $%,.2f", ...)` — Python's
  `%`-style logging has no comma flag, raising `ValueError: unsupported format character
  ','`. Cosmetic (the logging module swallows formatting errors) but it masked the equity
  readout. Replaced with an f-string.

## Still unaddressed

Selection bias. Every backtest so far uses 21 names chosen *because they ran*. Only
forward testing on contemporaneous scanner picks fixes that, and this pipeline is the
prerequisite for it.
