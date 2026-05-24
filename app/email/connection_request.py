from app.email.templates import render_email

_SUBJECT_TEMPLATE = "{sender_name} wants to connect with you on Boone Gifts"


def render_connection_request_email(
    *, sender_name: str, frontend_url: str
) -> tuple[str, str, str]:
    base = frontend_url.rstrip("/")
    link = f"{base}/connections"

    subject = _SUBJECT_TEMPLATE.format(sender_name=sender_name)

    body_html = (
        f"<p><strong>{sender_name}</strong> wants to connect with you on "
        "<strong>Boone Gifts</strong>.</p>"
        f'<p><a href="{link}">View and accept the request.</a></p>'
    )
    body_text = (
        f"{sender_name} wants to connect with you on Boone Gifts.\n\n"
        f"View and accept the request:\n{link}\n"
    )

    html, text = render_email(body_html, body_text)
    return subject, html, text
