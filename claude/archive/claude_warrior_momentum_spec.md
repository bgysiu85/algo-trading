> **SUPERSEDED 2026-09-09 by the Warrior spec set.** Everything buildable in
> this file has been rewritten, with the two key videos transcribed in full and
> the stop contradiction resolved, into:
>
> - **`warrior_0_universe_and_risk.md`** — universe, regime gate, stop and
>   sizing. **Read this first.**
> - `warrior_1_micro_pullback.md` — the primary setup
> - `warrior_2_flat_top.md` — its flat-top variant
> - `warrior_3_gap_and_go.md` — pre-market selection and grading
> - `warrior_4_reversal.md` — the fade
>
> **Do not build from this file.** It is kept because it is the log of *how the
> source was read*, and because §2 and §3 below are method findings that apply to
> the next channel as much as to this one. See `PROGRAM_INDEX.md` §6.

# Warrior Trading source-reading log

Compiled 2026-09-09. This records what was read, in what order, what each source
yielded, and the two method lessons that came out of it.

---

## 1. What was read

**All ten `warriortrading.com` strategy and topic pages**, plus
`warriortradingnews.com` search snippets. Then two videos in full:
`p1W8Mjl4kWs` (57:22) and `A3sbJBOLGuI` (58:28). Earlier sessions had already
read `eTUYXkAr6Pc` (S3) and `w2owyBNunDQ` (S5) — see
`archive/ema_source_comparison.md`.

| Page | Yield |
|---|---|
| `/momentum-day-trading-strategy/` | **High.** Universe + bull flag |
| `/bull-flag-trading/` | **High.** The pattern with thresholds |
| `/gap-go/` | **High.** The A/B/C grading rubric |
| `/reversal-trading-strategy/` | **High.** A complete fourth strategy |
| `/position-sizing/` | Low. One share range, and it contradicts the momentum page |
| `/premarket-trading/` | Low, but useful execution constraints |
| `/how-to-use-stock-scanners/` | Almost none. "In play if surging more than 4%" corroborates the Gap and Go floor |
| `/mean-reversion/` | **None of his.** ConnorsRSI, 90-day linear regression, Keltner bands |
| `/how-to-build-morning-watchlist/` | **None of his.** A generic FinViz worked example |
| `/technical-analysis/` | None. Names five indicators with **no periods on any of them** |

---

## 2. Method lesson — the site beats the videos, but only half the site

The handover's rule was "for a channel with a content-marketing site, read the
site before the videos." **That held**: one free page gave more codeable
parameters than thirteen Humbled Trader videos.

**But it holds only for the pages named after a specific setup.** The
general-topic pages on the same domain are SEO content — generic,
unparameterised, and in two cases describing methods he does not trade.
`/mean-reversion/` teaches an approach that contradicts everything else on the
site.

> **Sharpened rule: read the pages named after a specific setup. Treat
> general-topic pages on the same domain as a different author until a stated
> number matches something the source says elsewhere.**

**The second lesson corrects the first.** The site was declared to have made the
videos "lower priority." That was wrong. The two transcripts settled the stop
rule, gave the early-entry mechanism, the front-side/back-side gate, the
continuation RVOL exception, the daily-chart trust check, the price-grid
observation and nine years of self-reported metrics with **both sides of the
ledger** — none of which is anywhere on the site.

> **The site states the rules. The videos state the reasons, the exceptions and
> the numbers he actually trades.** For a source who sells a course, expect the
> written pages to be the sanitised version.

---

## 3. Float: six numbers, all from the same man

| Source | Float rule |
|---|---|
| `/momentum-day-trading-strategy/` | < 100M, "under 20M ideal" |
| `/gap-go/` grading | < 20M ideal · 50–100M marginal · > 100M avoid |
| `/how-to-build-morning-watchlist/` | < 50M — **not his, SEO content** |
| `p1W8Mjl4kWs` @ 16:19 | "less than **10 million** shares I tend to do better" |
| `A3sbJBOLGuI` @ 11:21–16:48 | **< 20M** main account; "sub **5 million** pretty much required" small account |

**No float threshold from this source is a fitted parameter.** The last row is
the most credible because it is the only one stated *conditionally*, with a
reason. Carried into `warrior_0_universe_and_risk.md` §1.

---

## 4. The contradiction that was open, and how it closed

The site says **stop = the low of the pullback**. `p1W8Mjl4kWs` @ 34:11 says the
opposite: "I don't stop at the low of this pullback, that's too far. I use an
arbitrary stop generally of 10 to 15 cents."

Reading both videos in full resolved it rather than picking a side: he uses the
structure stop **when it is tight enough** and a fixed cent cap when it is not,
and the cap is calibrated to his own average loser rather than to the chart. The
worked example in `A3sbJBOLGuI` @ 45:31 shows him taking an 11c structure stop
and calling anything wider "not ideal."

Full treatment in `warrior_0_universe_and_risk.md` §5.1, including why this
matters more than it looks: **every stop in our engines is a percentage, and 15c
is 7.5% at $2 and 0.75% at $20.**

---

## 5. Still unread on this channel

- `4jes2_N3m2I` — "Flat Top Breakout Pattern", 14:03. The only dedicated video on
  that setup, and short. Named in `warrior_2_flat_top.md` §6 as the obvious next
  extraction.
- `ORWJzImSTdE` (1:05:05) and `hz7vhSIXXSc` (51:55) — the dip-trading videos.
  These are the cross-check on Shay's dip-versus-breakout argument
  (`TzGQE8d0f18`) and the likely home of a long-side reversal expression.
- `W3jXQlgGbBc` (Sub VWAP Trap) and `mBT72-bFlPM` (Base Hit) both returned **zero
  hits on "float"**. Per the method, a zero-match needs a second common term
  before either is ruled out.
- `mfGQr2tHoX0` (MACD) and `iS5lvJGMM8E` (RSI) were swept, not transcribed. Both
  confirm he uses platform defaults, so the expected marginal yield is low.
- `warriortradingnews.com` and `media.warriortrading.com` (a public Technical
  Analysis PDF) surfaced detail absent from the main site. Worth searching when a
  specific parameter is missing.
