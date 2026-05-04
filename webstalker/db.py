from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import settings


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register models on Base.metadata)
    from sqlalchemy import inspect

    Base.metadata.create_all(engine)

    # Lightweight schema migration for SQLite when new columns are added to
    # existing tables. We don't want to require Alembic for a local-only tool.
    inspector = inspect(engine)
    if inspector.has_table("websites"):
        existing = {c["name"] for c in inspector.get_columns("websites")}
        adds: list[str] = []
        if "crawl_max_pages" not in existing:
            adds.append("ALTER TABLE websites ADD COLUMN crawl_max_pages INTEGER NOT NULL DEFAULT 25")
        if "crawl_max_depth" not in existing:
            adds.append("ALTER TABLE websites ADD COLUMN crawl_max_depth INTEGER NOT NULL DEFAULT 2")
        if adds:
            with engine.begin() as conn:
                for stmt in adds:
                    conn.exec_driver_sql(stmt)
