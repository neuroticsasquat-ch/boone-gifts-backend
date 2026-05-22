from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)


def login_limit() -> str:
    return settings.rate_limit_login


def register_limit() -> str:
    return settings.rate_limit_register


def refresh_limit() -> str:
    return settings.rate_limit_refresh


def forgot_password_limit() -> str:
    return settings.rate_limit_forgot_password


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    try:
        item = exc.limit.limit
        retry_after = item.multiples * item.GRANULARITY.seconds
    except AttributeError:
        retry_after = 60

    response = JSONResponse(
        {"detail": f"Rate limit exceeded: {exc.detail}"},
        status_code=429,
    )
    response.headers["Retry-After"] = str(retry_after)
    return response
