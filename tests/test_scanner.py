import io
import zipfile

from webstalker import models, scanner


def _add_website(client, **overrides):
    payload = {
        "name": "Example",
        "url": "https://example.com",
        "interval_value": 1,
        "interval_unit": "hours",
        "scan_mode": "raw",
        "ignore_whitespace": True,
        "ignore_timestamps": True,
        "ignore_selectors": "",
        "ignore_url_patterns": "",
        "enabled": True,
    }
    payload.update(overrides)
    r = client.post("/api/websites", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_first_scan_creates_initial_version(client, db, monkeypatch):
    monkeypatch.setattr(
        scanner,
        "_fetch_html",
        lambda url, timeout: ("<html><body>v1</body></html>", 200, "text/html"),
    )
    w = _add_website(client)
    # Create-website triggers an immediate scan synchronously when scheduler disabled.
    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["parent_version_id"] is None

    logs = client.get(f"/api/websites/{w['id']}/logs").json()
    assert any(l["result"] == "changed" and l["trigger"] == "added" for l in logs)


def test_unchanged_scan_creates_only_log(client, db, monkeypatch):
    monkeypatch.setattr(
        scanner,
        "_fetch_html",
        lambda url, timeout: ("<html><body>same</body></html>", 200, "text/html"),
    )
    w = _add_website(client)

    r = client.post(f"/api/websites/{w['id']}/scan")
    assert r.status_code == 200

    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    assert len(versions) == 1  # still just version 1

    logs = client.get(f"/api/websites/{w['id']}/logs").json()
    assert any(l["result"] == "unchanged" for l in logs)


def test_changed_scan_creates_new_version(client, db, monkeypatch):
    state = {"html": "<html><body>v1</body></html>"}

    def fetch(url, timeout):
        return state["html"], 200, "text/html"

    monkeypatch.setattr(scanner, "_fetch_html", fetch)
    w = _add_website(client)

    state["html"] = "<html><body>v2 changed</body></html>"
    r = client.post(f"/api/websites/{w['id']}/scan")
    assert r.status_code == 200

    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[0]["parent_version_id"] == versions[1]["id"]


def test_unchanged_when_only_whitespace_changes(client, db, monkeypatch):
    state = {"html": "<html><body>hello world</body></html>"}

    def fetch(url, timeout):
        return state["html"], 200, "text/html"

    monkeypatch.setattr(scanner, "_fetch_html", fetch)
    w = _add_website(client, ignore_whitespace=True)

    state["html"] = "<html>\n   <body>hello\tworld</body>\n</html>"
    r = client.post(f"/api/websites/{w['id']}/scan")
    assert r.status_code == 200
    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    assert len(versions) == 1


def test_scan_handles_http_error(client, db, monkeypatch):
    import httpx

    def fetch(url, timeout):
        request = httpx.Request("GET", url)
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr(scanner, "_fetch_html", fetch)
    w = _add_website(client)
    logs = client.get(f"/api/websites/{w['id']}/logs").json()
    assert any(l["result"] == "error" for l in logs)
    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    assert len(versions) == 0


def test_snapshot_zip_download(client, db, monkeypatch):
    monkeypatch.setattr(
        scanner,
        "_fetch_html",
        lambda url, timeout: ("<html><body>hello</body></html>", 200, "text/html"),
    )
    w = _add_website(client)
    versions = client.get(f"/api/websites/{w['id']}/versions").json()
    vid = versions[0]["id"]

    r = client.get(f"/api/versions/{vid}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "index.html" in names
    assert "metadata.json" in names
    html = z.read("index.html").decode("utf-8")
    assert "hello" in html
