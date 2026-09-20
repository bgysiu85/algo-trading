# REGISTERED — SPY intraday momentum, the DATA decisions

Amendments to `claude/spy_intraday_spec_20260917.md`. Every item below is
**PRE-RUN**: written and committed before any P/L for H-S1, H-S2 or H0 exists.
Section references are to that spec.

The spec left three things open and said to close them before running. This
closes them, and records one measurement the spec assumed.

---

## A (PRE-RUN) — The data channel. Which sources were checked, and what each reached

Spec §4 lists IBKR, Databento and Alpha Vantage in preference order. All three
were tested on 2026-09-17, along with everything else reachable, before a line
of pulling code ran:

| channel | reached | note |
|---|---|---|
| **IB `reqHistoricalData` via Gateway** | **the only channel that can reach the window** | measured by `--probe`, see D |
| Alpha Vantage `TIME_SERIES_INTRADAY` | nothing | premium endpoint on the current key; re-confirmed, not taken on trust |
| tvremix (headless TradingView) | 30m back to **2025-03-05** | hard cap of 5,000 bars per call, no offset parameter — it cannot be paginated backwards |
| TradingView desktop MCP | 500 bars per call | not a bulk channel |
| IBKR MCP `get_price_history` | errors | other IBKR MCP calls on the same login answer; §5 says the MCP connector and IB Gateway are mutually exclusive, one session per login |
| Databento, and any public HTTP | nothing | no network egress from the analysis environment at all |

**This is recorded because "we used IB" is not the same statement as "IB was
the only thing that could do it."** The second one is what makes the window in
D a measurement rather than a preference, and it means a future reader who
wants a longer window knows the alternatives were already tried.

---

## B (PRE-RUN) — The four prices are 30-minute bar CLOSES, and the reasons

With `useRTH=True` the RTH 30-minute grid is exactly thirteen bars labelled by
interval **start**: 09:30, 10:00, … 15:30. So

```
10:00 price        close of the 09:30 bar
15:30 price        close of the 15:00 bar
16:00 price        close of the 15:30 bar
prior 16:00 close  the PRIOR session's last close   (see C)
```

Closes throughout, never the next bar's open. On SPY the two are usually the
same number, which is exactly why the choice has to be written down: a rule
that is ambiguous and usually agrees is the kind that silently disagrees on
the sessions that matter most — the gaps.

`r12` (15:00→15:30) is computed for the reported-not-scored double filter of
§7 and is scored in nothing.

---

## C (PRE-RUN) — Prior close is the prior session's LAST close, not its 15:30 bar

Spec §4 requires half-days to be excluded and counted. It does **not** say to
exclude the session *after* a half-day, and that session must not be lost:

> On a half-day the market closed at 13:00 ET and the 13:00 print **is** that
> session's closing price. The next session's `r1` is therefore perfectly
> well defined, and reading `p_1600` for the prior close instead NaN's it.

Reading the 15:30 bar would have quietly discarded the day after Thanksgiving,
the day after Christmas Eve and the day after July 3rd **every year** — about
nine sessions a year, and precisely the unusual ones §4 warns against dropping
silently. **This was found by a planted-defect test, not by reading the code.**

An **incomplete** session is different and is treated differently. The
separator is **contiguity**, not bar count:

* contiguous from 09:30 and ending at the 12:30 bar → a clean early close. It
  is excluded from trading (no 15:30 bar) and its last close **is** used as
  the next session's prior close.
* anything else that is not the full thirteen → incomplete, a defect. The
  following session's `r1` is **marked unusable** rather than computed, and
  the count is reported.

A session with bars missing out of its middle and a session that legitimately
closed early are both "not a full day", and treating them alike would have
used a price the market never closed at.

---

## D (PRE-RUN) — The window is whatever `--probe` says it is

Spec §4 registers **2015-01-01 → present, ≈2,900 sessions** as the minimum
viable window. Nothing in this project has ever measured how deep IB's
intraday history actually is, and A shows there is no second channel to fall
back to.

`common.spy_intraday_data --probe` walks a year ladder per bar size and
reports the earliest year that returns bars.

**The rule, fixed before the answer is known:**

* **30-minute reaching 2015 or earlier** → the registered window stands.
* **30-minute reaching a later year** → the window becomes that year → present,
  recorded here as an amendment **with the probe output quoted**, before any
  P/L runs. The study is not silently run on a shorter window, and a shorter
  window is not a reason to drop the study.
* **5-minute reaching a later year than 30-minute** → `sigma1`, the boundary
  surface (§8.5) and therefore **H-S2** are registered on that shorter window,
  and H-S1's window is not shortened to match. The two cells then have
  different denominators and **every H-S1/H-S2 comparison must state both.**

An **empty** response from IB means "no data" *or* "you are being paced" — §5:
IB signals its cap by returning empty lists rather than errors. Every empty is
re-checked against a recent control window before it is read as depth. An
`AMBIGUOUS` row is a pacing artefact and **is not evidence of absence.**

---

## E (PRE-RUN) — `sigma1` comes from 5-minute bars, and the agreement check is a RANK

Spec §4: *"1-minute is limited to roughly six months, so `sigma1` needs either
a second source or a 5-minute proxy — register which before running."*

**A registers that there is no second source.** So: the **5-minute proxy**, by
elimination rather than by preference.

Definition, fixed now:

```
sigma1 = sqrt( sum over bars in 09:30-10:00 of ln(close_i / close_i-1)^2 )
```

with `close_0` the **open of the 09:30 bar**, so the window's own opening move
is inside the measurement and the overnight gap is not. Six terms at
5-minute, thirty at 1-minute.

**Why a coarser proxy is sound here, and what would break it.** A 5-minute
realised vol is systematically *smaller* than a 1-minute one over the same
window and noisier. **Neither matters**, because H-S2 gates on a **trailing
percentile rank** of `sigma1`, and a rank is invariant to any monotone
rescaling. What *would* matter is the two series disagreeing about **which**
sessions are the volatile ones.

So the registered agreement check, over whatever overlap IB's 1-minute depth
provides, is:

1. **Spearman rank correlation** between 5-minute and 1-minute `sigma1`.
2. The **share of sessions the two put on the same side of the 67th
   percentile** — the quantity the gate actually depends on.

**Pass bar, set now: rank correlation ≥ 0.90 and same-side agreement ≥ 90%.**
Below either, the 5-minute proxy is **not** an acceptable stand-in, H-S2 is
reported as **NOT RUN** on the pre-1-minute era, and it is not quietly run
anyway with a caveat. §8.3's standard applies to this too: *a control whose
output is indistinguishable from the failure it detects is not a control.*

---

## F (PRE-RUN) — Adjustment: `whatToShow="TRADES"`, unadjusted, and why that is right rather than merely allowed

Spec §4 requires a **consistently** adjusted or **consistently** unadjusted
series, because mixing injects a spurious ~0.4% jump into `r1` four times a
year with the same sign — the class of error that cost VW9 its headline.

One `whatToShow` for the entire pull, every symbol, every bar size, makes
mixing impossible by construction rather than by care.

`TRADES` returns split-adjusted and **not** dividend-adjusted prices. That is
the correct series here, not just a permitted one:

> `r1` spans the overnight boundary. On an ex-dividend morning the price
> really does open lower by the dividend, and the strategy **holds nothing
> overnight**, so it never receives the dividend. The unadjusted price is what
> a live trader would have seen at 10:00. A dividend-**adjusted** series would
> remove a gap that actually happened.

SPY, QQQ and IWM had no split in this window, so split adjustment cannot move
anything either. `SOURCE.txt` is written beside the bars recording all of it,
so a later reader cannot mistake which series this is — §1: a report names its
tape.

---

## G (PRE-RUN) — What the assertion pass must show before any P/L exists

Spec §12 step 1 stops before P/L. `common.spy_intraday --assert` computes no
P/L and cannot reach the verdict code. It must report **zero** on all of:

1. sessions not starting at 09:30 ET;
2. DST transitions after which the next session does not start at 09:30 —
   both transitions of every year in the window;
3. overlapping cache chunks that **disagree** on a price;
4. session gaps over four calendar days (`r1` reads the prior session's close,
   so a hole is a **wrong r1**, not a NaN — there is nothing to notice);
5. sessions where the 10:00 price read from the 30-minute cache differs by
   more than a cent from the 09:55 close in the independently pulled 5-minute
   cache.

**Check 5 is the control on the whole data path** — two pulls, two caches, one
number — and it is §4's standard applied to this study's own plumbing: measure
on a second source *before* stating a conclusion, not after.

**Every one of these five has been shown to fire**, against synthetic caches
with the defect planted deliberately: a four-hour timestamp shift (the
UTC-read-as-ET defect that moved every time-of-day conclusion), a missing
week, a duplicate row that disagrees on price, a 1-for-10 reverse split left
in, and a DST transition mishandled. The clean case passes all five and the
cross-cache check reads **exactly 0.0** when the two caches are built from one
price path. A guard that has never been seen to fire is indistinguishable from
its absence.

Half-day count is **reported, not asserted**: roughly nine a year is expected,
and **zero would be the suspicious answer** on a multi-year window.

---

## H (PRE-RUN) — The `|r13|` reading can stop the study, and the bar is set now

Spec §12 step 2 and §6: the economics assume an average absolute last-half-hour
move of **0.20–0.30%**, and *"if it is materially smaller the arithmetic
changes and the study must be re-registered before running."* "Materially" is
given a number here, before the number is known:

**If the whole-window mean `|r13|` is below 0.18%, the study STOPS** and §6's
table is recomputed at the measured figure before H0 runs.

At 1.15 bps realistic friction and a 54.37% hit rate, a 0.18% average move
gives `(2×0.5437−1)×0.0018 = 1.57 bps` gross and **0.42 bps net** — friction
is then 73% of gross, against the 43% §6 works from. That is a different
proposition from the one registered, and it should be re-argued rather than
discovered afterwards.

The per-year table is reported regardless, because a window-wide average can
hide the thing the whole study is about: §2's claim is that the effect died in
the 0DTE era, and a shrinking `|r13|` would be one mechanism for that.

---

## I (PRE-RUN) — `holdout_spy.json` is cut before the first P/L run

Per spec §9, and **not** `holdout.json`, which governs the small-cap universe.
Most recent **20%** of usable sessions, session list fingerprinted, `cut_at`
recorded. The cut reuses `holdout.split` so there is still **one**
implementation of the split arithmetic — the rule that exists because two
studies were once written without it and would have read the locked slice
while printing an ordinary-looking number.

`--make-holdout` **refuses to overwrite an existing `holdout_spy.json`.** A
holdout that can be re-cut is not a holdout.

---

## Registered prediction for the DATA pass only

The strategy predictions stay as spec §10 records them. This pass has its own,
recorded before the probe returns:

* **30-minute reaches 2015.** Moderate confidence — IB's documented depth
  limits bite hardest at 1-minute and below.
* **5-minute does not reach 2015**, and lands somewhere in 2018–2021. Low
  confidence, and it is the number that decides whether H-S2 — the cell §2
  says is the whole open question — runs on the registered window or a
  shorter one.
* **1-minute reaches roughly six months**, as §4 assumes.
* **The half-day count comes in near nine a year.** If it comes in at zero,
  the exclusion logic is wrong, not the calendar.

---

# RESOLVED — 2026-09-17, after the probes, before any P/L run

Two probes ran against IB Gateway. **Both of the spec's data assumptions were
wrong, and both were wrong in the study's favour.** The amendments below are
appended rather than edited into A–I above: a pre-registration that gets
quietly rewritten is not one.

## D-RESOLVED (PRE-RUN) — depth. Every bar size reaches 2004

Probe output, `var/reports/spy_intraday_probe.txt` and `_probe2.txt`:

| bar size | earliest year answering | registered expectation |
|---|---|---|
| 30 mins | **2004** | reach 2015 — moderate confidence |
| 5 mins | **2004** | *not* reach 2015, land 2018–2021 — low confidence |
| 1 min | **2004** | roughly six months |

**The registered scored window is unchanged: 2015-01-01 → present.** The spec
chose it deliberately as the era Ben would trade, containing the 0DTE regime
§2 identifies as the threat, and depth being available is not a reason to move
a window that was chosen for a reason.

**What the depth is spent on instead is K.** The pull runs from **2005-01-01**
so the extra history exists; the scored cells still read 2015 onward.

## E-SUPERSEDED (PRE-RUN) — sigma1 comes from real 1-minute bars

Amendment E registered a **5-minute proxy** for `sigma1`, with a rank
correlation ≥ 0.90 and ≥ 90% same-side agreement as the bar for accepting it.
It was registered by elimination, on the spec's belief that IB holds about six
months of 1-minute history.

**That belief was wrong twice over.** 1-minute reaches 2004, and it can be
requested **a month at a time** rather than a day (L), so a full-window
1-minute pull is about an hour rather than about ten.

So: **`sigma1` is computed from 1-minute bars over the whole window.** The
definition in E is unchanged — `sqrt(sum of ln(close_i/close_i-1)^2)` over
09:30–10:00 with `close_0` the 09:30 open, thirty terms instead of six.

The proxy, and the rank-agreement bar that would have governed accepting it,
are **withdrawn as unnecessary** — not as failed. **The 5-minute cache is not
pulled at all**, because 1-minute serves `sigma1`, the boundary surface
(§8.5's 10:05 / 10:15 / 15:25 / 15:35) and the cross-cache control by itself.

*This is a case of a registered fallback being retired because the constraint
that forced it turned out not to exist. The measurement is in the probe
reports; the belief it replaces was in the spec.*

## J (PRE-RUN) — Before 2009 SPY closed at 16:15, and that is a session-shape trap

**Measured, not assumed.** Thirty-minute bars per session, from the probe:

```
2026, 2022, 2015, 2011   13.00      last bar labelled 15:30
2009                     13.19      the transition year, mixed
2008, 2007, 2005         14.00      last bar labelled 16:00
```

and 81 five-minute bars against 78, last labelled 16:10. The extra bar is
**16:00–16:15**, the old ETF extended close.

**It does not move any of the four prices.** The 15:30 bar still runs
15:30–16:00, so its close is still the 16:00 price.

**What it breaks is an equality test on the grid, and the first version of
this module had one** — `full` required exactly thirteen bars, so every
pre-2009 session would have been marked not-a-full-day and **dropped in
silence**. That is the same shape as the half-day defect in amendment C, one
era earlier, and it only became reachable because D turned a replication leg
from hypothetical into affordable.

Registered treatment:

* a session is **full** if its first thirteen bars are exactly the 09:30→15:30
  grid; **trailing bars past 15:30 are allowed** and do not disqualify it;
* the **session's closing price is the 16:00 price (the 15:30 bar's close)**,
  never the last bar's close, which on a pre-2009 session is fifteen minutes
  later and would have entered the next session's `r1` several thousand times;
* `extended_close` is recorded per session so any result can be split on it.

Pinned by three tests, including one that asserts the two candidate prices are
genuinely different numbers — so the test could actually fail if the wrong one
were used.

## K (PRE-RUN) — H-R, a replication control over the paper's own sample. REPORTED, NOT SCORED

Spec §4 calls a 2005 start "welcome if cheap". D makes it cheap.

**H-R: H-S1, unchanged, over 2005-01-01 → 2013-12-31** — the overlap with
Gao/Han/Li/Zhou's 1993–2013 sample.

**This is a control on the harness, not evidence about the market.** It is
*in* the paper's sample, so a positive result is replication and not
out-of-sample support, and it cannot be promoted, cited as an edge, or used to
rescue anything. Its whole job is:

> If this pipeline cannot reproduce a documented, peer-reviewed,
> independently replicated effect **on the era the paper measured it in**,
> then a flat or negative reading on 2015+ says nothing about the market,
> because the pipeline has not been shown to be able to detect the effect at
> all.

That is the same argument as "H0 first; if the control is not flat, stop",
pointed the other way: **H0 proves the harness cannot manufacture an edge, H-R
proves it can find one that is known to be there.** A harness with only the
first control can pass it by measuring nothing.

**Pass bar, set now:** H-R positive at the realistic friction level, with an
annualised figure in the same order as the published 6.67%/yr — read as
**between 3% and 12%**. Outside that band, the 2015+ reading is reported as
**uninterpretable** rather than as a finding, and the pipeline is investigated
first.

**Registered prediction:** H-R positive, 4–9% annualised. Moderate confidence.
This is the one cell in the study where the literature says what the answer
should be, which is exactly what makes it useful as a control.

## L (PRE-RUN) — Measured request durations, and the truncation guard

`--probe-duration`, same run:

| bar size | IB's documented max | **measured** | chunks over 2005→present |
|---|---|---|---|
| 30 mins | 1 M | **1 Y** | 172 → **25** per symbol |
| 5 mins | 1 W | **3 M** | 713 → 104 (not pulled; see E) |
| 1 min | 1 D | **1 M** | ~4,300 → **318** |

None of the measured responses were truncated — "1 Y" at 30 minutes returned
12.95 bars per session over 251 sessions, "1 M" at 1 minute returned 390 bars
per session over 21.

**They were measured on a RECENT window, and that is the risk.** IB has been
known to answer a too-long request for *old* data with a short window rather
than an error, and a chunk size set from a recent measurement would then leave
holes in exactly the oldest part of the pull. For `r1`, a hole is a **wrong
number, not a missing one** — it reads the prior session's close straight
across the gap with nothing to notice.

Two independent defences, both registered:

1. **Chunks overlap.** The step is shorter than the duration, always.
2. **Every chunk's returned span is checked against the step it was meant to
   cover**, at fetch time, and a short one is counted and named in the pull
   report. The assertion pass counts gaps again afterwards, from the assembled
   cache, by a different route.

**The pull plan that follows from this:**

```
30-minute   SPY, QQQ, IWM   2005-01-01 -> present    75 requests   ~16 min
1-minute    SPY             2005-01-01 -> present   318 requests   ~66 min
5-minute    not pulled (superseded by E)
```

QQQ and IWM are the breadth control (§8.4), which runs **H-S1 unchanged** and
therefore needs only the four 30-minute prices. Pulling 1-minute for them
would buy nothing that is registered to be looked at.
