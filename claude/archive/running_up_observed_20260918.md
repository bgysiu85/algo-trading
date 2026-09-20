# The Running Up scanner, as observed — what the recording shows, and the one distinction the pre-flight missed

**Date:** 2026-09-18 · **Source:** `D:\Trading\Claude outputs\running up scanner - sample.mp4`
(8m24s, 2026-09-18 pre-market, 06:16–06:30 ET, recorded by Ben)
**Method:** frames sampled at 20s, 100s, 200s, 300s, 400s and 500s and read directly. No
attempt was made, and none will be, to recover the rule from the site's code — that was
declined on 2026-09-17 and stays declined. **This is observed behaviour only.**

---

## 0. The short version

Three things the recording establishes, and one correction it forces on
`running_up_preflight_RESULT_20260918.md`.

1. **The alert is a stream, not a trigger.** AKAN produced nine alert groups in five minutes,
   several of them marked *"7 in 8sec"* — dozens of individual alerts for one move. **You
   cannot "enter on the Running Up alert", because there are dozens of them.** Whatever picks
   one of them is the actual rule, and that rule is not in the scanner.
2. **It is genuinely selective, and the obvious columns do not explain it.** Two of the
   fourteen names on the Top Gainers board fired. The twelve that did not include names with a
   *higher* five-minute relative volume, a *smaller* float and a *larger* gap than the two that
   did.
3. **It does not fire on new highs.** Consecutive AKAN alerts run 3.64 → 3.56 → 3.64 → 3.69 →
   3.63 → 3.71 → 3.70 → 3.67. Four of those are lower than the alert before them. The
   high-of-day alert is a **separate panel** on the same screen.

**The correction.** The pre-flight tested the Running Up idea as a **per-entry gate** — given a
signal MCL or MC5 already produced, does momentum-at-entry separate the trades that die from
the ones that live? It answered no, and inverted. But the recording shows the intended use, and
Ben said so at the outset: *"run it in conjunction with the watchlist"* — as a **name
selector**, deciding which symbol-days are worth watching at all. **That is a different test
and it has not been run.** The index currently says the line is closed. It is closed as a gate;
it is untested as a universe.

---

## 1. What is on the screen

Five panels, four of them alerting, and the negatives are visible beside the positives — which
is what makes the recording worth more than a list of alerts.

| Panel | What it showed at 06:22:30–06:27:30 |
|---|---|
| **Top Gainers** | 14 names, ranked by change from close |
| **Running Up (Online)** | AKAN repeatedly, IMCC once |
| **Small Cap — High of Day Momentum** | AKAN, IMCC |
| **Ross's 5 Pillars Scan** | IMCC, then IMCC + AKAN — tighter than everything else |
| **Ross's 5 Pillars Alert** | IMCC and AKAN only |

The Running Up columns are Time, Symbol/News, Price, Volume, Float, Relative Volume (Daily
Rate), Relative Volume (5 min %), Gap %, Change From Close %, Short Interest. That is the data
the alert has to work with — **all of it is data this project already has**, except the
sub-minute timing.

## 2. The negatives, which are the informative half

Top Gainers at 06:22:30–06:27:30, with float and five-minute relative volume, **fired names in
bold**:

| | change | price | float | RVOL 5min % |
|---|---:|---:|---:|---:|
| **IMCC** | **133.84** | **4.07** | **471K** | **1,410,705** |
| SSM | 71.92 | 2.51 | 1.19M | 1,278 |
| TCRT | 47.46 | 2.36 | 2.13M | **7,752,365** |
| GIPR | 28.37 | 0.56 | 2.73M | 145 |
| **AKAN** | **24.83** | **3.67** | **477K** | **2,508** |
| DLXY | 19.55 | 1.01 | 11.40M | 24 |
| CPOP | 18.55 | 4.41 | **350K** | 2,643 |
| USDE | 16.34 | 8.97 | 14.46M | 201 |
| BNC | 11.44 | 6.04 | 37.92M | 22 |
| TELO | 10.71 | 1.24 | 35.48M | 5,979 |
| JBS | 10.53 | 13.33 | 436.30M | 0 |
| ZNB | 9.56 | 1.49 | 3.67M | 3 |
| BTCT | 8.62 | 1.26 | 11.79M | 1,012 |
| SPRU | 8.59 | 1.77 | 13.50M | 1,431 |

**TCRT has the highest five-minute relative volume on the board — three orders of magnitude
above AKAN — and it does not fire.** It is also up 47% against AKAN's 25%. **CPOP's float is
smaller than either firing name's** and its five-minute relative volume is higher than AKAN's,
and it does not fire. **TELO's is higher than AKAN's too.**

So the alert is not a relative-volume screen, not a float screen and not a gap screen. Those
columns are context printed beside the alert, not the condition.

What is left is movement **in the last seconds to minutes** — which is what "running up" means,
and it is the axis the pre-flight measured.

## 3. The stream, and why it matters more than the rule

AKAN, 06:23:44 → 06:28:46, one row per alert group:

| time | price | cumulative volume |
|---|---:|---:|
| 06:23:44 | 3.64 | 924.86K |
| 06:24:20 *(7 in 8sec)* | 3.56 | 1.07M |
| 06:24:34 *(4 in 4sec)* | 3.64 | 1.15M |
| 06:26:01 *(2 in 2sec)* | 3.69 | 1.46M |
| 06:26:43 *(2 in 2sec)* | 3.63 | 1.57M |
| 06:26:54 *(3 in 3sec)* | 3.71 | 1.63M |
| 06:27:25 *(4 in 5sec)* | 3.70 | 1.72M |
| 06:28:46 | 3.67 | 1.96M |

A million shares in five minutes on a **477,400-share float** — the float rotated twice in five
minutes, and four times over the session to that point.

Earlier, IMCC ran 4.51 → 4.66 → 4.60 → 4.85 → 4.92 → 5.00 across six alert groups in about
four minutes.

**That IMCC spread is 11%, and the strategies run a 5% trailing stop.** Entering on the first
alert of that stream and entering on the sixth are separated by more than two stop widths. The
alert does not tell you which one to take; the trader does. **Whatever Cameron's skill consists
of, this recording shows that a large part of it is not in the scanner.**

## 4. What this does and does not change

### It does not reopen the gate result

`running_up_preflight_RESULT_20260918.md` stands exactly as written. Momentum at entry
separates MCL's dying trades from its surviving ones with AUC 0.751 **pointing the wrong way** —
the trades that die were entered after a median +11.43% five-minute move against +4.90% for the
survivors. Nothing in this recording contradicts that, and §3 above is consistent with it: a
name that has already alerted six times has already moved.

### It does open two questions that have not been asked

**(a) The alert as a universe, not as a gate.** Ben's framing from the start was that the
scanner would run *beside* the watchlist, with the strategies keeping their own entry
conditions — i.e. it decides **which symbol-days to watch**, not which signals to take. Every
test run so far has been the second kind. The first has never been run, and it is a different
question: it removes whole names rather than individual entries, so the abstention control and
both denominators apply differently.

It is also harder, because "would this name have alerted" is not computable without the rule.
What *is* computable is a stand-in built from the tape — say, a short-horizon volume-and-price
condition on the 1-second bars, which are now known to be free — and the honest version of that
test registers the stand-in's definition before running it and reports it as a proxy, never as
the scanner.

**(b) The ordinal of the alert within its own stream.** Knowable at the time, never tested, and
on IMCC worth 11%. "First alert of a run" and "any alert of a run" are different rules, and the
pre-flight's continuous `ret_5m` threshold is a blunt proxy for the distinction. The prior is
poor — `ret_5m` read 0.751 the wrong way and this is correlated with it — but it is a sharper
cut than a threshold on a continuous feature, and it is the one thing in the recording that
looks like a rule rather than a display.

## 5. What this evidence is worth, stated plainly

**One morning. Two firing names. No way to replay it.** The scanner's history is not available
to us, so nothing here can be measured on 550 sessions the way everything else in this project
is. It is hypothesis generation, in exactly the category the index already puts source videos:
*a live scanner is one too*.

The two questions in §4 need registrations and computable definitions before either is run.
Neither is at the front of the queue: the rebound census and the pullback cell both carry
better-founded priors.

**And it remains the case that no gate can fix these books.** Break-even friction is −$0.96 a
round trip on MCL and −$4.67 on MC5; they lose at zero cost. A better universe is a different
claim from a better gate, which is why §4(a) is worth asking at all — but it is not a rescue,
and it should not be presented as one.
