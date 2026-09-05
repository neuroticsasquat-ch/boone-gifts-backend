import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.email import send_email
from app.email.family_invite import render_family_invite_email
from app.families import repository as families_repo
from app.family_invites import repository as repo
from app.list_families import service as list_family_service
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)

INVITE_EXPIRY_DAYS = 7


def _require_organizer(db: Session, family_id: int, actor: User) -> tuple[Family, FamilyMember]:
    family = families_repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    membership = families_repo.get_family_member(db, family_id=family_id, user_id=actor.id)
    if membership is None:
        raise ForbiddenError("Not a member of this family.")
    if membership.role != "organizer":
        raise ForbiddenError("Only organizers can manage invites.")
    return family, membership


def _is_expired(expires_at: datetime) -> bool:
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return expires_at < now


def _require_recipient(invite: FamilyInvite, actor: User) -> None:
    if invite.email != actor.email.strip().lower():
        raise ForbiddenError("This invite is addressed to a different account.")


def _require_pending(invite: FamilyInvite) -> None:
    if invite.accepted_at is not None:
        raise ConflictError("This invite has already been accepted.")
    if invite.declined_at is not None:
        raise ConflictError("This invite has already been declined.")
    if _is_expired(invite.expires_at):
        raise ConflictError("This invite has expired.")


def create_invite(
    db: Session,
    family_id: int,
    actor: User,
    email: str,
    role: str,
    simple_mode: bool,
) -> FamilyInvite:
    family, _ = _require_organizer(db, family_id, actor)

    existing_user = repo.find_user_by_email(db, email)
    if existing_user is not None:
        member = families_repo.get_family_member(
            db, family_id=family_id, user_id=existing_user.id
        )
        if member is not None:
            raise ConflictError("Already a member of this family.")

    dup = repo.find_unaccepted_invite_by_email(db, family_id, email)
    if dup is not None:
        if not _is_expired(dup.expires_at):
            raise ConflictError("An invite is already pending for this email.")
        repo.delete_invite(db, dup)

    invite = repo.create_invite(
        db,
        family_id=family_id,
        email=email,
        role=role,
        simple_mode=simple_mode,
        token=str(uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_EXPIRY_DAYS),
        invited_by_id=actor.id,
    )

    _send_invite_email(
        invite,
        family_name=family.name,
        inviter_name=actor.name,
        is_new_user=existing_user is None,
    )
    return invite


def _send_invite_email(
    invite: FamilyInvite, *, family_name: str, inviter_name: str, is_new_user: bool
) -> None:
    subject, html, text = render_family_invite_email(
        family_name=family_name,
        inviter_name=inviter_name,
        token=invite.token,
        expires_at=invite.expires_at,
        frontend_url=settings.frontend_url,
        is_new_user=is_new_user,
    )
    try:
        send_email(to=invite.email, subject=subject, html=html, text=text)
    except Exception:
        logger.exception("Failed to send family invite email to %s", invite.email)


def list_invites(db: Session, family_id: int, actor: User) -> list[FamilyInvite]:
    _require_organizer(db, family_id, actor)
    return repo.list_pending_invites(db, family_id)


def revoke_invite(db: Session, family_id: int, invite_id: int, actor: User) -> None:
    _require_organizer(db, family_id, actor)
    invite = repo.get_invite(db, invite_id)
    if invite is None or invite.family_id != family_id:
        raise NotFoundError("Invite not found.")
    if invite.accepted_at is not None:
        raise ConflictError("Cannot revoke an accepted invite.")
    if invite.declined_at is not None:
        raise ConflictError("Cannot revoke a declined invite.")
    repo.delete_invite(db, invite)


def decline_invite(db: Session, token: str, actor: User) -> None:
    invite = repo.get_invite_by_token(db, token)
    if invite is None:
        raise NotFoundError("Invite not found.")
    _require_recipient(invite, actor)
    _require_pending(invite)
    invite.declined_at = datetime.now(timezone.utc)
    db.flush()


def list_incoming_invites(db: Session, actor: User) -> list[dict]:
    email = actor.email.strip().lower()
    rows = repo.list_incoming_invites(db, email)
    return [
        {
            "id": invite.id,
            "token": invite.token,
            "role": invite.role,
            "expires_at": invite.expires_at,
            "created_at": invite.created_at,
            "family": {"id": family.id, "name": family.name},
            "invited_by": {"id": inviter.id, "name": inviter.name},
        }
        for invite, family, inviter in rows
        if not _is_expired(invite.expires_at)
    ]


def accept_invite(db: Session, token: str, actor: User) -> dict:
    invite = repo.get_invite_by_token(db, token)
    if invite is None:
        raise NotFoundError("Invite not found.")
    _require_recipient(invite, actor)
    _require_pending(invite)
    if families_repo.get_family_member(
        db, family_id=invite.family_id, user_id=actor.id
    ) is not None:
        raise ConflictError("Already a member of this family.")
    families_repo.create_family_member(
        db, family_id=invite.family_id, user_id=actor.id, role=invite.role
    )
    list_family_service.grant_existing_lists_on_join(db, actor, invite.family_id)
    invite.accepted_at = datetime.now(timezone.utc)
    db.flush()
    family = families_repo.get_family(db, invite.family_id)
    return {"family": {"id": family.id, "name": family.name}, "role": invite.role}
