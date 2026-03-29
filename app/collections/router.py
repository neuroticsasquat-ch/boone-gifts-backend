from fastapi import APIRouter, HTTPException, status

from app.collections import service as collection_service
from app.dependencies import CurrentUser, DbSession, OwnedCollection
from app.schemas.collection import (
    CollectionCreate,
    CollectionDetail,
    CollectionItemCreate,
    CollectionRead,
    CollectionUpdate,
)
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(request: CollectionCreate, user: CurrentUser, db: DbSession):
    return collection_service.create_collection(
        db, name=request.name, description=request.description, owner_id=user.id
    )


@router.get("", response_model=list[CollectionRead])
def list_collections(user: CurrentUser, db: DbSession):
    return collection_service.list_collections(db, owner_id=user.id)


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_collection(collection: OwnedCollection, db: DbSession):
    return collection_service.get_collection_detail(db, collection)


@router.put("/{collection_id}", response_model=CollectionRead)
def update_collection(
    request: CollectionUpdate, collection: OwnedCollection, db: DbSession
):
    update_data = request.model_dump(exclude_unset=True)
    return collection_service.update_collection(db, collection, update_data)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection: OwnedCollection, db: DbSession):
    collection_service.delete_collection(db, collection)


@router.post(
    "/{collection_id}/items",
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    request: CollectionItemCreate,
    collection: OwnedCollection,
    user: CurrentUser,
    db: DbSession,
):
    try:
        collection_service.add_item(
            db, collection=collection, list_id=request.list_id, user_id=user.id
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete(
    "/{collection_id}/items/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_item(list_id: int, collection: OwnedCollection, db: DbSession):
    try:
        collection_service.remove_item(db, collection=collection, list_id=list_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
