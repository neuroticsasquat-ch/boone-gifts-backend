import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.email import send_email
from app.email.invite import render_invite_email
from app.invites import repository as repo
from app.models.invite import Invite
from app.services.exceptions import NotFoundError

logger = logging.getLogger(__name__)


def create_invite(
    db: Session,
    email: str,
    role: str,
    expires_in_days: int,
    invited_by_id: int,
) -> Invite:
    invite = repo.create_invite(db, email, role, expires_in_days, invited_by_id)
    _send_invite_email(invite)
    return invite


def list_invites(db: Session) -> list[Invite]:
    return repo.get_all_invites(db)


def delete_invite(db: Session, invite_id: int) -> None:
    invite = repo.find_invite_by_id(db, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found.")
    repo.delete_invite(db, invite)


def _send_invite_email(invite: Invite) -> None:
    subject, html, text = render_invite_email(
        token=invite.token,
        expires_at=invite.expires_at,
        frontend_url=settings.frontend_url,
    )
    try:
        send_email(to=invite.email, subject=subject, html=html, text=text)
    except Exception:
        logger.exception("Failed to send invite email to %s", invite.email)
