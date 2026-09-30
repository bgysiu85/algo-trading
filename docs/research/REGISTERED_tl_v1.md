# REGISTERED — TL-v1: Tori Trades' own line construction + "A+" checklist, coded, on CME futures, daily

**Committed before any TL-v1 code exists, before its pre-flight is run, and before any return of
TL-v0 / TL-v0-rev (W15-0014), TL-bounce (W15-0016) or HTF-Ben v1 (W15-0011) has been seen.**
`PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0018** (Ben's decision + this registration), W15-0017 (channel sweep and gap analysis,
Result doc https://ben-siu.monday.com/docs/5031564077), **W15-0019** (free steps: engine, Pine
indicator, guards, parity, count-only pre-flight), **W15-0020** (backtest). Source:
`claude/w15_0017_tori_gap_analysis_RESULT_20260926.md` gaps 1–2, from the Step 2 collation of 79
videos (https://ben-siu.monday.com/docs/5031564014).

Ben's decision, 2026-09-26, in his words: *"go with option A"* — option A being: register her line
construction + A+ checklist now, as the trend-line line's last registered hypothesis, before
W15-0014's P&L is read.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result
is a new hypothesis, and this line has no budget left for one (§9).

---

## 0. Where this sits

- **Line budget.** `REGISTERED_tl_v0.md` §9 allowed two further hypotheses. TL-bounce used one.
  **TL-v1 uses the last.** After it the trend-line line takes no new registration; a further one
  needs a reason that does not begin with a result.
- **What it is.** TL-v0-rev with **only the entry side changed**: the action line is drawn her way
  (from the extreme swing, touching as many points as possible), and a break is taken only if it
  passes her A+ checklist. The safety line, weekly filter, reversal, sizing, costs, series, rolls
  and fills are **TL-v0-rev's, word for word** (`REGISTERED_tl_v0.md` §2.1–§2.2). So the result
  answers one question: *does her line-drawing and setup selection add anything over v0-rev and
  over a Donchian channel?*
- **Why the safety line is not changed.** Her stop trail is redrawn steeper through each new
  pullback (previous point B becomes new point A). Through the two latest swing lows, TL-v0's
  existing safety line is already that chained trail (gap analysis row 6: covered). Changing it
  too would mix two questions.
- **Not a change to TL-v0, v0-rev or TL-bounce.** All stand; none is re-scored because of this.
- **What has been seen.** Her self-reported trades and her 2024 tally (16 trades), from videos
  only. No bar of any market has been read by this study. The May 2026 CL short (TL-v0 fidelity
  trade) and the 2025-09-23+ CL 4-hour charts (W15-0008) are inside this study's holdout or seen
  window and are not used to set anything.

---

## 1. The hypothesis, in one sentence

**Taking only trend-line breaks that meet Tori Trades' A+ checklist (a line drawn from the extreme
swing that has been touched at least three times over more than a week, in a market that is
trending) — with TL-v0-rev's safety line, reversal, sizing and costs — makes money after measured
costs on the owned GLBX daily history of the TSMOM markets, beats a 20/10 Donchian channel on the
same markets, sizing and costs, and beats a random selection of the same number of breaks of the
same lines.**

---

## 2. The rules

Parameters are chosen here, before any data is read. **None of the numbers comes from her**; she
gives words ("three touch points", "more than a week of data", "trending, not consolidating"), and
these are the codings of them.

### 2.1 Inherited from TL-v0 / TL-v0-rev unchanged

Execution chart (**daily**), markets (TSMOM archive roots, rates arm MTN), pivot ensemble
(**equal-risk L = R ∈ {3, 5, 8}**, each alone reported), ATR(14), difference-back-adjusted signal
series, held-contract P&L with the TSMOM roll rule incl. Amendment C, **weekly top-down filter**
(completed weeks), **v0-rev safety line** (opposing weekly line ∓ 0.25 × daily ATR, falling back to
the daily two-latest-pivot line, then the swing fallback), stop never loosens, fills at the stop or
the gapped open, no target, **v0-rev reversal** (§2.4 below), **1% risk sizing, zero = skip,
counted**, friction **$0.50 / $1.25 / $2.50** per contract per side + one tick on every stop fill.

"Pivot" below = a confirmed `pivothigh/pivotlow(L, R)` of the sleeve's L, which exists from bar
i + R. "Touch pivot" = a confirmed pivot with **L = R = 2** (all sleeves), which exists from bar i + 2.

### 2.2 The action line — her construction (gap 1)

Resistance line (for long entries; support is the mirror image, for shorts), computed **at the
close of every bar t from pivots confirmed by t**, and used on bar t + 1:

| Step | Rule | Her words |
|---|---|---|
| **L1 Window** | Pivots whose bar lies in the last **W = 250** bars | "extreme visible pivot" |
| **L2 Anchor A** | Take the window's pivots in order of price, highest first. The first one from which a valid line (L3–L4) exists is A | point A = extreme visible pivot |
| **L3 Point B** | Among pivots after A, the one giving the **largest slope** from A (the line lies on or above every later pivot high). The slope must be **negative** (falling); if not, try the next A | "point B = next pivot price hasn't crossed"; ray tool |
| **L4 Never crossed** | Invalid if any close from A's bar to t is above the line by more than **0.10 × ATR** at that bar. Wicks through do not invalidate *(she may include wicks; coded on closes, as TL-v0)* | "never draw a line where price has already crossed it" |
| **L5 Span limit** | A to t ≤ **400** bars (as TL-v0) | — |

No valid A → no resistance line at t. The line is recomputed each bar, so a wick above it that
forms a new confirmed pivot moves the line up to that pivot — that is her redraw, done only with
confirmed pivots.

### 2.3 The A+ checklist (gap 2) and the entry

A long signal needs **all** of the following, judged on bar t's close:

| # | Rule | Her words |
|---|---|---|
| **E1 Break** | close[t] > resistance line in force at t (computed at t − 1's close) + **0.10 × ATR[t]** → enter at the **open of t + 1** (as TL-v0) | break, candle close |
| **A1 Touches ≥ 3** | Count touch pivots from A's bar to t − 1 whose high ≥ line − **0.25 × ATR** at that bar (A and B count if they qualify). Need **≥ 3** | "three touch points" — her 3-touch playbook |
| **A2 More than a week** | Calendar time from A's bar to the **last counted touch** ≥ **7 days** | "more than one week of data" |
| **A3 Trending** | Efficiency ratio ER(20) = \|close[t] − close[t−20]\| ÷ Σ\|close[i] − close[i−1]\| over the 20 bars. Skip if ER(20)[t] < **q25 of that market's** ER(20) over **training bars only** | "trending, not consolidating" |
| **A4 Near the stop line** | Not a separate rule: 1% risk ÷ stop distance already shrinks size as the stop gets farther, and skips when zero contracts fit (§2.1) | "close to the safety line, else reduce size" |
| **E2 Weekly filter** | As TL-v0 | top-down |

Counted, per market and year: breaks, failing A1, A2, A3, the weekly filter, skipped for size.

#### Amendment E — PRE-RUN (W15-0019, G2 pre-flight, run 2026-09-29 on the training side 2010-06→2021-12)

A3's training-only ER(20) percentile thresholds, per market, from `common.tl_v1_preflight`
(`var/reports/tl_v1_preflight.txt`, committed alongside the code at 306cecf). A3 uses **q25** per
the table above; q20/q33 are carried for the §3 neighbour grid only, not for A3 itself.

| Market | q20 | q25 (used by A3) | q33 |
|---|---|---|---|
| ES | 0.084 | 0.104 | 0.140 |
| RTY | 0.074 | 0.100 | 0.129 |
| CL | 0.087 | 0.109 | 0.147 |
| NG | 0.075 | 0.095 | 0.125 |
| 6A | 0.076 | 0.094 | 0.127 |
| 6B | 0.074 | 0.093 | 0.126 |
| 6E | 0.073 | 0.091 | 0.120 |
| 6J | 0.067 | 0.086 | 0.117 |
| GC | 0.079 | 0.103 | 0.134 |
| SI | 0.088 | 0.110 | 0.148 |
| HG | 0.071 | 0.090 | 0.120 |
| MTN | 0.067 | 0.086 | 0.121 |

**§5.2 stop rule, read on this run:** 1,025 TL-v1 entries, all markets, all three pivot sleeves
(R=3: 454, R=5: 335, R=8: 236) — clears the 150-entry floor. **G2 is cleared; the study is not
underpowered on this reading.**

**Also observed, reported here since it bears on §7's "not to be done" list and §8's risk list, not
because it changes any rule:** A2 (the ≥7-day span test) failed on **zero** breaks across every
market and pivot size in this run. At W=250 with L=R∈{3,5,8}, an anchor-to-point-B span under 7
calendar days essentially cannot occur — A2 is not doing any filtering work in this coding. A1
(touches≥3) and A3 (trending) are the checklist's two active gates; A1 is materially the stronger
of the two (645/520/408 failures vs. 369/325/266 for A3, by pivot size). This is a finding about
the coding, not a rule change — §2.3's A2 stands as registered.

#### Amendment F — PRE-RUN (W15-0019, G3 Pine↔Python parity, closed 2026-09-29)

Two comparisons were run, both CL1! daily, 2015–2019, back-adjustment off, pivLen (L=R) = 5:

1. **Pine vs. the Databento archive.** `pine/TL_v1.pine`'s two plotted lines against
   `common/tl_v1_lines.py`'s `build_series()` fed the archive's raw OHLC (`ro`/`rh`/`rl`/`rc` —
   not the difference-back-adjusted signal series §2.1 uses for the actual backtest, which the
   comparison script initially read by mistake and was corrected before this run): **~85%
   mismatch on both lines**, not clustered by roll date the way `REGISTERED_tl_bounce.md`
   Amendment 1 found.
2. **Self-consistency: Pine vs. Python, same data.** The same Python code run on **TradingView's
   own exported OHLC** (the identical CSV Ben's chart produced, no archive involved) against
   Pine's own plotted line: **805/813 Resistance bars and 798/847 Support bars matched within
   1 cent** (85–98%). The residual mismatches are small (deltas $0.50–$2.70) and localized (a
   line armed a few weeks earlier or later on one side, in isolated stretches) — the same shape
   Amendment 1 accepted for TL-bounce's own G3.

**Finding.** Check 2 shows `common/tl_v1_lines.py` is a correct port of §2.2's line-construction
algorithm: given the same prices Pine sees, it reproduces Pine's own line almost exactly. Check 1's
much larger mismatch is not a code defect — TradingView's CL1! and the Databento archive's own
continuous-contract construction are different price series, and L2's anchor picks the single most
extreme price in a 250-bar rolling window, so a difference in the underlying feed (not just a
roll-day offset) is enough to select an entirely different anchor and produce a line that never
converges, however long the two are compared.

**Ben's decision, 2026-09-29, in his words:** *"for §5.1 G3, let's go with python"* — G3 is closed
on check 2 (the self-consistency result). A direct Pine-vs-archive comparison (check 1) is not
treated as a meaningful test of the port: Pine has no way to see the archive's own feed, so it
cannot be expected to match it bar-for-bar regardless of how correct the code is.

**G3 is cleared on this basis** (§5.1's gates table and §7 updated below). W15-0020 is unblocked by
G3; it remains blocked only on W15-0014's C2 reference run.

#### Amendment G -- PRE-RUN (W15-0020 engine build, 2026-09-29, before any TL-v1 P&L exists or has been read)

Coding of sec 2-4 wording that admits more than one reading. Each is fixed here; none comes from a
result (no TL-v1 P&L has been computed by anyone). The code is `strategy/tl_v1/` and the small
backward-compatible `qual_up/qual_dn` extension of `strategy/tl_v0/sim.py`, committed before the run.

1. **Exit vs entry (sec 2.4).** An opposite *raw* line break (close beyond the support/resistance line by
   > 0.10 x ATR) always exits at the next open. It reverses only if that break is A+ (A1-A3) and passes the
   weekly filter; otherwise the walk goes flat. In-position same-side breaks are ignored (as v0-rev).
2. **A2 as registered.** Calendar days from A's bar to the *last counted touch* >= 7. The G2 pre-flight
   measured A's bar to the *break* bar (Amendment E's "A2 failed on zero breaks" is that reading). The report
   prints both counts. Neither changes a threshold.
3. **Criterion 2 "median trade date".** Split at the median *entry* date of the verdict book's trades;
   each half = net at mid of the trades that entered in it; an empty half fails.
4. **C3 matching.** Pool = every sec 2.2 break agreeing with the weekly filter; each draw picks, per market and
   pivot size, as many of them as TL-v1 has A+ breaks agreeing with the weekly filter (matched on breaks, not on
   filled entries, which depend on the path); same v0-rev simulator. Draw d is seeded
   `default_rng([crc32(str(d)), crc32(market), R])`. The median filled-entry count of the draws is printed
   beside TL-v1's.
5. **Verdict book.** Fractional ensemble at $22,129, mid friction (TL-v0 Amendment B, inherited by sec 2.1);
   integer book at $22,129 printed beside it. Criteria 7 (concentration) is "not read" (counts as not passed)
   when net <= 0.
6. **Breaks masked** where the repo's gated ATR(14) is unknown (first 13 bars); the line and touch tests use the
   pre-flight's ATR.
7. **Not in W15-0020:** the CL 4-hour variant (sec 2.5) and the seen window. The 4-hour variant needs the
   ohlcv-1h 4H-bar pipeline and HTF-Ben's costs; it is board item **W15-0027**, reported only, and cannot spend
   the holdout. The seen window lies inside the holdout region the training runner cannot read.

### 2.4 Exits and reversal — v0-rev, with one clarification

- Safety line and stop: v0-rev, unchanged.
- **Opposite break:** a close below the **support** line (built by §2.2's mirror) by more than
  0.10 × ATR → exit at the next open. **Reverse only if that break passes A1–A3 and the weekly
  filter**; otherwise go flat. *(v0-rev reverses on any qualifying entry; here "qualifying" means
  A+.)*

### 2.5 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| TL-v1−A+ | §2.2 lines, every break taken (no A1–A3) | whether her *line* differs from v0-rev's |
| TL-v1−A3 | no trending filter | whether A3 earns its place |
| TL-v1 2-touch | A1 = ≥ 2 | her 2-touch playbook |
| Each pivot size alone | L = R 3, 5, 8 | as TL-v0 |
| **CL 4-hour** | her chart: CL only, 4-hour bars from `ohlcv-1h` on the 18:00 New York session (as `REGISTERED_tl_bounce.md` §2.1); daily in place of weekly for the filter and safety line; costs as HTF-Ben v0 Amendment A, per 1 MCL | whether it looks different where she trades it |

**Known departures, not coded:** wick-based line validity; her chained multi-timeframe ladder
(monthly → execution); S/R, double confirmation and news; break-and-retest; the volatility overlay;
one instrument at a time; her 4–15% risk.

---

## 3. What every run must emit

`REGISTERED_tl_v0.md` §3 items 1–10 unchanged, for TL-v1 and every variant. Additions:

- **Counts:** breaks; failing A1 / A2 / A3 / weekly; entries; reversals; flats after a blocked
  reversal; skipped for size; median touches and median line span (days) at entry.
- **Controls — same markets, bars, fills, sizing, costs and v0-rev exits:**
  - **C1** Donchian 20/10 (as TL-v0).
  - **C2** **TL-v0-rev** itself, as registered (reference; from the W15-0014 run, not re-run).
  - **C3** **Random selection:** TL-v1−A+'s breaks (every break of §2.2 lines, weekly filter on),
    thinned at random to TL-v1's entry count per market; 1,000 seeded draws (crc32 of draw number);
    p5 / p50 / p95 of net. Answers "does the checklist beat picking the same number of breaks of
    the same lines by chance?"
- **Neighbour grid (27 cells, unranked):** touch buffer {0.15, 0.25, 0.35} × ATR × window W
  {125, 250, 400} × ER percentile {20, 25, 33}; net at mid friction per cell and the share positive.
- **Seen window, reported only** (2025-09-23 → end of data), labelled "seen — not evidence".

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — TL-v1, daily, ensemble, 1% sizing, mid friction, training side

Passes only if all hold:

1. Net > $0 at mid friction ($1.25/side).
2. Both halves net > $0 (split at the median trade date; an empty half fails).
3. drop-top-1 and drop-top-2 by market still > $0.
4. Bootstrap by market and by calendar year (2,000 seeded resamples each): net > 0 in ≥ 95%, each.
5. **Beats C1 (Donchian)** on net and on net per unit of realised volatility.
6. **Beats the p95 of C3** (random selection) on net.
7. No single year and no single market supplies more than 50% of net.
8. Still net > $0 at high friction ($2.50/side).
9. At least **18 of 27** neighbour cells net > $0.
10. **At least 150 trades.** Fewer → NOT READ, not failed.

**Failing 5 or 6 closes the study whatever else passes.** C2 (v0-rev) is reported beside it, not a
criterion: both are registered hypotheses and neither is chosen over the other on a result (§6).

---

## 5. Before the backtest — no P&L in this section

### 5.1 Gates

| # | Gate | Why | Status |
|---|---|---|---|
| G1 | **Data:** the TL-v0 daily archive (as `REGISTERED_tl_v0.md`); CL 1-hour for the 4-hour variant (HTF-Ben v0 G1, passed under Amendment B). No new data | Same bars | Cleared (reused, no new data) |
| G2 | **Pre-flight** (5.2) run and read; ER q20/q25/q33 per market written in here as PRE-RUN | Enough trades? | **Cleared 2026-09-29 — see §2.3 Amendment E** |
| G3 | **Pine ↔ Python parity** for the §2.2 line and A1–A2 on CL1! daily, 2015–2019, back-adjustment off: same A, B, touch count and break bars, mismatches listed, zero tolerated or each explained. Pine delivered as a file for Ben to paste; **never written into Ben's Pine Editor by a chat** | New line code; lets Ben eyeball it against how she draws | **Cleared 2026-09-29 — see §2.3 Amendment F (self-consistency check; Ben's call to close on it)** |
| G4 | **Holdout** (§6) cut and ledger in code, mutation-tested | `PROGRAM_INDEX` §1 | Cleared (`common/tl_v1_holdout.py`, tested, 306cecf) |
| G5 | **Look-ahead guards**, each broken by a one-bar shift in a test: the line in force at t uses only pivots confirmed by t − 1's close; touch pivots confirmed by t − 1; ER percentiles from training bars only (a test fails if a holdout bar changes them); weekly filter on completed weeks | Her replays are drawn on finished charts | Cleared (tests/test_tl_v1_hindsight_guard.py, 306cecf) |
| G6 | **W15-0014's engine and gates G3–G5 done** (TL-v1 reuses them) | One engine, not two | Cleared |

**All gates are cleared. W15-0020 is blocked only on W15-0014's C2 reference run being available.**

### 5.2 G2 pre-flight (training side only: 2010-06 → 2021-12)

For TL-v1, each §2.5 variant and C3's pool, per market per year: breaks, failures by A1/A2/A3/weekly,
entries, reversals; median touches and span; initial stop distance in $ per micro where one exists
(else per full contract); share sizeable at 1% and 2% of $22,000. **No exit price is read and no P&L
is computed; the runner refuses both in this mode.**

**Stop rules, fixed now:**
- Fewer than **150 TL-v1 entries** on the training side (all markets, ensemble) → stop as
  underpowered, reported as the finding, back to Ben before any P&L.
- TL-v0 §5.1's sizing rule applies unchanged.

**Run 2026-09-29 (see §2.3 Amendment E for the full table):** 1,025 entries — clears the stop rule.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31 (as TL-v0).
- **Holdout:** sessions from **2022-01-03 through 2025-09-22**, own cut file and ledger
  **`holdout_tl_v1.json`**. **Spent once**, by TL-v1 (daily, ensemble, mid friction, the ten
  criteria). Refuses `--limit` and every narrowing flag; mutation-tested. The TSMOM, TL-v0,
  TL-bounce, HTF-Ben (v0, v1), H60 and equity holdout files are refused by name.
- **Overlap with TL-v0's holdout (2022+).** Both are registered before either result is seen. If
  both v0-rev and TL-v1 qualify to spend, **both holdout results are reported together**; neither
  is picked after seeing the other.
- **Seen window:** 2025-09-23 onward. Never scored; reported only.

---

## 7. Registered as NOT to be done

- Tuning any threshold (touches, span, ER percentile, W, buffers) to her trades, her 2024 tally,
  Ben's charts, or anything from 2022 on.
- Changing the ER percentiles after G2 writes them in.
- Swapping a variant or grid cell (including 2-touch or the 4-hour chart) in for TL-v1 after a result.
- Changing the safety line, adding a target, S/R, news, break-and-retest or pyramiding after a
  result. This line has no registrations left.
- Quoting gross, the 4-hour variant, or a single market as the headline.
- Writing to Ben's TradingView Pine Editor from any chat.

---

## 8. Ways this could go wrong

- **Too few trades.** Three touches plus a trending filter may leave very few breaks. The pre-flight
  stop rule decides before any P&L. *(Resolved 2026-09-29: 1,025 entries, clears it — see §2.3
  Amendment E.)*
- **"Touch" is generous or strict by construction.** 0.25 × ATR on L = 2 pivots is a coding of her
  eye; the grid shows 0.15 and 0.35.
- **Extreme-anchor lines are long and shallow.** A break of a line anchored a year back can come
  late in a move. That is her method; C1 and C3 show whether it helps.
- **The checklist may just select trends.** A3 (ER) is itself a trend filter; TL-v1−A3 and C3
  separate the checklist from generic trend selection.
- **Her A+ includes judgement we don't code** (which line she chooses to draw at all). The result
  tests *her stated checklist*, not *her*.
- **Roll gaps as breaks, weekly peeking, gapped stops** — as TL-v0 §8.
- **A2 (the span test) may not be doing anything.** The G2 pre-flight found A2 failed on zero
  breaks in any market or pivot size (§2.3 Amendment E) — worth knowing when reading §3's counts,
  though §7 bars changing the rule now.
- **G3's comparison window can't be made to match TradingView's own feed.** Resolved 2026-09-29
  (§2.3 Amendment F): the Pine-vs-Python port is verified correct by a self-consistency check on
  TradingView's own data; the port is not re-checked against the archive's own feed, which is a
  different data source Pine cannot see.

---

## 9. Multiplicity budget

Families: construction/selection (fixed, with its ablations reported), pivot ensemble (as TL-v0),
grid (robustness only), friction (not a search). One holdout spend. **This is the trend-line
line's last registration** (`REGISTERED_tl_v0.md` §9: two further; TL-bounce was one, this is the
other).

---

## 10. A prediction, written down now

**TL-v1 keeps about 20–35% of TL-v1−A+'s breaks, roughly 150–300 trades on the training side
(close to the stop rule). Its win rate is higher than v0-rev's, but net per trade is about the same
and it does not beat the p95 of random selection (criterion 6), because on daily futures the
checklist mostly picks long, established trends — which a random pick from the same lines also
catches. It beats Donchian no more often than v0-rev does.** If that happens the reading is: *her
checklist describes her trades well but doesn't select better ones when applied mechanically; what
remains of her edge is the judgement that isn't in the checklist.* I'd be glad to be wrong.

*(2026-09-29 note: the pre-flight's actual entry count, 1,025, ran well above the "150–300" guessed
here — a break-count, not a P&L, read; the prediction itself is unaltered and unscored until
W15-0020.)*

---

## Next steps (board)

- **W15-0019** — build (on W15-0014's engine): §2.2 line code, A1–A3, Pine indicator file (G3),
  guards (G5), holdout cut (G4), count-only pre-flight (G2, writes the ER percentiles in here as
  PRE-RUN) — **code, tests, holdout, pre-flight and G3 parity all done (306cecf + the parity
  script commits, 2026-09-29); all gates cleared, item complete.** Build & test chat, Sonnet ·
  Medium. Pre-flight ran on Ben's PC.
- **W15-0020** — backtest, training side, Result doc. Blocked only by W15-0014 (C2 comes from
  it); W15-0019's G3 is cleared. Build & test chat, Sonnet · Medium; runs on Ben's PC.
- **W15-0014** — the P&L hold is lifted: TL-v1 is registered.

---

## POST-RUN note -- W15-0020 result (2026-09-29; no rule, threshold or variant above was changed by it)

Training-side run, `strategy/tl_v1` at commit 70231c9, report `Claude outputs/tl_v1_backtest_20260929.txt`,
Result doc on board item W15-0020.

- **Verdict: DOES NOT PASS.** Criteria 1, 5, 8, 9, 10 pass; 2, 3, 4, 6, 7 fail. Criterion 6 failed (net $775 vs the
  C3 p95 of $2,340; TL-v1 sits at the 68th percentile of 1,000 random selections), so under sec 4 **the study closes**.
  The TL-v1 holdout was **not spent** (sec 6 needs all ten). This was the trend-line line's last registration (sec 9).
- **Sec 10 prediction, scored.** Right: it does not beat the p95 of random selection. Wrong: trades (636, not 150-300 --
  already noted above), win rate (33% vs v0-rev's 35%, not higher), and it did beat Donchian on net and net/vol
  (C1 was itself negative at ($847)), which v0-rev did not.
- A2 as registered failed on 754 of 4,057 breaks (the pre-flight's A-to-break reading fails none), so it does some work.


## POST-RUN note, 2026-09-30 (W15-0033) -- TL-v1 re-quoted at IBKR costs; no rule, bar or verdict changed

Ben switched the program to IBKR costs. Costs are per trade, so the closed result is re-quoted from its own trade file, no re-run: ensemble fractional at $22,129: v1 $775 old mid -> $606 IBKR mid ($27 at IBKR high, $1,185 at IBKR low); C1 ($847) -> ($1,408). Verdict unchanged (it failed criterion 6, not on cost). Full tables (every spec, R, sizing, low / mid / high): `Claude outputs/w15_0033_requote_ibkr_20260930.txt` (script `tools/w15_0033_requote_ibkr.py`). The registered NinjaTrader-era figures above remain the record of what was tested.
