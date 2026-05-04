import logging
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import events, models, normalize, storage
from .config import settings
from .db import session_scope


log = logging.getLogger(__name__)


# In-process scan locking. Prevents concurrent scans for the same website.
_running_scans: set[int] = set()
_running_lock = threading.Lock()


def _try_lock(website_id: int) -> bool:
    with _running_lock:
        if website_id in _running_scans:
            return False
        _running_scans.add(website_id)
        return True


def _unlock(website_id: int) -> None:
    with _running_lock:
        _running_scans.discard(website_id)


def is_scanning(website_id: int) -> bool:
    with _running_lock:
        return website_id in _running_scans


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_for_hash(website: models.Website, html: str) -> str:
    selectors = normalize.split_lines(website.ignore_selectors or "")
    url_patterns = normalize.split_lines(website.ignore_url_patterns or "")
    return normalize.normalize_html(
        html,
        ignore_whitespace=website.ignore_whitespace,
        ignore_selectors=selectors,
        ignore_url_patterns=url_patterns,
        ignore_timestamps=website.ignore_timestamps,
    )


def _fetch_html(url: str, timeout: float) -> tuple[str, int, str]:
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "text/html")
        return resp.text, resp.status_code, ctype


def _fetch_playwright(url: str, timeout: float) -> tuple[str, int, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Install it with: "
            "pip install playwright && playwright install chromium"
        ) from e

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(user_agent=settings.user_agent)
            page = context.new_page()
            response = page.goto(url, timeout=int(timeout * 1000), wait_until="networkidle")
            html = page.content()
            status = response.status if response else 200
            return html, status, "text/html"
        finally:
            browser.close()


def _safe_asset_path(base_url: str, asset_url: str) -> str | None:
    """Return a safe relative path for a same-origin asset, or None to skip it."""
    try:
        full = urljoin(base_url, asset_url)
        base = urlparse(base_url)
        full_p = urlparse(full)
    except Exception:
        return None
    if (full_p.scheme, full_p.netloc) != (base.scheme, base.netloc):
        return None
    rel_path = full_p.path.lstrip("/")
    if not rel_path or rel_path.endswith("/"):
        rel_path = rel_path + "index"
    rel_parts: list[str] = []
    for part in rel_path.split("/"):
        if part in ("", ".", ".."):
            continue
        # Strip characters that could escape archive paths.
        part = part.replace("\\", "_").replace(":", "_")
        rel_parts.append(part)
    if not rel_parts:
        return None
    return "/".join(rel_parts)


def _collect_asset_targets(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    targets: list[str] = []

    def add(u: str | None) -> None:
        if not u:
            return
        u = u.strip()
        if not u or u.startswith("data:") or u.startswith("javascript:"):
            return
        if u in seen:
            return
        seen.add(u)
        targets.append(u)

    for tag in soup.find_all("link", href=True):
        rels = tag.get("rel") or []
        if any(r in ("stylesheet", "icon", "preload") for r in rels):
            add(tag["href"])
    for tag in soup.find_all("script", src=True):
        add(tag["src"])
    for tag in soup.find_all("img", src=True):
        add(tag["src"])
    return targets


_PATH_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _url_to_archive_path(base_url: str, target_url: str) -> str | None:
    """Map a same-origin URL into a safe relative path inside a snapshot tree.

    Examples (base = https://example.com/):
        https://example.com/         -> "index.html"
        https://example.com/about    -> "about.html"
        https://example.com/blog/    -> "blog/index.html"
        https://example.com/x/y.html -> "x/y.html"
        https://example.com/a?b=c    -> "a__b_c.html"
    """
    try:
        base = urlparse(base_url)
        target = urlparse(target_url)
    except Exception:
        return None
    if (target.scheme, target.netloc) != (base.scheme, base.netloc):
        return None
    path = target.path or "/"
    if not path or path == "/":
        path = "/index.html"
    elif path.endswith("/"):
        path = path + "index.html"

    parts: list[str] = []
    for seg in path.split("/"):
        if seg in ("", ".", ".."):
            continue
        parts.append(_PATH_SAFE_RE.sub("_", seg))
    if not parts:
        return "index.html"
    last = parts[-1]
    if "." not in last:
        parts[-1] = last + ".html"
    elif not last.endswith((".html", ".htm")):
        parts[-1] = last + ".html"
    if target.query:
        suffix = _PATH_SAFE_RE.sub("_", target.query)[:64]
        stem, _, ext = parts[-1].rpartition(".")
        parts[-1] = f"{stem}__{suffix}.{ext}" if stem else f"{parts[-1]}__{suffix}"
    return "/".join(parts)


def _crawl_pages(
    start_url: str,
    *,
    max_pages: int,
    max_depth: int,
    timeout: float,
    max_size: int,
) -> list[dict]:
    """HTTrack-style breadth-first crawl, same-origin only.

    Returns a list of {path, url, content, content_type}. The first page is
    always the start URL. HTML pages only; non-HTML responses are skipped.
    """
    visited: set[str] = set()
    pages: list[dict] = []
    used_paths: set[str] = set()
    base = urlparse(start_url)
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()
            url = url.split("#", 1)[0]
            if url in visited:
                continue
            visited.add(url)
            try:
                resp = client.get(url)
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            ctype = (resp.headers.get("content-type") or "").lower()
            if "html" not in ctype:
                continue
            content = resp.content
            if len(content) > max_size:
                continue

            arch_path = _url_to_archive_path(start_url, str(resp.url))
            if arch_path is None:
                continue
            unique_path = arch_path
            n = 1
            while unique_path in used_paths:
                if "." in arch_path:
                    stem, ext = arch_path.rsplit(".", 1)
                    unique_path = f"{stem}-{n}.{ext}"
                else:
                    unique_path = f"{arch_path}-{n}"
                n += 1
            used_paths.add(unique_path)

            pages.append(
                {
                    "path": unique_path,
                    "url": str(resp.url),
                    "content": content,
                    "content_type": ctype,
                }
            )

            if depth >= max_depth:
                continue

            try:
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception:
                continue
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href:
                    continue
                if href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                    continue
                full = urljoin(str(resp.url), href).split("#", 1)[0]
                p = urlparse(full)
                if p.scheme not in ("http", "https"):
                    continue
                if (p.scheme, p.netloc) != (base.scheme, base.netloc):
                    continue
                if full not in visited:
                    queue.append((full, depth + 1))

    return pages


def _fetch_assets(
    base_url: str,
    html: str,
    *,
    timeout: float,
    max_assets: int,
    max_size: int,
) -> list[dict]:
    out: list[dict] = []
    headers = {"User-Agent": settings.user_agent}
    paths_used: set[str] = set()
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for u in _collect_asset_targets(html):
            if len(out) >= max_assets:
                break
            full = urljoin(base_url, u)
            rel = _safe_asset_path(base_url, u)
            if rel is None or rel in paths_used or rel == "index.html":
                continue
            try:
                resp = client.get(full)
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            content = resp.content
            if len(content) > max_size:
                continue
            ctype = resp.headers.get("content-type", "")
            paths_used.add(rel)
            out.append(
                {"path": rel, "url": full, "content": content, "content_type": ctype}
            )
    return out


def _do_crawl_scan(*, db, website, trigger, start, end_payload) -> dict:
    """Crawl-mode scan path, runs inside the existing perform_scan db session."""
    url = website.url
    try:
        pages = _crawl_pages(
            url,
            max_pages=int(website.crawl_max_pages or 25),
            max_depth=int(website.crawl_max_depth or 2),
            timeout=settings.request_timeout_seconds,
            max_size=settings.max_asset_size_bytes,
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        err_msg = f"crawl failed: {type(e).__name__}: {e}"
        db.add(
            models.VerificationLog(
                website_id=website.id,
                trigger=trigger,
                result="error",
                error_message=err_msg,
                duration_ms=duration_ms,
            )
        )
        website.last_checked_at = _utcnow()
        website.last_status = "error"
        end_payload.update(result="error", duration_ms=duration_ms, error_message=err_msg)
        return {"result": "error", "reason": err_msg}

    if not pages:
        duration_ms = int((time.monotonic() - start) * 1000)
        err_msg = "crawl produced no pages (start URL unreachable or non-HTML)"
        db.add(
            models.VerificationLog(
                website_id=website.id,
                trigger=trigger,
                result="error",
                error_message=err_msg,
                duration_ms=duration_ms,
            )
        )
        website.last_checked_at = _utcnow()
        website.last_status = "error"
        end_payload.update(result="error", duration_ms=duration_ms, error_message=err_msg)
        return {"result": "error", "reason": err_msg}

    # Combined normalized hash: each page is normalized independently, then
    # joined in a deterministic order. Path is included so renaming a page
    # registers as a real change.
    parts: list[str] = []
    for p in sorted(pages, key=lambda x: x["path"]):
        try:
            text = p["content"].decode("utf-8", errors="replace")
        except Exception:
            continue
        parts.append(p["path"] + "\n" + _normalize_for_hash(website, text))
    normalized_combined = "\n---\n".join(parts)
    normalized_hash = storage.compute_sha256(normalized_combined.encode("utf-8"))

    latest = (
        db.query(models.Version)
        .filter(models.Version.website_id == website.id)
        .order_by(models.Version.version_number.desc())
        .first()
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    if latest is not None and latest.normalized_hash == normalized_hash:
        db.add(
            models.VerificationLog(
                website_id=website.id,
                trigger=trigger,
                result="unchanged",
                http_status=200,
                duration_ms=duration_ms,
                previous_version_id=latest.id,
            )
        )
        website.last_checked_at = _utcnow()
        website.last_status = "ok"
        end_payload.update(
            result="unchanged",
            duration_ms=duration_ms,
            http_status=200,
            version_id=latest.id,
            version_number=latest.version_number,
        )
        return {"result": "unchanged", "version_id": latest.id, "pages": len(pages)}

    new_number = (latest.version_number + 1) if latest else 1
    version = models.Version(
        website_id=website.id,
        version_number=new_number,
        parent_version_id=latest.id if latest else None,
        normalized_hash=normalized_hash,
        root_url=url,
        http_status=200,
    )
    db.add(version)
    db.flush()

    primary_path = "index.html" if any(p["path"] == "index.html" for p in pages) else pages[0]["path"]
    for p in pages:
        sha = storage.write_blob(p["content"])
        if db.get(models.Blob, sha) is None:
            db.add(
                models.Blob(
                    sha256=sha,
                    size=len(p["content"]),
                    content_type=p["content_type"],
                )
            )
        db.add(
            models.SnapshotEntry(
                version_id=version.id,
                path=p["path"],
                url=p["url"],
                blob_sha=sha,
                content_type=p["content_type"],
                is_primary=(p["path"] == primary_path),
            )
        )

    db.add(
        models.VerificationLog(
            website_id=website.id,
            trigger=trigger,
            result="changed",
            http_status=200,
            duration_ms=duration_ms,
            previous_version_id=latest.id if latest else None,
            created_version_id=version.id,
        )
    )
    website.last_checked_at = _utcnow()
    website.last_changed_at = _utcnow()
    website.last_status = "changed" if latest else "ok"
    end_payload.update(
        result="changed",
        duration_ms=duration_ms,
        http_status=200,
        version_id=version.id,
        version_number=new_number,
    )
    return {"result": "changed", "version_id": version.id, "pages": len(pages)}


def perform_scan(website_id: int, trigger: str) -> dict:
    """Perform a scan. Returns a dict summarizing the result.

    trigger: one of "added", "startup", "scheduled", "manual".
    """
    # Load website name + URL up front so every emitted event identifies
    # the site by name even when locking or DB lookup fails later.
    with session_scope() as db:
        w = db.get(models.Website, website_id)
        if w is None:
            return {"result": "error", "reason": "website not found"}
        website_name = w.name
        website_url = w.url

    if not _try_lock(website_id):
        with session_scope() as db:
            db.add(
                models.VerificationLog(
                    website_id=website_id,
                    trigger=trigger,
                    result="error",
                    error_message="Scan already running for this website; skipped.",
                )
            )
        events.publish({
            "type": "scan.end",
            "website_id": website_id,
            "website_name": website_name,
            "url": website_url,
            "trigger": trigger,
            "result": "skipped",
            "duration_ms": 0,
            "http_status": None,
            "error_message": "scan already running",
            "version_id": None,
            "version_number": None,
        })
        return {"result": "skipped", "reason": "already running"}

    events.publish({
        "type": "scan.start",
        "website_id": website_id,
        "website_name": website_name,
        "url": website_url,
        "trigger": trigger,
    })

    start = time.monotonic()
    end_payload: dict = {
        "type": "scan.end",
        "website_id": website_id,
        "website_name": website_name,
        "url": website_url,
        "trigger": trigger,
        "result": "error",
        "duration_ms": 0,
        "http_status": None,
        "error_message": None,
        "version_id": None,
        "version_number": None,
    }

    try:
        with session_scope() as db:
            website = db.get(models.Website, website_id)
            if website is None:
                end_payload["error_message"] = "website not found"
                return {"result": "error", "reason": "website not found"}

            url = website.url
            mode = website.scan_mode

            if mode == "crawl":
                return _do_crawl_scan(
                    db=db,
                    website=website,
                    trigger=trigger,
                    start=start,
                    end_payload=end_payload,
                )

            try:
                if mode == "playwright":
                    html, status_code, _ctype = _fetch_playwright(
                        url, settings.request_timeout_seconds
                    )
                else:
                    html, status_code, _ctype = _fetch_html(
                        url, settings.request_timeout_seconds
                    )
            except httpx.HTTPStatusError as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                err_status = e.response.status_code if e.response else None
                err_msg = f"HTTP {err_status}: {e}" if err_status else f"HTTP error: {e}"
                db.add(
                    models.VerificationLog(
                        website_id=website_id,
                        trigger=trigger,
                        result="error",
                        http_status=err_status,
                        error_message=err_msg,
                        duration_ms=duration_ms,
                    )
                )
                website.last_checked_at = _utcnow()
                website.last_status = "error"
                end_payload.update(
                    result="error",
                    duration_ms=duration_ms,
                    http_status=err_status,
                    error_message=err_msg,
                )
                return {"result": "error", "reason": str(e)}
            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                err_msg = f"{type(e).__name__}: {e}"
                db.add(
                    models.VerificationLog(
                        website_id=website_id,
                        trigger=trigger,
                        result="error",
                        error_message=err_msg,
                        duration_ms=duration_ms,
                    )
                )
                website.last_checked_at = _utcnow()
                website.last_status = "error"
                end_payload.update(
                    result="error",
                    duration_ms=duration_ms,
                    error_message=err_msg,
                )
                return {"result": "error", "reason": str(e)}

            normalized = _normalize_for_hash(website, html)
            normalized_hash = storage.compute_sha256(normalized.encode("utf-8"))

            latest = (
                db.query(models.Version)
                .filter(models.Version.website_id == website_id)
                .order_by(models.Version.version_number.desc())
                .first()
            )

            duration_ms = int((time.monotonic() - start) * 1000)

            if latest is not None and latest.normalized_hash == normalized_hash:
                db.add(
                    models.VerificationLog(
                        website_id=website_id,
                        trigger=trigger,
                        result="unchanged",
                        http_status=status_code,
                        duration_ms=duration_ms,
                        previous_version_id=latest.id,
                    )
                )
                website.last_checked_at = _utcnow()
                website.last_status = "ok"
                end_payload.update(
                    result="unchanged",
                    duration_ms=duration_ms,
                    http_status=status_code,
                    version_id=latest.id,
                    version_number=latest.version_number,
                )
                return {"result": "unchanged", "version_id": latest.id}

            html_bytes = html.encode("utf-8")
            html_sha = storage.write_blob(html_bytes)
            if db.get(models.Blob, html_sha) is None:
                db.add(
                    models.Blob(
                        sha256=html_sha, size=len(html_bytes), content_type="text/html"
                    )
                )

            new_number = (latest.version_number + 1) if latest else 1
            version = models.Version(
                website_id=website_id,
                version_number=new_number,
                parent_version_id=latest.id if latest else None,
                normalized_hash=normalized_hash,
                root_url=url,
                http_status=status_code,
            )
            db.add(version)
            db.flush()

            db.add(
                models.SnapshotEntry(
                    version_id=version.id,
                    path="index.html",
                    url=url,
                    blob_sha=html_sha,
                    content_type="text/html",
                    is_primary=True,
                )
            )

            if mode == "assets":
                try:
                    assets = _fetch_assets(
                        url,
                        html,
                        timeout=settings.asset_timeout_seconds,
                        max_assets=settings.max_assets_per_page,
                        max_size=settings.max_asset_size_bytes,
                    )
                    for a in assets:
                        sha = storage.write_blob(a["content"])
                        if db.get(models.Blob, sha) is None:
                            db.add(
                                models.Blob(
                                    sha256=sha,
                                    size=len(a["content"]),
                                    content_type=a["content_type"],
                                )
                            )
                        db.add(
                            models.SnapshotEntry(
                                version_id=version.id,
                                path=a["path"],
                                url=a["url"],
                                blob_sha=sha,
                                content_type=a["content_type"],
                                is_primary=False,
                            )
                        )
                except Exception:
                    log.exception("asset fetch failed for website %s", website_id)

            db.add(
                models.VerificationLog(
                    website_id=website_id,
                    trigger=trigger,
                    result="changed",
                    http_status=status_code,
                    duration_ms=duration_ms,
                    previous_version_id=latest.id if latest else None,
                    created_version_id=version.id,
                )
            )
            website.last_checked_at = _utcnow()
            website.last_changed_at = _utcnow()
            website.last_status = "changed" if latest else "ok"
            end_payload.update(
                result="changed",
                duration_ms=duration_ms,
                http_status=status_code,
                version_id=version.id,
                version_number=new_number,
            )
            return {"result": "changed", "version_id": version.id}
    finally:
        _unlock(website_id)
        events.publish(end_payload)
