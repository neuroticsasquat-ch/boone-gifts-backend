from unittest.mock import patch, MagicMock

import httpx


def _mock_html_response(html: str, content_type: str = "text/html; charset=utf-8") -> MagicMock:
    """Create a mock httpx.Response with the given HTML body."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": content_type}
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


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


def test_meta_with_og_tags(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", return_value=_mock_html_response(OG_HTML)):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/product"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Cool Gadget"
    assert data["description"] == "A very cool gadget for everyone"
    assert data["price"] == "29.99"
    assert data["image"] == "https://example.com/image.jpg"


def test_meta_with_basic_html_tags(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", return_value=_mock_html_response(BASIC_HTML)):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/page"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Basic Page Title"
    assert data["description"] == "A basic page description"
    assert data["price"] is None
    assert data["image"] is None


def test_meta_with_no_relevant_tags(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", return_value=_mock_html_response(EMPTY_HTML)):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/empty"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] is None
    assert data["description"] is None
    assert data["price"] is None
    assert data["image"] is None


def test_meta_og_price_fallback(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", return_value=_mock_html_response(OG_PRICE_HTML)):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/widget"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["price"] == "9.99"


def test_meta_non_html_content_type(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", return_value=_mock_html_response('{"key": "value"}', "application/json")):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/api.json"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] is None
    assert data["description"] is None
    assert data["price"] is None
    assert data["image"] is None


def test_meta_invalid_url_scheme(client, member_headers):
    response = client.get(
        "/meta",
        params={"url": "ftp://example.com/file"},
        headers=member_headers,
    )
    assert response.status_code == 400


def test_meta_private_ip(client, member_headers):
    response = client.get(
        "/meta",
        params={"url": "http://127.0.0.1/secret"},
        headers=member_headers,
    )
    assert response.status_code == 400


def test_meta_unauthenticated(client):
    response = client.get("/meta", params={"url": "https://example.com"})
    assert response.status_code == 401


def test_meta_fetch_failure(client, member_headers):
    with patch("app.routers.meta._resolve_and_validate_url"):
        with patch("app.routers.meta._fetch_url", side_effect=Exception("Connection failed")):
            response = client.get(
                "/meta",
                params={"url": "https://example.com/down"},
                headers=member_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] is None
    assert data["description"] is None
    assert data["price"] is None
    assert data["image"] is None
