# Handover — Rec. Model / Rec. Effort columns added (2026-09-23)

**From:** Project management chat · **To:** every Algo Trading chat · **Adds to:** rule 2 and rule 9 of the Project
instructions (rule 9 already asked for this recommendation; it just wasn't recorded as a board field until now).

## What changed

Ben asked for the per-task model/effort recommendation (Project instructions rule 9) to be recorded on the board
itself, not just given in chat. Two new dropdown columns were added to both boards:

| Board | Column | id | Labels |
|---|---|---|---|
| Items (`5031413876`) | **Rec. Model** | `dropdown_mm7f88hx` | Haiku · Sonnet · Opus · Fable |
| Items (`5031413876`) | **Rec. Effort** | `dropdown_mm7fy4k5` | Low · Medium · High · XHigh · Max |
| Subitems (`5031415830`) | **Rec. Model** | `dropdown_mm7fmg58` | Haiku · Sonnet · Opus · Fable |
| Subitems (`5031415830`) | **Rec. Effort** | `dropdown_mm7ftjja` | Low · Medium · High · XHigh · Max |

Backfilled every open item (Status not Done/Dropped — 67 items) and every open subitem (16 items) with a
recommendation, judged from the task's Type and title:

- **Haiku / Low** — hands-on relay steps for Ben, trivial fixes, simple decisions, housekeeping.
- **Sonnet / Low–Medium** — ordinary dev work, data pulls/tagging, reviews, moderate decisions.
- **Opus / High** — rigorous backtests/studies, engine builds, anything where a wrong analysis is costly (e.g.
  W02-0002 MC5-vs-MCL comparison, W03-0004/W03-0005 execution-cost studies, W05-0003 new strategy, W06-0005 TSMOM
  training run, W07-0002 point-in-time universe).

Items already Done/Dropped were left blank — no value in recommending a model for finished work.

## Going forward (addition to rule 2)

When a chat creates a new item (or subitem), it now also sets **Rec. Model** and **Rec. Effort** at creation time,
picking the cheapest model/effort that can do the job well (same judgment as above). This is an addition to the
column list in rule 2 of the Project instructions — see W11-0020 for the exact paste-in text.
