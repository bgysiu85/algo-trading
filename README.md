# Algo Trading

Pre-market US small-cap momentum strategies, with paper execution against
Interactive Brokers and TradeZero.

MCL and MC5 trade the 04:00-09:30 ET window and are flat by the open. The
EMA-crossover family (E15, VW9) trades the full 04:00-20:00 session and is at
the measurement stage.

## Strategies

| | timeframe | entry | exit | status |
|---|---|---|---|---|
| **MCL / V7** | 1-minute | MACD > signal and > 0, MFI and RSI rising, volume >= 3x prior bar, prior bar >= 50% of the 60-bar average | 5% trailing stop or window close. The apex-reversal exit was **removed 2026-09-05** -- it was net negative | live paper-tested |
| **MC5** | 5-minute | RSI rate of change >= +5% over 3 bars, EMA9 > EMA21, MACD > signal | RSI and MACD gradients both negative, 5% trailing stop, or window close | tested, **not yet run on real data** |
| **VW9** | 5/15-minute | VWAP reclaim or 9 EMA retest, confirmed on a candle close | structural stop, VWAP lost, or the exit mode's target | backtested 2026-09-05, **rejected** -- profit is two names and lives entirely pre-market |

Strategy modules are pure: indicators and signals, no broker and no I/O. That
is what lets the same code run in the live trader and in the offline backtest.
`strategy/mcl/mcl.py` is the reference for the shape a strategy must implement.

## Layout

```
main.py                 every mode: --mode paper|dry|backtest|scan|report|probe-window
run.ps1                 generic launcher; the run_*.ps1 scripts are the everyday ones

common/                 shared, broker-agnostic
  indicators.py           ema/rma/macd/rsi/mfi/atr/vwap/slopes -- ONE implementation
  backtest.py             the engine; --strategy dispatches to strategy/<name>
  data_ib.py              full-session bar puller for the EMA family
  cache_io.py             bar-cache layout and session slicing
  session_lock.py         the live-session guard
  sweep_variants.py       offline strategy-variant comparison over cached bars
  probe_window.py         validates the shared cache window against live IB
  commissions.py          real IBKR Fixed/Tiered and TradeZero schedules
  friction.py             per-exit-reason slippage from the live fill logs
  secrets_util.py  op_list.py  build_pairs.py  report_trades.py
  db_check.py  db_bars.py       Databento

  studies -- each is a `python -m` entry point that answers ONE question and
  prints its own evidence. They are kept because the answer is only as good as
  the test that produced it:
  trail_study.py          should TRAIL_PCT move?            (no)
  scale_grid.py           4,900-cell scale-out grid + an equivalence check
  scale_regimes.py        scale-out with size held constant vs growing
  scale_verdict.py        scale-out, bootstrapped and held out   (reject)
  scale_report.py         reads a scale_grid CSV: boundary, holdout, decomposition
  pyramid_study.py        add-on-a-recovered-dip vs simply starting bigger
  pyramid_verdict.py      the same, bootstrapped and held out    (reject)

brokers/
  ibkr/                   trader.py, scanner.py, scan_params.py
  tradezero/              client.py

strategy/
  mcl/mcl.py              the live strategy
  mc5/mc5.py
  vw9/                    vw9.py (logic), backtest.py (engine), preflight.py,
                          study.py, setup_counts.py, vw9_5m.py, vw9_15m.py

tests/                  mirrors the source tree
docs/                   MCL_PAPER_RUNBOOK.md, ema_crossover.md
bar_cache/              gitignored; one shared window, 3d_to_2000/
var/                    gitignored runtime: fills/ state/ logs/ reports/ archive/
```

Everything is a package, so modules run as `python -m common.backtest`, not by
path -- `python common\backtest.py` puts `common/` on `sys.path` instead of the
repo root and cannot resolve `strategy.mcl`. `main.py` handles this for you.

## Safety properties worth preserving

These are load-bearing. Removing one does not fail loudly.

- **IBKR is port-gated.** 4002/7497 are paper and accepted; 4001/7496 are live
  and refused by name. Every account id must also begin with `DU`.
- **TradeZero is key-gated, and cannot be port-gated.** One base URL serves both
  live and paper, and the key pair alone selects the environment.
  `brokers/tradezero/client.py` refuses to place anything until every account
  reports `accountType == "Paper"`.
- **Credentials resolve once, at startup.** A lazy re-resolve can block a live
  session on a 1Password unlock prompt with a position open.
  `common/secrets_util.get()` raises rather than fetching on demand.
- **The backtest will not start while a session is live.** `main.py` holds
  `var/state/session.lock` for `--mode paper|dry`, and the backtest refuses
  while it is held. IBKR's ~60-requests-per-10-minutes cap is account-wide, and
  IB signals throttling by returning empty lists rather than errors, so a
  collision is silent on both sides. A lock whose process is gone, or older than
  24h, is treated as stale and cleared -- a guard that never released would be
  worse than none.
- **Cached bars are sliced to the window each consumer asked for.** One shared
  superset is fetched to halve the IB budget, but a longer frame changes
  EMA-seeded indicators on identical bars, so nothing consumes it whole. A
  frame that does not reach back far enough is refused rather than used.
- **The trailing stop lives in the script, not at the broker.** If the process
  dies with a position open, that position is unprotected.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

setx OP_SERVICE_ACCOUNT_TOKEN "ops_..."
setx DATABENTO_API_KEY  "op://Trading/<item>/<field>"
setx TZ_API_KEY_ID      "op://Trading/<item>/<field>"
setx TZ_API_SECRET_KEY  "op://Trading/<item>/<field>"
```

Open a new terminal afterwards -- `setx` does not affect the current one.
`python -m common.op_list --vault Trading` prints the exact references rather
than guessing item and field names.

Two 1Password traps, both hit in practice:

- `OP_SERVICE_ACCOUNT_TOKEN` must hold the **literal** `ops_...` token, not an
  `op://` reference. A reference there cannot resolve itself -- expanding one
  requires an authenticated `op`, and that variable is what authenticates it.
  The symptom is `failed to parseToken, format is invalid` on every `op`
  command, including ones unrelated to trading.
- A service account **cannot read the Private, Personal, Employee or default
  Shared vaults**. Anything it must resolve belongs in a purpose-made vault.

Secrets are never stored in this repository. Values come from environment
variables holding either the literal secret or an `op://` reference resolved at
run time.

## Running

```powershell
.\run_dry.ps1                       # no orders placed
.\run_paper.ps1                     # places orders on the IBKR PAPER account
.\run_backtest_after_session.ps1    # waits for the session to end, then backtests
.\show_trades.ps1                   # read-only account viewer

.\.venv\Scripts\python.exe main.py --mode backtest --strategy mc5
.\run.ps1 -Mode backtest -Strategy mc5 -Extra "--limit 10"
```

## Tests

```powershell
.\run_tests.ps1
```

Two conventions are in play, which is why that script exists rather than a bare
`pytest`: a few suites are standalone scripts with their own `main()` and
PASS/FAIL output and run as modules; the rest are pytest, collected from the
whole `tests/` tree. Neither runner alone covers everything.

Point pytest at `tests`, never at a hand-listed set of subdirectories. This
script named two of them for a while, so suites added elsewhere were skipped
silently while it still reported ALL SUITES PASSED.

Detailed findings live in the Claude project (`PROGRAM_INDEX.md` first), not
in this repo.
