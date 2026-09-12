# NEU-1202 — Per-family list sharing

**Ticket:** [NEU-1202](https://linear.app/neuroticsasquatch/issue/NEU-1202/allow-non-simple-mode-users-to-not-include-all-lists-in-families-to)
**Project:** Boone Gifts: Maintenance
**Repos:** `backend` (data model, authorization, API) and `frontend` (create form, Families tab, revoke dialog)

---

## 1. Why

Family list visibility is currently **implicit and total**. `can_view_list` (`app/access.py:17`) grants
access whenever `users_share_family(viewer, owner)` is true, and
`get_family_visible_lists_with_grants` (`app/lists/repository.py:122`) joins
`lists → owner's FamilyMember → Family → viewer's FamilyMember`. There is no list↔family record
anywhere, so **every list a user owns is visible to every family they belong to, always**, with no
way to opt out.

That default is right for **simple mode** users — the mode exists so they never have to think about
sharing. It is wrong for **full mode** users, who should choose family by family.

`User.simple_mode` (`app/models/user.py:23`) exists today but drives **no backend behavior**. It rides
in the JWT claims and is read only by the frontend for nav chrome (`Layout.tsx:84`) and to hide the
"Shared with" tab (`ListDetail.tsx:36`). This ticket makes it govern real authorization behavior for
the first time.

## 2. What to build

A per-list, per-family grant record. Visibility becomes explicit; simple mode keeps its
"it just works" promise by having the backend create those grants automatically.

### 2.1 Data model

New table, mirroring `ListShare` (`app/models/list_share.py`), which is the existing list↔**user**
grant:

```python
# app/models/list_family_share.py
class ListFamilyShare(Base):
    __tablename__ = "list_family_shares"
    __table_args__ = (
        UniqueConstraint("list_id", "family_id", name="uq_list_family_shares_list_family"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"), index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Register in `app/models/__init__.py`.

**Core invariant: a grant row implies the owner is still a member of that family.** Enforced by
deleting grants on every membership departure (§2.5). The read queries rely on it and therefore do
not re-check owner membership.

### 2.2 Migration

Alembic revision on top of the current head `13861325bacf`. Create the table, then **backfill every
existing list against every family its owner currently belongs to** — archived lists included — so
that visibility on the morning after deploy is byte-for-byte what it was the night before. The
change is purely additive: nobody loses access, owners simply gain the ability to opt out.

```sql
INSERT INTO list_family_shares (list_id, family_id, created_at)
SELECT l.id, fm.family_id, CURRENT_TIMESTAMP
FROM lists l
JOIN family_members fm ON fm.user_id = l.owner_id;
```

Use `op.batch_alter_table` / SQLite-safe constructs, consistent with existing revisions.
`downgrade()` drops the table.

### 2.3 Visibility

`app/access.py` — replace the membership-overlap clause with a grant lookup:

```python
def can_view_list(db, user, gift_list) -> bool:
    """Owner OR a ListShare OR a family grant intersecting the viewer's families."""
    if gift_list.owner_id == user.id:
        return True
    if find_share(db, gift_list.id, user.id) is not None:
        return True
    return list_granted_to_any_family_of(db, gift_list.id, user.id)
```

where the new predicate is an `EXISTS` over
`list_family_shares JOIN family_members ON family_members.family_id = list_family_shares.family_id`
filtered to `list_id` and `user_id`.

`get_family_visible_lists_with_grants` (`app/lists/repository.py:122`) is rewritten to drive off the
grant table. The `fm_owner` join disappears; the grant row *is* the owner's opt-in:

```
FROM lists
JOIN list_family_shares lfs ON lfs.list_id = lists.id
JOIN families            f   ON f.id = lfs.family_id
JOIN family_members      fmv ON fmv.family_id = lfs.family_id
WHERE fmv.user_id = :user_id
  AND lists.owner_id != :user_id
  AND lists.is_archived = :archived
ORDER BY lists.updated_at DESC
```

The one-row-per-(list, family) shape is unchanged, so `get_family_lists`'s collapse into
`FamilyRef[]` (`app/lists/service.py:26`) and the `FamilyLists` page grouping both keep working
as-is.

**`users_share_access` is deliberately left alone.** It answers "is there any standing relationship
between these two people" (accepted connection OR shared family) and governs claim/collection
cleanup on relationship changes (`app/families/service.py:16`). It is a different question from list
visibility and must not be gated on grants — two people in a family still have a relationship even
when no list is shared between them.

`get_all_visible_lists` (the unfiltered `GET /lists`) already covers only owned + `ListShare` lists;
family lists reach the UI solely through `filter=family`. Unchanged.

`delete_list` (`app/lists/repository.py`) must also delete the list's `list_family_shares` rows,
alongside the existing `CollectionItem` / `ListShare` / `Gift` cleanup.

### 2.4 Creation behavior

`GiftListCreate` gains `family_ids: list[int] = []`.

`create_list` branches on the **server-side** `simple_mode` value — the client is never the gate:

| Owner mode | Behavior |
|---|---|
| `simple_mode = True` | Grants created for **all** families the owner belongs to. Any `family_ids` in the body is ignored. |
| `simple_mode = False` | Grants created for exactly the `family_ids` sent. Default `[]` — shared with no family. |

Every id in `family_ids` must be a family the caller belongs to; otherwise `403`.

### 2.5 Membership changes

Three sites create a `FamilyMember`; each needs the simple-mode auto-grant:

1. `app/family_invites/service.py:170` — `accept_invite`, an existing user joining. **The one that
   matters**: a simple-mode user joining a second family must have their existing lists appear there,
   because the toggles are forbidden to them (§2.6) and they would otherwise hit a dead end with no
   in-app way out.
2. `app/families/service.py` — `create_family`, creator becomes organizer. Same rule.
3. `app/auth/service.py:116` — register-via-family-invite. The user owns no lists yet, so this is a
   no-op in practice; call the same helper anyway so the rule lives in exactly one place.

The rule: **on gaining membership, if the new member has `simple_mode = True`, grant all their
non-archived lists to that family.** Full-mode joiners get nothing and opt in themselves — joining a
family must never silently re-share a list its owner deliberately kept private.

On **losing** membership — `remove_member` (self-leave and organizer-removal both) and
`delete_family` — delete grants for lists owned by the departing member on that family; deleting a
family deletes all of its grants. This preserves the §2.1 invariant. The existing
`_cleanup_if_dropped` call is unchanged and still runs.

### 2.6 Grant management API

New domain package `app/list_families/` (repository / service / router), mirroring `app/shares/`,
mounted at `/lists/{list_id}/families`. All routes use the existing `OwnedList` dependency.

| Route | Behavior |
|---|---|
| `GET /lists/{list_id}/families` | Every family the **owner** belongs to, each with a `shared` flag. Readable in both modes (simple mode renders it read-only). |
| `PUT /lists/{list_id}/families/{family_id}` | Create the grant. `204`. Idempotent. |
| `DELETE /lists/{list_id}/families/{family_id}?claims=release\|keep` | Revoke the grant. `204`, or `409` — see §2.7. |

**Full-mode-only mutations.** `PUT` and `DELETE` return `403` when the caller has
`simple_mode = True`, with the message *"Switch to full mode to manage family sharing for this
list."* The frontend mirrors this, but the backend is the gate — the hidden UI is not.

Response schema:

```python
class ListFamilyShareState(BaseModel):
    id: int          # family id
    name: str
    shared: bool
```

### 2.7 Revoking a grant: claims

Revoking can orphan claims made by that family's members, and can orphan collection items pointing
at the list.

**Collection items are always deleted** for members who lose access — this matches `delete_share`
(`app/shares/service.py:64`) and has no bearing on the surprise.

**Claims are the owner's call, prompted case by case.**

This must respect an existing invariant: **owners are blind to claim state on their own lists.**
`GiftListDetailOwner` uses `GiftOwnerRead`, which omits `claimed_by_id` / `claimed_at` /
`purchased_at` (`app/schemas/gift_list.py`), and `Lists.tsx` renders "X of Y claimed" only under
*Shared with Me*, never under *My Lists*. The prompt therefore reveals **that** claims exist and
nothing more — no count, no gift names, no claimer names. This is the same leak
`delete_list` already accepts with its *"This list has gifts that have been claimed"* `409`.

Flow:

- `DELETE` **without** `claims` — if no member of that family would lose a claim, revoke and return
  `204`. If any would, make **no change** and return `409` with detail *"Some gifts on this list are
  claimed by members of this family."* A `409` on this endpoint means exactly this one condition.
- `DELETE?claims=release` — revoke, then for each member of that family who can no longer view the
  list by any path (not owner, no `ListShare`, no other granting family), unclaim their claims on
  its gifts and delete their collection items pointing at it.
- `DELETE?claims=keep` — revoke and delete collection items, but leave claims standing. The claim
  survives on a list the claimer can no longer open; that is the owner's explicit choice.

"Would lose a claim" is evaluated per member with the same
not-owner / no-`ListShare` / no-other-granting-family test used by `claims=release`.

### 2.8 Frontend

**Create form** (`CreateList.tsx`) — a "Share with families" section listing the user's families as
**unchecked** checkboxes, posting `family_ids`. Hidden entirely when the user belongs to no families,
and when the user is in simple mode (the backend shares with all families regardless, so a control
would be a lie).

**List detail** (`ListDetail.tsx`) — a fourth tab, **Families**, beside "Shared with", in
`src/pages/list-detail/FamiliesTab.tsx`.

- *Full mode:* one toggle per family the owner belongs to, reflecting `shared`.
- *Simple mode:* the tab is **still visible** — unlike "Shared with", which stays hidden. It renders
  the list's actual sharing state read-only, plus the instruction to switch to full mode with a link
  to Account settings. It must show the real state rather than asserting "shared with your
  families", because a simple-mode user can own a list created in full mode and deliberately left
  unshared.

**Revoke dialog** — on a `409` from the `DELETE`, a modal offering **Release those claims** /
**Keep them claimed** / **Cancel**, which re-issues the request with `claims=release` or
`claims=keep`. No counts, no names.

**Types / API** — `ListFamilyShareState` in `src/types/index.ts`; `getListFamilies`,
`shareListWithFamily`, `unshareListFromFamily(listId, familyId, claims?)` in `src/api/lists.ts`.
Invalidate `["lists"]`, `["lists","family"]`, and `["list", listId]` on mutation.

---

## 3. Acceptance criteria

**Migration**
1. After migrating, every list visible to a family member before the deploy is still visible, with
   no user action — archived lists included.

**Full mode**
2. A full-mode user creating a list with no families checked: the list appears in no relative's
   Family Lists page, and `GET /lists?filter=family` for a co-member omits it.
3. Checking "The Boones" at creation makes the list appear under *The Boones* on co-members'
   Family Lists page, and not under any other family.
4. Toggling a family on in the Families tab grants access immediately; toggling off revokes it.
5. `POST /lists` with a `family_ids` entry for a family the caller does not belong to returns `403`.

**Simple mode**
6. A simple-mode user creating a list has it shared with all their families automatically, with no
   sharing control shown on the create form.
7. `POST /lists` from a simple-mode user with `family_ids: []` still shares with all their families
   (the body is ignored).
8. `PUT` / `DELETE` on `/lists/{id}/families/{fid}` from a simple-mode user returns `403` with the
   switch-to-full-mode message.
9. A simple-mode user opening the Families tab sees the list's real sharing state and the
   instruction to switch to full mode — not a toggle.

**Membership**
10. A simple-mode user accepting a family invite has their existing non-archived lists appear in that
    family's lists for its members.
11. A full-mode user accepting a family invite shares nothing with it until they opt in; a list they
    previously un-shared stays un-shared.
12. A simple-mode user who creates a family gets their existing lists granted to it.
13. When a user leaves or is removed from a family, their lists disappear from that family's view;
    the grant rows are gone, not merely filtered.
14. Deleting a family deletes all of its grants.

**Claims on revoke**
15. Revoking a grant with no affected claims returns `204` first time, no dialog.
16. Revoking a grant where a family member holds a claim returns `409`, changes nothing, and the UI
    shows the release/keep dialog with **no count and no gift or claimer names**.
17. `claims=release` revokes and unclaims only for members who lose all access paths — a member who
    also holds a `ListShare`, or sees the list via another granting family, keeps their claim.
18. `claims=keep` revokes without unclaiming.
19. Both paths delete collection items for members who lose access.

**Unchanged**
20. Connection-based `ListShare` sharing behaves exactly as before, including the
    must-be-connected rule and the list-shared email.
21. `users_share_access` semantics are unchanged: two people in a family still share access for
    claim/collection-cleanup purposes even with no list shared between them.

---

## 4. Out of scope / deferred

- **Notifying family members** when a list is newly granted to their family. Connection shares send
  an email (`app/email/list_shared.py`); family grants deliberately send nothing in this ticket.
- **The unseen-share badge.** `ListShare.seen_at` drives `GET /lists/unseen-count`; family grants
  have no `seen_at` and do not count toward the badge, as today.
- **Bulk management from the Families page** ("share these four lists with the Boones"). The
  list-detail tab is the only surface.
- **Changing `users_share_access`** or the connection-based sharing rules.
- **Auto-granting archived lists** on join — the simple-mode auto-grant covers non-archived lists
  only. (The one-time migration backfill *does* include archived lists, to preserve existing
  visibility.)
- **Switching modes does not change existing grants**, per the ticket: a full-mode user who switches
  to simple mode does not get their pre-existing lists auto-shared, and a simple-mode user switching
  to full mode keeps theirs. Mode governs creation and who may operate the toggles, never a
  retroactive rewrite.
- **Per-gift release choice** on revoke — rejected for breaking the owner's blindness to claim state.

## 5. Notes for implementation

- Backend tests: `tests/unit/services/test_access.py` patches `users_share_family` directly and will
  need reworking onto the new predicate. `tests/unit/services/test_lists.py` patches
  `get_family_visible_lists_with_grants`; its shape is unchanged, so those should survive.
  `tests/unit/services/test_families.py` covers `users_share_family`, which stays.
- No `CONTEXT.md` or ADRs exist in either repo, so there is nothing to update inline. The
  visibility invariants in §2.1 and §2.3 are the material worth promoting into one later.
