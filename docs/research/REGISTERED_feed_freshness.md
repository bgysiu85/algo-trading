# REGISTERED — the feed's two defects: staleness at the roll, and a delayed tape

**H-F1.** Written and committed 2026-09-18 **before any code exists**, because
this changes *what the live trader is allowed to arm* — the same class of change
as the drift guard (`REGISTERED_drift_guard`), the bar-after-exit rule, and the
price band, all of which restrict live to what the engine modelled.

Nothing in this registration touches the screen, the strategies, the ranker's
tiers, or Ben's standing rule of 2026-09-05: **do not remove, deprioritise.**

---

## 1. The two defects, and what is already established

Both were found on 2026-09-17 by `screen_validate`, on the way to a different
question, and both are in `screen_validate_itch_RESULT_20260917.md`.

**(a) The feed is about fifteen minutes behind the tape.** `tv_feed` POSTs to
`scanner.tradingview.com` with no session, and TradingView serves US equities
delayed to an unauthenticated caller. Every name IBKR refused was refused
**12–27 minutes after the simulation first qualified it — median +15.6, 8 of 8,
on both tapes.**

**(b) The first poll of a session arms the PREVIOUS session's screen.**
TradingView's `premarket_*` columns hold the prior session's values until
today's pre-market prints arrive, so the feed's first poll returns yesterday's
screen as ordinary live rows. The blocked files stamp them at **04:00:05,
04:00:06, 04:00:08 and 04:00:26** on four separate sessions — before any bar of
today's session has closed. Eighteen live names across seven sessions are this,
and `screen_validate` had to set them aside before it could read its own
verdict.

**(b) is not the carry-over that was already fixed.** On 2026-09-12 `Ranking`
was given `begin_session()` so a process spanning midnight stopped carrying
yesterday's names as COLD. That fix is correct and stays. It cannot touch this
one, because here the names **arrive fresh from the endpoint**, as rows, with
yesterday's numbers in them. A memory that forgets perfectly is no defence
against a source that repeats itself.

---

## 2. What ships now, and what does not

**(b) ships as a code change in this bundle. (a) does not.** (a) is an
entitlement and architecture question — a logged-in session with Ben's existing
US Market Data bundle, or IB's scanner, which is real-time — and this project's
standard is to measure before changing. A probe is registered in §5 and runs
first. **No behaviour change for (a) is in this bundle.**

---

## 3. The rule for (b), stated exactly

> **A name may not reach the watchlist until its `premarket_volume` has been
> observed to CHANGE, at least once, within the current session.**

- Scoped per session. `begin_session(day)` clears it, exactly as `Ranking`'s does.
- Once a name has been admitted it **stays** admitted for the rest of the
  session, whatever its volume does afterwards.
- A row whose `premarket_volume` is missing, non-numeric or NaN is **not**
  admitted — it cannot be shown to have moved. (NaN compares unequal to
  everything, so an unguarded `!=` would admit it. That trap was added to the
  index this morning from a different study.)
- A held name is excluded from the file **entirely** — not written as COLD.
  COLD symbols are armed by the trader too; a tier is an ordering, not a veto.

**There is no free parameter.** No threshold, no window, no grace period, no
clock. That is deliberate: a threshold here would be fitted to four observed
stamps between 04:00:05 and 04:00:26, and §4 of the index has a row about
exactly that kind of number.

### The safety property, which is what makes this cheap

**The gate can only ever delay a name's FIRST appearance. It can never remove a
name already in the file.** A test asserts it directly. This is what keeps the
change compatible with "do not remove but deprioritise" and with the rule that
dropping a name mid-session orphans a held position.

### What it costs, stated before the run

One poll — ten seconds — for a name that is actively printing. **The screen
itself bounds this:** the shipped screen is three clauses, and one of them is
`premarket_volume >= 100,000`, so an admitted name has already traded a hundred
thousand shares since 04:00 and is not sitting still. The pathological case for
a wait-for-a-print rule is a thin name, and a thin name does not clear that
clause.

(Written first as "`premarket_volume >= 100,000` **and**
`relative_volume_10d_calc >= 5`", which is wrong: relative volume was removed
from the screen on 2026-09-08 and is retained in `tv_screener` for
`day_over_day_only()` and the record only. Corrected here rather than quietly,
because the clause was load-bearing in the cost argument above and a
registration that overstates its own bound is the thing §4 warns about.)

The one real cost is a **mid-session restart**: the feed comes up at 06:00, every
name is unproven again, and each waits for its next print. Bounded by the same
argument, accepted, and **not** mitigated with persisted state — a state file
read inside the live loop is a new failure mode to buy back ten seconds.

---

## 4. What the first live session on this must show

Registered before the code, falsifiable, and read off the log rather than argued:

1. **Between one and roughly a dozen names HELD in the first minute**, and the
   held set at 04:00:0x should look like the previous session's list. Zero held
   names on a session where the previous day had a watchlist **fails** — the
   gate did not engage.
2. **The held count falls to zero, or near it, within the first few minutes.** A
   name still held at 05:00 is either genuinely not trading today (correct, and
   it should never have been on the screen) or the gate is stuck. Both are
   visible; they are distinguished by whether the name prints at all that day.
3. **No `Error 201` / closing-only block stamped at 04:00:0x.** That stamp is the
   signature of the defect and it should stop appearing.
4. **The file never shrinks because of the gate.** Any name written once stays
   until the ranker's cap trims it from the cold end.

If (1) fails on two consecutive sessions the mechanism is wrong, not the
threshold — there is no threshold — and it comes out.

---

## 5. The probe for (a), and for making (b) EXACT rather than inferential

`common/tv_probe.py`. Read-only: it never takes the writer lock, never writes
`watchlist.txt`, and cannot move the trader. Ben runs it locally at a session
start; it writes a report and a CSV.

**5.1 Is there a column that dates the row?** The rule in §3 infers freshness
from movement because nothing observed so far dates a row. If TradingView
carries an update-time column, the inference can be replaced by an exact test
later. The probe asks for a list of candidate column names and reports, per
candidate, whether values came back. **It is a probe precisely because column
names are guesses** — `tv_screener`'s own docstring records how much of that
mapping took guessing, and `ignored_filters` exists because the server accepts
things it then does not do.

**5.2 Observe the roll directly.** Every poll, every returned row's
`premarket_volume`, to CSV, from before 04:00 through the first half hour. Today
the roll is *inferred* from four blocked stamps. After one morning it is
measured: for each name, the poll at which its volume first moved.

**5.3 Price the delay, authenticated against not.** With `TV_SESSIONID` set in
the environment — **never a CLI flag**, the same rule `DATABENTO_API_KEY`
carries, because a flag puts the secret in shell history — the probe runs both
arms against the same query on the same poll and reports, per name, the
difference in the minute each arm first returns it. The registered reading is
the **median first-seen difference across names**, and the prediction is
**10–20 minutes**, consistent with the 12–27 minute band and +15.6 median the
blocked stamps already gave from the other direction.

**A result that reads ~0 would mean the delay is not the endpoint**, and would
send the 15-minute finding back to be re-explained rather than fixed.

---

## 6. My registered prediction, on the record

**(b):** the gate holds between two and twelve names on the first poll of a
session and the 04:00:0x blocked stamps stop. High confidence — the mechanism is
observed on four sessions and the rule tests the one thing that distinguishes a
stale row from a live one.

**(a):** the authenticated arm leads the unauthenticated one by 10–20 minutes,
median across names. Moderate confidence. The alternative I would bet on second
is that TradingView serves the scanner endpoint delayed **regardless of session
cookie**, because the entitlement is attached to the charting feed rather than
the scanner — in which case the fix is IB's scanner, `brokers/ibkr/scanner.py`
already exists, and the cost moves from credentials to reconciling two screen
definitions.

## 7. Nothing else changes

The screen is untouched. `Ranking`, the three tiers, the size cap and the
ordering are untouched. No strategy constant is read, written or swept here.
`holdout.json` is not involved. The gate sits between `fetch()` and the ranker,
and it is the only new thing in the live path.
