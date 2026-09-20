# Time of day, hold time, and the strategies by week — built

**Date:** 2026-09-18 · **Commit:** `2173fe4` · **Bundle:** `uiwork-FULL-20260918c.bundle`
**Answers:** DECISION 4 of `claude/reporting_tab_design_20260917.md` — Ben: *"yes to both"*

Two of the three remaining §6 items. The distribution (item 4) is now the only
one on the list not built.

---

## 1. By strategy, week by week (§6 item 3)

The card used to draw one horizontal bar per strategy: its total net. A single
total answers *did this make money*, which is a question you already know the
answer to by the time you ask it. **Is this one still working** needs the weeks —
a strategy that made four hundred dollars in its first week and has bled since
shows the same total as one grinding steadily upward.

Each strategy is now a row of weekly columns, above and below a centre line.

**Two things are shared across every row, and both are asserted in a browser:**

- **The week columns.** Every strategy is padded onto one week axis built once,
  server side, *including the weeks it did not trade*. Rows carrying only their
  own weeks would draw columns that do not line up between strategies, and a
  reader comparing two rows by eye would be comparing different weeks. Same trap
  the two scatters avoid by sharing their axes: the eye compares positions, not
  labels.
- **The scale.** One height means one amount of money in every row. Per-row
  scaling would draw a strategy that made twenty dollars exactly as tall as one
  that made two thousand.

**A week sat out is not a week broken even.** Both are zero. The first is 35%
opacity, the second solid, and *both are drawn at all* — which is a separate
property from being labelled differently, and the one that nearly slipped:
removing the 1px floor made a flat week vanish entirely and failed no test until
one was written that measured the rendered height.

> **A test that could not fail.** The first version of the shared-scale test
> passed with per-row scaling restored. The only quiet strategy in the book
> netted exactly zero in *both* weeks, so scaling it against itself produced
> byte-identical output. The book now carries a third strategy whose own best
> week is a fifth of the biggest on the card, and heights are compared as ratios
> so the assertion does not depend on the cell height in the stylesheet.

## 2. Time of day and hold time (§6 item 5)

Both were studied ad hoc before the tab existed. They are standing views now,
in a two-up row under *When trades happen*.

**Net, not counts.** "When do I make money" is the question. The trade counts sit
under each bar and in the tooltip, so the shape of the distribution is still
there — without it a single fat bucket passes for a reliable edge.

**Anchored at zero from both sides**, the same rule the grouped bars follow:
winners grow up from the zero line, losers down from it.

**Both take the entry time**, for the same reason `points` does — the question is
when a trade was *taken*, not when it was closed.

**Every half hour between the first and the last that traded is drawn**,
including the quiet ones. A chart that omits a quiet hour draws the day shorter
than it was and puts 09:30 next to 11:00 as though they were adjacent. Empty
buckets get the 1px sliver at 35%, so "nothing traded then" and "broke even
then" stay different facts.

### The two trades the charts cannot place — said out loud, not dropped

| Case | What happens | Why not the obvious thing |
|---|---|---|
| No entry time | Placed by its **exit**; the card counts how many | Dropping it makes the picture quietly incomplete, with no way to tell |
| No entry time → no hold time | **Not bucketed**; named in a warning footnote with its money | Bucketing a null as `<1m` invents the strongest claim the chart can make — that the money came from trades held for seconds |

The hold-time footnote carries the amount specifically so the bars and the
statistics panel can be reconciled by hand: bars + unknown = the headline net.

### Axis labels are thinned by room, not by count

Counting buckets hid **three of the hold chart's seven labels** on a card with
room for all of them — and a bar with no label is read against whichever label
is next along, which on a hold-time axis is a different duration entirely. The
step now comes from the widest label against the space per bucket. Both ends are
always labelled, and anything too close to the last one gives way, because
forcing the last on top of an evenly thinned sequence is what printed "14:30"
and "15:00" nearly on top of each other.

> **A second test that could not fail.** The collision test first estimated label
> width from the character count and passed three pixels of clearance. It now
> reads `getComputedTextLength()` — what the browser actually drew — and requires
> 8px between the right edge of one label and the left edge of the next.

---

## Verification

- **395 tests pass** (was 352 before the previous commit, 392 before this one).
- Rendered and read in **both light and dark** at 1240px.
- Reconciled by hand off the screenshot: hold buckets `120 + 0 − 30 + 25 − 75 +
  0 + 40 = 80`, plus the unplaceable `−55` = **25**, which is the headline net.
- **Nine mutations** applied and reverted; every one failed the test written for
  it, after two of them had to be rewritten because they did not:

| Mutation | Caught by |
|---|---|
| strategies keep their own weeks | column-alignment, sat-out |
| scale each row on its own | one-height *(second attempt)* |
| drop the 1px floor on a flat week | sat-out *(second attempt)* |
| a null hold time becomes the fastest bucket | unknown-not-bucketed, headline-total, hold-note |
| quiet half hours skipped | contiguity (store and browser) |
| net bars grow from the bottom | zero-line (both charts) |
| empty bucket drawn like a traded one | faint-bucket (both charts), sat-out |
| labels thinned by bucket count | every-hold-bucket-labelled |
| last label forced without making room | labels-never-collide |

## What is not built

**§6 item 4, the distribution** — a histogram of trade net, plus the existing
concentration analysis (drop the top 1/3/5 trades). Tail shape matters more than
the average, and at a 27% fill rate over 194 trades it is the view most likely to
say whether the edge is real.

## Related

- `claude/reporting_tab_design_20260917.md` — the design; §6 is the running list
- `claude/bundle_delivery_rule_20260918.md` — why bundles carry complete history
