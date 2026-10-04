import os
import sys
from pathlib import Path

# Ensure paths are set
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "desktop_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(DATA_DIR)

sys.path.insert(0, str(SCRIPT_DIR / "app"))

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  Snapchat Streak Bot - Mini Server Dashboard")
    print(f"  Access UI at: http://localhost:8080")
    print(f"  Data folder:  {DATA_DIR}")
    print("=" * 60)
    uvicorn.run("main:app", host="127.0.0.1", port=8080, log_level="info")
