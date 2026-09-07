# Domain model — Boone Gifts backend

The vocabulary this codebase uses, and the invariants that hold across it. Conventions,
commands, and architecture live in [`AGENTS.md`](AGENTS.md); this file is only about what
the words mean and what must stay true.

## Terms

| Term | Means | Where it lives |
|---|---|---|
| **Account** | One login. The unit of identity everywhere: one family member, one connection, one claimer | `users` |
| **List** | A gift list owned by exactly one account | `lists` |
| **Gift** | An item on a list, optionally claimed and optionally marked purchased | `gifts` |
| **Claim** | One account's private intent to buy a gift. Invisible to the list's owner | `gifts.claimed_by_id` |
| **Connection** | An accepted relationship between two accounts. A prerequisite for a direct share — **not** itself a grant of visibility | `connections` |
| **Direct share** | A grant of one list to one account | `list_shares` |
| **Family** | A named group of accounts, with organizers and members | `families`, `family_members` |
| **Family grant** | A grant of one list to one family. Not implied by co-membership | `list_family_shares` |
| **Occasion** | An account's private grouping of lists it can see — "Christmas 2026". Was called a *collection* | `occasions`, `occasion_items` |
| **Recipient** | A person with **no account** for whom an account keeps a list | `lists.recipient_name` |
| **Shared account** | An account used by more than one person, e.g. a couple sharing one login | `users.is_shared_account` |
| **Account person** | A named person on a shared account. **A label, never an identity** | `account_people` |

Deliberately *not* in the vocabulary: "collection" (renamed to occasion), "family list" (a list
reached through a family grant is just a shared list).

## Invariants

1. **The owner never sees claims on their own list.** `GiftOwnerRead` omits the claim fields;
   every surface that could leak claim state to an owner — including the 409 on revoking a family
   grant — reveals only *that* claims exist, never counts, gift names, or claimer names.

2. **Visibility has exactly one predicate.** `can_view_list` in `app/access.py`: owner, OR a
   `ListShare` row, OR the owner granted the list to a family the viewer belongs to. Claims and
   occasion membership both route through it. A connection alone grants nothing; bare family
   co-membership grants nothing.

3. **A family grant row implies the owner is still a member of that family.** Read queries rely on
   this and do not re-check it, so every membership departure deletes the affected grants.

4. **`users_share_access` is not `can_view_list`.** It answers "is there a standing relationship"
   — used to decide cascade cleanup when a relationship ends — and is deliberately not gated on
   grants.

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

9. **Simple mode is a sharing behaviour, not only a UI preference.** A simple-mode owner's lists are
   auto-granted to all their families on creation and on joining, and the per-family toggles are
   refused. Changing this changes who can see what.
