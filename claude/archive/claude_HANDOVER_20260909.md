# HANDOVER — YouTube / web source extraction, 2026-09-09

Read this first. It hands over an in-progress piece of work to a **PC-linked
session**. Three companion files accompany it.

---

## 1. Why you are reading this in a new chat

The previous session ran in Anthropic's cloud, **not linked to Ben's PC**. It
could call his local MCP servers (YouTube, TradingView) but **could not write
files to disk or into the project's Context folder** — `/mnt/project/` is
mounted read-only there and no tool exists to add to Context.

**A PC-linked session can write directly into the `claude` folder in project
Context** — the one already holding 54 items. That is why this work moved.

**Your first job:** confirm you can write there. If you can, save the three
companion files into that folder using their existing names, then continue.
If you cannot, say so plainly rather than assuming.

**Do not repeat the previous session's mistake:** it twice treated a limit of
its own sandbox as a limit of the product. Check what *you* can do.

---

## 2. The three companion files

| File | What it is |
|---|---|
| `claude_youtube_extraction_humbled_trader.md` | **Method + full extraction.** §1-§2 are the reusable method for any channel. §4 holds 13 video extractions. §5 the cross-cutting findings. **Already in Context** |
| `claude_youtube_extraction_ross_cameron.md` | Ross Cameron channel triage + website findings. **A corrected version supersedes the one in Context — replace it** |
| `claude_warrior_momentum_spec.md` | **New.** Cameron's three strategies documented as a spec. Not yet in Context |

---

## 3. What was done

**Humbled Trader (`@HumbledTraderOfficial`)** — complete. 1,073 videos
enumerated, 14 interviews swept, 13 videos extracted, 9 ruled out. Channel is
effectively exhausted. Findings and a ranked action list are in that file's §5
and §6.

**Ross Cameron / Warrior Trading (`@DaytradeWarrior`)** — partly done.
3,618 videos triaged to a 12-video shortlist, **but the website turned out to be
far richer than the videos.** Two site pages plus search snippets produced a
complete bull flag spec including the thresholds. See
`claude_warrior_momentum_spec.md`.

---

## 4. The single most useful method lesson

> **For a channel with a content-marketing site, read the site before the
> videos.** One free page from `warriortrading.com` gave more codeable
> parameters than 13 Humbled Trader videos. The videos sell the course; the
> strategy pages state the rules.

Two more, both learned the hard way:

- **Search project knowledge BEFORE enumerating a channel.** The first Cameron
  shortlist included two videos already read in full in earlier sessions
  (`archive_ema_source_comparison.md` S3 and S5).
- **`web_fetch` only accepts URLs from a prior search or fetch *result*** — not
  links embedded in fetched page content. Site pages need
  `web_search` → fetch the returned link.

The full method, including all the tooling gotchas (transcripts are free,
TubeAlfred credits, the leaky duration filter, sweep-before-transcribe), is in
`claude_youtube_extraction_humbled_trader.md` §1-§2.

---

## 5. Next actions, in order

### Immediate — finish the Warrior Trading site (free, fast, high yield)

Unread pages. Use `web_search` for each, then fetch the result:

`/reversal-trading-strategy/` · `/mean-reversion/` · `/position-sizing/` ·
`/how-to-build-morning-watchlist/` · `/premarket-trading/` ·
`/how-to-use-stock-scanners/` · `/technical-analysis/`

Also worth searching: `warriortradingnews.com` and
`media.warriortrading.com` (a public Technical Analysis PDF) — both surfaced
detail absent from the main site.

Fold results into `claude_warrior_momentum_spec.md`.

### Then — the Cameron video shortlist

Only for what the site does not state: the **micro pullback's** retracement
depth and volume condition. Sweep with `search_transcript` for **numbers**
(`percent`, `cents`, `9 EMA`), not topic words. Shortlist and IDs are in the
Cameron file §2. **Lower priority than the site.**

### Actionable now, without more research

From `claude_warrior_momentum_spec.md` §5:

1. **Bar-count vs percentage pullback** in the bull flag detector — he says
   2-3 red candles; `config.py` uses a retracement %.
2. **Retracement cap ≤ 50% of the pole**; **flag volume < pole volume** (a ratio
   between phases, not a fixed multiple).
3. **Pullback ≤ 3 red candles** and **9 EMA / VWAP invalidation** — may not be
   encoded in our detector at all.
4. **Confirm** whether our $500 risk / 2:1 config was taken from Cameron
   deliberately — his stated numbers are identical.
5. **Is MCL's universe derived from Cameron or convergent?** His bull-flag
   universe ($2–$20, 5× RVOL, float <20M, 10%+) is ours. This determines whether
   we have independent corroboration or an echo.
6. **Time-of-day-normalised RVOL** — his definition, versus our 10-day flat mean
   which `consolidated_volume_gap.md` §3.2 found is substantially noise.
7. **Session-conditional timeframe** — 1m before 11:30, 5m after.

And from the Humbled Trader file §6, top of that list:

8. **Dip-buy vs breakout A/B on MCL's existing universe and bar cache** — Shay
   argues breakouts have poor risk-reward on low-float small caps and gives a
   mechanism. Same names, same session, opposite entry.
9. **Resistance-vs-float trapped-supply filter** — the best-corroborated idea
   from that channel, two independent sources.
10. **Audit every screen for filters on nullable fields** — a live selection bug
    demonstrated on camera (a float filter silently drops rows with null float).

---

## 6. Standing rules — apply to everything above

- **Source videos and strategy pages are hypothesis generators, not results.**
  Per `source_videos_20260907.md` §4.
- **A win rate without a paired reward figure is not a result.** Compute
  breakeven `p = R/(R+1)` before treating any claim as an edge. Three of three
  guests who led with a headline accuracy figure had an unexamined or
  unfavourable reward side.
- **Treat every quoted threshold as an order-of-magnitude hint.** Shay's scanner
  numbers moved between two of her own videos; Cameron publishes two mutually
  inconsistent universes.
- **Resolve float rules per direction.** Every float restriction collected is
  from short sellers. MCL is long-only. An extreme move is a blowup if short and
  the win if long.

---

## 7. Housekeeping

- `PROGRAM_INDEX.md` is the canonical index and **does not yet reference any of
  these three files.** Add a line each.
- The Context folder duplicates the repo. Decide which is canonical before the
  copies drift further.
- TubeAlfred balance ≈5,024 credits. Transcripts via the local YouTube MCP cost
  **nothing** — never spend credits on them. TubeAlfred is only for paginated
  channel enumeration.
