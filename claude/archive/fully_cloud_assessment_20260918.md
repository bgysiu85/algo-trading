# Going fully cloud: what is left, and whether to do it

**Date:** 2026-09-18 · **Status:** assessment, nothing built · **Decision owner:** Ben

Ben asked what the last step is to make the setup 100% cloud based, and whether
it is moving IB Gateway. Gateway is the hardest piece, but it is not the only
one, and the reason to do it is probably not the one that prompted the question.

> **Corrected 2026-09-18.** §3 first named Fly `ord` (Chicago) as the region to
> move to. That was a hunch about IBKR being Chicago-centric, stated with more
> confidence than it had earned. For **US equities** the matching engines are in
> New Jersey — Nasdaq in Carteret, NYSE in Mahwah — so `ewr` is the better
> default and Chicago is the answer to a **futures** question. More importantly
> the region is an empirical matter, not a matter of opinion; §3 now says how to
> settle it.

---

## 1. Where everything is today

Verified, not remembered:

| Piece | Location | How it was confirmed |
|---|---|---|
| Relay (`thesiuz-trader-relay`) | **Sydney** | `deploy_relay.py --check-only` on Ben's machine printed `d8d996d7b94138  started  syd` |
| Pocket ID (`thesiuz-pocket-id`) | **Sydney** | `primary_region = "syd"` in `deploy/pocket-id/fly.toml` |
| Neon database | **Sydney**, `aws-ap-southeast-2` | the host in `var/neon.env`, checked by `check_neon.py` |
| Cloudflare tunnel | **no single location** | anycast; see below. Due for retirement anyway |
| IB Gateway + trader | **the ProArt**, Australia | — |

Cloudflare has no "your server". It is an anycast network of a few hundred edge
cities; the tunnel from the ProArt terminates at whichever edge is nearest,
which is Sydney, and requests reach it from wherever the visitor is. That is why
it never appeared in a region decision — there was none to make. It is slated
for removal in stage 4 of the Fly migration.

**Everything is in Sydney, and for everything that exists today that is
correct.** Every one of those components serves Ben, and Ben is in Australia.

---

## 2. What still runs on the ProArt

| Piece | What it is | Difficulty to move |
|---|---|---|
| **IB Gateway** | IBKR's Java desktop app; holds the broker connection | **Hard** — 2FA, headless, credentials |
| **The trader** | `main.py` / `run_paper.ps1`, `ib_async` | Easy — plain Python |
| **Bar cache** | `bar_cache_xnas_1s/` and friends | Easy — a volume |
| **Fill logs** | `var\fills\*.csv`, the system of record | Easy to move, **but see §7** |
| Screeners, studies | The strategy chat's work | Out of scope; they are research, not live |

Everything the portal needs is already off the PC. Milestone 4 did that. What is
left is the **trading system itself**.

---

## 3. Gateway is the one component Sydney is wrong for

This is the distinction that matters, and it is easy to miss.

Every other component's counterparty is **Ben**. Gateway's counterparty is
**IBKR**, whose servers are in the United States. So:

- Gateway on the ProArt (today): a Pacific round trip on every order.
- Gateway on Fly **`syd`**: *exactly the same* Pacific round trip. Same
  continent, same ocean. It would buy availability and **nothing else**.
- Gateway in a **US region**: that is the change that could affect fills.

**"Go 100% cloud" and "get faster fills" are therefore two separate decisions**
that happen to involve moving the same box. Doing the first without the second
gains only "survives the PC sleeping".

### Which US region — measure, do not guess

His strategy trades US small-cap equities, which match in **New Jersey**
(Nasdaq Carteret, NYSE Mahwah). Fly's `ewr` (Secaucus, NJ) and `iad` (Ashburn,
VA) are the candidates; `ord` (Chicago) is the right answer for futures, not for
this.

But latency with IB Gateway is to **IBKR's own servers**, which then route — not
to the exchange directly — and IBKR does not publish a clean map of which client
gateway a given account reaches. So the honest position is that `ewr` is the
better *default* and the question is settled empirically:

- stand up a throwaway machine in `ewr`, `iad` and `ord`;
- measure TCP connect time to the host Gateway actually resolves to;
- or, more decisively, run a week in one region and read the fill rate off the
  History tab.

That last option is nearly free now, which is the point of §4.

---

## 4. The measurement already exists

The order outcomes in the history say **427 of 1575 orders became trades —
27%**. The rest were abandoned or cancelled, which is what happens when a
marketable limit is sent and the price has moved by the time it lands. Some
unknown share of that 73% is the Pacific.

The `order_outcomes` table and the History tab record fill rate per day. Move
the trader, change nothing else, compare. A real experiment with a real readout
beats "it feels more robust" as a reason to spend a weekend.

The relay stays in `syd` — it serves his browser, and a 5-second state push does
not care about latency. The two are independent.

---

## 5. What it costs

Gateway wants ~1 GB of Java heap, so the machine grows from `shared-cpu-1x`
/256 MB to something like `shared-cpu-2x` /2 GB, plus a volume for the cache and
logs. Expect the whole stack to go from roughly **US$3–5 a month to US$15–25**.

Not a reason to refuse. Worth knowing before the bill arrives.

---

## 6. IB Gateway headless is a solved problem, with one catch

Mature images exist (`gnzsnz/ib-gateway-docker` is the usual one): IB Gateway +
IBC + Xvfb in a container, configured by environment variables.

The catch is **two-factor authentication on first login**, which needs a tap on
his phone. It cannot be automated away and should not be.

What makes unattended operation workable anyway is Gateway's own
`AUTO_RESTART_TIME`. The image's documentation states that this scheduled
restart **does not require daily 2FA validation** — so: authenticate once by
hand when the container starts, and Gateway restarts itself daily without asking
again. A container that actually *dies* (a deploy, a host failure) needs another
tap.

> **Worth five seconds of Ben's own knowledge, not research:** when he starts IB
> Gateway on the ProArt with his paper credentials today, does it ask for a
> phone tap? He already knows; sources disagree on whether paper logins carry
> the same 2FA as live, and his own Gateway is the authority.

---

## 7. A consequence that is easy to miss

The fill CSVs are currently **the system of record**, on his own disk, and they
are what makes the Neon history rebuildable — `backfill_fills.py` exists
precisely so the database can be reconstructed from them.

Move the trader and they live on a Fly volume instead. A volume is not a backup.
So the plan has to include one of:

- `upload_session.py` running in the container after every session, so Neon has
  the day within minutes and the volume stops being the only copy; **and/or**
- syncing the CSVs back to the ProArt or to object storage.

Without that, going cloud quietly downgrades the durability of the one dataset
everything else is derived from.

---

## 8. The risks, named plainly

1. **Broker credentials move into a cloud secret store.** Today they live on his
   own machine. This is a genuine escalation of what a compromise costs, and it
   is the single biggest change here. Fly secrets are encrypted and injected at
   boot, which is the right mechanism — but the blast radius is different.
2. **The IB API socket is unauthenticated plaintext TCP.** It must never be
   exposed publicly: Fly private networking only, never a public port. An
   exposed API port is full account access to anyone who finds it.
3. **No parallel rehearsal is possible.** IBKR allows one Gateway session at a
   time, so unlike the relay migration this cannot run side by side with the
   ProArt for a few days. It is a cutover. That makes stage 1 below more
   important than it looks.
4. **Nobody is watching.** Paper money today, so the stake is low — but the
   habit forms now, and it is worth deciding deliberately rather than by
   drifting into it.
5. **A logged-in TWS on his desktop may evict the cloud session.** One session
   at a time cuts both ways.

---

## 9. Staged plan

Mirroring how the relay migration went — each stage reversible, each one
proving something before the next depends on it.

| Stage | What | Proves |
|---|---|---|
| **1** | Gateway in its container **on the ProArt**, trader unchanged, connecting to it instead of the desktop app | The image, the IBC config, and exactly what the 2FA flow looks like — with him watching and the desktop app one click away |
| **2** | Gateway **and** trader together in a **US region** (`ewr` unless measurement says otherwise), volume for cache and fill logs, `upload_session.py` on a schedule | The cutover. Not parallel — see risk 3 |
| **3** | Measure: fill rate and slippage, before and after, from the History tab | Whether the latency argument was real |
| **4** | Retire the ProArt from the live loop; it keeps running studies | — |

Stages 1 and 2 are **strategy-side work**, not portal work: they touch
`main.py`, the broker connection and the run scripts, all of which
`docs/portal_ownership.md` puts on the other side of the line. The portal's only
involvement is that the trader keeps pushing to the same relay, and
`upload_session.py` moves from a manual step to a scheduled one.

---

## 10. Recommendation

**Do it — for latency, in a US region, measured, and not yet.**

Not yet, because the paper history currently reads −980.02 over 194 trades and
ten sessions, with every strategy bucket negative. Moving a system closer to the
exchange makes it do whatever it does faster. The sample is far too small to
call it a losing system — that is exactly what the `luck_vs_edge` work is
circling — but it is also not the moment to spend a weekend on infrastructure
and a monthly bill to make execution better.

The order in which these are worth doing:

1. Get a read on whether the edge is real, at the current fill rate.
2. Then move to a US region and find out how much of the 73% non-fill rate was
   distance.
3. Then decide about going live, which is a different conversation with
   different stakes — and the one where "nobody is watching" stops being cheap.

## Related

- `claude/relay_split_brain_FIXED_20260917.md` — the deployed relay
- `claude/reporting_tab_design_20260917.md` — where fill-rate measurement lives
- `docs/portal_ownership.md` — the line between portal and strategy work

## Sources

- [gnzsnz/ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker) — the image, its 2FA settings and `AUTO_RESTART_TIME`
- [IbcAlpha/IBC](https://github.com/IbcAlpha/IBC) — the automation layer underneath it
- [Fly.io regions](https://fly.io/docs/reference/regions/) — `syd` Sydney, `ewr` Secaucus NJ, `iad` Ashburn VA, `ord` Chicago
- [Neon regions](https://neon.com/docs/introduction/regions) — `aws-ap-southeast-2` Sydney
