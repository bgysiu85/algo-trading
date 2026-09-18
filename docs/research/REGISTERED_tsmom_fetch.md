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

**Eleven mutations run against these, eleven caught.**

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
