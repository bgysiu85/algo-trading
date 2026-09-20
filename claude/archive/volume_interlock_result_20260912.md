# The TNON interlock is routine, not anecdotal

`python -m common.volume_interlock` · raw: `var/reports/volume_interlock.txt`
372 symbol-days from `var/state/traded_pairs.json`, 424,685 bars, bundle
`20260912aa`. 35 symbol-days not tested (no cache, or too short for warm-up).

## The decisive numbers

Among **27,389 judgeable bars** — bars where MACD, MFI and RSI all agreed and a
trailing average existed:

| | count | of judgeable |
|---|---:|---:|
| `c_floor` alone blocked it (the TNON 07:35 shape) | **2,102** | 7.7% |
| `c_vol` alone blocked it (the follow-through) | **15,956** | 58.3% |
| **ignition refused AND run locked out behind it** | **1,162** | — |

- **3.12 locked runs per symbol-day**
- **75.8% of symbol-days have at least one**

Set that against the strategy's own output on the same population: **1,983 entry
signals.** The interlock refuses roughly **59 lost ignitions for every 100
entries MCL actually takes.**

TNON on 2026-09-11 was not bad luck. It is what happens three times a session,
on three sessions in four.

## The arithmetic behind it

    c_vol     volume   >= 3 x prev_vol      wants prev_vol SMALL
    c_floor   prev_vol >= 0.5 x trail_avg   wants prev_vol LARGE

Both hold only when `volume >= 1.5 x trail_avg`. On **56.6%** of judgeable bars
the window is arithmetically empty — no `prev_vol` could have satisfied both.
The median judgeable bar sits at **1.14x** its trailing average against a gate
of 1.5x; only 43.4% clear it.

`c_vol` is the dominant constraint at 58.3%, which matches the session-wide TNON
finding (sole blocker on 43 of 47 single-condition bars). But `c_floor` is the
one that refuses the **ignition** — and once the ignition is refused, `c_vol`
locks out everything behind it.

## A correction I made mid-run

The first version reported 14,531 hand-offs, 39 per symbol-day, 96% of sessions.
That number was inflated two ways: the pair is close to tautological (after a 3x
spike, the next bar can hardly avoid clearing the floor and failing the
multiple), and it counted bars the indicators had already rejected, which could
never have entered whatever the volume did. It is kept in the report as section
2b, labelled as the weakest number, because deleting the first figure reported
would quietly change the answer.

## DO NOT CONFLATE THIS WITH `floor_delta`

`floor_delta_result_20260911.md` found a floor delta of **0.16, NOT MATERIAL**.
That is the **point-in-time entry floor** — no entry before 04:30 / `first_seen`
— and has nothing to do with `c_floor`, the intraday volume floor measured here.
Two different mechanics with the same word in their name. **`c_floor` has never
been tested through `pit_delta`.**

## What this does NOT say

- **Not that those 1,162 ignitions were profitable.** Frequency only. MCL's win
  rate is 21.7% simulated and 47.1% live; most entries lose, and a rule that
  declines bursts out of nowhere may be declining exactly what it should.
- **Not an unbiased population.** `traded_pairs.json` is names MCL actually
  traded, so it is tilted toward names that qualified. `screen_pairs.json` would
  be a larger and differently-biased sample.
- **Not a licence to remove `c_floor`.** Every mechanic change measured in this
  project has lost money.

## The registered next step

The frequency bar is now cleared, so a variant belongs in `pit_delta` — with its
predicted failure written down first, per the project's standing rule.

**Pre-registered prediction (2026-09-12, before running):** removing or relaxing
`c_floor` will **lose money or be immaterial**. The prior on mechanic changes
here is uniformly poor, and 1,162 extra entries at MCL's win rate against
$4.26/round-trip friction is a large number of new losers. The interlock being
*frequent* is not evidence that it is *wrong*.

Candidate variants, in order of how cleanly they isolate the mechanism:

1. `c_floor` removed entirely — the cleanest single-variable test.
2. `FLOOR_FRACTION` relaxed (0.5 → 0.25), which opens the window to
   `volume >= 0.75 x trail_avg`.
3. A re-arm window: after a `floor_sole` rejection, allow the next bar to enter
   on `c_floor` alone. This targets the LOCKED shape specifically rather than
   loosening the rule everywhere, and is the only one of the three that would
   have bought TNON at 07:36.

(3) is the one worth most, because it is the only variant shaped like the defect
rather than like a parameter.

**This does not depend on the `prior_close` repair** and can run before it — the
interlock is a property of bars within a symbol-day, not of which names the
screen picked. Its P/L measurement through `pit_delta` does depend on the
universe, and that ordering has to be stated when the delta is reported.
