from sqlalchemy import delete, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.folder_item import FolderItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare
from app.models.user import User


def create_list(
    db: Session,
    name: str,
    description: str | None,
    owner_id: int,
    recipient_name: str | None = None,
    account_person_id: int | None = None,
) -> GiftList:
    gift_list = GiftList(
        name=name,
        description=description,
        owner_id=owner_id,
        recipient_name=recipient_name,
        account_person_id=account_person_id,
    )
    db.add(gift_list)
    db.flush()
    return gift_list


def get_lists_by_owner(db: Session, owner_id: int, archived: bool = False) -> list[GiftList]:
    query = select(GiftList).where(
        GiftList.owner_id == owner_id,
        GiftList.is_archived == archived,
    ).order_by(GiftList.updated_at.desc())
    return list(db.execute(query).scalars().all())


def get_shared_lists_with_source(
    db: Session, user_id: int, archived: bool = False
) -> list[tuple[GiftList, str, int, str]]:
    """Every list (matching the `archived` flag) someone else has made visible to
    the caller, by either path: a direct `ListShare`, or a family grant on a family
    the caller belongs to. One row per list, carrying the source that explains it —
    `("user", owner id, owner name)` or `("family", family id, family name)`.

    A list reachable both ways reports the direct share: it is the more specific
    fact, and the one the viewer can act on. A list granted through two of the
    caller's families reports the lower family id — arbitrary but stable, so the
    label does not flicker between requests.

    The caller's own lists are never in scope, however they were granted.
    """
    owner = aliased(User)
    direct = (
        select(
            ListShare.list_id.label("list_id"),
            literal("user").label("kind"),
            owner.id.label("source_id"),
            owner.name.label("source_name"),
            literal(0).label("priority"),
        )
        .join(GiftList, GiftList.id == ListShare.list_id)
        .join(owner, owner.id == GiftList.owner_id)
        .where(
            ListShare.user_id == user_id,
            GiftList.owner_id != user_id,
            GiftList.is_archived == archived,
        )
    )
    via_family = (
        select(
            ListFamilyShare.list_id.label("list_id"),
            literal("family").label("kind"),
            Family.id.label("source_id"),
            Family.name.label("source_name"),
            literal(1).label("priority"),
        )
        .join(GiftList, GiftList.id == ListFamilyShare.list_id)
        .join(Family, Family.id == ListFamilyShare.family_id)
        .join(FamilyMember, FamilyMember.family_id == ListFamilyShare.family_id)
        .where(
            FamilyMember.user_id == user_id,
            GiftList.owner_id != user_id,
            GiftList.is_archived == archived,
        )
    )
    sources = direct.union_all(via_family).subquery()
    # Rank the sources of each list so the dedupe stays in the query: a direct
    # share outranks any family grant, and family grants break ties by id.
    ranked = select(
        sources.c.list_id,
        sources.c.kind,
        sources.c.source_id,
        sources.c.source_name,
        func.row_number()
        .over(
            partition_by=sources.c.list_id,
            order_by=(sources.c.priority, sources.c.source_id),
        )
        .label("rank"),
    ).subquery()
    query = (
        select(GiftList, ranked.c.kind, ranked.c.source_id, ranked.c.source_name)
        .join(ranked, ranked.c.list_id == GiftList.id)
        .where(ranked.c.rank == 1)
        # `updated_at` is second-resolution, so lists touched in the same second
        # tie; id breaks it, keeping the order stable across requests.
        .order_by(GiftList.updated_at.desc(), GiftList.id.desc())
    )
    return [(row[0], row[1], row[2], row[3]) for row in db.execute(query).all()]


def get_all_visible_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    query = select(GiftList).where(
        or_(
            GiftList.owner_id == user_id,
            GiftList.id.in_(shared_list_ids),
        ),
        GiftList.is_archived == archived,
    ).order_by(GiftList.updated_at.desc())
    return list(db.execute(query).scalars().all())


def get_list_by_id(db: Session, list_id: int) -> GiftList | None:
    return db.get(GiftList, list_id)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    for field, value in updates.items():
        setattr(gift_list, field, value)
    db.flush()
    return gift_list


def has_claimed_gifts(db: Session, list_id: int) -> bool:
    count = db.execute(
        select(Gift.id).where(
            Gift.list_id == list_id,
            Gift.claimed_by_id.isnot(None),
        ).limit(1)
    ).first()
    return count is not None


def delete_list(db: Session, gift_list: GiftList) -> None:
    list_id = gift_list.id
    db.execute(delete(FolderItem).where(FolderItem.list_id == list_id))
    db.execute(delete(ListShare).where(ListShare.list_id == list_id))
    db.execute(delete(ListFamilyShare).where(ListFamilyShare.list_id == list_id))
    db.execute(delete(Gift).where(Gift.list_id == list_id))
    db.delete(gift_list)
    db.flush()


def get_unseen_share_count(db: Session, user_id: int) -> int:
    from sqlalchemy import func as sa_func
    result = db.execute(
        select(sa_func.count())
        .select_from(ListShare)
        .where(ListShare.user_id == user_id, ListShare.seen_at.is_(None))
    ).scalar()
    return result or 0


def get_lists_shared_by_user(
    db: Session, owner_id: int, shared_with_user_id: int
) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(
        ListShare.user_id == shared_with_user_id
    )
    query = (
        select(GiftList)
        .where(
            GiftList.owner_id == owner_id,
            GiftList.id.in_(shared_list_ids),
            GiftList.is_archived == False,
        )
        .order_by(GiftList.updated_at.desc())
    )
    return list(db.execute(query).scalars().all())


def mark_share_seen(db: Session, list_id: int, user_id: int) -> None:
    from datetime import datetime, timezone
    share = db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user_id,
            ListShare.seen_at.is_(None),
        )
    ).scalar_one_or_none()
    if share:
        share.seen_at = datetime.now(timezone.utc)
        db.flush()
