# Handover: TSMOM, end of 2026-09-18

**From:** the TSMOM chat, which has owned the line since 2026-09-17.
**State:** registered, tooled, tested. **No backtest code. No result. One gate
open and one unverified fact.**

**Read in this order:** `claude/tsmom_spec_20260917.md` →
`docs/research/REGISTERED_tsmom.md` → `docs/research/REGISTERED_tsmom_fetch.md`.
Everything below is a summary of those three and does not supersede them.

---

## 0. The one-paragraph version

TSMOM is specified from Moskowitz/Ooi/Pedersen (2012), registered with nine pass
criteria and a locked holdout, and the data is priced and buyable. **Three of
four PRE-RUN gates are cleared.** What is NOT done: the rates arm is Ben's
choice (G3), the engine does not exist, and **nobody has confirmed the data pull
actually completed.** Separately and more importantly: **a volatility-targeted
book of this kind does not fit a $22k account at any data price**, so measuring
this strategy and trading it are two different decisions and only the first is
in progress.

---

## 1. Gate status

| Gate | State |
|---|---|
| **G1** — the paper read off the page | **CLEARED 2026-09-17.** Ben allowlisted `pages.stern.nyu.edu` / `w4.stern.nyu.edu`; all five ★ lines verified. |
| **G2** — Ben has seen the cost and said yes | **CLEARED 2026-09-18** at the measured $3.65 (bracket: see §4). |
| **G3** — the rates arm | **OPEN. Ben's call, not the backtest's.** (a) full-size ZN, ~$2,062 maintenance ≈ 9% of equity for one contract; (b) MTN, price-quoted micro but referencing the Ultra 10-year and live only since 2024-03-25; (c) no rates sleeve, an 11-market book. Does not block the pull; blocks the run. |
| **G4** — the holdout cut and enforced in code | **CLEARED 2026-09-18.** `common/tsmom_holdout.py` + tests, ten mutations, ten caught. |

---

## 2. What exists in the repo

| Path | What it is |
|---|---|
| `claude/tsmom_spec_20260917.md` | The strategy from the paper. Every claim tagged [P]/[D]/[E]/[M]. §3 is the capacity finding. |
| `docs/research/REGISTERED_tsmom.md` | Gates, deployed spec, nine criteria, holdout, multiplicity budget, a written prediction. Amendment A (scope) and §6.1 (the holdout's own defect). |
| `docs/research/REGISTERED_tsmom_fetch.md` | The pull's own registration, and §§1.1–1.5 — every defect the live runs found. |
| `common/tsmom_data_price.py` | **Cannot spend.** No download path at all; a test scans the AST. 12 mutations, 12 caught. |
| `common/tsmom_holdout.py` | The 2022-01-01 lock, spend-once ledger, refuses `--limit` and the equity `holdout.json` by name. 10/10. |
| `common/tsmom_fetch.py` | **The only module that can spend.** Estimate-first, `--confirm`, `--max-cost`, skips what is on disk, retries transients, discovers late listings. 16/16 and 5/5 on the later pass. |
| `tests/strategy/test_tsmom_*.py` | 3 files. `tests/strategy` 503 passed at last full run. |
| `claude/raw/tsmom_price_20260917.txt` | The raw $3.65 estimate. |

**Bundles delivered:** `tsmom-20260917a..f`, `tsmom-20260918a..e`. Ben's tip
merged `e` at `f7276b5`.

---

## 3. The findings that matter beyond the tooling

### 3.1 The strategy does not fit the account — spec §3

Measured 2026-09-17 from free data, **before anything was bought**. At $22,129
equity, with the paper's sizing (40% ex-ante vol per position, equal weight):

- **Eight of thirteen markets cannot reach half a micro contract.** Target sizes
  run 0.02 (silver) to 1.43 (GBP).
- A forced one-lot book is **~173% portfolio volatility against the paper's 12%**
  and **108% of equity in maintenance margin**.
- **All thirteen markets feasible needs ~$532,000** (silver binds); ~$200,000
  without silver and Nasdaq.
- At $22k the largest book under a 15% vol cap is **five markets — four FX
  micros plus one other.** One and a bit asset classes.

**This is registered as a measurement, not a criterion** (registration §5),
because failing it would end a measurement worth making anyway. But it is the
single most important fact in this line and it should not get lost under the
tooling: **the crisis alpha, the commodity trends and the bond trends — the
entire reason `diversifier_candidates` §5.1 ranked TSMOM top — are the parts
that do not fit.**

### 3.2 RTY has seven years less history than the spec claimed — fetch §1.4

Russell 2000 futures were on **ICE** until CME relisted the E-mini for trade
date **2017-07-10** (CME SER-7960). Selection rule 3 asserted every root had
history from the dataset's start. **Amendment B corrects the rule; the
instrument set is unchanged** — swapping RTY out after seeing which root failed
would be choosing an instrument from a property of the data. The warm-up rule
already handles it. What changes is the honest description: **the book has fewer
markets in its early years**, so 2010–2017 is smaller and less diversified than
2018 onward, and every result must be read that way.

**Whether other roots list late is not yet known.** The pull now discovers and
reports it; nobody has read that output.

### 3.3 A roll break appeared before any strategy code existed — spec §3.1

Building the volatility estimates off front-month continuous series put a
**−46.3% single-day return into natural gas** on 2026-01-27. It is a roll break,
not a price move, and left in it takes NG's ex-ante vol from **41.8% to 56.7%** —
a 15-point error in the number that divides the position size. `PROGRAM_INDEX`
§3's signature failure, arriving on a free data pull whose only job was to size
a table. **The roll rule in spec §4 is not boilerplate.**

### 3.4 Databento's cost shape, worth knowing before the next futures pull

Measured on GLBX.MDP3: **`ohlcv-1d` ≈ $191/GiB, `definition` ≈ $1.75/GiB** — 109×
cheaper per byte, but `definition` is republished for **every listed instrument
every session**, so there is ~260× more of it. The first scoping came to
**$71.62 / 29.03 GiB**, of which $50.52 was definition. Scoped to what the
strategy reads — front+next contract via `continuous`, roll calendar sampled
monthly — the same inputs cost **$3.65**. And **ES is not representative**: 13
roots at ES's size would be 1.2 GiB, not 29. NG and CL are 51% of the bill.

---

## 4. The data

**Registered estimate $3.65 / 1.501 GiB. The pull's own estimate on 2026-09-18
read $3.01 / 1.127 GiB.** Both are sampled, from opposite ends of the range —
see fetch §1.5. The true cost is bracketed; no gate behaves differently at
either figure.

**UNVERIFIED, and this is the first thing to settle next session:** Ben was given
`--confirm` at 22:00 and the outcome was never read back. The archive lives on
`E:\Databento\`, which is not a folder this chat can reach.

```
Get-Content "E:\Databento\GLBX.MDP3\manifest_tsmom.json" | Out-File -FilePath "D:\Trading\Claude outputs\tsmom_manifest_20260918.txt" -Encoding utf8
```

That file answers: jobs run against jobs planned, the `late_listings` map, and
whether anything failed. **Until it is read, "the data is bought" is an
assumption, not a fact** — which is the same class of claim this whole line has
been catching itself making all week.

---

## 5. What the next session does, in order

1. **Read the manifest.** Confirm the pull, record the ACTUAL against the
   estimate in fetch §1.5, and find out which roots beyond RTY list late.
2. **G3** — ask Ben for the rates arm. Not from a backtest.
3. **The roll cross-check, before any return is computed.** Two independent
   readings of the roll calendar: `definition`'s `expiration`, and the dates
   `c.0` changes instrument. **Registered threshold, fixed before the numbers
   are seen: more than 2% of rolls disagreeing by more than one session, on any
   single root, stops the run.** This is the first thing the engine does.
4. **The engine**, with hand-built tests for: roll handling (a synthetic
   two-contract series where the continuous series and the held-contract book
   must differ by exactly the gap); the volatility estimator (`pandas` path
   against a hand-built weighted sum — `bias=True` versus `bias=False` is a
   one-flag difference that produces a plausible number); and integer contracts.
5. **Then the run**, on the training side only. `split_months` is the one
   implementation and every runner calls it.

---

## 6. The pattern this line kept hitting, for `PROGRAM_INDEX` §5

**Five defects in two days, and four of them were the same defect.** A property
was stated in prose — a docstring, a spec rule, a registration section — and
nothing implemented or checked it:

| Where | The claim | The reality |
|---|---|---|
| `tsmom_holdout._normalise` | "the correct side of a January 1st boundary either way" | `"2022-01" >= "2022-01-01"` is False. **The first month of the holdout read as training.** |
| `tsmom_fetch.definition_days` + fetch §1 | the grid "steps off non-sessions" | 55 of 190 samples landed on a weekend. |
| spec §2.1 rule 3 | every root "has history from the dataset's start" | RTY has none before 2017. |
| the sampled estimate | "the measured figure" | two figures from opposite ends of the range. |

Proposed entry: **"the assertions a project writes about its own inputs are
where its defects live."** §5 already has *a report must read its own inputs,
not assert them*; this is the same rule applied to specs and docstrings rather
than reports.

**And two defects in the METHOD, both recorded in fetch §1.2:**

- A **stale `__pycache__`** made every mutation verdict provisional: successive
  writes inside one clock second defeat mtime-based invalidation, so a
  "restored" module kept running the last mutant's bytecode. All sweeps were
  re-run with `python3 -B` and a cleared cache; **all verdicts held** (12/12,
  10/10, 16/16) but were not trustworthy until they had been. General form:
  **"the source says X" is not evidence that X ran.**
- **A commit went in with a failing test**, because `pytest > log; echo
  "EXIT=$?"` reports the status without gating the commit. §5 already carries
  this from 2026-09-16. It has now happened twice.

**A third, worth adding:** run the mutation sweep **after a refactor**, not only
after a fix. One sweep caught that a test had been silently **lost in a block
replacement** — the code was fine and the guard was gone.

---

## 7. Open items this line hands back to the index

- **TSMOM** (`PROGRAM_INDEX` §7 item 19) — no longer "unbuilt". Registered,
  tooled, not measured.
- **Item 23, cancel the Databento subscription.** TSMOM is a second claim on it,
  specifically on the **16-year L0 history the $199 Standard plan provides**.
  Cancelling before this archive is complete turns a $3 pull into a metered one.
- **`secrets_util` is the one credential resolver, and nothing enforces it
  repo-wide.** `tsmom_data_price` grew its own environment reader on 2026-09-17,
  sent an `op://` reference to Databento and got a 401 that reads like a revoked
  key — the third time that trap has fired. There is now a guard **in that one
  module**. A repo-wide rule in §1 and a scan like `test_encoding_guard.py`
  would close it properly. **Not this chat's to add.**
- **Databento's per-schema cost shape** (§3.4) belongs next to the ALL_SYMBOLS
  note in §1, because the next futures pull anyone scopes will meet it.

**Doc names for the index:** `claude/tsmom_spec_20260917.md`,
`docs/research/REGISTERED_tsmom.md`, `docs/research/REGISTERED_tsmom_fetch.md`,
`claude/raw/tsmom_price_20260917.txt`, `claude/handover_tsmom_20260918.md`.

---

## 8. What is NOT claimed

- **No backtest has been run. No return has been computed. There is no result.**
- The archive's completeness is **unverified** (§4).
- The capacity finding (§3.1) says nothing about whether the strategy works —
  only that trading it at $22k is a different question from measuring it.
- Every figure in §3.4 is from **this account's plan**; `get_cost` respects flat
  rate plans and another plan would price differently.
