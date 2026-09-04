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
import login_session
import socket


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
        # Always fetch fresh webcam frame before sending
        automation.fetch_webcam_image(force_refresh=True)

        if login_session.is_active():
            _emit("Using currently active live browser session to send streaks...")
            results = await login_session.run_streak_in_active_session(cfg["friends"], emit=_emit)
        else:
            results = await automation.send_streaks(cfg["friends"], emit=_emit)
        _state["last_run_results"] = results
        import time
        _state["last_run_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["logged_in"] = (automation.USER_DATA_DIR.exists() or automation.SESSION_FILE.exists())
    finally:
        _state["running"] = False



def _reschedule(schedule_time: str):
    """Update APScheduler job with a new HH:MM time without wiping other jobs."""
    try:
        _scheduler.remove_job("daily_streak")
    except Exception:
        pass
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

    # 15-minute webcam frame refresh
    def _refresh_cam():
        automation.fetch_webcam_image(force_refresh=True)

    _scheduler.add_job(
        _refresh_cam,
        trigger=CronTrigger(minute="*/15"),
        id="webcam_refresh_job",
        replace_existing=True,
    )
    # Fetch initial webcam frame on startup
    asyncio.create_task(asyncio.to_thread(_refresh_cam))

    _scheduler.start()
    yield
    _scheduler.shutdown()


app = FastAPI(title="SnapStreak", lifespan=lifespan)

# Serve static files (the web UI)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/webcam-feed")
async def get_webcam_feed():
    """Return the latest meteorology webcam frame."""
    from fastapi.responses import Response
    data = automation.fetch_webcam_image(force_refresh=True)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )




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

    # Detect server IP for noVNC link
    try:
        server_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        server_ip = "YOUR_SERVER_IP"

    return {
        "logged_in":       automation.SESSION_FILE.exists(),
        "login_active":    login_session.is_active(),
        "novnc_url":       f"http://{server_ip}:{login_session.NOVNC_PORT}/vnc.html?autoconnect=true&resize=scale",
        "running":         _state["running"],
        "last_run_time":   _state["last_run_time"],
        "last_run_results": _state["last_run_results"],
        "next_run":        next_run,
        "enabled":         cfg["enabled"],
        "friend_count":    len(cfg["friends"]),
    }


@app.post("/api/login/start")
async def login_start():
    """Start a visible browser session via VNC so you can log in manually."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="A send job is running.")
    if login_session.is_active():
        raise HTTPException(status_code=409, detail="Login session already active.")
    asyncio.create_task(_do_login_start())
    return {"message": "Starting login session..."}


async def _do_login_start():
    await login_session.start(emit=_emit)
    _emit("LOGIN_SESSION_READY")


@app.post("/api/login/save")
async def login_save():
    """Save the current VNC browser session as the active login."""
    if not login_session.is_active():
        raise HTTPException(status_code=400, detail="No active login session.")
    msg = await login_session.save(emit=_emit)
    _emit("LOGIN_DONE")
    return {"message": msg}


@app.post("/api/login/cancel")
async def login_cancel():
    """Cancel the active login session without saving."""
    await login_session.cancel(emit=_emit)
    return {"message": "Login session cancelled."}


@app.post("/api/login/clear-browser-data")
async def clear_browser_data():
    """Use CDP to clear the live browser's cache, cookies, and site storage."""
    cdp = login_session._state.get("cdp")
    page = login_session._state.get("page")
    context = login_session._state.get("context")

    if not cdp and not page:
        raise HTTPException(status_code=400, detail="No active browser session. Start a login session first.")

    try:
        # Clear network cache (images, scripts, stylesheets, etc.)
        await cdp.send("Network.clearBrowserCache")

        # Clear all site data for snapchat origins
        for origin in ["https://web.snapchat.com", "https://accounts.snapchat.com", "https://snapchat.com"]:
            try:
                await cdp.send("Storage.clearDataForOrigin", {
                    "origin": origin,
                    "storageTypes": "all"
                })
            except Exception:
                pass

        # Also clear cookies via context if available
        if context:
            await context.clear_cookies()

        _emit("🧹 Browser cache, cookies, and site data cleared successfully.")
        return {"ok": True, "message": "Browser cache and data cleared."}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


class SessionImportInput(BaseModel):
    data: str


@app.post("/api/session/import")
async def session_import(body: SessionImportInput):
    """Import cookies/storage state directly from standard JSON or cookie string."""
    raw = body.data.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty session data.")

    storage_state = {"cookies": [], "origins": []}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "cookies" in parsed:
            # Playwright storage state format
            storage_state = parsed
        elif isinstance(parsed, list):
            # Standard Cookie-Editor / EditThisCookie array format
            cookies = []
            for c in parsed:
                cookie = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain", ".snapchat.com"),
                    "path": c.get("path", "/"),
                    "expires": int(c.get("expirationDate", time.time() + 86400 * 180)) if c.get("expirationDate") else -1,
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "secure": bool(c.get("secure", True)),
                    "sameSite": "None" if c.get("sameSite") == "no_restriction" else (c.get("sameSite", "Lax").capitalize() if c.get("sameSite") else "Lax")
                }
                cookies.append(cookie)
            storage_state["cookies"] = cookies
            storage_state["origins"] = [{
                "origin": "https://web.snapchat.com",
                "localStorage": []
            }]
    except json.JSONDecodeError:
        # Cookie string format: key=val; key2=val2
        cookies = []
        for pair in raw.split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                cookies.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".snapchat.com",
                    "path": "/",
                    "expires": int(time.time() + 86400 * 180),
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax"
                })
        if not cookies:
            raise HTTPException(status_code=400, detail="Could not parse cookie string.")
        storage_state["cookies"] = cookies
        storage_state["origins"] = [{
            "origin": "https://web.snapchat.com",
            "localStorage": []
        }]

    # Save to session.json
    automation.SESSION_FILE.write_text(json.dumps(storage_state, indent=2))
    _state["logged_in"] = True
    _emit(f"✓ Successfully imported {len(storage_state.get('cookies', []))} session cookies! Server is now authenticated.")
    return {"ok": True, "cookies_count": len(storage_state.get("cookies", []))}



@app.post("/api/session/clear")
async def session_clear():
    """Delete all stored cookies, session data, and user-data-dir cache."""
    import shutil
    cleared = []

    # Remove session.json
    if automation.SESSION_FILE.exists():
        automation.SESSION_FILE.unlink()
        cleared.append("session.json")

    # Remove Playwright user-data-dir (profile cache, IndexedDB, cookies)
    if automation.USER_DATA_DIR.exists():
        shutil.rmtree(automation.USER_DATA_DIR, ignore_errors=True)
        cleared.append("browser profile cache")

    _state["logged_in"] = False
    _emit("🗑️ Cleared: " + (", ".join(cleared) if cleared else "nothing to clear") + ". All cookies and cache wiped.")
    return {"ok": True, "cleared": cleared}


@app.get("/api/login/screenshot")
async def login_screenshot():
    """Return the latest browser screenshot as a base64 JPEG."""
    return {
        "image": login_session.last_screenshot_b64(),
        "url":   login_session.current_url(),
        "active": login_session.is_active(),
    }


class ClickInput(BaseModel):
    x: int
    y: int

class TypeInput(BaseModel):
    text: str

class KeyInput(BaseModel):
    key: str

class NavInput(BaseModel):
    url: str


class FillInput(BaseModel):
    field: str
    value: str

@app.post("/api/login/fill")
async def login_fill(body: FillInput):
    res = await login_session.fill_field(body.field, body.value)
    return res

@app.post("/api/login/submit")
async def login_submit():
    res = await login_session.click_submit()
    return res

@app.post("/api/login/click")
async def login_click(body: ClickInput):
    await login_session.click(body.x, body.y)
    return {"ok": True}

@app.post("/api/login/type")
async def login_type(body: TypeInput):
    await login_session.type_text(body.text)
    return {"ok": True}

@app.post("/api/login/key")
async def login_key(body: KeyInput):
    await login_session.key_press(body.key)
    return {"ok": True}

@app.post("/api/login/navigate")
async def login_navigate(body: NavInput):
    await login_session.navigate(body.url)
    return {"ok": True}

@app.post("/api/login/upload-snap-here")
async def login_upload_snap_here():
    res = await login_session.upload_snap_to_chat()
    return res

@app.post("/api/macro/record/start")
async def macro_record_start():
    res = login_session.start_macro_recording()
    _emit("🔴 Macro recording started! Perform your actions on the live screen now...")
    return res

@app.post("/api/macro/record/stop")
async def macro_record_stop():
    res = login_session.stop_macro_recording()
    _emit(f"⏹️ Macro recording saved ({res['count']} steps recorded)!")
    return res

@app.get("/api/macro/info")
async def macro_info():
    return login_session.get_macro_info()


# ---------------------------------------------------------------------------
# Android ADB Routes
# ---------------------------------------------------------------------------
import android_client

@app.post("/api/android/connect")
async def android_connect():
    ok = await android_client.connect_adb(_emit)
    if ok:
        asyncio.create_task(android_client.start_screen_stream(_emit))
    return {"ok": ok, "connected": android_client.is_connected()}

@app.post("/api/android/tap")
async def android_tap(body: ClickInput):
    await android_client.tap(body.x, body.y)
    return {"ok": True}

@app.post("/api/android/type")
async def android_type(body: TypeInput):
    await android_client.type_text(body.text)
    return {"ok": True}

@app.post("/api/android/key")
async def android_key(body: KeyInput):
    await android_client.key_event(body.key)
    return {"ok": True}

@app.post("/api/android/launch")
async def android_launch():
    await android_client.launch_snapchat()
    return {"ok": True}


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


@app.get("/api/screenshot")
async def get_screenshot():
    """Return the last screenshot taken by the headless browser."""
    from fastapi.responses import FileResponse as FR, Response
    if not automation.SCREENSHOT_FILE.exists():
        raise HTTPException(status_code=404, detail="No screenshot yet. Trigger a send first.")
    return FR(
        str(automation.SCREENSHOT_FILE),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )



class CookieImport(BaseModel):
    cookies: list[dict]


@app.post("/api/import-cookies")
async def import_cookies(body: CookieImport):
    """
    Accept cookies exported from a browser extension (e.g. Cookie-Editor)
    and convert them into a Playwright storage_state session file.
    """
    if not body.cookies:
        raise HTTPException(status_code=400, detail="No cookies provided.")

    # Convert browser extension cookie format → Playwright storage_state format
    playwright_cookies = []
    for c in body.cookies:
        name  = c.get("name", "")
        value = c.get("value", "")
        if not name or not value:
            continue

        raw_domain = c.get("domain", ".snapchat.com")
        # Skip completely unrelated cookies
        if not any(x in raw_domain for x in ["snapchat", "snap.com"]):
            continue

        ss_raw = c.get("sameSite", c.get("samesite", "no_restriction"))
        ss_map = {
            "no_restriction": "None",
            "unspecified":    "None",
            "lax":            "Lax",
            "strict":         "Strict",
            "none":           "None",
        }
        same_site = ss_map.get(str(ss_raw).lower(), "None")

        exp = c.get("expirationDate", c.get("expires"))
        expires = int(exp) if isinstance(exp, (int, float)) and exp > 0 else None

        # Build cookie with ORIGINAL domain preserved exactly
        def make_cookie(domain: str) -> dict:
            ck: dict = {
                "name":     name,
                "value":    value,
                "domain":   domain,
                "path":     c.get("path", "/"),
                "secure":   bool(c.get("secure", True)),
                "httpOnly": bool(c.get("httpOnly", c.get("httponly", False))),
                "sameSite": same_site,
            }
            if expires:
                ck["expires"] = expires
            return ck

        # Add with original domain
        playwright_cookies.append(make_cookie(raw_domain))

        # Also add with .snapchat.com wildcard domain for maximum coverage
        if raw_domain != ".snapchat.com":
            playwright_cookies.append(make_cookie(".snapchat.com"))

        # Also add for web.snapchat.com specifically
        if "web.snapchat.com" not in raw_domain:
            playwright_cookies.append(make_cookie("web.snapchat.com"))

    session_state = {
        "cookies": playwright_cookies,
        "origins": [],
    }

    automation.SESSION_FILE.write_text(json.dumps(session_state, indent=2))
    _emit("✓ Cookies imported successfully. Session saved.")
    return {"message": f"Imported {len(playwright_cookies)} cookies. You're logged in!"}


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

