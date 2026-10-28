"""
login_session.py – Persistent Interactive Snapchat Web Browser & Live Screencast Engine.
Features:
  - Keeps login cookies & IndexedDB intact across restarts (never wipes session on save)
  - Launches Chromium/Edge/Chrome with live SJSU Meteorology webcam (Y4M + zero-CORS Data URL hook)
  - Real-time Port-8080 CDP/JPEG screencast + optional Linux Xvfb/noVNC support
  - Smart Macro Recorder that enriches live viewport clicks with DOM selector & text metadata
  - Direct execution of both AI/Expected Steps Mode and Custom Macro Mode
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, BrowserContext, Page

import config
from automation import (
    SESSION_FILE,
    SESSION_BACKUP_FILE,
    MACRO_FILE,
    USER_DATA_DIR,
    FIREFOX_PROFILE_DIR,
    Y4M_FILE,
    SNAPCHAT_WEB,
    VIEWPORT,
    STEALTH_INIT_SCRIPT,
    fetch_webcam_image,
    get_webcam_data_url,
    inject_webcam_frame_into_page,
    get_extension_bundle_script,
    load_cookies_into_context,
    save_cookies_from_context,
    dismiss_snapchat_blockers,
    detect_screen_state,
    inspect_element_at_point,
    execute_streak_flow_on_page,
    is_snapchat_authenticated_url,
)

logger = logging.getLogger("snapstreak.login")

DISPLAY = ":99"
VNC_PORT = 5900
NOVNC_PORT = 6080

_state: dict = {
    "pw": None,
    "browser": None,
    "context": None,
    "page": None,
    "cdp": None,
    "xvfb": None,
    "openbox": None,
    "x11vnc": None,
    "websockify": None,
    "active": False,
    "starting": False,
    "engine": "chromium",
    "macro_recording": False,
    "macro_events": [],
    "macro_last_ts": 0.0,
    "last_shot_b64": "",
    "url": "",
    "screen_state": "IDLE",
    "last_frame_ts": 0.0,
    "emit": None,
}


def is_active() -> bool:
    return bool(_state.get("active") and _state.get("page") is not None)


def is_starting() -> bool:
    return bool(_state.get("starting"))


def get_Cached_Screenshot() -> str:
    return _state.get("last_shot_b64", "")


def get_Current_Url() -> str:
    page: Page | None = _state.get("page")
    if page:
        try:
            return page.url
        except Exception:
            pass
    return _state.get("url", "")


def get_Screen_State() -> str:
    return _state.get("screen_state", "IDLE")


def _log(msg: str, emit: Callable | None = None):
    logger.info(msg)
    cb = emit or _state.get("emit")
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _find_chrome_executable() -> str | None:
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        # Prefer Microsoft Edge on Windows if the profile was created with Edge (DPAPI compatibility), or Chrome
        candidates = [
            os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app, "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    for candidate in (
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _start_linux_virtual_display(emit: Callable | None = None):
    """Start Xvfb + openbox + x11vnc + websockify on Linux servers if available."""
    if os.name == "nt":
        return

    try:
        lock_file = f"/tmp/.X{DISPLAY.lstrip(':')}-lock"
        if os.path.exists(lock_file):
            try:
                os.unlink(lock_file)
            except Exception:
                pass

        if shutil.which("Xvfb"):
            _state["xvfb"] = subprocess.Popen(
                ["Xvfb", DISPLAY, "-screen", "0", "1440x900x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = DISPLAY
            time.sleep(0.35)

        def _bg_vnc():
            try:
                env = {**os.environ, "DISPLAY": DISPLAY}
                if shutil.which("openbox"):
                    _state["openbox"] = subprocess.Popen(["openbox"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if shutil.which("x11vnc"):
                    _state["x11vnc"] = subprocess.Popen(
                        ["x11vnc", "-display", DISPLAY, "-forever", "-shared", "-nopw", "-rfbport", str(VNC_PORT), "-quiet"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                novnc_dir = next((d for d in ("/usr/share/novnc", "/usr/share/novnc/utils") if os.path.isdir(d)), None)
                if novnc_dir and shutil.which("websockify"):
                    _state["websockify"] = subprocess.Popen(
                        ["websockify", f"--web={novnc_dir}", "--heartbeat=30", str(NOVNC_PORT), f"localhost:{VNC_PORT}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except Exception:
                pass

        asyncio.get_running_loop().run_in_executor(None, _bg_vnc)
    except Exception as ex:
        logger.debug(f"Virtual display notice: {ex}")


async def ensure_extension_active(page: Page | None = None, force_toggle: bool = False):
    """Inject the SnapStreak extension bundle and live SJSU webcam Data URL into the active page."""
    target_page = page or _state.get("page")
    if not target_page:
        return
    try:
        url = target_page.url or ""
        if not ("snapchat.com" in url or "localhost" in url or "127.0.0.1" in url):
            return

        # Push latest SJSU webcam frame first so camera_hook.js has it immediately
        await inject_webcam_frame_into_page(target_page, force_refresh=False)

        already = await target_page.evaluate("() => Boolean(window.SnapStreakHUD && document.getElementById('snapstreak-hud-host'))")
        if not already:
            script = get_extension_bundle_script()
            if script:
                await target_page.evaluate(script)
                await asyncio.sleep(0.15)

        if force_toggle:
            await target_page.evaluate("() => { if (window.SnapStreakHUD) window.SnapStreakHUD.toggleWindow(true); }")
    except Exception as ex:
        logger.debug(f"Extension injection notice: {ex}")


async def _fast_frame_loop(emit: Callable | None = None):
    """
    Continuous background screencast + state detector + SJSU webcam frame refresher + cookie auto-saver.
    """
    last_cookie_save = time.time()
    last_webcam_push = 0.0
    last_state_check = 0.0

    while _state.get("active"):
        page: Page | None = _state.get("page")
        context: BrowserContext | None = _state.get("context")
        if not page:
            await asyncio.sleep(0.3)
            continue

        now = time.time()

        # 1. Refresh SJSU webcam frame into the page every 15 seconds
        if now - last_webcam_push > 15.0:
            last_webcam_push = now
            try:
                await inject_webcam_frame_into_page(page, force_refresh=False)
            except Exception:
                pass

        # 2. Detect screen state & auto-dismiss 'Use Here' every 2 seconds
        if now - last_state_check > 2.0:
            last_state_check = now
            try:
                await dismiss_snapchat_blockers(page)
                st = await detect_screen_state(page)
                _state["screen_state"] = st.get("state", "UNKNOWN")
                _state["url"] = page.url
            except Exception:
                pass

        # 3. Auto-save cookies every 30 seconds when on Snapchat Web
        if context and (now - last_cookie_save > 30.0):
            last_cookie_save = now
            try:
                cfg = config.load()
                if cfg.get("auto_save_cookies", True) and is_snapchat_authenticated_url(page.url):
                    await save_cookies_from_context(context)
            except Exception:
                pass

        # 4. Capture JPEG frame cleanly via CDP captureScreenshot (never deadlocks compositor)
        if now - _state.get("last_frame_ts", 0.0) >= 0.40:
            try:
                cdp = _state.get("cdp")
                b64 = ""
                if cdp:
                    res_shot = await asyncio.wait_for(
                        cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 68, "fromSurface": True}),
                        timeout=2.0,
                    )
                    b64 = res_shot.get("data", "") if isinstance(res_shot, dict) else ""
                if not b64:
                    img = await asyncio.wait_for(page.screenshot(type="jpeg", quality=68), timeout=2.5)
                    b64 = base64.b64encode(img).decode("ascii")
                if b64:
                    _state["last_shot_b64"] = b64
                    _state["url"] = page.url
                    _state["last_frame_ts"] = time.time()
                    cb = emit or _state.get("emit")
                    if cb:
                        cb(json.dumps({
                            "type": "screencast",
                            "image": b64,
                            "url": page.url,
                            "screen_state": _state.get("screen_state", "UNKNOWN"),
                        }))
            except Exception:
                pass

        await asyncio.sleep(0.35)


async def start(emit: Callable | None = None, engine: str | None = None) -> dict:
    """
    Launch (or reuse) the persistent Snapchat Web browser session while preserving all login cookies.
    """
    if emit:
        _state["emit"] = emit

    if is_active():
        page: Page = _state["page"]
        await ensure_extension_active(page)
        return {"ok": True, "url": page.url, "engine": _state.get("engine", "chromium"), "reused": True}

    if _state.get("starting"):
        for _ in range(50):
            if is_active():
                return {"ok": True, "url": get_Current_Url(), "engine": _state.get("engine", "chromium")}
            await asyncio.sleep(0.2)

    _state["starting"] = True
    try:
        return await _start_impl(emit=emit, engine=engine)
    finally:
        _state["starting"] = False


async def _start_impl(emit: Callable | None = None, engine: str | None = None) -> dict:
    await _cleanup_browser_only()

    config.ensure_data_dirs()
    cfg = config.load()
    chosen_engine = (engine or cfg.get("browser_engine") or "chromium").lower()
    _state["engine"] = chosen_engine

    # 1. Fetch SJSU webcam frame & generate Y4M before launching browser
    _log("📷 Fetching live SJSU Meteorology webcam frame...", emit)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, fetch_webcam_image, False)

    # 2. Start virtual display on Linux if needed
    _start_linux_virtual_display(emit=emit)

    # 3. Clean stale SingletonLock files
    for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        p = USER_DATA_DIR / lock_name
        if p.exists() or p.is_symlink():
            try:
                p.unlink()
            except Exception:
                pass

    pw = await async_playwright().start()
    _state["pw"] = pw

    # On Windows, run headless=True so our Port-8080 Web Studio embeds the browser cleanly without popping up annoying windows,
    # unless SNAPSTREAK_HEADED=1 is explicitly set. On Linux with Xvfb (:99), run headless=False inside Xvfb.
    if os.name == "nt":
        headless = os.environ.get("SNAPSTREAK_HEADED", "0") != "1"
    else:
        headless = False if os.environ.get("DISPLAY") else True

    chrome_exe = _find_chrome_executable()
    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--disable-session-crashed-bubble",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
    ]
    if Y4M_FILE.exists():
        launch_args.append(f"--use-file-for-fake-video-capture={Y4M_FILE}")

    kwargs = {
        "user_data_dir": str(USER_DATA_DIR),
        "headless": headless,
        "viewport": VIEWPORT,
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "permissions": ["camera", "microphone", "notifications"],
        "args": launch_args,
        "ignore_default_args": ["--enable-automation"],
    }
    if chrome_exe:
        kwargs["executable_path"] = chrome_exe
        _log(f"🌐 Launching persistent browser ({Path(chrome_exe).name})...", emit)
    else:
        _log("🌐 Launching Playwright Chromium with persistent profile...", emit)

    try:
        context = await pw.chromium.launch_persistent_context(**kwargs)
    except Exception as ex:
        _log(f"⚠ Primary browser launch notice ({ex}), retrying with bundled Chromium...", emit)
        kwargs.pop("executable_path", None)
        context = await pw.chromium.launch_persistent_context(**kwargs)

    # 4. Inject stealth + extension + SJSU webcam hook
    await context.add_init_script(STEALTH_INIT_SCRIPT)
    ext_script = get_extension_bundle_script()
    if ext_script:
        await context.add_init_script(ext_script)

    # 5. Load cookies from session.json into persistent context AND sync back to session.json
    injected_count = await load_cookies_into_context(context, emit=emit)
    if injected_count > 0:
        _log(f"🍪 Loaded {injected_count} saved cookies from session vault.", emit)

    # Also immediately export storage_state from persistent profile so session.json has all profile cookies
    save_res = await save_cookies_from_context(context, emit=emit)
    if save_res.get("ok"):
        _log(f"🍪 Cookie Vault synced: {save_res.get('snapchat_cookies', 0)} Snapchat cookies active.", emit)

    _state["context"] = context
    page = context.pages[0] if context.pages else await context.new_page()
    _state["page"] = page
    _state["active"] = True

    for origin in ("https://web.snapchat.com", "https://www.snapchat.com", "https://accounts.snapchat.com"):
        try:
            await context.grant_permissions(["camera", "microphone", "notifications"], origin=origin)
        except Exception:
            pass

    page.on("domcontentloaded", lambda p: asyncio.create_task(ensure_extension_active(p)))
    page.on("load", lambda p: asyncio.create_task(ensure_extension_active(p)))

    # 6. Attach CDP session for permissions and fast non-blocking captureScreenshot
    try:
        cdp = await context.new_cdp_session(page)
        _state["cdp"] = cdp
        for origin in ("https://web.snapchat.com", "https://www.snapchat.com", "https://accounts.snapchat.com"):
            try:
                await cdp.send(
                    "Browser.grantPermissions",
                    {
                        "permissions": ["videoCapture", "audioCapture", "notifications", "durableStorage"],
                        "origin": origin,
                    },
                )
            except Exception:
                pass
    except Exception as ex:
        logger.debug(f"CDP session notice: {ex}")

    asyncio.create_task(_fast_frame_loop(emit=emit))

    # 7. Always navigate to https://web.snapchat.com/ first so existing cookies log right in!
    target_url = SNAPCHAT_WEB
    _log(f"🚀 Opening {target_url} with saved login cookies & SJSU webcam...", emit)

    async def _initial_nav():
        try:
            await page.goto(target_url, timeout=35_000, wait_until="domcontentloaded")
            await ensure_extension_active(page, force_toggle=False)
            await dismiss_snapchat_blockers(page, emit=emit)
            st = await detect_screen_state(page)
            _state["screen_state"] = st.get("state", "UNKNOWN")
            _state["url"] = page.url
            await save_cookies_from_context(context)
        except Exception as ex:
            _log(f"Navigation notice: {ex}", emit)

    asyncio.create_task(_initial_nav())
    return {"ok": True, "url": target_url, "engine": chosen_engine}


async def save(emit: Callable | None = None) -> dict:
    """
    Save current cookies & localStorage to session.json and session_backup.json
    WITHOUT closing the active browser session!
    """
    context: BrowserContext | None = _state.get("context")
    if not context:
        summary = config.get_cookie_vault_summary()
        if summary.get("has_session_file"):
            return {"ok": True, "message": f"Session file already saved ({summary.get('snapchat_cookies', 0)} Snapchat cookies)."}
        return {"ok": False, "message": "No active browser session to save."}

    res = await save_cookies_from_context(context, emit=emit)
    if res.get("ok"):
        _log(f"✓ {res['message']}", emit)
    return res


async def import_cookies(raw_input: str | dict | list, emit: Callable | None = None) -> dict:
    """
    Import cookies from JSON (Cookie-Editor array or Playwright storage_state) or raw Cookie header string,
    inject them into the live browser context if active, and persist to session.json & session_backup.json.
    """
    config.ensure_data_dirs()
    parsed_cookies = []
    origins = []

    try:
        if isinstance(raw_input, str):
            text = raw_input.strip()
            if text.startswith("{") or text.startswith("["):
                data = json.loads(text)
            else:
                # Parse raw Cookie header string: key1=val1; key2=val2
                data = []
                for part in text.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        data.append({"name": k.strip(), "value": v.strip(), "domain": ".snapchat.com", "path": "/"})
        else:
            data = raw_input

        if isinstance(data, dict):
            raw_list = data.get("cookies", [])
            origins = data.get("origins", [])
        elif isinstance(data, list):
            raw_list = data
        else:
            raw_list = []

        for c in raw_list:
            if not isinstance(c, dict) or not c.get("name") or c.get("value") is None:
                continue
            same_site_raw = str(c.get("sameSite", "Lax")).lower()
            same_site = "None" if "no" in same_site_raw else ("Strict" if "strict" in same_site_raw else "Lax")
            cookie_obj = {
                "name": str(c["name"]),
                "value": str(c["value"]),
                "domain": str(c.get("domain", ".snapchat.com")),
                "path": str(c.get("path", "/")),
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": bool(c.get("secure", True)),
                "sameSite": same_site,
            }
            exp = c.get("expirationDate") or c.get("expires")
            if exp and float(exp) > 0:
                cookie_obj["expires"] = float(exp)
            parsed_cookies.append(cookie_obj)

        if not parsed_cookies:
            return {"ok": False, "message": "No valid cookies found in input."}

        # Merge with existing cookies in session.json so we never lose other cookies
        existing_cookies = []
        if SESSION_FILE.exists():
            try:
                old = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                existing_cookies = old.get("cookies", []) if isinstance(old, dict) else []
                if not origins and isinstance(old, dict):
                    origins = old.get("origins", [])
            except Exception:
                pass

        by_key = {(c.get("domain"), c.get("name"), c.get("path", "/")): c for c in existing_cookies if isinstance(c, dict)}
        for c in parsed_cookies:
            by_key[(c.get("domain"), c.get("name"), c.get("path", "/"))] = c

        merged_state = {"cookies": list(by_key.values()), "origins": origins}
        SESSION_FILE.write_text(json.dumps(merged_state, indent=2), encoding="utf-8")
        SESSION_BACKUP_FILE.write_text(json.dumps(merged_state, indent=2), encoding="utf-8")

        context: BrowserContext | None = _state.get("context")
        page: Page | None = _state.get("page")
        if context:
            await context.add_cookies(parsed_cookies)
            if page:
                await page.goto(SNAPCHAT_WEB, wait_until="domcontentloaded", timeout=30_000)

        return {
            "ok": True,
            "imported_count": len(parsed_cookies),
            "total_cookies": len(merged_state["cookies"]),
            "message": f"Imported {len(parsed_cookies)} cookies and saved to Cookie Vault.",
        }
    except Exception as ex:
        return {"ok": False, "message": f"Failed to import cookies: {ex}"}


async def restore_cookie_backup(emit: Callable | None = None) -> dict:
    """Restore session.json from session_backup.json and reload into active browser context."""
    config.ensure_data_dirs()
    if not SESSION_BACKUP_FILE.exists():
        return {"ok": False, "message": "No cookie backup file found."}
    try:
        shutil.copy2(SESSION_BACKUP_FILE, SESSION_FILE)
        context: BrowserContext | None = _state.get("context")
        page: Page | None = _state.get("page")
        count = 0
        if context:
            count = await load_cookies_into_context(context, emit=emit)
            if page:
                await page.goto(SNAPCHAT_WEB, wait_until="domcontentloaded", timeout=30_000)
        summary = config.get_cookie_vault_summary()
        return {
            "ok": True,
            "restored_cookies": count or summary.get("total_cookies", 0),
            "message": f"Restored {summary.get('total_cookies', 0)} cookies ({summary.get('snapchat_cookies', 0)} Snapchat cookies) from backup!",
        }
    except Exception as ex:
        return {"ok": False, "message": f"Restore backup failed: {ex}"}


# ─────────────────────────────────────────────────────────────────────────────
# LIVE BROWSER INTERACTION & SMART MACRO RECORDING
# ─────────────────────────────────────────────────────────────────────────────

async def click(x: int, y: int):
    """
    Click at viewport coordinates (x, y) in the live browser.
    If Macro Recording is active, inspects the DOM element at (x, y) first and records
    both DOM selector/text metadata and relative/absolute coordinates!
    """
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")

    if _state.get("macro_recording"):
        now = time.time()
        delay_ms = int((now - _state["macro_last_ts"]) * 1000) if _state.get("macro_last_ts") else 1200
        delay_ms = max(300, min(8000, delay_ms))
        _state["macro_last_ts"] = now

        meta = await inspect_element_at_point(page, x, y)
        step = {
            "id": f"step_{len(_state['macro_events']) + 1}_{int(now * 1000) % 100000}",
            "type": "click",
            "x": x,
            "y": y,
            "rx": meta.get("rx", round(x / VIEWPORT["width"], 4)),
            "ry": meta.get("ry", round(y / VIEWPORT["height"], 4)),
            "label": meta.get("label", f"Click at ({x}, {y})"),
            "selector": meta.get("selector", ""),
            "text": meta.get("text", ""),
            "ariaLabel": meta.get("ariaLabel", ""),
            "tagName": meta.get("tagName", "div"),
            "delay_ms": delay_ms,
        }
        _state["macro_events"].append(step)
        _log(f"🔴 [Macro Recorded #{len(_state['macro_events'])}] {step['label']} at ({x}, {y})")

    await page.mouse.move(x, y)
    await page.mouse.down()
    await asyncio.sleep(0.035)
    await page.mouse.up()
    _state["last_frame_ts"] = 0.0


async def send_text(text: str):
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")

    if _state.get("macro_recording") and text:
        now = time.time()
        delay_ms = int((now - _state["macro_last_ts"]) * 1000) if _state.get("macro_last_ts") else 1000
        _state["macro_last_ts"] = now
        _state["macro_events"].append({
            "id": f"step_{len(_state['macro_events']) + 1}_{int(now * 1000) % 100000}",
            "type": "type",
            "text": text,
            "label": f'Type "{text[:24]}"',
            "delay_ms": max(300, min(6000, delay_ms)),
        })

    await page.keyboard.type(text, delay=25)
    _state["last_frame_ts"] = 0.0


async def press_key(key: str):
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")

    if _state.get("macro_recording") and key:
        now = time.time()
        delay_ms = int((now - _state["macro_last_ts"]) * 1000) if _state.get("macro_last_ts") else 800
        _state["macro_last_ts"] = now
        _state["macro_events"].append({
            "id": f"step_{len(_state['macro_events']) + 1}_{int(now * 1000) % 100000}",
            "type": "key",
            "key": key,
            "label": f"Press [{key}]",
            "delay_ms": max(300, min(6000, delay_ms)),
        })

    await page.keyboard.press(key)
    _state["last_frame_ts"] = 0.0


async def scroll(delta_x: int = 0, delta_y: int = 300):
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")
    await page.mouse.wheel(delta_x, delta_y)
    _state["last_frame_ts"] = 0.0


async def navigate(url: str) -> dict:
    page: Page | None = _state.get("page")
    if not page:
        await start()
        page = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
    await ensure_extension_active(page)
    _state["last_frame_ts"] = 0.0
    return {"ok": True, "url": page.url}


async def go_back() -> dict:
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")
    await page.go_back(wait_until="domcontentloaded", timeout=15_000)
    _state["last_frame_ts"] = 0.0
    return {"ok": True, "url": page.url}


async def go_forward() -> dict:
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")
    await page.go_forward(wait_until="domcontentloaded", timeout=15_000)
    _state["last_frame_ts"] = 0.0
    return {"ok": True, "url": page.url}


async def reload_page() -> dict:
    page: Page | None = _state.get("page")
    if not page:
        raise RuntimeError("No active browser session")
    await page.reload(wait_until="domcontentloaded", timeout=30_000)
    await ensure_extension_active(page)
    _state["last_frame_ts"] = 0.0
    return {"ok": True, "url": page.url}


async def quick_fill_login(username: str, password: str, emit: Callable | None = None) -> dict:
    """Fill Snapchat login inputs without touching existing cookies."""
    page: Page | None = _state.get("page")
    if not page:
        await start(emit=emit)
        page = _state.get("page")
    if not page:
        return {"ok": False, "message": "Browser not active"}

    try:
        if "accounts.snapchat.com" not in page.url:
            await page.goto("https://accounts.snapchat.com/accounts/v2/login?continue=https%3A%2F%2Fweb.snapchat.com%2F", wait_until="domcontentloaded")
            await asyncio.sleep(1.0)

        user_inp = page.locator('input[name="accountIdentifier"], input[autocomplete="username"], input[type="text"], input[type="email"]').first
        if await user_inp.count() > 0:
            await user_inp.click()
            await user_inp.fill(username)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.5)

        if password:
            pw_inp = page.locator('input[type="password"], input[name="password"]').first
            if await pw_inp.count() > 0:
                await pw_inp.click()
                await pw_inp.fill(password)
                await page.keyboard.press("Enter")

        return {"ok": True, "message": "Login credentials submitted."}
    except Exception as ex:
        return {"ok": False, "message": f"Login fill notice: {ex}"}


async def repair_snapchat_session(emit: Callable | None = None) -> dict:
    """
    Repair Snapchat Web ('Already open in another tab', frozen camera, or blank screen)
    while strictly keeping all login cookies and IndexedDB intact!
    """
    if not is_active():
        await start(emit=emit)

    page: Page | None = _state.get("page")
    context: BrowserContext | None = _state.get("context")
    if not page or not context:
        return {"ok": False, "message": "Failed to attach to browser session."}

    try:
        _log("🔧 Repairing Snapchat Web (preserving all login cookies)...", emit)
        # Save cookies first
        await save_cookies_from_context(context, emit=emit)

        # Close extra tabs so only 1 Snapchat tab exists
        pages = list(context.pages)
        if len(pages) > 1:
            for extra in pages[1:]:
                try:
                    await extra.close()
                except Exception:
                    pass

        await page.goto(SNAPCHAT_WEB, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(0.8)
        await ensure_extension_active(page)
        await dismiss_snapchat_blockers(page, emit=emit)
        await inject_webcam_frame_into_page(page, force_refresh=True)
        _state["last_frame_ts"] = 0.0
        return {"ok": True, "message": "Snapchat Web repaired and SJSU webcam refreshed (all cookies preserved)."}
    except Exception as ex:
        return {"ok": False, "message": f"Repair error: {ex}"}


# ─────────────────────────────────────────────────────────────────────────────
# MACRO RECORDING & MANAGEMENT API IN LOGIN SESSION
# ─────────────────────────────────────────────────────────────────────────────

def start_macro_recording():
    _state["macro_recording"] = True
    _state["macro_events"] = []
    _state["macro_last_ts"] = time.time()
    _log("🔴 Started live Macro Recording! Click the steps on the Snapchat screen.")


def stop_macro_recording(macro_name: str = "Custom Recorded Macro") -> list[dict]:
    _state["macro_recording"] = False
    events = list(_state.get("macro_events", []))
    if events:
        macro_data = config.load_macro_data()
        name = (macro_name or "Custom Recorded Macro").strip()
        macro_data["active_macro"] = name
        macro_data["steps"] = events
        if "macros" not in macro_data or not isinstance(macro_data["macros"], dict):
            macro_data["macros"] = {}
        macro_data["macros"][name] = {
            "name": name,
            "steps": events,
            "is_default": False,
            "updated_at": int(time.time()),
        }
        config.save_macro_data(macro_data)
        _log(f"✓ Saved macro '{name}' with {len(events)} steps.")
    return events


def get_macro_info() -> dict:
    macro_data = config.load_macro_data()
    steps = _state["macro_events"] if _state.get("macro_recording") else macro_data.get("steps", [])
    return {
        "recording": bool(_state.get("macro_recording")),
        "active_macro": macro_data.get("active_macro", "Default Streak Flow"),
        "count": len(steps),
        "steps": steps,
        "macros": macro_data.get("macros", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RUN STREAK AUTOMATION IN ACTIVE SESSION (AI STEPS OR MACRO MODE)
# ─────────────────────────────────────────────────────────────────────────────

async def run_streak_in_active_session(
    friends: list[str] | None = None,
    emit: Callable | None = None,
    selection_method: str | None = None,
    streak_mode: str | None = None,
    preview_only: bool = False,
) -> dict[str, str]:
    """
    Execute either AI/Expected Steps Mode or Custom Macro Mode directly inside the active
    Snapchat Web browser session, then auto-save cookies once finished.
    """
    if not is_active():
        await start(emit=emit)
        for _ in range(30):
            if is_active():
                break
            await asyncio.sleep(0.2)

    page: Page | None = _state.get("page")
    context: BrowserContext | None = _state.get("context")
    if not page:
        return {"status": "error: Browser session is not active"}

    cfg = config.load()
    target_friends = friends if friends is not None else cfg.get("friends", ["*//Eric\\\\*", "Dylan"])
    mode = streak_mode or cfg.get("streak_mode", "ai_steps")
    sel_method = selection_method or cfg.get("selection_method", "direct")

    # Make sure we are on Snapchat Web
    if not ("snapchat.com" in (page.url or "")):
        await page.goto(SNAPCHAT_WEB, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(1.5)

    await ensure_extension_active(page, force_toggle=False)

    res = await execute_streak_flow_on_page(
        page=page,
        friends=target_friends,
        streak_mode=mode,
        selection_method=sel_method,
        preview_only=preview_only,
        emit=emit,
    )

    # Save cookies after run so session state stays fresh
    if context:
        try:
            await save_cookies_from_context(context)
        except Exception:
            pass

    _state["last_frame_ts"] = 0.0
    return res


async def cancel():
    """Stop the active browser session AFTER saving cookies first so login is never lost."""
    context: BrowserContext | None = _state.get("context")
    if context:
        try:
            await save_cookies_from_context(context)
        except Exception:
            pass
    await _cleanup_browser_only()


async def _cleanup_browser_only():
    _state["active"] = False
    for key in ("cdp", "context", "browser", "pw"):
        obj = _state.get(key)
        _state[key] = None
        if obj:
            try:
                if key == "cdp":
                    await obj.detach()
                elif key == "pw":
                    await obj.stop()
                else:
                    await obj.close()
            except Exception:
                pass
    _state["page"] = None
