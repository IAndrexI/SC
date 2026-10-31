"""
main.py – FastAPI Web Studio Server + APScheduler + WebSocket Screencast & Control API.
"""

import asyncio
import base64
import importlib
import json
import os
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Set

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import automation
from automation import (
    DATA_DIR,
    LOG_FILE,
    SCREENSHOT_FILE,
    SESSION_FILE,
    SNAP_IMAGE,
    WEBCAM_FILE,
    WEBCAM_URL,
    MACRO_FILE,
    fetch_webcam_image,
    get_webcam_data_url,
    inject_webcam_frame_into_page,
    send_streaks,
    preview_streaks,
    get_execution_state,
    request_stop,
    toggle_pause,
    log,
)
import login_session
import diagnostics

_ws_clients: Set[WebSocket] = set()
_last_run: str | None = None
_last_results: dict = {}
_running: bool = False
_preview_data: dict = {"screenshot": "", "timestamp": None, "results": {}}
_loop: asyncio.AbstractEventLoop | None = None

scheduler = AsyncIOScheduler()


def _broadcast(line: str):
    if _loop is None:
        return
    for ws in list(_ws_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, line), _loop)


async def _safe_send(ws: WebSocket, text: str):
    try:
        await ws.send_text(text)
    except Exception:
        _ws_clients.discard(ws)


async def _scheduled_job(force: bool = False):
    global _last_run, _last_results, _running
    if _running:
        log("WARN", "Send already in progress — skipping duplicate trigger.", _broadcast)
        return

    cfg = config.load()
    if not force and not cfg.get("enabled", True):
        log("INFO", "Scheduled run skipped (schedule disabled in config).", _broadcast)
        return

    friends = cfg.get("friends", [])
    streak_mode = cfg.get("streak_mode", "ai_steps")
    selection_method = cfg.get("selection_method", "direct")

    if not friends and streak_mode != "macro":
        log("WARN", "No friends configured — add streak recipients first.", _broadcast)
        return

    _running = True
    _last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log("INFO", f"🚀 Starting Auto Streak Maker (Mode: {streak_mode.upper()}, Method: {selection_method})...", _broadcast)
        _last_results = await send_streaks(
            friends=friends,
            emit=_broadcast,
            selection_method=selection_method,
            streak_mode=streak_mode,
        )
    except Exception as ex:
        log("ERROR", f"Automation error: {ex}", _broadcast)
        _last_results = {"error": str(ex)}
    finally:
        _running = False


def _reschedule(schedule_times: list[str] | str):
    for job in list(scheduler.get_jobs()):
        if job.id.startswith("daily_streaks"):
            scheduler.remove_job(job.id)

    if isinstance(schedule_times, str):
        times_list = [schedule_times]
    elif isinstance(schedule_times, list) and schedule_times:
        times_list = schedule_times
    else:
        times_list = ["09:00"]

    seen = set()
    scheduled = []
    for idx, t_str in enumerate(times_list):
        try:
            clean_t = str(t_str).strip()
            if clean_t in seen or ":" not in clean_t:
                continue
            seen.add(clean_t)
            hour, minute = map(int, clean_t.split(":"))
            scheduler.add_job(
                _scheduled_job,
                CronTrigger(hour=hour, minute=minute),
                id=f"daily_streaks_{idx}_{hour:02d}{minute:02d}",
                replace_existing=True,
            )
            scheduled.append(f"{hour:02d}:{minute:02d}")
        except Exception as ex:
            log("ERROR", f"Invalid schedule_time '{t_str}': {ex}")

    if scheduled:
        log("INFO", f"⏰ Scheduled daily streaks at {', '.join(scheduled)}")


async def _webcam_auto_refresh_job():
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, fetch_webcam_image, True)
        if login_session.is_active():
            page = login_session._state.get("page")
            if page:
                await inject_webcam_frame_into_page(page, force_refresh=False)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = config.load()
    config.load_macro_data()

    _loop.run_in_executor(None, fetch_webcam_image, False)
    _reschedule(cfg.get("schedule_times") or [cfg.get("schedule_time", "09:00")])
    scheduler.add_job(
        _webcam_auto_refresh_job,
        "interval",
        minutes=5,
        id="webcam_refresh",
        replace_existing=True,
    )
    scheduler.start()
    log("INFO", "✨ SnapStreak Studio started — SJSU Webcam & Cookie Vault active.")
    yield
    scheduler.shutdown(wait=False)
    await login_session.cancel()


app = FastAPI(title="SnapStreak Studio", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG & STATUS API
# ─────────────────────────────────────────────────────────────────────────────

class ConfigPayload(BaseModel):
    friends: list[str] | None = None
    schedule_time: str | None = None
    schedule_times: list[str] | None = None
    enabled: bool | None = None
    mode: str | None = None
    browser_engine: str | None = None
    streak_mode: str | None = None
    selection_method: str | None = None
    shortcut_name: str | None = None
    step_delay_seconds: float | None = None
    use_coordinate_delay: bool | None = None
    auto_save_cookies: bool | None = None
    strict_safety_guard: bool | None = None
    snap_image_custom: bool | None = None
    snapchat_username: str | None = None
    snapchat_password: str | None = None


@app.get("/api/config")
async def get_config():
    cfg = config.load()
    macro_info = login_session.get_macro_info()
    vault = config.get_cookie_vault_summary()
    v_info = config.get_version_info(check_remote=False)
    return {
        **cfg,
        "version": v_info["version"],
        "display_version": v_info["display_version"],
        "version_info": v_info,
        "has_session": vault["is_authenticated"],
        "cookie_vault": vault,
        "has_snap": SNAP_IMAGE.exists() or WEBCAM_FILE.exists(),
        "has_webcam": WEBCAM_FILE.exists(),
        "webcam_url": WEBCAM_URL,
        "has_macro": macro_info["count"] > 0,
        "macro_info": macro_info,
    }


@app.post("/api/config")
async def update_config(payload: ConfigPayload):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    cfg = config.save(updates)
    if "schedule_times" in updates or "schedule_time" in updates:
        _reschedule(cfg.get("schedule_times") or [cfg.get("schedule_time", "09:00")])

    # Sync updated config into active browser session if running
    if login_session.is_active():
        page = login_session._state.get("page")
        if page:
            try:
                await page.evaluate(
                    """(newCfg) => {
                        window.__SNAPSTREAK_SERVER_CONFIG__ = Object.assign(window.__SNAPSTREAK_SERVER_CONFIG__ || {}, newCfg);
                    }""",
                    {
                        "friends": cfg.get("friends", []),
                        "selectionMethod": cfg.get("selection_method", "direct"),
                        "streakMode": cfg.get("streak_mode", "ai_steps"),
                        "sendingEngine": "macro" if cfg.get("streak_mode") == "macro" else "direct",
                        "shortcutName": cfg.get("shortcut_name", "Streaks"),
                        "stepDelay": float(cfg.get("step_delay_seconds", 1.5)),
                    },
                )
            except Exception:
                pass

    log(
        "INFO",
        f"⚙️ Config saved — Mode={cfg.get('streak_mode')}, Method={cfg.get('selection_method')}, Friends={cfg.get('friends')}",
        _broadcast,
    )
    return {"ok": True, "config": cfg}


@app.get("/api/status")
async def get_status():
    cfg = config.load()
    vault = config.get_cookie_vault_summary()
    exec_state = get_execution_state()
    macro_info = login_session.get_macro_info()
    v_info = config.get_version_info(check_remote=False)

    next_runs = []
    for job in scheduler.get_jobs():
        if job.id.startswith("daily_streaks") and job.next_run_time:
            next_runs.append(job.next_run_time)
    next_runs.sort()
    next_run = next_runs[0].strftime("%Y-%m-%d %H:%M:%S %Z") if next_runs else None

    return {
        "version": v_info["version"],
        "display_version": v_info["display_version"],
        "version_info": v_info,
        "running": _running or exec_state.get("running", False),
        "execution": exec_state,
        "last_run": _last_run,
        "last_results": _last_results,
        "next_run": next_run,
        "schedule_times": cfg.get("schedule_times", [cfg.get("schedule_time", "09:00")]),
        "has_session": vault["is_authenticated"],
        "cookie_vault": vault,
        "has_snap": SNAP_IMAGE.exists() or WEBCAM_FILE.exists(),
        "has_webcam": WEBCAM_FILE.exists(),
        "webcam_url": WEBCAM_URL,
        "snap_image_custom": cfg.get("snap_image_custom", False),
        "login_active": login_session.is_active(),
        "login_starting": login_session.is_starting(),
        "login_url": login_session.get_Current_Url(),
        "screen_state": login_session.get_Screen_State(),
        "browser_engine": cfg.get("browser_engine", "chromium"),
        "streak_mode": cfg.get("streak_mode", "ai_steps"),
        "selection_method": cfg.get("selection_method", "direct"),
        "step_delay_seconds": cfg.get("step_delay_seconds", 1.5),
        "friends": cfg.get("friends", []),
        "has_screenshot": SCREENSHOT_FILE.exists(),
        "has_macro": macro_info["count"] > 0,
        "macro_info": macro_info,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COOKIE VAULT ENDPOINTS (PRESERVE / SAVE / IMPORT / EXPORT / RESTORE)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/cookies")
async def api_get_cookies():
    vault = config.get_cookie_vault_summary()
    cookie_list = []
    if SESSION_FILE.exists():
        try:
            state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            raw_cookies = state.get("cookies", []) if isinstance(state, dict) else []
            for c in raw_cookies:
                if isinstance(c, dict):
                    cookie_list.append({
                        "domain": c.get("domain", ""),
                        "name": c.get("name", ""),
                        "path": c.get("path", "/"),
                        "secure": c.get("secure", False),
                        "httpOnly": c.get("httpOnly", False),
                        "expires": c.get("expires"),
                        "value_preview": (str(c.get("value", ""))[:10] + "…") if len(str(c.get("value", ""))) > 10 else str(c.get("value", "")),
                    })
        except Exception:
            pass
    return {"ok": True, "vault": vault, "cookies": cookie_list}


@app.post("/api/cookies/save")
async def api_save_cookies():
    res = await login_session.save(emit=_broadcast)
    return {**res, "vault": config.get_cookie_vault_summary()}


class CookieImportPayload(BaseModel):
    cookies: str | list | dict


@app.post("/api/cookies/import")
async def api_import_cookies(payload: CookieImportPayload):
    res = await login_session.import_cookies(payload.cookies, emit=_broadcast)
    if not res.get("ok"):
        raise HTTPException(400, res.get("message", "Cookie import failed"))
    return {**res, "vault": config.get_cookie_vault_summary()}


@app.post("/api/cookies/restore-backup")
async def api_restore_cookie_backup():
    res = await login_session.restore_cookie_backup(emit=_broadcast)
    if not res.get("ok"):
        raise HTTPException(400, res.get("message", "Restore backup failed"))
    return {**res, "vault": config.get_cookie_vault_summary()}


@app.get("/api/cookies/export")
async def api_export_cookies():
    config.ensure_data_dirs()
    if not SESSION_FILE.exists():
        raise HTTPException(404, "No session.json file saved yet")
    return FileResponse(
        str(SESSION_FILE),
        media_type="application/json",
        filename="snapchat_session_cookies.json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SJSU METEOROLOGY WEBCAM ENDPOINTS (CORS-SAFE)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/webcam-feed")
async def get_webcam_feed(refresh: bool = False):
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, fetch_webcam_image, refresh)
    if data:
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Access-Control-Allow-Origin": "*",
            },
        )
    raise HTTPException(502, "Unable to fetch SJSU webcam image")


@app.get("/api/webcam-b64")
async def get_webcam_b64(refresh: bool = False):
    loop = asyncio.get_running_loop()
    data_url = await loop.run_in_executor(None, get_webcam_data_url, refresh)
    if not data_url:
        raise HTTPException(502, "Unable to load SJSU webcam Data URL")
    return JSONResponse(
        content={"ok": True, "data_url": data_url, "timestamp": int(time.time())},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
    )


@app.post("/api/webcam-refresh")
async def refresh_webcam():
    cfg = config.load()
    cfg["snap_image_custom"] = False
    config.save(cfg)
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, fetch_webcam_image, True)
    if login_session.is_active():
        page = login_session._state.get("page")
        if page:
            await inject_webcam_frame_into_page(page, force_refresh=False)
    if data:
        log("INFO", f"📷 Refreshed live SJSU Meteorology webcam frame ({len(data):,} bytes).", _broadcast)
        return {"ok": True, "size": len(data)}
    raise HTTPException(502, "Failed to refresh SJSU webcam frame")


@app.post("/api/snap-image")
async def upload_snap_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image (PNG/JPEG/WEBP)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    SNAP_IMAGE.write_bytes(data)
    cfg = config.load()
    cfg["snap_image_custom"] = True
    config.save(cfg)
    if login_session.is_active():
        page = login_session._state.get("page")
        if page:
            await inject_webcam_frame_into_page(page, force_refresh=False)
    log("INFO", f"🖼️ Custom snap image uploaded ({len(data):,} bytes)", _broadcast)
    return {"ok": True, "size": len(data)}


@app.get("/api/snap-image")
async def get_snap_image():
    cfg = config.load()
    if cfg.get("snap_image_custom") and SNAP_IMAGE.exists():
        return FileResponse(str(SNAP_IMAGE), headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})
    return await get_webcam_feed(refresh=False)


# ─────────────────────────────────────────────────────────────────────────────
# STREAK EXECUTION ENDPOINTS (AI / EXPECTED STEPS & MACRO MODE)
# ─────────────────────────────────────────────────────────────────────────────

class TriggerSendPayload(BaseModel):
    streak_mode: str | None = None
    selection_method: str | None = None
    friends: list[str] | None = None


@app.post("/api/send")
async def trigger_send(payload: TriggerSendPayload | None = None):
    if _running or get_execution_state().get("running"):
        raise HTTPException(409, "A streak run is already in progress")

    if payload:
        updates = {}
        if payload.streak_mode in ("ai_steps", "macro"):
            updates["streak_mode"] = payload.streak_mode
        if payload.selection_method in ("direct", "shortcut", "auto"):
            updates["selection_method"] = payload.selection_method
        if payload.friends is not None:
            updates["friends"] = payload.friends
        if updates:
            config.save(updates)

    asyncio.create_task(_scheduled_job(force=True))
    cfg = config.load()
    return {
        "ok": True,
        "streak_mode": cfg.get("streak_mode", "ai_steps"),
        "selection_method": cfg.get("selection_method", "direct"),
        "message": f"Started Auto Streak Maker ({cfg.get('streak_mode', 'ai_steps')})",
    }


@app.post("/api/send-preview")
async def trigger_send_preview(payload: TriggerSendPayload | None = None):
    global _running, _preview_data
    if _running or get_execution_state().get("running"):
        raise HTTPException(409, "A streak run is already in progress")

    if payload:
        updates = {}
        if payload.streak_mode in ("ai_steps", "macro"):
            updates["streak_mode"] = payload.streak_mode
        if payload.selection_method in ("direct", "shortcut", "auto"):
            updates["selection_method"] = payload.selection_method
        if updates:
            config.save(updates)

    cfg = config.load()
    friends = cfg.get("friends", [])
    streak_mode = cfg.get("streak_mode", "ai_steps")
    selection_method = cfg.get("selection_method", "direct")

    async def _run_preview():
        global _running, _preview_data
        _running = True
        try:
            res = await preview_streaks(
                friends=friends,
                emit=_broadcast,
                selection_method=selection_method,
                streak_mode=streak_mode,
            )
            _preview_data = {
                "screenshot": res.get("screenshot", ""),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "results": res.get("results", {}),
            }
        except Exception as ex:
            log("ERROR", f"Preview error: {ex}", _broadcast)
        finally:
            _running = False

    asyncio.create_task(_run_preview())
    return {"ok": True, "message": "Sample preview started — will pause right before clicking final Send"}


@app.get("/api/send-preview")
async def get_send_preview():
    return {
        "running": _running,
        "timestamp": _preview_data.get("timestamp"),
        "screenshot": _preview_data.get("screenshot", ""),
        "results": _preview_data.get("results", {}),
    }


@app.post("/api/automation/stop")
async def api_stop_automation():
    global _running
    request_stop()
    _running = False
    return {"ok": True, "message": "Stop signal sent to automation engine."}


@app.post("/api/automation/pause")
async def api_pause_automation():
    paused = toggle_pause()
    return {"ok": True, "paused": paused, "message": "Automation paused." if paused else "Automation resumed."}


# ─────────────────────────────────────────────────────────────────────────────
# MACRO STUDIO ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/macro")
async def api_get_macro():
    return login_session.get_macro_info()


@app.post("/api/macro/record/start")
async def api_macro_record_start():
    if not login_session.is_active():
        await login_session.start(emit=_broadcast)
    login_session.start_macro_recording()
    return {"ok": True, "recording": True, "message": "Macro recording active! Click steps on the live Snapchat screen."}


class MacroStopPayload(BaseModel):
    name: str | None = "Custom Recorded Macro"


@app.post("/api/macro/record/stop")
async def api_macro_record_stop(payload: MacroStopPayload | None = None):
    name = (payload.name if payload and payload.name else "Custom Recorded Macro").strip()
    events = login_session.stop_macro_recording(macro_name=name)
    return {"ok": True, "recording": False, "count": len(events), "steps": events, "macro_info": login_session.get_macro_info()}


class MacroSavePayload(BaseModel):
    name: str | None = None
    steps: list[dict]
    activate: bool = True


@app.post("/api/macro/save")
async def api_macro_save(payload: MacroSavePayload):
    macro_data = config.load_macro_data()
    name = (payload.name or macro_data.get("active_macro") or "Custom Macro").strip()
    if "macros" not in macro_data or not isinstance(macro_data["macros"], dict):
        macro_data["macros"] = {}
    macro_data["macros"][name] = {
        "name": name,
        "steps": payload.steps,
        "is_default": False,
        "updated_at": int(time.time()),
    }
    if payload.activate:
        macro_data["active_macro"] = name
        macro_data["steps"] = payload.steps
    config.save_macro_data(macro_data)
    return {"ok": True, "macro_info": login_session.get_macro_info()}


class MacroSelectPayload(BaseModel):
    name: str


@app.post("/api/macro/select")
async def api_macro_select(payload: MacroSelectPayload):
    macro_data = config.load_macro_data()
    macros = macro_data.get("macros", {})
    if payload.name not in macros:
        raise HTTPException(404, f"Macro '{payload.name}' not found")
    macro_data["active_macro"] = payload.name
    macro_data["steps"] = macros[payload.name].get("steps", [])
    config.save_macro_data(macro_data)
    return {"ok": True, "macro_info": login_session.get_macro_info()}


@app.post("/api/macro/reset-default")
async def api_macro_reset_default():
    macro_data = config.load_macro_data()
    default_steps = list(config.DEFAULT_EXPECTED_MACRO_STEPS)
    macro_data["active_macro"] = "Default Streak Flow"
    macro_data["steps"] = default_steps
    macro_data["macros"]["Default Streak Flow"] = {
        "name": "Default Streak Flow",
        "steps": default_steps,
        "is_default": True,
        "updated_at": int(time.time()),
    }
    config.save_macro_data(macro_data)
    return {"ok": True, "macro_info": login_session.get_macro_info()}


class MacroDeleteStepPayload(BaseModel):
    index: int


@app.post("/api/macro/step/delete")
async def api_macro_delete_step(payload: MacroDeleteStepPayload):
    macro_data = config.load_macro_data()
    steps = list(macro_data.get("steps", []))
    if 0 <= payload.index < len(steps):
        steps.pop(payload.index)
        macro_data["steps"] = steps
        active_name = macro_data.get("active_macro", "Custom Macro")
        if active_name in macro_data.get("macros", {}):
            macro_data["macros"][active_name]["steps"] = steps
        config.save_macro_data(macro_data)
    return {"ok": True, "macro_info": login_session.get_macro_info()}


@app.post("/api/macro/replay")
async def api_macro_replay():
    if _running or get_execution_state().get("running"):
        raise HTTPException(409, "Automation is already running")
    config.save({"streak_mode": "macro"})
    asyncio.create_task(_scheduled_job(force=True))
    return {"ok": True, "message": "Replaying macro in live browser session"}


@app.delete("/api/macro")
async def api_macro_clear():
    return await api_macro_reset_default()


# ─────────────────────────────────────────────────────────────────────────────
# LIVE SNAPCHAT BROWSER SESSION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class StartLoginPayload(BaseModel):
    engine: str | None = None


@app.post("/api/login/start")
async def start_login(payload: StartLoginPayload | None = None):
    engine = payload.engine if payload else None
    return await login_session.start(emit=_broadcast, engine=engine)


@app.get("/api/login/screenshot")
async def login_screenshot():
    if not login_session.is_active():
        if login_session.is_starting():
            return {"image": "", "url": "Starting Snapchat Web...", "starting": True, "screen_state": "STARTING"}
        raise HTTPException(404, "No active browser session")
    return {
        "image": login_session.get_Cached_Screenshot(),
        "url": login_session.get_Current_Url(),
        "screen_state": login_session.get_Screen_State(),
    }


class ClickPayload(BaseModel):
    x: int
    y: int


@app.post("/api/login/click")
async def login_click(payload: ClickPayload):
    try:
        await login_session.click(payload.x, payload.y)
        return {"ok": True, "macro_info": login_session.get_macro_info() if login_session._state.get("macro_recording") else None}
    except Exception as ex:
        raise HTTPException(400, str(ex))


class TypePayload(BaseModel):
    text: str


@app.post("/api/login/type")
async def login_type(payload: TypePayload):
    try:
        await login_session.send_text(payload.text)
        return {"ok": True}
    except Exception as ex:
        raise HTTPException(400, str(ex))


class KeyPayload(BaseModel):
    key: str


@app.post("/api/login/key")
async def login_key(payload: KeyPayload):
    try:
        await login_session.press_key(payload.key)
        return {"ok": True}
    except Exception as ex:
        raise HTTPException(400, str(ex))


class ScrollPayload(BaseModel):
    delta_x: int = 0
    delta_y: int = 300


@app.post("/api/login/scroll")
async def login_scroll(payload: ScrollPayload):
    try:
        await login_session.scroll(payload.delta_x, payload.delta_y)
        return {"ok": True}
    except Exception as ex:
        raise HTTPException(400, str(ex))


class NavigatePayload(BaseModel):
    url: str


@app.post("/api/login/navigate")
async def login_navigate(payload: NavigatePayload):
    try:
        return await login_session.navigate(payload.url)
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/login/back")
async def login_back():
    try:
        return await login_session.go_back()
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/login/forward")
async def login_forward():
    try:
        return await login_session.go_forward()
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/login/reload")
async def login_reload():
    try:
        return await login_session.reload_page()
    except Exception as ex:
        raise HTTPException(400, str(ex))


class QuickFillPayload(BaseModel):
    username: str
    password: str = ""
    save_to_config: bool = True


@app.post("/api/login/quick-fill")
async def api_login_quick_fill(payload: QuickFillPayload):
    if payload.save_to_config:
        config.save({"snapchat_username": payload.username, "snapchat_password": payload.password})
    res = await login_session.quick_fill_login(payload.username, payload.password, emit=_broadcast)
    if not res.get("ok"):
        raise HTTPException(400, res.get("message", "Quick fill failed"))
    return res


@app.post("/api/login/repair-snapchat")
async def api_repair_snapchat():
    return await login_session.repair_snapchat_session(emit=_broadcast)


@app.post("/api/login/save")
async def save_login():
    res = await login_session.save(emit=_broadcast)
    if not res.get("ok"):
        raise HTTPException(400, res.get("message", "Save failed"))
    return res


@app.post("/api/login/cancel")
async def cancel_login():
    await login_session.cancel()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# VERSION, 1-CLICK GIT UPDATER, DIAGNOSTICS, LOGS & WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/system/version")
async def get_system_version(check_remote: bool = False):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, config.get_version_info, check_remote)


@app.post("/api/system/update")
async def trigger_system_git_update():
    """
    1-Click Git Updater:
    Fetches & pulls latest code from GitHub (origin/main), pushes any local ahead commits,
    preserves all cookies/config, hot-reloads Python modules, and re-injects the updated
    extension bundle into any active Snapchat Web browser tab.
    """
    log("INFO", "⬆️ [1-Click Git Updater] Fetching & applying latest Git code to website...", _broadcast)
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, config.run_git_update)

    # Hot-reload backend modules so new logic takes effect immediately without dropping session
    try:
        importlib.reload(config)
        importlib.reload(diagnostics)
        importlib.reload(automation)
    except Exception as ex:
        log("WARN", f"Module hot-reload notice: {ex}", _broadcast)

    # Live re-inject updated extension bundle into active Snapchat Web browser page if open
    if login_session.is_active():
        page = login_session._state.get("page")
        if page:
            try:
                await page.evaluate(
                    """() => {
                        window.__SNAPSTREAK_EXTENSION_INJECTED__ = false;
                        const oldHost = document.getElementById('snapstreak-shadow-host');
                        if (oldHost) oldHost.remove();
                    }"""
                )
                ext_bundle = automation.get_extension_bundle_script()
                if ext_bundle:
                    await page.evaluate(ext_bundle)
                await automation.inject_webcam_frame_into_page(page, force_refresh=False)
                log("INFO", "  ✓ Live Snapchat Web page hot-updated with latest extension bundle!", _broadcast)
            except Exception as ex:
                log("WARN", f"  Notice updating live page bundle: {ex}", _broadcast)

    log("INFO", f"✅ [1-Click Git Updater] {res.get('message')}", _broadcast)
    return res


@app.get("/api/system/diagnostics")
async def get_system_diagnostics():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, diagnostics.run_diagnostics)


class ResolveIssuesPayload(BaseModel):
    fix_type: str = "all"


@app.post("/api/system/resolve-issues")
async def resolve_system_issues(payload: ResolveIssuesPayload | None = None):
    fix_type = payload.fix_type if payload else "all"
    return await diagnostics.auto_resolve_issues(fix_type=fix_type, emit=_broadcast)


@app.get("/api/screenshot")
async def get_last_screenshot():
    if not SCREENSHOT_FILE.exists():
        raise HTTPException(404, "No screenshot available yet")
    return FileResponse(str(SCREENSHOT_FILE), headers={"Cache-Control": "no-store"})


@app.get("/api/logs")
async def get_logs(limit: int = 300):
    if not LOG_FILE.exists():
        return {"lines": [], "total": 0}
    all_lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(all_lines)
    lines = all_lines if limit <= 0 else all_lines[-limit:]
    return {"lines": lines, "total": total}


@app.post("/api/logs/clear")
async def clear_logs():
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return {"ok": True}


@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        shot = login_session.get_Cached_Screenshot()
        if shot:
            await ws.send_text(json.dumps({
                "type": "screencast",
                "image": shot,
                "url": login_session.get_Current_Url(),
                "screen_state": login_session.get_Screen_State(),
            }))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
