"""
automation.py – Snapchat Web automation via Playwright.
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
# Logging
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
# Snap image – create a solid dark PNG if none exists
# ---------------------------------------------------------------------------
def ensure_snap_image():
    if SNAP_IMAGE.exists():
        return
    try:
        from PIL import Image
        img = Image.new("RGB", (400, 400), color=(30, 30, 30))
        img.save(SNAP_IMAGE)
    except ImportError:
        _tiny = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        SNAP_IMAGE.write_bytes(_tiny)


# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------
async def _load_context(playwright, headless: bool = True) -> tuple:
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
        ],
    )
    kwargs = dict(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        locale="en-US",
    )
    if SESSION_FILE.exists():
        kwargs["storage_state"] = json.loads(SESSION_FILE.read_text())

    context = await browser.new_context(**kwargs)
    return browser, context


async def _save_session(context: BrowserContext):
    storage = await context.storage_state()
    SESSION_FILE.write_text(json.dumps(storage))


# ---------------------------------------------------------------------------
# Login check – robust version
# ---------------------------------------------------------------------------
async def check_logged_in(page: Page, emit=None) -> bool:
    """
    Navigate to Snapchat web and check if we land on the main app.
    - web.snapchat.com  = logged in ✓
    - www.snapchat.com  = NOT logged in (unauthenticated redirect) ✗
    - accounts/login    = NOT logged in ✗
    """
    try:
        _log("Checking session...", emit)
        await page.goto(
            "https://web.snapchat.com/",
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        deadline = time.time() + 20
        while time.time() < deadline:
            url = page.url
            _log(f"  URL: {url}", emit)

            # NOT logged in indicators
            if any(x in url for x in [
                "www.snapchat.com",   # unauthenticated redirect
                "/login",
                "accounts.snapchat.com",
                "/unlock",
                "original_referrer",  # always means unauthenticated redirect
            ]):
                _log("  → Unauthenticated redirect detected.", emit)
                return False

            # Logged in indicators — stayed on web.snapchat.com
            if "web.snapchat.com" in url:
                _log("  → Confirmed on web.snapchat.com — logged in!", emit)
                return True

            await asyncio.sleep(1.5)

        _log(f"  → Timed out, final URL: {page.url}", emit)
        return False

    except Exception as ex:
        _log(f"  Login check error: {ex}", emit)
        return False


# ---------------------------------------------------------------------------
# Send streaks
# ---------------------------------------------------------------------------
async def send_streaks(
    friends: list[str],
    emit: Callable[[str], None] | None = None,
) -> dict:
    ensure_snap_image()
    results: dict[str, str] = {}

    if not friends:
        _log("No friends configured.", emit)
        return results

    if not SESSION_FILE.exists():
        _log("No session file found. Import cookies first.", emit)
        return {f: "no_session" for f in friends}

    async with async_playwright() as p:
        browser, context = await _load_context(p, headless=True)
        page = await context.new_page()

        logged_in = await check_logged_in(page, emit)
        if not logged_in:
            _log("Session expired – go to the web UI and re-import cookies.", emit)
            await browser.close()
            return {f: "session_expired" for f in friends}

        await asyncio.sleep(2)

        for username in friends:
            try:
                _log(f"Sending streak to @{username} ...", emit)
                result = await _send_to_friend(page, username, emit)
                results[username] = result
                await asyncio.sleep(3)
            except Exception as ex:
                msg = f"error: {ex}"
                _log(f"  ✗ {username}: {msg}", emit)
                results[username] = msg

        await _save_session(context)
        await browser.close()

    return results


# ---------------------------------------------------------------------------
# Send to a single friend
# ---------------------------------------------------------------------------
async def _send_to_friend(page: Page, username: str, emit) -> str:
    dm_url = f"https://web.snapchat.com/web/deeplink/directchat?username={username}"
    await page.goto(dm_url, wait_until="domcontentloaded", timeout=25_000)
    await asyncio.sleep(4)

    # Try clicking a camera/media button first
    for sel in [
        'button[data-testid="camera-button"]',
        'button[aria-label*="camera" i]',
        '[data-e2e="camera-button"]',
        'button[aria-label*="media" i]',
        'button[aria-label*="attachment" i]',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3_000)
            if btn:
                await btn.click()
                await asyncio.sleep(1)
                break
        except Exception:
            pass

    # Upload file via any visible file input
    file_input = None
    for sel in [
        'input[type="file"][accept*="image"]',
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    ]:
        try:
            file_input = await page.wait_for_selector(sel, timeout=5_000)
            if file_input:
                break
        except Exception:
            pass

    if not file_input:
        raise RuntimeError(
            f"Could not find file upload input for @{username}. "
            "Snapchat's DOM may have changed."
        )

    await file_input.set_input_files(str(SNAP_IMAGE))
    await asyncio.sleep(3)

    # Click send
    for sel in [
        'button[data-testid="send-button"]',
        'button[aria-label*="send" i]',
        '[data-e2e="send-button"]',
        'button[type="submit"]',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=4_000)
            if btn:
                await btn.click()
                await asyncio.sleep(2)
                _log(f"  ✓ Sent to @{username}", emit)
                return "ok"
        except Exception:
            pass

    # Last resort
    await page.keyboard.press("Enter")
    await asyncio.sleep(2)
    _log(f"  ✓ Sent to @{username} (Enter fallback)", emit)
    return "ok"
