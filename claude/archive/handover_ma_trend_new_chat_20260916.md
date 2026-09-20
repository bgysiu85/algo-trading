# Start here — building MA-TREND

You are the chat that builds **MA-TREND**, a moving-average trend-continuation
strategy for US equities intraday. This message is your brief. It was written by
the research chat that produced the spec; assume no shared context beyond it.

---

## 1. Read these first, in this order

1. **`claude/ma_trend_spec_20260916.md`** — the spec. Every rule, every
   parameter, the go/no-go, and the gate. This is the contract.
2. **`claude/PROGRAM_INDEX.md`** — §1 hard rules, §4 standards of evidence, §5
   traps. Non-negotiable and they pre-date you.
3. **`claude/orb_strategy_spec.md`** §11 — the model for a go/no-go fixed before
   code. MA-TREND's §9 is built on it.
4. **`claude/pullback_break_v6_RESULT_20260916.md`** — the closest prior attempt.
   Read the verdict before you start.
5. **`claude/source_videos_20260907.md`** §12 — where the rules came from and
   what is wrong with the source.

Do not start from the video. Start from the spec.

---

## 2. THE GATE — three things are not true yet

**Do not write strategy code until all three are cleared.** The spec's §8 is not
a caveats appendix; it is a gate, and it is there because two of the three would
otherwise be discovered halfway through a run.

**2.1 The free pre-check, and it can kill the whole thing.**
The central premise is that the edge lives in an **interior optimum** —
`ma20_slope` too flat means no momentum, too steep means overextended, good in
the middle. Every test in this project reads **directionally**:
`REGISTERED_bar_shape_20260916.md` is explicitly *"median split, HIGHER IS
BETTER"*, and `entry_split_result_20260914.md` read quartiles the same way.
**A middle-is-best optimum is invisible to a monotone test.**

So: **re-read `entry_split`'s existing quartile tables for an interior peak in
the trend family.** No new data, no new run, no code. **If there is no interior
peak anywhere, stop — the premise is gone** and nothing else in the spec should
be built.

This is the first thing you do.

**2.2 The tape has an undiagnosed defect inside the window.**
`pullback_break` v2–v6 carry an open item: **two price scales interleaved on 259
symbol-days**, with **290 trades moving more than 25% in a single bar, 235 of
them in the 08:00 hour**. The v6 verdict: *"stop tuning; diagnose the 08:00
interleaved-price defect."* A moving-average rule is **more** exposed than a
break rule, because one bad print poisons the MA for the next twenty bars.

**2.3 The SMA200 does not exist on the current cache.**
`entry_place_built_20260915.md`: the archive holds **04:00–09:30 slices only**,
so a 200-bar mean on the 1-minute view is **pre-market only**, and on the
5-minute view it is *"reported absent."* MA-TREND's §3.7 overhead veto and its
`sma200` exit both need **full-day `ohlcv-1m`**.

Do not approximate it from the pre-market slice. That is a different quantity
wearing the same name, and this project has been burned by exactly that before.

> **The full-day pull has three consumers**: MA-TREND's SMA200,
> `entry_place`'s `ema200_dist`, and the RVOL screen rule ORB is blocked on.
> Price it once, pull it once.

---

## 3. Hard rules you inherit

From `PROGRAM_INDEX` §1 and §4. These killed VW9, MC5, every `TRAIL_PCT`
candidate, the scale-out, the pyramid, H0, and six pullback registrations.

- **Register before you run.** Rules and pass criteria committed *before* the
  first result exists; the commit hash is the timestamp.
- **The `$2–20` price band, enforced at ENTRY.** VW9 shipped without it and
  traded at $4,152/share — an adjustment factor, not a price.
- **`gap_fills=True`, peak seeded from the entry price, never the entry bar's
  high.** These two corrections moved MC5 from +$20,156 to −$400 on identical
  trades.
- **Report at all three friction levels** — $1.00 / $4.26 / $8.92 per 100-share
  round trip. Commission-only is not "after costs."
- **Two denominators**, per trade and per symbol-day. **A disagreement is a
  refusal, not a result.**
- **drop-top-N on the level and on the delta.** Say `n/a`, never `$0`.
- **Both halves** of a temporal split, split point not swept.
- **The sample is SESSIONS, not trades.**
- **Boundary check on any grid.** An optimum on the edge is being arbitraged.
- **A control whose output is indistinguishable from the failure it detects is
  not a control.** This is the recurring failure here. For MA-TREND
  specifically: a gate conjunction that reproduces the ungated trade list prints
  0.00 and renders as NOT MATERIAL. **Report trade count and overlap, not only
  P/L.**
- **`var/state/holdout.json` is cut 2026-09-07 and unspent.** MA-TREND does not
  spend it. Nothing is ready to.

---

## 4. The multiplicity problem, pre-committed

The gate conjunction is **800 cells** before the timeframe map: 2 setups ×
slope band (5) × extension (2) × touches (2 directions) × acceleration veto (2)
× alignment (2) × exits (5).

The spec names a **primary cell before the run** — slope quintile 3, `EXT_MAX`
at the 80th percentile, touches two-sided and reported both ways, acceleration
veto ON, alignment OFF, `EXIT_MODE = trail_pct`, the session timeframe map.
**Everything else is the distribution, not a candidate.**

Report where the chosen cell sits in that distribution, and **run the
equal-weight ensemble beside it** — ReSolve's 1,226 GEM variants had the
published spec beating only **61%**, and the ensemble drew down 13.2% against
the median single spec's 17.4% at no cost.

---

## 5. Order of work

1. **§2.1's free pre-check.** If no interior peak, stop and say so.
2. **Diagnose the 08:00 interleaved-price defect.**
3. **Price and pull full-day `ohlcv-1m`** — three consumers, one pull.
4. **Settle the breadth criterion** that replaces `orb_strategy_spec.md` §11
   criterion 2, and re-score MC5 under it in the same pass. §11.1 is explicit
   that relaxing a pre-registered bar after seeing a result fail it is the sin
   the section exists to prevent.
5. **Pre-flight measurements**: `slope20_n` and `ext_n` quintile profiles, touch
   distribution, trigger counts per setup, and **`R / entry_price` median and
   p90 per stop rule**. ORB's own pre-flight eliminated a stop mode on exactly
   this measurement before any entry logic existed.
6. **Only then** write `strategy/ma_trend/`, unit-test the state machine on
   hand-built bars, and run the grid under the spec's §9.

---

## 6. What to refuse

- **Sweeping `DEPTH_MIN`/`DEPTH_MAX` independently.** The 40–60% retracement
  band is the third of three independent arrivals, and the anchor question —
  range versus impulse — is already registered as ORB's `zone_impulse` cell.
  **Whatever ORB's §10.3 count returns governs both documents.** One
  measurement, two consumers.
- **Adding indicators.** 22 features across 11 families cleared **0** on this
  universe; `macd_margin` was the best at 1.56× against a 1.86× requirement.
  The spec is EMA9, SMA20, SMA200 and nothing else, deliberately.
- **Fibonacci ratios as constants**, harmonic patterns, ICT/SMC constructions,
  and volume-profile or value-area work on the pre-market window (1.5% tape
  capture — the distribution cannot be built).
- **Re-opening MCL.** It loses **~$6.26/trade gross of all friction**. Nothing
  on the cost or fill side rescues it.
- **"Promising, worth another sweep."** That phrase kept the scale-out alive
  through four studies before the fill audit killed it. Any single failure in
  §9 is a rejection, written up whichever way it goes.

---

## 7. The honest prior — read this before you get attached

- **Six registrations, six NOTHINGs** on the pullback line, best case
  **(9.90)/trade at $4.26 friction**. None of them used MA-TREND's components,
  so this is genuinely untested — but it is the same *family* on the same
  universe, and that family just failed six times.
- **Every one of MA-TREND's features was individually measured below the bar** —
  `ma20_dist` 1.46×, `ma20_slope` 1.37×, against 1.86× needed.
- **Nothing in this project is profitable.** Every arm of every strategy loses at
  every friction level.
- **The source says the method cannot be programmed**, in his own words:
  *"there's so many criteria that go into identifying a high probability
  breakout or retracement from a low probability one."* So a faithful
  implementation is unavailable, and **a failure cannot distinguish "the idea is
  wrong" from "the subset is not the idea."** That is registered in the spec's
  banner and it must survive into the write-up.

**The premise that survives all of that is narrow and specific: that the edge is
in the SHAPE of the relationship (an interior optimum) and in the CONJUNCTION,
neither of which has been tested.** Test that. Do not test "moving averages."

---

## 8. How to work with Ben, and how to deliver

- **He is not proficient in PowerShell or git.** Send **exact copy-paste
  commands with real paths, one command per line.** Never describe what to do.
- **Windows, PowerShell, repo at `D:\Trading`.** Keep every `.ps1` pure ASCII;
  `Tee-Object` writes UTF-16, so write reports from Python.
- **Write tooling in Python, not PowerShell** — you can run and test Python
  before handing it over; you cannot validate PowerShell.
- **Delivered files go to `D:\Trading\Claude outputs`**, never the repo root.
- **Code ships as a git bundle**: build and test in the cloud clone,
  `git bundle create`, write the bundle into `D:\Trading\Claude outputs\`, and
  give Ben the `git fetch` line by local path.
- **Study and analysis results go out two ways** — a **published artifact page**
  (styled HTML, negatives bracketed and red per number) **in addition to** the
  raw `.txt` report. Not instead of.
- **One branch. Work on `main`.** Production is a TAG and a second working copy
  (`D:\TradingProd`), never a branch, and `D:\TradingProd\var` is a directory
  junction to `D:\Trading\var`.

> **Coordination warning.** Another chat owns program logic in this repo and has
> been committing daily; `claude/branch_drift_20260916.md` exists for a reason.
> **Agree with Ben which chat commits before you write a line**, or deliver as a
> bundle and let the other chat fetch it.

---

## 9. Your first message back to Ben

Tell him which of §2's three gate items you are starting with, and what result
would stop the project. If §2.1 comes back with no interior peak, **say so and
stop** — that is a successful outcome, not a failed one, and it costs a day
instead of a fortnight.
