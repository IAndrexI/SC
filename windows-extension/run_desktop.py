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
        # Detect best available browser
        brave_candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
            Path(r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
        brave_exe = next((p for p in brave_candidates if p.is_file()), None)

        edge_candidates = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
        edge_exe = next((p for p in edge_candidates if p.is_file()), None)

        profile_dir = DATA_DIR / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--enable-webgl",
            "--enable-webgl2",
        ]
        y4m_file = DATA_DIR / "webcam.y4m"
        if y4m_file.exists():
            args.append(f"--use-file-for-fake-video-capture={y4m_file.resolve()}")

        launch_kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "user_agent": automation.USER_AGENT,
            "viewport": {"width": 1440, "height": 900},
            "args": args,
            "permissions": ["camera", "microphone", "notifications"],
        }

        print("\nLaunching Chromium with Stealth mode...")
        context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        await context.add_init_script(automation.STEALTH_INIT_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        print("Checking Snapchat login status...")
        await page.goto("https://web.snapchat.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        session_file = DATA_DIR / "session.json"

        # Check if landing page shows login prompt or not authenticated
        login_btn = page.locator("text=Log in to chat, a:has-text('Log in'), button:has-text('Log in')").first
        has_login_btn = (await login_btn.count() > 0)
        needs_login = not session_file.exists() or has_login_btn or "accounts.snapchat.com" in page.url

        if needs_login:
            print("\n" + "=" * 60)
            print(" PLEASE LOG IN TO SNAPCHAT IN THE OPEN BROWSER WINDOW.")
            print(" Type your username, password, and SMS/2FA code.")
            print("=" * 60 + "\n")
            
            if "accounts/v2/login" not in page.url:
                await page.goto("https://accounts.snapchat.com/accounts/v2/login?continue=https%3A%2F%2Fweb.snapchat.com%2F")

            # Watch for successful login automatically
            print("Waiting for you to log in...")
            logged_in = False
            for _ in range(150):  # wait up to 5 minutes
                await asyncio.sleep(2)
                url = page.url
                if "web.snapchat.com" in url and "accounts" not in url:
                    btn = page.locator("text=Log in to chat").first
                    if await btn.count() == 0:
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
                session_file.write_text(json.dumps(storage, indent=2))
                print(f"✓ Saved session to {session_file}")

        selection_method = cfg.get("selection_method", "auto")
        print(f"\nStarting automated streak send flow (Selection: {selection_method.upper()}, Friends: {friends})...")
        results = await automation.send_streaks_flow(page, friends=friends, selection_method=selection_method, emit=print)
        print("\n" + "=" * 60)
        print(f"Streak Send Complete! Results: {results}")
        print("=" * 60)

        print("\nClosing browser in 5 seconds...")
        await asyncio.sleep(5)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
