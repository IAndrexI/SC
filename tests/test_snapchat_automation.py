"""
test_snapchat_automation.py
End-to-end simulation test of SnapStreak Extension & Automation methods.
Runs real Chromium/Edge via Playwright against a simulated Snapchat Web DOM.
"""

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright

EXT_DIR = Path(__file__).resolve().parent.parent / "linux-server" / "extension"

MOCK_SNAPCHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Snapchat Web Simulation</title>
  <style>
    body { margin: 0; padding: 0; background: #000; color: #fff; font-family: sans-serif; display: flex; height: 100vh; overflow: hidden; }
    #sidebar { width: 320px; background: #121212; border-right: 1px solid #222; display: flex; flex-direction: column; }
    .chat-row { padding: 12px; border-bottom: 1px solid #1a1a1a; display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
    .chat-row .name { font-weight: bold; font-size: 14px; }
    .chat-row .status { font-size: 12px; color: #888; }
    #main-camera-container { flex: 1; position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #181818; }
    #camera-viewfinder { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; }
    .shutter-btn { width: 70px; height: 70px; border-radius: 50%; border: 4px solid #fff; background: transparent; cursor: pointer; margin-top: auto; margin-bottom: 40px; }
    #photo-preview { display: none; width: 100%; height: 100%; position: relative; background: #2a2a2a; }
    .send-to-btn { position: absolute; bottom: 40px; right: 40px; background: #0fadff; color: #fff; padding: 12px 24px; border-radius: 24px; border: none; font-weight: bold; cursor: pointer; }
    #send-drawer { display: none; position: absolute; bottom: 0; left: 0; right: 0; height: 500px; background: #1a1a1a; border-top-left-radius: 16px; border-top-right-radius: 16px; padding: 20px; box-sizing: border-box; }
    .tab-pills { display: flex; gap: 8px; margin-bottom: 12px; }
    .tab-pill { background: #333; color: #fff; border: none; border-radius: 16px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
    .recipient-list { height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
    .recipient-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #222; border-radius: 8px; }
    .final-send-btn { position: absolute; bottom: 20px; right: 20px; width: 50px; height: 50px; border-radius: 50%; background: #0fadff; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; }
    .final-send-btn svg { width: 24px; height: 24px; fill: #fff; }
  </style>
</head>
<body>
  <div id="sidebar">
    <div style="padding: 16px; border-bottom: 1px solid #222; font-weight: bold;">Chats</div>
    <div class="chat-row" role="row" id="chat-my-ai">
      <div>
        <div class="name">My AI</div>
        <div class="status" id="status-my-ai">Say hi!</div>
      </div>
    </div>
    <div class="chat-row" role="row" id="chat-eric">
      <div>
        <div class="name">*//Eric\\*</div>
        <div class="status" id="status-eric">Tap to chat</div>
      </div>
    </div>
    <div class="chat-row" role="row" id="chat-dylan">
      <div>
        <div class="name">Dylan</div>
        <div class="status" id="status-dylan">Tap to chat</div>
      </div>
    </div>
  </div>

  <div id="main-camera-container">
    <div id="camera-viewfinder">
      <div style="color: #666; margin-bottom: 20px;">Camera Viewfinder Active</div>
      <button class="shutter-btn" id="btn-shutter" aria-label="Take a Snap"></button>
    </div>

    <div id="photo-preview">
      <div style="padding: 20px;">Photo Captured Preview</div>
      <button class="send-to-btn" id="btn-send-to" aria-label="Send To">Send To</button>
    </div>

    <div id="send-drawer" data-testid="send-drawer">
      <div style="font-weight: bold; margin-bottom: 10px;">Send To</div>
      <input type="text" id="drawer-search" placeholder="Send To..." style="width: 90%; padding: 8px; margin-bottom: 10px; background: #333; color: #fff; border: 1px solid #444; border-radius: 8px;" />
      
      <div class="tab-pills">
        <button class="tab-pill" id="pill-shortcut" aria-label="Shortcut ✨">✨ Streak Squad</button>
        <button class="tab-pill" id="pill-best-friends" aria-label="Best Friends">Best Friends</button>
      </div>

      <div class="recipient-list" id="recipient-list">
        <!-- My AI MUST NEVER BE CHECKED -->
        <div class="recipient-row" role="row" data-name="My AI">
          <span>My AI</span>
          <input type="checkbox" id="check-my-ai" role="checkbox" />
        </div>
        <div class="recipient-row" role="row" data-name="*//Eric\\*">
          <span>*//Eric\\*</span>
          <input type="checkbox" id="check-eric" role="checkbox" />
        </div>
        <div class="recipient-row" role="row" data-name="Dylan">
          <span>Dylan</span>
          <input type="checkbox" id="check-dylan" role="checkbox" />
        </div>
      </div>

      <button class="final-send-btn" id="btn-final-send" aria-label="Send Snap" data-testid="send-snap">
        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
      </button>
    </div>
  </div>

  <script>
    // State logic for mock Snapchat Web UI
    const shutter = document.getElementById('btn-shutter');
    const viewfinder = document.getElementById('camera-viewfinder');
    const preview = document.getElementById('photo-preview');
    const sendToBtn = document.getElementById('btn-send-to');
    const drawer = document.getElementById('send-drawer');
    const finalSendBtn = document.getElementById('btn-final-send');
    const searchInput = document.getElementById('drawer-search');
    const shortcutPill = document.getElementById('pill-shortcut');

    shutter.onclick = () => {
      viewfinder.style.display = 'none';
      preview.style.display = 'block';
    };

    sendToBtn.onclick = () => {
      drawer.style.display = 'block';
    };

    shortcutPill.onclick = () => {
      document.getElementById('check-eric').checked = true;
      document.getElementById('check-dylan').checked = true;
    };

    searchInput.oninput = (e) => {
      const q = e.target.value.toLowerCase().trim();
      document.querySelectorAll('.recipient-row').forEach(row => {
        const name = row.getAttribute('data-name').toLowerCase();
        if (!q || name.includes(q)) {
          row.style.display = 'flex';
        } else {
          row.style.display = 'none';
        }
      });
    };

    finalSendBtn.onclick = () => {
      drawer.style.display = 'none';
      preview.style.display = 'none';
      viewfinder.style.display = 'flex';

      // Update delivery in sidebar
      if (document.getElementById('check-eric').checked) {
        document.getElementById('status-eric').textContent = 'Delivered just now';
      }
      if (document.getElementById('check-dylan').checked) {
        document.getElementById('status-dylan').textContent = 'Delivered just now';
      }
    };
  </script>
</body>
</html>
"""

def assemble_bundle() -> str:
    parts = []
    for script_name in ["camera_hook.js", "automation.js", "macro.js", "overlay.js", "content.js"]:
        f = EXT_DIR / script_name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


async def run_test():
    print("=" * 60)
    print("🚀 STARTING E2E EXTENSION AUTOMATION TEST")
    print("=" * 60)

    bundle = assemble_bundle()
    print(f"Loaded extension bundle: {len(bundle)} bytes from {EXT_DIR}")

    async with async_playwright() as p:
        # Launch Chromium (using system Edge or Chromium)
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Intercept https://web.snapchat.com so the browser runs with real Snapchat URL & origin
        await page.route("https://web.snapchat.com/**", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=MOCK_SNAPCHAT_HTML
        ))
        page.on("console", lambda msg: print(f"[Browser Console {msg.type}] {msg.text}"))
        page.on("framenavigated", lambda frame: print(f"[Navigated] {frame.url}"))
        page.on("pageerror", lambda err: print(f"[Page Error] {err}"))

        await page.goto("https://web.snapchat.com/")
        print("✓ Mock https://web.snapchat.com/ loaded.")

        # Inject the extension bundle
        await page.evaluate(bundle)
        print("✓ Extension bundle evaluated in page DOM.")

        # Verify extension objects exist
        ext_check = await page.evaluate("""() => ({
            hasAutomation: Boolean(window.SnapStreakAutomation),
            hasOverlay: Boolean(window.SnapStreakOverlay),
            hasMacro: Boolean(window.SnapStreakMacro),
            hasHost: Boolean(document.getElementById('snapstreak-shadow-host'))
        })""")
        print("Extension status:", ext_check)
        assert ext_check["hasAutomation"], "window.SnapStreakAutomation missing!"
        assert ext_check["hasOverlay"], "window.SnapStreakOverlay missing!"
        assert ext_check["hasHost"], "Shadow host not attached!"

        # TEST 1: Direct Send Flow with Recipient Selection
        print("\n--- TEST 1: Direct Send Flow with Recipient Selection ---")
        friends = ["*//Eric\\\\*", "Dylan"]
        res1 = await page.evaluate("""async (friends) => {
            return await window.SnapStreakAutomation.runSendStreaks({
                friends: friends,
                selectionMethod: 'auto',
                humanMode: false,
                isTest: false,
                stepDelay: 0.1,
                maxRetries: 3
            });
        }""", friends)
        print("Test 1 Result:", res1)

        ai_checked = await page.evaluate("() => document.getElementById('check-my-ai').checked")
        eric_checked = await page.evaluate("() => document.getElementById('check-eric').checked")
        dylan_checked = await page.evaluate("() => document.getElementById('check-dylan').checked")
        eric_status = await page.evaluate("() => document.getElementById('status-eric').textContent")
        dylan_status = await page.evaluate("() => document.getElementById('status-dylan').textContent")

        assert not ai_checked, "CRITICAL ERROR: My AI was checked!"
        assert eric_checked, "Eric was not checked!"
        assert dylan_checked, "Dylan was not checked!"
        assert "Delivered" in eric_status, "Eric delivery status not updated!"
        assert "Delivered" in dylan_status, "Dylan delivery status not updated!"
        assert res1.get("success"), f"Streak sequence failed: {res1.get('error')}"
        print("✓ TEST 1 PASSED: Direct selection verified delivered to all specified users!")

        # TEST 2: Shortcut Selection Method
        print("\n--- TEST 2: Shortcut Selection Method ---")
        # Reset UI
        await page.evaluate("""() => {
            document.getElementById('check-eric').checked = false;
            document.getElementById('check-dylan').checked = false;
            document.getElementById('status-eric').textContent = 'Tap to chat';
            document.getElementById('status-dylan').textContent = 'Tap to chat';
        }""")

        res2 = await page.evaluate("""async () => {
            return await window.SnapStreakAutomation.runSendStreaks({
                friends: ['Dylan'],
                selectionMethod: 'shortcut',
                humanMode: false,
                isTest: false,
                stepDelay: 0.1,
                maxRetries: 2
            });
        }""")
        print("Test 2 Result:", res2)
        assert res2.get("success"), f"Shortcut streak sequence failed: {res2.get('error')}"
        dylan_status = await page.evaluate("() => document.getElementById('status-dylan').textContent")
        assert "Delivered" in dylan_status, "Dylan delivery not verified in shortcut mode!"
        print("✓ TEST 2 PASSED: Shortcut mode verified delivered!")

        # TEST 3: Sample Preview Mode (pauses before send, confirms on approval)
        print("\n--- TEST 3: Sample Preview Mode ---")
        # Start preview task asynchronously in page
        await page.evaluate("""async () => {
            window.__previewPromise = window.SnapStreakAutomation.runSendStreaks({
                friends: ['*//Eric\\\\*'],
                selectionMethod: 'auto',
                humanMode: false,
                isTest: true,
                stepDelay: 0.1
            });
        }""")

        # Wait for sample preview modal to appear
        await page.wait_for_selector("#snapstreak-sample-confirm-modal", timeout=15000)
        print("✓ Sample preview confirmation modal appeared on screen.")

        # Click confirm button to approve and dispatch
        await page.click("#snapstreak-btn-confirm-send")
        preview_res = await page.evaluate("() => window.__previewPromise")
        print("Preview Result:", preview_res)
        assert preview_res.get("success"), "Sample preview confirmation failed!"
        print("✓ TEST 3 PASSED: Sample preview paused and dispatched successfully on approval!")

        print("\n🎉 ALL 3 TEST SUITES PASSED FLAWLESSLY! 🔥")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_test())
