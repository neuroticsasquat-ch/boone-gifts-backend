# NEU-1321 — The occasion heading names its family

**Ticket:** [NEU-1321](https://linear.app/neuroticsasquatch/issue/NEU-1321/family-name-isnt-visible-anywhere-on-occasion-page-header)
**Repos:** `boone-gifts-backend` **and** `boone-gifts-frontend` — one ticket, two halves. This file is
checked in to both, identical, because either repo's `/implementit` must find the whole story.
**Project:** Boone Gifts: Maintenance. **No milestone, no project description, no project spec** —
the Maintenance project carries none, so there are no shared contracts to honour beyond the two
`CONTEXT.md` files and the ADRs named below.
**Story / parent:** none. **Blocked by:** nothing. **Blocks:** nothing. **Related:** nothing.
**Nearest project-spec text:** `docs/specs/occasions-and-navigation-project-spec.md` §9.2, which
describes `/occasions/:id` in three sentences and says nothing about the heading. It does not cover
this ticket; this file is the spec.
**Branch from and target:** `release/v0.6.0` in **both** repos — not `main`.

## What to build and why

`frontend/src/pages/OccasionDetail.tsx` renders the page's heading as `<h1>{occasion.name}</h1>` —
"Christmas 2026", and nothing else. The family that owns the occasion is named in exactly one place
on the page: the `BackControl`, through `backToFamily(occasion.family_id, family.data?.name)`.

That control only prints its fallback label at navigation **depth 0**. At depth > 0 it renders
`← Back` by design (`CONTEXT.md` rule 9 — "a generic label that is always true beats a specific one
that is sometimes a lie"). So:

| How the viewer arrived | Depth | Family name on screen |
|---|---|---|
| Occasion strip on `/lists` | > 0 | **nowhere** |
| An occasion group heading under *Shared with me* | > 0 | **nowhere** |
| The family page's Occasions section | > 0 | **nowhere** |
| The archive nudge in `ActionableBanner` | > 0 | **nowhere** |
| Cold deep link / reload / new tab | 0 | `← Boone Family` |

Every route a viewer actually takes to this page is a depth > 0 route. The one case that shows the
family name is the one nobody navigates.

**This is the page breaking a convention the rest of the app already keeps.** Three surfaces name an
occasion the same way, and all three say why:

- `lib/list-grouping.ts:45` defines a `qualifier` field for precisely this — *"A plain prefix ahead
  of the heading, never linked. Only an occasion has one: the family, without which the occasion
  name does not identify one occasion."* `Lists.tsx:352` renders it as `Boone Family · Christmas 2026`.
- `lists/OccasionStrip.tsx:176` prints `family_name` under the card name: *"Not decoration: two
  families routinely both call an occasion 'Christmas 2026', and the name alone does not identify one."*
- `list-detail/SharingSummary.tsx` prints `Boone Family · Christmas 2026`.

And both domain models already assert the canonical rendering as settled vocabulary:
`backend/CONTEXT.md:22` — ***Occasion** | A family's shared gifting occasion — "Boone Family ·
Christmas 2026"* — as does `backend/app/models/occasion.py`'s own docstring. The frontend
`OccasionDetail` docstring even claims the page shows `A family occasion — "Boone Family · Christmas
2026"`. It never has.

So the fix is not an invention. It is making the occasion page's heading read the way every heading
pointing *at* it already reads, and the way both `CONTEXT.md` files already say an occasion is named.

## What to change

### `boone-gifts-backend`

| File | Change |
|---|---|
| `app/schemas/occasion.py` | **New** `OccasionDetailRead(OccasionRead)` adding `family_name: str` |
| `app/occasions/service.py` | `_require_member` returns `tuple[Family, FamilyMember]`; `_load_for_member` forwards the family; `get_occasion` returns `tuple[Occasion, Family]` |
| `app/occasions/router.py` | `GET /occasions/{occasion_id}` → `response_model=OccasionDetailRead`, composed as `create` already composes its extra field |
| `tests` | The detail endpoint carries `family_name`; `PUT` still does not |

### `boone-gifts-frontend`

| File | Change |
|---|---|
| `src/types/index.ts` | **New** `OccasionDetail extends Occasion { family_name: string }` |
| `src/api/occasions.ts` | `getOccasion` returns `OccasionDetail` |
| `src/pages/OccasionDetail.tsx` | The `<h1>` gains the qualifier; the rename form gains it as static text; `backToFamily` gets `occasion.family_name`; `useTitle` gains it |
| `src/pages/OccasionDetail.test.tsx` | New cases below |
| `CONTEXT.md` | Rule 3 and the **Occasion** row — **already edited**, see below |

## Decisions

### 1. The family is an unlinked qualifier *inside* the `<h1>`

The heading reads `Boone Family · Christmas 2026`, family first, separated by ` · `, the family half
plain grey text and unlinked, the occasion half the ordinary heading weight.

This is `CONTEXT.md` rule 3 applied verbatim: *"An occasion heading names its family as an unlinked
prefix."* The rule was written for the Group-by heading, whose link's destination **is this page** —
so the heading the viewer clicked and the heading they land on now read identically, which is the
whole point of a qualifier that identifies one occasion among several with the same name.

Unlinked, specifically, for the reason ADR 0007 gives: the link on an occasion heading goes to the
occasion, and the family is a *label* there, not a destination. The family already has its
destination on this page — the `BackControl` directly above the heading — and a second link to the
same place two lines apart is the redundancy rule 3 avoids.

Rejected: **a grey subtitle beneath the `<h1>`**, matching the `OccasionStrip` card. It is the
surface most viewers arrive from, so the parallel is tempting, but a card's name is not a page's
heading — the card is one of fifteen and reads top-to-bottom as a block, while the `<h1>` is the
page's identity and a screen reader announces it as one string. `Boone Family · Christmas 2026`
announced whole is the identification; a name plus a detached line below it is not.

Rejected: **a linked eyebrow above the `<h1>`**, which contradicts rule 3's "unlinked" and
duplicates the `BackControl`.

### 2. `family_name` comes off the occasion payload, not a second request

`GET /occasions/{id}` gains `family_name`. The frontend reads `occasion.family_name` and does not
derive the heading from the page's `family` query.

The page **does** already hold a family query — `getFamily(occasion.family_id)`, for the organizer
gate — and it is already unconditional, so reusing its name would have cost no extra request. It was
still rejected, because the two queries are **strictly sequential**, not parallel:

```
OccasionDetail()          → useQuery(["occasion", id])
  if (occasion.isPending) return <Spinner />   ← the page is a spinner until this lands
  return <OccasionPage occasion={occasion.data} />
                          → useQuery(["family", occasion.family_id])   ← only fires now
```

`OccasionPage` — which owns the family query — does not mount until the occasion has resolved. So
the family name lands a **full round-trip after the `<h1>` has already painted**, every visit, not
as a race that sometimes goes the other way. With the qualifier at the *start* of the heading, that
means the page reliably paints `Christmas 2026` and then shoves it sideways to make room for
`Boone Family · `. The one exception is arriving from the family page, where `["family", id]` is
already cached.

Worse, the `backToFamily` precedent on this same page shows what the alternative actually looks like
in the interim: it prints the placeholder `Family` until the real name arrives. A heading that reads
`Family · Christmas 2026` for a round-trip is not an improvement on one that reads `Christmas 2026`.

### 3. The backend change costs **zero** extra queries

`_require_member` already loads the Family row and throws it away:

```python
def _require_member(db, family_id, actor) -> FamilyMember:
    family = families_repo.get_family(db, family_id)      # ← already fetched
    if family is None:
        raise NotFoundError("Family not found.")
    membership = families_repo.get_family_member(...)
    ...
    return membership                                      # ← family discarded
```

Every occasion read already pays for this row, on the existence check. So `family_name` is a field
the endpoint can already answer from data in hand: widen `_require_member` to return
`tuple[Family, FamilyMember]` and let `_load_for_member` forward it.

Five call sites, and the churn is small: lines 49, 68 and 81 discard the result already, and only
lines 124 and 256 bind `membership` and need an unpack.

Rejected: **a `family` relationship on the `Occasion` model.** The model carries no relationships at
all today and its docstring is pointed about what it deliberately does not carry; adding lazy loading
to serve one string, when the row is already loaded a few frames up the stack, buys nothing.

Rejected: **a second `get_family` call inside `get_occasion`**, which is one duplicate query for
something already fetched.

### 4. A sibling schema, not a field on `OccasionRead`

`OccasionDetailRead(OccasionRead)` adds `family_name`, leaving `OccasionRead` alone.

`OccasionRead` is the response model for **four** endpoints — the family occasion list, the detail
read, the update, and (through `OccasionCreateRead`) the create. Putting `family_name` on the base
would oblige all four to resolve it, including `GET /families/{family_id}/occasions`, where the
family is already named by the route and the field would be pure redundancy bought with a join.

`OccasionSummary` keeps its own `family_name` declaration and stays a **sibling** of
`OccasionDetailRead`, both extending `OccasionRead`. The duplicated line is deliberate: the index and
the detail read are separate contracts with separate callers, and collapsing them into an
inheritance chain to save one field declaration would couple the strip's payload to the page's.

### 5. `PUT` keeps returning `OccasionRead`, and that is safe because of how the client renames

The update endpoint is unchanged — no `family_name` on its response. This is safe only because the
rename mutation *invalidates* rather than writes:

```ts
const renameMutation = useMutation({
  mutationFn: (newName) => updateOccasion(occasion.id, { name: newName }),
  onSuccess: () => { invalidate(); ... },   // invalidateQueries(["occasion", id]) → refetch
});
```

The `PUT` response never enters the `["occasion", id]` cache entry, so its narrower shape cannot land
where the page expects an `OccasionDetail`.

**This is a constraint on the implementation, not a note.** An implementer who "optimises" either
mutation on this page to `setQueryData(["occasion", id], response)` would write an object with no
`family_name` into the cache and blank the qualifier until the next refetch. If that optimisation is
ever wanted, `PUT` must gain `OccasionDetailRead` first. The same applies to the archive toggle,
which shares `invalidate()`.

### 6. The rename form keeps the qualifier, as static text

Opening the rename form today replaces the entire heading row with the input. With the qualifier in
the `<h1>`, that would make the family name vanish from the page again the moment an organizer starts
typing — this ticket's own bug, re-created in a transient state, and at depth > 0 the `BackControl`
above reads only `← Back`, so there is nothing left to fall back on.

So the form renders `Boone Family · ` as plain text ahead of the input. It also says something true
and useful: the edit covers the occasion half of the heading and not the family. The input still
holds only `occasion.name`, still submits only `occasion.name`, and keeps its `sr-only` label
`Occasion name`.

The cost is input width on a narrow screen, which the existing `flex-1` on the input absorbs.

### 7. The `BackControl` on this page gets the real name immediately

`backToFamily(occasion.family_id, family.data?.name)` becomes
`backToFamily(occasion.family_id, occasion.family_name)`.

Same bug, same cause: at depth 0 the control currently reads `← Family` for a round-trip before it
reads `← Boone Family`. With the name on the occasion payload the placeholder is simply never needed
here.

`backToFamily`'s signature does **not** change and its `name: string | undefined` parameter stays —
`FamilyArchive.tsx:50` still calls it with `family.data?.name` and still needs the `Family`
placeholder and the reasoning in its docstring. Only this one argument changes.

### 8. The document title gains the family too

`useTitle(occasion.data?.name ?? "Occasion")` becomes the qualified string, so two families'
Christmas 2026 tabs stop being indistinguishable — the ticket's complaint, applied to the browser tab.

Note the call site: `useTitle` sits in `OccasionDetail`, **above** the pending/error guards, where
`occasion.data` is still `OccasionDetail | undefined`. The `?? "Occasion"` fallback is load-bearing
and stays; the qualified string is only built when `occasion.data` exists.

### 9. The page's `family` query stays

It is still needed: the organizer gate reads `family.data?.members`, which `family_name` does not
replace. Nothing about this ticket makes that query removable, and removing it would break both
`canRename` and `canArchive`.

### 10. Separator and order are not open questions

`Boone Family · Christmas 2026` — family first, `·` (U+00B7) with a space either side. Taken from
`list-grouping.ts`'s `headingText`, `Lists.tsx:352`, `SharingSummary.tsx`, and both `CONTEXT.md`
files. No new formatter is introduced for a two-part string used once per page; if a third page ever
needs it, that is when it earns a helper.

### 11. Archived occasions are unchanged

An archived occasion renders exactly like an active one (project spec §5.4), and the `Archived` pill
keeps its current position beside the occasion name. The qualifier goes ahead of the name, so the
order is `Boone Family · Christmas 2026  [Archived]`.

## `CONTEXT.md` edits

**Already applied** to `frontend/CONTEXT.md` during this session:

1. The **Occasion** vocabulary row now names the family, matching `backend/CONTEXT.md:22`, which
   already said `"Boone Family · Christmas 2026"` while the frontend's copy said `"Christmas 2026"`:

   > | **Occasion** | A family's shared gifting occasion — "Boone Family · Christmas 2026". The unit
   > a list is shared *to*, and the only thing that makes a family shareable. **Always named with its
   > family**, on its own page's heading exactly as in every heading that points at it — two families
   > routinely both call one "Christmas 2026" |

2. Rule 3 now says the page's own heading is the same heading, under the same rule:

   > The occasion **page's** own heading is that same heading once the viewer has arrived, so it reads
   > the same way and from the same rule — the family qualifies it, unlinked, and only the occasion
   > half is editable (NEU-1321).

`backend/CONTEXT.md` needs **no** edit. Invariant 9 already governs occasion ownership and the
vocabulary row already asserts the canonical rendering; this ticket makes the API match a statement
the domain model had already made.

**No ADR.** This decides nothing new — it applies rule 3 and ADR 0007 to the one page that was
missing them. ADR 0002 and ADR 0007 are unaffected.

## Acceptance criteria

1. `GET /occasions/{id}` returns `family_name` alongside the existing `OccasionRead` fields, for any
   member of the occasion's family.
2. It does so with **no additional database query** versus today.
3. `GET /families/{family_id}/occasions`, `PUT /occasions/{id}` and `POST` responses are byte-for-byte
   unchanged.
4. 403 and 404 on the detail endpoint are unchanged, and neither leaks a family name.
5. The occasion page's `<h1>` reads `Boone Family · Christmas 2026` on its **first** paint — no
   interim paint without the qualifier, at any navigation depth, with a cold cache.
6. The family half of the heading is not a link, and is visually subordinate to the occasion name.
7. Two occasions in different families both named "Christmas 2026" have visibly different headings.
8. With the rename form open, the heading row still shows `Boone Family · `, and the input contains
   only the occasion name.
9. Saving a rename updates the occasion half and leaves the qualifier intact.
10. At depth 0 the back control reads `← Boone Family` on first paint — never `← Family`.
11. The document title reads `Boone Family · Christmas 2026`; it is `Occasion` while the occasion is
    pending.
12. An archived occasion reads `Boone Family · Christmas 2026  [Archived]`.
13. `FamilyArchive`'s back control is unchanged and still shows `Family` before its name resolves.

## Tests

**Backend**
- `GET /occasions/{id}` as a family member → `family_name` is the family's name.
- The same response still carries every `OccasionRead` field.
- A non-member → 403, and an unknown id → 404, both with no body change.
- `PUT /occasions/{id}` response has **no** `family_name` key — the guard on decision 5.
- `GET /families/{family_id}/occasions` response shape unchanged.
- A query-count assertion around the detail endpoint if the suite has a mechanism for one; otherwise
  decision 3 is enforced by review, not by test.

**Frontend** (`src/pages/OccasionDetail.test.tsx`)
- The heading renders `Boone Family · Christmas 2026`, asserted as the accessible name of the `<h1>`
  so the whole announced string is covered rather than two separate text nodes.
- The family half is **not** a link: no anchor with the family's name in the heading.
- With the rename form open, `Boone Family ·` is still present and the textbox value is
  `Christmas 2026`.
- A successful rename leaves the qualifier and changes only the name.
- Deep-linked at depth 0, the back control reads `← Boone Family` — with **no** intermediate
  `← Family`, which is the assertion that would fail under the rejected frontend-only approach.
- `document.title` is `Boone Family · Christmas 2026`.
- An archived occasion shows the qualifier and the `Archived` pill.
- Existing cases for the tabs, the sharing modal, the 403/404 arm and the organizer gates must keep
  passing untouched; the MSW `getOccasion` fixture gains `family_name`.

## Out of scope / deferred

- **`OccasionSharingModal`'s own heading.** It takes `occasionName={occasion.name}` and names the
  occasion unqualified. It is opened from within the occasion page, whose heading now establishes the
  family two lines up, so the modal is not ambiguous in context. Left alone deliberately.
- **`MyShopping`, `BudgetLine`, and the tab bar.** Same argument: all are inside a page that now
  names the family.
- **`OccasionStrip`'s card layout.** It already shows `family_name`, in the subtitle form decision 1
  rejected *for a heading*. The card is not a heading and is not being changed to match.
- **A shared `occasionLabel()` formatter.** Decision 10 — two call sites plus a grouping that builds
  the string from a `qualifier` field is not yet three consumers of one helper.
- **`backToFamily`'s `Family` placeholder.** Still needed by `FamilyArchive`; not removed.
- **Adding `family_name` to `OccasionRead`, `PUT`, or the family occasions list.** Decisions 4 and 5.
- **Anything about `is_archived`, the archive nudge, or the organizer gates.** Untouched.
