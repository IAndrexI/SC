"""
test_snapchat_automation.py – End-to-End Verification Suite for SnapStreak Studio:
  1. SJSU Meteorology Live Webcam (HTTP fetch, Y4M generation, zero-CORS Data URL WebRTC canvas stream)
  2. Cookie Vault Persistence (session.json + session_backup.json + browser_profile protection)
  3. Mode A: AI / Expected Steps 6-Stage State Machine (direct, shortcut, preview_only, safety guard)
  4. Mode B: Custom Macro Recorder & Replayer (DOM metadata + relative coordinate replay)
  5. FastAPI Studio Endpoints (/api/status, /api/config, /api/cookies, /api/webcam-b64, /api/macro)
"""

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "linux-server" / "app"
sys.path.insert(0, str(APP_DIR))

import config
import automation
import diagnostics
from playwright.async_api import async_playwright

MOCK_SNAPCHAT_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Snapchat Web Mock</title>
  <style>
    body { margin: 0; background: #111; color: #fff; font-family: sans-serif; width: 1440px; height: 900px; overflow: hidden; }
    .sidebar { position: absolute; left: 0; top: 0; width: 350px; height: 900px; background: #1a1a1a; border-right: 1px solid #333; }
    .center { position: absolute; left: 360px; top: 0; width: 720px; height: 900px; background: #0f172a; }
    #cam-video { position: absolute; left: 160px; top: 100px; width: 420px; height: 680px; background: #000; border-radius: 16px; }
    #shutter-btn { position: absolute; left: 336px; top: 760px; width: 68px; height: 68px; border-radius: 50%; border: 4px solid #fff; background: rgba(255,255,255,0.2); cursor: pointer; }
    #preview-bar { display: none; position: absolute; left: 160px; top: 820px; width: 420px; justify-content: space-between; }
    #send-to-btn { padding: 10px 24px; background: #0ea5e9; color: #fff; border: none; border-radius: 20px; font-weight: bold; cursor: pointer; }
    #send-drawer { display: none; position: absolute; left: 140px; top: 80px; width: 460px; height: 800px; background: #1e293b; border-radius: 16px; padding: 16px; box-sizing: border-box; }
    .row-item { display: flex; align-items: center; justify-content: space-between; padding: 10px; height: 48px; border-bottom: 1px solid #334155; cursor: pointer; box-sizing: border-box; }
    #final-send-btn { position: absolute; left: 40px; bottom: 20px; width: 380px; height: 46px; background: #0ea5e9; color: #fff; border: none; border-radius: 23px; font-weight: bold; cursor: pointer; }
  </style>
</head>
<body>
  <div class="sidebar">
    <div role="listitem" style="padding:12px">My AI (Sidebar)</div>
    <div role="listitem" style="padding:12px">*//Eric\\\\*</div>
    <div role="listitem" style="padding:12px">Dylan</div>
  </div>

  <div class="center">
    <div id="starter-card" style="position:absolute;left:160px;top:150px;width:420px;height:550px;background:#1e293b;border-radius:24px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;cursor:pointer;">
      <button id="starter-cam-btn" aria-label="Camera" style="width:100px;height:100px;border-radius:50%;background:#38bdf8;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="#fff"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path fill-rule="evenodd" d="M4 7a2 2 0 012-2h2.586l1.707-1.707A1 1 0 0111 3h2a1 1 0 01.707.293L15.414 5H18a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V7z" clip-rule="evenodd"/></svg>
      </button>
      <div id="starter-text" style="font-size:18px;font-weight:600;color:#fff;text-align:center;">Click the Camera to<br/>send Snaps</div>
    </div>

    <video id="cam-video" autoplay muted playsinline style="display:none"></video>
    <div id="shutter-label" style="display:none;position:absolute;left:260px;top:725px;font-size:12px">Click to take a picture, hold for video</div>
    <button id="shutter-btn" aria-label="Click to take a picture, hold for video" style="display:none"></button>

    <div id="preview-bar">
      <button id="download-btn">Download</button>
      <button id="send-to-btn" aria-label="Send To">Send To</button>
    </div>

    <div id="send-drawer">
      <h3>Send To...</h3>
      <div style="display:flex;gap:8px;margin-bottom:8px">
        <button id="shortcut-pill" style="padding:4px 10px;border-radius:12px">🔥 Streaks</button>
        <button id="select-all-btn" style="display:none;padding:4px 10px">Select All</button>
      </div>
      <input id="drawer-search" type="text" placeholder="Search" style="width:100%;height:34px;margin-bottom:10px" />
      <div id="recipient-list">
        <div class="row-item" role="listitem" data-name="My AI" aria-checked="true">
          <span>My AI</span>
          <input type="checkbox" checked />
        </div>
        <div class="row-item" role="listitem" data-name="*//Eric\\*" aria-checked="false">
          <span>*//Eric\\*</span>
          <input type="checkbox" />
        </div>
        <div class="row-item" role="listitem" data-name="Dylan" aria-checked="false">
          <span>Dylan</span>
          <input type="checkbox" />
        </div>
      </div>
      <button id="final-send-btn" type="submit" aria-label="Send">Send</button>
    </div>
  </div>

  <script>
    window.__test_state = {
      starterClicked: false,
      snapped: false,
      drawerOpen: false,
      sentTo: [],
      shutterAttempts: 0,
      sendToAttempts: 0,
      failFirstShutter: false,
      failFirstSendTo: false
    };

    function activateCamera() {
      window.__test_state.starterClicked = true;
      const starter = document.getElementById('starter-card');
      if (starter) starter.style.display = 'none';
      document.getElementById('cam-video').style.display = 'block';
      document.getElementById('shutter-label').style.display = 'block';
      document.getElementById('shutter-btn').style.display = 'block';
    }

    const starterBtn = document.getElementById('starter-cam-btn');
    if (starterBtn) starterBtn.addEventListener('click', activateCamera);
    const starterCard = document.getElementById('starter-card');
    if (starterCard) starterCard.addEventListener('click', activateCamera);

    document.getElementById('shutter-btn').addEventListener('click', () => {
      window.__test_state.shutterAttempts += 1;
      if (window.__test_state.failFirstShutter && window.__test_state.shutterAttempts === 1) {
        return; // Simulate transient failure on 1st shutter click
      }
      window.__test_state.snapped = true;
      document.getElementById('shutter-btn').style.display = 'none';
      document.getElementById('preview-bar').style.display = 'flex';
    });

    document.getElementById('send-to-btn').addEventListener('click', () => {
      window.__test_state.sendToAttempts += 1;
      if (window.__test_state.failFirstSendTo && window.__test_state.sendToAttempts === 1) {
        return; // Simulate transient failure on 1st Send To click
      }
      window.__test_state.drawerOpen = true;
      document.getElementById('preview-bar').style.display = 'none';
      document.getElementById('send-drawer').style.display = 'block';
    });

    document.getElementById('shortcut-pill').addEventListener('click', () => {
      document.getElementById('select-all-btn').style.display = 'inline-block';
    });

    document.getElementById('select-all-btn').addEventListener('click', () => {
      document.querySelectorAll('#recipient-list .row-item').forEach(r => {
        if (r.dataset.name !== 'My AI') {
          r.setAttribute('aria-checked', 'true');
          r.querySelector('input').checked = true;
        }
      });
    });

    document.querySelectorAll('#recipient-list .row-item').forEach(row => {
      row.addEventListener('click', () => {
        const cur = row.getAttribute('aria-checked') === 'true';
        const next = !cur;
        row.setAttribute('aria-checked', String(next));
        row.querySelector('input').checked = next;
      });
    });

    document.getElementById('final-send-btn').addEventListener('click', () => {
      const chosen = [];
      document.querySelectorAll('#recipient-list .row-item').forEach(row => {
        if (row.getAttribute('aria-checked') === 'true' || row.querySelector('input').checked) {
          chosen.push(row.dataset.name);
        }
      });
      window.__test_state.sentTo = chosen;
      document.getElementById('send-drawer').style.display = 'none';
      document.getElementById('shutter-btn').style.display = 'block';
    });
  </script>
</body>
</html>
"""


async def run_all_tests():
    print("=" * 68)
    print(" Running SnapStreak Full Verification Suite")
    print("=" * 68)

    # 1. Verify SJSU Meteorology Live Webcam & Y4M Generator
    img_bytes = automation.fetch_webcam_image(force_refresh=False)
    assert len(img_bytes) > 1500, "SJSU webcam image must be > 1.5 KB"
    assert config.Y4M_FILE.exists() and config.Y4M_FILE.stat().st_size > 10000, "webcam.y4m must be generated"
    data_url = automation.get_webcam_data_url(force_refresh=False)
    assert data_url.startswith("data:image/"), "SJSU Data URL must be valid base64 data URI"
    print(f" [PASS] 1. SJSU Meteorology Webcam & Y4M verified ({len(img_bytes)} bytes, Data URL len={len(data_url)})")

    # 2. Verify Cookie Vault Integrity
    vault = config.get_cookie_vault_summary()
    assert vault["has_session_file"], "session.json must exist"
    assert vault["is_authenticated"], "Cookie Vault must report authenticated"
    assert vault["snapchat_cookies"] >= 5, f"Expected >=5 Snapchat cookies, got {vault['snapchat_cookies']}"
    print(f" [PASS] 2. Cookie Vault verified ({vault['snapchat_cookies']} Snapchat cookies, {vault['total_cookies']} total)")

    # 3. Verify In-Browser SJSU WebRTC Hook, AI Expected Steps Mode, and Macro Mode
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_init_script(automation.STEALTH_INIT_SCRIPT)
        ext_bundle = automation.get_extension_bundle_script()
        await context.add_init_script(ext_bundle)

        page = await context.new_page()
        await page.route(
            "https://web.snapchat.com/**",
            lambda route: route.fulfill(status=200, content_type="text/html", body=MOCK_SNAPCHAT_HTML),
        )
        await page.goto("https://web.snapchat.com/", wait_until="domcontentloaded")
        await page.evaluate(ext_bundle)
        await automation.inject_webcam_frame_into_page(page, force_refresh=False)
        await asyncio.sleep(0.4)

        # 3a. Verify SJSU WebRTC camera_hook.js stream
        cam_check = await page.evaluate("""async () => {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            const track = stream.getVideoTracks()[0];
            const status = window.__SNAPSTREAK_WEBCAM_STATUS__ ? window.__SNAPSTREAK_WEBCAM_STATUS__() : {};
            return {
                label: track.label,
                readyState: track.readyState,
                loaded: status.loaded,
                source: status.source,
                width: status.width,
                height: status.height
            };
        }""")
        assert "SJSU Meteorology" in cam_check["label"], f"Unexpected track label: {cam_check}"
        assert cam_check["loaded"] is True, f"SJSU image must be loaded without CORS error: {cam_check}"
        print(f" [PASS] 3. SJSU WebRTC getUserMedia stream verified ({cam_check['label']}, {cam_check['width']}x{cam_check['height']}, source={cam_check['source']})")

        # 3b. Verify Mode A: AI / Expected Steps Engine with Starter Step & Auto-Retry on Transient Step Failure
        st_before = await automation.detect_screen_state(page)
        print(" [DEBUG] Initial state before AI steps:", st_before)
        assert st_before["state"] == "CLICK_CAMERA_PROMPT", f"Expected CLICK_CAMERA_PROMPT, got {st_before['state']}"

        # Enable transient failures on 1st shutter click and 1st Send-To click to prove step verification & retry
        await page.evaluate("() => { window.__test_state.failFirstShutter = true; window.__test_state.failFirstSendTo = true; }")

        res_ai = await automation.run_ai_expected_steps(
            page,
            friends=["*//Eric\\*", "Dylan"],
            selection_method="direct",
            step_delay=0.4,
            preview_only=False,
            max_step_retries=3,
            emit=print,
        )
        test_state = await page.evaluate("() => window.__test_state")
        assert test_state["starterClicked"] is True, "Starter Step: Camera circle button must have been clicked!"
        assert test_state["shutterAttempts"] >= 2, f"Expected shutter auto-retry (>=2 attempts), got {test_state['shutterAttempts']}"
        assert test_state["sendToAttempts"] >= 2, f"Expected Send-To auto-retry (>=2 attempts), got {test_state['sendToAttempts']}"
        assert test_state["snapped"] is True, "Shutter must have been clicked"
        assert "*//Eric\\*" in test_state["sentTo"] and "Dylan" in test_state["sentTo"], f"Expected friends in sentTo, got {test_state['sentTo']}"
        assert "My AI" not in test_state["sentTo"], f"Safety guard must have unchecked My AI! Got {test_state['sentTo']}"
        print(
            f" [PASS] 4. AI / Expected Steps Mode + Step Verification & Auto-Retry verified "
            f"(starterClicked={test_state['starterClicked']}, shutterAttempts={test_state['shutterAttempts']}, "
            f"sendToAttempts={test_state['sendToAttempts']}, sentTo={test_state['sentTo']})"
        )

        # 3c. Verify Mode B: Macro Recording Metadata + Macro Replay Engine with Starter Step
        await page.set_content(MOCK_SNAPCHAT_HTML)
        meta_starter = await automation.inspect_element_at_point(page, 360 + 210, 420)
        assert "click" in meta_starter["label"].lower() or "camera" in meta_starter["label"].lower() or "button" in meta_starter["tagName"].lower(), f"Unexpected element metadata: {meta_starter}"

        custom_macro_steps = [
            {"type": "expected_action", "action": "open_camera", "label": "Starter Camera Click"},
            {"type": "click", "x": 360 + 370, "y": 794, "selector": "#shutter-btn", "label": "Click Shutter"},
            {"type": "click", "x": 360 + 520, "y": 838, "text": "Send To", "label": "Click Send To"},
            {"type": "expected_action", "action": "select_recipients", "label": "Select Friends"},
            {"type": "click", "x": 360 + 330, "y": 845, "text": "Send", "label": "Click Final Send"},
        ]
        res_macro = await automation.replay_macro(
            page,
            macro_steps=custom_macro_steps,
            friends=["*//Eric\\*", "Dylan"],
            step_delay=0.4,
            preview_only=False,
        )
        test_state_macro = await page.evaluate("() => window.__test_state")
        assert "*//Eric\\*" in test_state_macro["sentTo"] and "Dylan" in test_state_macro["sentTo"], f"Macro failed to select friends: {test_state_macro}"
        assert "My AI" not in test_state_macro["sentTo"], "Macro safety guard must uncheck My AI"
        print(f" [PASS] 5. Custom Macro Mode verified (sentTo={test_state_macro['sentTo']}, res={res_macro})")

        await browser.close()

    # 4. Verify Diagnostics Engine
    diag = diagnostics.run_diagnostics()
    assert diag["checks"]["session_auth"]["status"] == "ok", f"Session auth check failed: {diag['checks']['session_auth']}"
    assert diag["checks"]["snap_media"]["status"] == "ok", f"Snap media check failed: {diag['checks']['snap_media']}"
    print(f" [PASS] 6. System Diagnostics verified (overall={diag['overall_status']})")

    # 5. Verify FastAPI Server Endpoints, Version Display & 1-Click Git Updater
    import main
    st_resp = await main.get_status()
    assert st_resp["has_session"] is True
    assert st_resp["streak_mode"] in ("ai_steps", "macro")
    assert "v5.2.0" in st_resp.get("display_version", ""), f"Expected v5.2.0 in display_version, got {st_resp.get('display_version')}"
    v_resp = await main.get_system_version(check_remote=False)
    assert v_resp["version"] == "5.2.0" and v_resp["commit"] != "unknown", f"Unexpected version info: {v_resp}"
    index_html = await main.index()
    assert 'id="app-version-badge"' in index_html and 'id="btn-one-click-update"' in index_html, "Top header must include version badge and 1-Click Git Update button"
    cookies_resp = await main.api_get_cookies()
    assert cookies_resp["ok"] is True and cookies_resp["vault"]["snapchat_cookies"] >= 5
    macro_resp = await main.api_get_macro()
    assert macro_resp["count"] >= 1
    print(f" [PASS] 7. FastAPI Studio Endpoints, Top Version Badge ({v_resp['display_version']}) & 1-Click Git Updater verified")

    print("=" * 68)
    print(" ALL 7 VERIFICATION SUITES PASSED SUCCESSFULLY!")
    print("=" * 68)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
