# Handover: TSMOM (time-series momentum on micro futures), new chat

From: the ORB chat, 2026-09-17 (Sydney). To: a new chat that owns TSMOM from its first line.
Nothing has been built, pulled or measured for TSMOM in this project. This document is where it starts.

**Read first, in this order:**
1. `claude/PROGRAM_INDEX.md` §1 (hard rules), §4 (standards of evidence) and §2 (roster: TSMOM row).
2. `claude/diversifier_candidates_20260911.md` §4 (the ReSolve/GEM robustness lesson) and §5.1 (TSMOM).
3. `claude/orb_pit_RESULT_20260917.md`: how the last strategy was registered, run and closed. Copy the method, not the strategy.

---

## 1. Why TSMOM, and why now

Every intraday strategy on the small-cap screener universe loses on point-in-time data, before or after friction. That covers MCL, MC5, VW9, H0, six MCL-PB versions, the B-series entry gates and, on 2026-09-17, ORB (−$4.58 / −$5.01 per trade on the two PIT universes). The problem is the universe and the trade type, not a parameter.

TSMOM is the index's **best-evidenced unbuilt candidate**:
- **Source:** Moskowitz, Ooi & Pedersen, *Journal of Financial Economics* 2012 (<https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf>). Peer-reviewed and heavily replicated.
- **Mechanics:** long/short trend across bonds, FX, commodities and equity indices. Monthly rebalance, 12-month lookback, positions scaled by volatility.
- **Diversification:** no exposure to US small-cap order flow. It has documented "crisis alpha", paying during sustained equity drawdowns.
- **Costs:** monthly rebalance on liquid futures, so friction is small by construction. That is the opposite of what killed everything else here.
- **Margin fit:** futures initial margin only, roughly USD 10–20k for a micro book at a 10% volatility target. The AUD 50,000 retail margin-lending cap does not bind. The paper account `DUM215828` is about $22k net liquidation.

**ORB runs in parallel in the ORB chat** (liquid "stocks in play", 5-minute range, relative-volume ranking). The two do not share code or data. Do not touch `strategy/orb/`.

---

## 2. What the new chat has to settle before any code

### 2.1 The strategy, written down from the paper and not from memory
- **Signal:** sign of the trailing 12-month excess return per contract. Check the paper for exactly how the excess over the risk-free rate is formed with futures.
- **Sizing:** position = target vol ÷ ex-ante vol. Get the paper's vol estimator exactly: its EWMA centre of mass and the annualisation.
- **Rebalance:** monthly, and on which day. **Rebalance-date luck** (`diversifier_candidates` §4: often >100 bp/yr for concentrated books) means registering either tranching (4–5 sleeves on staggered days) or a reported grid over rebalance days.
- **Instrument set:** candidates from §5.1 are MES, M2K, MGC, micro crude, ZN, 6E. Pick 8–12 with enough history, and state the rule for choosing them *before* seeing returns.
- **Name collision:** "MCL" in the diversifier doc means the **micro crude oil future**, not the MCL strategy. Use `CL`/`micro crude` in TSMOM docs and code.

### 2.2 Data: price before buying (PROGRAM_INDEX §1)
- **Needed:** daily futures bars for each market, long enough to cover several regimes. At least 10–15 years if affordable. The paper used decades.
- **Source to price first:** Databento CME Globex (`GLBX.MDP3`) `ohlcv-1d`, with its definitions for roll dates and multipliers. The existing archive is equities only (XNAS/EQUS). **Micro contracts are recent** (most launched 2019+). Historical signals must come from the full-size contracts (ES, NQ, RTY, GC, CL, ZN, 6E), traded as micros later. Register that choice explicitly.
- **Continuous series:** build back-adjusted continuous series for signals with an explicit, registered roll rule. Compute P/L on the actual held contract, including roll cost. A continuous series that looks right while booking the wrong contract is this project's signature failure.
- `common/databento_fetch.py` refuses to spend without an estimate and `--confirm`. Use the same discipline. **The API key stays in the env var only.**
- **Hazard found 2026-09-17:** `databento_universe` month chunks that start mid-month overwrite the full month (`claude/archive_defect_daily_chunk_start_20260917.md`). Don't hit it on a new dataset.

### 2.3 Costs and capacity
- **Costs per contract:** IBKR futures commission plus exchange fees, one tick of slippage per side at the roll and the rebalance. State them in the registration, and report at more than one friction level.
- **Contract granularity:** at $22k, one micro contract can be a large fraction of the vol target for some markets. Measure how far integer rounding moves realised vol and turnover. It may make some markets untradeable at this size, and that is a finding, not a tuning knob.

### 2.4 The bar to clear, registered first
**Adapt §11 / the ORB registration's criteria to a monthly book:**
- Positive after costs.
- Both halves of the sample positive, split at the median date and not swept.
- Drop-top-N applied to markets rather than symbols.
- A cluster bootstrap by market or by year.
- A plain comparison against buy-and-hold of the same markets and against a cash-only benchmark.

**Additional requirements:**
- Report where the registered spec sits in the distribution of nearby specs (lookback 3/6/12 months, vol target). Prefer an equal-weight ensemble over any single chosen lookback.
- **Known risk to register up front:** trend-following had long weak stretches after 2012. The registration must say how a weak post-publication period is read, and it must not rest on one strong year. The QQQ-ORB replication found 76% of P/L in 2022, and that is the warning.
- **Holdout:** `var/state/holdout.json` covers the equity universe only and is not relevant here. If TSMOM wants an out-of-sample slice, cut one of its own **before** the first run and enforce it in code.

---

## 3. House rules that apply (short version; PROGRAM_INDEX §1 is authoritative)

- **Register before you run.** Amendments are marked PRE-RUN / POST-RUN. A threshold changed after seeing a result is a new hypothesis.
- **The IBKR account is read-only live. No orders, ever.** Paper only, and only after a backtest has passed everything.
- **One branch, `main`.** The repo is `D:\Trading`. Four chats now write to it: build/MCL, live analysis, ORB, TSMOM.
  - Either work directly in a clone of Ben's current tip, or cut bundles on a base that contains it.
  - Deliver bundles to `D:\Trading\Claude outputs`, prefixed `tsmom-YYYYMMDD[a-z].bundle`.
  - Suggested code home: `strategy/tsmom/`, tests in `tests/strategy/test_tsmom_*.py`.
- **Every text-mode open names `encoding="utf-8"`.** `tests/test_encoding_guard.py` refuses a bare one.
- **Every report names its data source** (dataset, schema, roll rule) and refuses the wrong one.
- **Mutation-test every guard before committing.** A check that cannot fail is removed.
- **Ben's working style:**
  - Windows PowerShell and not fluent in git, so give exact copy-paste commands, one per line, with real paths.
  - Tooling in Python, not PowerShell.
  - Results go to a `.txt` report **and** a published artifact page, with negatives in brackets and red.
- **Report progress to the project:** results docs go in `claude/tsmom_*.md` and registrations in `docs/research/REGISTERED_tsmom*.md`. The analysis chat indexes `PROGRAM_INDEX`, so send it the doc names.

---

## 4. Suggested first session

1. **Read the three docs above and the paper itself.** Write `claude/tsmom_spec_YYYYMMDD.md` from the paper: signal, vol estimator, sizing, rebalance, instruments, roll rule and costs, each sourced to a page or table.
2. **Price the data** with a dry-run estimate only. No spending without Ben confirming the number.
3. **Write the registration** (`docs/research/REGISTERED_tsmom.md`) and commit it before any backtest code runs.
4. **Build the engine with hand-built tests:** roll handling, vol scaling and integer contracts. Then pull the data and run.
