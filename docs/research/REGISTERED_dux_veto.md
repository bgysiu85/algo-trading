# REGISTERED — three long-side veto tags against Dux's short setups, fixed before the study runs

**Committed before any tagging code exists and before either book (backtest or live) has been
read for this study.** `PROGRAM_INDEX` §4: a hypothesis is registered before it is run. This is
a filter study on books that already lose money (MCL published PIT baseline (8.97)/trade, MC5
(8.57)/trade, `screen_pairs_pit_itch_v2.json`), so §4's abstention-control rule governs the read:
tagging is not evidence on its own, only a per-trade result against a matched random-removal
control is.

Board: **W03-0012**, subitem 1. Motivation: `claude/w05_0020_chart_fanatics_review_RESULT_20260927.md`
option A. Ben's decision, 2026-09-27 (W11-0032): option A, *"long-side veto study... no new data,
no shorting."*

---

## 0. PRE-RUN GATE — subitem 2 (the build-and-run) does not start until this is cleared

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | The three tag functions (`tag_crowded_gap`, `tag_dollar_block`, `tag_post_first_red_day`) are unit-tested against hand-built fixture cases before running against a real book: at least one true-positive and one true-negative per tag, and the boundary values exactly (gap = 100.0%, premkt volume = 50,000,000 shares, dollar block = $140M, a 3-green-day run whose cumulative range is exactly 300%, a 2-day run at exactly 1,000%). | Every gate this project has shipped has had its refusal/tag path unit- and mutation-tested before the study ran (`REGISTERED_drift_guard.md`, `REGISTERED_spread_gate.md` G2); a tag that is silently off-by-one at its own boundary is indistinguishable from a null result until it is checked there. |

No new data pull is required — see §3.

---

## 1. The claim, exactly

**Null:** MCL/MC5 long trades whose stock met a Dux short setup at entry carry the same per-trade
economics as the rest of the book.

**Alternative (per tag, tested separately — see §6 on multiplicity):** a trade tagged by one of
the three setups below loses *more* per trade than a matched random sample of untagged trades of
the same size, by a margin that clears this project's $4.26 friction bar, in both date-halves,
on a symbol-cluster bootstrap ≥ 0.95 — in which case the tag becomes a "do-not-buy" veto
candidate for MCL/MC5, on the drift-guard / spread-gate model (checked last, before the order
goes out, refuse and log).

This is a **veto study, not an entry-quality study**: nothing here selects a better trade; it
asks whether a computable pre-existing rule (Dux's) identifies trades this project would be
better off never taking. Framed this way it inherits the entry-gate literature already built
here (`first_entry_skip`, `range_rank`, `cold_veto`) and its central caveat — **on a losing book
a total-based reading rewards abstention** — applies with full force, hence §4's abstention
control being load-bearing rather than decorative.

## 2. The three tags, exact thresholds fixed now

**Universe note (Ben's "no new data" instruction):** none of the three tags gate on market cap,
float or sector — Dux's stated universe ($1–100M initial cap, 1–50M float, no biotech/energy/
China) needs point-in-time reference data this project does not own (`PROGRAM_INDEX` item 33,
"point-in-time float... nothing queued needs it"). The tags below run directly on MCL/MC5's
existing screened universe ($2–20, premarket volume ≥ 100k, gap ≥ 20% vs previous regular
close), which already skews toward small, thin, fast-moving names — the population Dux is
describing — but is not identical to it. Reported as a caveat, not corrected for (§7).

### Tag G — "crowded gap-up"

Fires when, **as of the entry bar** (the bar MCL/MC5 signals on):

```
gap_pct   = (running high-since-04:00, through and including the entry bar
             − previous regular-session close) / previous regular-session close × 100
premkt_vol = cumulative XNAS.ITCH shares traded from 04:00:00 through the entry bar's close

TAG_G = (gap_pct >= 100.0) AND (premkt_vol > 50,000,000)
```

Both numbers are Ben's, taken verbatim from the option-A text (not a range to pick within).
**Running high, not the entry bar's own close** — a stock whose morning pop has already stalled
and pulled back by the time MCL/MC5 signals is still "crowded" in Dux's sense; using the entry
bar's own price would silently exclude the fade cases his setup is built around. Source:
`bar_cache_xnas` / XNAS.ITCH pre-market minutes (owned) + `regular_close.json` (owned). Float
turnover (Dux's other crowding clause) is not tagged — not point-in-time computable here.

### Tag B — "overhead dollar block"

Operationalized from the RESULT doc's own coding note (§ "Extra rules worth coding"): *dollar
block = shares traded around the old consolidation price × that price*.

```
For each symbol, over the trailing 252 trading days before the entry date (or the symbol's full
IB daily bar_cache history if shorter — split-adjusted, per the hard rule):
  spike_day = the session with the LARGEST (close × volume) among sessions where
              (high - low) / low >= 100%   [a "spike" day, Dux's own gap-size language]
  IF no such session exists in the lookback window: TAG_B = False, no further computation.
  trapped_level = spike_day's close  (best available point estimate of "where the block traded";
                  this project has no intraday order-book data to locate it more precisely)
  dollar_block  = spike_day's close × spike_day's volume

TAG_B = (dollar_block >= $140,000,000) AND
        (entry-bar running high-since-04:00 is within +/-5% of trapped_level)
```

**$140M, not $130M or $150M.** Dux's own range is $130–150M; $140M is the round midpoint,
picked now rather than after seeing which end produces more (or better) tagged trades. Report
$130M and $150M as sensitivity endpoints (reported, never scored — the boundary-check standard,
§4) so a reader can see whether the verdict is sensitive to the exact cut. **±5% proximity** is
this project's own choice (Dux says only "as close to the level as possible"); a tight band was
picked over a wide one because a loose "near the level" band would tag ordinary continuation
moves that never actually contest the old block. **252-day lookback** bounds compute and keeps
the "spike day" recent enough to be a plausible resistance memory; a name with less than 252
days of owned daily history (or with none) reads TAG_B = False rather than searching an
unbounded past — documented as a limitation, not silently backfilled.

### Tag R — "day after first red day"

From the extraction, resolved where the transcript was ambiguous (flagged inline):

```
green day = close > previous close (split-adjusted IB daily bars)
red day   = close < previous close
run       = a maximal streak of consecutive green days, each with STRICTLY higher
            (close x volume) than the day before, of length >= 3
run range = (peak close of the run - close on the session immediately before the run
             started) / that pre-run close x 100
qualifying run =
    (len(run) >= 3 AND run_range >= 300%)  OR  (len(run) == 2 AND run_range >= 1,000%)
first_red_day = the first session after a qualifying run where close < previous close
giveback  = (run peak close - first_red_day's low) / (run peak close - pre-run close) x 100
SKIP (no tag) if giveback > 50%          [Dux's own skip clause: the move is already spent]

TAG_R fires on any MCL/MC5 entry whose session is the trading day immediately
following a qualifying, non-skipped first_red_day.
```

**Interpretive choice, PRE-RUN:** the transcript states "range ≥300%" against a run of ≥3 days
without saying explicitly whether that range is per-day or cumulative; this registration reads
it as **cumulative, start-of-run to peak** — consistent with how every other multi-day-runner
description in the same extraction (the exhaustion-by-dollar-volume rule, the bounce-short
level) refers to the whole move rather than a single session. If Build & test chat's read of
the source transcript disagrees, that is a PRE-RUN amendment to this document (before the
tagging code is written), not a POST-RUN one. The market-cap-bucketed exhaustion rule ("$1B
traded at the top under $50M cap...") is **not** tagged — it needs a point-in-time market-cap
bucket this project does not own, same gap as the universe filter above.

## 3. Data — all owned, nothing new bought

| Need | Source | Owned? |
|---|---|---|
| Pre-market minute bars, gap %, premkt volume | XNAS.ITCH `ohlcv-1m`, `regular_close.json` | Yes — the tape MCL/MC5 already run on |
| Daily bars for the spike-day and green/red-day lookbacks | IB `bar_cache` (split-adjusted) | Yes |
| MCL/MC5 entries to tag | `screen_pairs_pit_itch_v2.json` book (3,908 / 6,462 trades, current published baseline) | Yes |
| Live paper fills | `var/` fill ledger, all MCL/MC5 round trips to date | Yes |

No Databento pull, no IBKR request, no shorting, no borrow/locate data — matches Ben's "no new
data, no shorting" instruction exactly.

**See §9 (PRE-RUN amendment, 2026-09-27): the "IB `bar_cache` (split-adjusted)" row above turned
out to be wrong for Tag B/R's 252-day lookback — Tag G is unaffected.**

## 4. What the study must measure and report (subitem 2, Build & test chat)

Same bar as this project's other entry-gate work (`REGISTERED_spread_gate.md` §4,
`common/gate_study.py`'s five readings), adapted for three tags instead of one and for a second,
much smaller live-fills arm that is reported but never pooled with the backtest arm (agreement
between two different trade sets is not replication — §4):

1. **Cost, per tag, per strategy, per arm (backtest / live fills), separately:** count and % of
   book tagged; net $ tagged vs untagged; per-trade tagged vs untagged; win rate tagged vs
   untagged. Backtest arm at all three friction levels ($1.00 / $4.26 / $8.92); live arm at its
   own realized fills, no friction model needed.
2. **The abstention control — this is the verdict, not a supporting table.** For each tag, draw
   2,000 random same-size samples from the untagged+tagged pool (matched count to the tagged
   bucket) and report the 5th/50th/95th percentile of per-trade net. A tag only reads as
   selecting for losers if the tagged bucket's actual per-trade net sits **below** (worse than)
   the control's 5th percentile — not merely below the book average, which a total-based read
   would reward by abstention alone.
3. **Precision / recall as a loser-detector:** of tagged trades, % that actually lost (true
   positive) vs won (false positive); of untagged trades, % that lost anyway (false negative,
   what the tag does not catch).
4. **Full-bars treatment:** drop-top-N (N = 1, 3, 5) on the tagged-vs-untagged delta; both
   halves split at the median entry date; symbol-cluster bootstrap (10,000 resamples, every
   trade of a drawn symbol travels with it) on the delta, required ≥ 0.95.
5. **What each tag removes among the winners, not only the losers** — a veto that also refuses
   the book's best trades is a cost even where it removes more losers than winners overall.
6. **Overlap:** how many trades fire more than one of the three tags, and how many the existing
   drift guard / spread gate would already have refused (overlap, not double-counted).
7. **Sensitivity, reported and never scored:** Tag B at $130M and $150M beside the registered
   $140M.
8. Deliverables per the standing rule: a monday Result doc (plain language, tables in dollars,
   negatives bracketed), the raw `.txt`, a published artifact page, all three per tag or one
   combined doc covering all three — Build & test chat's call, so long as each tag's own verdict
   is separately stated.

## 5. Verdict, fixed now — per tag

- **PASS → recommend shipping as a live veto** (checked last in `trader.py`, alongside the
  drift guard and spread gate, refuse-and-log on a `SKIPPED_DUX_<G|B|R>` row): clears §4 item 2
  (below the abstention control's 5th percentile) **and** both halves **and** the bootstrap
  **and** the two denominators (per-trade, per-symbol-day) agree **and** the live paper-fill arm
  does not disagree in sign (it need not itself clear a bootstrap — n is far smaller than the
  backtest book).
- **STUDY-ONLY:** the backtest arm clears §4 item 2 and the bootstrap, but the live arm is too
  small to be informative or disagrees in sign. Measured and reported, not enforced live.
- **REFUSED / NOTHING** (this project's standard vocabulary): the tagged bucket does not clear
  the abstention control, or a half is empty/reversed, or the two denominators disagree.

Nothing in this document commits to shipping any of the three; the thresholds are fixed so the
study answers cleanly, not so the answer is chosen after seeing it.

## 6. Multiplicity

Three tags are three separate hypotheses (`PROGRAM_INDEX` §4: "multiplicity is counted by
family, not column"). A result doc that reports three PASSes should say so as three families,
not fold them into one headline; a study that finds exactly one of three tags interesting is a
plausible, not a suspicious, outcome, and finding all three would be the more surprising result
worth double-checking (e.g. against the drift guard's own already-measured refusals, §4 item 6).

## 7. Caveats — what this registration does not claim

- **Universe mismatch.** The tags run on MCL/MC5's screened universe, not Dux's stated
  cap/float/sector-filtered one (§2). A trade this study tags may not be a trade Dux himself
  would ever have looked at; the question is only whether his *rule*, applied mechanically to
  our universe, separates our winners from our losers.
- **`trapped_level` is a daily-close proxy, not an order-book level.** This project owns no
  intraday depth data for prior sessions; the $140M dollar-block figure is therefore a volume×
  price estimate, not a measured trapped-share count.
- **Tag R's cumulative-range reading is an interpretive choice** (§2), not a verbatim transcript
  quote, and is named as an amendment point if Build & test chat's own reading of
  `claude/raw/w05_0020_chart_fanatics_extracts_20260927.txt` disagrees.
- **A veto is a filter on an already-losing book.** Per §4, "a filter on a losing book cannot
  help by abstaining" — a PASS here makes MCL/MC5 lose less, not turn a profit; it does not
  reopen either book as a candidate on its own (same footing as the give-back cap's pass on
  MC5, `session_scenarios_RESULT_20260918.md`).
- **Self-reported source.** Dux's setups are hand-kept-spreadsheet claims (win rate, frequency)
  which this study does not test — it only tests whether the setups' *entry conditions*, applied
  mechanically, correlate with this project's own trade outcomes.

## 8. Timeline

1. **W03-0012 subitem 1 (this document):** register the three tags and the verdict; commit
   before subitem 2 starts.
2. **W03-0012 subitem 2 (Build & test chat):** clear gate G1 (§0); tag the backtest book and the
   live fills ledger; run §4's readings; write the Result doc(s), raw `.txt`, artifact page.
3. **Ben:** per tag, ship as a live veto / study-only / close (§5).

---

## 9. PRE-RUN AMENDMENT — 2026-09-27, Build & test chat: Tag B/R has no owned data source

**Found while building the tagging code (subitem 2), before either tag was run against any real
book.** §3's data table asserted Tag B and Tag R's 252-session daily lookback is owned via "IB
`bar_cache` (split-adjusted)". Direct inspection of the repo shows this is wrong:

- `bar_cache/3d_to_2000/` is IB **minute** bars, **three sessions deep**, covering 443
  (symbol, entry-date) pairs total — an old, small, non-daily cache built for a different
  purpose, not a 252-trading-day daily archive over the PIT universe.
- No split-adjustment table or split-adjusted daily archive exists anywhere else in the repo
  either. Databento's daily bars cover the whole tape but are explicitly **not** split-adjusted
  (`PROGRAM_INDEX` §5: *"a 1-for-10 reverse split prints as a ~900% overnight gain"*) — exactly
  the artefact `tag_dollar_block`'s "spike day" and `tag_post_first_red_day`'s "green run" would
  misread as real, the VW9 bug class (`PROGRAM_INDEX` §1: *"a strategy without the price band
  trades the adjustment factor"*).

So Tag G ("crowded gap-up") is fully unblocked — it only needs the entry session's own owned
XNAS.ITCH pre-market bars and `regular_close.json`, both already in hand — but Tag B and Tag R
cannot be run against the real book without a decision on where their daily history comes from.
`common/dux_veto.py` is written and unit-tested (G1 clear, 34/34 fixture tests passing,
including every named boundary value) for all three tags, but its CLI **refuses to run
`--tags B` or `--tags R`** without an explicit `--daily-source`, rather than silently running on
an unadjusted or too-shallow archive.

**Options for Ben — pick one, or close B/R and ship G alone:**

| # | Option | Cost | Risk |
|---|---|---|---|
| A | Pull real IB split-adjusted daily bars for the PIT universe, 252 sessions back | A new IB history request — technically the *existing* split-adjusted vendor, not a new one, but still new data pulled for this study. Tension with "no new data, no shorting" — Ben's call whether that instruction meant "no new venue/vendor" or "no new pull of any kind." | Low once pulled — same vendor already trusted elsewhere |
| B | Use Databento daily bars with a split-guard heuristic (detect an overnight ratio consistent with a known split factor, e.g. 2:1/3:1/1:10, and adjust before computing spike-day/green-run) | Extra engineering (a splits detector + adjustment pass), no new vendor | Medium — a heuristic can miss an odd-ratio split or false-positive on a genuine gap; needs its own unit tests against real split cases before trusting Tag B/R's numbers |
| C | Close Tag B and Tag R now; ship Tag G alone per §5's "REFUSED / NOTHING" vocabulary (not evaluated for lack of data, not failed on the merits); revisit if a split-adjusted daily archive gets built for other work | None now | None — leaves two of Dux's three setups untested, but Tag G alone is still a real answer to option A's original question for the crowded-gap-up case |

This registration's thresholds and reading rules (§2, §4, §5) are unchanged by this amendment —
only the data-source question for B/R is open. Tag G proceeds under the existing registration
without modification.
