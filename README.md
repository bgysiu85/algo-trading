# Algo Trading

Pre-market US small-cap momentum strategies, with paper execution against
Interactive Brokers and TradeZero.

Session window is 04:00-09:30 ET throughout. Every strategy is flat by the
open.

## Strategies

| | timeframe | entry | exit | status |
|---|---|---|---|---|
| **MCL / V7** | 1-minute | MACD > signal and > 0, MFI and RSI rising, volume >= 3x prior bar, prior bar >= 50% of the 60-bar average | apex reversal on any of MACD/MFI/RSI, 5% trailing stop, or window close | live paper-tested |
| **MC5** | 5-minute | RSI rate of change >= +5% over 3 bars, EMA9 > EMA21, MACD > signal | RSI and MACD gradients both negative, 5% trailing stop, or window close | tested, **not yet run on real data** |

Strategy modules are pure: indicators and signals only, no broker, no I/O. That
is what lets the same code run in the live trader and in the offline backtest.

## Layout (flat -- a reorganisation is planned)

**Strategy** `mcl_strategy.py`, `mc5_strategy.py`

**Execution** `mcl_paper_trader.py` (IBKR), `tz_check.py` (TradeZero probe)

**Backtest** `mcl_backtest.py`, `build_pairs.py`

**Data** `db_check.py`, `db_bars.py` (Databento), `mcl_scanner.py`,
`scan_params.py`

**Support** `secrets_util.py`, `op_list.py`, `report_trades.py`

**Runners** `run_paper.ps1`, `run_dry.ps1`, `run_backtest_after_session.ps1`,
`show_trades.ps1`

## Safety properties worth preserving

These are load-bearing. Removing one does not fail loudly.

- **IBKR is port-gated.** 4002/7497 are paper and accepted; 4001/7496 are live
  and refused by name. Every account id must also begin with `DU`.
- **TradeZero is key-gated, and cannot be port-gated.** One base URL serves both
  live and paper, and the key pair alone selects the environment. `tz_check.py`
  refuses to place anything until every account reports
  `accountType == "Paper"`.
- **Credentials resolve once, at startup.** A lazy re-resolve can block a live
  session on a 1Password unlock prompt with a position open. `secrets_util.get()`
  raises rather than fetching on demand.
- **The backtest will not start while the trader is running.** IBKR's
  ~60-requests-per-10-minutes cap is account-wide, and IB signals throttling by
  returning empty lists rather than errors, so a collision is silent on both
  sides.
- **The trailing stop lives in the script, not at the broker.** If the process
  dies with a position open, that position is unprotected.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\pip install ib_async pandas databento

setx OP_SERVICE_ACCOUNT_TOKEN "ops_..."
setx DATABENTO_API_KEY  "op://Trading/<item>/<field>"
setx TZ_API_KEY_ID      "op://Trading/<item>/<field>"
setx TZ_API_SECRET_KEY  "op://Trading/<item>/<field>"
```

Open a new terminal afterwards -- `setx` does not affect the current one. Run
`python op_list.py --vault Trading` to get the exact references instead of
guessing item and field names.

Secrets are never stored in this repository. Values come from environment
variables, which may hold either the literal secret or an `op://` 1Password
reference resolved at run time.

## Running

```powershell
.\run_dry.ps1                       # no orders placed
.\run_paper.ps1                     # places orders on the IBKR PAPER account
.\run_backtest_after_session.ps1    # waits for the session to end, then backtests
```

## Tests

```powershell
.\.venv\Scripts\python.exe test_mc5_strategy.py
.\.venv\Scripts\python.exe test_backtest_engine.py
.\.venv\Scripts\python.exe test_live_paths.py
.\.venv\Scripts\python.exe test_pacing_and_trail.py
.\.venv\Scripts\python.exe test_dryrun_roundtrip.py
```
