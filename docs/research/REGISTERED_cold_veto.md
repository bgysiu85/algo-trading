# REGISTERED — H-B4: no new entries after 07:00 on a session that reads cold at 07:00

From `claude/handover_luck_vs_edge_and_entry_quality_20260917.md` Part B, B4,
and `PROGRAM_INDEX` §7 item 18. `ladder_and_regime_20260911.md` §4 found the
**same-day** regime (from the daily archive, not knowable until the close)
separates MCL's trades — hot − cold **+$5.86/trade, p = 0.024, monotone** —
while yesterday's regime does not (p = 0.30, non-monotone). Two caveats
carried from there: the ceiling test was added after seeing the ordering, so
0.024 is suggestive; and every bucket is negative, so a perfect gate leaves
MCL losing. This registration is the one move that result licensed — an
intraday reading, at a fixed clock time, of the same three things — built
**as a veto only**. **Committed before the code that runs it exists.**

## 1. The 07:00 reading, exactly

The daily composite (`common/regime.py`) ranks three market-wide quantities:
how many names moved, how far the leader moved, and what share of the movers
gave the move back. None of those is knowable at 07:00 from the daily
archive. The 07:00 reading is the same three quantities over **the names the
screen had surfaced by 07:00** — every point-in-time record of the session
with `first_seen ≤ 07:00 ET` that has printed at least one bar before 07:00 —
which is the list a live trader has in front of it at that minute:

| component | daily composite | 07:00 reading |
|---|---|---|
| breadth | movers ≥ 30% from prior close, market-wide, volume-guarded | **`n_visible`**: names surfaced by 07:00. Every one is a mover with volume by the screen's own rules (≥ 20% gap, ≥ 100k shares), so the screen is the guard |
| leader | the leading gainer's move from prior close | **`lead`**: max over visible names of (pre-market high through 06:59 ÷ the session's first printed open) − 1 |
| give-back | share of movers retaining < 50% of the day's move into the close | **`round_trip`**: share of visible names whose last price before 07:00 retains < `RETAIN_MIN` = 0.5 of their own pre-market move (high − open); names with no move are excluded from the share, as `regime.day_features` excludes them |

**Why the session open and not the prior close.** The point-in-time file does
not carry a prior close, and the archive's daily close is the defect
`screen_sim.prior_closes` exists to repair. Reaching for it here would put a
repaired-vs-raw baseline choice inside a regime reading. The 04:00 open is on
the tape, is the same reference for every name, and measures the pre-market
run itself — which is the move the trader is in. It is a different quantity
from the daily composite's and is named as such; nothing here is claimed to be
`regime.composite` at 07:00.

**Terciles, point-in-time.** Each session's three components are converted to
percentile ranks **within the prior sessions only** (share of prior rated
sessions with a value ≤ today's; `round_trip` negated so bigger is hotter, as
`regime.composite` does), averaged into one composite in [0, 1]. The session
reads **cold** when its composite is ≤ the lower tercile of the prior rated
sessions' composites, each of those computed the same way at its own time.
Nothing about today enters today's cut. A session with fewer than
`MIN_NAMES` = 5 names visible at 07:00 reads **cold without rating**, as
`regime.classify` labels a day with too few movers: too few names by 07:00 is
the coldest reading available, and dropping such days would bias the sample
warm. The report prints the two kinds of cold separately.

**Warm-up.** Until `MIN_HISTORY` = 60 rated prior sessions exist, no session
is rated and the veto is inert (a count-cold session is still vetoed, because
that rule needs no history). The number of inert sessions is printed.

## 2. The rule, exactly

On a session that reads cold at 07:00, **no new entry is taken on any bar at
or after 07:00 ET**, on either strategy. Entries before 07:00 are untouched;
positions open at 07:00 are managed and exited by the published engine. The
mechanism is `entry_gate` (H-B3's hook, AND-ed with the rule, `None`
bit-identical): a series that is True on every session-day bar before 07:00
and, on a cold session, False from 07:00. Signal-ordinal, as every gate.

No parameter is chosen from data: 07:00 is the handover's clock, `MIN_NAMES`
and `RETAIN_MIN` are `regime.py`'s, the tercile is `regime.classify`'s, and
`MIN_HISTORY` = 60 is stated here once. There is no reported cell; one form.

## 3. Cells, controls and readings

Four books from one pass per session: MCL, **MCL-veto**, MC5, **MC5-veto**.
Universe, floor, `QTY`, frictions, halves and the population check as H-B3
§2. The pass needs the 07:00 readings for every session before any book
runs, because a session's cut depends on the sessions before it, so the
runner makes two passes over the slices: readings first, books second, with
the readings written beside the report so they can be inspected.

The **five readings of `REGISTERED_range_rank.md` §3 are inherited unchanged**
(`common/gate_study.py` is the one implementation): per trade ≥ $4.26 and per
symbol-day > 0 with a sign disagreement a refusal; both halves on both
denominators; drop-top-3 on level and delta; the cluster bootstrap on the
delta ≥ 0.95; and the abstention control at the 95th percentile. All five →
**PASSES**, a holdout candidate under its own registration; fewer → **NOTHING**.

Printed every time: sessions rated / count-cold / composite-cold / inert;
baseline entries at or after 07:00 (the only ones the veto can refuse) and the
share of those on cold sessions; the refused trades split into losses avoided
and winners lost; top-10 absent; the cascade (which should be near zero here —
a veto from a fixed clock cannot free a bar before it).

**Written before the run.** After-07:00 entries are MCL's worst blocks
(`time_of_day_pit_20260917.txt`: −$7.48 to −$16.83 a trade from 07:00 on), so
a veto that removes a third of them will move per trade up whatever the
reading says, and the abstention control is what decides whether the reading
chose *which* third. I expect reading 1's margin to fail for both strategies.
Of the four B-series gates this is the one with a mechanism behind it — the
same-day ceiling — so I expect reading 5 to be the closest call of the four,
and I would not be surprised by either outcome on it. If it passes reading 5
and fails only the margin, that is the result to carry to Part A, not a rule
to ship.

## 4. What would make this run wrong

- Any part of today's reading, or today's cut, using bars at or after 07:00,
  or sessions at or after today.
- The veto touching a bar before 07:00, or an exit.
- A session with no visible names treated as unrated rather than cold.
- The readings not written to a file beside the report.
- A cascade count far from zero: it would mean the gate was not a clock.
- The MCL baseline not counting 3,955.

## 5. What this cannot settle

- Not out of sample; `holdout.json` stays shut.
- Whether the daily composite's ceiling was real: this reading is a proxy
  for it, from the watchlist rather than the market. A NOTHING here does not
  retire the ceiling; a PASSES here does not confirm it.
- The size response — what Cameron actually changes on a cold day — is not
  a veto and is not here.
- The concurrency cap is not modelled.
