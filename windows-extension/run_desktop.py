# -*- coding: utf-8 -*-
"""
run_desktop.py - Direct Desktop Runner for SnapStreak on Windows.
Launches persistent Chromium/Edge with saved login cookies, SJSU Meteorology live webcam,
and runs either AI / Expected Steps Mode or Custom Macro Mode.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APP_DIR = REPO_ROOT / "linux-server" / "app"
DATA_DIR = REPO_ROOT / "linux-server" / "desktop_data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["SNAPSTREAK_HEADED"] = "1"
sys.path.insert(0, str(APP_DIR))

import config
import automation
import login_session


async def main():
    parser = argparse.ArgumentParser(description="SnapStreak Desktop Runner")
    parser.add_argument("--mode", choices=["ai_steps", "macro"], default=None, help="Execution mode: ai_steps or macro")
    parser.add_argument("--method", choices=["direct", "shortcut", "auto"], default=None, help="Recipient selection method")
    parser.add_argument("--preview", action="store_true", help="Pause right before clicking final Send")
    parser.add_argument("--keep-open", action="store_true", help="Keep browser open after sending streaks")
    args = parser.parse_args()

    cfg = config.load()
    streak_mode = args.mode or cfg.get("streak_mode", "ai_steps")
    selection_method = args.method or cfg.get("selection_method", "direct")
    friends = cfg.get("friends", ["*//Eric\\\\*", "Dylan"])

    print("=" * 64)
    print(" SnapStreak Desktop Runner — SJSU Live Webcam & Cookie Vault")
    print("=" * 64)
    print(f" • Streak Mode:      {streak_mode}")
    print(f" • Selection Method: {selection_method}")
    print(f" • Target Friends:   {', '.join(friends)}")
    print(f" • Cookie Vault:     {config.get_cookie_vault_summary()}")
    print("=" * 64)

    await login_session.start(emit=print)
    await asyncio.sleep(3.0)

    results = await login_session.run_streak_in_active_session(
        friends=friends,
        emit=print,
        selection_method=selection_method,
        streak_mode=streak_mode,
        preview_only=args.preview,
    )
    print("\n" + "=" * 64)
    print(f" Execution Results: {results}")
    print("=" * 64)

    if args.keep_open or args.preview:
        print("\nBrowser kept open. Press Ctrl+C when finished.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

    await login_session.cancel()


if __name__ == "__main__":
    asyncio.run(main())
