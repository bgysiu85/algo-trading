# REGISTERED — H-E3: the trail widens as the trade proves itself (PRE-RUN)

**Nothing is built or run yet.** This is the registration. Ben's idea, 2026-09-17,
arrived as its own inverse — see §0.

Author: research chat, 2026-09-17. Build: the build chat. No program logic under
`D:\Trading` was changed to write this. **Committed to the repo 2026-09-19 with
amendment A (PRE-RUN) below** — until then it existed only as a project doc, and
in this project the commit is the registration.

---

## 0. Provenance, and the proposal that was rejected first

Ben proposed the opposite rule: **trail % should shrink as price rises**, so the
dollar giveback stays constant. His arithmetic was right — a 5% trail on a $4
entry risks 20c, and 40c once price reaches $8.

It was rejected on three existing measurements, recorded here because they are
the prior this registration has to beat:

1. **The fraction of the gain given back already shrinks.** At $4.20 a 5% trail
   costs 105% of the unrealised gain; at $8.00 it costs 10%; at $20 it costs 6%.
   The dollars grow, the proportion falls. The fixed-% trail is already doing
   what the proposal wanted.
2. **The shape has been tested.** A fixed-cent stop *is* "constant dollars,
   shrinking %" — 15c is 7.50% at $2 and 0.75% at $20. `cent_stop_decision.md`:
   monotone worse at 10c/15c/20c, and the gap opens above $7, which is where
   MCL's 5% trail makes all of its money (+$5.40/trade at $7–12, +$8.70 at
   $12–20, against −$0.63 and +$4.73 for 15c).
3. **It cannot touch the losers.** `entry_excursion_result_20260914.md` splits
   the book: "drawdown first" 1,156 trades (29.3%), median MFE $38.12,
   **+$19.13/trade**; "move first" 2,794 trades (70.7%), median MFE **$8.46**,
   **−$22.73/trade**. The losing 70.7% peak about 2% above entry — a
   gain-conditioned trail never activates on them. Its entire effect lands on
   the 29.3% that carry the P&L.

**The inverse is what this registers.** Ben asked for it in the same exchange.

---

## 1. The rule

```
peak      = running max of high since entry        (monotone by construction)
level_pct = peak * (1 - TRAIL_PCT/100)             # the shipped 5% trail
level_gb  = peak - F * (peak - entry_px)           # give back F of the run
stop      = min(level_pct, level_gb)               # the WIDER of the two
```

`min` because a lower stop is a wider one. Near entry `level_pct` is lower and
binds; once the trade has run, `level_gb` is lower and binds. The crossover is at
`peak = entry * F / (F - 0.05)` — $5.00 at F = 0.25.

Effective trail, entry $4.00, F = 0.25:

| peak | 5% level | giveback level | binding | effective trail |
|---:|---:|---:|---|---:|
| 4.20 | 3.990 | 4.150 | 5% trail | 5.00% |
| 5.00 | 4.750 | 4.750 | crossover | 5.00% |
| 6.00 | 5.700 | **5.500** | giveback | 8.33% |
| 8.00 | 7.600 | **7.000** | giveback | 12.50% |
| 12.00 | 11.400 | **10.000** | giveback | 16.67% |
| 20.00 | 19.000 | **16.000** | giveback | 20.00% |

**One new parameter, `F`.** `TRAIL_PCT` is inherited at 5.0 and not swept —
sweeping both would be a two-dimensional fit on a book that has rejected
one-dimensional ones.

**Degenerate case, handled by the arithmetic rather than by a branch:** if the
trade never trades above entry, `peak − entry ≤ 0`, so `level_gb ≥ peak` and
`level_pct` always binds. The rule is bit-identical to today's trail on every
trade that never gets ahead. `F = None` must also be bit-identical — the
project's standing requirement for a new engine parameter.

---

## 2. Keyed to PEAK gain, not current gain — and why that is not a detail

Ben's follow-up question: when price reverses, should the % tighten back?

**No, and the reason is mechanical before it is empirical.** Keying the trail %
to the *current* gain makes the stop chase the price down. Entry $4, peak $8,
trail widened to 10%:

| price | current gain | trail % | stop level | gap |
|---:|---:|---:|---:|---:|
| 8.00 | 100% | 10.00% | 7.200 | +0.800 |
| 7.60 | 90% | 9.50% | 7.240 | +0.360 |
| 7.40 | 85% | 9.25% | 7.260 | +0.140 |
| 7.30 | 82.5% | 9.12% | 7.270 | +0.030 |
| 7.25 | 81% | 9.06% | 7.275 | **breached** |

The stop rises toward the falling price and fires almost immediately. A rule
written to allow 10% of room delivers nearly none, and it breaks the invariant
that makes a trailing stop a trailing stop: **the level never falls back.**

Keyed to `peak`, the level is monotone non-decreasing by construction. **Assert
it anyway**, every bar, and fail loudly — the engine should not depend on a
reader having done the algebra.

**The empirical half of the same answer already exists.**
`profit_floor_RESULT_20260917.md` is the "protect gains on the way down" rule
in discrete form, and its decomposition is the reason not to build the
continuous one:

| | MCL | MC5 |
|---|---:|---:|
| losers rescued | +12,343 | +8,332 |
| winners cut | (10,780) | (10,153) |
| re-entry knock-on | (1,656) | (2,103) |
| **net** | **(93)** | **(3,924)** |

MCL REFUSED as a wash (bootstrap P = 0.470); MC5 NOTHING. 148 MCL runners cut
cost $8,059.77 on their own. **A tightening rule buys back roughly what it
sells.** H-E3 is the mirror of this and must be read against it: if widening
works, its decomposition should show the *opposite* signs in the same two rows.

---

## 3. Cells

| | cell | status |
|---|---|---|
| **TW-25** | F = 0.25 | **PRIMARY** |
| TW-20 | F = 0.20 | boundary |
| TW-33 | F = 0.33 | boundary |
| **control** | F = None — today's 5% trail, must be **bit-identical** | required |

Three F values, chosen as a boundary check around one pre-named primary, not as
a menu. **If the best cell is TW-20 or TW-33 the boundary check fires** and the
range is in the wrong place — the project's standing rule, which is what closed
the cent stop.

`profit_floor` **off** in every cell. Two exit mechanics changed at once is not a
measurement.

Reported, not scored: the decomposition of §4.3; the same rule on MC5.

---

## 4. Readings

### 4.1 The five

At $4.26, then at $1.00 and $8.92, on the point-in-time book (**see amendment A
— the universe moves to v2**). The baseline must reproduce the published MCL
book exactly before anything else is read.

1. Δ per trade > 0 **and** Δ per symbol-day > 0 — **both denominators, and
   disagreement is a refusal**, not a tie-break;
2. both temporal halves positive;
3. **drop-top-3 and drop-top-5 on the delta**, not just on the level;
4. cluster bootstrap by symbol, 95% CI clear of zero;
5. beats the 95th percentile of random removal of the same trade count.

### 4.2 The concentration gate is the one that matters here

`mcl_rejected_mechanics.md` §4: the confirm-N trailing stop produced **+$8,300**
and was rejected because **91% of the gain sat in one quartile** and 80 of 174
symbols improved — worse than a coin flip. A widening trail is the same family of
change and will fail the same way if it fails. **Report symbols-better vs
symbols-worse alongside the net**, and treat a minority-of-symbols result as a
refusal regardless of the total.

### 4.3 Mechanism — the decomposition that makes this readable

Paired against the control, per trade:

- **runners** (reached +10%): count, and Δ dollars;
- **losers**: count, and Δ dollars — expected **negative**, because a wider trail
  gives back more before stopping;
- **hold time**: median bars, control vs cell;
- **re-entry knock-on**: trades that exist in one arm and not the other.

If widening earns its money anywhere it must be `runners` positive by more than
`losers` negative. If instead the total is positive but `runners` is flat, the
result is noise wearing a mechanism's clothes.

### 4.4 The operational cost, which the P/L does not contain

`mcl_robustness_analysis.md` flagged it for the wider-trail sweep and it applies
here unchanged: **the trailing stop is software-managed inside the running
process.** There is no broker-side stop outside RTH. A longer median hold is more
wall-clock exposure to a crash or disconnect leaving a position unprotected.
**Report the hold-time distribution and the worst single trade**, and argue any
adoption on those terms as well as on the net column.

---

## 5. Registered prediction

- **MCL: positive on the level, NOTHING on the gates.** Δ per trade +0.50 to
  +3.00, failing reading 3 (drop-top-N on the delta) or 4.2's symbol count.
  Confidence: **moderate-to-high**, and the reason is specific — every trail
  change measured on this project's data has been "five names, and largely the
  same five" (`mcl_rejected_mechanics.md` §5, where WLDS is the single largest
  contributor at every width).
- **Direction of the decomposition:** runners positive, losers negative, hold
  time up. If runners come out flat, the total is not to be believed whatever it
  says.
- **Boundary:** F = 0.33 expected to beat F = 0.25 on the raw net, which would
  **fire the boundary check** rather than recommend F = 0.33.
- **MC5:** worse than MCL. Coarser bars mean larger gaps through a wider stop,
  and `profit_floor` already found MC5 gapping below the floor on 56% of floor
  exits.

**A NOTHING here closes the trail-shape lever for MCL**, alongside the cent stop
(closed), the width sweep (never adopted), confirm-N (rejected) and the profit
floor (refused). That is a useful closing, and it should be written as one.

---

## 6. Implementation note

The hook already exists. `strategy/mcl/mcl.py`:

```python
def stop_level(peak: float, trail_pct: float, trail_cents: float | None = None) -> float:
    if trail_cents is not None:
        return peak - trail_cents
    return peak * (1.0 - trail_pct / 100.0)
```

The change is this function plus one parameter threaded through
`backtest_session`. Preserve, unchanged:

- the trail level is derived from the peak **as of the previous bar** (the same
  bar that sets the peak must not also be allowed to stop on it);
- `gap_fills=True`: the fill is `min(level, open) − SLIPPAGE_TICKS × TICK`.
  Pricing gap-throughs at the level overstated MC5 by $20,394 against a $20,156
  headline — the whole apparent edge;
- the exit order: trail first, then target, then `window_close`, then
  `green_hold`, then the signal exit, then the time cap.

`trail_cents` is already the constant-dollar form — i.e. **Ben's original
proposal is already reachable** with `trail_cents = entry × 0.05`. If the build
chat wants the rejected direction measured rather than argued, that is a free
extra arm and should be reported, not scored.

**And read the rule back as a measurement before trusting any number.** The first
run of the confirm-N study was gated on `if trail_confirm_bars > 0:` — a test on
a *parameter*, not on price — which made the `elif last_of_session` below
unreachable. Positions open at 09:30 were never closed and their trades vanished:
450 rows instead of 496, the missing P/L absent rather than zero. **Trade count
catches that; P/L does not.** Assert the cell's trade count against the control's
before reading a single dollar figure.

---

## 7. Go / no-go

**Adopt** only on all five readings at $4.26 *and* $8.92, a majority of symbols
improving, a decomposition where `runners` carries the gain, and a hold-time
change Ben accepts as an operational risk.

**Refuse** on any single gate. In particular a large net with a minority of
symbols improving is a refusal, not a finding — that is the exact shape that has
been rejected twice already on this book.

---

## AMENDMENT A — PRE-RUN, 2026-09-19, on committing this to the repo

Two changes, both before any code exists.

### A.1 The universe moves to v2, which is the deciding file

§4.1 as written names **"the v1 p50 point-in-time book"** and requires the
baseline to reproduce **MCL 3,960 trades / (8.81) per trade**. That was correct
on 2026-09-17 for about half a day. `screen_pairs_pit_itch_p50.json` was
superseded the same evening by **`screen_pairs_pit_itch_v2.json`** — the capture
ladder measured against the consolidated tape's cleared volume per half hour
rather than chained — and every published baseline has sat on v2 since.

**So this runs on `screen_pairs_pit_itch_v2.json`, and the baseline must
reproduce MCL 3,908 trades at (8.97) per trade exactly** before a single
dollar figure is read. Running it on v1 would produce a result on a superseded
universe that no other study could be compared against, which is the defect the
population check was added to catch.

Nothing else in §4 changes. The five readings, the concentration gate, the
decomposition and the operational cost all stand as written.

### A.2 What 2026-09-18 and 19 do and do NOT say about this rule

Three measurements landed after this was written, and all three close a *wider
stop* — which is close enough to this rule to be mistaken for it. Recorded here
so that it is not, in either direction.

**They close the UNIFORM wider stop, three ways:**

- **The width sweep** (`mcl_rejected_mechanics.md` §5): six widths against 5%,
  every confidence interval straddling zero, and widening makes more symbols
  worse than better (8%: 61 better, 111 worse).
- **H-R1, the rebound census** (2026-09-18): on MCL's one-bar trailing-stop
  exits, giving the position another 2.5% of room means the further fall arrives
  before the recovery **67.6%** of the time, and another 5% still **54.5%**.
- **ORB amendment F** (2026-09-19, the ORB chat, independently): winners barely
  touch the stop — median adverse excursion **0.63R** against losers' **5.51R** —
  and only **9.1%** of losers were rescuable against a registered 25% gate. ORB
  closed permanently on it.

**None of them touches H-E3, and the reason is in §0 item 3 of this document.**
H-E3 is `min(level_pct, level_gb)`: bit-identical to the shipped 5% trail until
the peak reaches `entry × F/(F−0.05)` — $5.00 on a $4 entry at F = 0.25. It only
ever widens on a trade that has **already run 25%**. The population all three
measurements describe is the opposite one: trades that never got ahead, stopped
out at or near their entry. A gain-conditioned trail never activates on them.

**So the honest reading is narrow in both directions.** H-E3 survives evidence
that killed the uniform version, and it survives it *by construction* rather than
by performing better — which is not the same as support, and must not be quoted
as any. What the three do supply is the prior for §5: the one population where a
wider stop has been measured and found wanting is not the one this rule acts on,
so the registered prediction of "positive on the level, NOTHING on the gates"
stands unchanged.

**And the mirror in §2 is now the sharper test.** `profit_floor` tightened and
bought back roughly what it sold (+12,343 rescued, (10,780) cut, net (93)). If
widening is real, §4.3's decomposition must show those two rows with their signs
reversed and the runners row carrying it. If it shows a positive total with flat
runners, the number is noise wearing a mechanism's clothes, and this document
said so before it ran.
