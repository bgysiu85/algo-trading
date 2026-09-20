# Handover — luck vs edge, and fewer losing entries

From: live paper-trade analysis chat (read-only on production).
To: strategy build and test chat.
Written 2026-09-17 (Sydney). Nothing in `D:\TradingProd` was changed.

Background reading, all in the project:
- `claude/green_day_attribution_20260916.md`: 09-16's +212.95 was the opportunity set (MEDS +149%, FTFT) rather than execution. About +344 of the +374 swing is price move; the execution legs were ordinary.
- `claude/PROGRAM_INDEX.md` §2, §4, §7 for standing results and rules.

**Ben's two asks:**
1. **Luck or edge?** Measure whether MCL/MC5 make enough on trend days to pay for the rest, over history rather than one session.
2. **Fewer losing entries.** Reduce entries into trades that don't have real momentum. Win rate is not the goal on its own: a filter only helps if it removes more loss dollars than winner dollars.

Every hypothesis below must be **registered before it is run** (§1), measured on the **point-in-time universe** (`screen_pairs_pit.json`), and reported with drop-top-N, both halves, the symbol-cluster bootstrap, and all three friction levels. The locked holdout stays shut.

---

## Part A — luck vs edge

**A1. Replay 2026-09-16 unchanged.**
- Pull Databento `XNAS.BASIC` `ohlcv-1m` 2026-09-16 04:00–09:30 for that day's watchlist: MEDS RETO FTFT NAMI VEEA MYSZ. **State the price before pulling.**
- Run MCL and MC5 exactly as configured on `prod-20260916b`.
- If the backtest is also green, the market reading is confirmed without relying on live fills.

**A2. How often do days like 16 Sep happen, and what does the strategy do on them?**
- Use `regime_labels` (validated against Ben's labels, AUC 0.730) on the full archive.
- Report the share of hot / mixed / cold sessions.
- Report MCL and MC5 per trade AND per session in each regime, on the PIT trade list.
- Also cut by a trend-day definition written down before looking, e.g. top watchlist name's 04:00→09:30 move ≥ X%. Pick X and write it in the registration.
- **Break-even question to answer in numbers:** at the measured hot-day profit and cold/mixed-day loss, what hot-day frequency breaks even, and how does it compare with the frequency actually seen?

**A3. Known-defect adjustment.**
Before judging, re-run with the three fixes already on `main`:
- stale-bar gate
- trail seeded from the fill
- ghost-position fix

Report how much of the live loss they account for. Live record for context:
- **09-09..09-16:** 134 round trips, (761.84), (5.69)/trade, 22.4% win.
- **28 trades held ≤ 1 minute** lost (536.37) at 10.7% win. Many of those are seed or stale-bar shaped. The 09-16 handovers list them.

---

## Part B — fewer losing entries

### B0. What has already been tested and failed (don't re-run as-is)

| Idea | Result | Doc |
|---|---|---|
| Entry-bar feature filters | `entry_features`: 22 features, **0 of 11 families**; `entry_margins`: **112 buckets, none positive** | `where_the_edge_is_20260913.md` |
| Anything preceding a run | best volatility-independent precision **0.21%** (base 0.108%) | same |
| Drift at order as entry filter | not monotone, null | `session_review_20260914_15.md` §3 |
| Confirmation / pullback-break | MCL-PB v1–v6, **none profitable**; confirmation premium +2.86% | `pullback_break_*_RESULT_20260916.md` |
| Yesterday's regime as a gate | not adoptable (shuffle 29.6%) | `regime_labels_RESULT_20260916.md` |
| Time-of-day window | concentration fails drop-top-3 in every block | `time_of_day_RESULT_20260916.md` |
| Dip entry, ladder, breakeven stop, partial | all lose | `ladder_and_regime_20260911.md` |

**Why bar filters keep failing:** MCL's five conditions already make its entries alike. And winners are extremely concentrated: live, the top 5 of 30 winners are 52% of winner dollars. A filter that removes "weak-looking" entries tends to remove the few trades that pay for everything. `dollar_vol` would have vetoed the TNON 07:35 trade it was meant to catch.

### B1. The live record points at the FIRST entry into a name (new, not yet tested)

Live paper, 09-09..09-16, all strategies, ordered by time within each symbol-day:

| | n | net | per trade | win |
|---|---:|---:|---:|---:|
| first entry in a name-day | 37 | **(812.80)** | **(21.97)** | 13.5% |
| later entries in the same name-day | 97 | **50.96** | 0.53 | 25.8% |

- 32 of the 37 first entries lost.
- Excluding CRBP (241.37) and the two 04:00 stale-bar losers (VEEA 09-16, TNON 09-11), first entries are still (513.69) over 34 = (15.11)/trade.

**This is suggestive, NOT a result, and carries a circularity:** a second entry only exists if the name kept signalling after the first. That is partly conditioned on the move continuing. The live numbers overstate any rule built from it. n = 134 over 6 sessions, in-sample.

**Register H-B1:** *Skip the first entry signal of each symbol-day; take the second and later ones.*
- Real-time implementable, no look-ahead.
- Measure on the PIT trade list against baseline MCL/MC5, one variable, same trades otherwise.
- Pass bar: per trade AND per symbol-day both improve, and both halves, drop-top-3 and the cluster bootstrap all agree.
- Also report how many of the baseline's top-10 winners the rule removes, so the cost is visible.
- **Variant to state up front, not tune:** skip until the name has made a new session high after its first signal. Pick one form in the registration and don't try both after seeing results.

### B2. One position per name across strategies

On 09-16 MCL and MC5 bought VEEA in the same second (200 shares, two losses).
**Register H-B2:** *one open position per symbol regardless of strategy.*

- Needs the concurrency cap modelled (§7 item 15), since which strategy gets the slot matters.
- Report entries removed and net change.

### B3. Rank names at signal time; trade only the strongest few

`universe_lift`: within-session `range_pct` rank at a cutoff gives **14.85× lift at top 5, 3.18× at top 50**, with the separation in the first handful.
**Register H-B3:** *take an entry signal only if the name ranks top-N by session range at that minute.*

- Pick N before running (e.g. 3).
- This is name selection, not bar selection. It is a different lever from B0's failures.
- It also gives the cap a ranking rule instead of arrival order.
- **Caveat to carry:** `range_pct` describes Ben's selection and did NOT separate his winners from losers (`won_vs_lost_20260916.md`). Expect it to cut trade count; whether it improves P/L is the open question.

### B4. Same-day regime veto at 07:00

§7 item 12: same-day regime is significant (+$5.86/trade, p = 0.024, monotone), but every bucket is negative and the ceiling test was added after seeing the ordering.
**Register H-B4 as a veto only:** *no new entries after 07:00 on a session the composite reads cold at 07:00.*

- Report losses avoided vs winners lost.

### B5. Do these combine?

Only after B1–B4 are read singly. Then the one combination the singles justify, as a new registration. No grid over combinations.

---

## What NOT to do

- Don't adopt anything from the 134 live trades directly. Live is for checking the backtest, not fitting.
- Don't tune thresholds after seeing results. Each changed threshold is a new hypothesis.
- Don't touch `D:\TradingProd`. Promote through the normal tag process after the close.
- Don't spend the locked holdout on any of these until one passes everything on the PIT set.

## Deliverables Ben expects

- A registration doc per hypothesis, committed before running.
- Each result as a `.txt` in `D:\Trading\Claude outputs` **and** a published artifact page (negatives bracketed and red).
- A one-paragraph plain-English verdict per hypothesis: fewer entries by how many, losses avoided, winners lost, net.
- Exact PowerShell/git commands at the end of each piece of work.
