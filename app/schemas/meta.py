from pydantic import BaseModel


class UrlMetaResponse(BaseModel):
    title: str | None = None
    description: str | None = None
    price: str | None = None
    image: str | None = None
