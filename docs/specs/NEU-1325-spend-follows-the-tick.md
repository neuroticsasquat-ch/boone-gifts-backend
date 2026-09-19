# NEU-1325 — Spend follows the tick

**Ticket:** [NEU-1325](https://linear.app/neuroticsasquatch/issue/NEU-1325) · Boone Gifts: Maintenance
**Repo:** boone-gifts-backend only. No frontend change.
**Planned:** 2026-09-14

## What and why

A claim keeps its `amount_paid` when the claimer unticks bought, so re-ticking does not make them
retype what they paid. Today that held amount still counts toward the budget rollup's `spent`, so a
gift the user has said they have *not* bought is charged against their occasion or folder budget.
The only way to get it out of the total is to clear the amount, save, then untick — which throws
away the number the untick was supposed to preserve.

From this ticket on, **the budget counts an amount only while the claim is ticked bought.** The
amount itself is still stored on the unticked claim; the rollup simply treats it as zero.

This reverses a rule that was written down deliberately (the `_spend_select` docstring, the AGENTS.md
Budgets bullet "`spent` counts recorded money; the counts describe shopping", and the integration
test `test_an_amount_survives_unticking_and_stays_in_the_spend`). The old reasoning was that money
which left the claimer's pocket should never silently vanish from the total. The product decision
now is that an unticked gift is *not bought*, and a budget line that charges for it is wrong, not
cautious. The disclosure rule for **priced-ness** — a bought gift with no amount counts toward
`unpriced_count` and never toward `spent` — is untouched.

## Rule

For the caller's own claims in one scope (an occasion the claims are filed under, or a folder whose
lists they sit on):

| Claim state | `spent` | `bought_count` | `unpriced_count` | `total_count` |
|---|---|---|---|---|
| ticked, amount recorded | + amount | +1 | — | +1 |
| ticked, no amount | — | +1 | +1 | +1 |
| **unticked, amount recorded** | **— (was: + amount)** | — | — | +1 |
| unticked, no amount | — | — | — | +1 |

`remaining` is `amount - spent` as before, and may still go negative. Nothing about who may read a
rollup changes: it is still only ever the caller's own claims (`CONTEXT.md` invariant 1).

## Acceptance criteria

1. Tick a claimed gift bought with an amount, then untick it: the occasion's shopping payload
   reports `spent` without that amount, `bought_count` down by one, `unpriced_count` unchanged,
   `total_count` unchanged. Re-tick it (with the body omitted, so the held amount stands): `spent`
   includes the amount again. Both the occasion and folder rollups behave the same, because they
   share one select.
2. An amount written by `PATCH /claims/{id}` onto a claim that is not ticked bought does not count
   toward `spent` either. The frontend never offers that path; this pins the rule for anyone using
   the API directly.
3. `DELETE .../purchase` still leaves `amount_paid` on the claim, and the shopping row for the
   unticked claim still carries it in `amount_paid` — the frontend seeds the re-tick prompt from it.
4. A ticked claim with no amount still counts toward `bought_count` and `unpriced_count` and never
   toward `spent` (unchanged; the existing test keeps passing).
5. `GET /occasions/{id}/shopping`, `GET /folders/{id}/shopping`, and every `PUT`/`DELETE .../budget`
   response reflect the new `spent` — they all read the same rollup, so this follows from one change.
6. The documentation that states the old rule is corrected everywhere it appears (see below). A
   reader of any one of them must not find the reversed rule.

## Technical decisions

- **One change, in the aggregate.** `app/claims/repository.py:_spend_select` sums `amount_paid`
  inside a `case` gated on `Claim.purchased_at.isnot(None)` (mirroring how `unpriced_count` is
  already gated), still coalesced to `0`. `bought_count` (`count(purchased_at)`), `total_count`, and
  `unpriced_count` are untouched. Both `get_spend_for_occasion` and `get_spend_for_folder` inherit
  it. No schema change, no migration, no new field on `BudgetRollup`.
- **The store is unchanged.** `unpurchase_gift` keeps `amount_paid`; `PurchaseCreate`'s
  omitted-vs-null distinction stays exactly as it is. This ticket changes what is *counted*, not what
  is *kept*.
- **Rewrite the docstring, don't just delete it.** `_spend_select`'s docstring currently argues for
  the old rule. Replace that paragraph with the new rule and its reason — an unticked gift is not
  bought, so it is not spend — so the next reader does not "fix" it back.
- **Tests.** Flip and rename `test_an_amount_survives_unticking_and_stays_in_the_spend` in
  `tests/integration/routers/test_budgets.py` to assert `spent == "0.00"`, `bought_count == 0`,
  `unpriced_count == 0`, `total_count == 1`, and that the shopping row still carries
  `amount_paid == "85.00"`. Add the re-tick half (spend returns) and the PATCH-on-unticked case
  (criterion 2), and one folder-scope assertion so the shared select is proven on both tabs. The
  unit tests in `tests/unit/services/test_budgets.py` mock the repository and need no change.
- **Docs to correct**, all in this repo:
  - `AGENTS.md` → Budgets: replace the bullet "`spent` counts recorded money; the counts describe
    shopping …" with the new rule.
  - `app/schemas/budget.py:BudgetRollup` docstring: add that `spent` counts ticked claims only.
  - `docs/specs/shopping-lists-project-spec.md` §7: add one sentence — an amount held on an unticked
    claim is stored but not counted.
  - `CONTEXT.md` invariant 10: already updated alongside this spec (uncommitted in the working
    tree); ship it in the same PR.
- **Frontend:** nothing. Its comments, `CONTEXT.md` rule 5 and tests describe only the
  "amount survives untick" half, which stays true. The tab already re-reads the whole shopping
  payload on every purchase change, so the corrected `spent` renders with no client work.

## Out of scope

- Any indication on an unticked shopping row that an amount is being held (decided: show nothing —
  the number reappears in the prompt on re-tick).
- Offering the Add/Edit amount control on unticked rows.
- A new rollup field disclosing held-but-uncounted amounts.
- Clearing `amount_paid` on untick.
