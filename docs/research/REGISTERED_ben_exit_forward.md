# REGISTERED — PROVE-IT exit: a forward test against Ben's own MCL exits

Registered 2026-10-18 (Sydney), before any trade of the test sample exists. Build & test chat for Ben. Board: W16-0026 (this registration), W16-0027 (the run).
Status: **hypothesis from an exploratory look at 32 trades; nothing here is validated.** Rules, numbers and pass criteria below are fixed. Any change after the first test trade is made is a new hypothesis and needs a new registration.

## 1. Question
Would a fixed exit rule, applied to the entries Ben actually takes on MCL, have made more money than Ben's own discretionary exits?

## 2. Where the hypothesis comes from (development sample, not used for scoring)
W16-0024 replayed Ben's 32 live MCL round trips of 4–16 Oct 2026 (net $1,146 after commissions) with five mechanical exits. Reading that comparison afterwards suggested:
- A fixed stop plus a two-hour hold wins less often than Ben (53% against 69%) but its winners are larger (1.54 R against 0.88 R). Its lead over Ben ($69) came from three trades; without them Ben was ahead by $1,676.
- A trade that is in profit 30 minutes after entry did much better over the next two hours than one that is underwater.
- Ben took the two largest B-STOP winners out after 3 minutes.
These are patterns in 32 trades. They may be noise. This registration exists to find out.

## 3. The rule under test: PROVE-IT
For each of Ben's MCL round trips, from his entry as filled:
1. **R** = 2.0 × ATR(14) of the 5-minute bars, taken from the last bar completed before the first fill. A long's stop sits R below the average entry price; a short's R above. The stop is never moved.
2. **No profit target and no trailing, and no exit for profit before the check below.**
3. **30-minute check.** At the close of the 5-minute bar that ends 30 minutes after the bar containing the first fill: if the position is below the entry price (above it for a short), exit at the open of the next bar. Otherwise keep it.
4. **Time exit.** A position still open 120 minutes after the first fill is exited at the open of the next bar.
5. Fill rules, conservative: a stop is hit if the bar's low (a short: high) reaches it; a gap through the stop fills at the open. Within a bar the stop is tested before anything else. The entry bar's high and low are limited to the entry price and the bar's close, so nothing before the fill counts.
6. Every contract of the position leaves together, at one price.

Reference rules computed from the same data and reported but not scored: **B-STOP-120** (steps 1, 4 only, no 30-minute check); Ben's actual exits.

## 4. The test sample
- Every MCL (any contract month) round trip Ben opens **after this registration is committed**, in order, until **30 round trips** have closed. A round trip is a flat-to-flat position per contract month; scale-ins and scale-outs belong to the same trip. Entry price = size-weighted average of his entry fills; entry time = his first fill.
- A round trip is skipped only if the 5-minute bars for it are missing; the skip is reported, not hidden.
- Ben trades as he normally does. **He does not use this rule or adapt his exits to it during the test**, so that his exits remain his own.
- Data: an IBKR Flex export of executions covering the period, and the 5-minute MCL bars (IBKR history pull or the Databento archive). Trade times are Sydney time.
- Only one look. The scoring run happens once, when 30 round trips have closed. No interim peeking at P&L.

## 5. Costs and units
- Commissions as Ben's actual fills. PROVE-IT and B-STOP-120 pay $0.86 commission per contract per side and 1 tick ($1.00) of slippage on each exit fill; Ben's exits are as filled. Reported at Ben's actual size and per contract.
- D = net(PROVE-IT) − net(Ben), paired by round trip, in dollars at Ben's size.

## 6. Pass test (all four needed to say "worth adopting for a further trial")
1. Total D > 0.
2. Total D > 0 after dropping the two largest positive D trips.
3. Bootstrap by round trip (2,000 draws, seed fixed in the code before the run): D > 0 in at least 90% of draws.
4. D > 0 in both halves (first 15 and last 15 round trips).

Also reported, not scored: win rate; average win and loss in R; the split by long / short and by NY hour; the same table for B-STOP-120 (does the 30-minute check add anything?); largest loss; trade-by-trade table.

## 7. What each outcome means
- **Passes:** PROVE-IT is a candidate worth a longer paper trial (exit manager rule set 'B-STOP-plus with progress check'). It is not proven by 30 trades.
- **Fails:** Ben keeps his own exits; the idea is closed unless a new registration is written. Failure is not hidden or re-run with other numbers.
- **Fewer than 30 round trips by 2026-12-31:** the test is NOT READ and reported as such.

## 8. Limits
- 30 trades is small: even a rule that really helps can fail, and a rule that does not can pass. The pass test guards against a result carried by a few trades; it does not remove luck.
- Bars are 5-minute: the path inside a bar is unknown, so stops are tested conservatively.
- MCL only; MNQ and other symbols are not covered. The development sample came from two weeks in which oil moved sharply; the test sample may be quieter.
- Multiplicity: one rule, one primary comparison, one run.

## 9. Next steps (board)
- **W16-0026** — Build & test chat writes this file into the repo; Ben commits it. (Sonnet · Low)
- **W16-0027** — Ben trades as usual until 30 MCL round trips have closed, then exports the Flex report; Build & test chat builds `tools/ben_exit_forward.py` from `tools/ben_trade_exits.py` BEFORE seeing the data, runs it once, writes the Result doc. (Sonnet · Medium)
