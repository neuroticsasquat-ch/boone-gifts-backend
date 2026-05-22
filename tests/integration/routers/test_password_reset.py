from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.password_reset_token import PasswordResetToken


@pytest.fixture
def small_forgot_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "rate_limit_forgot_password", "100/minute")


@pytest.fixture
def captured_emails():
    sent = []

    def fake_send(*, to, subject, html, text):
        sent.append({"to": to, "subject": subject, "html": html, "text": text})

    with patch("app.auth.service.send_email", side_effect=fake_send):
        yield sent


class TestForgotPassword:
    def test_unknown_email_returns_200_and_sends_nothing(
        self, client, captured_emails, small_forgot_limit
    ):
        response = client.post(
            "/auth/forgot-password", json={"email": "nobody@test.com"}
        )
        assert response.status_code == 200
        assert captured_emails == []

    def test_known_email_returns_200_and_sends_reset_email(
        self, client, db, member_user, captured_emails, small_forgot_limit
    ):
        response = client.post(
            "/auth/forgot-password", json={"email": "member@test.com"}
        )
        assert response.status_code == 200
        assert len(captured_emails) == 1
        sent = captured_emails[0]
        assert sent["to"] == "member@test.com"
        assert "/reset-password?token=" in sent["text"]

    def test_known_email_persists_token_hash(
        self, client, db, member_user, captured_emails, small_forgot_limit
    ):
        client.post("/auth/forgot-password", json={"email": "member@test.com"})

        tokens = db.query(PasswordResetToken).filter_by(user_id=member_user.id).all()
        assert len(tokens) == 1
        assert tokens[0].token_hash
        expires_at = tokens[0].expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        assert expires_at > datetime.now(timezone.utc)


class TestResetPassword:
    def _request_reset(self, client, captured_emails, email: str) -> str:
        client.post("/auth/forgot-password", json={"email": email})
        text = captured_emails[-1]["text"]
        marker = "?token="
        start = text.index(marker) + len(marker)
        end = text.index("\n", start)
        return text[start:end].strip()

    def test_valid_token_updates_password(
        self, client, db, member_user, captured_emails, small_forgot_limit
    ):
        token = self._request_reset(client, captured_emails, "member@test.com")

        response = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "brand-new-password"},
        )
        assert response.status_code == 200

        login = client.post(
            "/auth/login",
            json={"email": "member@test.com", "password": "brand-new-password"},
        )
        assert login.status_code == 200

    def test_invalid_token_returns_400(self, client, member_user, small_forgot_limit):
        response = client.post(
            "/auth/reset-password",
            json={"token": "not-a-real-token", "new_password": "whatever-1234"},
        )
        assert response.status_code == 400

    def test_expired_token_returns_400(
        self, client, db, member_user, small_forgot_limit
    ):
        from app.auth.service import _hash_reset_token

        raw = "expired-raw-token"
        db.add(
            PasswordResetToken(
                user_id=member_user.id,
                token_hash=_hash_reset_token(raw),
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        db.flush()

        response = client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "whatever-1234"},
        )
        assert response.status_code == 400

    def test_reused_token_returns_400(
        self, client, db, member_user, captured_emails, small_forgot_limit
    ):
        token = self._request_reset(client, captured_emails, "member@test.com")

        first = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "brand-new-password"},
        )
        assert first.status_code == 200

        second = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "another-password"},
        )
        assert second.status_code == 400

    def test_reset_invalidates_existing_refresh_tokens(
        self, client, db, member_user, captured_emails, small_forgot_limit
    ):
        login = client.post(
            "/auth/login",
            json={"email": "member@test.com", "password": "member123"},
        )
        assert login.status_code == 200
        client.cookies.set("boone_refresh_token", login.cookies["boone_refresh_token"])

        token = self._request_reset(client, captured_emails, "member@test.com")
        reset = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "brand-new-password"},
        )
        assert reset.status_code == 200

        refresh = client.post("/auth/refresh")
        assert refresh.status_code == 401


class TestForgotPasswordRateLimit:
    def test_returns_429_after_limit(self, client, monkeypatch):
        monkeypatch.setattr(settings, "rate_limit_forgot_password", "2/minute")

        for _ in range(2):
            response = client.post(
                "/auth/forgot-password", json={"email": "nobody@test.com"}
            )
            assert response.status_code == 200

        response = client.post(
            "/auth/forgot-password", json={"email": "nobody@test.com"}
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers
