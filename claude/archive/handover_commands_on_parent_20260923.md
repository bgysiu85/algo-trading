# Handover — commands: full sequence also on the parent item (2026-09-23)

**From:** Project management chat · **To:** every Algo Trading chat · **Adds to:** rule 7 ("commands on the board")
of the Project instructions. Confirms rule 7 already covers the base request; this only adds the parent-item copy.

## What was already in force (rule 7, since 2026-09-20)

Any step needing commands run carries the exact commands on the board, posted as an Update **on that step's
subitem** (or on the item itself if it has no subitems), inside `<pre>…</pre>` — copy-paste PowerShell, one command
per line, full absolute paths, a one-line "what this does" before and "what to report back" after.

## What's new (Ben, 2026-09-23)

When a task **has subitems**, each subitem's Update still carries only that step's own commands — but the **parent
item** now also gets an Update with the **full end-to-end command sequence** (every step's commands, in order, in
one `<pre>` block), so Ben can run the whole task start-to-finish from the parent item alone, or work through the
subitems one at a time — his choice. This doesn't replace the per-subitem commands; it's in addition to them.

## Addition to rule 7 (paste-in text)

Append to the end of rule 7:

> When the task has subitems, each subitem's Update carries only that step's own commands as before. The **parent
> item** also gets its own Update with the **full end-to-end command sequence** — every subitem's commands
> concatenated in order, in one `<pre>` block — so Ben can run the whole task from the parent alone instead of
> hopping between subitems. Keep both in sync: if a subitem's commands change, update that subitem's Update **and**
> regenerate the parent's full-sequence Update.
