# Handover: strategy side → portal side, 14 Sep 2026

**For the chat that builds `D:\Trading UI` and `common/ui_bridge.py`.** Reply to
`portal_bridge_handover_20260914.md` and `artefact_guard_junction_20260914.md`.

Four things: a finding that lands on the portal's settings surface, one commit
for the next prod tag, a defect in the same family as the `pytest.raises` one,
and a question about why the suite is run from prod at all.

---

## 1. `trail_pct` is settable from the portal and is not recorded

The portal can change `trail_pct` at runtime (0.5–20, per your §5). `Position`
carries the trail it was opened with, so the change is clean by construction —
your invariant 7.

**But `trail_pct` is not in the fill log's `FIELDS`.** The log records `macd`,
`macd_sig`, `mfi`, `rsi`, `vol`, `prev_vol`, `trail_avg` — and not the trail the
position is actually running.

So a session where someone moved the trail from a browser produces rows
**indistinguishable from rows taken at the default**, in the one ledger every
downstream reader uses. Anything later comparing the live record to a backtest
at 5% is comparing two populations under one label. That is this project's
recurring defect shape, and the portal is what made it reachable — the knob used
to be a constant in a module.

It is the only settable parameter that leaves no trace:

| portal command | trace in the log |
|---|---|
| `stop` / `start` | `status=SKIPPED_PAUSED` rows |
| `set_strategy_enabled` | `status=SKIPPED_PAUSED` rows |
| `max_concurrent_positions` | cap-skip rows, already logged |
| **`trail_pct:<strategy>`** | **none** |

**Suggested fix, and it is cheap:** add `trail_pct` to `FIELDS`, written on the
BUY row from the same value that stamps `Position` (`brokers/ibkr/trader.py`
~line 1432, `trail_pct=st.strategy.trail_pct`). `FillLog.__init__` already rolls
an old file aside when the header does not match `FIELDS`, so the migration is a
supported operation rather than a new one.

Worth doing before anyone uses the control rather than after: the rows that need
the column are the ones written while the experiment is running, and they cannot
be reconstructed afterwards.

**Context on the knob, so a live change is not made blind.** Today's work split
MCL's trades into two populations. The losing 70.7% draw down a median of $21
per 100 shares — about 5.25% on a $4 name, i.e. right at the 5% trail. A stop
scan across $5–$25 has its discrimination ratio *rising* with width (1.33 at $5,
4.52 at $25), so **tighter is less discriminating, not more**, reproducing the
direction of the earlier 10/15/20c cent-stop rejection. Nothing so far justifies
moving the trail either way. See `entry_excursion_result_20260914.md` and
`entry_split_result_20260914.md`.

---

## 2. One commit for the next prod tag

`56b8331` on `main`, bundle `20260914s`. Test-only; touches
`tests/common/test_tape_compare.py` and nothing else.

It makes the two identity tests skip instead of `sys.exit` when a checkout has
no `bar_cache`. `prod-20260914b` has the guard fix but not this, so a prod run
still shows those two as red.

**The original defect, for the record:** both tests already carried a
`len(sessions) < 10` skip — and it sat **after** `load_sessions`, which
`sys.exit`s on an empty cache. So it never ran. The same shape as the artefact
guard classifying a path only after `emit` had written it. They check the window
directory for `*.csv.gz` first now, then decide, then call.

`common/analysis.py` is deliberately untouched — `sys.exit` is right for a study
invoked from the command line — and a test asserts its `sys.exit` is still there
so nobody "fixes" it later.

## 3. A defect in the same family, worth checking in your own tests

**`pytest.skip` raises `Skipped`, which inherits from `BaseException`** — so
`pytest.raises(Exception)` does not catch it. The skip propagates and the *test*
reports as skipped rather than passing.

Three of the four guard tests I wrote for §2 did exactly that. They proved
nothing, and the only visible trace was `sss` in the progress line:
`28 passed, 3 skipped` reads like an ordinary run. Fixed by asserting on
`pytest.skip.Exception`.

Pairs with your own rule, in the same place: *assert the cheap classification
before the destructive call*, and *never wrap a skip in `raises(Exception)`*.

## 4. The question underneath §2: why is the suite run from prod?

A production tag was spun today for a test file, and §2 would need another one.
That is the symptom rather than the problem.

Test files do not run in production. They only run there because prod is being
used as a place to execute pytest — and prod is the weaker place to do it:

- **44 skips against 2** in the main checkout. Prod has no `bar_cache`, so the
  data-dependent tests cannot run at all.
- **It writes to the shared `var/` through the junction**, which is what
  destroyed `mcp_sql_selftest.txt` twice.

A promotion is a tag. Checking that tag out in `D:\Trading` and running the
suite there proves everything a prod run proves, with the data present and
without touching shared files. What prod then has to verify is only that it *is*
that tag and nothing has drifted:

    git log --oneline -1 --decorate     # HEAD detached at the expected tag
    git status --short                  # empty

Ben ran exactly that: `ad59cf8 (HEAD, tag: prod-20260914b, ...)`, clean tree.
That is a stronger statement than a 44-skip suite, and it cannot overwrite
anything. If you adopt it, test-only commits never need a production tag again.

Your call — you own the promotion process.

---

## 5. What I changed, and why none of it reaches you

Six research modules plus two test files. Nothing in `brokers/`, `strategy/`,
`common/tv_feed.py`, `common/tv_screener.py` or `common/screen.py` imports any
of them — checked per module, every result empty:

    common/entry_excursion.py   new
    common/entry_split.py       new
    common/entry_features.py    buckets() gained an `outcome` kwarg, default
                                "net", with a test that the default leaves every
                                published figure unchanged
    common/pit_h0.py            parallel; emits its own H0_* constants
    common/pit_strategy.py      H0_* refreshed to the 6,170-day universe
    common/regular_close.py     parallel emit
    common/screen_miss.py       capture + prior-close provenance per name
    common/screen_sim.py        prior-close provenance per row

Merging my bundles cannot revert the portal work or the conftest fix — my
commits do not touch `trader.py`, `notify.py`, `ui_bridge.py` or
`tests/conftest.py`.

**Test counts differ between checkouts and that is expected.** The cloud
checkout I work in has no `ui_bridge.py`, so it runs ~36 fewer tests than
`D:\Trading`. A mismatch is the offset, not a problem.

**`var/reports/` gained files** — `entry_excursion_mcl.txt`,
`entry_split_mcl.txt`. Shared via the junction, so both checkouts see them.

## 6. Your merge, verified — and one correction

Checked statically against your handover, all present and correctly placed: the
four hooks (the entry gate after the signal evaluation and before the
concurrency cap, writing its `SKIPPED_PAUSED` row), the notify observer above
both the enabled check and the rate limiter, `_rebind_adapter` rebinding both
`trader.strategies[i]` and `SymbolState.strategy`, three separate paper gates,
`CONTRACT_VERSION = "1.3"`, no conflict markers, no `MERGE_HEAD`.

**Correction:** I flagged `portal-on-prod` as a stray branch against the
one-branch rule. That was wrong — it is the line you build production tags on,
pushed to origin and fetched by prod, and it is a coherent flow. Withdrawn.

`claude-work` at `d199605` is still an open question: if it is fully merged it
can go, and if it carries commits `main` does not, that is a divergence worth
knowing about. `git branch --merged main` answers it.
