import re
from typing import Iterable

from bs4 import BeautifulSoup


# Patterns used when ignore_timestamps is enabled.
TIMESTAMP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
    ),  # ISO-8601
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?\b", re.I),
    re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b"
    ),
    re.compile(r"\b1[5-9]\d{8}\b"),  # Unix timestamps in seconds (since ~2017)
    re.compile(r"\b1[5-9]\d{11}\b"),  # Unix timestamps in milliseconds
]

WHITESPACE_RE = re.compile(r"\s+")


def normalize_html(
    content: str,
    *,
    ignore_whitespace: bool = True,
    ignore_selectors: Iterable[str] = (),
    ignore_url_patterns: Iterable[str] = (),
    ignore_timestamps: bool = True,
) -> str:
    """Apply ignore rules and return normalized text used for hashing/comparison."""
    text = content

    selectors = [s for s in ignore_selectors if s and s.strip()]
    if selectors:
        try:
            soup = BeautifulSoup(text, "lxml")
            for sel in selectors:
                try:
                    for el in soup.select(sel):
                        el.decompose()
                except Exception:
                    # Bad selector — skip silently
                    continue
            text = str(soup)
        except Exception:
            # If parsing fails, fall back to the raw text
            pass

    for pattern in ignore_url_patterns:
        if not pattern or not pattern.strip():
            continue
        try:
            text = re.sub(pattern, "<!-- ignored-url -->", text)
        except re.error:
            continue

    if ignore_timestamps:
        for pat in TIMESTAMP_PATTERNS:
            text = pat.sub("<!-- timestamp -->", text)

    if ignore_whitespace:
        text = WHITESPACE_RE.sub(" ", text)
        # Drop whitespace adjacent to tag boundaries — most HTML treats it as
        # insignificant, and keeping it inflates noise from formatter changes.
        text = re.sub(r"\s*<", "<", text)
        text = re.sub(r">\s*", ">", text)
        text = text.strip()

    return text


def split_lines(text: str) -> list[str]:
    return [s.strip() for s in (text or "").splitlines() if s.strip()]
