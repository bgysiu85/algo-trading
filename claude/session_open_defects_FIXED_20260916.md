# Both session-open defects fixed, with the parity test that makes them stay fixed

2026-09-16. Answers `claude/handover_session_open_bugs_20260916.md`. Everything
below is in `D:\Trading`. **Nothing is promoted to `D:\TradingProd` until after
the close** — the handover's own constraint, and these touch the entry path.

---

## Defect 1 — the clock was checked and the bar was not

`MCLPaperTrader.in_session` asks what time it is. At 04:00:10 that is inside
04:00–09:30, so the poll proceeded. But nothing had printed yet that morning,
so the frame IB handed back still ended with **yesterday's 19:59 bar**. The
strategy evaluated it, the entry dedupe saw a timestamp it had never seen
before and let it through, and the trader bought at the open on a signal from
last night's close.

Two checks that look like one check. This is the catalogue shape **a check
placed one step short of the thing it protects**: the clock gate protects "are
we trading now", and what needed protecting was "is this signal about now".

### The fix

`brokers/ibkr/trader.bar_session_ok(signal_ts, now_et, session_start,
session_end)`. The bar must be **today** and inside **[session_start,
session_end)**. Three things about how it is wired matter more than the rule:

1. **It is handed `signal_ts`, the value the dedupe already resolved** —
   not a second read of `sig.bar_ts`. A gate that works out "which bar" on its
   own, standing next to a guard that works it out differently, is two values
   that look comparable and are not.
2. **The window comes off the ADAPTER**, never a module constant. MCL and MC5
   share 04:00–09:30 so today every answer is the same; VW9 runs to 20:00 and
   will not. A test moves the window and watches the gate follow.
3. **It sits after the dedupe and after `if not sig.long_entry: return`.**
   After the dedupe, so a frame frozen at last night's close writes *one*
   refusal rather than one per second until the first print of the day. After
   the entry check, so only real entry attempts are logged.

It is first among the refusals. Everything below it — paused, concurrency cap,
price band — is about *us*; this one is about whether the signal is about today
at all, and a stale bar should not be filed under the cap it also happened to
hit.

Refusals write **`SKIPPED_STALE_BAR`** with the bar's timestamp in
`reject_reason`. A silent skip is indistinguishable from "no signal fired" when
the session is reviewed, which is exactly how this survived. Nothing downstream
needed changing: every reader filters on `status in ("FILLED", "PARTIAL_FILL")`
rather than enumerating the skips — checked in `ui_bridge`, `db.py`,
`db_load.py`, `friction.py`, `notify.py`. `paper_fill.status` is `String(32)`
and the new value is 17 characters.

### A naive timestamp fails CLOSED

If a frame ever arrives without a timezone, the gate refuses rather than
guessing. Guessing is a five-hour error in whichever direction the guess fell,
and one of those directions admits exactly the bar this exists to stop. The
consequence is that the trader would stop entering, loudly, rather than trade
blind.

---

## The parity test is the fix; the gate is just code

A gate written only in the trader is a **fourth opinion** about what "in
session" means. So `strategy/mcl/mcl.in_session_mask(index, session_date, tz)`
was extracted out of `backtest_session` **unchanged**, and `backtest_session`
now calls it.

`test_gate_agrees_with_the_engine_bar_for_bar` runs both over a three-day
1-minute frame and asserts they agree bar for bar. Had the test restated the
expression instead, it would have been a guard tested by a copy of itself. It
also asserts the engine mask is neither all-True nor all-False, or agreeing
with it would mean nothing.

Same date equality, same half-open interval, same left-labelled bars — 09:29 is
the last bar of a session ending at 09:30.

---

## Defect 2 — the trail started from a price the position never traded at

The entry seeded `peak=max(avg, sig.close)`. `sig.close` is the **signal bar's**
close, from before the order existed. On VEEA the signal bar closed at 5.8709
and the fill came at 5.70, so the position opened with a trail level of **5.5774
against an entry of 5.70** — eleven cents from a stop it had never had the
chance to earn.

Now `peak=avg`. A trail measures **giveback**, and giveback can only be measured
from a high the position actually saw.

The two neighbouring paths already had this right:

| path | seeds the peak from | correct before today? |
|---|---|---|
| `manage_position` bar feed | bar highs from bars that closed **after** entry | yes |
| restart adoption | `max(entry_price, highs since entry)` | yes |
| Pine `peakSinceEntry` | bars from entry onward | yes |
| **live entry** | `max(fill, signal close)` | **no** |

Three of four agreed. The fourth was the one placing orders.

Measured, with the trail at 5.0%: peak 5.70 → level **5.415**, and an ask of
5.55 does not exit. Under the old seeding the level was 5.5774 and 5.55 did
exit — a losing trade produced entirely by a price the position never traded
at. Both directions are asserted, so the test is known to be capable of
failing.

---

## What was measured

`tests/brokers/ibkr/test_stale_signal_bar.py`, 18 tests. Full suite **2,940
passed, 4 skipped**; the seven script-style broker suites all pass.

**Mutation pass — seven mutations, seven caught, none survived:**

| mutation | caught by |
|---|---|
| drop the date check | yesterday's 19:59 bar |
| drop the window check | today's 03:59 overnight bar |
| guess ET for a naive stamp | the naive-frame case |
| `peak=avg` → `peak=max(avg, sig.close)` | the VEEA trail level |
| move the gate before the dedupe | one row per stale bar, not per poll |
| engine's window closed at the end | the parity test |
| gate's window closed at the end | the 09:30 boundary |

The controls are deliberate and they are half the suite: the first real bar of
the session is still taken, the last bar before the close is still taken, and
an entry still reaches an order. Without them every assertion here is satisfied
by a trader that has simply stopped trading.

---

## What I did NOT change, and why

**`drop_forming_bar`'s unconditional `iloc[:-1]`.** The handover asked me to
review it. The review:

It embeds an assumption — that IB's response *includes* the forming minute. If
IB instead returns only completed bars, the trim discards a good one and **every
entry in this project's live history is a minute late**. On a name moving 12¢ in
two minutes that is most of the gap Ben measured on BNC.

The assumption is decidable from the clock alone: a 1-minute bar labelled 09:03
is still forming iff `now < 09:04`. I could have made the trim conditional on
that this afternoon. **I did not, and I think that is right**:

- it is a behaviour change to the live entry path derived from my reasoning, not
  from a measurement, and this project's rule is register → measure → change;
- `common/bar_freshness.py` already exists to answer it, and answers it **by
  calling `drop_forming_bar` itself**, so the probe cannot drift from what the
  trader really does. Changing the function first would invalidate its premise;
- it has never been run. There is no `var/reports/bar_freshness.txt`.

So it stays as-is behind one command. **The probe is the read-only IB bar tool
the handover asked for — it already exists**, refuses live ports by name
(`LIVE_PORTS` check at `common/bar_freshness.py:264`), uses a spare client id,
writes to a file, and makes 12 historical requests on the default settings.

---

## Commands

Run from `D:\Trading`, one line at a time.

```
python -m pytest tests/ -q
```

```
python -m tests.brokers.ibkr.test_price_band
```

```
python -m tests.brokers.ibkr.test_live_paths
```

```
python -m tests.brokers.ibkr.test_pacing_and_trail
```

Then, **alongside a live session with Gateway up on the paper port** (this is
the measurement that settles `drop_forming_bar`):

```
python -m common.bar_freshness --symbols BNC --seconds 180
```

It writes `var\reports\bar_freshness.txt`. Send me that file and I will either
leave the trim alone or register the change.

**Promotion to `D:\TradingProd` waits until after the close.**
