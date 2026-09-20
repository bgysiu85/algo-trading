# Warrior 4 — reversal

Assumes `warrior_0_universe_and_risk.md`. **This is the only one of his four
strategies that fades the move rather than following it**, and it is the natural
counterpart to the other three: same names, same session, opposite side of the
same wave.

Source: W-REV (`warriortrading.com/reversal-trading-strategy/`), read 2026-09-09.
**No video on this setup has been transcribed.** It is the thinnest-sourced
document in the set.

> **Update 2026-09-11:** `iS5lvJGMM8E` (his RSI training) has now been
> transcribed in full — see `rsi_strategy_spec.md`. It confirms the 10:29 quote
> in §4 verbatim and adds a stronger statement of the same point, but it **does
> not contain the 10/90 figures**. The RSI thresholds below remain sourced to
> W-REV alone. §4 is revised accordingly.

---

## 1. Why this one is here at all

Three reasons it earns a place despite being single-sourced:

1. **It is the exit side of the move MCL is long.** MCL currently has no concept
   of a move being *over* — only of a position being stopped. His reversal
   triggers are a candidate definition of "over," and they are computable.
2. It uses **RSI at 10 and 90**, not the textbook 30/70. MCL gates on "RSI
   rising." If his extremes are where the move ends, our gate and his trigger are
   measuring the same thing from opposite ends.
3. `TzGQE8d0f18` (Shay) argues dip-buying beats breakout-buying on low-float
   small caps. **Cameron trades both sides and ranks his own setups**, so how he
   decides which applies is the natural cross-check on that disagreement.

**Direction caveat, and it is decisive:** `short_selling_feasibility.md`
answered 2026-09-08 that IBKR refuses opening trades in this universe in **either
direction**. **The short expression of this strategy is not buildable on the
current broker.** What *is* buildable is its use as an **exit and stand-aside
signal for the long strategies**, and that is how the builder should treat it
until the broker question changes.

---

## 2. The pattern

| Element | Rule |
|---|---|
| Universe | Low-float microcap momentum, **parabolic runners preferred** — the same names |
| Setup | **5–10 consecutive 5-minute candles of the same colour** |
| Entry | **The first candle that begins to reverse** |
| Confirmation 1 | **RSI below 10 or above 90** — extreme, not 30/70 |
| Confirmation 2 | **Momentum divergence** — price makes a new high, MACD (or a 3-10 oscillator) does not |
| Confirmation 3 | Volume: strong on advancing bars, **weak on declining bars** |
| Volume baseline | **5-day volume average** |
| **Stop** | **At the high/low, or minus 20 cents** |
| Target | **None stated.** "Trailing stops to keep myself in these winning trades as long as possible" |
| Session | **Not specified** |

**Additional stop guidance, and it is the same idea as Shay's:** avoid placing
the stop at the exact support or resistance point; allow for the volatility
range. Shay's version (`TzGQE8d0f18`) was "10–15c *below* the level, never at
it — if you put your stop right at support you're always going to get stopped
out." Two independent sources, same correction.

---

## 3. The 20-cent stop is now a constant across his whole method

This is the finding worth carrying out of this document.

| Setup | Stop |
|---|---|
| Bull flag / micro pullback | `min(structure, 10–20c)` — Warrior 0 §5.1 |
| MA setup (S5) | low of the last 5-minute candle, **giving 10–20c stops** |
| **Reversal** | **at the high/low, or minus 20 cents** |

Three different strategies, three different structures, **the same 10–20 cent
answer every time**. In the reversal it appears as an explicit *alternative* to
the structure stop rather than as an override of it, which is the clearest
statement of the design he uses: structure when structure is tight enough, a
fixed cent cap when it is not.

> **Every stop in our engines is a percentage.** Warrior 0 §5.1 makes the
> arithmetic case; this document is the third independent confirmation that the
> cent figure is not incidental to one setup.

---

## 4. RSI at 10 and 90 — revised 2026-09-11

Worth isolating because it is unusual and because MCL already carries an RSI
condition.

He is not using RSI as an overbought/oversold oscillator in the textbook sense —
30 and 70 do not appear. He wants **10 and 90**, i.e. genuine tail readings, and
only in combination with a same-colour candle run and a momentum divergence.

### 4a. Sourcing, now that the video has been read

`iS5lvJGMM8E` (27:44) was transcribed in full on 2026-09-11. Two results:

**Confirmed.** The 10:29 quote this section relied on is verbatim: *"it's okay
that the RSI is near the overbought area because it's trending up."* RSI in the
70s is not a signal for him in either direction.

**Strengthened, and beyond what this section claimed.** He goes considerably
further than "the 70s are not a signal":

- [13:32] *"using RSI to help me time entries to the long side for momentum is
  not particularly helpful — I find MACD is more than enough."*
- [26:51] *"RSI doesn't currently make the cut for my momentum trading
  strategy."*
- [21:13] *"MACD is not something that I scan for, but RSI **is** something I
  will scan for."*

So RSI's surviving role for him is **upstream, in scanning and selection**, not
downstream in entry timing. That is consistent with this document's premise —
reversal detection is a different job from entry timing — but it removes any
support for RSI as an *entry* condition anywhere in the Warrior set.

**Not confirmed.** The figures **10 and 90 do not appear anywhere in the video.**
The only numeric RSI values he gives in 27:44 are the length (**14**, platform
default, deliberately untuned) and passing references to the conventional 70/30
band. The 10/90 thresholds therefore remain **single-sourced to the W-REV web
page**, with no video corroboration. The builder should treat them as a
hypothesis to measure, not a number to hard-code.

> **Testable and cheap, and now more clearly worth doing:** on our existing trade
> list, what was RSI doing at the bar MCL exited on? If MCL's exits cluster well
> below 90, his reversal trigger and our trail are not measuring the same event
> and one of them is early. Run the same measurement without assuming 90 — take
> the empirical distribution of RSI at the session high and let it name its own
> threshold, pre-registered before the comparison.

See `rsi_strategy_spec.md` for the full eight-video RSI reading, including the
near-unanimous rejection of naive 70/30 mean reversion and the one novel
pivot-placement rule.

---

## 5. What the builder needs

1. **Do not build the short side.** `short_selling_feasibility.md`.
2. **Build the trigger as a measurement first**: on the existing bar cache, flag
   every bar meeting the same-colour-run + RSI-extreme + divergence conditions,
   and check where those flags fall relative to MCL's own exits and relative to
   the session high. That answers "is this the top?" without a strategy.
3. **Then**, if it holds, offer it to MCL as an exit condition and as a
   re-entry veto.
4. The **5-day volume average** is a different baseline from anything we
   currently compute (we use 10-day for RVOL). Trivial, but state which.
5. **Do not add an RSI entry condition.** §4a: the practitioner this document is
   built from says explicitly that RSI does not earn a place in momentum entry.

## 6. Gaps and warnings

- **The 10/90 thresholds are single-sourced from a web page and are not
  corroborated by his own RSI video** (§4a). This is the largest open gap in the
  document.
- `ORWJzImSTdE` (1:05:05) and `hz7vhSIXXSc` (51:55) are the dip-trading videos
  and would be the place to look for the long-side expression of a reversal.
  Neither is transcribed.
- **No target rule at all** — the trailing stop is the entire profit mechanism.
  Same construction as our `TRAIL_PCT`, which is already settled at 5%.
- **No session window**, which for a strategy about exhaustion is a conspicuous
  omission.
- The page carries the same generic disclaimer statistics as the others (Taiwan
  1992–2006, "9.81% of day trading volume was generated by predictably profitable
  traders") and **no performance data for the strategy itself**.
