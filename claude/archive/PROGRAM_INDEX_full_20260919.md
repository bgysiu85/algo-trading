# Algo Trading — program index

**Read this first.** The single entry point for the multi-strategy
conversation. Everything below is either a hard rule, a current state, or a
pointer to the doc that has the detail.

Keep this doc current. When a strategy's state changes, update the roster table
here in the same pass as the detail doc.

> **2026-09-08 — no strategy in this project has a positive edge after measured
> costs.** MC5 was described as the survivor for one day and is not: the
> +$8,209 credited to it on 09-07 was before the $4.26/round-trip friction
> measured live on 09-03 (with it, −$3.15/trade), and on the fuller XNAS.BASIC
> tape it is **−$8.93/trade, −$97,335, negative on every drop-top-N**. A
> pre-registered programme of three new hypotheses was run the same day and none
> survived. See `premarket_hypotheses_results_20260908.md`.
>
> **2026-09-11 — and it is not friction that is wrong with them.**
> `friction_reconciliation_20260911.md` §3 computed break-even friction on the
> screened universe: **MCL −$0.96/RT, VW9 −$0.70, MC5 −$4.67**. A negative
> break-even means the strategy loses money *at zero cost*. Every out-of-sample
> result here is negative **gross**. The long argument about which friction
> figure is right was answering a question that does not change the sign.
>
> Four attempts to improve MCL's exit or entry were measured on 19,292 sessions
> the same day — the take-profit ladder, Cameron's partial, Cameron's breakeven
> stop, and a dip entry. **All four lose.** Three looked promising on
> `bar_cache` first. See `ladder_and_regime_20260911.md`.
>
> **2026-09-11, later — the screener was finally simulated, and the leak was not
> where the audit was aimed.** `screen_sim` built a point-in-time universe;
> `pit_h0` and `pit_strategy` ran H0, MCL and MC5 on it. Splitting the
> look-ahead in two on one tape found the **universe leak NEGATIVE** for all
> three — stage 2's RVOL/range filter picked *worse* names than the live screen
> would have — and the whole leak, and more, in **buying a name before the
> screen would have surfaced it**. That second defect is a pure backtest
> artefact the live trader has never had, worth **+$6.84 (MCL) to +$61.06 (H0)**
> per trade. **MCL beats its control on both denominators** for the first time,
> and still loses $10.49 a trade. See `pit_strategy_result_20260911.md`,
> `pit_three_results_20260911.md`.
>
> ~~**The simulated universe has never been checked against the live screen**, and
> that now gates everything below it. See §7 item 1.~~ **Checked 2026-09-17 —
> see the entry of that date below.**
>
> **2026-09-16 — ORB is built, and it is the first strategy here to clear §11
> criteria 1–6 on its baseline cell: +$3.33/trade on XNAS.BASIC, flat 100,
> honest fills, drop-5 +$13,571, both halves positive, cluster bootstrap 1.000.**
> Criterion 7 is not met — the length family's optimum sits on the grid's edge —
> and, more than that, **it is measured on the stage-2-survivor universe, where
> H0 read +$4.72 and then −$15.78 point-in-time.** Nothing is believed until the
> PIT run. See `orb_first_results.md` §0. The same day: the live trader bought
> at the open on yesterday's 19:59 bar, and seeded its trail from a price the
> position never traded at — both fixed with a parity test against the engine
> (`session_open_defects_FIXED_20260916.md`); criterion 2 was replaced by a
> symbol-cluster bootstrap before ORB had a number, and MC5 fails it
> (`breadth_RESULT_20260916.md`); and the forming-bar trim became conditional on
> the clock (`bar_trim_RESULT_20260916.md`). Later the same day the live record
> exposed the **MEDS ghost** — an abandon path that read fills before IB had
> confirmed the cancel — fixed in seven parts with a reverse-ghost adoption the
> handover did not list (`ghost_position_FIXED_20260916.md`), promoted as
> `prod-20260916c`.
>
> **2026-09-17 — the first of the "fewer losing entries" hypotheses, H-B1 (skip
> the first entry of each symbol-day), reads NOTHING for MCL and REFUSED for
> MC5 on the point-in-time universe, and the live table that motivated it does
> not replicate:** first trades −$11.08, later trades −$9.64, both losing. The
> rule halves the trade count and moves per trade by +$0.03. Its bootstrap on
> the delta read P = 1.000 — because **on a losing book every total-based
> reading rewards abstention** (§4, new row). The time-of-day question **closes**
> on the same books: every MCL block negative at every friction, the named
> 07:45 cell failing all four pre-stated checks. See
> `first_entry_skip_RESULT_20260917.md`. ORB has moved to its own chat:
> `handover_orb_build_20260917.md`. **Later the same day, H-B3 (take a signal
> only if the name is top-3 by session range among the names visible at that
> minute) reads NOTHING for both** — the gate bound on 85% of entries, refused
> 55% of MCL's trades, and moved per trade by +$0.86 against random removal's
> 95th percentile of +$1.27. **Two of the four "fewer losing entries"
> hypotheses are read and the losing trades are not marked** — not by ordinal,
> not by relative range. See `range_rank_RESULT_20260917.md`. **And then
> H-B4, the 07:00 cold veto, reads NOTHING for both by four cents** — +$0.70 a
> trade against random removal's +$0.74 — closing the B-series at three of
> three: not by the morning's breadth either. B5 has nothing to combine. See
> `cold_veto_RESULT_20260917.md`. **Then Part A — luck or edge — answered
> neither:** MCL loses **$84.74 per session on same-day-hot sessions** against
> $58.82 on cold, MC5 $211 against $124; per trade is flat across the weather
> and a hot day only means more trades. Reading 1 fails on both paying labels,
> so **no regime gate, however good, rescues either book**, and the survivor
> universe's hot/mixed/cold ordering (−2.95 / −6.59 / −8.81) is gone on the
> point-in-time books (−9.66 / −11.42 / −10.68). See
> `luck_vs_edge_RESULT_20260917.md`. **The archive was then extended through
> 2026-09-17 at $0.00 (XNAS.BASIC daily, 04:00–09:30 and 15:55–16:05 slices),
> the screen simulated forward over the seven new sessions into a separate
> file, and A1 and A3 read: the 09-16 green day replays green (MCL +$36.54,
> MC5 +$12.41 on FTFT/MEDS/NAMI/RETO), and over 09-09..09-16 the code with
> the three fixes loses $783 where the live trader lost $762 — the fixes
> explain none of the six-session loss; the loss is the strategies.** See
> `replay_and_live_gap_RESULT_20260917.md`.
>
> **2026-09-17 — the tape was wrong, and the baselines have moved to the clean
> one.** Until 2026-03-30 the TRF opened at 08:00 and released the overnight
> off-exchange trades stamped with the release minute, so **every XNAS.BASIC
> pre-market bar from 08:00 on before that date carries prices from hours
> earlier** (`tape_spikes`, `trf_probe`). XNAS.ITCH — Nasdaq's book alone, no
> TRF — was pulled for the same window at $0. On the same 6,170 symbol-days the
> bars alone moved MCL from (10.52) to (8.82) and erased the before/after gap
> (`tape_compare_RESULT_20260917.md`). The screen was then rebuilt on XNAS.ITCH
> under `REGISTERED_screen_itch`: the diagnosis check passed exactly (the two
> tapes are identical until 08:00 before the cut, 1.000 at every decile), the
> exchange carries **23%** of BASIC's pre-market shares (not the 55–75%
> predicted), and the **published baselines are now H0 (11.90), MCL (8.81),
> MC5 (8.49) per trade** on a 6,564 symbol-day universe
> (`screen_pairs_pit_itch_p50.json`). Both beat the control on both
> denominators and still lose in both halves. The one defect the run found in
> its own method — a single 09:30 capture applied to a pre-08:00 window where
> the tapes were identical — was closed the same day by **v2**: the capture
> measured directly against the consolidated tape's cleared volume, every half
> hour, on each side of the TRF change (before: ~0.25 until 08:00 then 0.14–0.15;
> after: 0.020 at 04:30 rising to 0.111), and the screen rebuilt on that ladder.
> **The published baselines are H0 (11.77), MCL (8.97), MC5 (8.57) per trade on
> `screen_pairs_pit_itch_v2.json` (6,411 symbol-days)** — within cents of v1;
> the tape line closes. **Every 08:00-hour and before/after-2026-03-30
> conclusion measured on XNAS.BASIC is withdrawn as unmeasured.** See
> `screen_itch_v2_RESULT_20260917.md`, `screen_itch_RESULT_20260917.md`,
> `handover_tape_switch_20260917.md`.
>
> **2026-09-17 — halts, read off the tape for the first time.** The XNAS.ITCH
> `status` schema was pulled for 555 sessions at $0.00 under a registration.
> **Two trades in 10,370** on the v2 books had a halt begin inside them; no LULD
> pause exists before 09:30; pre-market halts touch 1.7% of universe symbol-days
> and are news halts at 06:30–08:30. **After the open, 17% of the universe's
> symbol-days are paused, and 37% of those pauses start 09:30–10:00 — 2.7 per
> session across the watchlist.** Halts are an ORB fact, not a pre-market one.
> The same pass re-based H-B1 on the v2 universe: REFUSED / REFUSED. See
> `halt_census_RESULT_20260917.md`.
>
> **2026-09-17 — the B-series and Part A re-based on the tape of record, and
> nothing moves.** Item 1c ran as four commands under PRE-RUN amendments: H-B1,
> H-B3, H-B4, Part A2 and the time-of-day table on `screen_pairs_pit_itch_v2`
> with XNAS.ITCH bars. **Every verdict stands.** What changed is the sign of the
> per-trade deltas: three of the six gated cells are now *negative* per trade
> (skip-first (0.41) / (0.78), top-3 (0.18) for MC5, the veto (0.16) for MCL)
> and read REFUSED by the denominator rule; the other three sit inside random
> removal's band (top-3 MCL +0.67 vs p95 +1.37; the veto MC5 +0.36 vs +0.94).
> Reading 1 of Part A fails on every label for both strategies (MCL (66.23) per
> session on same-day-hot, MC5 (120.66)); the 07:45 cell fails all four checks
> and the 08:00 blocks that read (16)–(17) a trade on BASIC read (8)–(10) here.
> The population check now keys on the universe file (3,955 / 3,960 / 3,908),
> and `luck_vs_edge` refuses inputs from different runs. See
> `bseries_itch_RESULT_20260917.md`.
>
> **2026-09-17 — the simulated screen is validated against the live
> watchlists, and it holds: 61 of 63 live names reproduced on XNAS.ITCH, and
> the identical 61 of 63 on XNAS.BASIC (97%, Wilson 89–99%, GOOD on the
> pre-registered band).** Eight automated sessions, 09-08 → 09-17 (seven on
> the day, 09-17 added on the 18th at 12 of 12), the September extension
> pulled on both tapes at $0.00. The 22 other live names are **yesterday's
> screen, re-served by TradingView at the feed's first poll** — the blocked
> files stamp them at 04:00:05–04:00:26, before any bar has closed — and the
> two real misses are a missing prior close (RML) and a name that peaked at
> +19.5% on both tapes (TPET). **Item 1 closes; the "unmeasured agreement"
> caveat on the v2 baselines is retired; item 23 (the Databento subscription)
> is unblocked.** Two live-feed facts came with it: **every name IBKR refused
> was refused 12–27 minutes after the tape first qualified it (median +15.6,
> 10 of 10, on both tapes)** — `tv_feed` polls the scanner endpoint without a
> session, and TradingView serves US equities 15 minutes delayed without a
> real-time subscription — and the first poll arms the previous session's
> names. The 15 minutes is a registration of its own (§7 item 1d) and a feed
> fix (live chat). See `screen_validate_itch_RESULT_20260917.md`.
>
> **2026-09-17, evening — three live-path defects from the 09-17 session fixed on
> `main`, not promoted** (`live_defects_FIXED_20260917.md`). The session itself
> was +10.16 over 37 trips on `prod-20260916c`, with every fix from the night
> before holding. **A.** After `_settle` began waiting for IB, a cancel the
> trader sent came back as `Cancelled` plus a blank 202 and was logged
> REJECTED — six rows, and the no-fill statuses vanished; the trader now
> remembers the ids it cancelled. **B.** Seven re-entries within five seconds
> of the same strategy's own exit, on a bar that had closed during the old
> position (RETO: sold 3.30, bought 3.29 on a bar that closed 2.45); an entry
> now needs a bar that OPENED at or after the exit, which is the engine's own
> rule — a first version on the bar's close was caught by the parity test.
> **C.** A registered placement guard (`REGISTERED_drift_guard`, 6% on the ask
> against the signal close, the 09-14/15 review's number, fixed before the
> code): a BUY is not sent into a quote that has left its reference. **D.** The
> research chat's finding that MC5's apex exit was OFF in every published
> figure and ON in every live session since 09-10 — the MCL split of 09-05,
> one module later, and the test meant to catch it compared the live value to
> the raw signal — is fixed the same way MCL was; live MC5 rows 09-10 to the
> promotion are apex-ON rows. Promote after a close, all four together
> (`build-20260917k`).
>
> **2026-09-18 — SPY intraday momentum is built, run and CLOSED, and it is the
> first line here to fail with a control proving the harness could have found
> the effect.** Gao/Han/Li/Zhou's *Market Intraday Momentum* (JFE 2018): the
> first half-hour return predicts the last half-hour return. Registered in full
> before any code (`spy_intraday_spec_20260917.md`, amendments A–M), run on
> 5,694 IB sessions back to 2004, with an independently pulled 1-minute cache
> agreeing with the 30-minute one **to the cent across 5,476 sessions**.
> **H0 flat** (−1.149 bps against the −1.150 the arithmetic demands). **H-R, the
> replication control over the paper's own 2005–2013 sample, reads AS
> PUBLISHED: +5.41%/yr, 53.52% directional hit against the published 54.37%,
> +3.320 bps/trade gross.** From 2015: **H-S1 48.12% hit, −0.308 bps GROSS,
> 0 of 5 gates over 2,336 sessions; H-S2 48.69%, −0.271 GROSS, 0 of 5 over
> 762.** The breadth control agrees and is also negative gross — QQQ (0.009),
> IWM (0.577). **Negative gross is the whole reading: no venue, fee schedule or
> execution improvement reaches it**, so `spy_intraday_AMENDMENT_A`'s Alpaca
> column changes nothing, exactly as its own §A.5 says for the small-cap books.
> By three-year block the gross runs +0.32, **+7.55**, +1.07, +1.24, (0.83),
> (0.19), (0.05), +0.20 — concentrated in 2007–09, where the paper's own R²
> table puts it (recessions 6.6% against expansions 1.0%), and **gone from 2016,
> which is earlier than the 0DTE era the skeptical reading blames; this does not
> support that mechanism, it dates the decay before it.** A registered stop fired
> on the way (amendment H: mean |r13| 0.1765% against a 0.18% bar set before the
> number was known) and the study was re-registered on the measured economics
> with the cell structure deliberately unchanged, because promoting the better-
> conditioned cell *after* seeing a measurement that favours it cannot be
> distinguished later from fitting. `holdout_spy.json` is committed and
> **unspent**. See `spy_intraday_RESULT_20260918.md`,
> `spy_intraday_data_pass_20260918.md`.
>
> **2026-09-18 — the five scenarios, and the first rule in this project to pass its own readings.** Ben's five: a $5 entry floor on the $2–20 watchlist, a 50% session give-back cap, the same per strategy, and the two combinations. Registered in `REGISTERED_price_floor.md` (H-S5) and `REGISTERED_giveback_cap.md` (H-S4, the research chat's, plus this chat's amendment A) before any code existed, run on `screen_pairs_pit_itch_v2.json` from one engine pass. **The $5 floor is nothing** — REFUSED for MCL (the denominators disagree), NOTHING for MC5 — and its registered mechanism does not operate as written: a flat per-trade friction cancels exactly out of a difference of means, which is why the floor's per-trade delta is **identical at $1.00, $4.26 and $8.92**. The share of the move that friction eats does differ by price, and it shows up per symbol-day, not per trade. **The give-back cap: MC5 passes all six registered readings, under both scopes, at every friction level — the first rule in this project to do that** — while MCL fails, and under session scope is made *worse* ((0.35) a trade), because the account-level cap fires largely on MC5's give-back and then removes MCL trades better than its average. The two combinations read NOTHING, failing the control alone: once the floor has removed the cheap names, the cap is no longer doing anything the floor was not. **Three corrections to the readings, all found by reading the first run against the registration rather than against itself, and all cutting toward the pass:** reading 5 was clustered by symbol where §4 says by session (corrected, MC5 still P = 1.000 over 546 sessions); **the matched-count control amendment A4 promised was never implemented** — the scored random cut removed 880 trades where the cap removed 1,022, and the per-trade delta scales with the share removed, so the mismatch flattered the cap; with the count matched exactly MC5 still clears (+0.78 against +0.57), and that is the check that could have overturned the pass; and the leading alternative explanation is now measured rather than argued (one-bar trades are 30.8% of removed against 27.5% of kept — real, and nowhere near enough to be the mechanism). The fire clock is spread across 04:00–09:00, so this is **not the time-of-day filter under another name**. **The pass is narrow and it does not reopen MC5**, which still loses **$7.79 a trade** after the cap against $8.57 before, and has been closed as a candidate since 2026-09-08. A rule that recovers 78 cents on a book losing $8.57 reduces a loss; it does not create an edge. See `session_scenarios_RESULT_20260918.md`.
>
> **2026-09-18 — and one test stands between that pass and the holdout.** H-S6 (`docs/research/REGISTERED_stop_compare.md`, then `common/stop_compare.py`, each committed before the next existed) asks whether the give-back's **peak-relative shape** beats the simplest rule in the same family: a **daily loss stop**, an absolute drawdown from zero, no arm and no ratio. The give-back fires on sessions *selected for having declined*, where stopping is close to tautologically better than continuing; all H-S4 established is that it beats a random cut in those same sessions. The two rules are genuinely different — a session that goes +$200 then back to +$50 trips the give-back and never trips a flat stop; a session that goes straight to −$150 without ever being up trips a flat stop and can never trip the give-back — and the question is what that extra piece of information is worth. **The threshold is solved, not chosen:** for each (strategy, scope, friction) cell, the STOP that removes as close as possible to the number of trades the give-back removed, so both rules spend the same abstention budget and no stop is ever selected for performing well. FLAT-40/100/200 are reported and never scored. **Run the same day: NO CELL SURVIVES.** Three of the four read UNDECIDED and one — MCL under strategy scope — reads THE SHAPE ADDS NOTHING, so §4 spends the holdout on neither rule. **The registered prediction was wrong in an informative direction:** it predicted the flat stop would capture most of the give-back's 78 cents leaving a residual of +0.10 to +0.50, and instead the flat stop captures **almost none of it** (+0.03 a trade against +0.68). What ends it is the bootstrap, not the magnitude — 0.932 and 0.934 where §4 requires 0.95 — because the two rules fire on 126 and 119 sessions and **share only 35**, so the whole difference rests on the ninety-odd sessions where the give-back fires alone. **And at $8.92, the friction this project treats as honest, MC5 strategy scope collapses to +0.21 with P = 0.665** — the give-back barely moves across the ladder while the matched flat stop gets thirteen times better, because at higher friction a stop solved to the same removal count sits deeper and fires on sessions that genuinely went wrong rather than on sessions that merely paid friction. That is not a near miss at the level that counts. **H-S4's pass is not withdrawn; what is withdrawn is the attribution** — that the 50% peak-relative *shape* is what produces those 78 cents is unsupported. One asymmetry worth keeping: the flat stop fires two-thirds of the time in the 07:00 and 08:00 hours because it needs losses to accumulate, so **of the two rules the give-back is the less clock-like**, which is the opposite of H-S4 §5's worry. `holdout.json` stays shut. See `stop_compare_RESULT_20260918.md`.
>
> **2026-09-18 — Ben's Running Up scanner, priced before it was built, and the
> answer came back inverted.** Modelled on Warrior Trading's Day Trade Dash
> alert and intended to run *in conjunction with* the watchlist — the strategies
> keeping their own entry conditions — so that between them they would identify
> names actually moving. `common/running_up.py` (eleven features, a crc32-seeded
> null control and a clock control) and `common/running_up_preflight.py`
> (descriptive only: no rule, no threshold, and a test asserting that no money
> and no scoring vocabulary reaches the report) ran the separation pass before
> any rule existed. **Every momentum feature separates in the WRONG direction.**
> MCL's five-minute return at entry reads AUC **0.751** against a null of 0.526
> and a clock control of 0.528: the trades that die on the next bar were entered
> after a **+11.43%** five-minute move, the ones that survive after **+4.90%**.
> A Running Up gate therefore keeps MORE dying trades than surviving ones at
> every threshold — it selects on the same axis, pointed the wrong way. MC5 is
> U-shaped rather than monotone (its bottom decile reads 41.3% one-bar against a
> 37.2% base), so **"don't buy while it is dropping" survives weakly** while the
> dominant structure is a **ceiling, not a floor**. The one cell pointing the
> other way is the pullback grid measured on the same pass: **near the session
> high AND not extended reads 3.3% one-bar on MCL against a 12.6% base, and
> 15.5% on MC5 against 37.2%** — which explains MCL-PB's six failures rather
> than contradicting them, because those versions bought the *breakout* after
> the pullback and paid a median +2.86% premium against a 5% trail. **And the
> one-bar sizing puts a ceiling on the whole line:** MC5's 2,412 one-bar trades
> lose **(31.95)** each, 139% of its net, and the remaining 4,050 are +$5.36 at
> $4.26 but **+$0.70 at $8.92**. MCL loses in every bucket. See
> `running_up_preflight_RESULT_20260918.md`.
>
> **2026-09-18 — H-E2, the entry sweep: earlier entry is achievable, and every
> trade it finds still loses money.** Registered in `8f36b2f` before any code
> existed and before either engine had a parameter for the swept constants.
> Three families, one constant each — MCL's MACD-above-zero clause, MCL's 3×
> volume multiple, MC5's RSI rate-of-change threshold — because V9 dropped the
> first two *together* and collapsed 81%, so neither had ever been read alone.
> Eleven books over the same 6,411 symbol-days, one tape pass, 95 seconds.
> **Nothing CLEARS and nothing IMPROVES.** Both scored families read
> **UNDECIDED — BOUNDARY** (best cell at the edge of the swept range: MCL vol
> 4.0, MC5 roc 1.0), seven of the nine non-base cells are REFUSED on the
> denominator rule, and MCL vol 4.0's +0.27 sits inside random removal's p95 of
> +0.75. **The informative number is not the verdict but the marginal trade —
> what each ADDED or REFUSED trade is worth — and it is negative everywhere:
> the best is (7.00), the worst (9.99).** Most of these cells ADD trades, so for
> the first time a per-trade reading in this project cannot have been
> manufactured by abstaining, and the answer is still no: adding trades worth
> (7.00) to a book averaging (8.97) raises the average and deepens the loss, and
> every per-trade "improvement" in the table is dilution rather than selection.
> **The mechanism operated at every link and paid nothing:** MACD-off moves
> entry extension 5.33% → 4.71% and one-bar deaths 12.6% → 11.1%; MC5's dial
> moves extension monotonically (2.17 / 2.38 / **2.69** / 3.08 / 3.24%) with
> one-bar deaths tracking it (34.5% → 40.9%). **And it refuted the registered
> primary hypothesis:** the 3× volume surge moves entry extension by **0.23
> percentage points** at its loosest, with the two middle cells reading no
> change at all — the surge is NOT what makes MCL's entry late, and F2 is also
> the worst family in the sweep, which now has an explanation instead of being a
> mystery. This is `friction_reconciliation`'s 2026-09-11 result seen one trade
> at a time: break-even friction MCL **(0.96)** and MC5 **(4.67)** a round trip
> means every entry these five clauses can be made to find, at any confirmation
> level, is a losing entry. **What it does not close is the pullback cell**,
> which selects *among* the entries the strategies already take rather than
> adding more; it carries a heavier prior after today and is still unregistered
> and unrun. See `entry_sweep_RESULT_20260918.md`.
>
> **2026-09-18 — the feed probe ran, and the login fixes the delay.** H-F1 §5
> (`common/tv_probe.py`, the build chat's) polled the scanner endpoint on two
> arms through pre-market. **Anonymous, TradingView labels its own row
> `delayed_streaming_900` — nine hundred seconds, the quarter-hour the block
> stamps measured from the other direction. Signed in with `sessionid` +
> `sessionid_sign`, the same column reads `streaming`.** The one name seen
> uncensored on both arms (CPOP) reached the signed-in arm 15.1 minutes first;
> at the same instant SSM showed 9.25M shares anonymously against 9.62M signed
> in. And the 04:00 carry-over was watched: five of 09-17's six HOT names sat on
> the first poll and never moved in 35 minutes. **`premarket_time` dates the
> row** — yesterday's 04:00 on the stale row, today's 04:00 once it is live — so
> the H-F1 gate can become an exact test. **The fix is a procedure, not a study:
> set `TV_SESSIONID` and `TV_SESSIONID_SIGN` in the window that starts the feed
> (via `op read`, never `setx`, which would send an `op://` reference as the
> cookie) and the watchlist is real-time from that session on.** See
> `feed_freshness_probe_RESULT_20260918.md`.
>
> **2026-09-19 — the 900 seconds priced (H-D1), and they are NOT the shape
> of the live book.** Every live session before 09-18 traded a screen 900 s
> behind the tape. Moving the simulation's entry floor to `first_seen + 15
> min` changes **MCL by +$0.09 a trade and MC5 by ($1.03)** — MC5 loses 29%
> of its entries, its better ones — moves win rate by under a point and R by
> under a quarter, and closes none of the distance to the live book; the
> registration's fixed words read **not it** on both the 550-session universe
> and the eight live sessions. **The gap the study existed to explain had
> mostly closed on its own:** live MCL is 50 round trips at 34% win / R 1.15
> over 09-08 → 09-17 against a simulated 30% / 1.47 on the same sessions —
> the 47% / 0.72 that started it was seventeen trades. One prediction failed
> informatively: a later floor enters *less* extended, not more — the +20%
> crossing that qualifies a name is the extension. Item 1d(a) closes; the
> live record before 09-18 is evidence about the published strategies. See
> `feed_delay_cost_RESULT_20260919.md`.
>
> **2026-09-19 — the pullback cell (H-P2), Ben's choice for the next build,
> ran the same day and is REFUSED on both books — and the reason closes a
> whole line of thought.** Within 5% of the session high AND `ret_5m` ≤ +3%,
> through `entry_gate`: the deployed gate kept 409 of MCL's 3,908 entries and
> 855 of MC5's 6,462 and **selected exactly the cell the pre-flight measured
> — one-bar deaths 2.9% and 16.3% against 12.6% and 37.3%** — and the kept
> books **lose more per trade than the books they were cut from: (9.40)
> against (8.97), (10.18) against (8.57)**. Win rate rose (23% → 28%); the
> money fell. All ten of MCL's ten best trades and nine of MC5's are outside
> the cell: the extension that produces the next-bar stop-outs produces the
> fat right tail too. The conjunction is worse than either of its halves.
> **The one-bar death rate closes as an entry-selection target** — the chase
> gate, the delay cost, the pullback cell and the pre-flight now agree from
> four directions — and the "fewer losing entries" line is closed in both
> directions on both tapes. New §4 standard: *a lower failure rate is not a
> better book.* See `pullback_cell_RESULT_20260919.md`.

---

## 1. Hard rules — non-negotiable, do not relitigate

| Rule | Why |
|---|---|
| **The connected IBKR account is LIVE and read-only. No orders, ever.** | Ben's explicit instruction. Enforced by a port allowlist (7497/4002 accepted; 7496/4001 rejected **by name**) and a `DU`-prefix `managedAccounts()` check. Paper account is `DUM215828`, net liq ~$22,129. |
| **TradeZero: nothing is placed until every account reports `accountType == "Paper"`.** | One base URL serves both live and paper; **only the key pair selects the environment**. |
| **API keys never appear in chat.** | Env vars, a local `tz_credentials.json`, or `op://` references resolved on Ben's machine. `DATABENTO_API_KEY` is env-only — never a CLI flag, which would put it in shell history. Client exceptions are scrubbed, because a Telegram token once leaked out of an error handler. |
| **A 1Password service account cannot read Private, Personal, Employee, or the default Shared vault.** | Hard product limit. Trading secrets live in a vault called **Trading**. |
| **`OP_SERVICE_ACCOUNT_TOKEN` must hold a literal token, not an `op://` reference.** | A reference cannot resolve itself. |
| **The SQL Server MCP login is read-only (`db_datareader`). Writes go only through `common/db_load.py`.** | The loader is idempotent by design; an ad-hoc write is not, and a doubled sum looks exactly like a valid one. |
| **One branch. Work on `main`.** | A branch cut before a shipped change silently reverts it. **Production is a TAG and a second working copy, never a branch** — see §3. |
| **Every strategy enforces the `$2–20` price band, at ENTRY.** | IB returns split-adjusted history. VW9 shipped without the band and traded entries up to **$4,152/share** — the adjustment factor, not a price. |
| **Every strategy uses the corrected fill model.** `gap_fills=True`, peak seeded from the entry price. | Found 2026-09-05. Inflated **every** published result: MC5 +$20,156 → −$400, MCL +$1,567 → +$161. Identical trades, different booking price. |
| **Every P/L figure states whether friction is charged.** | Added 2026-09-08. MC5's headline was quoted for a day without the $4.26/RT measured on 09-03, which was the difference between +$1.11 and −$3.15 a trade. Commission-only is not "after costs". **Strengthened 2026-09-11:** `leak_control` reports the engine's net and does NOT subtract friction, while every study does. Two numbers that looked comparable and were not launched a whole investigation into a 10× gap that was exactly $4.26. |
| **A hypothesis is registered before it is run.** | Added 2026-09-08. Rules and pass criteria written to a doc and committed first; the commit hash is the timestamp. With 29M bars, something profitable-looking is a property of search. `docs/premarket_hypotheses_20260908.md` is the template. |
| **The locked holdout is spent once, by one candidate, and code enforces it.** | `holdout.json`, 164 sessions from 2026-01-12. `strategy/premkt/run.py --set locked` refuses a second candidate and refuses `--limit`. A rule that lives only in prose gets broken by the first near-miss. **Since 2026-09-11 `holdout.split_sessions` is the ONE implementation** and every study that loads sessions calls it — a test asserts that, because two studies were written without it and would have read the locked slice while printing an ordinary-looking number. **Still unspent as of 2026-09-17.** **A second cut exists from 2026-09-18 — `holdout_spy.json`, 584 sessions from 2024-05-09, for the SPY study only — and it is unspent too. Each file names the study it governs and says the other does not apply.** |
| **A tool that can spend money states the number before it spends it.** | The same Databento request priced at **$1,500** with `symbols="ALL_SYMBOLS"` and under a cent scoped to the tickers actually wanted. **And a tool that can spend HOURS states that number too** (2026-09-18): the SPY puller prints its request count and wall clock and refuses to start without `--confirm`. |
| **`ib_async` is pinned at 2.1.0.** | Added 2026-09-12. The repo migrated off the archived `ib_insync` on 2026-09-04; `requirements.txt` then carried a bare `ib_async`, free to float. A broker API fails the morning IBKR changes something, mid-session, with a position open — not at install time. |
| **A report names the tape it read, and a grid refuses a tape it was not registered on.** | Added 2026-09-16. The first full ORB grid ran on EQUS.MINI because the default `--cache` pointed there and the runner recorded no tape; the report was indistinguishable from a real one. `strategy/orb/grid.py` now reads `SOURCE.txt` and refuses anything but XNAS.BASIC without `--anyway`. **Extended 2026-09-17:** every gate report names its universe file and its bars, and the population check compares against the count published for THAT file, never another's. |
| **Every text-mode file open names its encoding, and a guard refuses a bare one.** | Added 2026-09-16. Ben's machine is cp1252 and the cloud is UTF-8; a `§` in a report proved it. `tests/test_encoding_guard.py` also refuses a file whose parse raises a warning. |
| **An order's outcome is not known until IB says the order is finished.** | Added 2026-09-16. The MEDS ghost: fills read in the instant after a cancel was sent, before IB confirmed it. `_settle` waits for `isDone()`; an unconfirmed outcome is `ORDER_UNKNOWN` and nothing is sent until IB's position has been read. **And a cancel the trader sent is not a rejection** (2026-09-17): IB answers it with `Cancelled` and a blank 202, and the trader must know the id was its own. |
| **A strategy's live evaluation reads every flag its backtest reads, and the parity test compares the live value to the GATED rule.** | Added 2026-09-17, the third instance (harness literal 09-05, MCL evaluate 09-08, MC5 evaluate 09-17). `mc5.evaluate_last_bar` returned the raw apex signal for a week after the constant went False, and the test that compared live to backtest compared it to the raw signal too, so it pinned the defect. `tests/strategy/mc5/test_live_backtest_apex_parity.py`. |
| **An entry signal comes from a bar that opened after the strategy's last exit, and a BUY is not sent into a quote more than 6% from the signal close.** | Added 2026-09-17. The engine reads each bar once; a bar it held through or exited on is never an entry bar. A live BUY at a quote far from its reference is a trade the backtest does not contain, not a worse fill of one. Both restrict what live may buy; neither touches an exit. `live_defects_FIXED_20260917.md`, `docs/research/REGISTERED_drift_guard.md`. |
| **Pre-market bars are read from XNAS.ITCH. XNAS.BASIC pre-market bars before 2026-03-30 carry late-reported TRF prints from 08:00 on and are not quoted.** | Added 2026-09-17. 89.5% of 16,787 spike bars sat in the 08:00 hour; the prints cannot be picked out individually (no execution time, no condition flag), only removed as a class. Ratio conditions survive the switch; absolute volume thresholds must be re-scaled (`tape_capture`). `handover_tape_switch_20260917.md`. |
| **A sweep parameter reaches `backtest_session` and never `evaluate_last_bar`, and a test asserts the signature.** | Added 2026-09-18. H-E2 needed MCL's volume multiple and MC5's RSI rate-of-change as parameters, and both constants are read by `signals()`, which the live evaluator calls — so a research sweep sits one keyword away from altering live behaviour. The separation `price_min` already had is now the pattern: `None` reads the constant and is bit-identical, the swept value is passed to the backtest only, and `tests/strategy/test_sweep_params.py` asserts the parameter is absent from the live signature and present in the backtest one. |

---

## 2. Strategy roster

**All per-trade figures below are after tiered commission AND the $4.26/round-trip
friction measured live on 2026-09-03, unless the row says otherwise.** That
figure is now known to be **too small by roughly half** — see §4's friction row
and `stop_fill_20260911.md`.

### Built

| Name | Timeframe | Session | Status | Detail doc |
|---|---|---|---|---|
| **ORB** | 5-min trigger on a 15-min range | 09:45–16:00 ET, RTH only | **Built 2026-09-16; six of §11's seven on the baseline cell, and NOT shipped.** XNAS.BASIC, stage-2 survivors, flat 100, §9 fills, tiered commission and one tick each side (NOT the $4.26 row rule above — ORB's own registered friction is the engine's $3.37/RT against a measured $2.37 in RTH): **+$3.33/trade, +$16,218 over 4,875 trades / 2,414 symbols**; drop-3/5 **+$14,381 / +$13,571**; halves **+$7,050 / +$9,168**; cluster bootstrap **1.000**; passes the replaced criterion 2 that MC5 fails. **Criterion 7 not met** — the length optimum sits on the box's edge under both readings of "wins" (amendment C). **And the universe has manufactured an edge this size before** (H0: +$4.72 → −$15.78 PIT). The point-in-time run decides; nothing is believed until it has. `trail_pct` beat every fixed target in all 18 length×stop×retest combinations; the registered prediction held, for the wrong reason. **Owned by the ORB chat from 2026-09-17** (`handover_orb_build_20260917.md`). **Its RTH bars are on XNAS.BASIC; the tape switch note says check the spike census over the ORB window before assuming they are clean.** | `orb_first_results.md`, `orb_strategy_spec.md`, `docs/research/REGISTERED_orb_grid.md` (+ amendments A–C), `orb_preflight_RESULT_20260916.md`, `handover_orb_build_20260917.md` |
| **SPY-IM** | 30-min prices, 1-min sigma | 15:30–16:00 ET, one trade a session | **CLOSED 2026-09-18 — both cells NOTHING, and negative GROSS.** The JFE 2018 intraday-momentum mechanism: first half-hour predicts last half-hour. H-S1 (unconditional r1→r13): 48.12% hit, **−0.308 bps/trade before any friction**, (1.458) net at 1.15 bps, **0 of 5 gates** over 2,336 sessions. H-S2 (gated on sigma1 ≥ trailing 252-session p67, point-in-time): 48.69%, **−0.271 gross**, 0 of 5 over 762. Breadth agrees and is also negative gross: QQQ (0.009), IWM (0.577), both NOTHING. **H-R, the replication control, PASSED** — +5.41%/yr, 53.52% hit over the paper's own 2005–2013 sample — so the negative reading is about the market, not the pipeline. The effect concentrates in 2007–09 (+7.55 bps gross) and is gone from **2016**, earlier than the 0DTE era it is usually blamed on. Holdout **unspent** (584 sessions from 2024-05-09). No adapter and none wanted: **a strategy is paper-traded when it passes, and this did not.** Boundary surface and mechanism test deliberately NOT run — both are refusal checks for a *passing* cell, and a 3×3 grid over a dead cell only manufactures numbers to be tempted by. | `spy_intraday_RESULT_20260918.md`, `spy_intraday_spec_20260917.md`, `docs/research/REGISTERED_spy_intraday_data.md` (A–M), `spy_intraday_AMENDMENT_A_20260917.md`, `spy_intraday_data_pass_20260918.md` |
| **MCL** | 1-minute | 04:00–09:30 ET | **Live paper trading, apex OFF.** **Published point-in-time baseline, 2026-09-17 (v2), on XNAS.ITCH (universe and bars): −$8.97/trade, −$5.47/symbol-day over 3,908 trades**, beating H0 on both denominators (+2.79 / +5.13), negative in both halves ((8.94) / (9.00)) and after drop-top-5 ((9.86)). Superseded: v1 −$8.81 over 3,960; BASIC −$10.52 over 3,955. XNAS.BASIC training set: −$5.22/trade. It still loses, and "never trade" scores 0.00/symbol-day. Kept live to gather paper fills. **2026-09-16:** two session-open defects and the MEDS ghost fixed; `prod-20260916c` promoted. **2026-09-17:** skipping the first entry of each symbol-day does nothing per trade (+$0.03 on BASIC, (0.41) on ITCH v2); no entry gate and no regime bucket pays on either tape (`bseries_itch_RESULT_20260917.md`); the time-of-day table is negative in every block on both. **A3, 2026-09-17: over the six live sessions 09-09..09-16 the code with the fixes loses (498.95) in the backtest against (388.27) live — the fixes explain none of the live loss.** **2026-09-18: the $5 entry floor is REFUSED and the 50% give-back cap FAILS for MCL** — (0.16) a trade under strategy scope, (0.35) under session scope, where the account-level cap removes MCL trades better than its average (`session_scenarios_RESULT_20260918.md`). **And H-S6 ends MCL's cell outright: THE SHAPE ADDS NOTHING** — a flat daily stop matched on trades removed reads +0.24 a trade against the give-back's (0.16) at $4.26, and removes genuinely worse trades ((11.63) against (7.18)). Neither clears anything; MCL loses about $9 a trade either way (`stop_compare_RESULT_20260918.md`). **2026-09-18, the Running Up pre-flight: MCL's dying trades are its MOST extended entries** — median +11.43% five-minute move at entry against +4.90% for survivors, AUC 0.751 against a 0.526 null — so a momentum scanner used as a gate keeps more of them than it removes, at every threshold (`running_up_preflight_RESULT_20260918.md`). **And H-E2 closes "enter earlier" as a lever:** dropping the MACD-above-zero clause does move the entry earlier (5.33% → 4.71% extension, 12.6% → 11.1% one-bar deaths) and the 855 trades it adds are worth **(7.00) each**, the least-bad marginal trade anywhere in the sweep; the 3× volume multiple turns out not to be what makes the entry late at all (0.23pp at its loosest). The pullback cell — near the session high and not extended, 3.3% one-bar against a 12.6% base — **was run 2026-09-19 as H-P2 and is REFUSED: the deployed gate reads 2.9% one-bar and (9.40) a trade against (8.97), with all ten of MCL's best trades outside it** (`pullback_cell_RESULT_20260919.md`). The entry line is closed in both directions. **The universe these figures sit on reproduces the live screen (61 of 63 over eight sessions, 2026-09-17/18).** | `momentum_confluence_strategy.md`, `mcl_rejected_mechanics.md`, `screen_itch_v2_RESULT_20260917.md`, `screen_itch_RESULT_20260917.md`, `pit_strategy_result_20260911.md`, `session_open_defects_FIXED_20260916.md`, `ghost_position_FIXED_20260916.md`, `first_entry_skip_RESULT_20260917.md`, `bseries_itch_RESULT_20260917.md`, `replay_and_live_gap_RESULT_20260917.md`, `screen_validate_itch_RESULT_20260917.md`, `running_up_preflight_RESULT_20260918.md`, `entry_sweep_RESULT_20260918.md` |
| **MC5** | 5-minute | same window | **CLOSED as a candidate, 2026-09-08.** **Live MC5 ran apex ON from 2026-09-10 until the 09-17 fix is promoted** (`live_defects_FIXED_20260917.md` §D): every live MC5 row in that window is a different strategy from the published one. **Published point-in-time baseline, 2026-09-17 (v2), on XNAS.ITCH: −$8.57/trade, −$8.64/symbol-day over 6,462 trades**, beating H0 on both denominators (+3.20 / +1.96) — the denominator disagreement that refused a verdict on BASIC (+1.90 / −1.06) is gone, and at (8.57) a trade it changes nothing. 2,412 one-bar trades at (31.95) are 139% of its net. Superseded: v1 −$8.49 over 6,630; BASIC −$13.50 over 6,883. Apex exit switched OFF 2026-09-11. **Fails the replaced criterion 2 at 90.2% against 95%** (`breadth_RESULT_20260916.md`). **A3: 09-09..09-16 backtest (284.33) over 61 trades against (373.57) live over 93 — the live MC5 re-arms far more often than the backtest (43 live closes on 09-11 against 14).** **2026-09-18: the 50% give-back cap is the first rule in this project to pass all six of its registered readings, and it passes for MC5 under both scopes at every friction level** (+0.78 a trade at $4.26 under session scope, +0.68 under strategy, against a matched-count control's +0.57 / +0.47). **It does not reopen MC5**, which still loses $7.79 a trade after the cap; §6 of its registration says a pass is not adoptable on its own, and H-S6 — the daily loss stop that spends the same abstention budget — **was run the same day and read UNDECIDED under both scopes**: the matched flat stop captures almost none of the gain (+0.03 against +0.68) but the session-clustered bootstrap of the difference reads 0.932/0.934 against a required 0.95, and at $8.92 the cell collapses to +0.21 with P = 0.665. **The cap's pass stands; the attribution to the peak-relative shape does not** (`session_scenarios_RESULT_20260918.md`, `stop_compare_RESULT_20260918.md`). No entry gate and no regime bucket pays on ITCH v2 either (`bseries_itch_RESULT_20260917.md`). **2026-09-18, the one-bar sizing, and it is the ceiling on this line:** the 2,412 trades that die on the next bar lose **(31.95)** each — 139% of net — and the 4,050 that survive it are **+$5.36 at $4.26 but +$0.70 at $8.92**, so even a perfect one-bar filter leaves seventy cents a trade at honest friction. Its momentum separation is U-shaped rather than monotone (bottom decile 41.3% one-bar against a 37.2% base), so *don't buy while it is dropping* survives weakly and a Running Up gate does not (`running_up_preflight_RESULT_20260918.md`). **H-E2: the RSI rate-of-change dial moves entry extension monotonically (2.17 / 2.38 / 2.69 / 3.08 / 3.24%) with one-bar deaths tracking it (34.5% → 40.9%), every one of its four non-base cells is REFUSED on the denominators, and every marginal trade is worth (7.46) to (8.44)** (`entry_sweep_RESULT_20260918.md`). | `premarket_hypotheses_results_20260908.md` §1, `screen_itch_v2_RESULT_20260917.md`, `screen_itch_RESULT_20260917.md`, `apex_and_ladder_20260911.md`, `pit_strategy_result_20260911.md`, `first_entry_skip_RESULT_20260917.md`, `bseries_itch_RESULT_20260917.md`, `replay_and_live_gap_RESULT_20260917.md`, `running_up_preflight_RESULT_20260918.md`, `entry_sweep_RESULT_20260918.md` |
| **VW9** | 5m and 15m | 04:00–20:00 ET | **REJECTED on history.** Screened universe: −$4.96/trade. Break-even friction −$0.70/RT. Not in `LIVE_STRATEGIES` — cannot be paper traded. | `vw9_strategy_spec.md`, `vw9_backtest_engine.md` |
| **H0** | — | 04:30 entry, 8% trail | **The CONTROL, not a candidate — and rejected as a rule.** +$4.72/trade on stage-2 survivors was a look-ahead artefact. **Published control, 2026-09-17 (v2), XNAS.ITCH universe and bars: as screened −$11.77/trade, −$10.60/symbol-day over 5,775; knowable at 04:30 −$12.05 over 1,587, sitting 15% below the stage-2 rejects.** Superseded: v1 −$11.90 / −$10.71; BASIC −$15.40 / −$13.99. Constants live in `var/reports/pit_h0_itch_v2.json`, read by `pit_strategy --h0`; the `H0_*` block in `pit_strategy.py` remains the BASIC reference. | `screen_itch_v2_RESULT_20260917.md`, `screen_itch_RESULT_20260917.md`, `pit_h0_result_20260911.md`, `strategy/premkt/h0_engine.py` |

**Four attempts to fix MCL, all rejected 2026-09-11** on 19,292 sessions
(`ladder_and_regime_20260911.md`): the take-profit ladder (−$1,612, and the
**linear control lands within $13**); Cameron's partial (−$1,435); **Cameron's
breakeven stop (−$27,260**); and an inferred dip entry.

**Re-tested floored, 2026-09-12** (`floor_delta_result_20260911.md`): the
ladder's delta does not move (0.16, not material); Cameron's partial's **does**
(0.87, material) — its cost fell by a third, and its **direction survived**. The
rule to carry: **published deltas are durable in direction and unreliable in
magnitude.** The breakeven stop, the largest of the four at −$6.31/trade, is the
one that cannot yet be expressed as a variant — see §7 item 6.

**The 5% trail survives every challenge brought against it.** It has never been
run as an **ensemble**, which §4 says it should be. **And on ORB it beat every
fixed target from the ten source videos, at every length and both stops.**

**MCL-PB — six registered versions on 2026-09-16, none profitable.** Wait for a
pullback, buy the break of the peak. v1 cancelled 72.5% of setups on depth and
paid a median +2.86% premium to be confirmed; the later versions are Ben's own
rules from his trade history. See `pullback_break_*_RESULT_20260916.md`.
**v2's 08:00 anomaly is what exposed the tape defect.** **And 2026-09-18 gives
the six failures a mechanism rather than a shrug:** waiting for the dip is not
what failed — *buying the breakout after it* is. The pre-flight's pullback grid,
which never buys the break, reads 3.3% one-bar on MCL against a 12.6% base, and
the archive shows MCL lost $4.46 a trade on pullback days against $14.56 on
others (`running_up_preflight_RESULT_20260918.md`).

**Fewer losing entries — the B-series, 2026-09-17** (from
`handover_luck_vs_edge_and_entry_quality_20260917.md`). **H-B1, skip the first
entry: NOTHING / REFUSED**; first entries are not worse than later ones on the
point-in-time books. **H-B3, top-3 by session range among visible names:
NOTHING / NOTHING**; the gate's per-trade gain (+$0.86 / +$0.96) sits inside
random removal's band (p95 +$1.27 / +$1.34), and top-1 (reported) is tighter
and still inside. **H-B4, no new entries after 07:00 on a session that reads
cold at 07:00: NOTHING / NOTHING**, the closest call (+$0.70 against random's
+$0.74 for MCL); the watchlist proxy for the composite is dominated by its
count rule (297 of 363 vetoes) and separates vetoed from admitted after-07:00
trades by $0.97. H-B2 (one position per name across strategies) needs the
concurrency cap modelled first (§7 item 15). **B5 has nothing to combine.**
**Re-based on the ITCH v2 universe the same day (`bseries_itch_RESULT_20260917.md`):
H-B1 REFUSED / REFUSED, H-B3 NOTHING / REFUSED, H-B4 REFUSED / NOTHING.** The
per-trade deltas turned negative in three of six cells — skip-first (0.41) /
(0.78), top-3 (0.18) for MC5, the veto (0.16) for MCL — so the trades those
gates refuse are, if anything, slightly better than the ones they keep; the
other three sit inside random removal's band (+0.67 vs +1.37, +0.36 vs +0.94,
top-1 +1.99 vs +3.25). The veto reads 341 of 550 sessions cold (240 by
count, 101 by composite). **Not a pass on either tape, in the same direction,
by the same control; the BASIC result docs stand as BASIC results.**

**The entry line, 2026-09-18 — the other direction, and it closes too.** Every
B-series hypothesis asked which existing trades to *remove*. H-E2 asked the
opposite question — whether *less* confirmation, taken earlier in the move, is
worth taking — because the pre-flight had shown the entries die from being late
rather than from being unselective. Nine cells across three families, most of
them ADDING trades, and **every marginal trade is worth between (7.00) and
(9.99)**. Taken with the B-series, both directions on the entry are now read on
the tape of record: **removing trades does not select, and adding them does not
either.** `entry_sweep_RESULT_20260918.md`.

### Specified, no code

| Name | What | Readiness |
|---|---|---|
| **Warrior 2 / 3 / 4** | Flat top, gap-and-go, reversal | **Argued against by the census.** By Cameron's own record these are his *riskiest* setups — flat top **1.9×** red-day lift, halt resumption **2.4×**, reversal **2.6×**, against the micro pullback's 0.7. The reversal's short side is **not buildable**. | `warrior_2_flat_top.md`, `warrior_3_gap_and_go.md`, `warrior_4_reversal.md` |
| **L1 / L2 large-cap** | Intraday momentum + short-term reversal, 5-min, US large caps | **Premise already measured and it is weak.** The raw Bollinger dip-buy shows **no edge**: −0.010% excess per trade, t = −0.18 Newey-West, and what edge appeared was **2008 alone**. RSI(14) vs %b is **ρ = +0.911** — one signal, not two. **And the SPY-IM result of 2026-09-18 bears on L1 directly: the published large-cap intraday-momentum effect is gone from 2016 and negative gross on SPY, QQQ and IWM.** | `largecap_strategy_spec.md`, `largecap_evidence_20260911.md`, `factor_correlation_result_20260911.md`, `spy_intraday_RESULT_20260918.md` |
| **TSMOM** | Time-series momentum, ~8–12 micro futures, monthly | **Best evidence of anything unbuilt.** Moskowitz/Ooi/Pedersen, *JFE* 2012, heavily replicated, documented **crisis alpha**, no exposure to US small-cap order flow. Futures margin only (~USD 10–20k). **Register a replication control with it** (§4, added 2026-09-18): the same code over the paper's own sample, with a pass band fixed before the run. | `diversifier_candidates_20260911.md` §5.1, `tsmom_spec_20260917.md`, `docs/research/REGISTERED_tsmom.md` |
| **Faber** | 5 ETFs, 10-month SMA, long-or-cash, monthly | **Lowest effort, weakest evidence.** Has materially underperformed buy-and-hold since ~2009. | `diversifier_candidates_20260911.md` §5.2 |
| **E15** | 15-minute, 04:00–20:00 ET | **Dormant.** Cannot reach pre-market. VW9's result lowers the prior considerably. | `archive/ema15_full_day_strategy_spec.md` |

### Rejected before building

**GEM (Antonacci Dual Momentum)** — verified and rejected 2026-09-11. Out of
sample since publication: **8.4%/yr against SPY's 13.6%** over twelve years.
`diversifier_candidates_20260911.md` §2–3.

### What is live

`main.py` has **`LIVE_STRATEGIES = {"mcl", "mc5"}`**. VW9 remains backtest-only.
**ORB is not in `LIVE_STRATEGIES` and has no adapter; the trader has never
placed an RTH order.** **SPY-IM is closed and will never get one — it failed
every gate.** **Only MCL and MC5 have ever placed an order, and only on
paper.** Production is at **`prod-20260918`** as of 2026-09-18, which carries
the four 09-17 live-path fixes (self-cancel, bar-after-exit, drift guard, MC5
apex gate); the promotion was measured first — **9 of 208 changed files reach
the live import closure, six of them encoding-only.** `main` is ahead of it by
research code only. **The live-path surface in any future diff is `trader.py`,
`mcl.py`, `mc5.py`, `session_lock.py`, `scanner.py`, `scan_params.py`;
everything else — ORB's SIP modules, the swing spread work, the SPY study, the
Running Up and entry-sweep modules — is research code the trader never imports.**

**The live record, 2026-09-12 — the only look-ahead-free evidence here:**

```
99 round trips over 6 sessions, -$679.69
MCL   n=17   (81.38)   (4.79)/trade   win 47.1%   R 0.72   needed 1.12
MC5   n=59  (369.97)   (6.27)/trade   win 11.9%   R 2.71   needed 7.43
```

**Updated to 09-16 by the analysis chat:** 134 round trips over 09-09..09-16,
(761.84), (5.69)/trade, 22.4% win; 28 trades held ≤ 1 minute lost (536.37).
The 09-16 green day (+212.95) was the opportunity set — MEDS +149% — not
execution (`green_day_attribution_20260916.md`). **And the backtest with this
week's three fixes, on the simulated screen for the same six sessions, loses
(783.28) over 113 trades — the same money. The 09-16 day replays green
(`replay_and_live_gap_RESULT_20260917.md`).**

**The live record disagrees with the point-in-time backtest about the shape of
the deficit.** Live MCL is 47.1% win / R 0.72 — the published stage-2 shape.
The simulation says 21.7% / R 1.67. Same screen specification, different tape
and reality. n=17 is nothing; 2,682 simulated trades on an unvalidated universe
is not automatically better. See `mcl_session_20260911_review.md` §3. **And the
live "first entries lose" table did not replicate either** — six sessions of a
circular cut (`first_entry_skip_RESULT_20260917.md` §4). **The universe is
validated now (2026-09-17/18, 61 of 63), and the feed's quarter-hour delay
has been priced (H-D1, 2026-09-19): a 15-minute floor costs MCL nothing per
trade and MC5 a dollar, and moves neither book toward the live one. At fifty
live MCL trades the shape is 34% / R 1.15 against a simulated 30% / 1.47 on
the same sessions — most of the gap was sample size. What remains (a third of
a point of R; a live hold of 12 minutes against 5) is not the feed; the
concurrency cap is the next candidate (item 15).**

### MCL — currently shipped config

```
USE_APEX_EXIT            = False    # gated in evaluate_last_bar too, 2026-09-08
REQUIRE_MACD_POSITIVE    = True     # H-E2 swept it OFF: REFUSED, and the 855
                                    # trades it adds are worth (7.00) each
TRAIL_PCT                = 5.0      # ONE draw from a distribution -- see §4
VOL_MULTIPLE             = 3.0      # H-E2 swept 1.5/2.0/2.5/4.0: UNDECIDED --
                                    # BOUNDARY, and it is NOT what makes the
                                    # entry late (0.23pp at its loosest)
PRICE_MIN, PRICE_MAX     = 2.0, 20.0
ENFORCE_PRICE_BAND       = True     # applied in the LIVE path, trader.py:985
COMMISSION_PLAN          = "ibkr_tiered"
max positions            = --max-positions, default 2; run at 3 for mcl,mc5
gap_fills                = True     # corrected 2026-09-05
seed_peak_with_bar_high  = False    # corrected 2026-09-05
SLIPPAGE_TICKS           = 1        # measured: overcharges ~$1/RT, kept
scale_out / pyramid / scale_up / ladder / target_exit = None   # all REJECTED
not_before               = None     # the point-in-time entry floor; live has
                                    # it for free, backtests must be told
skip_entries             = 0        # H-B1's parameter; 0 is bit-identical, and
                                    # 1 read NOTHING on BASIC, REFUSED on ITCH
                                    # -- never set live
vol_multiple             = None     # H-E2's parameter; None reads the constant,
                                    # and evaluate_last_bar does not take it
```

**Apex removal is worth +$1,702 at a 5% trail but only +$311 at a 2% trail.**
The two rules are substitutes. Do not quote +$1,702 as its value in general.

### The live screen (TradingView), as of 2026-09-08

```
premarket_change   >= 20        # gap vs the PREVIOUS REGULAR CLOSE
premarket_close    in [2, 25]   # screen ceiling $25; the trader still refuses above $20
premarket_volume   >= 100,000
```

Relative volume and float were removed. All three columns are verified to filter
server-side.

**What the simulated screen surfaces, run forward at 60s cadence:** 9.1
candidates a session against stage 2's 41.8, a **median of ONE name by 04:30**,
and **29.7% of sessions with none at all**. Half the universe does not appear
until after 07:30. `screen_sim_result_20260911.md`. **On XNAS.ITCH v2 (2026-09-17):
6,411 symbol-days, median 11 a session, 1,771 knowable by 04:30, first seen
median 07:01. The volume clause is scaled by a measured capture ladder; on
post-2026-03-30 sessions that threshold is 2k–11k exchange shares and a weak
proxy for the live clause (`screen_itch_v2_RESULT_20260917.md` §2).**

**Validated against the archived live watchlists, 2026-09-17/18
(`screen_validate_itch_RESULT_20260917.md`):** 61 of 63 live names reproduced
on both tapes over eight sessions, once the 04:00 carry-over is set aside.
**Two things the live feed does that the simulation does not:** it returns the
previous session's screen at its first poll (TradingView's `premarket_*`
columns hold yesterday's values until today's prints; blocked stamps at
04:00:05–04:00:26 prove it), and — until 2026-09-18 — it saw each name **15
minutes after the tape did**: the scanner endpoint, polled without a session,
labels its rows `delayed_streaming_900`; signed in it labels them `streaming`
(`feed_freshness_probe_RESULT_20260918.md`). With the two cookie variables set
before the feed starts, the live watchlist is real-time. On post-change sessions the ITCH ladder admits ~13% more
symbol-days than the live screen showed (11 sim-only names against BASIC's 2).

---

## 3. Infrastructure

**Repo:** `D:\Trading`, one git repo, private GitHub `bgysiu85/algo-trading`.
**3,647 tests green on `main`, 2026-09-18** (3,363 after the live-path fixes and
`screen_validate`, plus 40 for the SPY intraday modules), and **3,738 after the
Running Up and entry-sweep modules** (24 + 17 + 19 + 13 + 18). Measured in the
cloud minus the four modules that need `databento` / `sqlalchemy`; confirm on
the next full Windows run.

```
main.py                 single entry point
common/                 backtest.py, cache_io.py, indicators.py, analysis.py,
                        commissions.py, portfolio.py, notify.py, report_io.py,
                        report_fmt.py       accounting brackets + terminal colour
                        textio.py           the two-generation decoder (cp1252 then UTF-8)
                        harness.py          ONE position lifecycle, validated
                        holdout.py          the locked cut + split_sessions
                        leak_control.py     survivor-vs-reject, rate AND quality
                        entry_latency.py    where the fill sits in the signal bar
                        provenance.py       WHICH code is running, WHICH var/
                        tape_compare.py     two caches, the same symbol-days
                        tape_capture.py     ITCH/BASIC pre-market volume ratio ladder (v1; the chain, superseded)
                        itch_capture.py     ITCH vs EQUS.SUMMARY cleared volume by the half hour, per regime -> the ladder
                        pairs_overlap.py    two universe files side by side
                        regime.py / regime_study.py    hot/mixed/cold
                        regime_labels.py    the composite against 277 human labels
                        breadth.py          criterion 2 as replaced: the cluster bootstrap
                        bar_freshness.py    which minute the trader acts on, and IB's clock
                        dip_entry.py / dip_study.py    the inferred dip entry
                        profit_ladder.py / target_exit.py   both REJECTED
                        pullback_break.py   MCL-PB v6, the study template
                        first_entry_skip.py H-B1: four books from one PIT pass, + trades CSV;
                                            the population check keyed on the universe file
                        time_of_day.py      the ET block table, read off that CSV
                        session_stop.py     H-S4's give-back cap and H-S6's flat daily stop as ONE
                                            forward sweep, the random-cut control, and the SOLVED
                                            threshold that matches the two rules' removal counts
                        session_scenarios.py  the five scenarios of 2026-09-17 from one engine pass
                        stop_compare.py     H-S6: the give-back's shape against the matched flat stop,
                                            off the scenarios trades CSV -- no second pass over the tape
                        running_up.py       the Running Up features: eleven of them, a crc32-seeded
                                            null control (str hashing is salted per process), a clock
                                            control, and AUC with average ranks over ties
                        running_up_preflight.py  the separation pass: DESCRIPTIVE ONLY -- no rule, no
                                            threshold, and a test asserting no money and no scoring
                                            vocabulary reaches the report
                        entry_sweep.py      H-E2: eleven books from one tape pass, the marginal trade,
                                            and the mechanism read back as a measurement (median
                                            five-minute return at entry, per cell)
                        gate_study.py       the five readings every entry gate inherits,
                                            with the abstention control
                        range_rank.py       H-B3: rank among visible names, gated at top-N
                        cold_veto.py        H-B4: the 07:00 reading, point-in-time cut, clock veto
                        luck_vs_edge.py     Part A: the books by four session labellings, per session
                                            over ALL sessions, the break-even reading; --daily-dataset
                                            for the regime, refuses inputs from different runs
                        tape_spikes.py / trf_probe.py   the tape probes that found the TRF defect
                        halt_census.py      the status schema: halts by window and reason, joined to the books
                        spy_intraday_data.py    IB depth/duration probe + the paced, resumable pull
                        spy_intraday.py         sessions, the five assertions, the SPY holdout cut
                        spy_intraday_study.py   H0, H-R, H-S1, H-S2, the five gates, breadth
                        screen.py           the screener, simulated
                        screen_at.py        the screen AS OF a timestamp
                        screen_sim.py       it, run forward -> the PIT universe (--dataset, --capture, --capture-ladder,
                                            --out, --after: new sessions only, refuses the deciding file)
                        screen_validate.py  the simulated universe against the archived live watchlists:
                                            header date, the 04:00 carry-over set aside, two clocks, --diagnose
                        screen_miss.py / screen_lag.py   the older per-clause diagnosis and the session-offset probe
                        pit_h0.py           H0 on that universe; writes its constants as JSON beside the report
                        pit_strategy.py     MCL/MC5/H0, three arms, one tape; --h0 <json> picks the control
                        pit_delta.py        does the floor move a DELTA?
                        mfe_exit.py         is the exit the problem?
                        db.py / db_load.py  SQL Server: 16 tables, drift check
                        databento_*.py      the archive, scoped and priced
                        tv_screener.py      the live screen, pinned
                        tv_feed.py          it, on a loop, -> var/watchlist.txt; sends the TradingView
                                            session cookie when BOTH env vars are set, reads update_mode
                                            at startup, holds a name until its premarket_volume moves (H-F1)
                        tv_probe.py         the two-arm probe: update_mode, the roll, authenticated lead
brokers/                ibkr (trader, scanner), tradezero
strategy/mcl|mc5|vw9/   the three engines (mcl and mc5 carry not_before,
                        entry_bars [mcl only], skip_entries, entry_gate, and
                        H-E2's sweep parameters -- vol_multiple on mcl,
                        entry_rsi_roc on mc5, both backtest-only)
strategy/orb/           preflight.py, orb.py (the rule, one symbol-day, no
                        aggregates), grid.py (ninety cells, nothing ranked,
                        refuses the wrong tape) -- the ORB chat's from 09-17
strategy/premkt/        the registered hypotheses, their runner, h0_engine
pine/                   MCL, MC5, VW9 TradingView scripts + README
tests/                  central, 3,738
bar_cache/3d_to_2000/       IB bars, SPLIT-ADJUSTED, p50 0.831 of the tape
bar_cache_db/3d_to_2000/    Databento EQUS.MINI, raw, p50 0.048
bar_cache_xnas/3d_to_2000/  Databento XNAS.BASIC, raw, p50 0.552
bar_cache_spy/30min/        IB 30-min RTH, TRADES, 2005+ -- SPY, QQQ, IWM
bar_cache_spy/1min/         IB 1-min RTH, TRADES, 2005+ -- SPY (sigma1, boundary, cross-check)
holdout_spy.json            the SPY cut -- 584 sessions from 2024-05-09, UNSPENT
var/                    gitignored: real fills, real positions, reports
E:\Databento\           the bought archive -- OUTSIDE the repo
                        XNAS.BASIC/ohlcv-1m  04:00-09:30 windows, TRF-contaminated before 2026-03-30
                        XNAS.ITCH/ohlcv-1m   the same windows, exchange only -- the tape to quote
                        XNAS.ITCH/status     trading status, whole day, 27 monthly chunks -- halts
                        EQUS.SUMMARY/statistics   consolidated cleared volume by the clock, stage-2 + PIT names
```

### Production and development — two trees, ONE `var/`

```
D:\Trading          development. main. Edit freely. Studies and backtests here.
D:\TradingProd      production. Checked out at a TAG. Sessions run from here.
D:\TradingProd\var  a DIRECTORY JUNCTION to D:\Trading\var
```

**The junction is not a convenience, it is the safety property.**
`session_lock.LOCK_PATH` is relative, so two trees with their own `var/` have
**two lock files** and the lock protects nothing. One shared `var/` also keeps
ONE fill ledger, which is required because the IB account is shared.

A junction fails **silently**, so it is checked rather than assumed:

```
python -m common.provenance --expect-shared-var D:\Trading\var
```

`SESSION_MODES = {"paper", "dry"}` take the lock and **backtests do not**, so
research in the development tree runs freely during a session. **But a paced
multi-hundred-request IB pull is not a backtest: it shares the account-wide
request budget with the live trader. Check `var/state/session.lock` first.**

**A promotion is measured, not assumed** (2026-09-18). `main` was 208 files
ahead of the tag across three chats; the question that matters is not how many
files changed but **how many of them the live process imports**. Walking the
import closure from `main.py` found **9 of 208**, six of those encoding-only —
so the promotion of `prod-20260918` was a four-fix promotion with a large
research diff riding along, and could be described that way before it happened.

### Which tape, and why it decides results

**EQUS.MINI publishes a median 4.8% of the consolidated tape. XNAS.BASIC
publishes a median 55%** (p10 0.458, p50 0.552, p90 0.656). **TRF-inclusive is
not consolidated**, so any volume-derived figure on that cache is understated by
about 1.8×.

**XNAS.ITCH is XNAS.BASIC without the TRF, and it is the pre-market tape from
2026-09-17.** Before 2026-03-30 the TRF opened at 08:00 and released the
overnight off-exchange trades stamped with the release minute; BASIC's minute
bars from 08:00 on carry those prices in high, low, close and volume. ITCH
carries **23% of BASIC's pre-market shares** at 09:30 (band median; p10 0.009,
p90 0.677 — a far wider capture band than BASIC's), and before 08:00 on every
pre-cut session the two tapes are identical. Measured directly against the
consolidated tape's cleared volume (`itch_capture`), Nasdaq's book carries
**~0.25 of what the live screen could see until 08:00 before the change, then
0.14–0.15; after the change 0.020 at 04:30 rising to 0.111 by 09:30** (band
medians; p10 is 0.000 early after the change). The screen scales its 100,000
by that ladder, per tick, per regime.

**A result on one tape is not a result on the other**, and MC5 is the proof:
+$1.11/trade on EQUS.MINI, −$8.93 on XNAS.BASIC. **And the bars alone moved MCL
from (10.52) to (8.82) between BASIC and ITCH on a fixed universe.**

**The tape decides WHICH trades get taken and barely touches how a shared trade
turns out.** Only **16.4% of trades pair** between xnas and MINI. Per trade the
two land close — **but they share 16% of their trades, so that agreement is
arithmetic and not replication.**

**The archive reaches 2026-09-17 on both pre-market tapes as of 2026-09-18**
(XNAS.BASIC daily, 04:00–09:30 and 15:55–16:05 slices; XNAS.ITCH 04:00–09:30;
all inside the free window; the September daily chunk re-pulled whole on the
18th, which restored the 09-01–04 bars). The September sessions are screened
into separate files — `screen_pairs_pit_itch_ext.json` (ITCH, v2 ladder, 76
symbol-days) and `screen_pairs_pit_ext2.json` (BASIC, 67), 09-08 → 09-17 —
and `screen_validate` read both against the archived live watchlists:
**61 of 63 on each** (`screen_validate_itch_RESULT_20260917.md`). September
2026 is after the TRF change, so BASIC's 08:00 defect does not touch these
sessions; on them the ITCH ladder is the looser screen (11 sim-only against 2).

**The RTH large-cap bars are a fourth source and are IB's, not Databento's**
(2026-09-18): `bar_cache_spy/` holds SPY, QQQ and IWM 30-minute RTH from 2005
and SPY 1-minute over the same window, `whatToShow="TRADES"`, split-adjusted
and consistently **not** dividend-adjusted. The 30-minute and 1-minute caches
were pulled independently and agree on the 10:00 price **to the cent across
5,476 sessions** — the cheapest control this project has ever had on a data
path.

**Still open: the same check for MC5.** `tape_compare` runs MCL only.

### The Databento archive

**Billing is on RETRIEVAL. A file on disk is free to read forever.** L0
(`ohlcv-*`, `definition`, `statistics`) gets 8+ years; L1 gets **one rolling
year**.

**Daily bars are NOT split-adjusted.** A 1-for-10 reverse split prints as a
~900% overnight gain. Left in, they ARE the leading gainer on most days.

**Cloud-sandbox delivery.** Build and test in the cloud clone,
`git bundle create`, write the bundle into `D:\Trading\Claude outputs\`,
`git fetch` it by local path. **Three chats now write to one repo** (build,
live analysis, ORB): a bundle is cut only on a base that already contains
Ben's current tip, and bundle names are prefixed by chat. **When the Cowork
session has `D:\Trading` connected it can commit to `main` directly and no
bundle is needed — but `git status` there writes `.git/index.lock` and cannot
delete it without a delete grant, and every git command on Ben's side then
fails until the file is removed.**

---

## 4. Standards of evidence

A result is not accepted on net P/L alone. This list killed V8, V9, every
`TRAIL_PCT` candidate, VW9, the scale-out, the pyramid, the scale-up, confirm-N,
MC5, all three pre-registered hypotheses of 2026-09-08, the take-profit ladder,
Cameron's partial, Cameron's breakeven stop, the dip entry, **H0 itself**,
six versions of MCL-PB, the first-entry skip, both SPY-IM cells, **and every
cell of the entry sweep**.

| Check | What it is |
|---|---|
| **Register before you run** | Rules and pass criteria committed *before* the first result exists. A rule that needs changing is a new hypothesis and spends from a fixed budget. **Amendments are marked PRE-RUN or POST-RUN.** **And a registered stop can fire before a result exists at all:** SPY-IM's amendment H set 0.18% on a volatility measurement, the measurement came in at 0.1765%, and the study stopped and re-registered on measured economics before H0 ran. |
| **Friction, always, and stated** | Break-even $/round trip against the **measured** figure. **The $4.26 is too small by roughly half:** 21 live trailing-stop exits give a **mean −$8.46 per 100 shares**, converging with the independent end-to-end −$8.92. |
| **Report at all three friction levels** | $1.00 / $4.26 / $8.92. Every `pit_*` module does this. One extra column, and it removes the argument from every future doc. **A venue column is the same idea** (`spy_intraday_AMENDMENT_A`): reported, never scored, because a cell that passes only at a fee schedule we have not traded on has not been demonstrated. |
| **Where does the chosen cell sit in the DISTRIBUTION of cells?** | ReSolve built **1,226 GEM variants**: the published spec beat only **61%**. "Beat 61% of variants" is far more honest than "best in the grid". |
| **Prefer an ensemble to a chosen parameter** | ReSolve's equal-weight ensemble had a **13.2% drawdown against the median single spec's 17.4%**, at no cost. **Cheap, and never tried** for MCL's trail. |
| **drop-top-N on the level** | Net after removing the best 1/3/5 symbols. **And say "n/a" rather than $0 when the arm has N or fewer symbols** — the drop then removes everything, and a printed zero reads as "the top names cancelled out". |
| **drop-top-N on the *delta*** | The same rule applied to a *change*. |
| **A LEVEL bias does not transfer to a DELTA** | Added 2026-09-12. The intraday floor moved MCL's level by **6.84** and the ladder's delta by **0.16** — a 43× difference, because a subtraction between two exit rules on the same trades shares its entry timing. But a delta with a real effect **does** move: Cameron's partial shifted 0.87, a third of its size. **Direction durable, magnitude not.** `floor_delta_result_20260911.md`. |
| **Two denominators, and a disagreement is a refusal** | Added 2026-09-11. H0 takes at most one trade per symbol-day; a strategy takes as many as it likes. MC5 read **+1.53/trade and −1.12/symbol-day** against the control — a sign flip living entirely in the denominator, decided by how often it trades rather than how well. Report both; refuse a verdict when they disagree. **Clarified 2026-09-16: the refusal attaches to a COMPARISON.** One cell's two denominators are the same net over two positive divisors and always share a sign; a per-cell version of the check can never fire. **Fired again 2026-09-17** on MC5-skip1 (−1.05 / +4.71), and on ITCH v2 on three more cells whose per-trade delta went negative while per symbol-day stayed positive. **A one-trade-per-session design removes the ambiguity by construction** (SPY-IM, spec §8.2) — the two denominators are identical, and the check cannot fire because there is nothing for it to catch. **And it fires hardest on a family that LOOSENS a threshold** (H-E2, 2026-09-18): seven of nine cells refused, and the pattern is mechanical in every one — loosen and you get more trades, a better per-trade figure and a worse per-symbol-day figure; tighten and all three reverse. |
| **On a losing book, a total-based reading rewards abstention** | Added 2026-09-17. Every trade in the PIT books loses $10–15 on average, so a rule that removes half of them improves per-symbol-day, survives drop-top-N on the delta and clears a bootstrap on the delta at P = 1.000 — all while moving per trade by +$0.03. Those readings measured *trades less*. A filter on a losing book is judged **per trade, with a margin ($4.26), against an abstention control** — the same number of trades removed at random, 2,000 seeded draws — or it is not judged. `first_entry_skip_RESULT_20260917.md` §3, §6. **Applied the same day to H-B3:** the range gate's +$0.86 sat inside random removal's band, and its per-symbol-day +$3.97 was random removal's median +$3.73. `common/gate_study.py` carries the control for every gate. **On ITCH v2 the same three gates read (0.41) to +0.67 a trade against p95s of +0.67 to +1.40** — the per-trade reading is the only one that moved, and it moved the wrong way. |
| **A rule that ADDS trades is the clean test, and it was still negative** | Added 2026-09-18. Every entry rule tested here for a year *removed* trades, so the abstention caveat above hung over all of them. H-E2's loosened cells add 855 to 3,246 trades each, which no amount of trading less can flatter — and they lose anyway. **A project that only ever tests filters cannot tell a selective rule from an abstaining one; testing in both directions is what makes the reading interpretable.** |
| **A lower failure rate is not a better book** | Added 2026-09-19. The pullback cell (H-P2) cut MCL's next-bar death rate from 12.6% to 2.9% — the mechanism it was built on, confirmed — and per trade went from (8.97) to (9.40); the same on MC5 (37.3% → 16.3%, (8.57) → (10.18)). The trades that die on the next bar are entered on the same extension as the trades that pay for a week of them; a state that avoids the first avoids the second. A failure-rate reduction is a *mechanism* reading and never a *money* reading, and a gate is judged on the money. Four studies (pre-flight, chase gate, delay cost, pullback cell) now agree from four directions. |
| **The marginal trade, not the average** | Added 2026-09-18. When a cell changes the trade count, the per-trade average moves for two reasons at once, and only one of them is selection. What each *added* or *refused* trade is worth — `(tot(cell) − tot(base)) / (n(cell) − n(base))` — separates them, and it is one line of arithmetic off a trades CSV that no study here had ever computed. It reframed the whole entry sweep: the "best" cells improve the average by adding trades worth (7.00) to a book averaging (8.97), which is **dilution, not selection**, and the tightened cells refuse trades worth (7.46) to (9.56), which is why their per-symbol-day figures improve. It is friction-invariant between two books, so it needs no ladder. **Quote it beside the average whenever a rule moves the denominator.** |
| **Multiplicity is counted by FAMILY, not column** | Added 2026-09-16. ORB's grid is ninety cells and four independent choices; a claim made from the grid carries four. |
| **Paired-by-symbol bootstrap** | 10,000 resamples of symbols, zero-filled over the full universe. **And the symbol-CLUSTER bootstrap is criterion 2** (`REGISTERED_breadth.md`): symbols drawn with replacement, every trade of a drawn symbol travelling with it, total > 0 in ≥ 95% of 2,000 resamples. One condition — a second one was withdrawn before use because it could not fail independently of the first. **On a single-instrument study the cluster is the CALENDAR MONTH**, because volatility clusters and resampling sessions independently treats a volatile fortnight as twenty independent observations. |
| **Temporal holdout** | Split the dates, require the effect in **both** halves. **It cannot detect a bad cost model; it certifies one.** |
| **An empty half is not a sign flip** | A bucket with no trades has a spread of exactly 0.0, which fails the both-halves test for the same reason a genuine reversal does. |
| **The sample is SESSIONS, not trades** | Trades inside one session share a market. The regime run showed 9 / 9 / 53 trades from **1 / 2 / 11 sessions**. **And the session median closed the time-of-day question** — 07:45's +$20.98/trade on the stale book was 131 sessions with a median of (19.83) on the PIT book. **A seven-session extension printed PASSES for H-B1 on 59 trades; it is not a reading.** |
| **The leak cut, both halves of it** | Rate *and* quality. |
| **Boundary check on any grid** | An optimum on the edge of the box is being arbitraged, not fitted. **And say where it cannot apply:** a two-value family is all boundary, an unordered family has none. **And say when it need not run at all:** a boundary surface is a refusal check for a *passing* cell, so over a cell that read NOTHING it produces nine numbers and no information (SPY-IM, 2026-09-18). **Scored rather than decorative is what makes it bite** (H-E2, 2026-09-18): both swept families put their best cell at the edge and therefore read UNDECIDED — BOUNDARY *regardless of their numbers*, which the registration said before the numbers existed. |
| **Hold the confound fixed** | Compare against the baseline *at the same setting of everything else*. **A re-basing holds everything but the universe file and the bars:** the regime labels for Part A come from the same BASIC daily archive on both tapes, so the only thing that moves between the two readings is the books. **And a sweep holds everything but ONE constant** — V9 dropped MACD-above-zero and the 3× surge together, collapsed 81%, and left nobody able to say which did it; H-E2 separated them, with a test asserting no family moves two constants. |
| **Block split before headline** | PRE / RTH / POST separately. |
| **One variable at a time** | And check for interaction: apex and the trail are substitutes. |
| **Coverage in the same pass as the P/L** | Bars loaded, first/last timestamp, missing intervals, open-position flag. |
| **Control the tool** | **Measure on a second source before stating a conclusion, not after.** |
| **A control that proves the harness can FIND an effect, beside the one that proves it cannot invent one** | Added 2026-09-18. H0 shows a harness cannot manufacture an edge from random signs. It says nothing about whether the harness could detect a real one — **a pipeline that measures nothing passes H0 perfectly.** So a study of a *published* mechanism carries a second control: the same code, unchanged, over the window the effect was documented in, with a pass band registered before the run. SPY-IM's H-R read +5.41%/yr against a registered 3–12% band on the paper's own 2005–2013 sample, and that is the only reason its flat 2015+ reading is interpretable rather than merely negative. Registered as **reported and never scored**: it sits *inside* the source's sample, so it is replication, not out-of-sample support, and it can never be promoted or quoted as an edge. `REGISTERED_spy_intraday_data.md` amendment K. **TSMOM should carry one.** |
| **A check that cannot tell a real absence from an explained one produces three alarms where there is one defect** | Added 2026-09-18. SPY-IM's gap check counted calendar days and flagged three holes over 5,694 sessions. Two were the market being **shut** — President Ford's national day of mourning and Hurricane Sandy — and one was real. The cost of the false two is not the noise, it is that the real one stops being read. The check now names the weekdays actually missing and tests them against the exchange calendar (federal holidays *as the NYSE keeps them* — it trades Columbus Day and Veterans Day and closes Good Friday, which is not federal at all — plus five unscheduled closures), and a test asserts the two traded days are **not** treated as closed, because explaining away a real hole is the same defect pointed the other way. |
| **Agreement between two different trade sets is not replication** | EQUS.MINI and XNAS.BASIC agree within $0.75 while sharing **16.4% of their trades**. That is arithmetic. |
| **Internal consistency is not validation** | Added 2026-09-12. `screen_sim`'s gate was its fast path against `screen_at` — 0 disagreements — which verifies the implementation against **itself**. It had never been compared to what TradingView actually surfaced. **Measured 2026-09-17/18: 61 of 63 live names on both tapes over eight sessions, with the reason for the other 22 named (the feed's 04:00 carry-over) rather than scored** (`screen_validate_itch_RESULT_20260917.md`). |
| **An exclusion rule is written blind to the outcome it protects** | Added 2026-09-17. The carry-over rule in `screen_validate` removes a live name by its tier at 09:29 and its presence on the previous list — never by whether the simulation found it — and prints what it cost (4 of 22 removed names the simulation had). A rule that consults the result it is cleaning is the result. |
| **Read the rule back as a measurement** | Cameron's breakeven stop was argued to convert losses into scratches, and **scratch% did not move at all**. **Registered as a requirement rather than a courtesy** (H-E2 §5, 2026-09-18): every cell claiming to "enter earlier" had to print the median five-minute return at entry, and a cell that did not lower it may not be *called* entering earlier whatever its P&L says. That is what made the volume family's 0.23pp a fact rather than a puzzle, and it refuted the study's own primary hypothesis in the process. |
| **A comparator with a free parameter is SOLVED against a constraint, never chosen** | Added 2026-09-18. H-S6 had to compare the give-back cap against a flat daily stop, and a flat stop has a threshold the give-back does not — so comparing them at any chosen `$STOP` would have been a search wearing a comparison's clothes. The threshold was instead solved, per cell, to remove **the same number of trades the incumbent removed** (matched to within three trades of hundreds). Both rules then spend the same abstention budget and the only thing that differs is which trades they spend it on. The count comes from the incumbent's behaviour, never from either rule's P/L, so no comparator is ever selected for performing well. The same logic as H-S4's matched-count control, one level up. |
| **The most quotable number in a report is usually the one that was fenced off before the run** | Added 2026-09-18. H-S6 printed three fixed stops as reported-and-never-scored so the trade-off between threshold and removal count would be visible, and FLAT-40 on MC5 came back at **+$3.93 a trade** — the largest per-trade improvement anywhere in this project's gate work, and close to the $4.26 margin. It removes **71% of the book**, has no abstention control, and is not comparable to anything else in the report, because a per-trade delta scales with the share removed. It is quotable only because §3 of the registration barred it in advance, before anyone had seen it. **Print the tempting cells, and fence them in the registration rather than in the result.** |
| **Measure the tool against the bars it traded** | `entry_latency` compared 5-minute fills with 1-minute bars and reported fill positions of 7.85× the range. |
| **Parity across strategies, and between live and backtest** | Whatever a backtest enforces, the live path must. **And the parity test is the fix:** the live session gate is tested against `mcl.in_session_mask`, the engine's own construction, bar for bar. |
| **State the bar before the result** | Go/no-go criteria in the spec before any code. |
| **An n = 1 measurement is not a constant** | Two documented "facts" came from single sessions and were both wrong, one sign-reversed. **Six sessions is not much better:** the live first-entry table (37 vs 97 trades) did not replicate on 6,170 symbol-days. |
| **A comparison between two outcome-dependent quantities is circular** | Discriminate on features knowable *at* entry. **"Later entries" is outcome-dependent:** a second entry exists only because the name kept signalling. |
| **A pre-flight that measures separation is not allowed to price it** | Added 2026-09-18. `running_up_preflight` asks only whether a feature separates dying trades from surviving ones, and a test asserts that **no money and no scoring vocabulary reaches its report** — because a descriptive pass that quietly prints a P&L column becomes a search over thresholds the moment anyone reads it. The rule it would have justified is registered separately or not at all. It is also what let the pass be believed when it came back **inverted**: there was no cell to be tempted by. |
| **A control whose output is indistinguishable from the failure it detects is not a control** | The recurring shape. Instances: an inert halves control; an entry map keyed on the wrong type that matched **none of 71 real trades**; a verdict that blamed the exits while the paired trades ended identically; a **floor that never fires** producing the same trade list as a strategy that never enters early; a **variant that equals its base** printing a 0.00 delta that renders as NOT MATERIAL; **R with no losers** reading 0.00 against a requirement that also reads 0.00; **a cross-cache check reading the wrong bar** and printing a $4.96 disagreement with nothing behind it; **a swept cell that silently equals its base** because the published config was merged over the swept value (H-E2, caught by a test that asserts the merge order). |
| **A second condition that cannot fail independently of the first is not a second condition** | Added 2026-09-16. Breadth's condition (b) was (a) at a stricter level; the grid's per-cell denominator check was the same net over two divisors. Both found by trying to write a failing case and being unable to. |
| **A sentinel that is also a legal value is not a sentinel** | Added 2026-09-16. `(0, 0)` is midnight ET. |
| **A yes/no verdict over a quantity that is actually a distribution** | Added 2026-09-16. The freshness probe reported the mode ("the trim is correct") over rows in which one sample in eleven was the expensive case. |
| **A hash cited in prose is a second source of truth that goes stale in silence** | Added 2026-09-16. Assert git ancestry instead. **And an item NUMBER cited between chats is the same failure with a smaller blast radius** (2026-09-18): `REGISTERED_giveback_cap` and `REGISTERED_stop_compare` both point at "§7 item 11, the daily loss stop", §7 has been rewritten three times since, item 11 is now Cameron's breakeven stop, and the daily loss stop had fallen out of the list entirely. Name the rule; do not number it. |
| **A check placed one step short of the thing it protects** | Added 2026-09-16. A clock inside the session is not a bar inside the session; constants that match are not values that reach the call. |
| **A decision made on a snapshot the counterparty has not confirmed** | Added 2026-09-16. The MEDS ghost: 850+ SELLs into a flat account over 3.5 hours because fills were read in the instant between a cancel being sent and IB acting on it. |
| **Signal-ordinal is not book-ordinal** | Added 2026-09-17. Deleting a trade from a finished book and not taking it live are different rules: with the position never opened, bars the baseline was in a trade for become live signals (417 such entries for MCL, 1,360 for MC5). A study reads the form that would be deployed and prints the other beside it. |
| **A time-of-day pattern is a tape question before it is a strategy question** | Added 2026-09-17. The 08:00 hour read (18.45) for MCL on XNAS.BASIC and (9.71) on XNAS.ITCH, same universe, same code; the "pattern" was late-reported prints. Before an hour-of-day or before/after-a-date finding is read as market behaviour, the same hour is read on a second tape. **A diagnosis of the tape is registered with a shape it must produce** (`REGISTERED_screen_itch` §2.1: identical tapes until 08:00 before the cut) **and stops the work if it does not.** |
| **A capture ratio is a function of the clock, not a constant** | Added 2026-09-17. Applying one 09:30 figure to a 05:00 window where the two tapes were the same tape made 2,902 names "knowable" earlier by construction. A scaled absolute threshold carries the time and regime its scale was measured at. **Measured properly (v2), the early names it "found" were mostly real: BASIC's daily 0.552 had been too tight before 08:00 by ~2.3×.** |
| **A freshness rule must ask whether the number could have moved** | Added 2026-09-17. A cumulative statistic republished on change carries an old timestamp on every quiet name and is still exactly right. Row age failed the registered bar on every thin name at 05:00; "stale while the exchange printed" was 0.00%. The rule was restated pre-run, and the mistake is recorded rather than the bar quietly met. |
| **A published count belongs to a universe file, not to a strategy** | Added 2026-09-17. The population check compared every run against the BASIC 3,955, so a seven-session extension and an ITCH run both printed *** DOES NOT MATCH *** against a number that was never theirs. The count is looked up by the file that was run (BASIC 3,955; ITCH p50 3,960; ITCH v2 3,908), and a file with no published count says so. A study that reads another study's CSV refuses one written on a different tape or universe, or a readings file carrying sessions the trades never ran. |
| **A promotion made after seeing a measurement that favours it cannot be un-rung** | Added 2026-09-18. SPY-IM's conditional cell was better conditioned on every measured number — friction 48.2% of gross against 74.6%, twice the margin — and both the source paper and the skeptical reading point at it. It was **not** promoted to primary, because what had been looked at by then was volatility, which is the weakest possible form of the objection and still the objection: a year later, "promoted because the literature said so" and "promoted after the data made it look better" are not distinguishable from the record. Gates decide thin cases; a pre-emptive promotion forecloses them. |

**Universal caveats:**

- **Selection bias.** `bar_cache` IS Ben's own trade universe — anything measured
  there is in-sample.
- **The screener is simulated (2026-09-11) and validated against the live
  screen (2026-09-17/18): 61 of 63 live names over eight sessions, on both
  tapes.** What the simulation does not carry is the live feed's own
  behaviour — a 900-second delay on every name (measured 2026-09-18; gone
  once the feed is signed in) and the previous session's names at the first
  poll. **The delay is priced (H-D1, 2026-09-19): +$0.09 a trade on MCL,
  ($1.03) on MC5, no movement in shape** — so a point-in-time figure is a
  fair description of what the live trader could act on, to within that.
- **The stage-2-survivor universe has manufactured a positive edge before**
  (H0: +$4.72 → −$15.78 PIT). Any figure on `screen_pairs_consolidated.json` is
  an upper bound until the same code has run on the point-in-time universe —
  `screen_pairs_pit_itch_v2.json` from 2026-09-17; `screen_pairs_pit_itch_p50.json`
  (v1) and `screen_pairs_pit.json` (BASIC) are superseded.
- **IB split-adjusted prices.** Ratio rules survive; absolute price and volume
  floors do not.
- **Backtests model no halts, and for the pre-market books they need not:**
  two trades in 10,370 had a halt begin inside them (`halt_census_RESULT`).
  **For ORB they do:** 17% of universe symbol-days are paused after the open,
  2.7 pauses per session in 09:30–10:00.
- **Backtests model neither the concurrency cap nor IBKR's refusals.** Live,
  **29% of buy attempts** were rejected by the cap (46 of 159) and 2 of 8
  watchlist names were refused outright as closing-only. Every backtest takes
  every signal. **H-B2 cannot be run until this is modelled.**
- **Source videos are hypothesis generators, not evidence.** **And a live
  scanner is one too** — Day Trade Dash's Running Up alert generated a
  hypothesis that the pre-flight then answered in the opposite direction.
- **A peer-reviewed mechanism is a better prior and not a result.** SPY-IM had
  publication, independent replication and a stated economic mechanism, and
  still read NOTHING in the era it would be traded. What the literature bought
  was a cheap, decisive test and a control that made the negative
  interpretable — not a higher chance of passing.

---

## 5. Traps and hard-won facts

**Universe and data**

- **A strategy without the price band trades the adjustment factor.** VW9 took
  positions in PFSA at $4,152/share.
- **Exchange TEST symbols are in the tape.** Excluded by `screen.is_test_symbol()`.
- **An `ALL_SYMBOLS` pull embeds no symbol mapping**, and `to_df(map_symbols=True)`
  returns `symbol=None` on every row **without failing**.
- **A daily bar is not known until 20:00.** Any screen rule using today's volume
  or range is look-ahead.
- **`ts_event` is the interval START.** A bar is not knowable until it CLOSES.
  Screening on `index <= t` reads up to 59 seconds of the future on every symbol
  at every cadence tick.
- **A trade's timestamp on the tape is its REPORT time.** Until 2026-03-30 the
  TRF opened at 08:00 (FINRA Notice 26-07, Nasdaq DTN 2026-4), so an
  off-exchange trade executed at 05:12 printed at 08:00-something on
  XNAS.BASIC with its 05:12 price. `trades` schema: `ts_event == ts_recv`, no
  condition flags; only `publisher_id` (82/83 = TRF) separates them. Exchange
  publishers 81/88/89 = XNAS.ITCH.
- **A session's shape is not constant across eras.** Before 2009 SPY closed at
  **16:15**, so IB returns **14** thirty-minute RTH bars per session against 13
  from 2011 (2009 is the transition year at 13.19 bars). It moves none of the
  four prices the intraday-momentum rule needs — the 15:30 bar still runs
  15:30–16:00 — but **a full-day test written as an equality on the bar grid
  silently drops every pre-2009 session**, and a session's closing price must be
  read from the 15:30 bar (the 16:00 price), never the last bar (16:15), which
  would otherwise enter the next session's overnight return several thousand
  times. Measured, not assumed.
- **A documented API limit is a claim, not a measurement.** IB's table gives max
  durations of 1 M / 1 W / 1 D for 30-minute / 5-minute / 1-minute bars.
  Measured on this account 2026-09-18: **1 Y / 3 M / 1 M**, and 1-minute history
  reaches **2004**, not the ~6 months assumed. The 1-minute row alone turned a
  ten-hour pull into a one-hour one and retired a registered 5-minute proxy as
  unnecessary. **But the measurement was taken on a recent window**, and IB
  answers a too-long request for *old* data with a truncated one rather than an
  error — so chunks overlap and every chunk's returned span is checked against
  the step it was meant to cover.
- **A report must read its own inputs, not assert them.** The ORB pre-flight
  printed its EQUS.MINI caveat verbatim over XNAS.BASIC numbers, and two tests
  *asserted* that paragraph, so the suite pinned the bug. **And the ORB grid then
  ran on EQUS.MINI without saying so** — same lesson, one module later.
- **`screen_pairs.json` is 12,128 symbol-days; `screen_pairs_consolidated.json`
  is the 22,882 the spec names; `screen_pairs_pit.json` is the 6,170 point-in-time
  set on XNAS.BASIC; `screen_pairs_pit_itch_p50.json` is the 6,564 on XNAS.ITCH
  (v1, p10 8,907 / p90 5,555 beside it, sensitivity only); `screen_pairs_pit_itch_v2.json`
  is the 6,411 on XNAS.ITCH with the measured capture ladder — **the deciding
  file**; `screen_pairs_pit_ext.json` is the 52 symbol-days of 2026-09-08..09-16,
  BASIC, screened after the archive extension (the file A1/A3 read);
  `screen_pairs_pit_ext2.json` is its re-run through 09-17 for the validation
  (67), and `screen_pairs_pit_itch_ext.json` is the same eight sessions on
  ITCH (76).** Nine files, eight universes. Count before running.
- **A cumulative statistic is republished on change.** `CLEARED_VOLUME`'s row
  age is time since the last trade, not staleness; a freshness rule on row age
  fails on every thin name at 05:00 while the number is exactly right. Stale
  *while trading* is the test (0.00% on 17,929 symbol-days).
- **A mid-month re-pull overwrote a whole-month daily chunk** (the ORB chat's
  extension, `archive_defect_daily_chunk_start_20260917.md`): 2026-09-01..04
  daily bars vanished, `regular_close.json` was regenerated, and v2 of the
  screen ran with three sessions swapped against v1. **Repaired 2026-09-18** by
  re-pulling the September chunk from the 1st; v2's swapped sessions stand as
  published.
- **A slice pulled the same day can arrive without its symbology sidecar, and
  a day is not on every tape at once.** Databento resolves a day's instrument
  ids with a lag; `databento_universe` prints `SYMBOLOGY FAILED` and keeps the
  bars, every reader then refuses the file (`read_dbn` requires symbols), and
  `regular_close --emit` stops on it without writing. `--resymbolize` fills
  the sidecars later without re-buying anything. XNAS.ITCH minutes for a day
  were not published at all the evening of that day, and the prior close is
  read through the **daily** archive, so a new session needs its daily bar
  too. The 09-17 add took three passes for those three reasons (2026-09-18).
- **The writer and the reader must agree on the layout.** A correct 515 MB pull
  produced a cache of zero files.
- **`load_sessions` returns a THREE-DAY frame** for warm-up. An unbounded
  detector fired on the warm-up days and reported signals a median of **245 bars
  "earlier"**.
- **`.asi8` returns MICROSECONDS on a `datetime64[us]` index** while
  `Timestamp.value` is nanoseconds — a 1000× mismatch that made an entire
  session visible at 04:01 and produced a plausible-looking universe.
- **Two modules must not share an output path.** `pit_strategy --strategy h0`
  defaulted to `var/reports/pit_h0.txt`, exactly where `common.pit_h0` writes,
  and overwrote it.
- **A duplicated timestamp breaks `get_loc`.** The 2025-06-09 slice carries
  duplicate `ts_event` rows; `index.get_loc(ts)` returns a slice and the next
  comparison raises. Three modules hit it in one day. Locate by
  `np.flatnonzero(index == ts)`, never by `get_loc`.
- **RVOL is not computable from `bar_cache_*`**: 2 of 27,777 symbol-days carry
  all ten prior sessions. The 09:30 RTH screen is simulated on three of its four
  rules, and the fourth is the one the literature says carries the edge.
- **`entry_time` in `screened/backtest_trades_mcl.csv` is UTC.** Read as ET it
  moved every time-of-day conclusion four hours and still looked coherent. The
  PIT trade CSV names its columns `entry_et` and its meta file says `ET`, and
  `time_of_day` refuses anything else. **The SPY caches name their index
  `ts_et` for the same reason.** **And a feature computed at a timestamp
  refuses a naive one outright** (`running_up.features`), because pandas'
  own error for a tz mismatch names neither the argument nor the fix.
- **The session after an early close still has a prior close.** The market shuts
  at 13:00 ET about nine times a year; reading the close off a fixed
  end-of-day bar NaNs the *next* session's overnight return and silently drops
  the day after Thanksgiving, Christmas Eve and July 3rd every year — precisely
  the unusual sessions an exclusion rule is supposed to preserve. A session with
  bars missing from its **middle** is a different thing and its successor is
  marked rather than computed; **contiguity separates them, not bar count.**
- **Auto-generated transcripts render dollar prices as clock times.** `6:20`,
  `8:81`, `9:50` are prices. Any harvest of `H:MM` from a transcript corpus
  needs a price filter and a manual audit.
- **A partial run must not write the deciding file.** `screen_sim --after`
  refuses `--out var/state/screen_pairs_pit.json`; the file every point-in-time
  result was decided on is regenerated only on purpose, whole, under a
  registration.
- **A study that reads another study's output inherits its tape.** The trades
  CSV, the universe file and the readings file `luck_vs_edge` reads must be one
  run's; a BASIC readings file on ITCH trades labels every session with a
  watchlist that was never screened. The module refuses the mismatch by the
  meta file's `dataset` and `pairs` and by stray session dates.

**Fill modelling**

- **You cannot sell AT a level when the bar OPENS below it.** `gap_fills=True`.
- **The entry bar's high happened before the close you bought at.**
- Together these took MC5 from +$20,156 to −$400 and MCL from +$1,567 to +$161
  **with identical trades**.
- **`Trade.entry_time` is a STRING, not a Timestamp.**
- **A gapped target does NOT fill better than the level.** ORB takes the gap on
  a stop (worse) and the level on a target (not better); modelling both the same
  way lets one of them flatter you.
- **The entry bar's own high cannot raise the trail during that bar.** The bar
  is post-entry and its high belongs in the peak — from the next bar.

**Execution cost** — `execution_cost_measured.md`, 18,552 fills

- **Median spread: PRE 83 bps, RTH 60 bps, POST 87 bps.**
- **Crossing costs $1.00 per 100-share round trip.**
- **There is no buy/sell asymmetry.** The documented one came from ONE session.
- **THE TAPE MATTERS MORE THAN THE METHOD.**
- **Commissions are per ORDER.** Fixed/Tiered crossover at exactly **150 shares**.
- **`window_close` is the most expensive exit of all** — −$0.0700/share median
  against the trail's −$0.0225. Nothing has ever priced it separately.
- **The exit MECHANIC decides the friction.** Measured live 2026-09-11:
  trailing-stop sells fill a median **−$0.0563/share** worse than reference;
  `gradient_reversal` sells fill at **$0.0000**. A signal exit fills at the
  reference; a stop fills through it.
- **A fixed per-order minimum is a small-account tax and a venue-dependent
  parameter.** 13 SPY shares carry $0.046 of marginal commission and IBKR's
  $0.35 minimum charges 7.6× that; it stops binding at 100 shares. It is worth
  a reported column and never a verdict — **and it cannot rescue a negative
  gross**, which is why it changed nothing for SPY-IM, MCL, MC5 or VW9.
- **A per-trade DELTA between two books is friction-invariant.** A flat
  per-round-trip cost cancels out of a difference of means, which is why the $5
  floor's delta is identical at all three levels and why the marginal trade
  needs no ladder. A per-*symbol-day* delta is not, because the trade counts
  differ.

**IB / live**

- Pacing is ~60 historical requests / 10 min, **and qualification is paced too**.
  IB signals throttling by returning **empty lists, not errors**.
- **A paced pull and a live session share one account-wide request budget**, so
  the cost of a breach lands on the *trader* — going quietly blind mid-session —
  not on the puller, which sees something it can mistake for absent data. Check
  `var/state/session.lock` before any multi-hundred-request pull; MCL and MC5
  hold it 04:00–09:30 ET.
- `"N D"` counts **trading sessions**, endpoint **exclusive**.
- Outside RTH, IBKR takes **Day Limit orders only** — every stop is
  software-managed.
- **Read-Only API being ticked cannot be detected by a dry run.**
- **IBKR refuses some screened names outright**, closing-only status, ~25% of a
  day's watchlist.
- **The IBKR MCP connector and IB Gateway are mutually exclusive** — one session
  per login. IB data during a session comes through Gateway on a spare client id.
  **The MCP connector's `get_price_history` errors while its other calls answer
  when Gateway holds the login.**
- **IB includes the forming minute in a history response — usually.** 10 of 11
  on BNC. The eleventh ended with a closed bar because nothing had printed; the
  old unconditional trim threw it away. The trim now asks the clock.
- **At 04:00:10 the frame still ends with yesterday's 19:59 bar.** A clock inside
  the session is not a bar inside the session.
- **A cancel is a request, not an outcome.** The fill can land between the
  read and the cancel; read `trade.fills` only after `isDone()`.
- **IB reports the trader's own cancel as `Cancelled` plus `Error 202: Order
  Canceled - reason:` with nothing after the colon** — the same shape as a
  refusal. The fakes that left the status at `Submitted` after a cancel are
  why this reached production.
- **The live exit fires inside a bar; that bar is the engine's exit bar.** A
  re-entry rule on the bar's close admits it; the rule is on the bar's open.
- **A quote can be 34% from the signal close by the time the order goes out**
  (RETO, 09-17, four minutes after the bar). The engine never pays that
  price; the guard keeps live inside what the engine modelled.
- **A BUY whose cancel IB never confirms can leave shares with no position on
  the book** — the reverse ghost. `_adopt_unknown_entry` reads IB and adopts.
- **TradingView's scanner returns yesterday's screen at 04:00.** Its
  `premarket_*` columns hold the previous session's values until today's
  prints arrive; `tv_feed`'s first poll arms them and the trader probes them
  (blocked stamps at 04:00:05, 04:00:06, 04:00:08, 04:00:26 on four
  sessions). The session-scoped ranker (2026-09-12) cannot stop it, because
  the names arrive fresh. A name is not on today's screen until its
  pre-market volume has changed between two polls.
- **The unauthenticated scanner endpoint is 900 seconds behind the tape, and
  it says so.** Every name IBKR refused was refused 12–27 minutes (median
  +15.6, 10 of 10) after the simulation first qualified it, on both tapes; the
  probe then read TradingView's own `update_mode` column:
  `delayed_streaming_900` anonymously, `streaming` with `sessionid` +
  `sessionid_sign` (2026-09-18). Both cookies or neither — `sessionid` alone is
  served anonymously with no error. **Set them with `$env:… = op read …` in the
  feed's window, not `setx`:** `tv_feed` reads them raw and would send an
  `op://` reference as the cookie. An expired cookie reverts silently to
  delayed; only the startup `update_mode` check tells the two apart.
- **`premarket_time` dates the pre-market row.** On the stale first-poll row it
  reads the previous session's 04:00 ET; once today's prints arrive it reads
  today's. `update_time`, `last_bar_update_time` and `time` all date the
  previous regular session and are useless for the gate. Sampled one row per
  run so far; confirm per row before the H-F1 gate is rewritten on it.
- **`tv_probe` writes one CSV per run and overwrites it.** The 35-minute run's
  CSV was lost to a 3-minute repeat before it was copied. Copy before
  re-running.

**Sizing**

- **Capital-based sizing can flip a strategy's sign.**

**Strategy logic**

- **A hard exit evaluated on the fill bar produces same-bar round trips.**
- **"Previous candle high" is ambiguous and the two readings are opposite trades.**
- **A test on a PARAMETER is not a test on the DATA.** Trade **count** catches it.
- **A looser exit rule can only remove exits.**
- **A breakeven stop is not risk reduction for a winner.** Once a trade is up
  more than ~5.3%, breakeven sits *below* a 5% trail.
- **Confirmation is the cost.** MCL-PB paid a median +2.86% to be confirmed;
  ORB's retest arms lose to `none` at the structure stop. **And H-E2 priced the
  other side of it: removing confirmation buys earlier entries that lose $7 to
  $10 each.** Confirmation is expensive and the absence of it is not cheaper.
- **The structure stop anchors on the last bar that had CLOSED when the order
  filled.** Uniform across modes; it removes a look-ahead a resting order would
  otherwise carry.
- **A leg is not a trade.** `r_3_trim` books two legs per position, so its
  per-trade column is per-leg. The comparison-level refusal caught it.
- **A filter on a losing book cannot help by abstaining.** Fewer trades means
  fewer losses on any book that loses per trade; only a per-trade improvement
  against random removal is selection. Three gates in one day read exactly
  random removal's number, the one with a mechanism closest. **Re-based on the
  tape of record, the same three read negative per trade in three of six
  cells** — the trades refused were slightly better than the trades kept.
- **The momentum a scanner would select on is the momentum that kills these
  trades.** MCL's dying trades were entered after a median +11.43% five-minute
  move and its survivors after +4.90% (AUC 0.751 against a 0.526 null), so a
  Running Up gate keeps more dying trades than surviving ones at every
  threshold. MC5's version of the same measurement is **U-shaped** — its bottom
  decile is also bad — so "don't buy while it is dropping" is a real but weak
  floor, and the dominant structure is a ceiling. **An alert built to find
  momentum cannot fix a book whose problem is buying momentum.**
- **Waiting for the dip and buying the breakout after it are different rules,
  and only the second was tested.** MCL-PB failed six times buying the break of
  the peak, at a median +2.86% premium. The pullback state itself — near the
  session high AND not extended — reads 3.3% one-bar on MCL against a 12.6%
  base and has never been run as a rule. Do not quote MCL-PB's failure as
  evidence against pullback entry.
- **The one-bar trades are the ceiling on MC5.** Its 2,412 next-bar deaths lose
  (31.95) each, 139% of net; the 4,050 that survive the first bar are +$5.36 at
  $4.26 and **+$0.70 at $8.92**. A perfect one-bar filter, which nothing here
  has come close to, leaves seventy cents a trade at honest friction — so
  "remove the instant deaths" is a bounded programme, not an open one.
- **A trailing percentile is computed over ALL knowable history, then restricted
  to the scored window — not computed inside it.** Point-in-time means "using
  only what was knowable then", and last year's values were knowable. Computing
  the trailing window inside the trimmed sample leaves its first year ungated
  for no reason; on SPY-IM that cost the conditional cell 113 trades, and it was
  caught by two trade counts disagreeing rather than by reading the code.
- **A regime that separates trades on one universe need not on another.** The
  survivor books' monotone hot/mixed/cold ordering (p = 0.024) is absent on the
  point-in-time books; the universe, the floor and the calendar all changed and
  the run cannot say which removed it. Quote a regime effect with its universe.
- **A hot day is more trades, not better trades, for a rule that fires on
  signals.** MCL takes 8.8 trades on a hot session and 5.5 on a cold one at the
  same per-trade loss, so it loses more when the market is best. Cameron's 16×
  is a size and selection response; a signal rule has neither.
- **A floor from the market does not transfer to the watchlist.** `MIN_NAMES`
  = 5 movers is a quiet day market-wide and a typical morning on a
  point-in-time list with a median of four names by 07:00; carried across
  unchanged it vetoed two sessions in three. Look at the distribution of the
  thing a threshold will cut before registering the threshold.
- **The point-in-time watchlist is deeper at signal time than at 04:30.** A
  median of one name by 04:30 became four to fifteen visible names at most
  MCL signals; a registration that assumed a thin list was wrong on that
  point, and the binding count printed beside the verdict is what caught it.
- **A fixed trader loses what the defective one lost.** Over 09-09..09-16 the
  backtest without the three session-open and ghost defects loses (783) where
  the live trader lost (762). A defect that is real and fixed is not thereby
  the cause of the loss; the loss was the strategies, and the fix is worth
  what it is worth (VEEA at 04:00 on 09-16: +$72.74 across both books).
- **A published effect can be real, replicable, and gone.** SPY-IM reproduces at
  +5.41%/yr on the paper's own 2005–2013 sample and is negative gross from 2016
  on SPY, QQQ and IWM alike. Peer review and independent replication say the
  effect existed; they say nothing about whether it still pays.
- **Entering earlier within the MOVE and earlier within the BAR are different
  axes.** H-E2 answered the first and cannot speak to the second; a 10-second
  trigger under a 1-minute setup needs sub-minute data this project does not
  own, and that has to be priced before it is bought.

**Data plumbing**

- **De-duplicate on an ID, never on field values.** Deleted **1,314 real
  executions** and moved the P/L by $3,360.
- **Flex `DateTime` is in the account's report timezone.**
- **`create_all` never ALTERs an existing table.**
- **A cache root must be gitignored before it is written.** And `var/` not
  `var/` with a trailing slash — the slash is directory-only, and a junction
  reads as a file, which left the production tree permanently DIRTY.
- **`git bundle create` cannot write into `/mnt/user-data/outputs/`** (rclone
  FUSE). Create in `/root/`, copy across.
- **A test that pipes through `| tail -1 &&` masks its exit code.** A commit
  went in with a failing test that way on 2026-09-16. Check `$PIPESTATUS`.
- **Ben's tip can be pulled INTO the cloud clone before a bundle is cut.**
  `git bundle create` in `D:\Trading` from the Cowork shell, stage the file,
  fetch it in the cloud, fast-forward, then build. The bundle's prerequisite
  is then Ben's actual HEAD. **Run git there with `--no-optional-locks`** —
  a plain `git status` from the Cowork shell writes `.git/index.lock` and
  cannot delete it, and every git command on Ben's side then fails until he
  removes the file by hand (2026-09-17).
- **File times seen from the Cowork shell are UTC.** A report "generated
  2026-09-18 09:42 AEST" lists as `Sep 17 23:42`, which is 19:42 ET on the
  17th — after the close, not mid-morning. A wrong reading of that clock put a
  wrong reason in a result doc for an hour (2026-09-17).
- **Python's `hash()` on a str is SALTED PER PROCESS.** A null control seeded
  with `hash(key)` differs in every worker and on every run, so the one column
  that exists to say "this is what no signal looks like" would have been
  irreproducible — and nothing about the output would have looked wrong.
  `zlib.crc32(key.encode())` instead, and the expected value of the control is
  pinned in a test (2026-09-18).
- **A mutation harness that dies between mutating and restoring leaves the
  mutation on disk.** A 120-second Bash timeout killed one mid-run and left a
  hardcoded `vol_multiple = 3.0` in `mcl.signals`; it surfaced only because an
  unrelated monkeypatch test failed oddly. Restore in a `finally` **and** via
  `atexit`, and give the runner a timeout longer than the harness needs.
- **A merge of two config dicts can make a swept cell a silent duplicate of its
  base.** `engine("mcl")` returns the published LIVE config, which already
  contains `require_macd_pos=True`; merged over the swept value it would have
  produced a macd-off cell identical to the base, with a plausible-looking
  table and no error. The swept value goes LAST — `{**extra, **kw}` — and a
  test pins the order.
- **A test fake whose signature has drifted from the real function hides the
  parameter it was meant to exercise.** Four fakes took `(df5)` or a fixed
  keyword while the real `signals()` had grown one. **Fix the fake, never the
  call** — this is the same class of defect that let the self-cancel bug reach
  production.
- **NaN is not None and it breaks sorting.** An ad-hoc median over a column
  containing NaN returned sign-flipped garbage (a "median ret_5m" of −7.46%
  against the report's +5.01%). Filter with an explicit `math.isnan` before
  taking a quantile, and when a hand-written script disagrees with a tested
  module, suspect the script.

**Windows / PowerShell**

- **Keep every `.ps1` pure ASCII.**
- `Tee-Object` writes **UTF-16**. Write reports from Python.
- **A terminal can show `(.venv)` while `python` resolves to the system install.**
- **PowerShell does not glob-expand arguments for native commands.**
- **`--strategy mcl mc5` silently drops the second.**
- **ANSI colour must never reach a `.txt`.** `report_io.emit` prints painted and
  writes plain.
- **Ben is not proficient in PowerShell or git.** Send exact copy-paste commands
  with **real paths**, one command per line.
- **Every result is written to a file.** No copy-paste from terminals.
- **A bare `read_text()` is cp1252 on Ben's machine and UTF-8 in the cloud.**
  Same commit, two answers, decided by locale. The encoding guard exists for it.

---

## 6. Doc map

**Start here:** this file.

### Current

| Question | Doc |
|---|---|
| **Would a Running Up momentum scanner tell these strategies which names to enter?** | **`running_up_preflight_RESULT_20260918.md`** — no, and the separation runs the wrong way; the pullback cell is the one exception, and the MC5 one-bar sizing is here. `raw/running_up_scanner_observed_20260918.txt` |
| **Can either strategy enter earlier in the move, and is an earlier entry worth taking?** | **`entry_sweep_RESULT_20260918.md`** — yes and no: the dials work, and every marginal trade loses $7 to $10. `entry_sweep_HOWTO_20260918.md`, `docs/research/REGISTERED_entry_sweep.md` |
| **Does the published intraday-momentum effect still work, and how do we know the harness could tell?** | **`spy_intraday_RESULT_20260918.md`** — NOTHING on both cells, negative gross, and H-R replicating on the paper's own sample. `spy_intraday_data_pass_20260918.md` (the data and the registered stop), `spy_intraday_spec_20260917.md`, `docs/research/REGISTERED_spy_intraday_data.md` (A–M), `spy_intraday_AMENDMENT_A_20260917.md` |
| **Does a $5 entry floor or a 50% session give-back cap help?** | **`session_scenarios_RESULT_20260918.md`** — the floor is nothing; MC5's cap is the first rule here to pass all six of its readings. `session_scenarios_HOWTO_20260917.md`, `docs/research/REGISTERED_price_floor.md`, `docs/research/REGISTERED_giveback_cap.md` |
| **Is the give-back's peak-relative SHAPE what does the work, or would a flat daily stop do it?** | **`stop_compare_RESULT_20260918.md`** — UNDECIDED at three cells, ADDS NOTHING at the fourth; the holdout is spent on neither. `docs/research/REGISTERED_stop_compare.md`, `stop_compare_HOWTO_20260918.md` |
| **Does taking only the pullback state (at the high, not extended) select better entries?** | **`pullback_cell_RESULT_20260919.md`** — no: it selects the low-death-rate cell exactly and loses more per trade; the one-bar death rate closes as a target. `docs/research/REGISTERED_pullback_cell.md` (H-P2) |
| **Did the feed's 15-minute delay shape the live book?** | **`feed_delay_cost_RESULT_20260919.md`** — no: +$0.09 / ($1.03) a trade, win and R unmoved, and the live shape had converged at n = 50. `docs/research/REGISTERED_feed_delay_cost.md` (H-D1) |
| **Is the live feed delayed, and does logging in fix it?** | **`feed_freshness_probe_RESULT_20260918.md`** — `delayed_streaming_900` anonymously, `streaming` signed in; the carry-over watched; `premarket_time` dates the row. `feed_handover_REPLY_20260918.md`, `docs/research/REGISTERED_feed_freshness.md` (H-F1) |
| **Does the simulated screen match the live watchlists?** | **`screen_validate_itch_RESULT_20260917.md`** — 61 of 63 on both tapes over eight sessions; the 04:00 carry-over; the 15-minute clock. `docs/research/REGISTERED_screen_validate_itch.md` |
| **Which tape, and what moved when the screen was rebuilt on it?** | **`screen_itch_v2_RESULT_20260917.md`** (current baselines), `screen_itch_RESULT_20260917.md`, `tape_compare_RESULT_20260917.md`, `tape_spikes_RESULT_20260917.md`, `trf_probe_RESULT_20260917.md`, `handover_tape_switch_20260917.md`, `docs/research/REGISTERED_screen_itch.md`, `docs/research/REGISTERED_screen_itch_v2.md` |
| **How often is the universe halted, and did a halt ever fall inside a trade?** | **`halt_census_RESULT_20260917.md`**, `docs/research/REGISTERED_halt_census.md` |
| **What went wrong in the 09-17 session, and what changed?** | **`live_defects_FIXED_20260917.md`**, `session_review_20260917.md`, `docs/research/REGISTERED_drift_guard.md` |
| **Do the entry gates and the regime readings hold on the tape of record?** | **`bseries_itch_RESULT_20260917.md`** — every verdict stands; the four registrations' PRE-RUN amendments |
| **Does skipping the first entry help, and is there a time of day?** | **`first_entry_skip_RESULT_20260917.md`**, `docs/research/REGISTERED_first_entry_skip.md` — the time-of-day part is withdrawn with the tape; both re-read on ITCH v2 in `bseries_itch_RESULT_20260917.md` |
| **Does ranking names by session range at signal time help?** | **`range_rank_RESULT_20260917.md`**, `docs/research/REGISTERED_range_rank.md` |
| **Does a 07:00 cold-session veto help?** | **`cold_veto_RESULT_20260917.md`**, `docs/research/REGISTERED_cold_veto.md` |
| **Luck or edge — do the books pay on the sessions that pay?** | **`luck_vs_edge_RESULT_20260917.md`**, `docs/research/REGISTERED_luck_vs_edge.md` |
| **Does 09-16 replay green, and do the three fixes explain the live loss?** | **`replay_and_live_gap_RESULT_20260917.md`** — green; no |
| **Where does the MCL chat stand, and what does the feed line look like joined across chats?** | **`handover_mcl_chat_20260918.md`** — close of day 2026-09-18 |
| **What are the open asks from the live-analysis chat?** | **`handover_luck_vs_edge_and_entry_quality_20260917.md`** |
| **What did ORB do, and why is it not shipped? Where does the ORB chat start?** | **`orb_first_results.md`**, **`handover_orb_build_20260917.md`** |
| **What was the MEDS ghost, and what stops it recurring?** | **`ghost_position_FIXED_20260916.md`** |
| **What is the screen's honest universe, and was the +$4.72 real?** | **`screen_sim_result_20260911.md`**, **`pit_h0_result_20260911.md`** (BASIC; superseded figures) |
| **What are MCL and MC5 worth without the look-ahead?** | **`screen_itch_v2_RESULT_20260917.md`** (current), `screen_itch_RESULT_20260917.md` (v1), `pit_strategy_result_20260911.md` (BASIC) |
| **H0's own leak split, the floor-delta test, MFE-after-exit** | **`pit_three_results_20260911.md`** |
| **Does the intraday floor move a rejected mechanic's delta?** | **`floor_delta_result_20260911.md`** |
| **What did live trading say, and where does it disagree?** | **`mcl_session_20260911_review.md`**, `session_review_20260914_15.md`, `green_day_attribution_20260916.md` |
| **What went wrong at the session open, and how is it pinned?** | **`session_open_defects_FIXED_20260916.md`**, `bar_trim_RESULT_20260916.md` |
| **What replaced criterion 2, and does MC5 pass it?** | **`breadth_RESULT_20260916.md`**, `docs/research/REGISTERED_breadth.md` |
| **The pullback-breakout line, v1–v6** | `pullback_break_RESULT_20260916.md` … `pullback_break_v6_RESULT_20260916.md` |
| **Why does a `§` break a test on Windows?** | `encoding_guard_20260916.md` |
| **Is anything profitable, and is friction the reason?** | **`friction_reconciliation_20260911.md`** |
| **What does a stop actually cost to fill?** | **`stop_fill_20260911.md`** |
| **The ladder, Cameron's exit, dip buying, the regime gate** | **`ladder_and_regime_20260911.md`** |
| **The state of every strategy** | **`premarket_hypotheses_results_20260908.md`** |
| **What does execution actually cost?** | **`execution_cost_measured.md`** |
| The screen AS OF a timestamp | `screen_at_build.md`, `screener_simulation_scope.md` |
| Where does the fill sit in the signal bar? | `entry_latency_20260908.md` |
| What is MCL and how did it get here? | `momentum_confluence_strategy.md` |
| **Which position mechanics have been tried and rejected?** | **`mcl_rejected_mechanics.md`** |
| Cameron's exit / dip buying, measured | `cameron_exit_result.md`, `dip_entry_result.md` |
| **Three exit experiments, registered but not run** | **`exit_candidates_20260911.md`** |
| What is ORB and what would make it ship? | `orb_strategy_spec.md`, `docs/research/REGISTERED_orb_grid.md`, `orb_preflight_RESULT_20260916.md` |
| **Large caps, and why Bollinger+RSI does not survive** | **`largecap_evidence_20260911.md`**, `factor_correlation_result_20260911.md`, `spy_intraday_RESULT_20260918.md` |
| **What could diversify this book, and why GEM is rejected** | **`diversifier_candidates_20260911.md`** |
| **What the literature says, from different data** | **`external_evidence_20260911.md`** |
| Win rate and R | `win_rate_and_r.md` |
| **How large can this be traded?** | **`sizing_and_capacity.md`** |
| **Can this universe be shorted at all?** | **`short_selling_feasibility.md`** |
| Tooling risk | `tooling_audit_20260911.md` |
| The database and the MCP | `database_and_mcp.md` |
| Setup guides | `ib_async_setup_guide.md`, `tradingview_mcp_setup.md` |

### The Warrior spec set

> **Start at `HANDOVER_TO_BUILD_20260910.md`.**

| Question | Doc |
|---|---|
| How the 401-video census was built | `CENSUS_SPEC.md` |
| **Universe, regime gate, stop, size — read first** | **`warrior_0_universe_and_risk.md`** |
| **His primary setup — the one MCL implements** | **`warrior_1_micro_pullback.md`** |
| Flat top / gap-and-go / reversal | `warrior_2_flat_top.md`, `warrior_3_gap_and_go.md`, `warrior_4_reversal.md` |
| How he actually picks | `warrior_5_selection_in_practice.md` |
| **401 videos as a dataset** | **`warrior_census_20260910.md`** |
| **What he actually DOES day to day** | **`execution_gap_20260910.md`** |
| Do the recaps carry trade times? **No** — probed, 0 of 12 | `time_of_day_RESULT_20260916.md` |
| The 46-day source review | `source_videos_13_cameron_46day_20260917.md` |

### Archive — superseded. **Do not quote as current.**

`archive/` — the five rejected MCL mechanics, VW9's rejection, early parameter
tests, the 09-02 and 09-03 session reviews, E15, the repo reorg.

---

## 7. Open questions, in priority order

**Rewritten 2026-09-12; ORB items rewritten 2026-09-16; B-series added
2026-09-17; tape items added 2026-09-17; item 1 closed 2026-09-17; SPY-IM
closed 2026-09-18; the Running Up line added and closed 2026-09-18.** The list
that opened on 2026-09-12 with "validate the simulated screen against the live
watchlists — *the one that gates everything else*" no longer has a gate at its
head. What replaced it is smaller and specific: the live feed's own delay.

### The one that gated everything else — closed

1. ~~**Validate the simulated screen against the live watchlists.**~~ **Done
   2026-09-17: 61 of 63 live names on XNAS.ITCH and the same 61 of 63 on
   XNAS.BASIC (97%, Wilson 89–99%) over eight automated sessions, carry-over
   set aside — GOOD on the pre-registered band** (49 of 51 on the seven
   sessions the registration was scored on; 09-17 added on the 18th at 12 of
   12). The 22 names set aside are the previous session's screen re-served at
   the feed's first poll (proved by 04:00:0x blocked stamps); the two misses
   are a missing prior close and a +19.5% peak. The point-in-time figures on
   `screen_pairs_pit_itch_v2.json` describe the live screen's universe.
   `screen_validate_itch_RESULT_20260917.md`.

   **1d. The live feed's quarter-hour — measured 2026-09-18: 900 seconds,
   and the login removes it.** Every name IBKR refused was refused 12–27
   minutes after the tape first qualified it (median +15.6, 10 of 10, on both
   tapes); the probe then read `update_mode` off the endpoint itself:
   `delayed_streaming_900` anonymously, `streaming` signed in
   (`feed_freshness_probe_RESULT_20260918.md`). **(b) closes as a procedure:**
   `TV_SESSIONID` + `TV_SESSIONID_SIGN` set in the feed's window before
   `run_paper.ps1`, both or neither, via `op read`; the startup check logs
   INFO streaming / ERROR delayed-with-cookie. **Ben decided YES to the
   cookie on 2026-09-19** (the ToS question in `tv_cookie_in_the_cloud_20260918.md`
   §1 is his call and he has made it). **Not in production yet:**
   `prod-20260918` predates the cookie code; the build chat's promotion after
   a close, with the feed changes, is what makes Monday's session real-time —
   and the two `$env:` lines before `run_paper.ps1` (runbook, "The feed,
   signed in"). The 04:00 carry-over rule (a
   name is not on today's screen until its pre-market volume has changed) is
   built as H-F1 and scored from `watchlist_arrivals_*.csv` once the feed has
   run with it; `premarket_time` may make it exact. **(a) changes purpose:**
   the `first_seen + 15 min` registration no longer describes the future live
   trader; it prices what every live session before 09-18 was trading — a
   screen exactly 900 s behind the tape — and whether that is the shape gap
   (live 47% win / R 0.72 against simulated 21.7% / R 1.67). ~~REGISTERED
   2026-09-19 as H-D1~~ **Run 2026-09-19: NOT IT, both arms**
   (`feed_delay_cost_RESULT_20260919.md`). MCL +$0.09 a trade at +15, MC5
   ($1.03) with 29% of its entries removed; win rate and R barely move;
   the live MCL shape at n = 50 (34% / 1.15) had already converged most of
   the way to the simulation (30% / 1.47). The pre-09-18 live record is
   evidence about the published strategies. For MC5 reconciliations (AT-14)
   compare against the +15 book in `feed_delay_trades.csv`. **Closed.**

   ~~**1b. A time-varying capture for the ITCH screen.**~~ **Done 2026-09-17
   (v2).** Measured against the consolidated cleared volume, not chained; the
   ladder is in `ScreenConfig`; the baselines moved by cents. What remains
   imprecise is the volume clause on post-change sessions (2k–11k exchange
   shares, p10 zero) — **and the validation put a number on it: 11 sim-only
   names on ITCH against 2 on BASIC over the September sessions, ~13% more
   symbol-days.** A hybrid universe (ITCH before the change, BASIC after) is
   available under its own registration **only if a study needs those
   sessions' names precisely**. Nothing queued depends on it.

   ~~**1c. Re-base the B-series and Part A on the ITCH universe.**~~ **Done
   2026-09-17, all four, on `screen_pairs_pit_itch_v2.json`** under PRE-RUN
   amendments to each registration: H-B1 REFUSED / REFUSED, H-B3 NOTHING /
   REFUSED, H-B4 REFUSED / NOTHING, Part A2 neither, the time-of-day cell
   fails all four. Every verdict stands; three per-trade deltas turned
   negative. `bseries_itch_RESULT_20260917.md`. **Nothing in the B-series or
   Part A is a BASIC-only result any more.**

### ORB — owned by the ORB chat from 2026-09-17; listed here for the index

2. **Register and run ORB on the point-in-time universe**
   (`screen_pairs_pit_itch_v2.json`, 6,411 symbol-days — not the BASIC or v1 file).
   The stage-2 survivors gave H0 +$4.72 and PIT gave −$11.77 on ITCH; ORB's
   +$3.33 sits inside that gap. The seven criteria are re-read on the baseline
   cell there. **Nothing in `orb_first_results.md` §1 is believed until this
   has run.** ORB's RTH bars are on XNAS.BASIC; run the `tape_spikes` census
   over the ORB window first (`handover_tape_switch_20260917.md`).
3. **Push the grid box to 45 minutes** (amendment C) and read criterion 7.
4. **Close the §12 gaps in the runner in one pass:** count round trips not legs
   (`r_3_trim`), capital-based sizing and the price-decile table, per-ticker
   and per-exit-reason friction, aggregate the downside break and the V2 fade,
   R-per-cell; narrow `_boundary_block` to the `none` arm.
5. **Only if 2 and 3 hold:** the live path. ORB has no `strategy_adapter`, the
   trader has never placed an RTH order, and RTH permits a native stop that the
   backtest deliberately does not model (spec §6).

### The 09-17 handover — luck vs edge, and fewer losing entries

6. ~~Part A — luck or edge~~ **Done 2026-09-17.** A2: neither — no bucket of
   any labelling is positive for either strategy at any friction; hot days are
   more trades at the same per-trade loss. A1: the 09-16 replay is green in the
   backtest (MCL +$36.54, MC5 +$12.41), same names as live. A3: over
   09-09..09-16 the fixed code loses $783 where the live trader lost $762 — the
   three fixes explain none of it. **A2 re-read on ITCH v2 the same day:
   neither** (MCL (66.23) / (78.43) / (47.07) per session hot / mixed / cold;
   MC5 (120.66) / (83.77) / (97.75)); reading 1 fails on every label.
7. ~~H-B3 — top-N by session range at signal time~~ **Done 2026-09-17,
   NOTHING / NOTHING.** The gate bound on 85% of entries and its gain was
   random removal's. `range_pct` did not separate winners from losers here
   either. **On ITCH v2: NOTHING / REFUSED** (+0.67 vs p95 +1.37; MC5 (0.18)
   a trade), bound on 89%.
8. ~~H-B4 — same-day cold veto after 07:00~~ **Done 2026-09-17, NOTHING /
   NOTHING by four cents.** The 07:00 watchlist proxy separates vetoed from
   admitted trades by $0.97; the daily composite's +$5.86 ceiling is not
   retired by it and not confirmed. The readings file is a point-in-time
   session classifier Part A can use. **On ITCH v2: REFUSED / NOTHING** (MCL
   (0.16) a trade; MC5 +0.36 vs p95 +0.94); 341 of 550 sessions vetoed.
9. **H-B2 — one open position per name across strategies.** Blocked by item 15.
10. ~~B5 — one combination~~ **Nothing to combine, 2026-09-17.** Three gates
    that each read as random removal do not sum to selection. **On ITCH v2,
    three of the six cells are negative per trade; still nothing to combine.**

### The session give-back, and the one test before the holdout

**The daily loss stop.** Restored to this list by name on 2026-09-18 after
falling out of it in a rewrite — see §4's row on item numbers. `if realised <=
-STOP, no further entries this session`: an absolute drawdown from zero, no
arm, no peak, no ratio. It is now registered and built as **H-S6**, the
comparator for the give-back cap rather than a candidate in its own right
(`docs/research/REGISTERED_stop_compare.md`, `common/stop_compare.py`).
**Run 2026-09-18: NO CELL SURVIVES.** Three of the four read UNDECIDED and MCL
under strategy scope reads THE SHAPE ADDS NOTHING. The matched flat stop
captures almost none of the give-back's gain (+0.03 a trade against +0.68), so
what ends it is the session-clustered bootstrap — 0.932 and 0.934 against a
required 0.95 — and, decisively, $8.92, where MC5 strategy scope falls to +0.21
with P = 0.665 because the flat stop improves thirteenfold across the friction
ladder while the give-back does not. `stop_compare_RESULT_20260918.md`.

**What is left open, and it is narrow.** The difference is real in sign at every
cell but one and rests on about ninety sessions where the give-back fires and
the flat stop does not — the two rules share only 35 of their ~210 session
fires. Nothing about that is worth a holdout spend or a second registration on
the same data; if it is ever revisited it needs more sessions, not more
statistics on these.

**Then, and only then, the holdout.** `REGISTERED_giveback_cap` §6 sets three
conditions on the pass: that it is not the time-of-day filter (checked, it is
not), that the live trader can compute `realised` exactly as the backtest does
(**not built** — this project has been bitten three times by a constant the
live path never read, most recently MC5's own apex exit, and a session-level
rule needs its parity test before it goes anywhere near a live session), and
the one holdout spend. H-S6 decides which rule that spend is for.

**And the $5 entry floor is closed.** REFUSED for MCL, NOTHING for MC5, and the
mechanism registered for it — that friction is a larger share of a $2 stock's
move — is arithmetically invisible in a per-trade delta between two books.

### The Running Up line — closed, and what it leaves behind

**The scanner itself is closed as a gate.** Ben's Running Up idea was priced
before it was built, and the pre-flight came back inverted: every momentum
feature separates dying trades from surviving ones in the wrong direction, so a
gate on it keeps more of the losers. `running_up_preflight_RESULT_20260918.md`.
**"Enter earlier in the move" is closed too** — H-E2 turned three dials, two of
them moved entry extension in the right direction with the predicted fall in
one-bar deaths, and every trade the loosening admitted was worth (7.00) to
(9.99). `entry_sweep_RESULT_20260918.md`.

~~**10b. The pullback cell.**~~ **Run 2026-09-19 as H-P2: REFUSED on both
books, and closed** (`pullback_cell_RESULT_20260919.md`). Within 5% of the
session high AND `ret_5m` ≤ +3%, through `entry_gate`; the deployed gate
selected exactly the pre-flight's cell (one-bar 2.9% / 16.3%) and the kept
books lose more per trade — (9.40) vs (8.97), (10.18) vs (8.57) — with all
ten of MCL's best trades outside the cell. Neither half alone nor either
neighbour beats random removal; the conjunction is worse than its parts.
**The one-bar death rate is closed as an entry-selection target** (§4). What
is not an entry rule remains: the cap (item 15 / AT-25), the stop mechanics,
and the 10-second strategy as a new strategy (10d / AT-33). It is **not** what MCL-PB tested — those six
versions bought the *breakout* after the pullback and paid a median +2.86%
premium to be confirmed — and it selects *among* the entries the strategies
already take rather than adding more, so H-E2 does not bear on it. It needs its
own registration, with the abstention control and both denominators, before it
is run. **It carries a heavier prior than anything else currently unrun here.**

**10c. The rebound study — Ben's, asked for 2026-09-17, not yet run.** "How
often does an open position drop below the entry price and come back to a
profit?" It is the question behind both the give-back cap and the trail's
give-back, Ben has watched a profitable trade become a loss because the trail
allowed the position below entry, and it is answerable off the existing trades
CSV plus the tape without a new engine pass. Nothing is registered for it.

**10d. The 10-second timeframe.** Cameron drops to a 10-second chart once a
name meets his criteria and the Running Up alert fires. The right shape is a
1-minute **setup** with a 10-second **trigger** — and this project does not own
sub-minute data for the pre-market window, so it must be priced before it is
bought. H-E2 is explicit that this is a different axis from the one it read.

**NOT the Day Trade Dash algorithm itself.** Reverse-engineering the scanner's
proprietary rule out of its JavaScript was declined on 2026-09-17 and stays
declined. A screen recording is useful only as **observed behaviour**, and the
most informative recording would include a panel of names that are moving and
**not** firing — the negatives are what would identify the rule, and a feed of
positives alone cannot.

### Strategy work, in the order it is worth doing

11. **Make Cameron's breakeven stop expressible as a `pit_delta` variant, and
    re-run it floored.** Largest of the four rejected mechanics at −$6.31/trade.
12. **The dip entry through `pit_delta`.** Non-trivial delta, not yet run.
13. **The early-names measurement.** MCL early −9.19 vs all −10.49 (+1.30); MC5
    −8.39 vs −14.25 (+5.86). MC5's early arm is heavily concentrated. 789
    symbol-days cannot separate selection from sample size. **On ITCH v2: MCL
    (8.73) vs (8.97), MC5 (7.48) vs (8.57) over 1,771 early symbol-days — the
    early set is now on a measured threshold.** **And item 1d bears on it
    directly: "early" on the tape is fifteen minutes before the live feed.**
14. **The trail-width ENSEMBLE for MCL.** §4's standard. Cheap, never tried.
    ORB's grid adds a datum: the 5% trail beat every fixed target at every length.
15. **Model the concurrency cap.** Live, **29% of buy attempts were rejected**
    (46 of 159; 30 of 62 on 09-10). No backtest models it, and which signals get
    dropped is decided by arrival order rather than quality. **Blocks H-B2**, and
    is where a skip rule's freed slot would be priced.
16. **Re-register the exit candidates** (`exit_candidates_20260911.md`) on
    `screen_pairs_pit_itch_v2.json` — item 1 has settled which universe is real.
17. **Transcribe the two dip videos** (`ORWJzImSTdE`, `hz7vhSIXXSc`).
18. ~~The intraday regime reading at 07:00~~ **Built and read as H-B4, item
    8.** The open question it leaves: whether the 66 composite-cold sessions
    (as opposed to the 297 count-cold ones) carry the daily ceiling — answerable
    from `cold_veto_readings` and the trade CSV without a re-run, under its own
    registration if anyone wants it. On ITCH v2 the split is 101 composite /
    240 count (`cold_veto_readings_itch.csv`).
19. **TSMOM**, if a genuine diversifier is wanted — grid **and** ensemble.
    **Register a replication control with it** (§4, added 2026-09-18): the same
    code over Moskowitz/Ooi/Pedersen's own sample, with a pass band fixed
    before the run. SPY-IM is the argument — without H-R its negative reading
    would have been indistinguishable from a harness that finds nothing.
20. **NOT the Cameron set.** Flat top, gap-and-go and reversal are his riskiest
    setups by his own census, and the reversal's short side is not buildable.
20b. **NOT the L1 large-cap intraday-momentum line.** Its premise is the
    mechanism SPY-IM just closed: negative gross on SPY, QQQ and IWM from 2016,
    with the effect intact only in 2007–09.

### Execution and the live path

21. **Price the three legs separately in the engine.** Entry +0.0007/share
    median, trail −0.0225, `window_close` **−0.0700**.
22. **Decompose the 1,658 real fills** into effective spread paid vs adverse
    selection suffered.
23. **Cancel the Databento subscription** — $199/month. **Unblocked 2026-09-17,
    and nothing further is wanted from it as of 2026-09-18:** the ITCH
    extension and the September daily repair are on disk and the validation
    has run on eight sessions. Item 38 (the 09:30–09:45 window for RVOL) is
    the one thing that would need the subscription back. **And 10d —
    sub-minute pre-market data — would be a new purchase, not this one.**
24. **Model LULD halts — for ORB.** Measured 2026-09-17 on the tape of record
    (`halt_census_RESULT_20260917.md`): 17.2% of the universe's symbol-days
    are paused after the open, 37% of those pauses start 09:30–10:00 (2.7 per
    session across the watchlist), median 5 minutes, and a paused name is
    paused 3.7 times that day. For the pre-market books the question is
    closed (two trades in 10,370). Whether ORB's 09:45 entry needs a
    halt-aware rule is the ORB chat's registration; the status archive is on
    disk at $0 and `halt_census.csv` lists every halt with a universe flag.
25. **A spread gate at entry.**
26. **One definition of the universe.** The live screen and `common/screen.py`
    compute different quantities under the same names.
27. **Generalise the trader further.** VW9 still cannot be paper traded; ORB has
    no adapter. **SPY-IM needs neither — it failed.**
28. **Confirm from a statement whether IBKR bills per order or per execution.**
29. **The fetch cadence.** `bar_freshness` measured a median acted lag of 98 s.
30. **Settle §4 trap 1 of the ORB spec** (the 09:30 bar). ORB chat.
31. **Read the MEDS exit price from the Flex statement**, and whether any
    earlier session lost a fill the same way on the timeout path.
31b. ~~**Promote the four 09-17 live-path fixes**~~ **Done 2026-09-18 as
    `prod-20260918`**, after measuring the live import closure (9 of 208 changed
    files reach the trader, six encoding-only). Read the first session on it for
    `NO_FILL_*` rows returning, `SKIPPED_BAR_BEFORE_EXIT` after exits,
    `SKIPPED_DRIFT` at about one entry signal in ten, and **no MC5
    `gradient_reversal` exit at all**. The analysis chat still owes the tagging
    of live MC5 rows 2026-09-10 → the promotion as apex-ON in the paper_fill
    join.
31c. **The feed's two defects** (item 1d b). **The delay: done 2026-09-18 by
    the probe's reading** — the cookie support is in `tv_feed`
    (`build-20260918g`), the login makes the endpoint `streaming`, and the
    remaining work is Ben's two `$env:` lines before each session (runbook,
    "The feed, signed in"), once a tag carrying it is promoted — `prod-20260918`
    does not. **The ToS question is decided: yes (Ben, 2026-09-19); the
    promotion is now the only gate and it is the build chat's.** Open in
    the build chat: resolve `op://` references for the pair through
    `secrets_util` so `setx` works as it does for every other key. **The
    carry-over: built as H-F1's gate**, unscored until the arrivals file has a
    session; `premarket_time` is the candidate exact test.

### Longer term

32. **The TRF check for MC5.** `tape_compare` runs MCL only. **Largely moot:
    MC5's baseline is now on ITCH.**
33. **Point-in-time float.** The EDGAR shares-outstanding pull ran 2026-09-14
    on the BASIC universe: SEC's current map covers 80% of symbol-days, the
    point-in-time join knows shares outstanding on 57% (median filing lag 65
    days), 28.5% of covered symbol-days carry 50M+ shares — a ceiling test
    only, never float. FINRA short interest is the other free source, not
    probed. Nothing queued needs either.
34. **Capacity.** At flat 100 shares, 22% of MCL's trades already exceed 1% of
    the volume in the minute they fill. FINRA Notice 26-10 ended the $25,000 PDT
    minimum on 2026-06-04. **Capacity on ITCH is a different number: the
    exchange sees 23% of BASIC's pre-market shares.**
35. **Short selling — the answer is no.** Two cheap items remain. **On large-cap
    ETFs it is a non-issue** — SPY borrow is a few tenths of a percent
    annualised, and SPY-IM's short leg was never discounted.
36. **The 8-year regime test.**
37. **`TZ_API_KEY_ID` / `TZ_API_SECRET_KEY` point at the Private vault.**
38. **Price the Databento 09:30–09:45 window pull** so RVOL becomes computable.

### Closed since the last rewrite

| Item | Outcome |
|---|---|
| Simulate the live screen and re-run on it | **Done.** The +$4.72 was a look-ahead artefact; the leak was intraday, not universe |
| Report at all three friction levels | **Done** in every `pit_*` module; now a §4 standard |
| The production/development split | **Done and verified** on Windows |
| `ib_insync` is archived | **Already migrated** 2026-09-04; pinned at 2.1.0 on 2026-09-12 |
| Re-price every delta for the intraday floor | **Demoted.** A level bias does not transfer to a delta. Survives only as item 11 |
| ORB's six pre-flight measurements | **Done 2026-09-16**, on both tapes; `opposite` eliminated by a pre-set threshold; RVOL not computable |
| Settle criterion 2 before ORB has a number | **Done 2026-09-16.** Replaced by the symbol-cluster bootstrap; MC5 fails it at 90.2% |
| Write `strategy/orb/orb.py` and the hand-built bar tests | **Done 2026-09-16.** 44 cases, 20 mutations caught |
| Run the ORB grid | **Done 2026-09-16** on XNAS.BASIC (after one run on the wrong tape). Six of seven; see §7 items 2–3 |
| The read-only IB bar probe | **Already existed** as `common/bar_freshness.py`; ran 2026-09-16 |
| The MEDS ghost position (D1–D7) | **Fixed 2026-09-16**, promoted `prod-20260916c`; the reverse ghost closed with it |
| Encoding: 242 bare text-mode opens | **Fixed 2026-09-16**, guard in place; a parse warning is refused too |
| **H-B1 — skip the first entry of each symbol-day** | **NOTHING (MCL) / REFUSED (MC5), 2026-09-17.** First entries are not worse; the live table did not replicate |
| **The time-of-day window (`execution_gap` §7 item 4 / `HANDOVER_TO_BUILD` item 6)** | **Closed 2026-09-17.** Every MCL block negative at every friction; 07:45–08:00 fails all four pre-stated checks on the PIT books. **The block table itself was on XNAS.BASIC and its 08:00 row is withdrawn; the verdict (no paying block) is not affected in direction.** Re-read on ITCH v2 the same day: every block negative, the cell fails all four, the 08:00 blocks halve |
| **H-B3 — top-N by session range among visible names** | **NOTHING / NOTHING, 2026-09-17.** Bound on 85% of entries; the gain was abstention's; 4 of each strategy's 10 best trades removed |
| **H-B4 — no new entries after 07:00 on a cold 07:00 reading** | **NOTHING / NOTHING, 2026-09-17,** by $0.04 on the abstention control for MCL. Vetoed 66% of sessions, 82% of them by the count rule |
| **B5 — the combination of B1–B4** | **Nothing to combine, 2026-09-17** |
| **Part A2 — luck or edge by regime** | **Neither, 2026-09-17.** MCL (84.74)/session hot vs (58.82) cold; no paying subset of sessions exists for either strategy |
| **Part A1 — replay 2026-09-16** | **Green, 2026-09-17.** MCL +36.54 / MC5 +12.41 in the backtest on the same four names as live |
| **Part A3 — how much of the live 09-09..09-16 loss the three fixes explain** | **None, 2026-09-17.** Backtest with the fixes (783.28) over 113 trades against live (761.84) over 134 |
| **Extend the archive past 2026-09-04** | **Done 2026-09-17/18 on both pre-market tapes, at $0.00**, through 09-17; `screen_sim --after` screens new sessions without touching the deciding file |
| Trade times from Cameron's recaps | **Closed 2026-09-16** by the research chat: 0 of 12 recaps yield a usable pair; do not commission an extraction pass |
| **MCL-PB, the pullback-breakout line (v1–v6)** | **NOTHING × 6, 2026-09-16.** Closed on both timeframes; v2 exposed the tape defect. **2026-09-18 gives the six failures a mechanism: it was the breakout purchase, not the wait — the pullback state alone reads 3.3% one-bar (item 10b)** |
| **The 08:00 tape defect — diagnose, probe at trade level, fix** | **Done 2026-09-17.** Late TRF reporting until 2026-03-30; XNAS.ITCH pulled at $0; `tape_compare` (10.52) → (8.82) on a fixed universe |
| **Rebuild the point-in-time screen on XNAS.ITCH and re-base H0 / MCL / MC5** | **Done 2026-09-17.** Stop rule passed exactly; H0 (11.90), MCL (8.81), MC5 (8.49); capture 0.126 with a time-varying defect carried to item 1b |
| **1b — the capture by the clock (screen_itch v2)** | **Done 2026-09-17.** Direct against consolidated cleared volume, per half hour, per regime; H0 (11.77), MCL (8.97), MC5 (8.57) on 6,411 symbol-days. The tape line closes |
| **Halts on the tape (item 24, the pre-market half)** | **Done 2026-09-17.** XNAS.ITCH status at $0; two trades in 10,370 spanned a halt; no LULD before 09:30. Closed for MCL/MC5; the ORB numbers are in the doc |
| **The 09-17 session's three defects (self-cancel as REJECTED, re-entry on a held-through bar, no drift guard)** | **Fixed on `main` 2026-09-17**, 29 tests, 20 mutants; **promoted 2026-09-18 as `prod-20260918`.** `live_defects_FIXED_20260917.md` |
| **MC5's apex exit OFF in the backtest, ON live (research chat handover)** | **Fixed on `main` 2026-09-17** (`0c50036`), mirroring MCL's 09-08 fix; the pinning test corrected; **promoted 2026-09-18.** `live_defects_FIXED_20260917.md` §D |
| **1c — the B-series and Part A re-based on ITCH v2** | **Done 2026-09-17; every verdict stands.** H-B1 REFUSED / REFUSED (−0.41 / −0.78 a trade), H-B3 NOTHING / REFUSED (+0.67 vs p95 +1.37; −0.18), H-B4 REFUSED / NOTHING (−0.16; +0.36 vs +0.94), Part A2 neither, the 07:45 cell fails all four. The population check keys on the universe file; `luck_vs_edge` refuses inputs from different runs. `bseries_itch_RESULT_20260917.md` |
| **Item 1 — validate the simulated screen against the live watchlists** | **Done 2026-09-17: GOOD on both tapes.** 49 of 51 live names (96%, Wilson 87–99%) over the seven registered sessions, 61 of 63 (97%, 89–99%) with 09-17 added on the 18th, once the 04:00 carry-over is set aside; two misses, both diagnosed on the tape (no prior close; +19.5%). The feed's quarter-hour delay and its 04:00 carry-over found on the way (item 1d). `screen_validate_itch_RESULT_20260917.md` |
| **SPY intraday momentum (H-S1 / H-S2), the JFE 2018 mechanism** | **CLOSED 2026-09-18, NOTHING × 2, negative GROSS on all three instruments.** H0 flat; **H-R replicated the published effect on 2005–2013 (+5.41%/yr, 53.52% hit)**, so the pipeline demonstrably detects it where it is documented. The effect concentrates in 2007–09 and is gone from **2016** — earlier than the 0DTE regime blamed for it. A registered stop fired first (mean \|r13\| 0.1765% against a 0.18% bar set pre-run) and forced a re-registration on measured economics before H0 ran. Holdout unspent. `spy_intraday_RESULT_20260918.md` |
| **The five scenarios — a $5 entry floor, and the 50% session give-back cap (H-S5, H-S4)** | **2026-09-18. The floor is NOTHING** (REFUSED for MCL), and its registered mechanism is arithmetically invisible in a per-trade delta — the floor's delta is identical at all three frictions. **The cap: MC5 passes all six registered readings under both scopes at every friction, the first rule in this project to do that**, while MCL fails and is made worse under session scope; the combinations read NOTHING. Three corrections found by reading the run against the registration, including a matched-count control amendment A4 promised and nobody had implemented. **It does not reopen MC5** at $7.79 a trade. `session_scenarios_RESULT_20260918.md` |
| **H-S6 — does the give-back's SHAPE beat a flat daily stop matched on trades removed?** | **2026-09-18. UNDECIDED × 3, ADDS NOTHING × 1; the holdout is spent on neither.** The flat stop captures almost none of the give-back's gain (+0.03 against +0.68), so the magnitude was never the problem — the session-clustered bootstrap reads 0.932/0.934 against 0.95 because the two rules share only 35 of ~210 session fires, and at **$8.92 MC5 strategy scope falls to +0.21, P = 0.665**, the flat stop having improved thirteenfold across the friction ladder while the give-back did not. H-S4's pass stands; **the attribution to the peak-relative shape does not.** The give-back also turns out to be the *less* clock-like of the two rules. `stop_compare_RESULT_20260918.md` |
| **The Running Up scanner as a gate (Ben's, from Day Trade Dash)** | **CLOSED 2026-09-18, and inverted.** Every momentum feature separates dying trades from surviving ones in the WRONG direction: MCL's five-minute return at entry reads AUC 0.751 against a 0.526 null and a 0.528 clock control, with dying trades entered after +11.43% and survivors after +4.90%, so a gate keeps more losers at every threshold. MC5 is U-shaped, which leaves "don't buy while it is dropping" alive but weak. Descriptive only — the pre-flight is barred from printing money. What it leaves behind is the pullback cell (item 10b) and the MC5 one-bar ceiling (+$0.70 a trade at $8.92 even with every instant death removed). `running_up_preflight_RESULT_20260918.md` |
| **H-E2 — the entry sweep: does less confirmation enter earlier, and does earlier pay?** | **CLOSED 2026-09-18. Nothing CLEARS, nothing IMPROVES; both scored families UNDECIDED — BOUNDARY, seven of nine cells REFUSED.** The dials work — MACD-off moves entry extension 5.33% → 4.71% and one-bar deaths 12.6% → 11.1%, MC5's threshold moves both monotonically across its range — and **every marginal trade is worth (7.00) to (9.99)**, so the improvement in every loosened cell is dilution rather than selection. Most cells ADD trades, so this is the first entry reading here that abstention cannot explain. **It refuted the study's own primary hypothesis:** the 3× volume surge moves entry extension by 0.23pp and is not what makes MCL late. It does not close the pullback cell. `entry_sweep_RESULT_20260918.md` |
| **The feed probe (H-F1 §5) — is the scanner delayed, and does the login change it?** | **Done 2026-09-18. Anonymous `delayed_streaming_900`, signed in `streaming`, both runs.** CPOP +15.1 min on the signed-in arm; median +11.2 over two names (one censored); the 04:00 carry-over watched (five of 09-17's HOT names, never moved in 35 min); `premarket_time` dates the row. §6(a) held; the "scanner ignores the login" alternative refuted. The fix is two environment variables before the feed starts. `feed_freshness_probe_RESULT_20260918.md` |
| **H-D1 — what the feed's 900 seconds cost, and are they the shape of the live book?** | **Done 2026-09-19: NOT IT on both arms.** +15 min floor: MCL +$0.09 a trade (395 of 3,908 removed, marginal (9.74)); MC5 ($1.03) (1,858 of 6,462 — 29% — removed, marginal (6.01)); win rate ±0.2 pt, R ±0.22; the +0 books reproduce the published baselines exactly. Live MCL at n = 50 is 34% / R 1.15 against a simulated 30% / 1.47 — the 47% / 0.72 gap was seventeen trades. A later floor enters *less* extended (P5 failed, informatively). Item 1d(a) closed. `feed_delay_cost_RESULT_20260919.md` |
| **H-P2 — the pullback cell: at the session high AND not extended, as an entry gate** | **REFUSED × 2, 2026-09-19, and the line closes.** Kept 409 / 855 trades; one-bar deaths 2.9% / 16.3% (mechanism held); per trade (0.43) / (1.61) worse than the base, inside random removal; per symbol-day up only by abstention. All ten of MCL's best trades outside the cell. Distance alone +0.55 (inside p95 +1.38), calm alone (0.02), the pair (0.43) — the conjunction subtracts. Three of six predictions held; P3 (per trade +$2–12) failed on sign. Item 10b closed; the one-bar death rate closed as an entry target. `pullback_cell_RESULT_20260919.md` |
