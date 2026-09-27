# ORB — symbols, or days? (amendment G, 2026-09-19)

Registration: `docs/research/REGISTERED_orb_sip.md` **amendment G**, committed with its bar and its prediction before the measurement ran. Raw: `var\reports\orb_sip_carrier.txt`. Bundle: `orb-20260919b.bundle`. Nothing bought, no gate applied.

**My prediction was wrong and is recorded as wrong.** The market-context gate in `handover_orb_build_chat_20260918.md` §5 earns a registration.

## Why this was asked

The book is +4.8R over 7,239 trades and turns on five symbols (MWA +56.9R, TD +51.9R, NYT +51.5R, IONS +51.2R, THC +50.8R), with drop-top-1 at (52.1)R. A market-context gate switches whole **sessions** on and off, so it can only reach that concentration if the concentration lives in **days**. If the carrying trades were single names doing single-name things on unrelated sessions, no market-wide rule could touch them at any threshold, and the gate would be dead before it was written.

## The primary reading (G.3)

Carrier trades are the N largest by net R; carrier days are the sessions they land on. The carrier trades themselves are excluded from both sides — a gate takes the whole session or leaves it, so what it could trade is **the rest**.

| N | carrier days | rest of book | all other days | lift | bar +0.10R |
|---:|---:|---:|---:|---:|---|
| 20 | 20 | **+0.274R** (299) | (0.134)R (6,920) | **+0.408R** | MET |
| 50 | 48 | **(0.076)R** (719) | (0.254)R (6,470) | **+0.178R** | MET |

Both clear the bar, at both pre-stated N. **Day-level structure exists in this book.** The days that produced the biggest winners were better days for everything else traded on them.

## The supporting reading (G.4)

| N | distinct days | null mean | null p05 | p | |
|---:|---:|---:|---:|---:|---|
| 20 | 20 | 19.6 | 18.0 | 1.000 | no clustering |
| 50 | 48 | 47.4 | 45.0 | 0.742 | no clustering |

2,000 permutation draws from the same ledger, seed 20260916, so the null inherits the real trades-per-session distribution. The carriers do **not** share days beyond chance — each big winner sits on its own session. G.5's secondary prediction holds.

That combination is the interesting part: the big winners don't cluster with each other, but the days they fall on are systematically better for the rest of the book.

## What this does NOT license, stated before anyone quotes the +0.408R

**1. The measurement is conditioned on the outcome.** Carrier days were selected *because* they contained a huge winner. "Days that produced a giant winner were also good days" is not the same claim as "an observable variable identifies those days at 09:45." G measured the first. Only a registered gate can test the second.

**2. The gate's registration must carry a shuffled-day control.** The honest null is: permute trades' day labels, keeping each session's trade count, then re-select carriers and recompute the lift. Under that null there is no day structure, so any remaining lift is pure selection artifact. **This is a requirement on the gate's registration, not a retroactive addition to G** — G is reported exactly as it was registered, per the `breadth_RESULT_20260916` precedent that a criterion is not added after seeing a result.

**3. The practical bar is severe, and G's own table says so.** At N=50 the rest of the book on carrier days is **still negative** at (0.076)R. Only the top 20 sessions come out positive. **A gate would have to identify roughly the best 4.5% of sessions (20 of 446) to make the rest of the book profitable at all.** No market-context variable in the four failed precedents operated at anything like that precision.

**4. It does not address concentration.** The handover's §2 test stands unchanged: a proposal that improves the mean without improving drop-top-N has not addressed the failure. G measured a mean. The gate must be scored on drop-top-N within bucket, date-level, never pooled — as §5 already specifies.

## Status of the ORB levers

| lever | status |
|---|---|
| **Stop width** (amendment F) | **Closed permanently.** Winners reach a median 0.63R against them, losers 5.51R. Rescuable losers 9.1% against a 25% gate. |
| **Market context** (§5) | **Earns a registration.** Not adopted, not run. Its own pre-stated prior still expects NOT ADOPTABLE, and it now also carries the three requirements above. |
| **Volume confirmation on the break** (§5, second candidate) | Untouched. Registered separately if at all — a two-filter grid on a book this concentrated is a search, not a test. |
| Verdict, universe, ranking, criteria, holdout | Unchanged. 1 of 7. `holdout.json` unspent. |

## A correction to amendment F's wording

F.3's consequence sentence read *"ORB closes permanently. No variant is registered."* F.5 in the same amendment read that F *"does not touch the universe, the ranking, the **filters**…"*. A market-context gate is a filter, so those two sentences conflicted. Recorded in G.0 rather than resolved silently: **F measured stop width and closes stop width.** A measurement cannot close a hypothesis it never tested. The error was mine.

## For PROGRAM_INDEX

- **ORB: the stop lever is closed; the market-context lever is open and unregistered.** Do not read "ORB is closed" without reading which lever.
- New standing fact: **on this book, the sessions carrying the biggest winners are better sessions for everything else traded on them** — the rest of the book reads +0.274R on the top-20 days against (0.134)R elsewhere. Day-level structure exists. It is measured conditional on the outcome and is not itself tradeable.
- New standing fact: **the carriers do not share days.** 20 largest trades, 20 distinct sessions, against a null mean of 19.6. Concentration by symbol and clustering by day are separate questions and this book has the first without the second.
- Method note: **G registered a bar at two pre-stated sample sizes, with a split declared a refusal in advance.** That construction is what stops a reading being taken from whichever cut falls the convenient side of the line.
