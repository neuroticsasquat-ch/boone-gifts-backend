from unittest.mock import patch

import httpx
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
            "email_reply_to": "",
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

    def test_sets_reply_to_when_configured(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch, email_reply_to="Boone Gifts <hello@test.com>")
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Welcome",
                html="<p>Hi</p>",
                text="Hi",
            )
        msg = instance.send_message.call_args.args[0]
        assert msg["Reply-To"] == "Boone Gifts <hello@test.com>"
        assert msg["From"] == "Boone Gifts <noreply@test.com>"
        assert msg["To"] == "user@test.com"
        assert msg["Subject"] == "Welcome"

    def test_omits_reply_to_when_empty(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_smtp(monkeypatch)
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            email_sender.send_email(
                to="user@test.com",
                subject="Welcome",
                html="<p>Hi</p>",
                text="Hi",
            )
        msg = instance.send_message.call_args.args[0]
        assert msg["Reply-To"] is None

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


class TestSendEmailResendProvider:
    def _configure_resend(self, monkeypatch: pytest.MonkeyPatch, **overrides):
        defaults = {
            "email_provider": "resend",
            "email_from": "Boone Gifts <noreply@mail.test.com>",
            "email_reply_to": "",
            "resend_api_key": "re_test_key",
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            monkeypatch.setattr(settings, k, v)

    def _send(self):
        email_sender.send_email(
            to="user@test.com",
            subject="Welcome",
            html="<p>HTML body</p>",
            text="TEXT body",
        )

    def test_posts_to_resend_with_bearer_token_and_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_resend(monkeypatch)
        with patch("app.email.sender.httpx.Client") as mock_client:
            instance = mock_client.return_value.__enter__.return_value
            instance.post.return_value = httpx.Response(200, json={"id": "abc"})
            self._send()
        url = instance.post.call_args.args[0]
        kwargs = instance.post.call_args.kwargs
        assert url == "https://api.resend.com/emails"
        assert kwargs["headers"]["Authorization"] == "Bearer re_test_key"
        assert kwargs["json"] == {
            "from": "Boone Gifts <noreply@mail.test.com>",
            "to": ["user@test.com"],
            "subject": "Welcome",
            "html": "<p>HTML body</p>",
            "text": "TEXT body",
        }

    def test_includes_reply_to_when_configured(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_resend(monkeypatch, email_reply_to="hello@test.com")
        with patch("app.email.sender.httpx.Client") as mock_client:
            instance = mock_client.return_value.__enter__.return_value
            instance.post.return_value = httpx.Response(200, json={"id": "abc"})
            self._send()
        assert instance.post.call_args.kwargs["json"]["reply_to"] == "hello@test.com"

    def test_omits_reply_to_when_empty(self, monkeypatch: pytest.MonkeyPatch):
        self._configure_resend(monkeypatch)
        with patch("app.email.sender.httpx.Client") as mock_client:
            instance = mock_client.return_value.__enter__.return_value
            instance.post.return_value = httpx.Response(200, json={"id": "abc"})
            self._send()
        assert "reply_to" not in instance.post.call_args.kwargs["json"]

    @pytest.mark.parametrize("status", [400, 422, 500, 503])
    def test_http_error_raises_email_send_error(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ):
        self._configure_resend(monkeypatch)
        with patch("app.email.sender.httpx.Client") as mock_client:
            instance = mock_client.return_value.__enter__.return_value
            instance.post.return_value = httpx.Response(
                status, json={"message": "nope"}
            )
            with pytest.raises(email_sender.EmailSendError) as exc_info:
                self._send()
        assert str(status) in str(exc_info.value)

    def test_transport_error_raises_email_send_error(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_resend(monkeypatch)
        with patch("app.email.sender.httpx.Client") as mock_client:
            instance = mock_client.return_value.__enter__.return_value
            instance.post.side_effect = httpx.ConnectError("connection refused")
            with pytest.raises(email_sender.EmailSendError):
                self._send()

    def test_missing_api_key_raises_without_calling_resend(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_resend(monkeypatch, resend_api_key="")
        with (
            patch("app.email.sender.httpx.Client") as mock_client,
            pytest.raises(email_sender.EmailSendError),
        ):
            self._send()
        mock_client.assert_not_called()

    def test_resend_provider_does_not_call_smtplib(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        self._configure_resend(monkeypatch)
        with (
            patch("smtplib.SMTP") as mock_smtp,
            patch("app.email.sender.httpx.Client") as mock_client,
        ):
            instance = mock_client.return_value.__enter__.return_value
            instance.post.return_value = httpx.Response(200, json={"id": "abc"})
            self._send()
        mock_smtp.assert_not_called()
