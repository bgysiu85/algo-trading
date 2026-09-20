# The feed fix, and the probe that measures what is still guessed

2026-09-18, build chat. Bundle **`build-20260918d`** — `ef9a5d9` the
registration, `8b0ca58` the code, each committed before the next existed.
Registered in `docs/research/REGISTERED_feed_freshness.md` (H-F1).
**3,761 tests pass. Mutation-tested 10/10.**

## What it fixes

TradingView holds the previous session's `premarket_*` values until today's
pre-market prints arrive. So `tv_feed`'s **first poll of a session returns
yesterday's screen as ordinary live rows** — and the trader arms every name in
the file. The blocked files stamp them at 04:00:05, 04:00:06, 04:00:08 and
04:00:26 on four separate sessions, before a single bar of today has closed.
Eighteen live names across seven sessions are this, and `screen_validate` had to
set them aside before it could read its own verdict.

This is **not** the carry-over that was fixed on 09-12. That one was the ranker
remembering across midnight, and that fix is right and stays. Here the names
arrive *fresh from the endpoint*, carrying yesterday's numbers — a memory that
forgets perfectly is no defence against a source that repeats itself.

**The rule, and it has no free parameter:** a name may not reach the watchlist
until its `premarket_volume` has been seen to change within the session. No
threshold, no grace window, no clock — four stamps between 04:00:05 and 04:00:26
are exactly the kind of number a window gets fitted to.

**Why it is safe:** the gate can only ever delay a name's *first* appearance. It
can never remove a name already in the file, so it cannot orphan a position and
your "do not remove but deprioritise" rule is untouched. A held name is withheld
entirely rather than written as COLD, because the trader arms COLD names too.

**What it costs:** one poll — ten seconds — for a name that is trading. The
screen's own `premarket_volume >= 100,000` clause means an admitted name has
already traded a hundred thousand shares since 04:00.

## Pull it and test it

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260918d.bundle" main
```

```
python -m pytest tests\ -q
```

## Do NOT promote before tomorrow's session — and that is deliberate

`tv_feed` runs from `D:\TradingProd`, so **the gate does nothing until it is
promoted**, and promotion is after a close as always. That is the right order
here for a second reason: tomorrow morning's session runs on the *unfixed* feed,
which is the last clean chance to measure the defect with the probe below before
the fix removes it. Promote after tomorrow's close.

## The probe — run it tomorrow at the open of pre-market

**04:00 ET is 18:00 your time** (ET is on daylight time, you are not yet). Run it
beside the live session; it is read-only, never takes the writer lock, and
cannot touch `watchlist.txt`.

It answers three things that are currently inferred rather than measured:
whether any TradingView column actually *dates* a row (which would let the gate
stop inferring), the 04:00 roll itself name by name, and what the ~15-minute
delay really is.

The third needs a logged-in session cookie. **Set it as an environment variable,
never as a flag** — a flag puts it in your PowerShell history, the same rule
`DATABENTO_API_KEY` carries. If it is in the Trading vault:

```
$env:TV_SESSIONID = op read "op://Trading/TradingView/sessionid"
```

If it is not in 1Password yet, get it from a logged-in TradingView tab —
DevTools, Application, Cookies, `sessionid` — and put it in the Trading vault
first rather than pasting it at a prompt. **Without it the probe still runs**
and still measures the roll; it just cannot price the delay.

Then, at 18:00:

```
python -m common.tv_probe --minutes 35
```

```
copy var\reports\tv_probe.txt "D:\Trading\Claude outputs\tv_probe_20260919.txt"
```

```
copy var\reports\tv_probe.csv "D:\Trading\Claude outputs\tv_probe_20260919.csv"
```

The CSV is the raw record and can be re-read any time without polling again:

```
python -m common.tv_probe --replay var\reports\tv_probe.csv
```

## What the probe should show, written before it runs

- **Names that never move inside the window are the carry-over.** A row whose
  volume is identical at 04:00:05 and at 04:35 is describing yesterday.
- **The authenticated arm should lead the plain one by 10–20 minutes**, median
  across names — consistent with the +15.6 median the blocked stamps gave from
  the other direction.
- **A reading near zero would be the interesting result**: it would mean the
  delay is not the endpoint at all, and the 15-minute finding needs another
  explanation. My second bet is that the scanner is delayed *regardless* of the
  cookie, because the entitlement attaches to the charting feed — in which case
  the fix is IB's scanner, `brokers/ibkr/scanner.py` already exists, and the cost
  moves from credentials to reconciling two screen definitions.

## What the first promoted session should show

Registered before the code, so it can falsify rather than be interpreted:

1. **Between one and roughly a dozen names HELD in the first minute**, and they
   should look like the previous session's list. Zero held on a session after a
   day with a watchlist means the gate did not engage — that is a failure.
2. **The held count falls to zero or near it within a few minutes**, visible in
   the watchlist header as `held=N`.
3. **No `Error 201` closing-only block stamped at 04:00:0x.** That stamp is the
   defect's signature and it should stop appearing.
4. **The file never shrinks because of the gate.**

If (1) fails twice the mechanism is wrong rather than mistuned — there is
nothing to tune — and it comes out.

## Nothing else changed

The screen is untouched. The ranker, the three tiers, the size cap and the
ordering are untouched. No strategy constant is read or written. `holdout.json`
is not involved.
