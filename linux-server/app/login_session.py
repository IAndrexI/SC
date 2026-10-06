"""
login_session.py – Remote browser login via headless Playwright + screenshot streaming.

No extra ports, no VNC, no Xvfb. Works entirely through port 8080.
Browser runs headless, takes screenshots every second, forwards
mouse/keyboard events from the web UI.
"""

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from automation import (
    DATA_DIR,
    SESSION_FILE,
    USER_AGENT,
    VIEWPORT,
    USER_DATA_DIR,
    MACRO_FILE,
    Y4M_FILE,
    STEALTH_INIT_SCRIPT,
    replay_macro,
    fetch_webcam_image,
    _cleanup_stale_locks,
    _log,
)





import os
import sys
import shutil
import socket
import subprocess

DISPLAY    = ":99"
VNC_PORT   = 5900
NOVNC_PORT = 6080
NOVNC_WEB  = "/usr/share/novnc"

_macro: dict = {
    "recording": False,
    "events": [],
    "last_time": 0.0,
}


def start_macro_recording() -> dict:
    _macro["recording"] = True
    _macro["events"] = []
    _macro["last_time"] = time.time()
    return {"ok": True, "recording": True}


def stop_macro_recording() -> dict:
    _macro["recording"] = False
    events = list(_macro["events"])
    if events:
        MACRO_FILE.write_text(json.dumps(events, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(events), "events": events}


def get_macro_info() -> dict:
    has_macro = MACRO_FILE.exists()
    count = 0
    if has_macro:
        try:
            count = len(json.loads(MACRO_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"has_macro": has_macro, "count": count, "recording": _macro["recording"]}


_state: dict = {
    "active":        False,
    "playwright":    None,
    "context":       None,
    "page":          None,
    "cdp":           None,
    "last_shot_b64": "",
    "url":           "",
    "xvfb":          None,
    "openbox":       None,
    "x11vnc":        None,
    "websockify":    None,
    "chrome_proc":   None,
}


def _kill(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _cleanup_processes():
    _kill(_state.get("chrome_proc"))
    _kill(_state.get("websockify"))
    _kill(_state.get("x11vnc"))
    _kill(_state.get("openbox"))
    _kill(_state.get("xvfb"))
    _state["xvfb"] = _state["openbox"] = _state["x11vnc"] = _state["websockify"] = _state["chrome_proc"] = None

    # Kill lingering instances by process name if orphaned
    try:
        subprocess.run(["pkill", "-9", "-f", "x11vnc"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "websockify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "Xvfb :99"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "google-chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "firefox_profile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "browser_profile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Remove stale X11 and profile lock files
    for f in [
        "/tmp/.X99-lock",
        "/tmp/.X11-unix/X99",
        "/data/sc/firefox_profile/.parentlock",
        "/data/sc/firefox_profile/parent.lock",
        "/data/sc/firefox_profile/lock",
    ]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except Exception:
        return False


async def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 4.0) -> bool:
    start_t = time.time()
    while time.time() - start_t < timeout:
        if _is_port_listening(port, host):
            return True
        await asyncio.sleep(0.2)
    return False


async def _cleanup():
    _cleanup_processes()
    try:
        if _state["cdp"]:
            await _state["cdp"].detach()
    except Exception:
        pass
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
        context=None, page=None, cdp=None, last_shot_b64="", url="",
        xvfb=None, x11vnc=None, websockify=None
    )


def is_active() -> bool:
    return _state["active"]


def last_screenshot_b64() -> str:
    """Return the latest screenshot as a base64 JPEG string."""
    return _state.get("last_shot_b64", "")


def current_url() -> str:
    return _state.get("url", "")


async def _fast_frame_loop():
    """Fallback frame loop in case CDP screencast is idle."""
    while _state["active"]:
        try:
            page: Page = _state["page"]
            if page and not _state["last_shot_b64"]:
                img = await page.screenshot(type="jpeg", quality=60, full_page=False)
                _state["last_shot_b64"] = base64.b64encode(img).decode()
                _state["url"] = page.url
        except Exception:
            pass
        await asyncio.sleep(0.5)


def _find_chrome_executable() -> str | None:
    for path in [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/google-chrome",
        "/usr/bin/chromium",
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ]:
        if os.path.exists(path):
            return path
    return None


def _find_firefox_executable() -> str | None:
    for path in [
        "/usr/bin/firefox-esr",
        "/usr/bin/firefox",
        "/opt/firefox/firefox",
        "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
        "C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe",
    ]:
        if os.path.exists(path):
            return path
    return None


_start_lock = asyncio.Lock()


def is_starting() -> bool:
    return _start_lock.locked()


async def start(emit: Callable | None = None, engine: str | None = None) -> str:
    """Serialize launches: a second concurrent start used to stop the first
    launch's Playwright driver, producing 'Target ... has been closed'."""
    if _start_lock.locked():
        _log("  ℹ A browser launch is already in progress — ignoring duplicate request.", emit)
        return "Already starting."
    async with _start_lock:
        try:
            return await _start_impl(emit=emit, engine=engine)
        except Exception:
            await _cleanup()
            raise


async def _start_impl(emit: Callable | None = None, engine: str | None = None) -> str:
    if _state["active"] and _state["page"]:
        return "Already running."

    await _cleanup()
    _cleanup_stale_locks()
    fetch_webcam_image()  # ensure Y4M_FILE is ready before launch
    _log("Launching browser with persistent profile...", emit)

    pw = await async_playwright().start()
    _state["playwright"] = pw

    is_linux = sys.platform.startswith("linux")
    has_xvfb = shutil.which("Xvfb") is not None

    env = dict(os.environ)
    if is_linux and has_xvfb:
        _log("Starting virtual X11 desktop (Xvfb)...", emit)
        _cleanup_processes()
        await asyncio.sleep(0.3)

        _state["xvfb"] = subprocess.Popen(
            ["Xvfb", DISPLAY, "-screen", "0", f"{VIEWPORT['width']}x{VIEWPORT['height']}x24", "-ac", "+extension", "RANDR", "+extension", "GLX", "-noreset"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        await asyncio.sleep(1.0)

        _log("Starting VNC server (x11vnc)...", emit)
        _state["x11vnc"] = subprocess.Popen(
            [
                "x11vnc",
                "-display", DISPLAY,
                "-nopw",
                "-forever",
                "-shared",
                "-rfbport", str(VNC_PORT),
                "-listen", "127.0.0.1",
                "-wait", "5",
                "-defer", "5",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

        vnc_ok = await _wait_for_port(VNC_PORT, "127.0.0.1", timeout=3.5)
        if vnc_ok:
            _log(f"  ✓ x11vnc listening on 127.0.0.1:{VNC_PORT}", emit)
        else:
            _log(f"  ⚠ x11vnc failed to bind port {VNC_PORT} in time.", emit)

        if shutil.which("openbox"):
            _log("Starting X11 window manager (openbox)...", emit)
            _state["openbox"] = subprocess.Popen(
                ["openbox"],
                env={**env, "DISPLAY": DISPLAY},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            await asyncio.sleep(0.3)

        novnc_web = NOVNC_WEB if Path(NOVNC_WEB).exists() else None
        websock_cmd = [
            "websockify",
            "--web", novnc_web,
            f"0.0.0.0:{NOVNC_PORT}",
            f"127.0.0.1:{VNC_PORT}",
        ] if novnc_web else [
            "websockify",
            f"0.0.0.0:{NOVNC_PORT}",
            f"127.0.0.1:{VNC_PORT}",
        ]
        _log(f"Starting web desktop proxy (noVNC port {NOVNC_PORT} -> 127.0.0.1:{VNC_PORT})...", emit)
        _state["websockify"] = subprocess.Popen(
            websock_cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        novnc_ok = await _wait_for_port(NOVNC_PORT, "127.0.0.1", timeout=3.5)
        if novnc_ok:
            _log(f"  ✓ noVNC websockify listening on port {NOVNC_PORT}", emit)
        else:
            _log(f"  ⚠ websockify failed to bind port {NOVNC_PORT}.", emit)

        env["DISPLAY"] = DISPLAY
        headless = False
        _log(f"✓ Real browser desktop ready on port {NOVNC_PORT}.", emit)
    else:
        headless = True

    import config
    cfg = config.load()
    chosen_engine = (engine or cfg.get("browser_engine") or "firefox").lower()

    context = None
    if chosen_engine == "firefox":
        _log("🦊 Using Firefox ESR Gecko Engine (Arkose Labs anti-bot bypass)...", emit)
        ff_exe = _find_firefox_executable()
        ff_profile_dir = DATA_DIR / "firefox_profile"
        ff_profile_dir.mkdir(parents=True, exist_ok=True)

        ff_kwargs = {
            "user_data_dir": str(ff_profile_dir),
            "headless": headless,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "locale": "en-US",
            "timezone_id": "America/Los_Angeles",
            "permissions": ["camera", "microphone", "notifications"],
            "firefox_user_prefs": {
                "media.navigator.permission.disabled": True,
                "permissions.default.camera": 1,
                "permissions.default.microphone": 1,
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
            },
            "env": env,
        }
        if not headless:
            ff_kwargs["no_viewport"] = True
        else:
            ff_kwargs["viewport"] = VIEWPORT
        # NOTE: Playwright requires its own patched Firefox build (Juggler protocol).
        # Stock /usr/bin/firefox-esr closes immediately ("Target ... has been closed").
        _log("  ℹ Using Playwright's patched Firefox (Gecko) build.", emit)

        try:
            _log("  Launching Firefox persistent context...", emit)
            context = await pw.firefox.launch_persistent_context(**ff_kwargs)
            _log("  ✓ Firefox context launched successfully.", emit)
        except Exception as ff_err:
            _log(f"  ⚠ Firefox ESR failed to launch: {ff_err}", emit)
            _log("  🔄 Automatically falling back to Google Chrome / Chromium...", emit)
            chosen_engine = "chromium"

    if not context or chosen_engine != "firefox":
        _log("🌐 Using Google Chrome / Chromium engine...", emit)
        chrome_exe = _find_chrome_executable()
        if chrome_exe:
            _log(f"  ✓ Using official browser: {chrome_exe}", emit)
        else:
            _log("  ℹ Using Playwright Chromium.", emit)

        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--start-maximized",
            "--window-position=0,0",
            f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--no-first-run",
            "--disable-infobars",
            "--disable-features=IsolateOrigins,site-per-process",
            "--enable-webgl",
            "--enable-webgl2",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ]
        if Y4M_FILE.exists():
            launch_args.append(f"--use-file-for-fake-video-capture={Y4M_FILE}")

        # Auto-load SnapStreak extension so the user has the overlay HUD just like Windows
        ext_dir = None
        candidates = [
            Path(__file__).resolve().parent.parent / "extension",
            Path(__file__).resolve().parent / "extension",
            Path("/opt/sc/linux-server/extension"),
            Path("/opt/sc/extension"),
            Path("/opt/snapstreak/linux-server/extension"),
            Path(__file__).resolve().parent.parent.parent / "windows-extension" / "extension",
        ]
        for cand in candidates:
            if (cand / "manifest.json").exists():
                ext_dir = cand.resolve()
                break

        if ext_dir and not headless:
            launch_args.extend([
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}",
            ])
            _log(f"  ✓ Loaded SnapStreak Extension: {ext_dir}", emit)

        CDP_PORT = 9222
        # If an official system Chrome is installed, launch it as a native OS process with remote debugging
        # This completely strips all Playwright automation drivers, process trees, and runtime flags.
        if chrome_exe and not headless:
            _log("  🚀 Launching official Chrome as native system process (CDP un-automated mode)...", emit)
            chrome_cmd = [
                chrome_exe,
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={USER_DATA_DIR}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
                "--enable-webgl",
                "--enable-webgl2",
                "--start-maximized",
                "--window-position=0,0",
                f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
                f"--user-agent={USER_AGENT}",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ]
            if Y4M_FILE.exists():
                chrome_cmd.append(f"--use-file-for-fake-video-capture={Y4M_FILE}")
            if ext_dir:
                chrome_cmd.extend([
                    f"--disable-extensions-except={ext_dir}",
                    f"--load-extension={ext_dir}",
                ])

            for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                try:
                    (USER_DATA_DIR / lock_name).unlink()
                except Exception:
                    pass

            chrome_env = {**env, "DISPLAY": DISPLAY}
            _state["chrome_proc"] = subprocess.Popen(
                chrome_cmd,
                env=chrome_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            _log(f"  ⏳ Waiting for native Chrome CDP on port {CDP_PORT}...", emit)
            cdp_ready = await _wait_for_port(CDP_PORT, "127.0.0.1", timeout=8.0)
            if cdp_ready:
                _log(f"  ✓ Native Chrome listening on CDP port {CDP_PORT}. Connecting...", emit)
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                await context.add_init_script(STEALTH_INIT_SCRIPT)
                _log("  ✓ Connected cleanly to native Chrome without automation flags.", emit)
            else:
                _log("  ⚠ Native Chrome CDP wait timed out; falling back to persistent context...", emit)

        if not context:
            kwargs = {
                "user_data_dir": str(USER_DATA_DIR),
                "headless": headless,
                "user_agent": USER_AGENT,
                "locale": "en-US",
                "timezone_id": "America/Los_Angeles",
                "permissions": ["camera", "microphone", "notifications"],
                "args": launch_args,
                "env": env,
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Upgrade-Insecure-Requests": "1",
                },
                "ignore_default_args": ["--enable-automation"],
            }
            if not headless:
                kwargs["no_viewport"] = True
            else:
                kwargs["viewport"] = VIEWPORT

            if chrome_exe:
                kwargs["executable_path"] = chrome_exe

            try:
                _log("  Launching Chromium persistent context...", emit)
                context = await pw.chromium.launch_persistent_context(**kwargs)
            except Exception as cr_err:
                _log(f"  ⚠ Chrome failed to launch: {cr_err}", emit)
                if "executable_path" not in kwargs:
                    raise
                _log("  🔄 Retrying with Playwright's bundled Chromium...", emit)
                kwargs.pop("executable_path", None)
                for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                    try:
                        (USER_DATA_DIR / lock_name).unlink()
                    except Exception:
                        pass
                context = await pw.chromium.launch_persistent_context(**kwargs)
            await context.add_init_script(STEALTH_INIT_SCRIPT)
            _log("  ✓ Chromium context launched successfully.", emit)

    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                _log(f"  ✓ Injected {len(cookies)} cookies from session.json into browser context.", emit)
        except Exception as ex:
            _log(f"  ⚠ Failed to inject session cookies: {ex}", emit)

    _state["context"] = context

    page = context.pages[0] if context.pages else await context.new_page()
    _state["page"] = page
    _state["active"] = True

    # Start screencast: CDP for Chromium, fast frame loop for Firefox
    if chosen_engine != "firefox":
        try:
            cdp = await context.new_cdp_session(page)
            _state["cdp"] = cdp

            async def on_screencast_frame(params):
                session_id = params.get("sessionId")
                data_b64 = params.get("data", "")
                if session_id:
                    try:
                        await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                    except Exception:
                        pass
                if data_b64:
                    _state["last_shot_b64"] = data_b64
                    _state["url"] = page.url
                    if emit:
                        emit(json.dumps({"type": "screencast", "image": data_b64, "url": page.url}))

            cdp.on("Page.screencastFrame", lambda params: asyncio.create_task(on_screencast_frame(params)))

            await cdp.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 60,
                "maxWidth": 1440,
                "maxHeight": 900,
                "everyNthFrame": 1,
            })
        except Exception as ex:
            _log(f"CDP Screencast fallback: {ex}", emit)
            asyncio.create_task(_fast_frame_loop())
    else:
        _log("  ℹ Firefox active — streaming via screenshot loop.", emit)
        asyncio.create_task(_fast_frame_loop())

    # Navigate directly to Snapchat Web with autoboot enabled so the extension activates
    target_url = "https://web.snapchat.com/?snapstreak_autoboot=1"
    _log(f"Navigating to {target_url}...", emit)

    async def _initial_navigation():
        try:
            # Short wait for commit/DOM, letting the user watch the load live in noVNC
            await page.goto(target_url, timeout=45_000, wait_until="commit")
        except Exception as ex:
            _log(f"Navigation notice: {ex}", emit)

    asyncio.create_task(_initial_navigation())

    # Background task to monitor for login completion directly inside the browser
    async def _auto_save_watcher():
        while _state.get("active"):
            try:
                p = _state.get("page")
                ctx = _state.get("context")
                if p and ctx:
                    u = p.url
                    # User completed login if on web.snapchat.com and not on accounts/login page
                    if "web.snapchat.com" in u and "accounts.snapchat.com" not in u and "/login" not in u:
                        cookies = await ctx.cookies()
                        c_names = {c.get("name") for c in cookies}
                        if any(k in c_names for k in ["sc-a-nonce", "sc-session", "web_client_id"]) or len(cookies) >= 5:
                            storage = await ctx.storage_state()
                            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                            SESSION_FILE.write_text(json.dumps(storage, indent=2), encoding="utf-8")
                            _log("✓ Detected successful Snapchat login inside emulated browser! Session saved.", emit)
                            if emit:
                                emit("LOGIN_AUTO_SAVED")
                            break
            except Exception:
                pass
            await asyncio.sleep(3)

    asyncio.create_task(_auto_save_watcher())

    _log("✓ Browser ready — live stream active.", emit)
    return "ok"


async def click_google_login() -> dict:
    """Click Continue with Google / Sign in with Google button."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    google_selectors = [
        'button:has-text("Google")',
        '[aria-label*="Google" i]',
        'button:has([data-testid*="google" i])',
        'a:has-text("Google")',
        'div[role="button"]:has-text("Google")',
    ]
    for sel in google_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.scroll_into_view_if_needed()
                await btn.click(delay=80)
                _log("  ✓ Clicked Continue with Google button.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue
    return {"ok": False, "error": "Google button not found on this page"}






async def click(x: int, y: int):
    """Forward a click at (x, y) to the browser with realistic mouse move and click."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 1200
        _macro["last_time"] = now
        _macro["events"].append({"type": "click", "x": x, "y": y, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        try:
            await page.mouse.move(x, y)
            await asyncio.sleep(0.04)
            await page.mouse.click(x, y, delay=50)
            await asyncio.sleep(0.2)
        except Exception:
            pass


async def fill_field(field: str, value: str) -> dict:
    """Smart field focus, clear, and input with full React property descriptor synchronization."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    selectors_map = {
        "username": [
            "input#accountIdentifier",
            "input[name='accountIdentifier']",
            "input[autocomplete='username']",
            "input[name='username']",
            "input[type='email']",
            "input[placeholder*='Username' i]",
            "input[placeholder*='Email' i]",
            "input[type='text']",
        ],
        "password": [
            "input#password",
            "input[name='password']",
            "input[autocomplete='current-password']",
            "input[type='password']",
            "input[placeholder*='Password' i]",
        ],
        "code": [
            "input[name='code']",
            "input[name='verificationCode']",
            "input[inputmode='numeric']",
            "input[type='number']",
            "input[maxlength='6']",
            "input[placeholder*='code' i]",
            "input[type='text']",
        ],
    }

    selectors = selectors_map.get(field.lower(), ["input[type='text']", "input"])

    # 1. Try finding input via selectors and filling properly
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.click()
                await asyncio.sleep(0.05)
                # Playwright's native fill() handles focus, clear, and input dispatch
                await loc.fill(value)
                # React 16+ controlled input synchronization fallback
                await page.evaluate("""
                    ([selector, val]) => {
                        const el = document.querySelector(selector);
                        if (el) {
                            el.focus();
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                            if (setter) {
                                setter.call(el, val);
                            } else {
                                el.value = val;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                        }
                    }
                """, [sel, value])
                _log(f"  ✓ Quick filled {field} into '{sel}'.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    # 2. Fallback: Type directly into active focused element with React sync
    try:
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(value, delay=40)
        await page.evaluate("""
            (val) => {
                const el = document.activeElement;
                if (el && el.tagName === 'INPUT') {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                }
            }
        """, value)
        _log(f"  ✓ Typed {field} directly into active focused element.")
        return {"ok": True, "fallback": "active_element"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


async def click_submit() -> dict:
    """Click primary submit / Next / Log In button with accurate click event."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No active browser session"}

    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Next')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        "input[type='submit']",
        "[data-testid='submit-button']",
    ]
    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.scroll_into_view_if_needed()
                await btn.click(delay=80)
                _log(f"  ✓ Clicked submit button '{sel}'.")
                return {"ok": True, "selector": sel}
        except Exception:
            continue

    # Fallback: Press Enter key
    try:
        await page.keyboard.press("Enter")
        _log("  ✓ Pressed Enter for submission.")
        return {"ok": True, "fallback": "Enter"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}



async def type_text(text: str):
    """Type text into the browser."""

    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 800
        _macro["last_time"] = now
        _macro["events"].append({"type": "type", "text": text, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        await page.keyboard.type(text, delay=60)


async def key_press(key: str):
    """Press a special key (Enter, Tab, Backspace, Escape...)."""
    if _macro["recording"]:
        now = time.time()
        delay = int((now - _macro["last_time"]) * 1000) if _macro["last_time"] else 800
        _macro["last_time"] = now
        _macro["events"].append({"type": "key", "key": key, "delay_ms": delay})

    page: Page | None = _state["page"]
    if page:
        await page.keyboard.press(key)


async def navigate(url: str) -> dict:
    """Navigate the browser to a URL (supports query searches or full URLs)."""
    page: Page | None = _state["page"]
    if not page:
        return {"ok": False, "error": "No browser active"}
    url = url.strip()
    if not url:
        url = "https://web.snapchat.com/"
    elif not url.startswith(("http://", "https://", "about:")):
        if "." in url and " " not in url:
            url = "https://" + url
        else:
            import urllib.parse
            url = f"https://www.google.com/search?q={urllib.parse.quote(url)}"
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        _state["url"] = page.url
        return {"ok": True, "url": page.url}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


async def go_back() -> dict:
    """Navigate back in browser history."""
    page: Page | None = _state["page"]
    if page:
        try:
            await page.go_back(timeout=10_000)
            _state["url"] = page.url
            return {"ok": True, "url": page.url}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
    return {"ok": False, "error": "No browser active"}


async def go_forward() -> dict:
    """Navigate forward in browser history."""
    page: Page | None = _state["page"]
    if page:
        try:
            await page.go_forward(timeout=10_000)
            _state["url"] = page.url
            return {"ok": True, "url": page.url}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
    return {"ok": False, "error": "No browser active"}


async def reload_page() -> dict:
    """Reload the active webpage."""
    page: Page | None = _state["page"]
    if page:
        try:
            await page.reload(timeout=15_000)
            _state["url"] = page.url
            return {"ok": True, "url": page.url}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
    return {"ok": False, "error": "No browser active"}


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
    """Execute streak sequence directly inside the currently visible interactive browser."""
    if not _state["active"] or not _state["page"]:
        return {"error": "Browser not active"}

    from automation import MACRO_FILE, replay_macro, send_streaks_flow, ensure_snap_image
    import config
    ensure_snap_image()
    page = _state["page"]

    cfg = config.load()
    if not friends:
        friends = cfg.get("friends") or ["*//Eric\\\\*", "Dylan"]
    selection_method = cfg.get("selection_method", "auto")

    if MACRO_FILE.exists():
        _log("Replaying custom recorded macro in active browser...", emit)
        results = await replay_macro(page, emit=emit)
    else:
        _log(f"Starting auto send streak sequence in active browser (Targets: {friends})...", emit)
        results = await send_streaks_flow(page, friends=friends, selection_method=selection_method, emit=emit)
    return results




async def save(emit: Callable | None = None) -> str:
    if not _state["active"]:
        return "No active session."
    _log("Saving session...", emit)
    try:
        storage = await _state["context"].storage_state()
        SESSION_FILE.write_text(__import__("json").dumps(storage), encoding="utf-8")
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

