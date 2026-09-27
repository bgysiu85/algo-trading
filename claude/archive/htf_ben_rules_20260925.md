# HTF-Ben v0 — Ben's crude-oil 4-hour method, written as exact rules (DRAFT for Ben to confirm)

2026-09-25 · High timeframe chat · Board: W15-0001 (this doc), W15-0002…0005 (next steps)
Source: Ben's questionnaire answers, 2026-09-25 (quoted where they matter). No data looked at, no P&L computed.

## Revised 2026-09-25: Ben confirmed §2 (overrides the table below)

| Point | Ben's answer | Rule now |
|---|---|---|
| R7 trail trigger | "$0.20/bbl price move" | Midpoint stop starts at $0.20/bbl open profit ($20/MCL, $200/CL), any size |
| R4 "next candle" | "Within the next 2 bars" | EMA9 rising and closing on EMA21 on bar t+1 or t+2 after the MACD cross; enter at the open of the bar after the confirming bar |
| R3 daily trend | "Price vs daily EMAs" | Up = last completed daily close above both daily EMA9 and EMA21; down = below both; between = no trade (exact form assumed; Ben may veto) |
| R2 bar times | "18:00 New York" | 4H bars at 18:00, 22:00, 02:00, 06:00, 10:00, 14:00 NY |

## In plain terms

This is the method you paper-trade on NinjaTrader, written as rules a computer can follow. It trades
crude oil on the 4-hour chart. It only goes long when the daily trend is up, and only short when it's
down. The trigger is MACD crossing its signal line, followed by EMA9 turning and closing the gap to
EMA21. The stop goes beyond the last obvious swing. Once the trade is about $0.20/bbl in profit
($2,000 on your 10 CL), the stop jumps to halfway between entry and price and keeps ratcheting, so it
always protects at least half the open profit. There are no targets: the trailing stop is the only
exit. It's tested two ways, **intraday** (flat before the CME daily close) and **multi-day** (holds
overnight), each on a **$10,000** account allowed to draw down up to **70%**.

It's quite different from TL-v0 (Tori's textbook method, W01-0013). That's intentional: this one is
*yours*.

## 1. The rules

| # | Element | Rule as coded (v0) | Ben's words / source |
|---|---|---|---|
| R1 | Market | CL (NYMEX crude). Results in MCL (1/10 size, $100 per $1/bbl) and CL ($1,000 per $1/bbl) | "Crude (MCL/CL)" |
| R2 | Entry chart | 4-hour bars, CME session (18:00–17:00 New York) | "4-hour" |
| R3 | Trend filter | Long only if the **Daily** trend is up; short only if it's down. Daily trend = direction of the last completed daily trend-line break (TL-v0's line code, completed daily bars only). Weekly: reported as context, **not** a filter | "Daily must agree, weekly as context" |
| R4 | Trigger (long) | 4H bar *t*: MACD(12,26,9) line crosses **above** its signal line. Bar *t+1* (next completed 4H bar): EMA9 is rising (EMA9[t+1] > EMA9[t]) **and** the gap to EMA21 is closing (\|EMA9−EMA21\| smaller at t+1 than at t). Enter at the **open of bar t+2**. Short = mirror image | "When MACD crosses above signal line and the next candle i can see EMA9 trending upwards and closing gap with EMA21, i enter a long trade. vice versa for short sell" |
| R5 | Trend line | Visual aid only in v0 (not required). A variant **v0-TL** also requires a 4H trend-line break-and-retest in the same direction within the last *N* bars (see §3) | "I use trendline as the visual aid with the indicators as confirmation of the trend" |
| R6 | Initial stop | Just beyond the last confirmed 4H swing: long = below the most recent swing low; short = above the most recent swing high. Swing = a bar whose low (high) is the lowest (highest) of the 2 bars either side (confirms 2 bars later, so no look-ahead). Buffer 1 tick | "Beyond last swing", "Obvious turning point" |
| R7 | Stop to "half profit" | When open profit first reaches **$0.20/bbl** (= Ben's ~$2,000 on 10 CL), move the stop to the midpoint of entry and current price. Then, whenever price makes a new favourable extreme, move the stop to the new midpoint. The stop never loosens. Checked on completed 4H bars (v0); a 1-hour-checked variant is listed in §3 | "once it is approximately $2000 in the green… move the stop loss to mid point between entry price and current price… always protecting at least 50% of profit" |
| R8 | Exit | Only the stop (R6/R7). No targets | "I use the trailing stop" |
| R9 | Opposite signal while in a trade | Ignored; the stop decides the exit. One position at a time | (not asked; Ben doesn't add, "No") |
| R10 | Adds | None | "No" |
| R11 | Scenario A — **Intraday** | As above, plus: flat at the last price before **17:00 New York** (CME daily close); no new entry in the final 4H bar of the session | "close position by end of day due to margin requirements" · "Flat before CME close" |
| R12 | Scenario B — **Multi-day** | As above, holding overnight and over weekends; gaps fill at the open | "Once my capital is large enough, i will start holding overnight" |
| R13 | Account | $10,000 start per scenario. Report whole-MCL sizes and 1 CL. Largest size whose worst historical drawdown stays under **70% ($7,000)** named as the "max size"; a run that touches $3,000 equity is flagged **ruined** | "Assume a $10k account size… both have full account size and can draw up to 70% of account" |
| R14 | Costs | NinjaTrader commission + exchange fees per side (priced from NinjaTrader's published schedule before the run); slippage 1 tick per side on entries and stops, 2 ticks at 3× friction | project standard |

## 2. Points for Ben to confirm (W15-0001, subitem 3)

1. **The $2,000 trigger as $0.20/bbl.** On 10 CL, $2,000 = $0.20/bbl. On a $10k account with 1–2 MCL, $2,000 would be $10–20/bbl, and the trail would almost never start. v0 keeps your *price* behaviour ($0.20/bbl). Correct?
2. **"Next candle" in R4.** Is it the very next 4H bar after the MACD cross, or any bar within the next 2–3?
3. **The daily trend.** Coded as the last daily trend-line break (the TL-v0 line code). Alternatively daily EMA9 > EMA21, or daily MACD > signal. Which is closer to what you look at?
4. **4-hour bar times.** NinjaTrader's CME session template starts bars at 18:00 New York. If your chart uses different bar times, signals will differ.

## 3. Variants registered alongside v0 (fixed now, before any result)

| Variant | Change | Why |
|---|---|---|
| v0-TL | R5 made mandatory: also needs a 4H trend-line break then a retest touch with a rejection candle, within 6 bars before the MACD cross | Your earlier answer ("Break, then retest", "Touch + rejection candle") |
| v0-1H | R7 checked on 1-hour bars instead of 4-hour | You probably move the stop during the bar, not only at the 4H close |

Controls, same costs and sizing: **C1** MACD cross alone (no EMA check, no daily filter); **C2** Donchian 20/10 on 4H; **C3** random entries on the same bars (1,000 draws). If v0 can't beat C1 and C2 after costs, the extra rules aren't adding anything.

## 4. Data and holdout

- Needs **CL 1-hour bars** (Databento GLBX.MDP3 `ohlcv-1h`, 2010–2026), resampled to 4H on the CME session. Priced before buying (W15-0002). The project owns only daily CL bars today.
- **Holdout** (the most recent years, kept unseen until one final test): 2022-01-01 onward, locked, with its own ledger (not TL-v0's). Training = 2010–2021.

## 5. Things to know before the numbers

- **Paper size vs this test.** On paper you trade 10 CL on $50k→$77.6k, about $10,000 per $1/bbl. A 4H swing stop is usually $1.50–$4 away, i.e. $15,000–$40,000 at risk per trade. The $10k scenarios will show what that kind of risk does over 12 years, not just two good weeks.
- **Intraday + 4H bars.** A same-day exit gives a 4H signal at most 1–4 bars to work, and the $0.20 trail usually won't have started. In Scenario A the exit will mostly be the initial stop or the 17:00 close. Expect A and B to differ a lot.
- **Your NinjaTrader trades** are for checking the code copies you (W15-0005), not for evidence of an edge.

## Next steps (board)

- **W15-0001** (Ben): confirm §2, save 3–5 annotated 4H chart screenshots to `D:\Trading\Claude outputs\htf_ben_screens\`, and authorise the Ninja_Trader_Paper connector in claude.ai settings.
- **W15-0002** (High timeframe chat, Sonnet · Low): price, then pull CL `ohlcv-1h` 2010–2026.
- **W15-0003** (High timeframe chat, Opus · Medium): write `REGISTERED_htf_ben_v0.md` from this doc plus your §2 answers.
- **W15-0004** (Build & test chat, Sonnet · Medium): build and run both scenarios on the training side, then the Result doc. Runs on your PC.
- **W15-0005** (Sonnet · Medium): replay your NinjaTrader trades against the coded rules (fidelity check).
