# REGISTERED — stock news (dilution filings + press headlines) as an entry veto (H-N1) and an exit alert (H-N2) on the MCL/MC5 books; news-triggered entries (H-N3) NOT registered here

**2026-09-23/24, PRE-RUN, PRE-CODE.** No classifier exists beyond the read-only probe (`w03_0010_news_probe.py`, board commands on subitem 2). This document is committed to git before the classifier, the puller, or the study runner exist. Git's ordering is the claim (`PROGRAM_INDEX` §1: a hypothesis is registered before it is run).

Board: **W03-0010**, subitem 3. Parents: `claude/news_feed_options_20260924_RESULT.md` (the options memo, Ben's decision); `claude/raw/w03_0010_news_probe_20260924.txt` (the probe: both sources reachable at $0; all 8 recently-traded names carry a reverse-split or offering flag; the fix list this document resolves). Ben, 2026-09-24, in his words (via the options memo): source = **EDGAR + Alpaca/Benzinga**; first use = **veto + exit alert + news-triggered entries. Entries are registered as a separate hypothesis because they're a new strategy test.** Where this document and `PROGRAM_INDEX` §4 disagree, §4 wins and this file is the bug.

---

## In plain terms

The probe found that 7 of 8 recently-traded small caps had a dilution or reverse-split filing in the last 90 days — so a blunt "any dilution ever" veto would refuse almost the whole book, which on a strategy that already loses money is a filter rewarded for refusing everything rather than for selecting anything (`PROGRAM_INDEX` §4). This document fixes, before any result exists, a **narrow, dated rule**: veto only a fresh dilution *event* (an offering priced or proposed in the last 2 days) or a reverse split *filed* (not merely proposed) in the last 30 days — and tracks the ongoing "company has an active shelf" state as a separate, unscored label rather than folding it into the veto. It registers two things to measure — **should a new long be refused** (H-N1) and **should an open position be exited early on the same trigger** (H-N2) — on the 10,370 trades this project already has, at two data-source levels (EDGAR alone; EDGAR plus press headlines), so the study answers what the headlines add over the filings. A third idea, using news to *trigger* new entries, is not measured here: it needs a signal-generation rule that does not exist yet, and the closest thing tried on this project (Cameron's news-spike setups) already read negative before costs. I expect H-N1 and H-N2 to read NOTHING or REFUSED, for the same reason every other entry-side filter on these books has — the books lose money gross, so a filter can reduce the loss but not invert it — and §9 says so before the run.

---

## 0. PRE-RUN GATES — subitem 4 (build) does not start until every gate below is cleared, in order

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **This document is committed to git**, before the classifier or puller exist (subitem 3b, Ben). | Registration before code. |
| **G2** | **The classifier is built and unit/mutation-tested** with: (a) the exclusion list from the probe's own fix list — a "Bundle Offering" headline (product bundle, not a securities offering; the GM/PCG case) and a "regained compliance" delisting headline (the opposite of a new deficiency; the IMCC case) both classify as NOT FLAGGED; (b) HTML-entity (`&#39;` → `'`) and non-standard-hyphen (U+2011 `‑` → `-`) normalization before any keyword match; (c) 424B3 filings and proxy-only reverse-split filings (`DEF 14A` / `PRE 14A` / `DEFA14A`) held OUT of the scored trigger sets (§3) and reported only as descriptive labels; (d) EDGAR's `acceptanceDateTime` confirmed as Eastern Time, DST-aware, before it is used in any point-in-time join. | The probe flagged all four as open questions; none has been checked. A join on the wrong timezone silently shifts every "before entry" cut by up to an hour. |
| **G3** | **Sanity check against the probe's own hand-read sample.** The classifier must flag every event a human already read off `claude/raw/w03_0010_news_probe_20260924.txt` (the 8 symbols' EDGAR filings, the 30-day headline sample) as the same type a human assigned it, and must score the two named false positives (G2a) as NOT flagged. | A control whose output can't be checked against a case someone already read by eye is not a control (`PROGRAM_INDEX` §4, "a control whose output is indistinguishable from the failure it detects is not a control"). |
| **G4** | **Both pulls are priced (no `--confirm`) then landed, per-symbol, not market-wide.** EDGAR's per-symbol filing history and Alpaca/Benzinga's per-symbol headline history, for every symbol in §2.1's population, full history back to the earliest trade. If either prices above $0 it stops for Ben. | The probe's market-wide headline pull (2,000 cap) covered about one day; a per-symbol pull is the only way to reach the population's full window, and both sources were sampled at $0 per-symbol already (probe step 2). |
| **G5** | **Live websocket latency is remeasured during US pre-market hours (04:00–09:30 ET)**, not the probe's midnight-NY-time sample. | The probe's "1 headline in 45s" reading was taken outside trading hours; the exit-alert's whole premise — that the alert can beat the move — is a speed claim, and it is currently unmeasured when it matters. |

---

## 1. The claims, exactly — two registered, one explicitly not

### H-N1 — entry veto

For MCL and MC5 **separately** (this project never pools them; different books, different friction, different trade counts), on the population in §2.1: **a new long entry is refused when, as of the entry timestamp, Trigger A or Trigger B (below) is true for that symbol.** Two source cells per book: **EDGAR-only** and **EDGAR + Alpaca/Benzinga headlines** (the trigger fires on whichever source reports it first). Accounting form only — refused entries are removed, not re-entered elsewhere — the same convention as `entry_gates.py`, `range_rank.py` and the spread gate (`REGISTERED_spread_gate.md`).

### H-N2 — exit alert

For MCL and MC5 separately, on the same population, **restricted to trades where Trigger A or Trigger B newly becomes true while the position is open**: simulate exiting immediately at the next bar's open (`gap_fills=True`, the project's standing fill rule) instead of waiting for the strategy's normal exit, and compare the simulated net to the trade's actual net. This is a **paired delta on existing trades**, not a filter, so it is scored differently from H-N1 (§5.2). Same two source cells.

### H-N3 — news-triggered entries: NOT registered in this document

Ben's decision names this as a first use, and `replication_pipeline_spec_20260919.md`'s own Stage-1 refusal list has a category for exactly this state: **"construction not fully specified in public."** No rule exists yet for what would generate a *new* signal from news alone — which headline/filing types qualify, whether it overlays the existing MCL/MC5 screen or replaces it, what sizes and exits it uses. Registering thresholds around an unspecified construction is how a study becomes unfalsifiable. **What is fixed now:** H-N3 stays blocked until a separate registration states the construction, and that registration inherits a poor prior — the closest analog this project has run, Cameron's news-spike setups within the MCL/MC5 family, already read negative before costs (`claude/news_feed_options_20260924_RESULT.md`). Scoring it is **subitem 4's classifier work minus the entry-generation rule**, which is a build task, not a research one; §11 leaves it off the timeline pending that spec.

---

## 2. Populations

### 2.1 Scored — the PIT ITCH v2 backtest book

`var/reports/chase_gate_trades.csv`, rows `book ∈ {MCL, MC5}` — the same **10,370** entries (**MCL 3,908 + MC5 6,462**) every 2026-09 gate study on this project scores (`REGISTERED_l2_entry.md` §2.1, `bseries_itch_RESULT_20260917.md`). Friction **$4.26** a round trip, reported also at **$1.00** and **$8.92** (`PROGRAM_INDEX` §4). **No holdout exists for these books** — both were built and cut many times before any lock — so this is in-sample on a heavily-searched book, which is why §7's multiplicity bar applies at full strength, same caveat as `REGISTERED_l2_entry.md` §2.1.

### 2.2 Descriptive, never scored — the live paper book

The **256** live round trips, 10 sessions, **2026-09-10 → 2026-09-23** (`claude/paper_cuts_20260924_RESULT.md`). Ten sessions is too few for a symbol-cluster bootstrap (`PROGRAM_INDEX` §4: "the sample is SESSIONS, not trades") and this book motivates the study, exactly as the live 180-trade book motivated the spread gate without being the thing that was scored. Reported the same shape W02-0013 used for its live table: outcome buckets (big win / small win / small loss / big loss, W02-0013's own cut points), Trigger A/B state at entry and during the hold, GRML's own six signals listed by name since they are what Ben asked about.

### Coverage, stated with every table

The 2026-09-14 EDGAR pull found SEC's current-day ticker map covers **80%** of BASIC-universe symbol-days (`PROGRAM_INDEX` item 33) — a different universe and a different date than §2.1's ITCH v2 book, so this is re-measured on the actual scored population in subitem 4, not assumed. Whatever the figure comes out to, the uncovered share is reported next to every bucket table as **a population the veto/alert cannot answer for**, never silently dropped — the parent doc's own commitment.

---

## 3. The triggers, exactly — fixed now, not fitted after seeing a bucket table

The probe's own finding is the reason these are narrow: 7 of 8 names carry a dilution/split filing somewhere in 90 days, so "any dilution event, ever" refuses almost everything and would pass `PROGRAM_INDEX`'s abstention trap by construction. Both triggers are **events with a short, stated window**, not an ongoing state.

**Trigger A — a fresh dilution event.** True at time *t* if, in the **trailing 2 calendar days** before *t*: a filing of type `{S-1, S-1/A, S-3, 424B4, 424B5, EFFECT, 8-K item 1.01, 8-K item 3.02}` was accepted, **or** a headline classified `OFFERING_PRICED` or `OFFERING_PROPOSED` was published.

- **424B3 is excluded from Trigger A.** It is a routine prospectus supplement filed under an *already-effective* shelf — WHLR filed 70 in 90 days — a continuous state, not a discrete event; tracked as its own descriptive label, **`ACTIVE_SHELF`** (≥ 3 `424B3` filings in the trailing 90 days), reported per bucket, never scored.

**Trigger B — a reverse split filed.** True at *t* if, in the **trailing 30 calendar days** before *t*: an `8-K` item `5.03` filing (the split takes effect) was accepted, **or** a headline classified `REVERSE_SPLIT` was published.

- **A proxy alone is not Trigger B.** `DEF 14A` / `PRE 14A` / `DEFA14A` ("check for reverse split") propose a vote that may not pass; tracked as **`PROPOSED_RS`**, descriptive only.

**Veto / alert condition = Trigger A OR Trigger B.** `DELIST_NOTICE` and `ATM`-only headlines are **not** a trigger — the parent doc's own event table treats a delisting notice as context (it often *precedes* one of the two triggers above) and an active ATM as a risk label, not an action — both are reported as descriptive columns beside the scored buckets, never folded into A or B. Nothing above is a threshold grid: each is a fixed sign (fires / does not), the same parameter-free form `REGISTERED_l2_entry.md` §3.1 uses and for the same reason — a threshold invites a search, and this book has already been searched enough (§2.1).

**Reported, descriptive, never scored:** the full recency table (0–1 day / 2–7 / 8–30 / 31–90 / none) for both trigger types, so the 2-day and 30-day cuts above can be read against the shape of the data without becoming a second, post-hoc rule.

---

## 4. Data sources

**EDGAR** — full text and filing index, per symbol, `SEC_CONTACT` set (fair-access rule: max 10 req/s; the existing puller paces at ~6.7/s and refuses to start without it). **Alpaca/Benzinga** — historical news per symbol (back to 2015 per the probe) plus the live websocket for the latency remeasurement (G5). Both priced at $0 per-symbol in the probe; G4 prices the full per-symbol pull before it lands. Both run on Ben's PC — `sec.gov` is blocked from the cloud session, and this is already the project's rule for external pulls (`PROGRAM_INDEX` §3).

---

## 5. What must be measured and reported

### 5.1 H-N1 (veto) — per rule cell (EDGAR-only, EDGAR+headlines), per book (MCL, MC5): four cells, six readings each, reusing `common.gate_study` unchanged (the same module W03-0002 and W02-0013 use)

1. **Two-denominator verdict:** per-trade gain ≥ $4.26 **and** per-symbol-day gain > 0 on the refused set vs kept set; a disagreement is a refusal (`PROGRAM_INDEX` §4).
2. **Both halves**, split at the median session of §2.1's own sample.
3. **Drop-top-3** on the delta.
4. **Symbol-cluster bootstrap** on the delta, P ≥ 0.95, 10,000 resamples.
5. **Abstention control — mandatory, not optional, on a losing book:** random removal of the same count of trades, 5,000 seeded draws, **seed 20260924**. Per `PROGRAM_INDEX` §4 ("on a losing book, a total-based reading rewards abstention"), the veto's per-trade gain must beat random removal's percentile, and because **four cells are scored** (2 sources × 2 books) the bar is Bonferroni-adjusted: the **99.375th percentile** (0.05 / 4) of the random-removal distribution, not the 95th.
6. **The marginal trade** — `(tot(veto) − tot(base)) / (n(veto) − n(base))` — at all three friction levels, reported beside the average per `PROGRAM_INDEX` §4's "the marginal trade, not the average."
7. **Fewer than half of the book's 20 best trades refused** — a filter that cuts the fat tail the strategy exists to catch is not a pass whatever its average does (`REGISTERED_l2_entry.md` §7 item 4).
8. **Overlap, reported only, never double-counted:** against the W03-0002 spread gate's refusals on the same order path.

### 5.2 H-N2 (exit alert) — per rule cell, per book: paired delta, not a filter

For every trade where Trigger A or B newly fires while the position is open: `delta = net(simulated news exit) − net(actual exit)`.

1. **Mean delta**, both halves, drop-top-3 on the delta — same shape as §5.1 items 2–3, applied to the paired series.
2. **Placebo control, in place of random removal** (a substitution has no "remove N trades" analog): for the same trades, replace the real trigger's elapsed time (entry → trigger) with a time drawn at random from the *other* triggered trades' own elapsed-time distribution, and simulate exiting there instead. 5,000 seeded draws, seed 20260924. The real trigger's mean delta must beat this placebo's **99.375th percentile** (four cells here too: 2 sources × 2 books).
3. **Symbol-cluster bootstrap on the delta**, P ≥ 0.95.
4. **How many trades this could even apply to**, reported first — if under ~30 trades carry a mid-hold trigger on either book, the reading is described as underpowered rather than scored as a pass or fail (`PROGRAM_INDEX` §4, "an n = 1 measurement is not a constant" — the same caution scaled up).
5. **Friction is unaffected** (one round trip either way); the delta is a pure price comparison and needs no friction ladder, unlike H-N1.

### 5.3 Reported, never scored (both hypotheses)

- The four cells run again on the 374⁠-⁠style live-signal population (§2.2), same shape as `REGISTERED_l2_entry.md` §5.2 — described, not a rule.
- GRML's six signals, named, with Trigger A/B state at entry and through the hold, since that is what motivated Ben's question.
- The `ACTIVE_SHELF` and `PROPOSED_RS` descriptive buckets (§3), and the full recency table.
- `DELIST_NOTICE` / `ATM`-only headline counts, by book, unscored.

---

## 6. The bar — a rule is carried forward (subitem 6/7) only if, on at least one book

1. `gate_study.verdict` (or the paired-delta equivalent) passes;
2. it beats the multiplicity-adjusted control (§5.1.5 / §5.2.2);
3. G2–G5 all cleared;
4. (H-N1 only) fewer than half of the 20 best trades are refused.

### 6.1 Retirement clause

If H-N1 and H-N2 both fail on both books at both source levels, **dilution/reverse-split filings and headlines, at these windows, are retired as MCL/MC5 entry or exit signals**: no re-fit of the 2-day or 30-day cut, no threshold sweep, no combination with the spread gate, without a fresh registration stating why the fixed windows above were wrong rather than merely unlucky. H-N3 is unaffected either way — it was never scored here (§1).

### 6.2 What this registration does not claim

1. **Priced before pulled.** G4 runs without `--confirm` first; a non-zero price stops for Ben rather than silently narrowing the population.
2. **EDGAR's ticker map is current-day, not point-in-time** (probe finding) — a symbol that changed tickers or delisted between the trade date and today can mis-map or miss coverage; §2's coverage figure is what's uncovered, not what's wrong, and the two are not the same thing.
3. **This is a filter and a substitution on already-losing books, not an edge claim.** MCL and MC5 lose money gross (`PROGRAM_INDEX` §4); H-N1 can at best reduce the loss, and H-N2 can at best make individual exits cheaper. Neither can turn the books' sign.
4. **Corporate-action data, not price/volume data.** Every other entry-side filter this project has tried (first-entry skip, range rank, cold veto, the pullback cell, the entry sweep, Running Up) is derived from the same bars the strategies trade on and has read as random removal or worse. This is a genuinely different input, which is the reason it is being run despite §9's prediction, not a reason to expect a different result.
5. **H-N3 is not deferred forever by default** — it is deferred pending a specific missing document (a construction registration), named in §1, not pending "further thought."

---

## 7. Multiplicity, stated once

Eight cells are scored in total: H-N1 (2 books × 2 sources) + H-N2 (2 books × 2 sources). Each family's control (§5.1.5, §5.2.2) is adjusted to its own four-cell family, not to all eight together, because H-N1 and H-N2 ask different questions of the same data and a pass on one says nothing about the other. This mirrors `REGISTERED_l2_entry.md` §5.1.2's reasoning at a smaller scale (three rules there, four cells here).

---

## 8. What a pass would buy

Nothing is deployed on a pass. A pass on H-N1 and/or H-N2 earns (a) the engine-form backtest (refused entries free the concurrency slot; W02-0013 subitem 8's pattern), and (b) a live-shadow registration — the veto/alert computed and logged in the trader without acting on it, per `PROGRAM_INDEX`'s standing rule that a session-level or event-level rule needs its own parity test before it goes near a live order (the MC5 apex-gate defect is why). Subitem 7 is gated on this, not on the result alone — the same shape as every other gate in this project (spread gate §5, L2 §8).

---

## 9. Predictions, scored either way

- **G3 sanity check: PASSES** (the classifier is built to match a hand-read sample; a miss here is a classifier bug, not a finding).
- **G5 latency: near-instant during RTH**, materially faster than the probe's off-hours sample — Benzinga's business is speed.
- **H-N1, both books, both sources: NOTHING or REFUSED.** Mechanism: the books lose gross, so any filter's per-trade gain has to clear the *abstention* bar, not just be positive, and every prior filter on these books has failed exactly there.
- **H-N2: UNDERPOWERED** on at least one book — mid-hold triggers (a filing landing while a multi-minute MCL/MC5 trade is already open) are the rarer case; §5.2.4 says this is reported as such rather than forced to a verdict.
- **No secondary "real but insufficient" prediction is made** — that form of hedge was wrong twice on ORB's amendments H and I (`PROGRAM_INDEX` §4) and is not repeated here.

---

## 10. What would make this run wrong

- Pulling or reading any filing or headline before this document is committed (G1).
- Reading a trigger without the exclusions and normalization in G2, or before G3's sanity check has passed.
- Scoring anything G4 has not landed at a confirmed price.
- Widening the 2-day or 30-day window, re-including 424B3 or proxy-only filings in the scored triggers, or changing the friction ladder after seeing a bucket table. Each is a new registration.
- Quoting a veto or alert cell without its multiplicity-adjusted control beside it.
- Treating H-N3 as scored by this document in any form.

---

## 11. Timeline — board item W03-0010, one subitem per step

| # | Step | Who | Rec. model / effort |
|---|---|---|---|
| 1 | Decide source + first use | Ben | — (Done) |
| 2 | Probe: Alpaca news + EDGAR reach | Build & test chat | Sonnet / Low (Done) |
| 3 | **Register the study (this document)** | Research & spec chat | Sonnet / High (Done, today) |
| 3b | Commit this document to git, before subitem 4 starts | Ben (commands on the subitem) | — |
| 4 | Build the classifier (G2–G3), the per-symbol pullers (G4), the study runner, and its tests | Build & test chat | Sonnet / High |
| 5 | Run the study locally (G5, then §5) | Ben | — |
| 6 | Result doc (H-N1 and H-N2, both books, both sources, dollars, brackets, sample trades) | Research & spec chat | Sonnet / Medium |
| 7 | Only if §6 clears (per §8): live-shadow veto + exit alert in the trader, a flag in the portal | Build & test chat | Sonnet / High |

H-N3 (news-triggered entries) is not on this timeline — it needs its own construction registration first (§1), to be opened as a new subitem once that spec exists.
