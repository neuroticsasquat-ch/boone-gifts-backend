from fastapi import APIRouter, HTTPException, Query, status

from app.folders import service as folder_service
from app.dependencies import CurrentUser, DbSession, OwnedFolder
from app.schemas.folder import (
    FolderCreate,
    FolderDetail,
    FolderItemCreate,
    FolderRead,
    FolderUpdate,
    ShoppingListItem,
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


@router.get("/{folder_id}/shopping-list", response_model=list[ShoppingListItem])
def get_shopping_list(folder: OwnedFolder, user: CurrentUser, db: DbSession):
    return folder_service.get_shopping_list(db, folder.id, user.id)
