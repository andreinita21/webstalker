import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .. import events


router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def event_stream(request: Request):
    """Server-Sent Events stream of scan events.

    On connect we backfill the last ~50 events so a freshly-opened tab can show
    what already happened, then push live events as they occur.
    """
    queue = events.subscribe()

    async def gen():
        try:
            yield ":\n\n"  # initial comment to flush headers
            for ev in events.get_recent(50):
                yield f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/events/recent")
def recent_events(limit: int = 50):
    """JSON snapshot, used when the browser doesn't support EventSource."""
    return {"events": events.get_recent(max(1, min(limit, 200)))}
