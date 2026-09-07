from sqlalchemy.orm import Session

from app.account import repository as repo
from app.models.account_person import AccountPerson
from app.models.user import User
from app.schemas.account import AccountUpdate
from app.services.exceptions import BadRequestError, ConflictError, NotFoundError

TOO_FEW_PEOPLE_MESSAGE = "A shared account needs at least two people."
EMPTY_NAME_MESSAGE = "A person needs a name."
DUPLICATE_NAME_MESSAGE = "Two people on one account cannot share a name."
REPEATED_ID_MESSAGE = "The same person cannot appear twice."
UNKNOWN_PERSON_MESSAGE = "No such person on this account."

# A rename that swaps two names would collide with the (user_id, name) unique
# constraint mid-flush, because SQLite checks it per statement. Parking every
# changing name on an id-derived placeholder first makes any permutation legal.
_PENDING_NAME = "__account_person_pending_{id}__"


class LabelsWouldBeStripped(ConflictError):
    """The 409 of §3.3: this change would strip labels off lists, and the
    caller has not said yes to that yet. Re-issue with `?confirm=true`."""

    def __init__(self, affected_lists: int):
        super().__init__(
            f"This change would take the label off {affected_lists} list(s). "
            "Re-send with ?confirm=true to proceed."
        )
        self.affected_lists = affected_lists


def _validate_people(desired: AccountUpdate) -> None:
    """The shape rules of §4.3, as 400s.

    They live here rather than in the schema because a ValueError raised in a
    request-body validator surfaces as FastAPI's 422. The names are already
    stripped by the schema; what is left of nothing is rejected here.

    A full replace means the submitted array *is* the resulting set, so
    checking within it is complete; the (user_id, name) unique constraint stays
    as the backstop.
    """
    if any(not person.name for person in desired.people):
        raise BadRequestError(EMPTY_NAME_MESSAGE)

    ids = [person.id for person in desired.people if person.id is not None]
    if len(set(ids)) != len(ids):
        # The same person twice is a contradictory instruction, not a rename.
        raise BadRequestError(REPEATED_ID_MESSAGE)

    names = [person.name for person in desired.people]
    if len(set(names)) != len(names):
        raise BadRequestError(DUPLICATE_NAME_MESSAGE)


def _state(db: Session, user: User) -> dict:
    return {
        "is_shared_account": user.is_shared_account,
        "people": repo.get_people(db, user.id),
    }


def get_account(db: Session, user: User) -> dict:
    return _state(db, user)


def replace_account(
    db: Session, user: User, desired: AccountUpdate, confirm: bool = False
) -> dict:
    """Apply the whole desired state of the account's people (§3.2).

    An entry with an id renames in place, one without creates, an existing
    person left out is deleted, and the array's order becomes `position`.
    """
    _validate_people(desired)

    existing = repo.get_people(db, user.id)
    by_id: dict[int, AccountPerson] = {person.id: person for person in existing}

    for entry in desired.people:
        if entry.id is not None and entry.id not in by_id:
            # A person id belonging to another account is indistinguishable
            # from one that never existed — a 403 would confirm it exists.
            raise NotFoundError(UNKNOWN_PERSON_MESSAGE)

    # A shared account takes at least two people (§4.3). The one exception is
    # an account that is already shared being cut down to exactly one: that is
    # the documented auto-unmark below, which is what lets a client delete a
    # person by simply leaving them out and learn from the 200 that the mode
    # changed. Asking for a shared account with *nobody* on it is not that
    # case — it is a contradiction, and answering 200 would silently do
    # something other than what was asked.
    if desired.is_shared_account and len(desired.people) < 2:
        if not user.is_shared_account or not desired.people:
            raise BadRequestError(TOO_FEW_PEOPLE_MESSAGE)

    entries = desired.people
    if len(entries) < 2:
        # One person on an account labels nothing — there is no second person to
        # tell them apart from. Deleting down to one removes the last one too
        # and unmarks the account (§4.3); the response is how the client learns.
        entries = []
    resulting_shared = desired.is_shared_account and len(entries) >= 2

    kept_ids = {entry.id for entry in entries if entry.id is not None}
    removed = [person for person in existing if person.id not in kept_ids]

    # An account that is no longer shared loses every label; otherwise only the
    # lists pointing at a deleted person do.
    clears_every_label = not resulting_shared
    if clears_every_label:
        affected_lists = repo.count_lists_labelled(db, user.id)
    else:
        affected_lists = repo.count_lists_for_people(
            db, user.id, [person.id for person in removed]
        )
    if affected_lists and not confirm:
        raise LabelsWouldBeStripped(affected_lists)

    # Order matters throughout: the FK on lists.account_person_id is enforced,
    # so labels are nulled before the people they point at are deleted, and the
    # deletes are flushed before any create that might reuse a freed name.
    repo.clear_labels(
        db, user.id, None if clears_every_label else [p.id for p in removed]
    )
    repo.delete_people(db, removed)

    renamed = [
        by_id[entry.id]
        for entry in entries
        if entry.id is not None and by_id[entry.id].name != entry.name
    ]
    for person in renamed:
        person.name = _PENDING_NAME.format(id=person.id)
    if renamed:
        db.flush()

    for position, entry in enumerate(entries):
        if entry.id is None:
            continue
        person = by_id[entry.id]
        person.name = entry.name
        person.position = position
    db.flush()

    for position, entry in enumerate(entries):
        if entry.id is None:
            repo.create_person(db, user.id, name=entry.name, position=position)

    user.is_shared_account = resulting_shared
    db.flush()

    return _state(db, user)


def get_owned_person_id(db: Session, owner_id: int, person_id: int | None) -> int | None:
    """Validate that a label a list is being given belongs to the list's own
    account. Someone else's person id is a 404 for the same reason as in
    §3.2 — never silently accepted, never confirmed to exist."""
    if person_id is None:
        return None
    if repo.get_person(db, owner_id, person_id) is None:
        raise NotFoundError(UNKNOWN_PERSON_MESSAGE)
    return person_id
