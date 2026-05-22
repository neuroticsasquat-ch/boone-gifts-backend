_HTML_LAYOUT = """\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Boone Gifts</title>
  </head>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 2em auto; color: #222;">
    <div style="padding: 1.5em; border: 1px solid #eee; border-radius: 6px;">
      {body}
      <hr style="border: none; border-top: 1px solid #eee; margin: 2em 0 1em;" />
      <p style="font-size: 0.85em; color: #888;">Boone Gifts</p>
    </div>
  </body>
</html>
"""

_TEXT_FOOTER = "\n\n--\nBoone Gifts\n"


def render_email(body_html: str, body_text: str) -> tuple[str, str]:
    html = _HTML_LAYOUT.format(body=body_html)
    text = body_text + _TEXT_FOOTER
    return html, text
