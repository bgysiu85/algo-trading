# REGISTERED — dist_from_high as an entry gate, on its own registration

**Committed before this gate is coded or run, and before any dist_from_high-gated P&L has
been seen under this registration.** `PROGRAM_INDEX` §1: a hypothesis is registered before it
is run. Board: W05-0005.

**Origin, and why this is a fresh registration rather than a re-read of an existing number.**
`chase_gate_RESULT_20260918.md` §4 tested `dist_from_high` **instead of** the `ret_5m` chase
ceiling, at a budget matched to each `ret_5m` cell's removal count, and reported it **never
scored**:

| at a matched budget | removed | per trade | vs random p95 |
|---|---:|---:|---:|
| MCL dist ≥ −0.1594 | 1,118 | +0.92 | +0.68 — beats it |
| MC5 dist ≥ −0.1993 | 1,203 | +0.59 | +0.65 — just inside |

That is the only cell in the whole chase-gate study to beat its own abstention control, and
`session_close_20260918.md` §5 item 4 is explicit about why it cannot be promoted as-is: it was
fenced off before the run precisely so a good-looking number could not be promoted after the
fact. **The two thresholds above (−0.1594, −0.1993) are themselves the output of that fencing
and are not reused here.** Reusing them would be scoring a number chosen after seeing which
number looked best — the exact failure mode the fence exists to prevent. What carries forward
instead is the **procedure**: solve the threshold to match a removal count, blind to P&L, per
§4's rule that a comparator with a free parameter is solved against a constraint, never chosen.

---

## 1. The claim, exactly

**A BUY entry is refused when `dist_from_high` — the signal bar's distance below the session's
running high-to-date, `(close − session_high) / session_high`, always ≤ 0 — is more negative
than a threshold**, i.e. the name has fallen further from its own high than the threshold
allows. The signal is recorded as refused (mirroring `chase_gate`'s row discipline) with
`dist_from_high` and the threshold on the row; the bar is marked evaluated; the next signal
bar is judged on its own value. Entries only — this is a backtest parameter through
`entry_gate`, the same mechanism `chase_gate.py` uses, and it does not reach
`evaluate_last_bar`; a test asserts that, mirroring `tests/strategy/test_sweep_params.py`.

## 2. Population

`screen_pairs_pit_itch_v2.json` — the same point-in-time, XNAS.ITCH universe as
`chase_gate_RESULT_20260918.md` and every current baseline (6,411 symbol-days). MCL and MC5
only. No new data pull.

## 3. Thresholds — solved, not chosen

**Five budgets per book, taken from the same family `chase_gate.py` already computed** (the
`ret_5m` ceilings 0.033 / 0.083 / 0.100, plus two additional values spaced the same way over
the observed range of `dist_from_high` at signal time). For each budget, the `dist_from_high`
threshold is **solved** so the gate removes the same number of trades (±3, matching
`stop_compare`'s tolerance) as the corresponding `ret_5m` cell removed in `chase_gate_RESULT`,
computed **fresh from the current trades file, using only the removal count, never the P&L** —
so no cell is selected because it performed well. This is the same solving step
`entry_gates`/`stop_compare` already use; what changes here is that it runs **before** any of
the five cells' money is looked at, not after.

Ten cells total (five per book), plus the two base books (no gate) for reference.

## 4. Registered readings — inherited from `common/gate_study.py`, all five, all scored

1. **Per-trade delta ≥ MIN_MARGIN ($4.26) AND per-symbol-day > 0** — the standing pass rule.
2. **Both halves** (before/after the median session date) — the delta's sign must hold in both.
3. **Drop-top-3** on the delta — remove the gate's three best trades; the gate must still pass.
4. **Symbol-cluster bootstrap, P ≥ 0.95** on the delta.
5. **Abstention control** — the same number of trades removed at random, 2,000 seeded draws
   (`crc32`-seeded per §4's null-control rule); the gate must beat the random band's p95, not
   merely sit inside it.

All five are scored this time, not reported. `common/gate_study.py`'s `G.render()` is reused
unchanged — the same five readings every entry gate in this project inherits.

## 5. What is reported alongside, never scored

- **The marginal trade** — what each refused trade is worth, per §4's standing rule.
- **Two denominators** (per-trade and per-symbol-day) with the standing refusal-on-disagreement
  rule.
- **Overlap with the chase gate itself** — of the trades this gate refuses, how many `ret_5m`'s
  ceiling at the matched cell already refused. `dist_from_high` and `ret_5m` are correlated (a
  name far below its high has usually just made a large move down), and a gate that mostly
  re-refuses the chase gate's own trades is not a second mechanism.
- **Where the ten solved thresholds land relative to −0.1594 / −0.1993** — reported for
  context only, because the two numbers from the fenced pass are not a target and are not
  scored against.

## 6. What decides whether this goes anywhere

**Decision point (Ben only), after the result:**

- **(a) Study-only** — a passing cell here would be a direction confirmed once, not a rule to
  ship; nothing in this project ships off one registration.
- **(b) Close** — the scored run does not clear the five readings, or clears them only by
  re-refusing the chase gate's own trades (§5).
- **(c) A second registration** — if it passes cleanly and independently of the chase gate,
  the next step is a holdout-free live-parity check, the same bar `REGISTERED_giveback_cap`
  set before any session-level rule goes near a live session.

Nothing in this document commits to any of the three. Nothing ships; `holdout.json` untouched;
`entry_gate` stays a backtest-only parameter.

## 7. Caveats — what this registration does not claim

- **The prior is favorable, and that is disclosed, not hidden.** This gate is being tested
  because it beat its abstention control once, under a fence built for exactly this situation.
  A second, independent, fully-scored pass is what turns "the only cell to beat the ceiling"
  into a result rather than a story about one lucky fence.
- **`dist_from_high`'s own separation is weak by the same pre-flight that motivated it**
  (`running_up_preflight`: AUC 0.494 MCL / 0.443 MC5 against the one-bar death rate) — the
  claim here is about the money, not about separating deaths, per §4's "a lower failure rate is
  not a better book."
- **This is not a re-open of the chase gate**, which is closed (`chase_gate_RESULT_20260918.md`
  §7): "the chase trades are the better half of a losing book." This registration tests a
  different, correlated signal, reported against the chase gate's own trades (§5) precisely so
  the two are not silently conflated.

## 8. Timeline

1. **W05-0005, this document:** register the gate; commit before any code exists or any cell
   is scored.
2. **W05-0005, build + run (Build & test chat):** extend `common/gate_study.py`'s pattern —
   `common/dist_from_high_gate.py`, mirroring `chase_gate.py` — solve the ten thresholds (§3),
   run the full population, render all five readings scored, write the Result doc, the raw
   `.txt`, and a published artifact page.
3. **W05-0005, decision (Ben):** per §6.
