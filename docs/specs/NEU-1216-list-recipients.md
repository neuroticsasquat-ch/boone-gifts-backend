# NEU-1216 — Lists can name who they're for

**Ticket:** [NEU-1216](https://linear.app/neuroticsasquatch/issue/NEU-1216/lists-can-name-who-theyre-for-proxy-shared-account-lists)
**Project:** unassigned
**Repos:** `backend` (columns, schemas, share email) and `frontend` (create/edit form, attribution helper, display sites)

---

## 1. Why

Two household situations the app cannot express today:

1. **Someone keeps a list for a partner who will never sign up.** Tom maintains Beth's list. The
   family sees it attributed "from Tom," because that is the only name available.
2. **Two people share one email address and one account, but want a list each.** Both lists carry
   the same account name, so the family cannot tell whose is whose.

Both reduce to a single gap: **a list needs to name who it is *for*, separately from the account that
owns it.** Sharing (`app/shares/`), family grants (`app/list_families/`), visibility
(`app/access.py`) and claiming (`app/gifts/service.py`) are all keyed on `owner_id`, and neither
situation asks for any of that to change.

The seam already exists. `owner_name` is a live property on the model
(`app/models/gift_list.py:33-35`) with no storage of its own, feeding six display sites and nothing
else. Nothing in the codebase currently reasons about who a list is *for*.

## 2. What to build

Two nullable columns on `lists` and the display logic they drive. **This ticket is display-only** —
see §4 for what that deliberately excludes.

### 2.1 Data model

```python
# app/models/gift_list.py
recipient_name: Mapped[str | None] = mapped_column(String(255), default=None)
recipient_has_account: Mapped[bool | None] = mapped_column(Boolean, default=None)

@property
def kept_for_absent_person(self) -> bool:
    """This list is kept on behalf of someone who has no account and will never
    log in. Distinct from a list for a co-resident who shares this login — that
    person reads the list themselves, so nothing about it is hidden from them."""
    return self.recipient_name is not None and self.recipient_has_account is False
```

`String(255)` matches `User.name` (`app/models/user.py:19`).

**The state is genuinely three-valued** — no recipient / a recipient with an account / a recipient
without one — and a nullable boolean is the only shape that maps to it exactly. The hazard is that
`not gift_list.recipient_has_account` is **true for a list with no recipient at all**, which is
precisely how the warning and the "kept by" label would get written by accident.

**Therefore: no call site anywhere touches `recipient_has_account` directly.** The property above is
the only reader in the backend; `attributionFor` (§2.6) is the only reader in the frontend.

A NOT NULL `recipient_absent` defaulting to false was considered and rejected: `false` would mean
both "no recipient" and "a recipient who has an account," so every consumer would have to consult
`recipient_name` anyway.

### 2.2 Migration

Alembic revision on top of the current head `c4f2a91d7e30`. Follow the `seen_at` precedent
(`e9730fad709a:23-28`) — direct `op.add_column` on the upgrade with the reason comment, batch mode
on the downgrade:

```python
# Use ADD COLUMN directly (SQLite supports it natively for simple additions)
# to avoid batch mode's drop/recreate which fails on FK constraints.
op.add_column('lists', sa.Column('recipient_name', sa.String(length=255), nullable=True))
op.add_column('lists', sa.Column('recipient_has_account', sa.Boolean(), nullable=True))
```

**No `server_default` and no backfill.** Existing rows come out NULL, which is exactly today's
behavior. Note that no nullable *string* column in this repo carries a server default — server
defaults appear only on NOT NULL boolean/timestamp additions (`e721ca9a6ebf:25-32`).

### 2.3 Schemas and validation

`app/schemas/gift_list.py` — add both fields to `GiftListCreate`, `GiftListUpdate`, `GiftListRead`,
`GiftListDetailOwner` and `GiftListDetailViewer`:

```python
recipient_name: str | None = None
recipient_has_account: bool | None = None
```

**Trap:** `GiftListRead.compute_counts` (`schemas/gift_list.py:65-83`) is a `mode="before"` validator
that builds an **explicit dict**. Fields absent from that dict are silently dropped. Both new keys
must be added there or every list-collection endpoint will return them as `None`.

Both fields go on the **viewer** schema too — the viewer's label depends on the flag to choose
between "for Beth · kept by Tom" and "from Jane." It discloses only that Beth has no account, which
"kept by Tom" already implies.

Two validators on the input schemas:

```python
@field_validator("recipient_name")
@classmethod
def normalize_recipient_name(cls, v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip() or None

@model_validator(mode="after")
def require_name_with_account_answer(self):
    if self.recipient_has_account is not None and self.recipient_name is None:
        raise ValueError("recipient_has_account requires a recipient_name")
    return self
```

The normalizer follows `family_invite.py:19-22`, the only existing normalizer in the schema layer; a
whitespace-only name would otherwise render "for  " and trigger nothing. The structural validator
follows `ConnectionCreate.require_user_id_or_email` (`schemas/connection.py:10-14`).

**No pydantic `max_length`.** No string field in `app/schemas/` has one, and a lone constraint here
would be an inconsistency, not an improvement.

### 2.4 API

No new endpoints. Both fields ride on the existing `POST /lists` and `PUT /lists/{id}`.

- `app/lists/service.py:create_list` and `app/lists/repository.py:create_list` take the two fields
  and pass them to the `GiftList` constructor.
- Updates need nothing: `lists/router.py:56` already does `model_dump(exclude_unset=True)` and the
  repo does blind `setattr` (`lists/repository.py:55-59`), so an explicit `null` clears a field
  while an omitted key leaves it alone.

**The two fields always travel together.** They are one control in the UI (§2.7), so the client
sends both or neither. A payload carrying `recipient_has_account` alone is rejected by the validator
above — deliberately, since a flag with no name is meaningless. Sending neither (e.g. renaming a
list) passes untouched, because `exclude_unset` leaves both at their `None` defaults.

### 2.5 Attribution rules

The flag decides. This is the whole feature:

| List state | Viewer sees | Owner sees on their own rows |
|---|---|---|
| No recipient | "from Tom" *(as today)* | nothing *(as today)* |
| Recipient **with** an account | "from Jane" | "for Jane" |
| Recipient **without** an account | "for Beth · kept by Tom" | "for Beth" |

Rationale for the split: on a shared account, Jane *is* the person a viewer would talk to, so naming
the account as well is noise. When the recipient is absent, Tom is the only reachable human, so he
has to stay visible.

Link behavior on `ListDetail`'s `ViewerHeader` (`ListDetail.tsx:164-182`), which links the owner to
their connection profile when an accepted connection exists: in the **absent** case the link moves to
the "kept by Tom" half and "Beth" is plain text — linking "Beth" to Tom's profile would be simply
wrong. In the other two cases the link is unchanged.

### 2.6 The attribution helper

All of the above lives in **one** frontend module, so six display sites cannot drift apart:

```ts
// frontend/src/lib/attribution.ts
type ListAttribution =
  | { kind: "owner";  subject: string; keeper: null }    // "from {subject}"
  | { kind: "shared"; subject: string; keeper: null }    // "from {subject}"
  | { kind: "absent"; subject: string; keeper: string }  // "for {subject} · kept by {keeper}"

export function attributionFor(list: ListLike): ListAttribution
export function recipientLabel(list: ListLike): string | null   // "for Beth" | null, owner-side rows
```

`kind` selects the "from"/"for" preposition and tells a caller which half to link (`subject` for
`owner`/`shared`, `keeper` for `absent`).

### 2.7 Create and edit form

`CreateList.tsx` currently renders Name, Description, and — full mode only — the family checkboxes.
Simple mode's form is two fields, and keeping it that way is a hard constraint.

**Progressive disclosure.** One unchecked control below Description:

> ☐ This list is for someone else

Unchecked, the form is byte-for-byte what it is today. Checked, it reveals:

- A text input, "Who is this list for?"
- A **required** radio pair: "{Name} uses this app" / "{Name} doesn't use this app", falling back to
  "They use this app" / "They don't use this app" before a name is typed.

The radio is required rather than a default-off checkbox on purpose. The flag is a property of the
*person*, not the list, and free text (§4) gives nothing to keep it consistent across that person's
lists. A default-off checkbox is exactly how it would drift; a required choice cannot be forgotten.
It is also what decides whether the warning appears at all.

Submission is blocked while the disclosure is open and no radio is chosen. Unchecking the disclosure
sends `null` for both fields.

`EditListHeader` (`ListDetail.tsx`) gets the same control, seeded from the list's current values.
**Every transition is permitted** — self-list to recipient list and back, and either radio to the
other. Both fields are display-only, so nothing cascades: no access path shifts and no claim is
invalidated. Locking them would only ever produce a stuck user, since `delete_list` refuses once any
gift is claimed (`lists/service.py:62-68`) and a typo found in December would be uncorrectable by any
route the UI offers.

### 2.8 The keeper's warning

Because the owner stays blind to claims (§4), someone keeping a list for an absent person can neither
see what has been claimed nor claim anything themselves. They must be told, or they will list the
gift they are personally buying and a relative will duplicate it.

**On the create form**, the moment "doesn't use this app" is selected:

> You won't see who's claimed what on this list, and you can't claim anything on it yourself. So if
> there's something you're planning to get Beth, leave it off — otherwise someone else may buy it
> too, and Beth will end up with two.

Falling back to "them" where the name is blank.

**On the list itself** — a muted line under the header on any list where `kept_for_absent_person`,
shown to the owner only. Not a dismissible alert; plain grey text that stays put:

> You can't see or make claims on Beth's list. Leave off anything you're buying them yourself.

Creation is the moment the keeper has the *fewest* gifts in mind; most get added over the following
weeks, which is exactly when the temptation arrives. A once-seen sentence on a form does not cover
that.

**Neither warning fires on the shared-account branch**, where the advice is actively wrong — Jane is
on that login and reads the list herself.

Register: plain second person, no "proxy", no "claim state", no "owner". Matches the existing
`RevokeClaimsDialog` copy (`FamiliesTab.tsx:143-172`).

### 2.9 Display sites

| Site | Change |
|---|---|
| `Lists.tsx:129` (Shared with Me) | `attributionFor` |
| `Lists.tsx:97-100` (owned rows) | **new** — `recipientLabel` |
| `Dashboard.tsx:96` (Shared with Me) | `attributionFor` |
| `Dashboard.tsx:69-72` (My Lists) | **new** — `recipientLabel` |
| `FamilyLists.tsx:65` | `attributionFor` |
| `ListDetail.tsx` `ViewerHeader` | `attributionFor`, with the link placement of §2.5 |
| `ListDetail.tsx` `OwnerHeader` | **new** — `recipientLabel` as subtitle, warning line beneath |
| `CollectionDetail.tsx:253` | `attributionFor` — note this changes the wording from "by X" to "from X"/"for X", accepted for consistency |
| `SharedWithTab.tsx:149,154` | **unchanged** — "Tom has shared this list with:" is about who performed the sharing, which is still Tom |

The owner-side additions matter because Tom now has his list and Beth's list side by side in a view
that renders no attribution at all today — distinguishable only by whatever he typed as the list
name.

### 2.10 Share email

`render_list_shared_email` (`app/email/list_shared.py:15-16`) hardcodes the possessive:

> **Tom** shared **their list** "Beth's Christmas" with you on **Boone Gifts**.

Which is untrue for a list with a recipient, and reachable: `shares/service.py` has no `simple_mode`
gate, so a full-mode Tom can share Beth's list with a connection who is in no family at all.

Add an optional `recipient_name` parameter and branch the possessive — "Tom shared **Beth's list**
"Christmas Ideas" with you" — falling back to "their list". Both the HTML and text bodies.
`create_share` (`shares/service.py:39-44`) passes `gift_list.recipient_name`. **The subject line is
unchanged**: it is Tom doing the sharing either way.

## 3. Acceptance criteria

**Data and API**

1. `POST /lists` with a name, `recipient_name` and `recipient_has_account` persists all three and
   returns them.
2. `POST /lists` with no recipient fields creates a list with both columns NULL and behaves exactly
   as before.
3. `recipient_name: "  "` normalizes to NULL; `recipient_name: " Beth "` normalizes to `"Beth"`.
4. `recipient_has_account` supplied without `recipient_name` is rejected with a 422.
5. `PUT /lists/{id}` with explicit `null` for both fields clears them; a `PUT` that touches only
   `name` leaves both untouched.
6. Every list-collection endpoint (`GET /lists`, all filters, and the collection detail lists)
   returns both fields — i.e. `compute_counts` was updated.
7. Both fields appear on the viewer's detail response as well as the owner's.
8. `kept_for_absent_person` is `False` for a list with no recipient, `False` for a recipient with an
   account, and `True` only for a named recipient with `recipient_has_account = False`.

**Attribution**

9. A viewer of a list with no recipient sees "from Tom", linked as today.
10. A viewer of a list whose recipient has an account sees "from Jane", linked to the owner as today.
11. A viewer of a list whose recipient has no account sees "for Beth · kept by Tom", with the link on
    "Tom" and "Beth" as plain text.
12. The owner's own rows show "for Beth" on a list with a recipient and nothing on a list without
    one.
13. `SharedWithTab` still reads "Tom has shared this list with:" regardless of recipient.

**Form**

14. With the disclosure unchecked, the create form renders exactly the fields it does today, and
    simple mode still sees no family control.
15. Checking the disclosure reveals the name input and the radio pair; the radio labels use the typed
    name once one exists.
16. The form cannot be submitted with the disclosure open and no radio selected.
17. Unchecking the disclosure and submitting sends `null` for both fields.
18. The edit control is seeded from current values, and every transition — including recipient list
    back to self-list, and either radio to the other — succeeds and takes effect immediately.

**Warning**

19. Selecting "doesn't use this app" shows the create-form warning; selecting "uses this app" shows
    nothing.
20. A list where `kept_for_absent_person` shows the muted line under the header **to the owner
    only**; a viewer never sees it.
21. A list whose recipient has an account shows no warning anywhere.

**Email**

22. Sharing a list with a recipient emails "Tom shared Beth's list …"; sharing a list without one is
    byte-for-byte unchanged, subject included.

**Unchanged**

23. Visibility, family grants, the simple-mode auto-grant on create and on join, and the unseen-share
    badge all behave exactly as before.
24. The owner still receives `GiftOwnerRead` with no claim fields, and `claim_gift` still rejects the
    owner — on lists with a recipient as much as any other.

## 4. Out of scope / deferred

- **Letting a keeper see or make claims on the list they keep.** Considered and deferred: the
  owner/viewer split is currently a clean binary, and a third permission state is worth building only
  once someone has actually missed it. **If it is ever built, it cannot be gated on
  `recipient_name is not null`** — a shared-account list sets that field too, and using it would
  expose claims on Jane's list to the login Jane shares. That is what `recipient_has_account` is
  being captured for now, while the person filling in the form still knows the answer.
- **A `list_recipients` table.** Free text was chosen over a per-account person record; the
  management surface (rename, delete, and what happens to that person's lists) is more than this
  scale warrants. The accepted cost is drift — see §5.
- **Transferring a list** if the absent recipient later signs up. Every claim on it belongs to
  someone who would need to keep it, and the keeper's family grants are not the newcomer's. If it
  happens once, do it by hand.
- **Per-person grouping or sorting on `FamilyLists`.** It groups by family and sorts by `updated_at`;
  a household with three recipients yields three individually-labelled rows, which reads fine.
- **An account-level "this account is shared" flag** making the recipient field required. The field
  being optional is what keeps it invisible for everyone who does not need it.
- **A feature flag.** Two nullable columns and a conditional label on a single-deploy family app.
- **A migration test.** The precedent at `integration/test_migration_list_family_shares.py` exists
  because that revision carried a data backfill with a visibility invariant to protect. This one
  adds two nullable columns and backfills nothing.
- **The existing claim-state leaks.** An owner can already infer claims from the 409 on deleting a
  claimed gift (`gifts/service.py:34-40`) and the list-delete message rendered verbatim at
  `ListDetail.tsx:319-322`. Both predate this ticket and are untouched by it.

## 5. Notes for implementation

- **Tests.** Extract the attribution logic first (§2.6) and unit test all three `kind` values plus
  `recipientLabel` there once; each page test then asserts one representative string rather than
  re-deriving the matrix. Extend `CreateList.test.tsx` (disclosure, required radio, warning, payload
  shape), `ListDetail.test.tsx` (both header variants, warning visibility by role),
  `FamilyLists.test.tsx`, `Dashboard.test.tsx` (which covers the owner-side label, so no new
  `Lists.test.tsx` is needed for a page that has never had one), and `CollectionDetail.test.tsx`.
  Backend: a new `tests/unit/schemas/test_gift_list_schema.py` for the two validators (precedent:
  `unit/schemas/test_family_invite_schema.py`), the tri-state property in
  `integration/models/test_gift_list.py`, create/update/clear round-trips and the 422 in
  `integration/routers/test_lists.py`, and the possessive branch in `unit/services/test_shares.py`,
  which already patches the send path.
- **Commands.** `task test` / `task test-file -- <path>` in both repos; `task migration -- 'add
  recipient to lists'` to scaffold the revision.
- **The drift risk is the one accepted bet in this design.** Free text plus a per-list flag means the
  same person can end up marked as having an account on one list and not on another. The symptom
  will be the §2.8 warning appearing on one of Beth's lists and not another — that is the first place
  to look if anyone reports the warning behaving strangely. The required radio (§2.7) is what keeps
  this improbable; it is not what makes it impossible.
- **No token or auth impact.** `recipient_name` is a column on `lists`, not a JWT claim, so unlike
  `User.name` (`dependencies.py:40`) nothing needs re-issuing when it changes.
- No `CONTEXT.md` or ADRs exist in either repo. The three-state invariant in §2.1 and the attribution
  table in §2.5 are the material worth promoting into one later.
