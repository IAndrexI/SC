"""
automation.py – Core Snapchat Web Automation Engine for SnapStreak.
Supports:
  1. Live SJSU Meteorology Webcam pipeline (HTTP fetch + Y4M generator + zero-CORS Data URL page injection)
  2. Cookie & Session Vault persistence (never wipes cookies; bidirectional sync between browser_profile & session.json)
  3. Mode A: AI / Expected Steps 6-Stage State Machine (Prepare -> Camera -> Capture -> Send To -> Select & Audit -> Send)
  4. Mode B: Smart Macro Recorder & Replayer (DOM selector + relative coordinate hybrid replay with safety guard)
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import shutil
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

import config

logger = logging.getLogger("snapstreak")

DATA_DIR = config.DATA_DIR
SESSION_FILE = config.SESSION_FILE
SESSION_BACKUP_FILE = config.SESSION_BACKUP_FILE
SNAP_IMAGE = config.SNAP_IMAGE
WEBCAM_FILE = config.WEBCAM_FILE
Y4M_FILE = config.Y4M_FILE
MACRO_FILE = config.MACRO_FILE
USER_DATA_DIR = config.USER_DATA_DIR
FIREFOX_PROFILE_DIR = config.FIREFOX_PROFILE_DIR
WEBCAM_URL = config.WEBCAM_URL

LOG_FILE = DATA_DIR / "activity.log"
SCREENSHOT_FILE = DATA_DIR / "last_screenshot.png"
EXTENSION_DIR = Path(__file__).resolve().parent.parent / "extension"

SNAPCHAT_WEB = "https://web.snapchat.com/"
VIEWPORT = {"width": 1440, "height": 900}

FORBIDDEN_TARGETS = [
    "my ai",
    "my story",
    "our story",
    "spotlight",
    "snap map",
    "team snapchat",
    "public profile",
    "add to story",
    "post to story",
]

# Global execution control flags
_execution_state = {
    "running": False,
    "paused": False,
    "stop_requested": False,
    "current_mode": "ai_steps",
    "current_step": 0,
    "total_steps": 6,
    "step_name": "Idle",
    "screen_state": "UNKNOWN",
    "last_updated": 0.0,
}


def get_execution_state() -> dict:
    return dict(_execution_state)


def update_execution_state(**kwargs):
    _execution_state.update(kwargs)
    _execution_state["last_updated"] = time.time()


def request_stop():
    _execution_state["stop_requested"] = True
    _execution_state["paused"] = False


def toggle_pause() -> bool:
    _execution_state["paused"] = not _execution_state["paused"]
    return _execution_state["paused"]


async def _check_pause_or_stop(emit: Callable | None = None) -> bool:
    """Return True if stop was requested. Wait while paused."""
    if _execution_state.get("stop_requested"):
        log("WARN", "🛑 Stop requested by user. Aborting automation.", emit)
        return True
    while _execution_state.get("paused"):
        if _execution_state.get("stop_requested"):
            return True
        await asyncio.sleep(0.25)
    return False


def _cleanup_stale_locks():
    """Remove stale Chromium lock files if no browser is holding them."""
    for profile in (USER_DATA_DIR, config.EDGE_PROFILE_DIR):
        for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            p = profile / lock_name
            if p.exists() or p.is_symlink():
                try:
                    p.unlink()
                except Exception:
                    pass


def log(level: str, msg: str, emit: Callable | None = None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    logger.info(line)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if emit:
        try:
            emit(line)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. SJSU METEOROLOGY LIVE WEBCAM ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def generate_y4m_from_image(
    image_bytes: bytes,
    out_path: Path = Y4M_FILE,
    width: int = 1280,
    height: int = 720,
    fps: int = 15,
    frames: int = 30,
):
    """
    Convert JPEG/PNG image bytes into a valid YUV420p .y4m video file for Chromium
    --use-file-for-fake-video-capture. Includes a pure-Python fallback if Pillow is absent.
    """
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageOps

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS)
            ycbcr = img.convert("YCbCr")
            y, cb, cr = ycbcr.split()
            cb_sub = cb.resize((width // 2, height // 2), resample=Image.Resampling.BILINEAR)
            cr_sub = cr.resize((width // 2, height // 2), resample=Image.Resampling.BILINEAR)
            frame_data = y.tobytes() + cb_sub.tobytes() + cr_sub.tobytes()
        except ImportError:
            # Pure-Python fallback YUV420p frame (dark slate blue) if PIL not installed
            y_plane = bytes([45]) * (width * height)
            u_plane = bytes([140]) * ((width // 2) * (height // 2))
            v_plane = bytes([118]) * ((width // 2) * (height // 2))
            frame_data = y_plane + u_plane + v_plane

        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420jpeg\n".encode("ascii")
        frame_header = b"FRAME\n"
        tmp_path = out_path.with_suffix(".y4m.tmp")
        with open(tmp_path, "wb") as f:
            f.write(header)
            for _ in range(frames):
                f.write(frame_header)
                f.write(frame_data)
        tmp_path.replace(out_path)
    except Exception as ex:
        logger.debug(f"Y4M generation notice: {ex}")


def fetch_webcam_image(force_refresh: bool = False) -> bytes:
    """
    Fetch the latest live frame from the San Jose State University Meteorology webcam
    (https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg), update webcam_latest.jpg,
    snap.png (unless custom image is active), and webcam.y4m.
    """
    config.ensure_data_dirs()
    now = time.time()

    if (
        not force_refresh
        and WEBCAM_FILE.exists()
        and WEBCAM_FILE.stat().st_size > 1500
        and (now - WEBCAM_FILE.stat().st_mtime) < 180
    ):
        data = WEBCAM_FILE.read_bytes()
        if not Y4M_FILE.exists() or Y4M_FILE.stat().st_size < 10000:
            generate_y4m_from_image(data)
        return data

    try:
        sep = "&" if "?" in WEBCAM_URL else "?"
        live_url = f"{WEBCAM_URL}{sep}_t={int(now * 1000)}"
        req = urllib.request.Request(
            live_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Referer": "https://www.met.sjsu.edu/",
            },
        )
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
            data = resp.read()
            if data and len(data) > 1500:
                WEBCAM_FILE.write_bytes(data)
                cfg = config.load()
                if not cfg.get("snap_image_custom"):
                    SNAP_IMAGE.write_bytes(data)
                generate_y4m_from_image(data)
                return data
    except Exception as ex:
        logger.warning(f"SJSU webcam fetch fallback: {ex}")

    if WEBCAM_FILE.exists() and WEBCAM_FILE.stat().st_size > 1500:
        data = WEBCAM_FILE.read_bytes()
        if not Y4M_FILE.exists():
            generate_y4m_from_image(data)
        return data

    if SNAP_IMAGE.exists() and SNAP_IMAGE.stat().st_size > 1500:
        return SNAP_IMAGE.read_bytes()

    return b""


def get_webcam_data_url(force_refresh: bool = False) -> str:
    """
    Return the active camera image (SJSU live webcam or custom uploaded snap) as a
    CORS-immune base64 Data URL ('data:image/jpeg;base64,...').
    """
    cfg = config.load()
    if cfg.get("snap_image_custom") and SNAP_IMAGE.exists() and SNAP_IMAGE.stat().st_size > 500:
        raw = SNAP_IMAGE.read_bytes()
    else:
        raw = fetch_webcam_image(force_refresh=force_refresh)

    if not raw:
        return ""
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def inject_webcam_frame_into_page(page, force_refresh: bool = False) -> bool:
    """
    Push the live SJSU webcam Data URL directly into the browser page's global state
    so camera_hook.js renders the real SJSU camera image without any CORS issues.
    """
    if not page:
        return False
    try:
        loop = asyncio.get_running_loop()
        data_url = await loop.run_in_executor(None, get_webcam_data_url, force_refresh)
        if not data_url:
            return False
        await page.evaluate(
            """(dataUrl) => {
                window.__SNAPSTREAK_SJSU_DATA_URL__ = dataUrl;
                window.dispatchEvent(new CustomEvent('SNAPSTREAK_WEBCAM_FRAME', {
                    detail: { dataUrl: dataUrl, timestamp: Date.now() }
                }));
            }""",
            data_url,
        )
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. CLEAN STEALTH & VIRTUAL CAMERA INIT SCRIPT
# ─────────────────────────────────────────────────────────────────────────────

STEALTH_INIT_SCRIPT = """
(() => {
    try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    } catch(e) {}

    try {
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {};
    } catch(e) {}

    try {
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    } catch(e) {}

    try {
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        delete window.__playwright;
        delete window.__pw_manual;
    } catch(e) {}
})();
"""


def get_extension_bundle_script() -> str:
    """
    Bundle camera_hook.js + macro.js + automation.js + overlay.js + content.js
    for injection into Snapchat Web. Injects the initial SJSU webcam data URL
    and server config so the camera hook has the real SJSU image immediately on page load.
    """
    try:
        cfg = config.load()
        macro_data = config.load_macro_data()
        sjsu_data_url = get_webcam_data_url(force_refresh=False)

        server_boot = {
            "version": config.APP_VERSION,
            "versionInfo": config.get_version_info(False),
            "friends": cfg.get("friends", ["*//Eric\\\\*", "Dylan"]),
            "selectionMethod": cfg.get("selection_method", "direct"),
            "sendingEngine": "macro" if cfg.get("streak_mode") == "macro" else "direct",
            "streakMode": cfg.get("streak_mode", "ai_steps"),
            "shortcutName": cfg.get("shortcut_name", "Streaks"),
            "stepDelay": float(cfg.get("step_delay_seconds", 1.5)),
            "scheduleEnabled": bool(cfg.get("enabled", True)),
            "scheduleTime": cfg.get("schedule_time", "09:00"),
            "scheduleTimes": cfg.get("schedule_times", ["09:00"]),
            "activeMacro": macro_data.get("active_macro", "Default Streak Flow"),
            "macroSteps": macro_data.get("steps", []),
            "macros": macro_data.get("macros", {}),
        }

        css_path = EXTENSION_DIR / "overlay.css"
        css_text = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

        js_files = ["camera_hook.js", "macro.js", "automation.js", "overlay.js", "content.js"]
        js_parts = []
        for fn in js_files:
            p = EXTENSION_DIR / fn
            if p.exists():
                js_parts.append(f"\n// === {fn} ===\n" + p.read_text(encoding="utf-8"))

        if not js_parts:
            return ""

        combined_js = "\n".join(js_parts)
        return f"""
(() => {{
    if (window !== window.top) return;
    const host = (window.location && window.location.hostname) || '';
    if (host && !host.includes('snapchat.com') && !host.includes('localhost') && !host.includes('127.0.0.1')) return;

    window.__SNAPSTREAK_SERVER_CONFIG__ = {json.dumps(server_boot)};
    if ({json.dumps(bool(sjsu_data_url))}) {{
        window.__SNAPSTREAK_SJSU_DATA_URL__ = {json.dumps(sjsu_data_url)};
    }}
    if (window.__SNAPSTREAK_EXTENSION_INJECTED__) return;
    window.__SNAPSTREAK_EXTENSION_INJECTED__ = true;
    window.__SNAPSTREAK_OVERLAY_CSS__ = {json.dumps(css_text)};

    if (typeof window.chrome === 'undefined') window.chrome = {{}};
    if (!window.chrome.storage || !window.chrome.storage.local) {{
        const _prefix = 'snapstreak_ext_';
        window.chrome.storage = {{
            local: {{
                get: (keys, cb) => {{
                    const res = {{}};
                    const list = Array.isArray(keys) ? keys : (typeof keys === 'string' ? [keys] : Object.keys(keys || {{}}));
                    list.forEach(k => {{
                        try {{
                            const raw = localStorage.getItem(_prefix + k);
                            if (raw !== null) res[k] = JSON.parse(raw);
                            else if (typeof keys === 'object' && !Array.isArray(keys) && keys[k] !== undefined) res[k] = keys[k];
                        }} catch(e) {{}}
                    }});
                    if (cb) setTimeout(() => cb(res), 0);
                    return Promise.resolve(res);
                }},
                set: (items, cb) => {{
                    Object.keys(items || {{}}).forEach(k => {{
                        try {{ localStorage.setItem(_prefix + k, JSON.stringify(items[k])); }} catch(e) {{}}
                    }});
                    if (cb) setTimeout(() => cb(), 0);
                    return Promise.resolve();
                }}
            }}
        }};
    }}
    if (!window.chrome.runtime) window.chrome.runtime = {{}};
    if (!window.chrome.runtime.sendMessage) {{
        window.chrome.runtime.sendMessage = (msg, cb) => {{
            if (cb) setTimeout(() => cb({{ status: 'ok' }}), 0);
        }};
    }}
    if (!window.chrome.runtime.onMessage) {{
        window.chrome.runtime.onMessage = {{ addListener: () => {{}} }};
    }}

    {combined_js}
}})();
"""
    except Exception as ex:
        logger.warning(f"Failed to bundle extension scripts: {ex}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. COOKIE & SESSION VAULT PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

def is_snapchat_authenticated_url(url: str) -> bool:
    """Return True if URL is inside the Snapchat Web application (not login page)."""
    u = (url or "").lower()
    if "accounts.snapchat.com" in u or "/login" in u:
        return False
    return "web.snapchat.com" in u or "snapchat.com/web" in u


async def load_cookies_into_context(context, emit: Callable | None = None) -> int:
    """
    Load saved cookies from session.json (or session_backup.json) into the Playwright context
    without overwriting newer cookies already in the persistent profile.
    """
    config.ensure_data_dirs()
    source_file = SESSION_FILE if SESSION_FILE.exists() else (SESSION_BACKUP_FILE if SESSION_BACKUP_FILE.exists() else None)
    if not source_file:
        return 0

    try:
        data = json.loads(source_file.read_text(encoding="utf-8"))
        cookies = data.get("cookies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not cookies:
            return 0
        valid_cookies = []
        for c in cookies:
            if not isinstance(c, dict) or not c.get("name") or c.get("value") is None:
                continue
            item = {
                "name": str(c["name"]),
                "value": str(c["value"]),
                "domain": str(c.get("domain", ".snapchat.com")),
                "path": str(c.get("path", "/")),
            }
            if c.get("expires") and float(c["expires"]) > 0:
                item["expires"] = float(c["expires"])
            if "httpOnly" in c:
                item["httpOnly"] = bool(c["httpOnly"])
            if "secure" in c:
                item["secure"] = bool(c["secure"])
            if c.get("sameSite") in ("Strict", "Lax", "None"):
                item["sameSite"] = c["sameSite"]
            valid_cookies.append(item)

        if valid_cookies:
            await context.add_cookies(valid_cookies)
            return len(valid_cookies)
    except Exception as ex:
        logger.debug(f"Cookie load notice: {ex}")
    return 0


async def save_cookies_from_context(context, emit: Callable | None = None) -> dict:
    """
    Export cookies + localStorage from the active Playwright context to session.json
    and session_backup.json WITHOUT closing the browser!
    Safeguard: never overwrite an authenticated session.json with an unauthenticated empty state.
    """
    if not context:
        return {"ok": False, "message": "No active browser context"}

    try:
        config.ensure_data_dirs()
        state = await context.storage_state()
        cookies = state.get("cookies", [])
        sc_cookies = [c for c in cookies if "snapchat" in str(c.get("domain", "")).lower()]
        auth_names = {
            "sc_at",
            "__Host-sc-a-auth-session",
            "__Host-X-Snap-Client-Cookie",
            "sc-a-nonce",
            "__Host-sc-a-nonce",
            "sc-a-csrf",
        }
        has_auth_now = any(c.get("name") in auth_names for c in sc_cookies)

        # Check if existing session.json already has auth cookies and current state has none
        if not has_auth_now and SESSION_FILE.exists():
            try:
                old_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                old_cookies = old_state.get("cookies", []) if isinstance(old_state, dict) else []
                had_auth_before = any(c.get("name") in auth_names for c in old_cookies)
                if had_auth_before and len(sc_cookies) < 5:
                    # Merge old auth cookies into current context instead of wiping them!
                    await context.add_cookies(old_cookies)
                    state = await context.storage_state()
                    cookies = state.get("cookies", [])
                    sc_cookies = [c for c in cookies if "snapchat" in str(c.get("domain", "")).lower()]
                    has_auth_now = any(c.get("name") in auth_names for c in sc_cookies)
            except Exception:
                pass

        SESSION_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        if has_auth_now or not SESSION_BACKUP_FILE.exists():
            SESSION_BACKUP_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

        return {
            "ok": True,
            "total_cookies": len(cookies),
            "snapchat_cookies": len(sc_cookies),
            "has_auth": has_auth_now,
            "message": f"Saved {len(cookies)} cookies ({len(sc_cookies)} Snapchat cookies) to session vault.",
        }
    except Exception as ex:
        return {"ok": False, "message": f"Cookie save error: {ex}"}


# ─────────────────────────────────────────────────────────────────────────────
# 4. SNAPCHAT WEB SCREEN STATE DETECTION & DOM HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def dismiss_snapchat_blockers(page, emit: Callable | None = None) -> list[str]:
    """
    Safely dismiss ONLY known blocking modals on Snapchat Web:
      - 'Snapchat is already open in another tab' -> clicks 'Use Here'
      - Browser notification prompt -> clicks 'Not now'
      - Cookie banner -> clicks 'Accept All' ONLY inside cookie banner
    Never clicks generic 'Continue' or 'Allow' buttons indiscriminately.
    """
    if not page:
        return []
    try:
        clicked = await page.evaluate(
            """() => {
                const actions = [];
                const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
                for (const b of buttons) {
                    if (b.closest('#snapstreak-hud-host, #snapstreak-shadow-host')) continue;
                    const rect = b.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    const text = (b.innerText || b.textContent || '').trim().toLowerCase();
                    if (text === 'use here') {
                        b.click();
                        actions.push('Clicked "Use Here" (multi-tab takeover)');
                    } else if (text === 'not now') {
                        b.click();
                        actions.push('Clicked "Not now" (notification prompt)');
                    }
                }
                return actions;
            }"""
        )
        for act in (clicked or []):
            log("INFO", f"  🛡️ {act}", emit)
        return clicked or []
    except Exception:
        return []


async def detect_screen_state(page) -> dict:
    """
    Inspect the live Snapchat Web DOM and classify the current screen state into one of:
      - LOGIN_REQUIRED
      - BLOCKED_MODAL
      - SEND_TO_DRAWER
      - PHOTO_CAPTURED
      - CLICK_CAMERA_PROMPT
      - CAMERA_READY
      - CHAT_OPEN
      - HOME_NO_CAMERA
      - LOADING
    Also returns coordinates for key interactive targets on the current screen.
    """
    if not page:
        return {"state": "OFFLINE", "url": ""}

    try:
        url = page.url or ""
        info = await page.evaluate(
            """() => {
                const vw = window.innerWidth || 1440;
                const vh = window.innerHeight || 900;
                const isVisible = (el) => {
                    if (!el || el.closest('#snapstreak-hud-host, #snapstreak-shadow-host, #snapstreak-virtual-cursor')) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width < 4 || r.height < 4) return false;
                    const st = window.getComputedStyle(el);
                    return st.display !== 'none' && st.visibility !== 'hidden' && parseFloat(st.opacity || '1') > 0.05;
                };
                const centerOf = (el) => {
                    const r = el.getBoundingClientRect();
                    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) };
                };

                const allBtns = Array.from(document.querySelectorAll('button, div[role="button"], [role="button"]')).filter(isVisible);

                // 1. Check for 'Use Here' blocker
                const useHereBtn = allBtns.find(b => (b.innerText || b.textContent || '').trim().toLowerCase() === 'use here');
                if (useHereBtn) {
                    return { state: 'BLOCKED_MODAL', blocker: 'use_here', coords: centerOf(useHereBtn) };
                }

                // 2. Check for Login form
                const loginInput = document.querySelector('input[name="accountIdentifier"], input[autocomplete="username"], input[type="password"]');
                if (loginInput && isVisible(loginInput)) {
                    return { state: 'LOGIN_REQUIRED' };
                }

                // 3. Check for Send-To Drawer (search input inside drawer or recipient list with checkboxes)
                const searchInputs = Array.from(document.querySelectorAll('input[placeholder*="Search" i], input[aria-label*="Search" i]')).filter(isVisible);
                const drawerSearch = searchInputs.find(inp => inp.getBoundingClientRect().left > 340);

                // Look for final 'Send' button at bottom of Send-To drawer (blue pill or submit button at y > vh * 0.72, x > 350)
                let finalSendBtn = null;
                let sendToBtn = null;
                let downloadBtn = null;

                for (const b of allBtns) {
                    const r = b.getBoundingClientRect();
                    if (r.left < 340) continue; // ignore left conversation sidebar
                    const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || b.getAttribute('title') || '').trim().toLowerCase();

                    if (txt === 'send to' || aria === 'send to' || txt.startsWith('send to')) {
                        sendToBtn = b;
                    } else if (txt === 'download' || aria === 'download') {
                        downloadBtn = b;
                    } else if (
                        r.top > vh * 0.72 &&
                        (txt === 'send' || aria === 'send' || aria === 'send snap' || txt === 'send snap')
                    ) {
                        finalSendBtn = b;
                    }
                }

                // Check selected pills/checkboxes in drawer
                const checkedEls = Array.from(document.querySelectorAll('[aria-checked="true"], input[type="checkbox"]:checked')).filter(el => {
                    if (!isVisible(el)) return false;
                    return el.getBoundingClientRect().left > 340;
                });

                if (drawerSearch || finalSendBtn || checkedEls.length > 0) {
                    // Also check if Send-To header or 'Send To...' text is visible in center panel
                    const hasSendToHeader = Array.from(document.querySelectorAll('div, span, h1, h2, h3')).some(el => {
                        if (!isVisible(el)) return false;
                        const r = el.getBoundingClientRect();
                        if (r.left < 340 || r.top > 300) return false;
                        const t = (el.innerText || '').trim().toLowerCase();
                        return t === 'send to' || t === 'send to...' || t === 'shortcuts' || t === 'recents' || t === 'best friends';
                    });
                    if (drawerSearch || hasSendToHeader || checkedEls.length > 0 || (finalSendBtn && !sendToBtn)) {
                        return {
                            state: 'SEND_TO_DRAWER',
                            selected_count: checkedEls.length,
                            search_coords: drawerSearch ? centerOf(drawerSearch) : null,
                            final_send_coords: finalSendBtn ? centerOf(finalSendBtn) : null,
                        };
                    }
                }

                // 4. Check for Photo Captured preview ('Send To' button + 'Download' button visible)
                if (sendToBtn || (downloadBtn && !drawerSearch)) {
                    return {
                        state: 'PHOTO_CAPTURED',
                        send_to_coords: sendToBtn ? centerOf(sendToBtn) : { x: 556, y: 877 },
                        download_coords: downloadBtn ? centerOf(downloadBtn) : null,
                    };
                }

                // 4b. Starter Step: Check for "Click the Camera to send Snaps" prompt card
                const clickCameraTextEl = Array.from(document.querySelectorAll('h1, h2, h3, div, span, p')).find(el => {
                    if (!isVisible(el)) return false;
                    const r = el.getBoundingClientRect();
                    if (r.left < 300) return false;
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return t.includes('click the camera') || (t.includes('send snaps') && t.includes('camera'));
                });

                if (clickCameraTextEl) {
                    const tr = clickCameraTextEl.getBoundingClientRect();
                    const cx = Math.round(tr.left + tr.width / 2);
                    let circleBtn = null;
                    const parentCard = clickCameraTextEl.closest('div[class*="card" i], div[class*="container" i], div') || clickCameraTextEl.parentElement;
                    if (parentCard) {
                        const btns = parentCard.querySelectorAll('button, div[role="button"], svg');
                        for (const b of btns) {
                            if (isVisible(b)) { circleBtn = b; break; }
                        }
                    }
                    const camCoords = circleBtn ? centerOf(circleBtn) : { x: cx, y: Math.max(120, Math.round(tr.top - 90)), w: 80, h: 80 };
                    return {
                        state: 'CLICK_CAMERA_PROMPT',
                        camera_open_coords: camCoords,
                        prompt_text: (clickCameraTextEl.innerText || clickCameraTextEl.textContent || '').trim(),
                    };
                }

                // 5. Check for Camera Viewfinder Ready (video element or shutter button in center panel)
                const videos = Array.from(document.querySelectorAll('video')).filter(v => {
                    if (!isVisible(v)) return false;
                    const r = v.getBoundingClientRect();
                    return r.left > 300 && r.width > 180 && r.height > 200;
                });

                // Look for the shutter button:
                // Either tooltip 'Click to take a picture, hold for video' is present,
                // or a large circular button (width 52..105, abs(w-h) <= 12) near bottom-center of the camera card
                let shutterBtn = null;
                const tooltipEl = Array.from(document.querySelectorAll('div, span')).find(el => {
                    if (!isVisible(el)) return false;
                    const t = (el.innerText || '').trim().toLowerCase();
                    return t.includes('click to take a picture');
                });

                const cameraRect = videos.length > 0 ? videos[0].getBoundingClientRect() : { left: 480, right: 960, top: 100, bottom: 880, width: 480, height: 780 };
                const camCenterX = (cameraRect.left + cameraRect.right) / 2;

                const shutterCandidates = [];
                for (const b of allBtns) {
                    const r = b.getBoundingClientRect();
                    if (r.left < 350) continue;
                    const aria = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '')).toLowerCase();
                    const txt = (b.innerText || '').trim().toLowerCase();

                    // Exclude filter lenses and menu buttons
                    if (aria.includes('lens') || aria.includes('filter') || aria.includes('close') || aria.includes('more') || txt === '✕') {
                        continue;
                    }

                    if (aria.includes('take a picture') || aria.includes('capture') || aria.includes('shutter') || aria.includes('take snap')) {
                        shutterCandidates.push({ el: b, score: 1000, pos: centerOf(b) });
                        continue;
                    }

                    // Geometric match: circular button near horizontal center of camera card, in bottom half
                    const isRoundish = r.width >= 48 && r.width <= 110 && r.height >= 48 && r.height <= 110 && Math.abs(r.width - r.height) <= 14;
                    const cx = r.left + r.width / 2;
                    const cy = r.top + r.height / 2;
                    const distFromCamCenter = Math.abs(cx - camCenterX);

                    if (isRoundish && cy > vh * 0.60 && cy < vh * 0.96 && distFromCamCenter < 95) {
                        const score = 500 - distFromCamCenter;
                        shutterCandidates.push({ el: b, score, pos: centerOf(b) });
                    }
                }

                shutterCandidates.sort((a, b) => b.score - a.score);
                if (shutterCandidates.length > 0) {
                    shutterBtn = shutterCandidates[0].pos;
                } else if (tooltipEl) {
                    const tr = tooltipEl.getBoundingClientRect();
                    shutterBtn = { x: Math.round(tr.left + tr.width / 2), y: Math.round(tr.bottom + 42), w: 68, h: 68 };
                } else if (videos.length > 0) {
                    shutterBtn = { x: Math.round(camCenterX), y: Math.round(cameraRect.bottom - 65), w: 68, h: 68 };
                }

                if (videos.length > 0 || shutterBtn) {
                    return {
                        state: 'CAMERA_READY',
                        shutter_coords: shutterBtn || { x: Math.round(camCenterX), y: 797 },
                        video_active: videos.length > 0,
                    };
                }

                // 6. Check if a Chat conversation is open (chat message input visible in center panel)
                const chatInput = Array.from(document.querySelectorAll('input[placeholder*="Send a chat" i], textarea[placeholder*="Send a chat" i], [contenteditable="true"]')).find(el => {
                    if (!isVisible(el)) return false;
                    return el.getBoundingClientRect().left > 340;
                });
                if (chatInput) {
                    return { state: 'CHAT_OPEN' };
                }

                // 7. Check if left conversation sidebar is visible (HOME_NO_CAMERA)
                const hasConvoList = document.querySelectorAll('[role="listitem"], [aria-label*="Chat" i], input[placeholder*="Search" i]').length > 0;
                if (hasConvoList) {
                    // Find center camera activator button if present
                    let camOpenCoords = { x: Math.round(vw * 0.52), y: Math.round(vh * 0.52) };
                    for (const b of allBtns) {
                        const r = b.getBoundingClientRect();
                        if (r.left > 350 && r.left < vw * 0.75 && r.top > vh * 0.3 && r.top < vh * 0.85) {
                            camOpenCoords = centerOf(b);
                            break;
                        }
                    }
                    return { state: 'HOME_NO_CAMERA', camera_open_coords: camOpenCoords };
                }

                return { state: 'LOADING' };
            }"""
        )
        if "accounts.snapchat.com" in url.lower() or "/login" in url.lower():
            info["state"] = "LOGIN_REQUIRED"
        info["url"] = url
        _execution_state["screen_state"] = info.get("state", "UNKNOWN")
        return info
    except Exception as ex:
        return {"state": "UNKNOWN", "url": getattr(page, "url", ""), "error": str(ex)}


async def inspect_element_at_point(page, x: int, y: int) -> dict:
    """
    Inspect the DOM element at viewport coordinates (x, y) for Smart Macro Recording.
    Returns human-readable label, CSS selector, text, aria-label, and relative coordinates.
    """
    vw, vh = VIEWPORT["width"], VIEWPORT["height"]
    fallback = {
        "x": x,
        "y": y,
        "rx": round(x / vw, 4),
        "ry": round(y / vh, 4),
        "label": f"Click at ({x}, {y})",
        "selector": "",
        "text": "",
        "ariaLabel": "",
        "tagName": "div",
    }
    if not page:
        return fallback

    try:
        meta = await page.evaluate(
            """({x, y}) => {
                const vw = window.innerWidth || 1440;
                const vh = window.innerHeight || 900;
                const el = document.elementFromPoint(x, y);
                if (!el) return null;
                const target = el.closest('button, a, [role="button"], [role="listitem"], [role="checkbox"], input') || el;
                const tag = (target.tagName || 'div').toLowerCase();
                const text = (target.innerText || target.textContent || '').trim().split('\\n')[0].slice(0, 50);
                const aria = (target.getAttribute('aria-label') || target.getAttribute('title') || target.getAttribute('placeholder') || '').trim();
                let selector = '';
                if (target.id) {
                    selector = '#' + CSS.escape(target.id);
                } else if (aria) {
                    selector = `${tag}[aria-label=${JSON.stringify(aria)}]`;
                } else if (target.getAttribute('data-testid')) {
                    selector = `[data-testid=${JSON.stringify(target.getAttribute('data-testid'))}]`;
                }
                let label = aria || text || `${tag.toUpperCase()} at (${x}, ${y})`;
                if (label.length > 48) label = label.slice(0, 48) + '…';
                return {
                    x,
                    y,
                    rx: Number((x / vw).toFixed(4)),
                    ry: Number((y / vh).toFixed(4)),
                    label: `Click "${label}"`,
                    selector,
                    text,
                    ariaLabel: aria,
                    tagName: tag
                };
            }""",
            {"x": x, "y": y},
        )
        return meta or fallback
    except Exception:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# 5. STEP-BY-STEP ACTIONS & MANDATORY SAFETY AUDIT
# ─────────────────────────────────────────────────────────────────────────────

async def audit_and_sanitize_drawer_selections(page, allowed_friends: list[str], emit: Callable | None = None) -> dict:
    """
    Scan the open Send-To drawer for any checked recipients.
    Forcibly uncheck any forbidden target (My AI, My Story, Spotlight, Team Snapchat, etc.).
    Returns {'valid_selected': [...], 'unselected_forbidden': [...]}.
    """
    if not page:
        return {"valid_selected": [], "unselected_forbidden": []}

    try:
        result = await page.evaluate(
            """({allowedFriends, forbiddenList}) => {
                const isVisible = (el) => {
                    if (!el || el.closest('#snapstreak-hud-host')) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 4 && r.height > 4;
                };
                const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                const allowedNorms = (allowedFriends || []).map(norm).filter(Boolean);

                const validSelected = [];
                const unselectedForbidden = [];

                // Find all rows in the Send-To drawer (x > 340) that appear selected/checked
                const rows = Array.from(document.querySelectorAll('li, [role="listitem"], [role="option"], [role="row"]')).filter(r => {
                    if (!isVisible(r)) return false;
                    const box = r.getBoundingClientRect();
                    return box.left > 340 && box.height >= 28 && box.height <= 110;
                });

                for (const row of rows) {
                    const text = (row.innerText || row.textContent || '').trim().split('\\n')[0].trim();
                    const lower = text.toLowerCase();
                    const hasChecked = !!(
                        row.querySelector('[aria-checked="true"], input[type="checkbox"]:checked') ||
                        row.getAttribute('aria-checked') === 'true' ||
                        row.getAttribute('aria-selected') === 'true'
                    );

                    // Also detect blue/filled SVG checkmark inside row right side
                    let svgChecked = false;
                    const svgs = row.querySelectorAll('svg');
                    for (const svg of svgs) {
                        const sr = svg.getBoundingClientRect();
                        if (sr.left > row.getBoundingClientRect().left + 120) {
                            const style = window.getComputedStyle(svg);
                            const fill = (svg.getAttribute('fill') || style.fill || '').toLowerCase();
                            const color = (style.color || '').toLowerCase();
                            if (fill.includes('11, 173, 255') || fill.includes('0badff') || color.includes('11, 173, 255')) {
                                svgChecked = true;
                            }
                        }
                    }

                    if (!hasChecked && !svgChecked) continue;

                    const isForbidden = forbiddenList.some(f => lower.includes(f));
                    if (isForbidden) {
                        row.click();
                        unselectedForbidden.push(text || 'Forbidden Target');
                    } else {
                        validSelected.push(text || 'Recipient');
                    }
                }

                return { valid_selected: validSelected, unselected_forbidden: unselectedForbidden };
            }""",
            {"allowedFriends": allowed_friends, "forbiddenList": FORBIDDEN_TARGETS},
        )
        for bad in result.get("unselected_forbidden", []):
            log("WARN", f"  🛡️ Safety Guard: Unchecked forbidden recipient '{bad}'!", emit)
        return result
    except Exception as ex:
        logger.debug(f"Safety audit notice: {ex}")
        return {"valid_selected": [], "unselected_forbidden": []}


async def select_friends_in_drawer(
    page,
    friends: list[str],
    selection_method: str = "direct",
    shortcut_name: str = "Streaks",
    emit: Callable | None = None,
) -> list[str]:
    """
    Select target recipients inside the open Send-To drawer using:
      - 'direct': Search/scan each friend in `friends` list and click their row in the drawer
      - 'shortcut': Click the user's custom Shortcut pill (excluding 'Groups') + 'Select All'
      - 'auto': Try direct friend matching first, plus shortcut if configured
    """
    selected: list[str] = []

    if selection_method in ("shortcut", "auto"):
        try:
            shortcut_res = await page.evaluate(
                """({shortcutName, forbiddenList}) => {
                    const isVisible = (el) => {
                        if (!el || el.closest('#snapstreak-hud-host')) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 8 && r.height > 8;
                    };
                    const targetLower = (shortcutName || 'streaks').trim().toLowerCase();
                    const ignoredPills = ['all', 'recents', 'groups', 'best friends', 'contacts', 'following', 'friends'];

                    const pills = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]')).filter(el => {
                        if (!isVisible(el)) return false;
                        const r = el.getBoundingClientRect();
                        return r.left > 340 && r.top >= 80 && r.top <= 340 && r.height <= 52;
                    });

                    let matchedPill = null;
                    for (const p of pills) {
                        const txt = (p.innerText || p.textContent || '').trim();
                        const lower = txt.toLowerCase();
                        if (!txt || forbiddenList.some(f => lower.includes(f))) continue;
                        if (lower === targetLower || lower.includes(targetLower) || /\\p{Emoji_Presentation}/u.test(txt)) {
                            if (!ignoredPills.includes(lower)) {
                                matchedPill = p;
                                break;
                            }
                        }
                    }

                    if (!matchedPill) return { clicked_shortcut: false };
                    matchedPill.click();
                    return { clicked_shortcut: true, pill_text: (matchedPill.innerText || '').trim() };
                }""",
                {"shortcutName": shortcut_name, "forbiddenList": FORBIDDEN_TARGETS},
            )
            if shortcut_res and shortcut_res.get("clicked_shortcut"):
                log("INFO", f"  ✨ Clicked Shortcut pill '{shortcut_res.get('pill_text')}'", emit)
                await asyncio.sleep(0.6)
                sel_all = await page.evaluate(
                    """() => {
                        const btns = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                        for (const b of btns) {
                            if (b.closest('#snapstreak-hud-host')) continue;
                            const r = b.getBoundingClientRect();
                            if (r.left < 340 || r.width <= 0) continue;
                            const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                            if (t === 'select all') {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }"""
                )
                if sel_all:
                    log("INFO", "  ✓ Clicked 'Select All' inside shortcut.", emit)
                    await asyncio.sleep(0.5)
                    audit = await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
                    if audit.get("valid_selected"):
                        return audit["valid_selected"]
        except Exception as ex:
            logger.debug(f"Shortcut selection notice: {ex}")

    # Direct selection: for each friend in `friends`, click their row directly if visible in the drawer,
    # or type their name into the drawer's Search input and click the matching row.
    for friend in friends:
        if await _check_pause_or_stop(emit):
            break
        friend_clean = friend.strip()
        if not friend_clean:
            continue
        if any(f in friend_clean.lower() for f in FORBIDDEN_TARGETS):
            log("WARN", f"  🛡️ Skipping forbidden target '{friend_clean}'", emit)
            continue

        # 1. Try clicking row directly in the visible Send-To list without searching first
        direct_hit = await page.evaluate(
            """(targetName) => {
                const isVisible = (el) => {
                    if (!el || el.closest('#snapstreak-hud-host')) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 20 && r.height >= 24 && r.height <= 110 && r.left > 340;
                };
                const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                const tLower = targetName.toLowerCase();
                const tNorm = norm(targetName);

                const rows = Array.from(document.querySelectorAll('li, [role="listitem"], [role="option"], [role="row"], div')).filter(el => {
                    if (!isVisible(el)) return false;
                    const r = el.getBoundingClientRect();
                    // Must look like a single recipient row inside the center drawer
                    return r.width >= 180 && r.width <= 620 && r.height >= 36 && r.height <= 88 && r.top > 150 && r.top < 820;
                });

                for (const row of rows) {
                    const lines = (row.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                    if (!lines.length) continue;
                    const primary = lines[0];
                    const pLower = primary.toLowerCase();
                    const pNorm = norm(primary);
                    if (pLower === tLower || (tNorm.length >= 3 && pNorm === tNorm)) {
                        const r = row.getBoundingClientRect();
                        return { found: true, name: primary, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                    }
                }
                return { found: false };
            }""",
            friend_clean,
        )

        if direct_hit and direct_hit.get("found"):
            await page.mouse.click(direct_hit["x"], direct_hit["y"])
            selected.append(direct_hit.get("name") or friend_clean)
            log("INFO", f"  ✓ Selected '{friend_clean}' directly in Send-To drawer.", emit)
            await asyncio.sleep(0.4)
            continue

        # 2. Fallback: Use the drawer Search box
        search_box = await page.evaluate(
            """() => {
                const inputs = Array.from(document.querySelectorAll('input[placeholder*="Search" i], input[aria-label*="Search" i], input[type="search"], input[type="text"]'));
                for (const inp of inputs) {
                    if (inp.closest('#snapstreak-hud-host')) continue;
                    const r = inp.getBoundingClientRect();
                    if (r.left > 340 && r.width > 60 && r.height > 15) {
                        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                    }
                }
                return null;
            }"""
        )

        if search_box:
            # Strip punctuation like *//Eric\\* -> Eric for search query if special chars exist
            alnum_query = re.sub(r"[^a-zA-Z0-9_.-]+", "", friend_clean) or friend_clean
            await page.mouse.click(search_box["x"], search_box["y"])
            await asyncio.sleep(0.15)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(alnum_query, delay=35)
            await asyncio.sleep(0.65)

            search_hit = await page.evaluate(
                """({targetName, query}) => {
                    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                    const tLower = targetName.toLowerCase();
                    const tNorm = norm(targetName);
                    const qNorm = norm(query);

                    const rows = Array.from(document.querySelectorAll('li, [role="listitem"], [role="option"], [role="row"], div')).filter(el => {
                        if (!el || el.closest('#snapstreak-hud-host')) return false;
                        const r = el.getBoundingClientRect();
                        return r.left > 340 && r.width >= 180 && r.width <= 620 && r.height >= 36 && r.height <= 88 && r.top > 180 && r.top < 800;
                    });

                    for (const row of rows) {
                        const lines = (row.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                        if (!lines.length) continue;
                        const primary = lines[0];
                        const pLower = primary.toLowerCase();
                        const pNorm = norm(primary);
                        if (pLower.includes('my ai') || pLower.includes('my story') || pLower.includes('spotlight')) continue;
                        if (pLower === tLower || pNorm === tNorm || (qNorm.length >= 3 && pNorm.includes(qNorm))) {
                            const r = row.getBoundingClientRect();
                            return { found: true, name: primary, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                        }
                    }
                    return { found: false };
                }""",
                {"targetName": friend_clean, "query": alnum_query},
            )

            if search_hit and search_hit.get("found"):
                await page.mouse.click(search_hit["x"], search_hit["y"])
                selected.append(search_hit.get("name") or friend_clean)
                log("INFO", f"  ✓ Found & selected '{friend_clean}' via drawer search.", emit)
                await asyncio.sleep(0.35)
            else:
                log("WARN", f"  ⚠ Could not find recipient '{friend_clean}' in Send-To drawer.", emit)

            # Clear search input
            await page.mouse.click(search_box["x"], search_box["y"])
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.25)

    await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
    return selected


# ─────────────────────────────────────────────────────────────────────────────
# 6. STEP VERIFICATION HELPERS & MODE A: AI / EXPECTED STEPS 6-STAGE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def is_strict_friend_match(candidate: str, target_friend: str) -> bool:
    """Return True if candidate display name matches target_friend (exact or normalized alphanumeric)."""
    c = (candidate or "").strip().lower()
    t = (target_friend or "").replace("\\\\", "\\").strip().lower()
    if not c or not t:
        return False
    if c == t or t in c or c in t:
        return True
    c_norm = re.sub(r"[^a-z0-9]", "", c)
    t_norm = re.sub(r"[^a-z0-9]", "", t)
    return bool(c_norm and t_norm and (c_norm == t_norm or t_norm in c_norm))


async def wait_for_screen_states(
    page,
    target_states: tuple[str, ...] | list[str],
    timeout_s: float = 3.0,
    poll_s: float = 0.35,
) -> dict:
    """Poll detect_screen_state(page) until state matches one of target_states or timeout expires."""
    deadline = time.time() + max(0.3, timeout_s)
    last_info = {"state": "UNKNOWN"}
    while time.time() < deadline:
        last_info = await detect_screen_state(page)
        if last_info.get("state") in target_states:
            return {"matched": True, "state_info": last_info}
        await asyncio.sleep(poll_s)
    last_info = await detect_screen_state(page)
    return {"matched": last_info.get("state") in target_states, "state_info": last_info}


async def _click_starter_camera_on_page(page, state_info: dict | None = None):
    """Click the Starter Camera opener button ('Click the Camera to send Snaps') via both DOM & mouse."""
    state_info = state_info or await detect_screen_state(page)
    cam_coords = state_info.get("camera_open_coords") or {"x": 750, "y": 500}
    try:
        await page.evaluate(
            """() => {
                const isVis = (el) => {
                    if (!el || el.closest('#snapstreak-hud-host, #snapstreak-shadow-host')) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 4 && r.height > 4;
                };
                // 1. Check for starter camera button or 'Click the Camera to send Snaps' card
                const allEls = Array.from(document.querySelectorAll('h1, h2, h3, div, span, p, button'));
                for (const el of allEls) {
                    if (!isVis(el)) continue;
                    const r = el.getBoundingClientRect();
                    if (r.left < 300) continue;
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (t.includes('click the camera') || (t.includes('send snaps') && t.includes('camera'))) {
                        const card = el.closest('div[class*="card" i], div[class*="container" i], div') || el.parentElement;
                        if (card) {
                            const btn = card.querySelector('button, div[role="button"], svg');
                            if (btn && isVis(btn)) {
                                const target = btn.closest('button, div[role="button"]') || btn;
                                target.click();
                                return true;
                            }
                        }
                        el.click();
                        return true;
                    }
                }
                // 2. Also click any 'Turn on camera' / 'Allow' / 'Try Again' prompt button
                const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                for (const b of btns) {
                    if (!isVis(b)) continue;
                    const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (t.includes('turn on camera') || t.includes('enable camera') || t.includes('try again') || a === 'camera') {
                        b.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
    except Exception:
        pass
    await page.mouse.click(cam_coords["x"], cam_coords["y"])


async def _click_shutter_on_page(page, state_info: dict | None = None, use_dom_fallback: bool = False):
    """Perform a zero-drag quick click on the center shutter button, with optional DOM fallback."""
    state_info = state_info or await detect_screen_state(page)
    shutter = state_info.get("shutter_coords") or {"x": 750, "y": 797}
    await page.mouse.move(shutter["x"], shutter["y"])
    await page.mouse.down()
    await asyncio.sleep(0.035)
    await page.mouse.up()

    if use_dom_fallback:
        try:
            await page.evaluate(
                """({x, y}) => {
                    const direct = document.querySelector(
                        '#shutter-btn, button[aria-label*="take a picture" i], button[aria-label*="Take Snap" i], [data-testid*="capture" i]'
                    );
                    if (direct) {
                        direct.click();
                        return true;
                    }
                    const el = document.elementFromPoint(x, y);
                    const btn = el ? (el.closest('button, [role="button"]') || el) : null;
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }""",
                {"x": shutter["x"], "y": shutter["y"]},
            )
        except Exception:
            pass


async def _click_send_to_on_page(page, state_info: dict | None = None):
    """Click the 'Send To' button on the photo preview screen via DOM and mouse coordinates."""
    state_info = state_info or await detect_screen_state(page)
    send_to = state_info.get("send_to_coords") or {"x": 556, "y": 877}
    clicked_dom = False
    try:
        clicked_dom = await page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                for (const b of btns) {
                    if (b.closest('#snapstreak-hud-host, #snapstreak-shadow-host')) continue;
                    const r = b.getBoundingClientRect();
                    if (r.left < 340 || r.width <= 0) continue;
                    const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (t === 'send to' || a === 'send to' || t.startsWith('send to')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
    except Exception:
        pass
    if not clicked_dom:
        await page.mouse.click(send_to["x"], send_to["y"])


async def _click_final_send_on_page(page, state_info: dict | None = None):
    """Click the final 'Send' submit button at the bottom of the Send-To drawer."""
    state_info = state_info or await detect_screen_state(page)
    sent_clicked = False
    try:
        res = await page.evaluate(
            """() => {
                const vh = window.innerHeight || 900;
                const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                for (const b of btns) {
                    if (b.closest('#snapstreak-hud-host, #snapstreak-shadow-host')) continue;
                    const r = b.getBoundingClientRect();
                    if (r.left < 340 || r.width <= 0 || r.top < vh * 0.70) continue;
                    const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (t === 'send' || a === 'send' || a === 'send snap' || t === 'send snap') {
                        b.click();
                        return { clicked: true };
                    }
                }
                return { clicked: false };
            }"""
        )
        sent_clicked = bool(res and res.get("clicked"))
    except Exception:
        pass
    if not sent_clicked:
        fc = state_info.get("final_send_coords") or {"x": 750, "y": 865}
        await page.mouse.click(fc["x"], fc["y"])


async def run_ai_expected_steps(
    page,
    friends: list[str] | None = None,
    selection_method: str | None = None,
    step_delay: float | None = None,
    preview_only: bool = False,
    max_step_retries: int = 3,
    emit: Callable | None = None,
) -> dict:
    """
    Execute the 6 Expected Steps state-machine flow on the active Snapchat Web page,
    verifying every single step's screen transition and retrying up to max_step_retries (3)
    times with self-healing recovery if any step fails to transition:
      Step 1: Prepare & Dismiss Blockers + Inject SJSU Webcam Frame (Verified)
      Step 2: Starter Step — Click Camera to Open Viewfinder ('Click the Camera to send Snaps') (Verified -> CAMERA_READY)
      Step 3: Capture Snap (Center Shutter Quick-Click) (Verified -> PHOTO_CAPTURED)
      Step 4: Open 'Send To' Drawer (Verified -> SEND_TO_DRAWER)
      Step 5: Select Streak Recipients & Run Mandatory Safety Audit (Verified -> all valid recipients checked, 0 unauthorized)
      Step 6: Click Final 'Send' & Verify Delivery (Verified -> drawer closed)
    """
    cfg = config.load()
    friends = friends if friends is not None else cfg.get("friends", ["*//Eric\\\\*", "Dylan"])
    selection_method = selection_method or cfg.get("selection_method", "direct")
    delay = float(step_delay if step_delay is not None else cfg.get("step_delay_seconds", 1.5))
    delay = max(0.4, min(10.0, delay))
    max_retries = max(1, int(max_step_retries))

    update_execution_state(
        running=True,
        paused=False,
        stop_requested=False,
        current_mode="ai_steps",
        current_step=1,
        total_steps=6,
        step_name="Step 1/6: Preparing Snapchat & SJSU Webcam",
    )

    try:
        # ── STEP 1: PREPARE & DISMISS BLOCKERS (WITH VERIFICATION & RETRY) ──
        log("INFO", "🧠 [AI Expected Steps 1/6] Preparing Snapchat Web & injecting live SJSU webcam frame...", emit)
        state_info = {}
        state = "UNKNOWN"
        for attempt in range(1, max_retries + 1):
            await inject_webcam_frame_into_page(page, force_refresh=False)
            await dismiss_snapchat_blockers(page, emit=emit)
            state_info = await detect_screen_state(page)
            state = state_info.get("state", "UNKNOWN")

            if state == "LOGIN_REQUIRED":
                msg = "Snapchat is on the Login screen. Please sign in once in the live browser — your cookies will be kept automatically."
                log("ERROR", f"❌ {msg}", emit)
                return {f: f"error: {msg}" for f in friends}

            if state == "CHAT_OPEN":
                log("INFO", f"  ↩ [Step 1/6 Attempt {attempt}/{max_retries}] Closing open chat panel...", emit)
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                state_info = await detect_screen_state(page)
                state = state_info.get("state", "UNKNOWN")

            if state not in ("BLOCKED_MODAL", "CHAT_OPEN", "OFFLINE"):
                log("INFO", f"  ✅ [Step 1/6 Verified] Initial screen ready (state={state}).", emit)
                break
            await asyncio.sleep(0.4)

        if await _check_pause_or_stop(emit):
            return {f: "stopped" for f in friends}

        await asyncio.sleep(delay * 0.4)

        # ── STEP 2: STARTER STEP: CLICK CAMERA TO OPEN VIEWFINDER (WITH VERIFICATION & RETRY) ──
        update_execution_state(current_step=2, step_name="Step 2/6: Starter Step: Clicking Camera to Open Viewfinder")
        state_info = await detect_screen_state(page)
        state = state_info.get("state", "UNKNOWN")

        if state in ("PHOTO_CAPTURED", "SEND_TO_DRAWER"):
            log("INFO", f"🧠 [AI Expected Steps 2/6] Already at {state} — advancing directly!", emit)
        else:
            log("INFO", "🧠 [AI Expected Steps 2/6] Starter Step: Verifying Camera Viewfinder & opening camera...", emit)
            for attempt in range(1, max_retries + 1):
                state_info = await detect_screen_state(page)
                state = state_info.get("state", "UNKNOWN")
                if state in ("CAMERA_READY", "PHOTO_CAPTURED", "SEND_TO_DRAWER"):
                    log("INFO", f"  ✅ [Step 2/6 Verified] Camera Viewfinder active (state={state}).", emit)
                    break

                cam_coords = state_info.get("camera_open_coords") or {"x": 750, "y": 500}
                log(
                    "INFO",
                    f"  📸 [Step 2/6 Attempt {attempt}/{max_retries}] Starter Step: Clicking Camera button at ({cam_coords['x']}, {cam_coords['y']}) ('Click the Camera to send Snaps')...",
                    emit,
                )
                await _click_starter_camera_on_page(page, state_info)
                await asyncio.sleep(0.6)
                await inject_webcam_frame_into_page(page, force_refresh=False)

                wait_res = await wait_for_screen_states(
                    page,
                    ("CAMERA_READY", "PHOTO_CAPTURED", "SEND_TO_DRAWER"),
                    timeout_s=max(1.8, delay * 1.5),
                )
                state_info = wait_res["state_info"]
                state = state_info.get("state", "UNKNOWN")
                if wait_res["matched"]:
                    log("INFO", f"  ✅ [Step 2/6 Verified] Camera Viewfinder ready on attempt {attempt}/{max_retries} (state={state})!", emit)
                    break
                log("WARN", f"  ⚠️ [Step 2/6 Attempt {attempt}/{max_retries}] Viewfinder not active yet (state={state}), retrying...", emit)

        if await _check_pause_or_stop(emit):
            return {f: "stopped" for f in friends}

        # ── STEP 3: CAPTURE SNAP FROM SJSU WEBCAM (WITH VERIFICATION & RETRY) ──
        update_execution_state(current_step=3, step_name="Step 3/6: Capturing SJSU Webcam Snap")
        state_info = await detect_screen_state(page)
        state = state_info.get("state", "UNKNOWN")

        if state not in ("PHOTO_CAPTURED", "SEND_TO_DRAWER"):
            for attempt in range(1, max_retries + 1):
                state_info = await detect_screen_state(page)
                state = state_info.get("state", "UNKNOWN")
                if state in ("PHOTO_CAPTURED", "SEND_TO_DRAWER"):
                    break

                # Self-Heal: if screen slipped back to CLICK_CAMERA_PROMPT or HOME_NO_CAMERA, re-open camera first
                if state in ("CLICK_CAMERA_PROMPT", "HOME_NO_CAMERA", "CHAT_OPEN"):
                    log("INFO", f"  🔄 [Step 3/6 Self-Heal] Screen is at {state}; re-clicking Starter Camera button first...", emit)
                    await _click_starter_camera_on_page(page, state_info)
                    await wait_for_screen_states(page, ("CAMERA_READY",), timeout_s=2.0)
                    state_info = await detect_screen_state(page)

                shutter = state_info.get("shutter_coords") or {"x": 750, "y": 797}
                log(
                    "INFO",
                    f"🧠 [Step 3/6 Attempt {attempt}/{max_retries}] Clicking center Shutter button at ({shutter['x']}, {shutter['y']})...",
                    emit,
                )
                await _click_shutter_on_page(page, state_info, use_dom_fallback=(attempt >= 2))

                wait_res = await wait_for_screen_states(
                    page,
                    ("PHOTO_CAPTURED", "SEND_TO_DRAWER"),
                    timeout_s=max(1.0, delay),
                )
                state_info = wait_res["state_info"]
                state = state_info.get("state", "UNKNOWN")
                if wait_res["matched"]:
                    log("INFO", f"  ✅ [Step 3/6 Verified] Snap captured & preview ready on attempt {attempt}/{max_retries} (state={state})!", emit)
                    break
                log("WARN", f"  ⚠️ [Step 3/6 Attempt {attempt}/{max_retries}] Photo preview not detected yet (state={state}), retrying shutter...", emit)

        if state not in ("PHOTO_CAPTURED", "SEND_TO_DRAWER"):
            msg = f"Step 3/6 verification failed after {max_retries} attempts: Photo capture did not transition to preview (state={state})."
            log("ERROR", f"❌ {msg}", emit)
            return {f: f"error: {msg}" for f in friends}

        if await _check_pause_or_stop(emit):
            return {f: "stopped" for f in friends}

        # ── STEP 4: OPEN 'SEND TO' DRAWER (WITH VERIFICATION & RETRY) ──
        update_execution_state(current_step=4, step_name="Step 4/6: Opening 'Send To' Drawer")
        if state != "SEND_TO_DRAWER":
            for attempt in range(1, max_retries + 1):
                state_info = await detect_screen_state(page)
                state = state_info.get("state", "UNKNOWN")
                if state == "SEND_TO_DRAWER":
                    break

                # Self-Heal: if screen fell back to CAMERA_READY, recapture photo first
                if state in ("CAMERA_READY", "CLICK_CAMERA_PROMPT"):
                    log("INFO", f"  🔄 [Step 4/6 Self-Heal] Screen slipped to {state}; re-capturing snap first...", emit)
                    if state == "CLICK_CAMERA_PROMPT":
                        await _click_starter_camera_on_page(page, state_info)
                        await wait_for_screen_states(page, ("CAMERA_READY",), timeout_s=1.5)
                    await _click_shutter_on_page(page, await detect_screen_state(page), use_dom_fallback=True)
                    await wait_for_screen_states(page, ("PHOTO_CAPTURED",), timeout_s=1.5)
                    state_info = await detect_screen_state(page)

                send_to = state_info.get("send_to_coords") or {"x": 556, "y": 877}
                log(
                    "INFO",
                    f"🧠 [Step 4/6 Attempt {attempt}/{max_retries}] Clicking 'Send To' button at ({send_to['x']}, {send_to['y']})...",
                    emit,
                )
                await _click_send_to_on_page(page, state_info)

                wait_res = await wait_for_screen_states(
                    page,
                    ("SEND_TO_DRAWER",),
                    timeout_s=max(1.0, delay),
                )
                state_info = wait_res["state_info"]
                state = state_info.get("state", "UNKNOWN")
                if wait_res["matched"]:
                    log("INFO", f"  ✅ [Step 4/6 Verified] 'Send To' drawer opened on attempt {attempt}/{max_retries}!", emit)
                    break
                log("WARN", f"  ⚠️ [Step 4/6 Attempt {attempt}/{max_retries}] 'Send To' drawer not open yet (state={state}), retrying...", emit)

        if state != "SEND_TO_DRAWER":
            msg = f"Step 4/6 verification failed after {max_retries} attempts: 'Send To' drawer did not open (state={state})."
            log("ERROR", f"❌ {msg}", emit)
            return {f: f"error: {msg}" for f in friends}

        if await _check_pause_or_stop(emit):
            return {f: "stopped" for f in friends}

        # ── STEP 5: SELECT STREAK RECIPIENTS & SAFETY AUDIT (WITH VERIFICATION & RETRY) ──
        update_execution_state(current_step=5, step_name="Step 5/6: Selecting Recipients & Safety Audit")
        final_selected: list[str] = []
        for attempt in range(1, max_retries + 1):
            state_info = await detect_screen_state(page)
            if state_info.get("state") == "PHOTO_CAPTURED":
                log("INFO", "  🔄 [Step 5/6 Self-Heal] Re-opening 'Send To' drawer before selecting recipients...", emit)
                await _click_send_to_on_page(page, state_info)
                await wait_for_screen_states(page, ("SEND_TO_DRAWER",), timeout_s=1.5)

            # Determine which target friends still need to be selected
            missing_friends = [
                f for f in friends
                if not any(is_strict_friend_match(sel_name, f) for sel_name in final_selected)
            ]
            target_list = missing_friends if missing_friends else friends
            method_for_attempt = selection_method if attempt == 1 else "direct"

            log(
                "INFO",
                f"🧠 [Step 5/6 Attempt {attempt}/{max_retries}] Selecting recipients ({', '.join(target_list)}) via '{method_for_attempt}'...",
                emit,
            )
            selected = await select_friends_in_drawer(
                page,
                friends=target_list,
                selection_method=method_for_attempt,
                shortcut_name=cfg.get("shortcut_name", "Streaks"),
                emit=emit,
            )
            await asyncio.sleep(max(0.25, delay * 0.5))

            audit = await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
            audited_list = audit.get("valid_selected", [])
            for name in (audited_list or selected):
                if name not in final_selected:
                    final_selected.append(name)

            # Verify whether all requested friends have been matched
            still_missing = [
                f for f in friends
                if not any(is_strict_friend_match(sel_name, f) for sel_name in final_selected)
            ]
            if final_selected and (not still_missing or selection_method == "shortcut"):
                log(
                    "INFO",
                    f"  ✅ [Step 5/6 Verified] Recipients selected & safety-audited on attempt {attempt}/{max_retries}: {', '.join(final_selected)}",
                    emit,
                )
                break
            log(
                "WARN",
                f"  ⚠️ [Step 5/6 Attempt {attempt}/{max_retries}] Missing recipients ({', '.join(still_missing)}), retrying selection...",
                emit,
            )

        if not final_selected:
            msg = f"Step 5/6 verification failed after {max_retries} attempts: No valid streak recipients could be selected in the Send-To drawer."
            log("ERROR", f"❌ {msg}", emit)
            return {f: f"error: {msg}" for f in friends}

        # ── STEP 6: FINAL SEND & DELIVERY VERIFICATION (OR PAUSE FOR PREVIEW) ──
        if preview_only:
            update_execution_state(current_step=6, step_name="Step 6/6: Preview Ready (Paused Before Send)")
            log("INFO", "🧪 [Preview Mode] Paused before clicking final 'Send' so you can inspect selected friends!", emit)
            try:
                await page.screenshot(path=str(SCREENSHOT_FILE))
            except Exception:
                pass
            return {f: "preview_ready" for f in friends}

        update_execution_state(current_step=6, step_name="Step 6/6: Clicking Final Send & Verifying")
        for attempt in range(1, max_retries + 1):
            await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
            log("INFO", f"🧠 [Step 6/6 Attempt {attempt}/{max_retries}] Clicking final 'Send' button...", emit)
            await _click_final_send_on_page(page, await detect_screen_state(page))

            wait_res = await wait_for_screen_states(
                page,
                ("CAMERA_READY", "CLICK_CAMERA_PROMPT", "HOME_NO_CAMERA", "CHAT_OPEN"),
                timeout_s=max(1.0, delay),
            )
            state_after = wait_res["state_info"].get("state", "UNKNOWN")
            if wait_res["matched"] or state_after != "SEND_TO_DRAWER":
                log(
                    "INFO",
                    f"  ✅ [Step 6/6 Verified] Send-To drawer closed (state={state_after}) on attempt {attempt}/{max_retries}!",
                    emit,
                )
                break
            log("WARN", f"  ⚠️ [Step 6/6 Attempt {attempt}/{max_retries}] Send-To drawer still visible, retrying final Send click...", emit)

        try:
            await page.screenshot(path=str(SCREENSHOT_FILE))
        except Exception:
            pass

        log("INFO", f"🎉 Streak snap successfully sent & verified to: {', '.join(final_selected)}!", emit)
        return {f: "sent" for f in friends}

    except Exception as ex:
        log("ERROR", f"AI Expected Steps error: {ex}", emit)
        return {f: f"error: {ex}" for f in friends}
    finally:
        update_execution_state(running=False, paused=False, current_step=0, step_name="Idle")


# ─────────────────────────────────────────────────────────────────────────────
# 7. MODE B: CUSTOM MACRO RECORDER & REPLAYER ENGINE (WITH STEP VERIFICATION)
# ─────────────────────────────────────────────────────────────────────────────

async def replay_macro(
    page,
    macro_steps: list[dict] | None = None,
    friends: list[str] | None = None,
    step_delay: float | None = None,
    use_recorded_delay: bool | None = None,
    preview_only: bool = False,
    max_step_retries: int = 3,
    emit: Callable | None = None,
) -> dict:
    """
    Replay a saved or custom macro on the live Snapchat Web page with per-step verification and retry.
    Supports both:
      - User-recorded steps: {'type': 'click'|'type'|'key'|'wait', 'x', 'y', 'rx', 'ry', 'selector', 'text', 'delay_ms'}
      - Expected-action steps: {'type': 'expected_action', 'action': 'open_camera'|'capture_snap'|'click_send_to'|'select_recipients'|'click_final_send'}
    Enforces the configured step_delay (default 1.5s — never the old 30s sleep!), verifies each step, and runs mandatory pre-send safety audit.
    """
    cfg = config.load()
    friends = friends if friends is not None else cfg.get("friends", ["*//Eric\\\\*", "Dylan"])
    macro_data = config.load_macro_data()
    steps = macro_steps if macro_steps is not None else macro_data.get("steps", [])
    max_retries = max(1, int(max_step_retries))

    if not steps:
        return {f: "error: Macro has 0 steps. Record or load default steps first." for f in friends}

    delay = float(step_delay if step_delay is not None else cfg.get("step_delay_seconds", 1.5))
    delay = max(0.3, min(10.0, delay))
    use_rec = bool(use_recorded_delay if use_recorded_delay is not None else cfg.get("use_coordinate_delay", False))

    update_execution_state(
        running=True,
        paused=False,
        stop_requested=False,
        current_mode="macro",
        current_step=1,
        total_steps=len(steps),
        step_name=f"Macro Step 1/{len(steps)}",
    )

    try:
        log("INFO", f"🎬 [Macro Engine] Replaying {len(steps)} macro steps with step verification (delay={delay:.1f}s)...", emit)
        await inject_webcam_frame_into_page(page, force_refresh=False)
        await dismiss_snapchat_blockers(page, emit=emit)

        state_info = await detect_screen_state(page)
        if state_info.get("state") == "LOGIN_REQUIRED":
            msg = "Snapchat is on the Login screen. Please sign in first."
            log("ERROR", f"❌ {msg}", emit)
            return {f: f"error: {msg}" for f in friends}

        for idx, step in enumerate(steps, start=1):
            if await _check_pause_or_stop(emit):
                return {f: "stopped" for f in friends}

            stype = step.get("type", "click")
            action = step.get("action", "")
            label = step.get("label") or f"{stype} ({step.get('x', '')}, {step.get('y', '')})"

            update_execution_state(
                current_step=idx,
                total_steps=len(steps),
                step_name=f"Macro {idx}/{len(steps)}: {label}",
            )
            log("INFO", f"  ▶ Macro Step {idx}/{len(steps)}: {label}", emit)

            # Handle expected_action steps inside hybrid/default macro with verification & retry
            if stype == "expected_action":
                if action == "open_camera":
                    for attempt in range(1, max_retries + 1):
                        st = await detect_screen_state(page)
                        if st.get("state") in ("CAMERA_READY", "PHOTO_CAPTURED", "SEND_TO_DRAWER"):
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Camera viewfinder ready.", emit)
                            break
                        log("INFO", f"    📸 [Macro Step {idx} Attempt {attempt}/{max_retries}] Starter Step: Opening camera...", emit)
                        await _click_starter_camera_on_page(page, st)
                        await inject_webcam_frame_into_page(page, force_refresh=False)
                        w = await wait_for_screen_states(page, ("CAMERA_READY", "PHOTO_CAPTURED", "SEND_TO_DRAWER"), timeout_s=max(1.2, delay))
                        if w["matched"]:
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Camera ready on attempt {attempt}/{max_retries}.", emit)
                            break
                elif action == "capture_snap":
                    for attempt in range(1, max_retries + 1):
                        st = await detect_screen_state(page)
                        if st.get("state") in ("PHOTO_CAPTURED", "SEND_TO_DRAWER"):
                            break
                        if st.get("state") == "CLICK_CAMERA_PROMPT":
                            await _click_starter_camera_on_page(page, st)
                            await wait_for_screen_states(page, ("CAMERA_READY",), timeout_s=1.5)
                            st = await detect_screen_state(page)
                        await _click_shutter_on_page(page, st, use_dom_fallback=(attempt >= 2))
                        w = await wait_for_screen_states(page, ("PHOTO_CAPTURED", "SEND_TO_DRAWER"), timeout_s=max(1.0, delay))
                        if w["matched"]:
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Snap captured on attempt {attempt}/{max_retries}.", emit)
                            break
                elif action == "click_send_to":
                    for attempt in range(1, max_retries + 1):
                        st = await detect_screen_state(page)
                        if st.get("state") == "SEND_TO_DRAWER":
                            break
                        await _click_send_to_on_page(page, st)
                        w = await wait_for_screen_states(page, ("SEND_TO_DRAWER",), timeout_s=max(1.0, delay))
                        if w["matched"]:
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Send-To drawer open on attempt {attempt}/{max_retries}.", emit)
                            break
                elif action == "select_recipients":
                    for attempt in range(1, max_retries + 1):
                        sel = await select_friends_in_drawer(
                            page,
                            friends=friends,
                            selection_method=cfg.get("selection_method", "direct") if attempt == 1 else "direct",
                            shortcut_name=cfg.get("shortcut_name", "Streaks"),
                            emit=emit,
                        )
                        audit = await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
                        valid_sel = audit.get("valid_selected", []) or sel
                        if valid_sel:
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Selected recipients: {', '.join(valid_sel)}", emit)
                            break
                elif action == "click_final_send":
                    await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
                    if preview_only:
                        log("INFO", "🧪 [Preview Mode] Paused before final Macro Send step!", emit)
                        return {f: "preview_ready" for f in friends}
                    for attempt in range(1, max_retries + 1):
                        await _click_final_send_on_page(page, await detect_screen_state(page))
                        w = await wait_for_screen_states(page, ("CAMERA_READY", "CLICK_CAMERA_PROMPT", "HOME_NO_CAMERA", "CHAT_OPEN"), timeout_s=max(1.0, delay))
                        if w["matched"] or w["state_info"].get("state") != "SEND_TO_DRAWER":
                            log("INFO", f"    ✅ [Macro Step {idx} Verified] Final Send completed on attempt {attempt}/{max_retries}.", emit)
                            break

            elif stype == "click":
                # Check if this is the final step or a Send click in Preview mode
                is_final_send_click = (
                    idx == len(steps)
                    and (
                        "send" in str(step.get("text", "")).lower()
                        or "send" in str(step.get("label", "")).lower()
                        or int(step.get("y", 0)) > 780
                    )
                )
                if is_final_send_click:
                    await audit_and_sanitize_drawer_selections(page, friends, emit=emit)
                    if preview_only:
                        log("INFO", "🧪 [Preview Mode] Paused before final Macro click!", emit)
                        return {f: "preview_ready" for f in friends}

                for attempt in range(1, max_retries + 1):
                    before_st = (await detect_screen_state(page)).get("state", "UNKNOWN")
                    # Self-heal if starter camera card is blocking a shutter click
                    lbl_lower = (str(step.get("label", "")) + " " + str(step.get("text", "")) + " " + str(step.get("selector", ""))).lower()
                    if before_st == "CLICK_CAMERA_PROMPT" and ("shutter" in lbl_lower or "picture" in lbl_lower or "capture" in lbl_lower):
                        await _click_starter_camera_on_page(page)
                        await wait_for_screen_states(page, ("CAMERA_READY",), timeout_s=1.5)
                        before_st = (await detect_screen_state(page)).get("state", "UNKNOWN")

                    x = int(step.get("x", 750))
                    y = int(step.get("y", 500))
                    if step.get("rx") is not None and step.get("ry") is not None:
                        vw_vh = await page.evaluate("() => ({ w: window.innerWidth || 1440, h: window.innerHeight || 900 })")
                        x = int(round(float(step["rx"]) * vw_vh["w"]))
                        y = int(round(float(step["ry"]) * vw_vh["h"]))

                    smart_pos = await page.evaluate(
                        """({selector, text, ariaLabel}) => {
                            const isVisible = (el) => {
                                if (!el || el.closest('#snapstreak-hud-host, #snapstreak-shadow-host')) return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 4 && r.height > 4;
                            };
                            if (selector) {
                                try {
                                    const el = document.querySelector(selector);
                                    if (isVisible(el)) {
                                        const r = el.getBoundingClientRect();
                                        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                                    }
                                } catch (e) {}
                            }
                            const targetTxt = (text || ariaLabel || '').trim().toLowerCase();
                            if (targetTxt) {
                                const btns = Array.from(document.querySelectorAll('button, div[role="button"], [role="listitem"]')).filter(isVisible);
                                for (const b of btns) {
                                    const r = b.getBoundingClientRect();
                                    if (r.left < 340) continue;
                                    const bt = (b.innerText || b.textContent || '').trim().toLowerCase();
                                    const ba = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                                    if (bt === targetTxt || ba === targetTxt) {
                                        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                                    }
                                }
                            }
                            return null;
                        }""",
                        {
                            "selector": step.get("selector", ""),
                            "text": step.get("text", ""),
                            "ariaLabel": step.get("ariaLabel", ""),
                        },
                    )
                    if smart_pos and smart_pos.get("x") and smart_pos.get("y"):
                        x, y = int(smart_pos["x"]), int(smart_pos["y"])

                    await page.mouse.move(x, y)
                    await page.mouse.down()
                    await asyncio.sleep(0.035)
                    await page.mouse.up()

                    await asyncio.sleep(0.35)
                    after_st = (await detect_screen_state(page)).get("state", "UNKNOWN")
                    # Verify expected state change for known navigation clicks
                    if "shutter" in lbl_lower and after_st not in ("PHOTO_CAPTURED", "SEND_TO_DRAWER") and attempt < max_retries:
                        log("WARN", f"    ⚠️ [Macro Step {idx} Attempt {attempt}/{max_retries}] Shutter click did not reach PHOTO_CAPTURED (state={after_st}), retrying...", emit)
                        continue
                    if "send to" in lbl_lower and after_st != "SEND_TO_DRAWER" and attempt < max_retries:
                        log("WARN", f"    ⚠️ [Macro Step {idx} Attempt {attempt}/{max_retries}] 'Send To' click did not open drawer (state={after_st}), retrying...", emit)
                        continue
                    log("INFO", f"    ✅ [Macro Step {idx} Verified] Click executed at ({x}, {y}) -> state={after_st}.", emit)
                    break

            elif stype == "type":
                text = str(step.get("text", ""))
                if text:
                    await page.keyboard.type(text, delay=35)

            elif stype == "key":
                key = str(step.get("key", "Enter"))
                await page.keyboard.press(key)

            elif stype == "wait":
                wait_s = min(10.0, max(0.2, float(step.get("delay_ms", 1000)) / 1000.0))
                await asyncio.sleep(wait_s)
                continue

            # Wait between macro steps
            if use_rec and step.get("delay_ms"):
                step_wait = min(8.0, max(0.3, float(step["delay_ms"]) / 1000.0))
            else:
                step_wait = delay
            await asyncio.sleep(step_wait)

        try:
            await page.screenshot(path=str(SCREENSHOT_FILE))
        except Exception:
            pass

        log("INFO", "🎉 Macro execution & step verification completed successfully!", emit)
        return {f: "sent (macro)" for f in friends}

    except Exception as ex:
        log("ERROR", f"Macro replay error: {ex}", emit)
        return {f: f"error: {ex}" for f in friends}
    finally:
        update_execution_state(running=False, paused=False, current_step=0, step_name="Idle")


# ─────────────────────────────────────────────────────────────────────────────
# 8. UNIFIED TOP-LEVEL ENTRYPOINT (DISPATCHES AI STEPS OR MACRO MODE)
# ─────────────────────────────────────────────────────────────────────────────

async def execute_streak_flow_on_page(
    page,
    friends: list[str] | None = None,
    streak_mode: str | None = None,
    selection_method: str | None = None,
    preview_only: bool = False,
    emit: Callable | None = None,
) -> dict:
    """
    Run the configured Streak Maker flow (either 'ai_steps' or 'macro') on an active Playwright Page.
    """
    cfg = config.load()
    mode = streak_mode or cfg.get("streak_mode", "ai_steps")
    friends_list = friends if friends is not None else cfg.get("friends", ["*//Eric\\\\*", "Dylan"])
    sel_method = selection_method or cfg.get("selection_method", "direct")

    if mode == "macro":
        return await replay_macro(
            page,
            friends=friends_list,
            step_delay=cfg.get("step_delay_seconds", 1.5),
            use_recorded_delay=cfg.get("use_coordinate_delay", False),
            preview_only=preview_only,
            emit=emit,
        )
    else:
        return await run_ai_expected_steps(
            page,
            friends=friends_list,
            selection_method=sel_method,
            step_delay=cfg.get("step_delay_seconds", 1.5),
            preview_only=preview_only,
            emit=emit,
        )


async def send_streaks(
    friends: list[str],
    emit: Callable | None = None,
    selection_method: str = "direct",
    streak_mode: str | None = None,
) -> dict[str, str]:
    """
    High-level streak sender used by the scheduler and /api/send.
    Always prefers the active live browser session in login_session so it never conflicts
    with an open browser or loses cookies.
    """
    import login_session

    cfg = config.load()
    mode = streak_mode or cfg.get("streak_mode", "ai_steps")

    # Ensure live browser session is running
    if not login_session.is_active():
        log("INFO", "🚀 Starting persistent Snapchat Web browser session...", emit)
        await login_session.start(emit=emit)
        for _ in range(40):
            if login_session.is_active():
                break
            await asyncio.sleep(0.25)
        await asyncio.sleep(2.0)

    return await login_session.run_streak_in_active_session(
        friends=friends,
        emit=emit,
        selection_method=selection_method,
        streak_mode=mode,
        preview_only=False,
    )


async def preview_streaks(
    friends: list[str],
    emit: Callable | None = None,
    selection_method: str = "direct",
    streak_mode: str | None = None,
) -> dict:
    """
    Run Steps 1..5 in the live browser session and pause right before clicking final Send.
    """
    import login_session

    cfg = config.load()
    mode = streak_mode or cfg.get("streak_mode", "ai_steps")

    if not login_session.is_active():
        log("INFO", "🚀 Starting persistent Snapchat Web browser session for Preview...", emit)
        await login_session.start(emit=emit)
        for _ in range(40):
            if login_session.is_active():
                break
            await asyncio.sleep(0.25)
        await asyncio.sleep(2.0)

    res = await login_session.run_streak_in_active_session(
        friends=friends,
        emit=emit,
        selection_method=selection_method,
        streak_mode=mode,
        preview_only=True,
    )
    shot = login_session.get_Cached_Screenshot()
    return {"status": "preview_ready", "results": res, "screenshot": shot}
