# Domain model — Boone Gifts backend

The vocabulary this codebase uses, and the invariants that hold across it. Conventions,
commands, and architecture live in [`AGENTS.md`](AGENTS.md); this file is only about what
the words mean and what must stay true.

## Terms

| Term | Means | Where it lives |
|---|---|---|
| **Account** | One login. The unit of identity everywhere: one family member, one connection, one claimer | `users` |
| **List** | A gift list owned by exactly one account | `lists` |
| **Gift** | An item on a list. Carries the owner's asking price, and nothing about who has claimed it | `gifts` |
| **Claim** | One account's private intent to buy a gift, with what it cost. Invisible to the list's owner | `claims` |
| **Amount paid** | What the *claimer* spent. Distinct from `gifts.price`, the owner's asking price, which every viewer sees | `claims.amount_paid` |
| **Connection** | An accepted relationship between two accounts. A prerequisite for a direct share — **not** itself a grant of visibility | `connections` |
| **Direct share** | A grant of one list to one account | `list_shares` |
| **Family** | A named group of accounts, with organizers and members | `families`, `family_members` |
| **Occasion share** | A grant of one list to one family occasion. Not implied by co-membership. Was a *family grant*, pointed at the family itself | `list_occasion_shares` |
| **Folder** | An account's private grouping of lists it can see — "Christmas 2026". Was called an *occasion*, and before that a *collection* | `folders`, `folder_items` |
| **Occasion** | A family's shared gifting occasion — "Boone Family · Christmas 2026". Owned by a family, carries **no dates** | `occasions` |
| **Active occasion** | An occasion with `is_archived = false` | `occasions.is_archived` |
| **Budget** | What one account means to spend on one occasion, or on one folder. Private to the account that set it; there is no family budget | `budgets` |
| **Rollup** | A budget with the caller's own spend counted against it — target, spent, remaining, and the bought/total/unpriced counts | computed, `app/budgets/service.py` |
| **Recipient** | A person with **no account** for whom an account keeps a list | `lists.recipient_name` |
| **Shared account** | An account used by more than one person, e.g. a couple sharing one login | `users.is_shared_account` |
| **Account person** | A named person on a shared account. **A label, never an identity** | `account_people` |

Deliberately *not* in the vocabulary: "collection" (renamed to occasion, then to folder),
"family list" (a list reached through an occasion share is just a shared list), and "simple mode"
(retired entirely — see `docs/adr/0004-simple-mode-is-retired.md`). **"Occasion" now means the
family's, never the user's** — the user's curated set is a *folder*, and the name `occasions` was
vacated by the rename precisely so the family concept could claim it.

## Invariants

1. **The owner never sees claims on their own list.** This is structural, not discipline: the claim
   is its own row and there is nothing claim-shaped left on `gifts`, so an owner-facing serializer
   has nothing to forget (ADR 0003). `claimed_count` and `my_unpurchased_claim_count` live on
   `GiftListViewerRead`, and `app/lists/service.py:to_summary` is the single place that decides
   which schema a list row gets — route new list-row responses through it rather than naming a
   schema at the endpoint. Every surface that could leak claim state to an owner — including the
   409 on revoking an occasion share — reveals only *that* claims exist, never counts, gift names,
   or claimer names.
   `tests/integration/test_owner_blindness.py` sweeps the owner-facing responses for it.

2. **Visibility has exactly one predicate.** `can_view_list` in `app/access.py`: owner, OR a
   `ListShare` row, OR the list is shared to an occasion of a family the viewer belongs to. Claims
   and folder membership both route through it. A connection alone grants nothing; bare family
   co-membership grants nothing. It does **not** consult `occasions.is_archived` — archiving blocks
   new shares and nothing else, so it never withdraws visibility.

3. **An occasion share row implies the owner is still a member of the occasion's family.** Read
   queries rely on this and do not re-check it, so every membership departure deletes the affected
   share rows — on every occasion of that family, not just one.

4. **`users_share_access` is not `can_view_list`.** It answers "is there a standing relationship"
   — used to decide cascade cleanup when a relationship ends — and is deliberately not gated on
   shares.

5. **A shared account is one identity.** Its people are labels on its lists. They are not members,
   not connections, not claimers, and they never receive their own visibility. It follows that
   claims stay hidden on every list a shared account owns, including a list marked for the other
   person — accepted deliberately, see [ADR 0001](docs/adr/0001-shared-accounts-are-one-identity.md).

6. **An account marked shared always has at least two people.** Marking it with fewer is refused,
   and deleting down to one un-marks the account rather than leaving it in a one-person state.

7. **A list is for an account person, or for a recipient, or for neither — never both.**
   `lists.account_person_id` and `lists.recipient_name` are mutually exclusive, enforced in the
   service layer. "Neither" is a legitimate state on a shared account: it is a household list,
   belonging to everyone who uses the login.

8. **A recipient has no account.** `recipient_name is not None` means the list is kept on behalf of
   someone who will never log in, so its keeper cannot see claims on it and cannot claim from it.

9. **An occasion belongs to exactly one family, and has no dates.** Any member may read and create
   one; only an organizer may rename or archive one. Creating a second *active* occasion is allowed
   and flagged (`has_other_active`), never refused — a family with no active occasion cannot be
   shared to at all, so nobody may be blocked waiting on an absent organizer.
   Deleting the family deletes its occasions, and the shares pointing at them first.
   **A list is shared to an occasion, never to a family**, and archiving one refuses new shares
   (409) without withdrawing the shares already made.
   See [ADR 0002](docs/adr/0002-family-shares-target-an-occasion.md).

10. **A budget is private, and belongs to exactly one scope.** One per `(user, occasion)` and one
    per `(user, folder)`, always the caller's own: no endpoint anywhere returns another user's
    budget, spend or counts, and no spend is aggregated across accounts at any time — that is
    invariant 1's reasoning applied to money. `budgets.occasion_id` and `budgets.folder_id` are
    mutually exclusive with exactly one set, enforced in `app/budgets/service.py`.
    **The money total always discloses its own incompleteness**: a purchase whose `amount_paid` is
    null counts toward `bought_count` and `unpriced_count` and never toward `spent`, and is never
    guessed at from the owner's asking price. A budget dies with its scope — deleting a folder, a
    family (through its occasions) or a user clears the budgets pointing at it.
