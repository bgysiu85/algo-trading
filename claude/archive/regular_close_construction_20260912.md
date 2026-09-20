# Which print is the regular close — 27 rows, and the venue split answers it

`python -m common.regular_close --dataset XNAS.BASIC` · raw:
`var/reports/regular_close_XNAS_BASIC.txt` · bundle `20260912q`

## The split that settles the TPET question

| candidate | AMEX | NASDAQ | NYSE |
|---|---:|---:|---:|
| `last_bar_before_1600` | 1/3 | 10/19 | 2/2 |
| **`open_at_1600`** | **0/3** | **17/19** | **2/2** |
| `bar_at_1600` | 2/3 | 8/19 | 1/2 |
| `last_bar_at_or_before_1600` | 2/3 | 8/19 | 1/2 |
| **`auction_else_last`** | **0/3** | **17/19** | **2/2** |

Pooled: `auction_else_last` 19/24.

**XRTX matched.** The thin NASDAQ name — ~10k shares on a quiet day — is right on
3 of its 4 rows. So **liquidity is not the problem**, and TPET's failure is about
where it lists: NYSE Arca, whose closing cross does not appear on a Nasdaq tape
at all. AMEX scores **0/3** on the construction that scores 17/19 on NASDAQ.
That is not a broken construction; it is a partial tape.

ACVA (NYSE) is 2/2, so "non-Nasdaq fails" is too broad a reading — but it is
only two rows.

## The two NASDAQ misses

| | truth | bef 16:00 | open 16:00 | auc\|last | ours (1d) |
|---|---:|---:|---:|---:|---:|
| FTFT 09-10 | 2.05 | 2.02 | 2.03 | 2.03 | 2.11 |
| XRTX 09-10 | 2.11 | **2.11** | 2.18 | 2.18 | 2.44 |

XRTX 09-10 is the interesting one: `last_bar_before_1600` gets it **exactly**
while `open_at_1600` does not. The first print at or after 16:00:00 was an
extended-hours trade at 2.18, not the cross. The Nasdaq closing cross is
disseminated at 16:00:00 but the print can be timestamped either side of the
boundary, and minute OHLCV cannot tell a cross from any other trade.

## The pre-registered bar was NOT met

`regular_close` requires a construction to reproduce **every** discriminating
row. `auction_else_last` reproduces 17 of 19 NASDAQ rows. The verdict is
therefore `NONE of the candidates reproduces the truth`, and the module refuses
to authorise the 552-session pull.

**Proceeding anyway is a decision to relax a pre-registered bar, and must be
recorded as one rather than slipped through.**

## What the repair is worth, stated honestly

Today, `prior_close` is wrong on 24 of 27 rows, frequently by a lot: ACVA 44%,
SUNE 31%, TNON 24%, XRTX 16%.

With `auction_else_last` it is wrong on 2 of 19 NASDAQ rows, by **1–3.5%**.

The screen's clause is `change >= 20%`. A 1–3.5% error in the divisor moves the
computed change by roughly 1–3.5pp, so it can still flip membership for a name
sitting within ~3pp of the threshold — which is exactly how TPET was lost (a
2.8% error turned +20.4% into 17.20%).

So the repair moves the archive from **systematically wrong** to **occasionally
marginal**. That is a large improvement and it is not exactness, and
`screen_validate`'s re-run will carry residual disagreement that is NOT a
simulation defect.

## The fork

1. **Accept and pull.** Take `auction_else_last`, record the relaxed bar, treat
   non-NASDAQ listings as a known gap, state the 1–3.5% residual wherever the
   repaired closes are used. Cheapest path.
2. **Resolve the residual first.** Pull the `trades` schema for 15:59–16:01 on
   the probe sessions; a closing cross carries a trade condition that identifies
   it exactly, which minute OHLCV cannot. Small targeted pull, exact answer,
   and it would likely take NASDAQ to 19/19.

Option 2 costs one more probe and removes the need to relax anything.

## Standing

- EQUS.MINI is settled and rejected: 2/8 where XNAS.BASIC scored 5/9, rows
  missing entirely, no 16:00 bar on most. No consolidated source is needed and
  no new subscription.
- The truth table is **not out of sample** — all 27 rows were read while chasing
  this defect.
- `pit_strategy --strategy mcl` / `mc5` remain on hold: they run on a universe
  this defect selected.
- **Do not cancel Databento.**
