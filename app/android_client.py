"""
ADB client for interacting with the Android container (ReDroid / Waydroid).
Handles screen capture streaming, input events, and app lifecycle.
"""
import asyncio
import base64
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

ADB_HOST = os.environ.get("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.environ.get("ADB_PORT", "5555"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

_state = {
    "connected": False,
    "streaming": False,
    "last_frame_b64": "",
    "device_width": 720,
    "device_height": 1280,
}


async def connect_adb(emit: Callable[[str], None] | None = None) -> bool:
    """Connect to the Android container over ADB."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "connect", f"{ADB_HOST}:{ADB_PORT}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        out_str = stdout.decode(errors="ignore")
        if "connected to" in out_str.lower() or "already connected" in out_str.lower():
            _state["connected"] = True
            if emit:
                emit(f"✓ Connected to Android container at {ADB_HOST}:{ADB_PORT}")
            return True
    except Exception as ex:
        if emit:
            emit(f"⚠ ADB connect notice: {ex}")
    
    _state["connected"] = False
    return False


def is_connected() -> bool:
    return _state["connected"]


async def screencap_bytes() -> bytes:
    """Capture raw PNG/JPEG screenshot from Android."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", f"{ADB_HOST}:{ADB_PORT}", "exec-out", "screencap", "-p",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        return stdout
    except Exception:
        return b""


async def tap(x: int, y: int):
    """Tap at screen coordinates (x, y)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", f"{ADB_HOST}:{ADB_PORT}", "shell", "input", "tap", str(x), str(y),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
    except Exception:
        pass


async def type_text(text: str):
    """Type text into focused Android field."""
    try:
        safe_text = text.replace(" ", "%s").replace("&", "\&").replace("'", "\\'")
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", f"{ADB_HOST}:{ADB_PORT}", "shell", "input", "text", safe_text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
    except Exception:
        pass


async def key_event(key_code: int | str):
    """Send Android keyevent (e.g. 3 for HOME, 4 for BACK, 66 for ENTER)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", f"{ADB_HOST}:{ADB_PORT}", "shell", "input", "keyevent", str(key_code),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
    except Exception:
        pass


async def launch_snapchat():
    """Launch the Snapchat app on Android."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", f"{ADB_HOST}:{ADB_PORT}", "shell", "monkey", "-p", "com.snapchat.android", "-c", "android.intent.category.LAUNCHER", "1",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
    except Exception:
        pass


async def start_screen_stream(emit: Callable[[str], None] | None = None):
    """Continuously broadcast Android screen frames over WebSocket."""
    _state["streaming"] = True
    while _state["streaming"]:
        try:
            if not _state["connected"]:
                await connect_adb(emit)
                if not _state["connected"]:
                    await asyncio.sleep(2)
                    continue

            frame = await screencap_bytes()
            if frame and len(frame) > 1000:
                frame_b64 = base64.b64encode(frame).decode("ascii")
                _state["last_frame_b64"] = frame_b64
                if emit:
                    import json
                    emit(json.dumps({
                        "type": "screencast",
                        "image": frame_b64,
                        "platform": "android"
                    }))
        except Exception:
            pass
        await asyncio.sleep(0.15)  # ~7-10 FPS smooth live screen
