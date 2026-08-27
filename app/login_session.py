"""
login_session.py – Manages a visible browser session via virtual display + VNC.

Flow:
  1. start()  → Xvfb + Playwright (non-headless) + x11vnc + websockify
  2. User opens noVNC in their browser, logs into Snapchat normally
  3. save()   → Playwright saves storage_state (cookies), all processes killed
"""

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation import SESSION_FILE, USER_AGENT, VIEWPORT, _log

DISPLAY       = ":99"
VNC_PORT      = 5900
NOVNC_PORT    = 6080
NOVNC_WEB     = "/usr/share/novnc"   # installed by apt

# Global state for the active login session
_state: dict = {
    "active":    False,
    "playwright": None,
    "browser":   None,
    "context":   None,
    "page":      None,
    "xvfb":      None,
    "x11vnc":    None,
    "websockify": None,
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


def _cleanup_processes():
    _kill(_state["x11vnc"])
    _kill(_state["websockify"])
    _kill(_state["xvfb"])
    _state["xvfb"] = _state["x11vnc"] = _state["websockify"] = None


async def _cleanup_browser():
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
    _state["browser"] = _state["context"] = _state["page"] = _state["playwright"] = None


def is_active() -> bool:
    return _state["active"]


async def start(emit: Callable | None = None) -> str:
    """
    Start virtual display + visible Chrome + VNC.
    Returns the noVNC URL the user should open.
    """
    if _state["active"]:
        return f"Already running – open noVNC on port {NOVNC_PORT}"

    _log("Starting virtual display (Xvfb)...", emit)
    _state["xvfb"] = subprocess.Popen(
        ["Xvfb", DISPLAY, "-screen", "0", "1440x900x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(2)

    _log("Starting VNC server (x11vnc)...", emit)
    _state["x11vnc"] = subprocess.Popen(
        [
            "x11vnc",
            "-display", DISPLAY,
            "-nopw",           # no VNC password (LAN only)
            "-forever",
            "-port", str(VNC_PORT),
            "-quiet",
            "-shared",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(1)

    _log("Starting noVNC websocket proxy...", emit)
    _state["websockify"] = subprocess.Popen(
        ["websockify", "--web", NOVNC_WEB, str(NOVNC_PORT), f"localhost:{VNC_PORT}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(1)

    _log("Launching Chrome on virtual display...", emit)
    env = {**os.environ, "DISPLAY": DISPLAY}

    pw = await async_playwright().start()
    _state["playwright"] = pw

    browser = await pw.chromium.launch(
        headless=False,
        env=env,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1440,900",
            "--disable-blink-features=AutomationControlled",
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

    await page.goto("https://web.snapchat.com/", timeout=30_000)
    _state["active"] = True

    _log(f"✓ Login session ready on noVNC port {NOVNC_PORT}", emit)
    return f"http://SERVER_IP:{NOVNC_PORT}/vnc.html?autoconnect=true&resize=scale"


async def save(emit: Callable | None = None) -> str:
    """
    Save the current browser session (cookies) to disk, then tear everything down.
    """
    if not _state["active"]:
        return "No active login session."

    _log("Saving session cookies...", emit)
    try:
        context: BrowserContext = _state["context"]
        storage = await context.storage_state()
        SESSION_FILE.write_text(__import__("json").dumps(storage))
        _log("✓ Session saved.", emit)
        msg = "Session saved successfully. You are now logged in."
    except Exception as ex:
        msg = f"Error saving session: {ex}"
        _log(msg, emit)

    await _cleanup_browser()
    _cleanup_processes()
    _state["active"] = False
    return msg


async def cancel(emit: Callable | None = None):
    """Abort login session without saving."""
    _log("Cancelling login session...", emit)
    await _cleanup_browser()
    _cleanup_processes()
    _state["active"] = False
