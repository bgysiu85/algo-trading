# REGISTERED — HTF-Ben v2: v1's entries, v0's stop/trail only (no signal exits)

**Committed before any v2 code exists and before any v2 return has been seen** — except for one
number, disclosed in full in §0: the reported (never scored) v1−X ablation. `PROGRAM_INDEX` §1:
a hypothesis is registered before it is run; §0 is where this one admits it starts from a result,
not from Ben's own reading of the chart, and says what that costs.

Board: **W15-0021** (this registration + build), W15-0011 (v1's training run and the v1−X
ablation this comes from, Result doc https://ben-siu.monday.com/docs/5031569518). Parent:
`docs/research/REGISTERED_htf_ben_v1.md` for entries (§2.1, unchanged) and
`docs/research/REGISTERED_htf_ben_v0.md` for exits and everything not restated here (bars,
session, series, costs, account view, report contents, look-ahead guard style).

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a
v2 result is a new hypothesis and spends from the budget in §9 — and §9 says there is none left
after this one without a reason that doesn't begin with a result.

---

## 0. Where this comes from, and what has already been seen

Honest provenance, because it decides what a v2 result can mean — more so than usual:

1. **v0 was run and failed** its §4 criteria on the training side (0/9 relevant checks that
   mattered; closed). **v1 was run and closed** on the training side (W15-0011): 5 of 9 criteria
   passed, but criterion 5 failed — v1's own $1,150.22 net (293 trades, mid friction, scenario B)
   lost to its own C2 Donchian control ($5,163.50). v1 never spent its holdout.
2. **Unlike v1, this hypothesis does not come from Ben describing how he reads a chart.** It
   comes directly from a number: v1's registered §2.4 reported-only ablation "v1−X" (v1's entries,
   but exits = v0's unmodified S1/S2 stop/trail, dropping v1's own X1/X2 signal exits) netted
   **$3,956.12 on 286 trades**, training side, mid friction, scenario B — about **3.5x** full v1's
   $1,150.22 on 293 trades. That number was computed inside v1's own registered engine as a
   *reported, never-ranked* variant (REGISTERED_htf_ben_v1.md §2.4, §9), so it is not itself a
   holdout spend or a new rule fitted after the fact — but it is a P&L number this hypothesis is
   being written *because of*, which is exactly the situation §7's multiplicity discipline exists
   to police. The fresh, independently-matched controls and an untouched holdout in this file are
   the safeguard, not the training-side net by itself.
3. **Caution already on the board (W15-0021 opening note, 2026-09-27):** v1−X's $3,956.12 is
   still *less* than $5,163.50 — but that $5,163.50 is v1's **own** C2, matched to v1's 293-trade
   run, not to v1−X's 286-trade one. Re-quoting it for v2 would be comparing two different trade
   populations under one baseline's name. §2's controls are therefore re-defined and re-run fresh
   against v2's own actual trades (§3, §5.2), never imported from W15-0011's Result doc.
4. **Per REGISTERED_htf_ben_v1.md §7 and §9**, a rule change discovered from a result is a new,
   separately pre-registered hypothesis, not an amendment to v1. This file is that hypothesis.
5. **Multiplicity budget carried forward.** v0 §9 allowed two further registered hypotheses on
   this line; v1 was "hypothesis 1 of 2" (REGISTERED_htf_ben_v1.md §0.1, §9). v1 §9: *"After v1,
   one further registered hypothesis is left; a third needs a reason that doesn't begin with a
   result."* **v2 is that one remaining hypothesis.** See §9.
6. **The seen window (2025-09-23 → 2026-09-24) is not fresh either.** It was looked at by Ben
   (W15-0008 annotations) and by NinjaTrader paper trades before v1 was designed, and v1's
   entries — carried unchanged into v2 — were shaped partly by Ben's answers about those trades
   (W15-0009). It stays "reported only, never scored" here too (§6), for the same reason it was
   in v1: it has already informed the rules being tested.

---

## 1. The hypothesis, in one sentence

**v1's entry logic exactly as registered (the EMA9/EMA21 cross and MACD-curl-off-a-trend-line
routes, the no-range and last-touched-line filters, the daily filter) paired with v0's original,
unmodified initial-swing stop and half-profit trail — with v1's own signal exits (X1 opposite
cross, X2 EMA9 turning) removed entirely and no take-profit added — makes money after measured
costs on 2010–2021 CL on the 4-hour multi-day chart, and beats a plain MACD cross run with v2's
own exits, a Donchian channel, and random entries, each measured fresh and matched to v2's own
trade count and mix (not reused from v1's or v0's runs).**

---

## 2. The rules

### 2.1 Entries — inherited unchanged from REGISTERED_htf_ben_v1.md §2.1

Every entry rule below is **frozen exactly as v1 registered it**. Nothing about the entry side is
re-opened, re-tuned, or re-derived for v2 — that would spend a hypothesis on something v1 already
tested (v1 criterion 8: 24/24 neighbour cells net-positive; entries were not v1's problem).

| # | Rule | As registered in v1 |
|---|---|---|
| E1a | Cross route: MACD crosses above signal at t; confirmation c ∈ {t+1, t+2, t+3}, first bar where E2 holds and hist[c] > 0 | v1 §2.1 |
| E1b | Curl route: hist[t] < 0, rising 2 bars running, T holds at t, E2 holds at t; c = t | v1 §2.1 |
| T | Trend-line rejection (curl route only): touch of an active rising line 2–3 bars before t, closes above it since | v1 §2.1 |
| E2 | Confirmation: EMA9[c] > EMA9[c−1] and spread[c] > spread[c−1] | v1 §2.1 |
| F1 | No-range skip: rolling 9-bar max\|hist\|/ATR ≤ q_h and max\|spread\|/ATR ≤ q_e | v1 §2.1, values below |
| F2 | Last-touched-line direction filter (30-bar lookback) | v1 §2.1 |
| E3 | Daily EMA9/EMA21 filter | v0 §2.2, unchanged |
| Fill | Market at the open of bar c + 1 | v0 E4 |

**F1 thresholds are inherited, not re-derived.** q_h and q_e are computed purely from the
training-side indicator series (rolling \|hist\|/ATR and \|spread\|/ATR ratios) and do not depend
on which exit rule is attached — v2's entries read exactly the same bars v1's did, so recomputing
would reproduce the same numbers. Per **REGISTERED_htf_ben_v1.md Amendment C**:

- **q_h = 0.190280** (25th percentile, rolling max\|hist\|/ATR(14), 9-bar window, training side)
- **q_e = 0.501239** (25th percentile, rolling max\|spread\|/ATR(14), 9-bar window, training side)

These are carried into v2 by reference, not recomputed in G2 (§5.2). **What G2 must recompute for
v2 is the trade/entry count** — not because the entry rule changed, but because E5 (one position
at a time) means how long a position stays open changes which later triggers are "ignored while
in position." v0's exits hold trades open differently than v1's did, so the realized entry count
will differ from both v1's 324 (B, training) and the v1−X ablation's implied count even before
E5 filtering. This is measured, not assumed (§5.2).

### 2.2 Exits — inherited unchanged from REGISTERED_htf_ben_v0.md §2.3, in full

**v1's X1 (opposite cross) and X2 (EMA9 turns) are removed. No take-profit is added.**

| # | Rule | As registered in v0 |
|---|---|---|
| S1 | Initial stop: most recent confirmed swing low/high (L = R = 2), 1 tick beyond; void condition unchanged | v0 §2.3 |
| S2 | Half-profit trail: once highest-favourable-excursion reaches fill ± $0.20/bbl, stop ratchets to protect ≥ 50% of open profit; never loosens | v0 §2.3 |
| S3 | Trail checked each completed bar; conservative order (stop tested against the bar's low/high before that bar can move it) | v0 §2.3 |
| S4 | Stops tested on 1-hour bars (as v1 carried forward); fills at stop price or the bar's open on a gap-through, plus slippage | v0 §2.3, v1 §2.2 |
| S5 | No targets — the stop/trail is the only exit | v0 §2.3 |

If a stop and what would have been a v1 signal exit coincide on the same bar, it is moot: v2 has
no signal exit to compete with the stop. Slippage: v0 §2.5, every leg.

### 2.3 Scenario — B only

**Scenario B (4-hour, multi-day) is the sole scenario in scope**, because it is the only scenario
the originating $3,956.12 / 286-trade number was measured on (v1's §2.4 ablation table reports
B only). **A-2H is not run for v2.** Running it would mean inventing an A-2H ablation number that
was never reported for v1−X, and scope creep is exactly what §7 exists to block. If v2 clears its
own bar on B, extending to A-2H is a fair candidate for a *separate* registration — not this one,
and not automatically (§9 has no budget left on this line regardless — see below).

### 2.4 Variants

**None.** v2 is a single, fixed rule set (v1 entries + v0 exits). It does not itself define
further ablations — the entry-side ablations (v1−curl, v1−F1, v1−F2) are already characterized in
v1 §2.4 and are not repeated here, and there is no exit-side rule left in v2 to ablate (S1/S2 are
its whole exit).

---

## 3. What every run must emit

Inherited from v0 §3 / v1 §3, for scenario B only, adjusted for v2's exits:

1. **In dollars and actual trades, per 1 MCL and per 1 CL:** trades, wins/losses, gross, costs,
   net, average win, average loss, largest loss, worst consecutive-loss run — at all three
   friction levels, mid as the headline.
2. Every calendar year of the training side.
3. Both halves, split at the median trade date.
4. **Exit reasons:** initial stop / trailed stop / data end (no signal exits, no 17:00 flat — B
   holds overnight); share of trades where the trail ever started; median hold in hours.
5. **Counts:** triggers by route, lapsed, blocked by E3/F1/F2, curl setups failing T, entries,
   voided (S1), roll legs.
6. **Controls — each run fresh against v2's own trades, never re-quoted from v0's or v1's runs:**
   - **C1 (v2):** MACD cross alone (no E2, F1, F2, no curl route) — same stripped entry as v0's
     and v1's C1 — paired with **v2's own exits** (S1/S2 only). This is a different pairing from
     v1's C1 (which used v1's X1/X2), so its trade count and net will differ from $981.56/475
     trades; that is expected and correct.
   - **C2 (v2):** Donchian 20/10 breakout / opposite-10-bar-channel exit, exactly as v0 defined
     it — self-contained and unaffected by v2's entry/exit choice. **Re-run inside v2's own
     backtest pass** (same bars, sizing, costs, period) rather than importing v1's $5,163.50/594
     trades. The dollar figure should come out identical to v1's C2 run since the strategy and
     data are the same either way; the point of re-running it here is that v2's registration and
     gates (G1–G5) stand on their own, not on trust in a different file's run.
   - **C3 (v2):** 1,000 seeded random-entry draws (crc32 of draw number, as v0/v1), **matched to
     v2's own realized trade count and long/short mix** — not v1's 293 — same v0 S1/S2 exits.
     Report p5/p50/p95 of net.
7. **Neighbour grid (§4 criterion 8; see below):** exit-side only, 6 cells, net at mid friction
   and share net-positive.
8. **Account view (§2.5), as v0/v1.**
9. **20 sample trades** (every 1/20th of the list): entry/exit time, side, fill, stop, exit,
   exit reason, net $ per MCL.
10. **Seen window (2025-09-23 → end of data), reported only, clearly labelled "seen — not
    evidence."** No criterion uses it (§0.6).

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — v2, scenario B, 1 MCL, mid friction, training side

Passes only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. Bootstrap by calendar year (2,000 seeded resamples): net > 0 in ≥ 95%.
5. **Beats v2's own, freshly-run C1 and C2 on net** — failing this closes v2 regardless of the
   rest, exactly as it closed v1. No number from W15-0011 may be substituted here.
6. Beats the p95 of v2's own C3 (matched to v2's realized trade count/mix) on net.
7. Still net > $0 at high friction.
8. **At least 4 of the 6 neighbour cells (§5.3) net > $0** (same ≈ two-thirds bar as v0's 12/18
   and v1's 16/24, scaled to a smaller, exit-only grid — see §5.3 for why the grid shrank).
9. **At least 150 trades.** Fewer → NOT READ, not failed.

---

## 5. Before the backtest — no P&L in this section

### 5.1 Gates

| # | Gate |
|---|---|
| G1 | Data: v0's G1 stands (passed under Amendment B). No new data. |
| G2 | Pre-flight (§5.2): fresh entry/trade counts for v2 only; q_h, q_e inherited, not recomputed. |
| G3 | **v2 holdout cut and ledger** (§6), mutation-tested, new file name (§6). |
| G4 | Look-ahead guards: entry-side guards are v1's, already tested and unchanged (nothing about
      them changes when the exit module is swapped). Exit-side guards are v0's S1/S2 guards,
      already tested. What is new and must be mutation-tested here is the **E5 recombination**
      itself — a position opened under v1's entry timing but held under v0's (longer) exit
      timing must still correctly block a new trigger while flat-vs-in-position, tested with a
      case that only breaks if the wrong module's position state is consulted. |
| G5 | Costs: v0 Amendment A stands. |

### 5.2 G2 pre-flight (training side only, scenario B)

Run v2's actual entry/exit engine with **no P&L** (the runner refuses it in this mode, as
v0/v1's did): report, per year, triggers by route, confirmations, blocks by E3/F1/F2, curl
setups failing T, **entries** (the number that matters here, since it is exit-dependent via E5),
and initial stop distance in $ per MCL (median, p90, max).

**Stop rule:** fewer than **150 v2 entries on B** → stop as underpowered, reported as the
finding, and back to Ben before any P&L — exactly v0/v1's rule.

This gate is expected to land close to, but not necessarily equal to, the 286 trades the v1−X
ablation reported inside v1's engine; a large divergence from 286 is itself worth flagging to
Ben rather than silently accepted, since it would mean v2's standalone engine and v1's ablation
code disagree about something.

### 5.3 Neighbour grid — exit-side, not entry-side

v1's own neighbour grid (confirmation window × F1 window × F1 percentile × X2 bar count, 24
cells) already established that v1's **entries** are not fragile (24/24 net-positive) — that
question is closed and is not re-asked here, because v2 changes nothing about entries. What v2
changes is the exit, and *that* side has never been robustness-checked in this combination. So
v2's own grid re-tests the **exit** parameters instead, using v0's original exit-grid dimensions:

- Swing size **L = R ∈ {2, 3}** (S1)
- Trail trigger **∈ {$0.10, $0.20, $0.40}** (S2)

**6 cells** (2 × 3), net at mid friction, training side, scenario B. Criterion 8's bar (4 of 6 ≈
67%) matches the ≈ two-thirds bar used for v0's 18-cell and v1's 24-cell grids.

---

## 6. The holdout

- **Training:** 2010-06-06 → 2021-12-31 (unchanged from v0/v1).
- **v2 holdout: 2022-01-03 → 2025-09-22**, same window convention as v1's, but its **own cut file
  and ledger, `holdout_htf_ben_v2.json`**, refused by name from v0's, v1's, TSMOM's, TL-v0's,
  H60's and every other line's ledger, and refusing `--limit` and every narrowing flag,
  mutation-tested. Nothing about the *dates* is new — no hypothesis on this line has ever spent
  2022+ data — but the discipline of a fresh, separately-named ledger for a fresh hypothesis is
  the same one v1 used against v0's file, and is kept here for the same reason.
- **Spent once, by v2 on B, 1 MCL, mid friction, the same nine criteria (§4).**
- **Seen window: 2025-09-23 onward.** Reported only (§3.10), never scored — see §0.6 for why it
  cannot be treated as fresh for this hypothesis either.

---

## 7. Registered as NOT to be done

- Adding back X1, X2, or any other signal exit "to see if it helps" v2 after a result — that is
  a new hypothesis, not a v2 patch.
- Tuning swing L/R, the trail trigger, or any F1/F2/E2 threshold to fit a v2 result.
- Quoting v1's or v0's C1/C2/C3 dollar figures for v2 — every control is re-run fresh against
  v2's own trades (§3.6).
- Quoting gross, or 1 CL/10 CL figures, as the headline.
- Spending the v2 holdout more than once, or with `--limit` or any narrowing flag.
- Treating a pass here as proof the entries are "good" — v1's entries were already shown robust
  to nearby settings (24/24); a v2 pass would show the *exit* choice matters, not that the
  entries were previously mis-tested.

---

## 8. Ways this could go wrong

- **This hypothesis started from a P&L number, not from Ben's own reading of a chart** (§0.2) —
  the single biggest difference from v1's provenance, and the reason the fresh, independently
  matched controls and an untouched holdout matter more here than usual. A training-side pass
  alone would not be persuasive; passing against fresh C1/C2/C3 and a real bootstrap is the bar.
- **The Donchian control is a strong baseline.** It beat v1 by more than 4x on v1's own numbers.
  v0's plain stop/trail may still not be enough to close that gap even though it helped v1's exit
  problem — "beats v1" is not a criterion anywhere in §4; only "beats v2's own C1/C2/C3" is.
- **Trade count may not land near 286.** §5.2 flags this explicitly: if v2's own engine produces
  a materially different entry count than the v1−X ablation implied, that is a signal to check
  the E5/position-state recombination (G4) before trusting anything downstream.
- **Lines are still fragile** (inherited risk from v1 §8): F2 and T test *a* trend-line rule, not
  Ben's own eye-drawn lines. This risk carries into v2 unchanged since entries are unchanged.
- **Multiplicity is not a nice-to-have here.** This is explicitly the last hypothesis this line's
  budget allows (§9) — there is no "try one more variant" after this without a reason that
  doesn't begin with a result.

---

## 9. Multiplicity budget

v0 §9 allowed **two** further registered hypotheses on this line. v1 was hypothesis 1 of 2
(REGISTERED_htf_ben_v1.md §0.1). **v2 is hypothesis 2 of 2 — the last one this line's budget
allows.** After v2 reports (pass or fail), this line closes under the original budget; continuing
it a third time needs a reason that doesn't begin with a result (v0 §9, v1 §9), and that
reason — if Ben has one — should be written down before any further code is read, exactly as this
file was.

---

## 10. A prediction, written down now

**v2 nets more than v1 did on the training side** — removing X1/X2 should let winners run instead
of cutting them at the first EMA9 wobble or opposite cross, and the ablation number already hints
at the size of that effect. I doubt it clears its **own**, freshly-run C2, though: Donchian's edge
over v1 wasn't really about v1's bad exits, it was that a raw 20/10 breakout on CL over
2010–2021 captured most of the available trend-following return in this window on its own,
without needing any of Ben's entry filters. If v2 beats its own C1 (a fair result — the entry
filters should do *something*) but still loses to its own C2, the reading is the same shape as
v1's: the entry logic is fine, but a dumb breakout captures the underlying crude trend at least
as well, and the "edge," such as it is, may be in position sizing and patience rather than in
either the entries or this particular exit. I'd be glad to be wrong.

---

## Next steps (board, W15-0021)

- **Subitem 2** — Ben reviews and confirms this registered v2 spec before any code is written.
- **Subitem 3** — Build v2 engine (reuse v1's entry modules unchanged + v0's exit module
  unchanged; `v2_holdout.py` / `v2_controls.py` / `v2_report.py` analogous to v1's), with the
  G4 recombination test from §5.1. Build & test chat, Sonnet · Medium; runs on Ben's PC.
- **Subitem 4** — Ben: push + run `v2_report.py` (dry run, then full) on the training side.
- **Subitem 5** — Extract results, score against §4's criteria using v2's own C1/C2/C3 (§3.6,
  §5.2), write the Result doc.
