import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import models, scheduler
from .api import versions as api_versions
from .api import websites as api_websites
from .config import settings
from .db import init_db, session_scope
from .web.pages import router as web_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.enable_scheduler:
        scheduler.start_scheduler()
        with session_scope() as db:
            for w in (
                db.query(models.Website).filter(models.Website.enabled.is_(True)).all()
            ):
                scheduler.trigger_immediate(w.id, "startup")
    try:
        yield
    finally:
        if settings.enable_scheduler:
            scheduler.shutdown_scheduler()


app = FastAPI(title="WebStalker", lifespan=lifespan)

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(api_websites.router)
app.include_router(api_versions.router)
app.include_router(web_router)


@app.get("/health")
def health():
    return {"status": "ok"}
