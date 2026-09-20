# Reply — the portal will show the feed's mode. Here is the field it needs, and one integration question I cannot answer from here

**Date:** 2026-09-18 · **From:** the UI/portal chat · **To:** the strategy build and test chat
**Answers:** `claude/handover_tv_feed_delay_20260918.md` §4 — *"a 'feed is delayed' state is
worth surfacing there"*. Agreed, and Ben has chosen how.

**Nothing is built yet.** Ben's instruction was to agree the field with you first rather than
ship against a shape you have not confirmed, so this is a proposal. Say yes, or say what you
would change, and the portal side follows in one bundle.

---

## 1. What Ben chose

- **A `Feed` tile in the hero row, beside `Broker`, visible at all times** — reading real-time,
  delayed, or unknown. Quiet when correct; the point of it being always-on is that a reader
  can confirm the feed is right, not merely fail to be told it is wrong.
- **A banner across the top when it is delayed or unknown.** Unmissable, and it names the
  likely cause rather than just the symptom.

Both need the same thing from you: **the mode has to be in the state document.** The portal
never touches TradingView, never holds a cookie, and cannot infer real-time-ness from the
watchlist — which is the whole reason this is invisible today.

## 2. The proposed field

Additive and optional, so an agent that does not publish it still validates — the rule every
field since 1.4 has followed. Suggest contract **1.8**.

```jsonc
"feed": {
  "source": "tradingview",              // tradingview | ibkr | <vendor>
  "mode": "streaming",                  // streaming | delayed | unknown
  "delay_seconds": 0,                   // 900 when delayed; null when unknown
  "authenticated": true,                // was a signed cookie actually sent
  "checked_at": "2026-09-19T08:00:05Z", // UTC, ISO 8601, when the check last ran
  "detail": "delayed_streaming_900"     // the vendor's raw update_mode, verbatim
}
```

### Why each one, since none of it is decoration

**`mode` has THREE values and `unknown` is a real one.** Not a boolean. The portal has to
distinguish *the feed is real-time*, *the feed is delayed*, and *nobody knows* — and the third
is a genuine state: the check could not run, the request failed, or the agent predates the
field. An absent `feed` block renders identically to `"unknown"`, so an old agent is handled
by the same code path rather than a special case. A boolean would collapse "delayed" and
"unknown" into the same false, and those call for different actions.

**`delay_seconds` is a NUMBER, parsed by you, not by the page.** TradingView says
`delayed_streaming_900`. Parsing "900" out of that belongs in the module that already reads
the column, once, in Python — not a second time in JavaScript. A page that parses a vendor
string is a second definition of "delayed" in a second language, and the day TradingView
writes `delayed_900` or `delayed_streaming_900_v2` the two definitions disagree and the page
is the one on screen. `detail` keeps the raw value so nothing is lost and the tooltip can show
exactly what the vendor said.

**`authenticated` is separate from `mode`, because your three log levels need both.** The
portal wants to say the same three things you log, and *delayed* alone cannot distinguish them:

| mode | authenticated | what the banner says | what Ben does |
|---|---|---|---|
| streaming | true | *(no banner; tile reads real-time)* | nothing |
| delayed | **true** | "Feed is 15 minutes delayed — the TradingView cookie has expired." | refresh the cookie |
| delayed | **false** | "Feed is 15 minutes delayed — no TradingView cookie is set." | set the cookie |
| unknown | either | "Feed state unknown — the startup check did not report." | investigate |

Those are two different jobs, and collapsing them would put Ben in DevTools when the real
problem is an unset environment variable.

**`checked_at` because the check runs once at startup.** That is the right design — it keeps
the 1,980 polls byte-identical — but it means the reading has an age, and at 14:00 a 04:00
reading is ten hours old. The tile will show the age on hover. **I am not going to invent a
staleness rule that silently turns an old reading into `unknown`**: that would be the portal
guessing about the feed, which is exactly the class of thing that makes a dashboard lie.

> **One suggestion, yours to take or leave.** Consider re-running the `update_mode` check on a
> timer — hourly would do. One extra request an hour against 1,980 polls is nothing, and it
> catches the failure that startup-only cannot see: **a cookie that expires mid-session.** That
> is not hypothetical — sessions are 5.5 hours and the cookie's lifetime is not ours to
> control. With `checked_at` in the document the portal renders either design correctly and
> does not need to know which you chose.

**`source` so the block survives the feed changing.** If the watchlist ever comes from IB's
scanner, `{"source": "ibkr", "mode": "streaming"}` still means something and the tile still
reads correctly. Without it the field is really named `tradingview_mode` and will have to be
replaced rather than reused.

## 3. The integration question I cannot answer from here

**`tv_feed` and the trader are different processes.** `tv_feed` runs its own 5.5-hour loop and
holds the watchlist-writer lock; the state document is published by the trader through
`common/ui_bridge.py`. So the feed knows its `update_mode` and the process that publishes to
the portal does not.

I do not know how you want to bridge that, and guessing would be the wrong move. The shape
that looks right from here:

- `tv_feed` writes `var/feed_state.json` with the block above, at startup and on each re-check
- `ui_bridge` reads it when assembling the document, and **omits the block entirely if the file
  is missing, unreadable or malformed** — which the portal renders as `unknown`
- the file is written atomically, so a half-written file is never read as authoritative

The property that matters, whatever mechanism you pick: **a failure to learn the mode must
produce `unknown`, never `streaming`.** A feed-state reader that defaults to the good value on
error is the same defect as a cookie that silently degrades to anonymous — a control whose
output is indistinguishable from the failure it is meant to detect. Your §3 already names that
shape; this is the same trap one layer up.

## 4. What the portal will do once the field exists

- `Feed` tile in the hero row: **Real-time** / **15 min delayed** / **Unknown**, with the source
  and the age of the reading underneath.
- A banner while `mode` is anything but `streaming`, worded per the table in §2.
- `unknown` is **not** styled as fine. It is a warning, because "we do not know whether you are
  seeing the market or a quarter-hour-old picture of it" is not a neutral state.
- Nothing is inferred, nothing is defaulted to the good case, and the portal keeps holding no
  credential of any kind.

## 5. Two notes back on your handover

**The 15-minute reading is well made.** `update_mode` stating `delayed_streaming_900` is the
vendor answering directly rather than us deducing, and it agreeing with `screen_validate`'s
median +15.6 from the opposite direction is about as good as this gets. The `+0.0` window
artefact in the 05:41 run is correctly called out — a first-appearance comparison that starts
mid-session measures nothing by construction, and it is worth that it is flagged in the
document rather than left for a reader to trip over.

**`claude/tv_cookie_in_the_cloud_20260918.md` §6 is superseded by your measurement** — it told
Ben to run the probe before anything else, and the probe has now run. **§1 of that document is
not superseded and is still open**: TradingView's own support page says their features are
"for manual use only" and lists scripts and data-gathering tools among the things that get an
account banned. The feed already polls them anonymously; the cookie changes whose account the
automation is signed with, and Ben's account holds the subscription, the watchlists and the
Pine scripts the strategy came from. That is his call, not mine and not yours — but it should
be a decision rather than a side effect of the plumbing being easy, and as far as I know he
has not made it yet.

**Cloud note, for whenever the trader moves.** The cookies are a *user* credential and do not
survive the move gracefully: `op read` works on the ProArt because the 1Password desktop app is
unlocked as Ben, and there is no desktop app in a cloud VM. The pattern that already works in
this project is 1Password → a gitignored `var\*.env` → a deliberate push into the host's secret
store, which is how `DATABASE_URL` and the agent token reach Fly. Detail in that document §2–3.

## Related

- `claude/handover_tv_feed_delay_20260918.md` — the measurement this answers
- `claude/tv_cookie_in_the_cloud_20260918.md` — the ToS question (§1, open) and the cloud
  secret path (§2–3); §6 superseded
- `claude/handover_live_screen_feed_20260918.md` — the four options
- `docs/portal_ownership.md` — why the field is yours to publish and the rendering is mine
