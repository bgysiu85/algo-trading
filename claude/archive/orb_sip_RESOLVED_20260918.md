# ORB on Stocks in Play — the entry-minute ordering RESOLVED (2026-09-18)

Registration: `docs/research/REGISTERED_orb_sip.md` **amendment E**, written and committed before the one-second data was priced or bought. This doc supersedes the two-readings table in `claude/orb_sip_RESULT_20260918.md`; everything else in that doc stands.

Raw: `var\reports\orb_sip_resolved.txt`. Verdicts: `var\cache\orb_sip\entrybar_resolved.csv.gz`. Bundle: `orb-20260918g.bundle`.

## What was open

The stop sits 10% of ATR from entry — about 9¢ — so **39.9% of top-20 trades had the stop price touched during the minute the position was opened**. A one-minute bar carries a high and a low but not their order, so the study could not say whether those trades were stopped or never exposed. The two readings differed by 0.40R a trade, which was the difference between 1 of 7 criteria and 5 of 7.

## What the seconds said

2,888 symbol-days of `ohlcv-1s` on XNAS.ITCH, entry minute only, **698.1 MB at $0.00** (inside the free window). Every one resolved — no missing data.

| verdict | trades | share | meaning |
|---|---:|---:|---|
| `stop_first` | **1,602** | **55.5%** | the low printed *before* the trigger — no position existed to stop |
| `entry_first` | 993 | 34.4% | trigger, then the stop fired — the trade really was stopped |
| `same_second` | 293 | 10.2% | both inside one second — unresolvable at this schema |
| `no_seconds` | 0 | 0.0% | — |

**More than half of the entry-minute stops never happened.** The registered reading charged 1,602 trades a −1R loss they never took.

Amendment E.3 set a tripwire in advance: `same_second` above 20% would have meant one-second bars did not settle the question either, and no number could be quoted as final. It came in at 10.2%, so a figure of record stands.

## The figure of record

E.2 fixed the recombination before the data was bought: `entry_first` keeps the stop, `stop_first` takes the alternative path, `same_second` keeps the stop because that is the conservative side. Net R per trade at BASE friction:

| reading | mean net | gross | total | drop-top-5 | win | bootstrap |
|---|---:|---:|---:|---:|---:|---:|
| registered (charged every entry-minute stop) | −0.350R | +0.003R | −2,532R | −2,783R | 11.9% | 0.000 |
| **RESOLVED — the figure of record** | **+0.001R** | **+0.351R** | **+4.8R** | **−257.5R** | 14.6% | 0.496 |
| band (`same_second` → alternative) | +0.058R | +0.407R | +416R | +125R | 15.0% | 0.853 |
| alternative (charged none) | +0.055R | +0.405R | +401R | +70R | 15.6% | 0.834 |

The band is a disclosed sensitivity showing the width of what one-second bars could not settle — 293 trades. It is not the result.

## Verdict: unchanged, and predicted in advance

**1 of 7 criteria met** (trade count). Amendment E.3 said before the data was bought that resolution could not produce a pass, because the ceiling — the optimistic reading — already failed criteria 2 and 7, and a figure between the two readings cannot clear a bar the better of them missed. That held.

| criterion | resolved | verdict |
|---|---|---|
| 1 drop-top-3 / -5 > 0 | −155.5R / −257.5R | FAIL |
| 2 bootstrap P(total>0) ≥ 0.95 | 0.496 | FAIL |
| 3 mean ≥ +0.05R | +0.001R | FAIL |
| 4 trades ≥ 100 | 7,239 | pass |
| 5 both halves > 0 | −198.6R / +203.4R | FAIL |
| 6 both sides > 0 | long −0.028R / short +0.029R | FAIL |
| 7 no optimum on a boundary | best top-40 | FAIL *(registered reading — not resolved)* |

**Criterion 7 is deliberately not re-scored.** The seconds were bought for the primary cell alone, per E.2's scope. Ranks 21–40, the `eligible` and `unfiltered` arms and the 15-minute arm still carry unresolved entry-minute stops. Ranking a resolved top-20 against an unresolved top-40 would award the difference between two *readings*, not two cells — a two-denominator comparison this program refuses. It fails in both readings, so the verdict does not turn on it.

## The finding underneath the mean

A mean of +0.001R looks like a zero-edge coin flip. It is not.

Of the 1,602 trades the seconds freed, **1,301 (81.2%) re-reach the same stop a minute or two later and die anyway, for the same money.** Only **301 genuinely change outcome** — and those 301 carry the entire move, at **+8.43R each on average**, +2,536R in total against a registered book of −2,532R. Their median is +4.6R; their largest is +46.9R.

So the whole resolved book, +4.8R across 7,239 trades, rests on a few hundred very large winners:

| | total |
|---|---:|
| resolved book | **+4.8R** |
| drop the top 1 symbol | −52.1R |
| drop the top 3 symbols | −155.5R |
| drop the top 5 symbols | −257.5R |
| drop the top 10 symbols | −492.4R |

Top 5: MWA +57R, TD +52R, NYT +51R, IONS +51R, THC +51R. **Removing the single best symbol takes the book from +4.8R to −52.1R.** This is exactly the shape criterion 1 exists to catch, and it caught it.

There is a second reading of the same numbers worth keeping: gross is **+0.351R** and friction is **0.350R**. The paper's gross edge does reproduce out of sample (it claims +0.38R) — and at realistic retail costs, friction consumes essentially all of it.

## Verification

- **13 verdicts re-derived by hand** from the raw one-second bars without the resolver, spanning all three outcomes and including the four largest movers: 13 of 13 matched.
- **Tape agreement**: on a 10% sample (299 trades, 45 days) the seconds tape contained the minute bar's stop touch in 299 of 299 cases. The two tapes do not disagree about whether a price traded, only about when.
- **Arithmetic reconciles exactly**: −0.349706R + 2,536.3R/7,239 = +0.000663R.
- 18 tests on `sip_resolved`, 20 mutations, no survivors. Full ORB suite 138 passed.

## Limits of the resolution itself

- `ohlcv-1s` emits a bar only where a trade printed. The entry minute carries a median of 16 traded seconds (p10 6, p90 47); 4.0% have three or fewer. Ordering inside those is known but coarse, and sub-second sequence is never available at this schema.
- R is 10% of ATR, so a name that trends all session produces a 40R+ winner. The R-multiples are arithmetically correct and still make the tail heavier than a dollar book would show.
- The random-20 control was run on the resolved ledger but its population (`eligible`) is unresolved, so it reads the ranking's transfer rather than a clean like-for-like margin.

## For PROGRAM_INDEX

- ORB on stocks in play: **closed**, does not pass, holdout unspent. Figure of record +0.001R net / +0.351R gross at BASE, 1 of 7.
- New standing fact: **a minute bar's high and low have no order, and at a 10%-ATR stop that ambiguity is worth 0.35R a trade.** Where entry and stop fall in the same bar, one-second bars settle it for $0.00 inside the free window — and here they showed **55.5% of same-bar stops never happened**. Any strategy whose stop sits inside typical one-bar range needs this check before its fill model is believed.
- New standing fact: **freeing a trade from a same-bar stop mostly does not save it** — 81.2% re-reach the same stop within a minute or two. The change concentrates in a small tail, which is a drop-top-N question, not a mean question.
