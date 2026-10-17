from fastapi import APIRouter

from app.dependencies import AdminUser

router = APIRouter(prefix="/debug", tags=["debug"])


class TelemetryTestError(RuntimeError):
    """Raised on purpose, so it groups as its own issue and never with a real failure."""


@router.post("/raise-test-error")
def raise_test_error(admin: AdminUser) -> None:
    raise TelemetryTestError(
        "boone-gifts.debug.raise-test-error: deliberate test error"
    )
