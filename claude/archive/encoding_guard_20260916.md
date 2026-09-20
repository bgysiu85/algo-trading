# Every text-mode open in the tree now names its encoding, and a guard keeps it so

2026-09-16. Answers the Windows failure in `test_orb_grid` reported by the live-analysis
chat: `report_io.emit` writes UTF-8, the fixture read it back with a bare `read_text()`,
and on Ben's cp1252 locale `§` came back as `Â§`. Same commit, same code, two answers.

**It was one instance of a class.** An AST scan found **242** text-mode opens across
`tests/`, `common/`, `strategy/` and `brokers/` with no `encoding=`. The production ones
are the worse half: a fill log written in cp1252 and read in UTF-8 is not a failing test,
it is a wrong number — which `common/textio.py` already exists to cope with, because the
fill log itself was written that way until FillLog named its encoding.

## What changed

- **All 242 fixed mechanically by AST** — `open`, `Path.open`, `read_text`, `write_text`,
  and text-mode `gzip.open` — inserting `encoding="utf-8"`. Binary modes untouched (there
  are none in the tree outside the guard's own examples).
- **`tests/test_encoding_guard.py`**: walks the same four roots, refuses any bare text-mode
  open, and **is checked against itself** with twenty shapes it must and must not flag,
  plus a planted-file mutation — a guard that never fires is indistinguishable from its
  absence.
- **The whole suite passes under `LC_ALL=C PYTHONUTF8=0`** (locale = ASCII), which is
  stricter than cp1252: any bare read of a non-ASCII byte there raises rather than
  mangles. **3,080 green** both ways.

## Two things the mass fix got wrong, both caught by the self-check

1. **It read the mode from `args[0]` for every call.** For the builtin `open(path, mode)`
   and `gzip.open(path, mode)` that is the *path*. The self-check flagged `open("x", "rb")`
   as text and `gzip.open(p, "rt")` as binary. Mode position now depends on the callee.
   No binary open in the tree was damaged — there are none — but the guard would have
   passed on a tree that had one.
2. **It put `encoding=` on `textio.read_text(path)`**, the repo's own two-generation
   decoder, which takes none — and broke `churn_count.load`. The guard now exempts
   `common.textio` **by import**, not by the letter `T`, which is also what three test
   files call the trader. A bare-name `read_text(...)` is never `Path`'s and is not
   flagged.

A parametrised mode (`open(HOLDOUT, mode)` in `test_artefact_guard`) cannot be judged
statically and is skipped, on purpose and visibly — one call.

`PYTHONUTF8=1` would have hidden this from the machine most likely to hit it.
