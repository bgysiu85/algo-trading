# REGISTERED — H-E2: does LESS confirmation enter earlier, and does earlier pay? (PRE-RUN)

**Committed before `common/entry_sweep.py` exists and before either engine
gained a parameter for the constants below.**

## 1. Why this, and why now

`running_up_preflight_RESULT_20260918.md` measured the thing that kills these
books: **entries taken after a large recent move die immediately.** On MCL the
five-minute move before a trade that dies is +11.43% against +4.90% for one
that survives; the most-extended decile dies 42.3% of the time against a 12.6%
base, and on MC5 70.2% against 37.2%.

The pre-flight also killed the obvious fix. A "Running Up" filter — take the
trade only when the name is climbing — keeps *more* of the dying trades than of
the surviving ones at every threshold, because it selects on the same axis in
the wrong direction. Adding confirmation makes it worse.

**So the question turns inward, to the entry conditions themselves.** MCL
requires all five of:

| clause | what it is |
|---|---|
| `c_macd` | MACD > signal **and MACD > 0** |
| `c_mfi` | MFI rising |
| `c_rsi` | RSI rising |
| `c_vol` | this bar's volume **>= 3x the previous bar's** |
| `c_floor` | previous bar's volume >= half the 60-bar average |

Every one is a confirmation, and two of them are the reason the entry lands on
the spike. `MACD > 0` is the most lagging clause in the set — it cannot be true
until the move is already established. `VOL_MULTIPLE = 3.0` requires the surge
bar itself. **The lateness is not a filter problem; it is the signal.**

MC5 is a different shape — `rsi_roc >= 5.0`, `ema_fast > ema_slow`,
`macd > macd_sig`, no volume clause and no MACD-above-zero. Its one
"how much confirmation" dial is `ENTRY_RSI_ROC_PCT`.

**Neither MCL clause has ever been tested on its own.** `mcl.py` says so in a
comment that predates this registration: V9 dropped `MACD > 0` **and** the 3x
surge at the same time and its expectancy collapsed 81%, so the damage cannot
be attributed to either, and "sweeping this flag with the surge left intact is
the missing single-variable test". This is that test.

## 2. The cells — three families, single variable, counted as three

§4 counts multiplicity by FAMILY. Three families, each sweeping ONE constant
with every other constant at its published value:

| family | constant | values | base |
|---|---|---|---|
| **F1** | `mcl.REQUIRE_MACD_POSITIVE` | True, **False** | True |
| **F2** | `mcl.VOL_MULTIPLE` | 1.5, 2.0, 2.5, **3.0**, 4.0 | 3.0 |
| **F3** | `mc5.ENTRY_RSI_ROC_PCT` | 1.0, 2.5, **5.0**, 7.5, 10.0 | 5.0 |

In F1, `VOL_MULTIPLE` stays 3.0. In F2, `REQUIRE_MACD_POSITIVE` stays True.
That separation is the whole point; V9's failure is what it is for.

Eleven books in one pass over the tape, on `screen_pairs_pit_itch_v2.json` with
XNAS.ITCH bars. `holdout.json` is not touched.

## 3. Most of these ADD trades, which makes the reading cleaner than the B-series

Every entry rule this project has tested for a year REMOVED trades, and §4's
standing warning applies to all of them: on a losing book a rule that abstains
improves the total by construction. **Four of the five swept values in F2 and
F3 go the other way** — a looser threshold takes MORE trades, so a per-trade
improvement cannot be manufactured by abstaining.

The exceptions are `VOL_MULTIPLE = 4.0` and `ENTRY_RSI_ROC_PCT` above its base,
which tighten. **Any cell with fewer trades than its base is scored against
`gate_study.abstention` as well**, and a cell that fails that control is not a
pass however it reads otherwise.

## 4. How it is read — fixed now

Net per trade at **$4.26**, reported at $1.00 / $4.26 / $8.92. Halves at the
median session. Both denominators; a disagreement between per trade and per
symbol-day is a REFUSAL, as everywhere else here.

| verdict | all of |
|---|---|
| **CLEARS** | net per trade > 0 in **both** halves, and total net > 0 after dropping the top 5 trades |
| **IMPROVES** | not CLEARS; beats its base on net per trade **and** on total net, in **both** halves |
| **NOTHING** | anything else |

Both are required because these books lose: a cell that trades less always
raises its per-trade figure, and one whose total also improves has genuinely
kept money the base gave away.

**The boundary check (§4) is scored, not decorative.** If a family's best cell
sits at the edge of its swept range, the optimum is being arbitraged rather
than fitted and the family reads **UNDECIDED — BOUNDARY** regardless of its
numbers. F2's range spans below and above the base; so does F3. F1 is a
two-value family and §4 says a two-value family is all boundary, so **no
boundary check applies to F1** and none will be claimed.

## 5. The mechanism must be read back as a measurement

§4: read the rule back as a measurement. The claim is that looser confirmation
**enters earlier in the move**. That is directly observable, so the report
prints, for every cell, the **median five-minute return at entry** — the same
`running_up.ret_5m` the pre-flight measured.

> **If a looser cell does not lower the median extension at entry, the
> mechanism did not operate**, whatever the P&L says, and the cell may not be
> described as "entering earlier".

Also printed, and nothing may be read without them: trade count per cell
against its base (a test on a parameter is not a test on the data — the count
catches it); the share of entries that die in one bar; and per-symbol-day net.

## 6. Registered prediction

- **F1, MACD > 0 off: NOTHING.** It is the one clause that establishes a trend
  exists at all; removing it should admit a flood of entries into names that
  are not moving. Expect a large trade-count rise and a worse per-trade figure.
  Confidence: moderate.
- **F2, the volume multiple: the most likely of the three to IMPROVE**, at 1.5
  or 2.0, because the 3x surge is what forces the entry onto the spike bar the
  pre-flight identified. Expect median extension at entry to fall as the
  multiple falls. Confidence: low-moderate — and a fall in extension with no
  P&L improvement is the outcome I would bet on second.
- **F3: no prediction.** MC5's RSI rate-of-change has no measured relationship
  to entry extension and I have no mechanism to state in advance.
- **F2 at 4.0 and F3 above base are expected to look good on per trade and bad
  on total**, which is the abstention signature, and §3 is why the control is
  attached to them.

## 7. What this does not decide

Nothing ships. `holdout.json` stays shut. A cell that CLEARS or IMPROVES is a
direction, not an edge, and would need its own holdout registration. Neither
constant changes in the live path from this run: `REQUIRE_MACD_POSITIVE` and
`VOL_MULTIPLE` are read by `signals()`, which the live evaluator calls, so a
change would alter live behaviour and needs the parity test the last four
live/backtest splits earned.

**And this is not the sub-minute question.** Entering earlier *within the move*
and entering earlier *within the bar* are different axes; the second needs data
this project does not own and must be priced before it is bought.
