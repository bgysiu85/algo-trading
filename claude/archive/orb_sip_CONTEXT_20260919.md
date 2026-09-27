# ORB — the market-context gate (amendment H, 2026-09-19)

Registration: `docs/research/REGISTERED_orb_sip.md` **amendment H**, committed with its rule, its bar, its four controls and two separately-scored predictions before anything was run. Raw: `var\reports\orb_sip_context.txt`. State: `var\state\orb_sip_spy_or.csv`. Bundle: `orb-20260919c.bundle`. **Nothing bought** — SPY was already inside the XNAS.ITCH minute files.

Proposed by `handover_orb_build_chat_20260918.md` §5, sourced from `source_videos_14_breitstein_20260918.md` §14.2–14.3, earned by amendment G.

## The rule, and why it had no parameter

A trade is **WITH** when its side matches the sign of SPY's own 5-minute opening range (09:30–09:34, the same window the strategy uses on its own names, read at the instant the trigger arms). **AGAINST** when it opposes it. The gate trades WITH and skips AGAINST.

No threshold. The magnitude of SPY's move was deliberately unused and never swept — a threshold makes this a grid, a grid on a book carried by five symbols is a search rather than a test, and all four failed regime precedents had one. H.5 fixed in advance that a failure retires the family rather than earning it a knob.

## The result

| bucket | trades | mean net | gross | total | drop-top-5 | win | bootstrap |
|---|---:|---:|---:|---:|---:|---:|---:|
| **WITH** (retained) | 3,770 | **+0.001R** | +0.351R | +4.8R | (233.9)R | 14.6% | 0.521 |
| **AGAINST** (discarded) | 3,452 | **+0.004R** | +0.355R | +14.2R | (232.8)R | 14.7% | 0.500 |
| FLAT | 17 | (0.835)R | (0.446)R | (14.2)R | (18.6)R | 11.8% | 0.036 |

**The bucket the gate throws away is marginally better than the one it keeps.** There is no direction effect here to gate on.

### The bar (H.2): 1 of 6

| criterion | WITH bucket | |
|---|---|---|
| 1 drop-top-3 / -5 > 0 | (151.7)R / (233.9)R | FAIL |
| 2 bootstrap P(total>0) ≥ 0.95 | 0.521 | FAIL |
| 3 mean ≥ +0.05R | +0.001R | FAIL |
| 4 trades ≥ 100 | 3,770 | pass |
| 5 both halves > 0 | (277.1)R / +281.8R | FAIL |
| 6 both sides > 0 | (0.022)R / +0.026R | FAIL |
| 7 | unscored, per E.2's scope | — |

## The control that settles it

**H.3(a), the shuffled-sign null.** The same signs dealt to the same 446 sessions at random, 2,000 draws, seed 20260916 — the proportion of up and down days preserved, only *which* sessions got which sign changed.

| | observed | null p95 | p | |
|---|---:|---:|---:|---|
| mean R | +0.001 | +0.093 | **0.478** | does not beat |
| drop-top-5 | (233.9) | +84.8 | **0.463** | does not beat |

**The real split sits at the median of random relabellings.** This was the control amendment G's result made mandatory — G measured that carrier days were better days, but measured it conditional on the outcome, so a 50/50 session split could inherit the artifact. It didn't inherit anything, because there is nothing there.

### The other three controls

**(b) Side composition** — the advantage does not exist within either side either:

| | AGAINST | WITH |
|---|---:|---:|
| long | (0.032)R | (0.022)R |
| short | +0.038R | +0.026R |

Longs do marginally better WITH the market, shorts marginally better AGAINST it. The two cancel.

**(c) Two denominators** — they agree, and agree on the wrong sign: per trade (0.003)R, per session (0.021)R. Both favour the discarded bucket.

**(d) drop-top-N on the delta** — the WITH-less-AGAINST difference is (9.5)R across 1,990 symbols, and (264.7)R after dropping its top 5.

## Predictions, both scored

- **Primary — NOT ADOPTABLE: correct.**
- **Secondary — "the WITH mean will beat AGAINST while drop-top-5 stays negative": WRONG.** I expected a real direction effect that failed to fix concentration. There is no direction effect at all. The failure is more complete than predicted, and that is worth recording precisely because the wrong half was the half that assumed the source had identified something real.

## What this closes

Per H.5, **the market-context family is retired for ORB.** No threshold sweep, no second index, no second window, no "QQQ instead", no "only when SPY moves more than X" — those are the same hypothesis with a knob, which is what H was written to refuse. It joins `luck_vs_edge_RESULT_20260917`, `cold_veto_RESULT_20260917`, `spy_intraday_RESULT_20260918` H-S2 and the BandWidth squeeze pre-flight: **the regime-gate family is now 0 for 5 on this project's data.**

## Where the ORB levers stand

| lever | status |
|---|---|
| Stop width (F) | **Closed permanently.** Winners reach 0.63R against them, losers 5.51R; rescuable 9.1% against a 25% gate. |
| Market context (H) | **Retired, family-wide.** A coin flip, p = 0.478. |
| Volume confirmation on the break | **Untouched.** The last named candidate from the source review, and the only one left. See below. |
| Verdict / holdout | 1 of 7, unchanged. `holdout.json` unspent. |

**On the remaining candidate, honestly:** H's retirement does not cover it — it is a different mechanism (the quality of the break, per trade) rather than the same one with a knob, and G's "a gate needs the best 4.5% of sessions" constraint is a session-level bound that a per-trade filter is not subject to. So it is not closed by anything measured so far. But it faces the same criterion 1, concentration is symbol-level, and neither lever tested so far has touched it. It is registered separately if at all; a two-filter grid on this book is a search, not a test.

## For PROGRAM_INDEX

- **The regime-gate family is 0 for 5.** Five independent attempts, five different framings, on four different strategies. Treat the next proposal in this family as requiring an unusually specific mechanism before it gets a registration.
- New standing fact: **on ORB SIP, trading with the index's opening-range direction is indistinguishable from a coin flip** — p = 0.478 against a 2,000-draw shuffled-sign null, and the discarded bucket was marginally better. Breitstein's "market context" claim does not survive its most faithful parameter-free operationalisation on this book.
- Method note worth reusing: **the shuffled-label null is the control that separates a rule from a relabelling.** It preserves the split's shape and randomises only the assignment, so it prices exactly what the rule claims to add. Any future gate on this project should carry one.
- Method note: **a parameter-free operationalisation, registered with a family-wide retirement clause, is how a qualitative source claim gets retired in one pass** instead of generating a sequence of tuned near-misses.
