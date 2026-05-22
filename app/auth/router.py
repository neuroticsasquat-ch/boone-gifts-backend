from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.auth import service as auth_service
from app.config import settings
from app.dependencies import DbSession
from app.rate_limit import (
    forgot_password_limit,
    limiter,
    login_limit,
    refresh_limit,
    register_limit,
)
from app.schemas.auth import (
    AccessTokenResponse,
    ForgotPasswordRequest,
    GenericMessageResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.exceptions import BadRequestError, UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "boone_refresh_token"
REFRESH_COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/auth",
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path="/auth",
    )


@router.post("/login", response_model=AccessTokenResponse)
@limiter.limit(login_limit)
def login(request: Request, body: LoginRequest, response: Response, db: DbSession):
    try:
        tokens = auth_service.login(db, body.email, body.password)
    except UnauthorizedError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    set_refresh_cookie(response, tokens["refresh_token"])
    return AccessTokenResponse(access_token=tokens["access_token"])


@router.post("/register", response_model=AccessTokenResponse)
@limiter.limit(register_limit)
def register(request: Request, body: RegisterRequest, response: Response, db: DbSession):
    try:
        tokens = auth_service.register(
            db, body.token, body.name, body.password
        )
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    set_refresh_cookie(response, tokens["refresh_token"])
    return AccessTokenResponse(access_token=tokens["access_token"])


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit(refresh_limit)
def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    boone_refresh_token: str | None = Cookie(default=None),
):
    if boone_refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        tokens = auth_service.refresh(db, boone_refresh_token)
    except UnauthorizedError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    set_refresh_cookie(response, tokens["refresh_token"])
    return AccessTokenResponse(access_token=tokens["access_token"])


@router.post("/forgot-password", response_model=GenericMessageResponse)
@limiter.limit(forgot_password_limit)
def forgot_password(request: Request, body: ForgotPasswordRequest, db: DbSession):
    auth_service.forgot_password(db, body.email)
    return GenericMessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=GenericMessageResponse)
def reset_password(body: ResetPasswordRequest, db: DbSession):
    try:
        auth_service.reset_password(db, body.token, body.new_password)
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return GenericMessageResponse(message="Password updated.")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    delete_refresh_cookie(response)
