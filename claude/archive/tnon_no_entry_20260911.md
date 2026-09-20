# Why MCL did not take TNON's 07:35 run — and what it exposes

`python -m common.why_no_entry --symbol TNON --date 2026-09-11 --strategy mcl
--from 07:20 --to 07:55`, run 2026-09-12 on the XNAS.BASIC window slices.
Output `var/reports/why_no_entry_mcl_TNON_2026-09-11.txt`.

## 1. The answer

**At 07:35 the sole blocker was `c_floor`.**

    time    close      volume    blocked by
    07:34    7.28      20,032    c_rsi, c_vol, c_floor
    07:35    7.48     158,245    c_floor
    07:36    7.64     169,761    c_vol
    07:37    7.88     268,105    c_vol
    ...
    07:47    8.37     758,725    c_vol
    07:48    8.20     364,577    c_vol

158,245 against the previous bar's 20,032 is **7.9×**, so `c_vol` (≥3×) passed
easily. MACD, MFI and RSI all held. The only condition that said no was the
volume floor: the *previous* bar's 20,032 was below half the 60-bar average.

It was not the position cap. MCL never signalled on TNON after 07:00 and there
is no cap reject for it; at 07:37–07:40 only two positions were open.

## 2. The mechanism — the two volume conditions hand off

This is the part worth keeping. `c_vol` and `c_floor` read the **same number**
in opposite directions:

    c_vol     this bar's volume  >=  3 x prev_vol        wants prev_vol SMALL
    c_floor   prev_vol           >=  0.5 x trail_avg     wants prev_vol LARGE

Both pass only inside

    0.5 x trail_avg  <=  prev_vol  <=  volume / 3

which is non-empty only when `volume >= 1.5 x trail_avg`, and which narrows as
the trailing average rises through a session.

**On TNON they did not merely narrow — they took turns.** The burst bar (07:35)
had a quiet predecessor, so it cleared the multiple and failed the floor. Every
bar after it had a loud predecessor, so it cleared the floor and failed the
multiple. The entire run from 7.28 to 8.37 — **a 15% move over thirteen
minutes** — was locked out by two conditions one minute apart.

MC5 bought it at 07:41 and sold at 07:47 for **+$90.62**, its best trade of the
day. MC5 has no bar-over-bar volume test.

## 3. Session-wide, `c_vol` is the binding constraint

    325 bars without an entry, 47 of them failing exactly one condition

    condition   SOLE blocker   blocked at all
    c_macd                 0              195
    c_mfi                  1              181
    c_rsi                  0              163
    c_vol                 43              300
    c_floor                3              123

`c_vol` stands alone on **43 of 47** single-condition bars. `c_macd` blocks 195
bars and is never the sole blocker — it is always accompanied, so it costs
nothing on its own.

Note the asymmetry with §1: session-wide the binding constraint is `c_vol`, but
**at the one bar that mattered it was `c_floor`**. Both numbers are needed;
neither alone describes the rule.

## 4. What this is not

- **Not the bars the live trader saw.** It ran on IB's feed; this is XNAS.BASIC
  at 55.2% capture, so every volume here is roughly half the consolidated
  figure. Survivable *for this question* because both conditions are ratios and
  a roughly constant capture cancels in a ratio — an absolute threshold
  diagnosed on this tape would be wrong by about 1.8×. On this tape MCL signals
  at 05:03 / 05:19 / 05:34 / 06:26 / 06:48 against the live 05:05 and 06:41:
  close, not identical.
- **Not proof a trade would have happened.** A bar where four of five conditions
  held is a bar where the rule said no.
- **Not a recommendation to remove `c_floor`.** Every mechanic change measured in
  this project has lost money. This identifies a structural interlock; whether
  relaxing either side earns anything is a separate registered question.

## 5. The measurement this earns

The hand-off is anecdotal until counted. `c_vol` and `c_floor` can be evaluated
over the whole point-in-time universe with no parameters:

1. How often is the joint window **empty** — `volume < 1.5 x trail_avg` — on a
   bar that would otherwise pass every non-volume condition?
2. How often does a bar clear `c_vol` and fail `c_floor` while the **next** bar
   does the reverse? That is the hand-off, and it is the shape that costs a run
   rather than a bar.
3. What is the distribution of `volume / trail_avg` on bars where the other
   three conditions hold?

Only if that says the interlock is common does a variant belong in `pit_delta`
— and it should be registered with its predicted failure first, because the
prior on any mechanic change here is poor.
