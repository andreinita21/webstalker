from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import diff, models, scanner, scheduler, storage
from ..db import SessionLocal
from ..interval import INTERVAL_UNITS, humanize, to_seconds


router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ---------- Jinja helpers ----------


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _humanize_ago(dt: datetime | None, *, now: datetime | None = None) -> str:
    if dt is None:
        return "never"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


def _short_hash(s: str | None, n: int = 8) -> str:
    if not s:
        return ""
    return s[:n]


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n = n / 1024
    return f"{n:.1f} TB"


templates.env.filters["fmt_dt"] = _format_dt
templates.env.filters["ago"] = _humanize_ago
templates.env.filters["short_hash"] = _short_hash
templates.env.filters["fmt_size"] = _fmt_size
templates.env.filters["humanize_interval"] = lambda v, u: humanize(v, u)
templates.env.globals["INTERVAL_UNITS"] = list(INTERVAL_UNITS.keys())
templates.env.globals["SCAN_MODES"] = [
    ("raw", "Raw HTML only"),
    ("assets", "HTML + same-origin assets"),
    ("crawl", "Crawl subpages (HTTrack-style)"),
    ("playwright", "Browser-rendered (Playwright)"),
]


# ---------- DB dependency ----------


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Helpers ----------


def _flash(request: Request) -> dict | None:
    msg = request.query_params.get("flash")
    kind = request.query_params.get("flash_kind", "info")
    if not msg:
        return None
    return {"message": msg, "kind": kind}


def _redirect_with_flash(url: str, message: str, kind: str = "info") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    from urllib.parse import quote

    return RedirectResponse(
        f"{url}{sep}flash={quote(message)}&flash_kind={kind}",
        status_code=303,
    )


# ---------- Dashboard ----------


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    websites = db.query(models.Website).order_by(models.Website.name).all()
    counts = []
    for w in websites:
        version_count = (
            db.query(models.Version)
            .filter(models.Version.website_id == w.id)
            .count()
        )
        counts.append(version_count)
    items = list(zip(websites, counts))
    running_ids = {wid for wid in (w.id for w in websites) if scanner.is_scanning(wid)}
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "items": items,
            "running_ids": running_ids,
            "flash": _flash(request),
        },
    )


# ---------- New / edit website ----------


@router.get("/websites/new", response_class=HTMLResponse)
def website_new(request: Request):
    return templates.TemplateResponse(
        request,
        "website_form.html",
        {
            "website": None,
            "errors": {},
            "values": {
                "name": "",
                "url": "",
                "interval_value": 1,
                "interval_unit": "hours",
                "scan_mode": "raw",
                "crawl_max_pages": 25,
                "crawl_max_depth": 2,
                "ignore_whitespace": True,
                "ignore_timestamps": True,
                "ignore_selectors": "",
                "ignore_url_patterns": "",
                "enabled": True,
            },
            "flash": _flash(request),
        },
    )


@router.post("/websites/new")
def website_create(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    url: str = Form(...),
    interval_value: int = Form(1),
    interval_unit: str = Form("hours"),
    scan_mode: str = Form("raw"),
    crawl_max_pages: int = Form(25),
    crawl_max_depth: int = Form(2),
    ignore_whitespace: bool = Form(False),
    ignore_timestamps: bool = Form(False),
    ignore_selectors: str = Form(""),
    ignore_url_patterns: str = Form(""),
    enabled: bool = Form(False),
):
    from ..schemas import WebsiteCreate
    from pydantic import ValidationError

    try:
        payload = WebsiteCreate(
            name=name,
            url=url,
            interval_value=interval_value,
            interval_unit=interval_unit,
            scan_mode=scan_mode,
            crawl_max_pages=crawl_max_pages,
            crawl_max_depth=crawl_max_depth,
            ignore_whitespace=ignore_whitespace,
            ignore_timestamps=ignore_timestamps,
            ignore_selectors=ignore_selectors,
            ignore_url_patterns=ignore_url_patterns,
            enabled=enabled,
        )
        to_seconds(payload.interval_value, payload.interval_unit)
    except (ValidationError, ValueError) as e:
        errors = {}
        if isinstance(e, ValidationError):
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors[loc] = err["msg"]
        else:
            errors["interval_value"] = str(e)
        return templates.TemplateResponse(
            request,
            "website_form.html",
            {
                "website": None,
                "errors": errors,
                "values": {
                    "name": name,
                    "url": url,
                    "interval_value": interval_value,
                    "interval_unit": interval_unit,
                    "scan_mode": scan_mode,
                    "crawl_max_pages": crawl_max_pages,
                    "crawl_max_depth": crawl_max_depth,
                    "ignore_whitespace": ignore_whitespace,
                    "ignore_timestamps": ignore_timestamps,
                    "ignore_selectors": ignore_selectors,
                    "ignore_url_patterns": ignore_url_patterns,
                    "enabled": enabled,
                },
                "flash": None,
            },
            status_code=400,
        )

    w = models.Website(**payload.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    scheduler.reconcile_website(w.id)
    scheduler.trigger_immediate(w.id, "added")
    return _redirect_with_flash(
        f"/websites/{w.id}", f"Added “{w.name}”. Initial scan started.", "success"
    )


@router.get("/websites/{website_id}/edit", response_class=HTMLResponse)
def website_edit(request: Request, website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    return templates.TemplateResponse(
        request,
        "website_form.html",
        {
            "website": w,
            "errors": {},
            "values": {
                "name": w.name,
                "url": w.url,
                "interval_value": w.interval_value,
                "interval_unit": w.interval_unit,
                "scan_mode": w.scan_mode,
                "crawl_max_pages": w.crawl_max_pages,
                "crawl_max_depth": w.crawl_max_depth,
                "ignore_whitespace": w.ignore_whitespace,
                "ignore_timestamps": w.ignore_timestamps,
                "ignore_selectors": w.ignore_selectors,
                "ignore_url_patterns": w.ignore_url_patterns,
                "enabled": w.enabled,
            },
            "flash": _flash(request),
        },
    )


@router.post("/websites/{website_id}/edit")
def website_update(
    request: Request,
    website_id: int,
    db: Session = Depends(get_db),
    name: str = Form(...),
    url: str = Form(...),
    interval_value: int = Form(1),
    interval_unit: str = Form("hours"),
    scan_mode: str = Form("raw"),
    crawl_max_pages: int = Form(25),
    crawl_max_depth: int = Form(2),
    ignore_whitespace: bool = Form(False),
    ignore_timestamps: bool = Form(False),
    ignore_selectors: str = Form(""),
    ignore_url_patterns: str = Form(""),
    enabled: bool = Form(False),
):
    from ..schemas import WebsiteCreate
    from pydantic import ValidationError

    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")

    try:
        payload = WebsiteCreate(
            name=name,
            url=url,
            interval_value=interval_value,
            interval_unit=interval_unit,
            scan_mode=scan_mode,
            crawl_max_pages=crawl_max_pages,
            crawl_max_depth=crawl_max_depth,
            ignore_whitespace=ignore_whitespace,
            ignore_timestamps=ignore_timestamps,
            ignore_selectors=ignore_selectors,
            ignore_url_patterns=ignore_url_patterns,
            enabled=enabled,
        )
        to_seconds(payload.interval_value, payload.interval_unit)
    except (ValidationError, ValueError) as e:
        errors = {}
        if isinstance(e, ValidationError):
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors[loc] = err["msg"]
        else:
            errors["interval_value"] = str(e)
        return templates.TemplateResponse(
            request,
            "website_form.html",
            {
                "website": w,
                "errors": errors,
                "values": {
                    "name": name,
                    "url": url,
                    "interval_value": interval_value,
                    "interval_unit": interval_unit,
                    "scan_mode": scan_mode,
                    "crawl_max_pages": crawl_max_pages,
                    "crawl_max_depth": crawl_max_depth,
                    "ignore_whitespace": ignore_whitespace,
                    "ignore_timestamps": ignore_timestamps,
                    "ignore_selectors": ignore_selectors,
                    "ignore_url_patterns": ignore_url_patterns,
                    "enabled": enabled,
                },
                "flash": None,
            },
            status_code=400,
        )

    for k, v in payload.model_dump().items():
        setattr(w, k, v)
    db.commit()
    scheduler.reconcile_website(w.id)
    return _redirect_with_flash(f"/websites/{w.id}", "Settings saved.", "success")


@router.post("/websites/{website_id}/delete")
def website_delete(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    name = w.name
    db.delete(w)
    db.commit()
    scheduler.reconcile_website(website_id)
    return _redirect_with_flash("/", f"Deleted “{name}”.", "success")


@router.post("/websites/{website_id}/scan")
def website_scan(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    scheduler.trigger_immediate(w.id, "manual")
    return _redirect_with_flash(
        f"/websites/{w.id}?tab=logs",
        f"Scan started for “{w.name}”.",
        "info",
    )


@router.post("/websites/{website_id}/toggle")
def website_toggle(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    w.enabled = not w.enabled
    db.commit()
    scheduler.reconcile_website(w.id)
    state = "enabled" if w.enabled else "disabled"
    return _redirect_with_flash(f"/websites/{w.id}", f"Monitoring {state}.", "success")


@router.post("/scan-all")
def scan_all_now(db: Session = Depends(get_db)):
    websites = db.query(models.Website).filter(models.Website.enabled.is_(True)).all()
    for w in websites:
        scheduler.trigger_immediate(w.id, "manual")
    return _redirect_with_flash("/", f"Scanning {len(websites)} website(s).", "info")


# ---------- Website detail ----------


@router.get("/websites/{website_id}", response_class=HTMLResponse)
def website_detail(
    request: Request,
    website_id: int,
    tab: str = "versions",
    db: Session = Depends(get_db),
):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    if tab not in ("versions", "logs", "settings"):
        tab = "versions"
    versions = (
        db.query(models.Version)
        .filter(models.Version.website_id == w.id)
        .order_by(models.Version.version_number.desc())
        .all()
    )
    logs = (
        db.query(models.VerificationLog)
        .filter(models.VerificationLog.website_id == w.id)
        .order_by(models.VerificationLog.timestamp.desc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "website_detail.html",
        {
            "website": w,
            "tab": tab,
            "versions": versions,
            "logs": logs,
            "is_scanning": scanner.is_scanning(w.id),
            "flash": _flash(request),
        },
    )


# ---------- Version detail (with diff) ----------


@router.get("/versions/{version_id}", response_class=HTMLResponse)
def version_detail(
    request: Request, version_id: int, db: Session = Depends(get_db)
):
    v = db.get(models.Version, version_id)
    if not v:
        raise HTTPException(404, "version not found")
    website = db.get(models.Website, v.website_id)
    entries = (
        db.query(models.SnapshotEntry)
        .filter(models.SnapshotEntry.version_id == v.id)
        .all()
    )
    if v.parent_version_id is None:
        old_entries: list[models.SnapshotEntry] = []
    else:
        old_entries = (
            db.query(models.SnapshotEntry)
            .filter(models.SnapshotEntry.version_id == v.parent_version_id)
            .all()
        )
    old_tuples = [(e.path, e.blob_sha, e.content_type) for e in old_entries]
    new_tuples = [(e.path, e.blob_sha, e.content_type) for e in entries]
    file_diffs = diff.diff_versions(old_tuples, new_tuples, storage.read_blob)
    total_adds = sum(f.additions for f in file_diffs)
    total_dels = sum(f.deletions for f in file_diffs)

    return templates.TemplateResponse(
        request,
        "version_detail.html",
        {
            "website": website,
            "version": v,
            "entries": entries,
            "file_diffs": file_diffs,
            "total_adds": total_adds,
            "total_dels": total_dels,
            "flash": _flash(request),
        },
    )
