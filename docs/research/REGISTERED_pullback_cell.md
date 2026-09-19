# REGISTERED — the pullback cell: take the entry only when the name is at its session high and has not just run

**H-P2.** `PROGRAM_INDEX` §7 item 10b. Written and committed 2026-09-19
(Sydney) before `common/pullback_cell.py` exists and before any gated book
has been run. Decided by Ben on 2026-09-19 as the next thing to build, over
the 10-second strategy. **Cost $0.00** — one pass over bars on disk.
`holdout.json` is not involved. No live change.

## 0. What is known, said plainly

- **The cell was named before it was measured.** Ross Cameron's primary
  setup is the micro pullback — buy the first dip after a move, near the high,
  not the extension (`warrior_1_micro_pullback.md`). The Running Up pre-flight
  put that name on a 3×3 grid of `ret_5m` × `dist_from_high` terciles *before*
  reading it, and the cell "at the high, not extended" read **3.3% one-bar
  deaths on MCL against a 12.6% base (397 entries, 10% of the book) and 15.5%
  on MC5 against 37.2% (471, 7%)**
  (`Claude outputs\running_up_pullback_grid_20260918.txt`). The grid's own
  header says its terciles are data-derived and not thresholds, and that a
  registration must fix its own from the printed distributions. This one does.
- **Every entry gate before it read as random removal.** H-B1, H-B3, H-B4 on
  both tapes; H-P1 (the chase ceiling) refused the *better* half of a bad
  book. What is different here: the cell is a conjunction the pre-flight
  measured as a *rate*, not a threshold searched for, and its one-bar rate is
  a quarter of the base rate on MCL — a much larger separation than any gate
  so far carried into its registration. That is a reason to run it, not to
  believe it.
- **MCL-PB is not this.** Six versions bought the *breakout after* the
  pullback at a median +2.86% premium and all read NOTHING. This gate never
  buys a break; it selects *among* the entries MCL and MC5 already take. H-E2
  (looser confirmation) does not bear on it either — it adds no trades.
- **The ceiling.** Even a perfect one-bar filter leaves MC5 at +$0.70 a trade
  at $8.92 (`running_up_preflight_RESULT` §5). A pass here is a smaller loss
  or a thin gain; it does not reopen MC5 as a candidate.
- **Two things a chosen threshold could smuggle in.** `dist_from_high` alone
  was H-P1's fenced comparator and beat random removal on MCL at a matched
  budget — so the *distance* half may carry the effect on its own; and
  `ret_5m ≤ C` alone is H-P1's ceiling, which read NOTHING. Both halves are
  therefore run alone at the same thresholds, reported and never scored, so
  the conjunction is read against its parts.

## 1. The rule, and the thresholds, fixed now

> **An entry is taken only if, at the close of the signal bar, the name is
> within D of its session high AND its five-minute return is at most C.**

- `dist_from_high = close / session_high − 1 ≥ −D` with **D = 5%**. The grid's
  upper terciles sat at −4.3% (MCL) and −6.9% (MC5); 5% is the round number
  between them.
- `ret_5m ≤ C` with **C = +3%**. The grid's lower terciles sat at +3.6% (MCL)
  and +1.1% (MC5); 3% is the round number between them. One pair of
  thresholds for both books.
- Both features from `common/running_up` (`dist_series`, `ret_series`), the
  session's closed bars only, as the pre-flight computed them.
- **A NaN feature does NOT admit the entry.** This is a positive selection
  ("only if it is at the high and calm"), the opposite of H-P1's refusal
  ("not if it has run"), so the absence of evidence is not the state the
  gate asks for. The count refused for NaN alone is printed.
- Delivered through the engines' `entry_gate` hook — the **deployed** form:
  a refused entry leaves the engine flat and later bars fire as the rule
  says. The **book-ordinal** reading (the baseline's own entries classified
  by the gate at their entry bar) is printed beside it and never scored
  (§4's "signal-ordinal is not book-ordinal"). For MC5 the 1-minute gate is
  carried onto the 5-minute index by forward fill, the H-B3 / H-P1
  convention, up to five minutes conservative in the safe direction.

**Reported, never scored** (the fence is here, not in the result):

| book | why it is printed |
|---|---|
| `dist ≥ −5%` alone | is the distance half doing the work (H-P1's comparator)? |
| `ret_5m ≤ +3%` alone | is the calm half doing the work (H-P1's ceiling)? |
| cell at (D 3%, C +1%) | tighter neighbour — sensitivity, one step in |
| cell at (D 10%, C +5%) | looser neighbour — sensitivity, one step out |

Twelve books, one tape pass: two baselines, two cells, eight reported.

## 2. What is read, fixed now

The five gate readings of `REGISTERED_range_rank` §3 as `gate_study` scores
them, unchanged: (1) per trade ≥ $4.26 AND per symbol-day > 0, a sign
disagreement REFUSED; (2) both halves, both denominators; (3) drop-top-3 on
the level and the delta; (4) the symbol-cluster bootstrap on the delta,
P ≥ 0.95; (5) **the abstention control** — the same number of trades removed
at random, 2,000 seeded draws, the gate's per-trade delta beating the 95th
percentile. PASSES / NOTHING / REFUSED, per book, on
`screen_pairs_pit_itch_v2.json` with XNAS.ITCH bars, at $1.00 / $4.26 / $8.92.

Beside the verdict, and required:

- **The mechanism, read back.** The kept book's one-bar death rate. The cell
  was chosen because it reads 3.3% / 15.5%; if the deployed gate's kept book
  does not read under **6% (MCL) / 22% (MC5)**, the gate is not selecting the
  cell the pre-flight measured, whatever its P&L says, and the result says so
  first.
- **Binding.** The share of baseline entries the gate would refuse, and of
  those, the share refused for NaN alone. A gate that binds on 90% of a book
  is a different strategy from the one it gates; the report says how many
  trades a session it leaves.
- **The marginal trade** — what the refused entries were worth — and the
  kept book's **absolute** per trade at all three frictions. The absolute
  number is what the ceiling is about.
- **Trades per session** of the kept book against the live cap (3 slots):
  a gate that leaves one trade a week is not deployable however it reads.

## 3. Predictions

- **P1 (binding).** The gate keeps **7–13%** of MCL's entries and **5–10%** of
  MC5's; NaN-only refusals under 3% of entries.
- **P2 (mechanism).** The kept book's one-bar rate reads **3–6%** on MCL and
  **14–22%** on MC5 — the cell survives deployment.
- **P3 (per trade).** The cell improves per trade by **+$2 to +$7** on MCL and
  **+$4 to +$12** on MC5 at $4.26 — larger than any gate before it, because
  it removes the one-bar deaths preferentially and those are the worst
  trades in both books.
- **P4 (verdict).** **MCL NOTHING**, failing reading 5 or 4: ~390 kept
  trades against random removal of 90% is a wide band (p95 around +$3 to
  +$4). **MC5 clears readings 1 and 5 and fails at least one of 2–4** — so
  NOTHING, but with the per-trade reading beating abstention, which no gate
  here has done. Moderate confidence on both; the alternative worth naming
  is MC5 PASSES, which under the standing rule would still not reopen MC5
  (§0, the ceiling) and would send the cell to a second registration with
  the concurrency cap modelled before anything else.
- **P5 (absolute).** Both kept books remain **negative per trade at $8.92**;
  MC5's kept book is positive at $1.00 and within ±$2 of zero at $4.26. MCL's
  is negative at every level.
- **P6 (the parts).** `dist ≥ −5%` alone improves per trade by more than
  `ret_5m ≤ +3%` alone on MCL (H-P1's finding), and the conjunction improves
  by more than either part on both books. If the conjunction does **not**
  beat the distance half alone on MCL, the calm condition adds nothing and
  the cell is H-P1's comparator under a new name.

## 4. What this decides, and what it does not

- Decides item 10b: whether the pullback state is a selective gate on the
  tape of record, by the same five readings that closed H-B1, H-B3, H-B4 and
  H-P1.
- A PASS decides nothing about the trader. The next steps would be, in
  order: the concurrency cap modelled (the kept book is a tenth of the
  entries, so slot use changes completely), a parity test that the live
  evaluator computes the two features exactly as `running_up` does, and only
  then the holdout question, under its own registration. Nothing from this
  run reaches `main.py`.
- No threshold is chosen from the result. The four reported books are
  fenced above; a "better cell" among them is a direction for a new
  registration, never a promotion.
- `holdout.json` stays shut. `D:\TradingProd` untouched. $0.00.

## 5. Amendments

None yet. PRE-RUN / POST-RUN marked when they come.
