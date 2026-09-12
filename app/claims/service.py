"""Filing a claim under an occasion, and correcting that filing afterwards.

A claim is a global fact — the gift is taken, and nobody else should buy it.
`claims.occasion_id` is something narrower and private: the claimer's own filing
of their own spend, so it lands in exactly one budget. Where the two conflict
the claim wins, which is what `resolve_filing` turns on (NEU-1269 §3.2).
"""
from sqlalchemy.orm import Session

from app.claims import repository as repo
from app.list_occasions import repository as shares_repo
from app.models.claim import Claim
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.user import User
from app.schemas.claim import CandidateFamily, OccasionCandidate
from app.services.exceptions import BadRequestError, ForbiddenError

# The client had `claim_candidates` in the payload it already fetched and should
# have prompted. A machine-readable detail, unlike the human sentences the other
# 400s on this endpoint carry, because only a client ever reads this one.
AMBIGUOUS_OCCASION = "ambiguous_occasion"

NOT_YOUR_CLAIM = "Only the claimer can change this claim."


def occasion_sets(
    db: Session, gift_list: GiftList, user: User
) -> tuple[list[OccasionCandidate], list[OccasionCandidate]]:
    """The two derived sets a filing decision needs, as `(allowed, suggested)`.

    `allowed` is every occasion the list is shared to whose family the claimer
    belongs to, **archived included**. It validates an explicitly supplied id.

    `suggested` is the active members of `allowed`, or all of `allowed` when
    none are active. It decides auto-pick versus prompt.

    They are two sets rather than one because conflating them breaks in both
    directions. Narrowing `suggested` to active is what stops every claim
    prompting forever once a family has three Christmases behind it; the
    `else allowed` fallback keeps the January shopper working. Keeping
    `allowed` wide is what makes a misfiled late claim fixable — narrow it too
    and the correction path in §2.2 simply does not exist.

    Per list, not per gift: sharing is a property of the list.
    """
    allowed = [
        OccasionCandidate(
            id=occasion.id,
            name=occasion.name,
            is_archived=occasion.is_archived,
            family=CandidateFamily(id=family.id, name=family.name),
        )
        for occasion, family in shares_repo.get_shared_occasions_for_member(
            db, gift_list.id, user.id
        )
    ]
    active = [candidate for candidate in allowed if not candidate.is_archived]
    return allowed, (active if active else allowed)


def resolve_filing(
    db: Session,
    gift_list: GiftList,
    user: User,
    occasion_id: int | None,
    provided: bool,
) -> int | None:
    """Which occasion a new claim files under (NEU-1269 §3.1).

    Raises `BadRequestError(AMBIGUOUS_OCCASION)` when the caller supplied no id
    and two or more occasions are suggested — the one case where the claim is
    refused outright, and deliberately so: a frontend that silently stops
    prompting is otherwise indistinguishable from a working one, and every
    budget quietly reads low with no test anywhere failing (§3.3).
    """
    allowed, suggested = occasion_sets(db, gift_list, user)

    if provided:
        if occasion_id is None:
            # An explicit null is a choice, not an omission.
            return None
        if any(candidate.id == occasion_id for candidate in allowed):
            return occasion_id
        # A stale id — the share was revoked between the client's read and the
        # user's click. Claiming is competitive, so this must never cost the
        # user the gift (§3.2): fall through and file by the no-id rule, and
        # where that rule cannot decide, file under nothing rather than fail.
        # It is not an error and must not be logged as one.
        return suggested[0].id if len(suggested) == 1 else None

    if len(suggested) >= 2:
        raise BadRequestError(AMBIGUOUS_OCCASION)
    return suggested[0].id if suggested else None


def get_own_claim(db: Session, claim_id: int, user: User) -> Claim:
    """The caller's own claim, or a 403.

    A claim that does not exist raises the same ForbiddenError as somebody
    else's, so the response never reveals whether a claim exists — the list's
    owner must learn nothing by probing ids.
    """
    claim = repo.get_claim(db, claim_id)
    if claim is None or claim.user_id != user.id:
        raise ForbiddenError(NOT_YOUR_CLAIM)
    return claim


def update_claim(db: Session, claim_id: int, user: User, updates: dict) -> Claim:
    """Correct a claim's filing, its amount, or both.

    `updates` is `model_dump(exclude_unset=True)`, so an amount-only edit never
    touches the filing. A supplied `occasion_id` is validated against `allowed`
    rather than `suggested` — choosing a past occasion is exactly the correction
    §2.2 exists for — and anything outside it is refused. There is no fallback
    here: on a PATCH the user is explicitly choosing, and silently recording
    something else would be worse than refusing.
    """
    claim = get_own_claim(db, claim_id, user)

    if "occasion_id" in updates and updates["occasion_id"] is not None:
        gift = db.get(Gift, claim.gift_id)
        gift_list = db.get(GiftList, gift.list_id)
        allowed, _ = occasion_sets(db, gift_list, user)
        if not any(c.id == updates["occasion_id"] for c in allowed):
            raise ForbiddenError("That occasion is not available for this claim.")

    return repo.update_claim(db, claim, updates)
