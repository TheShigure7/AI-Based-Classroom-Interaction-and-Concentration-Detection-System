"""WebSocket realtime updates for the classroom page."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.runtime import runtime


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/classroom/realtime")
async def classroom_realtime_websocket(websocket: WebSocket) -> None:
    """Push classroom summary updates to the frontend."""
    await websocket.accept()
    try:
        while True:
            event = runtime.get_realtime_event()
            await websocket.send_json(event.model_dump())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
