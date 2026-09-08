# Pine scripts

The TradingView side of the three strategies. **These are copies**, not the
live source: TradingView stores the authoritative version and this directory
exists so a drift between Pine and Python is visible in a diff rather than
discovered months later.

That is not hypothetical. On 2026-09-08 the MCL script was found to be four
days stale: it was still running the apex-reversal exit that had been removed
from `strategy/mcl/mcl.py` on 09-05 for being net -$544 over 213 exits, and its
header quoted a headline that two separate corrections had already withdrawn.
Nothing pointed at it because nothing in the repo knew the script existed.

| file | Python it mirrors | TradingView script |
|---|---|---|
| `MCL.pine` | `strategy/mcl/mcl.py` | Momentum Confluence Long |
| `MC5.pine` | `strategy/mc5/mc5.py` | MC5 — Momentum 5m |
| `VW9.pine` | `strategy/vw9/backtest.py` (VW9-5) | VW9 — VWAP + 9 EMA |

## None of these three has a positive edge after measured costs

Recorded here because this file is where someone loading a script will look.
As of 2026-09-08, on the screened universe with tiered commission and the
$4.26/round-trip slippage measured live on 09-03: MCL is negative, VW9 is
negative, and MC5 — described as the survivor for one day — is −$3.15 a trade
on EQUS.MINI and −$8.93 a trade on XNAS.BASIC. The scripts exist to gather
paper results against a live feed, not because the history supports any of
them. `claude/premarket_hypotheses_results_20260908.md` has the numbers.

## What is verified, and what is not

`tests/strategy/vw9/test_pine_port_equivalence.py` transcribes VW9's Pine state
machine back into Python -- from the `.pine` file, not from `vw9.py`, since
transcribing from the target would be circular -- and requires identical
triggers on real cached bars: same bar, same setup kind, same structure low,
same pullback-volume gate inputs. It runs single-session, multi-session (which
is the only thing that tests the session RESET), and across a grid of parameter
settings that reach boundaries the defaults never touch.

Every branch of it was checked by mutating the transcription and confirming the
tests fail. Six mutations, six failures.

NOT verified by anything: order fills, the exit ladder, and Pine's broker
emulator. Those differ from the Python by construction -- gap-through fills,
next-open entry, same-bar target-versus-VWAP priority -- and each `.pine` header
lists its own divergences. Read those before comparing a Strategy Tester figure
to a backtest number. They are not the same measurement.

## Updating

Edit in TradingView, then copy the source back here in the same commit as any
matching Python change. A Pine script that has drifted from its Python is worse
than no Pine script: it looks authoritative and trades something else.
