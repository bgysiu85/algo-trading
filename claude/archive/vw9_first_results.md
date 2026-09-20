> **ARCHIVED 2026-09-08.** VW9 is rejected on history and paper-traded only for live data; its rules live in `vw9_strategy_spec.md`.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it. Applied to VW9 that correction cost roughly 73% of its
> headline; MCL went +$1,567 → +$161 and MC5 +$20,156 → −$400, on identical
> trades.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# VW9 — first contact with real data, 2026-09-05

The engine was built on 2026-09-04 and had never seen a real bar. This is the
whole §8 pre-flight plus the §7 grid, run over **374 cached sessions**.

**Verdict: reject in its current form.** Not because it loses — with one bug
fixed it makes money — but because the money is two names in a session block
whose fills the backtest cannot model. It fails the same drop-top-N test that
rejected V8, V9 and every `TRAIL_PCT` candidate.

Tools: `strategy/vw9/preflight.py` (§8.1/8.2/8.4/8.5) and
`strategy/vw9/study.py` (§7 grid, DV sweep, §10 detail). Both offline, ~1 min
for the full grid.

---

## 1. The pre-flight, first — because two of its answers were surprising

### §8.3 setup counts — PASS

| | Setup A | Setup B | mean/pair/session | threshold |
|---|---:|---:|---:|---|
| VW9-5 | 1007 | 236 | **3.32** | < ~5 ✓ |
| VW9-15 | 450 | 66 | **1.38** | < ~5 ✓ |

Both clear the go/no-go. Note Setup A is **81%** of triggers, and the spec
itself warns Setup A "is not a quality signal, only a frequency one."

### §8.1 bar availability — §0's premise holds

| tf | bar 9, p10 | median | p90 | §0 claimed | % reaching 06:30 |
|---|---|---|---|---|---:|
| 5m | 04:40 | **04:40** | 07:40 | 04:45 | **84.5%** |
| 15m | 06:00 | **06:00** | 09:00 | 06:15 | 77.0% |

Pre-market interval fill rate is **87%**, not the sparse tape that was feared.
So VW9-5 genuinely does reach the 04:00–06:30 window that carried 93% of V7's
P/L. The entire reason for building VW9 is validated.

### §8.5 VWAP degeneracy — not a problem

Median first 1% separation is at **bar 1** on both timeframes; 68% have
separated by bar 3. `MIN_VWAP_BARS = 3` is adequate, arguably conservative.
(Caveat: this measure conflates "VWAP is meaningless" with "price is near
VWAP". They are identical at bar 1 and genuinely different by bar 3.)

### §8.4 distributions — most gates are barely binding

5-minute bars:

| measure | n | p10 | median | p75 | p90 | current setting |
|---|---:|---:|---:|---:|---:|---|
| (close−ema9)/atr14 at trigger | 1243 | 0.11 | 0.59 | 1.22 | 2.03 | `MAX_EXT_ATR = 2.0` |
| bars below VWAP before reclaim | 1007 | 2 | 6 | 17 | 38 | `MIN_BELOW_BARS = 2` |
| pullback length (bars) | 236 | 1 | 1 | 3 | 4 | `MAX_PULLBACK_BARS = 6` |
| pullback depth (ATR) | 236 | 0.38 | 0.86 | 1.17 | 1.51 | `PULLBACK_CTRL_ATR = 1.5` |

Every threshold sits at or beyond p90 of its own distribution — they reject
roughly the top decile and nothing else. The strategy is looser than it reads.

### §8.2 dollar volume — the parameter §6 warned hardest about barely matters

§6: *"do not guess this one."* Measured, then swept end to end:

| $/min floor | trades | net | drop5 | PRE net |
|---:|---:|---:|---:|---:|
| 0 | 491 | +$9,813 | −$4,012 | +$11,296 |
| 10,000 | 432 | +$9,154 | −$4,567 | +$10,412 |
| **40,000** (shipped) | 407 | +$9,005 | −$4,643 | +$10,262 |
| 80,000 | 370 | +$3,556 | −$5,360 | +$4,867 |

Flat within ~$900 from 0 to 40k; only past 80k does it bite. It kills **0
names** on 5m at the shipped value, so the V5 share-floor disaster does not
repeat. The warning was right in principle and the parameter turned out not to
be the lever.

---

## 2. The bug that was the entire headline

**The engine had no price band.** §1's universe is "$2–20, RVOL ≥ 5×, float <
20m, top-2 pre-market gainer". Price is the only one of those four the engine
can enforce, and it enforced none of them. MCL has had `ENFORCE_PRICE_BAND`
since the apex sweep. VW9 never did — and nobody noticed, because the two
strategies' reports had never been read side by side.

It matters because IB returns **split-adjusted** history, so a small cap that
later reverse-split comes back inflated. VW9 was trading entries from **$0.30
to $4,152.11**:

| worst trades | entry | reason | net |
|---|---:|---|---:|
| ZNB 2025-09-04 | $1,976.01 | stop | −$3,306.79 |
| JDZG 2026-02-12 | $472.51 | vwap_lost | −$3,152.52 |
| PFSA 2025-09-11 | $4,152.11 | vwap_lost | −$2,828.59 |

| subset | trades | net | $/trade |
|---|---:|---:|---:|
| all (as shipped) | 643 | **−$31,296.17** | −$48.67 |
| inside $2–20 | 436 | **+$3,941.88** | +$9.04 |
| outside the band | 207 | −$35,238.05 | −$170.23 |

The headline loss was entirely an artifact of trading the adjustment factor.

The band carries the same residual **upward** bias it does for MCL: filtering
on adjusted price preferentially drops names that later reverse-split, and
reverse splits follow collapses. It removes an artifact; it does not clean the
sample.

---

## 3. The rule "the whole strategy rests on" is its worst rule

§3 states the hard rule: *never hold a long below VWAP*, and §5.3 makes it an
unconditional exit. §10 required "P/L with the VWAP gate disabled, so the
gate's contribution is measured rather than assumed." That was never run.

| | trades | net | $/trade | win% |
|---|---:|---:|---:|---:|
| VWAP hard exit ON | 436 | +$3,941.88 | +$9.04 | 21.1% |
| **VWAP hard exit OFF** | 407 | **+$9,004.63** | **+$22.12** | 29.5% |

**It costs $5,063.** The mechanism is structural, not bad luck:

| exit reason | n | net | avg | win% |
|---|---:|---:|---:|---:|
| `vwap_lost` | 386 | **−$49,252** | −$127.59 | **4.4%** |
| `trail_atr` | 161 | +$40,192 | +$249.64 | 68.9% |
| `stop` | 94 | −$22,273 | −$236.94 | 0.0% |

**189 of those 386 `vwap_lost` exits fired on the fill bar itself.** Setup A
enters because a bar *closed* above VWAP; §9 fills at the *next* bar's open;
if that bar closes back below VWAP the position is shut the instant it opens —
two ticks and commission each way. Price sitting on VWAP is exactly when it
oscillates across VWAP, so the rule fires hardest precisely where it carries
least information.

`use_vwap_exit` and `vwap_exit_grace_bars` are now parameters so this stays
measurable. A grace period of 1–2 bars recovers little (+$3,848 / +$3,371) —
most whipsaws were also out-of-band, so the band already removed them.

---

## 4. The §7 four cells — a clean answer to the question they were built for

Price band on, VWAP exit off, `MIN_TRIGGER_DV_PER_MIN = 40,000`:

| cell | wall-clock span | fixed_2r | ride_ema9 | **trail_atr** |
|---|---|---:|---:|---:|
| **A 5m EMA9** | 45 min | −$222 | −$1,445 | **+$9,005** |
| **B 15m EMA9** | 135 min | −$1,511 | −$1,074 | +$1,472 |
| **C 5m EMA27** | 135 min | −$1,256 | −$801 | +$2,773 |
| **D 15m EMA3** | 45 min | −$2,291 | −$6,671 | −$732 |

Two clean readings:

- **Bar size is the effect, not lookback.** The 5-minute cells (A, C) beat the
  15-minute cells (B, D) at *both* matched and unmatched wall-clock lookback.
  That is exactly the confound the four-cell design existed to separate, and
  it separates: granularity is worth something, smoothing length is not.
- **`trail_atr` wins in all four cells**, matching MCL's V3→V4 result that a
  fixed target caps the runners this universe is screened to produce.

---

## 5. Why it is still a reject

Best cell — A, 5m EMA9, `trail_atr`, band on, VWAP exit off:

| | |
|---|---:|
| net | +$9,004.63 |
| $/trade | +$22.12 |
| win rate | 29.5% |
| **drop top 1** | **+$2,860** |
| **drop top 3** | **−$3,770** |
| **drop top 5** | **−$4,643** |
| profitable symbols | **50 of 150 (33%)** |

**WLDS +$6,144 and PLYX +$5,146 together are $11,290 of a $9,005 result** —
more than the whole thing. Remove two names and it is negative.

And the block split is worse than the concentration:

| block | trades | net | $/trade |
|---|---:|---:|---:|
| **PRE** | 176 | **+$10,262.38** | +$58.31 |
| **RTH** | 222 | **−$1,257.52** | −$5.66 |
| POST | 9 | −$0.23 | −0.03 |

**All of the profit is in the pre-market block, and none of it is in RTH.**
§9 is explicit that pre-market fills are the ones the model cannot support —
outside RTH, IBKR takes Day Limit orders only, so there is no market order and
no resting stop. RTH is the one window where the fill assumptions are
believable, and there the strategy loses money.

So VW9's apparent edge is: **two names, in the hours the backtest is least
able to model.** Every one of the twelve grid cells has negative drop3 and
drop5. MCL V11, for comparison, has drop5 **+$1,883**.

---

## 6. What would change the verdict

Not more parameter sweeping — §8.4 shows the gates are barely binding and §8.2
shows the DV floor is nearly inert. The binding constraints are elsewhere:

1. **Setup A is 81% of triggers and is where the damage is** (−$56.36/trade vs
   Setup B's −$12.60 before the fixes). It is a reclaim counted whether or not
   it holds. A version of VW9 that trades **Setup B only** is a genuinely
   different and much more disciplined strategy, and it has never been tested
   on its own with the band on.
2. **The stop is structurally enormous.** Median R is **9.4% of price**, p90
   **20.7%**, because `structure_low` is the low of the whole bearish stretch
   (capped at `RECLAIM_LOOKBACK = 6` bars) and six bars of a collapsing small
   cap is a large move. §8.4 shows the stretch itself has median 6 bars and p90
   **38** — so on long stretches the cap truncates the structure and the stop
   is placed somewhere with no structural meaning at all.
3. **Pre-market fills.** Unchanged, and now the binding question for VW9
   specifically, since that is where 100% of its profit is.

---

## Caveats

- Same 374-session hindsight-selected pair set; still IB split-adjusted prices
  even inside the band.
- 33 of 407 pairs have no cached bars.
- VW9's own friction is unmeasured. The `after fric` columns apply MCL's
  $4.26, which was itself measured on one session under an exit mix that no
  longer exists (see `common/friction.py`).
- The §7 grid holds every other parameter at its spec default, twelve of which
  are uncalibrated guesses — §8.4 now gives distributions for four of them.
