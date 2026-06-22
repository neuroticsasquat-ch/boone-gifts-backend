from sqlalchemy.orm import Session

from app.families import repository as repo
from app.services.exceptions import ForbiddenError, NotFoundError


def _build_family_detail(db: Session, family_id: int) -> dict:
    family = repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    members_with_users = repo.get_family_members_with_users(db, family_id)
    return {
        "id": family.id,
        "name": family.name,
        "created_by_id": family.created_by_id,
        "members": [
            {"user_id": user.id, "name": user.name, "role": member.role}
            for member, user in members_with_users
        ],
    }


def create_family(db: Session, name: str, creator_id: int) -> dict:
    family = repo.create_family(db, name=name, created_by_id=creator_id)
    repo.create_family_member(db, family_id=family.id, user_id=creator_id, role="organizer")
    return _build_family_detail(db, family.id)


def list_families(db: Session, user_id: int) -> list[dict]:
    memberships = repo.get_user_memberships(db, user_id)
    result = []
    for membership in memberships:
        family = repo.get_family(db, membership.family_id)
        if family is None:
            continue
        member_count = repo.get_member_count(db, membership.family_id)
        result.append({
            "id": family.id,
            "name": family.name,
            "role": membership.role,
            "member_count": member_count,
        })
    return result


def get_family_detail(db: Session, family_id: int, user_id: int) -> dict:
    family = repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    membership = repo.get_family_member(db, family_id=family_id, user_id=user_id)
    if membership is None:
        raise ForbiddenError("Not a member of this family.")
    return _build_family_detail(db, family_id)


def rename_family(db: Session, family_id: int, user_id: int, name: str) -> dict:
    family = repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    membership = repo.get_family_member(db, family_id=family_id, user_id=user_id)
    if membership is None:
        raise ForbiddenError("Not a member of this family.")
    if membership.role != "organizer":
        raise ForbiddenError("Only organizers can rename the family.")
    repo.update_family_name(db, family, name)
    return _build_family_detail(db, family_id)


def delete_family(db: Session, family_id: int, user_id: int) -> None:
    family = repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    membership = repo.get_family_member(db, family_id=family_id, user_id=user_id)
    if membership is None:
        raise ForbiddenError("Not a member of this family.")
    if membership.role != "organizer":
        raise ForbiddenError("Only organizers can delete the family.")
    repo.delete_all_members(db, family_id)
    repo.delete_family(db, family)
