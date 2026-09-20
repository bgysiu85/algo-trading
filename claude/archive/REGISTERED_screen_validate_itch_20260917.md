# REGISTERED — does the simulated screen match the live watchlists? On the tape of record, with the 04:00 carry-over set aside, and with a clock

`PROGRAM_INDEX` §7 item 1, the one that gates everything else. Every
point-in-time figure rests on `screen_sim` reproducing what TradingView put on
the live watchlist, and that agreement has been measured once, on four
sessions of XNAS.BASIC, at 76% ("PARTIAL", `screen_validate.txt`, 2026-09-13).
Since then the tape moved to XNAS.ITCH (v2, `screen_pairs_pit_itch_v2.json`),
the archive has eight automated sessions (2026-09-08 → 09-17), and the reason
for most of the 76%'s misses is known.

**Committed before the XNAS.ITCH extension is pulled and before `screen_sim`
runs on it. Cost: $0.00 (inside the free window).**

## 0. What was seen before this was written — said plainly

- The eight archived watchlists and their blocked files were read by eye,
  and `common/screen_validate` was rebuilt against them. The BASIC extension
  (`screen_pairs_pit_ext.json`, 09-08 → 09-16) was run through the rebuilt
  tool as a smoke test. **So the BASIC numbers in §3 are not predictions —
  they are what the dry run printed, recorded so the ITCH run has something
  to be compared with.** The XNAS.ITCH universe for these sessions does not
  exist yet; every ITCH figure below is blind.
- The dry run showed one thing that was not looked for: on every session,
  every name IBKR refused was refused **13.3 to 16.0 minutes after the
  simulation first surfaced it** (8 of 8, median +14.9). §2.4 and P5 are
  written around that observation; the ITCH first_seen values that will test
  it have not been computed.

## 1. What is run

1. `databento_universe --dataset XNAS.ITCH --schema ohlcv-1m --window
   04:00-09:30 --start 2026-09-16 --end 2026-09-18` and the same on
   XNAS.BASIC for 2026-09-17 → 09-18. Free. `--end` is exclusive.
2. `regular_close --emit` so 2026-09-16's regular close exists for 09-17's
   `premarket_change`.
3. `screen_sim --dataset XNAS.ITCH --capture-ladder var/reports/itch_capture.json
   --ladder-cut 2026-03-30 --after 2026-09-08 --out
   var/state/screen_pairs_pit_itch_ext.json` — the v2 screen, forward over
   the September sessions, to a **new** file. `screen_pairs_pit_itch_v2.json`
   is not touched. The same on XNAS.BASIC at capture 0.552 to
   `screen_pairs_pit_ext2.json`; `screen_pairs_pit_ext.json` (09-08 → 09-16,
   the file A1/A3 were read on) is not touched either.
4. `screen_validate --diagnose` on each, `--label` naming the tape.

## 2. What is read, fixed now

### 2.1 The pairing

The session is the `# tv_feed YYYY-MM-DD` header's date, not the file's.
`archive_watchlist` stamps the local date at 09:30 ET, which is the ET date
under AEST and the next day under AEDT; every file in the archive today
agrees with its header, so this changes nothing yet and prevents a silent
off-by-one on 2026-10-04.

### 2.2 The 04:00 carry-over, set aside before the verdict

The live file is ordered HOT, WARM, COLD and the header carries the counts,
so each name's tier at 09:29 is recoverable. The COLD tail on 09-09, 09-10,
09-14 and 09-16 is exactly the previous session's list, and the blocked
files stamp those names at **04:00:05, 04:00:06, 04:00:08, 04:00:26** — the
feed's first poll. TradingView's `premarket_*` fields hold the previous
session's values until today's pre-market prints, so the first poll surfaces
yesterday's screen, and the trader arms it. That is a live-feed fact the
simulation cannot reproduce (its session starts empty) and it is not what
this study measures.

**Rule (sim-blind):** a live name that is COLD at 09:29 *and* on the
previous automated list is a carry-over candidate and is removed from both
numerator and denominator. The verdict is read on what remains; the
all-names figure is printed beside it. A genuine repeat runner is removed by
the same rule; `sim found` counts how many candidates the simulation
surfaced anyway, so the cost of the rule is visible. A session whose header
counts do not match its file sets nothing aside.

### 2.3 The verdict

Unchanged from 2026-09-12: the share of (clean) live names the simulation
surfaced, Wilson 95%, read from the **lower** bound: ≥ 80% GOOD, 50–80%
PARTIAL, < 50% a different universe. Blocked names count as screened.
Sim-only names are reported with their best simulated rank and do not move
the verdict.

### 2.4 Two clocks

The archive keeps no arrival times. Two things do:

- **Block stamps.** The trader's whatIf probe refuses a restricted name
  within seconds of arming it. `live − sim` = block stamp − simulated
  `first_seen`, for blocked names that are not carry-over and not stale
  04:00 arrivals.
- **First entry signal**, from `var/fills/mcl_fills_*.csv`. The trader
  signals only a name it has armed, so the first BUY is a looser upper
  bound on arrival for every traded name. What matters there is the
  *smallest* delta: one name signalled well under fifteen minutes after
  the tape first qualified it rules out a fixed feed delay of that size.

Both are lists with a median, never a rate.

### 2.5 The diagnosis

For every clean miss, the three clauses tick by tick on the tape the
simulation used (ladder applied): the best the name ever looked, and which
clause it failed there, or PASSED (which points at the simulation). For
every name the live record proves the feed had before the simulation's
`first_seen`, the three clauses at that moment.

## 3. Predictions

The BASIC column is the dry run (§0), not a prediction. ITCH is blind.

| | BASIC ext, 7 sessions (dry run) | **ITCH ext, prediction** |
|---|---|---|
| all live names found | 51/69 = 74% [62, 83] | 70–85% |
| carry-over set aside; found | 49/51 = 96% [87, 99] → GOOD | **≥ 90%, lower bound ≥ 80% → GOOD** (P1) |
| clean misses | RML 09-09, TPET 09-10 | ≤ 4 over 8 sessions (P2) |
| sim-only | 1 (BRNX 09-08, rank 2) | **more than BASIC: 3–12** — post-change ITCH thresholds are 2–11k shares, so the exchange-only screen admits more (P3) |
| ITCH ext symbol-days vs BASIC ext2, same sessions | — | ITCH ≥ BASIC, by 10–50% (P3) |
| carry-over candidates the sim found anyway | 2 of 18 | 2–5 of ~18 (P4) |
| block-stamp clock, median live − sim | +14.9 min, range +13.3 to +16.0 | **+12 to +18 min, every value positive** (P5) |
| first-signal clock, smallest delta | −42.0 (XRTX 09-11), 2 under +10 | at least one negative (P6) |

- **P1.** The simulation reproduces the live screen on the tape of record.
  If the lower bound lands under 80% on ITCH while BASIC's was 87%, the
  after-cut ladder (thresholds 2–11k) is the first suspect and the hybrid
  universe (ITCH before 2026-03-30, BASIC after) is the next registration.
- **P2.** Each clean miss is diagnosable and none reads PASSED. The likely
  clause is `change` — TradingView measures against its own prior close and
  the repaired 16:00 close can differ — or `volume` just under the ladder
  step. A PASSED verdict is a simulation defect and stops everything else.
- **P5.** The +15 minutes is a property of the feed, not the tape: the
  scanner endpoint `tv_feed` polls is unauthenticated, and TradingView serves
  US equities **15 minutes delayed** without a real-time exchange
  subscription. If ITCH's `first_seen` values, which are independent of
  BASIC's, give the same +13 to +16 cluster, the live watchlist runs a
  quarter of an hour behind the tape. That is a live-trading fact with a
  study of its own behind it (a `first_seen + 15 min` universe variant), not
  something read off this result.
- **P6.** At least one name reaches the live feed before the simulation
  qualifies it (XRTX 09-11 on BASIC, 42 minutes early). The moment-diagnosis
  says which clause the simulation was still failing then; the prediction is
  `volume` (TradingView's consolidated count reaches 100k before the
  tape-scaled threshold does) or `change` (a different prior close).

## 4. What this decides, and what it does not

- **Decides §7 item 1** in one of three ways per the bands, on the tape of
  record, with the carry-over named rather than scored. GOOD retires the
  "unmeasured agreement" caveat on the v2 baselines; PARTIAL keeps it with a
  number; a different universe reopens the screen.
- **Unblocks item 15** (the Databento subscription) once the ITCH extension is
  on disk, whichever way the verdict goes.
- Decides nothing about the +15 minutes beyond recording it. Decides nothing
  about a strategy.
- No pull beyond the free extension. `holdout.json` stays shut.
