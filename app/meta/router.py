from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser
from app.meta import service as meta_service
from app.schemas.meta import UrlMetaResponse
from app.services.exceptions import BadRequestError

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("", response_model=UrlMetaResponse)
def get_url_meta(user: CurrentUser, url: str = Query(...)) -> UrlMetaResponse:
    try:
        return meta_service.get_url_meta(url)
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
