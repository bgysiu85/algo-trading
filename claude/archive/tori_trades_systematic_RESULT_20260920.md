# AT-104 · Tori Trades trend-line method → systematic rules — RESULT

2026-09-20 · Futures Trading Viability Analysis chat · builds on the extraction doc (AT-104, subitem 2)

> **Addendum 2026-09-26 (W01-0014):** a later video adds a "trend-line bounce" setup that is not in §1. See §7 at the end.

## In plain terms

About two-thirds of Tori's method can be turned into exact rules a computer can follow: drawing the trend lines, the "action line" entry, the "safety line" trailing stop, and position sizing. The other third can't: which setups count as "A+", where support and resistance go, and the news judgement she uses to hold through pullbacks. That third is probably where most of her selectivity sits, so a coded version would test *the method*, not *her*. Her profit figures therefore tell us nothing about how the coded version would do. Once coded, the strategy is a trend-following breakout system, the same family as TSMOM, which the project is already testing. The useful question is narrow: **do her hand-drawn trend lines beat a plain channel breakout on the same markets?** You can answer that cheaply with daily futures bars the project already owns, at no data cost.

## Verdict / what Ben must decide

- **Verdict:** it can be coded, and it is worth a cheap test but not a build. Her track record is not evidence for the coded version, because the parts that can't be coded (setup selection, news overlay, 4–7% risk) are the ones that would have produced it.
- **Decision for Ben (AT-105):** register a trend-line study, "TL-v0", and run only the two free steps first: (1) a Pine indicator that draws the algorithm's lines, checked against the trades she shows in her videos, and (2) a pre-flight on the owned daily bars that counts signals and stop sizes without computing any profit and loss. Or drop it here. **Recommended:** run the two free steps, and wait for TSMOM's training-side result (AT-43) before spending anything or building a backtest.

## 1. What can be coded and what can't

| Element as taught | Codified rule (TL-v0) | Discretion left |
| --- | --- | --- |
| Hand-drawn trend lines (ray tool) | Line through the two most recent confirmed swing highs (falling) or swing lows (rising), extended forward. It is invalid once a bar closes through it | Pivot size (fixed as a small ensemble, see §2) |
| "Touch" of a line | High/low within 0.25 × ATR(14) of the line | None once fixed |
| Top-down analysis (monthly → execution TF) | Only trade in the direction of the last line break on the next-higher timeframe, using **completed** higher-timeframe bars only | Which timeframes to use (fixed: weekly filter on daily, daily filter on 4H) |
| Action line = entry | Bar closes through the active opposite line by > 0.1 × ATR → enter at the next bar's open | None |
| Safety line = stop + trail | Stop = opposing trend line − 0.25 × ATR ("wiggle room"), re-drawn as new confirmed pivots form; the stop never loosens; resting stop order | **Fallback when no opposing line exists at entry** (common right after a trend flips). Rule: last confirmed swing low/high ∓ 0.25 × ATR |
| No fixed target | Hold until the stop is hit | None |
| 1–2% risk per trade | Contracts = floor(risk $ ÷ (stop distance × multiplier)); zero means skip, and the skip is counted | None |
| Support / resistance "confluence" | **Not coded in v0.** She calls it "fairly subjective". Tested later as a separate variant if at all | All of it |
| "A+ setups only", one instrument, one timeframe | **Can't be coded.** v0 takes every valid signal | All of it |
| News/geopolitics to hold through drawdowns | **Can't be coded, and deliberately left out** | All of it |

## 2. Three traps that would make a backtest look better than it is

1. **Hindsight lines.** A swing high is only known *R* bars after it happens. If the code draws a line through a pivot before that pivot is confirmed, the backtest sees the future. Hand-drawn lines on a finished chart, including every TradingView replay walkthrough in her videos, carry this bias. Rule: a pivot enters the line set only at bar i+R, and every line is rebuilt from what was known on that bar. Pine's `ta.pivothigh(L, R)` already returns the value R bars late, so keep that and never shift it back.
2. **Roll gaps create fake breaks.** Lines drawn across a futures roll on an unadjusted series break on the roll gap, not on price action. Draw lines on a **difference-adjusted (back-adjusted) continuous series** and book P&L on the actual held contract, using the TSMOM roll calendar. Ratio adjustment is unusable for crude because the front month printed negative in April 2020.
3. **One market, few trades.** She trades CL almost exclusively (5 trades so far this year). A rule that only works on crude is fitted to crude. v0 runs on all 12 markets already bought for TSMOM, and CL is read as one of 12, not as the headline.

## 3. Sizing at the paper account's size (~$22,000)

Micro crude (MCL) = 100 barrels, so $1.00/bbl of stop distance = $100 of risk per contract. Her shown trade: 4 full-size CL contracts with about $11,000 of open risk, which works out to **$2.75/bbl** of stop distance.

| Stop distance ($/bbl) | Risk per MCL | Contracts at 1% ($220) | at 2% ($440) | at 5% ($1,100) |
| --- | --- | --- | --- | --- |
| $0.50 | $50 | 4 | 8 | 22 |
| $1.00 | $100 | 2 | 4 | 11 |
| $2.00 | $200 | 1 | 2 | 5 |
| **$2.75 (her trade)** | **$275** | **0 — skipped** | 1 | 4 |
| $4.00 | $400 | 0 — skipped | 1 | 2 |

**What this means:** at the 1–2% she tells beginners to use, a $22k account can't take her own showcase trade at 1%. At 2% it's one contract. At the 4–7% she says she uses herself, ten straight losses at 5% cost about 40% of the account. The pre-flight (step 2 of AT-105) measures what share of signals can be sized at 1% and 2% on each market *before* any profit is looked at. If most can't be sized, that ends the study for this account size, and that is a finding in itself.

## 4. What it actually is, and what to compare it against

Coded, this is **trend-following with a sloping trailing stop**. So the question isn't "does it make money". It's "do the trend lines add anything over simpler trend rules on the same markets?" Register three controls, all with the same sizing and costs:

| Control | What it isolates |
| --- | --- |
| C1 · Donchian breakout (20-bar entry, 10-bar opposite-channel exit) | Does trend-line geometry beat a plain channel? |
| C2 · TL-v0 entries with an ATR chandelier stop instead of the safety line | Is the safety-line exit worth anything? |
| C3 · TSMOM sign on the same market, same holding period | Is this anything other than slow trend exposure? |

If TL-v0 can't beat C1 net of costs, the trend lines are decoration and the study closes.

## 5. Build path (cheapest first)

| Step | What | Data cost | Looks at P&L? |
| --- | --- | --- | --- |
| 1 | Pine indicator "TL-v0" draws the algorithm's lines and signals on CL1! (daily, 4H). Check it against the trades she shows (the $51,843 CL short and the "boring strategy" setup): does it draw her line and fire within 1–2 bars of her entry? Report a fidelity rate | $0 | No |
| 2 | Pre-flight on owned GLBX daily bars (12 roots, 2010–2026): signals per market per year, median stop distance in $ per micro contract, share sizeable at 1% / 2% on $22k | $0 | No |
| 3 | Write `REGISTERED_tl_v0.md`: rules above, controls C1–C3, pass criteria, pivot ensemble L=R ∈ {3, 5, 8}, holdout | $0 | No |
| 4 | Daily backtest, training side only | $0 | Yes |
| 5 | Only if step 4 passes: price and buy `ohlcv-1h` for CL (aggregated to 4H) and rerun at her timeframe | price first | Yes |

**Pass criteria (from PROGRAM_INDEX §4, as used for TSMOM):** positive after costs at every friction level; both halves of the sample positive; drop-top-N applied to markets and to years; beats C1 net; the registered spec sits mid-distribution among its neighbours (pivot size, buffers), not at the edge; the locked holdout is used once.

## 6. What this means for the futures-vs-equities question

Her channel can't settle it. Her P&L is self-reported and unaudited, and it comes from parts of the method that can't be coded. The strategies that *can* be coded point the same way the project already went: slower trend trades on liquid futures, where costs are small against the size of the moves. That is what killed every intraday small-cap strategy here. So the evidence for moving toward futures will come from TSMOM (AT-43) and, if it earns a run, TL-v0, not from this channel. That is a judgement from the project's own results, not a measurement.

## Caveats

- Based on 12 of 1,349 videos, read from transcripts. The rules in §1 follow her stated method. Her live decisions may differ, and step 1's fidelity check exists for exactly that reason.
- The parameters (0.25 × ATR touch/stop buffer, 0.1 × ATR break buffer, pivot sizes) are chosen here for v0. They are not taken from her. The registration must fix them before any return is seen.
- No backtest has been run, and no profit and loss has been computed.

## Next steps

- **AT-105** · Decide: register TL-v0 and run the two free steps (Pine fidelity check + daily pre-flight), or drop. Assignee Ben.
- **W01-0015** (added 2026-09-26) · Decide whether to register the §7 bounce setup as "TL-bounce". Assignee Ben.

## Source files

- Extraction: AT-104 extraction doc (monday) · `D:\Trading\Claude outputs\tori_trades_extraction_20260920.txt`
- This result: `D:\Trading\Claude outputs\tori_trades_systematic_20260920.txt` · project doc `claude/tori_trades_systematic_RESULT_20260920.md`
- Data referenced: `D:\Trading\Claude outputs\tsmom_manifest_20260919.txt` (12 roots, GLBX daily bars 2010-06 → 2026-09)
- Addendum source (2026-09-26): `claude/w01_0014_tori_bounce_video_RESULT_20260926.md`

## 7. Addendum 2026-09-26 — the "trend-line bounce" setup (video TuXOgkcYw9E, W01-0014)

Added by the Research & spec chat. The rules in §1 above are unchanged; TL-v0 / TL-v0-rev are registered and
are **not** amended by this. Full review: `claude/w01_0014_tori_bounce_video_RESULT_20260926.md`.

Her 2026-09-24 video teaches a second setup that §1 did not capture: buying a **pullback to a rising trend
line**, not a break of a falling one. Five elements are missing from the coded method:

| # | Element as taught | Proposed rule (TL-bounce, long shown) | In TL-v0? |
|---|---|---|---|
| B1 | **Bounce entry**: price comes "at or near" the rising line and reacts | Bar low ≤ line + 0.25 × ATR(14) and close ≥ line → enter next bar's open (variant: resting limit at line + 0.25 × ATR) | No — TL-v0 enters on a break |
| B2 | **Stop just beyond the same line** ($42 per MCL in her example) | Lower of (line − 0.25 × ATR) and (touch bar low − 1 tick) | No — opposing line |
| B3 | **Exit on a close through the line** | First close below line − 0.10 × ATR → exit next open; or the resting stop | No — resting stop only |
| B4 | **Trail under each new higher low, never on the wrong side of the line** | stop = max(old, min(swing low, line now) − 0.25 × ATR) | Partly — trails on the line |
| B5 | **Re-entry** on a later touch of the same line | Allowed while flat and the line is active | No |

Also now fully specified (still not coded, §2.3 of the registration): the chained, steepening lines — first
down line from the highest monthly high, first up line from the lowest monthly low, each new line starting at
the previous line's last touch, steeper on each lower timeframe (monthly → weekly → daily → 4H → 1H → 15m);
and "price cannot intersect the line", which she appears to apply to wicks, where TL-v0 uses closes with a
0.10 × ATR buffer.

Testing B1–B5 is a new registration ("TL-bounce"), decided under **W01-0015**.
