# Green day attribution — 2026-09-16 paper session

Question (Ben): was the first green day the market, or the execution changes promoted that morning?

**Answer: the market (the watchlist's names), not execution.** Swing against the 09-09..09-15 average over 19 trades was +374: **+344 from the market move** (exit reference − signal close) and **+30 from execution legs**, none of it through code that changed.

| $/trade | market | entry | exit | comm | net |
|---|---:|---:|---:|---:|---:|
| 09-09..09-15 (n=115) | (2.92) | 2.42 | (6.60) | (1.37) | (8.48) |
| 09-16 (n=19) | 15.18 | 2.48 | (5.08) | (1.37) | 11.21 |

- Net 212.95 (MEDS 06:16 ghost position excluded, exit price unknown). Top 3 trades = 272.87: FTFT MCL +100.62 and FTFT MC5 +86.62 (both window_close 09:30), MEDS MC5 06:11 +85.63. Ex-top-3: (59.92)/16.
- Trailing-stop exit slippage median (0.0263)/sh vs (0.0295) prior. Entry spread median 0.391% vs 0.382%. Bootstrap from the prior 115 trades: P(19-trade net ≥ 212.95) = 0.045%.
- Promoted (prod-20260914d → prod-20260916b): 971e88a exit-abandon **engaged once = the MEDS ghost** (harmful); 9fa812a price band never used (0 rejections), drift/CONFIG logging only; 5cbe8a7 watchlist guard, no measurable effect; 55615ef/9d58397 no live effect. The 19 recorded round trips would have been identical under the old code.
- Market: IWM fell on 09-16 (open 285.63 → close 283.92). Watchlist gaps (open vs prior close): MEDS +149%, RETO +61%, FTFT +22%, NAMI +19%, VEEA (4%), MYSZ (19%). This was the largest runner of any session. Gap size alone doesn't predict (09-11 had six names > +20% and lost), so the key was trend persistence in the top names.
- Confidence: strong that execution didn't cause it; moderate that it was the opportunity set (1 session, 3 trades carried it).
- To firm up: replay MCL/MC5 unchanged on Databento 2026-09-16_0400_0930 (not pulled yet); add the MEDS exit from IB's statement; watch the exit leg on ordinary days.

Report: `D:\Trading\Claude outputs\green_day_attribution_20260916.txt`. Artifact page published.
