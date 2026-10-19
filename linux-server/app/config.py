"""
config.py – persistent settings stored in /data/config.json
"""

import json
import os
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "desktop_data"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR)))
CONFIG_FILE = DATA_DIR / "config.json"

_DEFAULTS = {
    "friends": ["*//Eric\\\\*", "Dylan"],  # list of Snapchat usernames/names
    "schedule_time": "09:00",              # HH:MM daily send time (backward compatibility)
    "schedule_times": ["09:00"],           # list of HH:MM daily send times
    "enabled": True,                       # whether auto-send is active
    "snap_image_custom": False,            # whether a custom image has been uploaded
    "mode": "web",                         # "web" (Browser) or "bliss" (Android VM)
    "browser_engine": "chromium",          # "chromium" (loads SnapStreak extension) or "firefox"
    "browser_autostart": True,             # automatically keep emulated browser active in background
    "selection_method": "auto",            # "auto" (shortcut + fallback), "direct" (search/click friends), or "shortcut"
    "step_delay": 4,                       # seconds between automation verification steps
    "bliss_host": "127.0.0.1",
    "bliss_port": 5555,
}


def clean_schedule_times(raw_times) -> list[str]:
    """Deduplicate and sanitize schedule times while preserving entry order."""
    if isinstance(raw_times, str):
        raw_times = [raw_times]
    elif not isinstance(raw_times, (list, tuple)):
        return ["09:00"]

    seen = set()
    cleaned = []
    for t in raw_times:
        if not t:
            continue
        s = str(t).strip()
        if not s:
            continue
        # Normalize HH:MM format
        parts = s.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            if 0 <= h < 24 and 0 <= m < 60:
                normalized = f"{h:02d}:{m:02d}"
                if normalized not in seen:
                    seen.add(normalized)
                    cleaned.append(normalized)
        except Exception:
            pass

    return cleaned if cleaned else ["09:00"]


def load() -> dict:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            merged = {**_DEFAULTS, **data}
            # Synchronize and deduplicate schedule_times and legacy schedule_time
            if "schedule_times" in data and isinstance(data["schedule_times"], list) and len(data["schedule_times"]) > 0:
                merged["schedule_times"] = clean_schedule_times(data["schedule_times"])
                merged["schedule_time"] = merged["schedule_times"][0]
            elif "schedule_time" in data and data["schedule_time"]:
                merged["schedule_times"] = clean_schedule_times([data["schedule_time"]])
                merged["schedule_time"] = merged["schedule_times"][0]
            else:
                merged["schedule_times"] = clean_schedule_times(merged.get("schedule_times"))
                merged["schedule_time"] = merged["schedule_times"][0]
            return merged
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if "schedule_times" in cfg:
            cfg["schedule_times"] = clean_schedule_times(cfg["schedule_times"])
            if cfg["schedule_times"]:
                cfg["schedule_time"] = cfg["schedule_times"][0]
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass
