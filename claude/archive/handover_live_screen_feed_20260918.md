# Handover — the live screening feed: what it is today, what it could be

From: live paper-trade analysis chat (read-only on production).
To: strategy build and test chat.
Written 2026-09-18 (Sydney). Nothing in `D:\TradingProd` was changed; nothing in `D:\Trading` was edited.

Ben's question: the watchlist feed looks like it is on delayed data, and he holds a TradingView
premium subscription with the US market bundle. Can it use real-time data instead?

Related project docs: `claude/databento_live_entitlement_20260918.md` (measured today),
`common/tv_screener.py` (the screen, pinned), `common/tv_feed.py` (the poller),
`brokers/ibkr/scanner.py` (the unrun alternative).

---

## 1. What is established

**`tv_feed` is not logged in.** `common/tv_feed.py` posts to
`https://scanner.tradingview.com/america/scan` with `Content-Type` and a browser `User-Agent`
and nothing else. No cookie, no token; nothing in the repo reads a TradingView login. So Ben's
premium entitlement does not reach it, whatever that entitlement is worth.

**Whether that feed is delayed is still UNMEASURED.** TradingView returns an `update_mode`
column that says so directly (`streaming` vs something containing `delayed`). Probe written
and delivered, not yet run: `D:\Trading\Claude outputs\tv_delay_probe.py`. It sends the same
request `tv_feed` sends, prints `update_mode` and the three screened columns, and optionally
repeats the request with `TV_SESSIONID` / `TV_SESSIONID_SIGN` from the environment so the two
can be compared. Writes nothing.

**The tvremix MCP cannot drive `tv_feed`.** Two independent reasons, and only the first is
fatal on its own:
- MCP tools are Claude-facing. `tv_feed` is an unattended Python process running 5.5 hours; it
  cannot call one. (`tv_feed`'s own docstring already says this.)
- Whether tvremix's screener data carries Ben's entitlement is unknown. Its account connection
  is real — `my_watchlists` returns his lists, including "MCL Today" — but reading his account
  does not prove the quote path is real-time.

**Databento live is entitled for EQUS.MINI only.** Measured 2026-09-18 with
`D:\Trading\Claude outputs\databento_live_entitlement.py`:

```
EQUS.MINI      OK        session opened, 2 record(s) in 4s
XNAS.BASIC     REFUSED   A live data license is required to access XNAS.BASIC.
XNAS.ITCH      REFUSED   A live data license is required to access XNAS.ITCH.
DBEQ.BASIC     REFUSED   A live data license is required to access DBEQ.BASIC.
```

`metadata.list_datasets()` listed 29 datasets including both XNAS feeds on the same key, so
**it is not an entitlement list** — only the live gateway answers that question.

EQUS.MINI is a median **4.8% of the consolidated tape** (`PROGRAM_INDEX` §3). Against the three
clauses: pre-market change and the price band survive that; **pre-market volume >= 100,000 does
not** — on a twentieth of the tape it is asking for ~2M consolidated, and the share varies by
name and venue mix. Databento live also does not deliver the prize (live screen and backtests
on one tape), because the backtests are XNAS and XNAS is not licensed live here.

**Alpha Vantage is not a candidate.** Per-symbol REST with rate limits and no cross-sectional
pre-market scan.

---

## 2. The four options, cheapest first

| | what it is | cost | keeps the screen's meaning? | state |
|---|---|---|---|---|
| **A. IB scanner** | `brokers/ibkr/scanner.py`, already written, writes `watchlist.txt` | free | unknown — IB's own columns, not TradingView's | **never run**; `--preview` settles it |
| **B. TradingView cookie** | one `Cookie` header on the request `tv_feed` already makes | free | exactly — same endpoint, same clauses | needs the delay probe first |
| **C. Databento EQUS.MINI** | live stream already entitled | usage only | no — volume clause breaks | needs the share-stability study (§4) |
| **D. Massive (Polygon.io) Advanced** | consolidated real-time, full-market snapshot | **USD 199/mo** | yes — consolidated tape, all three clauses | needs a paid month to evaluate |

**Massive's Developer plan at $79 is 15-minute delayed** and therefore pointless here. Only
**Advanced at $199** carries real-time. Massive is Polygon.io rebranded — the vendor the
project shortlisted in `overview.md` — and it offers 55+ venues including the FINRA TRFs
(100% of volume), a **full-market snapshot endpoint** covering 10,000+ tickers in one request,
extended hours 04:00–20:00 ET, unlimited calls, websockets, and 20+ years of tick history.

---

## 3. The order of work

**A and B are free and unrun. Do them before spending anything.**

1. **`tv_delay_probe.py`, during pre-market**, anonymous and then with the cookies. Outcomes:
   - anonymous says `streaming` → **there is no delay and this whole line of work closes.**
   - anonymous delayed, logged-in streaming → option B is a one-header change.
   - both delayed → the scanner endpoint ignores the login; B is dead, go to A or D.
2. **`main.py --mode scan --preview`, during pre-market with Gateway up.** Client id 55, places
   nothing, writes nothing. The open question in the file: whether IB's percent-gain scans
   compute before 09:30. If they do, real-time screening costs nothing and only surfaces names
   IB will actually let the account open — which removes the ~25% of TradingView names IBKR
   refuses outright.
3. **Quantify the cost of the delay before paying to remove it.** For the sessions on record,
   compare the minute each name first appeared in `var/archive/watchlist_YYYYMMDD.txt` against
   the minute `screen_at` says it first met the screen on the archive tape. The output is a
   distribution of minutes-late, not an anecdote. If the median is a minute or two, D is not
   worth $199/mo; if it is 15, that is 15 minutes of a 5.5-hour window on a strategy whose
   candidate edge sits early.

---

## 4. If option C is pursued anyway (data already on disk)

**Is EQUS.MINI's share of volume stable enough to re-derive the 100k floor?** Per symbol-day
over 04:00–09:30, compute MINI volume ÷ XNAS volume from `bar_cache_db` and `bar_cache_xnas`
(or the `ohlcv-1m` archive) and report the **distribution**: p10/p50/p90 across symbol-days,
and the dispersion *within* a symbol across days.

- tight → a scaled floor (~5k on MINI) is defensible and MINI live can run the screen
- wide → the volume clause cannot be reproduced there, and C is closed

Register before running. Report both denominators.

---

## 5. If option D is bought, what the first month must establish

Buy **Advanced**, not Developer. Then, before anything in the repo depends on it:

1. **Does the snapshot carry pre-market volume, or must it be summed from minute bars?** On
   Polygon's schema the `day` aggregate is the regular session. This decides how the screen is
   written, and it is the first thing to check.
2. **Is their change-vs-previous-close the same quantity as `premarket_change`?** The screen's
   definition is pre-market close minus the previous REGULAR-session close, over that close
   (`tv_screener.py`). Confirm rather than assume.
3. **Subscriber status.** Real-time plans ask professional vs non-professional; the answer
   changes entitlement and price.
4. **Run it in parallel for a week, writing to a second file** — never straight into
   `watchlist.txt`. Then compare, per morning: which names each surfaced, the minute each was
   surfaced, and the pre-market volume each reported against the archive tape. That is the same
   comparison §3 item 3 defines, and it is what `screen_sim`'s validation has always lacked.
5. **Only then** decide whether it also replaces Databento for history. 20+ years of
   consolidated tick data would put the live screen and the backtests on one tape at last
   (`PROGRAM_INDEX` §7 items 1 and 21) — but every published figure is on XNAS, so that is a
   re-baselining with its own registration, not a side effect of a feed swap.

---

## 6. Constraints that apply whichever way this goes

- A TradingView cookie is a **secret**: environment variable or the Trading vault, never the
  repo, and never printed. It expires, so the feed must **check `update_mode` at startup** and
  say so loudly — a silently expired cookie puts the screen back on delayed data while looking
  identical.
- A Massive API key is the same, and `PROGRAM_INDEX` §1 already covers the pattern.
- The screen's clauses live in `common/tv_screener.py` and are **derived, not restated**
  (`failing_clauses` reads `FILTERS`). Any new feed adapter must keep that property, or the
  "why did this name drop" message starts describing a screen that is not running.
- `tv_feed` holds the watchlist-writer lock. A second feed writing the same file at the same
  time is the failure mode that lock exists for; a parallel run writes to its own file.
- Nothing is promoted mid-session.

## 7. Deliverables Ben expects

- Each result as a `.txt` in `D:\Trading\Claude outputs` **and** a published artifact page
  (negatives bracketed and red).
- Exact PowerShell commands, one per line, full paths.
