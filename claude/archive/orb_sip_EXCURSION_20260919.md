# ORB — can a wider stop rescue it? (amendment F, 2026-09-19)

Registration: `docs/research/REGISTERED_orb_sip.md` **amendment F**, committed before the measurement ran, with the decision rule and the prediction both fixed in advance.

Raw: `var\reports\orb_sip_excursion.txt`. Data: `var\cache\orb_sip\excursion.csv.gz`. Bundle: `orb-20260919a.bundle`. **Nothing was bought — minute bars already on disk.**

## The question, and why it was worth asking

The resolved result (`claude/orb_sip_RESOLVED_20260918.md`) was gross **$254,100**, costs **$253,620**, net **$480**. The strategy finds real moves and cannot pay for them, because the stop is 10% of ATR (~9¢) while a round trip costs ~3¢ — a third of every bet.

The obvious lever is a wider stop. But at constant dollar risk a wider stop buys proportionally fewer shares, so gross and friction scale down together. It can only help through one channel: **trades that were stopped out and would otherwise have gone on to work.**

F measured whether those trades exist. Descriptive only: no stop width simulated, no P&L at any width, so there was nothing to select on.

## The answer

Maximum adverse excursion — how far the price went against the entry, from the entry bar to the session close, ignoring the registered stop:

| | trades | median MAE | p90 |
|---|---:|---:|---:|
| **Winners** | 1,057 | **0.63R** | 1.51R |
| **Losers** | 6,182 | **5.51R** | 15.59R |

**The stop is not cutting winners short. Winners barely touch it** — half of them never go more than two-thirds of the way to the stop. The losers go five and a half times the stop distance against you, and that is the whole distribution, not a tail.

Share of losers whose worst point stayed inside a given stop:

| stop | losers who survive it |
|---:|---:|
| 1.0R (registered) | 1.1% |
| 1.5R | 7.3% |
| 2.0R | 13.3% |
| 3.0R | 25.6% |
| 5.0R | 45.4% |

To keep even half the losers alive you would need a stop at **5.5R — 55% of ATR** instead of 10%.

## F.3, applied exactly as registered

F.3 defined a loser as **rescuable** if all three held: worst point inside 2R, closed the session in profit, and the adverse extreme came *before* the favourable one. The third condition matters: a trade that ran first and gave it all back was never rescued by a wider stop — it was already winning and then wasn't.

| | |
|---|---:|
| losers that would have closed green if never stopped | 41.3% |
| …and stayed inside 2R first | 10.5% |
| …**and in that order** | **9.1%** |
| **the registered gate** | **25%** |

**565 of 6,182 — 9.1%, against a gate of 25%.** F.3's pre-written consequence: *"the stop is doing its job, a wider one loses more slowly, and ORB closes permanently. No variant is registered, no further data is bought, the holdout stays locked."*

**F.4 predicted rescuable would land below 25% and ORB would close. The prediction was correct** and is recorded as such. Its basis was amendment E's finding that 81.2% of trades freed from an entry-minute stop re-reached that stop within a minute or two anyway.

## The one idea that survives the headline, and its tail

41.3% of losers would have closed the session in profit with no stop at all. That looks like a lead until it is priced:

| | in R | on $100 of intended risk |
|---|---:|---:|
| median worst point, for those that recover | 3.19R | $319 |
| worst point, p99 across all trades | 36.77R | **$3,677** |
| worst point, maximum | 232.66R | **$23,266** |

Removing the stop means one trade in a hundred goes $3,677 against a $100 bet, and the worst goes $23,266. Risk per trade stops being defined, equal-risk sizing collapses, and the criteria that measure this book no longer mean anything. It is not a rescue; it is a different strategy with an unbounded tail, and it is not registered.

## Verdict

**ORB is closed permanently.** Two attempts, both settled by measurement rather than opinion:

1. **Survivor universe (16 Sep)** — +$16,218, +$3.33/trade, 6 of 7 criteria. The point-in-time re-run (17 Sep) put it at −$4.58/trade and priced the leak at +$7.91/trade. Every dollar of profit was in names selectable only with hindsight.
2. **Stocks in play (18 Sep)** — a fresh, honest universe. Gross $254,100, costs $253,620, net $480 over 7,239 trades and 446 sessions. 1 of 7 criteria. One stock decides the sign.
3. **The rescue check (19 Sep)** — the stop is not the problem. 9.1% against a 25% gate.

`var/state/holdout.json` is unspent and stays so.

## For PROGRAM_INDEX

- **ORB: closed, both universes, all avenues.** Do not reopen without new data and a new mechanism; the stop width is answered and the concentration is untouched.
- New standing fact: **on this universe, ORB's winners reach a median 0.63R against them and its losers 5.51R.** A stop is not what separates them — the entry is. Any future intraday breakout work should measure this split *before* tuning an exit, because it costs nothing and it settles the exit question outright.
- New standing fact: **"the losers would have recovered" is not a lead until its tail is priced.** Here 41.3% recover and the p99 adverse excursion is 36.8× the intended risk.
- Method note worth keeping: F registered a **descriptive measurement plus its decision rule** before running, so the stop width could not be chosen by which one performed best. That pattern is reusable wherever a failed strategy has one obvious knob.
