# REGISTERED — a spread gate at entry, threshold fixed before the study runs

**Committed before the study is coded, before the quote pull runs (`--full --confirm`), and
before any spread-gate result has been seen.** `PROGRAM_INDEX` §1: a hypothesis is registered
before it is run. This is a live-path cost control, scored like the drift guard
(`docs/research/REGISTERED_drift_guard.md`), not a search for an edge.

Board: W03-0002, step 4. Motivation: `claude/handover_thin_tape_entries_20260918.md` §4(b) and
§5; `claude/thin_tape_RESULT_20260919.md` §8. Quote-pricing tool and sample:
`claude/handover_monday_board...` — `common/quote_price.py` (commit `58f6c8e`),
`var/reports/quote_price.txt` (2026-09-19, sample pricing, all four candidate tapes projected
$0.00 under the current plan). Ben's decision, 2026-09-19, in his words: *"let's price and get
the MBP-1 data"* — unblocking this line; step 3 (confirm the pull) closed 2026-09-23.

**This registration covers the spread gate only.** The companion signal-bar volume gate
proposed alongside it in the same handover is **CLOSED** — `thin_tape_RESULT_20260919.md` §8:
"Handover options (a) and (c) — a volume floor inside MC5, or a minimum signal-bar volume gate
in the trader — are closed on the backtest evidence. At the live cut's own threshold, a floor
refuses 744 MC5 entries that die less than half as often as the book." A volume gate is not
registered here or anywhere in this line; raising it again needs a fresh registration with a
reason that is not the handover already closed.

---

## 0. PRE-RUN GATES — step 5 (the build-and-run) does not start until both are cleared

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **The full quote pull runs and lands** (`common.quote_price --full --dataset XNAS.BASIC --schema cbbo-1s`, then `--confirm`), covering every entry window in both published books (§2). | The gate is being registered on real top-of-book quotes, not the backtest's close+tick surrogate; the study cannot start until the quotes it scores exist. |
| **G2** | **The `SKIPPED_SPREAD` row and refusal path exist and are unit- and mutation-tested**, mirroring the drift guard's own tests (refuses at and past the threshold, admits below it, never runs on a SELL, records once per bar, treats a missing quote as `NO_QUOTE` rather than a refusal). | `REGISTERED_drift_guard.md` §4 is the parity bar; a second gate on the same order path that is untested the same way is how the guard's own blind spot (§6 of the handover — the ask/mid difference) gets repeated. |

---

## 1. The claim, exactly

**A BUY entry is not sent when the quoted spread — (ask − bid) / mid, at the moment the order
is about to go out, on a fresh quote — is 2.0% or more.** The signal is recorded as refused
(`SKIPPED_SPREAD`) with the spread and the threshold on the row; the bar is marked evaluated;
the next signal bar is judged on its own quote. Entries only. Exits are never gated — a
position that cannot be exited is the MEDS failure (`PROGRAM_INDEX`), not a saving, and this
gate does not touch the exit path at all.

This sits beside the drift guard on the same order path (`brokers/ibkr/trader.py`), same shape:
check last, on a fresh quote, refuse and log, never retry the same bar a second later.

## 2. The threshold, and why it is this one

**`SPREAD_GUARD_PCT` = 2.0**, measured as `(ask - bid) / mid * 100` at the moment the order is
about to be sent.

- **Live book evidence** (180 round trips, 2026-09-10 → 09-18, both books):

  | spread at entry | n | net | per trade | win % |
  |---|---:|---:|---:|---:|
  | < 0.5% | 103 | (11.32) | (0.11) | 24 |
  | 0.5–1% | 42 | 4.34 | 0.10 | 26 |
  | 1–2% | 22 | (87.16) | (3.96) | 27 |
  | **≥ 2%** | **13** | **(601.87)** | **(46.30)** | **15** |

  The combined cut with the now-closed volume line — spread ≥ 2% **or** signal-bar volume <
  2,000 — was 21 trades, (656.85); on the spread clause alone the 13-trade bucket already
  carries (601.87) of that, essentially all of it.
- **2% is written down before the study runs, not fitted to it.** The same 2% would have
  refused CRBP (2.57% spread, (241.37), the single worst trade in the live book) — which is
  exactly the trade that makes a threshold chosen *after* seeing the book suspect. Stating the
  number and the reasoning now, before the full-quote study runs, is the point of this
  document.
- **Not a precision fit.** 1%, 1.5%, 2%, 2.5% are all defensible from the same table; 2% is the
  round number the live evidence points at most clearly (the bucket boundary where per-trade
  swings from +$0.10 to −$3.96 to −$46.30), not a grid-searched optimum. Moving it after seeing
  the full-quote result is a new registration, not an amendment to this one.
- **Not an edge claim.** Shipped as a cost control, on the drift guard's own footing: refuse to
  cross a visible toll; improve or be neutral, never a source of expected profit on its own.

**Interaction with the drift guard:** the drift guard reads drift on the ask against the signal
close (≤ 6.0%, `REGISTERED_drift_guard.md`); this gate reads the spread itself, independent of
where price has moved. `handover_thin_tape_entries_20260918.md` §6 recorded the case where they
diverge — a 10.47% spread where the ask sat only 5.6% from the reference, inside the drift
guard's own limit — which is the concrete argument for this gate existing rather than widening
the drift guard. The study (§4) reports the overlap between the two gates rather than assuming
either subsumes the other.

## 3. Data source for the quote — fixed now, before the pull

**`XNAS.BASIC` / `cbbo-1s`** (consolidated best bid/offer, one-second resolution) is the tape
this gate is measured and, if shipped, run against live.

- It is the **smallest** of the four priced candidates (0.47 GB vs 7.61–10.15 GB for the MBP-1
  tapes) and the question here is top-of-book spread only, not depth — `cbbo-1s` is exactly
  that and nothing more.
- It sits in the **same feed family the published backtests already use** (`XNAS.BASIC`
  point-in-time), so the spread measured here is on the same tape as the P&L it is being
  weighed against, rather than a different vendor product with its own gaps and conventions.
- All four sample candidates priced at **$0.00 projected** under the current plan
  (`var/reports/quote_price.txt`, 2026-09-19); the choice is not driven by cost.
- If the full pull (`--full --dataset XNAS.BASIC --schema cbbo-1s --confirm`) prices above $0
  once run on the complete window set, that is reported and the pull stops — it does not
  silently switch tapes.

## 4. What the study must measure and report (W03-0002 step 5)

Same bar as the rest of this project's gate work (`REGISTERED_tl_v0.md` §3 pattern, adapted):

1. **The gate's cost**, on the full point-in-time backtest book, both denominators (MCL and
   MC5 separately and combined): entries refused, count and % of book; P&L removed, total and
   per trade; win rate before and after.
2. **Gate quality, not only gate cost** — of the entries refused, how many would have lost
   money (true positives) vs. won (false positives); of the entries let through, how many still
   lose (false negatives). Precision = true positives / all refused; recall = true positives /
   all losers.
3. **Full bars**: drop-top-N (N = 1, 2, 3), both halves split at the median date, cluster
   bootstrap — the same treatment every published MC5/MCL result gets. The live 180-trade book
   motivates the gate; it is not the test (`handover_thin_tape_entries_20260918.md` §5.4).
4. **Interaction with the drift guard**: how many entries the drift guard already refuses; of
   those, how many the spread gate would also refuse (overlap, not double-counted savings).
5. **What it removes among the winners**, not only the losers — a gate that refuses the book's
   best trades is a loss even where it removes more losers than winners.
6. Deliverables follow the project's standing rule: a monday Result doc (plain-language verdict,
   tables in dollars, negatives bracketed), the raw `.txt`, and a published artifact page.

## 5. What decides whether it ships

**Decision point (Ben only), after the result:**

- **(a) Ship** as a production trader rule (`SPREAD_GUARD_PCT` enforced in `trader.py`, same as
  the drift guard).
- **(b) Study-only** — measured and reported, not enforced live.
- **(c) Close** — the full-quote study does not support it.

Nothing in this document commits to (a); the threshold and the data source are fixed so the
study answers the question cleanly, not so the answer is chosen in advance.

## 6. Caveats — what this registration does not claim

- **The 2% figure comes from the live book's fills, which is n = 180 with one trade (CRBP)
  and two more (both AEHL) carrying most of the ≥2% bucket's loss.** The full-quote study is
  what tells us whether that holds on 2,000+ backtest entries; this document fixes the number
  so that study is not read backwards into the threshold.
- **This is not a re-open of the volume line.** See the header: closed by
  `thin_tape_RESULT_20260919.md` §8, not reconsidered here.
- **A row is written on every refusal** (`SKIPPED_SPREAD`), so a refused entry stays visible
  and distinguishable from "the strategy never fired" — same discipline as `SKIPPED_DRIFT`,
  `SKIPPED_THIN_BAR` elsewhere in the trader.

## 7. Timeline

1. **W03-0002 step 4 (this document):** register the gate; commit to git before step 5 starts.
2. **W03-0002 step 5 (Build & test chat):** run the full quote pull (G1); build and
   mutation-test the gate (G2); run the study against the full point-in-time book; write the
   Result doc, raw `.txt`, and artifact page.
3. **W03-0002 step 6 (Ben):** ship / study-only / close, per §5.
