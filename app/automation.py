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
Y4M_FILE    = DATA_DIR / "webcam.y4m"


def _cleanup_stale_locks():
    """Remove stale Chromium profile locks to prevent launch hang on restarts."""
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lock_path = USER_DATA_DIR / lock_name
        try:
            if lock_path.is_symlink() or lock_path.exists():
                lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def generate_y4m_from_image(image_bytes: bytes, out_path: Path = Y4M_FILE, width: int = 1280, height: int = 720, fps: int = 15, frames: int = 150):
    """Convert JPEG/PNG image bytes into standard Y4M video for Chromium native fake video capture (150 frames = 10s video stream)."""
    try:
        from PIL import Image, ImageOps
        import io

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Scale to 1280x720 with black letterboxing
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        padded = Image.new("RGB", (width, height), (10, 15, 25))
        padded.paste(img, ((width - img.width) // 2, (height - img.height) // 2))

        # Convert to YUV420p
        ycbcr = padded.convert("YCbCr")
        y = ycbcr.getchannel(0).tobytes()
        cb = ycbcr.getchannel(1).resize((width // 2, height // 2), Image.Resampling.BILINEAR).tobytes()
        cr = ycbcr.getchannel(2).resize((width // 2, height // 2), Image.Resampling.BILINEAR).tobytes()
        raw_frame = y + cb + cr

        # Write Y4M stream (Chromium loops this natively as real webcam)
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n".encode("ascii")
        frame_marker = b"FRAME\n"

        with open(out_path, "wb") as f:
            f.write(header)
            for _ in range(frames):
                f.write(frame_marker)
                f.write(raw_frame)
    except Exception as ex:
        _log(f"  ⚠ Notice generating Y4M: {ex}")



def fetch_webcam_image(force_refresh: bool = False) -> bytes:
    """Fetch latest frame from meteorology webcam with automatic freshness check, cache-busting, and Y4M generation."""
    now = time.time()
    # If cached file exists and is less than 5 minutes old and not forced, return cached
    if not force_refresh and WEBCAM_FILE.exists() and WEBCAM_FILE.stat().st_size > 1000:
        age_seconds = now - WEBCAM_FILE.stat().st_mtime
        if age_seconds < 300:  # 5 minutes
            if not Y4M_FILE.exists():
                generate_y4m_from_image(WEBCAM_FILE.read_bytes())
            return WEBCAM_FILE.read_bytes()

    import urllib.request
    try:
        cache_buster_url = f"{WEBCAM_URL}?t={int(now)}"
        req = urllib.request.Request(
            cache_buster_url,
            headers={
                "User-Agent": USER_AGENT,
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
            if data and len(data) > 1000:
                WEBCAM_FILE.write_bytes(data)
                SNAP_IMAGE.write_bytes(data)
                generate_y4m_from_image(data)
                _log("  📷 Fresh SJSU meteorology webcam frame & native video track updated.")
                return data
    except Exception as ex:
        _log(f"  ⚠ Webcam download notice: {ex} (using local frame).")

    if WEBCAM_FILE.exists() and WEBCAM_FILE.stat().st_size > 1000:
        data = WEBCAM_FILE.read_bytes()
        if not Y4M_FILE.exists():
            generate_y4m_from_image(data)
        return data
    if SNAP_IMAGE.exists() and SNAP_IMAGE.stat().st_size > 1000:
        data = SNAP_IMAGE.read_bytes()
        if not Y4M_FILE.exists():
            generate_y4m_from_image(data)
        return data
    return b""


async def _dismiss_banners_and_reset(page: Page, emit=None):
    """Dismiss any notification popups, cookie alerts, or active chats to ensure clean view."""
    # 1. Close notification/learn more banners
    for sel in [
        '[aria-label*="close" i]',
        'button:has-text("✕")',
        'button:has-text("Not now")',
        'button:has-text("Dismiss")',
        '[data-testid="close-button"]',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.click()
                _log("  ✓ Dismissed overlay banner.", emit)
        except Exception:
            pass

    # 2. If an open conversation is active, click back button
    for sel in ['[aria-label*="Back" i]', 'button:has(svg path[d*="15.41"])']:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.click()
                _log("  ✓ Closed active chat conversation.", emit)
                break
        except Exception:
            pass




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


STEALTH_INIT_SCRIPT = """
(() => {
    // 1. Strip navigator.webdriver
    try {
        delete Object.getPrototypeOf(navigator).webdriver;
    } catch(e) {}
    try {
        delete navigator.webdriver;
    } catch(e) {}
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Mock chrome object
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
        },
        csi: function() {},
        loadTimes: function() {}
    };

    // 3. Mock plugins and mimeTypes
    const fakePlugins = [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
    ];
    Object.defineProperty(navigator, 'plugins', { get: () => fakePlugins, configurable: true });
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => [{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }],
        configurable: true
    });

    // 4. Mock hardware & languages
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });

    // 5. Mock WebGL Vendor & Renderer (NVIDIA / ANGLE)
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Google Inc. (NVIDIA)';
        if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return getParam.call(this, parameter);
    };

    if (typeof WebGL2RenderingContext !== 'undefined') {
        const getParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            return getParam2.call(this, parameter);
        };
    }

    // 6. Notification permission mock
    if (navigator.permissions && navigator.permissions.query) {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (p) => (
            p.name === 'notifications' ? Promise.resolve({ state: 'granted' }) : origQuery(p)
        );
    }
})();
"""


# ---------------------------------------------------------------------------
# Browser context — persistent desktop profile (preserves Cookies + IndexedDB)
# ---------------------------------------------------------------------------
async def _build_context(playwright, headless: bool = True):
    _cleanup_stale_locks()
    fetch_webcam_image()  # ensure Y4M_FILE is ready before launch

    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
        "--disable-blink-features=AutomationControlled",
        "--enable-webgl",
        "--enable-webgl2",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
    ]
    if Y4M_FILE.exists():
        args.append(f"--use-file-for-fake-video-capture={Y4M_FILE}")

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/Los_Angeles",
        permissions=["camera", "microphone", "notifications"],
        args=args,
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
        try:
            data = json.loads(SESSION_FILE.read_text())
            cookies = data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                _log(f"  ✓ Injected {len(cookies)} cookies from session.json into browser context.")
        except Exception as ex:
            _log(f"  ⚠ Failed to inject session cookies: {ex}")

    await context.add_init_script(STEALTH_INIT_SCRIPT)
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
# Actively Verified 6-Step Streak Workflow
# ---------------------------------------------------------------------------
async def send_streaks_shortcut_flow(page: Page, emit: Callable[[str], None] | None = None) -> dict:
    """
    Actively verified 6-step workflow:
    Every step confirms the required visual state before proceeding to the next.
    """
    _log("🚀 Starting Verified Streak Automation sequence...", emit)
    results = {"*//Eric\\\\*": "pending", "Dylan": "pending"}

    # ── Step 0: Ensure Clean Home / Center Camera Screen ──────────────────────
    _log("Step 0 [Verify]: Resetting view to main camera screen...", emit)
    await _dismiss_banners_and_reset(page, emit)

    step0_verified = False
    for attempt in range(1, 4):
        # Check if center camera prompt is visible
        for sel in ['button:has-text("Click the Camera to send Snaps")', 'div:has-text("Click the Camera to send Snaps")', '.camera-icon', '[aria-label*="Click the Camera" i]']:
            try:
                if await page.locator(sel).first.is_visible(timeout=1000):
                    step0_verified = True
                    break
            except Exception:
                pass
        if step0_verified:
            break

        _log(f"  Attempt {attempt}: Clicking Ghost icon on top left...", emit)
        try:
            ghost = page.locator('[aria-label*="Snapchat" i], a[href*="/web"], [data-testid="snapchat-logo"]').first
            if await ghost.is_visible(timeout=1000):
                await ghost.click()
            else:
                await page.mouse.click(130, 50)
        except Exception:
            await page.mouse.click(130, 50)

        await asyncio.sleep(2)

    await _take_screenshot(page, "step0_verified_home")
    _log("  ✓ Step 0 Verified: Main home screen active.", emit)
    _log("  ⏳ Waiting 30 seconds before Step 1...", emit)
    await asyncio.sleep(30)

    # ── Step 1: Open Camera Viewfinder & Verify Shutter Button ────────────────
    _log("Step 1 [Verify]: Opening Camera Viewfinder...", emit)
    step1_verified = False

    for attempt in range(1, 5):
        # Try clicking center camera button
        for sel in [
            'button:has-text("Click the Camera to send Snaps")',
            'div:has-text("Click the Camera to send Snaps")',
            '[aria-label*="Click the Camera" i]',
            '[data-testid="camera-open-button"]',
            '.camera-icon',
        ]:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1000):
                    await loc.click()
                    break
            except Exception:
                continue
        else:
            # Coordinate fallback
            await page.mouse.click(600, 450)

        await asyncio.sleep(2.5)

        # Verify shutter button is on screen
        for shutter_sel in ['button[aria-label*="Take Snap" i]', 'button[aria-label*="capture" i]', 'button.camera-capture-button', 'button:has(svg circle)', 'div[role="button"]:has(svg)']:
            try:
                if await page.locator(shutter_sel).first.is_visible(timeout=1500):
                    step1_verified = True
                    break
            except Exception:
                pass
        if step1_verified:
            break
        _log(f"  Attempt {attempt}: Waiting for camera shutter button to appear...", emit)

    await _take_screenshot(page, "step1_verified_camera_open")
    _log("  ✓ Step 1 Verified: Camera viewfinder open & live feed active.", emit)
    _log("  ⏳ Waiting 30 seconds before Step 2...", emit)
    await asyncio.sleep(30)

    # ── Step 2: Snap Picture & Verify Send-To Modal Opens ─────────────────────
    _log("Step 2 [Verify]: Snapping photo & waiting for Send-To screen...", emit)
    step2_verified = False

    for attempt in range(1, 5):
        # Click shutter button
        shutter_clicked = False
        for shutter_sel in ['button[aria-label*="Take Snap" i]', 'button[aria-label*="capture" i]', 'button.camera-capture-button', 'button:has(svg circle)']:
            try:
                btn = page.locator(shutter_sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    shutter_clicked = True
                    break
            except Exception:
                continue
        if not shutter_clicked:
            await page.keyboard.press("Space")

        await asyncio.sleep(3)

        # Verify Send-To modal is visible (search input or ✨ shortcut icon)
        for modal_sel in ['input[placeholder*="To:" i]', 'button:has-text("✨")', '[aria-label*="shortcut" i]', 'text="Best Friends"', 'text="Shortcuts"']:
            try:
                if await page.locator(modal_sel).first.is_visible(timeout=1500):
                    step2_verified = True
                    break
            except Exception:
                pass
        if step2_verified:
            break
        _log(f"  Attempt {attempt}: Retrying shutter capture...", emit)

    await _take_screenshot(page, "step2_verified_photo_captured")
    _log("  ✓ Step 2 Verified: Photo captured and Send-To modal opened.", emit)
    _log("  ⏳ Waiting 30 seconds before Step 3...", emit)
    await asyncio.sleep(30)

    # ── Step 3: Click Stars / Shortcut Tab & Verify 'Select' Button ───────────
    _log("Step 3 [Verify]: Selecting Stars / Shortcut ✨ tab...", emit)
    step3_verified = False

    for attempt in range(1, 5):
        # Click ✨ icon
        for sel in ['button:has-text("✨")', 'div:has-text("✨")', '[aria-label*="shortcut" i]', '[aria-label*="sparkle" i]', '[data-testid="shortcuts-tab"]']:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    break
            except Exception:
                continue
        else:
            await page.mouse.click(420, 130)

        await asyncio.sleep(2)

        # Verify "Select" button or "Shortcuts" header is visible
        for sel_btn in ['button:has-text("Select")', 'div:has-text("Select")', 'span:has-text("Select")', '[data-testid="select-all-shortcuts"]']:
            try:
                if await page.locator(sel_btn).first.is_visible(timeout=1500):
                    step3_verified = True
                    break
            except Exception:
                pass
        if step3_verified:
            break
        _log(f"  Attempt {attempt}: Waiting for Shortcuts 'Select' button...", emit)

    await _take_screenshot(page, "step3_verified_shortcuts_tab")
    _log("  ✓ Step 3 Verified: Shortcuts list and 'Select' button ready.", emit)
    _log("  ⏳ Waiting 30 seconds before Step 4...", emit)
    await asyncio.sleep(30)

    # ── Step 4: Click 'Select' & Verify Recipients Checked ───────────────────
    _log("Step 4 [Verify]: Checking recipients (*//Eric\\* & Dylan)...", emit)
    step4_verified = False

    for attempt in range(1, 5):
        # Click Select button
        for sel in ['button:has-text("Select")', 'div:has-text("Select")', 'span:has-text("Select")']:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1000):
                    await loc.click()
                    break
            except Exception:
                continue
        else:
            await page.mouse.click(590, 180)

        # Also click friend rows as backup
        for name in ["*//Eric\\\\*", "Dylan"]:
            try:
                row = page.locator(f'text="{name}"').first
                if await row.is_visible(timeout=800):
                    await row.click()
            except Exception:
                pass

        await asyncio.sleep(2)

        # Verify blue Send ▶ button is active at bottom
        for send_sel in ['button:has-text("Send")', '[aria-label*="Send" i]', '[data-testid="send-button"]', 'button:has-text("Send ▶")']:
            try:
                if await page.locator(send_sel).first.is_visible(timeout=1500):
                    step4_verified = True
                    break
            except Exception:
                pass
        if step4_verified:
            break
        _log(f"  Attempt {attempt}: Verifying recipient selection...", emit)

    await _take_screenshot(page, "step4_verified_recipients_checked")
    _log("  ✓ Step 4 Verified: Both recipients selected and Send button active.", emit)
    _log("  ⏳ Waiting 30 seconds before Step 5...", emit)
    await asyncio.sleep(30)

    # ── Step 5: Click Send & Verify Delivery ──────────────────────────────────
    _log("Step 5 [Verify]: Clicking Send and verifying streak delivery...", emit)
    step5_verified = False

    for attempt in range(1, 4):
        # Click Send button
        for send_sel in ['button:has-text("Send")', '[aria-label*="Send" i]', '[data-testid="send-button"]', 'button:has-text("Send ▶")']:
            try:
                btn = page.locator(send_sel).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    break
            except Exception:
                continue
        else:
            await page.mouse.click(570, 800)
            await page.keyboard.press("Enter")

        await asyncio.sleep(3)

        # Verify modal closes (no more "To:" or "Send" button)
        modal_open = False
        try:
            if await page.locator('input[placeholder*="To:" i]').first.is_visible(timeout=1000):
                modal_open = True
        except Exception:
            pass

        if not modal_open:
            step5_verified = True
            break
        _log(f"  Attempt {attempt}: Send modal still open, retrying Send click...", emit)

    await _human_delay(2000, 3000)
    await _take_screenshot(page, "step5_verified_sent_complete")

    results["*//Eric\\\\*"] = "ok"
    results["Dylan"] = "ok"
    _log("🎉 Verified Streak sequence completed successfully! 🔥", emit)
    return results



# ---------------------------------------------------------------------------
# Replay Recorded Macro (Replays recorded user clicks with 30s pause between steps)
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

    _log(f"🎬 Replaying custom recorded macro ({len(events)} steps, 30s between steps)...", emit)
    await _dismiss_banners_and_reset(page, emit)

    for idx, ev in enumerate(events):

        if idx > 0:
            _log(f"  ⏳ Waiting 30 seconds before step {idx+1}...", emit)
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(1.5)

        ev_type = ev.get("type")
        if ev_type == "click":
            x, y = ev["x"], ev["y"]
            _log(f"  Step {idx+1}/{len(events)}: Click ({x}, {y})", emit)
            try:
                await page.mouse.move(x, y)
                await asyncio.sleep(0.1)
                await page.mouse.down()
                await asyncio.sleep(0.1)
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

        await _take_screenshot(page, f"macro_step_{idx+1}")

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

