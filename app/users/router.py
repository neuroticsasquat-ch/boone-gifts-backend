from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.schemas.user import UserRead, UserSearchResult, UserUpdate
from app.services.exceptions import BadRequestError, NotFoundError
from app.users import service as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(admin: AdminUser, db: DbSession):
    return user_service.list_users(db)


@router.get("/search", response_model=list[UserSearchResult])
def search_users(
    user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=2),
):
    return user_service.search_users(db, q, current_user_id=user.id)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, admin: AdminUser, db: DbSession):
    try:
        return user_service.get_user(db, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, updates: UserUpdate, admin: AdminUser, db: DbSession):
    try:
        return user_service.update_user(
            db, user_id, updates.model_dump(exclude_unset=True),
            current_user_id=admin.id,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    admin: AdminUser,
    db: DbSession,
    purge: bool = Query(default=False),
):
    try:
        user_service.delete_user(
            db, user_id, current_user_id=admin.id, purge=purge
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
