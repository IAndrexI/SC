"""
config.py – persistent settings stored in /data/config.json
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
CONFIG_FILE = DATA_DIR / "config.json"

_DEFAULTS = {
    "friends": [],           # list of Snapchat usernames
    "schedule_time": "09:00", # HH:MM daily send time (24h)
    "enabled": True,          # whether auto-send is active
    "snap_image_custom": False, # whether a custom image has been uploaded
    "mode": "bliss",          # "bliss" (Android VM) or "web" (Browser)
    "bliss_host": "127.0.0.1",# IP of Bliss OS VM
    "bliss_port": 5555,       # ADB TCP port (default 5555)
}


def load() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            # Merge with defaults for any missing keys
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
