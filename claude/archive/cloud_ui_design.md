# Cloud UI for the trader — design notes

**Status: running. 2026-09-13** — the portal is live at `https://trader.thesiuz.com`
through a Cloudflare Tunnel, behind a passkey login served by Pocket ID at
`https://id.thesiuz.com`, both on the ProArt. The trader is still the replay agent; the
real adapter is the next piece. Started 2026-09-10.
All UI files live in **`D:\Trading UI`**; `D:\Trading` is reference only for this work.
Broker research that came out of it: `broker_rest_short_20260910.md`.

---

## 1. Decisions so far (Ben, 2026-09-10)

| Question | Decision |
|---|---|
| Where the trader + IB Gateway run | **Staged.** Build against the ProArt now; design so trader + Gateway can move to a VPS later with no UI changes |
| UI scope | **Monitor, controls, config edits, Claude panel** — all four |
| Cloud side | **One Python FastAPI app** serving both the relay API and the web UI |
| Where UI files live | `D:\Trading UI`, separate from the `D:\Trading` repo |
| Version control (2026-09-13) | **`D:\Trading UI` is its own git repo**, private GitHub, separate from `bgysiu85/algo-trading` |
| UI/logic coupling (2026-09-13) | **Independent, contract-based** — see §7. The UI knows nothing about trading |

## 2. Is there a cloud IB Gateway? (researched 2026-09-10)

**No broker-hosted equivalent exists for a retail account that can place orders.**

| Option | Cloud-native | Places orders | Verdict |
|---|---|---|---|
| **IBKR MCP connector** (official; `api.ibkr.com/v1/api/mcp-public`) | Yes | **No** — creates "order instructions" confirmed by hand in IBKR; stocks/ETFs, MKT/LMT only | Read-only views at most |
| **Client Portal Web API** | No — retail must run the Java Client Portal Gateway and log in via browser; OAuth is institutional only | Yes | Same problem as IB Gateway, plus a rewrite away from `ib_insync`. Rejected |
| **IB Gateway in Docker on a VPS** (`gnzsnz/ib-gateway-docker` + IBC; 10.48.1e / IBC 3.24.1 as of 2026-07-14) | Semi — same Gateway, headless | Yes; existing `ib_insync` code unchanged | **The real "cloud IB Gateway".** IBC restarts daily without 2FA; live logins need a 2FA tap on IBKR Mobile ~weekly. Paper logins usually skip 2FA — **verify on DUM215828** |

**Key point: a cloud UI does not need a cloud Gateway.** The trader pushes state
*outbound* to a relay and polls it for commands; the UI talks only to the relay. No
inbound ports at home, and the UI has no route to IBKR at all — consistent with hard
rule 1 (live account read-only).

A broker with a hosted REST API (Alpaca) would remove the Gateway entirely; see
`broker_rest_short_20260910.md`.

## 3. Architecture (proposed)

```
 Browser / phone ──HTTPS──▶ [ Cloudflare Access ] ──▶ FastAPI app (US-East)
                                                        ├─ web UI
                                                        ├─ relay API + store (SQLite)
                                                        └─ Claude panel (Anthropic API, server-side key)
                                                              ▲
             Trader (ProArt now, VPS later) ── outbound HTTPS/WS ┘
                ├─ push: heartbeat, positions, orders/fills, P/L (friction stated), signals, watchlist
                └─ poll: commands (pause, resume, flatten, config) → ack/reject
                IB Gateway :4002 (paper) — never exposed
```

Put the relay in US-East from day one, so it already sits next to the trader when the
trader moves.

## 4. Hosting (researched 2026-09-10, USD)

| Stage | Pick | Cost | Notes |
|---|---|---|---|
| **Now — relay + UI** | **Fly.io, Ashburn** | ~$2–6/mo (256 MB $1.94, 1 GB $5.70; disk $0.15/GB) | No free tier any more (trial only). Set `auto_stop_machines = "off"`. Deploy from a folder with `fly deploy`, no git needed. Runner-up: Railway Hobby ($5/mo min) |
| **Later — everything incl. IB Gateway** | **One 2 GB US-East VM running Docker Compose** (Gateway + trader + relay + cloudflared) | Lightsail $12 (browser SSH, easiest), DigitalOcean $12, Vultr $10 | Budget ≥2 GB — Gateway's Java heap defaults to 768 MB. Fly.io 2 GB ($10.70 + disk) also works |

**Avoid:** sleeping free tiers (Render, Koyeb, Cloud Run) — they drop the trader's
connection; Hetzner US (2026 price rises, US plans showed unavailable); Oracle Always
Free (A1 cut to 2 OCPU / 12 GB in July 2026; idle VMs reclaimed after 7 days);
Cloudflare Containers (no persistent disk, sleeps); PythonAnywhere (ASGI experimental).
**Never expose IB Gateway ports 4001/4002 to the internet.**

## 5. Website login (researched 2026-09-10)

| Rank | Option | Why |
|---|---|---|
| — | **Chosen 2026-09-13: Pocket ID behind a Cloudflare Tunnel.** Passkey-only, self-hosted, no third party holding the login. Needs HTTPS (WebAuthn does), hence the tunnel first, a domain (~$10–15/yr) and Docker. The portal requires the login only when it is configured; unconfigured it serves localhost and refuses everything else | |
| 1 | **Cloudflare Access + Tunnel** | Free up to 50 users (long-standing figure, not re-checked). No login code to write. Passkeys via Google/GitHub login; Cloudflare's own "Independent MFA" (Face ID / Windows Hello / keys) — free-plan inclusion **unverified**. Service tokens cover the trader. Needs a domain on Cloudflare (~$10/yr) |
| 2 | **Tailscale** | Free up to 6 users. No public site at all — UI reachable only from Ben's own devices |
| In-app passkeys | **Auth0 free** (25k MAU, passkeys included) or **Pocket ID** (self-hosted, passkey-only OIDC) | If login must live inside the app |
| Skip | Clerk (passkeys paid only), Firebase (no native passkeys), Supabase (passkeys beta since 28 May 2026), DIY `py_webauthn` (easy to get wrong) | |

**Gotcha:** behind Cloudflare Access on Fly, the default `*.fly.dev` hostname bypasses
login. Verify the `Cf-Access-Jwt-Assertion` header in FastAPI, or only serve via the tunnel.

**Trader → relay auth:** long random bearer token over HTTPS, constant-time compare,
with a rotation plan; behind Cloudflare add an Access service token
(`CF-Access-Client-Id` / `CF-Access-Client-Secret`). Optionally HMAC-sign commands with a
timestamp and accept only an allowlisted set of command types. Tokens live in the
1Password **Trading** vault, per hard rules.

## 6. Open design questions

1. **Relay unreachable — what does the trader do?** Keep trading / stop new entries /
   flatten. Lean: stop new entries after N seconds without contact; never auto-flatten.
2. **Command lifecycle.** Queued → picked up → acked/rejected, shown in the UI, so the UI
   never shows a state the trader isn't in. Flatten needs a second confirmation.
3. **Which config edits are safe mid-session?** E.g. trail % or daily loss stop for new
   positions only; price band next session. How edits get back into git.
4. **Paper-only guard with a command channel.** The trader already refuses non-`DU`
   accounts; the relay should also refuse to deliver commands to a trader that doesn't
   report a paper account.
5. **Login and secrets** — see §5; the relay holds no IBKR credentials at all.
6. **Claude panel scope.** Read-only over session data; Anthropic API key server-side
   (billed separately from Claude Pro).
7. **VPS move.** Provider, region, and whether a weekly 2FA tap is acceptable.
8. **Parity (PROGRAM_INDEX §4).** A daily loss stop set from the UI is a live rule; the
   backtest must enforce it too.
9. **How the trader hooks in.** **Decided 2026-09-13: thin hook** — the adapter lives in
   `D:\Trading` and is the only code that knows both worlds (§7.2). Original options kept
   for the record: *thin hook* — one bridge module added to `D:\Trading`,
   everything else in `D:\Trading UI`, contract documented in `D:\Trading UI` (lean) — or
   *sidecar* — a separate process in `D:\Trading UI` reading the trader's `var/` files and
   writing a command file; no change to `D:\Trading`, but slower and more fragile, and
   pause/flatten still need the trader to read that file.
10. **Is `D:\Trading UI` its own git repo?** **Decided 2026-09-13: yes**, its own private
    GitHub repo.

## 7. The independence contract

**Goal (Ben, 2026-09-13): the UI build is independent of the logic build.** The boundary
that buys that is not a layering convention — it is a *contract*, held as files and
enforced by tests on both sides. `D:\Trading UI` is its own git repo (private GitHub),
separate from `D:\Trading`, so every crossing of the boundary is deliberate.

### 7.1 The rule

**The UI knows nothing about trading.** It never imports trading code, never reads `var/`
file formats, never hard-codes a strategy name, a parameter name or a command name. It
renders whatever the state document describes. `if strategy == "mcl"` anywhere in the UI
means the boundary has already leaked.

Everything strategy-specific reaches the UI **as data**:

- **Settings** arrive as a list of `{key, label, type, value, constraints, editable_now}`;
  the UI draws a form from it. A new parameter, or a whole new strategy, is a trader-side
  change with no UI change.
- **Commands** arrive as `commands_available[]`; the UI draws one button per entry and
  sends a generic envelope back. Adding `flatten` later needs no UI release.

### 7.2 Who owns what

| Piece | Lives in | Owns |
|---|---|---|
| **Model** — the truth about positions, fills, settings | `D:\Trading` | the trader |
| **Adapter** (the thin hook) — translates trader internals into the contract, pushes, polls, acks | `D:\Trading`, one module | the only code that knows both worlds; deliberately dumb |
| **Contract** — JSON Schema + recorded example payloads | `D:\Trading UI\contract\` (canonical), vendored copy in `D:\Trading` | versioned, changed on purpose |
| **Relay + View + command queue** | `D:\Trading UI` | renders state, queues commands; holds no trading logic and no IBKR credentials |

### 7.3 State document — fields

One **full snapshot** per push (never deltas), JSON.

```
schema_version    e.g. "1.0"  — major bump = breaking
sent_at           UTC ISO 8601
agent             {id, kind: trader|replay, version}
session           {state: idle|premarket|rth|after|closed, opened_at, clock_et}
account           {broker, account_id, is_paper, mode: paper|dry|live}
strategies[]      {name, enabled, paused, paused_since}
positions[]       {strategy, symbol, qty, avg_price, opened_at, last_price,
                   unrealized_pnl, stop: {type, level}}
fills_today[]     {id, ts_et, strategy, symbol, action, qty, price, commission,
                   reason, trade_pnl|null, friction_charged}
pnl               {realized, unrealized, commission, friction_charged,
                   friction_per_round_trip|null, currency}
watchlist[]       {symbol, status: active|blocked|retired, note}
settings[]        {key, label, group, type: number|bool|enum|string, value,
                   min, max, step, options[], editable_now,
                   applies_to: new_positions|next_session}
commands_available[] {type, label, confirm: bool, args_schema}
health            {ib_connected, data_stale_seconds, uptime_s, last_error}
events[]          {ts, level: info|warn|error, text}    # optional, bounded
notifications[]   {id, sent_at, channel, status: sent|failed|suppressed|queued,
                   text, kind, batch_size, error}        # 1.2, bounded window
links[]           {label, url, kind}                     # 1.2, http(s) only
```

**Versions so far:** 1.0 the base; **1.1** per-strategy `pnl`, `settings[].set_command`,
`session.exchange`; **1.2** `notifications[]` and `links[]`.

**Invariants:** `is_paper` must be true for the relay to hand out any command; every P/L
figure travels with `friction_charged` (`PROGRAM_INDEX.md` §1); `fills_today[].id` is
stable, so the UI de-duplicates on an id and never on field values (§5 of that doc).

### 7.4 Command envelope

```
command   {id, type, args, issued_at, issued_by, expires_at}
ack       {id, status: applied|rejected|expired, detail, applied_at}
```

Rules: commands are **idempotent by `id`** — an ack replayed twice changes nothing; a type
not in `commands_available` is **rejected with `unknown_command`**, never ignored; the UI
shows *pending* until an ack arrives and never renders a state the agent has not confirmed;
anything destructive carries `confirm: true` and needs a second press.

### 7.5 Versioning

- Both sides **ignore fields they do not recognise** — that is what lets the two repos
  release on their own schedules.
- A **minor** bump adds optional fields. A **major** bump changes or removes one.
- On an unsupported major, the UI says *"agent version not supported"* rather than guessing.

### 7.5a Telegram, and why the portal mirrors rather than embeds

Researched 2026-09-13. **A Telegram chat cannot be embedded in a web page.** Telegram's own
widgets cover public channel posts, discussions, a share button and a login button only —
private chats are not among them, and Telegram Web refuses to be framed. Third-party
embed services (Elfsight, SociableKit) also cover public channels, and would route the
content through a third party.

So the portal **mirrors** instead: the agent publishes the messages it sent as
`notifications[]`, and the UI renders them as a feed. That is independent of Telegram
(it works when Telegram is down), it shows the batching that `notify_batch_minutes`
controls, and it needs no bot token anywhere near the relay. `links[]` carries a plain
`t.me` link for opening the real thing.

Two-way chat — typing in the portal and having it arrive in Telegram — is possible but
deferred: only one process may poll Telegram for incoming messages, so the **trader** would
have to do it and forward, keeping the bot token on Ben's machine per the hard rules.

**The mirror keeps Telegram's formatting** (contract 1.3, `notifications[].format`). The
trader's messages already carry Telegram's small HTML subset plus emoji; the adapter
passes them through as `telegram_html`, and the page **rebuilds them node by node** from an
allowlist — b, i, u, s, code, pre, a, blockquote, spoiler — with `href` accepted only for
http(s). Nothing from the agent reaches `innerHTML`. An unknown tag keeps its words and
loses the tag; images, scripts, styles and event handlers are dropped. Browser tests feed
the page an `onerror` image, a script, a `javascript:` link and a `data:` link and assert
none of them do anything. A message can also be published as plain `text`, and is then
shown character for character.

### 7.6 What keeps it honest

- `D:\Trading UI\contract\` holds the schema and a handful of **recorded example
  payloads**. The UI's tests render against those examples with **no trader present**.
- `D:\Trading` carries **one test** asserting that what its adapter pushes validates
  against its vendored copy of the schema.
- A shape change on either side then fails a test instead of quietly blanking the dashboard.
- `replay.py` (`cloud_ui_poc_plan.md` §6) is the reference implementation of the contract on
  the agent side, and the generator of those fixtures.

**The honest cost:** the schema is copied between two repos and version-bumped by hand.
That ceremony is the point.

## 8. Sources (2026-09-10)

- IBKR: [Web API auth](https://ibkrcampus.com/campus/ibkr-api-page/web-api-trading/) · [AI connector v1.0.0](https://ibkrguides.com/releasenotes/connector-v1.0.0.htm) · [custom connector v1.1.5](https://ibkrguides.com/releasenotes/connector-v1.1.5.htm) · [ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker) · [IBC](https://github.com/IbcAlpha/IBC) · [IBeam](https://github.com/Voyz/ibeam/wiki/IBeam-Configuration)
- Hosting: [Fly pricing](https://fly.io/docs/about/pricing/) · [Fly trial](https://fly.io/docs/about/free-trial/) · [Render free tier](https://render.com/docs/free) · [Railway pricing](https://railway.com/pricing) · [Koyeb instances](https://www.koyeb.com/docs/reference/instances) · [Northflank](https://northflank.com/pricing) · [DO Droplets](https://www.digitalocean.com/pricing/droplets) · [Lightsail](https://aws.amazon.com/lightsail/pricing/) · [Vultr](https://www.vultr.com/pricing/) · [Cloud Run](https://cloud.google.com/run/pricing) · [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) · [Oracle A1 change](https://community.oracle.com/customerconnect/discussion/970310/oci-always-free-updated-ampere-a1-compute-allocation) · [Hetzner 2026 increases](https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/) · [Cloudflare Containers](https://developers.cloudflare.com/containers/pricing/)
- Login: [CF Zero Trust plans](https://www.cloudflare.com/plans/zero-trust-services/) · [CF Independent MFA](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/independent-mfa/) · [CF service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/) · [Auth0](https://auth0.com/pricing) · [Clerk](https://clerk.com/pricing) · [Descope](https://www.descope.com/pricing) · [Supabase passkeys beta](https://supabase.com/changelog/46458-passkeys-for-supabase-auth-beta) · [WorkOS](https://workos.com/pricing) · [Kinde](https://kinde.com/pricing/) · [Hanko](https://www.hanko.io/pricing) · [Pocket ID](https://github.com/pocket-id/pocket-id) · [Tailscale](https://tailscale.com/pricing)
