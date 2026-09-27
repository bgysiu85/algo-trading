# The TradingView cookie in the cloud — and the finding that should decide option B first

**Date:** 2026-09-18 · **From:** portal/UI chat · **For:** the build chat and Ben
**Answers:** Ben's question — `op read "op://Trading/TradingView/sessionid"` works on the ProArt;
what happens when the trader runs in the cloud?

> **STATUS, updated later the same day.** The probe has since run.
> `claude/handover_tv_feed_delay_20260918.md` measured it directly: anonymous is
> `delayed_streaming_900` (**15 minutes**), authenticated is `streaming`. So **§6 item 1 of this
> document is done and §6's framing is superseded** — this line of work did not close for free.
>
> **§1 is NOT superseded and is still open.** Nothing in the measurement bears on it: the
> question is not whether the cookie works, but whether signing the automation with Ben's
> account is a trade he wants to make. As far as this chat knows, that decision has not been
> taken. §2–§5 stand as written.

**Bears on:** option B of `claude/handover_live_screen_feed_20260918.md` §2, and
`claude/feed_state_CONTRACT_PROPOSAL_20260918.md`, which is how the portal will surface an
expired cookie.

---

## 1. The finding — still open, and it should be a decision rather than a side effect

TradingView's own support page on suspicious-activity bans says the platform prohibits
"scripts, APIs, screen scraping, data mining, robots, or other data gathering and
extraction tools", and states that **all our features are for manual use only**. The named
consequence is the account being banned.

Source: <https://www.tradingview.com/support/solutions/43000674726-why-is-my-account-banned-due-to-suspicious-activity/>

**The distinction that matters here.** `tv_feed` already polls
`scanner.tradingview.com` ~1,980 times a session, anonymously, with a browser
`User-Agent`. That is already automated access to TradingView. What the cookie changes is
not *whether* there is automation — it is **whose account the automation is signed with**.

- Today, the worst case is an IP block, which costs a feed.
- With `sessionid` + `sessionid_sign` attached, the worst case is Ben's account, which
  carries the premium subscription, the watchlists and **the Pine scripts the strategy came
  from**.

That is a materially different bet, and it should be made deliberately rather than as a
side effect of "it is one environment variable".

**This does not close option B** — it is a risk for Ben to price, not a technical
impossibility, and the measurement shows the upside is real and large. But the fact that the
plumbing turned out to be easy is not an argument about the risk.

**It did not affect the probe.** Running `common.tv_probe` once, by hand, from Ben's own
desktop, for 35 minutes, is a different thing from an unattended 5.5-hour daily process signed
in as him from a datacentre. That distinction is also why "the probe was fine" is not evidence
that the shipped feed will be.

---

## 2. The mechanical answer: `op read` does not survive the move

`op read` on the ProArt works because the 1Password **desktop app** is unlocked and
authenticating as Ben — biometrics, or his account password. There is no desktop app in a
cloud VM, nobody to touch a fingerprint reader, and no interactive session.

The headless equivalent is a **1Password service account**: a non-human identity with
access to named vaults. Its token goes in `OP_SERVICE_ACCOUNT_TOKEN`, and with that set,
`op read` works with no desktop app and no sign-in. Requires CLI 2.18.0+. Service accounts
carry hourly and daily request limits, and reads are cheaper when passed item and vault IDs
rather than names.

Source: <https://www.1password.dev/service-accounts/use-with-1password-cli>

**But notice what that buys.** The cloud process now holds a long-lived token with access
to the Trading vault — a credential that is *broader* than the two cookies it was fetched
to retrieve. The secret has been moved, not removed, and made larger.

## 3. The pattern this project already has

The relay solved the same problem two days ago and the answer is worth reusing:

```
1Password (system of record)
      |  op read, on Ben's machine, interactively
      v
var\*.env  (gitignored, guarded by tests\conftest.py)
      |  tools\fly_secrets.py  -- a deliberate, manual push
      v
Fly secrets  ->  injected as environment variables at boot
```

`DATABASE_URL` and the agent token already travel exactly this way. Applied to the cookies,
`TV_SESSIONID` and `TV_SESSIONID_SIGN` become two more Fly secrets, and:

- the cloud holds **only the two cookies**, not a key to the vault
- nothing in the cloud can read 1Password at all
- rotation is a deliberate act with a human at one end, which is what a rotation should be

The cost is that refreshing an expired cookie is manual. See §4 — that cost is the real
objection to B in the cloud, and a service account would not remove it either, because
**something still has to put a fresh cookie into 1Password in the first place**, and that
something is a human with DevTools open.

## 4. The treadmill, which is what actually makes B worse in the cloud

A TradingView session cookie is a **user** credential. It expires, and it dies on logout,
password change, or a re-authentication. Every death means: open a logged-in tab, DevTools →
Application → Cookies, copy two values, update the vault, push to Fly, restart the feed.

On the ProArt that is mildly annoying and Ben is sitting there. Unattended in the cloud it
is a recurring manual task standing between the trader and real-time data, on a schedule
nobody controls.

The startup check the build chat shipped is what stops this being silent: a cookie that has
expired does not error at TradingView, it simply gets served the anonymous feed, and **a
delayed watchlist looks exactly like a real-time one**. That check logs ERROR for "delayed
WITH a cookie sent". It is the right guard and it becomes more important in the cloud, not
less — it is the only thing that will tell Ben the treadmill has stopped turning.

**Now also on screen.** `claude/feed_state_CONTRACT_PROPOSAL_20260918.md` puts the mode in the
state document and the portal shows it as a permanent tile plus a banner when it is wrong,
which is the difference between a line in a log nobody reads and a fact Ben cannot miss. That
proposal deliberately separates *delayed with a cookie* from *delayed with no cookie*, because
the first sends him to DevTools and the second to an environment variable.

One unknown worth naming rather than assuming: whether TradingView invalidates or challenges
a session that suddenly appears from a datacentre IP in another country. The support page
above does not mention IP or location. **Untested** — and cheaply testable, by running the
probe's authenticated arm once from a cloud host before anything depends on it. Worth doing as
part of the trader's migration rather than discovering it on the first cloud morning.

## 5. What the cloud move does to the four options

| | credential | affected by the move? |
|---|---|---|
| **A. IB scanner** | the Gateway session the trader already holds | **no** — it moves with the trader |
| **B. TradingView cookie** | **a user session, held by a person** | **yes, badly** — manual refresh, and the ToS exposure is now on an always-on process |
| **C. Databento EQUS.MINI** | API key | **no** |
| **D. Massive / Polygon Advanced** | API key | **no** |

**This is the structural point.** A, C and D authenticate with machine credentials, which is
what unattended software is supposed to use, and they do not care where they run. B is the
only option on the list that gets worse in the cloud, and the cloud move is precisely the
moment a borrowed user session stops fitting.

So the option ranking that was right for a desktop trader is not automatically right for a
cloud one. B was attractive as "free, one header, exact same screen" — and the measurement has
now shown the header is worth a full 15 minutes, which is a large prize. In the cloud the same
option is "free, one header, worth 15 minutes, plus a manual refresh on an unknown schedule,
plus the account the strategy lives in as collateral".

## 6. Recommendation, as it now stands

1. ~~Run the probe first.~~ **Done** — see the status note above. Anonymous is 15 minutes
   delayed; authenticated streams.
2. **Decide the ToS question in §1 before the cookie goes into production.** It is Ben's call
   and nobody else's; the facts are in §1 and they have not changed.
3. **If B is adopted: on the ProArt, a machine or user environment variable, or resolved from
   the Trading vault at launch — never a PowerShell session variable**, which dies with the
   shell while the feed runs from `D:\TradingProd`. In the cloud, the Fly-secrets pattern in
   §3: give it the two cookies, never a key to the vault.
4. **Test the datacentre-IP question before the trader migrates**, not after (§4).
5. **Treat B as a bridge with a life measured in months.** The destination for an unattended
   trader is a machine credential. IB's scanner now works pre-market — measured 05:48 ET,
   2026-09-18 — so the fallback is real, even though it screens a different universe and
   cannot replace TradingView without discarding the `screen_validate` agreement.

## Related

- `claude/handover_tv_feed_delay_20260918.md` — the measurement (15 minutes, stated by the vendor)
- `claude/feed_state_CONTRACT_PROPOSAL_20260918.md` — how the portal will surface an expired cookie
- `claude/handover_live_screen_feed_20260918.md` — the four options
- `claude/fully_cloud_assessment_20260918.md` — what remains on the ProArt
