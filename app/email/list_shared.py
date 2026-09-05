from app.email.templates import render_email

_SUBJECT_TEMPLATE = "{sharer_name} shared a list with you on Boone Gifts"


def render_list_shared_email(
    *,
    sharer_name: str,
    list_name: str,
    list_url: str,
    recipient_name: str | None = None,
) -> tuple[str, str, str]:
    # The subject is unchanged either way: it is the sharer doing the sharing.
    subject = _SUBJECT_TEMPLATE.format(sharer_name=sharer_name)

    possessive_html = (
        f"<strong>{recipient_name}&rsquo;s</strong> list"
        if recipient_name
        else "their list"
    )
    possessive_text = f"{recipient_name}'s list" if recipient_name else "their list"

    body_html = (
        f"<p><strong>{sharer_name}</strong> shared {possessive_html} "
        f"&ldquo;<strong>{list_name}</strong>&rdquo; with you on "
        "<strong>Boone Gifts</strong>.</p>"
        f'<p><a href="{list_url}">View the list and start shopping.</a></p>'
    )
    body_text = (
        f'{sharer_name} shared {possessive_text} "{list_name}" with you on '
        "Boone Gifts.\n\n"
        f"View the list and start shopping:\n{list_url}\n"
    )

    html, text = render_email(body_html, body_text)
    return subject, html, text
