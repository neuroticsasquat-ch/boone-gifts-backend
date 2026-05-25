from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.meta import service
from app.schemas.meta import UrlMetaResponse
from app.services.exceptions import BadRequestError

LINKPREVIEW = "app.meta.service._fetch_linkpreview"


def _mock_html_response(html: str, content_type: str = "text/html; charset=utf-8") -> MagicMock:
    """Create a mock httpx.Response with the given HTML body."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": content_type}
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


FETCH = "app.meta.service._fetch_url"
RESOLVE = "app.meta.service._resolve_and_validate_url"

OG_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Cool Gadget" />
    <meta property="og:description" content="A very cool gadget for everyone" />
    <meta property="product:price:amount" content="29.99" />
    <meta property="og:image" content="https://example.com/image.jpg" />
    <title>Cool Gadget - Example Store</title>
</head>
<body></body>
</html>
"""

BASIC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Basic Page Title</title>
    <meta name="description" content="A basic page description" />
</head>
<body></body>
</html>
"""

EMPTY_HTML = """
<!DOCTYPE html>
<html>
<head></head>
<body><p>No meta tags here</p></body>
</html>
"""

OG_PRICE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Widget" />
    <meta property="og:price:amount" content="9.99" />
</head>
<body></body>
</html>
"""


# --- Valid URL with OG tags ---


@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(OG_HTML))
def test_get_url_meta_with_og_tags(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/product")

    mock_resolve.assert_called_once_with("https://example.com/product")
    mock_fetch.assert_called_once_with("https://example.com/product")
    assert result.title == "Cool Gadget"
    assert result.description == "A very cool gadget for everyone"
    assert result.price == "29.99"
    assert result.image == "https://example.com/image.jpg"


# --- Basic HTML fallback (title tag + meta name) ---


@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(BASIC_HTML))
def test_get_url_meta_basic_html_fallback(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/page")

    assert result.title == "Basic Page Title"
    assert result.description == "A basic page description"
    assert result.price is None
    assert result.image is None


# --- No relevant tags ---


@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(EMPTY_HTML))
def test_get_url_meta_no_tags(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/empty")

    assert result.title is None
    assert result.description is None
    assert result.price is None
    assert result.image is None


# --- OG price fallback ---


@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(OG_PRICE_HTML))
def test_get_url_meta_og_price_fallback(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/widget")

    assert result.price == "9.99"


# --- Non-HTML content type ---


@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response('{"key": "value"}', "application/json"))
def test_get_url_meta_non_html_content_type(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/api.json")

    assert result.title is None
    assert result.description is None
    assert result.price is None
    assert result.image is None


# --- Invalid URL scheme ---


def test_get_url_meta_invalid_scheme():
    with pytest.raises(BadRequestError, match="http or https"):
        service.get_url_meta("ftp://example.com/file")


# --- Private IP (SSRF protection) ---


def test_get_url_meta_private_ip():
    with pytest.raises(BadRequestError, match="private networks"):
        service.get_url_meta("http://127.0.0.1/secret")


# --- Fetch failure returns empty response ---


@patch(RESOLVE)
@patch(FETCH, side_effect=Exception("Connection failed"))
def test_get_url_meta_fetch_failure(mock_fetch, mock_resolve):
    result = service.get_url_meta("https://example.com/down")

    assert result.title is None
    assert result.description is None
    assert result.price is None
    assert result.image is None


# --- LinkPreview fallback ---

GENERIC_AMAZON_HTML = """
<!DOCTYPE html>
<html><head><title>Amazon.com</title></head><body></body></html>
"""


@patch("app.meta.service.settings")
@patch(LINKPREVIEW, return_value=UrlMetaResponse(
    title="Cool Product", description="A great product", image="https://img.com/x.jpg"
))
@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(GENERIC_AMAZON_HTML))
def test_fallback_triggered_when_direct_fetch_returns_generic_title(
    mock_fetch, mock_resolve, mock_linkpreview, mock_settings
):
    mock_settings.linkpreview_api_key = "test-key"
    result = service.get_url_meta("https://www.amazon.com/product/123")

    mock_linkpreview.assert_called_once_with("https://www.amazon.com/product/123")
    assert result.title == "Cool Product"
    assert result.description == "A great product"
    assert result.image == "https://img.com/x.jpg"


@patch("app.meta.service.settings")
@patch(LINKPREVIEW)
@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(OG_HTML))
def test_fallback_not_triggered_when_direct_fetch_succeeds(
    mock_fetch, mock_resolve, mock_linkpreview, mock_settings
):
    mock_settings.linkpreview_api_key = "test-key"
    result = service.get_url_meta("https://example.com/product")

    mock_linkpreview.assert_not_called()
    assert result.title == "Cool Gadget"


@patch("app.meta.service.settings")
@patch(LINKPREVIEW)
@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(GENERIC_AMAZON_HTML))
def test_fallback_not_triggered_when_no_api_key(
    mock_fetch, mock_resolve, mock_linkpreview, mock_settings
):
    mock_settings.linkpreview_api_key = ""
    result = service.get_url_meta("https://www.amazon.com/product/123")

    mock_linkpreview.assert_not_called()
    assert result.title == "Amazon.com"


@patch("app.meta.service.settings")
@patch(LINKPREVIEW, return_value=UrlMetaResponse(
    title="Etsy Product", description="Handmade item", image="https://img.com/y.jpg"
))
@patch(RESOLVE)
@patch(FETCH, side_effect=Exception("Connection failed"))
def test_fallback_triggered_on_fetch_failure_with_api_key(
    mock_fetch, mock_resolve, mock_linkpreview, mock_settings
):
    mock_settings.linkpreview_api_key = "test-key"
    result = service.get_url_meta("https://www.etsy.com/listing/123")

    mock_linkpreview.assert_called_once()
    assert result.title == "Etsy Product"
    assert result.description == "Handmade item"


@patch("app.meta.service.settings")
@patch(LINKPREVIEW, return_value=UrlMetaResponse(
    title="Product Name", description="Desc from linkpreview", image="https://img.com/z.jpg"
))
@patch(RESOLVE)
@patch(FETCH, return_value=_mock_html_response(
    '<html><head><meta property="product:price:amount" content="19.99" />'
    "<title>Amazon.com</title></head></html>"
))
def test_fallback_preserves_price_from_direct_fetch(
    mock_fetch, mock_resolve, mock_linkpreview, mock_settings
):
    mock_settings.linkpreview_api_key = "test-key"
    result = service.get_url_meta("https://www.amazon.com/product/456")

    assert result.title == "Product Name"
    assert result.price == "19.99"
    assert result.image == "https://img.com/z.jpg"
