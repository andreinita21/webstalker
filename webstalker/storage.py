import hashlib
import os
import re
from pathlib import Path

from .config import settings


_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_sha(sha: str) -> None:
    if not _HEX_RE.match(sha):
        raise ValueError("invalid sha256 hex string")


def blob_path(sha: str) -> Path:
    _validate_sha(sha)
    # Two-level fan-out: blobs/aa/bbcc...
    return settings.blob_dir / sha[:2] / sha[2:]


def write_blob(content: bytes) -> str:
    sha = compute_sha256(content)
    path = blob_path(sha)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, path)
    return sha


def read_blob(sha: str) -> bytes:
    return blob_path(sha).read_bytes()


def blob_exists(sha: str) -> bool:
    return blob_path(sha).exists()
