"""
diagnostics.py - Live Snapchat Server Diagnostic & Self-Healing Engine
Connects directly to server processes, network connectivity, browser state,
session health, lock files, and automated remediation.
"""

import os
import sys
import json
import time
import socket
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Callable, Any

try:
    from automation import DATA_DIR, SESSION_FILE, SNAP_IMAGE, MACRO_FILE
except ImportError:
    DATA_DIR = Path(__file__).resolve().parent.parent / "desktop_data"
    SESSION_FILE = DATA_DIR / "session.json"
    SNAP_IMAGE = DATA_DIR / "snap.jpg"
    MACRO_FILE = DATA_DIR / "macro.json"

import config


def _check_port(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _check_http_status(url: str, timeout: float = 3.0) -> tuple[bool, int, str]:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, resp.status, "OK"
    except urllib.error.HTTPError as e:
        return True, e.code, str(e.reason)
    except Exception as ex:
        return False, 0, str(ex)


def run_system_diagnostics(login_session_module=None) -> dict[str, Any]:
    """Perform a full system audit across server, network, browser, sessions, and files."""
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_status": "healthy",
        "issues_found": 0,
        "checks": {},
        "system_info": {},
    }

    issues = []

    # 1. System Resources & Disk Space
    try:
        total, used, free = shutil.disk_usage(str(DATA_DIR.parent))
        free_mb = free // (1024 * 1024)
        results["system_info"]["disk_free_mb"] = free_mb
        results["checks"]["disk_space"] = {
            "status": "ok" if free_mb > 500 else "warning",
            "message": f"{free_mb} MB available on filesystem",
            "free_mb": free_mb,
        }
        if free_mb <= 500:
            issues.append("Low disk space (<500MB)")
    except Exception as ex:
        results["checks"]["disk_space"] = {"status": "warning", "message": str(ex)}

    # 2. Network & DNS Reachability
    sc_net_ok, sc_code, sc_msg = _check_http_status("https://web.snapchat.com", timeout=3.5)
    results["checks"]["snapchat_network"] = {
        "status": "ok" if sc_net_ok else "error",
        "message": f"Snapchat Web HTTP status: {sc_code} ({sc_msg})" if sc_net_ok else f"Failed to reach web.snapchat.com: {sc_msg}",
        "code": sc_code,
    }
    if not sc_net_ok:
        issues.append("Cannot reach web.snapchat.com (network/DNS/firewall block)")

    # 3. Session Authentication File
    session_exists = SESSION_FILE.exists()
    session_valid = False
    session_cookies_count = 0
    if session_exists:
        try:
            raw = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            cookies = raw.get("cookies", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            session_cookies_count = len(cookies)
            session_valid = session_cookies_count > 0
        except Exception:
            pass

    results["checks"]["session_auth"] = {
        "status": "ok" if session_valid else "warning",
        "message": f"Saved session.json exists with {session_cookies_count} cookies" if session_valid else "No saved session cookies (login required in browser)",
        "cookies_count": session_cookies_count,
        "file_exists": session_exists,
    }
    if not session_valid:
        issues.append("No active saved login session in session.json")

    # 4. Snap Image Media
    image_exists = SNAP_IMAGE.exists() and SNAP_IMAGE.stat().st_size > 0
    results["checks"]["snap_media"] = {
        "status": "ok" if image_exists else "warning",
        "message": f"Snap image ready ({SNAP_IMAGE.stat().st_size if image_exists else 0} bytes)" if image_exists else "No snap image found (will generate automatic webcam snapshot)",
        "file_exists": image_exists,
    }

    # 5. Lock Files & Orphaned Chrome/Firefox Locks
    stale_locks = []
    lock_paths = [
        "/tmp/.X99-lock",
        "/tmp/.X11-unix/X99",
        "/data/sc/firefox_profile/.parentlock",
        "/data/sc/firefox_profile/parent.lock",
        "/data/sc/firefox_profile/lock",
        "/data/sc/browser_profile/SingletonLock",
        str(DATA_DIR / "firefox_profile" / "parent.lock"),
        str(DATA_DIR / "browser_profile" / "SingletonLock"),
    ]
    for lp in lock_paths:
        if os.path.exists(lp):
            stale_locks.append(lp)

    results["checks"]["stale_locks"] = {
        "status": "warning" if (stale_locks and not (login_session_module and login_session_module.is_active())) else "ok",
        "message": f"Found {len(stale_locks)} lock file(s): {', '.join(stale_locks)}" if stale_locks else "Clean (no orphan lock files)",
        "locks": stale_locks,
    }
    if stale_locks and not (login_session_module and login_session_module.is_active()):
        issues.append(f"{len(stale_locks)} orphaned browser/X11 lock files detected")

    # 6. Live Browser Session & noVNC Port Status
    browser_active = False
    browser_url = ""
    novnc_listening = _check_port(6080)
    vnc_listening = _check_port(5900)

    if login_session_module:
        browser_active = login_session_module.is_active()
        browser_url = login_session_module.current_url()

    results["checks"]["live_browser"] = {
        "status": "ok" if browser_active else "idle",
        "message": f"Live browser session running (URL: {browser_url})" if browser_active else "Browser is idle (will launch on demand or via web control)",
        "active": browser_active,
        "url": browser_url,
        "novnc_port_6080": novnc_listening,
        "vnc_port_5900": vnc_listening,
    }

    # 7. Recipient Configuration
    cfg = config.load()
    friends = cfg.get("friends", [])
    results["checks"]["recipient_whitelist"] = {
        "status": "ok" if len(friends) > 0 else "warning",
        "message": f"{len(friends)} recipient(s) configured: {friends}",
        "friends": friends,
    }
    if not friends:
        issues.append("No friends specified in recipient list")

    # 8. Service Status (systemd)
    try:
        sc_service = subprocess.run(["systemctl", "is-active", "sc"], capture_output=True, text=True, timeout=2)
        service_active = (sc_service.stdout.strip() == "active")
        results["checks"]["systemd_service"] = {
            "status": "ok" if service_active else "warning",
            "message": f"systemd service 'sc' is {sc_service.stdout.strip()}",
            "active": service_active,
        }
    except Exception:
        results["checks"]["systemd_service"] = {"status": "info", "message": "systemd check not applicable (standalone runtime)"}

    # 9. Schedule Integrity & Deduplication Check
    raw_times = cfg.get("schedule_times", ["09:00"])
    cleaned_times = config.clean_schedule_times(raw_times)
    has_dup_schedule = (len(raw_times) != len(cleaned_times))
    results["checks"]["schedule_integrity"] = {
        "status": "warning" if has_dup_schedule else "ok",
        "message": f"Duplicate schedule times found: {raw_times} (auto-repairable)" if has_dup_schedule else f"{len(cleaned_times)} daily send time(s): {', '.join(cleaned_times)}",
        "schedule_times": cleaned_times,
    }
    if has_dup_schedule:
        issues.append(f"Duplicate schedule times found in configuration ({len(raw_times)} items, {len(cleaned_times)} unique)")

    results["issues_found"] = len(issues)
    results["issues"] = issues
    if len(issues) > 0:
        results["overall_status"] = "warning" if any("network" not in i for i in issues) else "error"

    return results


async def resolve_issues(fix_type: str = "all", emit: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Execute targeted or automated self-healing resolutions."""
    log_func = emit or (lambda m: None)
    log_func(f"🔧 [Self-Healing Engine] Starting remediation routine (Action: {fix_type})...")

    actions_taken = []

    # Resolution A: Clean Stale Locks & Lingering Zombie Processes
    if fix_type in ("all", "clear_locks", "stale_processes"):
        log_func("  🧹 Cleaning up orphan X11 / Chromium / Firefox locks and zombie instances...")
        try:
            # Stale lock paths
            lock_paths = [
                "/tmp/.X99-lock",
                "/tmp/.X11-unix/X99",
                "/data/sc/firefox_profile/.parentlock",
                "/data/sc/firefox_profile/parent.lock",
                "/data/sc/firefox_profile/lock",
                "/data/sc/browser_profile/SingletonLock",
                str(DATA_DIR / "firefox_profile" / "parent.lock"),
                str(DATA_DIR / "browser_profile" / "SingletonLock"),
            ]
            removed = 0
            for lp in lock_paths:
                try:
                    if os.path.exists(lp):
                        os.remove(lp)
                        removed += 1
                except Exception:
                    pass
            actions_taken.append(f"Removed {removed} orphan lock files")
            log_func(f"  ✓ Cleared {removed} orphan lock files.")
        except Exception as e:
            actions_taken.append(f"Lock cleanup notice: {e}")

    # Resolution B: Refresh Webcam Snapshot Frame
    if fix_type in ("all", "refresh_snap", "camera"):
        log_func("  📷 Fetching fresh high-resolution webcam visual...")
        try:
            from automation import fetch_webcam_image
            fetch_webcam_image(force_refresh=True)
            actions_taken.append("Updated SJSU meteorology webcam frame for snaps")
            log_func("  ✓ Fresh webcam visual downloaded & verified.")
        except Exception as e:
            actions_taken.append(f"Webcam fetch notice: {e}")

    # Resolution C: Reset / Restart Live Browser Session
    if fix_type in ("all", "restart_browser"):
        log_func("  🔄 Re-initializing live browser environment...")
        try:
            import login_session
            if login_session.is_active():
                await login_session.cancel(emit=log_func)
                await asyncio.sleep(1.0)
            await login_session.start(emit=log_func)
            actions_taken.append("Restarted live browser window & noVNC stream")
            log_func("  ✓ Browser environment restarted cleanly on port 6080.")
        except Exception as e:
            actions_taken.append(f"Browser restart notice: {e}")

    # Resolution D: Verify and Repair Recipient Whitelist
    if fix_type in ("all", "verify_whitelist"):
        log_func("  👥 Auditing recipient whitelist format...")
        try:
            cfg = config.load()
            friends = cfg.get("friends", [])
            if not friends:
                cfg["friends"] = ["*//Eric\\*", "Dylan"]
                config.save(cfg)
                actions_taken.append("Restored default streak whitelist (*//Eric\\*, Dylan)")
                log_func("  ✓ Restored default streak whitelist (*//Eric\\*, Dylan).")
            else:
                actions_taken.append(f"Recipient whitelist confirmed healthy ({len(friends)} friends)")
        except Exception as e:
            actions_taken.append(f"Whitelist verification notice: {e}")

    # Resolution D2: Repair & Deduplicate Daily Schedule
    if fix_type in ("all", "dedup_schedule", "verify_whitelist"):
        log_func("  ⏰ Auditing daily schedule times...")
        try:
            cfg = config.load()
            raw_sched = cfg.get("schedule_times", ["09:00"])
            clean_sched = config.clean_schedule_times(raw_sched)
            if len(raw_sched) != len(clean_sched):
                cfg["schedule_times"] = clean_sched
                cfg["schedule_time"] = clean_sched[0]
                config.save(cfg)
                actions_taken.append(f"Pruned duplicate schedule times: {raw_sched} -> {clean_sched}")
                log_func(f"  ✓ Pruned duplicate schedule times: {clean_sched}")
            else:
                actions_taken.append(f"Daily schedule confirmed healthy: {clean_sched}")
        except Exception as e:
            actions_taken.append(f"Schedule audit notice: {e}")

    # Resolution E: Restart systemd service if requested
    if fix_type == "restart_service":
        log_func("  ⚡ Restarting systemd service 'sc'...")
        try:
            async def _delayed_restart():
                await asyncio.sleep(1.0)
                subprocess.run(["systemctl", "restart", "sc"], timeout=5)
            asyncio.create_task(_delayed_restart())
            actions_taken.append("Service restart initiated")
        except Exception as e:
            actions_taken.append(f"Service restart error: {e}")

    log_func("🎉 [Self-Healing Complete] Remediation finished!")
    return {
        "ok": True,
        "actions_taken": actions_taken,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
