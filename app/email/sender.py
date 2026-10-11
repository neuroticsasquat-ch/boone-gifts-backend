import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_RESEND_TIMEOUT_SECONDS = 10.0


class EmailSendError(RuntimeError):
    """The configured provider could not deliver the message."""


def send_email(*, to: str, subject: str, html: str, text: str) -> None:
    if settings.email_provider == "smtp":
        _send_via_smtp(to=to, subject=subject, html=html, text=text)
    elif settings.email_provider == "resend":
        _send_via_resend(to=to, subject=subject, html=html, text=text)
    else:
        _send_via_log(to=to, subject=subject, html=html, text=text)


def _send_via_log(*, to: str, subject: str, html: str, text: str) -> None:
    logger.info(
        "[email:log] to=%s subject=%r\n%s",
        to,
        subject,
        text,
    )


def _send_via_smtp(*, to: str, subject: str, html: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    if settings.email_reply_to:
        msg["Reply-To"] = settings.email_reply_to
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port) as smtp:
        if settings.email_smtp_use_tls:
            smtp.starttls()
        if settings.email_smtp_username and settings.email_smtp_password:
            smtp.login(settings.email_smtp_username, settings.email_smtp_password)
        smtp.send_message(msg)


def _send_via_resend(*, to: str, subject: str, html: str, text: str) -> None:
    if not settings.resend_api_key:
        raise EmailSendError("APP_RESEND_API_KEY is not set")

    payload: dict[str, object] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if settings.email_reply_to:
        payload["reply_to"] = settings.email_reply_to

    try:
        with httpx.Client(timeout=_RESEND_TIMEOUT_SECONDS) as client:
            resp = client.post(
                _RESEND_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
    except httpx.HTTPError as e:
        logger.warning("resend transport error: %s", e)
        raise EmailSendError(f"resend transport error: {e}") from e

    if resp.status_code >= 400:
        logger.warning("resend returned HTTP %s: %s", resp.status_code, resp.text[:500])
        raise EmailSendError(
            f"resend returned HTTP {resp.status_code}: {resp.text[:200]}"
        )
