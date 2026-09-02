"""
adb_automation.py – Snapchat streak automation via ADB + uiautomator2
Targets the real Snapchat Android app running inside Waydroid.
"""

import asyncio
import base64
import io
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

DATA_DIR   = Path(os.environ.get("DATA_DIR", "/data"))
LOG_FILE   = DATA_DIR / "activity.log"
WEBCAM_URL = os.environ.get("WEBCAM_URL", "https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg")

SNAP_PKG   = "com.snapchat.android"
ADB_HOST   = os.environ.get("WAYDROID_ADB_HOST", "192.168.240.112:5555")

_device = None   # uiautomator2 device handle


def _log(msg: str, emit: Callable | None = None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if emit:
        emit(line)


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------
def adb(*args, timeout=30) -> str:
    """Run an adb command and return stdout."""
    cmd = ["adb", "-s", ADB_HOST] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def adb_tap(x: int, y: int):
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(0.4)


def adb_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))
    time.sleep(0.5)


def adb_key(keycode: str):
    adb("shell", "input", "keyevent", keycode)
    time.sleep(0.3)


def adb_screenshot_b64() -> str:
    """Return a base64 JPEG screenshot of the Waydroid display."""
    raw = subprocess.run(
        ["adb", "-s", ADB_HOST, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=10
    ).stdout
    if not raw:
        return ""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((900, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return base64.b64encode(raw).decode()


def is_adb_connected() -> bool:
    try:
        out = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        ).stdout
        return ADB_HOST in out
    except Exception:
        return False


def connect_adb() -> bool:
    """Ensure ADB is connected to Waydroid."""
    if is_adb_connected():
        return True
    subprocess.run(["adb", "connect", ADB_HOST], capture_output=True, timeout=10)
    time.sleep(2)
    return is_adb_connected()


# ---------------------------------------------------------------------------
# Snapchat app control
# ---------------------------------------------------------------------------
def launch_snapchat(emit=None):
    _log("Launching Snapchat...", emit)
    adb("shell", "am", "start", "-n", f"{SNAP_PKG}/.LandingPageActivity")
    time.sleep(4)


def go_home_screen(emit=None):
    """Tap the camera/home button in Snapchat."""
    _log("Going to Snapchat home (camera)...", emit)
    adb_key("KEYCODE_HOME")
    time.sleep(1)
    adb("shell", "am", "start", "-n", f"{SNAP_PKG}/.LandingPageActivity")
    time.sleep(3)


def fetch_webcam_snap(emit=None) -> Path:
    """Download the SJSU webcam image to /data/snap.png."""
    import urllib.request
    snap_path = DATA_DIR / "snap.png"
    try:
        _log(f"Fetching webcam image: {WEBCAM_URL}", emit)
        req = urllib.request.Request(WEBCAM_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            snap_path.write_bytes(r.read())
        _log("Webcam image saved.", emit)
    except Exception as e:
        _log(f"Webcam fetch failed: {e} — using existing snap if available", emit)
    return snap_path


def push_snap_image(emit=None):
    """Push the snap image to the Android device gallery."""
    snap_path = fetch_webcam_snap(emit)
    if not snap_path.exists():
        _log("No snap image available.", emit)
        return False
    remote = "/sdcard/Pictures/snap_send.png"
    adb("push", str(snap_path), remote)
    # Trigger media scan so gallery picks it up
    adb("shell", "am", "broadcast",
        "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d", f"file://{remote}")
    time.sleep(1)
    _log(f"Snap image pushed to device: {remote}", emit)
    return remote


# ---------------------------------------------------------------------------
# Streak send flow via uiautomator2
# ---------------------------------------------------------------------------
async def send_streaks_adb(friends: list[str], emit: Callable | None = None):
    """
    Full streak send flow using uiautomator2 UI automation.
    friends: list of Snapchat display names e.g. ['*//Eric\\\\*', 'Dylan']
    """
    results = {}

    if not connect_adb():
        _log("ERROR: ADB not connected to Waydroid. Is waydroid running?", emit)
        return {"error": "ADB not connected"}

    try:
        import uiautomator2 as u2
    except ImportError:
        _log("uiautomator2 not installed. Run: pip3 install uiautomator2", emit)
        return {"error": "uiautomator2 not installed"}

    _log("Connecting uiautomator2...", emit)
    d = u2.connect(ADB_HOST)
    d.implicitly_wait(8)

    # Push webcam image to device
    remote_img = push_snap_image(emit)

    # Launch Snapchat
    launch_snapchat(emit)
    await asyncio.sleep(4)

    for friend in friends:
        _log(f"Sending streak to: {friend}", emit)
        try:
            # 1. Go to chat/search for friend
            _log(f"  Searching for {friend}...", emit)
            # Tap search icon (top-left magnifier in Snapchat)
            d(description="Search").click()
            await asyncio.sleep(1)

            # Type friend name
            d.send_keys(friend, clear=True)
            await asyncio.sleep(2)

            # Tap first result
            results_list = d(resourceId=f"{SNAP_PKG}:id/search_result_item")
            if results_list.count > 0:
                results_list[0].click()
            else:
                # Fallback: tap first list item
                d(className="android.widget.ListView").child(index=0).click()
            await asyncio.sleep(1)

            # 2. Tap camera icon to go to camera for this friend (or send snap via chat)
            # Look for the camera icon in chat
            cam_btn = d(description="Camera") or d(resourceId=f"{SNAP_PKG}:id/camera_button")
            if cam_btn.exists:
                cam_btn.click()
                await asyncio.sleep(2)

            # 3. Take photo (tap shutter)
            shutter = d(resourceId=f"{SNAP_PKG}:id/capture_button") or d(description="Take a photo")
            if shutter.exists:
                shutter.click()
                await asyncio.sleep(2)
            else:
                # Fallback: tap center of screen (camera shutter position)
                info_size = d.window_size()
                w, h = info_size
                adb_tap(w // 2, int(h * 0.8))
                await asyncio.sleep(2)

            # 4. Send to friend (tap Send button)
            send_btn = d(text="Send") or d(description="Send") or d(resourceId=f"{SNAP_PKG}:id/send_button")
            if send_btn.exists:
                send_btn.click()
                await asyncio.sleep(1)

            results[friend] = "sent"
            _log(f"  ? Streak sent to {friend}", emit)

        except Exception as ex:
            results[friend] = f"error: {ex}"
            _log(f"  ? Failed for {friend}: {ex}", emit)

        # 30-second delay between each friend
        if friend != friends[-1]:
            _log("Waiting 30s before next streak...", emit)
            await asyncio.sleep(30)

    _log(f"Streak run complete: {results}", emit)
    return results


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def waydroid_status() -> dict:
    try:
        out = subprocess.run(
            ["waydroid", "status"], capture_output=True, text=True, timeout=5
        ).stdout
        running = "RUNNING" in out
    except Exception:
        running = False

    adb_ok = is_adb_connected()
    snap_installed = False
    if adb_ok:
        try:
            snap_installed = SNAP_PKG in adb("shell", "pm", "list", "packages")
        except Exception:
            pass

    return {
        "waydroid_running": running,
        "adb_connected": adb_ok,
        "snapchat_installed": snap_installed,
        "adb_host": ADB_HOST,
    }
