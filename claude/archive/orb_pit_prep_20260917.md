# ORB — PIT run prepared, not yet run (2026-09-17)

**Bundles:**

- `orb-20260917a` (merged as a1e581a): `REGISTERED_orb_pit.md` (PRE-RUN), then the runner fixes C.1, C.2 (45 min, 120 cells), C.3 (round trips) and **D.2**. D.2: `_rth_screen` read the 15:59 close, so the first run's criterion 6 split (+$31,103 / −$13,281) is WITHDRAWN. The same bundle added a refusal when more than 1% of cache files are missing, a `first_seen` refusal and `--labels`.
- `orb-20260917b`: `strategy/orb/pit_bars.py` plus tests.

**Blocker and the fix:**

- `bar_cache_xnas` lacks 2,537 of 6,170 PIT symbol-days. `bar_cache_build` wrote 0 of them, because the XNAS.BASIC minute archive is in the daily layout: each day's file holds only the symbols earlier fetches requested (survivors and rejects). The PIT-only names have just the 04:00–09:30 all-symbol slices.
- A naive `databento_fetch` for the missing names would (1) replace each day's file with only those names, deleting the survivor bars from the archive, and (2) skip the 98 dates whose manifest row has no symbol list (`covered()` treats those as covered).
- `pit_bars plan` reads each file's symbols from DBN metadata and writes a union pairs file: 536 dates, 27,163 symbols kept, 2,528 added. `--write-manifest` gives the unverified rows their symbol lists, keeping a backup. `pit_bars verify` refuses if any date lost a symbol after the fetch.

**For the chat that owns `common/`:** the two `databento_fetch` behaviours above are real hazards for any future scoped re-fetch. They are recorded here and not fixed in `common/`.

**Sequence:** plan → fetch dry run (cost) → fetch `--confirm` → verify → `bar_cache_build` → PIT grid → survivor re-run.

**For PROGRAM_INDEX §7:** ORB criterion 6 from `orb_first_results.md` is withdrawn (D.2). The PIT result is pending the bar fetch.
