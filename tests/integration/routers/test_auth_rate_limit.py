import pytest

from app.config import settings


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch):
    """Shrink the rate limits so tests don't have to fire dozens of requests."""
    monkeypatch.setattr(settings, "rate_limit_login", "3/minute")
    monkeypatch.setattr(settings, "rate_limit_register", "3/minute")
    monkeypatch.setattr(settings, "rate_limit_refresh", "3/minute")


def test_login_returns_429_when_rate_limited(client, small_limits):
    payload = {"email": "nobody@test.com", "password": "x"}

    for _ in range(3):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 401, response.text

    response = client.post("/auth/login", json=payload)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_register_returns_429_when_rate_limited(client, small_limits):
    payload = {"token": "invalid-token", "name": "x", "password": "password123"}

    for _ in range(3):
        response = client.post("/auth/register", json=payload)
        assert response.status_code == 400, response.text

    response = client.post("/auth/register", json=payload)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_refresh_returns_429_when_rate_limited(client, small_limits):
    for _ in range(3):
        response = client.post("/auth/refresh")
        assert response.status_code == 401, response.text

    response = client.post("/auth/refresh")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_per_endpoint_limits_are_independent(client, small_limits):
    payload = {"email": "nobody@test.com", "password": "x"}

    for _ in range(3):
        client.post("/auth/login", json=payload)
    login_response = client.post("/auth/login", json=payload)
    assert login_response.status_code == 429

    register_response = client.post(
        "/auth/register",
        json={"token": "invalid", "name": "x", "password": "password123"},
    )
    assert register_response.status_code != 429


def test_rate_limit_disabled_when_setting_off(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_login", "1/minute")
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    from app.main import app
    monkeypatch.setattr(app.state.limiter, "enabled", False)

    payload = {"email": "nobody@test.com", "password": "x"}
    for _ in range(5):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 401, response.text
