# ADR 0002 — A family share targets an occasion, not a family

**Status:** Accepted (2026-09-08)
**Project:** [BG: Shopping Lists](https://linear.app/neuroticsasquatch/project/bg-shopping-lists-6fdd1e4a3cc1)

## Context

The project needed to answer "what counts toward this budget?" — and, underneath it, "which lists
are *in play* right now?" Neither question has an answer in today's model. A `list_family_shares`
row is permanent and unqualified: Jane's wishlist is shared with the Boone Family, full stop, for as
long as both exist. Claims accumulate against it across years with nothing to partition them.

Two shapes were considered for supplying that partition.

1. **Derive it from time.** An occasion is a named date window owned by a family; a claim on a
   member's list falls into it automatically when `claimed_at` lands inside the window. Nobody
   curates anything.
2. **Make it the sharing edge.** A list is shared *to an occasion*, and a claim inherits the
   occasion from the share it came through.

The first was chosen initially and then abandoned, because deriving attribution from dates is
ambiguous in exactly the cases that occur in real families:

- Boone Family runs "Christmas 2026" (Nov 1 – Dec 25) and "Gran's 80th" (Dec 10 – Dec 20). A claim
  on Dec 15 matches both. Forbidding the overlap is not an option; December birthdays are real.
- Jane belongs to both Boone Family and Extended Family, both of which run a Christmas occasion. A
  claim on her list matches both.

Resolving these needs a tie-break rule invisible to the user (narrowest window? most recent?), a
per-claim override to escape it, and a prompt for the residual ties — three mechanisms to paper over
a guess.

## Decision

**Sharing goes through an occasion.**

- An `Occasion` belongs to a family: `family_id`, `name`, `is_archived`. It has **no dates**. Its
  only job was ever to bound a period, and naming it "Christmas 2026" bounds it well enough.
- A list is shared to an occasion, not to a family. `list_family_shares` is replaced by a share row
  pointing at `occasions.id`; the family is derived through `occasions.family_id` and is not stored
  twice.
- **A family with no active occasion cannot be shared to.** It still appears in the sharing UI,
  disabled, with the reason given.
- Exactly one active occasion is the common case and stays a single click: the checkbox selects the
  family, the occasion is displayed but not selectable. More than one, and the user picks.
- Any member may create an occasion, warned when the family already has an active one. Renaming and
  archiving are organizer-only, matching every other family-wide action in `families/service.py`.
- Archiving blocks **new shares only**. Claiming through an archived occasion still works, existing
  claims stay editable, and its lists stay viewable in the archive view.

## Consequences

**Good**

- Attribution is exact and needs no rule. A claim inherits its occasion from the share it arrived
  through; there is no window to compare against and no tie to break.
- "What is in play this season" becomes a fact the family stated, not one the app inferred. This is
  what makes a budget possible at all.
- It replaces simple mode's reason to exist. The auto-grant existed so a naive user's list reached
  their family without them understanding sharing; one pre-checked box against a family with one
  active occasion does the same job with no second mode. See [ADR 0004](0004-simple-mode-is-retired.md).
- Role gains its first job that affects what members see, which is a change worth noticing but a
  small one: organizers already own every other family-wide setting.

**Bad, and accepted**

- **A family can lock itself out of sharing.** Archive the last active occasion and no member can
  share a list to that family until someone creates another. Mitigated by letting any member create
  one, so nobody waits on an absent organizer.
- **Every existing family grant is dropped.** No backfill; testers re-share. A migration that
  invented an occasion per family would have preserved sharing, but it would also have seeded every
  family with a name nobody chose, and the beta's data is explicitly resettable. This one needs
  telling real people about before it deploys.
- One more step between "I made a list" and "my family can see it", in the multi-occasion case.

## Alternatives rejected

- **Date windows with derived attribution** — the original design. Rejected for the ambiguity above:
  it needs a hidden tie-break rule, a per-claim override, and a prompt anyway, and it still gets
  Christmas-vs-birthday wrong whenever the rule and the user disagree.
- **Occasions hold lists, curated by an organizer** — keeps sharing pointed at the family and adds
  curation on top. The organizer then maintains a list set by hand, new lists are silently missing
  from it, and claims made months apart on the same list still land in the same occasion.
- **The claimer tags each claim** — exact, but it puts a decision on the hottest path in the app,
  every time, for a piece of bookkeeping most users will not care about at that moment.
- **Occasions with both dates and an explicit list set** — two dials to disagree with each other, and
  a silently empty budget when they do.
