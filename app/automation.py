"""
automation.py – Emulates a real desktop user on web.snapchat.com
"""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, BrowserContext, Page, Locator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR   = Path(os.environ.get("DATA_DIR", "/data"))
SESSION_FILE = DATA_DIR / "session.json"
SNAP_IMAGE   = DATA_DIR / "snap.png"
LOG_FILE     = DATA_DIR / "activity.log"
SCREENSHOT_FILE = DATA_DIR / "last_screenshot.png"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Realistic desktop Chrome fingerprint (matches Playwright Chromium 130)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.6723.31 Safari/537.36"
)
VIEWPORT = {"width": 1440, "height": 900}


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
# Snap image
# ---------------------------------------------------------------------------
def ensure_snap_image():
    if SNAP_IMAGE.exists():
        return
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 600), color=(20, 20, 30))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 800, 600], fill=(random.randint(10,40), random.randint(10,40), random.randint(10,40)))
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
# Human-like helpers
# ---------------------------------------------------------------------------
async def _human_delay(min_ms: int = 600, max_ms: int = 1400):
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _take_screenshot(page: Page, label: str = ""):
    try:
        await page.screenshot(path=str(SCREENSHOT_FILE), full_page=False)
        _log(f"  📸 Screenshot saved [{label}]")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Browser context — full desktop emulation
# ---------------------------------------------------------------------------
async def _build_context(playwright, headless: bool = True):
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",  # hide automation flag
        ],
    )

    ctx_kwargs = dict(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/Los_Angeles",
        # Realistic desktop headers
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )

    if SESSION_FILE.exists():
        ctx_kwargs["storage_state"] = json.loads(SESSION_FILE.read_text())

    context = await browser.new_context(**ctx_kwargs)

    # Mask navigator.webdriver so Snapchat doesn't detect automation
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return browser, context


async def _save_session(context: BrowserContext):
    storage = await context.storage_state()
    SESSION_FILE.write_text(json.dumps(storage))


# ---------------------------------------------------------------------------
# Login check
# ---------------------------------------------------------------------------
async def check_logged_in(page: Page, emit=None) -> bool:
    _log("Navigating to web.snapchat.com...", emit)
    try:
        await page.goto(
            "https://web.snapchat.com/",
            wait_until="domcontentloaded",
            timeout=35_000,
        )
    except Exception as ex:
        _log(f"  Navigation error: {ex}", emit)
        return False

    # Wait up to 15s to see where we end up
    deadline = time.time() + 15
    while time.time() < deadline:
        url = page.url
        _log(f"  URL: {url}", emit)

        # Unauthenticated — Snapchat redirects to www or shows login
        if any(x in url for x in [
            "www.snapchat.com",
            "original_referrer",
            "/login",
            "accounts.snapchat.com",
        ]):
            await _take_screenshot(page, "unauthenticated")
            _log("  → Not logged in (redirected away from web app).", emit)
            return False

        # Authenticated — stayed on web.snapchat.com
        if "web.snapchat.com" in url:
            # Extra confirmation: wait for the chat sidebar to appear
            try:
                await page.wait_for_selector(
                    '[data-testid="chat-list-header"], '
                    '[aria-label="Chats"], '
                    '[data-testid="nav-item-chat"]',
                    timeout=10_000,
                )
                await _take_screenshot(page, "logged_in")
                _log("  → Chat UI detected — logged in ✓", emit)
                return True
            except Exception:
                # UI not found yet but URL is right — give it a moment
                pass

        await asyncio.sleep(1.5)

    await _take_screenshot(page, "timeout")
    _log(f"  → Timed out. Final URL: {page.url}", emit)
    return False


# ---------------------------------------------------------------------------
# Send streaks — main entry point
# ---------------------------------------------------------------------------
async def _live_stream_task(page: Page, is_running_flag: list):
    """Background task to continuously capture screenshot while automation is sending."""
    while is_running_flag[0]:
        try:
            await page.screenshot(path=str(SCREENSHOT_FILE), type="jpeg", quality=75, full_page=False)
        except Exception:
            pass
        await asyncio.sleep(0.8)


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
        _log("No session file. Import cookies first.", emit)
        return {f: "no_session" for f in friends}

    async with async_playwright() as p:
        browser, context = await _build_context(p, headless=True)
        page = await context.new_page()

        # Start live background screenshot loop
        run_flag = [True]
        stream_task = asyncio.create_task(_live_stream_task(page, run_flag))

        try:
            logged_in = await check_logged_in(page, emit)
            if not logged_in:
                _log("Not logged in — re-login in the web UI first.", emit)
                run_flag[0] = False
                await browser.close()
                return {f: "session_expired" for f in friends}

            await _human_delay(1500, 2500)

            for username in friends:
                try:
                    _log(f"Sending streak to @{username}...", emit)
                    result = await _send_to_friend(page, username, emit)
                    results[username] = result
                    await _human_delay(3000, 5000)  # natural pause between sends
                except Exception as ex:
                    msg = f"error: {ex}"
                    _log(f"  ✗ {username}: {msg}", emit)
                    await _take_screenshot(page, f"error_{username}")
                    results[username] = msg

            await _save_session(context)
        finally:
            run_flag[0] = False
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# Send to a single friend — navigates like a real user
# ---------------------------------------------------------------------------
async def _send_to_friend(page: Page, username: str, emit) -> str:
    """
    Real desktop flow:
    1. Use the search box to find the friend
    2. Click their chat thread
    3. Click the camera/media button in the chat
    4. Upload the snap image via file input
    5. Click Send
    """

    # ── Step 1: Search for the friend ──────────────────────────────────────
    _log(f"  Searching for @{username}...", emit)

    search_selectors = [
        '[data-testid="search-input"]',
        'input[placeholder*="Search" i]',
        'input[placeholder*="search" i]',
        '[aria-label*="Search" i]',
        'input[type="search"]',
    ]

    search_box = None
    for sel in search_selectors:
        try:
            search_box = await page.wait_for_selector(sel, timeout=5_000)
            if search_box:
                break
        except Exception:
            pass

    if not search_box:
        # Fallback: try clicking the search/new chat icon first
        for icon_sel in [
            '[aria-label*="new chat" i]',
            '[aria-label*="compose" i]',
            '[data-testid="new-chat"]',
        ]:
            try:
                btn = await page.wait_for_selector(icon_sel, timeout=2_000)
                if btn:
                    await btn.click()
                    await _human_delay()
                    break
            except Exception:
                pass

        for sel in search_selectors:
            try:
                search_box = await page.wait_for_selector(sel, timeout=4_000)
                if search_box:
                    break
            except Exception:
                pass

    if not search_box:
        raise RuntimeError("Could not find search box in Snapchat Web UI.")

    # Click search box and type username naturally
    await search_box.click()
    await _human_delay(300, 600)
    await search_box.fill("")
    await _human_delay(200, 400)

    # Type character by character like a human
    for char in username:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.05, 0.15))

    await _human_delay(1200, 2000)
    await _take_screenshot(page, f"search_{username}")

    # ── Step 2: Click the friend's result ──────────────────────────────────
    _log(f"  Clicking @{username} in results...", emit)

    result_selectors = [
        f'[data-testid="user-result-{username}"]',
        f'[aria-label*="{username}" i]',
        f'[title*="{username}" i]',
        '[data-testid="search-result"]:first-child',
        '[data-testid="user-row"]:first-child',
        '.search-result:first-child',
    ]

    clicked_result = False
    for sel in result_selectors:
        try:
            result = await page.wait_for_selector(sel, timeout=4_000)
            if result:
                await result.click()
                clicked_result = True
                break
        except Exception:
            pass

    if not clicked_result:
        # Last resort: press Enter to open first result
        await page.keyboard.press("Enter")

    await _human_delay(1500, 2500)
    await _take_screenshot(page, f"chat_{username}")

    # ── Step 3: Clear search and open the chat ─────────────────────────────
    # Press Escape to close search if needed
    await page.keyboard.press("Escape")
    await _human_delay(500, 800)

    # ── Step 4: Upload snap via file input ────────────────────────────────
    _log(f"  Uploading snap to @{username}...", emit)

    # Try clicking a camera/media/attachment button first
    for sel in [
        '[aria-label*="camera" i]',
        '[aria-label*="photo" i]',
        '[aria-label*="media" i]',
        '[aria-label*="attachment" i]',
        '[data-testid="camera-button"]',
        '[data-testid="media-button"]',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3_000)
            if btn:
                await btn.click()
                await _human_delay(600, 1000)
                break
        except Exception:
            pass

    # Find the file input (may be hidden)
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
        await _take_screenshot(page, f"no_input_{username}")
        raise RuntimeError(
            "Could not find file upload input. "
            "Check the screenshot at /api/screenshot to see what the browser sees."
        )

    await file_input.set_input_files(str(SNAP_IMAGE))
    await _human_delay(2000, 3000)
    await _take_screenshot(page, f"uploaded_{username}")

    # ── Step 5: Send ──────────────────────────────────────────────────────
    _log(f"  Sending to @{username}...", emit)

    for sel in [
        '[data-testid="send-button"]',
        '[aria-label*="send" i]',
        'button[type="submit"]',
        '[data-e2e="send-button"]',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=4_000)
            if btn:
                await _human_delay(400, 700)
                await btn.click()
                await _human_delay(2000, 3000)
                _log(f"  ✓ Streak sent to @{username}", emit)
                return "ok"
        except Exception:
            pass

    # Fallback: Enter key
    await page.keyboard.press("Enter")
    await _human_delay(2000, 3000)
    _log(f"  ✓ Streak sent to @{username} (Enter)", emit)
    return "ok"
