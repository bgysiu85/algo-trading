# MCL-PB v4 result — the structure stop, against a closed lever

`python -m common.pullback_break --jobs 8` (200s) · raw `var/reports/pullback_break_mcl.txt`,
trades `pullback_break_trades.csv` · registration `REGISTERED_pullback_break_v4_20260916.md` ·
bundle `mcl-pb-20260916f` · artifact "The Structure Stop". 551 sessions, 6,170 symbol-days,
**MCL 3,955 = published** (2025-06-09 duplicate-timestamp fix landed).

## Verdict: NOTHING vs MCL. Second reading passes the letter, fails the substance.

| @ $4.26 | trades | per trade | net | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|
| MCL | 3,955 | (10.52) | (41,599) | (10.68) | (10.40) | 22.2% |
| PB4-g3 (primary: hold 3 + structure stop) | 20,821 | (9.90) | (206,058) | (10.30) | (9.62) | 22.0% |
| PB4-g0 (structure stop only) | 17,238 | (11.48) | (197,921) | (11.80) | (11.25) | 20.0% |
| PB3-g3 (v3 control) | 20,132 | (10.08) | (202,858) | (10.53) | (9.76) | 22.8% |

Registered second reading (v4 §2): per trade holds in both halves; stopped trades (21.96)
vs (23.45) → report prints "THE STOP IS A DIRECTION". **But the margin is +0.18/trade —
1/24 of one round trip's friction — and the registration set no minimum margin (a defect
in it).** Paired by symbol-day: 1,087 better / 681 worse, total (3,200), bootstrap 95% CI
[(5,468), (908)], P(better) 0.2%. Under the project's standing rule (under friction ≠
finding): NOTHING.

**Structure-stop exits cost (23.66) — the same as v3's trail exits (23.45).** 2,727 of
20,821 exits; median hold 6 bars. The pullback low sits 3–5% under a close-of-break entry
and price comes through it on a gap. It is the 5% trail under another name. **The stop
lever is closed for the pullback line**, as `stop_lever_closed_20260914.md` closed it for MCL.

Pre-07 "holds" by one cent: (7.20) vs (7.21).

## Where the line stands

v1 (11.07) → v2 (16.11) → v3 (10.06) → v4 (9.90) per trade; MCL (10.52). Four
registrations, four NOTHINGs; entries filtered hard (volume/close/MACD refuse ~110k of
165k breaks) and still lose at MCL's rate; the exit payoff (3-bar take vs 5% stop) is ~1:5.

Untested on this line: a break OUT of a squeeze rather than inside one (Ben's chart, TNON
08:15 vs 08:31). Bollinger width did not separate his good/bad examples; needs a different
definition before registration. Holdout unspent.
