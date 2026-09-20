# The prior_close repair, measured — 58% → 76%, and the verdict moved a band

`PROGRAM_INDEX` §7 item 1, the one that gated everything else, is no longer
"A DIFFERENT UNIVERSE".

## 1. The headline

`screen_validate`, same four sessions, same pre-registered bands:

| | before (defective close) | after (repaired) |
|---|---|---|
| live names found | **22 of 38 — 58%** | **29 of 38 — 76%** |
| 95% Wilson interval | 42% – 72% | **61% – 87%** |
| verdict (from the LOWER bound) | **A DIFFERENT UNIVERSE** | **PARTIAL** |
| missed | 16 | **9** |
| sim-only | 2 | 1 |

The bands were registered in the module before it could run, and the verdict is
read from the lower bound precisely so a point estimate on 38 names is not
mistaken for precision. It crossed from below 50% to inside 50–80%.

**What that lifts:** the blanket caveat that point-in-time figures "may not be
quoted as live expectations" — *including that MCL beats its control*. They are
now "indicative of a related universe", which is weaker than a measurement and
much stronger than a different universe.

## 2. The repair fixed seven specific names

| session | fixed | still missing |
|---|---|---|
| 2026-09-08 | ISPC, SLE | — *(now 6 of 6)* |
| 2026-09-09 | SUNE | BNC, RML, WYHG |
| 2026-09-10 | CULP | BIAF, IRD, ODD, RML, SUNE, TPET |
| 2026-09-11 | ACVA, LBGJ, XRTX | — *(now 8 of 8)* |

**ACVA, ISPC and XRTX are in the TRUTH table** — the very rows used to pick the
construction — and all three now appear. Two sessions are perfect.

And the universe grew in the predicted direction: **4,997 → 6,170 symbol-days**,
+23.5%, 9.1 → 11.2 per session. The extended-hours close is an inflated divisor
for a name that ran after hours, which deflates its computed premarket change
below the 20% clause. Repair the divisor and exactly those names appear.

## 3. The residual is partly identified

Nine misses remain. One of them is already explained:

- **TPET is AMEX-listed**, and `auction_else_last` scored **0/3 on AMEX** — not
  one row matched, because its closing cross happens on a venue XNAS.BASIC does
  not carry. This miss was predicted by the relaxation record and is not fixable
  from this tape.
- **RML misses twice** (09-09, 09-10), so it is a property of the name rather
  than of a session.
- 2026-09-10 is still the worst session by far: **5 of 11**.

The old doc's §6 item 1 — measure the capture ratio on the missed names — is now
a sharper question against 9 names instead of 16, with one of them already
accounted for.

## 4. Coverage, and why the per-name figure mattered

Archive-wide the repair covers **92.4%** of prior closes (5,812,430 repaired,
474,729 still daily). That looked like it forced a choice between
`--prior-close repaired` and `require`. Among the names that actually reach the
universe:

    daily=38   repaired=6,132        0.6%

The uncovered rows are overwhelmingly names that never come near a 20% change
and a 55,200-share threshold. Every universe row now carries `prior_source`, so
this stays a filter on an existing file rather than another pass over 552
sessions.

## 5. What is now stale

`pit_strategy`'s `H0_PIT_*` constants pin **4,997** symbol-days. The universe is
6,170. They were already stale at 5,021; they are now doubly so, and the
module's staleness guard will say so. **`pit_h0` must be re-run before any
`pit_strategy` figure is quoted again.**

## 6. Defects found while wiring this up

1. **Nothing read the emitted file.** `--emit` could write the repair and no
   consumer loaded it — the fix existed while the defect stayed live in every
   screen figure.
2. **`cache.get(day) or read_dbn(p)`** — a DataFrame has no truth value, and the
   only cached days were the TRUTH days at the END of a chronological walk. The
   run ground through ~548 sessions in silence and died having written nothing.
   Now parallel, with the cache deleted rather than patched.
3. **The writer shouted and the reader was deaf.** The relaxation is recorded
   under `RELAXED_PRE_REGISTERED_BAR`; the loader read `"relaxed"`, so "AMEX
   0/3, residual error is real and must be stated wherever these closes are
   used" reached the consumer and printed nothing. One shared `RELAXED_KEY` now.
   My own test had passed by writing the key the READER expected.
4. **Provenance went to stdout**, so two reports were byte-comparable and not
   comparable. It is in the report now, and `daily` mode is stamped DEFECTIVE.
5. **110 MB, 13.6s load** — the close file covers the whole tape, 10,557 symbols
   a session. Flat columns and a merge join: 5.8s.

## 7. Next

1. **`pit_h0`**, to refresh the control constants against the 6,170-day universe.
2. **Capture on the 9 remaining missed names** — is the 55,200 threshold
   mis-scaled for exactly the low-float names this screen is for?
3. Then `pit_strategy` for MCL and MC5, and re-read the 2026-09-11 conclusions
   with "indicative of a related universe" attached rather than "do not quote".
