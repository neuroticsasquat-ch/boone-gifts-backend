# Shopping lists — project spec

**Linear project:** [BG: Shopping Lists](https://linear.app/neuroticsasquatch/project/bg-shopping-lists-6fdd1e4a3cc1)
**Initiative:** Boone Gifts · **Team:** NEU · **Label:** `b.g v0.5.x`
**Repos:** `boone-gifts-backend`, `boone-gifts-frontend` (this file is mirrored in both)
**Status:** shaped 2026-09-08, tickets not yet planned individually

This is the project-wide spec. `/implementit` falls back to it when a ticket has no per-ticket plan,
so it is written to be sufficient on its own: every decision below is settled, and anything still
open is listed under **Open questions** with instructions to resolve it in that ticket's `/planit`.

Four ADRs carry the reasoning behind the load-bearing decisions and should be read first:

- **backend** `docs/adr/0002-family-shares-target-an-occasion.md`
- **backend** `docs/adr/0003-claims-are-their-own-table.md`
- **backend** `docs/adr/0004-simple-mode-is-retired.md`
- **frontend** `docs/adr/0002-occasion-and-folder.md`

---

## 1. Problem

The app records that a gift is claimed. It does nothing with that fact afterwards.

- **There is no shopping surface.** `GET /occasions/{id}/shopping-list` exists and works, and its
  only consumer is a pill-toggle inside `OccasionDetail.tsx` — a page with no route since the nav
  project retired `/occasions` (`routes.test.tsx:48`). A user can file a list under an occasion and
  then never see that occasion again.
- **There is no record of what anything cost.** `gifts.price` is the *owner's* asking price, written
  by `GiftCreate` and shown to owner and viewers alike. What the claimer actually paid is nowhere.
- **Nothing bounds a period.** A `list_family_shares` row is permanent and unqualified. Claims
  accumulate against a list across years with nothing to partition them, so "what am I spending on
  the Boone family this Christmas" has no answer the app can compute.
- **Claim privacy is discipline, not structure.** `GiftOwnerRead` omits the claim fields by hand. It
  has already slipped: `GiftListRead.claimed_count` is computed for owned lists too and returned by
  `GET /lists` (`app/schemas/gift_list.py:116`). Nothing renders it, so nobody noticed.
- **Simple mode hides the organising tools from the users who need them most**, and its one real
  behaviour — the auto-grant — is what made hiding them safe.

## 2. Goal

A user can open the occasion they are shopping for, see everything they have claimed for it, tick
things off as they buy them, record what they paid, and watch it against a budget only they can see.
Getting there requires no mode, no curation, and no understanding of how sharing is recorded.

## 3. Non-goals

- Any aggregate spend visible across accounts. Every figure on every budget screen is the viewer's
  own money about their own claims (§7).
- Splitting the cost of one gift between claimers. `claims.gift_id` is unique; today's one-claimer
  behaviour is preserved exactly.
- A global cross-occasion shopping view (§9.4 — deliberately rejected, with the gap it leaves).
- Multi-currency. One implicit currency, as today (§14 open question 1).
- Reminders, notifications, or anything time-triggered. Occasions carry no dates at all.
- Reworking the claim/unclaim interaction itself, beyond adding the amount prompt.
- Re-litigating shared accounts (backend ADR 0001, shared accounts are one identity)
  or the two-tab navigation (frontend ADR 0001, one place for every list shared with me).

---

## 4. Vocabulary

The single most important section for anyone implementing a ticket here. Two concepts share the word
"occasion" today and are being split; see frontend ADR 0002 (`docs/adr/0002-occasion-and-folder.md` in the frontend repo).

| Term | Means | Where it lives |
|---|---|---|
| **Occasion** | A family's shared gifting occasion — "Boone Family · Christmas 2026". The unit a list is shared *to*, and the unit a budget hangs off. Owned by a family. **New.** | `occasions` (new table) |
| **Folder** | A user's private curated set of lists. Many-to-many. Available to every user. **Renamed from today's occasion.** | `folders`, `folder_items` |
| **Claim** | One account's private intent to buy a gift, now with the purchase and the amount paid on it. Invisible to the list's owner. **Promoted to its own table.** | `claims` |
| **Amount paid** | What the *claimer* spent. Distinct from `gifts.price`, which is the *owner's* asking price and is public to viewers | `claims.amount_paid` |
| **Budget** | A private target amount one user sets against one occasion or one folder | `budgets` |
| **Active occasion** | An occasion with `is_archived = false`. The only kind a list can be newly shared to | `occasions.is_archived` |

Unchanged and still authoritative: Account, List, Gift, Connection, Direct share, Family, Recipient,
Shared account, Account person — see each repo's `CONTEXT.md`.

Words this project **removes**: "simple mode" (retired entirely, §8), "family grant" / "family share"
as a thing pointing at a family (a share points at an occasion, §5). "Collection" stays retired and
is **not** revived — it reads too close to "connection".

### 4.1 A claim is one fact; its occasion is another

This distinction makes the whole model coherent and must not be blurred.

A **claim** is a global fact about a gift: it is taken, and nobody else should buy it. It has no
occasion in that sense. If Jane's list is shared to both Boone · Christmas and Extended · Christmas,
a gift claimed there is claimed for everyone who can see it, once.

`claims.occasion_id` is a different thing entirely: **the claimer's private filing of their own
spend**, so it lands in exactly one budget. A second gift off that same list may be filed under the
other occasion. Nothing about the filing is visible to anyone but the claimer.

---

## 5. Sharing goes through an occasion

The central change. Full reasoning in backend ADR 0002 (`docs/adr/0002-family-shares-target-an-occasion.md` in the backend repo).

### 5.1 The rule

A list is shared **to an occasion**, never to a family. `list_family_shares` is replaced by
`list_occasion_shares` pointing at `occasions.id`; the family is derived through
`occasions.family_id` and is not stored twice.

**A family with no active occasion cannot be shared to.** It is still listed in the sharing UI,
disabled, with the reason stated.

### 5.2 The sharing control

```
WHO CAN SEE THIS LIST

  PEOPLE
    ☑ Jane Boone
    ☐ Carol Boone

  FAMILIES
    ☑ Boone Family        Christmas 2026
    ☑ Extended Family     [ Christmas 2026  ▾ ]
    ☐ Work Friends        No active occasion — a member
                          needs to create one
```

- **Exactly one active occasion** — the common case. Checking the family selects it; the occasion
  name is displayed for transparency but is not a control.
- **More than one active occasion** — the checkbox is accompanied by a select. Checking the family
  without choosing is refused client-side and server-side.
- **No active occasion** — row disabled, reason given, checkbox not operable.
- **Pre-checked by default**: on the create-list form, every family the user belongs to that has
  exactly one active occasion arrives checked. This replaces simple mode's auto-grant (§8).

### 5.3 Occasion lifecycle

An occasion is `family_id`, `name`, `is_archived`. **No dates** — naming it "Christmas 2026" bounds
its period well enough, and dates only ever existed to support an attribution rule that no longer
exists.

| Action | Who | Notes |
|---|---|---|
| Create | **Any member** | Warn, do not block, when the family already has an active occasion |
| Rename | **Organizer** | Changes a label everyone sees and everyone's budgets are filed under |
| Archive / unarchive | **Organizer** | Consistent with every other family-wide action in `families/service.py` |

Any member may create so that nobody is blocked waiting on an absent organizer — which matters,
because a family with no active occasion cannot be shared to at all.

### 5.4 Archiving blocks new shares, and nothing else

| After archiving an occasion | |
|---|---|
| New shares to it | **Refused** (409) |
| New claims through it | **Allowed** — late shoppers are real |
| Existing claims: purchase toggle, `amount_paid`, re-filing | **Allowed** |
| Its lists | Still viewable, via the archive view (§9.5) |
| `can_view_list` | **Unaffected** — archiving is not unsharing |
| Budget and spend for it | Still readable, forever |

Archiving an occasion never archives a list. A list shared to two occasions is untouched by one of
them being archived.

---

## 6. Claims and money

Full reasoning in backend ADR 0003 (`docs/adr/0003-claims-are-their-own-table.md` in the backend repo).

### 6.1 The claim moves off the gift

`gifts.claimed_by_id`, `gifts.claimed_at` and `gifts.purchased_at` are **dropped**. Nothing
claim-shaped remains on the row an owner reads, so owner-blindness becomes a property of the schema
rather than a rule someone has to remember.

`GiftListRead.claimed_count` is fixed while we are here: computed from `claims`, and present only on
viewer-facing rows. It is currently returned for lists the caller owns.

### 6.2 Filing a claim under an occasion

Resolved when the claim is made, from **two** derived sets — not one. Conflating them produces
either permanent nagging or unfixable misfilings. Full reasoning in
`docs/specs/NEU-1269-claim-filing-and-candidates.md` §2 (backend repo).

- **`allowed`** — the occasions the list is shared to, intersected with the families the claimer
  belongs to, **archived included**. Validates an explicitly supplied `occasion_id`.
- **`suggested`** — the active members of `allowed`; or, when none are active, all of `allowed`.
  Decides auto-pick versus prompt, and is what the client renders.

| `suggested` | Behaviour |
|---|---|
| 0 (a direct share) | `occasion_id = null`. Budgets reach it only through a folder |
| 1 | Set silently. No prompt |
| 2+ | Prompt once, store the answer |

`suggested` narrows to active because occasions never disappear: by year three a standing wishlist is
shared to three Christmases, and a uniform set would prompt on every claim forever with the answer
obvious each time. `allowed` stays wide so a late claim filed under the wrong occasion can still be
corrected — archive Christmas 2026 while "Gran's 80th" is active and a January Christmas purchase
lands under Gran's 80th, which must remain fixable.

Always editable afterwards from the occasion's shopping tab. Deliberately **stored, not derived**: a
budget whose history rewrites itself when someone revokes a share, archives an occasion, or leaves a
family is worse than no budget.

### 6.3 Recording what it cost

Ticking purchased reveals an inline amount field. **Empty**, with the owner's asking price shown
beside it as a hint, never as a value — a budget pre-filled from someone else's wishlist price looks
precise and is a guess.

```
☑ Cast iron skillet
   What did you pay?
   [        ]   listed at $39
   [ Save ]  [ Skip ]
```

Skipping is one click and leaves `amount_paid` null. Unclaiming deletes the claim row, which clears
the purchase and the amount with it — no explicit reset, unlike `app/gifts/service.py:68` today.

---

## 7. Budgets

**Every budget is private to the claiming user.** One per `(user, occasion)`, one per
`(user, folder)`. Organizers set an occasion's name; they never touch money and never see any.

No spend is aggregated across accounts anywhere, at any time. This is not a scope decision, it is
`CONTEXT.md` invariant 1: if Gran can watch the Boone Christmas total move, she learns something was
claimed, and in a small family she can often work out what.

A budget line always discloses its own incompleteness:

```
Boone Family · Christmas 2026
$142 of $200 spent · $58 left
3 of 7 bought · 2 purchases with no amount recorded
```

An understated total must read as an understatement, never as fact. Purchases with `amount_paid`
null are counted in the "bought" tally and excluded from the money tally, and the count of them is
always shown when it is non-zero.

---

## 8. Simple mode is retired

Full reasoning in backend ADR 0004 (`docs/adr/0004-simple-mode-is-retired.md` in the backend repo). This **supersedes
`CONTEXT.md` invariant 9**, which must be deleted in the same ticket that removes the behaviour.

Deleted: `users.simple_mode`, `family_invites.simple_mode`, the JWT claim
(`app/dependencies.py:42`), the auto-grant on create and on join, the 403s in
`app/list_families/service.py:12`, and the account-page toggle. Frontend gates in `Layout.tsx:68,120`,
`Lists.tsx:46`, `ListDetail.tsx:74`, `SharingSummary.tsx:24`, `CreateList.tsx:30`, plus the
`simple_mode` flag on outgoing family invites in `FamilyDetail.tsx:50,87,304`.

Replaced by a default, not a mode:

1. Family share checkboxes **pre-checked** for every family with exactly one active occasion (§5.2).
2. A list shared with nobody says so on the list itself: *"This list isn't shared with anyone."*
   This is the entire mitigation for the auto-grant's disappearance and is **not** optional.

The sharing summary line stops being read-only for anyone and stops saying "Shared with your
families"; it names the occasions and people the list actually reaches.

---

## 9. Information architecture

Navigation stays **two tabs — Lists · People**. No tab is added; see §9.4.

### 9.1 Lists dashboard (`/lists`)

The shipped two-section shape is kept. Added: a **Group by** control that subdivides *Shared with
me*, an archive entry point, and an unpurchased-claims badge.

```
LISTS                              [⊕ New]
Group by: [ None ▾ ]        (None · Occasion · Person · Folder)

MY LISTS                           [sort ▾]
  Tom's Wishlist
  Beth's List                     for Beth

SHARED WITH ME                     [sort ▾]
  Jane's Wishlist    from Jane      • 2 to buy
  Carol's Wishlist   Boone Family

                            [ View archive ]
```

With **Group by: Occasion**, *Shared with me* becomes:

```
  Boone Family · Christmas 2026
    Carol's Wishlist
    Gran's List
  Extended Family · Christmas 2026
    Dave's Wishlist
  Not in an occasion
    Jane's Wishlist
```

- Every grouping needs its **"Not in a …"** bucket, or directly-shared lists silently vanish.
- The **`• N to buy` badge** counts the viewer's own unpurchased claims on that list. It is the only
  route to a claim on a directly-shared list (§9.4) and is therefore required, not decorative.
- All controls visible to every user. Nothing here is gated.

### 9.2 Occasion page (`/occasions/:id`)

Reintroduces the route the nav project retired, now meaning the family concept. Two tabs:

```
← Boone Family
Christmas 2026                                    [⋯]

  LISTS          MY SHOPPING

$142 of $200 spent · $58 left            [ Edit budget ]
3 of 7 bought · 2 purchases with no amount recorded

  Jane's Wishlist
    ☑ Running shoes        $85
    ☐ Cast iron skillet    listed at $39
  Gran's List
    ☑ Puzzle               $18
```

- **Lists** — every list shared to this occasion that the viewer can see.
- **My shopping** — the viewer's own claims within it, budget line, purchase toggles, amount fields.
  Never anyone else's claims, in any aggregate, ever.
- `[⋯]` carries rename and archive, **organizer only**.

### 9.3 Folder page (`/folders/:id`)

The same two-tab shape — **Lists** and **My shopping** with its own budget — for a user's curated
set. Reached from the Lists dashboard when grouping by folder, and from "Add to a folder…" on list
detail. Available to every user; the simple-mode gate at `ListDetail.tsx:74` is deleted.

### 9.4 No global shopping view — and the gap it leaves

Shopping lives per-occasion and per-folder only. There is no cross-cutting "everything I have to
buy" screen and no third nav tab.

**This leaves a real gap and the mitigation is mandatory.** A claim on a directly-shared list belongs
to no occasion and, unless the user files that list in a folder, to no folder either — so it appears
on no shopping tab at all. The `• N to buy` badge on the Lists row (§9.1) is its only route. Build
the badge, or those claims are unreachable.

### 9.5 Archive views

Archived lists, folders and occasions stay reachable behind an explicit archive entry point from the
relevant dashboard — never mixed into the default view. Reached from Lists (archived lists and
folders) and from a family's page (archived occasions).

### 9.6 Family page

`/people/families/:id` gains a section listing the family's **active occasions**, each linking to its
occasion page, with a create action for any member and an archive link for organizers.

---

## 10. API changes (backend)

### 10.1 Occasions

| Method | Path | Who |
|---|---|---|
| `GET` | `/families/{family_id}/occasions?archived=false` | Any member |
| `POST` | `/families/{family_id}/occasions` | Any member |
| `GET` | `/occasions/{id}` | Any member of the owning family |
| `PUT` | `/occasions/{id}` (name, `is_archived`) | **Organizer** — 403 otherwise |
| `GET` | `/occasions/{id}/lists` | Member; only lists the caller can view |
| `GET` | `/occasions/{id}/shopping` | Member; **the caller's own claims only** |

`POST` returns `201` and does **not** refuse a second active occasion — the warning is a client
concern (§5.3). The response includes `has_other_active` so the client can warn accurately.

### 10.2 Folders — renamed wholesale

`/occasions/*` → `/folders/*`, `Occasion*` schemas → `Folder*`, `app/occasions/` → `app/folders/`.
`/occasions/for-list/{id}` → `/folders/for-list/{id}`. The old shopping-list endpoint becomes
`GET /folders/{id}/shopping` and gains the budget rollup. **No compatibility shims** (§12).

### 10.3 Sharing

`PUT`/`DELETE /lists/{list_id}/families/{family_id}` are **removed**, replaced by:

| Method | Path | Notes |
|---|---|---|
| `PUT` | `/lists/{list_id}/occasions/{occasion_id}` | 409 if the occasion is archived; 403 if the caller is not the list owner or not a member of the occasion's family |
| `DELETE` | `/lists/{list_id}/occasions/{occasion_id}` | Existing claim-protection behaviour is preserved: reveal only *that* claims exist, never counts, gift names, or claimer names |

`GET /lists?filter=shared` keeps `shared_via`; its `kind: "family"` arm becomes `kind: "occasion"`,
carrying the occasion and the family:

```json
{ "id": 6, "name": "Carol's Wishlist",
  "shared_via": { "kind": "occasion", "id": 3, "name": "Christmas 2026",
                  "family": { "id": 1, "name": "Boone Family" } } }
```

A list reachable both directly and through an occasion still reports `kind: "user"`.

### 10.4 Claims

| Method | Path | Body |
|---|---|---|
| `POST` | `/lists/{list_id}/gifts/{gift_id}/claim` | `{ "occasion_id": int \| null }` — **400** if 2+ `suggested` and none given; an id outside `allowed` still returns **201** with the filing fallen back (§10.4.1) |
| `DELETE` | `/lists/{list_id}/gifts/{gift_id}/claim` | Deletes the row; clears purchase and amount with it |
| `POST` | `/lists/{list_id}/gifts/{gift_id}/purchase` | `{ "amount_paid": Decimal \| null }` |
| `DELETE` | `/lists/{list_id}/gifts/{gift_id}/purchase` | Clears `purchased_at`; leaves `amount_paid` for re-ticking |
| `PATCH` | `/claims/{id}` | `{ "occasion_id"?, "amount_paid"? }` — claimer only |

`GiftListDetailViewer` carries **`claim_candidates`** (= `suggested`) and **`claim_options`**
(= `allowed`), each entry `{ id, name, is_archived, family: { id, name } }`. This is how the client
knows whether to prompt, without a second request. **`GiftListDetailOwner` carries neither, ever** —
this is the field class that produced the `claimed_count` leak (§6.1).

#### 10.4.1 Why a stale `occasion_id` does not fail the claim

**Claiming is competitive** — it exists so two people don't buy the same present. A share revoked
between the client's read and the user's click is not the client's fault, and failing that claim
hands the gift to whoever clicks next, over a private bookkeeping detail nobody else can see. So
`POST` falls back and still creates the claim.

The **400** stays, because it is a different fault: the client had `claim_candidates` and should have
prompted. Without it, a frontend regression that silently stops prompting is indistinguishable from a
working one — every claim files under null, every budget quietly reads low, and no test fails.

`PATCH /claims/{id}` **does** return 403 for an occasion outside `allowed`: there the user is
explicitly choosing, and silently recording something else would be worse than refusing.

### 10.5 Budgets

`PUT`/`DELETE /occasions/{id}/budget` and `PUT`/`DELETE /folders/{id}/budget`, both operating on the
**caller's own** budget and returning the rollup. There is no endpoint, anywhere, that returns
another user's budget or spend.

### 10.6 Simple mode

`simple_mode` is removed from `PATCH /auth/profile`, from the JWT, from the invite payload, and from
every schema.

---

## 11. Data model and migrations (backend)

```
folders                     -- RENAMED from occasions
folder_items                -- RENAMED from occasion_items

occasions                   -- NEW, reusing the vacated name
  id
  family_id      → families.id, indexed
  name           str(255)
  is_archived    bool, default false, not null
  created_by_id  → users.id
  created_at, updated_at

list_occasion_shares        -- REPLACES list_family_shares
  id
  list_id        → lists.id, indexed
  occasion_id    → occasions.id, indexed
  unique (list_id, occasion_id)

claims                      -- NEW
  id
  gift_id        → gifts.id, unique         -- one claimer per gift, as today
  user_id        → users.id, indexed
  occasion_id    → occasions.id, nullable, indexed
  claimed_at
  purchased_at   nullable
  amount_paid    Numeric(10,2), nullable

budgets                     -- NEW
  id
  user_id        → users.id, indexed
  occasion_id    → occasions.id, nullable
  folder_id      → folders.id, nullable
  amount         Numeric(10,2), not null
  unique (user_id, occasion_id)
  unique (user_id, folder_id)

gifts        claimed_by_id, claimed_at, purchased_at   -- DROPPED
users        simple_mode                               -- DROPPED
family_invites  simple_mode                            -- DROPPED
```

**Constraint:** `budgets.occasion_id` and `budgets.folder_id` are mutually exclusive and exactly one
must be set. Enforce in the service layer — SQLite check constraints under `render_as_batch` are
more trouble than they are worth here — and cover both directions with tests.

**Migrations** (SQLite, `render_as_batch=True`, chained from the current head):

1. Rename `occasions` → `folders`, `occasion_items` → `folder_items`.
2. Create `occasions` (the new family concept) and `list_occasion_shares`; **drop
   `list_family_shares`** without backfill (§12).
3. Create `claims`; **backfill from `gifts`** — one row per gift with `claimed_by_id` not null,
   carrying `claimed_at` and `purchased_at`, `occasion_id` null, `amount_paid` null. Then drop the
   three gift columns.
4. Drop `users.simple_mode` and `family_invites.simple_mode`.
5. Create `budgets`.

Steps 1 and 2 **must be separate revisions**: the name `occasions` is vacated by one and reused by
the other.

Note the asymmetry in step 2 versus step 3, and do not "tidy" it: **grants are dropped, claims are
preserved.** A dropped grant is re-created by a user in seconds. A dropped claim silently invites two
people to buy the same present.

### 11.1 Access control

`can_view_list` (`app/access.py`) becomes: owner, **OR** a `ListShare` row, **OR** the list is shared
to an occasion of a family the viewer belongs to. It does **not** consult `is_archived` — archiving
is not unsharing (§5.4).

`CONTEXT.md` invariant 3 carries over unchanged in substance: a share row implies the list's owner is
still a member of the occasion's family, and read queries rely on it, so every membership departure
must delete the affected `list_occasion_shares` rows.

---

## 12. Rollout

Every current user is a tester. **No redirects from retired routes, no compatibility shims.**

**Existing family grants are dropped, not migrated.** Every list currently shared with a family goes
invisible on deploy, and every owner re-shares it — one checkbox each, against a family that has an
occasion. Claims survive (§11 step 3), so a re-shared list still shows what was already taken.

**This needs telling real people about before it deploys.** It is the one change in this project a
user experiences as something breaking rather than something appearing.

### 12.1 Branching

**Every ticket in this project branches from `release/v0.5.0`, and its PR targets `release/v0.5.0` —
not `main`.** This holds in both repos, which must each carry a branch of that name cut from `main`.

Nothing here is individually shippable: claims moving off the gift row, simple mode's removal, and
share-to-occasion each leave the app broken until the rest arrives, across both repos.
`release/v0.5.0` accumulates the project and merges to `main` once when v0.5.0 ships.

```bash
git fetch origin
git checkout -b <work-branch> origin/release/v0.5.0
gh pr create --base release/v0.5.0
```

Keep work branches current by merging `release/v0.5.0` in, never `main`. A ticket whose blocker
merged into `release/v0.5.0` sees that work only after such a merge — which matters most for the
frontend tickets consuming a backend change from the same milestone.

---

## 13. Testing expectations

**Backend**

- `can_view_list` through an occasion share, including that an **archived** occasion still grants
  visibility, and that leaving a family deletes the affected share rows.
- Sharing to an archived occasion is refused; sharing to an active one succeeds; a family with no
  active occasion has no shareable target.
- Organizer-only rename and archive; **any member** may create. Cover the 403s both ways.
- Claim filing: 0 candidates → null, 1 → set silently, 2+ → 400 without an explicit `occasion_id`,
  and 403 for an `occasion_id` outside the candidate set.
- Unclaim deletes the row and with it the purchase and amount.
- Budget rollup: sums only the caller's claims; excludes null `amount_paid` from the money total
  while counting them in the bought tally and reporting the unpriced count.
- **Owner-blindness regression guards** — assert no owner-facing response carries claim state, and
  specifically that `claimed_count` is absent from owned rows.
- Migration tests: the occasions→folders rename preserves rows; the claims backfill preserves every
  existing claim and its purchase state.

**Frontend**

- Sharing control in all three family states — one active occasion, several, none — including that
  boxes arrive pre-checked in the one-occasion case and that checking a multi-occasion family without
  choosing is refused.
- The "This list isn't shared with anyone" empty state.
- Group by on Lists renders every bucket including "Not in a …", and the `• N to buy` badge.
- Occasion and folder pages: both tabs, the budget line with its unpriced-purchase disclosure, the
  purchase amount prompt appearing empty with the asking price as a hint only.
- **No `simple_mode` reference survives anywhere** — a grep-level assertion is appropriate.

`scripts/seed_dev.py` (backend) must build every state these tests describe by hand — families with
zero, one and several active occasions; archived occasions with claims under them; claims with and
without amounts; budgets over, under and exactly at target. Keep it working as the model changes.

---

## 14. Open questions

Resolve these in the owning ticket's `/planit`, not by guessing:

1. ~~**Currency.**~~ **Resolved 2026-09-09** in NEU-1275, the ticket that introduced `budgets`:
   **no stored currency.** `budgets.amount` is a bare `Numeric(10, 2)`, exactly like
   `claims.amount_paid` and `gifts.price` beside it. A currency column that every site then
   hardcodes `$` for anyway buys nothing, and one stored per budget would let a budget and the
   spend counted against it disagree — the rollup subtracts them, so they cannot be allowed to be
   in different units. Making this app multi-currency is a project of its own, spanning all three
   money columns and every display site; it is not a column this ticket could have added honestly.
   The shared frontend formatting helper this question also asks for is unaffected and still owed
   by the frontend tickets.
2. ~~**Where claim candidates are exposed.**~~ **Resolved 2026-09-08** in NEU-1269's `/planit`:
   `claim_candidates` and `claim_options` ride on the viewer list-detail payload (§10.4), and the
   `allowed`/`suggested` split is settled in §6.2. See
   `docs/specs/NEU-1269-claim-filing-and-candidates.md` in the backend repo.
