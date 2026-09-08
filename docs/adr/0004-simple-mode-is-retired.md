# ADR 0004 — Simple mode is retired

**Status:** Accepted (2026-09-08)
**Supersedes:** `CONTEXT.md` invariant 9 ("Simple mode is a sharing behaviour, not only a UI preference")
**Project:** [BG: Shopping Lists](https://linear.app/neuroticsasquatch/project/bg-shopping-lists-6fdd1e4a3cc1)

## Context

Simple mode existed for the older user sharing a login who should not have to understand sharing. It
did six things:

| Surface | Behaviour | Where |
|---|---|---|
| Auto-grant | New lists granted to every family; joining a family grants existing lists; manual grant/revoke 403s | `list_families/service.py:12,78,95` |
| Folders | "Add to an occasion…" hidden, owner and viewer alike | `ListDetail.tsx:74` |
| People tab | Dropped from nav, demoted into the account dropdown | `Layout.tsx:68,120` |
| Lists controls | Occasion filter, sort control, archive toggle hidden | `Lists.tsx:46` |
| Sharing summary | Read-only "Shared with your families" | `SharingSummary.tsx:24` |
| Create form | Family checkbox group hidden | `CreateList.tsx:30` |

Only the first is a behaviour. The other five are subtractive UI, and the auto-grant is precisely
what made hiding the sharing control *safe*: a simple-mode user's list reached their family whether
or not they understood that it had.

[ADR 0002](0002-family-shares-target-an-occasion.md) removes that safety, because a list can no
longer be granted to a family that has no active occasion — there is nothing unambiguous to
auto-grant *to*. Simple mode had to be reconciled with the new sharing model regardless of whether
it survived.

Three of the five subtractions also stopped making sense on their own terms. Folders are being
opened to every user, because family occasions now handle the easy case and a folder is no longer an
advanced feature. The occasion filter becomes the Lists dashboard's primary grouping control rather
than an advanced toggle. And the read-only sharing summary describes an auto-grant that no longer
happens.

## Decision

**Delete simple mode.** `users.simple_mode`, `family_invites.simple_mode`, the JWT claim
(`dependencies.py:42`), the auto-grant, the 403s on manual grant/revoke, all frontend gates, and the
account-page toggle.

Its one real job is replaced by a **default**, not a mode:

- Family share checkboxes arrive **pre-checked** for every family the user belongs to that has
  exactly one active occasion.
- A list shared with nobody says so, on the list itself: *"This list isn't shared with anyone."*

## Consequences

**Good**

- One variant per surface. Every screen this project adds — the occasion picker, folders, budgets,
  the per-occasion shopping tab, the archive views — would otherwise need a simple-mode version and
  a simple-mode test. This is the decisive argument: **keeping simple mode costs more than removing
  it**, and the cost is paid per ticket, forever.
- An entire class of divergence bug disappears — a surface reachable in one mode and orphaned in the
  other, which is what frontend ADR 0001 (`docs/adr/0001-one-place-for-every-list-shared-with-me.md` in the frontend repo)
  was already fighting.
- Every user gets folders, the archive view, and grouping, rather than having them hidden on their
  behalf.

**Bad, and accepted**

- **A naive user can now create a list that reaches nobody**, by unchecking the pre-checked boxes or
  by belonging to no family with an active occasion. The auto-grant made that impossible. The empty
  state is the whole mitigation, and it has to actually be built — it is not a nice-to-have.
- Users invited in simple mode lose a setting they may have been told about. Nothing breaks; the
  controls they never saw simply appear.
- If the older users this was built for turn out to need it, bringing it back means re-deriving what
  to hide against a UI that has moved on. The pre-checked default is the cheaper half of the
  protection and it survives; only the hiding is gone.

## Alternatives rejected

- **Keep it, narrowed to pre-checking and hiding the People tab** — half the deletion, but every new
  surface still has to answer "and in simple mode?", which is the cost we are trying to stop paying.
- **Leave it untouched this project** — smallest immediate scope, but it does not survive contact
  with ADR 0002: the auto-grant has no unambiguous target once shares point at occasions, so simple
  mode's one real behaviour has to be rewritten anyway. Rewriting it in order to keep it is the
  worst of both.
