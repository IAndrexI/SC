# -*- coding: utf-8 -*-
"""
run_server.py - Starts the SnapStreak Studio Web Server on http://localhost:8080
Preserves all saved login cookies in linux-server/desktop_data and streams the SJSU webcam.
"""

import os
import sys
from pathlib import Path
import uvicorn

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APP_DIR = REPO_ROOT / "linux-server" / "app"
DATA_DIR = REPO_ROOT / "linux-server" / "desktop_data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(DATA_DIR)
sys.path.insert(0, str(APP_DIR))

if __name__ == "__main__":
    print("=" * 64)
    print(" SnapStreak Studio Server — http://localhost:8080")
    print(f" Cookie Vault & Data Directory: {DATA_DIR}")
    print("=" * 64)
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
