"""POST /debug/raise-test-error — the deliberate error that proves the reporting path."""

import pytest

from app.debug.router import TelemetryTestError


def test_admin_trigger_raises_the_test_error(client, admin_headers):
    # TestClient re-raises server exceptions, so the 500 a real client sees surfaces here
    # as the exception Sentry's FastAPI integration captures.
    with pytest.raises(TelemetryTestError, match="boone-gifts.debug.raise-test-error"):
        client.post("/debug/raise-test-error", headers=admin_headers)


def test_member_is_forbidden(client, member_headers):
    response = client.post("/debug/raise-test-error", headers=member_headers)
    assert response.status_code == 403


def test_anonymous_is_unauthorized(client):
    response = client.post("/debug/raise-test-error")
    assert response.status_code == 401
