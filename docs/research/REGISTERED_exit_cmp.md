# REGISTERED — EXIT-CMP: which exit rule set should the hybrid exit manager run by default? (W15-0053 sub 1)

**Committed before any exit-comparison code exists and before any exit price or P&L of any rule set below has been computed.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run. Board: **W15-0053** (item 2871535081), sub 1 (subitem 2871551157). Written 2026-10-18 by the Research & spec chat.

Amendments are marked **PRE-RUN** (before the outcome run of §9) or **POST-RUN**. A rule, threshold or coding changed after an outcome has been read is a new hypothesis.

---

## 0. In plain terms

Ben wants to place futures trades himself in any IBKR app and have a Python process take over the moment the order fills: put a protective stop at IBKR within about a second, then manage the exit by a rule. This document does two things.

**Part A (the registration, §1–§12)** says how the candidate exit rules will be compared *before* anyone looks at a result. The rules are Ben's trail with the ~$2,000 ratchet, momentum-loss exits (three red bars with MACD negative; the shooting-star body stop), and Tori's two exit habits from the Shorts sweep (X-ALERT, exit when the trend-line alert fires; X-JUMP, jump the stop into profit at about 1R). They are all run on the same entries: the 2,670 historical CL 1H long fills of CHARTMARK-v1 (the W15-0050 candidates), 2010-06 → 2021-12, priced at IBKR costs. Only the exit changes, so the comparison is trade-by-trade.

**This is not a test of whether Ben's entries make money.** Those 2,670 entries lose money under the v1 exits (net ($13,422)), and the clone study that tried to pick better ones failed. They are a fixed set of realistic entries to test exits on. The question is narrower: does any rule do better than the dumb baseline of "a stop at IBKR plus flat at 17:00", by more than random exit timing would, in more than one year and after costs? If none does, the manager ships with the stop-plus-flat default and the rules stay as logged options in the paper trial.

**Part B (the spec, §13–§17)** is the design of the manager: the per-symbol table for any futures fill, the cost model, the flat-before-close option and the safety rails. It is a specification, not a hypothesis; the rails are tested in sub 4 and in the paper trial (sub 5), not by this backtest.

---

## 1. Where this comes from

- **Ben, 2026-10-01:** *"we can also develop a trading system where i would place the trade and you can manage the exit... that would take away half the work for me."* Exit rule set selectable per trade; the trade log compares them; backtest the exit sets on the W15-0050 CL 1H candidates **before** building.
- **Ben, 2026-10-18 (multiple-choice picks):** Order *"Backtest exits first"*; Markets *"Any futures fill"* (per-symbol tick size / tick value / size cap from a symbol table); Entry *"Any IBKR app"* (the portal ticket, sub 7, is v2); Host *"Your PC for paper"*.
- **Ben, 2026-10-04 (W15-0058):** *"B · Exits to W15-0053 (Recommended)"* — X-ALERT (touch / close) and X-JUMP added to this comparison.
- **Ben's trail and ratchet, in his words** (HTF-Ben v0 §2.3 S2, 2026-09-25): *"once it is approximately $2000 in the green… move the stop loss to mid point… always protecting at least 50% of profit"*, confirmed as a *"$0.20/bbl price move"*. (That is $2,000 on 10 CL: 10 × 1,000 bbl × $0.20.)
- **Ben's momentum-loss exits** (CHARTMARK-v1 draft, 2026-09-29): *"exited around $63.70… as the previous 3 bars were red and MACD was negative already"* and *"exited earlier at $63.43… as the 8:00 candle formed a shooting star"*.

## 2. What this is and is not

- A comparison of **exit** rules on a **fixed** entry set. Entries, initial stops, sizes and the data are identical across rule sets; only what happens after the fill differs.
- Not a strategy test. No rule here may be quoted as an "edge", and **no holdout is spent** (§11).
- The entry set is a losing one. A rule that "wins" mostly by cutting losers faster than the baseline is a finding about exits, and is reported as such.
- Long only. The manager must also handle shorts, which are the mirror image; shorts are **not** backtested here (CHARTMARK has no short entries on this set) and are paper-trial territory.

---

## 3. Hypotheses

- **H-EX (primary).** At least one of the candidate rule sets (R-BEN, R-MOM, X-ALERT-touch, X-ALERT-close, X-JUMP) beats the baseline B-STOP on paired per-trade net, after IBKR costs, on the same 2,670 entries, and beats random exit timing at its own holding times.
- **H-LOG (reported, no criterion).** Each rule set reduces the give-back (trades that reached +$0.20 and closed at or below zero) and the size of the worst losing run, even where net does not improve. Ben's stated goal is to *"take away half the work"* and to protect profit, so risk reduction is a legitimate reason to choose a rule; it is reported, not graded.

---

## 4. The entry set (fixed; the "W15-0050 CL 1H candidates")

- **2,670 CHARTMARK-v1 base long fills**, training window 2010-06-06 → 2021-12-31, as produced by `strategy/chartmark` at the commit recorded in `REGISTERED_chartmark_clone.md` §3.1. Per entry year: 2010 132 · 2011 230 · 2012 240 · 2013 226 · 2014 219 · 2015 223 · 2016 217 · 2017 236 · 2018 220 · 2019 246 · 2020 231 · 2021 250.
- For every fill the runner takes **entry bar index, entry price (gap fills at the open, as v1 recorded), A₀ (ATR(14) at the close of the bar before the fill, v1 I1) and the initial stop S** (lowest low of the 5 bars ending at the entry bar − 1 tick, live from the bar after the entry bar, v1 §2.3 and I8) **by re-running the v1 entry machine** (`strategy.chartmark.engine.simulate`'s order logic), not by reading the exit, gross, cost or net columns of the trades CSV. The CSV is opened once, for the parity check G2, after the rule sets are frozen.
- **Independent trades.** Each fill is walked on its own to its exit under each rule set (overlap with another fill's holding period is allowed and counted, as C3 in `REGISTERED_chartmark_v1.md` I10). The entry set is therefore identical across rule sets and the comparison is **paired**.
- **Size and costs:** 1 MCL headline, 1 CL reported. Costs below (§8).
- **Slice reported, not graded:** Ben's 155 takes among the 500 blind-labelled candidates of W15-0050 (first labels; the label file is read for candidate ids only). 155 trades is too few to grade; it answers "do the exits behave differently on the entries Ben picked?".
- **Windows reported separately, not excluded:** 2014-07-01 → 2015-01-31 and 2020-02-01 → 2020-06-30 (as W15-0050 V-NOFAMOUS).

## 5. Common mechanics (all rule sets)

- Bars: 1H, difference-back-adjusted, the v1 frame (`strategy.chartmark.data`: `Frame`, `load_training_frame`), roll handling as v1 I6. Times New York. Tick 0.01.
- **Orders working for bar j are fixed from data ≤ bar j−1** (v1 §2.4 clarification). Within a bar, **every sell-stop is tested before any ratchet or trail raised by that bar's high** (the conservative order, HTF-Ben S3). A sell-stop level at or above the bar's open fills at the open; otherwise at the level (v1 I4).
- A **market exit decided at the close of bar j** fills at the **open of bar j+1** (the live manager acts on the bar-close event about a second late, so the next open is the nearest honest price).
- Indicators as v1 (`strategy.chartmark.data.Ind` / `indicators`): EMA9, EMA21, MACD(12,26,9) with SMA seeding, ATR(14) Wilder. A rule that needs an indicator which does not yet exist does not fire.
- **Scenarios**, every rule set run in both:
  - **FLAT (primary):** flat at the close of the last 1H bar of the session (the bar opening 16:00 NY, i.e. 17:00), at that close, whatever else is open. Entries are 02:00–12:00 (v1 X3), so every trade has at least 5 hours.
  - **HOLD (reported; also the parity scenario):** carried overnight and over weekends, gaps filling at the open, with a time cap of **120 1H bars** after the entry bar, exited at that bar's close.
- **Roll:** an open position carried through a roll pays two extra sides (v1 I6). Only HOLD can roll.

---

## 6. The rule sets (long shown; short is the mirror, not backtested)

All rule sets keep S (§4) as a resting floor that is never loosened, in addition to what is listed.

| ID | Role | Rule |
|---|---|---|
| **B-STOP** | **Baseline, the thing to beat** | S only, plus the scenario's flat / time cap. This is what an unmanaged server-side stop plus the 17:00 flat does. |
| **B-V1** | Parity reference (HOLD only, not scored) | CHARTMARK-v1 base exits unchanged (S, P1 EMA9 trail ≥ 1.0 A₀, P2 EMA21 trail ≥ 2.0 A₀, R reversal-candle). Must reproduce the 2,670 recorded trades (G2). |
| **R-BEN** | Ben's trail + ratchet | **Arm:** once the highest high since entry ≥ entry + **$0.20** (the "~$2,000" on 10 CL; a price distance, so it scales with the instrument, §13 table). **Then** stop = max(current stop, entry + (highest high − entry) ÷ 2), recomputed whenever a new highest high is made, evaluated at each bar close and effective from the next bar. Never loosens. No target. (HTF-Ben v0 S2.) |
| **R-MOM** | Momentum-loss exits | **M1:** at the close of any bar after the entry bar where the last **3** closes are each below their own open **and** MACD histogram < 0 → market sell at the next open. **M2:** v1 §2.5 reversal-candle exit unchanged (upper wick ≥ 50% of range and range ≥ 0.3 A₀ → sell-stop at that bar's body low − 1 tick, live for 3 bars). First of S, M1, M2. No profit-protecting trail. |
| **X-ALERT-touch** | Tori: exit when the trend-line alert fires, first touch | The **active rising support line** (below). Alert level for bar j = the line's value projected to bar j, from pivots confirmed ≤ j−1, eligible only while that level is below close[j−1]. Exit = market at the alert: modelled as a sell-stop at the level (gap through → open). S stays as the backstop only (Tori: *"the resting stop sits further away, only for when she is away"*). |
| **X-ALERT-close** | Same, on a bar close | Same line and eligibility; fires when **close[j] < line[j] − 0.10 × ATR**; market sell at the next open. (She does not say which of touch / close her alert is; both are coded, W15-0058.) |
| **X-JUMP** | Tori: jump into profit at about 1R | R₀ = entry − S. **Arm** when the highest high since entry ≥ entry + **1.0 R₀**. After arming, take each **confirmed 1H swing low** (a bar whose low is below the lows of the **2** bars either side, confirmed at the close of the 2nd bar after it; only swing lows formed after the arming bar). Stop = max(current stop, swing low − 1 tick), **only if that level is above the entry price** (straight into profit, no breakeven step); a swing low at or below entry is skipped and the next one is tried. Re-trails under each later, higher confirmed swing low. Never loosens. |

**The active rising support line (X-ALERT).** Built by `common/tl_v0_lines.py` unchanged — pivot lows, L = R = 5, break buffer 0.10 × ATR(14), the module's validity / span guard and its walk-and-break state machine — run on the 1H series. A line is *active* from the confirmation of its second pivot until its first break; it is the most recent unbroken rising support line. No line active → X-ALERT behaves exactly as B-STOP for that trade. If sub 2 finds the module cannot return a per-bar projected line value without modification, it stops and reports (no edits to the frozen module).

**Reported variants (fixed now, never ranked, cannot become the headline):**

| Variant | Change |
|---|---|
| R-BEN-EMA | R-BEN plus v1's EMA9 / EMA21 trail (P1 / P2); stop = max of all. (If "my trail" means the EMA trail rather than the swing stop, this is it.) |
| R-MOM+BEN | R-MOM plus the R-BEN ratchet (the likely real configuration: momentum-loss exit with a profit floor). |
| X-JUMP-1R-half | X-JUMP followed by the R-BEN half-profit ratchet once armed. |

**Neighbour grids (9 cells each, unranked; criterion 8):**

| Rule set | Dimension 1 | Dimension 2 |
|---|---|---|
| R-BEN | arm $ {0.10, **0.20**, 0.30} | ratchet fraction {0.40, **0.50**, 0.60} |
| R-MOM | red-bar run {2, **3**, 4} | M2 wick share {0.40, **0.50**, 0.60} |
| X-ALERT (touch; close reported beside it) | pivot L = R {3, **5**, 8} | break buffer {0.05, **0.10**, 0.20} × ATR |
| X-JUMP | arm {0.75, **1.0**, 1.5} R₀ | swing L = R {2, 3, 4} (**2** is the base) |

---

## 7. Controls (same entries, bars, fills, costs, scenario)

- **C-RANDX (the control that matters).** For each rule set, take its own holding times (bars from entry to exit) over the 2,670 trades, **shuffle them across trades**, and exit each trade at its assigned bar's close (S still live as the floor, same scenario cap). Rule-timed exits must beat exits at the same holding times placed at random. 1,000 seeded draws `np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(b"EXIT-CMP"), zlib.crc32(rule_id.encode())])`; p5 / p50 / p95 / **p99** of net at mid, 1 MCL.
- **B-STOP** is the paired baseline and the first thing every report line is compared with.
- **B-V1** is shown beside them as the existing reference, never a criterion.

---

## 8. Cost model

- **IBKR Pro, per contract per side** (W15-0033, read 2026-09-30): **MCL $0.77**, **CL $2.37** (`strategy.chartmark.spec.FEE`; per-instrument fees for the manager in §13).
- **Levels** (Ben, 2026-09-30, "Fee + 0/1/2 ticks"): **low** = fee, **mid (headline)** = fee + 1 tick per side, **high** = fee + 2 ticks. Slippage is charged on **every** fill (entry, stop, market exit, flat), as the program's other IBKR runs; there is no separate stop-fill slip. MCL round trip: low $1.54 / **mid $3.54** / high $5.54; CL $4.74 / $24.74 / $44.74.
- **An exit that is a market order costs the same as a stop** in this model. Live they differ (a stop-market can slip more in a fast tape; a market order at the bar-close event waits about a second). The high level is the guard; sub 5 measures real exit slippage against it and a PRE-RUN or POST-RUN amendment follows if the fees or slippage differ (as W15-0033 requires: confirm on the first IBKR fills).
- **Every fee in the live manager comes from the table in §13, not from a constant.**

---

## 9. What every run must emit

Per rule set, scenario and friction level, 1 MCL and 1 CL, in total and per year: trades, wins / losses, gross, costs, **net**, **D = net(rule) − net(B-STOP)**, average win and loss, largest loss, worst losing run, max drawdown, both halves, exits by type (S / ratchet / M1 / M2 / alert / jump / flat / time cap), median bars held, give-back share (trades that reached +$0.20 and closed ≤ $0), profit capture (net ÷ the sum of each trade's best open profit), net ÷ standard deviation of trade net, overlap share (trades opened while an earlier one was open), and **20 real trades** (entry / exit time and price, net $) per rule set. Negative figures in brackets. Counts of how often each trigger fired (ratchet armed, M1, M2, line active, X-JUMP armed, swing used).

**Also reported:** FLAT vs HOLD per rule set (paired difference), the "S wider than the emergency distance" count (§14 rail 3), the slices of §4, the 2020 and 2014 windows, and a table of results by entry session (Asia / London / US-AM).

**Nothing is ranked outside the pass test of §10. No "best cell".**

---

## 10. The bar to clear — per rule set, FLAT scenario, training 2010-06 → 2021-12, 1 MCL, IBKR mid, paired against B-STOP

A rule set passes only if all eight hold:

1. **D > 0** at mid.
2. D > 0 at **high** friction.
3. D > 0 in **both halves**: 2010-06 → 2015-12 and 2016-01 → 2021-12.
4. D > 0 after dropping the top-1 and top-2 calendar years (by D).
5. **Bootstrap by entry year** (2,000 seeded resamples): D > 0 in ≥ 95%.
6. **Net beats the p99 of C-RANDX** for that rule set.
7. No single year supplies more than 50% of D.
8. **At least 6 of the 9 neighbour-grid cells** have D > 0.

**Verdict wording.** A rule set that passes all eight: **PASS**. Failing 6 closes that rule set whatever else passes. A rule set whose trigger fires on fewer than 200 of the 2,670 trades (for X-ALERT: fewer than 200 trades that ever had an active line) is **NOT READ** (its D is mostly zeros), not failed.

**What Ben gets from the result (sub 3):**
- **At least one PASS:** the manager's default is the passing rule set with the highest D at mid; others stay selectable and are logged as shadow exits in the paper trial. Selection bias among up to five passers is stated; sub 5 is the confirmation.
- **None passes:** the default is **B-STOP-plus** (server-side stop at the initial level, flat before the close; §15), and the rule sets are paper-trial options whose shadow exits are logged. That is a valid outcome and is not a reason to widen the test.
- **HOLD vs FLAT** is reported per rule set. The default flat mode is Ben's decision on that table and on overnight margin (§15), not a pass criterion.

---

## 11. The holdout and the rest of the discipline

- **No holdout is spent.** The comparison is on the training side (2010-06 → 2021-12) only. The 2022-01-03 → 2025-09-07 window of CHARTMARK-v1 and CHARTMARK-CLONE is not opened, and the seen window (2025-09-08 →) is not scored. The out-of-sample evidence for the chosen rule is **sub 5**: the paper trial, where the manager logs the chosen rule's real exits and the **shadow exits** every other rule set would have made on the same real trades.
- One outcome run: the runner writes `exit_cmp_ledger.json` before any outcome exists and refuses a second run (as `clone_ledger_w15_0050.json`); `--retry-after-crash` only after a crash, recorded.
- **Registered as NOT to be done:** changing any threshold in §6 after a result; promoting a variant or a grid cell; quoting gross, a variant, the Ben-takes slice or a single year as the headline; mining the 2,670 trades for a new exit rule after the run; adding a target, a re-entry or a size change to any rule set under this registration; spending a holdout on any of it.

## 12. Gates before any outcome is read (no P&L in this section)

| # | Gate | Who |
|---|---|---|
| G1 | Data: the CL 1H frame of W15-0002 exactly as CHARTMARK-v1 loads it (cut before 2022-01-01 before resampling / back-adjusting) | Build & test (sub 2) |
| G2 | **Parity:** B-V1 in HOLD reproduces the 2,670 recorded trades (entry / exit timestamps and net per row to the cent) and net ($13,422) at mid, 1 MCL. The only use of the trades CSV's outcome columns, run after the code is frozen | Build & test |
| G3 | Entry-set check: the re-run entry machine gives 2,670 fills with the §4 per-year counts (mismatch = stop); no module opens an outcome column of the trades CSV (a static test) | Build & test |
| G4 | **Look-ahead guards**, each broken by a one-bar shift in a test: every rule uses bars ≤ j−1 for what works in bar j; M1 uses closes ≤ j; X-JUMP's swing low is used only from its confirmation; the X-ALERT line value uses pivots confirmed ≤ j−1 (**truncation invariance**: mutating every bar after j leaves the decision at j unchanged) | Build & test |
| G5 | Conservative ordering: a bar that can both hit a stop and raise the ratchet counts the stop first; the count of such bars is reported | Build & test |
| G6 | **Count-only pre-flight** (no exit price, no P&L): per rule set, how many trades reach its trigger (ratchet armed, M1 or M2 would fire, a line active, X-JUMP armed), per year, per scenario. The runner refuses to print an exit price or a P&L in this mode. Also the median CL 1H ATR(14) over training (to scale the §13 multipliers) and the count of trades whose S distance exceeds the §14 emergency distance | Build & test |
| G7 | Ledger and one-run lock (§11); seeds fixed; this registration's SHA-256 recorded before the run | Build & test |
| G8 | Per-symbol table (§13) unit-tested: tick, tick value, fee and the arm / emergency distances produce the CL / MCL numbers of §8 exactly | Build & test |

**Stop rule, fixed now:** G6 shows fewer than 200 trades reaching a rule set's trigger → that rule set is NOT READ; the others run. G2 fails → stop, back to the Research & spec chat; no outcome is read.

---

# Part B — Specification of the hybrid exit manager (sub 4 builds it; not a hypothesis)

## 13. Symbol table: any futures fill

The manager takes over **any futures fill** whose root is in the table; a fill in a symbol that is not in the table is **never touched** (alert only, rail 7). Contract details (multiplier, min tick) are also read from IBKR at start and must equal the table, or the symbol is disabled with an alert.

| Vehicle | $ per point | Tick | Tick $ | IBKR fee / side | Backtest evidence |
|---|---|---|---|---|---|
| **MCL** | 100 | 0.01 | 1.00 | $0.77 | CL 1H, this registration |
| **CL** | 1,000 | 0.01 | 10.00 | $2.37 | CL 1H, this registration |
| MES | 5 | 0.25 | 1.25 | $0.62 | none (rules unvalidated) |
| ES | 50 | 0.25 | 12.50 | $2.26 | none |
| MNQ | 2 | 0.25 | 0.50 | $0.62 | none |
| NQ | 20 | 0.25 | 5.00 | $2.26 | none |
| M2K, MGC, SIL, MHG, M6A / M6B / M6E, NG, 6J | per `strategy/tl_v0/spec.py` MARKETS | per that file | per that file | `strategy/futbt/costs_ibkr.py` FEE_PER_SIDE | none |

(Fees for MES / MNQ $0.62 and ES / NQ $2.26 are the figures read on 2026-09-30, W15-0033; the others are `costs_ibkr.py`. The table lives in one Python module, `exitmgr/symbols.py`, and the fees are re-confirmed against the first IBKR paper fills, §8.)

**Per-symbol rule distances.** CL / MCL: ratchet arm **$0.20**, emergency stop distance **$0.60** (the CHARTMARK-v2 K1 backstop). For every other symbol the distances are **the CL value scaled by volatility**: `distance = (CL value ÷ median CL 1H ATR(14), measured in G6) × that symbol's 1H ATR(14) at the fill`. These are **unvalidated** on any symbol except CL / MCL; for them the default rule set is B-STOP-plus until Ben says otherwise, and every trade is shadow-logged. This is stated so "any futures fill" does not read as "tested on any futures fill".

**Size cap per symbol** (hard maximum contracts the manager will manage as "within limits"; above it the manager still protects the position but raises an OVER-CAP alert and takes no other action): **a decision for Ben** (W15-0059). Proposal for the paper trial, not registered: CL 10 (the size of his NinjaTrader paper record), MCL 20, ES 2, MES 20, NQ 1, MNQ 10.

## 14. Safety rails (each is a requirement for sub 4, with a test; the live-money code gets Opus · High)

1. **Reduce-only.** The manager never opens a position, adds to one or increases size. Every order it sends is on the opposite side to the live position, and its quantity plus every other working exit order's quantity is ≤ the position, checked against a fresh broker position immediately before sending. A breach is refused and logged. If IBKR's futures order API offers a reduce-only / close-only attribute it is set; if not, rail 11 is the residual risk and is tested.
2. **One working exit order per position.** Orders carry `orderRef = XM:<symbol>:<fill-id>` in one OCA group per symbol; the manager *modifies* its own order and never stacks a second.
3. **Stop first, server-side.** The first order sent after the first fill is the protective stop; the target is ≤ 1 s from the fill event, measured and logged every time, and > 3 s raises an alert. The stop rests at IBKR, so a crashed PC, a dead internet link or a Gateway restart leaves the position protected. Initial level: **Ben's own stop if he attached one (rail 5), otherwise `max(S, fill − emergency distance)`**, where S is v1's structural stop from the last five 1H bars, fetched right after the emergency stop is placed (the emergency stop goes first, then is *tightened* to S if S is closer; never widened). The backtest uses S alone; G6 counts how many of the 2,670 trades S would have put wider than the emergency distance.
4. **Never loosens.** Every stop modification is asserted to be in the protective direction (up for a long, down for a short) every time; a loosening modification is refused and logged. (The rule sets are monotone by construction; this is the belt as well as the braces.)
5. **Existing orders from other apps.** On a fill, the manager reads all open orders. If Ben already attached a stop and the manager does **not** hold the master client id (0), it places **nothing** for that trade, shows OBSERVE-ONLY and alerts; it never creates a second exit order beside his. With the master client id it adopts the order and modifies it.
6. **Partial fills and scale-ins.** The protective stop quantity tracks the cumulative filled quantity (modified on every execution event); the position is reconciled with the broker's truth on every reconnect and at least every 30 s.
7. **Unknown or unsafe contract.** A fill in a symbol outside the table, or in a contract within 2 trading days of its last trade date, or whose contract details differ from the table: **alert only, no orders.**
8. **Size.** Over the cap (§13) → still protected, OVER-CAP alert, no other action. The manager never reduces size by itself in v1 except as a rule exit or a FLATTEN.
9. **Kill switches.** (a) **PAUSE:** stop all rule actions and modifications; the resting server-side stops stay. (b) **FLATTEN:** cancel the manager's own orders, market out each managed position, then PAUSE. (c) A file flag `STOP_MANAGER` checked every loop and the console key. (d) **Runaway guard:** more than 20 orders sent in a minute or more than 200 in a day → PAUSE and alert.
10. **Paper lock.** The connected account id must equal the configured paper account (IBKR paper ids begin `DU`) or the process exits. Live trading needs a separate explicit config flag **and** Ben's go decision at sub 6; it is not enabled by anything in sub 4.
11. **Flat position cancels the stop.** When the position reaches 0 for any reason (including Ben flattening by hand in an app), the manager cancels its orders for that symbol at once. The window between a manual flatten and that cancel, in which the stale stop could fill and open a short, is the main residual risk; sub 5 measures it deliberately (flatten by hand, record the time to cancel).
12. **Stale data.** No market data tick for 30 s in session → alert; the manager takes no rule action on stale bars and leaves the server stop.
13. **Maintenance and weekends.** No rule action during the 17:00 – 18:00 NY maintenance halt; the resting stop stands. Daily and weekly IBKR Gateway restarts are expected: the manager reconnects, reconciles (rail 6) and resumes from its state file; a managed position it cannot match to its state is alert-only.
14. **Log everything**, append-only JSON lines: every fill seen, every order sent / modified / cancelled with the rule and the numbers behind it, rule state at every bar close for the active rule set **and the shadow exits every other rule set would have made on the same trade**, latencies, version hash of code and config. This log is the evidence for sub 6.

## 15. The flat-before-close option

- **Config `flat_mode`:** `FLAT` = at **16:55 NY** the manager market-sells every managed position (cancelling its stop first only after the exit order is working, so there is never a moment unprotected); `HOLD` = carry through the close and over weekends on the server-side stop, with the rule set still active. Per-trade override is a v2 feature (the portal ticket).
- **Why it is an option, not a default:** overnight and weekend holds change the margin the account needs (Ben's NinjaTrader figures: MCL $884.53 overnight, CL $8,823.20; the IBKR figures are read at sub 5), widen the unattended risk, and cross rolls. The backtest gives FLAT (primary) and HOLD for every rule set and the paired difference; **Ben chooses the default from that table.** Until then the paper-trial default is `FLAT`.
- **1H limitation:** the backtest can flat only at the 17:00 bar close; the live 16:55 is five minutes earlier. The difference is not tested.

## 16. Architecture (summary for sub 4)

`ib_async` (the project's IBKR library) process on Ben's PC against an IB Gateway or TWS API port logged into the **paper** account. IBKR normally allows one trading-platform login per username, and IBKR Mobile or the web client are usually allowed alongside it; this is confirmed on the first paper session rather than assumed. If Ben places trades in TWS, the manager connects to **that** TWS's API port instead of a second Gateway. Components: fill listener (`execDetailsEvent` for all executions of the account, whichever app sent the order) → position / state store (JSON, rewritten atomically) → rule engine (the one active rule set plus shadow rule sets, pure functions of closed 1H bars and the tick stream, the same code the backtest runs) → order gateway (the only module that can send orders, enforcing rails 1, 2, 4, 5) → logger. Bar data for the rule engine comes from IBKR historical / streaming bars; the 1H bars are rebuilt from the same source as the backtest and compared (the first live day's rule decisions replayed through the backtest engine must match).

**The rule engine must be one code path** for the backtest and the manager (a pure function from the closed bars so far and the trade state to an action). Sub 2 writes it in that shape; sub 4 imports it unchanged.

## 17. Known limits of the comparison

- **1H bars cannot show the path inside a bar.** The ratchet and the alert are tick-level rules live; here they act at bar close or at the level with the conservative order (G5). A rule that looks marginal at 1H may behave differently in real time, in either direction. The paper trial's shadow log is the check.
- **The entries lose.** Rules that exit sooner get a head start on a losing population. C-RANDX at the rule's own holding times is the guard; it does not remove the effect completely.
- **Independent trades**, not a path: a rule that holds longer would have blocked later fills in real life. The overlap share is reported.
- **Tori's line is not Ben's.** The mechanical TL-v0 line is not the line Tori draws by eye (nor is it the line Ben would draw); the ALERT rule here is "alert on the mechanical line". A weak result is a weak result for that coding.
- **Replay vs live.** Real fills have latency, partial fills and queue effects that the 1H model does not have; the IBKR fee is read from the published rates and confirmed on real fills.
- **Long only.** Shorts are mirrored and unit-tested, not backtested here.
- **CL / MCL only.** The other table rows are untested parameters (§13).

## 18. Multiplicity budget

One entry set; five candidate rule sets (R-BEN, R-MOM, X-ALERT-touch, X-ALERT-close, X-JUMP) × one primary scenario; three reported variants and the HOLD scenario never promoted; one outcome run; no holdout spend. The selection among passers carries the usual winner's bias, which is why sub 5 is the confirmation.

## 19. Prediction, written now

- **None of the five passes all eight criteria:** about **55%**. Entries that lose before costs leave little for any exit to add.
- **R-BEN is the most likely to pass criterion 1** (it cuts give-back by construction), about even odds; it is less likely to clear the p99 of random timing. **R-MOM** is likely to improve loss size and give-back but not total net after the extra exits' friction. **X-ALERT-touch** is likely worse than X-ALERT-close (whipsaw). **X-JUMP** is the most sensitive to its swing definition; I expect it to be near zero.
- **Give-back share falls under every rule set versus B-STOP** (nearly mechanical); that is not evidence of edge.
- **FLAT beats HOLD on risk-adjusted terms for most rule sets**, and costs net on trades that trend overnight.

I'd be glad to be wrong.

## Amendment 1 — PRE-RUN, 2026-10-18 (before the pre-flight; no outcome read)

Written by the Build & test chat with Ben's approval ("1 YES … 3 Yes", 2026-10-18). Nothing below changes a rule number in §6; it fixes how the code reads them, adds one reported variant, and fixes the non-CL emergency distances.

**Interpretations fixed before any outcome (I1–I10).**
- **I1** "Highest high since entry" includes the entry bar's own high (a buy-stop fills at the first touch of its level, so that high came at or after the fill); anything computed from it works from the next bar.
- **I2** M1 (three red closes) uses only bars after the entry bar.
- **I3** X-ALERT: the level working in bar j is the line projected from the state after bar j−1, eligible only while below close[j−1]; X-ALERT-close fires at the close of j when close[j] < that level − buf × ATR[j].
- **I4** X-JUMP: a swing low is a bar with a strictly lower low than the L bars either side, confirmed at the close of bar i+L; only swings after the arming bar count; the stop moves to low − 1 tick only if that is above the entry price.
- **I5** X-JUMP-1R-half: once X-JUMP has armed, the R-BEN half-profit ratchet applies too (stop = the higher of the two).
- **I6** FLAT's session end is the bar that opens 16:00 NY, or the last bar before a gap when the session closes early (175 early-close sessions in the frame).
- **I7** Entry sessions are by NY entry hour: 02 / 03–07 / 08–12.
- **I8** A "give-back" trade is one whose best high before the exit bar reached +0.20 and whose net at mid is ≤ 0.
- **I9** Price thresholds are compared with a 1e-9 slack (float noise from back-adjustment).
- **I10** The B-V1 parity check runs without the 120-bar cap (0 of 2,670 v1 trades exceed it).

**Look-alike line tracker (Ben: "1 YES").** X-ALERT uses `exitmgr/lines.py`, an online tracker proven identical to the frozen `common/tl_v0_lines.walk_line_and_breaks` on random series plus a next-bar projection; the frozen module is untouched.

**Added reported variant: B-STOP-EMERG.** B-STOP with the initial stop capped at `max(S, entry − $0.60)`. It is reported and never ranked, in the §10 paired form against B-STOP. Reason: 1,458 of the 2,670 entries have S wider than $0.60, and the live manager's first order is the emergency stop (§14 rail 3), so the live stop is tighter than the tested one. The §18 multiplicity budget is unchanged (no new scored rule set).

**Non-CL emergency distance (Ben, 2026-10-18).** CL / MCL stay at $0.60 in every mode. For other symbols the manager has three selectable modes, default **A**: **A** the §13 volatility scaling; **B** about one big 30-min bar; **C** 1.5 × the median 1H range. Measured on MNQ 30-min / 1-hour bars, 3 Sep – 16 Oct 2026 (`tools/mnq_swing.py`): the 15 biggest 30-min bars average 247 points (≈$495 per MNQ contract), the 15 biggest 1-hour bars 281 points (≈$561); the median 1H bar is 70 points. Mode B is therefore 250 points (MNQ and NQ), mode C 105 points. These are unvalidated (§13) and are not backtested here (§17).

---

## Next steps (board)

- **W15-0053 sub 1** — this registration: Research & spec chat, **done**; Ben commits it (sub 1b, commands posted).
- **W15-0053 sub 2** — Build & test chat (Sonnet · Medium; the X-ALERT line piece Sonnet · High): the runner as one rule engine, tests G1–G8, delivers to `D:\Trading\Claude outputs`; commands on sub 3.
- **W15-0053 sub 3** — Ben runs the count-only pre-flight, then the one outcome run (commands on the subitem) → Result doc picks the default rule set and shows FLAT vs HOLD.
- **W15-0059** — Ben: confirm the symbol table (size caps, allow-list) before sub 4 starts. Does not block subs 2–3.
- **W15-0053 sub 4–6** — as on the item (sub 4 Build & test, Opus · High; subs 5 Ben, 6 Haiku · Low). Sub 7 (portal ticket) stays deferred to v2.
