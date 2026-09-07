# NEU-1228 — Shared accounts: schema, migrations, and API

**Ticket:** [NEU-1228](https://linear.app/neuroticsasquatch/issue/NEU-1228/shared-accounts-schema-migrations-and-api-backend)
**Project:** [BG: Navigation and shared accounts](https://linear.app/neuroticsasquatch/project/bg-navigation-and-shared-accounts-1cbf5b5d867b) · **Milestone:** M6 — Shared accounts and recipients
**Repo:** `boone-gifts-backend` · **Story:** NEU-1224
**Blocks:** NEU-1230 (drop `recipient_has_account`), NEU-1232 (account settings UI), NEU-1237 (create/edit picker)
**Reads with:** `docs/adr/0001-shared-accounts-are-one-identity.md`, `docs/specs/navigation-and-shared-accounts-project-spec.md` §5/§7.3/§8, `docs/specs/NEU-1216-list-recipients.md`

---

## 1. Why

Some households share one login. Today the only way to express that is the per-list checkbox "This
list is for someone else" with its sub-option "they use this app" — which actually means *this same
login* (`NEU-1216` §2.5, the "recipient **with** an account" row). Neither member of a couple thinks
of their own list as being for "someone else", so neither ticks it, and the wording gives no hint
that it is about the account rather than about another user of the app.

This ticket moves that case up to the account, where it belongs, and gives lists somewhere truthful
to point.

**Account people are labels, not identities.** The account stays the single identity everywhere —
one family member, one connection, one claimer. Nothing about visibility, claims, membership, or
attribution learns about them. See ADR 0001, including the cost that follows: claims stay hidden on
every list the account owns, so a couple cannot coordinate shopping through the app. That is
decided; do not "fix" it here.

## 2. Data model

```python
# app/models/user.py
is_shared_account: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

# app/models/account_person.py  (new)
class AccountPerson(Base):
    __tablename__ = "account_people"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_account_people_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column()          # display order, 0-based
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

# app/models/gift_list.py
account_person_id: Mapped[int | None] = mapped_column(
    ForeignKey("account_people.id"), default=None, index=True
)
```

`String(255)` matches `User.name` and `GiftList.recipient_name`. `position` is persisted rather than
derived so ordering survives a reorder that renames nothing.

### 2.1 Migration

One Alembic revision chaining from **whatever is head at implementation time** — `d8a3f1c05b64`
today, but NEU-1226 (occasions rename) may land first. Three operations:

1. `op.add_column("users", ...)` for `is_shared_account`, NOT NULL with `server_default="0"` —
   follow the `simple_mode` precedent in `bb79d1d4eacb`, which is the only NOT NULL boolean addition
   to `users` in this repo.
2. `op.create_table("account_people", ...)` with the FK and the unique constraint.
3. `op.add_column("lists", ...)` for `account_person_id`.

Use direct `op.add_column` on the upgrade (SQLite supports it natively) and batch mode on the
downgrade, per the `seen_at` precedent (`e9730fad709a`) and NEU-1216 §2.2. **No backfill**: no
existing row becomes a shared account, and `recipient_has_account = true` rows are left alone —
NEU-1230 drops that column without converting them, because the beta data is test data (project
decision 13).

`PRAGMA foreign_keys=ON` is live on every connection, so `lists.account_person_id` genuinely
constrains; deleting a person with lists still pointing at it raises. §4.3 is what prevents that.

## 3. API

### 3.1 A dedicated account resource

New package `app/account/` (`router.py`, `service.py`, `repository.py`), following the domain-package
shape. **Not** `PUT /auth/profile`: that endpoint reissues an access *and* refresh token on every
call because `simple_mode` is a JWT claim, and none of this belongs in the JWT. Renaming a person
must not rotate the session. `simple_mode` stays where it is.

```
GET /account
→ 200 { "is_shared_account": bool, "people": [ { "id": int, "name": str } ] }

PUT /account[?confirm=true]
← { "is_shared_account": bool, "people": [ { "id": int|absent, "name": str } ] }
→ 200 (same shape as GET)  |  409 { "affected_lists": int }  |  400
```

### 3.2 PUT is a declarative full replace

The body is the **whole desired state**, which is what a settings card's Save button naturally
submits:

- An entry **with** an `id` the caller owns → rename in place (a no-op rename is fine).
- An entry **without** an `id` → create.
- An existing person **omitted** from the array → delete.
- **Array order is display order** — `position` is assigned from the array index, so reordering is
  just a reordered array.

There is no `/account/people` sub-resource. One endpoint, one confirmation idiom.

An `id` that belongs to another account is a **404** — never silently ignored, and never leaked as a
403 (which would confirm the id exists).

### 3.3 Confirmation follows the existing revoke idiom

`DELETE /lists/{id}/families/{fid}` already returns 409 when a destructive choice has not been made
and is re-issued with `?claims=release|keep`. Mirror it exactly:

- A `PUT /account` that would **strip labels from lists** — by deleting a person that lists point
  at, or by setting `is_shared_account: false` — returns **409** with `{"affected_lists": N}` and
  changes nothing.
- The same request with `?confirm=true` commits.
- A PUT that strips no labels needs no confirmation, even if it deletes a person with no lists.

`affected_lists` is a bare count. Unlike the family-revoke 409 it discloses nothing sensitive, but
keep it a count anyway for symmetry.

### 3.4 List payloads

`account_person_id` and `account_person_name` ride on the existing list endpoints — no new routes.

- `GiftListCreate` and `GiftListUpdate` accept `account_person_id: int | None`.
- `GiftListRead`, `GiftListDetailOwner` and `GiftListDetailViewer` return both
  `account_person_id: int | None` and `account_person_name: str | None`.
- Flat, mirroring `owner_id` / `owner_name` for a single related record rather than the nested
  `FamilyRef` shape.

**Both fields go on the viewer schema too.** A family member browsing a shared account's lists sees
"for Gran"; that is the whole point of labelling them, and it discloses nothing the account has not
chosen to publish.

> **Trap (inherited from NEU-1216 §2.3):** `GiftListRead.compute_counts` is a `mode="before"`
> validator that builds an **explicit dict**. Any field missing from that dict is silently returned
> as `None`. Both new keys must be added there or every list-collection endpoint quietly loses them.

`PUT /lists/{id}` needs no special handling: the router already does
`model_dump(exclude_unset=True)` and the repository does blind `setattr`, so an explicit `null`
clears the assignment while an omitted key leaves it alone.

## 4. Rules

### 4.1 Mutually exclusive with `recipient_name`

A list is for an account person, **or** for a recipient with no account, **or** for neither — never
both. Enforce in the service layer (not a SQLite check constraint, which batch mode makes painful),
rejecting with **400** in either direction: setting `account_person_id` on a list that has a
`recipient_name`, or vice versa, in the same request or across a create-then-update.

The natural home is `app/schemas/gift_list.py`'s existing `RecipientFields` model-validator, which
already enforces "a flag with no name is meaningless" and is inherited by both create and update.
Extending it keeps one rule in one place — but note it cannot see the *stored* state on a partial
update, so the service layer must re-check against the persisted row.

### 4.2 Household lists are legal

A shared account may own a list with **neither** a person nor a recipient — that is a household list
("ideas for the kitchen"), and it renders with no "for" line. The API does **not** require an answer.

This deliberately drops the "a shared account must supply one of the two" rule from the ticket text:
it would have forced Gran and Grandpa to falsely attribute a joint list to one of them. The *form*
still presents the choice as required, with "Both of us" as the option that sends `null` (NEU-1237),
so the answer is deliberate rather than defaulted — but that is a client concern, not an invariant.

### 4.3 At least two people, always

An account marked shared always has at least two people.

- A PUT that sets `is_shared_account: true` with fewer than two people is a **400**.
- Deleting down to **one** person auto-unmarks the account: the last person is removed,
  `is_shared_account` becomes false, and every remaining label is cleared. This is a destructive
  change, so it goes through the same 409 confirmation, and the 200 response — which returns the
  resulting account state — is how the client learns the mode changed.

Names are stripped of surrounding whitespace and an empty result is a 400 (follow
`family_invite.py`'s normalizer, the existing precedent). Duplicate names within one account are a
400 via the unique constraint.

### 4.4 Deleting a person nulls, never cascades

Deleting a person sets `lists.account_person_id = NULL` on their lists, turning them into household
lists (§4.2). The lists themselves, their gifts, their shares, and their claims are untouched. **No
list is ever deleted by this ticket**, and no claim is ever released.

## 5. Out of scope

- **Anything frontend** — the settings card is NEU-1232, the create/edit picker is NEU-1237.
- **Dropping `recipient_has_account`** — NEU-1230, deliberately a separate PR so this one is purely
  additive and the two land in a reviewable order.
- **Per-person claim visibility, or a profile switcher.** Refused in ADR 0001.
- **Account people as identities** — no family membership, no connections, no claim attribution, no
  per-person visibility. Ever, without a new ADR.
- **Backfilling existing `recipient_has_account = true` lists** into account people.
- **Deleting or merging accounts**, and any migration path from a shared account to two real
  accounts.

## 6. Acceptance criteria

- `GET /account` returns the flag and the ordered people for the calling account.
- `PUT /account` creates, renames, reorders and deletes people declaratively, and toggles the flag.
- Marking shared with fewer than two people → 400.
- A person id belonging to another account → 404.
- A PUT that would strip labels → 409 with `affected_lists`; the same PUT with `?confirm=true`
  commits and returns the resulting state.
- Deleting down to one person, confirmed, leaves `is_shared_account: false`, no people, and no
  labelled lists.
- `POST /lists` and `PUT /lists/{id}` accept `account_person_id`; it must belong to the caller.
- `account_person_id` together with `recipient_name` → 400, both directions, on create and update.
- A shared account can create a list with neither.
- List reads carry `account_person_id` and `account_person_name`, including on the viewer schema and
  through `compute_counts`.
- Deleting a person leaves their lists, gifts, shares and claims intact and unassigned.
- Nothing about visibility or claims changes: `can_view_list`, `users_share_access`, the owner's
  claim blindness, and family grants all behave exactly as before.

## 7. Testing

Unit (mocked repo) for the service rules; integration for the endpoints and the model.

- Flag and people: create two, rename one, reorder, add a third, delete one, delete to one (auto
  unmark), fewer than two on marking → 400, duplicate name → 400, whitespace-only name → 400,
  another account's person id → 404.
- Confirmation: unconfirmed destructive PUT → 409 with the right count and **no** database change
  (assert the rows are untouched, not just the status code); confirmed → committed.
- Exclusivity: person + recipient on create → 400; adding a person to a list that has a recipient →
  400; adding a recipient to a list that has a person → 400; clearing one then setting the other →
  200.
- Household list: shared account creates a list with neither → 200.
- Payloads: both fields present on `GiftListRead` (via a collection endpoint, which is what exercises
  `compute_counts`), `GiftListDetailOwner`, and `GiftListDetailViewer`.
- Regression: an existing suite run proves claims, visibility, family grants and simple-mode
  auto-grant are unaffected.
- `scripts/seed_dev.py` gains a shared account with two people and one list each, so the frontend
  tickets have the state to build against.

## 8. Conventions to honour

- **Branch from `release/v0.4.0`, and target it with the PR** — not `main`. Every ticket in this
  project does; see the project-wide spec §9.1. The migration in §2.1 therefore chains from whatever
  is head on `release/v0.4.0` at implementation time, which is what NEU-1226 will have moved if the
  occasions rename lands first.
- **Routers use `db.flush()`, never `db.commit()`** — `get_db` commits on success.
- Domain package shape: `router.py` (thin HTTP), `service.py` (rules, raises domain exceptions from
  `app/services/exceptions.py`), `repository.py` (queries).
- Alembic `render_as_batch=True`; `PRAGMA foreign_keys=ON` is enforced on every connection.
- Pydantic v2 only (`model_config`, `model_dump()`, `from_attributes`).
