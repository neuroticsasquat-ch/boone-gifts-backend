from collections.abc import Sequence

from sqlalchemy import Integer, String, cast, delete, literal, null, or_, select
from sqlalchemy.orm import Session, aliased

from app.claims import repository as claims_repo
from app.models.folder_item import FolderItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
from app.models.occasion import Occasion
from app.models.user import User
from app.schemas.gift_list import (
    DirectShareRoute,
    NamedRef,
    OccasionShareRoute,
    ShareRoute,
)


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


def get_share_routes(
    db: Session, viewer_id: int, list_ids: Sequence[int] | None = None
) -> dict[int, list[ShareRoute]]:
    """Every route by which a list reached the viewer, keyed by list id.

    A route is one way the list became visible: a direct `ListShare`, or a share
    to an occasion of a family the viewer belongs to. A list can have several —
    shared directly *and* to an occasion, or to two occasions of two different
    families — and every one of them is reported. Nothing is ranked away here;
    the label rule (direct wins) lives in the client.

    `list_ids=None` means the viewer's whole shared scope, so the union defining
    that scope is written once: `app/lists/service.py:get_shared_lists` takes
    the scope from the keys rather than restating the query and drifting from it.

    Lists with no route are simply absent from the mapping — callers read it with
    `.get(list_id, [])`, so an owned row and a row the viewer can no longer see
    both come back as an empty array.

    Order within a list is direct first, then occasions by ascending occasion id
    — the same order the ranking used to break ties with, kept so a response is
    byte-stable across requests and tests can assert a literal. It is
    deliberately **not** a contract the client may read `routes[0]` from: giving
    direct-wins a second home here is what NEU-1290 set out to stop.

    The exclusions are load-bearing and unchanged: the viewer's own lists are
    never in scope however they were shared, and an archived occasion still
    yields a route, because archiving blocks new shares and never withdraws
    visibility (ADR 0002 §5.4, `CONTEXT.md` invariant 2).
    """
    if list_ids is not None and not list_ids:
        return {}

    owner = aliased(User)
    direct = (
        select(
            ListShare.list_id.label("list_id"),
            literal("direct").label("kind"),
            owner.id.label("source_id"),
            owner.name.label("source_name"),
            cast(null(), Integer).label("family_id"),
            cast(null(), String).label("family_name"),
            literal(0).label("priority"),
        )
        .join(GiftList, GiftList.id == ListShare.list_id)
        .join(owner, owner.id == GiftList.owner_id)
        .where(
            ListShare.user_id == viewer_id,
            GiftList.owner_id != viewer_id,
        )
    )
    via_occasion = (
        select(
            ListOccasionShare.list_id.label("list_id"),
            literal("occasion").label("kind"),
            Occasion.id.label("source_id"),
            Occasion.name.label("source_name"),
            Family.id.label("family_id"),
            Family.name.label("family_name"),
            literal(1).label("priority"),
        )
        .join(GiftList, GiftList.id == ListOccasionShare.list_id)
        .join(Occasion, Occasion.id == ListOccasionShare.occasion_id)
        .join(Family, Family.id == Occasion.family_id)
        .join(FamilyMember, FamilyMember.family_id == Occasion.family_id)
        .where(
            FamilyMember.user_id == viewer_id,
            GiftList.owner_id != viewer_id,
        )
    )
    if list_ids is not None:
        direct = direct.where(ListShare.list_id.in_(list_ids))
        via_occasion = via_occasion.where(ListOccasionShare.list_id.in_(list_ids))

    routes = direct.union_all(via_occasion).subquery()
    query = select(routes).order_by(
        routes.c.list_id, routes.c.priority, routes.c.source_id
    )

    by_list: dict[int, list[ShareRoute]] = {}
    for row in db.execute(query).all():
        if row.kind == "direct":
            route: ShareRoute = DirectShareRoute(
                kind="direct",
                person=NamedRef(id=row.source_id, name=row.source_name),
            )
        else:
            route = OccasionShareRoute(
                kind="occasion",
                occasion=NamedRef(id=row.source_id, name=row.source_name),
                family=NamedRef(id=row.family_id, name=row.family_name),
            )
        by_list.setdefault(row.list_id, []).append(route)
    return by_list


def get_lists_by_ids(
    db: Session, list_ids: Sequence[int], archived: bool = False
) -> list[GiftList]:
    """The lists with these ids, matching the `archived` flag.

    `updated_at` is second-resolution, so lists touched in the same second tie;
    id breaks it, keeping the order stable across requests.
    """
    if not list_ids:
        return []
    query = (
        select(GiftList)
        .where(
            GiftList.id.in_(list_ids),
            GiftList.is_archived == archived,
        )
        .order_by(GiftList.updated_at.desc(), GiftList.id.desc())
    )
    return list(db.execute(query).scalars().all())


def get_all_visible_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    """Every list the caller may see, by any path — the third term included.

    The three terms are `can_view_list`'s, restated as a query because this one
    answers for a whole scope rather than one row. Leaving the occasion term out
    made this disagree with the codebase's one visibility predicate
    (`CONTEXT.md` invariant 2), which is exactly the divergence the invariant
    exists to prevent.
    """
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    occasion_list_ids = (
        select(ListOccasionShare.list_id)
        .join(Occasion, Occasion.id == ListOccasionShare.occasion_id)
        .join(FamilyMember, FamilyMember.family_id == Occasion.family_id)
        .where(FamilyMember.user_id == user_id)
    )
    query = select(GiftList).where(
        or_(
            GiftList.owner_id == user_id,
            GiftList.id.in_(shared_list_ids),
            GiftList.id.in_(occasion_list_ids),
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


def delete_list(db: Session, gift_list: GiftList) -> None:
    list_id = gift_list.id
    db.execute(delete(FolderItem).where(FolderItem.list_id == list_id))
    db.execute(delete(ListShare).where(ListShare.list_id == list_id))
    db.execute(delete(ListOccasionShare).where(ListOccasionShare.list_id == list_id))
    # Claims hold a foreign key into `gifts`, so they unwind before the gifts do.
    claims_repo.delete_claims_on_lists(db, [list_id])
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
