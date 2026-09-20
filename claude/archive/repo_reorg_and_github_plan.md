> **ARCHIVED 2026-09-08.** The reorganisation described here is done.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

# GitHub, refactor, reorganisation

# ✅ COMPLETE — 2026-09-04

**The reorganisation is finished. Nothing in this document is outstanding.**
It is kept as the record of what was done and, more usefully, *why* — several
decisions here look arbitrary until you know what they prevent.

`D:\Trading` is one private GitHub repo (`bgysiu85/algo-trading`) covering both
strategy families, structured as `common/` `brokers/` `strategy/` `tests/`,
with runtime data under `var/` and a shared bar cache under `bar_cache/`.
**51 tests pass on Windows.** Every one of the ~34 file moves is recorded as a
git rename, so `git log --follow` traverses the whole history.

## What was done, in order

| | | |
|---|---|---|
| 1 | commit the flat structure | done 2026-09-03 |
| 2 | split `mcl_paper_trader.py` into strategy logic and IB execution | done |
| 3a | move the repo root up to `D:\Trading`, fold in EMA Crossover Strategy | done |
| 3b | reorganise into `common/` `brokers/` `strategy/` `tests/` | done |
| 3b-3 | move runtime output under `var/` | done |
| 3b-2 | merge the duplicated indicators into `common/indicators.py` | done |
| 3c | `main.py`, `run.ps1`, the session lock, `--strategy` backtest dispatch | done |
| — | bar cache keyed by window; RSI returned to float64 | done |
| — | shared superset window, validated against live IB and enabled | done |
| — | documentation brought up to the new layout | done |

## What is deliberately NOT here

These are strategy and testing work, not reorganisation, and belong in their
own thread:

- **Build the bar cache** — one ~42-minute paced pull, now serving both
  strategy families instead of two ~85-minute ones
- **Run `sweep_variants.py`** to settle apex on/off and `MACD > 0`, which §7
  already has strong evidence on (apex: −$858.71 across 295 exits)
- MC5 threshold calibration; VW9 §8.3 setup counts
- Databento — blocked on the 1Password service-account issue, not on code
- The unadjusted-price question from §7, which is what would settle whether
  MCL's edge survives realistic friction at all

## The five things most likely to be rediscovered the hard way

1. **IB's `N D` counts trading sessions, not calendar days**, and the endpoint
   is exclusive. Calendar arithmetic silently drops a whole session across a
   weekend. See the shared-window section.
2. **A longer warm-up changes indicators on identical bars** — up to 58 RSI
   points — because EMA has infinite memory. Nothing may consume a superset
   frame whole.
3. **The live-session guard is a lock file now**, not a process-name match.
   Stale locks are cleared rather than honoured; a guard that never released
   would be worse than none.
4. **`os.kill(pid, 0)` terminates the process on Windows.** The POSIX liveness
   idiom would kill the session it was checking for.
5. **`OP_SERVICE_ACCOUNT_TOKEN` must hold a literal token, not an `op://`
   reference** — a reference cannot resolve itself — and a service account
   cannot read the Private vault.

---

*Original planning document follows.*

**STEP 1 IS DONE (2026-09-03).** The flat structure is committed and pushed to
a private `algo-trading` repo. Steps 2 and 3 were originally scoped to
`D:\Trading\MCL Strategy` only — **that scope changed on 2026-09-04** (see
below).

---

## 0. Scope change (2026-09-04)

Originally this repo was going to stay scoped to `D:\Trading\MCL Strategy`.
Since then:

- A sibling folder, `D:\Trading\EMA Crossover Strategy`, was created at Ben's
  request to hold the EMA-crossover strategy family (E15, VW9) — see
  `claude/vw9_setup_count_measurement.md`. It has no git history yet.
- Ben now wants the **entire `D:\Trading` folder** in one GitHub repo, not
  just `MCL Strategy`.

Decision: **one repo, `D:\Trading` as the root.** `MCL Strategy\.git` moves up
a level so both `MCL Strategy\` and `EMA Crossover Strategy\` become
subdirectories of a single repo, still pushed to the existing `algo-trading`
GitHub repo. This preserves MCL's existing git history rather than starting
EMA Crossover Strategy from a fresh, unrelated repo or using submodules.

**Mechanically:** git has no "promote the working directory's parent to be
the repo root" command. The move is: relocate `MCL Strategy\.git` to
`D:\Trading\.git`, then `git add -A && git commit`. Every previously-tracked
file appears to git as deleted from its old path and added at
`MCL Strategy\<same file>` (or wherever it lands in the new tree — see Step
3). Because the content is identical, git's rename detection (on by default
in `git status` / `git log --follow`, and explicit via `-M` on `git diff`)
records these as renames rather than delete+add, so history follows the file.
Exact commands are written out once the tree in Step 3 is final, so the move
and the reorganise happen in the same operation rather than two.

---

## 1. Where things stand (2026-09-04)

`D:\Trading\MCL Strategy` — git repo, 26 tracked files as of Step 1, more
added since (Databento integration, MC5, tests). Also currently contains:

- **`bar_cache/`** — new, gzipped 1-minute bar cache with checkpointing,
  wired into `mcl_backtest.py`'s `Runner` (see §5 below).
- **Stray files pending Ben's review, not yet actioned:** `mcl_backtest-1.py`,
  `mcl_strategy-1.py`, `backtest_trades_1st attempt.csv`. These look like
  editing-session backup copies (Windows "-1" naming) made very recently —
  most likely Ben's own working copies while building the bar cache. **Do not
  touch these until Ben has looked at them.**

`D:\Trading\EMA Crossover Strategy` — no git yet. Holds the VW9 §8.3
setup-count measurement pipeline (`indicators.py`, `data_ib.py`, `cache_io.py`,
`vw9_strategy.py`, `vw9_setup_counts.py`, tests). Built against MCL's
interfaces per Ben's instruction, which is *why* it already duplicates logic
that should be shared (see §4, §5).

Two strategies live in MCL Strategy today:
- **MCL / V7** — 1-minute, live-tested, +$891 over 51 trades on the 21-name set
- **MC5** — 5-minute, 27 tests passing, never run on real data

One in EMA Crossover Strategy:
- **VW9** — setup-count measurement built, not yet run (go/no-go pending)

---

## Order (revised 2026-09-04)

1. ~~commit the **flat** MCL Strategy structure to GitHub~~ **DONE**
2. ~~**refactor** `mcl_paper_trader.py` (split strategy logic from IB
   execution)~~ **DONE and committed (2026-09-04)**
3. ~~**3a — move the repo root** up to `D:\Trading`, fold in
   `EMA Crossover Strategy`~~ **DONE and pushed (2026-09-04)**
4. ~~**3b — reorganise** into `common/` / `brokers/` / `strategy/` /
   `tests/`~~ **DONE, merged and verified on Windows (2026-09-04)** — all
   seven suites green from the new tree against a fresh venv built from
   `requirements.txt`; see "3b — what was built" below
5. ~~**3b-3 — move runtime output under `var/`**~~ **BUILT AND TESTED
   (2026-09-04)**, delivered as `var-runtime-dirs.bundle`; done ahead of
   `main.py` so the entry point is written against final paths rather than
   rewritten twice
6. ~~**3b-2 — merge the duplicated indicators**~~ **BUILT AND TESTED
   (2026-09-04)**
7. ~~**3c — build** `main.py`, `run.ps1`, the lock-file guard, and the
   central backtest engine~~ **BUILT AND TESTED (2026-09-04)**
8. ~~**Documentation** — README, runbook, EMA doc and every module docstring
   still described the flat layout~~ **DONE (2026-09-04)**. Every command in
   them named a file that no longer existed, so following the runbook meant
   discovering the move one failure at a time. The README's safety section
   survived with one correction (the backtest guard is the lock now) and two
   additions learned this session.

**The reorganisation is complete.** 51 tests pass.

### 3b-2 — the indicator merge

`ema` and `rma` existed in three places, `macd` and `rsi` in two. All copies
were verified structurally identical (AST comparison, docstrings stripped)
*before* the merge, and 21 outputs — including both strategies' full
`signals()` frames — were pinned bit-identical across it.

**The substantive change is that the shared functions take periods as
arguments rather than reading module constants.** The old copies closed over
their own module's `MACD_FAST`/`RSI_LEN`, so sharing one function would have
meant silently sharing one set of tuning parameters. MCL and MC5 happen to
use identical values today (12/26/9, RSI 14) — that coincidence is exactly
what would have hidden the coupling until someone retuned one strategy and
moved the other. Each strategy keeps thin wrappers binding its own constants,
so every call signature still works.

`mc5.to_5m` is now a wrapper over `resample_bars`; the two were verified
equal on contiguous, gapped, ragged-tail and offset-start input, including
the empty-bucket rule.

**Known wart, deliberately not fixed:** `rsi()` returns **object dtype**,
because `down.replace(0.0, pd.NA)` types the whole chain. Inherited
unchanged; fixing it would have broken the bit-exactness claim. It costs
speed on every backtest bar and surprises numpy comparisons — cast with
`.astype(float)` until it is tidied.

### 3c — `main.py` and the session lock

**The `mcl_paper_trader` process-name guard is gone**, and so is the file.
`common/session_lock.py` replaces it: `main.py` takes `var/state/session.lock`
for `--mode paper|dry`, and `common/backtest.py` refuses to start while it is
held (`--force` overrides).

Two details that matter more than they look:

- **Stale locks are cleared, not honoured.** A lock whose process is gone, or
  older than 24h, is removed. A guard that never released after a crash would
  block every later backtest — worse than no guard.
- **The pid probe must not be `os.kill(pid, 0)`.** On Windows `os.kill`
  *terminates* the target for any signal other than CTRL_C/CTRL_BREAK, so the
  POSIX idiom would kill the very session it was checking for. Windows uses
  `OpenProcess`/`GetExitCodeProcess` via ctypes.

`main.py --mode {paper,dry,backtest,scan,report} --strategy {mcl,mc5,vw9}`
forwards unrecognised arguments untouched. Unsupported combinations fail
loudly: MC5/VW9 have no live interface (only MCL implements
`evaluate_last_bar`), VW9 has no backtest engine.

The backtest engine dispatches on `--strategy` across mcl and mc5, whose
checkpoints and reports are now **per-strategy** (`backtest_state_mcl.json`
vs `_mc5.json`) — sharing one file would have made the second strategy skip
every pair the first marked done, reporting nothing while looking successful.

### Bar cache keyed by window, and RSI in float64 (2026-09-04)

Both done before the cache was built, which was the point — after the
~85-minute pull, the first would have meant discarding that work.

**The cache is now keyed by WINDOW, not just symbol and date.** The two pulls
are not interchangeable and **neither is a superset of the other**:

| | duration | ends | carries |
|---|---|---|---|
| `common/backtest.py` | `2 D` | 09:30 ET | prior-day warm-up, stops at the open |
| `common/data_ib.py` | `1 D` | 20:00 ET | no prior day, runs to the post-market close |

Bars live in `bar_cache/2d_to_0930/` and `bar_cache/1d_to_2000/`, and **the
directory name is derived from the duration and end time that build the IB
request**, so it cannot disagree with its contents and a third window gets a
folder automatically. This also landed §5's gzip decision — the EMA side had
been writing plain CSV.

`tests/common/test_cache_layout.py` asserts each writer's directory is
derived from the request it issues, and that each reader points at the window
its writer populates. That mismatch is silent both ways: an empty directory
reports "no cached bars" for data that is present, a populated wrong one
returns the wrong bars.

**RSI now returns float64.** `down.replace(0.0, pd.NA)` forced object dtype —
but only when there were zeros to replace, so the dtype was silently
**data-dependent**: float64 on a falling series, object on a rising one.
`.where(down != 0.0)` gives identical values in float64; all 12 reference
outputs across six series shapes (all-gains, all-losses, flat, NaN-bearing)
are bit-identical.

### Shared superset window — built, OFF, gated behind a probe (2026-09-04)

Serving both pulls from one fetch would halve the IB budget on the ~85-minute
build. Two findings changed the shape of it, and both are pinned in
`tests/common/test_cache_layout.py`.

**The obvious superset is wrong.** `2 D` ending 20:00 begins **10.5h after**
`backtest.py`'s window starts, losing the prior-day warm-up entirely. `3 D`
ending 20:00 is the smallest that spans both. Anyone reaching for this will
guess `2 D` first, which is why it has a test.

**A superset cannot be passed through unsliced.** Handing a strategy a longer
frame changes its indicators **on the identical bars** — EMA has infinite
memory, measured at up to **58 RSI points** on a 3000-bar series. My earlier
reasoning ("indicators only look backward, so trailing bars are harmless")
was right about *trailing* bars and wrong about *leading* ones. Every consumer
must `slice_window()` back to its own range first, or enabling this silently
revalues every backtest.

**ENABLED 2026-09-04, after the probe.** Both consumers now fetch one `3 D`
window ending 20:00 into `bar_cache/3d_to_2000/` and slice it to what they
each need — `backtest.py` to 2 sessions ending 09:30, `data_ib.py` to 1
session ending 20:00, `strategy/vw9/setup_counts.py` slicing on read. One
pull instead of two.

**The first probe failed, and it was the slicing, not the idea.** IB counts
**trading sessions**, not calendar time, and the numbers pinned the rule
exactly:

> `N D` ending T on date D = the N-1 preceding trading sessions IN FULL, plus
> D's own session up to but EXCLUDING T.

`1290 = 960 + 330` — one full 04:00–20:00 session plus 04:00 to 09:30. Every
mismatch was a whole session or a whole session's tail: Monday targets missing
exactly 960 (the Friday session a calendar slice discarded by landing on
Friday 20:00), the Friday target carrying exactly 630 extra (Wednesday
09:31–20:00, which a calendar slice reaches into and IB does not), and every
target carrying exactly 1 extra — the endpoint bar, so the bound is exclusive.
`data_ib` matched 4/4 throughout, because its window is one session ending the
same day and never crosses a weekend.

`slice_sessions()` replaced the calendar version. The re-probe came back clean
on all four pairs and both windows: zero missing, zero extra, zero drift.

**Holidays and half-days need no special handling, by construction.** Sessions
are taken from the dates PRESENT IN THE DATA rather than from a calendar, so a
day the market was shut has no bars and is not a session — in the direct
request and the superset alike. The slice inherits IB's calendar instead of
modelling it.

**The residual risk is narrower and it is loud.** A superset that does not
reach back far enough — a short IB response, or a symbol without that much
history — would hand a strategy less warm-up than it asked for and move its
EMA-seeded indicators silently. `check_sessions()` counts them and the pair is
recorded `NO_DATA` instead.

`python main.py --mode probe-window --limit N` remains, and is worth re-running
if IB's behaviour ever seems to have changed.

### 3b-3 — the `var/` layout, as built

Twelve loose data files were left in the repo root by 3b. Relocating them is
not a move — it means editing default paths inside `trader.py` and
`common/backtest.py`, which is live-trading code — so it got its own commit.

    var/watchlist.txt              var/fills/mcl_fills_*.csv
    var/watchlist_blocked.txt      var/state/backtest_state.json
    var/archive/                   var/state/traded_pairs.json
    var/logs/                      var/reports/backtest_trades*.csv
    var/scanner_parameters.xml     var/databento/

`bar_cache/` stays at the repo root, per the Step 3 tree — it is a cache
rather than run output, and §5 governs it.

**`watchlist_blocked.txt` and `archive/` needed no code change.** The trader
derives both from the watchlist's own location (`self.watchlist.parent /
"archive"`), so pointing `--watchlist` at `var/watchlist.txt` moves all three
together. Worth remembering before "fixing" either path by hand.

**`backtest.py` gained `--state-dir`.** The resumable checkpoint and the
trade report are different kinds of artefact and now sit in different `var/`
subdirectories, so one `--out-dir` could no longer carry both.

**Every writer creates its own parent directory.** Everything under `var/` is
gitignored and therefore absent on a fresh clone; without `mkdir(parents=True,
exist_ok=True)` the fill log would fail to open before a single order was
placed. This applies to `FillLog`, `Runner`, `build_pairs`, `scan_params`,
`db_check` and `sweep_variants`.

Git existing before the risky work (step 2) separates failure modes: if
something breaks after step 2 it's the refactor, if after 3b it's a path.

### Why the old Step 3 was split into 3a/3b/3c (2026-09-04)

The original plan had one "reorganise" step doing the `.git` relocation, the
folder move, the import rewrites and the launcher/guard changes together. A
break anywhere in that could have been any of the four. Splitting it applies
the same failure-mode separation that made Step 1 worth doing before Step 2.

**3a is the near-riskless half** and was done first: only the repo root and
the ignore rules move up a level, while every file stays physically where it
was. Nothing moves *relative to anything else*, so `.venv`, the four `.ps1`
launchers, every runtime path, and the `mcl_paper_trader` process guard all
keep working untouched, and the tests pass unchanged. It also delivers the
actual goal — the whole `D:\Trading` folder in one GitHub repo — without
waiting on the risky part.

The cost is that files get renamed twice across two commits
(`foo.py` → `MCL Strategy/foo.py` in 3a, then → `strategy/mcl/foo.py` in 3b).
That is cosmetic: git detects renames at diff time rather than storing them,
so `git log --follow` traverses both hops fine.

### 3a — what it actually produced

**26 renames, 8 additions, 1 modification.** Worth recording the arithmetic,
because "only 26" looks alarming against ~28 tracked files until you see why:
git paths are relative to the repo root, so `.gitignore` was `.gitignore`
before the move and is still `.gitignore` after — same path, not a rename,
shows as `M`. `.gitattributes` likewise kept its path *and* its content, so
git saw no change to it at all and it never appeared in `git status`. 28
tracked files minus those two is 26. Nothing was dropped.

The 8 additions are the EMA Crossover Strategy files, new to the repo and so
with no prior content to rename from.

**The ignore check that matters, and should be repeated in 3b:**

    git status --short | Select-String "venv|__pycache__|bar_cache|watchlist|fills|traded_pairs"

Must return nothing before committing. These are real fills, real positions
and a multi-hundred-MB venv; the point of running it before every structural
commit is that a `.gitignore` governing the wrong subtree fails silently.
`.gitignore` and `.gitattributes` now live at the repo root and govern both
strategy folders; `bars_cache/` and `data_pull_state*.json` were added to
cover the EMA puller's separate cache naming (§5).

---

## STEP 1 — DONE. What was committed, and what was learned

*(unchanged from the original plan — kept for reference)*

26 files tracked: 18 `.py`, 4 `.ps1`, `README.md`, `MCL_PAPER_RUNBOOK.md`,
`.gitignore`, `.gitattributes`.

**Secret audit passed clean.** 29 files scanned for service-account tokens, AWS
/ GitHub / Slack tokens, private-key blocks, JWTs, long hex, and
`key = "literal"` assignments. Nothing found. No IB account ids, emails, or
absolute user paths either. Every `op://` occurrence is a placeholder or prose —
those are pointers, not secrets, and are safe in source.

Correctly excluded: `.venv/`, `__pycache__/`, `archive/`, all `mcl_fills_*.csv`,
`backtest_state.json`, `watchlist.txt`, `watchlist_blocked.txt`,
`traded_pairs.json`, `scanner_parameters.xml`.

**Two mistakes made during this step — do not repeat:**

`.gitignore` inline comments do nothing — a `#` only starts a comment at the
START of a line, so a trailing comment on a pattern line gets matched as part
of the pattern and the file is silently tracked. Comments now live on their
own lines. **Always review `git status --short` before the first commit of
anything** — that's what caught it.

`.gitattributes` is in place: LF in the repo always, CRLF in the working tree
for `.ps1`/`.bat`/`.cmd`, LF elsewhere, binaries untouched. This is line
endings only — unrelated to the ENCODING bug that broke `run_paper.ps1` (a
UTF-8 em dash in a BOM-less `.ps1`, decoded by PowerShell 5.1 as U+201D,
flipping quote parity for the whole file). **Keep `.ps1` files pure ASCII.**

**Tooling, settled, not re-litigated:** the GitHub Integration connector is
read-only and unavailable in Cowork sessions — no use here. `gh` CLI not
installed, not needed. `git` is installed and working on Ben's machine.

---

## 2a. The cloud sandbox can READ the GitHub repo but cannot PUSH (2026-09-04)

Tested directly, so this does not need re-deriving. The sandbox routes GitHub
traffic through its own proxy, which authorises per session and per
repository — **Ben's PAT is not the deciding factor and turned out to be
unnecessary.** What was observed:

- `git clone https://github.com/bgysiu85/algo-trading.git` — **works.** Read
  access was already available to the session.
- `git push` — **refused**: "access denied by the git proxy: bgysiu85/
  algo-trading is not in this session's authorized repository set, so the
  proxy will not inject a credential for it."
- `api.github.com/repos/...` — **403 from the proxy**, not from GitHub, with
  a message pointing at an `add_repo` tool. `GET /user` did work (login
  `bgysiu85`).
- `add_repo` is **not present** in this session (checked by name via
  ToolSearch). So there is no in-session way to authorise a push.

**Consequence for the working model:** the cloud-clone workflow in §2 below
is still the right one — Claude can clone, branch, edit and run the full test
suite unattended — but the result comes back as a **git bundle** delivered
over the device bridge rather than as a pushed branch or a PR:

    git bundle create <name>.bundle <base>..<branch>

Ben fetches from the bundle locally (`git fetch <path> <branch>:<branch>`),
which preserves both the commits and git's rename detection. He pushes to
GitHub himself. A bundle for a change of this size is ~120 KB.

**Do not spend time on PAT setup for this again.** A fine-grained token
scoped to the repo does not change any of the above, because the proxy
refuses before the credential is ever consulted.

---

## 2. Execution mechanics — no shell on Ben's machine, and what that means

This session has no direct shell tool for Ben's computer — only a file
bridge (read/write via `device_stage_files`/`device_commit_files`) and a
separate Computer Use capability (screen/mouse/keyboard control, currently
off) that still requires Ben's PC to be on and the desktop app open. There is
no installable connector that grants a real remote shell — checked the MCP
connector registry directly, nothing relevant exists.

**The workaround that avoids needing either:** once the repo is pushed to
GitHub, Claude has a full, unrestricted shell in its own cloud workspace and
can clone the repo there. Everything in steps 2-4 above that doesn't require
Ben's local IB Gateway (the `mcl_paper_trader.py` split, the tree reorg, unit
tests, `main.py`) can happen as branch work in that cloud clone — including
overnight, unattended — landing as a PR or branch for Ben to review and merge
whenever. **What can't move off Ben's machine:** recreating `.venv` there, and
actually running `run_dry.ps1`/`run_paper.ps1`/the new `main.py` against a
live or paper IB Gateway session, since that connection is local-socket-only
(confirmed in `claude/ib_async_setup_guide.md`).

**For step 5 specifically (the `.git` move):** Ben runs this one himself, in
person, since it's a one-time repo-shape change worth verifying directly
rather than doing blind over a bridge.

---

## STEP 2 — DONE (2026-09-04). Refactored `mcl_paper_trader.py`

`mcl_paper_trader.py` was 53KB mixing strategy evaluation, IB execution,
order state, fill logging, watchlist management, and the tradability probe.
Split, tested in a cloud clone against all five test suites (green), and
delivered back to `D:\Trading\MCL Strategy`.

**What actually landed — flat, not yet at the Step 3 folder paths:**

- `mcl_strategy.py` (existing file, extended) — gained `Signals`,
  `MIN_BARS_REQUIRED`, and `evaluate_last_bar(df)`. The old paper trader
  carried its own separate copy of every indicator function plus its own
  reimplementation of the entry/exit logic (`evaluate()`), evaluated on the
  last bar of a rolling window instead of vectorised over a session.
  `evaluate_last_bar()` replaces that copy by calling the existing
  `signals()` and reading off the last row, so live and backtest now share
  one computation and cannot silently diverge again. `signals()` also gained
  `prev_vol`/`trail_avg` as output columns (additive only) so
  `evaluate_last_bar()` doesn't need to recompute them.
- `trader.py` (new file) — the IB-execution class (`MCLPaperTrader`),
  `Position`/`SymbolState`, `FillLog`, order placement, watchlist/archive
  mechanics, the tradability probe. Imports strategy logic from
  `mcl_strategy.py` instead of duplicating it.
- `mcl_paper_trader.py` — kept at this exact name and path, now an 18-line
  shim that just imports and calls `trader.main()`. **Deliberate deviation
  from the original "give new modules their final names now" instruction:**
  renaming it to `trader.py` outright would have broken
  `run_backtest_after_session.ps1`'s live-session guard (see below)
  immediately, before the Step 4 lock-file replacement exists to fix it.
  Keeping the filename stable means `run_dry.ps1`/`run_paper.ps1` and the
  guard both keep working unchanged until Step 3/4 do the coordinated move.

**Finding from the split, worth knowing before Step 3:** the old live
`evaluate()` hardcoded `macd_line > 0` unconditionally — it never actually
read `REQUIRE_MACD_POSITIVE`, unlike the backtest's `signals()`. Since that
flag currently defaults to `True` (matching the hardcoded live behaviour),
today's live trading is unaffected. But flipping it for a backtest sweep
would previously have changed backtest results without touching live at all
— exactly the silent-divergence risk the indicator consolidation (§4) is
about. `evaluate_last_bar()` fixes this: live and backtest now both honour
the flag, because both call `signals()`.

**Also confirmed unaffected, no changes needed:** `mcl_backtest.py` (still
`import mcl_strategy as S`, only additive column changes), `mc5_strategy.py`
/ `test_mc5_strategy.py` (27/27 passing, untouched), `mcl_scanner.py` (only
references `mcl_paper_trader` in a docstring, not an import).

**The trap, still live and still unfixed — this is Step 3/4's job, not
Step 2's:** `run_backtest_after_session.ps1` detects a running live session
by matching the literal string `mcl_paper_trader` in process command lines,
to avoid throttling IB's ~60-requests-per-10-minutes account-wide cap
against a live session. IB signals throttling by returning empty lists, not
errors, so a broken guard fails silently on both sides. This still works
today because `mcl_paper_trader.py` is still the invoked filename. It stops
working the moment Step 3/4 replaces every launcher with one `main.py` —
every process (MCL paper trading, MC5 backtest, VW9 setup-count run) will
then show `main.py` in its command line, so string-matching the script name
stops meaning anything. Replacement: a lock file at `var/state/session.lock`
(see Step 3), written by `main.py` on `--mode paper` start with
mode/strategy/pid, removed on clean exit; anything about to hit IB for a
backtest checks for that file first instead of grepping process names.
**Do not deploy `main.py` without this guard in place.**

---

## STEP 3b — reorganise (next)

Ben's structure (root entry point; a common/general-purpose folder; a brokers
folder with one subfolder per broker; a strategy folder with one subfolder
per strategy), refined through discussion to the tree below. Central backtest
engine and central `tests/` per Ben's preference (2026-09-04).

**Starting point after 3a:** everything MCL is under `MCL Strategy/`,
everything VW9/E15 under `EMA Crossover Strategy/`, both tracked in one repo
rooted at `D:\Trading`. Neither subfolder name survives 3b — the tree below
replaces both.

### 3b — what was built (2026-09-04)

Two commits on `reorg/3b-folder-structure`, delivered as a bundle (§2a):

1. **Remove an accidental gitlink.** The 3a commit ran `git add -A` while
   `D:\Trading` contained `_backup_MCL_20260904` — a backup of `MCL Strategy`
   taken *with its `.git` directory*. Git recorded the nested repo as a
   gitlink (mode `160000`, pointing at the Step 1 commit) rather than adding
   files: it clones as an empty directory and has no `.gitmodules` entry. No
   file contents were committed, so nothing leaked and nothing was lost.
   `.gitignore` now carries `_backup*/` and `*_backup_*/` so a backup made
   inside the repo cannot repeat this. **Keep backups outside the repo.**
2. **The reorganisation.** 34 files moved, all detected as renames at
   similarity 91-100%, so history follows every one.

**Everything is a package now**, so modules are invoked with `-m` from the
repo root. `python common\backtest.py` puts `common/` on `sys.path` instead
of the root and fails to resolve `strategy.mcl` — this is the packaging note
from §3 made real. `run_backtest_after_session.ps1` and `show_trades.ps1`
were updated to `-m common.backtest` / `-m common.report_trades`.

`mcl_paper_trader.py` stays at the repo root under that exact name, and
`run_dry.ps1`/`run_paper.ps1` still invoke `.\mcl_paper_trader.py`, so
**the process-name guard still matches**. It becomes `main.py` in 3c, at the
same time as the lock file that replaces the grep.

**Two conventions in the test suites, discovered by running them:**
`strategy/mcl` and `strategy/mc5` tests are standalone scripts with their own
`main()` and PASS/FAIL output, run via `-m`. `common/` and `strategy/vw9`
tests are **pytest**. Neither `pytest` alone nor `-m` alone runs everything,
which is why `run_tests.ps1` now exists. This also means the corrected
dependency list in §3 was still wrong — **`pytest` was missing** — and there
is now a real `requirements.txt` (`ib_async`, `pandas`, `numpy`,
`databento`, `pytest`).

**Verified green from the new tree:** 5 script suites plus 24 pytest tests,
in the cloud sandbox first and then **on Windows on bens-proart**, against a
`.venv` rebuilt at the repo root from `requirements.txt`. Per the Step 1
lesson that a green suite in one environment is not a baseline for another,
the Windows run is the one that counts.

**The venv is delete-and-recreate, not move.** Windows venvs do not relocate
reliably, and the `.ps1` launchers resolve `.venv\Scripts\python.exe` from
`$PSScriptRoot`, which is now the repo root:

    Remove-Item -Recurse -Force "MCL Strategy\.venv"
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

One wrinkle worth knowing: after deleting the old venv, a shell that still
has it activated keeps a stale `(.venv)` prompt and a PATH pointing at a
directory that no longer exists. Open a fresh terminal before rebuilding.
VS Code also holds a handle on the old folder while its Python extension has
that interpreter selected, which blocks deleting the now-empty
`MCL Strategy\` directory until VS Code is quit — harmless, since the
directory is empty and untracked.

**Untracked files git cannot move.** `.venv`, `watchlist.txt`,
`watchlist_blocked.txt`, `traded_pairs.json`, `backtest_state.json`,
`scanner_parameters.xml`, `archive/`, `bar_cache/`, `mcl_fills_*.csv` and
`backtest_run_*.log` are all ignored, so they stay behind in
`MCL Strategy\` after the merge and must be moved to the repo root by hand —
the launchers now run with the root as the working directory. The venv is
delete-and-recreate rather than move (Windows venvs do not relocate
reliably).

```
Trading/                          (repo root, was MCL Strategy\)
  main.py                         # entry point: --strategy X --broker Y --mode dry|paper|backtest [strategy args passthrough]
  run.ps1                         # activates .venv (creating it if missing, same bootstrap run_dry.ps1 already does), calls main.py

  common/
    indicators.py                 # ema/rma/atr/session_vwap — ONE copy (see §4)
    data_ib.py                    # IB history puller, generalised from EMA's version
    db_bars.py, db_check.py       # Databento data
    secrets_util.py
    op_list.py
    build_pairs.py
    report_trades.py              # account viewer
    backtest.py                   # central engine — takes --strategy, dispatches to strategy/<name> (see §6)

  brokers/
    ibkr/
      trader.py                   # execution slice of mcl_paper_trader.py
      scanner.py                  # mcl_scanner.py
      scan_params.py, scanner_parameters.xml   # IB TWS scanner format — broker-specific
    tradezero/
      client.py                   # tz_check.py

  strategy/
    mcl/mcl.py                    # strategy-evaluation slice of mcl_strategy.py + mcl_paper_trader.py
    mc5/mc5.py                    # mc5_strategy.py
    vw9/vw9.py, vw9/setup_counts.py

  tests/                          # mirrors the tree above: tests/common/, tests/brokers/ibkr/, tests/strategy/mcl/, etc.

  bar_cache/                      # gitignored — shared 1-minute bar cache, all strategies (see §5)
    <SYMBOL>_<DATE>.csv.gz
    pull_state.json

  var/                            # gitignored — runtime output: fills/, archive/, state/ (incl. session.lock), logs/
  docs/                           # MCL_PAPER_RUNBOOK.md + both READMEs
```

**What breaks on the move** (unchanged categories from the original plan,
paths updated):

Imports — every strategy/broker module's imports need updating to the new
package paths (`from strategy.mcl import ...` etc. instead of flat
`import mcl_strategy as S`). Test files import both the strategy under test
and, in several cases, `mcl_paper_trader` directly — those need to follow the
`brokers/ibkr/trader.py` split.

Hardcoded script paths — `run_paper.ps1`, `run_dry.ps1`,
`run_backtest_after_session.ps1` currently invoke `.\mcl_paper_trader.py` /
`.\mcl_backtest.py` directly; all three are replaced by `run.ps1` calling
`main.py` with the appropriate flags (Step 4).

Runtime paths resolved relative to the script (`watchlist.txt`,
`watchlist_blocked.txt`, `archive/`, `mcl_fills_*.csv`, `traded_pairs.json`)
move under `var/`. Update `.gitignore` accordingly.

`.venv` and `__pycache__/` are **not moved** — both already gitignored, both
cheap to regenerate. Delete the old `.venv` under `MCL Strategy\` once code
has landed at the new root; `run.ps1` recreates it on first run exactly as
`run_dry.ps1` already does (checks for `.venv\Scripts\python.exe`, creates
the venv and `pip install ib_async pandas` if missing — no `requirements.txt`
currently exists, that's the full dependency list today).

---

## 4. Indicator duplication — consolidate into `common/indicators.py`

`EMA Crossover Strategy/indicators.py` already contains `ema`/`rma` copied
"verbatim" from `mcl_strategy.py`, plus `atr` and `session_vwap` that MCL
never needed. Ben's own `claude/vw9_setup_count_measurement.md` flags this as
a deliberate-but-risky choice ("so E15/VW9/V7/MC5 never silently disagree on
what those mean"). Folding both strategy families into one repo makes the
verbatim-copy approach unnecessary — one `common/indicators.py`, all four
strategies import from it, and the "never silently disagree" property holds
by construction instead of by discipline.

---

## 5. Shared bar cache — two existing implementations, need to unify

Both strategy folders independently built IB bar caching very recently (this
is likely what triggered the file-timestamp questions earlier this session —
Ben was actively working on this in `mcl_backtest.py`):

| | `MCL Strategy/mcl_backtest.py` | `EMA Crossover Strategy/data_ib.py` |
|---|---|---|
| cache dir | `bar_cache/` | `bars_cache/` |
| file format | `<SYMBOL>_<DATE>.csv.gz` (gzipped) | `<SYMBOL>_<DATE>.csv` (plain) |
| checkpoint | `backtest_state.json` — pull status **and** computed trade results, mixed | `data_pull_state.json` — pull status only |
| window pulled | pre-market only, ending 09:30 ET | full session, 04:00-20:00 ET |

Merging into one repo makes this the same class of problem as §4: two
independently-evolving copies of the same idea. Plan: one shared `bar_cache/`
at the repo root (Step 3 tree), one format, one checkpoint file holding pull
status only.

**Confirmed with Ben (2026-09-04):**
- **Format — gzip.** Standardized on MCL's existing choice. EMA/VW9 pulls the
  full session rather than just pre-market, so its files are larger and
  benefit from compression more, not less.
- **Checkpoint split — confirmed.** `bar_cache/pull_state.json` holds fetch/
  qualify status only (keyed by symbol+date+window, since MCL's pre-market
  pull and VW9's full-day pull for the same symbol+date are not the same
  fetch and can't share one cache entry). Each strategy's computed trades /
  results move to `var/`, out of the cache checkpoint entirely.

Both are settled — safe to implement as part of Step 2-4 execution.

---

## 6. `main.py` and the central backtest engine

Per Ben's design (2026-09-04): one `main.py` at the root takes a strategy
flag and passes through strategy-specific parameters, rather than a script
per strategy per broker. Backtesting follows the same shape — one
`common/backtest.py` engine takes `--strategy` and dispatches into
`strategy/<name>/`, rather than each strategy owning its own backtest runner
(`mcl_backtest.py`'s `Runner` and EMA's `data_ib.py`'s `BarSource` are
currently two separate, near-identical implementations of the same
qualify/pace/checkpoint pattern — this consolidation retires both into one).

`tests/` is central, mirroring the source tree, rather than colocated inside
each strategy/broker folder (Ben's preference, 2026-09-04).

---

## Carried forward

- MC5 threshold calibration on real 5-min data (`slope_distribution()`)
- VW9 §8.3 setup-count measurement — built, not yet run (go/no-go pending)
- `--strategy` flag on the backtest runner, to compare MCL vs MC5 vs VW9 on
  the same pairs — now folded into the central `common/backtest.py` design
- Databento: `op_list.py` → set the three env vars → `db_check.py` →
  the `surges` diff that decides whether Databento is usable at all
- Ask TradeZero support whether paper enforces the same opening-trade
  restrictions as live
- `mcl_scanner.py --preview` has still never been run against IB
- Resolve the stray `mcl_backtest-1.py` / `mcl_strategy-1.py` /
  `backtest_trades_1st attempt.csv` files (Ben reviewing)
