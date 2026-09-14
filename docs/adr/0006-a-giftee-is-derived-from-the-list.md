# ADR 0006 — A giftee is derived from the list, not stored as its own row

**Status:** Accepted (2026-09-14)
**Project:** [Boone Gifts: Maintenance](https://linear.app/neuroticsasquatch/project/boone-gifts-maintenance-5b0684796a2f)
**Ticket:** [NEU-1326](https://linear.app/neuroticsasquatch/issue/NEU-1326/allow-budgeting-per-recipient)

## Context

Per-giftee budgeting needs something stable to hang a budget off that is *not* a list. A person
routinely has more than one list in an occasion — a Christmas list and a stocking list — and the
ticket is explicit that the budget is per person, not per list.

But "the person a list is for" is not one thing in this schema. A list is for its owner (nothing
marked), or for an account person on a shared login (`lists.account_person_id`), or for someone
with no account at all (`lists.recipient_name`, free text). The first two have ids. The third is a
string a keeper typed, and NEU-1216 §4 deliberately chose free text over a `list_recipients` table
because the management surface a table needs is more than this app warrants.

So there are three candidates for what a giftee budget points at:

1. **A list.** Wrong unit; rejected by the ticket.
2. **A new `giftees` table** that every list carries a foreign key to. Correct in the abstract, and
   it is the `list_recipients` table NEU-1216 rejected, now with the owner and account-person cases
   folded in. It would need creation on list create/update, merging when two keepers' "Beth"s turn
   out to be one person, and a way to rename. None of that exists and none of it is asked for.
3. **A derived identity**: the triple `(owner_id, account_person_id, recipient_name)` read off the
   list at query time, with a budget row carrying the same triple.

## Decision

**A giftee is derived from the list's three columns and is never its own row.** Two lists agree on
a giftee when their triples agree. A giftee budget stores the triple and a canonical string key
built from it, and the key is the only thing the API addresses a giftee by.

The account-person and owner cases are keyed on ids, so they follow renames for free. The absent
case is keyed on the name the keeper typed, so it does not: renaming "Beth" to "Bethany" on the
list makes a new giftee, and any budget on the old one survives as an empty, labelled group its
user can see and remove. That is the accepted cost, and it is the same drift NEU-1216 §5 accepted
when it chose free text.

## Consequences

- No new write path on lists. Creating, editing and sharing a list know nothing about giftees.
- The shopping tab's giftee set is computed per request from three sources — visible lists in
  scope, the caller's own claims in scope, and the caller's own giftee budget rows — and the union
  is what guarantees nothing that counts toward a total can be invisible.
- A giftee budget can be orphaned by a rename. It is never silently dropped and never silently
  re-keyed; it is shown, and it counts, until its user removes it.
- If a `giftees` table is ever wanted, the triple is exactly what it would be keyed on, and the
  budget rows already carry it — the migration is a backfill, not a redesign.
