from fastapi import APIRouter, HTTPException, status

from app.dependencies import AdminUser, DbSession
from app.schemas.user import UserRead, UserUpdate
from app.services.exceptions import NotFoundError
from app.users import service as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(admin: AdminUser, db: DbSession):
    return user_service.list_users(db)


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
            db, user_id, updates.model_dump(exclude_unset=True)
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: AdminUser, db: DbSession):
    try:
        user_service.delete_user(db, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
