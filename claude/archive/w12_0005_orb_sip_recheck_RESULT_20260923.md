# W12-0005 · ORB SIP figure-of-record recheck — RESULT

**Status: final. Verdict: revise ORB SIP's figure of record from +0.001R/trade (+$480) to −0.098R/trade (−$70,830) on the 7,239-trade primary cell. Confirmed real, spot-checked, written up — see "Write-up, same day (2026-09-23)" at the bottom for the full case.**

## In plain terms

While building W05-0003's G2 engineering gate (a tool that re-runs ORB's proven strategy using second-by-second price data instead of one-minute snapshots), the check came back failing — but not in a boring way. It fails against the official "figure of record" for ORB SIP (net +0.001R per trade, essentially break-even), and the more granular data instead shows something close to **net −0.098R per trade — a real, sizeable loss**, roughly **$(70,800)** across the 7,239-trade in-sample book instead of a wash.

I did not take that number at face value. I independently cross-checked the new tool's decisions against a completely separate dataset from a prior (18 September) study that had already verified real second-by-second data for one narrow slice of these trades — the new tool matched it **100%, on all 2,888 trades checked**. So the tool's core logic is not the problem.

What I found instead, digging into the biggest individual discrepancies, is more interesting: a handful of trades that the official minute-bar ledger says rode all day to a huge profit (one, PPG on 2025-04-09, shows +28.4R) instead show up in the second-by-second data as stopped out almost immediately, for a small loss. These are all trades with a very tight stop (well under 0.5% of the stock's price) on volatile days. That's consistent with either (a) a real, brief price dip that a coarse one-minute bar simply couldn't see, or (b) the two different data feeds (one-minute bars vs. one-second bars) not actually being built from the exact same trades — a known, documented risk with market-data vendors. I wrote a small, free diagnostic that tells these two apart directly, and Ben ran it on his machine.

## Revised 2026-09-23 — diagnostic result: (superseded — see Correction below)

**This section's verdict ("it's (b), confirmed") was wrong.** Kept for the audit trail; do not use it. The diagnostic (`strategy/orb/tensec_g2_diag.py`, output `var/reports/tensec_g2_diag.txt`, 626 KB / 5,904 lines) checked the 40 stock-days responsible for the biggest swings, and found 5,898 minutes present in the 1-second data with no matching bar in the official 1-minute data (39/40 stock-days affected), and 0 minutes where both sources have a bar and disagree on price. I concluded this coverage gap explained the divergence. It doesn't — see the Correction section: every one of those 5,898 gaps falls outside trading hours.

## Correction, same day (2026-09-23) — the "confirmed (b)" verdict above was wrong

**What went wrong:** I concluded the 5,898-missing-minute finding explained G2's divergence without checking *where* those minutes fall in the day. I caught this while building and unit-testing the "repair" fix (a `strategy/orb/tensec_g2_repair.py` module that re-walks the ledger on gap-filled minute bars): it changed **nothing** for the four known example trades (PPG, GLW, DXC, BJ), which sent me back to check the diagnostic more carefully.

**Where the 5,898 gaps actually are:** 4,308 pre-market, 1,590 post-market, **0 within trading hours (9:30am–4:00pm)**, across all 40 checked stock-days. The ORB strategy only ever looks at the trading-hours window — so this gap cannot be causing G2's divergence. The earlier "confirmed (b)" conclusion does not hold.

### What actually explains the divergence

Looked directly at the 209 trades (of 7,239) where the official ledger and the 1-second engine disagree on how the trade ended. They split cleanly into two mechanisms, both already understood and neither a data problem:

| Mechanism | Trades | What it is |
|---|---:|---|
| Entry-minute stop-order ambiguity | 142 | Entry price matches exactly between the two readings; the 1-minute bar can't tell whether the stop-loss level was touched before or after the trade entered, within that same minute. The 1-second data resolves it directly. **This exact mechanism was already independently verified 100% correct against ground truth by the 18 September study** — see "What's independently verified" below. |
| Genuine intra-minute entry-price gap | 67 | The 1-second data shows the price jumping past the entry trigger *within* a single minute, before that minute's own opening print. A 1-minute bar's open can't see this — it only knows the price *touched* the trigger level, not exactly when or how fast. Average gap 4.7¢, up to 22¢ — ordinary for these volatile small caps. Spot-checked, see below — not a data glitch. |

Together these two groups account for essentially the entire swing between the official reading and the 1-second reading (mean net R moves from −0.3497R to −0.0978R, a +0.2519R/trade shift; these 209 trades carry essentially all of it).

### Corrected verdict

**This points to explanation (a): the −$70,830 (−0.098R) full 1-second figure looks like a real, legitimate result, not a data-schema artifact.** Neither disagreement mechanism above is a vendor data problem — both are genuine information that only sub-minute resolution can see, and one of the two is already cross-validated against independent ground truth.

### Code change reverted

The `--repair-ledger` change to `tensec_g2.py` from earlier today has been fully reverted (verified via `git diff`, no changes remain). `strategy/orb/tensec_g2_repair.py` is left in place, unwired, as a correct and tested utility for a genuine RTH coverage gap, should one ever turn up elsewhere — it is not the fix for this issue and nothing imports it.

## Spot-check, same day (2026-09-23) — the 67 intra-minute entry-gap trades, checked for bad ticks

Ben's instruction before writing up the case: rule out that the 67 "genuine gap" trades are actually data errors (isolated bad prints), not real price moves. Checked **all 67** (not a sample) for two bad-tick signatures: (1) an isolated price spike on one print that immediately reverts within the next ~10 seconds, and (2) abnormally low trade volume at that print versus the surrounding seconds.

**Result: no bad ticks.** 65/67 show the gapped price persisting afterward — a real, sustained move on ordinary volume. 2/67 were flagged by the automatic check and reviewed by hand:

- **MBB, 2025-03-12** — the triggering print (93.095) carried 322 shares, above the local average (~200) — a real, liquid trade. The mild pullback afterward is ordinary short-term price drift, not a data problem.
- **PPG, 2025-04-09** — the flagship example used throughout this write-up. The triggering print ($91.71) is a genuine exchange trade (direct XNAS.ITCH feed, not a derived or synthetic quote) but on just **2 shares** — unusually thin. It's real, not corrupted, but worth carrying forward as a **fill-realism caveat**: a 2-share print briefly moving the last-trade price is weaker evidence that a full-size stop order would have filled at exactly that price, versus a thicker print. This doesn't change the conclusion (the subsequent stop was still genuinely reached a few seconds later at $91.65-ish, well within the position's actual downside path) but it means PPG specifically may overstate how cleanly $91.71 was achievable.

Raw output: `var/reports/w12_0005_entry_gap_spotcheck.csv` on D:\Trading.

## Write-up, same day (2026-09-23) — the case for revising ORB SIP's closed verdict

**Verdict: revise ORB SIP's headline to decisively negative.** The full one-second resimulation of the entire primary cell (7,239 trades, range 5 min, top 20 — the strategy's own primary book) is complete, checked against the seven registered pass/fail criteria, and checked for concentration. The current official "figure of record" (+0.001R/trade, ~+$480, from the 18-Sep entry-minute-tie correction) undercounts the true cost of ORB SIP's trigger once fills are read at the resolution the trigger actually fires at. The corrected figure is **−0.098R/trade, −$70,830** across the same 7,239 trades.

This does not reopen ORB SIP — it was already closed, not passing, on every reading checked so far (registered, RESOLVED, and now full-second all fail 6 of 7 criteria; RESOLVED and full-second both pass only criterion 4, trades ≥ 100). It makes the "closed" call more decisively negative: the strategy's true cost, at the resolution its own trigger fires at, is roughly $71,300 worse than the number currently on record.

### The three readings, in dollars and R (7,239 trades, $100 risk each, BASE friction)

| | registered (raw ledger) | RESOLVED (18-Sep, current figure of record) | full-second (today) |
|---|---:|---:|---:|
| Mean net R/trade | −0.350R | +0.001R | **−0.098R** |
| Mean gross R/trade | +0.003R | +0.351R | +0.253R |
| Win rate | 11.9% (861/7,239) | 14.6% (1,057/7,239) | 14.2% (1,027/7,239) |
| Gross $ | $1,908 | $254,100 | $183,023 |
| Cost (friction) $ | $(255,060) | $(253,620) | $(253,852) |
| **Net $** | **$(253,152)** | **$480** | **$(70,830)** |

`registered` is `sip_run`'s original minute-bar ledger, every entry-minute stop charged. `RESOLVED` is the current official closed-not-passing figure: one-second bars settled only entry-minute stop-order ties (142 trades). `full-second` re-walks every fill of every primary-cell trade second by second — it reproduces RESOLVED's tie answer on its own and goes further, so **the headline comparison that matters is RESOLVED → full-second**, not registered → full-second (that larger-looking swing is mostly the already-known 18-Sep fix, not new).

### The seven criteria, re-scored on full-second

| # | Criterion | full-second | Verdict |
|---|---|---:|---|
| 1 | drop-top-3 / drop-top-5 total R > 0 | −867.6R / −967.5R | FAIL |
| 2 | cluster bootstrap P(total>0) ≥ 0.95 | 0.029 | FAIL |
| 3 | mean net ≥ +0.05R/trade | −0.098R | FAIL |
| 4 | trades ≥ 100 | 7,239 | pass |
| 5 | both halves (chronological) > 0 | −584.9R / −123.4R | FAIL |
| 6 | both sides (long/short) > 0 | long −0.131R / short −0.065R | FAIL |
| 7 | no optimum on a boundary | range 5 min, top-40 (registered reading — not resimulated) | FAIL |

**1 of 7 met**, same as RESOLVED (also 1 of 7, criterion 4 only). Criterion 7 isn't re-scored: the one-second data was bought for the primary cell alone (range 5, top 20), same scope as RESOLVED; ranks 21–40, `eligible`, `unfiltered` and the 15-minute arm still carry minute-bar fills at every resolution checked so far, so comparing a resimulated top-20 against an unresimulated top-40 would score the difference between two readings, not two cells. It already fails on the registered reading, so this doesn't change the verdict.

Random-20 control (2,000 seeded draws of 20 eligible names/session, same trigger and friction): control mean −0.219R, control p95 −0.166R, top-20 actual −0.098R — beats the control's 95th percentile. The ranking still does something; it just isn't enough to clear a real edge at this resolution.

### What actually moved from RESOLVED to full-second — the new finding

Of the 7,239 primary-cell trades, **5,263 (73%) change net R** going from RESOLVED to full-second: 3,913 worsen, 1,350 improve, average move on the changed trades −0.135R. Two things drive it:

- **209 trades disagree on exit reason** with the *original* minute-bar ledger. 142 are the entry-minute stop-order ties RESOLVED already fixed (same direction, no new information). The other **67 carry a genuine intra-minute entry-price gap** RESOLVED never touched — a 1-minute bar's open can't see the price jumping past the trigger level within that same minute. All 67 were spot-checked against ohlcv-1s bar continuity and volume for bad ticks earlier today: **none found.** One caveat, PPG (2025-04-09) — see sample trades below.
- **The remaining ~3,400+ trades** keep the same exit reason at both resolutions but fill at a slightly different price — ordinary sub-cent-to-few-cent differences between where a minute-bar approximation puts a stop and where the tape actually printed. Individually tiny, but systematic and one-directional enough in aggregate to account for most of the −0.099R/trade move beyond the 67 flagged trades.

Concentration (full-second book, $100 risk/trade):

| | R | $ |
|---|---:|---:|
| Full-second total | −708.3R | $(70,830) |
| RESOLVED total (for comparison) | +4.8R | $480 |
| Drop top 1 symbol | −765.0R | $(76,496) |
| Drop top 3 symbols | −867.6R | $(86,764) |
| Drop top 5 symbols | −967.5R | $(96,751) |
| Drop top 10 symbols | −1,200.7R | $(120,071) |

Top 5 (best): MWA +56.7R, TD +51.6R, IONS +51.0R, NYT +50.0R, THC +49.9R.
Bottom 5 (worst): CWAN −20.7R, AEO −20.1R, KNX −19.8R, UCO −18.8R, ELS −18.6R.

Removing the single best symbol takes the book from $(70,830) to $(76,496) — same concentration pattern as every other reading of this strategy: a handful of very large winners, not a broad edge. Criterion 1 exists to catch exactly this, and does.

### Sample trades (actual $, $100 risk, 7,239-trade primary cell)

| Symbol / date | Reading | Entry | Exit | Reason | Gross $ | Net $ | Note |
|---|---|---:|---:|---|---:|---:|---|
| PPG, 2025-04-09 (long) | RESOLVED | $91.62 | $103.06 | session_end | +$2,850 | +$2,841 | Minute bars show this riding to the close as a huge winner. |
| PPG, 2025-04-09 (long) | full-second | $91.71 | $91.31 | stop | $(100) | $(111) | Second-by-second shows a stop-loss touch instead. The triggering $91.71 print is a real exchange trade but on just 2 shares — thin, spot-checked earlier today, not a bad tick, but weaker evidence a full-size order would have filled at exactly that price. Largest single-trade swing in the primary cell (~$3,000, ~30R); carried as a footnote caveat, not excluded — excluding it does not change the verdict (7,238 trades still fail 5 of 7 criteria). |
| CWAN, 2025-02-20 (short) | RESOLVED | $30.15 | $30.23 | stop | $(100) | $(159) | Ordinary stop-out, standard $100 risk. |
| CWAN, 2025-02-20 (short) | full-second | $30.13 | $30.28 | stop | $(199) | $(258) | Same trade, same stop reason — but the true tape shows more slippage through the stop than the minute-bar close approximates. Typical of the ~3,400 small-fill-difference trades behind most of the new −0.099R. |
| MWA, 2025-02-05 (long) | both | $24.35 | $26.93 | session_end | +$5,094 | +$5,027 | Unchanged at both resolutions — MWA's concentration in the full-second book is inherited from RESOLVED, not a new artifact of this resimulation. |

### Method (write-up)

`strategy/orb/tensec_g2_full_resolved.py` (new, this session). B0 (`strategy/orb/tensec_engine.b0_trade`) walks every primary-cell trade's entire post-OR path second by second against XNAS.ITCH `ohlcv-1s`, holding side/or_high/or_low/r fixed from the registered minute-bar ledger — the host is never recomputed, only the fill, per `REGISTERED_10sec.md`'s design. `tensec_g2_trades.csv.gz` (already computed, $0) is the row-for-row comparison this reads. Criteria, friction model, $100-risk sizing and the random-20 control all reuse `strategy/orb/sip_report.py` unchanged — identical methodology to every other ORB SIP reading, only entry/exit prices and reasons differ.

### Caveats (write-up)

- No tick/trades-level (mbp-1 or similar) schema was purchased. The 67 genuine-gap trades were spot-checked for bad ticks using ohlcv-1s bar continuity and volume heuristics only, not a trade-by-trade tape read.
- The PPG (2025-04-09) trade above is the single largest-magnitude divergent trade in the primary cell and rests on a thin 2-share print. It is real (confirmed earlier today), not excluded, and does not change the verdict on its own.
- Criterion 7 is reported on the registered reading, unchanged and flagged (see above) — the one-second data covers the primary cell only.
- Both candidate explanations for the original divergence were checked: (a) genuine resolution-driven fills — confirmed, this is what the −0.098R figure reflects; (b) a Databento ohlcv-1m coverage gap — ruled out (the 5,898 gaps found earlier are 100% outside trading hours, 0 within 9:30–16:00, and cannot touch any primary-cell trade).

## What Ben decided

1. ~~Run the diagnostic~~ — done, 2026-09-23.
2. First reading: diagnostic confirms (b) — **wrong, corrected same day, see above.**
3. Ben chose "redesign G2 now" based on the first (wrong) reading; the redesign was built, unit-tested, found not to apply, and reverted before any board/ledger artifact depended on it.
4. On the corrected picture, Ben chose "spot-check the 67 gap trades first" — done, see above, no bad ticks found.
5. On the spot-checked picture, Ben chose "yes, write it up now" — done, see "Write-up" above.
6. **G2 stays failed and nothing on W05-0003 (H-X1, H-Q1) is scored** until this resolves, per the registration.

### What Ben should decide now

1. **Accept this as ORB SIP's revised figure of record** (recommended) — closed, does not pass, true cost ≈ $(70,830) on the primary cell rather than the ~break-even $480 currently on record. No further action needed on ORB SIP itself; it stays closed permanently per the existing concentration checks.
2. Ask for anything else checked before this is finalized (e.g., the PPG trade excluded as a sensitivity check, or the 3,400 small-fill-difference trades broken down further).

## The numbers, in dollars and R (7,239 trades, $100 risk each, BASE friction) — original summary table

| | Published ledger (registered reading, on disk today) | Full 1-second resimulation (this session) | "Resolved figure of record" (18 Sep, entry-minute only) |
|---|---:|---:|---:|
| Mean net R/trade | −0.3497R | **−0.0978R** | +0.0010R |
| Mean gross R/trade | +0.0026R | +0.2528R | +0.3510R |
| Win rate | 11.9% (861/7,239) | 14.2% (1,027/7,239) | 14.6% |
| Gross $ | $1,908 | $183,023 | $254,100 |
| Cost (friction) $ | $(255,060) | $(253,852) | $(253,620) |
| **Net $** | **$(253,152)** | **$(70,830)** | **+$480 (+4.8R)** |

**Confirmed: the −$70,830 full-second figure is the trustworthy one** — a real, spot-checked finding, not an artifact of broken comparison data. The +$480 "resolved figure of record" was only a partial (entry-minute-only) resolution and understates the true cost by roughly $71,300.

The published ledger figures above are the raw, un-resolved reading (every entry-minute stop charged) — that is what's currently cached on disk in `var/cache/orb_sip/trades/`; it is not the +0.001R "figure of record" itself, which only exists after the 18 Sep entry-minute-only correction is applied on top of it.

## What's independently verified vs. still open

**Verified (high confidence):** for the 2,888 trades where the entry itself was ambiguous at 1-minute resolution (does the low touch the stop before or after the entry triggers, within that one minute?), the new engine's entry price matches the 18 Sep study's own independently-computed, ground-truth entry price **exactly, in all 2,888 cases** — split identically across all three of that study's outcome buckets (entry_first: 993/993, stop_first: 1,602/1,602, same_second: 293/293). It also correctly avoids charging a stop on `stop_first` trades at the entry second (matching the prior study's logic), while still finding 1,413 of those 1,602 (88%) genuinely get stopped out later in the day anyway — closely matching the 18 Sep study's own separate finding that "81.2% re-reach the same stop a minute or two later."

**Settled by the Correction, Spot-check and Write-up:** the 209 exit-reason disagreements are explained by entry-minute stop-order ambiguity (142 trades) and genuine, spot-checked intra-minute entry-price gaps (67 trades, no bad ticks, one fill-realism caveat on PPG) — not by any data-coverage gap. The remaining ~3,400 small same-reason price differences, plus these 209, together produce the full RESOLVED → full-second move.

**Still open:** none for this item's own scope; the fill-realism caveat on thin-print entries (PPG-style) is carried in the write-up as a footnote, not a blocker.

## Method and source files

- `strategy/orb/tensec_engine.py` (B0/T1 engine), `strategy/orb/tensec_g2.py` (parity run, unchanged — reverted), `strategy/orb/tensec_g2_diag.py` (diagnostic), `strategy/orb/tensec_g2_repair.py` (unwired repair utility, kept for reference), `strategy/orb/tensec_g2_full_resolved.py` (write-up script, new) — on `D:\Trading`.
- Ground-truth cross-check: `var/cache/orb_sip/entrybar_resolved.csv.gz` (from the 18 Sep study, `claude/orb_sip_RESOLVED_20260918.md`).
- Raw parity output: `var/reports/tensec_g2_parity.txt`, `var/cache/orb_sip/tensec_g2_trades.csv.gz` (both on D:\Trading) — this file is what the Correction's 209-trade breakdown and the Write-up's tables were computed from directly.
- Raw diagnostic output: `var/reports/tensec_g2_diag.txt` (D:\Trading).
- Raw spot-check output: `var/reports/w12_0005_entry_gap_spotcheck.csv` (D:\Trading).
- Raw write-up output: `var/reports/orb_sip_full_second_resolved.txt` (D:\Trading).
- Population: the 7,239-trade primary ORB SIP cell, in-sample (holdout untouched), exactly as registered in `docs/research/REGISTERED_10sec.md` §2.
- Caveat: the friction/net-R figures above use the registered BASE friction and $100-risk sizing (`strategy/orb/sip_report.py`), identical methodology to the published figures — only the entry/exit prices and reasons differ, sourced from the new engine's second-level walk instead of the one-minute bars.

Monday: W12-0005, Result doc column on that item (mirrored on monday, doc_id 3367505). W05-0003 subitem 4 references this.
