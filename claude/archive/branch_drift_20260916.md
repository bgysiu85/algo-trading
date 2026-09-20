# Production is running two-day-old code, and `main` is not the branch

**2026-09-16.** Found while checking why the 1c rerun hadn't happened. Not a
tidiness problem — three trader fixes shipped this morning are in neither
place that matters.

## What the repo actually looks like

`D:\Trading` is checked out on **`portal-on-prod`**, not `main`. Every bundle
since 2026-09-14 has been merged into that branch.

| ref | at | date |
|---|---|---|
| `portal-on-prod` (HEAD) | `9680c05` | 2026-09-16 |
| `main` | `e1a11b9` | 2026-09-14 |
| `origin/main` (GitHub) | `e1a11b9` | 2026-09-14 |
| `prod-20260914d` (latest prod tag) | `bbae2bb` | 2026-09-14 17:32 |

`git log HEAD..main` is **empty** — `main` is a strict ancestor, so nothing is
lost and the repair is a fast-forward with no merge and no conflict. But the
diff the other way is **60 files, +16,395 lines**.

This also violates the standing rule in its own words: *one branch, work on
`main`, production is a TAG and a second working copy, never a branch.* There
is a branch called `portal-on-prod`.

## The part that is not cosmetic

Production runs from a second working copy at `prod-20260914d`. Checked
directly with `git merge-base --is-ancestor`, these three are in **neither**
that tag nor `main`:

| commit | what it fixes |
|---|---|
| `971e88a` | **the exit does not wait out `ORDER_TIMEOUT_S` when its limit cannot fill** |
| `9fa812a` | the price band, `ref_drift_pct`, and a CONFIG row that does not need the portal |
| `5cbe8a7` | one bad ticker (PSNYW) stopped the watchlist reloading |

The first is the CRBP fix. On 2026-09-14 the trail fired at 07:02:10, the
order sat the full twenty seconds while the stock fell 42%, and the round trip
cost **$241.37 — 46% of that week's two-day loss**. The live trader still has
that behaviour.

The second means the fill log gains a column and **rolls aside on the next
session**, whenever the deploy happens. Expected, not a fault.

## Why this was invisible

Every merge commit reads `Merge branch 'main' of ...bundle into
portal-on-prod`. The words "branch 'main'" name the branch *inside the
bundle*, not the branch being written to — so the log of a repo whose `main`
has not moved in two days is full of lines that appear to say `main` was just
updated. **Two things with the same name that are not the same thing**, which
is this project's recurring shape wearing git's clothes.

The bundles themselves were never wrong: each is built from `main` in the
cloud repo and carries full history. Nothing needs re-cutting.

## The repair

1. Merge the outstanding bundle on `portal-on-prod`.
2. `git checkout main` and `git merge --ff-only portal-on-prod` — clean, since
   `main` is an ancestor.
3. `git push origin main`, so GitHub stops being two days behind.
4. Work on `main` from here, per the standing rule.
5. Cut a new prod tag and update the production working copy — **Ben's call
   whether that happens before tonight's session.** The suite is at 2,747
   passed, 4 skipped.

`portal-on-prod` is then redundant and can be deleted once `main` carries it.
