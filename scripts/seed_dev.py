"""Seed a dev database with every list-visibility state the UI can show.

The states that matter are the ones a single account cannot produce on its own:
a list shared directly with you, a list that reaches you only through a family,
a list that reaches you both ways at once, a list you keep for someone with no
account, a pending connection request, and a shared account with two people and
a list apiece. Reproducing those by hand through the UI takes
five logins, so this builds them in one pass.

    docker compose exec api python -m scripts.seed_dev            # seed
    docker compose exec api python -m scripts.seed_dev --reset    # re-seed
    docker compose exec api python -m scripts.seed_dev --purge    # remove

Run it with -m, as the other CLI entry points are: executing the file directly
puts scripts/ on sys.path instead of /app, and `app` stops importing.

Every fixture user is an @example.com address, and --purge/--reset delete only
rows reachable from those users. That is the safety mechanism: a real database
has no example.com users, so there is no wipe to fire by accident and no
destructive flag to guard.
"""

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models.account_person import AccountPerson
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.connection import Connection
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare
from app.models.user import User

DEFAULT_PASSWORD = "devpass123"

# (email, name, role)
SEED_USERS = [
    ("tom@example.com", "Tom Boone", "admin"),
    ("jane@example.com", "Jane Boone", "member"),
    ("mom@example.com", "Carol Boone", "member"),
    # Gran and Grandpa share this login — the shared-account fixture.
    ("gran@example.com", "Gran Boone", "member"),
    ("cousin@example.com", "Dave Boone", "member"),
]
SEED_EMAILS = [email for email, *_ in SEED_USERS]


def purge(db) -> int:
    """Delete every fixture user and everything hanging off them.

    Ordered child-first because SQLite runs with PRAGMA foreign_keys=ON, so a
    parent row with surviving children raises rather than cascading."""
    user_ids = set(
        db.execute(select(User.id).where(User.email.in_(SEED_EMAILS))).scalars()
    )
    if not user_ids:
        return 0

    list_ids = set(
        db.execute(
            select(GiftList.id).where(GiftList.owner_id.in_(user_ids))
        ).scalars()
    )
    family_ids = set(
        db.execute(
            select(Family.id).where(Family.created_by_id.in_(user_ids))
        ).scalars()
    )
    folder_ids = set(
        db.execute(
            select(Folder.id).where(Folder.owner_id.in_(user_ids))
        ).scalars()
    )

    # A fixture user may have claimed a gift on a list this purge is not
    # deleting, and a non-fixture list may be shared with them or into one of
    # their families — so each table is cleared by both routes, not just by list.
    if list_ids or user_ids:
        db.query(Gift).filter(
            Gift.list_id.in_(list_ids) | Gift.claimed_by_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(ListShare).filter(
            ListShare.list_id.in_(list_ids) | ListShare.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    if list_ids or family_ids:
        db.query(ListFamilyShare).filter(
            ListFamilyShare.list_id.in_(list_ids)
            | ListFamilyShare.family_id.in_(family_ids)
        ).delete(synchronize_session=False)
    if folder_ids or list_ids:
        db.query(FolderItem).filter(
            FolderItem.folder_id.in_(folder_ids)
            | FolderItem.list_id.in_(list_ids)
        ).delete(synchronize_session=False)
    if folder_ids:
        db.query(Folder).filter(Folder.id.in_(folder_ids)).delete(
            synchronize_session=False
        )
    if family_ids or user_ids:
        db.query(FamilyInvite).filter(
            FamilyInvite.family_id.in_(family_ids)
            | FamilyInvite.invited_by_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(FamilyMember).filter(
            FamilyMember.family_id.in_(family_ids)
            | FamilyMember.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    if family_ids:
        db.query(Family).filter(Family.id.in_(family_ids)).delete(
            synchronize_session=False
        )
    db.query(Connection).filter(
        Connection.requester_id.in_(user_ids) | Connection.addressee_id.in_(user_ids)
    ).delete(synchronize_session=False)
    if list_ids:
        db.query(GiftList).filter(GiftList.id.in_(list_ids)).delete(
            synchronize_session=False
        )
    # After the lists: lists.account_person_id references these rows and the FK
    # is enforced.
    db.query(AccountPerson).filter(AccountPerson.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
    return len(user_ids)


def seed(db, password: str) -> None:
    now = datetime.now(timezone.utc)

    users: dict[str, User] = {}
    for email, name, role in SEED_USERS:
        user = User(email=email, name=name, role=role, password_hash="")
        user.set_password(password)
        db.add(user)
        users[email] = user
    db.flush()

    tom = users["tom@example.com"]
    jane = users["jane@example.com"]
    carol = users["mom@example.com"]
    gran = users["gran@example.com"]
    dave = users["cousin@example.com"]

    def new_list(owner, name, description=None, recipient=None,
                 archived=False, person=None):
        gift_list = GiftList(
            name=name,
            description=description,
            owner_id=owner.id,
            recipient_name=recipient,
            account_person_id=person.id if person is not None else None,
            is_archived=archived,
        )
        db.add(gift_list)
        return gift_list

    def add_gifts(gift_list, names, claimed_by=None):
        """Claims land on the first gift only, so every list that has claims also
        has unclaimed gifts to look at."""
        for index, name in enumerate(names):
            claimed = claimed_by is not None and index == 0
            db.add(
                Gift(
                    list_id=gift_list.id,
                    name=name,
                    claimed_by_id=claimed_by.id if claimed else None,
                    claimed_at=now if claimed else None,
                )
            )

    tom_wishlist = new_list(tom, "Tom's Wishlist", "Ideas for me")
    tom_christmas = new_list(tom, "Christmas 2026", "What I want this year")
    # A recipient means one thing: someone with no account. Tom sees no claims on
    # it and cannot claim from it.
    beths_list = new_list(tom, "Beth's List", "Kept for Beth", recipient="Beth")
    new_list(tom, "Birthday 2025", archived=True)
    jane_wishlist = new_list(jane, "Jane's Wishlist", "Things I'd like")
    carol_wishlist = new_list(carol, "Carol's Wishlist", "Shared directly AND via family")
    # The shared account: one login, two people, and the three list shapes it
    # can produce — one for each person, and a household list for neither.
    gran.is_shared_account = True
    gran_person = AccountPerson(user_id=gran.id, name="Gran", position=0)
    grandpa_person = AccountPerson(user_id=gran.id, name="Grandpa", position=1)
    db.add_all([gran_person, grandpa_person])
    db.flush()

    gran_list = new_list(gran, "Gran's List", person=gran_person)
    grandpa_list = new_list(gran, "Grandpa's List", person=grandpa_person)
    kitchen_list = new_list(gran, "Ideas for the Kitchen",
                            "For the house, not for either of us")
    dave_wishlist = new_list(dave, "Dave's Wishlist")
    db.flush()

    add_gifts(tom_wishlist, ["Cast iron skillet", "Running shoes", "Coffee grinder"])
    add_gifts(tom_christmas, ["Wool socks", "Book: Piranesi"])
    add_gifts(beths_list, ["Puzzle", "Slippers"])
    add_gifts(jane_wishlist, ["Headphones", "Gardening gloves", "Tea sampler"],
              claimed_by=tom)
    add_gifts(carol_wishlist, ["Scarf", "Cookbook"], claimed_by=tom)
    add_gifts(gran_list, ["Cardigan", "Bird feeder"])
    add_gifts(grandpa_list, ["Fishing reel", "Reading lamp"])
    add_gifts(kitchen_list, ["Stand mixer", "Knife block"])
    add_gifts(dave_wishlist, ["Board game", "Whiskey glasses"])

    # Dave's request stays pending so the connection-request UI has something to
    # render; the rest are accepted.
    db.add(Connection(requester_id=tom.id, addressee_id=jane.id, status="accepted",
                      accepted_at=now))
    db.add(Connection(requester_id=carol.id, addressee_id=tom.id, status="accepted",
                      accepted_at=now))
    db.add(Connection(requester_id=gran.id, addressee_id=tom.id, status="accepted",
                      accepted_at=now))
    db.add(Connection(requester_id=dave.id, addressee_id=tom.id, status="pending"))

    boones = Family(name="Boone Family", created_by_id=tom.id)
    extended = Family(name="Extended Family", created_by_id=carol.id)
    db.add_all([boones, extended])
    db.flush()
    # Tom is organizer of one family and a plain member of the other, and belongs
    # to both — so "which family did this list come from?" has a real answer, and
    # the organizer-only surfaces (invites, rename, delete) are reachable as Tom.
    # "organizer"/"member" are the only roles the app understands; a family whose
    # top role is spelled anything else has no organizer at all.
    for user, role in [(tom, "organizer"), (carol, "member"), (gran, "member")]:
        db.add(FamilyMember(family_id=boones.id, user_id=user.id, role=role))
    for user, role in [(carol, "organizer"), (tom, "member"), (dave, "member")]:
        db.add(FamilyMember(family_id=extended.id, user_id=user.id, role=role))

    # Direct shares both ways, so "shared with me" and "shared by me" are both
    # populated for Tom.
    db.add(ListShare(list_id=jane_wishlist.id, user_id=tom.id))
    db.add(ListShare(list_id=tom_wishlist.id, user_id=jane.id))

    # Carol's list reaches Tom BOTH ways — it is the list that proves the dedupe
    # rule: one row in the shared scope, labelled with Carol, not the family.
    db.add(ListShare(list_id=carol_wishlist.id, user_id=tom.id))

    # Family shares. Gran's and Dave's lists reach Tom *only* this way — they are
    # the lists that prove the family/direct split.
    db.add(ListFamilyShare(list_id=carol_wishlist.id, family_id=boones.id))
    db.add(ListFamilyShare(list_id=gran_list.id, family_id=boones.id))
    db.add(ListFamilyShare(list_id=grandpa_list.id, family_id=boones.id))
    db.add(ListFamilyShare(list_id=kitchen_list.id, family_id=boones.id))
    db.add(ListFamilyShare(list_id=tom_christmas.id, family_id=boones.id))
    db.add(ListFamilyShare(list_id=tom_christmas.id, family_id=extended.id))
    db.add(ListFamilyShare(list_id=dave_wishlist.id, family_id=extended.id))

    christmas = Folder(owner_id=tom.id, name="Christmas 2026 Shopping",
                           description="Everyone I'm buying for")
    birthdays = Folder(owner_id=tom.id, name="Kids' Birthdays")
    db.add_all([christmas, birthdays])
    db.flush()
    for gift_list in (jane_wishlist, carol_wishlist, gran_list):
        db.add(FolderItem(folder_id=christmas.id, list_id=gift_list.id))
    db.add(FolderItem(folder_id=birthdays.id, list_id=beths_list.id))

    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the dev database")
    parser.add_argument("--password", default=DEFAULT_PASSWORD,
                        help=f"Password for every seeded user (default: {DEFAULT_PASSWORD})")
    parser.add_argument("--reset", action="store_true",
                        help="Delete existing seed data first, then seed")
    parser.add_argument("--purge", action="store_true",
                        help="Delete seed data and exit")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.purge or args.reset:
            removed = purge(db)
            print(f"Removed {removed} seeded user(s) and their data.")
            if args.purge:
                return

        existing = db.execute(
            select(User.email).where(User.email.in_(SEED_EMAILS))
        ).scalars().first()
        if existing:
            print(f"Seed data already present ({existing}). Re-run with --reset.")
            sys.exit(1)

        seed(db, args.password)
        print("Seeded 5 users, 10 lists, 2 families, 2 folders.")
        print(f"Log in as any of: {', '.join(SEED_EMAILS)}")
        print(f"Password: {args.password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
