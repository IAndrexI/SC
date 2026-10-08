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
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("snapstreak")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import io
import zipfile

import config
import automation
import login_session
import bliss_client
import socket


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "desktop_data"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR)))
STATIC_DIR = Path(__file__).resolve().parent / "static"
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_init_logged_in = False
try:
    _init_logged_in = automation.SESSION_FILE.exists()
except Exception:
    pass

_state: dict[str, Any] = {
    "logged_in": _init_logged_in,
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
    mode = cfg.get("mode", "web")
    friends = cfg.get("friends") or ["*//Eric\\\\*", "Dylan"]
    selection_method = cfg.get("selection_method", "auto")
    try:
        # Always fetch fresh webcam frame before sending
        automation.fetch_webcam_image(force_refresh=True)

        if mode == "bliss":
            _emit("Using Bliss OS Android Automation to send streaks...")
            results = await bliss_client.send_streaks(friends, emit=_emit)
        elif login_session.is_active():
            _emit("Using currently active live browser session to send streaks...")
            results = await login_session.run_streak_in_active_session(friends, emit=_emit)
        else:
            _emit(f"Using desktop browser emulation (Selection: {selection_method.upper()}) to send streaks...")
            results = await automation.send_streaks(
                friends=friends,
                selection_method=selection_method,
                emit=_emit,
            )

        _state["last_run_results"] = results
        import time
        _state["last_run_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["logged_in"] = automation.SESSION_FILE.exists()
    finally:
        _state["running"] = False



def _reschedule(schedule_times: list[str] | str):
    """Update APScheduler jobs with HH:MM times without wiping other jobs."""
    # Remove existing daily streak jobs
    for job in list(_scheduler.get_jobs()):
        if job.id == "daily_streak" or job.id.startswith("daily_streak_"):
            try:
                _scheduler.remove_job(job.id)
            except Exception:
                pass

    if isinstance(schedule_times, str):
        times = [schedule_times]
    elif isinstance(schedule_times, list):
        times = schedule_times
    else:
        times = ["09:00"]

    for idx, st in enumerate(times):
        try:
            parts = st.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            job_id = f"daily_streak_{idx}" if len(times) > 1 else "daily_streak"
            _scheduler.add_job(
                _do_send,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                replace_existing=True,
            )
            log.info(f"Scheduled {job_id} at {hour:02d}:{minute:02d}")
        except Exception as e:
            log.error(f"Failed to schedule daily streak with {st}: {e}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        cfg = config.load()
        if cfg.get("enabled", True):
            _reschedule(cfg.get("schedule_times") or cfg.get("schedule_time", "09:00"))
    except Exception as e:
        log.error(f"Failed to load initial schedule: {e}")

    # 15-minute webcam frame refresh
    def _refresh_cam():
        try:
            automation.fetch_webcam_image(force_refresh=True)
        except Exception:
            pass

    try:
        _scheduler.add_job(
            _refresh_cam,
            trigger=CronTrigger(minute="*/15"),
            id="webcam_refresh_job",
            replace_existing=True,
        )
        # Fetch initial webcam frame on startup in background
        asyncio.create_task(asyncio.to_thread(_refresh_cam))
    except Exception:
        pass

    try:
        _scheduler.start()
    except Exception as e:
        log.error(f"Scheduler failed to start: {e}")

    # Autostart emulated background browser with SnapStreak extension
    try:
        cfg = config.load()
        if cfg.get("browser_autostart", True) and cfg.get("mode", "web") == "web":
            async def _delayed_browser_autostart():
                await asyncio.sleep(2.5)
                if not login_session.is_active() and not login_session.is_starting():
                    log.info("Launching background desktop browser session with SnapStreak extension...")
                    try:
                        await login_session.start(emit=_emit)
                        _emit("LOGIN_SESSION_READY")
                    except Exception as err:
                        log.warning(f"Background browser autostart notice: {err}")
            asyncio.create_task(_delayed_browser_autostart())
    except Exception as e:
        log.warning(f"Failed to schedule browser autostart: {e}")

    yield

    try:
        _scheduler.shutdown()
    except Exception:
        pass


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
    candidates = [
        STATIC_DIR / "index.html",
        Path(__file__).resolve().parent / "static" / "index.html",
        Path("/opt/sc/linux-server/app/static/index.html"),
        Path("/opt/sc/app/static/index.html"),
        Path("/opt/snapstreak/linux-server/app/static/index.html"),
    ]
    for p in candidates:
        if p.exists():
            return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>SnapStreak is running</h2><p>Static UI loading...</p>", status_code=200)


# ---------------------------------------------------------------------------
# Routes – API
# ---------------------------------------------------------------------------
class ConfigUpdate(BaseModel):
    friends: list[str] | None = None
    schedule_time: str | None = None
    schedule_times: list[str] | None = None
    enabled: bool | None = None
    mode: str | None = None
    selection_method: str | None = None
    browser_engine: str | None = None
    step_delay: int | None = None
    bliss_host: str | None = None
    bliss_port: int | None = None


@app.get("/api/config")
async def get_config():
    try:
        return config.load()
    except Exception:
        return config._DEFAULTS


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    cfg = config.load()
    if body.friends is not None:
        # Strip whitespace and @ symbols
        cfg["friends"] = [u.strip().lstrip("@") for u in body.friends if u.strip()]
    if body.schedule_times is not None:
        cfg["schedule_times"] = [t.strip() for t in body.schedule_times if t.strip()]
        if cfg["schedule_times"]:
            cfg["schedule_time"] = cfg["schedule_times"][0]
        if cfg["enabled"]:
            _reschedule(cfg["schedule_times"])
    elif body.schedule_time is not None:
        cfg["schedule_time"] = body.schedule_time.strip()
        cfg["schedule_times"] = [body.schedule_time.strip()]
        if cfg["enabled"]:
            _reschedule(cfg["schedule_time"])
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
        if cfg["enabled"]:
            _reschedule(cfg.get("schedule_times") or cfg.get("schedule_time", "09:00"))
        else:
            _scheduler.remove_all_jobs()
    if body.mode is not None:
        cfg["mode"] = body.mode
    if body.browser_engine is not None:
        cfg["browser_engine"] = body.browser_engine
    if body.selection_method is not None:
        cfg["selection_method"] = body.selection_method
    if body.step_delay is not None:
        cfg["step_delay"] = int(body.step_delay)
    if body.bliss_host is not None:
        cfg["bliss_host"] = body.bliss_host.strip()
    if body.bliss_port is not None:
        cfg["bliss_port"] = int(body.bliss_port)
    config.save(cfg)
    return cfg


@app.get("/api/status")
async def get_status(request: Request):
    try:
        cfg = config.load()
        next_run = None
        next_runs = []
        for job in _scheduler.get_jobs():
            if job.id == "daily_streak" or job.id.startswith("daily_streak_"):
                if job.next_run_time:
                    next_runs.append(str(job.next_run_time))
        if next_runs:
            next_runs.sort()
            next_run = next_runs[0]

        host_ip = request.url.hostname or "localhost"
        novnc_url = f"http://{host_ip}:{login_session.NOVNC_PORT}/vnc.html?autoconnect=true&resize=scale&path=websockify"

        is_logged_in = False
        try:
            if cfg.get("mode") == "bliss":
                is_logged_in = bliss_client.is_connected()
            else:
                is_logged_in = automation.SESSION_FILE.exists()
        except Exception:
            pass

        return {
            "logged_in":       is_logged_in,
            "login_active":    login_session.is_active(),
            "login_starting":  login_session.is_starting(),
            "novnc_url":       novnc_url,
            "running":         _state.get("running", False),
            "last_run_time":   _state.get("last_run_time"),
            "last_run_results": _state.get("last_run_results", {}),
            "next_run":        next_run,
            "next_runs":       next_runs,
            "schedule_times":  cfg.get("schedule_times") or [cfg.get("schedule_time", "09:00")],
            "enabled":         cfg.get("enabled", True),
            "friend_count":    len(cfg.get("friends", [])),
            "mode":            cfg.get("mode", "web"),
            "bliss_connected": bliss_client.is_connected() if hasattr(bliss_client, "is_connected") else False,
            "bliss_target":    bliss_client.get_target_device() if hasattr(bliss_client, "get_target_device") else "127.0.0.1:5555",
            "selection_method": cfg.get("selection_method", "auto"),
            "awaiting_confirmation": _state.get("awaiting_confirmation", False),
            "paused":          _state.get("paused", False),
        }
    except Exception as ex:
        host_ip = request.url.hostname or "localhost"
        return {
            "error": str(ex),
            "logged_in": False,
            "login_active": False,
            "novnc_url": f"http://{host_ip}:6080/vnc.html?autoconnect=true&resize=scale",
            "running": False,
            "last_run_time": None,
            "last_run_results": {},
            "next_run": None,
            "enabled": False,
            "friend_count": 0,
            "mode": "web",
            "bliss_connected": False,
            "bliss_target": "127.0.0.1:5555",
            "selection_method": "auto",
        }



class LoginStartInput(BaseModel):
    engine: str | None = None


@app.post("/api/login/start")
async def login_start(body: LoginStartInput | None = None):
    """Start a visible browser session via VNC so you can log in manually."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="A send job is running.")
    if login_session.is_active():
        raise HTTPException(status_code=409, detail="Login session already active.")
    if login_session.is_starting():
        raise HTTPException(status_code=409, detail="Browser is already launching — please wait.")
    engine = body.engine if body else None
    asyncio.create_task(_do_login_start(engine=engine))
    return {"message": "Starting login session..."}


async def _do_login_start(engine: str | None = None):
    try:
        await login_session.start(emit=_emit, engine=engine)
        _emit("LOGIN_SESSION_READY")
    except Exception as ex:
        _emit(f"✗ Failed to start browser session: {ex}")


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


class GoogleLoginInput(BaseModel):
    email: str | None = None


@app.post("/api/login/google")
async def login_google(body: GoogleLoginInput | None = None):
    """Click Continue with Google in the active browser session and optionally fill email."""
    if not login_session.is_active():
        # Proactively start browser if not yet launched
        _emit("Launching browser for Google Sign-In...")
        try:
            await login_session.start(emit=_emit)
            await asyncio.sleep(2.0)
        except Exception as ex:
            raise HTTPException(status_code=500, detail=str(ex))

    email = body.email if body else None
    return await login_session.click_google_login(email=email, emit=_emit)



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
                raw_ss = c.get("sameSite")
                is_secure = bool(c.get("secure", True))
                if raw_ss is None or str(raw_ss).lower() in ("null", "none", "no_restriction", "unspecified"):
                    same_site = "None" if is_secure else "Lax"
                elif str(raw_ss).lower() in ("lax", "strict"):
                    same_site = str(raw_ss).capitalize()
                else:
                    same_site = "Lax"

                exp = c.get("expirationDate", c.get("expires"))
                expires = int(exp) if exp and isinstance(exp, (int, float)) and exp > 0 else -1

                cookie = {
                    "name": str(c.get("name", "")).strip(),
                    "value": str(c.get("value", "")),
                    "domain": str(c.get("domain", ".snapchat.com")),
                    "path": str(c.get("path", "/")),
                    "expires": expires,
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "secure": is_secure,
                    "sameSite": same_site
                }
                if cookie["name"]:
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
    try:
        automation.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        automation.SESSION_FILE.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")
        _state["logged_in"] = True
    except Exception as ex:
        _emit(f"⚠ Warning: Could not write session.json: {ex}")
        _state["logged_in"] = True

    # If live browser session is active, inject cookies immediately and navigate
    if login_session.is_active():
        try:
            ctx = login_session._state.get("context")
            pg = login_session._state.get("page")
            if ctx and storage_state.get("cookies"):
                await ctx.add_cookies(storage_state["cookies"])
                _emit("✓ Cookies injected into active browser session!")
                if pg:
                    await pg.goto("https://web.snapchat.com/", timeout=15000)
                    _emit("✓ Navigated to web.snapchat.com with imported cookies.")
        except Exception as ex:
            _emit(f"⚠ Live injection notice: {ex}")

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
    return await login_session.navigate(body.url)

@app.post("/api/login/back")
async def login_back():
    return await login_session.go_back()

@app.post("/api/login/forward")
async def login_forward():
    return await login_session.go_forward()

@app.post("/api/login/reload")
async def login_reload():
    return await login_session.reload_page()

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
# Bliss OS Android ADB Routes
# ---------------------------------------------------------------------------
class BlissConnectInput(BaseModel):
    host: str | None = None
    port: int | None = None

@app.post("/api/bliss/connect")
async def bliss_connect(body: BlissConnectInput | None = None):
    host = body.host if body else None
    port = body.port if body else None
    ok = await bliss_client.connect(host=host, port=port, emit=_emit)
    if ok:
        asyncio.create_task(bliss_client.start_screen_stream(_emit))
    return {
        "ok": ok,
        "connected": bliss_client.is_connected(),
        "target": bliss_client.get_target_device(),
    }

@app.post("/api/bliss/disconnect")
async def bliss_disconnect():
    bliss_client.stop_screen_stream()
    return {"ok": True}

@app.post("/api/bliss/tap")
async def bliss_tap(body: ClickInput):
    await bliss_client.tap(body.x, body.y)
    return {"ok": True}

@app.post("/api/bliss/type")
async def bliss_type(body: TypeInput):
    await bliss_client.type_text(body.text)
    return {"ok": True}

@app.post("/api/bliss/key")
async def bliss_key(body: KeyInput):
    await bliss_client.key_event(body.key)
    return {"ok": True}

@app.post("/api/bliss/launch")
async def bliss_launch():
    ok = await bliss_client.launch_snapchat(_emit)
    return {"ok": ok}

@app.post("/api/bliss/install-apk")
async def bliss_install_apk(file: UploadFile):
    """Upload and install an APK file directly onto Bliss OS."""
    if not file.filename.endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files can be installed.")
    content = await file.read()
    temp_apk = DATA_DIR / file.filename
    temp_apk.write_bytes(content)
    try:
        ok = await bliss_client.install_apk(str(temp_apk), emit=_emit)
        return {"ok": ok, "filename": file.filename}
    finally:
        try:
            temp_apk.unlink(missing_ok=True)
        except Exception:
            pass

class ShellInput(BaseModel):
    command: str

@app.post("/api/bliss/shell")
async def bliss_shell(body: ShellInput):
    """Execute raw Linux/Termux commands inside Bliss OS."""
    ret, stdout, stderr = await bliss_client.exec_shell(body.command)
    return {
        "exit_code": ret,
        "stdout": stdout,
        "stderr": stderr,
    }

@app.post("/api/bliss/push-cam")
async def bliss_push_cam():
    ok = await bliss_client.push_webcam_to_gallery(_emit)
    return {"ok": ok}

@app.post("/api/bliss/macro/record/start")
async def bliss_macro_record_start():
    res = bliss_client.start_macro_recording()
    _emit("🔴 Bliss OS macro recording started! Tap on the live screen to record...")
    return res

@app.post("/api/bliss/macro/record/stop")
async def bliss_macro_record_stop():
    res = bliss_client.stop_macro_recording()
    _emit(f"⏹️ Bliss OS macro recording saved ({res['count']} steps recorded)!")
    return res

@app.get("/api/bliss/macro/info")
async def bliss_macro_info():
    return bliss_client.get_macro_info()

# Backwards compatibility with generic android endpoints
@app.post("/api/android/connect")
async def android_connect():
    return await bliss_connect(None)

@app.post("/api/android/tap")
async def android_tap(body: ClickInput):
    return await bliss_tap(body)

@app.post("/api/android/type")
async def android_type(body: TypeInput):
    return await bliss_type(body)

@app.post("/api/android/key")
async def android_key(body: KeyInput):
    return await bliss_key(body)

@app.post("/api/android/launch")
async def android_launch():
    return await bliss_launch()


# ---------------------------------------------------------------------------
# Extension bridge callbacks
# ---------------------------------------------------------------------------
class ExtensionLogInput(BaseModel):
    message: str
    type: str | None = "info"


@app.post("/api/extension/log")
async def extension_log(body: ExtensionLogInput):
    """Receive live log entries directly from the in-browser SnapStreak Extension."""
    level_icon = "✓" if body.type == "success" else ("✗" if body.type == "err" else "ℹ")
    formatted = f"🧩 [Extension] {level_icon} {body.message}"
    _emit(formatted)
    try:
        automation.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(automation.LOG_FILE, "a", encoding="utf-8") as f:
            import time
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {formatted}\n")
    except Exception:
        pass
    return {"ok": True}


class ExtensionStatusInput(BaseModel):
    status: str
    recipientsCount: int | None = 0
    error: str | None = None
    timestamp: str | None = None


@app.post("/api/extension/status")
async def extension_status(body: ExtensionStatusInput):
    """Receive execution status callbacks from the in-browser SnapStreak Extension."""
    import time
    _state["last_run_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if body.status == "success":
        cfg = config.load()
        friends = cfg.get("friends") or ["*//Eric\\\\*", "Dylan"]
        _state["last_run_results"] = {f: "ok" for f in friends}
        _emit(f"🎉 Extension reported streaks sent successfully! ({body.recipientsCount} verified)")
    else:
        _state["last_run_results"] = {"error": body.error or "failed"}
        _emit(f"⚠ Extension reported streak error: {body.error}")
    return {"ok": True}


@app.get("/api/extension/info")
async def get_extension_info():
    """Return manifest and status info for the SnapStreak browser extension."""
    ext_dir = Path(__file__).resolve().parent.parent / "extension"
    manifest_path = ext_dir / "manifest.json"
    manifest_data = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception:
            pass

    return {
        "installed": ext_dir.exists(),
        "version": manifest_data.get("version", "4.1.0"),
        "name": manifest_data.get("name", "SnapStreak Auto"),
        "description": manifest_data.get("description", "Snapchat Streak Automation Extension"),
        "active_session": login_session.is_active(),
        "files": [f.name for f in ext_dir.glob("*.*")] if ext_dir.exists() else []
    }


@app.get("/api/extension/download")
async def download_extension_zip():
    """Package the SnapStreak browser extension directory as a downloadable ZIP."""
    ext_dir = Path(__file__).resolve().parent.parent / "extension"
    if not ext_dir.exists():
        raise HTTPException(status_code=404, detail="Extension directory not found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(ext_dir):
            for file in files:
                file_path = Path(root) / file
                archive_name = file_path.relative_to(ext_dir)
                zf.write(file_path, arcname=str(archive_name))
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="snapstreak-extension.zip"'}
    )


@app.post("/api/browser/toggle-extension")
async def toggle_browser_extension():
    """Toggle or re-inject the SnapStreak Extension HUD in the active browser session."""
    p = login_session.get_page()
    if not p:
        raise HTTPException(status_code=400, detail="No active browser session")
    try:
        ok = await login_session.ensure_extension_active(p, force_toggle=True)
        return {"ok": ok, "message": "Extension toggled in active browser"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}




@app.post("/api/task/awaiting-confirmation")
async def task_awaiting_confirmation(request: Request):
    """Callback when extension pauses at final send step awaiting user confirmation."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    _state["awaiting_confirmation"] = True
    _emit("🛑 [Awaiting Confirmation] Snap prepared! Final send paused waiting for your manual confirmation. Click 'Send Final Snap Now' in UI.")
    return {"ok": True}


@app.post("/api/send-preview")
async def trigger_send_preview():
    """Trigger a streak dry-run preview: executes all steps up to Send button and pauses."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="A task is already running.")

    async def _do_preview():
        _state["running"] = True
        _state["awaiting_confirmation"] = False
        _state["paused"] = False
        try:
            cfg = config.load()
            friends = cfg.get("friends") or ["*//Eric\\\\*", "Dylan"]
            automation.fetch_webcam_image(force_refresh=True)

            if login_session.is_active():
                _emit("🧪 Running Streak Sample Preview in active browser session (pausing before final Send)...")
                await login_session.run_streak_in_active_session(friends=friends, is_preview=True, emit=_emit)
            else:
                _emit("⚠ Starting emulated browser for preview...")
                await login_session.start(emit=_emit)
                await asyncio.sleep(2)
                await login_session.run_streak_in_active_session(friends=friends, is_preview=True, emit=_emit)
        finally:
            _state["running"] = False

    asyncio.create_task(_do_preview())
    return {"message": "Sample preview started. Automation will pause before final Send step."}


@app.post("/api/task/pause")
async def task_pause():
    """Pause currently executing streak automation."""
    _state["paused"] = True
    res = await login_session.pause_task(emit=_emit)
    return res


@app.post("/api/task/resume")
async def task_resume():
    """Resume currently paused streak automation."""
    _state["paused"] = False
    res = await login_session.resume_task(emit=_emit)
    return res


@app.post("/api/task/stop")
async def task_stop():
    """Stop/cancel running streak automation."""
    _state["running"] = False
    _state["paused"] = False
    _state["awaiting_confirmation"] = False
    res = await login_session.stop_task(emit=_emit)
    return res


@app.post("/api/task/confirm-send")
async def task_confirm_send():
    """Approve and fire final Send button from preview/confirmation state."""
    _state["awaiting_confirmation"] = False
    res = await login_session.confirm_send_task(emit=_emit)
    return res


@app.post("/api/send")
async def trigger_send():
    """Immediately trigger a streak send."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="Already running.")
    _state["awaiting_confirmation"] = False
    _state["paused"] = False
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
        is_secure = bool(c.get("secure", True))
        if ss_raw is None or str(ss_raw).lower() in ("null", "none", "no_restriction", "unspecified"):
            same_site = "None" if is_secure else "Lax"
        elif str(ss_raw).lower() in ("lax", "strict"):
            same_site = str(ss_raw).capitalize()
        else:
            same_site = "Lax"

        exp = c.get("expirationDate", c.get("expires"))
        expires = int(exp) if isinstance(exp, (int, float)) and exp > 0 else None

        # Build cookie with ORIGINAL domain preserved exactly
        def make_cookie(domain: str) -> dict:
            ck: dict = {
                "name":     name,
                "value":    value,
                "domain":   domain,
                "path":     c.get("path", "/"),
                "secure":   is_secure,
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

    automation.SESSION_FILE.write_text(json.dumps(session_state, indent=2), encoding="utf-8")
    _emit("✓ Cookies imported successfully. Session saved.")

    # Live inject into active browser if running
    if login_session.is_active():
        try:
            ctx = login_session._state.get("context")
            pg = login_session._state.get("page")
            if ctx and playwright_cookies:
                await ctx.add_cookies(playwright_cookies)
                _emit("✓ Injected cookies into live browser session.")
                if pg:
                    await pg.goto("https://web.snapchat.com/", timeout=25000)
                    _emit("✓ Navigated to web.snapchat.com with imported cookies.")
        except Exception as ex:
            _emit(f"⚠ Live injection notice: {ex}")

    return {"message": f"Imported {len(playwright_cookies)} cookies. You're logged in!"}


@app.get("/api/logs")
async def get_logs(limit: int = 1000):
    if not automation.LOG_FILE.exists():
        return {"lines": []}
    lines = automation.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if limit > 0 and len(lines) > limit:
        return {"lines": lines[-limit:]}
    return {"lines": lines}


@app.post("/api/logs/clear")
async def clear_logs():
    if automation.LOG_FILE.exists():
        automation.LOG_FILE.write_text("", encoding="utf-8")
    _emit("🧹 Logs cleared.")
    return {"ok": True}


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

