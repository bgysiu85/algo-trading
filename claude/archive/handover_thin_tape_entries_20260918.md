# Handover — entries on a tape with nothing in it: MC5 has no volume condition

From: live paper-trade analysis chat (read-only on production).
To: strategy build and test chat.
Written 2026-09-18, after the session. Nothing changed in either tree.

Ben, on the two MC5 AEHL trades of 2026-09-18: *"simply should not have happened. there
were no volume to support any trades."* He is right, and the ledger says so on its own rows.

Related: `claude/session_review_20260918.md` §3, `PROGRAM_INDEX` §7 item 20 (a spread gate
at entry), `claude/REGISTERED_drift_guard_20260917.md` (the guard this would sit beside).

---

## 1. The two trades

| | 04:06:01 | 06:31:01 |
|---|---|---|
| signal bar volume (5 min) | **2,003** | **634** |
| bid / ask at order | 10.52 / 11.75 | 12.10 / 12.35 |
| spread | **10.47%** | 2.02% |
| fill | 11.75 (the ask) | 12.35 (the ask) |
| result | (24.38), 9 min | **(84.38), 154 min** |

634 shares in five minutes is about two shares a second. The 10.47% spread on the first is
the same fact from the quote side: there was nobody there. Together **(108.76) — 7.5× the
day's net loss of (14.59)**.

The exit said it too: AEHL's first stop took **13 consecutive `NO_FILL_CANCELLED`**
(04:09:01 → 04:14:35) at a limit of 11.24 against a quoted bid of 11.27 before filling at
11.52. Five minutes to leave a $11 name.

## 2. The rule gap

**MC5's entry is three clauses and none of them is volume** (`strategy/mc5/mc5.py`):

```python
out["entry"] = out["c_rsi"] & out["c_ema"] & out["c_macd"]
```

**MCL has two volume clauses** (`strategy/mcl/mcl.py`, `VOL_MULTIPLE = 3.0`,
`FLOOR_FRACTION = 0.5`):

```python
out["c_vol"]   = (v >= prev_vol * VOL_MULTIPLE) & (prev_vol > 0)
out["c_floor"] = (trail_avg > 0) & (prev_vol >= trail_avg * FLOOR_FRACTION)
```

`c_floor` is the one that matters here: it refuses a bar whose predecessor was dead. MC5 has
no equivalent, and the `vol` figure on its fill rows is logged for the record and never
tested against anything. **So both AEHL trades were legal under MC5's rules.** This is a
strategy gap, not an execution defect.

## 3. What the live book says, descriptively — and why it is not a result

180 live round trips, 2026-09-10 → 09-18, cut by the signal bar's own volume and by the
spread at the moment the order went out. **Both cuts were chosen after seeing which trades
lost. That is a descriptive cut, not a test.**

| signal-bar volume | n | net | per trade | win |
|---|---:|---:|---:|---:|
| < 2,000 | 12 | (214.48) | (17.87) | 17% |
| 2k–10k | 15 | (111.57) | (7.44) | 27% |
| 10k–50k | 28 | 73.58 | 2.63 | 43% |
| ≥ 50k | 124 | (384.15) | (3.10) | 21% |

| spread at entry | n | net | per trade | win |
|---|---:|---:|---:|---:|
| < 0.5% | 103 | (11.32) | (0.11) | 24% |
| 0.5–1% | 42 | 4.34 | 0.10 | 26% |
| 1–2% | 22 | (87.16) | (3.96) | 27% |
| **≥ 2%** | **13** | **(601.87)** | **(46.30)** | 15% |

And the two cuts together:

```
spread >= 2% OR signal-bar volume < 2,000 :  21 trades   (656.85)
everything else                           : 159 trades    (39.16)   = (0.25)/trade
```

**Read that with both hands.** The 13 wide-spread trades include CRBP (241.37) and both
AEHL trades; ex-CRBP the bucket is still (360.50) over 12. The volume buckets are not
monotone — the ≥50k bucket is negative too — so "more volume is better" is NOT what this
says. What it says is that **the two extremes are where the large losses live**, which is
the shape a gate addresses and a ranking does not.

## 4. Three ways to stop it. They are different claims — pick and register one

**(a) A volume floor inside MC5**, mirroring MCL's `c_floor`.
- Strategy change. Alters every published MC5 figure and needs the full backtest treatment.
- **MC5 is CLOSED as a candidate** (−$8.93/trade on XNAS.BASIC, negative on every
  drop-top-N) and is on paper only to collect fill data. Reopening its rules is the most
  expensive of the three and buys the least.

**(b) A spread gate at entry, in the trader** — `PROGRAM_INDEX` §7 item 20, now with cases.
- Strategy-independent: it protects MCL, MC5 and anything that comes later, including ORB.
- The spread is already computed and already on every row, so the implementation is the same
  shape as the drift guard: last, on a fresh quote, refuse and write `SKIPPED_SPREAD`.
- Threshold must be **pre-committed** in the registration. Note that 2% would have refused
  CRBP (2.57%) — the single worst trade in the live book — but that is exactly the trade
  that makes an after-the-fact threshold suspect. State the number and the reasoning before
  running it.

**(c) A minimum signal-bar volume gate, in the trader.**
- Same shape as (b), on the number the strategies already put on the row.
- It is the cut that matches Ben's objection most literally, and it catches a dead tape even
  when the spread happens to look tight at that instant.

**My reading:** (b) and (c) are one registration with two clauses, not two projects, and they
belong in the trader rather than in either strategy. (a) is a separate question and probably
not worth spending on a closed candidate.

## 5. What the registration has to say before anything runs

1. **The thresholds, chosen and written down first**, with the reason. Not fitted to the 21
   trades above.
2. **Where it runs:** after the signal, before the order, on a fresh quote, entries only —
   exits are never gated (a position that cannot be exited is the MEDS failure, not a saving).
3. **A row is written on every refusal** (`SKIPPED_SPREAD`, `SKIPPED_THIN_BAR`), so a refused
   entry is visible and not indistinguishable from "the strategy never fired".
4. **Measured on the point-in-time books, both denominators**, with drop-top-N, both halves
   and the cluster bootstrap — the same bar as everything else. The live book is n=180 with
   two trades dominating; it motivates the test, it is not the test.
5. **Report what the gate removes, not only what it saves:** how many entries it refuses,
   and how many of the book's best trades it would have refused. A gate that removes the
   winners is a loss even if it removes more losers.
6. **Interaction with the drift guard**, which already refuses ~1 entry in 10. Two gates on
   the same path can be double counted; report the overlap.

## 6. The bit that is not a strategy question

On the 04:06 AEHL entry the drift guard measured the **ask** (−5.6% from the signal close,
inside the 6% limit) while the **mid** was −10.6% away. The guard is correct for its own
question — the ask is the side a marketable buy crosses — but on a 10% spread the two
readings differ by 5 points. That is an argument for (b) existing, not for changing the
guard's side. Recorded here so it is not fixed twice.
