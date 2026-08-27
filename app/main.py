"""
main.py – FastAPI application.

Endpoints:
  GET  /            → web UI (static HTML)
  GET  /api/config  → current settings
  POST /api/config  → update settings
  POST /api/login   → trigger headless browser login flow
  GET  /api/status  → login status, next run time, last results
  POST /api/send    → trigger an immediate streak send
  POST /api/upload-snap  → upload a custom snap image
  GET  /api/logs    → last 100 log lines
  WS   /ws/stream   → live log streaming during send
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import automation

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_state: dict[str, Any] = {
    "logged_in": automation.SESSION_FILE.exists(),
    "last_run_time": None,
    "last_run_results": {},
    "running": False,
}

_ws_clients: list[WebSocket] = []
_scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _emit(msg: str):
    """Broadcast a log line to all connected WebSocket clients."""
    for ws in list(_ws_clients):
        asyncio.create_task(ws.send_text(msg))


async def _do_send():
    if _state["running"]:
        return
    _state["running"] = True
    cfg = config.load()
    try:
        results = await automation.send_streaks(cfg["friends"], emit=_emit)
        _state["last_run_results"] = results
        import time
        _state["last_run_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["logged_in"] = automation.SESSION_FILE.exists()
    finally:
        _state["running"] = False


def _reschedule(schedule_time: str):
    """Update APScheduler job with a new HH:MM time."""
    _scheduler.remove_all_jobs()
    hour, minute = schedule_time.split(":")
    _scheduler.add_job(
        _do_send,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id="daily_streak",
        replace_existing=True,
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config.load()
    if cfg["enabled"]:
        _reschedule(cfg["schedule_time"])
    _scheduler.start()
    yield
    _scheduler.shutdown()


app = FastAPI(title="SnapStreak", lifespan=lifespan)

# Serve static files (the web UI)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Routes – UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = STATIC_DIR / "index.html"
    return HTMLResponse(html_file.read_text())


# ---------------------------------------------------------------------------
# Routes – API
# ---------------------------------------------------------------------------
class ConfigUpdate(BaseModel):
    friends: list[str] | None = None
    schedule_time: str | None = None
    enabled: bool | None = None


@app.get("/api/config")
async def get_config():
    return config.load()


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    cfg = config.load()
    if body.friends is not None:
        # Strip whitespace and @ symbols
        cfg["friends"] = [u.strip().lstrip("@") for u in body.friends if u.strip()]
    if body.schedule_time is not None:
        cfg["schedule_time"] = body.schedule_time
        if cfg["enabled"]:
            _reschedule(cfg["schedule_time"])
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
        if cfg["enabled"]:
            _reschedule(cfg["schedule_time"])
        else:
            _scheduler.remove_all_jobs()
    config.save(cfg)
    return cfg


@app.get("/api/status")
async def get_status():
    cfg = config.load()
    next_run = None
    job = _scheduler.get_job("daily_streak")
    if job:
        next_run = str(job.next_run_time)
    return {
        "logged_in": automation.SESSION_FILE.exists(),
        "running": _state["running"],
        "last_run_time": _state["last_run_time"],
        "last_run_results": _state["last_run_results"],
        "next_run": next_run,
        "enabled": cfg["enabled"],
        "friend_count": len(cfg["friends"]),
    }


@app.post("/api/login")
async def trigger_login():
    """
    Tells the user to connect to the server display / VNC to complete login.
    Since we're headless on a server, we use a virtual display (Xvfb) and 
    a VNC/noVNC session — OR we return a message explaining they need X11 
    forwarding. The simplest server approach: use --no-sandbox visible browser
    via virtual display.
    """
    if _state["running"]:
        raise HTTPException(status_code=409, detail="A send job is currently running.")
    
    asyncio.create_task(_run_login())
    return {"message": "Login browser session started. Check the /api/logs endpoint for progress."}


async def _run_login():
    msg = await automation.manual_login_and_save(emit=_emit)
    _state["logged_in"] = automation.SESSION_FILE.exists()
    _emit(f"LOGIN_DONE: {msg}")


@app.post("/api/send")
async def trigger_send():
    """Immediately trigger a streak send."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="Already running.")
    asyncio.create_task(_do_send())
    return {"message": "Streak send started. Connect to /ws/stream for live updates."}


@app.post("/api/upload-snap")
async def upload_snap(file: UploadFile):
    """Upload a custom image to use as the streak snap."""
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only PNG/JPEG/WEBP images allowed.")
    content = await file.read()
    automation.SNAP_IMAGE.write_bytes(content)
    cfg = config.load()
    cfg["snap_image_custom"] = True
    config.save(cfg)
    return {"message": "Snap image updated."}


@app.get("/api/logs")
async def get_logs():
    if not automation.LOG_FILE.exists():
        return {"lines": []}
    lines = automation.LOG_FILE.read_text().splitlines()
    return {"lines": lines[-100:]}  # last 100 lines


# ---------------------------------------------------------------------------
# WebSocket – live log streaming
# ---------------------------------------------------------------------------
@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)
