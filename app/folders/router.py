from fastapi import APIRouter, HTTPException, Query, status

from app.folders import service as folder_service
from app.dependencies import CurrentUser, DbSession, OwnedFolder
from app.schemas.budget import BudgetRollup, BudgetWrite
from app.schemas.claim import ShoppingPayload
from app.schemas.folder import (
    FolderCreate,
    FolderDetail,
    FolderItemCreate,
    FolderRead,
    FolderUpdate,
)
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
def create_folder(request: FolderCreate, user: CurrentUser, db: DbSession):
    return folder_service.create_folder(
        db, name=request.name, description=request.description, owner_id=user.id
    )


@router.get("", response_model=list[FolderRead])
def list_folders(user: CurrentUser, db: DbSession, archived: bool = Query(default=False)):
    return folder_service.list_folders(db, owner_id=user.id, archived=archived)


@router.get("/for-list/{list_id}", response_model=list[int])
def folders_for_list(list_id: int, user: CurrentUser, db: DbSession):
    return folder_service.get_folder_ids_for_list(db, list_id, user.id)


@router.get("/{folder_id}", response_model=FolderDetail)
def get_folder(folder: OwnedFolder, db: DbSession):
    return folder_service.get_folder_detail(db, folder)


@router.put("/{folder_id}", response_model=FolderRead)
def update_folder(
    request: FolderUpdate, folder: OwnedFolder, db: DbSession
):
    update_data = request.model_dump(exclude_unset=True)
    return folder_service.update_folder(db, folder, update_data)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder: OwnedFolder, db: DbSession):
    folder_service.delete_folder(db, folder)


@router.post(
    "/{folder_id}/items",
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    request: FolderItemCreate,
    folder: OwnedFolder,
    user: CurrentUser,
    db: DbSession,
):
    try:
        folder_service.add_item(
            db, folder=folder, list_id=request.list_id, user=user
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete(
    "/{folder_id}/items/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_item(list_id: int, folder: OwnedFolder, db: DbSession):
    try:
        folder_service.remove_item(db, folder=folder, list_id=list_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


# `OwnedFolder` is the whole access story here: a folder belongs to one user,
# so the caller is always reading their own claims.
@router.get("/{folder_id}/shopping", response_model=ShoppingPayload)
def get_shopping(folder: OwnedFolder, user: CurrentUser, db: DbSession):
    return folder_service.get_shopping(db, folder.id, user.id)


@router.put("/{folder_id}/budget", response_model=BudgetRollup)
def set_budget(
    request: BudgetWrite, folder: OwnedFolder, user: CurrentUser, db: DbSession
):
    return folder_service.set_budget(db, folder.id, user.id, request.amount)


# 200 with the rollup, not 204: the tab re-renders the same budget line with no
# target on it, and the counts beneath it are unchanged by the clearing.
@router.delete("/{folder_id}/budget", response_model=BudgetRollup)
def clear_budget(folder: OwnedFolder, user: CurrentUser, db: DbSession):
    try:
        return folder_service.clear_budget(db, folder.id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
