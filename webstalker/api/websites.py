from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, scheduler, schemas
from ..db import SessionLocal
from ..interval import to_seconds


router = APIRouter(prefix="/api/websites", tags=["websites"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[schemas.WebsiteOut])
def list_websites(db: Session = Depends(get_db)):
    return db.query(models.Website).order_by(models.Website.name).all()


@router.post("", response_model=schemas.WebsiteOut, status_code=201)
def create_website(payload: schemas.WebsiteCreate, db: Session = Depends(get_db)):
    try:
        to_seconds(payload.interval_value, payload.interval_unit)
    except ValueError as e:
        raise HTTPException(400, str(e))
    w = models.Website(**payload.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    scheduler.reconcile_website(w.id)
    scheduler.trigger_immediate(w.id, "added")
    return w


# IMPORTANT: Static paths must be declared before /{website_id} routes.
@router.post("/scan-all")
def scan_all(db: Session = Depends(get_db)):
    websites = (
        db.query(models.Website).filter(models.Website.enabled.is_(True)).all()
    )
    for w in websites:
        scheduler.trigger_immediate(w.id, "manual")
    return {"scheduled": len(websites)}


@router.get("/{website_id}", response_model=schemas.WebsiteOut)
def get_website(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    return w


@router.put("/{website_id}", response_model=schemas.WebsiteOut)
def update_website(
    website_id: int, payload: schemas.WebsiteUpdate, db: Session = Depends(get_db)
):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    data = payload.model_dump(exclude_unset=True)
    if "interval_value" in data or "interval_unit" in data:
        try:
            to_seconds(
                data.get("interval_value", w.interval_value),
                data.get("interval_unit", w.interval_unit),
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
    for k, v in data.items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    scheduler.reconcile_website(w.id)
    return w


@router.delete("/{website_id}", status_code=204)
def delete_website(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    db.delete(w)
    db.commit()
    scheduler.reconcile_website(website_id)
    return None


@router.post("/{website_id}/scan", response_model=schemas.ScanTriggered)
def scan_now(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    scheduler.trigger_immediate(w.id, "manual")
    return schemas.ScanTriggered(website_id=w.id, scheduled=True)


@router.get("/{website_id}/versions", response_model=list[schemas.VersionOut])
def list_versions(website_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    return (
        db.query(models.Version)
        .filter(models.Version.website_id == website_id)
        .order_by(models.Version.version_number.desc())
        .all()
    )


@router.get("/{website_id}/logs", response_model=list[schemas.LogOut])
def list_logs(website_id: int, limit: int = 200, db: Session = Depends(get_db)):
    w = db.get(models.Website, website_id)
    if not w:
        raise HTTPException(404, "website not found")
    limit = max(1, min(limit, 1000))
    return (
        db.query(models.VerificationLog)
        .filter(models.VerificationLog.website_id == website_id)
        .order_by(models.VerificationLog.timestamp.desc())
        .limit(limit)
        .all()
    )
