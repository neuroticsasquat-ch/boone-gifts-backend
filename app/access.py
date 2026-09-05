from sqlalchemy.orm import Session

from app.connections.repository import find_accepted_connection_between
from app.families.repository import users_share_family
from app.list_families.repository import list_granted_to_any_family_of
from app.models.gift_list import GiftList
from app.models.user import User
from app.shares.repository import find_share


def users_share_access(db: Session, a_id: int, b_id: int) -> bool:
    """Any standing access path between two users: accepted connection OR shared family."""
    if find_accepted_connection_between(db, a_id, b_id) is not None:
        return True
    return users_share_family(db, a_id, b_id)


def can_view_list(db: Session, user: User, gift_list: GiftList) -> bool:
    """Whether `user` may view `gift_list`: owner OR has a ListShare OR the owner
    granted the list to a family `user` belongs to. A connection alone does NOT
    grant visibility, and neither does bare family co-membership."""
    if gift_list.owner_id == user.id:
        return True
    if find_share(db, gift_list.id, user.id) is not None:
        return True
    return list_granted_to_any_family_of(db, gift_list.id, user.id)
