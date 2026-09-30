# REGISTERED — W16 DVP-F1: forward paper test of Conti's literal drift-VWAP rule on 1 MNQ

**Committed 2026-09-28, before any session it scores has traded.** It follows DVP-v1 (W16-0012: out-of-sample
2024-01-02 → 2026-09-25, net $76,377 per NQ / $4,861 per MNQ at L2, 5 of 6 criteria, missed the month bootstrap at
90.8%). Ben's decision on W16-0013 (multiple choice): *"B: Paper-trade forward"*.
**Board:** W16-0014. **Chat:** Scalping chat (registration, check-ins, Result doc). Build & test chat (build).

Every historical bar has now been used for this rule, so the only fresh evidence left is data that does not exist
yet. This is the second and last of DVP-v0 §11's further hypotheses. A third needs a reason that does not start from
a result.

---

## In plain terms

Starting with the session of **Tuesday 29 September 2026** (US time), we run Conti's exact rule on each new NQ day,
with the code frozen as it stands in commit 2ff1a15, for **six months, to Friday 26 March 2027** (about 125 sessions,
~390 trades). Each day's result is worked out the same way as the backtest, from the day's 1-minute bars. Where the
paper-trading setup can place the orders, it also places them on a paper account, so we can see what real fills cost
compared with the simulated ones. If it loses money after 150 trades, or falls further than its worst historical
drawdown, it stops early.

## 1. The rule — frozen

`strategy.w16.drift_vwap.generate_dvp_trades(frames, "NQ", dates, p_ref=None, loss_rule="total", trigger_minutes=5)`
at commit **2ff1a15**. Literal 80/40 long and 80/50 short points; 15-min VWAP with C1–C3 at 0.10%; first
opposite-colour 5-min candle; fill at the next 5-min open; fills 10:30–15:30 ET; flat at 15:55; at most 4 trades;
stop after the 2nd losing trade. No parameter, filter or time window changes during the test. A code fix that changes
any trade is a POST-RUN amendment that re-scores the whole period and says why.

## 2. What is scored — the simulated book (primary)

- **Instrument: 1 MNQ** ($2 a point). Costs L2: NinjaTrader Free $0.94 per side plus 1 tick ($0.50) on market and
  stop fills (SB-v0 Amendment A). The per-NQ figure is shown beside it.
- **Data:** Databento GLBX `NQ.v.0` `ohlcv-1m`, pulled at least weekly for the sessions since the last pull. The same
  read-back as G1 is applied to each new batch (daily closes agree with `ohlcv-1d` within 1 tick on ≥ 99% of days).
- **Sessions:** XNYS trading days 2026-09-29 → 2027-03-26 inclusive.

## 3. Paper orders (secondary, reported only)

If the paper stack (W02-style, IBKR paper or NinjaTrader paper; the Build & test chat checks which can route MNQ and
asks Ben) can place the same orders live, it does. Its results are **reported beside** the simulated book: fill
price versus simulated fill per trade, missed or extra trades, and the net difference. Paper fills never replace the
simulated score. If paper orders are not live on day 1, the simulated book still runs from day 1.

## 4. Early stop — checked after every session

- **Stop A:** after ≥ 150 trades, net (L2, 1 MNQ) ≤ $0.
- **Stop B:** drawdown from peak (L2, 1 MNQ) worse than **($3,300)**, about DVP-v1's worst ($3,266.68).

Either stop ends the test. It is reported as FAILED FORWARD, with a Result doc.

## 5. Pass at the end (26 March 2027), all per 1 MNQ at L2

1. Net > $0.
2. Win rate ≥ the break-even win rate implied by the realised average win and loss.
3. Net > $0 at L3 (+2 ticks).
4. Each calendar quarter (Q4 2026 from 29 Sep; Q1 2027 to 26 Mar) net > $0.
5. At least 300 trades. Fewer means NOT READ: extend by up to 2 months, then read.

A pass does **not** mean live trading. It earns a live-size discussion (1 MNQ, NinjaTrader) with its own
registration: risk limits, kill switch, and the quarterly edge-decay check from W11-0035 option F.

## 6. Check-ins

The Scalping chat (Sonnet · Medium) posts on W16-0014 every month (the first business day): trades, win rate, net at
L2 per MNQ, drawdown, and paper-versus-simulated slippage if running. Nothing is changed at a check-in. A stop that
fires between check-ins is reported when it is seen.

## 7. Prediction, written now

Net per MNQ is small but positive, about $300–$900 over the six months. The win rate is 61–64%. At least one of the
two quarters is negative, so it **fails criterion 4**. Stop A does not fire. I'd be glad to be wrong.

## 8. Not to be done

- Pausing, resizing or skipping days by judgement.
- Changing the stop or target, the 0.10% threshold, the times, or the daily limits mid-test.
- Starting the count from a later date because the first weeks went badly.

## Amendment 1 (POST-RUN, 2026-09-30, W15-0033) -- IBKR costs reported beside; scored basis unchanged until Ben decides

Ben's instruction (*"please use the IBKR costs as that will be the broker i'm using"*) arrived after the first forward session (2026-09-29) had been scored at NinjaTrader L2, so a change of scoring basis is POST-RUN. Nothing about the rule, the data or the stop/pass thresholds changes. From the next weekly pull the forward report **prints a second line: the same trades at IBKR** (1 MNQ: $0.62 per side + 0 / 1 / 2 ticks of $0.50 = $1.24 / $2.24 / $3.24 round trip vs NinjaTrader L2 $2.88 round trip). Stop A/B and the section 5 pass are still read on the registered NinjaTrader L2 figures **unless Ben says otherwise** (board: W15-0033). IBKR is cheaper than NinjaTrader Free, so this can only make a pass easier, which is why it is not switched silently. Fees: OTF-G Amendment 2.
