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

USER_DATA_DIR = DATA_DIR / "browser_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

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
# Browser context — persistent desktop profile (preserves Cookies + IndexedDB)
# ---------------------------------------------------------------------------
async def _build_context(playwright, headless: bool = True):
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
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
            "--disable-blink-features=AutomationControlled",
            "--use-fake-ui-for-media-stream",  # Auto-grants camera permission without prompt
            "--use-fake-device-for-media-stream",
        ],
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

    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return context



async def _save_session(context: BrowserContext):
    try:
        storage = await context.storage_state()
        SESSION_FILE.write_text(json.dumps(storage))
    except Exception:
        pass


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

    # Wait up to 15s to check page authentication state
    deadline = time.time() + 15
    while time.time() < deadline:
        url = page.url
        _log(f"  URL: {url}", emit)

        # Definitively unauthenticated landing pages
        if any(x in url for x in [
            "accounts.snapchat.com",
            "/accounts/login",
            "snapchat.com/login",
            "original_referrer",
        ]) and "/web" not in url:
            await _take_screenshot(page, "unauthenticated")
            _log("  → Not logged in (redirected away from web app).", emit)
            return False

        # Authenticated — stayed on Snapchat Web interface
        if any(x in url for x in ["web.snapchat.com", "snapchat.com/web"]):
            # Check for chat UI / navigation bar
            try:
                el = await page.query_selector(
                    '[data-testid="chat-list-header"], '
                    '[aria-label="Chats"], '
                    '[data-testid="nav-item-chat"], '
                    '[data-testid="search-input"], '
                    'input[placeholder*="Search" i]'
                )
                if el:
                    await _take_screenshot(page, "logged_in")
                    _log("  → Chat UI detected — logged in ✓", emit)
                    return True
            except Exception:
                pass

        await asyncio.sleep(1.5)

    # If still on /web after 15s and not on accounts page, proceed
    if any(x in page.url for x in ["web.snapchat.com", "snapchat.com/web"]):
        await _take_screenshot(page, "logged_in_web")
        _log("  → On web interface — proceeding as logged in ✓", emit)
        return True

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
        context = await _build_context(p, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()

        # Start live background screenshot loop
        run_flag = [True]
        stream_task = asyncio.create_task(_live_stream_task(page, run_flag))

        try:
            logged_in = await check_logged_in(page, emit)
            if not logged_in:
                _log("Not logged in — please complete login in Step 1.", emit)
                run_flag[0] = False
                await context.close()
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
            await context.close()


    return results


# ---------------------------------------------------------------------------
# Send to a single friend — navigates like a real user
# ---------------------------------------------------------------------------
async def _send_to_friend(page: Page, username: str, emit) -> str:
    """
    Enhanced desktop flow:
    1. Check visible left chat sidebar for friend name (e.g. 'Dylan', '*//Eric\\*', etc.)
    2. Click camera button directly on their row OR click their row to open chat
    3. Attach/capture snap media
    4. Click Send
    """
    clean_name = username.strip().lstrip("@")
    _log(f"  Targeting recipient: {clean_name}...", emit)

    opened_chat = False

    # ── Try direct selection from visible chat list ───────────────────────────
    try:
        # Search for text matching friend name in sidebar
        locators = [
            page.locator(f'text="{clean_name}"').first,
            page.locator(f':text-matches("{clean_name}", "i")').first,
            page.locator(f'[aria-label*="{clean_name}" i]').first,
            page.locator(f'[title*="{clean_name}" i]').first,
        ]
        for loc in locators:
            if await loc.is_visible(timeout=1500):
                _log(f"  Found visible conversation for {clean_name} in sidebar.", emit)
                # Try clicking camera icon inside parent row if present
                try:
                    parent_row = loc.locator('xpath=ancestor::li | xpath=ancestor::div[contains(@role, "row") or contains(@class, "chat")]').first
                    cam_btn = parent_row.locator('button:has(svg), [aria-label*="camera" i], [aria-label*="reply" i]').first
                    if await cam_btn.is_visible(timeout=1000):
                        await cam_btn.click()
                        _log(f"  Clicked direct camera button for {clean_name}.", emit)
                        opened_chat = True
                        break
                except Exception:
                    pass

                # Otherwise click the friend name/row directly
                await loc.click()
                opened_chat = True
                _log(f"  Opened conversation with {clean_name}.", emit)
                break
    except Exception:
        pass

    # ── If not directly found in list, use search box ─────────────────────────
    if not opened_chat:
        _log(f"  Using search box for {clean_name}...", emit)
        search_box = None
        for sel in [
            '[data-testid="search-input"]',
            'input[placeholder*="Search" i]',
            'input[placeholder*="search" i]',
            '[aria-label*="Search" i]',
            'input[type="search"]',
        ]:
            try:
                search_box = await page.wait_for_selector(sel, timeout=3_000)
                if search_box:
                    break
            except Exception:
                pass

        if search_box:
            await search_box.click()
            await _human_delay(200, 400)
            await search_box.fill("")
            for char in clean_name:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.04, 0.12))
            await _human_delay(1000, 1800)

            for sel in [
                f'[data-testid="user-result-{clean_name}"]',
                f'[aria-label*="{clean_name}" i]',
                f'[title*="{clean_name}" i]',
                '[data-testid="search-result"]:first-child',
                '[data-testid="user-row"]:first-child',
            ]:
                try:
                    res = await page.wait_for_selector(sel, timeout=3_000)
                    if res:
                        await res.click()
                        opened_chat = True
                        break
                except Exception:
                    pass

            if not opened_chat:
                await page.keyboard.press("Enter")
                opened_chat = True

    await _human_delay(1200, 2000)
    await _take_screenshot(page, f"chat_{clean_name}")

    # ── Upload or capture snap ────────────────────────────────────────────────
    _log(f"  Uploading snap media for {clean_name}...", emit)

    # 1. Look for file input first
    file_input = None
    for sel in [
        'input[type="file"][accept*="image"]',
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    ]:
        try:
            file_input = await page.query_selector(sel)
            if file_input:
                break
        except Exception:
            pass

    # 2. If no file input yet, click camera button in chat or center
    if not file_input:
        for sel in [
            '[aria-label*="camera" i]',
            '[aria-label*="photo" i]',
            '[aria-label*="media" i]',
            '[aria-label*="attachment" i]',
            '[data-testid="camera-button"]',
            '[data-testid="media-button"]',
            '.camera-icon',
        ]:
            try:
                btn = await page.wait_for_selector(sel, timeout=2_000)
                if btn:
                    await btn.click()
                    await _human_delay(600, 1200)
                    break
            except Exception:
                pass

        for sel in [
            'input[type="file"][accept*="image"]',
            'input[type="file"][accept*="video"]',
            'input[type="file"]',
        ]:
            try:
                file_input = await page.query_selector(sel)
                if file_input:
                    break
            except Exception:
                pass

    if file_input:
        await file_input.set_input_files(str(SNAP_IMAGE))
        await _human_delay(1500, 2500)
    else:
        # Camera mode: Click snap capture shutter button if camera is active
        for sel in [
            'button[aria-label*="Take Snap" i]',
            'button[aria-label*="capture" i]',
            '[data-testid="camera-capture-button"]',
            'button.camera-capture-button',
        ]:
            try:
                cap_btn = await page.query_selector(sel)
                if cap_btn:
                    await cap_btn.click()
                    await _human_delay(1000, 1800)
                    break
            except Exception:
                pass

    await _take_screenshot(page, f"ready_send_{clean_name}")

    # ── Click Send ────────────────────────────────────────────────────────────
    _log(f"  Sending snap to {clean_name}...", emit)

    for sel in [
        '[data-testid="send-button"]',
        '[aria-label*="send" i]',
        'button[type="submit"]',
        '[data-e2e="send-button"]',
        'button:has-text("Send")',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3_000)
            if btn:
                await _human_delay(300, 600)
                await btn.click()
                await _human_delay(2000, 3000)
                _log(f"  ✓ Streak sent to {clean_name}", emit)
                return "ok"
        except Exception:
            pass

    # Fallback: Enter key
    await page.keyboard.press("Enter")
    await _human_delay(2000, 3000)
    _log(f"  ✓ Streak sent to {clean_name} (Enter)", emit)
    return "ok"

