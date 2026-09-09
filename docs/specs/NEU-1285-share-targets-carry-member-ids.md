# NEU-1285 — Share targets carry their family's member ids

**Ticket:** [NEU-1285](https://linear.app/neuroticsasquatch/issue/NEU-1285/share-targets-carry-their-familys-member-ids-backend)
**Repo:** `boone-gifts-backend`
**Blocks:** [NEU-1284](https://linear.app/neuroticsasquatch/issue/NEU-1284/sharing-panel-families-first-and-disable-people-an-occasion-share)
(frontend — the sharing panel disables people an occasion share already covers)
**Project spec:** `docs/specs/shopping-lists-project-spec.md` §5.2

## What to build and why

`GET /lists/{list_id}/families` feeds the sharing control's families half. NEU-1284 adds a rule to
its **people** half: a connection who is a member of a family this list reaches through an active
occasion can already see the list, so their checkbox is disabled with the reason.

Nothing in the API tells the panel who is in which family. `ShareTargetFamily` is
`{id, name, occasions[]}`; `GET /connections` returns users with no family information. Add the
missing half here rather than making the client fan out `GET /families/{id}` per family — one
request keeps the disabled state from arriving after the rows are already interactive.

## What to change

`ShareTargetFamily` gains `member_ids: list[int]` — every member of the family, the owner included.

| File | Change |
|---|---|
| `app/schemas/list_occasion_share.py` | the new field on `ShareTargetFamily` |
| `app/list_occasions/service.py::list_share_targets` | populate it |
| `app/list_occasions/repository.py` | one batched query over `family_members` |

```json
[
  { "id": 7, "name": "The Boones", "member_ids": [1, 2, 9],
    "occasions": [{ "id": 10, "name": "Christmas 2026", "is_archived": false, "shared": true }] }
]
```

## Decisions

### 1. One batched query, not one per family

`list_share_targets` already loads occasions for all families in a single call
(`get_occasions_for_families`). Member ids follow the same shape — a new
`get_member_ids_for_families(db, family_ids)` returning `dict[int, list[int]]`. A per-family loop
would put the endpoint's query count on the number of families the owner belongs to, for a field
that is pure decoration on a payload already being assembled.

### 2. Ids, not members

The consumer does a set lookup against `ListShare.user_id` and `Connection.user.id`. Names and
roles are already on `GET /families/{id}` for anyone who needs them, and the panel labels its rows
from `/connections`. Returning full member objects here would be a second, competing source of a
person's name.

### 3. The owner is included

They are a member of the family, and excluding them would make the field mean "members other than
the caller" — a shape that has to be explained every time it is read. The owner never appears in
their own connections list, so the frontend is unaffected either way.

### 4. Not a new disclosure — say so in the docstring

Every family in this payload comes from `get_families_for_user(gift_list.owner_id)`, so the caller
is a member of each one, and `GET /families/{id}` already returns those members' `user_id`s to any
member. This field moves an existing permission into a payload the caller can already read; it
widens nothing.

The docstring should state this. The next reader will ask, and the endpoint is one an
owner-blindness review will keep landing on.

### 5. The direct-share endpoint is unchanged — deliberately

`POST /lists/{list_id}/shares` keeps accepting a direct share to a person a family occasion already
covers. The frontend disable is a **redundancy nudge, not a permission**: a direct share is the
grant that survives the person leaving the family or the occasion share being revoked, so refusing
it would quietly narrow who can see the list.

This is the deliberate exception to `frontend/CONTEXT.md` rule 1 ("anything the UI hides is also
refused server-side"), recorded there rather than left implicit.

## Acceptance criteria

1. `GET /lists/{list_id}/families` returns `member_ids` on every family.
2. The list holds every member of that family, the caller included, and nobody else.
3. A family whose only member is the owner returns just the owner's id.
4. The endpoint's query count does not grow with the number of families.
5. No other endpoint or response changes.

## Tests

* The payload carries every member id of each family, owner included.
* A family the owner belongs to with no other members carries just the owner.
* Two families with overlapping membership each carry the shared member.
* Query count holds as families are added — the batched shape, pinned.
* `tests/integration/test_owner_blindness.py` still passes: this field says nothing about claims.

## Out of scope

* Any change to `can_view_list` or to who can see a list.
* Refusing a redundant direct share (decision 5).
* Names, roles, or emails on this payload (decision 2).
