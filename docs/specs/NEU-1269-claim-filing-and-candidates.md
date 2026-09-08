# NEU-1269 — Claim filing and candidates (backend)

**Ticket:** [NEU-1269](https://linear.app/neuroticsasquatch/issue/NEU-1269/claim-filing-and-candidates-backend)
**Story:** [NEU-1251](https://linear.app/neuroticsasquatch/issue/NEU-1251/each-claim-is-filed-under-one-occasion) — Each claim is filed under one occasion
**Milestone:** M4 — Claims become their own table · **Repo:** `boone-gifts-backend`
**Project spec:** `docs/specs/shopping-lists-project-spec.md` §6.2, §10.4
**Blocked by:** NEU-1265 (share-to-occasion), NEU-1268 (claims table) — **neither merged at time of writing**
**Blocks:** NEU-1271 (frontend prompt), NEU-1273 (shopping endpoints)

**This spec resolves project-spec open question 2** and **amends the M4 shared contract** — see §7.

---

## 1. What to build, and why

Give every claim an occasion so it lands in exactly one budget, without putting a decision in front
of the user on the app's hottest path.

`claims.occasion_id` exists after NEU-1268 but is always null. This ticket populates it: resolving it
on claim, validating it, letting the claimer correct it, and telling the client enough to know
whether to prompt.

Two facts from the project spec govern everything below and must not be blurred:

- **A claim is a global fact.** The gift is taken; nobody else should buy it. That is occasion-free.
- **`claims.occasion_id` is the claimer's private filing of their own spend.** Nobody else can see
  it. It exists only so the claim lands in one budget.

The second is subordinate to the first. Where they conflict, the claim wins — which is what §3.2
turns on.

---

## 2. The two sets

The single most important thing in this spec. There are **two** derived sets, not one, and conflating
them produces either permanent nagging or unfixable misfilings.

```python
def occasion_sets(db, gift_list, user) -> tuple[list[Occasion], list[Occasion]]:
    """Returns (allowed, suggested)."""
    allowed = [
        o for o in occasions_the_list_is_shared_to(db, gift_list)
        if user_is_member_of(db, user, o.family_id)
    ]
    active = [o for o in allowed if not o.is_archived]
    suggested = active if active else allowed
    return allowed, suggested
```

| Set | Is | Used for |
|---|---|---|
| **`allowed`** | Every occasion the list is shared to whose family the claimer belongs to — **archived included** | Validating an explicitly supplied `occasion_id`, on `POST` and `PATCH` |
| **`suggested`** | The active members of `allowed`; or, when none are active, all of `allowed` | Deciding auto-pick vs. prompt, and what the client renders |

### 2.1 Why `suggested` narrows to active

Occasions never disappear. By year three the Boone family has Christmas 2026 and 2027 archived and
2028 active, and a standing wishlist is shared to all three. A uniform set means **every claim
prompts, forever**, with the right answer obvious every time. The prompt is meant to be rare.

The `else allowed` fallback keeps the late shopper working: a list shared only to an archived
occasion still yields exactly one suggestion, so the January purchase files correctly.

### 2.2 Why `allowed` stays wide

Boone archives Christmas 2026 on Jan 2 while "Gran's 80th" is active. A Jan 8 Christmas claim gets
`suggested = [Gran's 80th]` and files there. If `allowed` were also narrowed, the user could **never
move it back** — the correction path would not exist. Keeping `allowed` wide makes the mistake
fixable, which is the whole point of §5.4's late-shopping guarantee.

### 2.3 Scope of a set

Per **list**, not per gift — sharing is a property of the list. Compute once per request, not per
gift row.

Per **account**, not per person. A shared account is one identity (ADR 0001); membership is the
account's.

---

## 3. Endpoint contracts

### 3.1 `POST /lists/{list_id}/gifts/{gift_id}/claim`

Body: `{ "occasion_id": int | null }`, the whole body optional.

| Case | Result |
|---|---|
| No `occasion_id`, `len(suggested) == 0` | **201**, `occasion_id = null` |
| No `occasion_id`, `len(suggested) == 1` | **201**, filed under it silently |
| No `occasion_id`, `len(suggested) >= 2` | **400** `ambiguous_occasion` — no claim created |
| `occasion_id` ∈ `allowed` | **201**, filed under exactly that |
| `occasion_id` ∉ `allowed` | **201**, claim created, filing **falls back** to the no-id rule above |
| `occasion_id: null` explicitly | **201**, `occasion_id = null`. An explicit null is a choice, not an omission |

Every 201 response states the filing actually recorded, so a client is never left guessing.

Existing claim rules from NEU-1268 are unchanged and take precedence: cannot claim your own gift,
cannot claim on an archived list, 409 when already claimed.

### 3.2 Why a bad `occasion_id` does not fail the claim

**Claiming is competitive** — it exists so two people don't buy the same present. The stale case is a
share revoked between the client's read and the user's click: the client asked, the server answered,
the world moved. Failing that claim hands the gift to whoever clicks next, for a reason nobody but
the claimer can even see.

So a good-faith stale id is forgiven. It is **not** an error and must not be logged as one.

### 3.3 Why a missing id with 2+ suggestions *does* fail

Different fault. The client had `claim_candidates` in the payload it already fetched and should have
prompted. It didn't — that is a bug, and the 400 is the only thing that will ever catch it.

Without it, a frontend regression that silently stops prompting is indistinguishable from a working
one: every claim files under null, every budget quietly reads low, and no test anywhere fails.

Accepted cost: a share **added** while the page is open turns 1 suggestion into 2, and an
innocent client trips the 400. It refetches and the user clicks again. Rare, and one retry.

### 3.4 `PATCH /claims/{id}`

Claimer only — **403** for anyone else, including the list's owner, and the response must not reveal
whether the claim exists.

Body: `{ "occasion_id"?: int | null, "amount_paid"?: Decimal | null }`.

- **Omitted fields are unchanged.** An amount-only edit must never touch the filing. Use
  `model_dump(exclude_unset=True)`, matching `update_occasion` in today's service layer.
- `occasion_id` ∈ `allowed` ∪ `{null}` → **200**.
- `occasion_id` ∉ `allowed` → **403**. No fallback here: on `PATCH` the user is explicitly choosing,
  and silently recording something else would be worse than refusing.

`PATCH` validates against `allowed`, so a past occasion can be chosen deliberately even when
`suggested` hides it (§2.2).

### 3.5 `claim_candidates` on the viewer payload

`GiftListDetailViewer` gains:

```json
"claim_candidates": [
  { "id": 3, "name": "Christmas 2026", "is_archived": false,
    "family": { "id": 1, "name": "Boone Family" } }
],
"claim_options": [ ... same shape ... ]
```

- `claim_candidates` is **`suggested`** — what the client renders and counts to decide on prompting.
- `claim_options` is **`allowed`** — so the picker can offer "show past occasions" without a second
  request. Without it, the §2.2 correction path exists in the API and no UI can reach it.
- Both carry `name`, `family.name` and `is_archived` because the picker needs labels, and two
  families' occasions are routinely called the same thing.
- **`GiftListDetailOwner` carries neither field, ever.** They are derived from the viewer's own
  memberships and would be meaningless — but more importantly, this is the class of field that
  produced the `claimed_count` leak. Assert their absence.
- One query per list-detail read, not per gift.

---

## 4. Filing is stored, never derived

`claims.occasion_id` is written once and only changes when the claimer changes it. Specifically,
**none** of the following alter an existing claim's filing:

1. The list's share to that occasion is revoked.
2. The occasion is archived.
3. The claimer leaves the family that owns the occasion.

A budget whose history rewrites itself is worse than no budget. Note case 3 in particular: leaving a
family deletes `list_occasion_shares` rows (NEU-1265) and may cascade claims — where a claim
*survives*, its filing must too.

---

## 5. Acceptance criteria

- 0 suggestions → claim succeeds, filed under nothing, no prompt.
- 1 suggestion → claim succeeds, filed under it, no prompt.
- 2+ suggestions and no id → 400, and no claim row is created.
- An explicit id in `allowed` is honoured exactly, including an archived occasion.
- An explicit id not in `allowed` still creates the claim, filed by the fallback rule.
- `PATCH` moves a filing within `allowed` ∪ `{null}`; anything else is 403.
- `PATCH` with only `amount_paid` leaves `occasion_id` untouched.
- Only the claimer may `PATCH`; the list owner cannot, and learns nothing from trying.
- Revoking the share, archiving the occasion, and leaving the family each leave an existing filing
  unchanged — **tested separately, all three**.
- A viewer's list detail carries `claim_candidates` and `claim_options`; an owner's carries neither.
- No owner-facing response exposes any claim's `occasion_id`.

---

## 6. Testing expectations

Beyond the criteria above:

- **The archived matrix.** For a list shared to combinations of {no occasions, one active, one
  archived, one of each, two active, two archived}: assert `suggested` and `allowed` for each, and
  that the prompt fires only when `len(suggested) >= 2`.
- **The year-three case explicitly** — two archived Christmases plus one active — asserting a single
  silent filing. This is the regression that makes the feature unusable if it breaks, and it is
  invisible in a fresh test database.
- **The Jan 8 case** — archived Christmas plus active Gran's 80th — asserting the claim files under
  Gran's 80th *and* that `PATCH` to Christmas 2026 is accepted.
- **Privacy**: a second user's claims never appear in any response; the owner's list detail carries
  no claim state at all.
- Extend `scripts/seed_dev.py` to build a family with two archived occasions and one active, and a
  list shared to all three. None of the above is reachable by hand otherwise.

---

## 7. Contract amendments this spec makes

The M4 milestone previously read: *"400 when 2+ candidates and none supplied, 403 when the supplied
occasion is not a candidate."* The second half is **superseded**:

| | Before | Now |
|---|---|---|
| `POST` with an id not in `allowed` | 403 | **201**, filing falls back (§3.2) |
| `PATCH` with an id not in `allowed` | 403 | 403 — unchanged |
| `POST` with no id, 2+ suggested | 400 | 400 — unchanged |

Also new to the contract: `claim_options` alongside `claim_candidates`, and the `allowed`/`suggested`
split itself.

**NEU-1271 depends on this.** The frontend must prompt from `claim_candidates` rather than relying on
a 403 to tell it something was wrong, because a stale id no longer produces one.

---

## 8. Out of scope

- **The claims table, migration, and the claim/purchase endpoints** — NEU-1268. This ticket only adds
  filing to endpoints that already exist by then.
- **Budgets and any rollup over `occasion_id`** — NEU-1275. Nothing here sums anything.
- **The shopping endpoints that read filings** — NEU-1273.
- **The frontend prompt** — NEU-1271.
- **Splitting one gift's cost between claimers.** `claims.gift_id` stays unique.
- **Filing a direct-share claim under an occasion.** Considered and rejected: `allowed` is bounded by
  the list's shares, so a claim on a directly-shared list files under nothing and reaches a budget
  only via a folder. Its discovery route is the `• N to buy` badge (NEU-1280, project spec §9.4). If
  that proves wrong, the fix is to widen `allowed` — not to special-case it here.
- **A currency on `amount_paid`** — NEU-1272.

## 9. Deferred

Nothing. Project-spec open question 2 is resolved by §3.5.
