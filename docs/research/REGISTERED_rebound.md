# REGISTERED — the rebound census: when a position goes under, does it come back?

**H-R1.** Written and committed 2026-09-18 **before any code exists**.

Ben's question, asked on 2026-09-17 and quoted as he put it:

> *"How often does an open position drop below the entry price and rebound to a
> profitable position? I have watched a profitable trade become a loss because
> of the stop trailing rule allowing the position to drop below entry price."*

It has become load-bearing since. H-P1 measured, on 2,904 one-bar trades, that
**94% of MC5's instant deaths and 82% of MCL's are the trailing stop firing**,
filling at a median −5.23% against a stop set at −5%, with under 1% landing more
than half a point below it. They are stop-hits, not gaps and not reversals
running away. Which means the deficit may be a **stop-width** problem rather than
an entry problem — and **nothing in this project measures what the price did
after the stop fired.**

---

## 1. This is a CENSUS, not a rule

Descriptive, in the shape that worked for `running_up_preflight`: no rule, no
threshold, no verdict, no holdout, nothing to tune toward an answer.

**One line is drawn differently from that pre-flight, deliberately.** The
pre-flight barred money entirely because it was a separation pass and a P&L
column would have turned it into a threshold search. Here the question *is* about
price, so **price excursions in percent are the subject matter** — how far under,
how far back, how long. What stays barred is **strategy P&L, book comparisons,
and any verdict vocabulary**: no per-trade dollars, no CLEARS/NOTHING/REFUSED, no
scoring of any rule. A test enforces it, as it does for the pre-flight.

## 2. What is measured

For every trade in both published baselines on
`screen_pairs_pit_itch_v2.json` (MCL 3,908, MC5 6,462), read off the same
XNAS.ITCH bars the engines traded.

### 2.1 Inside the trade — Ben's question as he asked it

- **Did it go under?** Did the low at any bar between entry and exit fall below
  the entry price.
- **How far under** — the maximum adverse excursion, in percent of entry.
- **Did it come back?** After first going under, did it later trade **above
  entry** again before the exit.
- **And back to a profit?** The same, above **entry + the measured friction**
  ($4.26 per 100 shares = $0.0426/share), because a trade that merely touches
  entry again is not one that made money.

Reported as a distribution and as shares of trades, split by whether the trade
ultimately won or lost — descriptively, not as a discriminator.

### 2.2 After the exit — what H-P1 needs

For every trade, from the bar **after** the exit to the end of the session:

- the **highest** price reached, in percent of entry and of the exit;
- the **lowest** price reached, on the same two scales;
- whether the price ever returned to **entry**, and to **entry + friction**;
- how long that took, in bars.

The low matters as much as the high and is the half `mfe_exit` does not measure
(§4). A stop that fires before a further fall **saved** money; one that fires
before a recovery **cost** it, and the census must be able to say which without
being able to say by how much (§3).

### 2.3 The cut this exists for

The same two blocks restricted to the **one-bar trailing-stop exits** — 406 on
MCL and 2,283 on MC5 — reported separately. That is the population H-P1
identified, and it is where the answer changes what gets registered next.

---

## 3. What a census CANNOT do, stated before it runs

**It cannot price a wider stop.** Reading what the price did after a 5% stop
fired is not the same as running a 7% stop, for two reasons that both matter:

1. **A wider trail changes the path, not just the exit.** The trail tracks a
   peak; widening it changes when it arms and where it sits at every subsequent
   bar, so the counterfactual exit is not "the same trade, exited later".
2. **Signal-ordinal, again.** A position held longer consumes bars the strategy
   would otherwise have re-entered on, so the gated book is not the baseline
   book with one exit moved. This project has had a row about that since
   2026-09-17.

So the census bounds the opportunity and **cannot** convert it into dollars. Only
a `TRAIL_PCT` re-run can, and that is a separate registration with its own
readings. **The census's entire job is to decide whether that re-run is worth
registering.**

## 4. What already exists, and why this is not a rebuild

`common/mfe_exit.py` (run 2026-09-11, `pit_three_results_20260911.md` §3)
measures **MFE after exit** — the high left on the table. It found the median
trade exits *below* its entry despite having traded above it, and a median
$0.41/share left behind.

Three reasons it does not answer this:

- **It measures only the high.** There is no low, so it cannot say whether
  holding longer would have recovered or deepened the loss — which is the whole
  question here.
- **It ran on the superseded universe** (`screen_pairs_pit`, XNAS.BASIC, 2,682
  trades) rather than ITCH v2.
- **It ran on an 8% trail**, not the shipped 5%.

The excursion helper is extended in place rather than duplicated, so there is
one implementation of "where did this trade go".

## 5. How it can mislead, and the guards

- **Outcome-dependence is fine here and would not be in a gate.** "Came back" is
  measured after the fact, which is exactly what a census is for. Nothing in this
  document may be turned into an entry or exit condition without its own
  registration, precisely because every feature in it is outcome-dependent.
- **The window is the session.** Both strategies are pre-market only and exit at
  `window_close`, so a recovery after 09:30 is not a recovery they could have
  taken. Excursions stop at the session's last bar.
- **`window_close` exits must leave exactly nothing after them.** There are no
  bars after the session's last one, so any non-zero post-exit excursion on a
  `window_close` trade means the window is wrong. `mfe_exit` used this check and
  it caught nothing; it is kept because a silent window bug would corrupt every
  number in §2.2.
- **A one-bar trade has no "inside the trade" excursion to speak of.** Its MAE is
  the entry bar's own low. Reported, not hidden, and the §2.3 cut is where those
  trades are actually read.

## 6. My prediction, on the record

**Inside the trade (§2.1):** most trades that go under do *not* come back. I
expect the share that returns above entry after first going under to be **under
40%** on both books, because the trail is what ends most trades and it ends them
on the way down. Low-to-moderate confidence — and Ben's observation that he has
watched winners become losers is about a different population (trades that were
*up* first), which §2.1's win/lose split will show separately.

**After the exit (§2.2, and the one that matters):** I expect the one-bar
stop-outs to be **roughly symmetric** — a material share recover to entry within
the session, and a comparable share fall substantially further — with the
recoveries smaller than the further falls. If that is what it shows, a wider stop
trades a certain small loss for an uncertain larger one and the trail is doing
its job. Genuinely uncertain: these are names selected for having just moved 20%
pre-market, and high volatility cuts both ways.

**What would make me wrong, and it is the interesting outcome:** if a clear
majority of the one-bar stop-outs recover past entry within the session, the 5%
trail is harvesting noise on exactly the most volatile names, and a
volatility-scaled trail becomes the best-founded registration this project has
had in weeks.

## 7. Nothing ships

`holdout.json` untouched. No strategy constant is read, written or swept; no
engine parameter changes. The census reads the published books and the tape, and
writes a report and a CSV.

---

## AMENDMENT A — PRE-RUN, 2026-09-18, before `common/rebound.py` has been run

**Added: entries per symbol-day, per book, in the population check.**

Ben asked, reading the two denominators: *"shouldn't MC5 trade less given that
it's on a higher timeframe setup?"* It is a fair question and the answer is not
in any document. MC5 is on **5-minute** bars — 66 in a session against MCL's 330
— and yet takes **6,462** trades to MCL's **3,908**. Either it is finding an
entry on far more symbol-days, or it is re-entering repeatedly within a day, and
those are different things with different implications.

The census already reads every trade with its symbol and its date, so the answer
costs one pass over rows already in memory. The population check therefore also
prints, per book:

- how many of the 6,411 symbol-days carried **at least one** entry;
- **entries per touched symbol-day**, as a mean and as p50 / p90 / max.

**Still no P&L and still no verdict.** These are counts of the population, which
is what a population check is for, and they are printed for both books
separately rather than as a comparison scored one way or the other. The §1 bar on
book comparison stands: nothing here ranks the two, and nothing here may be read
as saying either is better.

Recorded before the run, as every amendment in this project must be.

---

## AMENDMENT B — POST-RUN, 2026-09-18, after the first run and because of it

**The first run measured MC5 on a window shifted by four minutes. §5's boundary
check is what caught it. The numbers below are re-run; the first run's MC5
figures are withdrawn.**

### What happened

Excursions are read off the **1-minute** tape for both books, because that is
the finest record of where the price went. **MC5 acts on 5-minute bars.** A bar
is stamped with its START, so an MC5 trade stamped 09:25 is filled at that
bar's **close**, four one-minute bars later. Measured against the stamp:

- the four minutes belonging to the exit bar were counted as **after the
  exit**, when they happened **before the fill**; and
- the same four minutes at the entry were excluded from **inside the trade**,
  when the position was not yet open during them.

Every MC5 trade in the census was affected, not only the ones at the session
end. MCL is exact — it trades the 1-minute bars directly.

### How it was caught, and it is the only reason it was

§5 required `window_close` exits to leave **exactly nothing** after them, on the
grounds that there are no bars after the session's last one. The first run
reported **679 of 1,159** window-close exits with tape after them — **every one
of them MC5**, 668 of them stamped 09:25 with up to four minutes following. The
check was carried over from `mfe_exit`, where it had caught nothing, and kept on
the stated grounds that *a silent window bug would corrupt every number in
§2.2*. That is precisely what it was.

Nothing else in the report looked wrong. Had the check not been there — or had
it been printed as decoration rather than scored — the MC5 columns would have
been read, quoted, and carried into whatever came next.

### The fix

Both boundaries move to the **last tape bar of the engine's own bar**:
`entry_t` and `exit_t` are offset by `bar_minutes − 1`. A 1-minute engine is
bit-identical to the first run.

### The check added with it, because the constant is a claim

`BAR_MINUTES = {"MCL": 1, "MC5": 5}` asserts something about two other modules,
and if it is ever wrong the offset is wrong and every number shifts by a few
minutes with nothing looking amiss. So it is **scored against the data**: a book
assumed to trade N-minute bars must have **every** entry minute land on an
N-minute boundary, and the report says so per book. A test separately asserts
that `mc5` still carries its resampler and `mcl` still does not.

### What is unchanged

No rule, no threshold, no verdict, no P&L, no holdout. §1's bar stands and its
test still passes. The only change is **which minutes belong to which side of a
trade**, and it makes the measurement match the strategy rather than the tape.
