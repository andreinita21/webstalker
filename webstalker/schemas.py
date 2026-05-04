import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScanMode = Literal["raw", "assets", "playwright"]
IntervalUnit = Literal["seconds", "minutes", "hours", "days", "weeks", "months"]

URL_RE = re.compile(r"^https?://[^\s/?#]+(?:[/?#][^\s]*)?$", re.I)


def _validate_url(v: str) -> str:
    v = (v or "").strip()
    if not URL_RE.match(v):
        raise ValueError("URL must be a valid http:// or https:// URL")
    return v


class WebsiteBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    enabled: bool = True
    interval_value: int = Field(default=1, ge=1)
    interval_unit: IntervalUnit = "hours"
    scan_mode: ScanMode = "raw"
    ignore_whitespace: bool = True
    ignore_selectors: str = ""
    ignore_url_patterns: str = ""
    ignore_timestamps: bool = True

    @field_validator("url")
    @classmethod
    def _val_url(cls, v: str) -> str:
        return _validate_url(v)


class WebsiteCreate(WebsiteBase):
    pass


class WebsiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    interval_value: int | None = Field(default=None, ge=1)
    interval_unit: IntervalUnit | None = None
    scan_mode: ScanMode | None = None
    ignore_whitespace: bool | None = None
    ignore_selectors: str | None = None
    ignore_url_patterns: str | None = None
    ignore_timestamps: bool | None = None

    @field_validator("url")
    @classmethod
    def _val_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_url(v)


class WebsiteOut(WebsiteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_status: str
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    website_id: int
    version_number: int
    parent_version_id: int | None
    normalized_hash: str
    root_url: str
    http_status: int | None
    created_at: datetime


class SnapshotEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    path: str
    url: str | None
    blob_sha: str
    content_type: str | None
    is_primary: bool


class VersionDetail(VersionOut):
    entries: list[SnapshotEntryOut]


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    website_id: int
    timestamp: datetime
    trigger: str
    result: str
    http_status: int | None
    error_message: str | None
    duration_ms: int | None
    created_version_id: int | None
    previous_version_id: int | None


class DiffLineOut(BaseModel):
    kind: str
    old_no: int | None
    new_no: int | None
    text: str


class FileDiffOut(BaseModel):
    path: str
    old_blob: str | None
    new_blob: str | None
    is_binary: bool
    additions: int
    deletions: int
    lines: list[DiffLineOut]


class DiffOut(BaseModel):
    version_id: int
    parent_version_id: int | None
    files: list[FileDiffOut]


class ScanTriggered(BaseModel):
    website_id: int
    scheduled: bool
