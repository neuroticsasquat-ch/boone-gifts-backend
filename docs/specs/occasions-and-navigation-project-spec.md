# Occasions and navigation — project spec

**Linear project:** not yet created — scaffold with `/projectit` before planning tickets
**Initiative:** Boone Gifts · **Team:** NEU · **Label:** `b.g v0.6.x`
**Repos:** `boone-gifts-backend`, `boone-gifts-frontend` (this file is mirrored in both)
**Status:** shaped 2026-09-09, tickets not yet planned individually

This is the project-wide spec. `/implementit` falls back to it when a ticket has no per-ticket plan,
so it is written to be sufficient on its own: every decision below is settled, and anything still
open is listed under **Open questions** with instructions to resolve it in that ticket's `/planit`.

One ADR carries the load-bearing reasoning and ships alongside this spec, in the frontend. Read it
first:

- **frontend** `docs/adr/0007-occasions-are-a-destination.md` — amends **frontend**
  `docs/adr/0005-grouping-returns-as-an-opt-in.md`

Two existing decisions are **not** reopened and should be read before planning anything here:

- **backend** `docs/adr/0002-family-shares-target-an-occasion.md` — occasions carry no dates
- **frontend** `docs/adr/0001-one-place-for-every-list-shared-with-me.md` — one shared scope

---

## 1. Problem

v0.5.0 made an occasion the unit a list is shared to. It never gave the user a way to reach one.

- **`/occasions/:id` has exactly one entry point, three levels deep.** People → a family → its
  Occasions section. Nothing on the landing page links to an occasion, the nav has two tabs, and
  ADR 0005 deliberately made the Group-by-Occasion headings dead (`A source is still not a
  destination`). The page holding your budget and your shopping list is the hardest page to find.
- **Sharing to an occasion also has exactly one entry point**, and it runs the other way: open a
  list, open its panel, find the family, pick the occasion. There is no way to start from the
  occasion, so an empty occasion is a dead end that says "No lists are shared to this occasion yet"
  and offers nothing.
- **Every back link is a hardcoded destination.** Seven of them, in seven phrasings, for four
  destinations — and two (`← Back to families`, `← Back to connections`) name a *section* of
  `/people` rather than the page. Entering a list from a folder or an occasion and pressing the
  page's own back link lands you on `/lists`.
- **The browser's own Back is no better.** `/lists`'s Folder, Sort and Group by are component state,
  not URL state, so opening a list and pressing Back returns you to an unfiltered page. The same is
  true of every tab on `/occasions/:id` and `/folders/:id`, which are therefore unlinkable and
  unbookmarkable.
- **`shared_via` cannot describe a list that arrived twice.** It is a single nullable field
  (`app/schemas/gift_list.py:181`), and the repo query behind it collapses multiple routes to one
  row. A list shared both directly and through an occasion reports `shared_via: null`, so Group by
  Occasion files it under **"Not in an occasion"** — the leftover bucket ADR 0005 introduced
  specifically so that nothing shared with the viewer could silently vanish from a section claiming
  to be complete.
- **Two pages disagree about the same list.** `/lists` labels Gran's List "Boone Family"; the folder
  page labels it "from Gran Boone". Same list, same viewer, two components.
- **The sharing control and the People page are flat walls.** Every family then every connection, no
  filter, no search — the only search box in the app finds *strangers to connect to*. At an extended
  family's scale this is the surface that fails first.
- **The destructive actions are the unconfirmed ones.** `Remove connection`, family `Remove member`
  and `Leave Family` all fire on click, while archiving a list — reversible, and yours alone — gets
  a `window.confirm`.
- **`is_archived` is untrustworthy** because nothing ever asks anyone to set it. A finished Christmas
  keeps accepting shares until somebody remembers it exists, which is the same discoverability
  problem seen from the other end.

## 2. Goal

A user opens the app and sees the occasions they are shopping for, reaches any of them in one click,
can share a list into one from either direction, and can always get back to where they came from —
including by bookmarking it or pressing the browser's Back button.

## 3. Non-goals

- **A dashboard, or any new top-level route.** `/` was retired with no redirects by the navigation
  project precisely because it was a near-duplicate of `/lists`
  (`navigation-and-shared-accounts-project-spec.md` §1). Two-thirds of what a dashboard would carry
  — your lists, your folders — is still `/lists`. What changed since is that occasions have no home,
  which is a hole in `/lists`. See §5.
- **Dates or a lifecycle field on occasions.** Backend ADR 0002 settled that they carry none, and
  nothing here needs them: the archive nudge (§8) runs on activity, not on a calendar.
- **The word "active" in the UI.** `is_archived` is the only signal and "active" implies a second
  one. §8 makes the flag trustworthy instead of dressing it up.
- **Pagination, or any bounded collection endpoint.** Designed for ~50 connections and ~8 families;
  every collection endpoint stays unbounded. Revisit when a real user passes ~15 connections.
- **A third nav tab, or any change to the two-tab bar.** Frontend ADR 0001 stands.
- **Aggregate spend, or reconciling an occasion budget against a folder budget.** A purchase counted
  by both is two independent targets, working as specified in the shopping-lists project. Named here
  only so nobody treats it as a bug (§14 open question 2).
- **Reworking claims, budgets, or the shared-account model.**

---

## 4. Vocabulary

| UI word | Means | Changed by this project |
|---|---|---|
| **Occasion** | A family's shared gifting occasion | Becomes a **destination**: linked from `/lists`, from grouping headings, and reachable in one click |
| **Active** | — | **Removed from the UI.** Where a distinction is needed the word is "archived" or nothing at all |
| **← Back** | Return to wherever you came from | Replaces seven hardcoded phrasings. Names a destination only when there is no in-app history to return to |
| **Share** | Make a list visible | Now runs in both directions: list → occasion, and occasion → list |

Words the UI must still not use: everything listed in `CONTEXT.md`, unchanged, plus **"active"** as a
qualifier on occasions, lists or folders.

---

## 5. Occasions become reachable

### 5.1 The strip on `/lists`

A row of occasion cards on `/lists`, **below the `ActionableBanner` and above `My Lists`**.

- **Every non-archived occasion in every family the viewer belongs to**, including occasions with no
  lists shared to them. An empty occasion is the one most likely to need action, so hiding it defeats
  the purpose.
- **Four cards, then "See all N"**, which expands in place. A viewer in eight families can hold
  fifteen occasions; a full grid of those pushes the viewer's own lists off the screen and would
  have fixed occasion discovery by burying everything else.
- Sorted by **last activity**, descending — the same value §8 uses, computed once (§5.3).
- **Renders nothing at all when the viewer has no non-archived occasions** — no empty card, no
  heading. Same shape as `ActionableBanner`.
- The expansion is a *preference*, not a place: it uses `replace` (§6.3).

### 5.2 What a card shows

Occasion name · family name · count of lists shared to it · **"N of M bought"**.

- `N of M bought` is the **viewer's own** claims in that occasion — `my_bought_count` of
  `my_claimed_count`. It is suppressed entirely when `my_claimed_count` is zero, so an untouched
  occasion reads as empty rather than as "0 of 0 bought".
- **No money.** The budget line stays on the occasion page. `/lists` is the first screen the app
  shows, and a budget figure there puts what the viewer is spending on Christmas in front of whoever
  is standing behind them — including the people they are buying for.
- An occasion with **no lists** renders its body as the call to action (§5.4).

### 5.3 Activity, and why it is restricted

`last_activity_at` for an occasion is the most recent of:

- a list being shared into that occasion, and
- the **viewer's own** claim or purchase filed under it.

**It must never include another user's claim.** `CONTEXT.md` rule 2 forbids any screen, count or
badge from revealing claim state on a list the viewer owns. An occasion containing only the viewer's
own list would rise to the top of their strip the moment somebody claimed from it — a badge by
another name, telling the viewer that someone is buying them something and roughly when. A share into
an occasion leaks nothing, because the list it carries is already visible to every member.

This is one definition with two consumers: the strip's sort order and the archive nudge's staleness
threshold (§8). It is computed in one place server-side and is per-viewer by construction.

### 5.4 Sharing runs both ways now

The empty card's body — and the empty state on `/occasions/:id` — is a control, not a sentence. It
opens the sharing modal (§7.1) in **occasion mode**: the occasion is fixed, the list is chosen, and
each selection is a `PUT /lists/{list_id}/occasions/{occasion_id}`.

That endpoint already exists and is gated on `OwnedList`, so a member can only offer lists they own
and no new authorization is introduced. Sharing your own list into an occasion was never an organizer
power, so putting a write control on a card any member can see is consistent.

### 5.5 Grouping headings become links

Group by Occasion on `/lists` renders headings that link to `/occasions/:id`. Group by Person
headings still link nowhere — a person is a source, an occasion is now a place.

This amends ADR 0005; the reasoning is in frontend ADR 0007.

### 5.6 The family page stops being the way in

`/people/families/:id`'s Occasions section is reduced to **management** — create, rename, archive,
view archive. It is no longer the only route to an occasion, and the page should stop reading as
though it were.

---

## 6. Navigation

### 6.1 Back is history-aware

Every page's back control renders as a plain **`← Back`**.

- A `NavigationDepth` context counts in-app pushes for the session. When depth > 0, the control calls
  `navigate(-1)`.
- When depth is 0 — a deep link, a new tab, an email — it falls back to the page's hardcoded parent
  and renders the **named** label instead.

A generic label that is always true beats a specific one that is sometimes a lie. React Router does
not expose whether a history entry is in-app, which is why the depth counter exists rather than an
inspection of `history.state`.

### 6.2 The fallback table

The seven existing links survive as this table, with one word per destination:

| Page | Fallback | Label |
|---|---|---|
| `ListDetail` | `/lists` | `← Back to Lists` |
| `FolderDetail` | `/lists` | `← Back to Lists` |
| `ListsArchive` | `/lists` | `← Back to Lists` |
| `FamilyDetail` | `/people` | `← Back to People` |
| `ConnectionProfile` | `/people` | `← Back to People` |
| `OccasionDetail` | the family | `← Boone Family` |
| `FamilyArchive` | the family | `← Boone Family` |
| `NumericId` (invalid id) | per route | unchanged |

`families` and `connections` are gone as navigation labels. `CONTEXT.md` already forbids "connect"
and "collect" as navigation words; "connections" belongs with them.

### 6.3 URL state, and push versus replace

A shared `useSearchParamState(key, { mode })` hook, where `mode` is **required, not defaulted** — so
every call site has to state which kind of state it is holding.

- **`replace`** — Folder, Sort and Group by on `/lists`; the gift filter and sort on `/lists/:id`;
  the strip's "See all" expansion.
- **`push`** — the Lists / My shopping tab on `/occasions/:id` and `/folders/:id`; the sharing modal
  (`?share=open`).

The line is *is this a place, or a preference about where I already am*. A tab and an open modal are
places you can be and should be linkable and Back-closable. A sort order is not, and pushing it makes
Back mean "undo my last dropdown" — four presses to leave a page you glanced at.

This is the prerequisite that makes §6.1 worth anything: history-aware Back is useless while going
back loses the filters you had.

---

## 7. Scale

Designed for **~50 connections and ~8 families**. Anticipated, not observed — no user is near it
today. Nothing here bounds a payload; see §3.

### 7.1 The sharing panel becomes a modal

`pages/list-detail/SharingPanel.tsx` moves from an inline region — currently rendered *above* the
gifts, pushing the list's actual content down — into a modal.

- **One filter box across both sections.** Someone typing "boone" does not know or care whether
  Boone is a family or a surname. Two boxes double the chrome in a dialog already dense with occasion
  dropdowns and disabled-with-reason rows.
- **The filter must not hide disabled rows.** `CONTEXT.md` rule 6 makes "listed, disabled, reason
  given" load-bearing: a family with no active occasion, and a person an occasion share already
  reaches, are both shown dead *with the reason*. A filter that drops them recreates the "why can't I
  share with Gran?" question the rule exists to answer.
- A **"Shared with N"** summary line, so the state is legible without reading every checkbox.
- Opening pushes `?share=open` (§6.3), so the mobile back gesture closes it.
- The revoke-a-share confirmation currently nested inside the panel becomes a `ConfirmDialog`
  (§7.3) rather than a second hand-rolled dialog inside the first.
- **Occasion mode** (§5.4): occasion fixed, filtered to lists the viewer owns.

### 7.2 `New List` reuses it

`CreateList` shares to **families only** today — a defect the navigation project already recorded in
v0.4.0 (*"The create form can share to families but not to people"*) and never fixed. It reuses the
modal component and gains a people picker.

**Nothing is pre-checked.** Today every family with an active occasion arrives ticked, so a list
created to hold a private idea is visible to the Boones before its first gift is added. "Uncheck any
you'd rather keep it from" is the wrong direction for a sharing control. With nothing checked the
section becomes optional rather than something the user must audit, which is also what makes reuse
safe rather than intimidating.

### 7.3 People, and the confirmations

- **Filter-as-you-type** across both Families and Individuals. Sections and headings stay.
- **`Remove` moves off the row** into an overflow menu. On mobile it is currently the most visually
  dominant element on the page.
- **`Remove` gains a confirmation** — and so do family `Remove member` and `Leave Family`.

A single `<ConfirmDialog>` component replaces all three patterns in use today: `window.confirm`
(`ListDetail`, `FolderDetail`), an inline two-step (`FamilyDetail`'s `Delete Family`), and the
hand-rolled `role="dialog"` modals.

**Confirm where the action is irreversible *or* affects somebody else.** That means:

| Action | Today | After |
|---|---|---|
| Archive a list / folder | confirmed | **not confirmed** — reversible, and yours alone |
| Delete a list / folder / family | confirmed | confirmed |
| Remove a connection | **unconfirmed** | confirmed |
| Remove a family member | **unconfirmed** | confirmed |
| Leave a family | **unconfirmed** | confirmed |
| Revoke a share | inline dialog | `ConfirmDialog`, wording unchanged |
| Archive an occasion | unconfirmed | confirmed — it affects the whole family |

The current arrangement is exactly backwards, which is the point of doing this as one audit rather
than one ticket at a time.

---

## 8. The archive nudge

`is_archived` is only worth building on if somebody sets it. A prompt in `ActionableBanner` — which
already renders nothing when nothing is pending, and is already the single implementation of the
accept/decline shape — asks the question.

- **Occasions only.** A list you stopped adding to is dormant, not finished, and nudging it teaches
  people to dismiss the banner that also carries connection requests and family invites. A stale
  folder is private and costs nobody. An occasion is the only one whose staleness misleads *other
  people*: a dead Christmas that still accepts shares.
- **Shown to the occasion's creator or an organizer of its family.** Organizer-only would leave a
  member-created occasion in a family with an absent organizer permanently un-nudged; the creator
  already had the authority to make it.
- **Trigger: no activity for 60 days**, using the restricted definition in §5.3. Computing staleness
  from other people's claims would leak through the banner exactly what §5.3 refuses to leak through
  the sort order.
- **"Not yet" snoozes for 30 days.** No dismissal at all trains people to ignore the banner; a
  permanent dismissal that resets on new activity is surprising, because activity is what happens on
  an occasion someone is deliberately keeping open. A date is one nullable column and behaves the way
  people expect.
- Archiving from the banner goes through `ConfirmDialog` (§7.3).

Archiving still **blocks new shares and withdraws none** — unchanged from the shopping-lists project.
An archived occasion still serves its My shopping tab.

---

## 9. Information architecture

### 9.1 `/lists`

```
┌─────────────────────────────┐
│ Dave Boone wants to connect │   ActionableBanner — now also carries
│        [Accept]  [Decline]  │   the archive nudge (§8)
└─────────────────────────────┘

OCCASIONS                                    ← new (§5)
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ Christmas  │ │ Christmas  │ │ Gran's 80th│ │  …         │
│ 2026       │ │ 2026       │ │ Extended   │ │            │
│ Boone Fam. │ │ Extended   │ │ No lists   │ │            │
│ 4 lists    │ │ 2 lists    │ │ yet —      │ │            │
│ 1 of 1     │ │ 1 of 1     │ │ share one  │ │            │
│ bought     │ │ bought     │ │            │ │            │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
                                              See all 6 →

LISTS                  [⊕ New]
Folder: [ All lists ▾ ]  Sort: [ ▾ ]  Group by: [ ▾ ]

MY LISTS
SHARED WITH ME          ← occasion headings now link (§5.5)
```

Unchanged: the two-section split, the leftover buckets, the folder filter, `• N to buy`.

### 9.2 `/occasions/:id`

Tab selection moves into the URL (§6.3). The Lists tab's empty state becomes the occasion-mode share
control (§5.4). Back is `← Back`, falling back to the family (§6.2).

### 9.3 `/folders/:id`

Tab selection in the URL. **"Add a List" must offer lists shared with the viewer**, not only lists
they own — the folder in the dev seed already contains three shared lists that its own picker cannot
add. Attribution comes from the shared `ListAttribution` (§10.1).

### 9.4 `/people` and `/people/:id`

The filter and the overflow menu (§7.3). `ConnectionProfile` is **derived client-side** from the
shared scope — every list owned by that person, by any route — and `GET /connections/{id}/lists` is
retired. Today it returns direct shares only, which is why clicking "from Carol Boone" on a list that
reached the viewer through an occasion lands on a page that omits the list they came from.

It does **not** gain a list of occasions shared with that person. That is the family's business and
belongs on the occasion card; the profile stays a label's destination, not a second index.

### 9.5 `/people/families/:id`

Occasions section reduced to management (§5.6). Everything else unchanged.

---

## 10. API changes (backend)

### 10.1 `shared_via` becomes a list of routes

**No migration.** `shared_via` is computed at read time in `app/lists/service.py:102`; there is no
column. `repo.get_shared_lists_with_source` currently collapses a list's routes to one row, and that
is what changes.

```
shared_via: ShareRoute[]          # was: SharedVia | None

ShareRoute = { kind: "direct", person: {id, name} }
           | { kind: "occasion", occasion: {id, name}, family: {id, name} }
```

- An empty array replaces `null`.
- **The label rule is direct-wins**: when both routes exist, the row reads "from Carol Boone". A
  direct share is the durable grant — it survives the viewer leaving the family or the occasion share
  being revoked — and it is what `/lists` already shows.
- **Grouping uses every route.** A list shared to two occasions appears under both headings. ADR 0005
  already accepted this duplication for folders as "the honest rendering of a many-to-many
  membership"; the scalar was the only reason occasions could not do the same.
- `ListAttribution` becomes the one component rendering this, used by `/lists` **and** the folder
  page. It ships in Milestone 1 alongside the array, not later — otherwise the two pages stay
  visibly inconsistent for most of the project.

This is a breaking response change with a single consumer.

### 10.2 New: `GET /occasions`

```
GET /occasions?archived=false  →  OccasionSummary[]
```

`OccasionSummary` = `OccasionRead` plus `family_name`, `list_count`, `my_claimed_count`,
`my_bought_count`, `last_activity_at`.

Every occasion in every family the caller belongs to. **It takes no parameter naming another user**,
and the two `my_*` counts are the caller's own by construction — `CONTEXT.md` rule 2.

ADR 0005 chose a client-side fan-out for folder grouping because the client already held the data and
nothing was fetched until the viewer opted in. Neither holds here: the strip is on by default on the
landing page, and the counts exist nowhere client-side. A fan-out would be eight requests before
first paint and eight more for counts.

`last_activity_at` uses the restricted definition in §5.3.

### 10.3 Retired

- `GET /connections/{id}/lists` — §9.4.

### 10.4 Unchanged

`PUT`/`DELETE /lists/{list_id}/occasions/{occasion_id}` already serve §5.4 as they stand.

---

## 11. Data model and migrations (backend)

**One migration.**

```sql
CREATE TABLE occasion_archive_prompts (
  id            INTEGER PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  occasion_id   INTEGER NOT NULL REFERENCES occasions(id),
  dismissed_until TIMESTAMP NOT NULL,
  UNIQUE (user_id, occasion_id)
);
```

Deleting an occasion or a user must delete its prompt rows — SQLite runs with
`PRAGMA foreign_keys=ON`, so the purge path in `scripts/seed_dev.py` needs the same child-first
ordering it already applies to budgets.

Nothing else in this project touches the schema. `shared_via` is a response shape (§10.1), the strip
is a read (§10.2), and the navigation work is entirely frontend.

---

## 12. Rollout

Nothing here breaks for an existing user. No data is dropped, no route is retired that a user could
have bookmarked, and no re-sharing is required. This project is additive from the user's side, which
is the opposite of v0.5.0 and worth saying out loud.

The one visible change of behaviour is §7.2: `New List` stops pre-checking families. A user who has
learned to rely on that will create their next list unshared. It is the right default and it is
still worth a line in the release notes.

### 12.1 Branching

**Every ticket in this project branches from `release/v0.6.0`, and its PR targets `release/v0.6.0` —
not `main`.** This holds in both repos, which must each carry a branch of that name cut from `main`.

Nothing here is individually shippable: the `shared_via` array is a breaking response change that
the strip, the grouping fix and `ListAttribution` all sit on, and the frontend consuming it cannot
merge to a `main` the backend has not changed. `release/v0.6.0` accumulates the project and merges to
`main` once when v0.6.0 ships.

```bash
git fetch origin
git checkout -b <work-branch> origin/release/v0.6.0
gh pr create --base release/v0.6.0
```

Keep work branches current by merging `release/v0.6.0` in, never `main`.

**This spec and frontend ADR 0007 live on the release branch**, or ticket branches never see them.

### 12.2 Milestones

Ordered by dependency; each is a milestone in the Linear project.

1. **Contract** — `shared_via` array + `ListAttribution` unified · `GET /occasions` ·
   `occasion_archive_prompts` migration · `ConfirmDialog`. All shared plumbing; everything else
   depends on something here.
2. **Navigation** — the strip · grouping headings link · family page reduced ·
   `← Back` + depth context + fallback table · `useSearchParamState` across `/lists`, `/lists/:id`,
   `/occasions/:id`, `/folders/:id`.
3. **Scale** — sharing modal (both modes) · `New List` reuse and default-off · People filter ·
   `Remove` overflow.
4. **Correctness** — archive nudge · `ConnectionProfile` derived · folder "Add a List" includes
   shared lists · login distinguishes a network failure from bad credentials · the confirmation audit
   in §7.3.

**Known consequence:** several user-visible bugs stay live on the release branch until Milestone 4.
Pulling `ListAttribution` into Milestone 1 covers the worst of them (two pages disagreeing), but the
folder picker and the connection profile stay wrong in the interim. Acceptable because the release
branch is not deployed.

---

## 13. Testing expectations

**Backend**

- `shared_via` is an array in every case: direct only, occasion only, **both**, and neither. The
  both-ways case is the regression this project exists to fix — assert it carries two routes, not one
  and not null.
- A list shared to two occasions returns both routes.
- `GET /occasions` returns occasions from every family the caller belongs to, including ones with no
  lists; excludes archived unless asked; and **carries no other user's claim state**. Assert
  `my_claimed_count` and `my_bought_count` change when the caller claims and not when anyone else
  does — this is the rule-2 guard and it is the most important test in the project.
- `last_activity_at` moves on a share into the occasion and on the caller's own claim, and **does
  not move** on another user's claim.
- The archive nudge's eligibility: creator or organizer only; 60-day threshold; a live
  `dismissed_until` suppresses it; an expired one does not.
- Migration test: `occasion_archive_prompts` rows are removed with their occasion and their user.

**Frontend**

- Strip: renders nothing with no occasions; shows four then "See all"; sorts by activity; suppresses
  the bought line at zero claims; renders the empty occasion's CTA.
- Group by Occasion: headings link; a two-occasion list appears under both; the both-ways list is in
  its **occasion** bucket and not in "Not in an occasion".
- Back: with in-app history it calls `navigate(-1)` and renders `← Back`; with none it renders the
  named fallback and navigates there.
- URL state: a filter change replaces and does not grow history; a tab change pushes and Back returns
  to the previous tab; `?share=open` opens the modal on load and Back closes it.
- Sharing modal: the filter matches families and people from one box, and **disabled rows survive the
  filter with their reason**.
- `New List` arrives with nothing checked.
- `ConfirmDialog`: archive no longer prompts; remove-connection, remove-member and leave-family do.
- `ListAttribution` renders identically on `/lists` and the folder page for the same list — assert it
  once, against both call sites.

`scripts/seed_dev.py` must keep building every state above by hand, and gains: an occasion with no
lists (already present as `Gran's 80th`), an occasion stale enough to trigger the nudge, and a
dismissed prompt row.

---

## 14. Open questions

Resolve these in the owning ticket's `/planit`, not by guessing:

1. **Strip cap.** Four cards is a judgement, not a measurement. If a real user in eight families
   finds "See all" is always the first thing they click, the cap is wrong. Revisit with the ticket
   that builds it, not before.
2. **Two budgets counting one purchase.** A gift on a list that is both in a folder and shared to an
   occasion counts against both budgets, and nothing reconciles them. This is specified behaviour
   (two independent targets, shopping-lists project §7), and it is out of scope here — but nothing
   in the UI *says* so, and a user who sets both will eventually notice. Decide whether that needs a
   line of copy on the budget line, in the ticket that touches `BudgetLine`.
3. **Depth counter across a reload.** A hard reload resets `NavigationDepth` to 0, so Back falls back
   to the named parent even though browser history exists. Acceptable, probably preferable — but
   confirm in the back-link ticket rather than discovering it in review.

---

## Appendix — not tickets in this project

- **Dev workspaces drift from head.** `backend/start.sh` runs `alembic upgrade head` and
  `Dockerfile.prod` uses it, so production migrates itself. The dev compose service runs
  `uvicorn main:app` directly and never touches `start.sh`, so a workspace sits on whatever revision
  it was created with. On 2026-09-09 this made every occasion's My shopping tab return 500
  (`no such table: budgets`) in a workspace whose code was current. This is a workspace-template fix,
  not a ticket.
- **Env hostname drift.** In the same workspace, `frontend/.env` pointed at
  `api--boone-gifts--tom…`, `backend/.env` allowed CORS only for `web--main--boone-gifts--tom…`, and
  `vite.config.ts` `allowedHosts` permitted only `web--boone-gifts--tom…`. Whichever host is browsed,
  one of the three rejects it. Also a template concern.
