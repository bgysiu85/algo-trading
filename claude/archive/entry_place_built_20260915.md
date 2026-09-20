# The placement instrument — built 2026-09-15, not yet run

**Bundle:** `20260915a` · commit `25b4ee8` · ref `main` · 2,535 passed, 2 skipped

---

## The 2026-09-14 pull landed

`E:\Databento\XNAS.BASIC\manifest.json` now carries:

```
ohlcv-1m/2026-09-14_0400_0930
  start 2026-09-14T08:00:00  end 2026-09-14T13:30:00
  bytes 4,005,855            degraded_days []
```

4.0 MB against the 11th's 3.2 MB, nothing degraded. **All nine samples on the
14th (06:57–08:21 ET) are inside it.** That was worth checking rather than
assuming — the two prior attempts both printed success-shaped output and
fetched nothing.

The `1555_1605` close chunk for the 14th was not pulled. Nothing here needs it.

## The third tranche — 22 → 27 features

Read off the indicator headers of Ben's screenshots, not from outcome data:

| column | what it is |
|---|---|
| `ema9_dist` | close / EMA(9) − 1, % |
| `ema200_dist` | close / EMA(200) − 1, % |
| `bb_pos` | where in BB(20, 2) the close sits — 0 lower band, 1 upper |
| `bb_width` | band width / mid, % |
| `vol_over_ma20` | volume / 20-bar mean volume, **including** this bar |

Families 11 → 13. `ema9_dist` joins **trend** (it is `ma20_dist` at a different
lookback — counting it separately would inflate one idea into two);
`vol_over_ma20` joins **volume headroom**; `ema200_dist` gets **regime** and the
bands get **band**.

### Three arithmetic decisions, each because the wrong one still prints a number

1. **`_ema` seeds with the simple mean of the first `span` values**, and is NaN
   before it has them. `pandas.ewm(adjust=False)` recurses from the frame's
   first value, so an EMA(200) at bar 200 still carries about **14%** of
   whatever that first bar happened to be — and reads as a settled number the
   whole time.
2. **Bollinger uses the population sigma (ddof=0)**, which is what the chart
   draws. pandas defaults to ddof=1: 2.6% on the half-width, always in the same
   direction, invisible unless asserted.
3. **`vol_over_ma20` includes the current bar**, because a Volume 20 SMA does.
   `vol_over_trail` is a *shifted* 60-bar mean. Different window, different
   convention — the two must never be compared.

## The module — `common/entry_place.py`

```
python -m common.entry_place --samples "...\Samples - Momentum Trading.xlsx"
```

Places each of the 21 samples in the distribution of **every bar of the
point-in-time universe**, on **both 1-minute and 5-minute** views, from the
**same archive**, through the **same frame builder**, scored by the **same
`features_at`**. A reference from `bar_cache/` (IB's tape) against samples from
the archive (XNAS.BASIC) would be two tapes wearing one percentile.

### The report leads with what it cannot show

21 samples · 27 features · no halves · a 0.108% base rate. A feature that flags
them is worth nothing — they were selected because their outcome was known, and
roughly half of any bar's features land in an outer quartile by construction.

**A feature that spreads them like ordinary bars rules itself out.** That list
is the output. It is deliberately hard to earn: at least half the samples in the
middle half **and** a median that is not itself extreme.

Unmeasurable samples are printed, never dropped.

### Stated up front, not buried

The archive holds 04:00–09:30 slices only, so:

- `ema200_dist` on the **1-minute** view is a 200-bar mean of **pre-market
  only** — not the line on his screen, which at 07:00 includes yesterday's
  regular session.
- `ema200_dist` on the **5-minute** view needs ~4 pre-market sessions. It does
  not exist here and is reported **absent**, not as NaN in a table.

Pulling full-day `ohlcv-1m` fixes both. Next lever, not this module's job.

## What the mutation pass found

Four survivors, two real.

1. **The 5-minute bar match was tested by a copy of itself.** A sample at 07:22
   belongs to the bar stamped 07:20 (bars are left-labelled). Swapping the
   module's `<=` for `==` left the test green — *a guard one step short of the
   thing it protects, inside the test written to guard against exactly that.*
   Extracted to `bar_index_at` and tested through it.
2. **The RULED OUT rule needs both its halves.** A set split between the
   extremes has an ordinary median and nothing in the middle — which is the
   shape of the two `pass` rows on MFI (**8.10** dead tape, **100.00** vertical)
   and the most interesting thing in the file. A median-only test would have
   filed that feature as settled.

Also fixed: `why_no_entry`'s "pull it first" hint printed `--end {day}`, which
is exclusive and fetches nothing. Ben ran that exact command and got
`0 weekday chunk(s)`.

## The set as it now stands (21)

| label | n |
|---|---|
| took | 11 |
| took and lost | 6 |
| pass | 3 |
| unlabelled | 1 |

**More `pass` rows are still the highest-information thing available.** Three
cannot carry a comparison. Every one of them is a bar that looked takeable and
was not.

## Not yet claimed

Nothing has been measured. The module is built and tested; the run needs the
archive, which is on Ben's machine.
