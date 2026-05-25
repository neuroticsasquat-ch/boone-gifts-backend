from app.email.templates import render_email

_SUBJECT_TEMPLATE = "{sharer_name} shared a list with you on Boone Gifts"


def render_list_shared_email(
    *, sharer_name: str, list_name: str, list_url: str
) -> tuple[str, str, str]:
    subject = _SUBJECT_TEMPLATE.format(sharer_name=sharer_name)

    body_html = (
        f"<p><strong>{sharer_name}</strong> shared their list "
        f"&ldquo;<strong>{list_name}</strong>&rdquo; with you on "
        "<strong>Boone Gifts</strong>.</p>"
        f'<p><a href="{list_url}">View the list and start shopping.</a></p>'
    )
    body_text = (
        f'{sharer_name} shared their list "{list_name}" with you on Boone Gifts.\n\n'
        f"View the list and start shopping:\n{list_url}\n"
    )

    html, text = render_email(body_html, body_text)
    return subject, html, text
