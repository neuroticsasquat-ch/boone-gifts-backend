"""Seed a dev database with every list-visibility state the UI can show.

The states that matter are the ones a single account cannot produce on its own:
a list shared directly with you, a list that reaches you only through a family,
a list that reaches you both ways at once, a list you keep for someone with no
account, a pending connection request, a shared account with two people and
a list apiece, and a family with two archived Christmases behind it plus one
active — the state that decides whether claiming prompts or files silently.
Reproducing those by hand through the UI takes five logins, so this builds them
in one pass.

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
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models.budget import Budget
from app.models.claim import Claim
from app.models.account_person import AccountPerson
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.connection import Connection
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
from app.models.occasion import Occasion
from app.models.occasion_archive_prompt import OccasionArchivePrompt
from app.models.user import User

DEFAULT_PASSWORD = "devpass123"

# "bought, but the claimer skipped the amount" — distinct from not bought at
# all, and the case a budget has to report as an understatement rather than a
# fact. A sentinel because None already means "not bought".
SKIPPED = object()

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

    # A fixture user may hold a claim on a list this purge is not deleting, and a
    # non-fixture list may be shared with them or into one of their families — so
    # claims and shares are cleared by both routes. Gifts go by list alone: a
    # foreign gift is not ours to delete just because a fixture user claimed it.
    if list_ids or user_ids:
        # Claims hold a foreign key into `gifts`, so they go first — by either
        # route, since a fixture user's claim may sit on a non-fixture gift.
        gift_ids = set(
            db.execute(select(Gift.id).where(Gift.list_id.in_(list_ids))).scalars()
        )
        db.query(Claim).filter(
            Claim.gift_id.in_(gift_ids) | Claim.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(Gift).filter(
            Gift.list_id.in_(list_ids)
        ).delete(synchronize_session=False)
        db.query(ListShare).filter(
            ListShare.list_id.in_(list_ids) | ListShare.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    occasion_ids = set(
        db.execute(
            select(Occasion.id).where(Occasion.family_id.in_(family_ids))
        ).scalars()
    ) if family_ids else set()
    # Budgets point at the occasions and folders below and at the users above,
    # so they go before all three. By either route: a fixture user may budget a
    # non-fixture occasion, and a non-fixture user may budget nothing of ours,
    # but a fixture folder they somehow reached would still block its delete.
    if occasion_ids or folder_ids or user_ids:
        db.query(Budget).filter(
            Budget.occasion_id.in_(occasion_ids)
            | Budget.folder_id.in_(folder_ids)
            | Budget.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    # Archive prompts point at the occasions below and the users above, exactly
    # as the budgets do, and go by both routes for the same reason: a fixture
    # user may have dismissed a non-fixture occasion.
    if occasion_ids or user_ids:
        db.query(OccasionArchivePrompt).filter(
            OccasionArchivePrompt.occasion_id.in_(occasion_ids)
            | OccasionArchivePrompt.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    if list_ids or occasion_ids:
        db.query(ListOccasionShare).filter(
            ListOccasionShare.list_id.in_(list_ids)
            | ListOccasionShare.occasion_id.in_(occasion_ids)
        ).delete(synchronize_session=False)
    if occasion_ids:
        db.query(Occasion).filter(Occasion.id.in_(occasion_ids)).delete(
            synchronize_session=False
        )
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

    def add_gifts(gift_list, names, claimed_by=None, bought=None, claimed_at=None):
        """Claims land on the first gift only, so every list that has claims also
        has unclaimed gifts to look at.

        `bought` is the amount the claimer recorded paying. Pass a Decimal for a
        purchase with a price on it, `SKIPPED` for one where they skipped the
        amount, and leave it None for a claim that has not been bought yet — the
        three states a budget rollup has to tell apart.

        `claimed_at` defaults to `now`, which is captured before the occasions
        and their shares are written and so lands *earlier* than every share's
        `CURRENT_TIMESTAMP`. Pass a later one where the claim has to be the
        newest thing that happened in its occasion."""
        for index, name in enumerate(names):
            gift = Gift(list_id=gift_list.id, name=name)
            db.add(gift)
            if claimed_by is not None and index == 0:
                db.flush()
                claimed = claimed_at or now
                db.add(
                    Claim(
                        gift_id=gift.id,
                        user_id=claimed_by.id,
                        claimed_at=claimed,
                        purchased_at=claimed if bought is not None else None,
                        amount_paid=bought if bought is not SKIPPED else None,
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
    # The year-three case: a standing list shared to every Christmas the Boones
    # have ever run, two of them archived. It is the only fixture that proves a
    # claim files silently instead of prompting once a family has history, and
    # it is invisible in a fresh database — every occasion there is active.
    standing_list = new_list(
        carol, "Carol's Standing Wishlist", "Shared to three Christmases, two past"
    )
    db.flush()

    add_gifts(tom_wishlist, ["Cast iron skillet", "Running shoes", "Coffee grinder"])
    # The one claim in this seed that is *not* Tom's, on a list Tom owns. Every
    # other claim here is his, so without it the dev database cannot show
    # NEU-1292's whole point by hand: with the per-viewer clock (ADR 0005) Tom's
    # Boone Christmas card does not move and his bought line does not change
    # when Carol takes this; with the obvious "last claim by anyone" it jumps to
    # the front of his strip the moment the seed runs.
    #
    # The explicit later timestamp is what makes that visible. On the shared
    # `now` the claim predates every occasion share, so both implementations
    # would leave the strip tied on the shares and ordered by id — identical
    # whether the clock leaks or not, which is the state this seed exists to end.
    add_gifts(
        tom_christmas,
        ["Wool socks", "Book: Piranesi"],
        claimed_by=carol,
        claimed_at=now + timedelta(days=1),
    )
    add_gifts(beths_list, ["Puzzle", "Slippers"])
    # Tom's three claim states, so every budget case is reachable by hand: taken
    # but not yet bought, bought with an amount, and bought with the amount
    # skipped — the last of which a rollup must report as an understatement.
    add_gifts(jane_wishlist, ["Headphones", "Gardening gloves", "Tea sampler"],
              claimed_by=tom)
    add_gifts(carol_wishlist, ["Scarf", "Cookbook"],
              claimed_by=tom, bought=Decimal("64.99"))
    add_gifts(gran_list, ["Cardigan", "Bird feeder"])
    # Claimed and filed under an *archived* Christmas, which is the only way to
    # see by hand that an archived occasion still serves its shopping tab.
    add_gifts(grandpa_list, ["Fishing reel", "Reading lamp"],
              claimed_by=tom, bought=Decimal("42.00"))
    add_gifts(kitchen_list, ["Stand mixer", "Knife block"])
    # Reaches Tom only through the Extended family's occasion, so it is also the
    # claim whose filing NEU-1269 has to resolve without a direct share.
    add_gifts(dave_wishlist, ["Board game", "Whiskey glasses"],
              claimed_by=tom, bought=SKIPPED)
    # Left unclaimed on purpose: claiming one as Tom is how the silent filing is
    # checked by hand, and the picker's "show past occasions" needs the two
    # archived Christmases behind it.
    add_gifts(standing_list, ["Umbrella", "Desk lamp", "Wool blanket"])

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
    # Work Friends deliberately never gets an occasion: it is the family the
    # sharing control has to render disabled, with the reason given.
    work_friends = Family(name="Work Friends", created_by_id=tom.id)
    db.add_all([boones, extended, work_friends])
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
    for user, role in [(tom, "organizer"), (dave, "member")]:
        db.add(FamilyMember(family_id=work_friends.id, user_id=user.id, role=role))

    # Direct shares both ways, so "shared with me" and "shared by me" are both
    # populated for Tom.
    db.add(ListShare(list_id=jane_wishlist.id, user_id=tom.id))
    db.add(ListShare(list_id=tom_wishlist.id, user_id=jane.id))

    # Carol's list reaches Tom BOTH ways — it is the list that proves routes are
    # plural: one row in the shared scope carrying TWO entries in `shared_via`,
    # the direct share and the Boones' Christmas. The client labels it "from
    # Carol" (direct wins, in `ListAttribution`) and still groups it under the
    # occasion, which is the grouping the old single-route field made impossible.
    db.add(ListShare(list_id=carol_wishlist.id, user_id=tom.id))

    # Occasions, in the three states the sharing control has to render: one
    # active (the single-click case), several active (the select case), and none
    # at all (the disabled row). The archived one exists to prove that archiving
    # blocks new shares without withdrawing the shares already made.
    boones_christmas = Occasion(
        family_id=boones.id, name="Christmas 2026", created_by_id=tom.id
    )
    boones_last_year = Occasion(
        family_id=boones.id,
        name="Christmas 2025",
        created_by_id=tom.id,
        is_archived=True,
    )
    # A second archived Christmas, so the Boones read as a family with history
    # rather than one that has just started: two past, one active.
    boones_two_years_ago = Occasion(
        family_id=boones.id,
        name="Christmas 2024",
        created_by_id=tom.id,
        is_archived=True,
    )
    extended_christmas = Occasion(
        family_id=extended.id, name="Christmas 2026", created_by_id=carol.id
    )
    extended_birthday = Occasion(
        family_id=extended.id, name="Gran's 80th", created_by_id=carol.id
    )
    # Two occasions gone quiet, so the archive nudge is reachable by hand — one
    # nudging and one snoozed, because suppression cannot be seen unless both
    # states are on screen at once and no occasion can be in both.
    #
    # Extended, and created by Tom, for two reasons. Every other family carries
    # a load-bearing fixture role: the Boones have exactly one active occasion
    # (the sharing control's single-click case) and Work Friends deliberately
    # has none (the disabled row), so adding to either destroys a fixture, while
    # Extended already has two and only becomes more several. And Tom is a plain
    # *member* of Extended — any member may create an occasion — so these
    # exercise the creator arm of the audience rule, and prove he can archive
    # them only because he made them.
    #
    # They get no shares at all: the simplest way to be stale, and the state
    # §5.1 says most needs action. `occasions.created_at` is a server default,
    # so the backdating has to be explicit — and if a share is ever added to
    # one, its own `created_at` must be backdated too or the occasion revives.
    extended_gone_quiet = Occasion(
        family_id=extended.id, name="Summer BBQ 2026", created_by_id=tom.id
    )
    extended_snoozed = Occasion(
        family_id=extended.id, name="Easter 2026", created_by_id=tom.id
    )
    db.add_all(
        [
            boones_christmas,
            boones_last_year,
            boones_two_years_ago,
            extended_christmas,
            extended_birthday,
            extended_gone_quiet,
            extended_snoozed,
        ]
    )
    db.flush()
    for occasion in (extended_gone_quiet, extended_snoozed):
        occasion.created_at = now - timedelta(days=90)
    db.flush()
    # Tom said "not yet" to one of them a fortnight ago, so it stays off his
    # banner for another fifteen days while its twin keeps nudging.
    db.add(
        OccasionArchivePrompt(
            user_id=tom.id,
            occasion_id=extended_snoozed.id,
            dismissed_until=now + timedelta(days=15),
        )
    )
    db.flush()

    # Occasion shares. Gran's and Dave's lists reach Tom *only* this way — they
    # are the lists that prove the occasion/direct split. Grandpa's reaches him
    # only through an archived occasion, which must not change that.
    db.add(ListOccasionShare(list_id=carol_wishlist.id, occasion_id=boones_christmas.id))
    db.add(ListOccasionShare(list_id=gran_list.id, occasion_id=boones_christmas.id))
    db.add(ListOccasionShare(list_id=grandpa_list.id, occasion_id=boones_last_year.id))
    db.add(ListOccasionShare(list_id=kitchen_list.id, occasion_id=boones_christmas.id))
    db.add(ListOccasionShare(list_id=tom_christmas.id, occasion_id=boones_christmas.id))
    db.add(ListOccasionShare(list_id=tom_christmas.id, occasion_id=extended_christmas.id))
    db.add(ListOccasionShare(list_id=dave_wishlist.id, occasion_id=extended_christmas.id))
    # All three Boones Christmases, which is what makes `suggested` narrow to
    # the active one while `claim_options` still offers the two past ones.
    for occasion in (boones_christmas, boones_last_year, boones_two_years_ago):
        db.add(ListOccasionShare(list_id=standing_list.id, occasion_id=occasion.id))

    # The filings, applied here because the claims above predate the occasions.
    # Every shopping tab needs something on it: Boone Christmas gets a purchase
    # with an amount, Extended Christmas one where he skipped it, and last
    # year's archived Christmas one that must still be served. Tom's claim on
    # Jane's list is deliberately left unfiled — a directly shared list belongs
    # to no occasion, and the folder tab is its only route (project spec §9.4).
    def file_under(gift_list, occasion, claimer=tom):
        gift_ids = select(Gift.id).where(Gift.list_id == gift_list.id)
        db.query(Claim).filter(
            Claim.gift_id.in_(gift_ids), Claim.user_id == claimer.id
        ).update({"occasion_id": occasion.id}, synchronize_session=False)

    file_under(carol_wishlist, boones_christmas)
    file_under(grandpa_list, boones_last_year)
    file_under(dave_wishlist, extended_christmas)
    # Carol's claim on Tom's own list, filed where it does the most good: Boone
    # Christmas is the card Tom reads, so a leak in the per-viewer clock shows
    # up on his strip rather than somewhere he would have to go looking.
    file_under(tom_christmas, boones_christmas, claimer=carol)

    christmas = Folder(owner_id=tom.id, name="Christmas 2026 Shopping",
                           description="Everyone I'm buying for")
    birthdays = Folder(owner_id=tom.id, name="Kids' Birthdays")
    db.add_all([christmas, birthdays])
    db.flush()
    for gift_list in (jane_wishlist, carol_wishlist, gran_list):
        db.add(FolderItem(folder_id=christmas.id, list_id=gift_list.id))
    db.add(FolderItem(folder_id=birthdays.id, list_id=beths_list.id))

    # Tom's budgets, chosen against the spends above so every state a budget
    # line can be in is on screen somewhere: under target, exactly at it, over
    # it, and — the one that matters most — a total that is honestly incomplete.
    # Every one is Tom's own; no other fixture user gets a budget, because a
    # second budget on the same occasion is only ever visible to its own owner.
    db.add_all([
        # Under: 64.99 of 100.00 spent, 35.01 left.
        Budget(user_id=tom.id, occasion_id=boones_christmas.id,
               amount=Decimal("100.00")),
        # Exactly at target: 42.00 of 42.00, nothing left and nothing overspent.
        Budget(user_id=tom.id, occasion_id=boones_last_year.id,
               amount=Decimal("42.00")),
        # Bought, but the amount was skipped: 0.00 of 25.00 spent with one
        # unpriced purchase, so the line must read as an understatement rather
        # than as an untouched budget.
        Budget(user_id=tom.id, occasion_id=extended_christmas.id,
               amount=Decimal("25.00")),
        # Over: the folder holds Carol's list, so 64.99 lands against 50.00 and
        # `remaining` goes negative. A budget is a target, not a limit.
        Budget(user_id=tom.id, folder_id=christmas.id, amount=Decimal("50.00")),
    ])

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
        print("Seeded 5 users, 11 lists, 3 families, 7 occasions, 2 folders.")
        print(f"Log in as any of: {', '.join(SEED_EMAILS)}")
        print(f"Password: {args.password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
