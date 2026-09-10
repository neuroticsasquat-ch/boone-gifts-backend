# ADR 0005 — An occasion's activity clock is per-viewer

**Status:** Accepted (2026-09-10), amended (2026-09-10, NEU-1294) — see [Amendment](#amendment-2026-09-10-neu-1294--the-nudge-does-not-use-this-clock)
**Project:** [BG: Occasions and Navigation](https://linear.app/neuroticsasquatch/project/bg-occasions-and-navigation-71dae76f947f)
**Ticket:** [NEU-1292](https://linear.app/neuroticsasquatch/issue/NEU-1292/occasion-index-endpoint-with-per-viewer-counts-backend)

## Context

Two features need to know when an occasion was last busy.

The occasion strip on `/lists` sorts its cards by it — the first screen the app shows, and the
reason occasions became reachable at all. M4's archive nudge ages an occasion out by it: no activity
for 60 days and the banner asks whether it should be archived.

The natural definition is the honest one: **the last thing that happened in this occasion, to
anyone.** A list shared in, a gift claimed, a purchase ticked — whoever did it. It is one aggregate
over rows the server already has, it is the same for every member so it can be cached, and it is
what a reader of `last_activity_at` will assume it means.

It also leaks, and it leaks the one thing this codebase is built around not leaking.

Frontend `CONTEXT.md` rule 2 — this repo's **invariant 1** — says no screen, count, badge or error
may reveal claim state on a list the viewer owns. Consider a viewer whose family occasion holds only
their own wishlist. Under the honest definition, that occasion sits quietly at the bottom of their
strip until somebody claims from it, and then rises to the top. The viewer learns that someone is
buying them a present, and roughly when. Nothing on the card says so; the *sort order* says so.

That is a badge by another name. ADR 0003 moved claims off the gift row precisely because
owner-blindness enforced by remembering had already failed once. A sort key is the same failure in a
new shape: nothing in the response is claim-shaped, so nothing looks like it needs guarding.

A share into an occasion is different, and safely so. The list it carries is already visible to
every member of the family — a share announces something the viewer could see by looking.

## Decision

**The clock is computed per-viewer, and never reads another user's claim.**

```
last_activity_at(occasion, viewer) = max(
    last share into the occasion,                      # everyone's, and safe
    viewer's own last claim or purchase filed under it, # theirs alone
    occasion.created_at,                               # the floor
)
```

Three properties make this hold as structure rather than as discipline:

- **The claim term is keyed on `claims.user_id == viewer.id`.** There is no argument to the query
  that could widen it, and no endpoint above it takes a parameter naming another user. A caller
  cannot ask for someone else's clock because the shape does not admit the question.
- **The claim term uses the stored filing** (`claims.occasion_id`), the same key the occasion's My
  shopping tab and budget line already use. Filing is stored and never re-derived (ADR 0003,
  NEU-1269 §4), so the clock agrees with the tab beneath it.
- **`created_at` is a floor, so the value is never null.** An occasion nothing has happened to still
  has a defensible age, which is what lets M4 nudge an empty occasion without a special case.

It is written **once**, as a SQL expression — `last_activity_at_expr(user_id)` in
`app/occasions/repository.py` — that both consumers embed in their own queries. The strip selects
it; the nudge filters on the narrower `shared_activity_at_expr()` it composes (see the Amendment).
Neither re-derives anything, and there is one place to read when the question
"does this leak?" comes up again.

## Consequences

**An occasion busy with other people's shopping sinks in your strip.** If four members of a family
are all buying from each other's lists and you have not claimed anything yet, that occasion looks as
stale to you as an abandoned one. This is the cost, it is real, and it is accepted: the alternative
tells you what those four people bought you.

**The clock is not cacheable across users.** Every viewer gets their own value, so it cannot be
denormalised onto `occasions` as a column, and it cannot be computed once per occasion in a
background job. It is a correlated subquery per row, per request. At the scale this project designs
for — ~8 families, ~15 occasions — that is not a problem worth pre-solving.

**Two members of one family can see the same occasions in a different order.** Expected, and worth
saying out loud before somebody reports it as a bug.

**M4's staleness is per-viewer too.** The nudge can fire for the occasion's creator and not for an
organizer who has been shopping in it. That is correct — the question the banner asks is "should
*this* be archived", and the person who has been active in it has their answer already.

**The obvious implementation is wrong, and does not look wrong.** Anyone optimising this query, or
adding a second sort key later, can reach the honest definition in one edit and break rule 2 without
touching anything named after a claim. That is why this decision has an ADR, a `CONTEXT.md` term,
and the project's most important test.

## Alternatives rejected

**Last activity by anyone.** The honest definition, described above. One cacheable value per
occasion, identical for every member, and it is what the field name suggests. Rejected: it turns the
strip's sort order into a claim badge on the viewer's own list.

**Shares only — drop the claim term.** Perfectly safe, cheap, and viewer-independent. Rejected
because it makes the clock useless for the thing it was built for: an occasion you have been
actively shopping in for a fortnight reads as untouched, and M4 would nudge you to archive it.

**Last activity by anyone, except on lists the viewer owns.** Keeps a shared value for most
occasions and patches the leak where it occurs. Rejected: it is per-viewer anyway the moment one
list is excluded, so it buys no caching — while being markedly harder to read, and one forgotten
`OR` away from leaking. If the value must be computed per viewer, compute it from the viewer's own
rows and have the guarantee by construction.

**A nullable clock, with `null` meaning nothing has happened.** Rejected in NEU-1292 Decision 2: the
nudge would have to decide what `null` means, almost certainly by falling back to `created_at`,
which puts a second copy of the definition in M4 — the one thing the M1 contract set out to prevent.

## Amendment (2026-09-10, NEU-1294) — the nudge does not use this clock

**The archive nudge ages an occasion by a narrower expression that reads no claim at all.** The
sentence above — *"The strip selects it; the nudge filters on it"* — was true when this ADR was
accepted and is false now. This section is the answer a future reader is looking for when they ask
why the nudge does not call `last_activity_at_expr`.

```
shared_activity_at(occasion) = max(
    last share into the occasion,   # everyone's, and safe
    occasion.created_at,            # the floor
)
```

It takes **no `user_id`**, and the absent parameter is the guarantee: there is no argument that could
widen it to a claim, and the signature says so at every call site.

### Why

The original decision keeps the caller's *own* claims because dropping them would make the strip's
sort useless. Eligibility for the nudge is a different question, and the same reasoning applied to it
lands somewhere else.

Under the per-viewer clock, eligibility turns on the caller's own claims, so two members disagree
about whether the same occasion is stale. That much is defensible — the Consequences section above
already accepts it. What is not defensible is the *shared* half of the disagreement.

Consider a family occasion holding only Gran's own wishlist, with nothing shared in for seventy days.
Gran is nudged. Tom claims a gift from her list today. If eligibility read anyone else's claims,
Gran's prompt would **vanish** — and Gran would learn that somebody is buying her a present, and
roughly when.

That is invariant 1 broken by the *absence* of a banner row. It is the same failure this ADR was
written about, in the one shape the original decision could not have caught: not a row that appears,
but one that stops appearing. A sort order at least leaves something on screen to be suspicious of.

Dropping the caller's own claims as well costs nothing — they are safe to read — and buys a property
worth having: **staleness is one fact about the occasion, identical for everyone eligible.** No
user's action can create or destroy another user's prompt, so there is nothing left to infer. Keeping
them would only spare the person actively shopping in an occasion a prompt the organizer beside them
still sees, which is not a benefit.

### Composition, not a second definition

`shared_activity_at_expr()` is the **first term of** `last_activity_at_expr(user_id)`, which calls
it rather than repeating it:

```python
func.max(
    shared_activity_at_expr(),
    func.coalesce(my_last_claim, Occasion.created_at),
    func.coalesce(my_last_purchase, Occasion.created_at),
)
```

The two clocks cannot drift, because one is literally built from the other. This keeps what the
original decision was actually protecting — one place to read when "does this leak?" is asked again —
while letting the narrower question have its own honest answer. Splitting the two across separate
files would have defeated the point of the ADR; two expressions in one module, one composed from the
other, does not.

### What this does not change

Everything above about the **strip** stands unamended: it still sorts on the per-viewer clock, that
clock still reads the caller's own claims, and the project's most important test still guards it.

One Consequence above is now wrong and worth naming: *"M4's staleness is per-viewer too. The nudge
can fire for the occasion's creator and not for an organizer who has been shopping in it."* It
cannot. Staleness is the same for both, and the audience — an organizer, or the occasion's creator —
is what decides who is asked.
