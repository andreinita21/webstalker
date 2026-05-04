import difflib
import re
from dataclasses import dataclass, field
from typing import Callable


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffLine:
    kind: str  # "context", "added", "removed", "hunk"
    old_no: int | None
    new_no: int | None
    text: str


@dataclass
class FileDiff:
    path: str
    old_blob: str | None
    new_blob: str | None
    is_binary: bool
    additions: int = 0
    deletions: int = 0
    lines: list[DiffLine] = field(default_factory=list)


def _is_text(content: bytes) -> bool:
    if not content:
        return True
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def diff_text(a: str, b: str, *, context: int = 3) -> tuple[list[DiffLine], int, int]:
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    out: list[DiffLine] = []
    additions = 0
    deletions = 0
    old_no = 0
    new_no = 0

    for line in difflib.unified_diff(a_lines, b_lines, n=context, lineterm=""):
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            m = _HUNK_RE.match(line)
            if m:
                old_no = int(m.group(1)) - 1
                new_no = int(m.group(2)) - 1
            out.append(DiffLine(kind="hunk", old_no=None, new_no=None, text=line))
        elif line.startswith("+"):
            new_no += 1
            out.append(DiffLine(kind="added", old_no=None, new_no=new_no, text=line[1:]))
            additions += 1
        elif line.startswith("-"):
            old_no += 1
            out.append(
                DiffLine(kind="removed", old_no=old_no, new_no=None, text=line[1:])
            )
            deletions += 1
        elif line.startswith(" "):
            old_no += 1
            new_no += 1
            out.append(
                DiffLine(kind="context", old_no=old_no, new_no=new_no, text=line[1:])
            )
        else:
            old_no += 1
            new_no += 1
            out.append(
                DiffLine(kind="context", old_no=old_no, new_no=new_no, text=line)
            )

    return out, additions, deletions


def diff_versions(
    old_entries: list[tuple[str, str | None, str | None]],
    new_entries: list[tuple[str, str | None, str | None]],
    blob_reader: Callable[[str], bytes],
) -> list[FileDiff]:
    """Compute file-by-file diffs between two snapshot trees.

    Each entry is (path, blob_sha, content_type).
    """
    old_map = {e[0]: e for e in old_entries}
    new_map = {e[0]: e for e in new_entries}
    files: list[FileDiff] = []

    for path in sorted(set(old_map) | set(new_map)):
        old_sha = old_map.get(path, (path, None, None))[1]
        new_sha = new_map.get(path, (path, None, None))[1]
        if old_sha == new_sha:
            continue

        old_bytes = blob_reader(old_sha) if old_sha else b""
        new_bytes = blob_reader(new_sha) if new_sha else b""
        text_old = _is_text(old_bytes)
        text_new = _is_text(new_bytes)

        if text_old and text_new:
            lines, adds, dels = diff_text(
                old_bytes.decode("utf-8"), new_bytes.decode("utf-8")
            )
            files.append(
                FileDiff(
                    path=path,
                    old_blob=old_sha,
                    new_blob=new_sha,
                    is_binary=False,
                    additions=adds,
                    deletions=dels,
                    lines=lines,
                )
            )
        else:
            files.append(
                FileDiff(
                    path=path,
                    old_blob=old_sha,
                    new_blob=new_sha,
                    is_binary=True,
                    additions=0,
                    deletions=0,
                    lines=[],
                )
            )

    return files
