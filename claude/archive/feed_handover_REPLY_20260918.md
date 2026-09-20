# Reply to the live-feed handover — one correction, one defect found in my own work, one item that cannot be done as written

2026-09-18, build chat, answering `claude/handover_live_screen_feed_20260918.md`.
Bundle **`build-20260918g`**, which **supersedes `d`, `e` and `f`** — pull only
`g`. Prerequisite is still `b93a138`. **3,834 tests pass.**

---

## 0. First, the duplication — two chats built the same probe

About an hour before this handover arrived I built `common/tv_probe.py` in this
chat, for the same question, from the other end: the 04:00 carry-over rather than
the delay. It is committed, tested, and does everything
`D:\Trading\Claude outputs\tv_delay_probe.py` does, plus the roll capture.

**Their script was right about something mine had wrong**, so this is not a case
of preferring my own work — see §1. I have folded what theirs knows into the repo
module. **Run the repo one**, `python -m common.tv_probe`, and treat
`tv_delay_probe.py` as a second opinion if you ever want one; two implementations
disagreeing would be informative, and it costs nothing to keep.

---

## 1. The defect the handover caught in my code

My probe sent `sessionid` and **only** `sessionid`. Their script sends
`sessionid` **and** `sessionid_sign`.

That is not cosmetic. **TradingView signs the session.** `sessionid` alone is
accepted by the endpoint and served **anonymously**. So my authenticated arm
would have been an anonymous request wearing a login: the two arms would have
agreed perfectly, the report would have said **"the login makes no difference"**,
and option B would have been closed for exactly the wrong reason — with no error
anywhere.

That is §4's recurring shape, *a control whose output is indistinguishable from
the failure it detects*, and it would have cost this line of work a week.

Fixed, and hardened past the original: **both cookies or neither.** A half-set
environment now produces an **ERROR** that names what would otherwise have
happened, and no cookie is sent at all. `cookie_header`, `mode_verdict`,
`COOKIE_ENV`, `SIGN_ENV` and `MODE_COLUMN` now live in `common/tv_feed.py` — the
**live** module — and `tv_probe` imports them, so the probe cannot measure one
definition of "signed in" while the feed uses another.

---

## 2. What is in the bundle

**The `update_mode` startup check you asked for (§6).** `tv_feed` reads the
column once at startup, in its **own** request, so the 1,980 polls of a session
stay byte-identical to what they were. The three cases are deliberately different
log levels:

- **streaming** → INFO, and says whether it is signed in.
- **delayed WITH a cookie sent** → **ERROR**, naming expiry. This is the case the
  check exists for: a stale cookie does not fail, the endpoint simply serves the
  anonymous feed, and a delayed watchlist is indistinguishable from a real-time
  one by looking at it.
- **delayed with no cookie** → WARNING, because that is today's shipped state and
  logging it at ERROR would train the reader to ignore the line that matters.

**Cookie support, dormant.** `tv_feed` will send the cookie when both environment
variables are set, and `--no-cookie` forces anonymous even when they are. **With
the environment empty nothing changes**, and a test asserts the request carries
exactly `Content-Type` and `User-Agent` and no third header. I built the
capability now so that if tomorrow's probe says "delayed anonymously, streaming
signed in", option B is one environment variable away rather than a day away —
but nothing is decided by building it.

**The screen is untouched**, `failing_clauses` still derives from `FILTERS`, the
probe never takes the writer lock and never writes `watchlist.txt`.

---

## 3. §3 item 3 cannot be done as written, and here is the evidence

> *"compare each name's first appearance in `var/archive/watchlist_YYYYMMDD.txt`
> against the minute `screen_at` says it first met the screen"*

**The archive has no per-name arrival times.** `watchlist_20260916.txt` is a
single snapshot stamped `09:29:56` — one file per session, written at the end.
The only timestamps in the archive are on **blocked** entries, which is precisely
why the existing reading (median +15.6 minutes, 12–27 min band) has **n = 8**.

And there is no second source: `var/logs/` contains **one** file,
`backtest_run_20260903.log`. The feed's own INFO lines, which do carry arrival
times, are not retained anywhere.

So the distribution cannot be recovered retrospectively at all. **It can only be
instrumented.** The bundle adds `Arrivals`: one line per name per session, written
the moment the name is first written to the watchlist, to
`var/archive/watchlist_arrivals_YYYYMMDD.csv` —

```
ticker,first_et,tier
VEEA,2026-09-19 04:00:05,hot
```

It appends, so a mid-session restart keeps what it had, and a disk failure costs
a row and never a poll. **After a week of sessions the minutes-late distribution
is a `screen_at` join away instead of an anecdote.** I have deliberately *not*
written that join yet — there is no data for it to read until the feed has run
with this.

One deliberate choice worth flagging: it stamps what was **written to the file**,
not what screened, because the question is when the *trader* could first have
acted and the trader reads the file.

---

## 4. What I did not do, and why

**Option C's share-stability study (§4 of the handover) — not built.** It is
well specified and the data is on disk, but it is downstream of a question that
tomorrow morning may close for free. If the anonymous probe says `streaming`, C
and D both die on the spot.

**Option D — nothing spent, nothing prepared.** Item 3 was supposed to price the
delay before paying to remove it, and item 3 cannot be run until the instrument
above has collected a week. So **$199/mo is not a decision that can be made
honestly this week**, and I would not make it on the n=8 blocked-name reading.

**The IB scanner (§3 item 2) — one small change, then it is yours to run.**
`--preview` existed and **printed to the terminal**, which collides with the
standing rule that every result is a file. Redirecting it in PowerShell is not
the fix — `>` and `Tee-Object` both write UTF-16, the encoding trap this repo
already carries a guard for. So it now writes its own report through
`report_io.emit` (painted to the terminal, plain UTF-8 to disk) at
`--preview-out`, default `var/reports/scan_preview.txt`. It still takes no lock
and still writes no watchlist, so it is safe beside a live feed — which is the
whole point of it.

---

## 5. The commands, in the handover's order

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260918g.bundle" main
```

```
python -m pytest tests\ -q
```

### Step 1 — the delay probe, during pre-market (04:00 ET = 18:00 your time)

**One run answers everything**, and it reads `update_mode` for both arms at the
top of the report before anything else. Set the cookies first if you have them —
**both variables or neither**, since one alone is silently anonymous and the
probe refuses to claim an authenticated arm ran:

```
$env:TV_SESSIONID = op read "op://Trading/TradingView/sessionid"
```

```
$env:TV_SESSIONID_SIGN = op read "op://Trading/TradingView/sessionid_sign"
```

```
python -m common.tv_probe --minutes 35
```

```
copy var\reports\tv_probe.txt "D:\Trading\Claude outputs\tv_probe_20260919.txt"
```

```
copy var\reports\tv_probe.csv "D:\Trading\Claude outputs\tv_probe_20260919.csv"
```

If the cookies are not in 1Password yet, take them from a logged-in TradingView
tab (DevTools → Application → Cookies → `sessionid` and `sessionid_sign`) and put
them **in the Trading vault**, not at a prompt. Without them the run still
happens and still reads the anonymous `update_mode` — which is the reading that
can close the line on its own — it just cannot price §5.3.

**Do not pass `--no-columns`.** That flag skips the `update_mode` probe, which is
the one thing here that settles the question. (I had it in an earlier draft of
these commands, which was wrong.)

### Step 2 — the IB scanner preview, same window, Gateway up

```
python main.py --mode scan --preview
```

```
copy var\reports\scan_preview.txt "D:\Trading\Claude outputs\scan_preview_20260919.txt"
```

**A scan that returns nothing pre-market is the ANSWER, not a failure** — it
means IB does not compute percent-gain scans before 09:30, which closes option A.
The report says so in as many words, so the zero-row case cannot be misread as a
broken scanner.

### Step 3 — nothing to run yet

The arrivals file starts filling on the next session the feed runs from
production. **The feed is promoted after a close, not mid-session**, so the
earliest it collects is the session after you promote.

---

## 6. What each probe outcome means, written before it runs

| anonymous | signed in | what follows |
|---|---|---|
| **streaming** | — | **The whole line closes.** No cookie, no IB scanner, no $199. Whatever made the watchlist look late is somewhere else — and the 04:00 carry-over that H-F1 fixes is the leading candidate for exactly that appearance. |
| delayed | **streaming** | Option B, and it is one environment variable. The startup check then earns its keep permanently. |
| delayed | delayed | B is dead. IB's scanner is the remaining free move; after that it is a paid consolidated feed, and it still should not be bought until the arrivals series has priced the delay. |
| delayed | not run | Unmeasured. Set both variables and repeat — do not read the anonymous arm alone as an answer about the login. |

**My prediction, on the record:** anonymous reads delayed with a value spelling
the delay in seconds, and signed-in reads streaming. Moderate confidence. My
second bet is that the scanner endpoint ignores the login entirely, because the
entitlement attaches to the charting socket rather than the scanner — in which
case B dies and the free move is IB.

---

## 7. What has not changed

`D:\TradingProd` is untouched. Nothing is promoted. `holdout.json` is shut. No
strategy constant was read or written, and nothing in this bundle can alter what
either engine trades — the feed decides which names are *watched*, and the H-F1
gate can only ever delay a name's first appearance, never remove one already in
the file.
