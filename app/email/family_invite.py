from datetime import datetime

from app.email.templates import render_email

_SUBJECT = "You're invited to a family on Boone Gifts"


def render_family_invite_email(
    *,
    family_name: str,
    inviter_name: str,
    token: str,
    expires_at: datetime,
    frontend_url: str,
    is_new_user: bool,
) -> tuple[str, str, str]:
    base = frontend_url.rstrip("/")
    expires = expires_at.strftime("%B %d, %Y")

    if is_new_user:
        link = f"{base}/register?family_invite={token}"
        action_html = (
            f'<p><a href="{link}">Create your account and join '
            f"the {family_name} family.</a></p>"
        )
        action_text = f"Create your account and join the {family_name} family:\n{link}\n"
    else:
        link = f"{base}/family-invites/{token}"
        action_html = (
            f'<p><a href="{link}">Accept your invite to '
            f"the {family_name} family.</a></p>"
        )
        action_text = f"Accept your invite to the {family_name} family:\n{link}\n"

    body_html = (
        f"<p><strong>{inviter_name}</strong> invited you to join the "
        f"<strong>{family_name}</strong> family on Boone Gifts, where members "
        "automatically share gift lists with each other.</p>"
        f"{action_html}"
        f"<p>This invite expires on {expires}.</p>"
        f'<p style="font-size: 0.85em; color: #888;">If the link above doesn\'t work, '
        f"paste this into your browser:<br/>{link}</p>"
    )
    body_text = (
        f"{inviter_name} invited you to join the {family_name} family on Boone Gifts, "
        "where members automatically share gift lists with each other.\n\n"
        f"{action_text}\n"
        f"This invite expires on {expires}.\n"
    )

    html, text = render_email(body_html, body_text)
    return _SUBJECT, html, text
