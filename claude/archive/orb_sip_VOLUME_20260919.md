# ORB — volume confirmation on the break, and the close of the line (amendment I, 2026-09-19)

Registration: `docs/research/REGISTERED_orb_sip.md` **amendment I**, committed with its rule, its ceiling disclosure, four controls and two separately-scored predictions before anything ran. Raw: `var\reports\orb_sip_volume.txt`. Cache: `var\cache\orb_sip\break_volume.csv.gz`. Bundle: `orb-20260919d.bundle`. **Nothing bought.**

The last named candidate from the source review. **It fails, and ORB closes with none remaining.**

## The rule, and the look-ahead that was the point

Breitstein: *"weak volume breakouts are far more likely to fail."* Operationalised parameter-free: **CONFIRMED** when the breakout bar's volume exceeds the median of the five minutes before it, **WEAK** otherwise. No multiplier — a sign comparison, one bit per trade.

**I.2 disclosed a deliberate look-ahead.** A minute bar's volume is complete only at the *end* of the minute the entry happens inside, so the breakout bar's volume is not knowable when the rule would fire. That made the primary reading a **ceiling**: if the filter cannot help while being handed the future, the honest version cannot succeed, and one run settles the family. A pass would have earned the tradeable form a registration and nothing more — I.1 was never adoptable on its own terms.

## The result

| bucket | trades | mean net | gross | total | drop-top-5 | bootstrap |
|---|---:|---:|---:|---:|---:|---:|
| **CONFIRMED** (kept) | 4,324 | **(0.002)R** | +0.347R | (8.2)R | (270.3)R | 0.470 |
| **WEAK** (discarded) | 2,874 | **+0.025R** | +0.375R | +71.2R | (165.9)R | 0.598 |
| NO_DATA | 41 | (1.418)R | (0.962)R | (58.2)R | (74.3)R | 0.000 |

**The weak-volume breakouts did better** — on a reading given information the trader does not have. Criteria on the retained bucket: **1 of 6**, and the one is the trade count.

## The controls

**(a) Shuffled-label null**, 2,000 draws, seed 20260916, the 60/40 proportion preserved:

| | observed | null p95 | p | |
|---|---:|---:|---:|---|
| mean R | (0.002) | +0.081 | **0.609** | does not beat |
| drop-top-5 | (270.3) | +88.5 | **0.625** | does not beat |

The real labelling is *worse* than the median random relabelling of the same shape.

**(b) Composition — and this one found something.** The CONFIRMED share climbs steadily with entry time:

| entry minute | trades | confirmed share |
|---|---:|---:|
| ≤ 09:35 | 2,876 | 51.1% |
| 09:36–09:40 | 2,024 | 57.6% |
| 09:41–10:00 | 1,234 | 71.9% |
| 10:01–11:00 | 593 | 74.5% |
| 11:01–13:00 | 282 | 78.4% |
| 13:01+ | 189 | 73.5% |

So the label is **partly a time-of-day proxy** — later breaks look "confirmed" because the baseline minutes around them are quiet, not because the break was strong. Across RVOL rank bands it is flat (59.6% / 59.7% / 61.5% / 59.4%), so it is **not** an RVOL proxy.

**(c) Two denominators** — they agree, and agree on the wrong sign: (0.027)R per trade and (0.027)R per symbol-day, both favouring the discarded bucket.

**(d) drop-top-N on the delta** — (79.4)R across 1,978 symbols, falling to (350.1)R after its top 5.

## The tradeable reading, reported and not decided on

The same rule one minute earlier, on the last *completed* bar:

| bucket | trades | mean net | total | drop-top-5 | bootstrap |
|---|---:|---:|---:|---:|---:|
| CONFIRMED | 2,823 | +0.034R | +95.7R | (143.2)R | 0.649 |
| WEAK | 3,855 | +0.019R | +75.0R | (189.6)R | 0.603 |

Here CONFIRMED is the better bucket. **The decision does not rest on this line** — I.2 fixed that in advance, precisely so that two readings could not be produced and the flattering one chosen. And it does not rescue anything: on its own numbers it fails criteria 1, 2 and 3.

**What it does show is worth recording.** Two versions of the same rule, one minute apart, disagree in *sign*: +0.015R lift on the tradeable reading against (0.027)R on the ceiling. A real effect does not flip when you shift its window by sixty seconds. That is what noise looks like.

## Predictions

- **Primary — NOT ADOPTABLE: correct.**
- **Secondary — "CONFIRMED's mean beats WEAK while drop-top-5 stays negative": WRONG.** For the second time running, and in exactly the same way it was wrong in amendment H.

**That repetition is the most useful thing in this document.** Twice I predicted a *real but insufficient* effect — a filter that lifts the mean without fixing concentration. Twice there was no effect at all to be insufficient. The prior I was carrying was that a widely-taught discretionary rule must be measuring *something*. On this book, two such rules measured nothing, and one of them measured slightly less than nothing.

## ORB is closed

| lever | verdict |
|---|---|
| Stop width (F) | Closed. Winners reach 0.63R against them, losers 5.51R; rescuable 9.1% against a 25% gate. |
| Market context (H) | Retired, family-wide. p = 0.478 against a shuffled-sign null. |
| Volume confirmation (I) | Retired, family-wide. Fails its own ceiling; p = 0.609. |
| **Named candidates remaining** | **None.** |

I.6 retires the volume family — no multiplier sweep, no alternative baseline window, no dollar-volume restatement, no confirmation-on-the-retest. **Any future ORB work needs a new mechanism and new data, not another cut of this book.**

Final position: **1 of 7 criteria**, net $480 gross $254,100 over 7,239 trades and 446 sessions, `holdout.json` unspent. Three attempts on three universes, closed by measurement each time.

## Next steps — on the task board

| card | what | assignee | status |
|---|---|---|---|
| **AT-86** | Merge `orb-20260919d.bundle` (cumulative: a–d) and run the ORB tests | Ben | Next up |
| **AT-56** | Fold the ORB 'For PROGRAM_INDEX' sections (RESOLVED, EXCURSION, CARRIER, CONTEXT, VOLUME) into `PROGRAM_INDEX.md` | Build & test chat | Next up |
| AT-87 | Amendments E–G (one-second resolution, stop-width rescue, symbols-or-days) | ORB chat | Done |
| AT-77 | Amendment H, market-context gate | ORB chat | Done |
| AT-62 | Amendment I, volume confirmation — ORB closed | ORB chat | Done |

No open ORB study remains. The ORB chat has no card assigned to it.

## For PROGRAM_INDEX

- **ORB is closed on all named avenues.** Survivor universe (leak), stocks in play (friction and concentration), stop width, market context, volume confirmation.
- New standing fact: **on ORB SIP, weak-volume breakouts outperformed confirmed ones** — (0.002)R against +0.025R, on a reading handed the future. The most-cited breakout heuristic in the source corpus does not survive its own ceiling here.
- New standing fact: **"volume above the recent median" is substantially a time-of-day label.** Its confirmed share runs 51% at the open to 78% midday. Any future volume filter must be normalised for time of day before it means anything.
- **Method note, the one to carry forward: register the CEILING when the honest version needs data you do not have.** A disclosed look-ahead reading that fails kills the tradeable version for free and in one pass, instead of spending a second registration to find out.
- **Meta-note worth keeping: two consecutive source-derived filters produced no measurable effect at all**, not a weak one. The repeated secondary prediction — real-but-insufficient — was wrong both times. Weight the next qualitative source claim accordingly: the null is not "small effect", it is "no effect".
