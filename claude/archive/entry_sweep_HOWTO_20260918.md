# The entry sweep — less confirmation, one constant at a time

2026-09-18, build chat. Bundle **`build-20260918c`** (commits `8f36b2f` the
registration, `b93a138` the code). **Nothing has been run** beyond unit tests.

## What it tests, and why it's this rather than another filter

The pre-flight found that entries taken after a big recent move die
immediately, and that a Running Up filter makes it *worse* — it selects on the
same axis in the wrong direction. So the question turns inward. MCL needs all
five of these at once, and every one is a confirmation:

- MACD above its signal line **and above zero**
- MFI rising
- RSI rising
- this bar's volume **at least 3× the previous bar's**
- the previous bar's volume at least half the 60-bar average

Two of them are why the entry lands on the spike. **MACD above zero** can't be
true until the move is already established. **The 3× volume rule** demands the
surge bar itself. The lateness isn't something a filter can fix — it's the
signal.

And neither has ever been tested on its own. There's a comment in `mcl.py`
saying exactly that: V9 dropped MACD-above-zero **and** the 3× surge at the
same time and its expectancy collapsed 81%, so nobody can say which did it.
This is the missing single-variable test.

MC5 is a different shape — three conditions, no MACD-above-zero and no volume
clause. Its one "how much confirmation" dial is the RSI rate-of-change
threshold, so that's its family.

## The three families

| family | what moves | values | base |
|---|---|---|---|
| **F1** | MCL's MACD-above-zero clause | on, **off** | on |
| **F2** | MCL's volume multiple | 1.5, 2.0, 2.5, **3.0**, 4.0 | 3.0 |
| **F3** | MC5's RSI rate-of-change | 1.0, 2.5, **5.0**, 7.5, 10.0 | 5.0 |

In F1 the volume multiple stays at 3.0. In F2 MACD-above-zero stays on. That
separation is the entire point and there's a test asserting no family moves two
constants.

## Two things that make this cleaner to read than anything before it

**Most of these cells ADD trades.** Every entry rule this project has tested for
a year *removed* trades, and on a losing book abstaining improves the total by
construction — that caveat has hung over H-B1, H-B3, H-B4 and the give-back cap.
A looser threshold takes more trades, so a per-trade improvement here can't be
manufactured by trading less. The two cells that tighten carry the abstention
control anyway, and a cell that fails it isn't a pass however it reads
otherwise.

**The mechanism is checked, not assumed.** The claim is that looser conditions
enter *earlier in the move*. That's directly observable, so every cell prints
the **median five-minute return at entry** — the same number the pre-flight
measured. If a looser cell doesn't lower it, the mechanism didn't operate,
whatever the P&L says, and the report won't let it be called "entering earlier".

The boundary check is **scored, not decorative**: if a family's best cell sits
at the edge of the swept range, it reads UNDECIDED — BOUNDARY regardless of its
numbers, because an optimum on the edge of the box is being arbitraged rather
than fitted. F1 is exempt — a two-value family is all boundary and none is
claimed.

## Run it

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260918c.bundle" main
```

```
python -m pytest tests\ -q
```

A 5-session smoke first:

```
python -m common.entry_sweep --limit 5 --jobs 8 --out var\reports\es_smoke.txt --csv var\reports\es_smoke.csv
```

Then the real run:

```
python -m common.entry_sweep --jobs 8
```

```
copy var\reports\entry_sweep.txt "D:\Trading\Claude outputs\entry_sweep_20260918.txt"
```

**This one is slower than the recent runs** — eleven books over the same 6,411
symbol-days, against four for the scenarios pass. One tape read, eleven engine
runs per symbol-day.

## My registered prediction, on the record

**F1, MACD-above-zero off: NOTHING.** It's the one clause establishing that a
trend exists at all, and removing it should admit a flood of entries into names
that aren't moving. Expect a large jump in trade count and a worse per-trade
figure. Moderate confidence.

**F2, the volume multiple: the most likely of the three to improve**, at 1.5 or
2.0, because the 3× surge is what forces the entry onto the spike bar the
pre-flight identified. Expect the median extension at entry to fall as the
multiple falls. Low-to-moderate confidence — and "extension falls but P&L
doesn't improve" is the outcome I'd bet on second.

**F3: no prediction.** MC5's RSI rate-of-change has no measured relationship to
entry extension and I have no mechanism to state in advance.

## Nothing ships from this

`holdout.json` stays shut. Both MCL constants are read by `signals()`, which the
live evaluator calls, so changing either would alter live behaviour and needs
its own parity test — the last four live/backtest splits earned that. The sweep
passes its values to `backtest_session` only; `evaluate_last_bar` still reads the
constants, and there's a test asserting the sweep parameter never appears in its
signature. This run cannot move the trader.

And this is **not** the sub-minute question. Entering earlier *within the move*
and earlier *within the bar* are different axes.
