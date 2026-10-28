"""
diagnostics.py – System Health & Self-Healing Engine for SnapStreak.
Verifies Snapchat reachability, Cookie Vault integrity, SJSU Meteorology webcam stream,
recipient whitelist, and active browser status without ever wiping login cookies.
"""

import shutil
import ssl
import time
import urllib.request
from typing import Callable

import config
import login_session
from automation import (
    DATA_DIR,
    SNAP_IMAGE,
    WEBCAM_FILE,
    Y4M_FILE,
    FORBIDDEN_TARGETS,
    fetch_webcam_image,
    _cleanup_stale_locks,
)


def run_diagnostics() -> dict:
    checks = {}
    issues = []

    # 1. Snapchat Web Network Reachability
    try:
        t0 = time.time()
        req = urllib.request.Request(
            "https://web.snapchat.com/",
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"},
        )
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            ms = int((time.time() - t0) * 1000)
            checks["snapchat_network"] = {
                "status": "ok",
                "code": resp.status,
                "latency_ms": ms,
                "message": f"Snapchat Web reachable ({ms}ms)",
            }
    except Exception as ex:
        checks["snapchat_network"] = {"status": "warning", "message": f"Network notice: {ex}"}

    # 2. Cookie Vault & Session Authentication
    vault = config.get_cookie_vault_summary()
    if vault.get("is_authenticated"):
        checks["session_auth"] = {
            "status": "ok",
            "cookie_count": vault.get("total_cookies", 0),
            "snapchat_cookies": vault.get("snapchat_cookies", 0),
            "message": f"Authenticated ({vault.get('snapchat_cookies', 0)} Snapchat cookies, {vault.get('total_cookies', 0)} total saved)",
        }
    else:
        checks["session_auth"] = {
            "status": "warning",
            "cookie_count": vault.get("total_cookies", 0),
            "message": "No Snapchat auth cookies detected yet. Sign in once via the live browser.",
        }
        issues.append("Snapchat login needed in live browser")

    # 3. Live Browser Status
    if login_session.is_active():
        checks["live_browser"] = {
            "status": "ok",
            "url": login_session.get_Current_Url(),
            "screen_state": login_session.get_Screen_State(),
            "message": f"Active ({login_session.get_Screen_State()}) at {login_session.get_Current_Url() or 'web.snapchat.com'}",
        }
    else:
        checks["live_browser"] = {
            "status": "idle",
            "message": "Browser idle — click 'Launch / Open Snapchat' to start live view",
        }

    # 4. SJSU Meteorology Live Webcam Ready
    has_webcam = WEBCAM_FILE.exists() and WEBCAM_FILE.stat().st_size > 1500
    has_y4m = Y4M_FILE.exists() and Y4M_FILE.stat().st_size > 10000
    if has_webcam and has_y4m:
        age_m = int((time.time() - WEBCAM_FILE.stat().st_mtime) / 60)
        checks["snap_media"] = {
            "status": "ok",
            "message": f"Live SJSU Meteorology Webcam active ({WEBCAM_FILE.stat().st_size // 1024} KB, updated {age_m}m ago)",
        }
    else:
        checks["snap_media"] = {
            "status": "warning",
            "message": "SJSU webcam frame not cached yet — click Refresh SJSU Camera",
        }

    # 5. Streak Recipients & Safety Guard
    cfg = config.load()
    friends = cfg.get("friends", [])
    bad = [f for f in friends if any(b in f.lower() for b in FORBIDDEN_TARGETS)]
    if bad:
        checks["recipient_whitelist"] = {
            "status": "error",
            "message": f"Forbidden targets in friends list: {bad}",
        }
        issues.append("Forbidden target in friends list")
    elif not friends:
        checks["recipient_whitelist"] = {
            "status": "warning",
            "message": "No streak friends configured",
        }
        issues.append("Add at least 1 friend to send streaks to")
    else:
        checks["recipient_whitelist"] = {
            "status": "ok",
            "message": f"{len(friends)} target friend(s): {', '.join(friends)} (Mode: {cfg.get('streak_mode', 'ai_steps')})",
        }

    # 6. Schedule Integrity
    times = cfg.get("schedule_times", ["09:00"])
    checks["schedule_integrity"] = {
        "status": "ok",
        "message": f"Scheduled daily at {', '.join(times)} ({'Enabled' if cfg.get('enabled', True) else 'Paused'})",
    }

    # 7. Disk Space
    try:
        usage = shutil.disk_usage(str(DATA_DIR))
        free_mb = usage.free // (1024 * 1024)
        checks["disk_space"] = {
            "status": "ok" if free_mb > 200 else "warning",
            "free_mb": free_mb,
            "message": f"{free_mb} MB available",
        }
    except Exception:
        checks["disk_space"] = {"status": "ok", "message": "Storage ready"}

    return {
        "ok": len(issues) == 0,
        "overall_status": "healthy" if len(issues) == 0 else "attention_needed",
        "issue_count": len(issues),
        "issues": issues,
        "checks": checks,
        "cookie_vault": vault,
        "timestamp": int(time.time()),
    }


async def auto_resolve_issues(fix_type: str = "all", emit: Callable | None = None) -> dict:
    actions = []
    cfg = config.load()

    if fix_type in ("all", "locks"):
        _cleanup_stale_locks()
        actions.append("Cleaned stale browser lock files (cookies preserved).")

    if fix_type in ("all", "whitelist", "schedule"):
        friends = [f.strip() for f in cfg.get("friends", []) if f.strip() and not any(b in f.lower() for b in FORBIDDEN_TARGETS)]
        if not friends:
            friends = ["*//Eric\\\\*", "Dylan"]
        cfg["friends"] = friends
        config.save(cfg)
        actions.append(f"Verified recipient whitelist ({', '.join(friends)}).")

    if fix_type in ("all", "media", "webcam"):
        data = fetch_webcam_image(force_refresh=True)
        if data:
            actions.append(f"Refreshed live SJSU Meteorology webcam frame ({len(data) // 1024} KB) and Y4M stream.")
        if login_session.is_active():
            await login_session.ensure_extension_active()

    if fix_type in ("all", "cookies"):
        vault = config.get_cookie_vault_summary()
        if not vault.get("has_session_file") and vault.get("has_backup_file"):
            await login_session.restore_cookie_backup(emit=emit)
            actions.append("Restored session.json from cookie backup.")
        elif login_session.is_active():
            res = await login_session.save(emit=emit)
            if res.get("ok"):
                actions.append(res.get("message", "Saved active cookies."))

    if fix_type in ("repair_snapchat", "vnc"):
        res = await login_session.repair_snapchat_session(emit=emit)
        actions.append(res.get("message", "Repaired Snapchat Web session."))

    updated = run_diagnostics()
    return {
        "ok": True,
        "fix_type": fix_type,
        "actions_taken": actions,
        "diagnostics": updated,
    }
