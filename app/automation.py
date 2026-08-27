"""
automation.py – Snapchat Web automation via Playwright.

Strategy:
  1. Load saved browser session (cookies) if it exists.
  2. Navigate to web.snapchat.com.
  3. If not logged in, pause for manual login and then save session.
  4. For each friend: open DM → click camera → upload snap image → send.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, BrowserContext, Page

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SESSION_FILE = DATA_DIR / "session.json"
SNAP_IMAGE = DATA_DIR / "snap.png"
LOG_FILE = DATA_DIR / "activity.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
def _log(msg: str, emit: Callable[[str], None] | None = None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if emit:
        emit(line)


# ---------------------------------------------------------------------------
# Ensure a snap image exists (solid blue 400×400 PNG)
# ---------------------------------------------------------------------------
def ensure_snap_image():
    """Creates a minimal solid-colour PNG if none is present."""
    if SNAP_IMAGE.exists():
        return
    try:
        from PIL import Image
        img = Image.new("RGB", (400, 400), color=(30, 30, 30))
        img.save(SNAP_IMAGE)
    except ImportError:
        # Pillow not available – write a tiny valid PNG directly (1×1 black)
        import base64
        # 1x1 black PNG (67 bytes, base64-encoded)
        _tiny = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        SNAP_IMAGE.write_bytes(_tiny)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
async def _save_session(context: BrowserContext):
    storage = await context.storage_state()
    SESSION_FILE.write_text(json.dumps(storage))


async def _load_context(playwright, headless: bool = True) -> tuple:
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--single-process",
        ],
    )
    if SESSION_FILE.exists():
        context = await browser.new_context(
            storage_state=json.loads(SESSION_FILE.read_text()),
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
    else:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
    return browser, context


# ---------------------------------------------------------------------------
# Login check / manual login flow
# ---------------------------------------------------------------------------
async def check_logged_in(page: Page) -> bool:
    await page.goto("https://web.snapchat.com/", wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)
    return "web.snapchat.com" in page.url and "/login" not in page.url


async def manual_login_and_save(emit: Callable[[str], None] | None = None) -> str:
    """
    Opens a visible (non-headless) browser so the user can log in manually.
    Saves the session once authenticated.
    Returns a status message.
    """
    async with async_playwright() as p:
        browser, context = await _load_context(p, headless=False)
        page = await context.new_page()
        await page.goto("https://web.snapchat.com/", timeout=30_000)
        _log("Browser opened for manual login. Waiting up to 3 minutes...", emit)

        deadline = time.time() + 180
        logged_in = False
        while time.time() < deadline:
            await asyncio.sleep(3)
            url = page.url
            if "web.snapchat.com" in url and "/login" not in url and "/accounts" not in url:
                logged_in = True
                break

        if logged_in:
            await _save_session(context)
            msg = "Login successful – session saved."
        else:
            msg = "Login timed out. Please try again."

        _log(msg, emit)
        await browser.close()
        return msg


# ---------------------------------------------------------------------------
# Send streaks
# ---------------------------------------------------------------------------
async def send_streaks(
    friends: list[str],
    emit: Callable[[str], None] | None = None,
) -> dict:
    """
    Send a snap to each username in `friends`.
    Returns { username: "ok" | "error: ..." }
    """
    ensure_snap_image()
    results: dict[str, str] = {}

    if not friends:
        _log("No friends configured – nothing to send.", emit)
        return results

    if not SESSION_FILE.exists():
        msg = "No session found. Please log in first via the web UI."
        _log(msg, emit)
        return {f: msg for f in friends}

    async with async_playwright() as p:
        browser, context = await _load_context(p, headless=True)
        page = await context.new_page()

        # Verify still logged in
        logged_in = await check_logged_in(page)
        if not logged_in:
            _log("Session expired – need to re-login.", emit)
            await browser.close()
            return {f: "session_expired" for f in friends}

        await asyncio.sleep(2)

        for username in friends:
            try:
                _log(f"Sending streak to @{username} ...", emit)
                result = await _send_to_friend(page, username, emit)
                results[username] = result
                await asyncio.sleep(2)  # brief pause between friends
            except Exception as ex:
                msg = f"error: {ex}"
                _log(f"  ✗ {username}: {msg}", emit)
                results[username] = msg

        # Refresh saved session (keeps cookies fresh)
        await _save_session(context)
        await browser.close()

    return results


async def _send_to_friend(page: Page, username: str, emit) -> str:
    """Navigate to a user's DM and send a snap image."""

    # --- Go to the DM directly via URL ---
    # Snapchat web supports direct chat links
    dm_url = f"https://web.snapchat.com/web/deeplink/directchat?username={username}"
    await page.goto(dm_url, wait_until="networkidle", timeout=20_000)
    await asyncio.sleep(3)

    # --- Look for the camera / media-upload button ---
    # The camera icon in Snapchat Web chat toolbar
    # These selectors may need updating if Snapchat changes their DOM.
    selectors_camera = [
        'button[data-testid="camera-button"]',
        'button[aria-label*="camera" i]',
        'button[aria-label*="Camera" i]',
        '[data-e2e="camera-button"]',
        'button svg[aria-label*="camera" i]',
    ]

    camera_btn = None
    for sel in selectors_camera:
        try:
            camera_btn = await page.wait_for_selector(sel, timeout=4_000)
            if camera_btn:
                break
        except Exception:
            pass

    if not camera_btn:
        # Fallback: look for any file input directly
        return await _upload_via_file_input(page, username, emit)

    await camera_btn.click()
    await asyncio.sleep(1)

    return await _upload_via_file_input(page, username, emit)


async def _upload_via_file_input(page: Page, username: str, emit) -> str:
    """
    Finds a file input on the page (Snapchat web uses one for media uploads)
    and uploads our snap image, then clicks send.
    """
    # Trigger the hidden file input
    file_input = None
    for sel in ['input[type="file"]', 'input[accept*="image"]', 'input[accept*="video"]']:
        try:
            file_input = await page.wait_for_selector(sel, timeout=5_000)
            if file_input:
                break
        except Exception:
            pass

    if not file_input:
        raise RuntimeError("Could not find file upload input on page.")

    await file_input.set_input_files(str(SNAP_IMAGE))
    await asyncio.sleep(2)

    # Click the Send button
    send_selectors = [
        'button[data-testid="send-button"]',
        'button[aria-label*="send" i]',
        'button[aria-label*="Send" i]',
        '[data-e2e="send-button"]',
    ]
    sent = False
    for sel in send_selectors:
        try:
            send_btn = await page.wait_for_selector(sel, timeout=4_000)
            if send_btn:
                await send_btn.click()
                sent = True
                break
        except Exception:
            pass

    if not sent:
        # Last resort: press Enter
        await page.keyboard.press("Enter")

    await asyncio.sleep(2)
    _log(f"  ✓ Snap sent to @{username}", emit)
    return "ok"
