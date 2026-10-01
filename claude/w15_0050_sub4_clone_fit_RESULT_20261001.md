# W15-0050 · CHARTMARK-CLONE — sub 4: fit and fidelity — RESULT

**Date:** 2026-10-01 · **Chat:** Build & test chat (Sonnet 5.5) · **Item:** W15-0050 (2870871640), subitem 4 (2870854970) · **Registration:** `docs/research/REGISTERED_chartmark_clone.md` §8 + Amendment 2 (PRE-RUN). **Labels and chart features only. No price, exit or P&L was read, computed or shown.**

## In plain terms

Your 500 blind labels (155 takes, 345 skips) were enough to fit the clone. A two-rule clone, built from the reasons you gave, reproduces about 61% of the trades you took, and 58% of the trades it takes are ones you took; you took 31% of candidates overall. That meets the registered bar, so by the registered order the rules clone (R) is the clone, and it is now frozen. It meets the bar only because the registered ceiling rule lowers the recall bar to your own consistency on repeats (54%, from just 13 repeated takes). Against the original 75% bar it would miss, and the logistic model (M, frozen beside it) would be the clone. Whether the clone's picks make money is not known yet: that is the one outcome run in sub 5.

## Verdict and what you must do

- **Verdict:** R meets the registered fidelity bar (take-recall 60.6% ≥ 53.8%; take-precision 58.0% ≥ 50%). **R is the frozen clone.** M and M-GB are frozen beside it for the registered variants.
- **Nothing for you to decide.** Sub 5 runs R as the headline and M as V-OTHER, exactly as registered.
- **You must run the commands on subitem 4b** (install scikit-learn, run the tests, commit and push). The frozen clone must be committed before sub 5 runs (§8.4).
- **Labelling is now closed.** The ledger records the label file's SHA-256 and the labelling tool refuses to start. Adding labels would change the frozen clone's inputs.

## 1. The labels

| | |
|---|---|
| Unique candidates labelled | 500 (minimum 500) |
| Takes / skips | 155 / 345 (take rate 31.0%; registered prediction 8–20%) |
| Repeats shown | 40, one sitting, nothing undone, median 3.2 s per decision |
| Skip reasons | 3 chop ×212 · 4 weak momentum ×84 · 7 other ×46 · 1 against trend ×2 · 5 order too far ×1 · 2 and 6 ×0 |
| Take reasons | A fresh momentum turn ×148 · C continuation ×5 · B breakout ×2 |
| Reason 7 share of skips | 13.3% (limit 25%): selection is not mostly outside the list |

Of the 46 "other" notes, 32 say some version of "wait another bar or two to see if it breaks the buy-stop, then enter". That is a confirmation-entry habit that no rule here can express.

## 2. Your own consistency (the ceiling)

| | Again the same | Interval (95%) |
|---|---|---|
| Takes taken again | 7 of 13 = 53.8% | 29.1% to 76.8% |
| Skips skipped again | 26 of 27 = 96.3% | |
| Overall agreement | 82.5% (33 of 40) | |

Registered bars: recall ≥ min(75%, 53.8%) = **53.8%**; precision ≥ **50%**.

## 3. Fidelity (5 × repeated stratified 5-fold CV, out of fold; mean of 5 repeats, range in brackets)

| Clone | Take-recall | Take-precision | Agreement | Kappa | Clone take rate | Registered bar |
|---|---|---|---|---|---|---|
| Always take (reference) | 100.0% | 31.0% | 31.0% | 0.000 | 100% | n/a |
| **R rules** | **60.6%** [57.4–61.9] | **58.0%** [57.8–58.2] | 74.2% | 0.404 | 32.4% | **MET** |
| M logistic | 95.6% [94.2–97.4] | 54.9% [53.5–55.7] | 74.3% | 0.501 | 54.0% | MET |
| M-GB boosting | 92.9% [87.7–96.8] | 51.3% [50.3–52.3] | 70.4% | 0.435 | 56.2% | MET |

Against the **uncapped 75% recall bar** (sensitivity, not a criterion): R **not met**, M met, M-GB met.

R confusion (mean of 5 repeats, 500 candidates): both take **94.0** · clone takes, you skipped **68.2** · clone skips, you took **61.0** · both skip **276.8**.

Sampling noise on R's headline (computed after the freeze, Wilson 95%): recall 52.8% to 68.0%, precision 50.3% to 65.4%. The lower end of recall is below the 53.8% bar.

Share of your skips of each reason that the clone also skips (out of fold): R: reason 3 80.8%, reason 4 96.7%, reason 7 48.3% · M: reason 3 64.5%, reason 4 81.2%, reason 7 39.1%.

## 4. The frozen clone (R)

| Rule | Skip when | Catches (your skips of that reason) | Also catches (your takes) |
|---|---|---|---|
| Reason 3, chop / quiet | F10 > 0.95: all of the last 10 bars traded below their 20-bar average volume | 65.6% of 212 | 28.4% of 155 |
| Reason 4, weak momentum | F5 < 0.0533: the MACD histogram rose by less than 0.053 ATR over the last 2 bars | 86.9% of 84 | 12.3% of 155 |

No rule for reasons 1, 2, 5, 6 (fewer than 15 uses) or 7 (not coded). The clone takes a candidate only if neither rule fires.

**What the chop rule really is.** F10 compares each bar with a 24-hour volume average, so it is mostly a time-of-day marker. It fires on 86.7% of London-session candidates and on 15% of US-morning ones. Result: you took 21% of London candidates, 42% of US-AM and 38% of US-PM; R takes 8%, 55% and 66% of them in-sample. R is in effect "mostly skip London, and skip when momentum is flattening".

## 5. What the labels say (labels only)

- Take rate by year: 2010 27% · 2011 33% · 2012 35% · 2013 29% · 2014 22% · 2015 24% · 2016 24% · 2017 41% · 2018 33% · 2019 27% · 2020 33% · 2021 40%.
- Up daily trend 31.6%, down 30.2%: the daily trend (F1) did not separate your choices.
- Take rate fell from 35% in the first 100 labels to 27% in 400–499 (mild fatigue drift).
- Famous windows (2014 collapse, 2020 crash): 25.6% on 39 candidates vs 31.5% on the other 461. No sign of recognition-driven choices.

## 6. Registered predictions (§16) vs what happened

| Prediction | Actual |
|---|---|
| You take 8–20% | 31.0% (outside) |
| Consistency on repeated takes 60–80% | 53.8% (outside; 13 observations) |
| Rules clone meets the bar, about 40% | Met, under the capped bar |
| Most-used skip reasons 3 and 1 | 3 and 4 (reason 1 used twice) |

## 7. Method

R is fitted first; each skip reason with ≥ 15 uses gets one rule on its registered features, threshold by Youden's J on the training fold. M is a standardised L2 logistic regression with C and the threshold chosen by inner 5-fold CV on the F2 score; M-GB is gradient boosting. Metrics are computed per repeat on pooled out-of-fold predictions and averaged. The final refit uses all 500 first labels. Interpretations I10–I22 were fixed in Amendment 2 before the fit was run. Guards: F1–F15 truncation invariance, a one-bar shift that must break it, and the same check on 40 real archive candidates (0 mismatches); 63 clone tests pass in my workspace (38 earlier + 25 new).

## 8. Caveats

- 13 repeated takes make the ceiling, and so the bar, soft. R's recall interval reaches below the bar.
- F10 is a time-of-day proxy (see §4). It is the registered definition.
- The 31% take rate and 54% consistency are outside what was predicted: you take more candidates than expected and repeat your takes less reliably, which caps how closely any clone can follow.
- Your habit of waiting for a confirming bar (32 notes) is outside the clone and outside this registration.
- Nothing here says the clone's picks make money; v1's entries lost before costs.

## 9. Source files

`D:\Trading\Claude outputs\clone_fit_report_w15_0050.txt` (raw report; copy in `docs/research/clone_w15_0050/`) · `clone_frozen_w15_0050.json` · `clone_features_w15_0050.csv` · `clone_fit_results_w15_0050.json` · `clone_ledger_w15_0050.json`.
Hashes: labels `50f073c3e2f0024e7c650709873a29042d3d82207ac6b36e21bf0869e4d433a6` · frozen clone `5eee53738325ad5320a89b33b47ce3fa607a3f94d3f01ad50b41544869e03a77` · queue `d5e0b0277dfa211925e5ddc73ae1e0dfef2d68fb9b9b11ccdfeb84c2b5584af0`. Code: `strategy/chartmark_clone/{features,clone,fit}.py`; tests `tests/strategy/chartmark_clone/test_{features,clone,freeze}.py`.

## Next steps (board)

- **W15-0050 sub 4** — Build & test chat: fit, fidelity, freeze. **Done.**
- **W15-0050 sub 4b** — Ben: `pip install scikit-learn`, run the tests, commit + push. Commands on the subitem and the parent.
- **W15-0050 sub 5** — fresh Build & test chat (Sonnet / High), after 4b: G6 gate parity, then the one outcome run → Result doc.
- **W15-0050 sub 6** — Ben: forward paper or close, after sub 5.
