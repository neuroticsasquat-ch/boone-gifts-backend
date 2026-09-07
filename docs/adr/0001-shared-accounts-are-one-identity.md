# ADR 0001 — A shared account is one identity; its people are labels

**Status:** Accepted (2026-09-07)
**Project:** [Navigation and shared accounts](https://linear.app/neuroticsasquatch/project/navigation-and-shared-accounts-1cbf5b5d867b)

## Context

Some households — the older users this app was built for — share a single login. Today the only way
to express that is a per-list checkbox, "This list is for someone else", whose sub-option "they use
this app" actually means *this same login*. Neither member of a couple thinks of their own list as
being for "someone else", so neither ticks it, and the wording gives no clue that it is about the
account rather than about another user of the app.

Moving the concept up to the account raises the question of what those named people **are** to the
rest of the system. Two shapes were considered:

1. **Labels** — the account stays the single identity everywhere; names exist only to answer "who is
   this list for?" and to label the list afterwards.
2. **First-class people inside an account** — each person appears as their own member in families, in
   share attribution, and as claim attribution, while sharing one login.

## Decision

**Labels.** An account may be marked shared and must then name at least two people
(`account_people`). A list may point at one (`lists.account_person_id`). Nothing else in the system
learns about them: the account remains one family member, one connection, one claimer. Other users
see "Gran & Grandpa" as a single member with lists filed under it.

## Consequences

**Good**

- No change to the identity model. `can_view_list`, connections, family membership, claim
  attribution, and every cascade rule keep working untouched.
- Renaming a person is one `UPDATE`; the FK means no list rows are rewritten.
- The concept is invisible to accounts that are not shared, so most users never meet it.

**Bad, and accepted**

- **A shared account cannot coordinate with itself.** Because the owner never sees claims on their
  own list (`CONTEXT.md` invariant 1) and the shared account *is* the owner, Grandpa cannot see what
  has already been bought for Gran, and cannot claim it, from inside the app. They coordinate the
  way they do now — out of band.
- Other members see one composite member rather than two people, so a family list of six households
  may read as five members.

An honesty-based "who is using this?" profile switcher would fix the first point by revealing claims
on the *other* person's list. It was rejected: it is unenforceable — anyone can switch and peek at
their own surprises — and a gift app that leaks surprises has failed at its only job. Do not
reintroduce it without a mechanism that actually separates the two people, which in practice means
two accounts.

## Alternatives rejected

- **First-class people inside an account** — cleaner for everyone else, but it makes "a person" no
  longer 1:1 with "an account", which touches visibility, claims, membership, and every cascade.
  Disproportionate to the problem, which is a couple with one login.
- **Per-list opt-in to reveal claims to the rest of the account** — a setting nobody would understand
  at the moment they must set it, defaulting either to a leak or to the behaviour above.
