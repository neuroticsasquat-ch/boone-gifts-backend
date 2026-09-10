# NEU-1290 — `shared_via` becomes a list of routes

**Ticket:** [NEU-1290](https://linear.app/neuroticsasquatch/issue/NEU-1290/shared-via-becomes-a-list-of-routes-backend)
**Repo:** `boone-gifts-backend`
**Story:** [NEU-1286](https://linear.app/neuroticsasquatch/issue/NEU-1286/a-list-that-reached-me-two-ways-says-so) — "A list that reached me two ways says so"
**Milestone:** M1 — Contract
**Blocks:** [NEU-1291](https://linear.app/neuroticsasquatch/issue/NEU-1291/one-attribution-component-for-lists-and-folders-frontend) (attribution component),
[NEU-1299](https://linear.app/neuroticsasquatch/issue/NEU-1299/occasion-and-folder-headings-link-person-headings-dont-frontend) (heading links),
[NEU-1316](https://linear.app/neuroticsasquatch/issue/NEU-1316/derive-the-connection-profile-from-the-shared-scope-frontend) (connection profile)
**Project spec:** `docs/specs/occasions-and-navigation-project-spec.md` §10.1, §13
**Branch from and target:** `release/v0.6.0` — not `main` (project spec §12.1)

## What to build and why

A list can reach a viewer more than one way: shared directly *and* to an occasion, or to two
occasions of two different families. `shared_via` holds one route, so
`get_shared_lists_with_source` ranks the candidates and throws the rest away — direct outranks
occasion, lower occasion id breaks ties.

The discard is what breaks grouping. On `/lists`, a both-ways list is labelled "from Carol" and
therefore knows about no occasion, so Group by Occasion drops it into **"Not in an occasion"** —
the leftover bucket ADR 0005 introduced precisely so nothing shared with the viewer could silently
vanish from a section claiming to be complete. A list shared to two occasions appears under one of
them arbitrarily.

Widen the field to every route. The label rule survives unchanged — **direct wins** — but it moves
to the client, where `ListAttribution` applies it; this endpoint reports routes and ranks nothing.

**No migration.** `shared_via` is computed at read time; there is no column.

## What to change

| File | Change |
|---|---|
| `app/schemas/gift_list.py` | `ShareRoute` union replaces `SharedVia`; `shared_via: list[ShareRoute] = []` |
| `app/lists/repository.py` | `get_share_routes` replaces `get_shared_lists_with_source`; `get_all_visible_lists` widens |
| `app/lists/service.py` | new `to_summaries`; `get_shared_lists` derives its scope from the routes |
| `app/folders/service.py` | rows go through `to_summaries` **and** `can_view_list` |
| `app/occasions/service.py` | rows go through `to_summaries` |
| `app/connections/service.py` | rows go through `to_summaries` |
| `CONTEXT.md` | **Share route** in Terms; invariants 1 and 2 amended |
| `scripts/seed_dev.py` | comments only — the fixtures already cover every case |

```json
{
  "id": 4, "name": "Carol's Wishlist", "owner_name": "Carol Boone",
  "shared_via": [
    { "kind": "direct", "person": { "id": 2, "name": "Carol Boone" } },
    { "kind": "occasion",
      "occasion": { "id": 10, "name": "Christmas 2026" },
      "family":   { "id": 7,  "name": "Boone Family" } }
  ]
}
```

An owned row carries `"shared_via": []`. **An empty array replaces `null` everywhere** — the field
is never absent and never null.

## Decisions

### 1. A discriminated union, not one class with optional arms

`SharedVia` is flat — `{kind, id, name, family}` — with a `model_validator` rejecting a `family` on
the direct arm and a missing one on the occasion arm. Replace it with two models under a
discriminator:

```python
class NamedRef(BaseModel):
    id: int
    name: str

class DirectShareRoute(BaseModel):
    kind: Literal["direct"]
    person: NamedRef

class OccasionShareRoute(BaseModel):
    kind: Literal["occasion"]
    occasion: NamedRef
    family: NamedRef

ShareRoute = Annotated[
    DirectShareRoute | OccasionShareRoute, Field(discriminator="kind")
]
```

The validator is **deleted, not ported**. It exists to reject a state the union cannot represent in
the first place; keeping both would mean two statements of one rule.

`SharedVia` and `SharedViaFamily` retire. The `"user"` arm is renamed `"direct"` — it matches the
`CONTEXT.md` term ("Direct share") and the M1 contract every downstream ticket is written against.

### 2. The direct arm names the owner, redundantly, on purpose

`person` on a direct route is always the list's owner, already on the row as `owner_id`/`owner_name`.
The frontend's `attribution.ts` says why it is there anyway: `shared_via` is "the authoritative
statement of it", and the owner's name is what stands in on a row carrying no route at all. Fixed by
the M1 shared contract; not reopened here.

### 3. One query function, and the shared scope derives from it

`get_shared_lists_with_source` does two jobs — define the shared scope, then pick one label. The
label half is what this ticket kills, and the scope half is worth keeping in one place:

```python
def get_share_routes(
    db: Session, viewer_id: int, list_ids: Sequence[int] | None = None
) -> dict[int, list[ShareRoute]]:
```

The same `direct ∪ via_occasion` union as today, minus the `row_number()` ranking. `list_ids=None`
means the viewer's whole shared scope, which is exactly what `filter=shared` needs — so
`get_shared_lists` asks for the routes and takes the scope from the keys, rather than the union
being written twice and drifting.

The existing exclusions are unchanged and load-bearing: the caller's own lists are never in scope
however they were shared, and an archived occasion still yields a route, because archiving blocks
new shares and never withdraws visibility (ADR 0002 §5.4, `CONTEXT.md` invariant 2).

### 4. Order is stable; it is not a ranking

Routes come back direct-first, then occasions by ascending occasion id — the old
`(priority, source_id)` order, kept so a response is byte-stable across requests and tests can
assert a literal.

It is **not** a contract the client may read `routes[0]` from. M1 puts direct-wins in
`ListAttribution` deliberately, and the client needs the whole array for occasion grouping anyway;
promising a ranking here would give the rule a second home. Say so in the docstring — the ordering
is there to stop diffs churning, nothing more.

### 5. `to_summaries` becomes the seam every list-row surface calls

`to_summary(gift_list, user_id)` has no `Session`, and routes need one query. Four surfaces return
list rows — `/lists`, folder detail, occasion detail, connection lists — and only the shared path
has ever set `shared_via`.

Add the plural:

```python
def to_summaries(
    db: Session, lists: Sequence[GiftList], viewer_id: int
) -> list[GiftListRead | GiftListViewerRead]:
```

One batched `get_share_routes` call, annotate, then map the existing `to_summary`. All four
surfaces call it; `to_summary` stays the singular serializer that decides owner-vs-viewer schema
(ADR 0003) but stops being called directly from services. A fifth surface then cannot ship empty
arrays by forgetting a step, because the only function that returns rows already fills them in.

This is why the ticket's "only `get_shared_lists_with_source` changes" is too narrow: the folder
page already renders `<ListAttributionLine>` (`FolderDetail.tsx:256`). It disagrees with `/lists`
because its rows carry no routes, not because it calls the wrong component — so NEU-1291 cannot fix
that disagreement frontend-only, and NEU-1286's "same attribution on `/lists` and on a folder page"
would go unmet.

### 6. The unfiltered `GET /lists` scope is corrected here

`get_all_visible_lists` matches owner OR `ListShare` — it has never included occasion shares, so it
disagrees with `can_view_list` and with `CONTEXT.md` invariant 2, which says visibility has exactly
one predicate. Widen it to the third term.

Deliberately in scope: the union is being written for `get_share_routes` regardless, and leaving a
list-returning query that answers a different question from the codebase's one visibility predicate
is the kind of divergence the invariant exists to prevent.

Its only consumer is the folder Add-a-List picker (`FolderDetail.tsx:282`), whose defect
[NEU-1318](https://linear.app/neuroticsasquatch/issue/NEU-1318/folder-add-a-list-offers-shared-lists-frontend)
owns in M4. That ticket is written frontend-only and still works as written; this just means the
backend half is already done when it is picked up. **NEU-1318 is not re-scoped in Linear** — note it
in that ticket when it is planned.

### 7. Folder rows are filtered through `can_view_list`

`get_lists_for_folder` returns every list id in the folder without a visibility check. Revoking an
occasion share does not remove folder items, so a folder can still return a list its owner can no
longer see. Today that row renders `from {owner_name}` and looks entirely normal.

After this change it comes back with **zero routes** — a non-owned row with no attribution line,
which is the first time the leak is visible. Fix it rather than ship the symptom: route every folder
row through `can_view_list`, exactly as `occasions/service.py:list_lists` already does and for the
reason it already documents — one predicate, so a term added to it is inherited here instead of
being quietly missed.

The cost is one query per folder row, which is the cost the occasion page already accepts. Filtering
on "zero routes" instead would be cheaper and wrong: it makes `get_share_routes` a second visibility
predicate, and a term added to `can_view_list` later would not reach it.

### 8. Detail responses stay route-free

`GiftListDetailOwner` and `GiftListDetailViewer` do not carry `shared_via` and do not gain it.
Nothing renders attribution on `/lists/:id`, no ticket in this project asks for it, and the
frontend's `attribution.ts` already documents the absence. "Every list row" means row responses.

### 9. `shared_via` stays on `GiftListRead`

It could move to `GiftListViewerRead`, since routes are always empty on a row the caller owns. It
does not: folder and occasion responses mix owned and shared rows, and a field that changes position
by ownership makes every consumer branch. NEU-1286 asks for "empty array, not null" in as many
words. ADR 0003's concern is claim state leaking onto owner rows; an empty array leaks nothing.

### 10. The frontend degrades between the two merges — accepted

The scalar reads in `attribution.ts` and `list-grouping.ts:96` do not throw against an array: they
fall through to `from {owner_name}`, and grouped lists land in the leftover bucket. So
`release/v0.6.0` renders wrong attribution from this merge until NEU-1291 lands.

Accepted. The release branch is not deployed, NEU-1291 is the next ticket, and M4's milestone note
already accepts a longer interim for worse defects. A compatibility shim would be code NEU-1291
deletes.

## `CONTEXT.md` edits

* **Terms** gains **Share route** — "One way a list reached a viewer: a direct share, or an occasion
  share of a family they belong to. A list can have several; computed at read time, never stored."
* **Invariant 1** repoints the seam sentence at `app/lists/service.py:to_summaries` — the function
  new list-row responses must route through. `to_summary` keeps its own sentence as the singular
  serializer it wraps.
* **Invariant 2** notes that folder *reads* now route through `can_view_list` too, not just folder
  writes.

## Acceptance criteria

1. `shared_via` is an array on every list row, on all four surfaces, in all four cases — direct
   only, occasion only, both, and neither.
2. A list reaching the viewer both ways returns **two** routes: one row, not one route and not null.
3. A list shared to two occasions returns both, each carrying its own family.
4. An owned row returns `[]`. No response anywhere returns `null` for `shared_via`.
5. The same list carries the same routes on `/lists?filter=shared`, on a folder page, on an occasion
   page and on a connection's lists.
6. Route order is direct-first then ascending occasion id, and identical across repeated requests.
7. Unfiltered `GET /lists` includes lists reaching the caller only through an occasion.
8. A folder holding a list the caller can no longer view does not return it.
9. `to_summary` is no longer called directly outside `to_summaries`.
10. Route count per response does not grow with the number of rows.

## Tests

* Both-ways: two routes, direct first — **the regression this project exists to fix** (project spec
  §13).
* Two occasions in two families: both routes, each with its own family.
* Direct only, occasion only, neither — the last returning `[]`, asserted as an array.
* The same list asserted route-identical across all four surfaces, in one test.
* Order is a literal assertion, and stable across two calls in one test.
* Archived occasion still yields its route (ADR 0002 §5.4).
* The caller's own list shared to an occasion the caller can reach is still not in the shared scope.
* Unfiltered `GET /lists` returns an occasion-only shared list.
* A folder item whose occasion share was revoked is absent from the folder's rows.
* Query count per response holds as rows are added — the batched shape, pinned.
* `tests/integration/test_owner_blindness.py` still passes: routes say nothing about claims.
* Existing tests asserting the dedupe (`test_filter_shared_dedupes_*`, the scalar assertions in
  `test_lists.py`, `test_list_occasions.py`, `test_gift_list_schema.py`, `test_lists.py` unit) invert
  rather than being deleted — each one names a case that still has an answer, now plural.

## Out of scope

* Any ranking of routes server-side. Direct-wins is `ListAttribution`'s, in NEU-1291 (decision 4).
* `shared_via` on the detail endpoints (decision 8).
* Retiring `GET /connections/{id}/lists` — that is NEU-1317, in M4.
* Any migration or schema change. There is no `shared_via` column and this ticket adds none.
* Re-scoping NEU-1318 in Linear (decision 6).
* A frontend compatibility shim (decision 10).
