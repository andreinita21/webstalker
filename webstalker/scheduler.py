import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import models, scanner
from .db import session_scope
from .interval import to_seconds


log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _job_id(website_id: int) -> str:
    return f"website-{website_id}"


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.start()
    with session_scope() as db:
        for website in db.query(models.Website).filter(models.Website.enabled.is_(True)).all():
            _add_job_for(website)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        log.exception("scheduler shutdown failed")
    _scheduler = None


def _add_job_for(website: models.Website) -> None:
    if _scheduler is None:
        return
    seconds = to_seconds(website.interval_value, website.interval_unit)
    next_run = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    _scheduler.add_job(
        scanner.perform_scan,
        trigger=IntervalTrigger(seconds=seconds),
        args=(website.id, "scheduled"),
        id=_job_id(website.id),
        replace_existing=True,
        next_run_time=next_run,
        coalesce=True,
        max_instances=1,
    )


def reconcile_website(website_id: int) -> None:
    """Sync the scheduler with the current state of a website (added/updated/toggled/deleted)."""
    if _scheduler is None:
        return
    job_id = _job_id(website_id)
    with session_scope() as db:
        website = db.get(models.Website, website_id)
        if website is None or not website.enabled:
            try:
                _scheduler.remove_job(job_id)
            except Exception:
                pass
            return
        _add_job_for(website)


def trigger_immediate(website_id: int, trigger_label: str) -> None:
    """Schedule a one-off scan that runs ASAP. Falls back to synchronous if no scheduler."""
    if _scheduler is None:
        scanner.perform_scan(website_id, trigger_label)
        return
    _scheduler.add_job(
        scanner.perform_scan,
        args=(website_id, trigger_label),
        id=f"oneshot-{website_id}-{int(time.time() * 1000)}",
        coalesce=False,
        max_instances=999,
        misfire_grace_time=60,
    )
