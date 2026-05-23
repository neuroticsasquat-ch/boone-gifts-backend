from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.email import sender as email_sender
from app.email.templates import render_email


class TestRenderEmail:
    def test_html_wraps_body(self):
        html, _ = render_email(body_html="<p>Hello</p>", body_text="Hello")
        assert "<p>Hello</p>" in html
        assert "<html" in html.lower()
        assert "</html>" in html.lower()

    def test_text_includes_body(self):
        _, text = render_email(body_html="<p>Hello</p>", body_text="Hello there")
        assert "Hello there" in text

    def test_text_is_not_html(self):
        _, text = render_email(body_html="<p>Hello</p>", body_text="Hello")
        assert "<p>" not in text
        assert "<html" not in text.lower()


class TestSendEmailLogProvider:
    def test_log_provider_writes_to_logger(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "email_provider", "log")
        with patch.object(email_sender.logger, "info") as mock_info:
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        assert mock_info.called
        logged = " ".join(str(call) for call in mock_info.call_args_list)
        assert "user@test.com" in logged
        assert "Hi" in logged

    def test_log_provider_does_not_call_smtplib(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "email_provider", "log")
        with patch("smtplib.SMTP") as mock_smtp:
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        mock_smtp.assert_not_called()


class TestSendEmailSmtpProvider:
    def _configure_smtp(self, monkeypatch: pytest.MonkeyPatch, **overrides):
        defaults = {
            "email_provider": "smtp",
            "email_from": "Boone Gifts <noreply@test.com>",
            "email_smtp_host": "smtp.example.com",
            "email_smtp_port": 587,
            "email_smtp_username": "",
            "email_smtp_password": "",
            "email_smtp_use_tls": False,
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            monkeypatch.setattr(settings, k, v)

    def test_calls_smtp_with_host_and_port(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch)
        with patch("smtplib.SMTP") as mock_smtp:
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        mock_smtp.assert_called_once_with("smtp.example.com", 587)

    def test_sends_multipart_message_with_subject_and_recipients(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_smtp(monkeypatch)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Welcome",
                html="<p>Hi</p>",
                text="Hi",
            )
        instance.send_message.assert_called_once()
        msg = instance.send_message.call_args.args[0]
        assert msg["To"] == "user@test.com"
        assert msg["Subject"] == "Welcome"
        assert msg["From"] == "Boone Gifts <noreply@test.com>"

    def test_starttls_when_use_tls_true(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch, email_smtp_use_tls=True)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        instance.starttls.assert_called_once()

    def test_no_starttls_when_use_tls_false(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch, email_smtp_use_tls=False)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        instance.starttls.assert_not_called()

    def test_logs_in_when_credentials_set(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(
            monkeypatch, email_smtp_username="me", email_smtp_password="pw"
        )
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        instance.login.assert_called_once_with("me", "pw")

    def test_no_login_when_credentials_empty(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>Hi</p>",
                text="Hi",
            )
        instance.login.assert_not_called()

    def test_message_includes_both_html_and_text_alternatives(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_smtp(monkeypatch)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Hi",
                html="<p>HTML body</p>",
                text="TEXT body",
            )
        msg = instance.send_message.call_args.args[0]
        body = msg.as_string()
        assert "HTML body" in body
        assert "TEXT body" in body
