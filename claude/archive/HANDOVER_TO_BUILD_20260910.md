# Handover to the build chat — 2026-09-10

**One entry point for everything the source-analysis chat produced.** Read this,
then §2's reading order. Nothing here is code; nothing here touches `D:\Trading`.

**What was done:** Ross Cameron's channel was censused — **401 videos, every
recap and watchlist from 2026-09-10 back to ~2025-07-01, all read in full** — and
put next to MCL's 2,413 backtest trades and Ben's 1,658 real IBKR round trips on
the same axes.

**Evidence status, applying to every number below:** Cameron's figures are
self-reported, narrated on camera, on a channel that sells a course. The census
fixes *selection* bias (it is a census, not a title-picked sample) but not
*source* bias. Per `PROGRAM_INDEX.md` §4 these are **hypotheses and each needs
its own registration.** Ben's figures are what actually happened and need none.

> **Provenance, confirmed by Ben 2026-09-10 and load-bearing for everything
> below: MCL is his own version of Cameron's strategy, loosely derived.**
> Two consequences, both in §0.

---

## 0. MCL is loosely derived from this source — what that changes

Ben, 2026-09-10: *"MCL was my version of Ross Cameron's strategy. So I guess you
can say loosely derived."* This closes the open question that three documents
were carrying, and it cuts two ways.

**1. The universe match is an echo, not corroboration.** `warrior_0` §0 notes
that he trades our exact universe — $2–20, 5× RVOL, float under 20M, top
percentage gainers — and treats that as a reason to weight him heavily. That
reasoning is now weaker: **the universes agree because ours was built from his.**
We have one source, not two agreeing. The same applies to the `$500 risk / 2:1`
match flagged in `warrior_0` §5.4 — most likely inherited, though "loosely"
means it cannot be called certain either way.

**2. The distribution divergence is drift, not design — and this is the bigger
point.** MCL was an *attempt at his method*. So the fact that it ended up
with a completely different trade distribution is not two valid strategies that
happen to share a universe. It is a gap between intent and result:

| | win rate | R | breakeven | margin |
|---|---:|---:|---:|---:|
| Cameron 2025 | 71.1% | 1.20 | 45.5% | **+25.6** |
| MCL | 32.4% | 2.01 | 33.2% | **−0.8** |

**He wins five trades in seven. MCL wins one in three.** The mechanism is the
exit: MCL's 5% trailing stop produces many small stop-outs and rare runners —
2,212 of its 2,413 exits are the trail at −$1.2 each, and only the 201 that
survive to `window_close` make money. Cameron does not trail. He takes half off
at a target and moves the rest to breakeven.

> **So where the spec set and MCL disagree, the spec is the intent and MCL is
> the deviation.** That is the right way to read every gap in §5 below. It does
> not mean the spec is correct — it is still an unvalidated source — but it does
> mean the gaps are worth closing rather than defending.

---

## 1. The three-line summary

1. **MCL does not behave like the method it was derived from.** See §0.
2. **Ben's ledger is inverted on all three things Cameron says decide it** — he
   adds to losers, trades more when losing, and has no enforced maximum loss.
3. **The entry is not where the money is.** Every high-lift cause of Cameron's
   red days is a sizing or gating decision. Not one is an entry rule.

---

## 2. Reading order

**Orientation, both, before anything:**
- `PROGRAM_INDEX.md` — §1 hard rules, §4 standards of evidence, §5 traps
- `warrior_0_universe_and_risk.md` — the base spec; the other five assume it

**The spec set:**
- `warrior_1_micro_pullback.md` — the primary setup, the one MCL implements
- `warrior_2_flat_top.md` — **read §6's caveat below before building this**
- `warrior_3_gap_and_go.md` · `warrior_4_reversal.md`
- `warrior_5_selection_in_practice.md` — how he picks and what he rejects, live

**The measurements, and these are where the actionable items are:**
- **`warrior_census_20260910.md`** — 401 videos as a dataset. Start here of the three.
- `execution_gap_20260910.md` — the three-way ledger comparison
- `claude_warrior_momentum_spec.md` — superseded, kept for method lessons only

**Already-existing context, so nothing is rebuilt:**
- `momentum_confluence_strategy.md` · `mcl_rejected_mechanics.md`
- `archive/ema_source_comparison.md` — same source, read in earlier sessions
- `archive/archive_early_ideas.md` — where the derivation happened; §0 above is
  the answer, so this is background rather than an open question

**Before writing code:** `premarket_hypotheses_20260908.md` (the registration
template), `execution_cost_measured.md`, `sizing_and_capacity.md`,
`consolidated_volume_gap.md` §3.2.

---

## 3. Settled — do not re-open

| Question | Verdict | Doc |
|---|---|---|
| Fixed-cent stops vs the % trail | **Rejected**, monotone, boundary check failed | `cent_stop_decision.md` |
| A maximum hold time | **Rejected**, −$2,245, boundary check failed | `hold_cap_decision.md` |
| Consolidation filter | **Rejected** 2026-09-09 | `consolidation_filter_test.md` |
| Short side | **Not buildable** on IBKR in this universe | `short_selling_feasibility.md` |
| A per-day trade-count cap | **Withdrawn by its own author** — see §6 | `warrior_census_20260910.md` §3 |
| Was MCL derived from Cameron? | **Yes, loosely** — Ben, 2026-09-10 | §0 above |

---

## 4. THE CONVERGENCE — your 1-bar-hold lead has an independent prior

`hold_cap_decision.md` §4 found, post-hoc, that **1-bar holds are 107 trades at
−$36.68 each, and 22.1% of trades destroy 96% of MCL's gross result.** You
correctly flagged it as a lead needing pre-registration, and noted it can only be
acted on as an *entry* filter.

**The census supplies the prior that lead was missing.**

A one-bar hold means price gave back 5% of its peak within the minute — you
bought a spike that immediately reversed. Cameron has a name for that and it is
one of his top red-day causes: **`chased_extended`, on 33.3% of his red days
against 17.6% of green, lift 1.9×.** His two stated countermeasures are both
entry-side and both computable:

- **The hold-50% rule** (`warrior_5_selection_in_practice.md` §1): reject a
  candidate not still holding ≥50% of its initial pre-market impulse at decision
  time. *"when we have stocks that pop up and then go all the way back down,
  pretty much immediately I'm like, nope, that's not going to work."*
- **The front-side gate** (`warrior_0` §4): no entries after the first MACD
  crossover, a moving-average crossover, **or a close below the 20 EMA.** MCL has
  the first only.

> **This turns a post-hoc bucket into a registrable hypothesis with a stated
> mechanism.** That is the difference between a lead and something you are
> allowed to test. It is the highest-value item in this handover.
>
> **One honesty note given §0:** the source is not fully independent of MCL,
> since MCL was derived from it. But the *mechanism* here — chasing an extended
> move — is not something MCL inherited, and the hold-50% rule is nowhere in our
> code. On this specific point the source is genuinely adding information rather
> than reflecting ours back.

**And it lands where you are already working.** `screen_at.py` is a
point-in-time screen; hold-50% is a point-in-time screen rule. It needs no new
field, no new feed, and it can go in beside the three imported `tv_screener`
clauses — though note it is a *ratio over the session so far*, not a threshold on
a single column, so it needs the intraday frame `screen_at` already truncates.

---

## 5. New, ranked by expected value

**1. A regime gate. The largest effect measured anywhere in this project.**

From 234 recaps he labels himself:

| his label | n | green rate | **mean day** | median trades | no-trade days |
|---|---:|---:|---:|---:|---:|
| hot | 53 | 94.3% | **$46,481** | 4 | 0 |
| mixed | 38 | 97.2% | $24,172 | 2 | 2 |
| cold | 143 | 76.9% | **$2,835** | 2 | 22 |

**16× on the mean day, and cold is 61% of the sample.** His win rate barely
moves; the size of the win collapses. Countable signals, all from daily bars:
count of >100% gainers, magnitude of the leading gainer, **round-trip rate**
(the same computation as hold-50%, market-wide instead of per-name), float and
price profile of the leaders. He also says the transition is asymmetric — *"the
shift from hot to cold is much more subtle than the shift from cold back to
hot"* — which argues for slow entry into cold and a fast exit out.

**A strategy validated on the hot 23% is not validated.**

**2. Dip buying — half his book, and we do not implement it.**
129 mentions against the micro pullback's 172, at the **same 0.7 red-day lift**.
The spec set barely covers it. Given §0 this is the clearest case of MCL having
inherited one half of the method and not the other, and
`warrior_4_reversal.md` §6 names the two untranscribed dip videos.

**3. A daily loss stop — a live-path rule, not a backtest parameter.**
On Ben's tape a **−$2,000 daily stop recovers $55,083, 48% of the total loss.**
Cameron reached the same conclusion from his own August: *"if I had stopped
trading on both of those days when I was down only 15 or 20 grand, I would have
an extra $100,000."* Note `PROGRAM_INDEX.md` §4 parity — whatever the backtest
enforces the live path must, and vice versa.

**4. Position construction on winners vs losers — one ratio, computable today.**

| | winner shares ÷ loser shares |
|---|---:|
| Cameron 2025 | **1.36** (19,000 vs 14,000) |
| Ben, real | **0.80** (1,963 vs 2,467) |

He adds to winners and never gets the chance on losers. **Ben's losers carry 26%
more shares than his winners, on 12.1 fills against 10.3.** That single asymmetry
is why his dollar R (0.56) is worse than his per-share R (0.58) while Cameron's
dollar R (1.67) is far better than his per-share R (1.20). Compute it on MCL and
on the live path.

**5. Re-rank the screen at decision time, not once.**
He is explicit that the 04:00 leader is usually spent by 07:00 and attention
migrates to whichever name is squeezing *now* — he calls it musical chairs and
applies it live. **MCL takes top-2 by gap, computed once.** This is one change to
the screen's ordering and `screen_at`'s cadence work (§6 item 2 of
`screen_at_build.md`) is exactly where it belongs.

**6. The 07:00 window.** 50 of 87 stated first trades are in the 07:00 hour, 7
before it, **none at 04:00 or 05:00 in the entire census.** MCL arms at 04:00 and
its 04:00–06:00 block is **−$2,166 against a −$1,270 total.** In-sample, so it
needs registration — but given §0, a window MCL does not share with the method it
came from is a drift worth measuring.

---

## 6. Corrections to earlier documents — apply these

- **The per-day trade-count cap is withdrawn.** `execution_gap_20260910.md` §2
  read Cameron's "40% fewer trades, 3× the money" as supporting a budget. The
  census disproves it: **his green rate is flat across trade counts and his P/L
  rises 14× with them.** His count tracks opportunity; Ben's tracks tilt (after a
  losing first three trades he takes a median of 9 more, against 6 after a
  winning start). A count cap would cut the best days hardest. **Use the daily
  loss stop instead.**
- **`warrior_0` §0 overstates the source's weight.** Its second reason for
  weighting Cameron heavily — that he trades our exact universe — is circular
  now that the derivation is confirmed. The first and third reasons stand.
- **`warrior_2_flat_top.md` needs re-reading against a 1.9× red-day lift**, and
  halt resumptions are 2.4×. The spec treats the flat top as a benign variant of
  the micro pullback; his own record says otherwise.
- **Back-side trading and slippage are NOT red-day drivers** — lift 1.1× and
  1.0× across 317 recaps. Both looked like top failure modes in the earlier
  35-video sample. That sample was title-selected and wrong.
- **MCL implemented the right setup.** The micro pullback is his most-used (172)
  and safest (0.7 lift). After a lot of criticism in these documents that deserves
  saying plainly — and given §0, it means the derivation picked correctly even
  where the exit did not follow.

---

## 7. Open questions this chat could not close

1. **The census has no calendar dates.** The playlist endpoint returns none, so
   it is position-ordered and cannot be joined to Ben's tape by date. **401 free
   metadata calls** would fix it and enable a day-level regime join.
2. **`trades_n` is stated on 175 of 317 recaps, `market` on 234.** Real
   denominators, not complete ones.
3. **Dilution and domicile.** He checks filings on every accepted name and
   tracks country on all of them. We can compute neither, and he refuses to
   filter on country anyway.
4. **His own counter-example, worth keeping in view.** On a name passing every
   stated pillar: *"very low float, has lots of room to the 200, didn't work
   very well. It's hard to understand why some of them end up making such big
   moves and others struggle."* **A low hit rate on these filters is expected,
   not an implementation error.**
5. **How much of the derivation was second-hand?** §0 settles *that* MCL came
   from Cameron, not *what* was carried across. `archive/archive_early_ideas.md`
   records the algo as built from his style "at second hand" — so some
   parameters may be reconstructions rather than his. Matters only where a spec
   number and a config number agree and that agreement is being used as evidence.

---

## 8. Artefacts

| | |
|---|---|
| `docs/research/warrior_census.csv` | 401 rows, schema in `warrior_census_20260910.md` §8 |
| `docs/research/warrior_video_index.csv` | 800-video channel index, position-ordered |
| `docs/research/README.md` | schema, limits, pointers back to these docs |
| `CENSUS_SPEC.md` | worker spec — closed vocabularies, reproducible |

The three files under `docs/research/` are **on disk and tracked but not yet
committed** — `var/` is gitignored so research data was deliberately placed in a
tracked path instead. `git add docs/research` picks them up; no existing ignore
rule catches `warrior_*.csv`.
