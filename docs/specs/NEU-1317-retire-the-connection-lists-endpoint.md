# NEU-1317 — Retire the connection-lists endpoint

**Ticket:** [NEU-1317](https://linear.app/neuroticsasquatch/issue/NEU-1317/retire-the-connection-lists-endpoint-backend)
**Repo:** `boone-gifts-backend`
**Story:** [NEU-1311](https://linear.app/neuroticsasquatch/issue/NEU-1311/a-persons-page-shows-everything-theyve-shared-with-me) — "A person's page shows everything they've shared with me"
**Milestone:** M4 — Correctness
**Blocked by:** [NEU-1316](https://linear.app/neuroticsasquatch/issue/NEU-1316/derive-the-connection-profile-from-the-shared-scope-frontend) — **merged**, spec at `boone-gifts-frontend` `docs/specs/NEU-1316-derive-the-connection-profile-from-the-shared-scope.md`
**Project spec:** `docs/specs/occasions-and-navigation-project-spec.md` §10.3, §9.4
**Branch from and target:** `release/v0.6.0` — not `main` (project spec §12.1)

## What to build and why

Delete `GET /connections/{id}/lists` and the service and repository functions behind it. There is
nothing to reimplement: its replacement is a client-side derivation over the shared scope, which
shipped in NEU-1316.

The endpoint answered **direct shares only**. `app/connections/service.py:136` reads
`list_repo.get_lists_shared_by_user`, whose predicate is `GiftList.id IN (SELECT list_id FROM
list_shares WHERE user_id = viewer)` — the direct-share table, and nothing else. So a list that
reached the viewer through an occasion was owned by a person whose page then omitted it. That is
the defect NEU-1311 was opened on: click "from Carol Boone" on an occasion-reached list and land on
a Carol page missing the list you came from.

Since NEU-1316 the person's page filters `GET /lists?filter=shared` on `owner_id`, and that scope
is taken from `get_share_routes`' keys — direct **and** occasion routes. The narrower question has
no caller left.

### The blocker is genuinely satisfied

NEU-1316 is merged on `release/v0.6.0` (`2df80aa`, PR #222). Its AC 4 required that no file under
`src/` mention `connections/{id}/lists`; verified — the only surviving hits in the frontend are a
comment and a *negative* assertion (`expect(asked).not.toContain("/connections/5/lists")`). Nothing
calls the route.

## What to change

| File | Change |
|---|---|
| `app/connections/router.py` | Delete `connection_lists` (line 70) and the `response_model` comment above it (lines 68–69) |
| `app/connections/service.py` | Delete `get_connection_lists` (lines 118–139); the `list_repo` and `list_service` imports (lines 6–7) go with it |
| `app/lists/repository.py` | Delete `get_lists_shared_by_user` (lines 229–244) |
| `tests/integration/routers/test_connections.py` | Delete the three endpoint tests (lines 208–238) |
| `tests/integration/test_owner_blindness.py` | Delete `test_a_connections_lists_carry_the_count` (lines 153–169) — decision 2 |
| `tests/integration/routers/test_lists.py` | Drop the `on_connection` arm from the four-surface test (lines 1034–1069), its `Connection` setup, and the now-unused import at line 6 — decision 3 |
| `README.md` | Delete the `GET /connections/{id}/lists` line (line 134) |
| `CONTEXT.md` | One clause on rule 2 — decision 5 |

`claims_repo` stays in `app/connections/service.py`: `cascade_disconnect` still calls
`unclaim_gifts_between`.

## Decisions

### 1. Straight deletion — no shim, and that is this repo's precedent, not just this ticket's preference

No redirect, no `410`, no deprecation window. NEU-1260 ("retire simple mode", `ad3cd57`) deleted its
routes, schema fields and tests outright and updated `README.md`, `CONTEXT.md` and `AGENTS.md` in the
same commit. There is no `deprecat*`, `HTTP_410` or `Gone` anywhere under `app/`. The single
consumer is in a repo we control and has already stopped calling it, and no user can have bookmarked
an API route.

`to_summaries` is **not** touched. It keeps three callers — `app/occasions/service.py:146`,
`app/folders/service.py:42` and `app/lists/service.py:126` — and remains the seam project spec §10.1
and `CONTEXT.md` rule 1 both name. Only the connections caller goes.

`get_lists_shared_by_user` **is** deleted rather than left: its sole caller is the service function
above it. It was the last read query in the codebase keyed on the direct-share table alone, which is
the exact shape of the defect; leaving it would leave the wrong question available to the next
person who needs a per-person read.

### 2. The owner-blindness assertion is deleted, because it is a literal duplicate

`test_owner_blindness.py:153` asserts the viewer half of `CONTEXT.md` rule 1 — a claim hidden from
the owner is still visible to the person who made it — through this endpoint, with a comment arguing
that `my_unpurchased_claim_count == 0` proves the count was *computed* rather than defaulted.

It is not re-pointed, because the assertion already exists on the surface that replaced the
endpoint. `test_a_viewer_gets_their_own_unpurchased_count` (`test_owner_blindness.py:225`) runs the
same `owned_list_with_a_claim` fixture against `GET /lists?filter=shared` and makes the identical two
assertions — `claimed_count == 1` and `my_unpurchased_claim_count == 0`. Re-pointing would produce
two copies of one test.

The "computed rather than defaulted" rationale survives without it, and structurally:
`my_unpurchased_claim_count` is a **required** field on `GiftListViewerRead`, and
`tests/unit/schemas/test_gift_list_schema.py:172` asserts that omitting it raises `ValidationError`.
A defaulted count is not a state the schema permits.

`CONTEXT.md` rule 1 names this file as the sweep, and the sweep is unweakened: `CLAIM_KEYS`
(line 31) still carries `my_unpurchased_claim_count` through every owner-facing assertion in the
file, and the viewer half is covered on `/lists?filter=shared` (line 225), on a folder's mixed rows
(line 206) and on the occasion index.

### 3. The four-surface consistency test becomes three, because the fourth surface is now the first

`test_lists.py:1034` — `test_the_same_list_carries_the_same_routes_on_every_surface` — asserts
NEU-1286's rule that every surface returning list rows agrees about how a list arrived, across
`/lists?filter=shared`, a folder page, an occasion page and this endpoint.

The `on_connection` arm and its `assert` are removed, and the docstring is amended to name three
surfaces. Nothing replaces it. The person's page is no longer a fourth surface that *could*
disagree: NEU-1316 decision 5 gave it the query key `["lists", "shared", { archived: false }]` — the
same cache entry `/lists` fills — so it renders arm 1's payload. Consistency there is now held by
construction rather than by assertion, which is what NEU-1316 set out to achieve.

Substituting the archived shared scope to keep the count at four was considered and rejected: no one
has claimed it disagrees, and `/lists/archive` is not this ticket's business.

### 4. Nothing asserts the route is gone

The three tests in `test_connections.py` are deleted and none replaces them. A `404` on an unrouted
path is FastAPI's default, so such a test asserts the framework rather than this codebase, and
NEU-1260 left no absence test behind when it retired simple mode. An OpenAPI-schema assertion would
introduce a kind of test the suite does not have, for one route.

### 5. What dies with the endpoint that is not a test, and why that is right

`get_connection_lists` carried a third guard the replacement has no equivalent for:

```python
if connection.status != "accepted":
    raise ForbiddenError("Connection not accepted.")
```

This was the only read in the codebase gated on connection status — `status == "accepted"` otherwise
appears only in `app/connections/service.py:98,112` (the delete path) and
`app/connections/repository.py:42,61` (listing connections). Its disappearance is **correct, not a
regression**: `CONTEXT.md` rule 2 makes `can_view_list` the single visibility predicate, and it
never consults connection status — "A connection alone grants nothing." A `ListShare` row is the
grant; the connection's state is not. The gate was belt-and-braces over a predicate that already
held, and `cascade_disconnect` deletes the share rows when a connection ends.

So rule 2 gains one clause recording the positive form of this, where the next person will hit it:
the shared scope is the only per-person read, and there is no server-side index of one person's
lists. That is why this endpoint was wrong, and why re-adding one would be. No Terms row is added —
"a person's page" is a frontend concept, recorded in the frontend's `CONTEXT.md` by NEU-1316, and
this repo deliberately has no such thing.

`AGENTS.md` needs no edit: line 78 already describes the connections package as "`/connections`
lifecycle + cascade disconnect", which the deletion makes more accurate rather than less.

## `CONTEXT.md` edit

Rule 2 ("Visibility has exactly one predicate", line 54) gains, after "A connection alone grants
nothing; bare family co-membership grants nothing":

> It follows that the shared scope is the only per-person read there is — `GET /connections/{id}/lists`
> was retired in v0.6.0 because it answered a narrower question (direct shares only) than the one
> predicate, and there is no server-side index of one person's lists to replace it.

## Acceptance criteria

1. `GET /connections/{id}/lists` returns 404 — the route is not registered and does not appear in
   `/openapi.json`.
2. No file under `app/` references `connection_lists`, `get_connection_lists` or
   `get_lists_shared_by_user`.
3. `app/connections/service.py` no longer imports `app.lists.repository` or `app.lists.service`, and
   still imports `app.claims.repository` for `cascade_disconnect`.
4. Every other `/connections` route is untouched and its tests pass unchanged.
5. `to_summaries` is unchanged and its three remaining callers still work: `GET /lists`,
   `GET /folders/{id}`, `GET /occasions/{id}/lists`.
6. `test_the_same_list_carries_the_same_routes_on_every_surface` passes over three surfaces and its
   docstring names three.
7. The owner-blindness sweep passes and still asserts the viewer half of rule 1 on
   `/lists?filter=shared`, on a folder's rows and on the occasion index.
8. `README.md` no longer lists the endpoint; the rest of the Connections section is unchanged.
9. `CONTEXT.md` rule 2 records why there is no per-person read.
10. `task test` passes with no skips, xfails or new warnings.

## Tests

This ticket adds no tests. It removes four and edits one:

* `test_connections.py` — `test_connection_lists`, `test_connection_lists_not_party` and
  `test_connection_lists_excludes_archived` deleted. The `shared_list` conftest fixture stays; eight
  other test files use it.
* `test_owner_blindness.py` — `test_a_connections_lists_carry_the_count` deleted (decision 2).
* `test_lists.py` — `test_the_same_list_carries_the_same_routes_on_every_surface` loses its
  `on_connection` arm, its `connection` setup (the `Connection` row at line 1041 and the query at
  1047 that fetches it) and the fourth `assert`; the docstring is amended (decision 3). The setup is
  safe to remove: `get_share_routes` never consults `connections` — a direct route is a `ListShare`
  row — so the three surviving arms still return the same three routes. Lines 1041 and 1047 are the
  file's only uses of `Connection`, so the module-level import at line 6 goes with them.

The full suite passing unchanged otherwise is the point: this is a deletion, and anything else that
moves is a finding, not a success.

## Out of scope

* **Any change to `GET /lists?filter=shared`.** It already answers the wider question; NEU-1290
  shipped that in M1.
* **Re-pointing the deleted owner-blindness assertion** — decision 2, it is already covered.
* **An absence test for the retired route** — decision 4.
* **Adding an OpenAPI snapshot test.** The suite has none, and introducing one for a single route is
  a separate argument.
* **The stale comment references in the frontend** (`ConnectionProfile.tsx:16`,
  `ConnectionProfile.test.tsx:166`). They are accurate history in a merged, spec-backed file, in the
  other repo.
* **`RELEASE_NOTES.md`.** It is assembled at release time from merged PRs — NEU-1294's commit did not
  touch it, and neither does this one.
* **A migration.** Nothing here touches the schema; project spec §11 carries exactly one migration
  for this project and it is not this ticket's.
