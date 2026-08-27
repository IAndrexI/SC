"""
login_session.py – Remote browser login via headless Playwright + screenshot streaming.

No extra ports, no VNC, no Xvfb. Works entirely through port 8080.
Browser runs headless, takes screenshots every second, forwards
mouse/keyboard events from the web UI.
"""

import asyncio
import base64
from typing import Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation import SESSION_FILE, USER_AGENT, VIEWPORT, USER_DATA_DIR, _log

NOVNC_PORT = 6080  # kept for API compat

_state: dict = {
    "active":     False,
    "playwright": None,
    "context":    None,
    "page":       None,
    "last_shot":  b"",   # last JPEG screenshot bytes
    "url":        "",
}


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
    if _state["active"]:
        return "Already running."

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
        },
    )

    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
    )
    _state["context"] = context

    page = context.pages[0] if context.pages else await context.new_page()
    _state["page"] = page
    _state["active"] = True

    await page.goto("https://web.snapchat.com/", timeout=30_000)

    asyncio.create_task(_screenshot_loop())
    _log("✓ Browser ready — view it in the web UI login panel.", emit)
    return "ok"



async def click(x: int, y: int):
    """Forward a click at (x, y) to the browser with realistic mouse move and down/up."""
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


async def fill_field(field: str, value: str) -> dict:
    """Smart field focus and fill for username, password, or verification code."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser"}

    selectors_map = {
        "username": [
            "input#accountIdentifier",
            "input[name='accountIdentifier']",
            "input[autocomplete='username']",
            "input[name='username']",
            "input[type='email']",
            "input[type='text']",
        ],
        "password": [
            "input#password",
            "input[name='password']",
            "input[autocomplete='current-password']",
            "input[type='password']",
        ],
        "code": [
            "input[inputmode='numeric']",
            "input[type='number']",
            "input[name='code']",
            "input[name='verificationCode']",
            "input[maxlength='6']",
            "input[type='text']",
        ]
    }

    selectors = selectors_map.get(field.lower(), ["input[type='text']"])
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1500):
                await loc.click()
                await asyncio.sleep(0.1)
                await loc.fill("")
                await asyncio.sleep(0.1)
                await loc.type(value, delay=50)
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    # Fallback: type directly into currently active element
    try:
        await page.keyboard.type(value, delay=50)
        return {"ok": True, "fallback": "active_element"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


async def click_submit() -> dict:
    """Click primary submit / Next / Log In button."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser"}

    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Next')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        "[data-testid='submit-button']",
    ]
    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    try:
        await page.keyboard.press("Enter")
        return {"ok": True, "fallback": "Enter"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


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
    """Execute shortcut streak sequence directly inside the currently visible interactive browser."""
    if not _state["active"] or not _state["page"]:
        return {"error": "Browser not active"}

    from automation import send_streaks_shortcut_flow, ensure_snap_image
    ensure_snap_image()
    page = _state["page"]
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

