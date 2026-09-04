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
    Y4M_FILE,
    STEALTH_INIT_SCRIPT,
    replay_macro,
    fetch_webcam_image,
    _cleanup_stale_locks,
    _log,
)





import os
import sys
import shutil
import subprocess

DISPLAY    = ":99"
VNC_PORT   = 5900
NOVNC_PORT = 6080
NOVNC_WEB  = "/usr/share/novnc"

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


_state: dict = {
    "active":        False,
    "playwright":    None,
    "context":       None,
    "page":          None,
    "cdp":           None,
    "last_shot_b64": "",
    "url":           "",
    "xvfb":          None,
    "x11vnc":        None,
    "websockify":    None,
}


def _kill(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _cleanup_processes():
    _kill(_state.get("websockify"))
    _kill(_state.get("x11vnc"))
    _kill(_state.get("xvfb"))
    _state["xvfb"] = _state["x11vnc"] = _state["websockify"] = None


async def _cleanup():
    _cleanup_processes()
    try:
        if _state["cdp"]:
            await _state["cdp"].detach()
    except Exception:
        pass
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
        context=None, page=None, cdp=None, last_shot_b64="", url="",
        xvfb=None, x11vnc=None, websockify=None
    )


def is_active() -> bool:
    return _state["active"]


def last_screenshot_b64() -> str:
    """Return the latest screenshot as a base64 JPEG string."""
    return _state.get("last_shot_b64", "")


def current_url() -> str:
    return _state.get("url", "")


async def _fast_frame_loop():
    """Fallback frame loop in case CDP screencast is idle."""
    while _state["active"]:
        try:
            page: Page = _state["page"]
            if page and not _state["last_shot_b64"]:
                img = await page.screenshot(type="jpeg", quality=60, full_page=False)
                _state["last_shot_b64"] = base64.b64encode(img).decode()
                _state["url"] = page.url
        except Exception:
            pass
        await asyncio.sleep(0.5)


def _find_chrome_executable() -> str | None:
    for path in [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/google-chrome",
        "/usr/bin/chromium",
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ]:
        if os.path.exists(path):
            return path
    return None




async def start(emit: Callable | None = None) -> str:
    if _state["active"] and _state["page"]:
        return "Already running."

    await _cleanup()
    _cleanup_stale_locks()
    fetch_webcam_image()  # ensure Y4M_FILE is ready before launch
    _log("Launching browser with persistent profile...", emit)

    pw = await async_playwright().start()
    _state["playwright"] = pw

    is_linux = sys.platform.startswith("linux")
    has_xvfb = shutil.which("Xvfb") is not None

    env = dict(os.environ)
    if is_linux and has_xvfb:
        _log("Starting virtual X11 desktop (Xvfb)...", emit)
        _cleanup_processes()
        _state["xvfb"] = subprocess.Popen(
            ["Xvfb", DISPLAY, "-screen", "0", f"{VIEWPORT['width']}x{VIEWPORT['height']}x24", "-ac"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(1.5)

        _log("Starting VNC server (x11vnc)...", emit)
        _state["x11vnc"] = subprocess.Popen(
            ["x11vnc", "-display", DISPLAY, "-nopw", "-forever", "-port", str(VNC_PORT), "-shared", "-quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(0.8)

        novnc_web = NOVNC_WEB if Path(NOVNC_WEB).exists() else None
        websock_cmd = ["websockify", "--web", novnc_web, str(NOVNC_PORT), f"localhost:{VNC_PORT}"] if novnc_web else ["websockify", str(NOVNC_PORT), f"localhost:{VNC_PORT}"]
        _log(f"Starting web desktop proxy (noVNC port {NOVNC_PORT})...", emit)
        _state["websockify"] = subprocess.Popen(
            websock_cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(0.8)
        env["DISPLAY"] = DISPLAY
        headless = False
        _log(f"✓ Real browser desktop ready on port {NOVNC_PORT}.", emit)
    else:
        headless = True

    chrome_exe = _find_chrome_executable()
    if chrome_exe:
        _log(f"  ✓ Using official browser: {chrome_exe}", emit)
    else:
        _log("  ℹ Using Playwright Chromium.", emit)

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
        "--disable-blink-features=AutomationControlled",
        "--no-default-browser-check",
        "--enable-webgl",
        "--enable-webgl2",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
    ]
    if Y4M_FILE.exists():
        launch_args.append(f"--use-file-for-fake-video-capture={Y4M_FILE}")

    kwargs = {
        "user_data_dir": str(USER_DATA_DIR),
        "headless": headless,
        "viewport": VIEWPORT,
        "user_agent": USER_AGENT,
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "permissions": ["camera", "microphone", "notifications"],
        "args": launch_args,
        "env": env,
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    }
    if chrome_exe:
        kwargs["executable_path"] = chrome_exe

    context = await pw.chromium.launch_persistent_context(**kwargs)


    await context.add_init_script(STEALTH_INIT_SCRIPT)


    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text())
            cookies = data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                _log(f"  ✓ Injected {len(cookies)} cookies from session.json into browser context.", emit)
        except Exception as ex:
            _log(f"  ⚠ Failed to inject session cookies: {ex}", emit)

    _state["context"] = context




    page = context.pages[0] if context.pages else await context.new_page()
    _state["page"] = page
    _state["active"] = True

    # Start native real-time CDP Screencast (high-speed, low-latency)
    try:
        cdp = await context.new_cdp_session(page)
        _state["cdp"] = cdp

        async def on_screencast_frame(params):
            session_id = params.get("sessionId")
            data_b64 = params.get("data", "")
            if session_id:
                try:
                    await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                except Exception:
                    pass
            if data_b64:
                _state["last_shot_b64"] = data_b64
                _state["url"] = page.url
                if emit:
                    emit(json.dumps({"type": "screencast", "image": data_b64, "url": page.url}))

        cdp.on("Page.screencastFrame", lambda params: asyncio.create_task(on_screencast_frame(params)))

        await cdp.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": 60,
            "maxWidth": 1440,
            "maxHeight": 900,
            "everyNthFrame": 1,
        })
    except Exception as ex:
        _log(f"CDP Screencast fallback: {ex}", emit)
        asyncio.create_task(_fast_frame_loop())

    _log("Navigating to Snapchat Login...", emit)
    try:
        await page.goto("https://accounts.snapchat.com/accounts/v2/login?continue=https%3A%2F%2Fweb.snapchat.com%2F", timeout=25_000, wait_until="domcontentloaded")
    except Exception as ex:
        _log(f"Navigation notice: {ex}", emit)

    _log("✓ Browser ready — live stream active.", emit)
    return "ok"


async def click_google_login() -> dict:
    """Click Continue with Google / Sign in with Google button."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    google_selectors = [
        'button:has-text("Google")',
        '[aria-label*="Google" i]',
        'button:has([data-testid*="google" i])',
        'a:has-text("Google")',
        'div[role="button"]:has-text("Google")',
    ]
    for sel in google_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.scroll_into_view_if_needed()
                await btn.click(delay=80)
                _log("  ✓ Clicked Continue with Google button.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue
    return {"ok": False, "error": "Google button not found on this page"}






async def click(x: int, y: int):
    """Forward a click at (x, y) to the browser with realistic mouse move and click."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 1200
        _macro["last_time"] = now
        _macro["events"].append({"type": "click", "x": x, "y": y, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        try:
            await page.mouse.move(x, y)
            await asyncio.sleep(0.04)
            await page.mouse.click(x, y, delay=50)
            await asyncio.sleep(0.2)
        except Exception:
            pass


async def fill_field(field: str, value: str) -> dict:
    """Smart field focus, clear, and input with full React property descriptor synchronization."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    selectors_map = {
        "username": [
            "input#accountIdentifier",
            "input[name='accountIdentifier']",
            "input[autocomplete='username']",
            "input[name='username']",
            "input[type='email']",
            "input[placeholder*='Username' i]",
            "input[placeholder*='Email' i]",
            "input[type='text']",
        ],
        "password": [
            "input#password",
            "input[name='password']",
            "input[autocomplete='current-password']",
            "input[type='password']",
            "input[placeholder*='Password' i]",
        ],
        "code": [
            "input[name='code']",
            "input[name='verificationCode']",
            "input[inputmode='numeric']",
            "input[type='number']",
            "input[maxlength='6']",
            "input[placeholder*='code' i]",
            "input[type='text']",
        ],
    }

    selectors = selectors_map.get(field.lower(), ["input[type='text']", "input"])

    # 1. Try finding input via selectors and filling properly
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.click()
                await asyncio.sleep(0.05)
                # Playwright's native fill() handles focus, clear, and input dispatch
                await loc.fill(value)
                # React 16+ controlled input synchronization fallback
                await page.evaluate("""
                    ([selector, val]) => {
                        const el = document.querySelector(selector);
                        if (el) {
                            el.focus();
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                            if (setter) {
                                setter.call(el, val);
                            } else {
                                el.value = val;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                        }
                    }
                """, [sel, value])
                _log(f"  ✓ Quick filled {field} into '{sel}'.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    # 2. Fallback: Type directly into active focused element with React sync
    try:
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(value, delay=40)
        await page.evaluate("""
            (val) => {
                const el = document.activeElement;
                if (el && el.tagName === 'INPUT') {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                }
            }
        """, value)
        _log(f"  ✓ Typed {field} directly into active focused element.")
        return {"ok": True, "fallback": "active_element"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


async def click_submit() -> dict:
    """Click primary submit / Next / Log In button with accurate click event."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Next')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        "input[type='submit']",
        "[data-testid='submit-button']",
    ]
    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.scroll_into_view_if_needed()
                await btn.click(delay=80)
                _log(f"  ✓ Clicked submit button '{sel}'.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    # Fallback: Press Enter key
    try:
        await page.keyboard.press("Enter")
        _log("  ✓ Pressed Enter for submission.")
        return {"ok": True, "fallback": "Enter"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}



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

