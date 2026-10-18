# W16-0019 · Tanja Trades (Chart Fanatics) + Tom Sosnoff videos and channels — RESULT

2026-10-18 · Research & spec chat · Decision item: **W16-0020** · Raw extracts: `claude/raw/w16_0019_tanja_sosnoff_extracts_20261018.txt`

## In plain terms

Neither video gives us a new strategy to test as it stands. The Tanja Trades episode (Chart Fanatics, July 2025) was already extracted in our 27 September sweep (W16-0001); her trade entries are the same "stop raid, sharp reversal, enter on the pullback" pattern recorded there, with no exact definitions. The one idea worth testing is her day filter: she only pushes hard on the New York morning after a major 8:30 release (CPI best, then PPI, jobs report, GDP, the day after a Fed decision), and stays out or trades smaller the day before those releases, around bank holidays, and the day after a very large range day. We can check that on NQ/ES 1-minute data we already own, without building a strategy first. Tom Sosnoff's video is about selling options (short puts, credit spreads, covered calls held about 45 days). It is a well-known, credible approach, but it is a different business from what this project does, we own no options history to test it, and naked puts most likely need the margin approval IBKR declined before. Neither channel is worth a full sweep.

All win rates and dollar figures below are the presenters' own claims. Nothing here is a backtest.

## What Ben must decide (W16-0020)

Pick any combination.

| Option | What it is | Data | Rec. model · effort |
|---|---|---|---|
| **A (recommended)** | **Day-type check on NQ/ES**, no P&L. Measure the New York morning (09:30–12:00 ET) on 2010–2023 for: release days (CPI, PPI, jobs report, GDP), the day after a Fed decision, the day before CPI/jobs/Fed, bank-holiday-adjacent days, the day after a very large range day, and ordinary days. Compare how far price travels and how much of that is one-way (net move ÷ total distance travelled). If release days really are cleaner, test the filter as a gate on DVP and future W16 entries against random removal. | NQ/ES 1-min (owned) + the MFLAG-v1 event calendar, plus PPI and GDP dates | Sonnet · Medium to build; Ben runs it locally |
| B | **Register her entry model** (W16-0002's unpicked option B): a 15-min shift in structure after a raid of a prior high/low, entry on a 1-min pullback into the gap, stop at the swing, part profit at 2R, stop to breakeven, two losses and done for the day. Heavier: "displacement" and "draw on liquidity" have to be defined by us. | NQ/ES 1-min (owned) | Opus · High to register; Sonnet · High to build |
| C | **Options premium-selling line.** First a free look: CBOE's published put-writing (PUT) and covered-call (BXM) index histories against the S&P 500, plus a check of which options strategies the IBKR account is permitted. Only then decide on buying options history. Would be a new workstream. | Free CBOE index files; IBKR account settings | Sonnet · Low |
| D | Record only. | — | — |

R = the risk on the trade (2R = a gain twice the stop distance).

## Video 1 — "This SIMPLE ICT Futures Trading Strategy Made Her Over $100,000 - Tanja Trades"

Chart Fanatics, 13 Jul 2025, 70 min, 249k views. https://www.youtube.com/watch?v=PZDWQgtqt2I · Full transcript read (100%).

**Already in the project:** W16-0001 (27 Sep) extracted this exact video. ICT = "Inner Circle Trader", a family of chart concepts (liquidity raids, fair value gaps, power of three).

**Her method, as stated**

1. Market moves in three phases: sideways build-up, a false move that runs stops ("manipulation"), then the real one-way move ("distribution"). She only trades the third.
2. Morning checklist: (a) economic calendar — red-folder (high-impact) release today? (b) are NQ, ES and YM moving alike? (c) can she name the target (equal highs/lows, an unfilled 4H/daily gap, a short-term high/low with untouched orders beyond)? No target, no trade. (d) has price broken a swing high/low with force, leaving a gap? (e) are higher-timeframe gaps being respected?
3. **Low-quality days (skip or trade small):** no red-folder release; bank holidays and the day after; the day before CPI (small size), the day before jobs (mostly skip), the day before a Fed decision; the day after a very large range day that hit a monthly/weekly target; "seek and destroy" chop where price keeps returning to the middle of the range.
4. **High-quality days:** the New York session after an 8:30 release — CPI is her favourite (she claims 70–80% wins on CPI days), then PPI, jobs, GDP, and the session after a Fed decision.
5. Entry: structure shift on the 15-min, entry on the 1-min into a gap or when a small gap is broken through ("inversion"); prefers 09:50–10:10 and 10:50–11:10 ET; often waits for the first 15-min candle.
6. Management: part profit around 2R, stop to breakeven, trail behind the last swing, keep a runner; two losses and she stops for the day.
7. Claims: trend 20–30% of the time; example trades $2,600 (100 NQ points in 15 min, CPI day) and $2,200 (PPI day, about 10 min).

**What's testable:** item 3–4 (the day filter) is pure calendar plus prior-day range, so it can be coded exactly. Items 2b–2e and 5 need our own definitions. She gives no record beyond selected stream trades. Her own recap videos show she trades prop-firm simulated "funded" accounts and evaluations, and the episode carries Apex, Tradezella and PropFirmTrader adverts.

**Against what we've already tested:** MFLAG-v1 (W15-0023) tested skipping entries on jobs/Fed days on a daily Donchian host and failed (90th percentile against a 95th bar). It listed intraday timing as untested. Her claim is different: release days are the good days intraday, not the bad ones. That's what option A measures.

## Tanja Trades channel

146k subscribers, 780 videos, joined Jun 2023, livestreams Tue–Fri 09:15 ET. Recent uploads are mostly vlogs, meetups, prop-firm reviews and interviews (JadeCap and Trader Kane were already covered in the Chart Fanatics sweep). Two strategy recaps read in full ("CPI Continuation Shorts Caught in Real Time", "Best Way to Trade High Resistance Conditions"). The only additions to the podcast: she holds trend-day shorts while price stays below the 10:00 or 08:30 opening price; when one of NQ/ES makes a new low of day and the other doesn't, she takes heavy partial profits; on choppy days she only fades the range extremes back to the middle. **Verdict: no sweep.** It is livestream and discretionary, and adds nothing to the podcast.

## Chart Fanatics channel

529k subscribers, 1,042 videos. Already swept in W16-0001 (32 scalping/ICT/order-flow videos) and reviewed in W11-0031. **No re-sweep.**

## Video 2 — "By Far, the 3 Best Trading Strategies" (Tom Sosnoff)

16 Oct 2026, 10 min, 97k views. https://www.youtube.com/watch?v=HR1OasBM9ew · Full transcript read (100%). Sosnoff founded thinkorswim and tastytrade.

**Rules as stated**

1. **Naked short put:** sell about the 25-delta put (16–25 in practice), just outside the expected move, about 45 days to expiry. He quotes a 75%+ chance of success, and margin of about 20% of the strike. Best on stocks that have sold off with high implied-volatility rank (IVR). Keep size small, diversify, don't average down; roll or sell a call against it if wrong.
2. **Credit spread:** short strike just outside the expected move, collect 25–33% of the strike width (20–25% on index call spreads). He mostly sells call spreads on SPX/QQQ/SPY because upside options are priced richer. Prefers monthly to weekly expiries.
3. **Covered call:** 100 shares plus one short call at about 30 delta, about 45 days; buy back at 50% of the premium and roll. Stocks $10–$100 that have sold off with high volatility. He claims it lifts the chance of profit on the stock from about 54% to about 64%.
4. **Portfolio:** roughly 10–20% stock, 10–20% credit spreads, up to 40% naked strangles or short puts.

**Reading it plainly:** the edge here is that options tend to be priced for more movement than actually happens, so sellers collect a premium on average and take occasional large losses (the volatility blow-ups of February 2018 and March 2020). "75% chance of success" is the chance the put expires worthless, not the chance of making money over time, because the losing 25% are much larger than the wins. Positions last weeks, and it is a portfolio approach rather than a signal. Testing it needs historical option prices, which we don't own. Naked puts and strangles need a margin account; IBKR declined Ben's margin application before. Spreads typically need margin at IBKR too, so the account's options permissions would need checking. Cash-secured puts tie up the full strike: $1,000–$10,000 per contract at his $10–$100 stock range.

## Tom Sosnoff channel

73k subscribers, 26 videos, started Nov 2025. The channel promotes his free platform Lossdog. Most titles are motivational ("Making You Infinitely Rich in 200 Seconds"). The strategy content is in this video and "11 'Boring' Trading Strategies" (also read in full: short puts at 16–22 delta and 35–50 days, jade lizard, put ratio spread, broken-wing butterfly, skewed iron condor, short strangles). He says short strangles plus discretionary volatility selling make up about 70% of his profits. **Verdict: credible on mechanics, off-strategy for this project. No sweep.**

## Addendum 2026-10-18 — wider channel check

Ben asked whether anything else on the two channels is worth considering. The YouTube transcript connector disconnected mid-check, so this pass used titles, page descriptions and chapter lists only.

- **Tanja Trades:** "How to Trade All-Time Highs" (Apr 2026), "Risk Management Protocol for Futures Prop Firms" (May 2024) and "How to Add to Winning Positions" (+88 pts NQ, Aug 2024). The descriptions carry no rules, only prop-firm affiliate offers. The one useful idea is adding to a winner. That is noted on W16-0022 as an optional variant, with the transcript to read once the connector is back. The prop-firm risk video doesn't apply, because Ben trades his own IBKR account.
- **Tom Sosnoff:** "If You Master Volatility" (IV rank basics), "I Quit Passive Investing" (his split: 30–40% cash, 30–40% options, 10% stocks, 20% futures), "If You Only Watch One Investment Video" (why to trade actively), "I Watched Markets for 40 Years" (a broker checklist: spreads, data and exchange fees, interest on idle cash, negotiable margin rates). Nothing to test. The broker checklist is general and IBKR already does well on it.
- **Verdict:** nothing further. No new items.

## Caveats

- Transcripts are YouTube auto-captions. Numbers are as spoken.
- Every win rate and dollar figure is the presenter's own and unaudited.
- The IBKR margin and spread-permission points come from Ben's earlier margin decline and IBKR's usual rules, not from checking the account.

## Next steps (board)

- **W16-0019** — this review, Done.
- **W16-0020** — Done 2026-10-18. Ben: "A · Day-type check (Recommended), B · Register her entry model".
- **W16-0021** — day-type check (A), Scalping chat, Sonnet · Medium. Run first.
- **W16-0022** — register Tanja's entry model (B), Scalping chat, Opus · High to register. Starts after W16-0021.

## Sources

- https://www.youtube.com/watch?v=PZDWQgtqt2I · https://www.youtube.com/@TanjaTrades (rr1NkWnedFs, 6YDR-q3bVnE) · https://www.youtube.com/@chart-fanatics
- https://www.youtube.com/watch?v=HR1OasBM9ew · https://www.youtube.com/@SosnoffonMoney (Z__VENA80Bo)
- Project: `claude/w16_0001_chart_fanatics_scalping_RESULT_20260927.md`, `claude/w15_0023_mflag_v1_RESULT_20260930.md`
