# What running the site found that the test suite did not — 2026-09-16

After the partial-exit work was merged and green (2,813 trading / 152 UI), the
portal was actually run: a fill log containing a position exited in two goes
(40 fills, remainder re-priced, 60 fills a minute later), plus a partial entry
and a rejection, driven through the real stack — replay agent → relay → browser.

Contract validated clean, no page errors, money reconciled (+20.00). **Three
defects surfaced anyway, none of which any test caught.**

## 1. An exit of a partly-closed position lost its entry time

A real bug in the same day's work. Once partial exits are listed, one position
produces **two** rows in *Closed today* — and the pairing did
`opened_by.pop(key)` on the first, so the second rendered `—` under *Entered*.
BDRX exited 40 at 10:19 and the remaining 60 at 10:20; only the first said when
it had been entered.

Fixed by mirroring the trader: forget the opening time only on the `FILLED`
exit, which is always the one that flattens the position (that order's quantity
*is* the remaining position). The opposite error is pinned too, and is the more
dangerous one — holding the time *past* a full exit would give a later round
trip an earlier entry timestamp: populated, plausible and wrong, rather than
obviously empty.

## 2. The replay was rendering time four hours early

`Replay.iso()` labelled naive Eastern timestamps as UTC without converting, with
a docstring arguing that was acceptable because the UI only displays them. It
is not: the page renders `opened_at` through `clockET()`, which converts UTC to
Eastern — so the mislabel reappeared four hours early. A position entered at
10:41 showed as **06:41, before the session began**.

**The live adapter was never affected** — `common/ui_bridge.py:_iso` converts
from a tz-aware `entry_time`. But the replay is how the page gets checked
without waiting for a session, and one that renders times differently from the
live path is worse than none: it teaches you to distrust the right answer, or
to trust the wrong one.

## 3. The footer under-reported the contract

`contract/VERSION` still said `1.6.0` while the page published 1.7 fields. The
agent's `CONTRACT_VERSION` had drifted the same way once before (saying 1.4
while emitting 1.6 fields). A test now fails if the two drift apart again.

## 4. …and then Windows found a fourth

`ET = ZoneInfo("America/New_York")` at module scope worked in the sandbox
because Linux ships the IANA database system-wide. **Windows does not** —
`zoneinfo` there needs the `tzdata` package — so the lookup raised during
import, pytest could not collect `test_replay.py`, and all 154 tests stopped at
one collection error.

The lookup is now lazy and cached (import succeeds; only the conversion
complains, with the pip command in the message), and `tzdata` is declared in
`requirements.txt` for win32. It refuses rather than falling back to a fixed
offset: Eastern is UTC-5 for part of the year and UTC-4 for the rest, so a
constant would be wrong for months and silently right in between.

## The pattern, now four for four

Every environment-shaped defect in this project has the same cause: **the
sandbox is more permissive than the machine that matters.**

| Defect | Sandbox had | Ben's machine had |
| --- | --- | --- |
| `FrozenInstanceError` | a permissive fake adapter | a frozen dataclass |
| artefact guard | a Linux symlink | a Windows junction |
| fill-log encoding | a UTF-8 default locale | cp1252 |
| `ZoneInfoNotFoundError` | a bundled tz database | none, without `tzdata` |

Writing the code is not the check. Running it where it runs is — and running
the *page*, not just the suite, is what found the first three above.

## Final state

| Repo | Commit |
| --- | --- |
| `D:\Trading` | `31b7184` |
| `D:\Trading UI` | `e57a0a4` |
| `D:\TradingProd` | `5ab22cc` (`prod-20260916`) — **not yet promoted** |

Suites: 2,813 passed / 6 pre-existing `databento` failures / 49 skipped; UI
153 passed / 1 skipped (the TradingView cross-check, which correctly skips when
the script loads).

**Production carries none of this.** Promotion is a tag in `D:\Trading` plus
`fetch --tags` and `checkout` in `D:\TradingProd`, per
`docs/MCL_PAPER_RUNBOOK.md`, and never mid-session.
