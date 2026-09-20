# The Python version gap — 2026-09-10

**Ben runs Python 3.14.7. The Claude session container ran 3.11.15. A green
suite in the session was not evidence the code ran on his machine.**

Recorded because it shipped a broken feature and the failure mode is silent in
exactly one direction: code that works on the older interpreter and not the
newer one passes every check before it leaves.

---

## What happened

A scripted edit left a stacked decorator on `common/notify.Notifier`:

```python
    @classmethod
    @staticmethod
    def batch_seconds(batch_min=None): ...
```

Chaining `classmethod` over `staticmethod` was **added in 3.9, deprecated in
3.11, and removed in 3.13**. On 3.11 it still resolves; on 3.14 `cls.method(x)`
passes `cls` as a positional argument:

```
TypeError: batch_seconds() takes from 0 to 1 positional arguments but 2 were given
```

Every call raised. Telegram batching was completely dead on his machine while
1,167 tests passed in the session container.

## Why no test caught it

Because **the call succeeds on 3.11 either way.** A behavioural test — call it,
check the number — passes on the old interpreter and cannot distinguish the two
constructs. The guard now added asserts on the *descriptor*:

```python
assert isinstance(N.Notifier.__dict__["batch_seconds"], staticmethod)
```

Verified by reintroducing the stacked decorator and confirming it fails. A test
that only exercised behaviour would have looked like coverage and provided
none.

## The fix, which is a process change rather than a code change

Python 3.14 is now installed in the session container:

```
uv python install 3.14
uv venv --python 3.14 /tmp/v314
uv pip install --python /tmp/v314/bin/python -r requirements.txt pytest
/tmp/v314/bin/python -m pytest -q
```

**Anything version-sensitive gets run there before it ships.** The container
is ephemeral, so a future session re-runs those four lines.

### What the 3.14 run currently reports

| | |
|---|---|
| 3.11.15 (container default) | 1,167 passed, 2 skipped |
| **3.14.0rc2 (matching Ben)** | **1,160 passed, 7 failed**, 2 skipped |
| Ben's 3.14.7 | 1,167 passed, 2 skipped |

The seven are all `tests/common/test_mcp_sql.py`, and all fail **inside
pydantic** (`Unable to evaluate type annotation "Literal['2.0']"`), not in this
project's code. The container resolved pydantic 2.13.5 against 3.14.0rc2; Ben's
combination is fine. So it is an artefact of the container's dependency
resolution, not a defect — but it means **the 3.14 run is a signal, not a gate**,
and the seven have to be read as known-environmental rather than treated as
noise to ignore wholesale. If that count changes, something real moved.

## The general shape

This is the same class of error the project already catalogues: two things that
agree by accident hide a defect in either. Here the two things were an
interpreter version and a test suite, and the accident was three minor versions
of removals nobody had looked at.

Constructs removed between 3.11 and 3.14 that would behave this way — silently
fine on the old one — are worth knowing about. Stacked
`classmethod`/`staticmethod` is the one that bit. The codebase was swept for
others and has none.
