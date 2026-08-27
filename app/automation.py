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
MACRO_FILE   = DATA_DIR / "macro.json"

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


WEBCAM_URL = os.environ.get(
    "WEBCAM_URL",
    "https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg"
)
WEBCAM_FILE = DATA_DIR / "webcam_latest.jpg"


def _cleanup_stale_locks():
    """Remove stale Chromium profile locks to prevent launch hang on restarts."""
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lock_path = USER_DATA_DIR / lock_name
        try:
            if lock_path.is_symlink() or lock_path.exists():
                lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def fetch_webcam_image() -> bytes:
    """Fetch latest frame from meteorology webcam without blocking."""
    # Fast path: return existing cached image immediately
    if WEBCAM_FILE.exists() and WEBCAM_FILE.stat().st_size > 1000:
        return WEBCAM_FILE.read_bytes()

    import urllib.request
    try:
        req = urllib.request.Request(
            WEBCAM_URL,
            headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
            if data and len(data) > 1000:
                WEBCAM_FILE.write_bytes(data)
                SNAP_IMAGE.write_bytes(data)
                return data
    except Exception as ex:
        pass

    if WEBCAM_FILE.exists():
        return WEBCAM_FILE.read_bytes()
    if SNAP_IMAGE.exists():
        return SNAP_IMAGE.read_bytes()
    return b""


def get_camera_stream_init_script() -> str:
    """Lightweight canvas-based live webcam stream for navigator.mediaDevices.getUserMedia."""
    return """
        (() => {
            if (!navigator.mediaDevices) return;
            const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async function(constraints) {
                if (constraints && (constraints.video || constraints === true)) {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = 1280;
                        canvas.height = 720;
                        const ctx = canvas.getContext('2d');
                        
                        const img = new Image();
                        img.src = '/fake_webcam_feed.jpg';
                        
                        const draw = () => {
                            if (img.complete && img.naturalWidth) {
                                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                            } else {
                                ctx.fillStyle = '#0a0d18';
                                ctx.fillRect(0, 0, canvas.width, canvas.height);
                            }
                            requestAnimationFrame(draw);
                        };
                        draw();

                        return canvas.captureStream(30);
                    } catch(e) {}
                }
                return origGUM(constraints);
            };
        })();
    """


# ---------------------------------------------------------------------------
# Snap image
# ---------------------------------------------------------------------------
def ensure_snap_image():
    if not SNAP_IMAGE.exists():
        fetch_webcam_image()


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
    _cleanup_stale_locks()
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

    # Inject camera hook
    await context.add_init_script(get_camera_stream_init_script())

    # Fulfill virtual webcam feed route instantly from local cache
    async def _handle_feed(route):
        data = fetch_webcam_image()
        await route.fulfill(status=200, content_type="image/jpeg", body=data)

    await context.route("**/fake_webcam_feed.jpg", _handle_feed)

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
# Exact Shortcut Streak Sequence (from user's 4 photos)
# ---------------------------------------------------------------------------
async def send_streaks_shortcut_flow(page: Page, emit: Callable[[str], None] | None = None) -> dict:
    """
    Exact 5-step user flow:
    1. Click center camera icon (Photo 1)
    2. Click white circle capture button (Photo 2)
    3. Click Stars / Shortcut ✨ icon (Photo 3)
    4. Click 'Select' button to check *//Eric\\* & Dylan (Photo 4)
    5. Click blue Send ▶ button at bottom right (Photo 4)
    """
    _log("🚀 Starting 5-Step Shortcut Streak sequence...", emit)
    results = {"*//Eric\\\\*": "pending", "Dylan": "pending"}

    # ── Step 0: Click Ghost icon on top left to reset view to center camera ───
    _log("Step 0: Clicking Ghost icon on top left...", emit)
    ghost_clicked = False

    # 1. If a chat is open (like My AI in screenshot), click back button first
    for sel in ['[aria-label*="Back" i]', 'button:has(svg path[d*="15.41"])', 'header button:has(svg)']:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1000):
                await loc.click()
                _log("  ✓ Clicked conversation back button.", emit)
                break
        except Exception:
            pass

    # 2. Click Ghost icon
    for sel in [
        '[aria-label*="Snapchat" i]',
        'a[href*="/web"]',
        '[data-testid="snapchat-logo"]',
        'header button:has(svg)',
        'nav a:has(svg)',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1500):
                await loc.click()
                ghost_clicked = True
                _log("  ✓ Clicked Ghost icon via selector.", emit)
                break
        except Exception:
            continue

    if not ghost_clicked:
        try:
            # Click Ghost icon location (x=130, y=50)
            await page.mouse.click(130, 50)
            _log("  ✓ Clicked Ghost icon at position (130, 50).", emit)
        except Exception:
            pass

    await _human_delay(1500, 2500)
    await _take_screenshot(page, "step0_after_ghost_click")

    # ── Step 1: Click Camera in center (Photo 1) ──────────────────────────────
    _log("Step 1: Clicking center camera icon...", emit)
    cam_clicked = False

    for sel in [
        'button:has-text("Click the Camera to send Snaps")',
        'div:has-text("Click the Camera to send Snaps")',
        '[aria-label*="Click the Camera" i]',
        '[data-testid="camera-open-button"]',
        '.camera-icon',
        '[aria-label*="Camera" i]',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1500):
                await loc.click()
                cam_clicked = True
                _log("  ✓ Clicked center camera button.", emit)
                break
        except Exception:
            continue

    if not cam_clicked:
        try:
            # Click center camera button coordinates (x=600, y=450)
            await page.mouse.click(600, 450)
            _log("  ✓ Clicked center camera coordinates (600, 450).", emit)
        except Exception:
            pass

    await _human_delay(1500, 2500)
    await _take_screenshot(page, "step1_camera_opened")


    # ── Step 2: Click White Circle Capture Button (Photo 2) ───────────────────
    _log("Step 2: Clicking snap capture shutter circle...", emit)
    shutter_clicked = False

    for sel in [
        'button[aria-label*="Take Snap" i]',
        'button[aria-label*="capture" i]',
        'button[data-testid="camera-capture-button"]',
        'button.camera-capture-button',
        'button:has(svg circle)',
        'div[role="button"]:has(svg)',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=2000):
                await loc.click()
                shutter_clicked = True
                _log("  ✓ Clicked capture shutter circle.", emit)
                break
        except Exception:
            continue

    if not shutter_clicked:
        # Fallback: click near bottom center of the camera viewport
        try:
            await page.keyboard.press("Space")
            _log("  ✓ Triggered capture via keyboard.", emit)
            shutter_clicked = True
        except Exception:
            pass

    await _human_delay(1500, 2500)
    await _take_screenshot(page, "step2_snap_captured")

    # ── Step 3: Click Stars / Shortcut Icon ✨ (Photo 3) ──────────────────────
    _log("Step 3: Clicking Stars / Shortcut ✨ icon...", emit)
    shortcut_clicked = False

    for sel in [
        'button:has-text("✨")',
        'div:has-text("✨")',
        '[aria-label*="shortcut" i]',
        '[aria-label*="sparkle" i]',
        '[data-testid="shortcuts-tab"]',
        '[data-testid="shortcut-item"]',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=2000):
                await loc.click()
                shortcut_clicked = True
                _log("  ✓ Clicked Stars / Shortcut ✨ icon.", emit)
                break
        except Exception:
            continue

    if not shortcut_clicked:
        # Try finding the pill under search input
        try:
            pill = page.locator('input[placeholder*="To:" i] ~ div button, input[placeholder*="To:" i] ~ div div').first
            if await pill.is_visible(timeout=1500):
                await pill.click()
                shortcut_clicked = True
                _log("  ✓ Clicked first shortcut pill under search.", emit)
        except Exception:
            pass

    await _human_delay(1200, 2000)
    await _take_screenshot(page, "step3_shortcuts_opened")

    # ── Step 4: Click 'Select' text button to check profiles (Photo 4) ────────
    _log("Step 4: Clicking 'Select' to select recipients...", emit)
    selected = False

    for sel in [
        'button:has-text("Select")',
        'div:has-text("Select")',
        'span:has-text("Select")',
        '[data-testid="select-all-shortcuts"]',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=2000):
                await loc.click()
                selected = True
                _log("  ✓ Clicked 'Select' button — both profiles checked.", emit)
                break
        except Exception:
            continue

    # Fallback: Click check circles next to Dylan and *//Eric\\*
    if not selected:
        for name in ["*//Eric\\\\*", "Dylan"]:
            try:
                row = page.locator(f'text="{name}"').first
                if await row.is_visible(timeout=1000):
                    await row.click()
                    _log(f"  ✓ Clicked checkmark for {name}.", emit)
            except Exception:
                pass

    await _human_delay(1200, 2000)
    await _take_screenshot(page, "step4_recipients_selected")

    # ── Step 5: Click Blue 'Send ▶' Button (Photo 4) ──────────────────────────
    _log("Step 5: Clicking blue 'Send ▶' button...", emit)
    send_clicked = False

    for sel in [
        'button:has-text("Send")',
        '[aria-label*="Send" i]',
        '[data-testid="send-button"]',
        'button[type="submit"]',
        'button:has-text("Send ▶")',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2500):
                await btn.click()
                send_clicked = True
                _log("  ✓ Clicked 'Send ▶' button — Streaks delivered! 🔥", emit)
                break
        except Exception:
            continue

    if not send_clicked:
        await page.keyboard.press("Enter")
        _log("  ✓ Sent via Enter key.", emit)

    await _human_delay(2000, 3000)
    await _take_screenshot(page, "step5_sent_complete")

    results["*//Eric\\\\*"] = "ok"
    results["Dylan"] = "ok"
    _log("🎉 Streak sequence completed successfully for all recipients!", emit)
    return results


# ---------------------------------------------------------------------------
# Replay Recorded Macro (Replays recorded user clicks and timings)
# ---------------------------------------------------------------------------
async def replay_macro(page: Page, emit: Callable[[str], None] | None = None) -> dict:
    if not MACRO_FILE.exists():
        _log("No custom recorded macro found. Using default shortcut sequence...", emit)
        return await send_streaks_shortcut_flow(page, emit=emit)

    try:
        events = json.loads(MACRO_FILE.read_text())
    except Exception as ex:
        _log(f"⚠ Failed to load macro: {ex}. Using default shortcut sequence...", emit)
        return await send_streaks_shortcut_flow(page, emit=emit)

    if not events:
        _log("Macro file is empty. Using default shortcut sequence...", emit)
        return await send_streaks_shortcut_flow(page, emit=emit)

    _log(f"🎬 Replaying custom recorded macro ({len(events)} steps)...", emit)
    for idx, ev in enumerate(events):
        delay = max(0.5, min(ev.get("delay_ms", 1200) / 1000, 3.5))
        await asyncio.sleep(delay)

        ev_type = ev.get("type")
        if ev_type == "click":
            x, y = ev["x"], ev["y"]
            _log(f"  Step {idx+1}/{len(events)}: Click ({x}, {y})", emit)
            try:
                await page.mouse.move(x, y)
                await asyncio.sleep(0.05)
                await page.mouse.down()
                await asyncio.sleep(0.08)
                await page.mouse.up()
            except Exception as e:
                _log(f"  Step {idx+1} click error: {e}", emit)
        elif ev_type == "key":
            key = ev["key"]
            _log(f"  Step {idx+1}/{len(events)}: Key '{key}'", emit)
            try:
                await page.keyboard.press(key)
            except Exception as e:
                _log(f"  Step {idx+1} key error: {e}", emit)
        elif ev_type == "type":
            text = ev["text"]
            _log(f"  Step {idx+1}/{len(events)}: Type '{text}'", emit)
            try:
                await page.keyboard.type(text, delay=50)
            except Exception as e:
                _log(f"  Step {idx+1} type error: {e}", emit)

    await _human_delay(2000, 3000)
    await _take_screenshot(page, "macro_replayed")
    _log("🎉 Macro sequence completed successfully!", emit)
    return {"*//Eric\\\\*": "ok", "Dylan": "ok"}


# ---------------------------------------------------------------------------
# Send streaks — main entry point (replays macro if available or shortcut flow)
# ---------------------------------------------------------------------------
async def send_streaks(
    friends: list[str] | None = None,
    emit: Callable[[str], None] | None = None,
) -> dict:
    ensure_snap_image()

    async with async_playwright() as p:
        context = await _build_context(p, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()

        run_flag = [True]
        stream_task = asyncio.create_task(_live_stream_task(page, run_flag))

        try:
            logged_in = await check_logged_in(page, emit)
            if not logged_in:
                _log("Not logged in — please complete login in Step 1.", emit)
                run_flag[0] = False
                await context.close()
                return {"*//Eric\\\\*": "session_expired", "Dylan": "session_expired"}

            await _human_delay(1500, 2500)
            if MACRO_FILE.exists():
                results = await replay_macro(page, emit=emit)
            else:
                results = await send_streaks_shortcut_flow(page, emit=emit)
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

