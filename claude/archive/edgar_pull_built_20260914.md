# The EDGAR pull — built, not yet run

**Date:** 2026-09-14
**Module:** `common/edgar_shares.py` · **Tests:** `tests/common/test_edgar_shares.py` (37)
**Bundle:** `20260914v`, ref `main`
**Status:** built and tested against fixtures; **no live request has been made**

---

## Why it is three steps and not one

`--coverage` costs **one request**. It asks the only question that can
invalidate the other 2,123: *does SEC's ticker map contain the symbols this
universe actually traded?*

That is not a formality. The map SEC publishes is **current-day**, and 43% of
this universe's 2,123 symbols appear on exactly one session — disproportionately
the delisted, renamed and acquired. If a third of them are missing, a full pull
produces a table with a third of its rows absent, and **an absent row in a join
looks exactly like a symbol that failed a filter**. That is this project's
recurring defect in a new costume, and measuring the hole costs one request
against ten minutes of digging one.

`--pull` then fetches one concept per matched symbol and caches every response
on disk, so an interrupted run resumes and a re-run is free.

`--asof` joins facts to the universe under the point-in-time rule and is the
**only** step that produces a number anything else may use.

## The point-in-time rule: `filed`, not `end`

Every XBRL fact carries two dates. `end` is what the figure is *as of*; `filed`
is when it became public. A 10-Q with `end=2026-06-30 filed=2026-08-14` **was
not knowable on 2026-07-01**, and joining on `end` would hand a July backtest a
number that did not exist for six more weeks.

`shares_known_at` therefore selects the greatest `filed` that is `<=` the session
date and **never consults `end` when choosing**. Amendments fall out correctly:
a restatement is a later `filed`, so it takes over from its own filing date and
not one day earlier. Before any filing the answer is `None`, not the oldest fact
— a recent IPO genuinely had no public share count, and substituting a later
figure is the same leak wearing a different hat.

## Two things it refuses to do

**1. It will not call this float.** EDGAR publishes shares **outstanding**.
Float is outstanding less insider, affiliate and restricted holdings, and on a
recent IPO or a founder-controlled microcap the two differ by an order of
magnitude — which is precisely the population this project trades. Outstanding
is an **upper bound**: useful as a ceiling test (a name with 400M shares
outstanding cannot be a low-float name), useless as a substitute near the
threshold. The sentence *"SHARES OUTSTANDING IS NOT FLOAT"* is printed in every
report and there is a test that fails if it stops being.

**2. It will not pretend the ticker map is point-in-time.** SEC publishes no
ticker→CIK history. So a symbol that has since been delisted, renamed, or whose
ticker has been **reused** resolves either to nothing (counted as a miss) or to
**whoever holds it today** (a plausible wrong number). `--asof` flags any
symbol-day that falls outside the filing history it was matched to, which
catches the blatant cases and does not catch a ticker handed between filers
inside the window. **That residual is stated in the report rather than argued
away.**

## What each step writes

| step | report | data |
|---|---|---|
| `--coverage` | `var/reports/edgar_coverage.txt` | — |
| `--pull` | `var/reports/edgar_pull.txt` | `var/edgar/shares_outstanding.csv` |
| `--asof` | `var/reports/edgar_asof.txt` | `var/edgar/universe_shares.csv` |

Coverage reports **both denominators** — symbols and symbol-days — because they
disagree by construction here and one rate would hide which. It lists **every**
miss, not a sample, because a truncated miss list is how a systematic gap reads
as a scatter of odd names. And it costs the pull before the pull runs.

`--asof` writes **one row per symbol-day including the ones with nothing
knowable**, with a reason (`no_cik`, `no_facts`, `before_first_filing`,
`known`, `stale`). Omitting them would make the output's own row count the
denominator, and a denominator that shrinks to fit turns 50% into 100%.

## Fair access and the contact address

SEC publishes a limit of 10 requests/second and requires a contact address in
the User-Agent. This sends **~6.7/s** and **refuses to start without
`SEC_CONTACT`** — the address is read from the environment, never defaulted and
never guessed from anything in the repo.

## Verification

37 tests, none touching the network — `Fetcher` takes its opener, clock and
sleep, so pacing and retry are measured rather than asserted in a comment. Two
drive `main()` end to end through all three steps, because a suite that never
runs the pipeline proves nothing (`entry_split` had 19 green tests and raised
`KeyError` the first time it was asked to run).

Five deliberate breakages were checked to fail it:

| mutation | caught by |
|---|---|
| join on `end` instead of `filed` | `test_a_fact_filed_after_the_session_is_invisible` |
| drop uncovered symbol-days | `test_a_symbol_day_with_nothing_knowable_is_a_row_not_a_gap` |
| truncate the miss list | `test_every_miss_is_printed` |
| match class shares without normalising | `test_a_class_share_matches_across_spellings` |
| stop retrying a 503 | `test_a_failure_is_not_cached_as_absence` |

Full suite: **2,334 passed, 2 skipped.**

## Why it has to run on Ben's machine

`sec.gov` and `data.sec.gov` are both refused by the cloud container's egress
proxy (`connect_rejected`), and the local workspace VM could not mount the
connected folders today. Neither is a property of the module.

## Next, once coverage is known

The hit rate decides whether the pull is worth running at all. Below roughly 80%
of **symbol-days**, the resulting table is too holed to filter on and the
question becomes whether a paid point-in-time reference is the only honest
route. Above it, `--pull` then `--asof`, and the first real use is a **ceiling
test**, not a float filter.
