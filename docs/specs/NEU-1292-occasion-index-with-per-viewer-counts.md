# NEU-1292 — Occasion index endpoint with per-viewer counts

**Ticket:** [NEU-1292](https://linear.app/neuroticsasquatch/issue/NEU-1292/occasion-index-endpoint-with-per-viewer-counts-backend)
**Repo:** `boone-gifts-backend`
**Story:** [NEU-1287](https://linear.app/neuroticsasquatch/issue/NEU-1287/the-app-can-list-every-occasion-i-can-see) — "The app can list every occasion I can see"
**Milestone:** M1 — Contract
**Blocks:** [NEU-1298](https://linear.app/neuroticsasquatch/issue/NEU-1298/occasion-strip-on-lists-frontend) (occasion strip on `/lists`)
**Also consumed by:** M4's archive nudge (project spec §8) — it reads the same clock
**Project spec:** `docs/specs/occasions-and-navigation-project-spec.md` §5.1, §5.2, §5.3, §8, §10.2, §13
**Branch from and target:** `release/v0.6.0` — not `main` (project spec §12.1)

> **A note on "rule 2".** The ticket, the M1 contract and §5.3 all cite "`CONTEXT.md` rule 2". That
> is the **frontend** repo's rule 2 — *"Owners are blind to claims, and no user sees another's."*
> This repo's equivalent is **invariant 1**, and rule/invariant 2 here is the unrelated
> *"Visibility has exactly one predicate."* Read invariant 1 when the sources say rule 2.

## What to build and why

Occasions are fetchable one family at a time (`GET /families/{id}/occasions`), and no endpoint
carries the counts or the sort key the strip needs. A viewer in eight families would need eight
requests before first paint and eight more for the counts — and would still miss the occasions with
no lists, which §5.1 says are the ones most likely to need action.

One endpoint returns every occasion in every family the caller belongs to, each carrying its family
name, its list count, the caller's own claimed/bought counts, and a `last_activity_at` to sort on.

**No migration.** Every timestamp this needs already exists: `list_occasion_shares.created_at`,
`claims.claimed_at`, `claims.purchased_at`. (`occasion_archive_prompts` belongs to M4's nudge
ticket, not this one.)

### The constraint that shapes everything

`last_activity_at` **must never include another user's claim.** The strip sorts on it, so an
occasion containing only the caller's own list would rise to the top of their strip the moment
somebody claimed from it — a badge by another name, telling the viewer that someone is buying them
a present and roughly when. A share into an occasion leaks nothing, because the list it carries is
already visible to every member.

The obvious implementation — *"the last claim on any list in this occasion"* — is the wrong one.
See `docs/adr/0005-occasion-activity-is-per-viewer.md`.

## What to change

| File | Change |
|---|---|
| `app/schemas/occasion.py` | new `OccasionSummary(OccasionRead)` |
| `app/occasions/repository.py` | new `last_activity_at_expr`, new `get_occasion_summaries` |
| `app/occasions/service.py` | new `list_all_occasions` |
| `app/occasions/router.py` | new `GET /occasions` |
| `scripts/seed_dev.py` | Carol claims from Tom's own list, filed under Boone Christmas |
| `CONTEXT.md` | new term, one invariant amended (see below) |
| `docs/adr/0005-…` | new — already written by `/planit` |

## Contract

```
GET /occasions?archived=false  →  OccasionSummary[]
```

`OccasionSummary` = `OccasionRead` + `family_name: str`, `list_count: int`,
`my_claimed_count: int`, `my_bought_count: int`, `last_activity_at: datetime`.

- Every occasion in every family the caller is a member of. **No family path parameter, and no
  parameter naming another user** — the two `my_*` fields and the claim half of the clock are the
  caller's by construction, not by filtering.
- A caller in no families gets `[]`, not a 404. There is no per-occasion membership check: the
  query is scoped by the caller's memberships, so an occasion they cannot see is not a row that
  gets filtered out, it is a row that never exists.
- Ordered `last_activity_at DESC, id DESC`.

## Decisions

### 1. The counts are keyed on the stored filing

`my_claimed_count` and `my_bought_count` count claims where `Claim.occasion_id == occasion.id` and
`Claim.user_id == caller.id` — nothing else.

This is exactly what the occasion's **My shopping** tab and its budget line already count:
`get_shopping_for_occasion` and `get_spend_for_occasion` both key on the filing alone and
deliberately do not join back to the shares, because filing is stored and never re-derived (ADR
0003, NEU-1269 §4). Counting by "gifts on lists shared to this occasion" instead would put a number
on the card that contradicts the tab printed beneath it on the occasion page.

Follow `get_spend_for_occasion`'s column choice: `my_bought_count` counts `purchased_at`,
`my_claimed_count` counts claims. They are driven off different columns on purpose.

**Accepted consequence:** a claim filed under an occasion survives its list being unshared, so
`my_claimed_count` can exceed anything `list_count` would suggest — an occasion with 0 lists can
legitimately show claims. That is the filing behaving as specified, not a bug, and the card renders
it fine because §5.2 suppresses the bought line only when `my_claimed_count` is zero.

### 2. `last_activity_at` is non-null, floored at `created_at`

```
last_activity_at = max(
    the last share into the occasion,          # may not exist
    the caller's own last claim or purchase,   # may not exist
    occasions.created_at,                      # always exists
)
```

Creation always precedes the other two, so it is a **floor**, not a third rule — the field is never
null and the client needs no null branch in its sort.

It also makes M4 correct with no special case. §8 nudges an occasion with "no activity for 60 days";
an occasion created 70 days ago that nothing ever happened to is precisely the dead Christmas still
accepting shares that the nudge exists for. A nullable field would force the nudge to decide what
null means — almost certainly by falling back to `created_at` itself, putting a second copy of the
definition in M4 and breaking the "defined once" contract.

### 3. One SQL expression, shared with M4

`last_activity_at_expr(user_id)` in `app/occasions/repository.py` returns a SQLAlchemy expression,
not a value. `get_occasion_summaries` is its first consumer; M4's nudge embeds the identical
expression in its own `WHERE` clause, alongside joins this endpoint has no use for
(`occasion_archive_prompts`, the family-organizer role).

That is what "defined once, server-side" buys: M4 filters and sorts on the clock **in the database**
without paying for `list_count` and both claim counts on every occasion just to read one timestamp.

### 4. Two SQL traps, both load-bearing

**a. Do not join `list_occasion_shares` and `claims` into one grouped query.** Two `LEFT JOIN`s fan
the rows out and `list_count` comes back multiplied by the claim count. Use **correlated scalar
subqueries** (or separate grouped CTEs joined in) so each aggregate is computed over its own rows.

**b. Coalesce every term before `max()`.** SQLite's *scalar* `max(a, b, …)` returns `NULL` if **any**
argument is `NULL` — verified: `select max(NULL, '2026-01-01')` → `NULL`. So the naive spelling
produces a null `last_activity_at` for exactly the empty occasion Decision 2 says must never be
null, and §5.1 says is the common case:

```python
# WRONG — null for any occasion with no shares, or no claims of the caller's
func.max(shares_max, claims_max, Occasion.created_at)

# RIGHT — every term floored before the comparison
func.max(
    func.coalesce(shares_max, Occasion.created_at),
    func.coalesce(claims_max, Occasion.created_at),
)
```

For the claim term, select `max(claimed_at)` and `max(purchased_at)` as two aggregates in the
subquery and combine them outside it. Do not nest a scalar `max` inside an aggregate `max` — it
reads as the same function meaning two different things, and `purchased_at` is nullable and not
guaranteed to be later than `claimed_at` (unticking a purchase keeps the amount, and `PATCH
/claims/{id}` can move things).

### 5. `list_count` is a raw aggregate, pinned by a test

`COUNT` over `list_occasion_shares` for the occasion — **not** filtered through `can_view_list`.

The two are provably equal here: `can_view_list`'s occasion arm is "the list is shared to an
occasion of a family the viewer belongs to", and the caller is a member of this occasion's family or
the occasion would not be in their index. `app/occasions/service.py:list_lists` filters anyway and
documents the redundancy as worth one query per list — but across every occasion in every family
that is exactly the fan-out §10.2 exists to kill, on the app's landing page.

Buy the safety back with a test instead: `list_count` must equal the number of rows
`GET /occasions/{id}/lists` returns for the same caller. If `can_view_list` ever gains a term, that
test fails loudly rather than the card quietly lying.

### 6. Ordered server-side, with an `id` tiebreak

`last_activity_at DESC, Occasion.id DESC`.

The server holds the definition and is the only place that can order on it without a consumer
re-deriving it. The tiebreak is not decoration: after Decision 2, two occasions created in the same
seeded transaction share `created_at` to the second and therefore tie. Without it, "the first four"
is whatever the query plan yields, the §5.1 cap test has no stable expectation, and two members of
one family can see the strip in different orders. The client may still re-sort; it never has to.

### 7. `?archived` is an exact match, default `false`

`Occasion.is_archived == archived`, exactly as `get_occasions_for_family` already reads it —
`archived=true` returns the archived ones **only**, never a union. One parameter name means one
thing across both occasion index endpoints, and neither consumer wants a union: the strip renders
active occasions and the nudge only nudges non-archived ones.

### 8. The seed gains another user's claim on Tom's own list

Every claim in `scripts/seed_dev.py` today is Tom's; nobody ever claims from a list Tom owns. So the
dev database cannot show this ticket's whole point by hand — the strip looks identical whether the
implementation is right or wrong.

`tom_christmas` is already shared into both `boones_christmas` and `extended_christmas`, so a claim
by Carol on its gifts, filed under `boones_christmas`, lands exactly where it needs to. With the
correct implementation Tom's Boone Christmas card does not move and his bought line does not change;
with the obvious one it jumps to the front of his strip the moment the seed runs.

Note `add_gifts` only claims the **first** gift of a list (`index == 0`), and `file_under` files
*Tom's* claims — Carol's filing needs its own line or a widened helper.

M4's two seed additions (a stale occasion, a dismissed prompt row) stay with M4.

### 9. `GET /families/{id}/occasions` is left alone

Project spec §10.4 leaves it unchanged, and it is declared `response_model=list[OccasionRead]` — a
per-viewer widening would change a response two other screens already read. The new endpoint is a
sibling, not a replacement. Only `last_activity_at_expr` is shared, and only with M4.

## `CONTEXT.md` edits

Recorded here rather than applied, following NEU-1290: the invariant edit describes the state
*after* the code lands, so applying it to `release/v0.6.0` now would make `CONTEXT.md` lie.

* **Terms** gains **Occasion activity** — "The clock an occasion sorts and ages by: the later of the
  last share into it and the *viewer's own* claim or purchase filed under it, floored at the
  occasion's creation. Per-viewer by construction — never another user's claim." Where it lives:
  `computed, app/occasions/repository.py:last_activity_at_expr`.
* **Invariant 1**'s closing sentence widens from "reveals only *that* claims exist, never counts,
  gift names, or claimer names" to also name **a timestamp that dates one** — so the next person to
  add a sort key to an owner-visible surface reads the prohibition before writing it rather than
  after review.

## Acceptance criteria

1. One request returns every non-archived occasion in every family the caller belongs to,
   **including occasions with no lists**.
2. Each row carries `family_name`, `list_count`, `my_claimed_count`, `my_bought_count` and a
   **non-null** `last_activity_at`.
3. `my_claimed_count` and `my_bought_count` **change when the caller claims and purchases**, and
   **do not change when another user does** — on a list the caller owns and on one they do not.
4. `last_activity_at` **moves** on a share into the occasion and on the caller's own claim or
   purchase, and **does not move** on another user's claim or purchase.
5. An occasion with no shares and no claims of the caller's reports `last_activity_at ==
   occasion.created_at`.
6. Rows come back ordered `last_activity_at DESC, id DESC`.
7. `archived=true` returns archived occasions only; the default and `archived=false` return active
   ones only.
8. The endpoint takes no parameter naming another user, and no family parameter.
9. A caller in no families gets `200 []`.
10. `list_count` equals the number of lists `GET /occasions/{id}/lists` returns for the same caller.

## Tests

**The rule-2 guard is the most important test in the project (§13).** It needs two users and a list
the caller *owns*: assert that when the other user claims and purchases from it, the caller's
`my_claimed_count`, `my_bought_count` and `last_activity_at` are all **byte-identical** to their
values before the claim — and that the same claim by the caller moves all three.

Also cover:

- Occasions from **several** families in one response, and one with **no lists** present.
- `last_activity_at` moves when a list is shared in.
- `last_activity_at == created_at` for an untouched occasion — the coalesce trap in Decision 4b
  regresses to `null` here, so assert the value, not just truthiness.
- Ordering, including the tie: two occasions with identical `last_activity_at` come back `id DESC`,
  stably across repeated requests.
- `archived` in all three forms (omitted, `false`, `true`).
- A caller in no families → `[]`.
- `list_count` against `GET /occasions/{id}/lists` for the same caller (Decision 5's guard).
- A claim filed under an occasion whose list was later unshared still counts (Decision 1's accepted
  consequence), and the row survives with `list_count` at 0.
- **No fan-out:** an occasion with several lists *and* several of the caller's claims reports the
  true `list_count`, not the product (Decision 4a).

`tests/integration/test_owner_blindness.py` should gain the new endpoint to its sweep.

## Out of scope

- **`occasion_archive_prompts` and the archive nudge** — M4. This ticket ships only the clock the
  nudge will read.
- **Pagination.** Project spec §3: out of scope until a real user passes ~15 connections.
- **Any change to `GET /families/{id}/occasions`** — Decision 9.
- **The strip itself** — NEU-1298, frontend.
- **Retiring `GET /connections/{id}/lists`** — §10.3, a different ticket.
