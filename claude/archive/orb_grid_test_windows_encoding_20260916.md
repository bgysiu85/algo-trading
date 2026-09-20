# `test_orb_grid` fails on Windows only — an encoding defect, not a logic one

**Failing:** `tests/strategy/test_orb_grid.py::test_the_report_says_how_many_cells_it_refused_and_how_many_are_thin`
**Where:** Ben's machine (`D:\Trading` at `2ac0233`, Python 3.14, Windows).
**Not on:** Linux. The same test at the same commit passes in the cloud sandbox.

## Not caused by the portal merge

The failure appeared in the run after `claude-ui-bridge-20260916f` was merged, so
the portal work was the obvious suspect. It isn't:

- That commit (`713ed6d`) touches exactly two files: `common/ui_bridge.py` and
  `tests/common/test_ui_bridge.py`.
- `strategy/orb/grid.py` imports `common.breadth` and `common.report_io`. It has
  no path to `common.ui_bridge`, and neither does the test.
- The failing assertion is about the *text of a report*.
- The test passes at Ben's exact tip — `2ac0233`, portal commit included — when
  run on Linux.

## The actual cause

`common/report_io.emit` writes reports as **UTF-8** (`report_io.py:62`), which is
right. The test reads one back with a **bare `read_text()`** and no encoding:

```python
return {"text": out.read_text(), ...}
```

`read_text()` with no encoding uses the *locale* default. On Linux that is UTF-8
and everything matches. On Windows with Python 3.14 it is cp1252, so the report's
`§` (UTF-8 `0xC2 0xA7`) decodes as `Â§`:

```
written  :  ... and are NOT READ (§5): below that, drop-top-5
read back:  ... and are NOT READ (Â§5): below that, drop-top-5

assert "are NOT READ (§5)" in text   ->  False   (Windows)
                                     ->  True    (Linux)
```

The report is fine. The *reader* in the test is what loses the character. The
ORB grid report is simply the first to use a non-ASCII character in a string the
tests assert on.

## The fix

One argument, in the `built` fixture of `tests/strategy/test_orb_grid.py`:

```python
return {"text": out.read_text(encoding="utf-8"),
        "rows": list(csv.DictReader(csvp.open(encoding="utf-8"))),
        ...}
```

## This is a class, not an instance

There are **71 bare `read_text()` / `.open()` calls** across the test suite with
no encoding. Most read ASCII and will never break. Every one that reads a
UTF-8 report is a latent Windows-only failure waiting for someone to put a `§`,
an em dash or an accented name into that report — and these reports are written
in prose, so that is a matter of time rather than chance.

Two ways to close it, for the strategy side to choose:

1. **Name the encoding at each site that reads a report.** Precise, no new
   dependency, matches what production code already does.
2. **A guard test** in the manner of the existing artefact guard: fail if a test
   reads a file produced by `report_io.emit` without an explicit encoding. Turns
   the class into something enforced rather than remembered.

Running the suite under `PYTHONUTF8=1` would make the symptom disappear without
fixing anything, and would make the tests run under an encoding the rest of the
machine does not use. Not recommended.

## The pattern, now five for five

Every environment-shaped defect in this project has the same cause: **one side's
environment is more permissive than the other's.** This is the first where the
sandbox is the permissive one and Ben's machine is right to complain.

| Defect | Permissive side had | The other side had |
| --- | --- | --- |
| `FrozenInstanceError` | a non-frozen fake adapter | a frozen dataclass |
| artefact guard | a Linux symlink | a Windows junction |
| fill log unreadable | a UTF-8 default locale | cp1252 |
| `ZoneInfoNotFoundError` | a bundled tz database | none, without `tzdata` |
| **this one** | **a UTF-8 default locale** | **cp1252** |

Third and fifth are the same defect in two different files, eleven days apart.
`7c9b132` fixed the fill log by naming its encoding; nothing generalised it.
