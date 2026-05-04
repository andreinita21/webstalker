import io
import json
import re
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import diff, models, schemas, storage
from ..db import SessionLocal


router = APIRouter(prefix="/api/versions", tags=["versions"])


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name).strip("_") or "version"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{version_id}", response_model=schemas.VersionDetail)
def get_version(version_id: int, db: Session = Depends(get_db)):
    v = db.get(models.Version, version_id)
    if not v:
        raise HTTPException(404, "version not found")
    entries = (
        db.query(models.SnapshotEntry)
        .filter(models.SnapshotEntry.version_id == v.id)
        .all()
    )
    return schemas.VersionDetail(
        id=v.id,
        website_id=v.website_id,
        version_number=v.version_number,
        parent_version_id=v.parent_version_id,
        normalized_hash=v.normalized_hash,
        root_url=v.root_url,
        http_status=v.http_status,
        created_at=v.created_at,
        entries=[schemas.SnapshotEntryOut.model_validate(e) for e in entries],
    )


@router.get("/{version_id}/diff", response_model=schemas.DiffOut)
def get_diff(version_id: int, db: Session = Depends(get_db)):
    v = db.get(models.Version, version_id)
    if not v:
        raise HTTPException(404, "version not found")
    new_entries = (
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
    new_tuples = [(e.path, e.blob_sha, e.content_type) for e in new_entries]
    files = diff.diff_versions(old_tuples, new_tuples, storage.read_blob)

    return schemas.DiffOut(
        version_id=v.id,
        parent_version_id=v.parent_version_id,
        files=[
            schemas.FileDiffOut(
                path=f.path,
                old_blob=f.old_blob,
                new_blob=f.new_blob,
                is_binary=f.is_binary,
                additions=f.additions,
                deletions=f.deletions,
                lines=[
                    schemas.DiffLineOut(
                        kind=l.kind, old_no=l.old_no, new_no=l.new_no, text=l.text
                    )
                    for l in f.lines
                ],
            )
            for f in files
        ],
    )


@router.get("/{version_id}/download")
def download_version(version_id: int, db: Session = Depends(get_db)):
    v = db.get(models.Version, version_id)
    if not v:
        raise HTTPException(404, "version not found")
    website = db.get(models.Website, v.website_id)
    entries = (
        db.query(models.SnapshotEntry)
        .filter(models.SnapshotEntry.version_id == v.id)
        .all()
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in entries:
            try:
                content = storage.read_blob(e.blob_sha)
            except Exception:
                continue
            zf.writestr(e.path, content)
        meta = {
            "version_id": v.id,
            "website_id": v.website_id,
            "website_name": website.name if website else None,
            "url": v.root_url,
            "version_number": v.version_number,
            "parent_version_id": v.parent_version_id,
            "normalized_hash": v.normalized_hash,
            "http_status": v.http_status,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "entries": [
                {
                    "path": e.path,
                    "url": e.url,
                    "blob_sha": e.blob_sha,
                    "content_type": e.content_type,
                }
                for e in entries
            ],
        }
        zf.writestr("metadata.json", json.dumps(meta, indent=2))

    buf.seek(0)
    name = _safe_filename(website.name if website else f"website-{v.website_id}")
    filename = f"{name}-v{v.version_number}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
