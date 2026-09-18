# The feed probe — result, 2026-09-18: the login makes the scanner real-time, and the anonymous delay is spelled out as 900 seconds

Registered in `docs/research/REGISTERED_feed_freshness.md` (H-F1, ef9a5d9; §5
the probe, §6(a) the prediction). Written up in the MCL chat because Ben
brought the reports here; the registration and the tool (`common/tv_probe.py`,
bundle `build-20260918g`) are the build chat's. This scores **§5 and §6(a)
only** — the (b) gate is scored later, from `watchlist_arrivals_*.csv`, once
the feed has run a session with it.

Two runs on 2026-09-18, both with the authenticated arm:
`python -m common.tv_probe --minutes 35` from 04:08:52 to 04:43:53 ET (197
polls, `Claude outputs\tv_probe_20260918_auth35.txt`), and a three-minute
repeat at 05:42–05:45 ET (17 polls, `var\reports\tv_probe.txt`). Cost $0.00.
Artifact page: "Feed Probe".

**Headline. The endpoint honours the login. Anonymous, `update_mode` reads
`delayed_streaming_900` — TradingView names the delay itself, 900 seconds,
fifteen minutes. Signed in, it reads `streaming`. Both runs, both arms,
no exceptions. Option B is the fix and it is already built: set
`TV_SESSIONID` and `TV_SESSIONID_SIGN` in the window that starts the feed and
the watchlist is real time from that session on.** The one name whose
first appearance the probe saw on both arms uncensored, CPOP, reached the
signed-in arm **15.1 minutes** before the anonymous one. And the 04:00
carry-over was watched happening: yesterday's five HOT names sat on the first
poll and never moved in thirty-five minutes.

## 1. §5.1 — is the feed delayed, and does the login change it?

| arm | `update_mode` | verdict |
|---|---|---|
| plain (no cookie) | `delayed_streaming_900` | DELAYED, 900 s |
| auth (`sessionid` + `sessionid_sign`) | `streaming` | STREAMING |

Identical in the 35-minute run and the 3-minute repeat an hour later. The
value is not inferred from timing; it is the server's own label on the row,
and the delay it states is the quarter-hour that `screen_validate` measured
from the block stamps (median +15.6, 10 of 10) before any of this existed.
Two independent readings — the exchange tape against IBKR's refusal clock,
and TradingView's own column — give the same fifteen minutes.

## 2. §5.3 — authenticated against not

| name | anonymous first seen | signed-in first seen | lead |
|---|---|---|---|
| CPOP | 04:43:42 | 04:28:36 | **+15.1 min** |
| SSM | 04:16:11 | 04:08:52 (first poll) | +7.3 min, **censored** |
| TCRT | after 04:43 (window ended) | inside the window | > 0, censored |

The registered reading is the median across names: **+11.2 minutes, n = 2**,
inside the predicted 10–20. Read the rows rather than the median. SSM was
already qualifying on the very first signed-in poll, so its lead is a floor,
not a measurement, and TCRT never reached the anonymous arm before the run
ended. CPOP is the one clean observation and it is 15.1 minutes — the 900
seconds plus one poll interval. The 3-minute repeat at 05:42 reported +0.0 for
SSM and TCRT because both were on both arms before it started; that run
measures nothing about the lead and is kept for §5.1 only.

At the same instant the two arms describe different mornings. 05:41:59, SSM:
anonymous 9,250,122 shares, +82.9%, 2.67; signed in 9,618,929 shares, +87.7%,
2.74. Three minutes later the anonymous change was still +82.87% to the
decimal while the signed-in row had moved to +80.8%. The anonymous arm is a
snapshot that refreshes on TradingView's cadence, not a stream.

## 3. §5.2 — the roll, watched

First poll of the 35-minute run, 04:08:52 ET, anonymous arm: **AEHL, AEMD,
BIAF, DAIC, VEEA** — five of 2026-09-17's six HOT names (NBIG, the sixth,
did not return) — and none of them moved a share in the
thirty-five minutes that followed. SSM arrived at 04:16:11 and moved 32
seconds later; it was today's. That is the mechanism `screen_validate` §2
inferred from four blocked stamps at 04:00:0x, seen directly: the first poll
serves yesterday's screen as ordinary live rows, and a row that never moves
is a row that describes yesterday. The H-F1 gate ("no name until its
`premarket_volume` has changed within the session") would have held all five
and admitted SSM at 04:16:43.

## 4. §5.1's other question — does any column date the row?

Four of the six candidate columns came back with values; two
(`premarket_volume_time`, `pricescale_update_time`) do not exist. Decoded:

| column | 35-min run (04:08–04:43) | 3-min run (05:42) | what it dates |
|---|---|---|---|
| `update_time` | 2026-09-17 19:59:59 ET | 2026-09-17 19:59:58 ET | the previous extended session's close — useless for pre-market |
| `last_bar_update_time` | 2026-09-17 20:15:15 ET | same | likewise |
| `time` | 2026-09-17 09:30:00 ET | same | the daily bar's open — useless |
| **`premarket_time`** | **2026-09-17 04:00:00 ET** | **2026-09-18 04:00:00 ET** | **the session the `premarket_*` values belong to** |

`premarket_time` is the column. On the row the probe sampled during the
first run it said *yesterday*; by 05:42 it said *today*. If that holds per
row — the probe sampled one row per run, not every row — the (b) gate can be
an exact test (`premarket_time` is today's 04:00 ET) instead of an inference
from movement, which is what §5.1 was registered to find out. That is a
second look, not a change: print `premarket_time` per row on the next
first-poll run and check that the five carry-over names say 09-18 04:00
while SSM says 09-19.

## 5. Predictions scored

- **§6(a), 10–20 minutes median, moderate confidence — held.** +11.2 median
  on two names, +15.1 on the one uncensored name, and the server's own
  `900`. The second bet — that the entitlement attaches to the charting
  socket and the scanner ignores the login — is refuted: the scanner
  endpoint reads `streaming` with the cookie.
- **Build chat reply §6, "anonymous reads delayed with a value spelling the
  delay in seconds, and signed-in reads streaming" — held exactly.**
- **§6(b), the gate holds 2–12 names on the first poll and the 04:00:0x
  stamps stop — not scored here.** The five carry-over names above are what
  it would have held on 09-18; the arrivals file scores it once the feed has
  run with it.

## 6. What this decides

- **Item 1d(b), the delay half, closes as a procedure, not a study.** Before
  `run_paper.ps1` or `main.py`, in that window:
  `$env:TV_SESSIONID = op read "op://Trading/TradingView/sessionid"` and
  `$env:TV_SESSIONID_SIGN = op read "op://Trading/TradingView/sessionid_sign"`.
  Both or neither. The startup check in `tv_feed` then logs INFO
  "streaming, signed in"; an expired cookie logs ERROR because the endpoint
  silently reverts to `delayed_streaming_900`, and that line is the only
  thing that distinguishes a delayed session from a live one.
- **A trap, recorded:** `tv_feed` reads the two variables with
  `os.environ.get` and does not resolve `op://` references the way
  `secrets_util` does for `DATABENTO_API_KEY`. `setx TV_SESSIONID "op://…"`
  would send the literal reference as the cookie and be served anonymously
  (the startup check would catch it, as ERROR, misnamed as expiry). The
  `$env: … = op read …` form hands over the value and is correct today;
  routing the pair through `secrets_util.get` is a two-line change for the
  build chat if the set-once form is wanted.
- **Item 1d(a), the `first_seen + 15 min` study, changes purpose.** With the
  login the live feed is no longer fifteen minutes late, so the study cannot
  be about the future of the live trader. It is about the past: every live
  session before 2026-09-18 traded a screen 900 seconds behind the tape, and
  the gap between the live book (47% win, R 0.72) and the v2 simulation
  (21.7%, R 1.67) may partly be that. The number to run it with is now exact.
- **The probe's CSV is per run and overwritten.** The 35-minute run's CSV was
  lost to the 3-minute repeat before it was copied; the file in
  `Claude outputs` named `_auth35.csv` is the repeat's. Copy both files
  before re-running, or the probe should stamp its outputs.
- Nothing about a strategy. `holdout.json` stays shut. `D:\TradingProd`
  untouched.
