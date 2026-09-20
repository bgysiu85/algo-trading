# Handover to the build chat — H-E3, the widening trail

Paste the block below into the build chat.

---

## Message to the build chat

New registered hypothesis: **H-E3, a trailing stop that widens as the trade
proves itself.** Full registration is `claude/REGISTERED_trail_widen_20260917.md`
in the project — read it before coding; this is the summary.

### Where it came from

Ben proposed the *opposite* first: trail % shrinking as price rises, so the
dollar giveback stays constant. Rejected here on three existing measurements,
which are also the prior for this one:

- The fraction of gain given back **already** shrinks — 105% of the unrealised
  gain at $4.20, 10% at $8.00, 6% at $20. The dollars grow; the proportion falls.
- A fixed-cent stop *is* that rule (15c = 7.50% at $2, 0.75% at $20) and
  `cent_stop_decision.md` found it monotone worse, diverging above $7 — where
  MCL's 5% trail makes all its money (+$5.40/trade at $7–12 vs −$0.63 for 15c).
- A gain-conditioned trail can't touch the losers.
  `entry_excursion_result_20260914`: the losing 70.7% peak at a median $8.46/100sh
  — about 2% above a $4 entry — so the rule never activates on them. All of its
  effect lands on the 29.3% that carry the book.

Ben then asked for the inverse in the same exchange. That is what this registers.

### The rule

```
peak      = running max of high since entry          # monotone by construction
level_pct = peak * (1 - TRAIL_PCT/100)               # the shipped 5% trail
level_gb  = peak - F * (peak - entry_px)             # give back F of the run
stop      = min(level_pct, level_gb)                 # the WIDER of the two
```

Near entry the 5% trail binds; past `entry * F/(F-0.05)` (= $5.00 at F=0.25) the
giveback rule binds. Effective trail at a $4 entry, F=0.25: 5% at $4.20, 8.33% at
$6, 12.50% at $8, 16.67% at $12.

**One new parameter.** `TRAIL_PCT` stays 5.0 and is not swept — sweeping both is a
2-D fit on a book that has rejected 1-D ones. `F = None` must be **bit-identical**
to today. A trade that never trades above entry has `peak − entry ≤ 0`, so
`level_gb ≥ peak` and the 5% trail binds — no branch needed.

### Keyed to PEAK gain, never current gain

Ben asked whether the % should tighten back when price reverses. **No**, and the
reason is mechanical: keying to *current* gain makes the stop chase the price
down. Entry $4, peak $8, 10% trail — as price falls 8.00 → 7.60 → 7.40 → 7.30 the
stop rises 7.200 → 7.240 → 7.260 → 7.270 and the gap closes from 0.800 to 0.030
before firing. A rule written to allow 10% delivers almost none, and it breaks the
invariant that the level never falls back.

Keyed to `peak` it is monotone by construction. **Assert that every bar anyway**
and fail loudly.

The empirical half of the same answer is already in hand:
`profit_floor_RESULT_20260917.md` is "protect gains on the way down" in discrete
form — MCL REFUSED (net −93, bootstrap P = 0.470), MC5 NOTHING (−3,924). Losers
rescued +12,343 against winners cut −10,780 and knock-on −1,656. **A tightening
rule buys back roughly what it sells.** H-E3 is its mirror and should be read
against it: if widening works, those two rows flip sign.

### Cells

| cell | F | status |
|---|---|---|
| **TW-25** | 0.25 | **PRIMARY** |
| TW-20 | 0.20 | boundary |
| TW-33 | 0.33 | boundary |
| control | None | must be bit-identical |

`profit_floor` **off** in every cell — two exit mechanics at once is not a
measurement. Best cell landing on TW-20 or TW-33 **fires the boundary check**;
that is what closed the cent stop.

### Readings

The five at $4.26, then $1.00 and $8.92, on the v1 p50 point-in-time book.
Baseline must reproduce **MCL 3,960 / (8.81)** exactly first. Both denominators
required, and **disagreement is a refusal, not a tie-break**. Drop-top-3 and
drop-top-5 **on the delta**. Cluster bootstrap by symbol. Beats the 95th
percentile of random removal.

**The gate that will decide this one is concentration.** `mcl_rejected_mechanics.md`
§4: confirm-N produced +$8,300 and was rejected because 91% sat in one quartile
and only 80 of 174 symbols improved. **Report symbols-better vs symbols-worse
next to the net, and treat a minority-of-symbols result as a refusal whatever the
total says.**

Decomposition, paired against the control: runners (reached +10%) Δ dollars;
losers Δ dollars (expected negative); median hold bars; re-entry knock-on. **If
the total is positive but `runners` is flat, it is noise wearing a mechanism's
clothes.**

Also report the hold-time distribution and the worst single trade. The trail is
software-managed inside the running process with no broker-side stop outside RTH,
so a longer hold is unpriced operational risk — `mcl_robustness_analysis.md`
flagged exactly this for the wider-trail sweep.

### Implementation

The hook exists — `strategy/mcl/mcl.py` line 345, `stop_level(peak, trail_pct,
trail_cents)`. It needs `entry_px` and `F`, plus threading through
`backtest_session`. Preserve unchanged: the level derives from the peak **as of
the previous bar** (docstring lines 24–29); `gap_fills=True` fill is
`min(level, open) − SLIPPAGE_TICKS × TICK` (pricing gap-throughs at the level
overstated MC5 by $20,394 against a $20,156 headline); and the exit order — trail,
target, `window_close`, `green_hold`, signal exit, time cap.

`trail_cents` is already the constant-dollar form, so **Ben's original (rejected)
proposal is reachable free** with `trail_cents = entry × 0.05`. Report it as an
extra arm if you want it measured rather than argued; do not score it.

**Assert the cell's trade count against the control's before reading any dollar
figure.** The first confirm-N run was gated on `if trail_confirm_bars > 0:` — a
test on a parameter, not on price — which made the `elif last_of_session` below
unreachable. 450 rows instead of 496, the missing P/L absent rather than zero,
every figure wrong and every figure plausible. Trade count catches it; P/L does not.

### Registered prediction

- **MCL: positive on the level, NOTHING on the gates.** Δ +0.50 to +3.00 per
  trade, failing drop-top-N on the delta or the symbol count. Moderate-to-high
  confidence — every trail change on this data has been "five names, and largely
  the same five", with WLDS the largest contributor at every width.
- Decomposition: runners positive, losers negative, hold time up. Runners flat →
  disbelieve the total.
- F = 0.33 expected to beat F = 0.25 on raw net, which **fires the boundary
  check** rather than recommending it.
- **MC5 worse than MCL** — coarser bars gap further through a wider stop, and
  `profit_floor` already found MC5 gapping below the floor on 56% of floor exits.

A NOTHING closes the trail-shape lever for MCL alongside the cent stop, the width
sweep, confirm-N and the profit floor. Write it up as a closing if so.

### Also still queued from this chat

- `claude/mc5_apex_live_split_20260917.md` — MC5's `evaluate_last_bar` never reads
  `USE_APEX_EXIT`; live has run apex ON since 2026-09-10 while every published
  figure is apex OFF. One-line fix plus a test.
- `claude/spy_intraday_spec_20260917.md` — the SPY intraday momentum line.

---

*(End of message to the build chat.)*
