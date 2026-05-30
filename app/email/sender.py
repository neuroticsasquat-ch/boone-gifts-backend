import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(*, to: str, subject: str, html: str, text: str) -> None:
    if settings.email_provider == "smtp":
        _send_via_smtp(to=to, subject=subject, html=html, text=text)
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
