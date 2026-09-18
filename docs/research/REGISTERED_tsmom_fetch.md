# REGISTERED — the TSMOM data pull

**Committed before `common/tsmom_fetch.py` is run with `--confirm`.** This is
the module that spends, so it gets its own registration rather than riding on
the strategy's.

Parent: `docs/research/REGISTERED_tsmom.md` (gates, spec, criteria) and its
**§0.1 amendment A** (scope). Spec: `claude/tsmom_spec_20260917.md` §4, §5.
Measured price: `claude/raw/tsmom_price_20260917.txt`.

---

## 1. What is bought, exactly

| | | |
|---|---|---|
| Dataset | **GLBX.MDP3** | read from `metadata.get_dataset_range`, never hard-coded |
| Range | **2010-06-06 .. 2026-09-17** | the vendor's full history, confirmed 2026-09-17 |
| Bars | **`ohlcv-1d`**, `continuous`, `<ROOT>.c.0` and `.c.1` | front contract + the next one |
| Roll calendar | **`definition`**, `parent`, `<ROOT>.FUT`, **one session per month** | the 15th, or the nearest earlier day the vendor has |
| Roots | **ES RTY GC SI HG CL NG 6E 6A 6B 6J ZN** | spec §2.2; `TN` only with `--with-tn` (rates arm (b)) |
| Archive | `E:\Databento\GLBX.MDP3\` | outside the repo, per `PROGRAM_INDEX` §3 |
| **Estimate** | **$3.65**, 1.501 GiB | $1.11 bars + $2.54 definition |
| Ceiling | `--max-cost` **$5.00** | aborts above it |

**The monthly grid is the 15th of each month, derived from the range**, not a
sample count chosen to hit a price. A contract is listed months to years before
expiry and stays listed, so any *session* in the month carries the same
expiration dates; the 15th avoids month-end and month-start holiday clustering.
A test pins the grid at 180–190 samples, because if it drifts the **$3.65
recorded in amendment A stops describing the pull**.

### 1.1 Non-sessions — the defect the first live run found, 2026-09-18

The first `--confirm`-less run stopped at:

```
pricing failed, nothing downloaded: 422 symbology_invalid_request
None of the symbols could be resolved
```

**55 of the 190 samples landed on a Saturday or Sunday** — the third, 2010-08-15,
being a Sunday. A one-day window over a non-session day resolves nothing.

**This section and the module docstring both already said the grid stepped off
non-sessions. Neither the code nor a test did.** That is the second property in
two days asserted in prose and not implemented (the other:
`common/tsmom_holdout._normalise`, `REGISTERED_tsmom` §6.1), and it is
`PROGRAM_INDEX` §5 — *a report must read its own inputs, not assert them.*

Now implemented, and registered:

- **Weekends are known in advance** and the sample steps **back** to the Friday,
  which keeps it inside its own month. A test asserts zero weekend samples and
  that every sample's day-of-month is ≤ 15.
- **Holidays are not known** — the exchange calendar is not in hand — so an
  unresolvable day is **retried forward up to three days**. The retry is narrow:
  only a symbology miss. Any other failure still aborts, because a blanket retry
  turns a mis-scoped request into a slow one instead of a loud one.
- **A month that still cannot be placed is reported by root and month**, never
  skipped silently, and **more than 2% of samples unplaceable aborts the run** —
  that is a calendar problem, not a few holidays.

And the error now **names the failing job** (root, schema, dates, symbols,
symbology). The first version's did not, which is why a 422 whose cause was a
Sunday could not be diagnosed from its own output.

### 1.2 A defect in the METHOD, not the code, 2026-09-18

Worth recording separately because it makes every mutation result in this line
provisional until re-run.

The sweeps here rewrite the module in rapid succession — mutate, run pytest,
restore, mutate again. **Python invalidates a `__pycache__` entry on the
source's mtime and size, and successive writes inside one clock second defeat
that.** After a sweep restored the original file, the next run was still
executing the bytecode of the last mutant (`share > 0.50`). The symptom was a
test failing identically alone and in the suite, against source that was
correct when read — and a commit that went in with it failing, because the
`echo EXIT=$?` after the redirect did not gate the commit. `PROGRAM_INDEX` §5
already has that one: *a test that pipes through `| tail -1 &&` masks its exit
code.*

**Every mutation sweep in this line was re-run with `python3 -B` and
`-p no:cacheprovider`, after clearing `__pycache__`.** All verdicts held —
**12/12 on `tsmom_data_price`, 10/10 on `tsmom_holdout`, 14/14 on
`tsmom_fetch`** — but they were not trustworthy until they had been.

The general form, for `PROGRAM_INDEX` §5: **"the source says X" is not evidence
that X ran.** It is §5's "a report must read its own inputs, not assert them"
one layer down — the interpreter was not reading its inputs either.

*(No test enforces this: a check that the sweep used `-B` can only inspect its
own file and cannot fail for the right reason. `common/holdout.py` set the
precedent — a promised counter that nothing incremented was removed rather than
shipped as decoration.)*

### 1.3 Pricing is SAMPLED, not summed — the second live run, 2026-09-18

```
pricing failed on NG definition 2023-01-13 -- nothing downloaded:
504 The remote gateway timed out.
```

The error named its job, which §1.1 had just made it do. What it named was a
**structural** problem rather than a bad request: the pull priced **every job
individually — 12 roots × 190 monthly samples = 2,280 metadata round trips,
plus 12 for the bars — before downloading a single byte.** At a few hundred
milliseconds each that is ten minutes of pricing, and NG 2023-01-13 was call
1,304 of 2,292. Nothing was lost. Nothing could ever finish, either: any one
transient failure anywhere in that sequence aborted everything.

**Definition is now priced the way the registered $3.65 was produced** —
`tsmom_data_price --scope lean` samples ONE representative session per root and
multiplies. Same methodology as the registered figure, **24 calls instead of
2,292**. The per-session cost is exact; the count is arithmetic. Bars are one
call each regardless and are still summed. Jobs already on disk are still
excluded from both the count and the total.

**And a transient gateway failure is now retried** with backoff — 504, 502,
503, 429, timeouts, connection resets. The retry is as narrow as the symbology
one: anything else still aborts, because a blanket retry turns a mis-scoped
request into a slow failure instead of a loud one.

**Holiday handling moved to download time** as a consequence. The grid is built
weekend-free; a definition day that will not resolve when fetched moves forward
up to three days; a month that still cannot be placed is named, and above 2% the
run says plainly that the roll calendar has holes and the engine should not be
run on the archive until that is explained.

**Sixteen mutations, sixteen caught** — one only after the sweep found that a
test asserting the error names its job had been **lost in a block replacement**
while this restructure was written. The sweep earning its keep, and an argument
for running it after a refactor rather than only after a fix.

### 1.4 RTY does not have the history the spec claims — the third live run, 2026-09-18

```
pricing failed on RTY definition: none of the first four monthly samples
could be resolved -- nothing downloaded
```

**RTY did not exist on CME Globex in 2010.** Russell 2000 futures were listed on
**ICE**; CME relisted the E-mini for trade date **2017-07-10**
([CME SER-7960](https://www.cmegroup.com/notices/ser/2017/07/SER-7960.pdf)). So
`RTY.FUT` has no GLBX history for roughly **seven of the sixteen years**.

**This is a defect in the SPEC, not in the code.** Selection rule 3 of
`claude/tsmom_spec_20260917.md` §2.1 states that every root *"has continuous
GLBX.MDP3 daily history from the dataset's start."* For RTY that is false, and
nothing checked it — **the third property in two days asserted in prose and not
verified** (§1.1's non-sessions, `REGISTERED_tsmom` §6.1's January boundary, and
now this). The pattern is consistent enough to be worth naming: *the assertions
this project writes about its own inputs are where its defects live.*

**What changes, and what does not:**

- **The instrument set is unchanged.** RTY stays. The §2 warm-up rule (261
  returns before an instrument enters) already handles a late start correctly —
  it enters the book in 2018 and not before.
- **What changes is the honest description of the book**: it has **fewer markets
  in its early years** than the registration implied. The equal-weight portfolio
  is over *instruments with a live signal*, so 2010–2017 is a smaller,
  less-diversified book than 2018 onward. **Every result must be read with that
  in mind**, and §3's coverage output is now the thing that says so.
- **No substitution.** Swapping RTY for something with longer history, now, after
  seeing which root failed, would be choosing an instrument from a property of
  the data. Rule 3 is amended to describe reality rather than the set being
  changed to fit the rule.

**Amendment B, PRE-RUN:** selection rule 3 of spec §2.1 is corrected to read —
*its full-size CME predecessor has GLBX.MDP3 daily history, and where that
history begins after the dataset's start, the root enters the book when the
warm-up rule admits it and the coverage table reports the gap.*

**And a root's first session is now DISCOVERED rather than assumed.** The pull
probes the first four monthly samples, then a yearly stride, then narrows within
the year that hits — all free metadata lookups, one call for a root that
resolves immediately. A late listing is reported as **LATE LISTINGS** with the
years missing, and recorded in the manifest as `late_listings` so a report can
**read** it. A root that resolves at *no* session in the whole range is a wrong
root, not a late one, and still aborts.

*(The discovery's three loops originally repeated the same error path. Mutation
testing showed the copy in the first loop could not fail independently — delete
it and the stride or the narrowing scan reaches the same failure and aborts
identically. `PROGRAM_INDEX` §4: a second condition that cannot fail
independently of the first is not a second condition. The three were collapsed
into one `_probe`.)*

## 2. The guards, and what each is for

1. **Estimate first, always.** The total prints before anything transfers.
2. **`--confirm` or nothing downloads.** A test asserts a run without it
   transfers zero bytes.
3. **`--max-cost` aborts, it does not warn.** A large estimate means the scope
   moved, not that the data got expensive — the same range once priced at
   $1,500 with `ALL_SYMBOLS` and under a cent scoped right, and this project's
   own first TSMOM scoping came to $71.62 for the same inputs that cost $3.65.
4. **Jobs already on disk are skipped and are NOT in the printed estimate.**
   Billing is on retrieval, so re-running is free by construction. An estimate
   that quotes the whole pull while intending to download a tenth of it teaches
   the reader to ignore estimates.
5. **A pricing failure aborts before any download.** Partial pricing plus a
   spend is the worst combination available.
6. **The key resolves through `common.secrets_util`.** Never the environment
   directly — `tsmom_data_price` shipped with its own reader on 2026-09-17,
   sent an `op://` reference to the vendor, and got a 401 that reads like a
   revoked subscription.
7. **Exceptions are scrubbed** before printing. A Telegram token once leaked
   out of `common/notify.py`'s exception handler.

**Fourteen mutations run against these, fourteen caught** — under §1.2's re-run conditions, not the first pass's.

## 3. The manifest, and why the pull writes one

`E:\Databento\GLBX.MDP3\manifest_tsmom.json` records, per pull: the date, the
range, the roots, jobs run against jobs planned, the estimate, the schemas and
symbology, and **which registration authorised it**.

`PROGRAM_INDEX` §1: *a report names the tape it read, and a grid refuses a tape
it was not registered on.* A report cannot do that unless the archive says what
it is. The ORB pre-flight printed an EQUS.MINI caveat over XNAS.BASIC numbers
**and two tests asserted that paragraph**, so the suite pinned the bug. The
manifest exists so every TSMOM report **reads** its provenance instead of
asserting it.

## 4. What this pull is NOT

- **Not the deferred months.** `c.2` and beyond are not bought. A later question
  about the term structure or the roll yield is a **new registration** and a new
  estimate, not a flag on this one.
- **Not intraday.** `ohlcv-1d` only. The strategy is monthly.
- **Not the equity archive.** Nothing here touches `E:\Databento\XNAS.*` and
  nothing there is read by TSMOM.
- **Not authorisation to run a backtest.** G3 (the rates arm) and the engine's
  own tests are still open. Buying the data clears G2 and nothing else.

## 5. The one thing to check after it lands

**The roll calendar has two independent sources and they must agree** —
amendment A's control. `definition` gives each contract's `expiration`;
Databento's `c.0` changes instrument at expiry, so the **symbol-change dates in
the bars** are a second reading of the same calendar.

**The first thing the engine does with this archive is compare them, and refuse
to proceed on disagreement.** Not warn — refuse. A continuous series that looks
right while booking the wrong contract is `PROGRAM_INDEX` §3's signature
failure, and spec §3.1 has it happening already: a free pull whose only job was
to size a table put a **−46.3% roll break** into natural gas and a 15-point
error into the divisor of its own position size.

Disagreement is expected in a small number of places — a vendor's calendar roll
need not land on the exchange's last trade date — so the run reports **the
count, the roots and the dates** rather than a yes/no, and the threshold for
"refuse" is registered here **before the numbers are seen**:

> **More than 2% of rolls disagreeing by more than one session, on any single
> root, stops the run.** Under that, every disagreement is listed in the report
> and the registered `definition` date is the one used.
