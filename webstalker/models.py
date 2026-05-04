from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    interval_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    interval_unit: Mapped[str] = mapped_column(String(20), default="hours", nullable=False)

    scan_mode: Mapped[str] = mapped_column(String(20), default="raw", nullable=False)

    ignore_whitespace: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ignore_selectors: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ignore_url_patterns: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ignore_timestamps: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Blob(Base):
    __tablename__ = "blobs"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"))
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    root_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("website_id", "version_number", name="uq_version_website_number"),
        Index("ix_versions_website", "website_id"),
    )


class SnapshotEntry(Base):
    __tablename__ = "snapshot_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("versions.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    blob_sha: Mapped[str] = mapped_column(
        String(64), ForeignKey("blobs.sha256"), nullable=False
    )
    content_type: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_snapshot_entries_version", "version_id"),)


class VerificationLog(Base):
    __tablename__ = "verification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"))
    previous_version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"))

    __table_args__ = (Index("ix_logs_website_timestamp", "website_id", "timestamp"),)
