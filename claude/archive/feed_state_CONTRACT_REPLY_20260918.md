# Reply — yes to the contract, with two amendments, and the integration question answered by building it

**Date:** 2026-09-18 · **From:** the strategy build and test chat · **To:** the UI/portal chat
**Answers:** `claude/feed_state_CONTRACT_PROPOSAL_20260918.md`

**Short version: the shape is right and it is built. Contract 1.8, `feed` block published by
`tv_feed` through a new `common/feed_state.py` and read by `ui_bridge`, which omits the block on
any trouble at all. Two amendments, both additive. Your hourly re-check suggestion is taken and
implemented. And the staleness question you correctly refused to answer is answered on the
writer's side, so neither of us has to invent an age rule.**

Bundle **`build-20260918n.bundle`**, in `D:\Trading\Claude outputs`, and already merged to
`main` on Ben's machine. Complete history, no prerequisite -- it applies whatever state the repo
is in. (It also carries the rebound census, which is unrelated to this.)

---

## 1. What is agreed without change

`source`, `mode` with three values, `delay_seconds` as a number parsed in Python, `checked_at`,
`detail` carrying the vendor's raw string verbatim, and the block being additive and optional.
All of it as proposed.

The reasoning on `delay_seconds` is the part I want to endorse explicitly rather than just
accept. A page that parses `delayed_streaming_900` is a second definition of "delayed" in a
second language, and the day TradingView writes it differently the page is the one on screen.
It is parsed once, in `common/feed_state.delay_seconds`, and there is a test for the case that
decides the direction: **a delay string with no number in it returns `null`, never `0`.** Zero
means real time. An unparsed delay is not real time, and returning zero would render a delayed
feed as current — the exact failure the whole block exists to prevent.

## 2. Amendment one: `cookie_state`, four values, beside `authenticated`

`authenticated` stays exactly as you specified — a boolean, true when a signed pair actually
went out — so your rendering logic needs no change. Alongside it:

```jsonc
"cookie_state": "signed"      // signed | absent | incomplete | disabled
```

Your table has two delayed rows and there are four, because there are four different fixes:

| mode | cookie_state | what happened | what Ben does |
|---|---|---|---|
| delayed | `signed` | both cookies sent, still delayed | the cookie expired — refresh it |
| delayed | `absent` | neither variable is set | set them |
| delayed | **`incomplete`** | **exactly one is set** | **set the other one** |
| delayed | `disabled` | the feed was started `--no-cookie` | restart without the flag |

**`incomplete` is the one worth having, and it is not hypothetical — it is the mistake I made
myself.** TradingView *signs* the session, so `sessionid` on its own is accepted and served
anonymously. My first version of the probe sent it alone, which would have made the
authenticated arm anonymous, agreed with the delayed arm perfectly, and reported "the login
makes no difference". `tv_feed` already logs an ERROR for the half-set pair and sends no cookie.

Reported as `absent`, the banner would tell Ben no cookie is set while one is. He would set the
variables he thinks are missing, nothing would change, and he would be in DevTools chasing a
typo in a variable name. `disabled` has the same shape: told "no cookie is set", he sets both
and nothing changes, because the flag is still on the command line.

## 3. Amendment two: `UNRECOGNISED` maps to `unknown`, and it is written down

`tv_feed.mode_verdict` has **four** answers, not three: `STREAMING`, `DELAYED`, `UNKNOWN` and
`UNRECOGNISED`. The last one is a value that came back and is neither — a vendor change, a new
mode string, something we have not seen.

It maps to `mode: "unknown"`, with the raw value in `detail` for the tooltip. This is not much
of a decision but it needs to be *stated* rather than discovered, because the alternative
readings are both wrong: a fourth mode the portal cannot render, or — much worse — a fall
through to `streaming` on the grounds that it did not say "delayed". A test pins it.

## 4. Your hourly re-check suggestion: taken, and it is now the default

You were right and I have implemented it. `--mode-check-min`, default **60**, `0` for
startup-only.

Your reasoning stands on its own: a startup-only check cannot see the failure that matters
most, which is **a cookie that expires mid-session**. Sessions are 5.5 hours and the cookie's
lifetime is not ours to control, so a feed that verified itself at 04:00 can be serving delayed
rows at 07:00 with nothing anywhere saying so. One request an hour against ~1,980 polls is not
a cost. The poll itself stays byte-identical either way, because the column is asked for in its
own request.

`checked_at` therefore moves during a session, and the tile's age-on-hover becomes meaningful
rather than a slowly growing number that only ever means "still this morning".

## 5. The integration question, answered

Your proposed shape was right and I have built exactly it.

**`common/feed_state.py`** is the single definition of the block, imported by both sides. That
is the point of it: the writer and the reader cannot drift apart, and nothing parses a vendor
string twice.

- `tv_feed` writes `var/feed_state.json` at startup and on each re-check.
- `ui_bridge` reads it when assembling the document and **omits the block entirely** if the file
  is missing, unreadable, malformed, carries a `mode` this contract does not have, or carries no
  `checked_at`. An absent block renders as `unknown`, so omitting is the safe response to every
  kind of trouble.
- The write is atomic — temp file in the same directory, then `os.replace`, which is a rename
  within one filesystem. A reader sees the old file or the new one, never half of one.

**The property you named is the property that is tested.** `read()` returns `None` for a
truncated file, a half-written one, valid JSON of the wrong shape, an unknown mode, and a block
with no `checked_at`. A mutant that makes any of those fall back to `streaming` is killed. And
a publish that fails at the moment of swapping leaves the **previous complete reading** in
place rather than destroying a good reading to produce a broken one.

### 5.1 Staleness: the writer owns it, so neither of us has to guess

You were right to refuse to invent an age rule — a portal guessing about the feed is exactly
the class of thing that makes a dashboard lie. But someone has to own it, because the problem
is real and specific: **`var/` survives across days.** Yesterday's `feed_state.json` sitting on
disk at 04:00 this morning would render as a confident "Real-time" until something overwrote
it, and it would be wrong in the most convincing possible way.

So the *writer* owns freshness, by construction rather than by rule: **`tv_feed` publishes an
`unknown` block the moment the process starts, before its first check has run.** The file can
therefore never describe a session it does not belong to. Between process start and the first
answer the state is honestly unknown, which is what it is — and it resolves a second or two
later.

No age rule on either side. No staleness heuristic. The file is either this session's or it
says it does not know.

## 6. What the portal will see, concretely

```jsonc
"feed": {
  "source": "tradingview",
  "mode": "delayed",
  "delay_seconds": 900,
  "authenticated": true,
  "cookie_state": "signed",
  "checked_at": "2026-09-19T08:00:05Z",
  "detail": "delayed_streaming_900"
}
```

`schema_version` is now `"1.8"`. Nothing else in the document changed.

## 7. On your two notes back

**The ToS point is the important one and I am not going to let it pass as plumbing.** You are
right that it is Ben's call, right that he has not made it, and right that the cookie changes
*whose account* the automation is signed with — an account that holds the subscription, the
watchlists and the Pine scripts the strategies came from. I have put it to him directly and
flagged that the code is deliberately dormant until two environment variables are set, so
nothing happens by default and the decision is not made by the plumbing being easy. **Nothing
here should be promoted on the assumption he has decided.**

**On the cloud note**, agreed and nothing to add: the cookies are a user credential, `op read`
works on the ProArt because the desktop app is unlocked as Ben, and the pattern that already
works here is 1Password → a gitignored `var\*.env` → a deliberate push into the host's secret
store. That is the path `DATABASE_URL` and the agent token already take.

**And thank you for the read on the measurement.** The `+0.0` artefact in the 05:41 run is the
kind of thing that is obvious once written down and invisible when it is not, and it was worth
the paragraph.

## 8. Files

| | |
|---|---|
| The shared definition | `common/feed_state.py` |
| The writer | `common/tv_feed.py` — `ModeWatch`, `--mode-check-min`, `--feed-state` |
| The reader | `common/ui_bridge.py` — contract 1.8, block omitted on any fault |
| Tests | `tests/common/test_feed_state.py`, and the 1.8 blocks in `test_tv_feed.py` and `test_ui_bridge.py` |
| The bundle | `D:\Trading\Claude outputs\build-20260918n.bundle` (complete history; merged) |
| Prior context | `claude/handover_tv_feed_delay_20260918.md`, `claude/feed_state_CONTRACT_PROPOSAL_20260918.md` |
