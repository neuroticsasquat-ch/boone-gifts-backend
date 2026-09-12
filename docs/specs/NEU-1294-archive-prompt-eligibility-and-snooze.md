# NEU-1294 — Archive-prompt eligibility, snooze table and endpoints

**Ticket:** [NEU-1294](https://linear.app/neuroticsasquatch/issue/NEU-1294/archive-prompt-eligibility-snooze-table-and-endpoints-backend)
**Repo:** `boone-gifts-backend`
**Story:** [NEU-1289](https://linear.app/neuroticsasquatch/issue/NEU-1289/the-app-knows-which-occasions-have-gone-quiet) — "The app knows which occasions have gone quiet"
**Milestone:** M1 — Contract
**Blocks:** [NEU-1315](https://linear.app/neuroticsasquatch/issue/NEU-1315/archive-nudge-in-the-actionable-banner-frontend) (archive nudge in `ActionableBanner`, M4)
**Builds on:** [NEU-1292](https://linear.app/neuroticsasquatch/issue/NEU-1292/occasion-index-endpoint-with-per-viewer-counts-backend) — merged, `6a12d4d`. Its `last_activity_at_expr` is refactored here.
**Project spec:** `docs/specs/occasions-and-navigation-project-spec.md` §8, §11, §12.1
**ADR:** `docs/adr/0005-occasion-activity-is-per-viewer.md` — **amended by this ticket**
**Branch from and target:** `release/v0.6.0` — not `main` (project spec §12.1)

> **A note on "rule 2".** The ticket, the M1 contract and §8 all cite "`CONTEXT.md` rule 2". That is
> the **frontend** repo's rule 2 — *"Owners are blind to claims, and no user sees another's."* This
> repo's equivalent is **invariant 1**. Read invariant 1 when the sources say rule 2.

## What to build and why

`is_archived` exists, and nothing ever asks anyone to set it. A finished Christmas keeps accepting
shares until somebody remembers it is there. This ticket is the whole backend surface for the nudge
that asks: which occasions have gone quiet, who should be asked about them, and remembering that
they said "not yet". The banner that consumes it is NEU-1315, in M4.

Three pieces: one migration, one read endpoint, one write endpoint.

## What to change

| File | Change |
|---|---|
| `alembic/versions/<new>.py` | new — `occasion_archive_prompts`, `down_revision = 'c1f9a7d4e260'` |
| `app/models/occasion_archive_prompt.py` | new model |
| `app/occasions/repository.py` | new `shared_activity_at_expr`; `last_activity_at_expr` refactored to compose it; new `get_archive_prompts`, `upsert_dismissal`, `delete_prompts_for_occasions`, `delete_prompts_by_user` |
| `app/occasions/service.py` | new `list_archive_prompts`, `dismiss_archive_prompt`; two new constants; `update_occasion` re-gated per field |
| `app/occasions/router.py` | new `GET /occasions/archive-prompts`, new `POST /occasions/{id}/archive-prompt/dismiss` |
| `app/schemas/occasion.py` | new `ArchivePrompt` |
| `app/families/service.py` | `delete_family` clears prompt rows before its occasions |
| `app/users/repository.py` | `cascade_delete_user` clears the user's prompt rows |
| `scripts/seed_dev.py` | two stale occasions, one dismissed prompt row, purge ordering |
| `docs/adr/0005-…` | amendment section (see Decision 2) |
| `CONTEXT.md` | one new term, invariant 9 amended (recorded below, **not applied**) |

## The migration — the only one in this project

```python
op.create_table(
    'occasion_archive_prompts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('occasion_id', sa.Integer(), nullable=False),
    sa.Column('dismissed_until', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'occasion_id',
                        name='uq_occasion_archive_prompts_user_occasion'),
)
```

`down_revision = 'c1f9a7d4e260'` (the current head, `add_budgets_table`). Nothing is backfilled and
nothing could be: no prompt has ever been dismissed, and inventing a snooze would suppress a nudge
the user never saw.

`dismissed_until` is `NOT NULL`. A row exists only to record a dismissal, so there is no state in
which the column is meaningless — a nullable one would invite "row present, never dismissed", which
nothing needs and every reader would have to branch on.

## Contract

```
GET  /occasions/archive-prompts                        →  ArchivePrompt[]
POST /occasions/{occasion_id}/archive-prompt/dismiss   →  204 No Content
```

```python
class ArchivePrompt(BaseModel):
    id: int
    name: str
    family_id: int
    family_name: str
```

- **`GET`** returns every occasion the caller should be nudged about, across every family they
  belong to. Takes no parameter of any kind. Ordered `id DESC`. A caller with nothing to answer gets
  `200 []`, never a 404.
- **`POST`** takes no body — the 30 days is the server's rule. `404` if the occasion does not exist,
  `403` if the caller is outside the audience, `204` otherwise.

## Decisions

### 1. The nudge ages on *shared* activity, not the per-viewer clock

```python
def shared_activity_at_expr():
    """max(last share into the occasion, occasion.created_at)"""
```

`last_activity_at_expr(user_id)` is refactored to call it as its first term, so the two cannot
drift.

The per-viewer clock was the obvious choice — the M1 contract and ADR 0005 both say the nudge would
filter on it — and it is wrong here, for the same reason the honest clock was wrong in NEU-1292,
arrived at from the other side.

Under the per-viewer clock, eligibility depends on the caller's own claims, so two members disagree
about whether the same occasion is stale. That much is defensible. What is not: the *shared* half of
the disagreement. Consider a family occasion holding only Gran's own wishlist, with nothing shared in
for seventy days. Gran is nudged. Tom claims a gift from her list today. If eligibility read anyone
else's claims, Gran's prompt would vanish — and Gran would learn that somebody is buying her a
present, and roughly when. That is invariant 1 broken by the *absence* of a banner row, which is
exactly as invisible as ADR 0005's sort order and exactly as disclosive.

So the nudge reads **no claim at all, the caller's included**. Dropping the caller's own claims costs
nothing — they are safe to read, but including them would mean the person actively shopping in an
occasion is spared a prompt the organizer beside them sees, for no benefit — and it buys a property
worth having: **staleness is one fact about the occasion, identical for everyone eligible.** No
user's action can create or destroy another user's prompt, so there is nothing to infer.

`shared_activity_at_expr()` **takes no `user_id`**. The absent parameter is the guarantee: there is
no argument that could widen it to a claim, and the function signature says so at every call site.

`created_at` stays the floor for the same reason NEU-1292 gave it one — an occasion created seventy
days ago that nothing ever happened to is precisely the dead Christmas the nudge exists for, and a
null clock would make M4 decide what null means.

### 2. ADR 0005 is amended in place

ADR 0005 currently states as accepted fact: *"The strip selects it; the nudge filters on it."* After
Decision 1 that sentence is false, and it is the sentence a future reader will land on when they ask
why the nudge does not use `last_activity_at_expr`.

Add a dated **Amendment (2026-09-10, NEU-1294)** section to `docs/adr/0005-…` recording the narrower
expression, the composition that prevents drift, and the reasoning above. One ADR remains the single
answer to "what is this clock and who reads it", which is the document's whole purpose — splitting it
across two files would defeat it.

**Apply the amendment in the implementation PR, not the spec PR**, following NEU-1290 and NEU-1292:
it describes code that is not on `release/v0.6.0` yet.

### 3. The audience: a member, and either an organizer or the creator

```
eligible(caller, occasion) =
        occasion.is_archived = false
    AND shared_activity_at_expr() < now − ARCHIVE_PROMPT_IDLE_DAYS
    AND member_of(caller, occasion.family)
    AND (organizer_of(caller, occasion.family)
         OR occasion.created_by_id = caller.id)
    AND NOT EXISTS (prompt row for (caller, occasion) with dismissed_until > now)
```

**Why the creator.** §8's reason stands: organizer-only leaves a member-created occasion in a family
with an absent organizer permanently un-nudged — the dead Christmas the feature exists for.

**Why membership as well.** A member can leave a family, and `occasions.created_by_id` keeps pointing
at them. A departed creator is not nudged and cannot archive: leaving withdraws what membership
granted (invariant 3's spirit), every other occasion endpoint runs through `_require_member` first,
and the banner should never name a family the caller has left.

### 4. Archiving widens to the creator; renaming does not

This is the correctness fix the audience rule forces, and the ticket does not mention it.

`update_occasion` is organizer-only today (`ORGANIZER_ONLY`, `_require_organizer`), and archiving
*is* `PUT /occasions/{id}` with `is_archived`. So under Decision 3 a member who created an occasion
would be nudged and then get a **403** when they pressed Archive. §8's justification — *"the creator
already had the authority to make it"* — is true of creation and false of archiving.

So `update_occasion` gates **per field**:

| Field | Who |
|---|---|
| `name` | organizer only — unchanged |
| `is_archived` | an organizer, **or** the occasion's creator |

A rename changes a label everyone sees and every budget is filed under. Archiving is reversible,
withdraws no shares, and still serves every My shopping tab — it is the mildest write on an occasion,
and it was carrying the strictest gate.

The gate is on the **field, not the direction**: unarchiving carries the same rule as archiving. A
creator who can close an occasion can reopen one they closed by mistake.

A request setting both fields at once needs the organizer role, because it contains a rename.

### 5. Dismissal is gated on the audience, not on staleness

`POST …/dismiss` re-checks Decision 3's audience terms — membership, and organizer-or-creator — and
deliberately **does not** re-check the 60-day term or the snooze.

The race is real and ordinary: the banner renders, somebody shares into the occasion, and only then
does the user press "Not yet". Re-checking staleness would fail that call with a 409 the user cannot
explain — they pressed a button that was on screen — and would hand NEU-1315 an error branch that
exists only to be swallowed. Anyone who could ever be nudged may record "not yet"; the worst case is
a harmless row on an occasion that is no longer stale.

`UNIQUE (user_id, occasion_id)` makes the write an **upsert**: update `dismissed_until` if a row
exists, insert otherwise. A second dismissal after the snooze lapses extends it rather than
colliding.

**No dismissal-on-activity reset.** §8 settled it: a permanent dismissal that resets on new activity
is surprising, because activity is what happens on an occasion someone is deliberately keeping open.
The date expires and the nudge returns.

### 6. Suppression is evaluated in SQL, never in Python

The snooze term is a correlated `NOT EXISTS` inside the eligibility query, compared against a
`datetime.now(timezone.utc)` bound as a parameter.

This is not a style preference. SQLAlchemy's SQLite `DATETIME` **strips tzinfo on the way in and
returns naive values on the way out** — verified against the running container, not assumed:

```
server_default=func.now()      → '2026-09-10 04:51:06'
datetime.now(timezone.utc)     → '2026-09-10 04:51:06.994568'
```

Both are naive UTC strings, so they compare correctly *in the database* and the 60-day and snooze
filters are sound. But a `dismissed_until` read back into Python is naive, and
`row.dismissed_until > datetime.now(timezone.utc)` raises `TypeError: can't compare offset-naive and
offset-aware datetimes`. Doing the comparison in SQL avoids the trap; doing it in Python means
remembering, every time, to strip the tz first.

The same applies to the idle cutoff: bind `now − 60 days` as a parameter and let SQLite compare.

### 7. A prompt row is inert everywhere except the three FK paths

SQLite runs with `PRAGMA foreign_keys=ON`, so three paths **must** clear prompt rows or the delete is
refused:

| Path | Clears by |
|---|---|
| `app/families/service.py:delete_family` | the family's occasion ids, **before** `delete_occasions_for_family` |
| `app/users/repository.py:cascade_delete_user` | `user_id` |
| `scripts/seed_dev.py:purge` | **both** routes — `occasion_id IN (…) OR user_id IN (…)` — exactly as `Budget` already does, since a fixture user may have dismissed a non-fixture occasion |

In `delete_family`, prompt rows go beside the budgets, before the occasions: same position in the
unwind, same reason.

**Nothing else clears a row.** Archiving an occasion and leaving a family both leave the row in
place. The eligibility query already excludes archived occasions and non-members, so the row is
invisible rather than wrong — and it stays meaningful if the occasion is unarchived or the person
rejoins, which is what a user expects of a snooze they set. Two fewer code paths that have to
remember this table exists.

### 8. Constants, and where the code lives

```python
ARCHIVE_PROMPT_IDLE_DAYS = 60
ARCHIVE_PROMPT_SNOOZE_DAYS = 30
```

Module constants in `app/occasions/service.py`, mirroring `INVITE_EXPIRY_DAYS` in
`app/family_invites/service.py`. Not settings: they are product rules from §8, not deployment knobs,
and a per-environment threshold would make the seed's stale fixture depend on config.

**No new package.** The model gets its own file (`app/models/occasion_archive_prompt.py`, as every
model does); everything else lands in the existing `app/occasions/` module and `app/schemas/occasion.py`.
The whole surface is occasion-scoped, and the eligibility query is an occasions query with two extra
joins.

### 9. `ArchivePrompt` is purpose-built, not derived from `OccasionRead`

Four fields, `BaseModel`, built from scratch rather than subclassing. NEU-1315: *"The prompt names
the occasion and its family and nothing else — no counts, no claimers, no gifts."*

The narrowness is the guarantee. A subclass of `OccasionRead` or a reuse of `OccasionSummary` would
put `my_claimed_count` and `my_bought_count` on a banner payload, and would drag `list_count` and
both claim subqueries into a query that needs none of them. There is no field on `ArchivePrompt` that
could ever carry claim state.

`id`, not `occasion_id` — it matches every other occasion payload, and it is what the dismiss and
archive calls take.

**No `quiet_since`.** Now that the clock reads no claims, a date would be safe to expose — but
NEU-1315 does not want one, and a `datetime` on a prompt invites the next reader to assume it is
`last_activity_at`, which it deliberately is not.

### 10. Route ordering

`GET /occasions/archive-prompts` must be declared **above** `GET /occasions/{occasion_id}`, which is
the note `list_all_occasions` already carries for the same reason. Declared below, FastAPI matches
the parameterised path first and fails to parse `"archive-prompts"` as an `int` — a 422, not a 404,
which is a confusing way to find out about a route ordering bug.

### 11. The seed gains two stale occasions in the Extended Family

Both active, both created by **Tom**, both backdated past the 60-day threshold:

| Occasion | Family | State |
|---|---|---|
| *(a stale occasion)* | Extended | eligible — Tom sees the nudge |
| *(a second stale occasion)* | Extended | eligible **but** carries `dismissed_until = now + 15 days` for Tom |

Two, not one: suppression cannot be seen by hand unless one nudges while the other is snoozed, and
one occasion cannot be in both states.

**Why Extended, and why created by Tom.** Every existing family carries a load-bearing fixture role
the seed comments name: the Boones have **exactly one** active occasion (the sharing control's
single-click case), Extended has two (the select case), Work Friends deliberately has **none** (the
disabled row). Adding an active occasion to the Boones or to Work Friends destroys a fixture; adding
two to Extended only makes "several" more several.

It is also the better test. Tom is a plain **member** of Extended, and any member may create an
occasion — so these two exercise the **creator arm** of Decision 3, the arm §8 widened the rule for,
and they prove Decision 4, since Tom can archive them only because he created them.

`occasions.created_at` and `list_occasion_shares.created_at` are both `server_default=func.now()`, so
the backdating must be **explicit** on the occasion rows. Give the stale occasions no shares at all
(the simplest way to be stale, and §5.1 says an occasion with no lists is the likeliest to need
action); if a share is added later, its `created_at` must be backdated too or the occasion stops
being stale.

## `CONTEXT.md` edits

Recorded here rather than applied, following NEU-1290 and NEU-1292: these describe the state *after*
the code lands, so applying them to `release/v0.6.0` now would make `CONTEXT.md` lie. **Apply them in
the implementation PR**, alongside the ADR 0005 amendment.

* **Terms** gains **Shared activity** — "The clock the archive nudge ages an occasion by: the later
  of the last share into it and its own creation. Reads no claim, by anyone — so no user's shopping
  can create or remove another user's prompt. The first term of *Occasion activity*, and the whole of
  what the nudge sees." Where it lives: `computed, app/occasions/repository.py:shared_activity_at_expr`.
* **Terms** gains **Archive prompt** — "A standing question to one account about one occasion that
  has gone quiet: archive it, or not yet. 'Not yet' is a dated snooze, not a permanent dismissal."
  Where it lives: `occasion_archive_prompts`.
* **Invariant 9**'s sentence "only an organizer may rename or archive one" becomes "**only an
  organizer may rename one; an organizer or the occasion's creator may archive or unarchive one**" —
  with the reason, that archiving is reversible and withdraws nothing while a rename changes a label
  everyone's budgets are filed under.

## Acceptance criteria

1. An occasion with no share for 60 days is reported to an **organizer** of its family.
2. The same occasion is reported to its **creator**, even when they are not an organizer.
3. It is **not** reported to a member who is neither, nor to a creator who has **left** the family.
4. It is **not** reported once archived.
5. **Another user's claim or purchase changes nothing** — an occasion eligible before a claim is
   still eligible after it, for every viewer. Likewise the caller's own claim.
6. `POST …/dismiss` suppresses the occasion for that caller and **for that caller only** — another
   eligible viewer still sees it.
7. Suppression **lapses**: a row whose `dismissed_until` has passed stops suppressing, and the
   occasion is reported again.
8. A second dismissal **extends** the snooze rather than failing on the unique constraint.
9. Dismissal succeeds on an occasion that is not currently stale (`204`, no 409) and is refused
   outside the audience (`403`) and for an unknown occasion (`404`).
10. A creator who is not an organizer **can archive** the occasion they created, and **cannot rename**
    it.
11. Deleting a family, and purging a user, both succeed with prompt rows present.
12. A caller with nothing to answer gets `200 []`.

## Tests

**The disclosure guard is the one that matters.** It needs two users, an occasion stale by 60+ days,
and a list the *caller owns* shared into it: assert the caller's `GET /occasions/archive-prompts`
response is **byte-identical** before and after the other user claims and purchases from that list.
The whole of Decision 1 is that this assertion holds.

Also cover:

- Both audience arms (organizer, creator) and both exclusions (plain member, departed creator).
- Archived occasions absent; an occasion with **no lists at all** present (the `created_at` floor).
- The boundary: 59 days idle absent, 61 days idle present.
- Snooze lifecycle — dismiss suppresses, a lapsed row does not, a second dismissal extends, and one
  caller's dismissal leaves another eligible viewer's prompt alone.
- Dismissal status codes: `204` on a non-stale occasion, `403` for a plain member, `404` for an
  unknown id.
- `update_occasion`: creator archives (200), creator unarchives (200), creator renames (403),
  creator renames **and** archives in one request (403), non-creator member archives (403).
- `delete_family` and `cascade_delete_user` with prompt rows present — these must exercise the real
  foreign keys, so they belong where FKs are actually enforced.
- `tests/integration/test_migration_occasion_archive_prompts.py`, joining the existing per-migration
  suite: the unique constraint holds one row per `(user, occasion)`, both foreign keys refuse an
  orphan, `dismissed_until` refuses NULL, and the downgrade drops the table.
- `tests/integration/test_owner_blindness.py` gains the new endpoint to its sweep. Trivially blind
  now that no claim feeds it — which is the point: if the query ever grows a claim term, the sweep
  fails rather than review catching it.

## Out of scope

- **The banner itself** — NEU-1315, frontend, M4.
- **`ConfirmDialog` on the archive action** — NEU-1315 and the §7.3 confirmation audit.
- **Any change to `GET /occasions`** — its contract is fixed by M1 and two consumers ship against it.
- **Clearing prompt rows on archive or on leaving a family** — Decision 7.
- **A configurable idle or snooze period** — Decision 8.
- **Pagination.** Project spec §3: out of scope until a real user passes ~15 connections.
- **Notifying anyone by email.** The nudge is a banner row and nothing else.
