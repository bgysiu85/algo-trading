# Getting Alerts Off the Desk

**Pushing signals from a systematic strategy to a phone — setup cost, running cost, and which options fall over when the alert fires at 2am.**

*September 2026 · Python / IBKR context*

---

## The short version

Telegram and Discord are a single HTTP request and about ten minutes of setup. WhatsApp is technically possible but its messaging rules are built for customer support, not unattended alerting. iMessage has no public API and needs a Mac permanently in the loop.

| Channel | Setup | Cost | Free-form text anytime | Best for |
|---|---|---|---|---|
| **Telegram** | ~10 min | Free | Yes | Intraday signal alerts |
| **Discord** | ~5 min | Free | Yes | Multi-strategy, charts, shared logs |
| **WhatsApp** | Days | Per message | 24h window only | Client-facing, templated updates |
| **iMessage** | n/a | Mac or paid relay | No public API | Not worth it for alerting |
| **Push (ntfy, Pushover)** | ~5 min | Free / one-off | Yes | Pure notifications, no chat |

---

## Channel by channel

### Telegram — recommended

Message `@BotFather` inside Telegram to create a bot and receive a *bot token* (a secret string that authenticates your script). Every alert is then one POST:

```python
# requires only `requests` — no SDK, no auth dance
requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={"chat_id": CHAT_ID,
          "text": "AAPL  RSI 24.1 / MFI 18.6  →  long setup"},
    timeout=5,
)
```

No approval process, no per-message cost, and the rate limits (roughly one message per second to a single chat) sit far above anything a screener produces. Supports Markdown formatting and image uploads if you want to attach a chart.

### Discord — recommended

Create a private server, add a *webhook* to a channel — a URL that turns any POST into a message in that channel — and you're done. No bot account, no token management.

Better than Telegram when you want alerts split by strategy (one channel each), rich embeds with colour-coded direction, or a searchable history the whole group can read. Slightly worse for phone notifications, since Discord's mobile alerting is noisier to tune.

### WhatsApp — workable, with friction

Requires Meta's WhatsApp Cloud API, or Twilio acting as a reseller. That means a Meta Business account, business verification, and a dedicated phone number that isn't the one on your handset.

The real constraint is the **24-hour session window**: free-form text may only be sent within 24 hours of the recipient last messaging your business number. Outside that window, every message must use a template pre-approved by Meta — fixed wording with variable slots — and is billed per message.

For alerts firing unattended overnight, that means templated messages like *"{symbol} triggered {setup} at {price}"* rather than arbitrary text. Workable if the wording is stable; painful if you iterate on alert content.

### iMessage — not practical

No public API exists. The standard workaround drives the Messages app with AppleScript, which requires a Mac running permanently — no help on a Windows trading box. Paid relay services (Sendblue, LoopMessage and similar) run that Mac for you, but you're paying a subscription for something Telegram does free.

### Push services (ntfy, Pushover) — good minimal option

If all you want is a notification on the lock screen with no conversation attached, these are simpler still. `ntfy` is free and self-hostable; Pushover charges a small one-off licence per platform. Both are a single POST, and neither gives you a message history you can scroll through later.

---

## Where the send actually lives

Worth separating, because the two get conflated and they have very different failure modes.

**Script-side** — `screener → broker API → HTTP POST → phone`

The strategy code sends its own alerts. Milliseconds of latency, no external dependency beyond the messaging API, runs whether or not anything else is up. The right shape for anything time-sensitive.

**Assistant-side** — `scheduled run → model → tool call → phone`

A scheduled assistant task reads the market, decides what's worth saying, and sends it. Adds seconds of latency and a per-run cost, but it can summarise and prioritise. Suited to a pre-open briefing or an end-of-day wrap, not to an entry signal.

---

## Before pointing it at a live strategy

- **Rate-limit and de-duplicate at the source.** A screener bug that fires fifty alerts in a minute gets the channel muted, which is worse than no alerts at all.
- **Send a daily heartbeat** — "screener up, 412 symbols scanned" — so silence is unambiguous. A dead alerter and a quiet market look identical from the phone.
- **Keep tokens in environment variables**, not in the script. A bot token in a committed file is a stranger posting into your alert channel.
- **Timestamp every alert with an explicit timezone.** Overnight US sessions plus a local clock is how the wrong bar gets acted on.
- **Include the trigger values, not just the symbol.** "AAPL long" tells you nothing three hours later; the indicator readings let you reconstruct the decision.
- **Never let the notifier block the trading loop.** Wrap the send in a try/except with a short timeout — a messaging outage must not stall order logic.

---

*Setup effort and pricing reflect the state of each platform as of September 2026; WhatsApp's Cloud API terms in particular have changed repeatedly, so confirm current template pricing before committing to it.*
