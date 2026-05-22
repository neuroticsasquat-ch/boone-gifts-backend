from datetime import datetime

from app.email.templates import render_email

_SUBJECT = "You're invited to Boone Gifts"


def render_invite_email(
    *, token: str, expires_at: datetime, frontend_url: str
) -> tuple[str, str, str]:
    base = frontend_url.rstrip("/")
    link = f"{base}/register?token={token}"
    expires = expires_at.strftime("%B %d, %Y")

    body_html = (
        "<p>You've been invited to <strong>Boone Gifts</strong>, a place to share "
        "wishlists and pick out presents for the people you care about.</p>"
        f'<p><a href="{link}">Accept your invite and create your account.</a></p>'
        f"<p>This invite expires on {expires}.</p>"
        f'<p style="font-size: 0.85em; color: #888;">If the link above doesn\'t work, '
        f"paste this into your browser:<br/>{link}</p>"
    )
    body_text = (
        "You've been invited to Boone Gifts, a place to share wishlists and pick out "
        "presents for the people you care about.\n\n"
        f"Accept your invite and create your account:\n{link}\n\n"
        f"This invite expires on {expires}.\n"
    )

    html, text = render_email(body_html, body_text)
    return _SUBJECT, html, text
