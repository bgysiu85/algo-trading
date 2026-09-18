# MCL pre-market paper trading — runbook

Companion to `brokers/ibkr/trader.py`, which is launched through `main.py`. Everything here runs on **your machine**, not in
the Claude session — the IB API is a local socket only.

---

## WHICH TREE DO I RUN FROM? (2026-09-11)

There are now two working copies and **sessions run from the production one**.

| | |
|---|---|
| `D:\TradingProd` | **production.** Checked out at a tag. **Every `--mode paper` and `--mode dry` runs here.** |
| `D:\Trading` | development. `main`. Edit freely; run backtests and studies here. |
| `D:\TradingProd\var` | a **junction** to `D:\Trading\var` — one fill log, one watchlist, **one session lock** |

**The junction is the safety property, not a convenience.** The session lock
lives at the relative path `var/state/session.lock`, so it resolves against
whichever directory you are in. Two trees with separate `var/` directories have
**two locks**, and the lock then stops protecting anything: both processes could
connect to the same IB account and compete for its account-wide request budget.

A junction fails silently. Check it — from `D:\TradingProd`, in **Command
Prompt or PowerShell**:

```
python -m common.provenance --expect-shared-var D:\Trading\var
```

Three things must be true before a session: `describes as  prod-<date>`,
`uncommitted   no`, and `OK   var/ is shared`. If it says **WRONG**, do not
start a session.

Backtests and studies do **not** take the lock, so research in `D:\Trading`
runs freely while a session is live.

Every session prints its version at startup and writes it into the lock, so a
second session blocked by the first is told which tree the first is running
from — and the fill log can be traced back to the code that produced it. If you
accidentally start from `D:\Trading`, the banner says so.

### Promoting a new baseline — never mid-session

```
git -C "D:\TradingProd" fetch origin --tags
git -C "D:\TradingProd" checkout <new-tag>
```

---

## What this does and does not do

**Does:** runs the shipped MCL configuration — **apex exit OFF** since
2026-09-05, not V7 — watches 1-minute bars live, and places
**marketable limit orders** against an IBKR **paper** account during pre-market.
Logs every signal with the live bid/ask, the limit sent, and the fill or no-fill.

**Does not:** pick the stocks. You supply today's qualifying tickers. The strategy has
never had a scanner and Pine can't express one (no float, no cross-sectional ranking).

**The point of the exercise** is the fill log, not the P/L. Every backtest number so far
assumed a fill at the bar close with 1 tick of slippage. Nothing has tested whether that
fill exists pre-market. This measures it.

---

## Safety — read this first

Your live IBKR account (net liq ~$4.1k) is currently the one connected to Claude. The
script **refuses to touch it**. Two independent guards:

1. **Port allowlist.** Only `7497` (TWS paper) and `4002` (Gateway paper) are accepted.
   Ports `7496` and `4001` are LIVE and are rejected by name before any connection work.
2. **Account-id check.** After connecting it reads `managedAccounts()` and aborts unless
   every account id starts with `DU`, which is IBKR's paper prefix.

Either failing exits before a single order or market-data request is made.

Additionally: leave **Read-Only API** ticked in TWS until you have run `--dry-run` at
least once and are happy with what it reports.

---

## One-time setup

Files live in `D:\Trading` (development) and `D:\TradingProd` (production —
see the section above; that is where sessions run). The venv in `D:\Trading`
serves both: activate it, then `cd` to whichever tree you mean. You are using
**IB Gateway**, so the paper port
is **4002** — this is now the script's default, and `run_dry.ps1` passes it explicitly.
(TWS paper would be 7497; both are in the safety allowlist.)

Easiest path — just run the helper, which creates the venv and installs deps on first use:

```powershell
cd "D:\Trading"
.\run_dry.ps1
```

If PowerShell blocks the script, either run it once with
`powershell -ExecutionPolicy Bypass -File .\run_dry.ps1`, or do it by hand:

```powershell
cd "D:\Trading"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --mode dry --strategy mcl --port 4002
```

In **IB Gateway, logged into the PAPER account** — Configure → Settings → API → Settings:
- ✅ Enable ActiveX and Socket Clients
- Socket port `4002`
- Trusted IPs: `127.0.0.1`
- Read-Only API: leave ✅ for the dry run, untick only when you want real paper orders

---

## Before every session: stop the machine sleeping

The trader, IB Gateway, and Claude's link to this folder all run **on your computer**. If
it sleeps mid-session:

- the Python process suspends — no bars, no trail checks, no orders;
- the Gateway socket drops, and there is **no reconnect logic**, so it may need a restart;
- **an open position loses its trailing stop entirely.** The trail lives in that process,
  not at IBKR. The position sits unprotected until the machine wakes.
- Claude loses access to this folder and to TradingView, so no live help and no review.

PowerShell, as administrator, once:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Sleep and hibernate to Never on mains power. The **display** can still switch off — screen
blanking is harmless, only sleep matters.

On a laptop, also set **Settings → System → Power & battery → Lid, power and sleep button
controls → "Closing the lid" → Do nothing** (plugged in). Closing the lid sleeps the
machine regardless of the timeout settings.

Leave the **Claude desktop app running** if you want Claude able to read the fill log or
drive the chart during or after the session.

### Letting it sleep afterwards

To have the machine sleep itself once the session is genuinely finished:

```powershell
.\run_paper.ps1 -SleepWhenDone                      # sleeps 20 min after 09:30
.\run_paper.ps1 -SleepWhenDone -SleepDelayMin 45    # or pick your own delay
```

The trader exits at 09:30 ET once flat, prints the session summary, waits out the delay,
then suspends. The delay exists so there is time to read the log — or for Claude to run
its review — before the bridge goes down.

Two guards: it **refuses to sleep while a position is open** (the trailing stop lives in
that process, so suspending it would leave the position unprotected), and **Ctrl-C during
the countdown cancels it**.

---

## Daily workflow

### 1. Build the watchlist (you, ~03:45 ET)

Run your scanner and write today's qualifying names into `var/watchlist.txt`, one per line:

```
# 2026-09-02 — $2-20, RVOL>=5x, float<20m, top-2 premarket gainer
ABCD
WXYZ
```

Lines starting with `#` are ignored; blanks and duplicates are dropped; case doesn't matter.

**The file is re-read every 5 seconds while the script runs**, so you do not need to have
the final list ready before you start:

- **Add a ticker mid-session** → it is qualified and subscribed within ~5s and becomes
  eligible for entries immediately.
- **Remove a ticker mid-session** → it stops taking *new* entries. If it is currently
  **holding a position, that position is still managed through to its exit** — the trail
  and the signal exit keep running. A position is never orphaned by an edit to the file.
- **Re-add a ticker** → it becomes eligible again.

Every add/remove is announced in the console log.

To start before you have any names at all:

```powershell
.venv\Scripts\python.exe main.py --mode dry --strategy mcl --port 4002 --allow-empty
```

Without `--allow-empty` an empty watchlist is treated as a mistake and the script exits.

### 2. Dry run first, every time

```powershell
cd "D:\TradingProd"
.\run_dry.ps1
```

Places nothing. Logs every signal it would have taken with the live bid/ask at that
moment. Run this for at least one full session before letting it trade.

It prints the account ids it connected to on startup. **They must begin with `DU`** —
that is IBKR's paper prefix, and the script aborts if they don't. This is also the
cleanest confirmation you are on paper, given the Claude↔IBKR connector can't currently
read account data.

### 3. Paper orders

**Untick Read-Only API** in IB Gateway (Configure → Settings → API → Settings) — with it
on, every order is rejected. The script now names that failure explicitly rather than
logging it as a no-fill, so you'll know within a minute if you forgot.

```powershell
cd "D:\TradingProd"
.\run_paper.ps1
```

It asks you to type `PAPER` to confirm, then trades.

**The prompt is in `main.py`, not in this script** (moved there 2026-09-10). It fires
however you start the trader, including `python main.py --mode paper` directly. Pass
`--yes` to skip it for a scheduled run; without a terminal and without `--yes` the run
is REFUSED rather than assumed either way.

The prompt is not the protection and should never be read as it. The port allowlist
(4001/7496 refused *by name* as LIVE) and the `DU`-prefix account check live in
`trader.main_async` and cannot be bypassed from any entry point. Add `-AllowEmpty` to
start before the watchlist is ready.

For more than one strategy:

```powershell
.\run_paper.ps1 -Strategy mcl,mc5 -MaxPositions 3
```

### The watchlist feed runs in the same process (2026-09-10)

`--mode paper` starts `common.tv_feed` in a thread, so ONE command starts
everything. **Do not also run `run_tv_feed.ps1`** — a writer lock refuses the
second one rather than letting two processes overwrite `watchlist.txt` every few
seconds. The same lock covers the IB scanner (`--mode scan`).

The feed is strictly subordinate to the trader. If it dies, the process prints
`watchlist feed died ...`, the watchlist goes stale, and **trading continues** — a
stale watchlist is survivable, whereas a killed process leaves an open position
with no trailing stop, because the stop lives in this process and not at IBKR.

`--no-feed` turns it off when something else is writing the watchlist.

`--strategy` takes ONE comma-separated value. `--strategy mcl mc5` with a space is
refused, because it would otherwise run MCL alone while looking like it ran both.

It exits on its own at 09:30 ET once flat. Ctrl-C is handled cleanly.

**Watch the first order.** The single most likely failure is a rejection you don't notice.
Confirm the first BUY line reads `filled` and not `REJECTED`.

### The feed, signed in (2026-09-18)

Polled without a login, TradingView's scanner serves the watchlist **15 minutes
late** — it says so itself, `update_mode = delayed_streaming_900`. Signed in with
your session cookies the same endpoint reads `streaming`
(`docs/research/feed_freshness_probe_RESULT.md`). `tv_feed` sends the cookies
when **both** `TV_SESSIONID` and `TV_SESSIONID_SIGN` are set in the environment
it starts under, and sends nothing when either is missing.

**Only a production tag that carries the cookie code can use it.** Check once,
from `D:\TradingProd`:

```powershell
.venv\Scripts\python.exe -c "from common.tv_feed import COOKIE_ENV; print('cookie support present')"
```

An `ImportError` means the tag predates it (`prod-20260918` does) and the two
variables do nothing until the next promotion, after a close.

**One-time:** in a logged-in TradingView tab, F12 → Application → Cookies →
`https://www.tradingview.com`, copy the values of `sessionid` and
`sessionid_sign` into a 1Password item **TradingView** in the **Trading** vault,
fields `sessionid` and `sessionid_sign`. Never into the repo, a `.ps1`, or a
chat.

**Every session**, in the SAME PowerShell window you will start the trader from,
before `.\run_paper.ps1`:

```powershell
$env:TV_SESSIONID = op read "op://Trading/TradingView/sessionid"
```

```powershell
$env:TV_SESSIONID_SIGN = op read "op://Trading/TradingView/sessionid_sign"
```

Each line asks 1Password (Windows Hello) and holds the value in that window
only; `run_paper.ps1` and the python it starts inherit it. Both lines or
neither — `sessionid` alone is served **anonymously** with no error, which is
why a half-set pair logs ERROR and sends nothing.

**Do not `setx` these two.** Unlike `DATABENTO_API_KEY`, `tv_feed` does not
resolve an `op://` reference; a persisted reference would be sent as the cookie
and served anonymously. (Resolving them through `secrets_util` is a pending
change; until then the `$env:` lines are the way.)

**Read the startup line.** `tv_feed` checks `update_mode` once at startup:

- `streaming` → INFO, signed in. Good.
- `delayed` **with** a cookie sent → **ERROR**: the cookies have expired or the
  session was logged out. Repeat the one-time step (new values into the same
  vault item) and restart.
- `delayed` with no cookie → WARNING: the variables were not set in this window.

Cookies do not rotate on their own; they die on logout in that browser, a
password change, "log out of all devices", or their expiry date (visible in the
DevTools Expires column). Do not log out of the browser you copied them from.

**Two things this does not settle.** TradingView's terms describe its features
as for manual use; signing the feed with your account is your decision to make,
not a side effect of setting two variables (`claude/tv_cookie_in_the_cloud_20260918.md`
§1). And a session variable does not travel to a scheduled task or a cloud host
— those need the cookies in the process environment another way.

---

## End of session: the watchlist archives itself

When the session finishes, `var/watchlist.txt` and `var/watchlist_blocked.txt`
are copied into `var/archive/` with the date appended, then cleared:

```
var/archive/watchlist_20260902.txt
var/archive/watchlist_blocked_20260902.txt
```

So the next morning starts from an empty list and cannot accidentally trade
yesterday's names.

Guards:

- **An early Ctrl-C does not clear anything.** Only a session that actually
  reached 09:30 ET archives. `--force-archive` overrides.
- **It refuses while a position is open**, and tells you which.
- **A file that fails to archive is never cleared.**
- **Running twice in a day does not overwrite** — the second becomes
  `watchlist_20260902_2.txt`.
- **`watchlist_pinned.txt` is left alone** — it is meant to persist.

`watchlist_blocked.txt` is cleared too, deliberately: broker restrictions change,
and the `whatIf` probe re-detects anything still blocked within seconds. The daily
archives are also the record of how often IBKR refused a name, which is the number
that decides whether IBKR can host this strategy at all.

`--no-archive` turns the whole thing off.

---

## The verification step that actually matters

**IB's 1-minute bars are not TradingView's 1-minute bars.** Different exchange
inclusion, different consolidation, different handling of odd lots and thin prints.
So the Python signals will *not* be identical to the Pine signals, and the size of that
gap is itself something we need to know.

After the first dry run:

1. Open the same ticker and date on the TradingView chart with `pine/MCL.pine`
   attached — the **current** script, apex off. Reconciling against V7 would
   compare the live trader with a configuration it stopped running on 2026-09-05.
2. Compare the buy/sell markers on the chart against the `entry_signal` rows in
   `var/fills/mcl_fills_YYYYMMDD.csv`.
3. Send me the CSV plus the chart's trade list and I'll reconcile them.

Signals that appear in one and not the other are the thing to chase. Expect some
mismatch; large mismatch means the data source difference matters more than the rules.

---

## TradeZero API credentials (one-time setup)

Only needed for the hybrid experiment — routing names IBKR refuses to TradeZero.

### 1. Generate paper keys

TradeZero **Paper** portal → **Enable API Trading** → sign the paper agreements →
**API Key Management** → **Generate API Keys**. Keep the page open: the secret is
shown once.

### 2. Store them in 1Password

New **API Credential** item, named exactly `TradeZero Paper`, in the `Private`
vault, with two fields named exactly:

| Field | Value |
|---|---|
| `key id` | the public key |
| `secret` | the secret |

The names become the address the script uses, so they must match.

### 3. Install the CLI

```powershell
winget install 1password-cli
op --version
```

Then in the 1Password desktop app: unlock, enable **Windows Hello**, and turn on
**Settings → Developer → Integrate with 1Password CLI**.

### 4. Prove it works BEFORE wiring anything up

```powershell
op read "op://Private/TradeZero Paper/secret"
```

Windows Hello prompt, then the secret prints. If not:

- *"isn't an item"* → wrong item or vault name; `op item list` shows the truth.
- *"isn't a field"* → wrong field name;
  `op item get "TradeZero Paper" --format json` shows the real ones.
- *no Hello prompt* → step 3's integration is not active; reopen the terminal.

### 5. Point the script at the references

```powershell
setx TZ_API_KEY_ID     "op://Private/TradeZero Paper/key id"
setx TZ_API_SECRET_KEY "op://Private/TradeZero Paper/secret"
```

**Reopen PowerShell** — `setx` only affects new terminals.

### 6. Check

```powershell
.\.venv\Scripts\python.exe -m brokers.tradezero.client              # read-only
.\.venv\Scripts\python.exe -m brokers.tradezero.client --probe JLHL # can TradeZero open it?
```

Expect `PAPER ACCOUNT CONFIRMED`. The probe places one BUY 1 @ $0.01 — far below
any market so it cannot fill — and cancels it.

### Fallbacks if 1Password is more trouble than it is worth

The script also accepts the values directly, in the same variables, or in
`tz_credentials.json` beside it:

```json
{"key_id": "...", "secret": "..."}
```

Either field there may also hold an `op://` reference. Keep that file out of any
repository and off shared drives.

### Why the paper guard matters more here than at IBKR

IBKR could be made safe by port: 4002 physically cannot reach the live account.
**TradeZero serves live and paper from one base URL and the key pair alone selects
the environment** — live keys in these variables would place live orders. So
`brokers/tradezero/client.py` refuses to do anything beyond reading until every account reports
`accountType == "Paper"`.

---

## Seeing what the account is doing (Gateway has no UI)

IB Gateway shows no orders, positions or trades, and IBKR won't let the same
username hold a Client Portal / TWS / IBKR Desktop session while Gateway has it.
The API is the way in — it accepts **multiple simultaneous clients** on one Gateway,
so a second, read-only process can look at the account while the trader runs.

```powershell
.\show_trades.ps1            # print once
.\show_trades.ps1 -Watch     # refresh every 30 seconds
```

It prints balances, open positions, open orders, and today's executions. It connects
on client id `77`, places nothing, and is safe to run alongside `run_dry.ps1`.

**One IB quirk:** a client only sees the orders and executions *it* placed, unless it
is the designated master. To make the trader's fills visible in `show_trades`:

> Gateway → Configure → Settings → API → Settings → **Master API client ID: `77`**,
> then restart Gateway.

Balances and positions are account-wide and show up either way — so even without that
setting you can see the position appear and disappear.

**The authoritative record is still `var/fills/mcl_fills_YYYYMMDD.csv`**, written by the trader
itself. It has more than IB will tell you: the bid/ask at signal time, the limit sent,
and the slippage against what the backtest assumed. IB's own trade log has none of that.

Three other routes, for completeness:

- **The trader's console output.** Every signal, order and fill is logged live.
- **IBKR paper Client Portal.** Paper accounts have their own username (usually your
  live one with a suffix). Logging in there kicks Gateway's session out, so only do it
  after the session ends. Statements → Activity gives the official trade report.
- **Trade confirmation emails.** Off by default for paper; can be enabled in Client
  Portal settings if you want a passive record.

---

## What a dry run does and does not prove

A dry run **simulates the full round trip**: it opens a virtual position at the
marketable-limit price, then runs the trailing stop against live quotes exactly
as the live version would (the apex exit is OFF). Every SELL row carries `entry_price`,
`exit_price`, `trade_pnl`, `trade_pct` and `hold_minutes`, and the session ends with a
printed summary of trades and net P/L.

**What it proves:**
- The signals fire, on the names and at the times you'd expect.
- How they compare against TradingView — the reconciliation step below.
- What crossing the real spread costs. Fills are priced at the actual bid/ask plus
  20bps, not at the bar close, so `slippage_vs_ref` is a genuine measurement.

**What it cannot prove:** whether the size was there. A simulated fill assumes someone
was resting at the touch. Pre-market on a $3 stock with 200 shares on the offer, that
assumption is exactly the thing in doubt — and only live paper orders test it. So read
the dry-run P/L as *the best case*: the version of the strategy where every order fills.
If that number is bad, the strategy is bad. If it's good, it is still unproven.

That is why session 3 onward places real paper orders. The gap between dry-run P/L and
paper P/L **is** the fill risk, quantified.

---

## Reading the fill log

`var/fills/mcl_fills_YYYYMMDD.csv`, one row per signal:

| Column | What it tells you |
|---|---|
| `ref_close` | what the backtest assumed you'd get |
| `bid` / `ask` / `spread` / `spread_pct` | the real book at signal time |
| `limit_sent` | marketable limit, priced 20bps through the touch |
| `fill_price` / `status` | what actually happened |
| `slippage_vs_ref` | **fill − ref_close.** Negative = worse than the backtest assumed |
| `seconds_to_fill` | how long it took |
| `status` | `FILLED`, `PARTIAL_FILL`, `NO_FILL_CANCELLED`, `REJECTED`, `DRY_RUN`, `NO_QUOTE` |
| `reject_reason` | IB's own words, when it refused the order outright |
| `entry_price` / `exit_price` | round trip, written on the SELL row |
| `trade_pnl` / `trade_pct` | P/L for that trade, net of commission only — **not** net of the measured stop-fill friction |
| `hold_minutes` | time in the position |

Three questions to answer from one session:

1. **What is the average `slippage_vs_ref`?** **Corrected 2026-09-11 — the old
   text here said "against V7's +$924 over 50 trades, anything worse than about
   −$18/trade wipes out the edge". There is no edge to wipe out.** On the
   screened universe MCL's break-even friction is **−$0.96 per round trip**: it
   loses money at zero cost. Measured from 21 live trailing-stop exits, the real
   stop-fill cost is a **mean −$8.46 per 100 shares** (median −$2.25, 20 of 21
   adverse), against the $4.26 every backtest charges — so the shipped figure is
   too small by roughly half. See `stop_fill_20260911.md`. **This is what the
   session is for**: each round trip improves that estimate, which is the
   largest un-nailed number in the project.
2. **How often is `status = NO_FILL_CANCELLED`?** Every no-fill is a backtest trade that
   would not have existed. If the winners are the ones that don't fill, the edge is
   imaginary. Count `PARTIAL_FILL` here too — a 40-share fill on a 100-share signal is
   60% of a trade that didn't happen. **`REJECTED` rows are not liquidity** and must be
   excluded from this ratio; they mean a setting was wrong.
3. **What is the typical `spread_pct`?** On a $3 stock a 3-cent spread is 1% — a fifth
   of the entire 5% trailing stop.

---

## On syncing from a TradingView watchlist

Claude can read the **currently selected** TradingView watchlist and write its contents
into `var/watchlist.txt`. What it cannot do:

- **Create or switch watchlists.** The connector's `watchlist_add` / `watchlist_get` only
  act on whichever list is active in the UI. Create `MCL Today` yourself and select it.
- **Poll on a timer.** Claude only runs when you send a message. Scheduled tasks start a
  fresh session with no context and are hourly at minimum, so a 30-second sync is not
  possible from Claude's side.

This is why the script hot-reloads the file instead. `var/watchlist.txt` is the source of
truth and it works whether or not Claude is in the conversation. Ask for a sync when it
suits; edit the file directly the rest of the time.

## Known gaps

- **Trailing stop is software-side.** IBKR's native trailing stop fires a market order,
  which IBKR does not accept pre-market for US stocks. This script tracks the peak itself
  and sends a marketable limit when breached. If the script dies, **the stop dies with it**
  and the position sits unprotected. Do not leave it unattended with a real position.
- **Bar-close evaluation.** Mirrors Pine's `process_orders_on_close`, so there is up to
  60 seconds of lag between the move and the order. Real, and deliberately not hidden.
- ~~**Position sizing differs from the backtest.**~~ **Resolved.** Paper equity is
  **$22,290.96**, so the 40% cap is $8,916 — it only reduces size above **$89.16/share**.
  The universe is $2-20, so every trade is a full 100 shares, exactly as the backtest
  assumed. No need to fund the account further.
- **No scanner.** Universe is manual, so the selection bias in every backtest so far
  (21 names chosen because they ran) is still unaddressed. Forward testing on
  contemporaneous scanner picks is the only thing that fixes it.
- **Single session, single process.** No reconnect logic if TWS drops. Watch it.

---

## Suggested sequence

**Updated 2026-09-11.** The original sequence is complete — five sessions of
paper fills exist and the slippage substitution has been made
(`stop_fill_20260911.md`). What the sessions are for now:

| When | What |
|---|---|
| Every session | **More trailing-stop fills.** n = 21. It is the largest un-nailed number in the project, the $4.26 the backtests charge is roughly half the measured mean, and nothing else in this repository can improve it. |
| Every session | Run from `D:\TradingProd` and check the provenance line. A session run from the wrong tree is only visible in that line. |
| Not yet | Any read of session P/L as validation. Both live strategies are negative **gross** on the screened universe — before any cost assumption — so a good night is variance and a bad one is not news. |
