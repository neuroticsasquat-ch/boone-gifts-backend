# Navigation and shared accounts — project spec

**Linear project:** [Navigation and shared accounts](https://linear.app/neuroticsasquatch/project/navigation-and-shared-accounts-1cbf5b5d867b)
**Initiative:** Boone Gifts · **Team:** NEU · **Label:** `b.g v0.4.x`
**Repos:** `boone-gifts-backend`, `boone-gifts-frontend` (this file is mirrored in both)
**Status:** shaped 2026-09-07, tickets not yet planned individually

This is the project-wide spec. `/implementit` falls back to it when a ticket has no per-ticket plan,
so it is written to be sufficient on its own: every decision below is settled, and anything still
open is listed under **Open questions** with instructions to resolve it in that ticket's `/planit`.

---

## 1. Problem

The navigation splits things that are the same thing and duplicates things that are different.

Observed on 2026-09-07 against a seeded local stack, mobile viewport, both modes:

- **Family-shared lists are unreachable from anywhere a user would look.** They appear only on
  `/family-lists`, which in full mode has no nav item — it is a "View Family Lists →" text link on
  the Families page. Landing there highlights no bottom tab.
- **`/` and `/lists` are near-duplicates.** Dashboard adds only the pending-requests block; Lists
  adds a sort control and an archive toggle. Neither shows family lists.
- **Simple mode's "My Lists" tab is not my lists** — it is my lists *plus* "Shared with Me", while
  family-shared lists are a separate tab.
- **Simple mode's Dashboard is orphaned**, reachable only via the logo, yet it is the only place a
  connection request can be accepted — and Connections is otherwise hidden in that mode.
- **Simple mode shows a Collections tab on a list** despite having no Collections nav entry.
- **Five mobile tabs, two of them "Connect" and "Collect".**
- **Own-list detail is four tabs** — Gifts | Collections | Shared with | Families — on a 390px
  viewport, with sharing split across two of them.
- **The create form can share to families but not to people**, and its "for someone else → they use
  this app" radio actually means *this same login*.

## 2. Goal

A user — including an older one sharing a login with a spouse — can find any list they can see in
one place, can tell at a glance whose it is and how it reached them, and never has to understand the
words "connection", "collection", or "family list" to use the app.

## 3. Non-goals

- A profile switcher, or per-person claim visibility inside a shared account (explicitly rejected, §7.3)
- Splitting a shared household into two real accounts
- A general notifications inbox
- Redesigning the claim/unclaim interaction itself
- Email-to-list (its own project)
- Roles or granular permissions
- Changing simple mode's *sharing* semantics (§6.2)

---

## 4. Information architecture

### 4.1 Primary navigation

Two tabs plus the existing account menu, at every screen size, in both modes.

```
┌──────────────────────────────┐
│ 🎁 Boone Gifts            👤 │
└──────────────────────────────┘
┌──────────────────────────────┐
│   📋¹ Lists     👥² People   │
└──────────────────────────────┘
```

- **Lists** — everything list-shaped. Badge: unseen shares (existing `/lists/unseen-count`).
- **People** — connections and families together. Badge: pending connection requests + incoming
  family invites.
- **Account menu** — account settings, admin links, logout. Unchanged, except that People collapses
  into it in simple mode.

Retired routes, with **no redirects** (§9): `/` (Dashboard), `/families`, `/family-lists`,
`/collections`. `/families/:id` survives as a People sub-page (§4.3).

### 4.2 Lists page (`/lists`)

One page, two sections, plus a banner region.

```
┌─────────────────────────────┐
│ Dave Boone wants to connect │
│        [Accept]  [Decline]  │
└─────────────────────────────┘

LISTS                  [⊕ New]
Occasion: [ All lists      ▾ ]

MY LISTS                [sort ▾]
  Tom's Wishlist
  Christmas 2026
  Beth's List        for Beth

SHARED WITH ME          [sort ▾]
  Jane's Wishlist    from Jane
  Carol's Wishlist   Boone Family
  Gran's List        Boone Family
  Dave's Wishlist    Extended Family
```

- **Actionable banner** — anything awaiting a decision (connection requests, family invites) renders
  above the lists, with accept/decline inline. This is what unstrands them in simple mode, where
  People is hidden. Full history stays on People.
- **Shared with me is flat**, sorted, with the source as a label on the row — never as a separate
  destination. `from <name>` for a direct share, `<family name>` for a family share. A list that
  reaches the viewer both ways is shown once, labelled as the direct share.
- **Occasion filter** — a select in the page header, default "All lists". Selecting one filters both
  sections. A list belonging to several occasions appears under each of them.
- **Sort and archive** controls behave as they do today. Hidden in simple mode (§6.1).

### 4.3 People page (`/people`)

Connections and families on one page, families first (they are the coarser grouping).

```
PEOPLE                 [⊕ Add]

FAMILIES
  Boone Family        3 members  ›
  Extended Family     3 members  ›

INDIVIDUALS
  Jane Boone
  Carol Boone
  Gran Boone
```

- Family rows link to the existing family detail page, re-rooted at `/people/families/:id`.
- Individual rows link to the existing connection profile, re-rooted at `/people/:id`.
- Pending requests and invites appear here in full, in addition to the Lists banner.
- "Add" covers both: send a connection request, or create a family.

### 4.4 List detail (`/lists/:id`)

**No tab bar.** The gifts are the page.

```
← Back to lists
┌─────────────────────────────┐
│ Tom's Wishlist              │
│ Ideas for me                │
│                             │
│ 👥 Shared with Jane,        │
│    Boone Family    [Change] │
│                             │
│ [Edit]  [⋯]                 │
└─────────────────────────────┘

[ + ADD A GIFT ]
  • Cast iron skillet
  • Running shoes
```

- **Sharing summary line** — one line naming who can see the list, people and families together,
  with a **Change** control opening a single "Who can see this list" panel where people and families
  are one combined picker. Owner-only.
- **Occasion membership** moves into the header `⋯` menu ("Add to an occasion…"), owner or viewer —
  anyone who can see a list can file it under one of their own occasions.
- **Simple mode** shows the same summary line, read-only, reading "Shared with your families"
  (§6.2), with no Change control.
- **Viewer (non-owner) view** — same shape minus the owner controls: header, then gifts with claim
  actions, plus "Add to an occasion…".

---

## 5. Shared accounts

### 5.1 Model

An account may be marked **shared**. When it is, it names its **people** — required, at least two.
Account people are **labels, not identities**: the account remains a single identity everywhere —
one family member, one connection, one claimer. Other users see "Gran & Grandpa" as one member with
lists filed under it.

### 5.2 Assignment

On a shared account, creating a list **requires** picking who it is for: one of the account's people,
or "Someone else" (§5.4). The two are mutually exclusive — choosing "Someone else" clears any
account-person assignment and vice versa.

A non-shared account sees **no picker at all**: name, description, family checkboxes (full mode),
and the "This list is for someone else" checkbox. Identical to today minus the deleted radio.

### 5.3 Claim privacy — accepted cost

Claims stay hidden on **every list the account owns**, including a list marked for the other person.
Grandpa cannot see what has already been bought for Gran, and cannot claim it, from inside the app.

This follows from §5.1: the owner-never-sees-claims rule is absolute, and the shared account is the
owner. There is no honesty-based profile switcher. This was decided with eyes open; do not
"fix" it in a ticket.

### 5.4 Recipients after this project

`recipient_name` + `recipient_has_account` currently encode two different things. After this project:

- **`recipient_has_account` is deleted.** Its `true` case meant "a co-resident who reads this list on
  this same login" — which is exactly what account people now model.
- **"This list is for someone else" narrows to one meaning**: a person who does not use the app.
  Claims stay hidden from the keeper and the keeper cannot claim on it — today's
  `kept_for_absent_person` behaviour, which becomes the only behaviour.

### 5.5 Turning sharing off

Un-marking an account as shared warns with a count — "3 lists are marked for Gran or Grandpa;
turning this off removes those labels" — and on confirm nulls `account_person_id` on those lists and
deletes the people rows. The lists themselves survive, unlabelled. No claim or visibility semantics
change.

---

## 6. Simple mode

### 6.1 Purely subtractive in the UI

Simple mode never changes labels, wording, or destinations. It only hides:

| Surface | Full mode | Simple mode |
|---|---|---|
| Nav | Lists · People | Lists (People collapses into the account menu) |
| Lists page | Sort, archive toggle, occasion filter | None of them |
| Lists page banner | Requests + invites | Same — this is the only route to them |
| List detail | Sharing summary + Change | Sharing summary, read-only |
| Create form | Name, description, family checkboxes, recipient | Name, description, recipient |

### 6.2 Unchanged on the backend — deliberate exception

Simple mode remains a real server-side behaviour and this project does not touch it:

- A simple-mode user's new list is auto-granted to every family they belong to
- Joining a family auto-grants their existing non-archived lists
- `PUT`/`DELETE /lists/{id}/families/{family_id}` return 403 in simple mode
- `POST /lists` ignores `family_ids` in simple mode

The auto-grant is precisely what makes hiding the sharing control safe. The read-only summary line
therefore reads "Shared with your families".

---

## 7. API changes (backend)

### 7.1 Combined shared scope

`GET /lists?filter=shared` returns **every list shared with the caller by any path** — a `ListShare`
row or a family grant — with each row carrying its source:

```json
{ "id": 5, "name": "Jane's Wishlist",
  "shared_via": { "kind": "user",   "name": "Jane Boone",   "id": 2 } }
{ "id": 6, "name": "Carol's Wishlist",
  "shared_via": { "kind": "family", "name": "Boone Family", "id": 1 } }
```

- A list reachable both ways reports `kind: "user"` (the direct share is the more specific fact).
- `?filter=family` is **removed** along with `/family-lists`.
- `?filter=owned` and the `archived` param are unchanged.
- Sorting stays a client concern for now; the endpoint returns a stable order (most recently updated
  first) so the client does not have to merge two orders.

### 7.2 Occasions rename

| Before | After |
|---|---|
| `collections` table | `occasions` |
| `collection_items` table | `occasion_items` |
| `/collections/*` | `/occasions/*` |
| `/collections/{id}/shopping-list` | `/occasions/{id}/shopping-list` (meaning unchanged: gifts *I* have claimed within it) |
| `/collections/for-list/{list_id}` | `/occasions/for-list/{list_id}` |
| `Collection*` schemas, `app/collections/` | `Occasion*`, `app/occasions/` |

No compatibility shims — testers only (§9).

### 7.3 Shared accounts

- `PUT /auth/profile` (or a dedicated account endpoint — settle in `/planit`) accepts
  `is_shared_account` and the people list. Marking shared **requires** at least two people; the API
  rejects a shared account with fewer.
- Un-marking returns the affected-list count so the client can confirm before committing, then
  clears assignments on the second call.
- `POST /lists` and `PUT /lists/{id}` accept `account_person_id`. Validation: the person must belong
  to the calling account; `account_person_id` and `recipient_name` are mutually exclusive; a shared
  account **must** supply one of the two.
- List responses carry the assigned person's name so rows can render "for Gran".

### 7.4 Recipients

`recipient_has_account` is dropped from the API and the schemas. `recipient_name` alone now means
"kept for a person with no account", and `kept_for_absent_person` becomes
`recipient_name is not None`.

---

## 8. Data model (backend)

```
users
  is_shared_account   bool, default false, not null

account_people                      -- new
  id
  user_id     → users.id, indexed
  name        str(255)
  position    int          -- display order
  unique (user_id, name)

lists
  account_person_id  → account_people.id, nullable, indexed
  recipient_name     unchanged
  recipient_has_account  -- DROPPED

occasions        -- renamed from collections
occasion_items   -- renamed from collection_items
```

**Constraint:** `account_person_id` and `recipient_name` are mutually exclusive. Enforce in the
service layer (SQLite check constraints under `render_as_batch` are more trouble than they are worth
here); cover with tests both ways.

**Migrations** (SQLite, `render_as_batch=True`, chain from `d8a3f1c05b64`):

1. Rename `collections` → `occasions`, `collection_items` → `occasion_items`
2. Add `users.is_shared_account`, create `account_people`, add `lists.account_person_id`
3. Drop `lists.recipient_has_account`

No backfill of `recipient_has_account = true` rows into account people — the beta data is test data
and may be reset (§9). Existing `recipient_has_account = false` rows keep working unchanged, since
`recipient_name is not None` is the new predicate for exactly that case.

---

## 9. Rollout

Every current user is a tester. **No redirects from retired routes, no compatibility shims, no
careful backfill.** Migrations may be destructive and the data can be reset. The two repos ship
independently; sequence backend before the frontend ticket that consumes it (§11 dependencies).

### 9.1 Branching

**Every ticket in this project branches from `release/v0.4.0`, and its PR targets
`release/v0.4.0` — not `main`.** This holds in both repos, which each carry a branch of that name.

The project retires routes, drops a column, and renames a table; none of it is individually
shippable, and `main` stays deployable while it lands. `release/v0.4.0` accumulates the whole
project and merges to `main` once when v0.4.0 ships.

Practically, for each ticket:

```bash
git fetch origin
git checkout -b <work-branch> origin/release/v0.4.0
gh pr create --base release/v0.4.0
```

Keep the work branch current by merging `release/v0.4.0` into it, not `main`. A ticket whose
blocker merged into `release/v0.4.0` sees that work only after such a merge — which matters most
for the frontend tickets that consume a backend change from the same milestone.

---

## 10. Vocabulary

| Term | Means |
|---|---|
| **List** | A gift list owned by one account |
| **Share** | A grant of visibility, either to a person (`ListShare`) or to a family (`ListFamilyShare`) |
| **`shared_via`** | How a shared list reached the viewer: a user or a family |
| **Family** | A named group whose members can be granted lists |
| **Occasion** | A user's saved grouping of lists — was "collection" |
| **Account person** | A named person on a shared account. A label, never an identity |
| **Recipient** | A person with no account for whom a list is kept. Claims hidden from the keeper |
| **Connection** | An accepted relationship between two accounts; a prerequisite for a direct share |

Words this project **removes** from the UI: "collection", "family list", "connect"/"collect" as tab
labels, "they use this app".

---

## 11. Testing expectations

- **Backend**: unit tests for the combined `shared` scope including the both-paths dedupe; service
  tests for the account_person/recipient exclusivity in both directions; a migration test for the
  occasions rename that asserts existing rows survive; tests that simple-mode auto-grant behaviour is
  unchanged (regression guard for §6.2).
- **Frontend**: Lists page renders both sections with correct source labels; the actionable banner
  appears in simple mode; list detail renders the sharing summary and opens the combined picker;
  create form shows the account-people picker only on a shared account and enforces exclusivity;
  simple mode hides exactly the surfaces in §6.1 and nothing else.
- `scripts/seed_dev.py` (backend) builds every state these tests describe by hand; keep it working as
  the model changes.

## 12. Open questions

Resolve these in the owning ticket's `/planit`, not by guessing:

1. Whether the shared-account settings live on `PUT /auth/profile` or a dedicated `/account`
   endpoint (§7.3).
2. Exact copy for the sharing summary line when a list is shared with many people/families
   (truncation rule, e.g. "Jane, Boone Family and 2 others").
3. Whether "Add to an occasion…" belongs in the header `⋯` menu or as a footer action on the list
   page — settle when building §4.4.
4. Empty states for the merged Lists page in both modes.
5. Whether People needs its own empty state or reuses the current Connections one.
