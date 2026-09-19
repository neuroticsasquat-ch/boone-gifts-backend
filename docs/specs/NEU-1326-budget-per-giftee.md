# NEU-1326 — Budget per giftee

**Ticket:** [NEU-1326](https://linear.app/neuroticsasquatch/issue/NEU-1326/allow-budgeting-per-recipient)
**Repos:** `boone-gifts-backend` **and** `boone-gifts-frontend` — one ticket, two halves. This file is
checked in to both, identical, because either repo's `/implementit` must find the whole story. Ship
the backend first: the frontend reads fields that do not exist until it lands.
**Project:** Boone Gifts: Maintenance. **No milestone, no project description, no project spec** —
there are no shared contracts to honour beyond the two `CONTEXT.md` files, the ADRs named below, and
the shopping-lists project spec §7 and §9.2, which describe the budget line this ticket extends.
**Story / parent:** none. **Blocked by:** nothing. **Blocks:** nothing. **Related:** nothing.
**Builds on (merged):** NEU-1325 (spend follows the tick), NEU-1216 / NEU-1228 (who a list is for).
**Planned:** 2026-09-14

## Vocabulary

The ticket says "recipient". The backend glossary already reserves **Recipient** for a person with
no account (`lists.recipient_name`, invariant 8), so the wider concept gets its own word:

- **Giftee** — who a list is *for*: its owner, or the account person it is marked for, or the
  recipient it is kept for. Derived from the list, never stored as a row (ADR 0006). Two lists
  agreeing on all three facts are one giftee.
- **Giftee budget** — what the caller means to spend on one giftee within one occasion or folder.
- **Overall budget** — the existing `budgets` row, unchanged in storage.
- **Allocated** — the sum of the caller's giftee budgets in a scope.

Both `CONTEXT.md` files were updated alongside this spec (Giftee, Giftee budget, Budget, Rollup,
My shopping; backend invariant 10; frontend rule 5). Ship those edits in the same PRs.

## What to build and why

A single number per occasion is too coarse for the way people actually shop: "$600 for Christmas"
is really "$200 for Gran, $150 each for the kids, and whatever is left for Beth". Today the shopping
tab groups by list and carries one budget line, so the user keeps that split in their head or in a
spreadsheet.

From this ticket on, the **My shopping** tab groups by **giftee**, every giftee in scope gets a
group — empty if the caller has claimed nothing for them yet — and every group carries its own
budget line with the same shape as the overall one. The overall line learns how much of it has been
allocated and whether the allocation exceeds it, and an overall the user never set reads as the sum
of what they allocated, labelled as such.

Nothing here widens who sees what. Every giftee budget is the caller's own; every rollup counts the
caller's own claims; the giftees shown are derived from lists the caller can already view. Backend
`CONTEXT.md` invariants 1, 2 and 10 hold unchanged.

## What to change

### `boone-gifts-backend`

1. New table `giftee_budgets` and its migration (decision 2).
2. `app/budgets/giftees.py` — the giftee key: build from a list, parse from a path segment
   (decision 1).
3. `app/budgets/repository.py` — giftee budget CRUD and the four cascade deletes (decision 7).
4. `app/claims/repository.py` — per-giftee spend, and `giftee_key` + the three giftee columns on
   the shopping row (decision 4).
5. `app/list_occasions/repository.py` / `app/folders/repository.py` — no change; the service reuses
   `get_lists_shared_to_occasion` and `get_lists_for_folder` (decision 3).
6. `app/budgets/service.py` — the giftee set, per-giftee rollups, the extended overall rollup, and
   `set_giftee_budget` / `clear_giftee_budget` (decisions 3, 5).
7. `app/schemas/budget.py` — `BudgetRollup` gains four fields; new `GifteeRead` and `BudgetBlock`.
   `app/schemas/claim.py` — `ShoppingItem` gains `giftee_key`; `ShoppingPayload` gains `giftees`.
8. `app/occasions/router.py` + `service.py`, `app/folders/router.py` + `service.py` — the four new
   endpoints (decision 6).
9. `app/account/service.py`, `app/folders/service.py`, `app/families/service.py`,
   `app/users/repository.py` — call the cascades (decision 7).
10. `AGENTS.md` Budgets section and migration table; `docs/specs/shopping-lists-project-spec.md`
    §7 and §9.2 gain a paragraph each.

### `boone-gifts-frontend`

1. `src/types/index.ts` — `BudgetRollup`, `ShoppingItem`, `ShoppingPayload`, new `Giftee`,
   `BudgetBlock`.
2. `src/api/occasions.ts`, `src/api/folders.ts` — `setGifteeBudget`, `clearGifteeBudget`.
3. `src/lib/giftees.ts` — grouping and labelling (decisions 8, 9).
4. `src/components/BudgetLine.tsx` — split into the line and a reusable editor; the overall line's
   new clauses; a giftee variant (decisions 10, 11, 12).
5. `src/components/MyShopping.tsx` — group by giftee, empty groups, row-level list name
   (decisions 8, 9).
6. `AGENTS.md` My shopping / budget notes.

## Decisions

### 1. The giftee key is a string the server mints and the client treats as opaque

Three shapes, one per way a list can be "for" someone:

| List state | Key | Name shown | Keeper |
|---|---|---|---|
| Neither marked | `owner:{owner_id}` | owner's name | — |
| `account_person_id` set | `person:{account_person_id}` | the person's name | owner's name |
| `recipient_name` set | `absent:{owner_id}:{name_b64}` | the recipient name | owner's name |

`name_b64` is the recipient name, UTF-8, base64url **without padding**. It exists so that a name
with a space, a slash or a dot is still one URL path segment and the key needs no escaping on the
wire. The client never builds a key and never reads inside one: it receives keys on `giftees[]`
and on each item, and sends one back on a write.

`app/budgets/giftees.py` owns both directions: `key_for(gift_list) -> str` and
`parse_key(key) -> GifteeRef` (a small frozen dataclass of `owner_id`, `account_person_id`,
`recipient_name`), raising `ValueError` on anything malformed. It is the only module that knows the
format. The three columns on a `GiftList` are mutually exclusive already (invariant 7), so
`key_for` is total.

### 2. Storage: `giftee_budgets`, the triple plus the key

```python
class GifteeBudget(Base):
    __tablename__ = "giftee_budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "occasion_id", "giftee_key", name="uq_giftee_budgets_user_occasion_key"),
        UniqueConstraint("user_id", "folder_id", "giftee_key", name="uq_giftee_budgets_user_folder_key"),
    )
    id, user_id (FK users, index)
    occasion_id (FK occasions, nullable), folder_id (FK folders, nullable)
    giftee_key: String(300)                       # decision 1; the unique handle
    owner_id: FK users                            # the list owner the giftee resolves through
    account_person_id: FK account_people, nullable, index
    recipient_name: String(255), nullable
    amount: Numeric(10, 2)
```

Why both the key **and** the three columns: uniqueness needs a single non-null column, because
SQLite never collides two NULLs in a unique index and `(owner_id, NULL, NULL)` would be storable
twice. The cascades need real foreign keys, because "or the FK refuses" is how this repo catches a
forgotten teardown (invariant 10). Spend is grouped in SQL by the list's three columns, and the
budget row carrying the same three is what makes the join symmetrical. The service is the only
writer of all four and derives the key from the triple, so they cannot disagree.

Migration: one revision on top of `f6b2c9e41a58`, `op.create_table` with the FKs above and both
unique constraints, plain `op.drop_table` on downgrade. No backfill. Add the row to the migration
table in `AGENTS.md`. The scope rule — exactly one of `occasion_id` / `folder_id` — is enforced in
the service by the existing `_require_one_scope`, for the same reason the `budgets` table has no
check constraint.

### 3. The giftee set is a union of three sources, computed per request

For one caller in one scope, the giftees shown are the union of:

1. **Visible lists in scope, minus the caller's own.** Occasion: `get_lists_shared_to_occasion`
   filtered by `can_view_list` — exactly what the Lists tab shows. Folder: `get_lists_for_folder`
   (folder reads already route through the one predicate). Lists the caller owns are dropped:
   they cannot claim on them, so there is nothing to budget.
2. **Lists behind the caller's own claims in scope** — the lists the shopping rows stand on.
   Filing is stored, not derived, so a claim on a since-unshared list still shows, and its giftee
   must have a group to sit in.
3. **The caller's own giftee budget rows in scope.** A row whose lists have all left the scope —
   or whose recipient was renamed — is still a group: empty, labelled, removable. Nothing that
   counts toward `allocated` may be invisible.

Each entry needs a display name and a keeper name: the owner's `User.name`, the
`AccountPerson.name`, or the `recipient_name`. Sources 1 and 2 have the list in hand. Source 3 has
only the triple; resolve the owner and the person by id (one query each, `IN` over the ids). A
person id that no longer resolves cannot happen — decision 7 deletes the row with the person.

Order: giftees with at least one shopping row first, then the rest; within each half by name
(case-insensitive), then key. The client renders array order and does not re-sort, the rule the
occasion index already carries.

### 4. Per-giftee spend is one grouped select beside `_spend_select`

`_spend_select` gains a sibling, `_spend_by_giftee_select`, that joins `GiftList` and groups by
`GiftList.owner_id, GiftList.account_person_id, GiftList.recipient_name`, emitting the same four
aggregates per group. `get_spend_by_giftee_for_occasion` / `_for_folder` apply the same two `where`
clauses as today's pair and return `dict[str, dict]` keyed by giftee key. Spend follows the tick
and the unpriced disclosure are inherited because the aggregate expressions are shared, not
copied — extract them into module-level helpers so both selects read one definition.

`_shopping_select` adds `GiftList.owner_id`, `GiftList.account_person_id`, `GiftList.recipient_name`
to its projection, and `_shopping_rows` emits `giftee_key` (via `key_for`) alongside the existing
`list_id` / `list_name`. Row order is unchanged (list then gift); the client groups on the key.

### 5. The rollup grows, and the overall is never written from the split

`BudgetRollup` gains:

| Field | Meaning |
|---|---|
| `allocated: Decimal` | Sum of the caller's giftee budgets in scope, `0.00` when none. Includes orphaned rows — they are shown, so they count. |
| `unallocated: Decimal \| None` | `amount − allocated`; null when `amount` is null. May be negative: over-allocation is reported, never refused. |
| `target: Decimal \| None` | The figure the money line is measured against: `amount` when set; else `allocated` when at least one giftee budget exists; else null. |
| `allocation_count: int` | How many giftee budgets exist in scope. What lets the client say "the sum of 3 people's budgets". |

`remaining` is now `target − spent`, null when `target` is null. `amount` keeps its meaning — the
set overall, or null — and remains the client's one predicate for offering *set* versus *edit*.
Existing tests that assert `remaining` against `amount` still pass, because `target == amount`
whenever `amount` is set.

Each giftee's rollup is a plain `BudgetRollup` too, with `allocated = 0.00`, `unallocated = None`,
`target = amount`, `allocation_count = 0` — the same shape so `BudgetLine` renders either. (A giftee
budget is a leaf; nothing allocates beneath it.)

`set_budget` / `clear_budget` on the overall are untouched except that the rollup they return is the
extended one. `set_giftee_budget` and `clear_giftee_budget` mirror them, keyed by `giftee_key`, and
return a `BudgetBlock`. **Nothing in either path reads or writes the other table.**

Validation on a giftee write: parse the key (malformed → 400); the giftee must be in sources 1 or
2 of decision 3 for this caller and scope (else 404 — the client can only have got the key from
this scope's payload, so a miss means the list has since gone). A `DELETE` with no row is 404, as
the overall's is. The amount uses `BudgetWrite` unchanged.

### 6. Endpoints: PUT/DELETE by key, answering with the whole budget block

```
PUT    /occasions/{id}/giftees/{giftee_key}/budget   body: BudgetWrite   → 200 BudgetBlock
DELETE /occasions/{id}/giftees/{giftee_key}/budget                       → 200 BudgetBlock
PUT    /folders/{id}/giftees/{giftee_key}/budget     body: BudgetWrite   → 200 BudgetBlock
DELETE /folders/{id}/giftees/{giftee_key}/budget                         → 200 BudgetBlock

BudgetBlock  = { budget: BudgetRollup, giftees: list[GifteeRead] }
GifteeRead   = { key: str, kind: "owner" | "person" | "absent", name: str,
                 keeper: str | None, list_count: int, budget: BudgetRollup }
ShoppingPayload = { budget, giftees, items }       # BudgetBlock + items
ShoppingItem   += giftee_key: str
```

A giftee write answers with the block rather than one rollup because it moves two things at once:
that giftee's line and the overall's `allocated` / `target`. The existing overall `PUT` / `DELETE`
keep returning `BudgetRollup`: an overall write changes no giftee's figures, only the hint each
unbudgeted giftee shows, which the client derives from the overall. Access is the scope's own gate,
as today: family membership for an occasion (`_load_for_member`, archived included), ownership for
a folder. 403 / 404 mapping copies the existing budget routes.

`keeper` is the owner's name for `person` and `absent`, null for `owner`. `list_count` is how many
lists in sources 1 ∪ 2 resolve to this giftee — the client uses it to decide whether rows name
their list (decision 9).

### 7. Cascades: four deletes, all beside the ones that already exist

| Event | Existing call | Add |
|---|---|---|
| Folder deleted | `delete_budgets_for_folder` | `delete_giftee_budgets_for_folder` |
| Family deleted (its occasions) | `delete_budgets_for_occasions` | `delete_giftee_budgets_for_occasions` |
| User purged | `delete_budgets_by_user` | `delete_giftee_budgets_by_user` — rows the user **set** *and* rows whose `owner_id` **is** the user (their lists are going, and with them every giftee they resolved through) |
| Account person removed (`replace_account`) | `repo.clear_labels` then `repo.delete_people` | `delete_giftee_budgets_for_people(person_ids)` **before** `delete_people`, or the FK refuses |

A recipient rename on a list is deliberately **not** a cascade (ADR 0006). A list leaving the
scope — unshared, removed from the folder, archived — is not one either: the row stays, and shows
as an empty group by decision 3.

### 8. The tab groups by giftee key, and every giftee gets a group

`MyShopping` replaces `groupByList` with `groupByGiftee(giftees, items)` in `src/lib/giftees.ts`:
one group per entry of `giftees[]` in array order, each holding the items whose `giftee_key`
matches. An item whose key matches no giftee cannot happen (source 2 of decision 3 guarantees the
group), but the helper tolerates it by appending a group with the item's key and no budget, rather
than dropping a claim — a section that claims to hold everything must never quietly lose a row.

A group with no items renders its header, its budget line, and one muted sentence:
"Nothing claimed for {name} yet." The scope-level empty state ("You haven't claimed anything for
this occasion yet.") is shown only when `items` **and** `giftees` are both empty — a folder with no
lists, or an occasion nobody has shared into.

### 9. Labels: the name alone, the keeper only on collision; the list only when it matters

`gifteeLabel(giftee, all)`: the giftee's `name`, unless another entry in `all` has the same name
(case-insensitive), in which case `person` reads `"{name} · {keeper}'s account"` and `absent` reads
`"{name} · kept by {keeper}"` — the wording `attribution.ts` already uses. Two `owner` giftees with
the same name stay identical: there is nothing truthful to add, and it is the case the app already
lives with on every shared row.

Within a group, a row shows a muted `from {list_name}` only when that giftee's `list_count > 1`.
The common one-list giftee stays as clean as today's list-grouped card.

### 10. `BudgetLine` becomes a line plus an editor, used at two levels

Extract the editor (field, validation regex, Save / Cancel / Remove, the failure behaviour) into
`BudgetEditor`, parameterised by two callbacks: `save(amount) → Promise<T>` and
`clear() → Promise<T>`, plus `onSaved(T)`. `BudgetLine` keeps the overall's summary and tally and
mounts the editor with the overall endpoints; the new `GifteeBudgetLine` mounts it with the giftee
endpoints and writes the returned `BudgetBlock` into the cache entry (`budget` and `giftees`,
leaving `items` alone). Both still use `shoppingKey(scope)` from `lib/shopping.ts`; no second key.

The field's `id` gains the key (`budget-amount-{giftee_key}`) so several editors can be open at
once without colliding labels.

### 11. The overall line's new clauses

Money line (`summarize`): measured against `target`, not `amount`. With `amount` null and `target`
non-null it reads `$142.00 of $230.00 spent · $88.00 left` exactly as a set budget would; the tally
line then says where the figure came from.

Tally line (`tally`), clauses joined with ` · `:

1. `3 of 7 bought` — unchanged.
2. `2 purchases with no amount recorded` — unchanged, non-zero only.
3. Allocation, one of:
   - `amount` set, `allocation_count > 0`, `unallocated ≥ 0`: `$150.00 of $200.00 allocated to people`
   - `amount` set, `unallocated < 0`: `$230.00 allocated · $30.00 over your budget`
   - `amount` null, `allocation_count > 0`: `budget is the sum of 3 people's budgets` (singular:
     `1 person's budget`)
   - otherwise: no clause.

`unallocated` is rendered through `formatMoney` with the sign moved into the word, the way
`remaining` already is. The Set / Edit button still reads `amount === null`, so a derived target
offers **Set budget**, and setting one replaces the derived figure with the typed one.

### 12. The unbudgeted giftee's hint

When the overall `amount` is set and a giftee's `budget.amount` is null:

- the giftee's editor field carries `placeholder={formatMoney(unallocated)}`, and
- a muted line beside its **Set budget** control reads `{unallocated} of your {amount} not yet
  allocated` (or `{over} over your budget` when negative, with no placeholder).

Saving with the field empty saves nothing, as today. The placeholder is never copied into the
value: `BudgetLine`'s "nothing honest to pre-fill" reasoning stands, and a proposal to give one
person everything left is exactly the number the user did not choose. With no overall set there is
nothing to allocate from, and neither the placeholder nor the hint appears.

### 13. What does not change

- The overall `budgets` row, its endpoints, its uniqueness, its cascades.
- `_spend_select` semantics: spend follows the tick, unpriced is disclosed.
- Who can read a shopping tab, and that it is only ever the caller's own claims.
- Row order from the backend, the purchase and amount controls on a row, and every rule in
  `MyShopping`'s existing tests about them.
- The Lists tab, list detail, `attribution.ts`, and the "for Beth" wording anywhere outside the
  shopping tab.

## Acceptance criteria

**Backend**

1. `GET /occasions/{id}/shopping` and `GET /folders/{id}/shopping` return `{ budget, giftees, items }`;
   every item carries a `giftee_key`, and every distinct key on `items` appears in `giftees`.
2. `giftees` holds one entry per giftee resolved from: visible lists in scope not owned by the
   caller, lists behind the caller's claims in scope, and the caller's giftee budget rows in scope.
   A list the caller cannot view contributes no entry; a list the caller owns contributes none.
3. Two lists with the same owner and no marking are one giftee; two lists by one keeper both
   `recipient_name = "Beth"` are one giftee; the same name kept by two owners is two giftees;
   a list marked for an account person is keyed on the person, not the owner.
4. Giftee order is: those with at least one item first, then the rest; each half by name then key.
5. `PUT .../giftees/{key}/budget` creates or replaces the caller's own row and answers 200 with
   `{ budget, giftees }`; `budget.allocated` and `budget.allocation_count` reflect the write.
   A second caller in the same family sees no change to their own payload.
6. `DELETE .../giftees/{key}/budget` answers 200 with the block, 404 when no row exists.
7. A malformed key is 400; a well-formed key for a giftee not in scope for this caller is 404;
   both endpoints 403 a non-member / non-owner and 404 an unknown scope, like the overall's.
8. A negative amount is refused (422) by `BudgetWrite`, unchanged.
9. Per-giftee `spent`, `bought_count`, `total_count`, `unpriced_count` count only that giftee's
   lists, follow the tick, and disclose unpriced purchases; their sum across giftees equals the
   overall's figures.
10. Overall rollup: `amount` null and no giftee budgets → `target` null, `remaining` null,
    `allocated = 0.00`, `allocation_count = 0`. `amount` null and two giftee budgets of 100 and 130
    → `target = 230.00`, `remaining = 230 − spent`, `allocation_count = 2`. `amount = 200` with the
    same two → `target = 200.00`, `allocated = 230.00`, `unallocated = -30.00`. `amount = 200` with
    one of 150 → `unallocated = 50.00`.
11. Setting or clearing the overall never creates, changes or deletes a giftee budget row, and vice
    versa.
12. A giftee budget whose lists have all left the scope (share revoked, list removed from folder)
    still appears as an empty giftee with its budget, and still counts toward `allocated`.
13. Renaming a list's `recipient_name` leaves the old giftee's budget row as an empty group under
    the old name and starts the new name with no budget.
14. Deleting an account person (through `PUT /account`) deletes every giftee budget keyed on it, in
    every scope, for every user. Deleting a folder, a family, or purging a user takes the giftee
    budgets in those scopes; purging a user also takes every giftee budget resolving through that
    user's lists. No FK error in any path.
15. The migration upgrades and downgrades cleanly against a real SQLite file, and both unique
    constraints hold: a second row with the same `(user, scope, key)` is refused.
16. `tests/integration/test_owner_blindness.py` still passes; nothing on `giftees[]` or a giftee
    rollup reveals another account's claim, spend, or budget.

**Frontend**

17. The tab renders one card per entry of `giftees[]`, in array order, headed by the giftee's
    label, with that giftee's budget line and its rows beneath.
18. A giftee with no rows renders the header, the budget line, and "Nothing claimed for {name}
    yet."; the scope-level empty state renders only when both `giftees` and `items` are empty.
19. Two giftees sharing a name render as `Beth · kept by Tom` / `Beth · kept by Jane`, or
    `Gran · Tom's account`; a unique name renders bare.
20. A row shows `from {list name}` only when its giftee's `list_count` is greater than one.
21. Setting a giftee budget calls `PUT .../giftees/{key}/budget` on the tab's scope, and the
    returned block updates both that giftee's line and the overall's tally without a refetch;
    removing one calls `DELETE` on the same path. Folder scope hits the folder path.
22. The overall money line measures against `target`; with a derived target the tally says
    `budget is the sum of N people's budgets`; with a set target it says how much is allocated, or
    how far the allocation exceeds it. No allocation clause when nothing is allocated.
23. An unbudgeted giftee, with an overall set, shows the unallocated amount as the field's
    placeholder and as a hint beside Set budget; with the allocation already over, the hint says so
    and there is no placeholder; with no overall set, neither appears. The placeholder is never the
    saved value.
24. Every existing `MyShopping` and `BudgetLine` test about ticking, amounts, validation, failures
    and folder routing still passes, with fixtures extended to carry `giftees` and `giftee_key`.

## `CONTEXT.md` edits

Already applied in both repos alongside this spec, uncommitted. Backend: **Budget**, **Rollup**
rows amended; **Giftee** and **Giftee budget** rows added; invariant 10 extended. Frontend:
**My shopping** and **Budget** rows amended; **Giftee** row added; rule 5 extended. ADR 0006
(backend) records why a giftee is derived rather than stored. Commit them with the code.

## Tests

**Backend**

- `tests/integration/routers/test_giftee_budgets.py` (new): criteria 1–14 — one test per criterion
  is about the right grain; the fixtures in `test_budgets.py` (member, occasion, folder, a claimed
  gift) are the starting point. The three-source union, the two-keeper collision, and the
  account-person deletion each get their own test.
- `tests/integration/routers/test_budgets.py`: extend the rollup tests for the four new fields
  (criterion 10); the existing assertions stay.
- `tests/integration/test_migration_giftee_budgets.py` (new, precedent `test_migration_budgets.py`):
  upgrade, both unique constraints, FK enforcement, downgrade.
- `tests/unit/services/test_budgets.py`: `key_for` / `parse_key` round-trips including a name with
  spaces and a slash, the `ValueError` cases, and the overall rollup assembly with the repository
  mocked (`target` / `unallocated` arithmetic).
- `tests/integration/test_owner_blindness.py`: add the two new endpoints' responses to the sweep.

**Frontend**

- `src/lib/giftees.test.ts` (new): grouping keeps array order and never drops an item; label
  collision rules; the singular/plural allocation sentence.
- `src/components/MyShopping.test.tsx`: criteria 17–21, 24. The MSW handlers gain the giftee
  budget routes for both scopes.
- `src/components/BudgetLine.test.tsx`: criteria 22–23; the editor extraction must leave every
  existing case green.
- Commands: `task test` in each repo; `task migration -- 'add giftee_budgets'` to scaffold the
  revision. Do not report green on local runs alone — CI is the arbiter (frontend `AGENTS.md`).

## Out of scope / deferred

- A `giftees` table, merging two keepers' "Beth" into one person, or following a recipient rename
  (ADR 0006). If a rename ever needs following, the budget rows already carry the triple.
- Budgeting for a giftee on a list the caller owns (they cannot claim on it).
- Refusing an allocation that exceeds the overall. A budget is a target, not a limit; the overage
  is stated.
- Any change to the Lists tab, list detail, the occasion strip, or `attribution.ts`.
- Per-giftee budgets outside a scope (a standing "Gran is always $200"). Budgets remain per
  occasion or per folder.
- Suggesting an allocation (splitting the overall evenly, or from asking prices). The placeholder
  shows what is left; it proposes nothing.
