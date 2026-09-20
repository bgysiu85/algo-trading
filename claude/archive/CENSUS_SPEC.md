# Census extraction spec — Ross Cameron daily videos

You are one of 34 workers building a dataset. Your output is **rows, not prose.**
Consistency with this spec matters more than insight: rows from all 34 workers
get concatenated and computed on, so an off-schema row is worse than a row full
of `?`.

## Your videos

Read your batch list from `/home/claude/handover/batch_lists.txt`, the section
headed `### BATCH <N>` where `<N>` is the batch number in your task. Each line is
`videoId  title`.

## Getting transcripts

Load both tools first:
`ToolSearch` query: `select:mcp__TubeAlfred__youtube_video_transcript,mcp__remote-devices__YouTube__get_transcript`

**Use `mcp__TubeAlfred__youtube_video_transcript` (parameter `video_id`).** It costs
1 credit per call and roughly 5,000 are available, so cost is not a concern.

If `mcp__remote-devices__YouTube__get_transcript` also loaded, it is free and you
may prefer it (parameter `url`), but it is often disconnected — **if it errors or
does not load, go straight to the TubeAlfred one and do not retry it.**

**The tool usually refuses to return a long transcript inline and instead saves a
JSON file and gives you the path.** When that happens, condense it with Bash and
read the condensed file. This works:

```
python3 -c "
import json,sys
p,out=sys.argv[1],sys.argv[2]
d=json.load(open(p))
segs=d['segments'] if isinstance(d,dict) and 'segments' in d else json.loads(d[0]['text'])['segments']
o=[];buf=[];st=None
for s in segs:
    if st is None: st=s['timestamp']
    buf.append(s['text'].strip())
    if s['offsetMs']%30000<6000 and len(buf)>8:
        o.append('['+st+'] '+' '.join(buf));buf=[];st=None
if buf: o.append('['+st+'] '+' '.join(buf))
open(out,'w').write(chr(10).join(o))
" INPUT.json OUTPUT.txt
```

Read the whole condensed file before writing the row. If a transcript is
unavailable (no captions), emit the row with `kind=NOCAPS` and `?` elsewhere.

## The schema — pipe-delimited, one row per video, in batch order

```
videoId | kind | day_result | pnl_usd | account | trades_n | symbols | setups | mistakes | market | first_et | last_et | max_loss_hit | notable
```

**Use `?` for anything not stated. Never guess. Never leave a field empty.**

| field | values |
|---|---|
| `kind` | `recap` (he reviews his own trading that day) · `watchlist` (names to watch, next session) · `training` · `interview` · `promo` · `news` · `other` · `NOCAPS` |
| `day_result` | `green` · `red` · `flat` · `notrade` · `?` — his result for that session only |
| `pnl_usd` | the day's net as a bare number, minus sign for a loss, e.g. `-64000`, `19323`. `?` if not stated. If he gives separate main and small account figures, use the MAIN account and put the other in `notable` |
| `account` | `main` · `small` · `both` · `?` |
| `trades_n` | integer count of trades he says he took that day. `?` if not stated. Count entries, not symbols |
| `symbols` | tickers he traded, semicolon separated, e.g. `WETO;STKH;ONFO`. Tickers only discussed but not traded go in `notable`, not here |
| `setups` | from this list ONLY, semicolon separated: `micro_pullback` `first_pullback` `bull_flag` `flat_top` `gap_and_go` `abcd` `vwap_break` `dip_buy` `reversal` `half_whole_dollar` `red_to_green` `halt_resumption` `other` |
| `mistakes` | from this list ONLY, semicolon separated: `chased_extended` `back_side` `added_to_loser` `reentry_after_stop` `oversized` `no_cushion` `ignored_own_filter` `traded_low_quality` `broke_ice_boredom` `didnt_bank_green` `stop_widened` `outside_window` `divided_attention` `slippage` `none` |
| `market` | `hot` · `cold` · `mixed` · `?` — how HE characterises conditions, not your judgement |
| `first_et` / `last_et` | clock time of his first and last trade as `HH:MM` 24h, e.g. `07:06`. `?` if not stated. Assume Eastern; do not convert |
| `max_loss_hit` | `Y` if he says he hit his max loss or daily stop, `N` if he says he stopped short of it, `?` otherwise |
| `notable` | ONE clause, max 120 chars, no pipes. The single most useful specific thing — a stated rule, a number, a named cause. `-` if nothing |

## Rules that decide edge cases

- A video can be `watchlist` **and** report the day's result. If he reports a
  result, `kind=recap` wins.
- If he traded two accounts, `account=both`, `pnl_usd` = main account.
- "Max loss" means his own daily stop, not a per-trade stop.
- Do not infer `market` from the stock action. Only record it if he characterises
  conditions himself.
- Percentages a **stock** moved are not `pnl_usd`. Only his own dollars count.
- If he says "I'm up X on the day" mid-video and then loses it, the row records
  the FINAL stated result.

## Output — write to a file, do not return the rows

**Write your rows to `/home/claude/handover/census/batch_<N>.txt`** — one row per
line, no header, in batch order. Create the directory if needed
(`mkdir -p /home/claude/handover/census`). Use `Write`, or python from Bash.

Then verify: `wc -l` the file and confirm the line count equals your video count.

**Your final message must be ONLY this one line:**

`DONE batch <N>: <n> rows written, <k> NOCAPS, <m> fully read`

Do NOT paste the rows into your reply — they are already on disk and repeating
them wastes the orchestrator's context. No preamble, no commentary, no
per-video summaries. If you could not read a video in full, still write its row
and mark the shortfall in `notable`.
