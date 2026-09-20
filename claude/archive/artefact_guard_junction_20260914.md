# The artefact guard was defeated by the `var` junction — 14 Sep 2026

**Short version:** running `pytest` from `D:\TradingProd` overwrote
`var\reports\mcp_sql_selftest.txt` and created `var\reports\anything.txt`. Both
are the shared, real files. The guard in `tests/conftest.py` that exists to
prevent exactly this did not fire. Fixed; merge the bundle before running the
suite from prod again.

## What happened

`D:\TradingProd\var` is a junction to `D:\Trading\var`, so both checkouts write
the same files. The suite was run from the prod checkout to verify a promotion.
Four tests failed; two of them had already done damage by the time they failed.

`tests/test_report_guard.py` writes to `var/reports/...` and asserts the guard
refuses it. In prod the guard did not refuse, so the write landed on the real
file — 64 bytes containing the test's payload `x`.

This is the **second** loss of that file. The first, on 2026-09-07, is the
incident the guard was written for.

## Why the guard was silent

`tests/conftest.py` held:

```python
REPO = Path(__file__).resolve().parents[1]
PROTECTED = (REPO / "var", REPO / "bar_cache", REPO / "bar_cache_db")

rp = Path(p).resolve()          # resolves THROUGH the junction
rp.relative_to(root)            # root was never resolved
```

From prod, `var/reports/anything.txt` resolves to
`D:\Trading\var\reports\anything.txt`. The root is the literal string
`D:\TradingProd\var`. `relative_to` raises `ValueError`, the path is classified
as unprotected, and `emit` writes it for real.

From `D:\Trading` there is no junction, the two agree, and the guard works. So
it protected one checkout and not the other — which is worse than no guard,
because the working one teaches you to trust it.

## The second defect, in the test

```python
with pytest.raises(AssertionError, match="real artefact directory"):
    report_io.emit("x", "var/reports/anything.txt")
```

`pytest.raises` calls `emit` first. When the guard is broken, `emit` writes the
file and the assertion fails afterwards. **The test that exists to prevent the
overwrite performs it.** That is the part worth carrying to other tests: when a
test proves a destructive call is refused, assert the cheap classification
before making the call.

## The fix

Commit `23084b3`, branch `claude-work`, delivered as
`D:\Trading\Claude outputs\claude-ui-bridge-20260914c.bundle`.

- `_roots()` keeps **both** spellings of each protected directory, resolved and
  literal. Resolved catches a write through a junction; literal catches a path
  that never resolved.
- `_protected()` checks the candidate path both ways.
- `test_report_guard.py` calls `_must_be_recognised(path)` before `emit`, so a
  broken guard fails without writing.
- Two new tests: the junction case reproduced with a symlink (fails against the
  old logic), and one asserting the widened rule still lets ordinary paths
  through — a guard that refuses everything gets deleted.

1344 passed locally; the 5 failures are the pre-existing `databento`-absent ones.

## What you need to do

1. Merge the bundle into `D:\Trading` before running the suite from prod again.
2. `python -m common.mcp_sql --selftest` regenerates the lost report — confirm
   its contents look real, not `x`.
3. Delete `var\reports\anything.txt` if it is still there.

## Standing facts worth keeping

- **`D:\TradingProd\var` is a junction to `D:\Trading\var`.** Fills, watchlist,
  logs and reports are one set of files. Anything either checkout writes to
  `var/` hits the same place. `bar_cache` is NOT shared — prod has none, which
  is why two `test_tape_compare` tests `sys.exit` there rather than skipping.
- **If you add a protected directory, add its name to `NAMES` in
  `tests/conftest.py`**, not to a second tuple.
- `prod-20260914` is the current production tag: `prod-20260911` plus the three
  portal-bridge commits, nothing else. The guard fix is NOT in it — it is a
  test-only change, so it does not need to be.
