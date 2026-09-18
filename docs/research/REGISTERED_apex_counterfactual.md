# REGISTERED — what MC5's apex exit cost on 2026-09-17 (PRE-RUN)

Written and committed **before the run**, on a session whose live outcome is
already known — which is exactly why it is registered rather than just computed.

## 1. The question, and why arithmetic does not answer it

MC5 lost **(85.21)** live on 2026-09-17. Ten of its exits were
`gradient_reversal` — the apex exit, which `USE_APEX_EXIT = False` turns off in
the backtest and which the live path was not gating until `0c50036`
(`live_defects_FIXED_20260917.md` §D). Those ten exits booked **(150.74)**.

Subtracting gives **+65.53**, and that subtraction is wrong for two reasons:

1. **Removing an exit does not remove a trade.** With apex off the position
   stays open and leaves later on the 5% trailing stop or the 09:30 window
   close, at some other price. Nine of the ten were already 2–4% underwater
   when apex fired, which is close to the trail — so the later exit could
   easily be *worse*. §5: a looser exit rule can only remove exits, and what
   the position does afterwards is a measurement, not a subtraction.
2. **The ten trades are not independent.** MEDS appears five times. Those are
   sequential re-entries on one name, and MC5 holds one position per symbol —
   so if the 04:31 exit never happens, the 05:31 entry never happens either.
   Deleting ten rows from a finished book is a different object from running
   the rule without them (§4, *signal-ordinal is not book-ordinal*).

## 2. The design — two arms, one variable

**MC5 through `pit_strategy`, twice, identical in every respect but
`use_apex`.** Same universe file, same tape, same dates, same entry rule, same
fill model, same friction. The delta between the two arms is the apex exit's
contribution and nothing else (§4, *hold the confound fixed*; *one variable at
a time*).

Both arms are backtests. **The live book is reported beside them and never
subtracted from them** — it differs by execution, by latency, and by the three
other defects fixed in the same commit, so a backtest-minus-live figure would
mix four causes.

`pit_strategy` gains one flag, `--use-apex {on,off}`, injected into the kwargs
it already forwards to `backtest_session`. Default unchanged (the constant).

## 3. Universe and tape, and the one deviation

XNAS.ITCH is the tape of record. **Its extension universe
(`screen_pairs_pit_itch_ext.json`) stops at 2026-09-16**; the BASIC one
(`screen_pairs_pit_ext2.json`, 67 symbol-days) reaches 09-17.

So, registered: **09-17 runs on XNAS.BASIC**, universe and bars. September 2026
is after the 2026-03-30 TRF change, so BASIC's 08:00 late-print defect does not
touch these sessions (§3, and `screen_validate_itch_RESULT_20260917.md`).

**The overlap is the check on that deviation.** 09-08..09-16 exists on both
tapes and is run on both. If the two tapes' deltas agree there, the BASIC-only
09-17 reading stands; if they disagree materially, 09-17 is reported as
**tape-dependent** and the ITCH screen for it is run before anything is
concluded.

## 4. What gets reported, and the readings fixed now

1. Net per session and over the window, both arms, both tapes where available.
2. **Delta = apex-OFF − apex-ON**, per session and over the window.
3. For 09-17 specifically: whether the delta exceeds the live **(85.21)** — i.e.
   whether the day would have been green.
4. Trade counts for both arms beside the live count, so a simulation that does
   not resemble the session is visible rather than assumed away.

## 5. The controls, and what makes this NOT a reading

- **If the two arms produce identical trade lists, the run measured nothing.**
  It must say so rather than print a 0.00 delta as a result — §4's recurring
  shape, *a variant that equals its base rendering as NOT MATERIAL*. The
  report states how many trades differ between the arms before it states any
  delta.
- **ONE SESSION IS NOT A READING, and this is registered before the number
  exists.** §4: the sample is sessions, not trades; an n=1 measurement is not a
  constant. The general question is already answered on the full sample — apex
  removal is worth **+$1,702** at a 5% trail — and nothing 09-17 produces
  changes that, in either direction. This measures **one day**, because one day
  is what was asked about.
- The window figure (09-08..09-17, ~8 sessions) is reported for context and is
  also not a reading: A3 measured the same period and found the fixes explained
  none of the live loss.

## 6. Registered prediction

**The delta on 09-17 is positive but smaller than +150.74**, because the
positions continue into a trailing stop rather than vanishing, and most were
already near it. **Whether it exceeds +85.21 — i.e. whether the day flips
green — is genuinely uncertain, and that is the question.** Low confidence,
deliberately.

Over 09-08..09-17 the delta is expected positive, consistent with the +$1,702
full-sample figure, and small in absolute terms on eight sessions.

**Nothing here can promote MC5.** It is CLOSED as a candidate at (8.57)/trade
over 6,462 point-in-time trades. This measures what one defect cost on one day.
