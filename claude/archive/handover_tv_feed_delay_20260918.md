# Handover — the tv_feed delay is measured, and it is fixable for free

From: strategy build and test chat.
To: the UI build chat (and the live paper-trade analysis chat, which raised it).
Written 2026-09-18, Sydney evening / New York pre-market.

**Short version: the watchlist feed is delayed by exactly 15 minutes because it
is not logged in. Ben's TradingView premium subscription fixes it, the change is
one HTTP header, the code is written and tested, and it is dormant until two
environment variables are set. Nothing costs money.**

This answers `claude/handover_live_screen_feed_20260918.md` §3 items 1 and 2.
Bundle **`build-20260918j`**, prerequisite `b93a138`.

---

## 1. What was measured, and how

`common/tv_probe.py`, run by Ben during live pre-market, twice — 04:08 ET for 35
minutes and 05:41 ET for 3 minutes, both with the session cookies set.

TradingView returns an **`update_mode`** column that answers the question
directly, so nothing here is inferred:

```
  plain  DELAYED     update_mode = 'delayed_streaming_900'
  auth   STREAMING   update_mode = 'streaming'
```

**900 seconds is fifteen minutes, stated by the vendor in the value itself.**
Both runs agree.

That number matches the one `screen_validate` reached from the opposite
direction on 2026-09-17 — every name IBKR refused was refused 12–27 minutes
after the tape first qualified it, median **+15.6**. Two independent routes, the
same answer, and this one is TradingView saying it rather than us deducing it.

**Corroboration from first appearances.** The 04:08 run also compared when each
name first appeared in each arm: CPOP **+15.1 min**, SSM **+7.3 min**, median
**+11.2** across two names, with TCRT returned only by the authenticated arm.

**A reading not to be misled by.** The 05:41 run shows §5.3 as **+0.0 minutes**.
That is a window artefact, not a contradiction: a first-appearance comparison
only measures anything if the probe is already running *before* the names
qualify. Starting mid-session, both arms have every name on the first poll and
the delta is zero by construction. `update_mode` is the reading that does not
depend on when the probe starts.

---

## 2. Why the feed was delayed at all

`common/tv_feed.py` POSTs to `scanner.tradingview.com` with `Content-Type` and a
browser `User-Agent` and **nothing else**. No cookie, no token — nothing in the
repo has ever read a TradingView login. So the premium entitlement Ben pays for
has never reached the process that builds the watchlist, and TradingView serves
an unauthenticated caller delayed US equity data.

---

## 3. What is in the bundle, and what it does NOT do

**Cookie support, dormant.** `tv_feed` sends the cookie when **both**
`TV_SESSIONID` and `TV_SESSIONID_SIGN` are set in the environment, and
`--no-cookie` forces anonymous even when they are. **With the environment empty
nothing changes at all** — a test asserts the request carries exactly
`Content-Type` and `User-Agent` and no third header.

**Both cookies or neither, and this is the part worth knowing.** TradingView
*signs* the session: `sessionid` on its own is accepted and served
**anonymously**. A half-set environment would look logged in, read delayed data,
and raise nothing anywhere. A half-set pair now logs an ERROR naming exactly
that and sends no cookie. My own first version of the probe had this wrong — it
sent `sessionid` alone, which would have made the authenticated arm anonymous,
agreed with the delayed arm perfectly, and reported "the login makes no
difference". The analysis chat's `tv_delay_probe.py` had it right and is where
the correction came from.

**An `update_mode` check at startup.** One extra request when the feed starts,
so the 1,980 polls of a session stay byte-identical to what they were. Three
deliberately different levels:

- `streaming` → INFO.
- delayed **with** a cookie sent → **ERROR**, naming expiry. This is why the
  check exists: a stale cookie does not fail, the endpoint simply serves the
  anonymous feed, and a delayed watchlist looks identical to a real-time one.
- delayed with no cookie → WARNING, because that is the shipped state today.

**The screen is untouched.** Same endpoint, same three clauses, `failing_clauses`
still derived from `FILTERS`. **Only the latency changes.**

---

## 4. The operational detail that will bite if it is missed

**The cookies must live in the environment the trader runs under, not in a
PowerShell session.** A variable set in one shell dies with that shell, and the
feed runs from `D:\TradingProd`. So: a machine or user environment variable, or
resolved from the Trading vault at launch. They are secrets — environment or
vault, never the repo, never a CLI flag (a flag puts them in shell history), and
the probe and feed never log or write the values.

**They expire.** The `update_mode` ERROR line is the only thing that will tell
anyone. Whatever the UI ends up showing, **a "feed is delayed" state is worth
surfacing there** — it is the difference between the trader seeing the market
and seeing it a quarter of an hour late, and it is invisible from the watchlist
itself.

---

## 5. The other free option, and why I would not take it

IB's own scanner (`brokers/ibkr/scanner.py`) had never been run. Ben ran
`main.py --mode scan --preview` at 05:48 ET today and **it works pre-market** —
the open question in that file is now settled. It returned 5 names and would
have written IMCC, SSM, TCRT. Free, real-time, and it only surfaces names IBKR
will actually let the account open, which removes the ~25% it refuses outright.

It also agrees with the authenticated TradingView arm: IMCC was one of the two
names **only** the authenticated arm returned at 05:41.

**But it is not the same screen.** IB ranks by `TOP_PERC_GAIN` and takes the top
three. Ben's screen is three clauses — pre-market change ≥ 20%, price $2–25,
pre-market volume ≥ 100,000. Every backtest figure in the project sits on the
simulated version of *that* screen, and `screen_validate_itch_RESULT_20260917`
established it reproduces the live one at 49 of 51 names. Switching the live
feed to IB's ranking would replace the universe with a different one and discard
that validation.

So: **option B (the cookie) for the feed, option A (IB) kept as a cross-check on
refusals and as the fallback if the cookie path ever stops working.**

---

## 6. What this changes for the paid options

**Databento live (option C) stays closed** — entitled for EQUS.MINI only, which
is ~4.8% of the consolidated tape, so the 100,000-share clause cannot be
reproduced there (`claude/databento_live_entitlement_20260918.md`).

**The $199/month consolidated feed (option D) is not a decision anyone can make
honestly this week.** §3 item 3 of the original handover wanted the delay's cost
quantified before paying to remove it — and that measurement **cannot be done
retrospectively**: `var/archive/watchlist_YYYYMMDD.txt` is a single 09:29
snapshot with no per-name arrival times, and `var/logs/` holds one backtest log
from 09-03. The bundle instruments it going forward (`Arrivals`, one line per
name per session into `var/archive/watchlist_arrivals_YYYYMMDD.csv`), so the
distribution exists after a week of sessions. **And with the delay about to be
removed for free, the thing D was going to buy is mostly already bought.**

---

## 7. What has not happened yet

- **Nothing is promoted.** `tv_feed` runs from `D:\TradingProd`, so none of this
  is live until after a close. Promote after today's, with the cookies in the
  trader's environment.
- **The 04:00 roll capture is still owed.** Today's probe started at 04:08, past
  the session open, so H-F1's carry-over observation was partly missed. Tomorrow
  at 04:00, 35 minutes.
- **`premarket_time` may make the freshness gate exact.** It came back as a real
  value and was observed to **roll from yesterday's 04:00 ET to today's between
  the 04:08 and 05:41 runs** — which is the 04:00 carry-over, dated precisely,
  where the shipped gate has to infer it by waiting for volume to move. Not
  acted on: both readings came from the delayed arm only. Tomorrow's run prints
  the dating columns for both arms side by side, which settles it.

## 8. Files

| | |
|---|---|
| The measurement | `D:\Trading\Claude outputs\tv_probe_20260918.txt` (3-min run), `tv_probe_20260918_auth35.txt` (35-min run) |
| The registration | `docs/research/REGISTERED_feed_freshness.md` (H-F1) |
| The code | `common/tv_feed.py`, `common/tv_probe.py`, `brokers/ibkr/scanner.py` |
| The bundle | `build-20260918j.bundle`, prerequisite `b93a138` |
| Prior context | `claude/handover_live_screen_feed_20260918.md`, `claude/feed_handover_REPLY_20260918.md` |
