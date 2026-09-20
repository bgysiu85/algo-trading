# Simulating the live screen — scope, 2026-09-09

`premarket_hypotheses_results_20260908.md` §4 put this first: *"the only way to
find out whether the +$4.72 is the leak or the screen."* Every P/L figure in
this project is drawn from a universe chosen with the whole day already known,
and the one measurement of what that is worth — survivors +$4.72/trade against
rejects −$9.81/trade — brackets the truth without locating it.

**The good news first: this is smaller than `screener_simulation.md` §7 says,
and two of the three things that document lists as missing are no longer
missing.**

---

## 1. What the live screen actually is

Read off `common/tv_screener.py`, not from memory. Three clauses, a sort, a cap:

```
premarket_change   >= 20%            vs the previous REGULAR-session close
premarket_close    in [2.00, 25.00]  inclusive
premarket_volume   >= 100,000        cumulative since 04:00
sort by premarket_change desc, take the top 40   (tv_feed.MAX_SYMBOLS)
```

That is the whole thing. Two consequences that shrink the job considerably:

- **Float is not a filter.** `FLOAT_RANGE` survives as a display column only —
  Ben's decision earlier today. `screener_simulation.md` §7 opens with "Float.
  MCL's universe rule is `float < 20m` and no Databento tier carries
  fundamentals", and treats it as the blocking gap. **It is no longer a gap at
  all.** That document needs a correction note.
- **RVOL is not a filter either.** `relative_volume_10d_calc` appears in
  `CLAUSE_LABELS` but not in `FILTERS`. `screen.py`'s `stage2` still applies
  `min_rvol = 5.0`, so the simulated screen and the live screen currently
  disagree about their own rules.

Every remaining column is computable from pre-market minute bars plus the prior
regular-session close. **No fundamentals, no vendor-specific derived field.**

## 2. What is missing, precisely

`common/screen.py` splits its rules honestly and tests the split:

| | uses | decidable at 03:59? |
|---|---|---|
| `stage1()` | prior close, trailing 10-day avg dollar volume | **yes** |
| `stage2()` | **today's daily RVOL and today's daily range** | **no — 20:00 data** |

Stage 2 is the leak, and it is the only leak. It was always labelled a *fetch
filter* rather than a trading rule, and `leak_control.py` measured what it is
worth. Replacing it with a screen evaluated **as of a timestamp** is the job.

So the deliverable is one function:

```python
screen_at(bars_before_t, prior_close, t) -> ranked candidates
```

computing `premarket_close` (last print ≤ t), `premarket_volume` (cumulative
04:00 → t) and `premarket_change` (against prior regular close), applying the
three clauses, sorting and capping at 40.

## 3. The data, and the one thing that decides feasibility

We need 1-minute bars from 04:00 to the screen time for **every stage-1
passer** — not just the candidates. You cannot know who the top-40 pre-market
gainers are without looking at everyone who could have been.

| | |
|---|---:|
| stage-1 passers | 3,510,637 symbol-days |
| sessions | 864 (2023-03-28 → 2026-09-04) |
| per session | ~4,063 |
| window needed | 04:00 → screen time |

That sounds enormous and probably is not, because **pre-market is thin**: most
of those symbol-days have a handful of printed minutes or none. The daily pull
for the same universe was 443.8 MB and cost $0.00.

**This is answerable for free before anything is spent.** `get_billable_size`
and `get_cost` are both metadata calls. `common/databento_probe.py` now takes
`--window HH:MM-HH:MM` in ET so the pre-market slice can be priced directly
rather than inferred from a whole-day figure that would overstate it by better
than an order of magnitude. One command settles it (§6).

## 4. The three ways this produces a confident wrong answer

Registered before the run, because each returns a plausible number rather than
an error.

**Tape capture, and it is the serious one.** `premarket_volume >= 100,000` is a
threshold against TradingView's consolidated figure. XNAS.BASIC carries a
median **55%** of the consolidated tape (p10 0.458, p90 0.656) and EQUS.MINI
about **4.8%**. Screening on a partial tape at the consolidated threshold
silently raises the bar: on XNAS.BASIC a name needs ~182k of real pre-market
volume to show 100k. On EQUS.MINI it needs ~2.1M, which would empty the
universe and read as "the screen is too tight."

The choice must be made and written down before the run, not swept after:
either scale the threshold by the measured capture, or hold the threshold and
report how many names it costs. **Scaling is the honest option** and it makes
the capture ratio a load-bearing input — so its p10/p90 spread becomes a
sensitivity to report, not a footnote.

**The screen is a loop, not a moment.** `tv_feed` re-fetches and re-ranks
through the session; the watchlist carries provenance like `UPC # added 05:55,
rank 1`. A simulation that screens once at 04:30 measures a different mechanism
from the one that runs. It should re-screen on a cadence and maintain the
HOT/WARM/COLD tiering `tv_feed` already implements — including *never drop a
symbol with an open position*.

**Look-ahead through the back door.** `stage1`'s guard greps its own source,
which is weak. The stronger form here is behavioural: `screen_at` takes a frame
already truncated at `t`, and a test appends **future** bars and asserts the
output is byte-identical. A function that cannot see the future cannot be
changed by it.

## 5. The decisive comparison

Re-run H0 (buy 04:30, hold — the only hypothesis that passed anything) and MCL
on the simulated live universe, against the two numbers that already bracket
the answer:

| universe | H0 per trade |
|---|---:|
| stage-2 survivors (today's daily bar) | **+$4.72** |
| stage-2 rejects | **−$9.81** |
| **simulated live screen** | **← the measurement** |

Land near +$4.72 and the screen was doing the work. Land near −$9.81 and the
$4.72 was the leak, and with it every P/L figure this project has produced.

The controls are the standing ones: both halves, drop-top-N on level *and*
delta, and the locked holdout in `holdout.json` — which **is** clean for this,
because it was cut on 2026-09-07 over the screened universe and a screen built
now has not been fitted on it. That is the first time the locked set is
actually usable, and it should not be spent on anything else first.

## 6. Order of work

1. **Price the pull.** Free, one command, and it decides everything downstream:

   ```
   python -m common.databento_probe --size XNAS.BASIC:ohlcv-1m EQUS.MINI:ohlcv-1m --window 04:00-04:30 --day 2026-08-04
   ```

   Multiply by 864 sessions. If it is affordable, continue; if not, the
   fallback is to screen a stratified sample of sessions rather than all of
   them, which costs statistical power and must be said out loud.

2. **Confirm the Databento subscription is still live.** `PROGRAM_INDEX` §7
   carries "cancel Databento" as an open item. This pull has to happen before
   that, or it cannot happen at all. **Scheduling constraint, not a technical
   one, and it is the only irreversible thing in this document.**

3. Pull pre-market minute bars for the window, archived the same way
   `databento_universe` archives daily — with the symbology sidecar, because a
   pull with `symbols="ALL_SYMBOLS"` embeds no mapping and `to_df` returns
   `symbol=None` on every row without failing. That produced a structurally
   zero report once already (`screener_simulation.md` §4, run 1).

4. Build `screen_at` with the leak test in §4, and reconcile `screen.py`'s
   `stage2` with the live `FILTERS` — they currently disagree on RVOL.

5. Re-screen on a cadence through the session; feed the resulting universe to
   the existing backtest path.

6. Run §5. Report against both brackets, both halves, drop-top-N.

## 7. What this will not settle

The screen reproduces TradingView's *columns*, not TradingView's *data*. Its
`premarket_volume` comes from whatever consolidation TradingView uses, and ours
will come from one Databento dataset with a measured 55% capture. Even a
perfect reimplementation ranks a slightly different list. The simulation
therefore answers "is the +$4.72 a look-ahead artefact?" — which is the
question blocking everything — and **not** "would this exact watchlist have
appeared on Ben's screen that morning." Those are different questions and only
the first one is worth this much work.
