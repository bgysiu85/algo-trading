# prior_close is not the defect — the SESSION is — 2026-09-12

`python -m common.prior_close_check` · raw: `var/reports/prior_close_check.txt`
Artifact: "Screen Agreement"

## The hypothesis is refuted

`screen_miss` found four names on a +20% gainers watchlist that the simulation
scored at or below zero (ACVA 0.76%, RML 0.00%, IRD (1.27)%, WYHG (4.28)%). I
suspected an off-by-one in the daily frame's date alignment — RML at exactly
zero looking like a session's own close used as its own baseline.

**It is not.** Every name's `prior_close` was the correct previous daily row:

| name | list date | prior_close in use | is that the previous session? |
|---|---|---|---|
| ACVA | 2026-09-11 | 10.38 (09-10 close) | yes |
| RML | 2026-09-10 | 9.50 (09-09 close) | yes |
| IRD | 2026-09-10 | 6.07 (09-09 close) | yes |
| WYHG | 2026-09-09 | 5.61 (09-08 close) | yes |

`daily_frame`'s UTC-stamp date derivation is correct. There is no offset.

The consistent baselines — the daily closes off which the premarket high does
clear +20% — were not one row back either. They were **two to five rows back, at
different distances per name**, which cannot be an offset in a shift.

## What the report printed instead

The same shape on every name: **the 20% move had already happened, one session
before the watchlist that carries the name.**

| name | on this list | moved on | from | to | that move | change on list date |
|---|---|---|---:|---:|---:|---:|
| ACVA | 2026-09-11 | 2026-09-10 | 7.37 | 10.38 | +40.8% | 0.76% |
| IRD | 2026-09-10 | 2026-09-09 | 4.48 | 6.07 | +35.5% | (1.27)% |
| BIAF | 2026-09-10 | 2026-09-09 | 8.86 | 10.91 | +23.1% | 0.73% |
| WYHG | 2026-09-09 | 2026-09-08 | 4.06 | 5.61 | +38.2% | (4.28)% |

Four for four. Each name is genuinely a +20% gainer — on the session **before**
the file that lists it. By the file's own date it is flat, which is exactly what
the simulation reports.

## The mechanism, if it holds

`brokers/ibkr/trader.py::archive_watchlist` stamps with
`datetime.now(ET).strftime("%Y%m%d")` **at the moment of archiving**, and
deliberately refuses to archive-and-clear when:

- the session stopped before `SESSION_END` (guard against a mid-session Ctrl-C
  wiping a list that took work to build), or
- a position is still open ("NOT archiving — still holding X").

A list left behind by either guard is then archived under the **next** day's
stamp, or cleared with `--force-archive` at the start of the following session
with `now` already rolled over. Either way session D's names land in
`watchlist_D+1.txt`.

## Why this matters more than the threshold question

If the pairing is off by one session, **the 58% is not a screen measurement**.
`screen_validate` compared session D's simulated universe against session D−1's
live list. The one-directional shape it found — 16 missed against 2 sim-only —
is what a shifted comparison looks like, not what an under-producing screen looks
like.

## Not yet established

Four names I selected are a hypothesis, not evidence. `common/screen_lag.py`
(bundle `20260912i`) scores **every** automated watchlist against **every**
universe at offsets −2…+2 in **trading sessions**, with the claim
pre-registered before the first run:

> A lag is claimed only if a single non-zero offset (a) beats offset 0 by ≥10pp
> on the pooled found-rate, AND (b) beats offset 0 on **every session
> individually**.

Several offsets improving is reported as NOT ESTABLISHED — that is the signature
of watchlists carrying persistent names, not of a shift. Offsets scored over
fewer sessions than offset 0 are not ranked against it, and a missing offset
renders as a dash rather than a zero (scoring it zero would manufacture the lag
being tested for). Five refusal tests, one positive.

Run: `python -m common.screen_lag`

## Side findings

- **RML 2026-09-09** has no prior close at all — its first daily bar is 09-09 —
  and its premarket tape shows first print 10.00, high **40.73**, last 14.04 over
  only 60 bars, against a 09-09 daily close of 9.50. That is the signature of a
  corporate action (reverse split or ticker change creating a new instrument_id),
  not a trade. Worth a separate look before any splits handling is trusted.
- TV Remix `get_ohlcv` refuses `NASDAQ:ACVA` and `NASDAQ:TPET` as invalid
  symbols, so no external prior-close verification is available through it.
