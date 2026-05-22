from datetime import datetime, timedelta, timezone

from app.email.password_reset import render_password_reset_email


class TestRenderPasswordResetEmail:
    def test_subject_is_set(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        subject, _html, _text = render_password_reset_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert subject
        assert "password" in subject.lower()

    def test_html_contains_reset_link_with_token(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        _subject, html, _text = render_password_reset_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "https://boone-gifts.example/reset-password?token=abc-123" in html

    def test_text_contains_reset_link_with_token(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        _subject, _html, text = render_password_reset_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "https://boone-gifts.example/reset-password?token=abc-123" in text

    def test_mentions_expiry(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        _subject, html, text = render_password_reset_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "1 hour" in html.lower() or "hour" in html.lower()
        assert "hour" in text.lower()

    def test_trailing_slash_in_frontend_url_is_handled(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        _subject, html, _text = render_password_reset_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example/",
        )
        assert "//reset-password" not in html
