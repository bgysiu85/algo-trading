# REGISTERED — W02-0018: exit re-pricing in a collapse (PRE-RUN)

**Author: Build & test chat, 2026-09-28.** Written before any replay code exists,
per the standing rule (commit hash is the timestamp). Board item W02-0018.

---

## 0. Provenance

Raised by W02-0017 (Live analysis chat): the 09-23 session review found trailing
stops filling $635 below their stop levels in total (largest on record); 9 of
that session's exits needed re-pricing. The worst, GRML MCL 09:28, sent 4
abandoned sell limits over 6 seconds and filled at 15.08 against a 17.195 stop
level, -$243.39 on its own — 45% of the day's loss.

**The mechanism (`brokers/ibkr/trader.py`).** A SELL exit is priced
`LIMIT_CROSS_BPS` (20bps, 0.2%) under the current bid. If the quote moves
through that limit for `EXIT_ABANDON_POLLS` consecutive ~1s polls, the order is
cancelled and immediately re-priced 0.2% under the *new* bid. In an ordinary
market this closes the trade in one or two ticks. In a fast collapse the bid
keeps falling faster than one 0.2%-under retry can catch it, so the order is
perpetually re-priced to a level the market has already passed — each retry is
"stale within a second" (W02-0017's phrase) — and the eventual fill lands far
below the level that triggered the exit.

**Ben's decision, 2026-09-24: "A · Measure first."** Replay every re-priced
exit since 09-16 against Databento MBP-1 (real order-book depth, not just the
1-second bid/ask snapshots the fill log already has) and price a wider retry
ladder — 1% under bid, then 2% — against what the book actually offered. No
live-path change until it shows a gain. Options were A (this), B build the
wider ladder now without measuring, C leave it.

---

## 1. Population — and why this is a replay of every known incident, not a powered test

Every `NO_FILL_ABANDONED` SELL row in `var/fills/mcl_fills_*.csv` from
2026-09-16 (the session `EXIT_ABANDON_POLLS` went live) through 2026-09-28,
grouped into episodes (consecutive abandons on the same strategy+symbol,
closed by a FILLED/PARTIAL_FILL/CANCELLED/REJECTED row or end of session).

**2026-09-16 is excluded.** That day alone has 496 `NO_FILL_ABANDONED` rows,
all on MEDS — this is "THE MEDS GHOST" documented in `trader.py`'s own history
(the abandon path broke and re-priced against its own stale poll loop before
the fix at line ~132). It is a code bug, not evidence about market behaviour
in a collapse, and including it would swamp every other session by two orders
of magnitude.

That leaves **21 episodes over 15 symbol-days across 8 sessions** (09-18,
09-21, 09-22, 09-23 x4, 09-24 x4, 09-25, 09-28):

| date | strategy/symbol | abandons | terminal | fill |
|---|---|---:|---|---:|
| 09-18 | MC5 IMCC | 1 | FILLED | 4.20 |
| 09-18 | MC5 BIAF | 1 | FILLED | 11.00 |
| 09-21 | MC5 GRML | 1 | FILLED | 4.98 |
| 09-22 | MC5 AKAN | 1 | FILLED | 3.72 |
| 09-22 | MCL DCOY | 1 | FILLED | 4.53 |
| 09-22 | MC5 DCOY | 1 | FILLED | 5.26 |
| 09-23 | MCL IPDN | 1 | FILLED | 8.13 |
| 09-23 | MC5 IPDN | 2 | FILLED | 7.80 |
| 09-23 | MCL IMCC | 1 | FILLED | 6.91 |
| 09-23 | MC5 IMCC | 1 | FILLED | 9.71 |
| 09-23 | MC5 IMCC | 1 | FILLED | 7.50 |
| 09-23 | MC5 IMCC | 1 | FILLED | 7.54 |
| 09-23 | MCL DCOY | 1 | FILLED | 4.34 |
| 09-23 | MC5 DCOY | 1 | FILLED | 4.36 |
| **09-23** | **MCL GRML** | **4** | **FILLED** | **15.08** |
| 09-24 | MC5 WETO | 1 | FILLED | 2.31 |
| 09-24 | MC5 PFSA | 1 | FILLED | 3.44 |
| 09-24 | MCL VBIO | 1 | FILLED | 3.92 |
| 09-24 | MC5 IMCC | 1 | FILLED | 3.46 |
| 09-25 | MCL KITT | 1 | FILLED | 6.00 |
| 09-28 | MC5 MEDS | 1 | FILLED | 3.42 |

**This is the whole population, not a sample.** 20 of the 21 episodes needed
only 1-2 retries and every one of them eventually filled — nothing here is
unresolved. Only GRML/MCL/09-23 matches the severity that opened this item.
n=21, mostly single-retry, is not enough to run a significance test and this
study does not attempt one (no bootstrap, no p-value below). **The question
this answers is descriptive and dual-sided: would a wider ladder have caught
GRML materially higher, and what would it have cost on the 20 episodes that
were already fine** — a rule that fixes the rare collapse by giving away edge
on every ordinary exit is a different, worse result than one that is a clean
win on both.

---

## 2. Method

**Data.** Databento `XNAS.ITCH` schema `mbp-1` (full top-of-book, updated on
every order-book event, not just trades — the thing a 1-second bid/ask poll
cannot see) for the 15 symbol-days above, from 2s before each episode's first
abandon through 10s after its actual terminal fill (or 30s cap, for episodes
that never resolve in the replay window). Pair list:
`var/state/w02_0018_exit_reprice_pairs.json` (15 pairs, written this session).
Estimate only — no spend — until Ben approves the cost
(`common.databento_fetch` defaults to `--max-cost 5.00` and never downloads
without `--confirm`; per `PROGRAM_INDEX`, Standard's one-year L1 window makes
mbp-1 back to 09-16 in-plan, so this is expected to be near-free, but the
estimate is run and reported rather than assumed).

**Replay.** For each episode, walk the mbp-1 book tick by tick from the first
abandon's timestamp:

- **Actual (control):** reproduce today's rule — SELL limit at `bid - 0.2%`,
  re-priced on each retry exactly as the fill log recorded it (same retry
  timestamps, same abandon count) — and confirm the replay's fill price
  matches the live fill log's `fill_price` within a cent. This validates the
  replay engine against ground truth before trusting its counterfactuals.
- **B1 — flat 1%:** every retry priced `bid - 1%`.
- **B2 — escalating:** first retry `bid - 1%`, second and later retries
  `bid - 2%`.

A simulated limit is filled the instant the book shows a bid (SELL) at or
below the limit with displayed size >= the 100-share order — filled at the
**limit price**, never better; no price-improvement assumption. If the book
never reaches the limit within the replay window the episode is scored
unfilled for that ladder (worse than actual, since actual did eventually
fill).

**Compare, per episode and in aggregate:** fill price and $ difference at 100
shares (live size) for B1 and B2 vs actual, split into the GRML episode and
the other 20, plus time-to-fill.

---

## 3. What would change the recommendation

- If B1/B2 fill **materially worse** than actual on the 20 calm episodes
  (giving up edge on every ordinary exit to fix one rare event), that is a
  cost the GRML saving has to clear, and the writeup says so explicitly rather
  than netting it away.
- If the GRML-style collapse is fast enough that **even 2% under bid is still
  through the market** a poll later, no ladder width fixes it and the
  recommendation is **C — leave it** (the fix would need to be something else,
  e.g. a hard cap on retries followed by a market order, which is out of
  scope here and would be its own item).
- Only if B2 (or B1) fills GRML meaningfully higher **and** costs nothing
  material on the other 20 does this recommend **B — build it**.

---

## 4. Next steps (board)

- Estimate the Databento pull (no spend) — command below.
- On Ben's go-ahead (or if the estimate is $0, run it and say so), fetch the
  15 symbol-days and build `common/exit_reprice_study.py` on this spec.
- Write the result as a monday Doc per rule 8; update this item.
