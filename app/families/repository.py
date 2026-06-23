from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.user import User


def create_family(db: Session, name: str, created_by_id: int) -> Family:
    family = Family(name=name, created_by_id=created_by_id)
    db.add(family)
    db.flush()
    return family


def get_family(db: Session, family_id: int) -> Family | None:
    return db.get(Family, family_id)


def get_family_member(db: Session, family_id: int, user_id: int) -> FamilyMember | None:
    return db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == user_id,
        )
    ).scalar_one_or_none()


def get_family_members_with_users(
    db: Session, family_id: int
) -> list[tuple[FamilyMember, User]]:
    rows = db.execute(
        select(FamilyMember, User)
        .join(User, FamilyMember.user_id == User.id)
        .where(FamilyMember.family_id == family_id)
    ).all()
    return [(member, user) for member, user in rows]


def get_user_memberships(db: Session, user_id: int) -> list[FamilyMember]:
    return list(
        db.execute(
            select(FamilyMember).where(FamilyMember.user_id == user_id)
        )
        .scalars()
        .all()
    )


def get_member_count(db: Session, family_id: int) -> int:
    result = db.execute(
        select(func.count(FamilyMember.id)).where(
            FamilyMember.family_id == family_id
        )
    ).scalar_one()
    return result


def create_family_member(
    db: Session, family_id: int, user_id: int, role: str
) -> FamilyMember:
    member = FamilyMember(family_id=family_id, user_id=user_id, role=role)
    db.add(member)
    db.flush()
    return member


def update_family_name(db: Session, family: Family, name: str) -> Family:
    family.name = name
    db.flush()
    return family


def delete_all_members(db: Session, family_id: int) -> None:
    db.execute(
        delete(FamilyMember).where(FamilyMember.family_id == family_id)
    )


def delete_family(db: Session, family: Family) -> None:
    db.delete(family)
    db.flush()


def count_organizers(db: Session, family_id: int) -> int:
    return db.execute(
        select(func.count(FamilyMember.id)).where(
            FamilyMember.family_id == family_id,
            FamilyMember.role == "organizer",
        )
    ).scalar_one()


def delete_family_member(db: Session, member: FamilyMember) -> None:
    db.delete(member)
    db.flush()


def update_member_role(db: Session, member: FamilyMember, role: str) -> FamilyMember:
    member.role = role
    db.flush()
    return member


def family_ids_for_user(db: Session, user_id: int) -> set[int]:
    rows = db.execute(
        select(FamilyMember.family_id).where(FamilyMember.user_id == user_id)
    ).scalars().all()
    return set(rows)


def users_share_family(db: Session, a_id: int, b_id: int) -> bool:
    return bool(family_ids_for_user(db, a_id) & family_ids_for_user(db, b_id))


def get_member_user_ids(db: Session, family_id: int) -> list[int]:
    return list(
        db.execute(
            select(FamilyMember.user_id).where(FamilyMember.family_id == family_id)
        ).scalars()
    )
