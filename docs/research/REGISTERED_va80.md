# REGISTERED — VA80 v1: Dalton's "80% rule" on ES 1-minute (open outside yesterday's value area, two half-hours accepted back inside → trade to the far edge)

**Written before any volume profile or value area has been computed on any bar, and before any code for it exists.**
`PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0025** (sub 1 = this file; sub 2 = Ben reviews + commits; sub 3 = build + free gates; sub 4 = count-only
pre-flight; sub 5 = training run + Result doc). Companion: `REGISTERED_otf_gate.md` (the one-time-framing gate).
Source: `claude/raw/w11_0034_iqcapital_extracts_20260928.txt` batch 6, video 1 (Imre, IQ Capital, SQZjXXNSlcU),
rules 8–10, after Jim Dalton; shortlist #7 of `claude/w11_0034_iqcapital_review_RESULT_20260928.md`.

**Ben's decision, 2026-09-30, his multiple-choice pick:** *"Yes, register it now (Recommended)"* — a stand-alone ES
study with its own pass bar and holdout, NQ reported. Costs: IBKR (W15-0033), all-in fee + 0 / 1 / 2 ticks.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is a new
hypothesis (§9).

---

## In plain terms

Yesterday's "value area" is the price band where 70% of yesterday's volume traded. The 80% rule says: if today opens
outside that band, and then price gets back inside it and stays there for two half-hours in a row, it will travel all
the way to the other side of the band about 80% of the time. So you trade toward the far edge.

We test it two ways on ES from 2010 to 2023: first **how often the far edge is actually reached** (the 80% claim),
then **whether trading it makes money after IBKR costs** and beats entering the same days at random times.

---

## 0. Where this sits

- **The claim.** Imre, rule 9: once price reclaims the value area low (in a range) there is an ~80% probability of a
  full rotation to the value area high, and vice versa — "Jim Dalton's long-standing technical study", "strongest /
  most tested on ES", "very slightly different based on the market". Target = the far edge (rule 10); point of
  control as an optional partial, which he does not use. No stop given (rule 19). No sample, win rate or drawdown.
- **Dalton's own wording** (*Mind Over Markets*): the market opens outside the prior value area, then trades back
  into it for two consecutive half-hour (TPO) periods → high probability of filling the value area. The primary rule
  uses Dalton's two-period version; Imre's looser "reclaim" is a reported variant.
- **Data we own.** ES.v.0 / NQ.v.0 `ohlcv-1m`, 2010-06 onward (W16 archive, `REGISTERED_w16_session_baselines.md`
  §2). A value area needs volume at each price; 1-minute bars give volume per minute and a high-low range, so the
  profile here is an **approximation** (§2.1). That is a known departure, not a choice made on a result.
- **Nothing has been seen.** No profile, value area, setup count or outcome has been computed by anyone.

---

## 1. The hypothesis, in one sentence

**On ES regular-hours sessions that open outside the prior session's 70% value area, entering toward the far edge
once two consecutive 30-minute periods have closed back inside that value area — target the far edge, stop just past
the day's extreme outside it, flat at the close — makes money after IBKR costs on 1 MES, and beats the 95th
percentile of entering the same sessions in the same direction at a random time with the same target and stop rule.**

---

## 2. The rules

**Every number is fixed here, before any profile is built. None is tuned.**

### 2.1 Session, bars, profile

| Element | Rule |
|---|---|
| Market / series | **ES** (scored), NQ (reported). Databento `ES.v.0` / `NQ.v.0` `ohlcv-1m`, `ts_event` = bar start, as W16 §2. |
| Session | **Regular hours 09:30–16:00 America/New_York**, XNYS trading days; early closes end at the XNYS close. Sessions missing the 09:30 bar or with a gap > 5 min inside the session are skipped and counted, as are the sessions that follow them. |
| Rolls | If the profile session and today carry different `instrument_id`s, today is skipped and counted (~4 a year). |
| **Profile** | Built from the **prior** session's RTH 1-min bars only. Each bar's volume is spread **evenly over every tick from its low to its high inclusive** (tick 0.25). |
| **POC** | The tick with the most volume. Ties → the tied tick closest to the prior session's 16:00 close; still tied → the lower one. |
| **Value area (70%)** | Start at the POC. Repeatedly compare the volume of the next tick above the area with the next tick below it; add the larger (tie → add the one above). Stop as soon as the area holds ≥ 70% of the session's volume. **VAH / VAL** = the area's top and bottom ticks. |

### 2.2 Setup, trigger, entry

| # | Rule |
|---|---|
| O | **Open outside:** today's 09:30 open > VAH (**above**) or < VAL (**below**). An open exactly at VAH or VAL is not outside. |
| B | **Brackets:** the 30-minute periods starting 09:30, 10:00, …, 15:30. A bracket **closes inside** if the close of its last 1-min bar is within [VAL, VAH]. |
| T | **Trigger:** the first time **two consecutive brackets both close inside**. The second bracket must end by **15:00** (brackets starting 14:30 or earlier). |
| E | **Entry** at the open of the first 1-min bar after the trigger. Open above → **short**; open below → **long**. One VA80 trade per session. |
| A | **Already rotated:** if price has already traded at or through the far edge (VAL for a short, VAH for a long) at any time between 09:30 and the entry, there is no trade (counted). |

### 2.3 Exits

| # | Rule |
|---|---|
| Tgt | **Target** = the far edge (VAL for a short, VAH for a long), resting limit. Filled only if a later bar trades **through** it by ≥ 1 tick (W16 convention: a touch is not a fill). |
| Stop | **1 tick beyond the day's extreme outside the value area up to the entry** (high of day for a short, low of day for a long), resting. A bar that opens through the stop fills at its open. |
| Time | **Flat at the 16:00 close** (close of the 15:59 bar, or the early-close bar). |
| Both | If one bar reaches both stop and target, **the stop wins**. |

### 2.4 Costs, sizing

- **1 MES per trade** (headline, $5 a point); 1 ES reported. Before May 2019, micro = full ÷ 10 (convention, as W16
  and TSMOM). Account $22,129, fixed 1 micro, no compounding.
- **IBKR** all-in fee per side for MES and ES from W15-0033, written here as a **PRE-RUN amendment before any P&L**
  (G5). Levels: **low** = fee, 0 ticks; **mid (headline)** = fee + 1 tick on every market or stop fill; **high** =
  fee + 2 ticks. Target limit fills: fee, 0 ticks (W16 §4 convention).

### 2.5 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| **Reclaim (Imre)** | trigger = the first 1-min close back inside the value area | his looser reading |
| **One bracket** | trigger = one 30-min bracket closing inside | how much the second period filters |
| **No stop** | stop removed; target or 16:00 only | the pure rotation claim as a trade |
| **POC half** | half out at the POC, rest to the far edge | Imre's optional partial |
| **NQ** | same rules on NQ, 1 MNQ | "slightly different by market" |
| **Neighbour grid** | acceptance brackets {1, 2, 3} × bracket length {15, 30, 60 min} × value-area share {60%, 70%, 80%} = 27 cells, net at mid | whether the centre cell is a lucky spike (criterion 6) |

---

## 3. What every run must emit

- **Counts per year:** sessions; skipped (data, roll); opens above / below / inside the value area; triggers; already
  rotated; trades by side.
- **The 80% check (claim check, reported first, not a pass criterion):** of all triggered setups (including already
  rotated), the share that trade **at** the far edge before 16:00; the share that hit the stop level first; the share
  that do neither. Beside it: the same share for C-RT entries (below). Claim reproduced if the far-edge rate is
  **≥ 70%**; reported either way.
- **Book at low / mid / high:** gross, costs, net, trades, wins, losses, win %, mean win, mean loss, target / stop /
  time exits, worst drawdown, by year, by side; target and stop distances in points (median, p10, p90).
- **Sample trades:** 15 trades spread over the years (date, side, VAH, VAL, entry time and price, exit reason, net $).
- **Controls, 1,000 seeded draws each** (`np.random.default_rng([zlib.crc32(str(draw)), zlib.crc32(date), 80])`):
  - **C-RT random time (scored):** on each trade's session, same side, entry at the open of a random 1-min bar between
    10:00 and 15:00 at which the prior bar closed inside the value area and the far edge has not yet been reached;
    same target and stop rule (§2.3). Tests whether the two-bracket trigger adds anything to being in on that day.
  - **C-ND no-setup days (reported):** sessions that opened **inside** the value area; random side; entry as C-RT;
    target = the edge on that side, stop = 1 tick past the day's extreme on the other side so far. Tests whether
    opening outside matters.
  - Percentiles p5 / p50 / p95 / p99 of net at mid, and VA80's percentile.

**Nothing is ranked. No best-variant table.**

---

## 4. The bar to clear — ES, 1 MES, IBKR mid, training side

Passes only if all hold:

1. **Net > $0** at mid.
2. **Net > the p95 of C-RT.**
3. **Both halves net > $0** (split at the median entry date; an empty half fails).
4. **Net > $0 at high** friction.
5. **No single year** supplies more than 50% of net.
6. **At least 18 of the 27 neighbour cells** net > $0 at mid.
7. **At least 200 trades.** Fewer → **NOT READ**, not failed. (200, not W16's 300: by construction the rule fires on a
   minority of sessions; the pre-flight count decides before any P&L.)

**Failing 2 closes the study, whatever else passes.**

---

## 5. Before the run — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | **Data:** ES.v.0 / NQ.v.0 `ohlcv-1m`, W16 archive (owned). No new pull. Sessions and early closes from the W16 session code (`strategy/w16/sessions.py`), reused. | Open (sub 3) |
| G2 | **Count-only pre-flight** (sub 4): §3 counts per year, and the value-area width distribution (points). Reads bars only up to each entry; a test proves no bar after the entry minute is read in pre-flight mode. **No outcome, no far-edge rate, no P&L.** | Open |
| G3 | **Holdout ledger** `holdout_va80.json` (§6), own lock, refused by name from every other ledger (including `holdout_w16_sb.json` and `holdout_otf_gate.json`); refuses `--limit` and narrowing flags; mutation-tested. | Open |
| G4 | **Look-ahead guards**, each proven by a test that a one-bar shift breaks: the profile uses only the prior session; a bracket counts only once its last bar has closed; the entry is the bar after the trigger; the stop level uses only bars before the entry. Plus a hand-built session with a known POC / VAH / VAL (every tie rule exercised). | Open |
| G5 | **Costs:** IBKR MES / ES / MNQ / NQ fees from W15-0033 written in as a PRE-RUN amendment. | Open (blocked by W15-0033) |

**Stop rule, fixed now:** fewer than **200 ES triggers** on the training side → stop; the counts are the finding, back
to Ben before any outcome is read.

---

## 6. The holdout

- **Training: 2010-06-07 → 2023-12-29** (the first profile needs a prior session). **Holdout: 2024-01-02 → the end of
  the owned 1-min data**, same cut as W16 (Ben's choice for the ES/NQ archive), with its **own ledger
  `holdout_va80.json`**.
- **Spent once, only on a seven-of-seven pass.** Holdout pass = net > $0 at mid **and** ≥ p90 of C-RT, reported with
  the trade count and the far-edge rate.
- **Overlap:** W16 SB-v0, the W16 bar batch and OTF-G's H-B hold out the same window for other hypotheses; none spent.
  If more than one ever is, all holdout results are reported together.

---

## 7. Registered as NOT to be done

- Changing the value-area share, bracket length, acceptance count, entry deadline, target or stop after a result.
- Swapping a variant or grid cell (reclaim, one bracket, no stop, POC half, NQ) in as the primary after a result.
- Adding filters (OTF state, gap size, day of week, value-area width) after a result — each is a new registration.
  (Combining VA80 with OTF-G's balance state is Imre's full method; it needs its own registration and a reason that
  does not begin with either result.)
- Quoting the far-edge rate, gross, or 1 ES as the headline.

---

## 8. Ways this could go wrong

- **The profile is approximate.** Spreading each minute's volume evenly over its range blurs the POC and the edges by
  a tick or two. Real TPO/volume profiles differ; the result is about this construction. Tick data would settle it
  but is not owned for 2010–2023.
- **Geometry does the work.** A far edge that is close and a stop that is far give a high hit rate and a poor payoff
  at the same time. The 80% check and the book are reported side by side, with target and stop distances.
- **The stop can be wide.** On gap days the day's extreme may sit far outside the value area; losses are then large
  against 1-tick costs, which is the honest price of the rule as written.
- **Costs.** At 1 MES, fee + 1 tick per side is roughly $3–4 a round trip against targets of a few points ($5 each).
- **Few trades.** Opens outside the value area may be half of all sessions; two accepted half-hours before 15:00 may be
  a fraction of those. The pre-flight decides.

---

## 9. Multiplicity budget

One primary (ES, §2), one variant family (§2.5, unranked), one holdout spend. A second value-area registration needs
a reason that does not begin with this result.

---

## 10. A prediction, written down now

**About 250–450 ES triggers in 13.5 years. The far edge is reached on about 50–65% of them, not 80%. Because the stop
at the day's extreme is usually further away than the far edge, the book wins more often than it loses but nets near
zero after costs, and sits between the 50th and 90th percentile of C-RT — criterion 2 fails. Most likely reading:
*price that returns into yesterday's value often crosses it, but not more often than price already inside it does
at a random time.*** I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0025 sub 2** (Ben): review, then commit this file and `REGISTERED_otf_gate.md` (commands on the board).
- **W15-0025 sub 3** (Build & test chat, Sonnet · High): profile/value-area builder, bracket/trigger engine, exits,
  C-RT / C-ND, grid, guards G3/G4, ledger; handover `claude/handover_w15_0025_build_20260930.md`.
- **W15-0025 sub 4 / sub 5**: count-only pre-flight, then the training run → Result doc.
- **W15-0033**: IBKR fees (blocks G5).
