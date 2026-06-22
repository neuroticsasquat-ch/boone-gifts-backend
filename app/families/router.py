from fastapi import APIRouter, HTTPException, status

from app.families import service as family_service
from app.dependencies import CurrentUser, DbSession
from app.schemas.family import FamilyCreate, FamilyDetail, FamilyRead, FamilyUpdate
from app.services.exceptions import ForbiddenError, NotFoundError

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", response_model=FamilyDetail, status_code=status.HTTP_201_CREATED)
def create_family(request: FamilyCreate, user: CurrentUser, db: DbSession) -> dict:
    return family_service.create_family(db, name=request.name, creator_id=user.id)


@router.get("", response_model=list[FamilyRead])
def list_families(user: CurrentUser, db: DbSession) -> list[dict]:
    return family_service.list_families(db, user_id=user.id)


@router.get("/{family_id}", response_model=FamilyDetail)
def get_family(family_id: int, user: CurrentUser, db: DbSession) -> dict:
    try:
        return family_service.get_family_detail(db, family_id=family_id, user_id=user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.put("/{family_id}", response_model=FamilyDetail)
def rename_family(
    family_id: int, request: FamilyUpdate, user: CurrentUser, db: DbSession
) -> dict:
    try:
        return family_service.rename_family(
            db, family_id=family_id, user_id=user.id, name=request.name
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(family_id: int, user: CurrentUser, db: DbSession) -> None:
    try:
        family_service.delete_family(db, family_id=family_id, user_id=user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
