# Session-aware screening — what an all-day strategy needs, 2026-09-05

Ben's observation while closing VW9: a strategy trading 04:00–20:00 cannot be
fed by a pre-market screen, because two thirds of its session is screened on
columns that no longer describe the stock.

He is right, and the point turns out to be larger than tooling. It exposes a
gap in VW9's specification, and a gap in how every backtest in this project
has been run.

---

## 1. The column mapping, verified

`common/tv_screener.py` pins the pre-market screen. These are its siblings.
Every one was confirmed to FILTER server-side (not merely return as a column)
against the live endpoint on 2026-09-05:

| session | ET | % change | price | volume |
|---|---|---|---|---|
| **PRE** | 04:00–09:30 | `premarket_change` | `premarket_close` | `premarket_volume` |
| **RTH** | 09:30–16:00 | `change` (close-to-close) or `change_from_open` | `close` | `volume` |
| **POST** | 16:00–20:00 | `postmarket_change` | `postmarket_close` | `postmarket_volume` |

Row counts as a filter sanity check: `change > 20` → 487; `postmarket_change >
10` → 14; `change_from_open > 10` AND `postmarket_volume > 100k` → 28. All
returned without an `ignored_filters` key.

Two columns need no swapping:

- **`relative_volume_10d_calc` is time-of-day adjusted**, so "≥ 5×" means the
  same thing at 04:30, 11:00 and 18:00. It is the one filter that carries
  across all three blocks unchanged — and the reason to prefer it over
  `volume_change`, which compares today's volume so far against yesterday's
  full day and therefore drifts through the session.
- **`float_shares_outstanding`** is static.

`change` vs `change_from_open` is a real choice, not a synonym. `change` is
against the previous close, so at 09:31 it still carries the entire overnight
gap; `change_from_open` measures only what has happened during RTH. For a
strategy that wants "moving now" rather than "gapped this morning",
`change_from_open` is the honest one.

**Always read `ignored_filters` on the response.** The server accepts unknown
or unsupported filter clauses, returns a plausible result set, and silently
does not apply them — `volume_change` behaves exactly this way. See
`common/tv_screener.check_response()`.

## 2. The specification gap this exposes in VW9

`vw9_strategy_spec.md` §1 defines the universe as:

> $2–20, RVOL(1D) ≥ 5×, float < 20m, **top-2 pre-market gainer**

That is a pre-market screen. VW9 trades until 20:00. So from 09:30 onward it
holds a universe chosen hours earlier on criteria that have expired. A stock
that gapped 30% at 05:00 and has been flat since is not what "top-2 gainer"
meant at 14:00, and nothing in the spec re-screens it.

This was never noticed because the spec's universe rule and the spec's session
rule live in different sections and were never read against each other — the
same failure mode as the price band, which MCL enforced and VW9 did not
because their two reports were never read side by side.

## 3. The larger gap: no backtest here has ever modelled a screener

Sharper than the above, and it applies to MCL too.

Every backtest in this project runs on `var/state/traded_pairs.json` — 407
pairs assembled in hindsight — for the whole session. **The screener is not
simulated at any point.** The backtest is handed the universe; it never has to
discover it.

For MCL that is a modest gap: its session is 04:00–09:30 and the live scanner
screens once at the start of it, so "the universe is fixed for the session" is
roughly what happens live too.

For VW9 it is not modest. Its RTH numbers presuppose a universe you have **no
live mechanism to construct**: nothing in the system tells you which names to
have loaded at 14:00. Even in the world where VW9's RTH block had looked good,
it would not have been tradeable, because the instruction "trade these names
during RTH" has no source.

Worth stating plainly because it cuts both ways:

- **Charitably** — VW9's RTH block was never fairly tested, since it was
  measured on a universe selected for a different session.
- **Less charitably** — the one part of VW9 that looked believable is also the
  part furthest from anything executable.

Neither reading rescues it. A fair RTH test still has to clear drop-top-3, and
VW9's RTH result is currently 97% one stock (AEHL). See
`vw9_setup_b_decision.md`.

## 4. What an all-day strategy would need

Recorded so the question is answered before, not after, the next strategy is
specified. This is design, not code — nothing below is built.

1. **A screen per block, switched on the ET clock.** Three filter sets, the
   mapping in §1, swapped at 09:30 and 16:00.
2. **A rule for what happens at the boundary.** A name that qualifies at 09:29
   on pre-market criteria may not qualify at 09:31 on RTH criteria. Does it
   leave the watchlist, get deprioritised, or stay until flat? `common/tv_feed.py`
   already answers this within a session — HOT / WARM / COLD, never delete —
   and that mechanism extends cleanly, but the choice is a strategy decision.
3. **Never drop a symbol with an open position.** Already true of `tv_feed`,
   and it becomes load-bearing here: a block switch is exactly when a name
   would otherwise vanish mid-trade.
4. **A universe rule in the spec, not just an entry rule.** VW9's spec has an
   entry rule for all day and a universe rule for pre-market only. Any
   all-day strategy needs to say what its universe is *in each block*.
5. **Backtest the screener, or state that you have not.** As long as the
   backtest is handed a hindsight pair list, an all-day strategy's non-PRE
   results describe something unbuildable. This is the item that actually
   matters, and it is not a small piece of work.

## 5. What is verified and what is not

**Verified today:** the nine column names, that each filters server-side, and
the row counts above.

**Not verified:** how quickly `postmarket_*` populate after 16:00; whether
`change` and `premarket_change` overlap or conflict during the 09:25–09:35
transition; and whether TradingView's own session boundaries match ET exactly
across DST changes. All three would need checking before anything is built on
this, and all three are the kind of edge that returns a plausible wrong answer
rather than an error.

---

## Where this leaves things

Nothing to build. VW9 is closed (`vw9_setup_b_decision.md`) and MCL is
pre-market only, so neither needs this today. The value here is that the
mapping is established and the architectural question is written down — so the
next all-day strategy answers it during specification rather than discovering
it after a grid has already been run.
