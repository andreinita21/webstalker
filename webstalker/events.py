"""In-process pub/sub for scan events.

Scans run in APScheduler's threadpool, so publishing has to be thread-safe.
Subscribers (the SSE endpoint) live on the FastAPI event loop, which we capture
once at startup so we can dispatch into it via `call_soon_threadsafe`.

Events are also kept in a bounded deque so a newly-connected client can backfill
recent history. This is what makes "close the tab, come back later" feel right:
the scan completed in the background, was logged to SQLite, and the last few
events are still in memory for the next viewer.
"""

import asyncio
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any


_RECENT_MAX = 200

_recent: deque[dict[str, Any]] = deque(maxlen=_RECENT_MAX)
_subscribers: list[asyncio.Queue] = []
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_seq = 0


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish(event: dict[str, Any]) -> dict[str, Any]:
    """Publish a scan event. Safe to call from any thread."""
    global _seq
    with _lock:
        _seq += 1
        full = {**event, "id": _seq, "ts": _now_iso()}
        _recent.append(full)
        subs = list(_subscribers)
    if _loop is not None:
        for q in subs:
            try:
                _loop.call_soon_threadsafe(_safe_put, q, full)
            except RuntimeError:
                # Loop may be closed during shutdown.
                pass
    return full


def _safe_put(q: asyncio.Queue, item: Any) -> None:
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        pass


def get_recent(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        items = list(_recent)
    if limit and len(items) > limit:
        items = items[-limit:]
    return items


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)
