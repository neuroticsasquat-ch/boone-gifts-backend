import ipaddress
import logging
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.schemas.meta import UrlMetaResponse
from app.services.exceptions import BadRequestError

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_TIMEOUT = 10.0
_LINKPREVIEW_URL = "https://api.linkpreview.net/"

# Private/reserved IP networks to block (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]


class _StopParsing(Exception):
    pass


class _MetaParser(HTMLParser):
    """Parses <head> for meta tags and <title>."""

    def __init__(self):
        super().__init__()
        self.og: dict[str, str] = {}
        self.meta_name: dict[str, str] = {}
        self.title_text: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
            self._title_parts = []
            return

        if tag == "meta":
            attr_dict = {k.lower(): v for k, v in attrs if v is not None}
            content = attr_dict.get("content")
            if content is None:
                return

            prop = attr_dict.get("property", "").lower()
            if prop:
                self.og[prop] = content

            name = attr_dict.get("name", "").lower()
            if name:
                self.meta_name[name] = content

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title_text = "".join(self._title_parts).strip() or None
        if tag == "head":
            raise _StopParsing()

    def extract(self) -> UrlMetaResponse:
        title = self.og.get("og:title") or self.meta_name.get("title") or self.title_text
        description = self.og.get("og:description") or self.meta_name.get("description")
        price = self.og.get("product:price:amount") or self.og.get("og:price:amount")
        image = self.og.get("og:image")
        return UrlMetaResponse(
            title=title, description=description, price=price, image=image
        )


def _resolve_and_validate_url(url: str) -> None:
    """Resolve hostname and check against private IP ranges."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise BadRequestError("Invalid URL.")
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise BadRequestError("Could not resolve hostname.")
    for _, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise BadRequestError(
                    "URLs pointing to private networks are not allowed."
                )


def _fetch_url(url: str) -> httpx.Response:
    """Fetch a URL with httpx. Separated for testability."""
    with httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    ) as client:
        return client.get(url)


def _parse_html(html: str) -> UrlMetaResponse:
    """Parse HTML and extract meta tag values."""
    parser = _MetaParser()
    try:
        parser.feed(html)
    except _StopParsing:
        pass
    return parser.extract()


_USELESS_TITLES = frozenset({
    "Amazon.com",
    "Robot or human?",
})


def _result_is_useful(result: UrlMetaResponse) -> bool:
    return bool(result.title and result.title not in _USELESS_TITLES)


def _fetch_linkpreview(url: str) -> UrlMetaResponse:
    """Fetch metadata via LinkPreview.net API."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            _LINKPREVIEW_URL,
            params={"q": url},
            headers={"X-Linkpreview-Api-Key": settings.linkpreview_api_key},
        )
        resp.raise_for_status()
        data = resp.json()
    return UrlMetaResponse(
        title=data.get("title") or None,
        description=data.get("description") or None,
        image=data.get("image") or None,
    )


def get_url_meta(url: str) -> UrlMetaResponse:
    """Validate, fetch, and parse a URL for metadata.

    Tries a direct fetch first, then falls back to LinkPreview.net
    if the result is empty and an API key is configured.

    Raises BadRequestError for invalid URLs or private IPs.
    Returns empty UrlMetaResponse for fetch failures or non-HTML content.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequestError("URL must use http or https.")

    _resolve_and_validate_url(url)

    result = UrlMetaResponse()

    try:
        response = _fetch_url(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            result = _parse_html(response.text)
    except Exception:
        pass

    if not _result_is_useful(result) and settings.linkpreview_api_key:
        try:
            fallback = _fetch_linkpreview(url)
            result = UrlMetaResponse(
                title=result.title if _result_is_useful(result) else fallback.title,
                description=result.description or fallback.description,
                price=result.price,
                image=result.image or fallback.image,
            )
        except Exception:
            logger.exception("LinkPreview fallback failed for %s", url)

    return result
