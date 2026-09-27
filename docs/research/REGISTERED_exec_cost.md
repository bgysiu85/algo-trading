# REGISTERED — Execution-cost modelling (W03-0005)

**Registered 2026-09-27 by the Build & test chat, committed before either runner existed.**
Board: W03-0005. Source: archived PROGRAM_INDEX §7 items 21–22
(`claude/archive/PROGRAM_INDEX_full_20260919.md`), `claude/archive/stop_fill_20260911.md`,
`claude/archive/execution_cost_measured.md`.

This is a **measurement, not a rule test.** Nothing here can pass or fail a strategy. Both books
lose before costs (PROGRAM_INDEX §1), so no cost model can turn either one positive, and this
registration does not claim otherwise. It fixes the definitions, the sample, the controls and the
decision words in advance. That way the cost figure a later study quotes as "honest" is chosen
by a rule, not by looking at the numbers first.

Two parts. They share nothing but the item number.

- **Part A**: what each leg of an MCL/MC5 trade costs on the live paper account, and the
  backtest books re-priced leg by leg instead of with a flat per-round-trip charge.
  Runner: `common/exec_cost_legs.py`.
- **Part B**: Ben's real IBKR executions broken into commission, spread paid, the price
  move in the first minute after each fill, and the rest of the hold.
  Runner: `common/fill_markout.py`.

---

## Part A — per-leg execution cost

### A.1 Why

Every P&L here is quoted at $1.00 / $4.26 / $8.92 per 100-share round trip. That is **one
blended number**, charged on top of the engine's own modelled fills (1 tick each way, gap-through
on stops, commission per order). The legs cost very different amounts. On 2026-09-11
(n = 51 / 21 / 7) the median entry was +$0.0007/share (favourable), the trailing stop
−$0.0225 and `window_close` −$0.0700. `window_close` is on the trades that ran, the ones
worth most, and it has never been priced on its own. The ledger now holds roughly 300 live
round trips, up from 21 stops.

### A.2 The live sample (fixed now)

- Files: `var/fills/mcl_fills_YYYYMMDD*.csv`, sessions **2026-09-09 → 2026-09-25 inclusive**.
  2026-09-09 is the first session with `ref_kind` on every row, and 2026-09-25 is the last
  session before this registration. Sessions after it are **not** in this sample.
- Rows: `status` in {FILLED, PARTIAL_FILL}, `strategy` in {mcl, mc5} (blank = mcl, the only
  strategy before multi-strategy), `filled_qty > 0`, `fill_price > 0`, `ref_close > 0`.
- The three legs, by `(action, reason, ref_kind)`:

  | Leg | Rows | Reference | Cost per share (positive = worse) |
  |---|---|---|---|
  | **ENTRY** | BUY, `ref_kind = signal_close` | the signal bar's close | fill − ref |
  | **TRAIL** | SELL, `reason = trailing_stop`, `ref_kind = trail_level` | the stop level | ref − fill |
  | **WCLOSE** | SELL, `reason = window_close`, `ref_kind = quote` | the quote at the exit | ref − fill |
  | OTHER | any other filled SELL (gradient_reversal, give-back, reconciled …) | as logged | reported only, never used |

  Rows with `ref_kind` in {late_fill, ib_position, ib_execution} are excluded: no decision
  price stands behind them.
- Unit: **basis points of the reference** (cost ÷ ref × 10,000). This is what carries across to
  the backtest, whose price mix is not the live one. $/share and $ per 100-share leg are
  printed beside it.
- Statistic: the **mean**, because a book pays the mean ("you pay the mean, not the median",
  stop_fill_20260911). Median, p10 and worst are reported beside it, and so are the means
  after dropping the worst 1 and worst 3 fills. Those are reported only.
- Uncertainty: a **session-cluster bootstrap**, 2,000 draws, seed 20260927, 95% interval.
- **Pooled across MCL and MC5** is primary for every leg. Both strategies run the same software
  stop and the same marketable-limit code. Per-strategy figures are reported, and a second
  re-pricing uses them (sensitivity only).
- ENTRY is also split, reported only, into the part paid to the spread (fill vs the mid at
  order, from the row's own bid/ask) and the drift between the signal close and the mid at
  order.
- **Minimum sample:** a leg with fewer than 15 pooled fills is **not separately measurable**.
  If that is WCLOSE, the book prices window_close at TRAIL's mean, and the report says so at
  the top. ENTRY and TRAIL are expected to be far above 15. If either is not, the run stops.

### A.3 The backtest books

`screen_pairs_pit_itch_v2.json` on XNAS.ITCH, MCL and MC5 at their published configurations
(`common.pit_strategy.engine`), `not_before` = first_seen (offset 0), QTY = 100. These are the
books of record.

The runner runs each book **twice**: once as published (`gap_fills=True`) and once with
`gap_fills=False`. The only difference is the trailing-stop fill, which is
`min(level, open) − 1 tick` as published and `level − 1 tick` otherwise. So the second run gives
**each trailing exit's stop level exactly** (its exit + 1 tick), taken from the engine's own
arithmetic, with nothing reconstructed.

### A.4 The re-pricing

Each trade keeps its bars, times and commission. Only its prices change.

- **R1 (primary):** entry = signal close × (1 + E_ENTRY/10⁴), where signal close = engine
  entry − 1 tick. Trailing exit = level × (1 − E_TRAIL/10⁴). window_close exit = bar close
  × (1 − E_WCLOSE/10⁴), where bar close = engine exit + 1 tick. Every other exit keeps its
  engine price, and the count is printed. **No flat charge on top:** the legs replace both the
  engine's ticks and the flat friction.

  The trailing exit is priced from the **level**, not added on top of the engine's gap-through
  fill. The live figure is fill-vs-level at tick resolution, so it already contains whatever
  gaps the market produced. Adding it to an engine price that has already charged a bar-level
  gap would count the gap twice. On MC5's 5-minute bars that double count would be large: 48%
  of MC5 stop exits open below the level.
- **R2 (conservative bound):** as R1, except that each trailing exit takes the **worse** of the
  engine's own price and R1's. This is an upper bound on cost, not a central estimate.
- **R0 (control):** E_ENTRY = +1 tick, E_WCLOSE = +1 tick, trailing = the engine's own price.
  It must reproduce the engine's net to the cent.
- **Flat-equivalent (FE):** the flat per-round-trip charge that, added on top of the engine's
  net, gives the same total as the re-priced book: FE = (Σ engine net − Σ re-priced net) ÷
  trades. It is directly comparable to $1.00 / $4.26 / $8.92. Its 95% interval comes from the
  same session bootstrap: each draw recomputes the three pooled means and re-prices the book.

### A.5 Controls — any failure stops the run and prints why

1. **C1 baseline:** the published books reproduce exactly. MCL **3,908 trades, (35,063.12)** at
   $4.26. MC5 **6,462 trades, (55,364.07)** at $4.26.
2. **C2 pairing:** the `gap_fills=False` books have the identical trade key list (symbol, date,
   ordinal, entry time, exit time, reason) as the published ones. On every trailing exit the
   published price is ≤ the gap-off price + $0.000001. The share of trailing exits where the
   two are equal (no gap) is printed.
3. **C3 ledger sign:** the cost computed from fill and reference equals −`slippage_vs_ref` within
   $0.001 on at least 99% of the rows used. The mismatches are listed.
4. **C4 null:** R0 equals the engine's net to the cent on both books.

### A.6 What is reported

In dollars and trades throughout, negatives in brackets:

1. The per-leg table: n, sessions, mean, median, p10, worst (bps, $/share, $ per 100-share
   leg), bootstrap interval, drop-worst-1/3; pooled, MCL, MC5, first and second half of the
   sessions (split at the middle session).
2. Per book: trades, gross, costs, net, per trade, wins/losses under engine + $1.00 / $4.26 /
   $8.92, R1, R2 and R1-per-strategy. Also FE with its interval, the exit mix, and the cost
   attributed to each leg (entries, trailing exits, window_close exits, other).
3. The window_close trades on their own: count, engine net at $8.92, R1 net, and a sample of
   real trades.
4. Stability, reported: the TRAIL mean by half. If the halves differ by more than 2×, the leg is
   flagged **UNSTABLE** in the report header.

### A.7 Decision words, fixed now

**Per book (MCL, MC5), on FE under R1:**

- the 95% interval contains $8.92 → **"$8.92 STANDS"**
- the interval is entirely above $8.92 → **"$8.92 UNDERSTATES"**
- the interval is entirely below $8.92 → **"$8.92 OVERSTATES"**. The report also says whether
  the interval clears $4.26.

If MCL and MC5 get different words, both are reported and there is no single word.

**window_close against the trailing stop, on the pooled leg means (bps):**

- WCLOSE's interval is entirely above TRAIL's mean → **"window_close is the dearer exit"**
- WCLOSE's interval is entirely below TRAIL's mean → **"window_close is the cheaper exit"**
- otherwise → **"no measurable difference"**
- if WCLOSE is not separately measurable (A.2) → **"not measurable"**

**What follows from the words.** If both books say UNDERSTATES, or both say OVERSTATES, the
Result recommends that future studies quote R1 per-leg pricing as the honest level in place of
$8.92. **Ben decides.** STANDS changes nothing. No strategy verdict changes under any word.

### A.8 Caveats that travel with every number

These are **IBKR paper fills**. The simulator's dispersion is real, but whether it is kinder or
harsher than real capital is unmeasurable without real capital. The live stop and exit code
changed during the sample: exit re-pricing and the drift guard were promoted mid-sample, and
that is what the halves reading is for. The live universe is the live watchlist, not
`screen_pairs_pit_itch_v2.json`, which is why the measurement is in bps and not in cents.

---

## Part B — Ben's real fills: spread versus the move after the fill

### B.1 Why

`execution_cost_measured.md` (2026-09-06) priced every one of Ben's executions against the quote
at the time. The cross vs mid is 17.3 bps, and the half-spread is 40–41 bps on XNAS.BASIC. That
is the **effective spread**. What it did not measure is what happened **after** each fill: did
the price keep going his way, or turn against him within the minute (being picked off, or late)?
That is the other half of the decomposition item 22 asked for. Together they turn "real trading
lost $114,983" into named, additive dollar pieces.

### B.2 Population (fixed now)

- Every execution in the Flex exports under `var/flex/*.csv` (de-duplicated on TradeID, stocks
  only, `common.flex`), with a resolved time (`flex.measure_offsets`).
- Grouped into positions with `flex.round_trips` (flat to flat within a symbol-day). Positions
  flagged `open_at_end` are excluded from the identity and counted.
- **C1:** the run prints its execution and position counts against the published **18,621
  executions / 1,658 positions**. A mismatch is printed at the top of the report with the
  counts. It does not stop the run, because Ben may have exported a longer history since. The
  published figures are the ones this registration refers to.

### B.3 Quotes

XNAS.BASIC `tcbbo` from the Databento archive (`<archive>/XNAS.BASIC/tcbbo/<date>.dbn.zst`),
already on disk, $0. This is the tape `execution_cost_measured.md` chose over EQUS.MINI, on
three grounds.

- m_t = the mid of the last record at or before the fill's timestamp, and only if that record
  is at most 60 s old. Otherwise the fill is unpriced. This is `friction_quotes.match`,
  reused unchanged.
- m_{t+Δ} = the mid of the last record at or before t + Δ. It always exists once m_t does,
  because at worst it is the same record. The share of fills where it is the same record
  (nothing printed in the window) is reported.
- **Primary Δ = 60 s.** Δ = 5 s and 300 s are reported only, so there is no choosing a
  horizon after the fact.

### B.4 The identity, per position

For each execution, let d = +1 for a buy and −1 for a sell, and let q be the shares and p the
price. A fill is an **entry** if it grows the absolute position and an **exit** if it shrinks
it. That covers shorts as well as longs.

```
gross        G  = −Σ d·p·q                  (what the fills made, before commission)
spread paid  S  =  Σ d·(p − m_t)·q          (positive = paid; split entries / exits)
mid P&L      M  = −Σ d·m_t·q                (so G = M − S exactly)
first-Δ move D_in  = Σ_entries d·(m_{t+Δ} − m_t)·q   (positive = went his way after he got in)
             D_out = Σ_exits   d·(m_{t+Δ} − m_t)·q   (positive = went his way after he got out)
rest of hold R  = M − D_in − D_out
commission   C  = −Σ IBCommission            (positive = paid)
net          N  = D_in + D_out + R − S − C
```

A position enters the identity only if **every** one of its fills is priced. The coverage of
positions and of gross dollars is printed.

**C2:** Σ (M − S) equals Σ G to the cent. The difference between Σ G and IBKR's own
`FifoPnlRealized` sum over the same positions is printed as a reconciliation. It is not a stop.

### B.5 What is reported

- The identity in **dollars**, summed over the included positions, at Δ = 60 s. Also per
  position, and per 100 shares of peak position.
- The same at Δ = 5 s and 300 s.
- Split by session block (PRE / RTH / POST, by entry time), by winners vs losers (net), and by
  inside vs outside the $2–20 band.
- The spread paid, re-stated in bps against the 2026-09-06 figure, as a check that this run
  reproduces it.

### B.6 Decision words, fixed now

**First-minute move after buying**: the mean of D_in at Δ = 60 s per 100 shares, with a
symbol-day-cluster bootstrap (2,000 draws, seed 20260927, 95%):

- interval entirely below 0 → **"PICKED OFF"**: the price reliably moves against him in the
  minute after he gets in
- interval entirely above 0 → **"MOMENTUM ON HIS SIDE"**: it reliably keeps going his way
- otherwise → **"NO RELIABLE FIRST-MINUTE MOVE"**

**Where the money went**: the component with the largest dollar drag among C, S, and D_in,
D_out and R where negative, named as the main source. The others are ranked beside it.

Nothing here is a trading rule. A pattern seen in this decomposition earns its own
registration.

### B.7 Caveats

These are discretionary hotkey orders at moments he chose. They bound what is achievable on
this universe at these hours, and they do not measure MCL's marketable limits. XNAS.BASIC's BBO
is not the NBBO. Flex stamps to the second, so a fill inside a second is matched to the quote
at the start of that second. tcbbo carries a quote only where a trade printed, so on a quiet
minute m_{t+Δ} can equal m_t. That is reported, never imputed.

---

## Order of work

1. This registration, committed on its own.
2. Both runners, with unit tests pinning the sign conventions, the identity (B.4), the pairing
   and null controls (A.5) and the re-pricing arithmetic, all on synthetic data.
3. Ben runs both locally. Heavy runs stay on his PC.
4. A read-out chat writes the Result doc against this registration only.
