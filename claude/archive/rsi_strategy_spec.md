# RSI — Source Reading and Strategy Specification

**Created:** 2026-09-11
**Status:** SOURCE READING COMPLETE. NO RULE IN THIS DOCUMENT HAS BEEN MEASURED.
**Scope:** eight YouTube videos supplied by Ben on 2026-09-11, read in full via transcript.
**Governing standards:** `PROGRAM_INDEX.md` §4 (evidence rules). Source videos are hypothesis generators, not evidence.

> **Read this first.** Seven of the eight sources do not trade this project's universe
> ($2–$20, low float, high RVOL, pre-market and first-hour small-cap momentum). They trade
> forex majors, large-cap equities, crypto and index CFDs on 15m–4h charts. The eighth,
> Ross Cameron, *does* trade this universe — and his conclusion in the supplied video is
> that RSI does **not** earn a place in his momentum entry. That asymmetry is the single
> most important fact in this document and it is the reason the recommendation at §8 is
> narrow.

---

## 1. Source inventory

| # | Video ID | Channel | Length | Universe / timeframe | Performance claim | Grade |
|---|---|---|---|---|---|---|
| 1 | `iS5lvJGMM8E` | **Ross Cameron** | 27:44 | US small-cap momentum, 1m/5m — **our universe** | none | **A** — practitioner in our universe, reasons out loud, states his own negative conclusion |
| 2 | `ar-Kdir6wQ0` | The Moving Average | 12:03 | Forex, 15m | 33 trades, 17W/16L (51.5%), 1:2 R:R, PF 2.0 | **C** — only quantified claim in the set; see §5 for why it does not survive |
| 3 | `BoD0I5J_eLU` | Mind Math Money | 47:46 | Mixed equities/crypto, daily & 4h | none | B — long-form, careful, explicitly warns against naive use |
| 4 | `JWcX8YA0G3A` | LuxAlgo | 3:56 | General, higher timeframes | none | B — short but internally consistent |
| 5 | `hbcCykbX14U` | Charles Schwab | 4:21 | Large-cap equities, daily | none | B — institutional educational, conservative |
| 6 | `4a-qbkLXOzI` | MoneyZG | 10:10 | Forex/crypto, 1h–4h | none | C — generic, no stop rule, no R:R |
| 7 | `TQMayZS9o1U` | The Moving Average | 2:47 | Forex, 15m | none | C — teaser-length |
| 8 | `pCmJ8wsAS_w` | **TradingLab** | 6:40 | Mixed | "86%" — **belongs to a different video about a different strategy** | **F** — see §7 |

**Six of eight make no performance claim of any kind.** Three (LuxAlgo, TradingLab, MoneyZG)
specify **no stop-loss rule at all**, and the same three specify **no reward:risk**. Under
PROGRAM_INDEX §4 ("a win rate without a paired reward figure is not a result"), that is not a
deficiency in presentation — it means there is no result to evaluate.

---

## 2. The decisive source: Cameron (`iS5lvJGMM8E`)

Cameron trades our universe. What he says about RSI therefore outranks everything else here.

Direct quotes, timestamped:

- **[13:32]** *"using RSI to help me time entries to the long side for momentum is not particularly helpful — I find MACD is more than enough."*
- **[26:51]** *"RSI doesn't currently make the cut for my momentum trading strategy."*
- **[21:13]** *"MACD is not something that I scan for, but RSI *is* something I will scan for."*
- **[~10:29]** *"it's okay that the RSI is near the overbought area because it's trending up."*

Settings: **RSI length 14, platform defaults, deliberately** — he states he has not tuned it.

### 2.1 What survives from Cameron

RSI's role collapses from "signal" to three narrow jobs:

| Role | Rule shape | Cameron's own confidence |
|---|---|---|
| `rsi_rising` | co-confirmation only — never the trigger | weak; MACD already covers it |
| `bearish_divergence` | veto on a new long / arming condition for a short | stated, unquantified |
| `rsi_rank` | **scanner field** — sort/filter the universe, not gate the entry | this is the only use he actively keeps |

The third is the one that matters. Cameron uses RSI **upstream, in selection**, not downstream
in entry timing. That is a materially different integration point from where MCL currently
uses it, and it is the only RSI idea in all eight videos that comes from someone trading our
universe.

### 2.2 The 10 / 90 thresholds — what this video does and does not say

`warrior_4_reversal.md` records RSI reversal thresholds of **10 / 90**, sourced to the
Warrior Trading web page `warriortrading.com/reversal-trading-strategy/` (W-REV). That
attribution is correct and stands — the figures are not mine to withdraw.

What is now settled is that **this video does not corroborate them**. Having read the full
transcript (it was previously swept but not transcribed), the only numeric RSI values
Cameron gives anywhere in 27:44 are the length (**14**) and passing references to the
conventional 70/30 band. **10 and 90 do not appear.**

So the 10/90 rule remains **single-sourced from one web page, with no video support**, in a
document that already describes itself as the thinnest-sourced in the set. The video *does*
confirm the [~10:29] quote that `warrior_4_reversal.md` §4 relies on, verbatim.

It also adds something §4 of that document could not have known: Cameron's explicit
statement that RSI is not part of his momentum entry at all (§2 above). That is consistent
with — and strengthens — §4's reading that RSI in the 70s is not a signal for him in either
direction. `warrior_4_reversal.md` has been updated accordingly.

---

## 3. Near-unanimous finding: naive 70/30 mean reversion is rejected

Five of eight sources independently reject "buy below 30, sell above 70" as a standalone rule:

- **LuxAlgo** — extremes are an *exit* consideration, never an entry.
- **MoneyZG** — extremes are neither; only trend context matters.
- **Mind Math Money** — an instrument in a strong trend can sit above 70 for weeks; treating
  that as a short signal is how the indicator kills accounts.
- **The Moving Average** (`ar-Kdir6wQ0`) — the whole point of his pivot construction (§4) is
  that the raw threshold cross is unusable.
- **Charles Schwab** — implicitly; frames RSI as confirmation within a trend read.

**TradingLab alone advocates counter-trend entry at the extremes**, and TradingLab is the
weakest source in the set (§7).

Cameron's [~10:29] line is the same point from inside our universe: on a low-float runner,
RSI above 70 is the *normal state of a working trade*, not a reason to be out.

**Implication for us:** an overbought veto on a momentum long is, on the balance of these
sources, more likely to cut winners than to prevent losses. If MCL or the Pine strategy
contains one, it is a candidate for measurement, not a feature to preserve by default.

---

## 4. The one genuinely novel, codeable rule

From `ar-Kdir6wQ0` (The Moving Average). It is a **pivot-placement** filter, not a
threshold cross:

```
# Bearish arming (mirror for bullish with 30)
rsi_pivot_1 > 70          # first RSI swing high sits OUTSIDE the band
rsi_pivot_2 <= 70         # the NEXT RSI swing high sits INSIDE the band
=> bearish condition armed
```

The idea: momentum that reached an extreme and then failed to reach it again on the next
push is decaying. This is a *sequence* condition on two consecutive RSI swing points, which
is structurally different from — and strictly more selective than — a level cross. It is
also close kin to a divergence test, but keyed on the band rather than on price.

It is the only rule in the eight videos that (a) is new relative to what this project has
already documented, (b) can be written down unambiguously enough to code, and (c) is not
already covered by MACD.

**But it is not specified.** See §6.

---

## 5. The single quantified claim, and why it does not survive §4 of PROGRAM_INDEX

`ar-Kdir6wQ0`: **33 trades, 17W / 16L (51.5%), 1:2 R:R, profit factor 2.0.**

Failures against the project's own standards:

| Standard | Status |
|---|---|
| Sample size | **n = 33**, one symbol, one week. "An n=1 measurement is not a constant" — this is barely better. |
| Hand-marked in hindsight | Yes, by his own account. Swing points were identified with the right-hand side of the chart visible. This is the definition of look-ahead. |
| Friction | **Assumed zero.** He says on camera that it is broker-dependent. Our measured friction is **$4.26/round-trip**. |
| Stop realism | 1.5×ATR. On the pair shown, ATR ≈ 1 pip → **a ~1.5-pip stop**. At any retail spread that stop is inside the spread; the 1:2 R:R is arithmetic on a stop that cannot be filled. |
| Drop-top-N | Not possible to apply — trade-level data not published. |
| Temporal holdout | None. |

**Verdict: not evidence.** The PF 2.0 figure should not be quoted anywhere downstream.

---

## 6. What is unspecified — the free parameters

If the §4 rule were built as described, the following are undefined and would each be a
researcher degree of freedom. Under this project's rules, an unspecified parameter that gets
chosen after seeing results is a leak.

1. **Swing/pivot detection.** No source defines it. Fractal-N? ZigZag with what deviation?
   Rolling argmax over what window? This single choice can swing signal count by an order of
   magnitude.
2. **Minimum bar spacing between pivot 1 and pivot 2.** Unspecified. Without a floor, adjacent
   bars qualify; without a ceiling, pivots months apart qualify.
3. **Maximum lookback for pivot 1.** Unspecified.
4. **Whether pivots are RSI pivots, price pivots, or both confirmed.** The video shows RSI
   pivots; the narration sometimes describes price. Ambiguous.
5. **Wick / doji tolerance** on the confirming price bar. Unspecified.
6. **Timeframe.** Demonstrated on 15m forex. Nothing in the source justifies transferring it
   to 1m US small-caps.
7. **RSI length.** 14 everywhere except TradingLab's unexplained 13.
8. **Entry trigger after arming.** "Armed" is not "in". No entry rule is given — next bar
   close? break of the pivot bar? limit at the band? Unspecified.
9. **Stop and target.** Only `ar-Kdir6wQ0` gives any (1.5×ATR / 1:2). The other seven give none.

**Nine free parameters and one unusable performance figure.** Any grid over these needs a
boundary check (§4) and a pre-registered parameter set.

---

## 7. TradingLab — explicit warning

`pCmJ8wsAS_w`, titled as a strategy "That Actually Works", is supported by:

- no backtest
- no sample size
- no trade list
- no reward:risk
- one number — **86%** — which on inspection belongs to a **different video about a different
  strategy**, and is quoted there without a paired R figure.

TradingLab is already flagged as unreliable in `source_videos_20260907.md`. This video is
consistent with that flag. It is also the **only** source advocating counter-trend entry at
RSI extremes (§3) and the only one using length 13 rather than 14, in both cases without
explanation. **Do not build from it.** It is listed here so that a future reader who
re-encounters the video knows it has already been assessed and rejected.

---

## 8. Recommendation

Ordered by expected value, applying the asymmetry stated at the top.

### 8.1 Do not build a new RSI strategy for the momentum universe

The one source who trades our universe tested RSI in it and dropped it, in favour of MACD,
which MCL already has (`REQUIRE_MACD_POSITIVE = True`). Building an RSI momentum entry would
be building against the only relevant practitioner evidence we have. **Nothing in the other
seven videos is about our universe.**

### 8.2 Two cheap measurements worth running (in this order)

**Measurement A — RSI as a selection field, not an entry gate.**
Cameron's one retained use (§2.1). Compute `rsi_rank` across the candidate universe at the
arming bar and test whether ranking or filtering on it improves MCL's selection. This is the
highest-value test in the document because it is (a) the only idea from a same-universe
practitioner and (b) at a point in the pipeline MCL does not currently use.
Requirements: register before running; paired-by-symbol bootstrap; drop-top-N on both level
and delta; temporal holdout; leak cut on both rate and quality.

**Measurement B — does MCL's existing RSI gate pay for itself?**
Ablation, not addition. §3 gives a concrete reason to suspect an overbought veto costs more
in cut winners than it saves. Run MCL with the RSI condition removed and compare. Same
standards as A. This is a one-line change and a re-run; it is the cheapest test here.

### 8.3 The pivot-placement rule — park it

§4 is interesting and genuinely new. It is also nine free parameters deep (§6) with a
non-result attached (§5), demonstrated on 15m forex. It does not justify build time ahead of
A and B. If it is ever built, it should be for the **Pine RSI/MFI mean-reversion strategy**
(where it is at least in the right family of ideas), not for MCL, and with the nine
parameters pre-registered before any run.

---

## 9. Bearing on existing work

| Existing item | Effect of this reading |
|---|---|
| **MCL** | No new entry rule. Two ablation/selection tests proposed (§8.2). MACD already covers what Cameron says RSI would add. |
| **Pine RSI/MFI mean-reversion strategy** (ATR stops, optional 200 EMA trend filter) | §3 is a direct challenge to its premise if it enters on raw 70/30. The 200 EMA trend filter is the right instinct and is what four of the eight sources are gesturing at. §4 is the only candidate refinement, and only under §6's pre-registration. |
| **`warrior_4_reversal.md`** | **RSI 10/90 thresholds are unsourced.** Correct or remove. |
| **`source_videos_20260907.md`** | TradingLab's unreliable flag is confirmed by a second video. |
| **`warrior_1_micro_pullback.md`** | Unaffected. Cameron's entry remains MACD + price structure. |

---

## 10. Open question for Ben

**Which system is this document for?** The three candidates change the answer materially:

1. **MCL / pre-market momentum** — then §8.1 stands: don't build, run the two measurements.
2. **The Pine RSI/MFI mean-reversion strategy** — then §4 and §6 are the live content, and
   §3 is a challenge to the existing entry.
3. **A standalone new strategy** — then the honest answer is that these eight videos do not
   contain enough specified, evidenced material to found one. §6 lists what is missing.

This document assumes (1) unless told otherwise, because that is the project's active system.

---

## 11. Provenance

Eight video transcripts read in full on 2026-09-11 by four parallel extraction workers, all
returning complete results. Quotes in §2 are verbatim from the transcript with original
timestamps. No claim in this document rests on a video title, thumbnail, or description.
No rule in this document has been backtested by anyone in this project.
