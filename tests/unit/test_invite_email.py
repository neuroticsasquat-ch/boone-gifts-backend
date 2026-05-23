from datetime import datetime, timedelta, timezone

from app.email.invite import render_invite_email


class TestRenderInviteEmail:
    def test_subject_is_set(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        subject, _html, _text = render_invite_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert subject
        assert "Boone Gifts" in subject

    def test_html_contains_registration_link_with_token(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        _subject, html, _text = render_invite_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "https://boone-gifts.example/register?token=abc-123" in html

    def test_text_contains_registration_link_with_token(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        _subject, _html, text = render_invite_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "https://boone-gifts.example/register?token=abc-123" in text

    def test_mentions_expiry(self):
        expires = datetime(2026, 6, 1, tzinfo=timezone.utc)
        _subject, html, text = render_invite_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example",
        )
        assert "2026" in html
        assert "2026" in text

    def test_trailing_slash_in_frontend_url_does_not_produce_double_slash(self):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        _subject, html, _text = render_invite_email(
            token="abc-123",
            expires_at=expires,
            frontend_url="https://boone-gifts.example/",
        )
        assert "https://boone-gifts.example/register?token=abc-123" in html
        assert "//register" not in html
