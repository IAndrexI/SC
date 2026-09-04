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
    friends = cfg.get("friends") or ["*//Eric\\\\*", "Dylan"]
    print(f"Target friends: {friends}")

    print(f"Webcam source:  {automation.WEBCAM_URL}")
    print("\nFetching latest SJSU meteorology webcam frame...")
    automation.fetch_webcam_image(force_refresh=True)
    
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        print("\nLaunching official Microsoft Edge browser...")
        profile_dir = DATA_DIR / "edge_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="msedge",
            headless=False,
            viewport=None,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
            ],
            permissions=["camera", "microphone", "notifications"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("Checking Snapchat login status...")
        await page.goto("https://web.snapchat.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # If not logged in, navigate directly to login page
        if "accounts.snapchat.com" in page.url or ("snapchat.com" in page.url and "/web" not in page.url):
            print("\n" + "=" * 60)
            print(" PLEASE LOG IN TO SNAPCHAT IN THE OPEN EDGE WINDOW.")
            print(" Type your username, password, and SMS/2FA code.")
            print("=" * 60 + "\n")
            
            if "accounts/v2/login" not in page.url:
                await page.goto("https://accounts.snapchat.com/accounts/v2/login?continue=https%3A%2F%2Fweb.snapchat.com%2F")

            # Watch for successful login automatically
            print("Waiting for you to log in...")
            logged_in = False
            for _ in range(120):  # wait up to 4 minutes
                await asyncio.sleep(2)
                url = page.url
                if "web.snapchat.com" in url and "accounts" not in url:
                    logged_in = True
                    break

            if not logged_in:
                ans = input("\nAre you logged in now? [y/n]: ").strip().lower()
                if ans == "y":
                    logged_in = True

            if logged_in:
                import json
                print("\n✓ Login detected! Saving session state...")
                await asyncio.sleep(3)
                storage = await context.storage_state()
                session_file = DATA_DIR / "session.json"
                session_file.write_text(json.dumps(storage, indent=2))
                print(f"✓ Saved session to {session_file}")

        print("\nStarting automated 6-step streak send flow...")
        results = await automation.send_streaks_shortcut_flow(page, emit=print)
        print("\n" + "=" * 60)
        print(f"Streak Send Complete! Results: {results}")
        print("=" * 60)

        print("\nClosing browser in 5 seconds...")
        await asyncio.sleep(5)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
