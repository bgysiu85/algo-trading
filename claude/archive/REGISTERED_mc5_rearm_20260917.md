# REGISTERED — H-C1: MC5 re-arms only after its entry signal switches off (PRE-RUN)

Registration: `docs/research/REGISTERED_mc5_rearm.md`, commit `1d521e4` on `main`
(D:\Trading, not pushed). Nothing is built or run yet.

**Rule.** After any exit, MC5 may not re-enter the same symbol that session until a
closed 5-minute bar at or after the exit bar has its entry signal FALSE. The first entry
of the day is unchanged. It is built as `rearm_after_exit` on
`mc5.backtest_session`, and False must be bit-identical. This is the live-deployable
form, not deletion from the finished book.

**Scope.**
- MC5 only, 04:00–09:30, XNAS.ITCH.
- Universe: the published PIT universe at run time (screen_itch v2 if its RESULT is
  committed, else ITCH p50 v1).
- The baseline must reproduce the published MC5 figure, e.g. (8.49)/trade on v1 p50.

**Readings.** The gate_study five at $4.26: Δ per trade ≥ $4.26 AND Δ per symbol-day
> 0; both halves; drop-top-3; cluster bootstrap ≥ 0.95; beats the 95th percentile of
random removal of the same count. All five → PASSES (holdout candidate). Otherwise
NOTHING.

The edge-only variant (enter only on the bar the signal turns on) is reported, not scored.

**Known at registration (counts only, BASIC PIT book).**
- 3,152 of 6,883 MC5 trades (45.8%) are re-entries.
- Only 379 come on the very next bar.
- A further 604 come after 2 bars and 365 after 3.

**Prediction.** Binds on 15–35% of trades; Δ per trade (1.00) to +2.00; NOTHING.
