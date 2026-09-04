# -*- coding: utf-8 -*-
"""
run_desktop.py - Snapchat Streak Bot Desktop Runner for Windows
Runs directly on your Windows PC using your local Chrome/Chromium.
Zero datacenter IP blocks, zero server captcha issues.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Set up local data directory
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "desktop_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(DATA_DIR)

# Add app to path
sys.path.insert(0, str(SCRIPT_DIR / "app"))

import automation
import config

async def main():
    print("=" * 60)
    print(" Snapchat Streak Bot - Desktop Runner (Windows)")
    print("=" * 60)
    
    cfg = config.load()
    friends = cfg.get("friends", ["*//Eric\\\\*", "Dylan"])
    print(f"Target friends: {friends}")
    print(f"Webcam source:  {automation.WEBCAM_URL}")
    print("\nFetching latest SJSU meteorology webcam frame...")
    automation.fetch_webcam_image(force_refresh=True)
    
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        print("\nLaunching browser with local persistent profile...")
        context = await automation._build_context(pw, headless=False)
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Checking Snapchat login status...")
        logged_in = await automation.check_logged_in(page)
        
        if not logged_in:
            print("\n" + "!" * 60)
            print(" PLEASE LOG IN TO SNAPCHAT IN THE OPEN BROWSER WINDOW.")
            print(" Once logged in and on the main chat/camera screen, return here.")
            print("!" * 60 + "\n")
            
            while not logged_in:
                ans = input("Are you logged in now? [y/n/exit]: ").strip().lower()
                if ans == "exit":
                    await context.close()
                    return
                if ans == "y":
                    logged_in = await automation.check_logged_in(page)
                    if logged_in:
                        print("✓ Login verified! Saving profile session...")
                        await automation._save_session(context)
                        break
                    else:
                        print("✗ Not detected on web.snapchat.com yet. Please finish logging in.")
        
        print("\nStarting automated 6-step streak send flow...")
        results = await automation.send_streaks_shortcut_flow(page, emit=print)
        print("\n" + "=" * 60)
        print(f"Streak Send Complete! Results: {results}")
        print("=" * 60)
        
        print("Closing browser in 5 seconds...")
        await asyncio.sleep(5)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
