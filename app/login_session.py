"""
login_session.py – Remote browser login via headless Playwright + screenshot streaming.

No extra ports, no VNC, no Xvfb. Works entirely through port 8080.
Browser runs headless, takes screenshots every second, forwards
mouse/keyboard events from the web UI.
"""

import asyncio
import base64
import json
import time
from typing import Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation import (
    SESSION_FILE,
    USER_AGENT,
    VIEWPORT,
    USER_DATA_DIR,
    MACRO_FILE,
    replay_macro,
    get_camera_stream_init_script,
    fetch_webcam_image,
    _cleanup_stale_locks,
    _log,
)



NOVNC_PORT = 6080  # kept for API compat

_state: dict = {
    "active":     False,
    "playwright": None,
    "context":    None,
    "page":       None,
    "last_shot":  b"",   # last JPEG screenshot bytes
    "url":        "",
}

_macro: dict = {
    "recording": False,
    "events": [],
    "last_time": 0.0,
}


def start_macro_recording() -> dict:
    _macro["recording"] = True
    _macro["events"] = []
    _macro["last_time"] = time.time()
    return {"ok": True, "recording": True}


def stop_macro_recording() -> dict:
    _macro["recording"] = False
    events = list(_macro["events"])
    if events:
        MACRO_FILE.write_text(json.dumps(events, indent=2))
    return {"ok": True, "count": len(events), "events": events}


def get_macro_info() -> dict:
    has_macro = MACRO_FILE.exists()
    count = 0
    if has_macro:
        try:
            count = len(json.loads(MACRO_FILE.read_text()))
        except Exception:
            pass
    return {"has_macro": has_macro, "count": count, "recording": _macro["recording"]}



async def _cleanup():
    try:
        if _state["context"]:
            await _state["context"].close()
    except Exception:
        pass
    try:
        if _state["playwright"]:
            await _state["playwright"].stop()
    except Exception:
        pass
    _state.update(
        active=False, playwright=None,
        context=None, page=None, last_shot=b"", url=""
    )


def is_active() -> bool:
    return _state["active"]


def last_screenshot_b64() -> str:
    """Return the latest screenshot as a base64 JPEG string."""
    if not _state["last_shot"]:
        return ""
    return base64.b64encode(_state["last_shot"]).decode()


def current_url() -> str:
    return _state.get("url", "")


async def _screenshot_loop():
    """Background task: keeps refreshing the screenshot every second."""
    while _state["active"]:
        try:
            page: Page = _state["page"]
            if page:
                img = await page.screenshot(type="jpeg", quality=75, full_page=False)
                _state["last_shot"] = img
                _state["url"] = page.url
        except Exception:
            pass
        await asyncio.sleep(1)


async def start(emit: Callable | None = None) -> str:
    if _state["active"] and _state["page"]:
        return "Already running."

    await _cleanup()
    _cleanup_stale_locks()
    _log("Launching browser with persistent profile...", emit)

    pw = await async_playwright().start()
    _state["playwright"] = pw

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=True,
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/Los_Angeles",
        permissions=["camera", "microphone", "notifications"],
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
            "--disable-blink-features=AutomationControlled",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ],
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )

    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
    )
    await context.add_init_script(get_camera_stream_init_script())

    async def _handle_feed(route):
        data = fetch_webcam_image()
        await route.fulfill(status=200, content_type="image/jpeg", body=data)

    await context.route("**/fake_webcam_feed.jpg", _handle_feed)

    _state["context"] = context

    page = context.pages[0] if context.pages else await context.new_page()
    _state["page"] = page
    _state["active"] = True

    # Start screenshot stream immediately so UI updates
    asyncio.create_task(_screenshot_loop())

    _log("Navigating to Snapchat Web...", emit)
    try:
        await page.goto("https://web.snapchat.com/", timeout=25_000, wait_until="domcontentloaded")
    except Exception as ex:
        _log(f"Navigation notice: {ex}", emit)

    _log("✓ Browser ready — view it in the web UI login panel.", emit)
    return "ok"




async def click(x: int, y: int):
    """Forward a click at (x, y) to the browser with realistic mouse move and down/up."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 1200
        _macro["last_time"] = now
        _macro["events"].append({"type": "click", "x": x, "y": y, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        try:
            await page.mouse.move(x, y)
            await asyncio.sleep(0.05)
            await page.mouse.down()
            await asyncio.sleep(0.08)
            await page.mouse.up()
            await asyncio.sleep(0.3)
        except Exception:
            pass


async def type_text(text: str):
    """Type text into the browser."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 800
        _macro["last_time"] = now
        _macro["events"].append({"type": "type", "text": text, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        await page.keyboard.type(text, delay=60)


async def key_press(key: str):
    """Press a special key (Enter, Tab, Backspace, Escape...)."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 800
        _macro["last_time"] = now
        _macro["events"].append({"type": "key", "key": key, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        await page.keyboard.press(key)


async def navigate(url: str):
    """Navigate the browser to a URL."""
    page: Page | None = _state["page"]
    if page:
        await page.goto(url, timeout=20_000)


async def upload_snap_to_chat() -> dict:
    """Upload snap image to whichever chat is currently open."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser"}
    
    from automation import ensure_snap_image, SNAP_IMAGE
    ensure_snap_image()

    for sel in [
        '[aria-label*="camera" i]',
        '[aria-label*="photo" i]',
        '[aria-label*="media" i]',
        '[aria-label*="attachment" i]',
        '[data-testid="camera-button"]',
        '[data-testid="media-button"]',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=1500)
            if btn:
                await btn.click()
                await asyncio.sleep(0.5)
                break
        except Exception:
            pass

    file_input = None
    for sel in ['input[type="file"][accept*="image"]', 'input[type="file"][accept*="video"]', 'input[type="file"]']:
        try:
            file_input = await page.wait_for_selector(sel, timeout=2000)
            if file_input:
                break
        except Exception:
            pass

    if file_input:
        await file_input.set_input_files(str(SNAP_IMAGE))
        await asyncio.sleep(1)
        return {"ok": True, "message": "Snap image uploaded to active chat."}
    return {"ok": False, "error": "Could not find upload button on active page."}


async def run_streak_in_active_session(friends: list[str] | None = None, emit: Callable | None = None) -> dict:
    """Execute streak sequence directly inside the currently visible interactive browser."""
    if not _state["active"] or not _state["page"]:
        return {"error": "Browser not active"}

    from automation import MACRO_FILE, replay_macro, send_streaks_shortcut_flow, ensure_snap_image
    ensure_snap_image()
    page = _state["page"]
    if MACRO_FILE.exists():
        results = await replay_macro(page, emit=emit)
    else:
        results = await send_streaks_shortcut_flow(page, emit=emit)
    return results




async def save(emit: Callable | None = None) -> str:
    if not _state["active"]:
        return "No active session."
    _log("Saving session...", emit)
    try:
        storage = await _state["context"].storage_state()
        SESSION_FILE.write_text(__import__("json").dumps(storage))
        _log("✓ Session saved.", emit)
        msg = "Logged in and session saved!"
    except Exception as ex:
        msg = f"Error saving: {ex}"
        _log(msg, emit)
    await _cleanup()
    return msg


async def cancel(emit: Callable | None = None):
    _log("Cancelling login session.", emit)
    await _cleanup()

