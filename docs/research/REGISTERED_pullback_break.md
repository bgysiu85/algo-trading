# REGISTERED — MCL-PB: wait for the pullback, buy the break of the peak

Ben, 2026-09-16:

> very often, particularly in hours before 7am ET, even though all the entry
> conditions were met, the increase in price does not hold or does not have
> enough momentum and results in a reversal in price and lost trade.
> ... when the entry conditions are met, do not enter the trade yet. Wait for
> the stock price to peak and reverse/pull back in price. When the price passes
> the previous peak, that's when to enter the trade (provided that the current
> entry conditions are still met).

**Committed before `common/pullback_break.py` has produced a number.** Every
choice below was made by Ben in chat or fixed here in advance; none of it may
move after a run. A change is a new registration.

---

## 1. The rule, exactly

Everything not named here is MCL as published (`common.analysis.LIVE`:
apex exit off, MACD > 0 required, 5% trail seeded at the fill, flat at 09:30,
100 shares, $2-20 band, point-in-time `first_seen` floor).

| step | rule | chosen by |
|---|---|---|
| **Signal** | MCL's own five-clause `entry` is true on a completed in-session bar `s` at or after `first_seen`, while flat and with no setup pending | MCL |
| **Peak** | starts at `high[s]`; any later bar with a higher high raises it | Ben |
| **Arm** | the first later bar whose `high < peak` (a lower-high bar) arms the setup, effective from the NEXT bar | Ben: "lower-high bar" |
| **Trigger** | a buy-stop resting at `peak + $0.01`. Fires on the first armed bar whose `high >= peak + $0.01` | Ben: "stop order at peak+1c" |
| **Fill** | `max(peak + $0.01, open) + 1 tick` — gap-through, same convention as the exits, plus the engine's market-order tick | fixed here |
| **Still met** | `macd > macd_sig AND macd > 0` on the LAST COMPLETED bar (`j-1`). If false, the break does not fire; the peak moves up and the setup is disarmed | Ben: "MACD only" |
| **Cancel: depth** | at a bar's close, `low < peak - 0.5 x (peak - low[s])` | Ben: "pullback too deep"; 50% and the `low[s]` base fixed here (Cameron's 50% rule) |
| **Cancel: MACD** | at a bar's close, `macd < macd_sig` | Ben: "MACD rolls over" |
| **Cancel: window** | no trigger on the final in-session bar; the setup dies at 09:30 | fixed here |
| **After** | cancel or exit at bar `e` → the next setup needs a fresh MCL signal on a bar `> e` | fixed here |

Within one bar the resting stop is tested first, then the cancels. A bar that
triggers is the entry bar and, as in every engine here, is not itself managed.

New MCL signals while a setup is pending are ignored — the setup is not reset.

## 2. The control

MCL as published, on the **same** sessions, universe, floor, size and costs,
computed in the same process. Point-in-time universe
`var/state/screen_pairs_pit.json`, XNAS.BASIC, `holdout.json` **not touched**.

## 3. How it is read — fixed now

Outcome is net per trade at **$4.26** per round trip, the project's measured
friction. Halves are `entry_shares.split` (median session).

| verdict | all of |
|---|---|
| **CLEARS** | net per trade > 0 in **both** halves · total net > 0 after dropping the top 5 trades |
| **IMPROVES** | not CLEARS · beats MCL on net per trade in **both** halves · beats MCL on total net in **both** halves |
| **NOTHING** | anything else |

IMPROVES requires the total as well as the average **because** MCL loses: a rule
that trades less always raises its per-trade figure, and a rule whose total is
also better has genuinely kept money MCL gave away. It is still a direction,
not an edge.

**Ben's specific claim** — the damage is before 07:00 ET — is read separately
and does not change the verdict above:

> **PRE-07 HOLDS** if, for trades entered before 07:00 ET, MCL-PB's net per trade
> beats MCL's in both halves.

The report must also print, and nothing may be read without them:

- setups opened / triggered / cancelled by depth / by MACD / by window / band-refused
- median entry premium: fill vs the signal bar's close, in %
- the same table at $1.00 and $8.92
- MCL's trade count against `PUBLISHED_TRADES` — a mismatch stops the reading

## 4. What would not be a finding

- A best cell. There is one cell.
- Moving the 50% depth, the base, or the MACD clause after seeing the table.
- Anything on the holdout. If this CLEARS, the holdout run is its own registration.
