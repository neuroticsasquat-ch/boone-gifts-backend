from datetime import datetime

from app.email.templates import render_email

_SUBJECT = "Reset your Boone Gifts password"


def render_password_reset_email(
    *, token: str, expires_at: datetime, frontend_url: str
) -> tuple[str, str, str]:
    base = frontend_url.rstrip("/")
    link = f"{base}/reset-password?token={token}"

    body_html = (
        "<p>We received a request to reset your <strong>Boone Gifts</strong> password.</p>"
        f'<p><a href="{link}">Click here to set a new password.</a></p>'
        "<p>This link will expire in 1 hour. If you didn't request a reset, you can "
        "ignore this email — your password won't change.</p>"
        f'<p style="font-size: 0.85em; color: #888;">If the link above doesn\'t work, '
        f"paste this into your browser:<br/>{link}</p>"
    )
    body_text = (
        "We received a request to reset your Boone Gifts password.\n\n"
        f"Set a new password:\n{link}\n\n"
        "This link will expire in 1 hour. If you didn't request a reset, you can ignore "
        "this email — your password won't change.\n"
    )

    html, text = render_email(body_html, body_text)
    return _SUBJECT, html, text
