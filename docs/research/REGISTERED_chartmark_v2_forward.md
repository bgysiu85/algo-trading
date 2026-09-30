# REGISTERED — CHARTMARK-v2 F1: forward test of K1 (plus V-SESSION and V-WICKGATE) on new CL 1H bars, with IBKR paper orders as the fill check

**Committed 2026-09-30, before the first bar it scores exists** (first scored bar: CL 1H bar opening Wed 30 Sep 2026 18:00 New York = Thu 1 Oct 08:00 Sydney). `PROGRAM_INDEX` §1: registered before it is run.
**Board:** W15-0037. **Parent:** W15-0036 (CHARTMARK-v2, closed FAIL at step C, 2026-09-30). **Chats:** Research & spec (this registration), Build & test (scorer + paper runner), Live analysis (monthly check-ins).

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule, threshold or date changed after any forward bar has been scored is a POST-RUN amendment and says why.

---

## In plain terms

From the CL session of Thursday 1 October 2026 we run CHARTMARK-v2's K1 rule, frozen exactly as the backtest ran it, on every new hour of CL for **twelve months, to the session of Thursday 30 September 2027**. Each week the new hourly bars are downloaded and the same engine decides what K1 would have done. That book is the score, so it doesn't matter if the PC is off or Ben is away. Separately, a runner places the same orders in 1 MCL on the IBKR paper account, so we can see whether real fills match what the engine assumes. Two variants that held up at high friction on 2016–2021 (V-SESSION and V-WICKGATE) are scored the same way, engine only, with a stricter bar because they were picked after seeing results. A rule is stopped early if it is down $1,000 after 30 trades or falls further than K1's worst historical drawdown. Nothing can pass early.

---

## 0. Why this exists, and what the backtest says. Stated plainly because it doesn't support K1.

1. **Step S (2010–2015):** K1 won the selection among four losing candidates: 317 trades, net **($1,795)** per MCL at IBKR mid.
2. **Step C (2016–2021):** K1 made **$533** net on 317 trades but failed six of nine criteria, including losing to random entries (p99 $2,349) and to Donchian 20/10 ($2,357). Registration Amendment 4.3 says that closes CHARTMARK-v2 (`claude/w15_0036_chartmark_v2_stepC_RESULT_20260930.md`). The 2022–2025 holdout was not touched and stays locked.
3. **Why run it anyway:** Ben: *"The world and economy has changed so much since then… Would that have worked 10+ years ago?"*, then *"can't we do them all?"* / *"yes go ahead with A and B"* (B = this test). On 2026-09-30, after being asked what happens if step C fails, he chose **"Keep running"**: step C's fail is written beside every check-in and does not stop this test. New bars are the only data nobody has seen, so this is the one clean test of the modern market.
4. **The last twelve months (seen, not evidence):** on the seen window (2025-09-08 →), which Ben has traded and marked, K1 took 69 trades for +$229 gross per MCL (REGISTERED_chartmark_v2 Amendment 5.4). That is about **($15) net** after roughly $244 of mid costs. Break-even is the honest expectation to beat.
5. **The variants are added knowingly after results** (Ben, 2026-09-30: *"Yes, score them alongside"*). V-SESSION ($1,229 net, $911 at high friction) and V-WICKGATE ($1,877 / $1,023) were the only two positive at high friction on 2016–2021. They were read on that window, so each must clear a stricter random-entry bar (§5, F3), and neither can rescue K1.

## 1. The rules, frozen

**Engine:** `strategy.chartmark_v2.engine.simulate(fr, ind, p, start=…)` with the files `strategy/chartmark_v2/engine.py`, `strategy/chartmark_v2/spec.py`, `strategy/chartmark/spec.py`, `strategy/htf/bars.py` and `strategy/futbt/loading.py` exactly as at **commit f3872ff** (the last commit touching any of them; step S and step C ran on them). The scorer checks `git diff f3872ff HEAD -- <those paths>` is empty before every run and refuses otherwise.

| Rule | Params (spec.py) | Role |
|---|---|---|
| **K1** | `Params(prev_high=True, theta=0.05)` = REGISTERED_chartmark_v2 §2 + Amendments 1–5: live trigger level (max of red-candle open above the close + 1 tick, previous high + 1 tick, live EMA/MACD condition prices + 1 tick), $0.60 backstop, Amendment 5 fill-bar rule, EMA21 exit clauses 1–3, no session filter, long only | **Primary.** Scored, and traded on IBKR paper. |
| **V-SESSION** | K1 with `session=True` (orders only for bars opening 02:00–12:00 NY) | Secondary. Engine only. |
| **V-WICKGATE** | K1 with `wickgate=True` (previous-high term only when ≥ 2 of the last 3 green bars have upper wick ≥ 50% of range) | Secondary. Engine only. |

No parameter, filter, time window or exit changes during the test. A code fix that changes any trade is a POST-RUN amendment that re-scores the whole period and says why.

## 2. What is scored: the engine on new bars (primary)

- **Instrument:** 1 MCL ($100 per $1.00). 1 CL shown beside it.
- **Costs:** IBKR, as registered for CHARTMARK-v2 §4: MCL $0.77 per side + 0 / 1 / 2 ticks (low / mid / high). A roll carried through costs two extra sides. **Mid is the headline.**
- **Data:** Databento GLBX.MDP3 `CL.c.0`, the same schema and symbology as the W15-0002 training archive, pulled at least weekly for the sessions since the last pull. It is day-partitioned so that a week only buys its new days (the `strategy.w16.dvp_forward` pattern). Each new batch is read back: its hourly bars' session closes agree with Databento `ohlcv-1d` within 1 tick on ≥ 99% of sessions, and any gap hour is listed.
- **Indicators:** computed over the archive plus the forward bars, so they are warmed up. Difference-back-adjusted as `strategy/htf/bars.back_adjust`. The engine is **flat before the first forward bar** (`simulate(start=<index of the 2026-09-30 18:00 ET bar>)`), so every scored trade is an entry on a forward bar. The bars between the archive end and the start are warm-up only and never scored.
- **Window:** CME sessions dated **2026-10-01 → 2027-09-30** inclusive (first bar Wed 30 Sep 2026 18:00 ET; last bar ends Thu 30 Sep 2027 17:00 ET). A position open at the end is closed at the last close (J11).
- **Ledger:** `forward_chartmark_v2.json` records the scored sessions, each rule's trades, and the frozen commit. A session already scored is never re-scored. The ledger is not a holdout, and the 2022–2025 holdout ledger is never opened.

## 3. IBKR paper orders (secondary): the fill check for K1

The paper book **never replaces** the engine's score. It measures whether K1's orders can actually be filled as the engine assumes. Paper orders start when the runner is built and IBKR futures data is live on the paper account (§7). The score runs from day 1 regardless.

**3.1 How the runner trades (the build must follow this):**
- **Signals** come from IBKR CL front-month 1H bars (18:00 ET session, bars start on the hour), back-adjusted like the engine, computed with the frozen engine functions. **Orders** are placed in 1 MCL front month. The CL–MCL price difference ends up in the measured slippage, which is intended.
- **Entry:** at the close of arming bar t, a BUY STOP for 1 MCL at L*, good until the end of bar t+1 (GTD, so IBKR cancels it server-side). Re-computed and re-placed at every close while arming holds (J12). No order at a roll bar (J10).
- **Backstop after the fill (Amendment 5, live form):**
  - If EMA9 was falling at the arming close (EMA9[t] < EMA9[t−1]), or the fill is a gap fill (fill > L* + 1 tick, i.e. the bar opened above the level), the SELL STOP at fill − $0.60 goes on **immediately**, server-side.
  - Otherwise a **disaster stop at fill − $1.20** goes on for the fill bar only. At the fill bar's close: if close ≤ fill − $0.60, sell at market (the engine books the $0.60 stop, and the difference is logged); if not, the disaster stop is replaced by the $0.60 stop.
  - From the next bar on, the $0.60 stop sits at IBKR (GTC), so a runner outage never leaves a position unprotected.
- **EMA21 exit:** at the close of a bar where clause 1, 2 or 3 fires, sell at market within 60 seconds of the bar end. The backstop is cancelled through an OCA (one-cancels-all) group.
- **Roll:** the position is rolled to the next MCL no later than 2 trading days before the held MCL's last trade date, with the stop moved by the same dollar distance. Signals continue on back-adjusted CL. Roll prices are logged.
- **Outages:** if the runner is down at a bar close it does not chase afterwards. Missed entries are logged as *missed (runner down)*, and a missed EMA21 exit is taken at the first close after restart and logged.
- **Safety:** the W02 guards apply: paper port only (4002 / 7497), account id must start with "DU". A separate process with its own IB client id. W02 trades stocks, so there is no symbol overlap with MCL futures.

**3.2 Matching and slippage (reported monthly and at the end):**
- A paper trade **matches** an engine trade when both enter in the same 1H bar. The report lists matched trades, engine-only trades (with the cause: runner down / order rejected / data / coding difference) and paper-only trades.
- **Realised slippage per side** = paper fill vs the engine's raw price before modelled friction, in ticks, adverse-positive, for entry and exit separately. It is compared with the 0 / 1 / 2-tick friction levels.
- **Agreement (criterion F8, K1 only):** judged only on the weeks the runner was up. ≥ 90% of engine trades matched, ≤ 10% of paper trades unmatched, and median realised slippage ≤ 1 tick per side. If the runner was up for less than half of the window, F8 is **NOT READ** (disclosed) and the other criteria still decide.
- **If realised average slippage is worse than 2 ticks per side** (beyond high friction), F1 is re-read at the realised cost per trade instead of mid.

## 4. Early stop: checked at every weekly scorer run, per rule

- **Stop A:** after ≥ 30 trades, net at mid ≤ **($1,000)** per MCL.
- **Stop B:** drawdown from peak at mid worse than **($2,300)** per MCL (K1's worst drawdown over 2010–2015 was ($2,301)).

Either stop ends that rule, reported as **FAILED FORWARD** in a Result doc. If K1 stops, the paper orders stop. A variant that stops ends only itself. **There is no early pass.** Nobody reads a rule as "working" before 30 Sep 2027.

**Execution flag (not a stop):** after 15 matched paper trades, if average realised slippage is worse than 2 ticks per side, the check-in raises it to Ben as a board item. The score continues.

## 5. Pass at the end: each rule on its own, 1 MCL, IBKR costs, forward window

| # | Criterion | K1 | V-SESSION / V-WICKGATE |
|---|---|---|---|
| F1 | Net > $0 at mid | ✓ | ✓ |
| F2 | Net > $0 at high friction | ✓ | ✓ |
| F3 | Beats random entries (C3) on net | **p95** | **p99** (stricter: chosen after results, three rules tested) |
| F4 | Beats Donchian 20/10 long (C1) on net, same bars, same costs | ✓ | ✓ |
| F5 | Both halves net > $0: sessions 2026-10-01 → 2027-03-31 and 2027-04-01 → 2027-09-30 | ✓ | ✓ |
| F6 | Shape matches the backtest: win rate ≥ 20% **and** average losing trade no worse than ($70) (step S ($48), step C ($42); a $0.60 stop plus costs is about ($64)) | ✓ | ✓ |
| F7 | At least **50 trades**. Fewer → extend to the session of 2027-12-31, then NOT READ if still under 50 | ✓ | ✓ |
| F8 | Paper book agrees with the engine (§3.2) | ✓ | — |

**Controls on the forward bars:** C1 = CHARTMARK-v1's Donchian 20/10 long code without the session filter (as step C). C3 = random entries at the open of random forward bars while flat, the same count as the rule's forward trades, exited by the rule's own backstop + EMA21 walk (no entry conditions), 1,000 draws seeded `np.random.default_rng([crc32(str(d)), crc32("CL-v2-F1"), N])`. For V-SESSION the random bars are drawn only from bars opening 02:00–12:00 NY.

**What a pass earns:** nothing live. It earns a Ben decision, with its own registration, on (a) whether the locked 2022–2025 holdout should be spent on that rule (step C failed, so this would be a disclosed waiver of Amendment 4.6), and (b) a live-size discussion with risk limits and a kill switch. A variant that passes when K1 fails is a new line (W15-0038), not a rescue of K1.

## 6. Check-ins

Monthly, on the first business day (Live analysis chat, Haiku / Low): per rule, trades, wins and losses, gross, costs, net at low/mid/high, drawdown, stop status. For K1, also matched / missed / extra paper trades and realised slippage. Step C's FAIL is stated at the top of every check-in. **Nothing is changed at a check-in.** A stop that fires between check-ins is reported when the weekly scorer sees it.

## 7. Before the first paper order (the score does not wait for these)

1. **Ben:** IBKR futures market data from 1 Oct must cover **NYMEX** (CL and MCL are NYMEX products, not CME). Turn on market-data sharing from the live account to the paper account, and confirm the paper account can trade futures.
2. **Build & test:** the weekly scorer (§2), with G-checks: the frozen-commit check; a read-back; truncation invariance (scoring week by week gives the same trades as scoring all weeks at once); the engine reproducing step C's K1 trades on 2016–2021 before it touches forward bars; and a test that the ledger refuses a re-score.
3. **Build & test:** the paper runner (§3.1), with a dry mode that logs orders without sending them. It first runs dry against paper for ≥ 3 sessions and its decisions are compared with the scorer's for those sessions. Only then does it send orders.
4. The runner needs IB Gateway up about 23 hours a day, 5 days a week. On the ProArt or the W10-0013 cloud server, whichever is live. Ben is away 4–12 Oct, so paper orders will most likely start after he's back. That's fine, because F8 is judged on the weeks the runner was up.

## 8. Prediction, written now

**K1:** 50–75 trades over the year, win rate 25–33%, net between **($1,200) and +$600** per MCL at mid. Stop A has about a one-in-four chance of firing. I give K1 about **one chance in eight** of passing F1–F7. **V-WICKGATE** is the most likely of the three to finish positive, but I expect it to miss the p99 bar. Realised paper slippage will be 0–1 tick per side on entries (stop orders in a liquid market) and on EMA21 exits (market orders right after the close).

## 9. Not to be done

- Pausing, resizing, skipping days or overriding a trade by judgement.
- Changing any rule, threshold, the $0.60 stop, the dates or the pass bar once a forward bar has been scored.
- Restarting the count from a later date because the first weeks went badly.
- Adding more variants under this registration.
- Declaring a pass, or trading live, before the end date.
- Scoring the paper book as the result, or quoting gross, the seen window or a variant as K1's headline.

## Next steps (board)

- **W15-0037 sub 1** (Research & spec): this registration. Done.
- **W15-0037 sub 2** (Build & test, Sonnet / Medium): weekly forward scorer + ledger + G-checks (§7.2).
- **W15-0037 sub 3** (Ben): IBKR NYMEX futures data + share to paper + futures permission on paper (§7.1).
- **W15-0037 sub 4** (Build & test, Sonnet / Medium): IBKR paper runner, dry 3 sessions, then live paper (§3.1, §7.3).
- **W15-0037 sub 5** (Ben, then Live analysis Haiku / Low): run the weekly scorer to 30 Sep 2027; monthly check-ins; final read → Result doc.
