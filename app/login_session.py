"""
login_session.py – Remote browser login via Playwright screenshot streaming.

No VNC, no extra ports. Works on the same port as the web UI.
The browser runs on Xvfb (virtual display), takes screenshots every second,
and forwards mouse/keyboard events from the web UI to the browser.
"""

import asyncio
import base64
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation import SESSION_FILE, USER_AGENT, VIEWPORT, _log

NOVNC_PORT = 6080  # kept for API compat, not used anymore

_state: dict = {
    "active":     False,
    "playwright": None,
    "browser":    None,
    "context":    None,
    "page":       None,
    "xvfb":       None,
    "last_shot":  b"",   # last JPEG screenshot bytes
    "url":        "",
}


def _kill(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


async def _cleanup():
    try:
        if _state["browser"]:
            await _state["browser"].close()
    except Exception:
        pass
    try:
        if _state["playwright"]:
            await _state["playwright"].stop()
    except Exception:
        pass
    _kill(_state["xvfb"])
    _state.update(
        active=False, playwright=None, browser=None,
        context=None, page=None, xvfb=None, last_shot=b"", url=""
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
    if _state["active"]:
        return "Already running."

    _log("Starting virtual display (Xvfb)...", emit)
    xvfb = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", f"{VIEWPORT['width']}x{VIEWPORT['height']}x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _state["xvfb"] = xvfb
    await asyncio.sleep(2)

    if xvfb.poll() is not None:
        _log("⚠ Xvfb failed to start — trying without virtual display (may not work).", emit)

    _log("Launching browser...", emit)
    env = {**os.environ, "DISPLAY": ":99"}

    pw = await async_playwright().start()
    _state["playwright"] = pw

    browser = await pw.chromium.launch(
        headless=False,
        env=env,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    _state["browser"] = browser

    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/Los_Angeles",
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
    )
    _state["context"] = context

    page = await context.new_page()
    _state["page"] = page
    _state["active"] = True

    await page.goto("https://web.snapchat.com/", timeout=30_000)

    # Start screenshot loop in background
    asyncio.create_task(_screenshot_loop())

    _log("✓ Login browser ready. View it in the web UI.", emit)
    return "ok"


async def click(x: int, y: int):
    """Forward a click at (x, y) to the browser."""
    page: Page | None = _state["page"]
    if page:
        await page.mouse.click(x, y)
        await asyncio.sleep(0.3)


async def type_text(text: str):
    """Type text into the browser."""
    page: Page | None = _state["page"]
    if page:
        await page.keyboard.type(text, delay=60)


async def key_press(key: str):
    """Press a special key (Enter, Tab, Backspace, Escape...)."""
    page: Page | None = _state["page"]
    if page:
        await page.keyboard.press(key)


async def navigate(url: str):
    """Navigate the browser to a URL."""
    page: Page | None = _state["page"]
    if page:
        await page.goto(url, timeout=20_000)


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
