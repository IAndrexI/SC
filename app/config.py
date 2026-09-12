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
    "schedule_time": "09:00",              # HH:MM daily send time (24h)
    "enabled": True,                       # whether auto-send is active
    "snap_image_custom": False,            # whether a custom image has been uploaded
    "mode": "web",                         # "web" (Browser) or "bliss" (Android VM)
    "selection_method": "auto",            # "auto" (shortcut + fallback), "direct" (search/click friends), or "shortcut"
    "step_delay": 4,                       # seconds between automation verification steps
    "bliss_host": "127.0.0.1",
    "bliss_port": 5555,
}


def load() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Merge with defaults for any missing keys
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
