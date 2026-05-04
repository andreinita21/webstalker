import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import models, normalize, storage
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


def perform_scan(website_id: int, trigger: str) -> dict:
    """Perform a scan. Returns a dict summarizing the result.

    trigger: one of "added", "startup", "scheduled", "manual".
    """
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
        return {"result": "skipped", "reason": "already running"}

    start = time.monotonic()
    try:
        with session_scope() as db:
            website = db.get(models.Website, website_id)
            if website is None:
                return {"result": "error", "reason": "website not found"}

            url = website.url
            mode = website.scan_mode

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
                db.add(
                    models.VerificationLog(
                        website_id=website_id,
                        trigger=trigger,
                        result="error",
                        http_status=e.response.status_code if e.response else None,
                        error_message=f"HTTP {e.response.status_code}: {e}",
                        duration_ms=duration_ms,
                    )
                )
                website.last_checked_at = _utcnow()
                website.last_status = "error"
                return {"result": "error", "reason": str(e)}
            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                db.add(
                    models.VerificationLog(
                        website_id=website_id,
                        trigger=trigger,
                        result="error",
                        error_message=f"{type(e).__name__}: {e}",
                        duration_ms=duration_ms,
                    )
                )
                website.last_checked_at = _utcnow()
                website.last_status = "error"
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
            return {"result": "changed", "version_id": version.id}
    finally:
        _unlock(website_id)
