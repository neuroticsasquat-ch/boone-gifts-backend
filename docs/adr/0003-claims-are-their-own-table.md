# ADR 0003 — Claims are their own table

**Status:** Accepted (2026-09-08)
**Project:** [BG: Shopping Lists](https://linear.app/neuroticsasquatch/project/bg-shopping-lists-6fdd1e4a3cc1)

## Context

A claim lives on the gift row today: `gifts.claimed_by_id`, `gifts.claimed_at`,
`gifts.purchased_at`. The gift belongs to the list owner. The claim belongs to somebody else, and
`CONTEXT.md` invariant 1 says the owner must never see it.

That separation is currently **serializer discipline**, not structure. `GiftOwnerRead`
(`app/schemas/gift_list.py:55`) simply omits the three fields; `GiftRead` includes them; `get_list`
picks between them on `owner_id == user_id`. It works only for as long as everyone remembers.

It has already slipped once. `GiftListRead.claimed_count` is computed in a model validator
(`app/schemas/gift_list.py:116`) for *every* list row `GET /lists` returns, including lists the
caller owns. The API has been telling owners how many of their own gifts are claimed since the
endpoint was written. Nothing renders it, so nobody noticed.

This project needed to add `amount_paid` — what the claimer actually spent, as opposed to
`gifts.price`, which is the owner's asking price and is shown to everyone. Putting a second party's
money on the owner's row would have added a fourth thing to remember, on the same rule that had
already failed once.

## Decision

**Promote the claim to its own entity.**

```
claims
  id
  gift_id      → gifts.id, unique      -- one claim per gift
  user_id      → users.id, indexed     -- the claimer
  occasion_id  → occasions.id, nullable, indexed
  claimed_at
  purchased_at   nullable
  amount_paid    Numeric(10,2), nullable
```

`gifts.claimed_by_id`, `gifts.claimed_at` and `gifts.purchased_at` are dropped. There is nothing
claim-shaped left on the gift row, so an owner-facing serializer cannot leak claim state by
forgetting something — it has nothing to forget. `claimed_count` is fixed on the way past: it is
computed from `claims` and returned only on viewer-facing rows.

`occasion_id` is the claimer's private filing of their own spend, resolved when the claim is made
(automatic when the list is shared to exactly one occasion the claimer can see, a prompt when
several, null for a direct share) and editable afterwards. It is deliberately **not** derived from
the share at read time: a budget whose history rewrites itself when someone revokes a share or
archives an occasion is worse than no budget.

## Consequences

**Good**

- Owner-blindness stops being a rule and becomes a property of the schema.
- Budget rollups are a plain aggregate over one table: `sum(amount_paid) where user_id = ? and
  occasion_id = ?`. No join through sharing, and no dependence on sharing still being in place.
- Unclaim is a row delete, which clears purchase state and amount paid without the explicit
  `purchased_at = None` reset the service does today (`app/gifts/service.py:68`).
- A recorded spend survives the share being revoked, the occasion being archived, and the claimer
  leaving the family.

**Bad, and accepted**

- **A wide migration.** Claim/unclaim/purchase/unpurchase, `has_claimed_gifts`, `any_claims_by_users`,
  the teardown cascades in `connections/repository.py`, `list_families/repository.py` and
  `users/repository.py`, viewer-side sorting, and every test that touches claim state all move.
- One more join on the viewer's list-detail read. Immaterial at this scale, and worth naming so
  nobody "optimises" the column back onto `gifts`.
- The `unique (gift_id)` constraint hard-codes one claimer per gift. That matches today's behaviour
  exactly; a future split-the-cost feature would relax it, and this shape makes that a constraint
  change rather than a redesign.

## Alternatives rejected

- **`gifts.amount_paid`** — by far the smallest change, and the reason it was rejected is written
  above: it extends a discipline that had already failed silently, on the same row, with money.
- **A `purchases` side table, claim staying on `gifts`** — gets money off the owner's row without the
  full move, but then claim state lives in two places and unclaim has to remember to clean up the
  second. Half the migration for less than half the benefit.
