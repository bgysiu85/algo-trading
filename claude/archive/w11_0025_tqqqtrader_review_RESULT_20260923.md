# W11-0025 · Kinfo/Mallik (TQQQTrader) review — RESULT

2026-09-23 · Research & spec chat · Source: `claude/yt_collation_kinfo_mallik_tqqqtrader_20260923.md`

## In plain terms

The one rule in the video that can be tested is "hold 3x Nasdaq (TQQQ) while price is above its 50-day and 250-day averages, and short it (SQQQ) when below". I tested it on 21 years of QQQ data from your own IB cache (2005–2026), starting from $22,129. The best reading of the rule made **24.1% a year, the same as simply holding TQQQ (24.2%)**. What the rule actually bought was a smaller worst drawdown: 63% instead of 95%. The literal "above both averages" reading did worse than holding plain QQQ, and **adding the SQQQ short side lost money: 5 wins in 59 short trades**. The video's ~80% a year over 42 years does not come from these rules. It comes from 7 strategies kept out of 300–350 tried, on a 3x series that didn't exist before 2010. His real ~40% a year over 2022–2025 is what a TQQQ trend filter made in that bull market, a bit less than just holding TQQQ.

## Verdict — what Ben must decide

- **Nothing to build. W11-0025 closes as Done.** No new item is raised.
- **Discard:** the strategy (it is leveraged Nasdaq exposure plus a drawdown filter, which is beta rather than an edge), the ~80% a year backtest claim, and the SQQQ short side.
- **Keep one note (no item):** his execution pattern (compute a target weight each day, diff it against holdings, place only the delta ~10 minutes before the close) is the right shape for any daily-bar line that goes live (W06 TSMOM, W07 swing). Whoever builds that execution picks it up; it is not a task now.
- **It confirms, and adds nothing to,** what W11-0024 found on SPY and BTC: a long-only trend filter cuts drawdowns and doesn't beat holding. W06 TSMOM already tests trend properly, and it was NOT CARRIED FORWARD.
- **No decision is needed from Ben** unless he wants TQQQ-with-a-250-day-filter as a long-term personal allocation. That is an investing choice, not a trading system, and it carries a 63% historical drawdown on the account.

## Results — $22,129 start, QQQ daily 2005-11-25 → 2026-09-16 (20.8 years)

Gross = before switching costs; net = after 0.05% a side. Fees (0.9% a year) and financing are inside both.

| Variant | Gross P&L | Net P&L | Net a year | Worst drawdown | Trades | Wins / losses |
| --- | --- | --- | --- | --- | --- | --- |
| Hold QQQ (1x) | $350,254 | $350,254 | 14.6% | (53.3%) | 1 | 1 / 0 |
| Hold TQQQ (3x, synthetic) | $1,956,936 | $1,956,936 | 24.2% | (94.9%) | 1 | 1 / 0 |
| **3x when above the 250-day, else cash** * | $2,056,976 | **$1,938,610** | **24.1%** | **(63.4%)** | 59 | 14 / 45 |
| 1x when above the 250-day, else cash * | $202,437 | $189,670 | 11.5% | (26.1%) | 59 | 15 / 44 |
| 3x when above 50 & 250, else cash (literal rule) | $253,155 | $208,914 | 12.0% | (59.3%) | 175 | 39 / 136 |
| 3x long above both / 3x short below both (TQQQ/SQQQ) | ($8,374) | **($11,245)** | **(3.4%)** | (84.7%) | 234 | 44 / 190 |
| Literal rule, filled one day later | — | $173,943 | 11.1% | (60.4%) | 175 | 65 / 110 |
| Long/short, filled one day later | — | ($17,787) | (7.5%) | (93.0%) | 234 | 79 / 155 |

\* Added after the first run, because the collation says he treats the 250-day alone as "binary permission". It is reported whatever it showed.

**The short side:** 59 SQQQ trades, 5 winners, compounded (94.9%). It earned +5.0% in 2008 but lost (51.0%) in 2011, (50.8%) in 2015 and (32.5%) in 2016.

### His live window (Sep 2022 → Sep 2025)

| Variant | Net P&L | A year | Worst drawdown |
| --- | --- | --- | --- |
| Hold QQQ | $19,969 | 24.0% | (22.9%) |
| Hold TQQQ | $52,412 | 50.1% | (58.0%) |
| 3x above 250-day | $44,179 | 44.4% | (43.2%) |
| 3x above 50 & 250 | $34,533 | 37.0% | (35.1%) |
| Long/short TQQQ/SQQQ | $12,087 | 15.7% | (54.1%) |

His reported ~40% a year with two ~30% drawdowns fits a TQQQ trend filter in a bull market. It is below holding TQQQ outright.

### The known weak spot (2014–2016 flat market)

| Variant | Net P&L | Worst drawdown |
| --- | --- | --- |
| Hold TQQQ | $19,318 | (45.2%) |
| 3x above 250-day | $3,979 | (52.7%) |
| Long/short | ($14,027) | (73.4%) |

### Sample trades (long/short variant, most recent)

2026-04-09 → 07-07 TQQQ +50.7% · 2026-07-10 → 07-13 TQQQ (4.9%) · 2026-08-10 → 08-20 TQQQ (5.4%) · 2026-08-28 → 09-01 TQQQ (5.7%) · 2026-09-04 → 09-10 TQQQ (3.9%). The literal 50/250 rule whipsaws around the 50-day, with 175 round trips in 21 years.

## Why the headline number isn't credible

- 80% a year for 42 years turns $22,129 into roughly $1.2 × 10^15. That figure is not a strategy result.
- The 3x series before February 2010 is synthetic, so none of those 42 years were traded.
- 300–350 strategies were tried and 7 kept, and the backtest reported is the combination of the survivors. That is the same selection problem refused at W08 Stage 1 and in W11-0022.
- His 7 strategies aren't published. Only the 50/250 rule and a vague "deceleration" trim are described, and those are what was tested here.

## Method

- Data: `D:\Trading\bar_cache_spy\30min\QQQ` (IB reqHistoricalData TRADES, RTH, split-adjusted, not dividend-adjusted). The daily close is the last 30-minute bar, giving 5,482 days from 2004-12-01 to 2026-09-16 and a test from 2005-11-25 after the 250-day warm-up.
- Signal at close t, position held close t → close t+1 (he trades about 10 minutes before the close), plus a one-day-later fill check.
- Synthetic 3x = 3 × daily return − 0.9% a year fee − 2 × T-bill. Synthetic −3x = −3 × return − fee + T-bill. Cash earns the T-bill. Switching cost is 0.05% of notional a side.
- Calibration: synthetic 3x gives (79.1%) in 2022 and +195.9% in 2023, against real TQQQ's roughly (79%) and +198%.
- Script: `D:\Trading\Claude outputs\w11_0025_tqqq_ma_check.py`. Raw report: `D:\Trading\Claude outputs\w11_0025_tqqq_ma_check_report_20260923.txt`.

## Caveats

- QQQ stands in for NDX. It is price-only, which is about 0.5–0.8% a year short and affects all variants alike.
- 2005 onward misses the 2000–2002 crash, where he claims the SQQQ side made +200%. No free 1985+ NDX series was reachable from here (Yahoo and FRED are blocked by the proxy). The 2008 and 2022 bears are covered, and the long/short variant made +5.0% in 2008 and (22.9%) in 2022.
- T-bill rates are approximate annual averages typed into the script. They move the 3x variants by well under a point a year.
- His "deceleration" trim/add rule is undefined in the video, so it wasn't tested. Nothing described suggests it would turn the result around.

## Next steps (board ids)

- **W11-0025:** Done (this doc).
- No new items.

### Token recommendation (rule 9)

This fitted one Sonnet/Medium session. Future "review a YouTube collation" items: use Sonnet/Low when the answer is a judgement only, and Sonnet/Medium when there is one concrete rule worth a quick data check, as here. Opus isn't needed for either.
