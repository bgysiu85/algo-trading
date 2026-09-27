# RESULT — SPY intraday momentum (H-S1 / H-S2): NOTHING, and the effect died around 2016

**2026-09-18.** Code `01f22e4`. Spec `claude/spy_intraday_spec_20260917.md`;
registration `docs/research/REGISTERED_spy_intraday_data.md` (amendments A–M);
venue column `claude/spy_intraday_AMENDMENT_A_20260917.md`.

> **Both scored cells read NOTHING, and the reading is not about friction.**
> H-S1 is **−0.308 bps per trade GROSS** and H-S2 **−0.271**, before any cost at
> all. The breadth control agrees on QQQ (−0.009) and IWM (−0.577). No venue,
> fee schedule or execution improvement reaches a negative gross — the argument
> `AMENDMENT_A` §A.5 makes for MCL, MC5 and VW9 now applies here too.
>
> **And the study can say that with confidence, because H-R passed.** Over
> 2005–2013, the paper's own sample, the same code reads **+5.41%/yr, 53.52%
> directional hit against the published 54.37%**. The pipeline finds the effect
> where it is documented and does not find it afterwards. A flat reading from a
> harness that has never been shown able to detect anything would have meant
> nothing.

---

## 1. The controls, which ran first

| | verdict | reading |
|---|---|---|
| **H0** — same dates, random sign, 10,000 draws | **FLAT** | mean net −1.149 bps against the −1.150 arithmetic demands |
| **H-R** — H-S1 over 2005-01-01 → 2013-12-31 (amendment K) | **AS PUBLISHED** | +5.41%/yr, band 3–12%; 2,242 sessions, +3.320 bps gross, +2.170 net, hit 53.52% |

H-R is **reported and not scored**. It sits inside the paper's sample, so it is
replication and not out-of-sample support, and it cannot be promoted or cited as
an edge. Its only job is to rule out the failure where a pipeline passes H0 by
measuring nothing at all.

## 2. The scored cells — both NOTHING

Window 2015-01-02 → 2024-05-08 (training side; the holdout is unspent). Gates
read at the realistic level, 1.15 bps.

| | H-S1 (primary) | H-S2 (secondary) |
|---|---:|---:|
| sessions traded | 2,336 | 762 |
| trades / year | 250 | 82 |
| directional hit | **48.12%** | **48.69%** |
| **gross bps / trade** | **−0.308** | **−0.271** |
| net bps / trade @ 1.15 | (1.458) | (1.421) |
| annualised | (3.64)% | (1.16)% |
| both halves | (1.578) / (1.337) | (1.578) / (1.264) |
| drop-top-3 / 5, level | (4,308) / (4,741) | (2,031) / (2,464) |
| drop-top-3 / 5, delta vs H0 | (0.749) / (0.917) | (1.605) / (2.160) |
| cluster bootstrap (month) | 113 blocks, CI [(2.882), +0.383], P(>0) = 0.056 | 98 blocks, CI [(5.277), +3.613], P = 0.245 |
| beats H0 p95 | no — p95 (0.046) | no — p95 +1.829 |
| **gates passed** | **0 of 5** | **0 of 5** |

H-S2's trade count landed at **82/year against a registered prediction of
80–90**. The sign did not.

## 3. Breadth control (§8.4) — the same answer three times

| | verdict | hit | gross bps | net @ 1.15 |
|---|---|---:|---:|---:|
| SPY | NOTHING | 48.12% | −0.308 | (1.458) |
| QQQ | NOTHING | 49.79% | −0.009 | (1.159) |
| IWM | NOTHING | 48.46% | −0.577 | (1.727) |

§8.4 exists to refuse a result that lives on one instrument. Here it does the
opposite job and is worth more for it: **absent on all three** is the same
statement three times over.

## 4. When it died — and it is not the 0DTE story

Gross bps per trade, H-S1 unchanged, by three-year block:

| block | n | hit | gross bps |
|---|---:|---:|---:|
| 2004–06 | 735 | 51.57% | +0.323 |
| **2007–09** | 742 | **55.12%** | **+7.554** |
| 2010–12 | 749 | 52.60% | +1.067 |
| 2013–15 | 747 | 49.80% | +1.235 |
| 2016–18 | 748 | 47.86% | (0.825) |
| 2019–21 | 751 | 47.00% | (0.186) |
| 2022–24 | 747 | 50.20% | (0.052) |
| 2025–26 | 424 | 50.00% | +0.195 |

Two things follow.

**The effect is concentrated in 2007–2009** — exactly where the paper's own R²
table puts it (recessions 6.6% against expansions 1.0%). Our +7.554 bps in that
block against +1.07 either side is that table, measured independently.

**It is gone from 2016, which is earlier than the 0DTE era.** The skeptical
measurement that motivated registering H-S2 dates the death to the post-2022
0DTE regime. On this data the sign had already flipped by 2016–18 and the
2022–24 block is the flattest of the negative ones. **This does not support the
0DTE mechanism — it dates the decay before it.** What it is consistent with is
the paper's own conditioning: the effect lives in high-volatility, high-hedging-
demand regimes, 2007–09 was the largest such episode in the sample, and the
decade after it was not.

## 5. What the registered prediction got right

Recorded pre-run in spec §10, unrevised through amendment M:

- **H-S1 → NOTHING**, moderate confidence. **Correct.** It was predicted to be
  positive-but-marginal and fail a gate; it is negative and fails all five.
- **H-S2 → genuinely uncertain**, +2 to +5 bps on 80–90 trades/year, low
  confidence. **Count right (82), sign wrong.** This was the open question and
  it now has an answer.
- **H0 → flat.** Correct, to a thousandth of a basis point.

## 6. Two defects, both found by running rather than reading

- **The run gate read the whole cache.** Seven pre-2015 anomalies and one 2004
  hole blocked a 2015+ book they cannot reach — the only channel between
  sessions is the prior close, which spans exactly one session. It now reads the
  scored window plus that one boundary session, with four tests that it still
  fires inside the window.
- **The `sigma1` trailing percentile was computed inside the trimmed window**,
  leaving the first year ungated for no reason and costing H-S2 113 trades.
  2014's `sigma1` was knowable in January 2015. Found because two counts
  disagreed, not by reading the code.

## 7. Status

**The holdout is UNSPENT.** `holdout_spy.json`, 584 sessions locked from
2024-05-09, committed. Nothing cleared the gates, so nothing earned it.

**Not run, and why:** the boundary surface (§8.5) is a refusal check for a
*passing* cell — with NOTHING there is no clock-fitting to detect, and running a
3×3 grid over a dead cell only manufactures nine numbers to be tempted by. The
mechanism test (§8.3) is likewise moot: `sigma1` has nothing to be a proxy *for*.

**This closes the SPY intraday-momentum line.** Spec §10 anticipated it: *"if
both cells return NOTHING that is a complete and useful answer… it closes
intraday equity for this project with a published mechanism rather than a
homemade one."* It cost two days and four prices a session, and unlike the six
`pullback_break` NOTHINGs it closes against a peer-reviewed, independently
replicated effect that this pipeline demonstrably *can* detect — in the era it
was documented.
