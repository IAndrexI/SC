"""
config.py – Persistent settings, macro storage, and cookie vault paths for SnapStreak.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

APP_VERSION = "5.2.0"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_DATA_DIR = (
    Path("/data")
    if os.name != "nt" and Path("/data").exists()
    else Path(__file__).resolve().parent.parent / "desktop_data"
)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_DEFAULT_DATA_DIR)))
CONFIG_FILE = DATA_DIR / "config.json"
SESSION_FILE = DATA_DIR / "session.json"
SESSION_BACKUP_FILE = DATA_DIR / "session_backup.json"
MACRO_FILE = DATA_DIR / "macro.json"
WEBCAM_FILE = DATA_DIR / "webcam_latest.jpg"
SNAP_IMAGE = DATA_DIR / "snap.png"
Y4M_FILE = DATA_DIR / "webcam.y4m"
USER_DATA_DIR = DATA_DIR / "browser_profile"
EDGE_PROFILE_DIR = DATA_DIR / "edge_profile"
BACKUP_PROFILE_DIR = DATA_DIR / "profile_backup_authenticated"
FIREFOX_PROFILE_DIR = DATA_DIR / "firefox_profile"

WEBCAM_URL = "https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg"

_DEFAULTS = {
    "friends": ["*//Eric\\\\*", "Dylan"],  # Default streak recipients
    "schedule_time": "09:00",               # Primary HH:MM daily send time (24h)
    "schedule_times": ["09:00", "21:00"],   # Multiple daily send times (HH:MM 24h)
    "enabled": True,                        # Whether scheduled auto-send is active
    "snap_image_custom": False,             # False = Live SJSU Webcam, True = Custom uploaded image
    "webcam_source": "sjsu",                # "sjsu" | "custom" | "physical"
    "mode": "web",                          # "web" (Snapchat Web Browser)
    "browser_engine": "chromium",           # "chromium" | "msedge" | "firefox"
    "streak_mode": "ai_steps",              # "ai_steps" (AI/Expected Steps state machine) | "macro" (Recorded/Custom Macro)
    "selection_method": "direct",           # "direct" (search/click friends), "shortcut" (shortcut pill + select all), "auto" (hybrid)
    "shortcut_name": "Streaks",             # Optional name/emoji of Snapchat shortcut pill
    "step_delay_seconds": 1.5,              # Delay between expected steps / macro steps (seconds)
    "use_coordinate_delay": False,          # False = use step_delay_seconds, True = use recorded delay_ms
    "auto_save_cookies": True,              # Automatically persist cookies to session.json & backup
    "strict_safety_guard": True,            # Block My AI, My Story, Spotlight, and non-whitelisted targets
    "bliss_host": "127.0.0.1",
    "bliss_port": 5555,
    "snapchat_username": "",
    "snapchat_password": "",
}

DEFAULT_EXPECTED_MACRO_STEPS = [
    {
        "id": "step_1",
        "type": "expected_action",
        "action": "open_camera",
        "label": "Starter Step: Click Camera to Open Viewfinder ('Click the Camera to send Snaps')",
        "x": 750,
        "y": 500,
        "rx": 0.5208,
        "ry": 0.5556,
        "selector": "button[aria-label*='Camera' i], div:has-text('Click the Camera'), svg[data-icon*='camera'], video",
        "delay_ms": 1500,
    },
    {
        "id": "step_2",
        "type": "expected_action",
        "action": "capture_snap",
        "label": "Click Center Shutter Button (Take Snap)",
        "x": 750,
        "y": 797,
        "rx": 0.5208,
        "ry": 0.8856,
        "selector": "button[aria-label*='take a picture' i], button[title*='take a picture' i]",
        "delay_ms": 1800,
    },
    {
        "id": "step_3",
        "type": "expected_action",
        "action": "click_send_to",
        "label": "Click 'Send To' Button",
        "x": 556,
        "y": 877,
        "rx": 0.3861,
        "ry": 0.9744,
        "selector": "button[aria-label*='Send To' i]",
        "text": "Send To",
        "delay_ms": 1800,
    },
    {
        "id": "step_4",
        "type": "expected_action",
        "action": "select_recipients",
        "label": "Select Configured Streak Friends & Safety Audit",
        "x": 750,
        "y": 360,
        "rx": 0.5208,
        "ry": 0.4000,
        "selector": "input[placeholder*='Search' i]",
        "delay_ms": 2000,
    },
    {
        "id": "step_5",
        "type": "expected_action",
        "action": "click_final_send",
        "label": "Click Final 'Send' Button",
        "x": 750,
        "y": 865,
        "rx": 0.5208,
        "ry": 0.9611,
        "selector": "button[type='submit'], button[aria-label='Send' i]",
        "text": "Send",
        "delay_ms": 2000,
    },
]


def ensure_data_dirs():
    """Ensure DATA_DIR and browser profile directories exist without ever wiping existing cookies."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # If backup or edge_profile has cookies and browser_profile does not, migrate automatically
    cookies_in_browser = USER_DATA_DIR / "Default" / "Network" / "Cookies"
    cookies_in_edge = EDGE_PROFILE_DIR / "Default" / "Network" / "Cookies"
    cookies_in_backup = BACKUP_PROFILE_DIR / "Default" / "Network" / "Cookies"

    if not cookies_in_browser.exists():
        if cookies_in_backup.exists():
            try:
                shutil.copytree(BACKUP_PROFILE_DIR, USER_DATA_DIR, dirs_exist_ok=True)
            except Exception:
                pass
        elif cookies_in_edge.exists():
            try:
                shutil.copytree(EDGE_PROFILE_DIR, USER_DATA_DIR, dirs_exist_ok=True)
            except Exception:
                pass

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Restore session.json from session_backup.json if session.json is missing
    if not SESSION_FILE.exists() and SESSION_BACKUP_FILE.exists():
        try:
            shutil.copy2(SESSION_BACKUP_FILE, SESSION_FILE)
        except Exception:
            pass


def _deduplicate_times(times_list: list) -> list[str]:
    seen = set()
    clean = []
    for t in times_list:
        if not isinstance(t, str):
            continue
        s = t.strip()
        if ":" in s and s not in seen:
            seen.add(s)
            clean.append(s)
    return clean if clean else ["09:00"]


def load() -> dict:
    ensure_data_dirs()
    cfg = dict(_DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass

    raw_times = cfg.get("schedule_times")
    if isinstance(raw_times, list) and raw_times:
        cfg["schedule_times"] = _deduplicate_times(raw_times)
    elif cfg.get("schedule_time"):
        cfg["schedule_times"] = _deduplicate_times([cfg["schedule_time"]])
    else:
        cfg["schedule_times"] = ["09:00"]

    cfg["schedule_time"] = cfg["schedule_times"][0]

    # Normalize streak_mode ("ai_steps" | "macro")
    if cfg.get("streak_mode") not in ("ai_steps", "macro"):
        cfg["streak_mode"] = "ai_steps"

    # Normalize selection_method ("direct" | "shortcut" | "auto")
    if cfg.get("selection_method") not in ("direct", "shortcut", "auto"):
        cfg["selection_method"] = "direct"

    # Ensure friends is a non-empty list of strings
    friends = cfg.get("friends")
    if not isinstance(friends, list) or not [f for f in friends if str(f).strip()]:
        cfg["friends"] = list(_DEFAULTS["friends"])
    else:
        seen_f = set()
        clean_f = []
        for f in friends:
            s = str(f).strip()
            if s and s not in seen_f:
                seen_f.add(s)
                clean_f.append(s)
        cfg["friends"] = clean_f

    try:
        delay = float(cfg.get("step_delay_seconds", 1.5))
        # Fix legacy configs that had 30s hardcoded step delay
        if delay >= 15.0:
            delay = 1.5
        cfg["step_delay_seconds"] = max(0.3, min(15.0, delay))
    except Exception:
        cfg["step_delay_seconds"] = 1.5

    return cfg


def save(cfg: dict) -> dict:
    ensure_data_dirs()
    current = load()
    current.update(cfg)
    raw_times = current.get("schedule_times")
    if isinstance(raw_times, list) and raw_times:
        current["schedule_times"] = _deduplicate_times(raw_times)
    elif current.get("schedule_time"):
        current["schedule_times"] = _deduplicate_times([current["schedule_time"]])
    else:
        current["schedule_times"] = ["09:00"]
    current["schedule_time"] = current["schedule_times"][0]

    CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def load_macro_data() -> dict:
    """
    Load macro configuration from macro.json.
    Supports both legacy list format and structured dict format:
    {
      "active_macro": "Default Streak Flow",
      "steps": [...],
      "macros": {
         "Default Streak Flow": {"name": "Default Streak Flow", "steps": [...], "updated_at": ...}
      }
    }
    """
    ensure_data_dirs()
    if MACRO_FILE.exists():
        try:
            raw = json.loads(MACRO_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                steps = raw if raw else list(DEFAULT_EXPECTED_MACRO_STEPS)
                return {
                    "active_macro": "Custom Recorded Macro",
                    "steps": steps,
                    "macros": {
                        "Custom Recorded Macro": {
                            "name": "Custom Recorded Macro",
                            "steps": steps,
                            "updated_at": int(time.time()),
                        },
                        "Default Streak Flow": {
                            "name": "Default Streak Flow",
                            "steps": list(DEFAULT_EXPECTED_MACRO_STEPS),
                            "is_default": True,
                            "updated_at": int(time.time()),
                        },
                    },
                }
            elif isinstance(raw, dict):
                macros = raw.get("macros") or {}
                if "Default Streak Flow" not in macros:
                    macros["Default Streak Flow"] = {
                        "name": "Default Streak Flow",
                        "steps": list(DEFAULT_EXPECTED_MACRO_STEPS),
                        "is_default": True,
                        "updated_at": int(time.time()),
                    }
                active_name = raw.get("active_macro") or "Default Streak Flow"
                steps = raw.get("steps")
                if not isinstance(steps, list) or not steps:
                    if active_name in macros and isinstance(macros[active_name].get("steps"), list):
                        steps = macros[active_name]["steps"]
                    else:
                        steps = list(DEFAULT_EXPECTED_MACRO_STEPS)
                return {
                    "active_macro": active_name,
                    "steps": steps,
                    "macros": macros,
                }
        except Exception:
            pass

    default_data = {
        "active_macro": "Default Streak Flow",
        "steps": list(DEFAULT_EXPECTED_MACRO_STEPS),
        "macros": {
            "Default Streak Flow": {
                "name": "Default Streak Flow",
                "steps": list(DEFAULT_EXPECTED_MACRO_STEPS),
                "is_default": True,
                "updated_at": int(time.time()),
            }
        },
    }
    save_macro_data(default_data)
    return default_data


def save_macro_data(macro_data: dict) -> dict:
    ensure_data_dirs()
    MACRO_FILE.write_text(json.dumps(macro_data, indent=2), encoding="utf-8")
    return macro_data


def get_cookie_vault_summary() -> dict:
    """Inspect session.json and browser_profile to report cookie health without opening a browser."""
    ensure_data_dirs()
    cookies = []
    origins = []
    if SESSION_FILE.exists():
        try:
            state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                cookies = state.get("cookies", []) or []
                origins = state.get("origins", []) or []
            elif isinstance(state, list):
                cookies = state
        except Exception:
            pass

    sc_cookies = [
        c for c in cookies
        if isinstance(c, dict) and ("snapchat" in str(c.get("domain", "")).lower())
    ]
    auth_cookie_names = {
        "sc_at",
        "__Host-sc-a-auth-session",
        "__Host-X-Snap-Client-Cookie",
        "sc-a-nonce",
        "__Host-sc-a-nonce",
        "sc-a-csrf",
        "sc-a-dbsc-session",
    }
    found_auth = [c.get("name") for c in sc_cookies if c.get("name") in auth_cookie_names]
    profile_cookies_db = USER_DATA_DIR / "Default" / "Network" / "Cookies"
    has_profile_db = profile_cookies_db.exists() and profile_cookies_db.stat().st_size > 1024

    return {
        "has_session_file": SESSION_FILE.exists(),
        "has_backup_file": SESSION_BACKUP_FILE.exists(),
        "has_profile_db": has_profile_db,
        "total_cookies": len(cookies),
        "snapchat_cookies": len(sc_cookies),
        "auth_cookie_names": found_auth,
        "is_authenticated": bool(found_auth) or has_profile_db,
        "origins_count": len(origins),
        "last_saved": int(SESSION_FILE.stat().st_mtime) if SESSION_FILE.exists() else None,
    }


def get_version_info(check_remote: bool = False) -> dict:
    """Return current semantic version, git commit short SHA, branch, commit message, and remote update status."""
    commit_hash = "unknown"
    branch = "main"
    commit_msg = ""
    commit_date = ""
    remote_commit = ""
    behind_count = 0
    ahead_count = 0
    update_available = False

    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r.returncode == 0 and r.stdout.strip():
            commit_hash = r.stdout.strip()

        r_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r_branch.returncode == 0 and r_branch.stdout.strip():
            branch = r_branch.stdout.strip()

        r_msg = subprocess.run(
            ["git", "log", "-1", "--pretty=%s||%ci"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r_msg.returncode == 0 and "||" in r_msg.stdout:
            parts = r_msg.stdout.strip().split("||", 1)
            commit_msg = parts[0].strip()
            commit_date = parts[1].strip()

        if check_remote:
            subprocess.run(
                ["git", "fetch", "origin", branch],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=8,
            )
            r_rem = subprocess.run(
                ["git", "rev-parse", "--short", f"origin/{branch}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=4,
            )
            if r_rem.returncode == 0 and r_rem.stdout.strip():
                remote_commit = r_rem.stdout.strip()

            r_counts = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=4,
            )
            if r_counts.returncode == 0 and r_counts.stdout.strip():
                c_parts = r_counts.stdout.strip().split()
                if len(c_parts) == 2:
                    ahead_count = int(c_parts[0])
                    behind_count = int(c_parts[1])
                    update_available = behind_count > 0
    except Exception:
        pass

    return {
        "version": APP_VERSION,
        "display_version": f"v{APP_VERSION} ({commit_hash})",
        "commit": commit_hash,
        "branch": branch,
        "commit_message": commit_msg,
        "commit_date": commit_date,
        "remote_commit": remote_commit or commit_hash,
        "behind_count": behind_count,
        "ahead_count": ahead_count,
        "update_available": update_available,
    }


def run_git_update() -> dict:
    """
    1-Click Git Updater:
    1. Preserves all user session cookies, backups, config, and macros in memory.
    2. Fetches latest commits from GitHub (origin/main) and pulls/fast-forwards local repo.
    3. If local commits are ahead of origin/main, pushes them to origin/main as well.
    4. Restores any user data files if touched and returns the updated version & commit report.
    """
    ensure_data_dirs()
    preserved_files = {}
    for pf in (SESSION_FILE, SESSION_BACKUP_FILE, CONFIG_FILE, MACRO_FILE):
        if pf.exists():
            try:
                preserved_files[pf] = pf.read_bytes()
            except Exception:
                pass

    before = get_version_info(check_remote=False)
    old_commit = before.get("commit", "unknown")
    branch = before.get("branch", "main") or "main"
    logs = []

    try:
        # 1. Fetch latest from origin
        r_fetch = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r_fetch.stdout.strip():
            logs.append(r_fetch.stdout.strip())
        if r_fetch.stderr.strip():
            logs.append(r_fetch.stderr.strip())

        # 2. Check ahead/behind counts
        ahead_count, behind_count = 0, 0
        r_counts = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r_counts.returncode == 0 and r_counts.stdout.strip():
            parts = r_counts.stdout.strip().split()
            if len(parts) == 2:
                ahead_count, behind_count = int(parts[0]), int(parts[1])

        # 3. Pull latest changes from origin/main
        if behind_count > 0 or ahead_count == 0:
            r_pull = subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", branch],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=20,
            )
            logs.append((r_pull.stdout or "") + (r_pull.stderr or ""))
            if r_pull.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=str(REPO_ROOT), capture_output=True, timeout=5)
                r_reset = subprocess.run(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logs.append((r_reset.stdout or "") + (r_reset.stderr or ""))

        # 4. If local branch has new commits ahead of origin, push to origin
        if ahead_count > 0:
            r_push = subprocess.run(
                ["git", "push", "origin", branch],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=20,
            )
            logs.append((r_push.stdout or "") + (r_push.stderr or ""))

    except Exception as ex:
        logs.append(f"Git command notice: {ex}")
    finally:
        # 5. Always guarantee preserved cookies & config remain intact
        for pf, raw_bytes in preserved_files.items():
            if not pf.exists() or pf.stat().st_size == 0:
                try:
                    pf.parent.mkdir(parents=True, exist_ok=True)
                    pf.write_bytes(raw_bytes)
                except Exception:
                    pass

    after = get_version_info(check_remote=False)
    new_commit = after.get("commit", "unknown")
    updated = old_commit != new_commit
    clean_log = "\n".join([line.strip() for line in logs if line and line.strip()])

    return {
        "ok": True,
        "updated": updated,
        "old_commit": old_commit,
        "new_commit": new_commit,
        "version": after.get("version", APP_VERSION),
        "display_version": after.get("display_version"),
        "commit_message": after.get("commit_message", ""),
        "commit_date": after.get("commit_date", ""),
        "branch": branch,
        "output": clean_log or "Already up to date with origin/main.",
        "message": (
            f"Updated website from #{old_commit} to #{new_commit} ({after.get('display_version')})!"
            if updated
            else f"Website is up to date on {after.get('display_version')} — reloaded live code & extension bundle."
        ),
    }
