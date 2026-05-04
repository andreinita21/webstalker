def _make(client, **overrides):
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
    return client.post("/api/websites", json=payload)


def test_list_empty(client):
    r = client.get("/api/websites")
    assert r.status_code == 200
    assert r.json() == []


def test_create_website(client, monkeypatch):
    # Stub fetch so the "added" scan doesn't hit the network.
    from webstalker import scanner

    monkeypatch.setattr(
        scanner, "_fetch_html", lambda url, timeout: ("<html><body>hi</body></html>", 200, "text/html")
    )

    r = _make(client, name="Example.com", url="https://example.com")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Example.com"
    assert body["id"] > 0


def test_update_and_delete(client, monkeypatch):
    from webstalker import scanner

    monkeypatch.setattr(
        scanner, "_fetch_html", lambda url, timeout: ("<html>x</html>", 200, "text/html")
    )

    r = _make(client)
    wid = r.json()["id"]

    r = client.put(
        f"/api/websites/{wid}",
        json={"name": "Renamed", "interval_value": 5, "interval_unit": "minutes"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["interval_value"] == 5

    r = client.delete(f"/api/websites/{wid}")
    assert r.status_code == 204

    r = client.get(f"/api/websites/{wid}")
    assert r.status_code == 404


def test_invalid_url_rejected(client):
    r = _make(client, url="not-a-url")
    assert r.status_code == 422


def test_invalid_interval_unit_rejected(client):
    r = _make(client, interval_unit="fortnights")
    assert r.status_code == 422
