import httpx
import pytest


def _mock_httpx_client(monkeypatch, pages_db: dict[str, str]):
    """Replace httpx.Client used by the scanner with one that serves pages_db."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        html = pages_db.get(url)
        if html is None and not url.endswith("/"):
            html = pages_db.get(url + "/")
        if html is None:
            return httpx.Response(404, text="not found")
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    transport = httpx.MockTransport(handler)

    class MockedClient(httpx.Client):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    monkeypatch.setattr("webstalker.scanner.httpx.Client", MockedClient)


def test_url_to_archive_path_examples():
    from webstalker.scanner import _url_to_archive_path

    base = "https://example.com/"
    assert _url_to_archive_path(base, "https://example.com/") == "index.html"
    assert _url_to_archive_path(base, "https://example.com/about") == "about.html"
    assert _url_to_archive_path(base, "https://example.com/blog/") == "blog/index.html"
    assert _url_to_archive_path(base, "https://example.com/blog/post-1") == "blog/post-1.html"
    assert _url_to_archive_path(base, "https://example.com/x.html") == "x.html"
    # Cross-origin returns None.
    assert _url_to_archive_path(base, "https://other.com/x") is None
    # Query strings are folded into a unique filename.
    p = _url_to_archive_path(base, "https://example.com/search?q=hello")
    assert p is not None and p.startswith("search") and p.endswith(".html")


def test_crawl_pages_visits_same_origin_links(monkeypatch):
    from webstalker.scanner import _crawl_pages

    pages_db = {
        "https://example.com/": "<html><body><a href='/about'>about</a><a href='/blog/'>blog</a><a href='https://other.com/'>off-site</a></body></html>",
        "https://example.com/about": "<html><body><a href='/'>home</a></body></html>",
        "https://example.com/blog/": "<html><body><a href='/blog/post-1'>p1</a></body></html>",
        "https://example.com/blog/post-1": "<html><body>post 1 content</body></html>",
    }
    _mock_httpx_client(monkeypatch, pages_db)

    pages = _crawl_pages(
        "https://example.com/",
        max_pages=10,
        max_depth=2,
        timeout=5.0,
        max_size=1_000_000,
    )
    paths = {p["path"] for p in pages}
    assert "index.html" in paths
    assert "about.html" in paths
    assert "blog/index.html" in paths
    assert "blog/post-1.html" in paths
    # Did not follow off-site link.
    assert not any("other" in p["url"] for p in pages)


def test_crawl_pages_respects_max_depth(monkeypatch):
    from webstalker.scanner import _crawl_pages

    pages_db = {
        "https://example.com/": "<html><body><a href='/a'>a</a></body></html>",
        "https://example.com/a": "<html><body><a href='/b'>b</a></body></html>",
        "https://example.com/b": "<html><body><a href='/c'>c</a></body></html>",
        "https://example.com/c": "<html><body>leaf</body></html>",
    }
    _mock_httpx_client(monkeypatch, pages_db)

    pages = _crawl_pages(
        "https://example.com/",
        max_pages=20,
        max_depth=1,
        timeout=5.0,
        max_size=1_000_000,
    )
    paths = {p["path"] for p in pages}
    # depth 0 = root only; depth 1 = root + immediate links
    assert paths == {"index.html", "a.html"}


def test_crawl_pages_respects_max_pages(monkeypatch):
    from webstalker.scanner import _crawl_pages

    pages_db = {
        "https://example.com/": "<html><body>"
        + "".join(f"<a href='/p{i}'>p{i}</a>" for i in range(20))
        + "</body></html>",
    }
    for i in range(20):
        pages_db[f"https://example.com/p{i}"] = f"<html><body>page {i}</body></html>"
    _mock_httpx_client(monkeypatch, pages_db)

    pages = _crawl_pages(
        "https://example.com/",
        max_pages=5,
        max_depth=2,
        timeout=5.0,
        max_size=1_000_000,
    )
    assert len(pages) == 5


def _add_crawl_site(client, url="https://example.com/"):
    return client.post(
        "/api/websites",
        json={
            "name": "Crawl test",
            "url": url,
            "interval_value": 1,
            "interval_unit": "hours",
            "scan_mode": "crawl",
            "crawl_max_pages": 10,
            "crawl_max_depth": 2,
            "ignore_whitespace": True,
            "ignore_timestamps": True,
            "ignore_selectors": "",
            "ignore_url_patterns": "",
            "enabled": False,
        },
    )


def test_crawl_scan_creates_multi_file_version(client, monkeypatch):
    pages_db = {
        "https://example.com/": "<html><body><h1>Home</h1><a href='/about'>about</a></body></html>",
        "https://example.com/about": "<html><body><h1>About</h1></body></html>",
    }
    _mock_httpx_client(monkeypatch, pages_db)

    r = _add_crawl_site(client)
    assert r.status_code == 201, r.text
    wid = r.json()["id"]

    versions = client.get(f"/api/websites/{wid}/versions").json()
    assert len(versions) == 1
    detail = client.get(f"/api/versions/{versions[0]['id']}").json()
    paths = {e["path"] for e in detail["entries"]}
    assert "index.html" in paths
    assert "about.html" in paths
    primary = [e for e in detail["entries"] if e["is_primary"]]
    assert len(primary) == 1
    assert primary[0]["path"] == "index.html"


def test_crawl_unchanged_creates_no_new_version(client, monkeypatch):
    pages_db = {
        "https://example.com/": "<html><body>same</body></html>",
        "https://example.com/about": "<html><body>about</body></html>",
    }
    pages_db["https://example.com/"] = (
        "<html><body><h1>Home</h1><a href='/about'>a</a></body></html>"
    )
    _mock_httpx_client(monkeypatch, pages_db)

    wid = _add_crawl_site(client).json()["id"]
    assert len(client.get(f"/api/websites/{wid}/versions").json()) == 1

    r = client.post(f"/api/websites/{wid}/scan")
    assert r.status_code == 200
    assert len(client.get(f"/api/websites/{wid}/versions").json()) == 1

    logs = client.get(f"/api/websites/{wid}/logs").json()
    assert any(l["result"] == "unchanged" for l in logs)


def test_crawl_change_in_subpage_creates_new_version(client, monkeypatch):
    state = {
        "https://example.com/": "<html><body><h1>Home</h1><a href='/about'>a</a></body></html>",
        "https://example.com/about": "<html><body><h1>About v1</h1></body></html>",
    }

    def handler(request):
        url = str(request.url)
        html = state.get(url) or state.get(url.rstrip("/"))
        if html is None:
            return httpx.Response(404)
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)

    class MockedClient(httpx.Client):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    monkeypatch.setattr("webstalker.scanner.httpx.Client", MockedClient)

    wid = _add_crawl_site(client).json()["id"]
    assert len(client.get(f"/api/websites/{wid}/versions").json()) == 1

    # Change a subpage only; root unchanged.
    state["https://example.com/about"] = "<html><body><h1>About v2 changed</h1></body></html>"
    client.post(f"/api/websites/{wid}/scan")
    versions = client.get(f"/api/websites/{wid}/versions").json()
    assert len(versions) == 2
