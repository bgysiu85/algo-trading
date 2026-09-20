# Pre-market hypotheses — training results, 2026-09-08

**No hypothesis survived. The holdout stays sealed.** The programme registered
in `premarket_hypotheses_20260908.md` (commit `5075784`) ends here, as it said
it would; a second needs a new registration.

That is the headline required by the rules. It is not the most important thing
in the report. Three findings are, and one of them retracts a claim this
project has been resting on since 09-07.

Report: `var/reports/premkt_training.txt`. Trades: `var/reports/premkt/`.
Bars: `bar_cache_xnas`, 15,777 survivor symbol-days and 3,264 rejects over the
381 training sessions. Costs: tiered commission plus the measured $4.26 per
round trip. 100 shares flat.

---

## 1. MC5 does not survive the tape, and did not survive friction either

| MC5, 100 shares flat | trades | net | per trade | drop-top-5 |
|---|---:|---:|---:|---:|
| EQUS.MINI, all 545 sessions, commission only (09-07) | 7,403 | +$8,209 | +$1.11 | +$2,537 |
| EQUS.MINI, same, **with the $4.26 friction** | 7,403 | **−$23,328** | −$3.15 | — |
| **XNAS.BASIC, 381 training sessions, with friction** | 10,905 | **−$97,335** | **−$8.93** | **−$109,030** |

Two things are wrong with "MC5 is the first result to survive drop-top-5",
and I wrote that sentence.

**It was never after friction.** `screened_universe_results.md` charged tiered
commission and nothing else. The one live measurement of slippage — $4.26 a
round trip, from the 09-03 session — takes +$1.11 to −$3.15 a trade on the
same bars. That was computable on 09-07 and was not computed.

**It does not hold on the fuller tape.** On XNAS.BASIC, which carries the TRF
prints EQUS.MINI's median 4.8% capture omits, MC5 fires 2.5 times as often
(0.69 signals per symbol-day against 0.27), wins 21.7% of the time, and loses
$8.93 a trade with friction — about −$3.30 gross. Every drop-top-N is deeper
than the total. There is no subset of symbols on which it works.

The mechanism is plausible and unverified: a fuller tape has more prints, so a
minute's low is lower and the 5% trail is reached more often, and gap-through
fills are worse. **The one check worth making before treating this as final:**
whether XNAS.BASIC's minute ranges are widened by late-reported TRF prints
landing in the wrong minute, which would trigger trails a real-time trader
would not have seen. That is measurable — compare trail-hit rates on identical
symbol-minutes across the two tapes — and until it is made, the honest
statement is that MC5 is negative after friction on *both* tapes, and much
worse on the one this project has already decided is closer to reality.

MC5's Pine script and the `pine/` README describe it as the survivor. Both
need the same correction as this document.

## 2. Every entry rule made the screen worse

Same universe, same 8% trail, same session end, same size. The only thing
that varies is the entry.

| | trades | per trade | drop-top-5 |
|---|---:|---:|---:|
| **H0 — buy at 04:30, no entry rule** | 6,541 | **+$4.72** | +$22,481 |
| H1 — new session high on 2× volume | 1,753 | −$8.44 | −$17,827 |
| H2 — 04:00–04:29 range break on 2× volume | 604 | −$12.21 | −$9,514 |
| B0 — MC5's five indicator conditions | 10,905 | −$8.93 | −$109,030 |

H1 costs $13.16 a trade against H0; H2 costs $16.93. Waiting for confirmation
— a session high, a range break, an oscillator alignment — selected trades
that then did worse than entering with no confirmation at all. This is the
direct test of Ben's 09-08 observation that the entries fill after the move,
and the answer is sharper than the observation: on these names, with this
exit, the confirmation itself is the cost.

It is also the same result V8 and V9 gave from the other side. Relaxing MCL's
conditions made it worse; here, *having* conditions made it worse. The
consistent reading is that indicator- and breakout-style entries on
pre-market gappers are buying the top of the move, and that no amount of
tuning which top to buy fixes that.

## 3. H0 is the only lead, and it failed for two reasons that both matter

H0 passed five criteria: positive after all costs, positive on drop-top-5 and
drop-top-10, 6,541 trades across 2,460 symbols, beats the benchmark, and the
same sign at every trail width. It failed two, and neither is a technicality.

**Regime.** Early half (2024-07 → 2025-04) −$1,850; late half (2025-04 →
2026-01) +$32,751. The result is one period's. A pre-market-gapper regime that
ran for nine months is a plausible thing to exist, and it is exactly the thing
the halves criterion exists to refuse.

**The leak.** Survivors +$4.72 a trade; rejects −$9.81 a trade over 636 trades.
That is the mirror image `quality_verdict` was built to catch. Stage 2 of the
screen selected the universe using the session's own daily bar — including
the day's range — and H0 is "buy at 04:30 and hold." So on survivors H0 is
"buy at 04:30 the names that will turn out to have had a big day." The rejects
are what buying the screen looks like without that knowledge, and it loses.

This is the finding from `session_aware_screening.md` §3 becoming load-bearing:
**no backtest here has simulated the screener.** The backtest universe is
chosen with the whole day known. The live TradingView screen at 04:30 knows the
gap and the volume so far, and nothing else. The truth for a live H0 lies
somewhere between −$9.81 and +$4.72, and nothing in this project can currently
say where.

Two smaller observations, recorded and not acted on:

- The trail is monotone: 5% → +$2.58, 8% → +$4.72, 12% → +$6.57 a trade. Wider
  was better at every step tested. Selecting on that would be selecting on a
  sweep; it is a direction for a future registration, not a result.
- H0 at 12% passes drop-top-10 at +$28,323. Whatever this is, it is not one
  stock.

## 4. What this closes and what it opens

**Closed.** The registered programme. MC5 as a candidate for live capital.
"Enter earlier on the same signals" as a direction — the signals are the
problem. The idea that an indicator confirmation on a pre-market gapper is
worth its latency.

**Open, in order.**

1. **Simulate the live screen.** Build the universe the way the TradingView
   feed builds it — the gap and the cumulative volume *at the time of the
   screen*, nothing from later in the day — and re-run H0 on that. This is
   the only way to find out whether the +$4.72 is the leak or the screen. It
   is the item `session_aware_screening.md` §4.5 called "not a small piece of
   work," and it is now the most important piece of work in the project.
2. **The tape check on MC5** (§1) — trail-hit rates on identical minutes
   across the two tapes. Small, and it decides whether −$97k is the tape or
   the truth.
3. **The entry-latency measurement** (`common/entry_latency.py`), already
   built and queued. Given §2 it is likely to confirm that the fill sits at
   the top of the signal bar; what it adds is *how much* of the move is in
   the bar, which sizes what a screen-and-hold entry is actually capturing.
4. A second registration, only after (1), with H0 on the honest universe as
   its benchmark and the trail width as an explicit hypothesis rather than a
   robustness read.

## 5. Corrections owed

- `screened_universe_results.md` presents MC5's +$8,209 as a survivor. It is
  before friction, and it does not survive the tape. A note goes at the top.
- `pine/README.md` and the MC5 Pine header say the same. Same note.
- `PROGRAM_INDEX.md` §7 should list the screener simulation first.

Tonight's paper session is MCL, apex off, band on — unaffected by any of this.
The point of it was live fills on the strategy as backtested, and that stands.
