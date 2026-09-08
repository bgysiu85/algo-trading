# Pre-market hypotheses — pre-registration, 2026-09-08

**This document was committed before any of the runs below were made.** The
commit hash is the timestamp. Nothing in it changes after a result is seen: a
rule that needs changing is a new hypothesis, and it spends from the budget.

Ben's request: everything so far has tested someone else's idea against this
data. Test what the data itself suggests. Long only, pre-market first, RTH as
a separate programme once a session-aware screen exists.

## Why pre-register

With 29 million bars and freedom to search, something profitable-looking on
the training set is guaranteed to turn up. That is not a finding, it is a
property of search. Every video strategy in this project looked good before it
met drop-top-N. So: a small fixed set of hypotheses, each with its rule and its
pass criteria stated here first, and the locked holdout touched once, by one
survivor, at the end.

## Data

| | |
|---|---|
| Bars | `bar_cache_xnas/3d_to_2000` — XNAS.BASIC, TRF-inclusive, raw prices |
| Universe | `var/state/screen_pairs_consolidated.json` (survivors, scored) and `var/state/screen_rejects.json` (rejects, the leak-control population) |
| Training | 381 sessions, 2024-07-05 → 2026-01-09, halves split at 2025-04-08 (`holdout.json`) |
| Holdout | 164 sessions from 2026-01-12, **sealed**, one survivor may touch it once |
| Session | 04:00–09:30 ET, flat at 09:30 |
| Size | 100 shares flat, every trade, so size never explains a result |
| Costs | `ibkr_tiered` commission per order **plus** the −$4.26 per round trip of slippage measured live on 2026-09-03 (n = 2 sessions; the only live measurement there is) |
| Fills | Entry at signal-bar close + 1 tick. Exits: `gap_fills=True`, peak seeded at entry price, stop wins ties — the corrected model of 2026-09-05 |
| Price band | $2–20 at entry, as every engine here applies it |

The tape is XNAS.BASIC and not EQUS.MINI because the pre-flight showed
EQUS.MINI publishes a median 4.8% of consolidated volume. Every earlier
screened-universe result ran on EQUS.MINI, so the benchmark is re-run on the
same tape as the hypotheses. Nothing here is comparable to a figure computed
on the other tape.

## What the data has said so far — the source of the hypotheses

1. **P/L is carried by a handful of runners.** Scale-out, pyramid and scale-up
   all failed for one reason: anything that reduces exposure to a runner costs
   more than the round-trips earn (`mcl_scale_up_decision.md` §3).
2. **Exiting on an indicator turn while the trail is intact loses money.**
   Apex exits were −$544 over 213 exits at a 27% win rate; every trailing cut
   was positive (`mcl_apex_macd_sweep.md`).
3. **The cost floor is high.** ~$1.37 commission + ~$4.26 friction per round
   trip is over 1% of a 100-share position at $5. Scalps cannot clear it; the
   strategy needs multi-percent moves.
4. **MCL's entry conditions carry almost no signal.** +$0.85/trade gross out
   of sample (`screened_universe_results.md`). Five indicator conditions
   selected trades no better than chance after costs.
5. **The edge dies with order fragmentation.** MC5 turns negative between 3
   and 4 orders per round trip. One entry, one exit.

Together these say: the entry matters less than the exit; the exit should be
a trail and only a trail; and the test of any rule is whether the tail pays
for the losers after friction. That is what H1 and H2 test, and H0 tests
whether the *screen alone* already does it.

## The budget: four runs

| id | what | new code |
|---|---|---|
| **B0** | MC5, shipped config, on XNAS.BASIC | none — benchmark |
| **H0** | Buy the screen | yes |
| **H1** | Runner | yes |
| **H2** | Pre-market opening range | yes |

Trail width 5% and 12% are *reported* alongside every hypothesis's primary 8%
as a robustness read. They are not selected on. A hypothesis whose sign
flips between 5% and 12% has failed as fragile, whatever the 8% number says.

No other parameter is varied. No hypothesis is re-run with a changed rule.

### B0 — the benchmark

MC5 at its shipped configuration, run on XNAS.BASIC over the training
sessions. Every hypothesis must beat it. If MC5's own edge does not survive
the fuller tape, that is a finding in its own right and it is recorded.

### H0 — buy the screen

*Hypothesis: the pre-market gainer screen is itself the edge, and every
entry rule layered on it has been subtracting value.*

- Entry: the close of the first bar at or after **04:30 ET** whose close is
  inside $2–20. One entry per symbol-session.
- Exit: 8% trail from the peak since entry (peak seeded at entry price), or
  09:30.
- Falsified if: net after costs ≤ 0, or drop-top-5 ≤ 0.

H0 is the control the other two are read against. If H0 passes and H1/H2 do
not beat it, the entry logic is worthless and the answer is "buy the screen."
If H0 fails, the screen selects names that fade, and an entry rule has to
earn its keep against that.

### H1 — runner

*Hypothesis: a new session high on expanding volume identifies the runners
the P/L depends on, early enough to hold them.*

- Entry: bar close where `close > max(high of all prior bars this session)`
  **and** `volume ≥ 2 × mean(volume of prior bars this session)`, with at
  least 15 prior bars so the session high means something. Close inside
  $2–20. One entry per symbol-session.
- Exit: 8% trail, or 09:30.
- Falsified if: net after costs ≤ 0, or drop-top-5 ≤ 0, or it does not beat
  H0 on net per trade.

### H2 — pre-market opening range

*Hypothesis: the first half hour of pre-market defines a range whose upside
break, on volume, is a better-timed version of H1.*

- Range: high and low of bars from 04:00 to 04:29 ET inclusive; requires at
  least 10 bars in it (the same idea as ORB's `MIN_RANGE_BARS`, measured on
  this tape to be a real choice).
- Entry: the first bar close at or after 04:30 ET with `close > range high`
  **and** `volume ≥ 2 × mean(volume of range bars)`. Close inside $2–20. One
  entry per symbol-session.
- Exit: 8% trail, or 09:30.
- Falsified if: net after costs ≤ 0, or drop-top-5 ≤ 0, or it does not beat
  H0 on net per trade.

## Pass criteria — all of them, on the 381 training sessions

A hypothesis survives training only if **every** line holds:

| # | criterion | why |
|---|---|---|
| 1 | Net > 0 after tiered commission **and** −$4.26/RT friction | the only live cost measurement there is |
| 2 | Net > 0 with the top 5 symbols by P/L removed | concentration is what killed everything else |
| 3 | Net > 0 on both training halves (split 2025-04-08) | one regime is not a result |
| 4 | ≥ 200 trades and ≥ 100 distinct symbols | so that drop-top-5 means something |
| 5 | Leak cut: `common/leak_control.quality_verdict` does not reject — the survivor edge must not depend on stage 2's read of the session's own daily bar | stage 2 leaks by construction |
| 6 | Beats B0 on net per trade **and** on drop-top-5 net | a new strategy that does not beat the shipped one is not a result |
| 7 | Same sign at trail 5% and 12% | fragile is failed |

Not required: a positive median trade. A tail strategy is expected to lose
more often than it wins.

## What happens next

**If one hypothesis survives**, it runs once on the 164 locked sessions with
the rule exactly as written above. Criteria 1–4 and 7 apply there. Pass or
fail, the holdout is spent for this programme.

**If more than one survives training**, the one with the higher drop-top-5
net goes to the holdout. The other does not — it stays a training result.
Choosing the best of two on the holdout would be selecting on the holdout.

**If nothing survives**, the holdout stays sealed and this programme ends. A
second programme needs a new registration and new hypotheses; it does not get
to adjust these.

**Order of execution:** B0 and H0 first, then H1 and H2. Results are recorded
in one report, all four, whether or not they pass.

## Not allowed

- Changing a rule, threshold, window or trail after seeing any result.
- Adding a filter to rescue a near-miss.
- Running the holdout more than once, or on more than one candidate.
- Quoting a training figure as a result. Only the holdout figure is one.
- Dropping a criterion because the others passed.

## Not addressed here

The RTH programme. Its hypotheses can be written now but not run honestly: no
backtest here has ever simulated the screener, and for an RTH strategy the
instruction "trade these names at 14:00" has no source until the session-aware
screen in `session_aware_screening.md` exists. Registering RTH hypotheses
before that would be registering something untestable.
