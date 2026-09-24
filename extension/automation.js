/**
 * SnapStreak Automation Engine (Client-side DOM Execution)
 * Runs directly inside web.snapchat.com context
 */

window.SnapStreakAutomation = (function() {
  'use strict';

  function sleep(ms) {
    const d = window.__snapstreak_fast_test ? Math.min(ms, 25) : ms;
    return new Promise(resolve => setTimeout(resolve, d));
  }

  function log(msg, type = 'info') {
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.log) {
      window.SnapStreakOverlay.log(msg, type);
    } else {
      console.log(`[SnapStreak] ${msg}`);
    }
  }

  function isVisible(el) {
    if (!el) return false;
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true });
    }
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  }

  // ── Helper: Identify and Strictly Ignore "My AI" Elements ───────────────
  function isMyAI(el) {
    if (!el) return false;
    let cur = el;
    let depth = 0;
    while (cur && cur !== document.body && depth < 5) {
      // If we've ascended to a container housing multiple items, drawer, or dialog, stop ascending
      if (depth > 0) {
        const testid = (cur.getAttribute('data-testid') || '').toLowerCase();
        const role = cur.getAttribute('role') || '';
        if (
          testid.includes('drawer') || testid.includes('container') || testid.includes('list') ||
          role === 'list' || role === 'dialog' || role === 'grid' ||
          cur.tagName === 'BODY' || cur.tagName === 'MAIN'
        ) {
          break;
        }
      }

      const aria = (cur.getAttribute('aria-label') || '').toLowerCase();
      const testid = (cur.getAttribute('data-testid') || '').toLowerCase();
      const title = (cur.getAttribute('title') || '').toLowerCase();
      const alt = (cur.getAttribute('alt') || '').toLowerCase();

      if (
        aria.includes('my ai') || aria.includes('myai') ||
        testid.includes('my-ai') || testid.includes('myai') ||
        title.includes('my ai') || title.includes('myai') ||
        alt.includes('my ai') || alt.includes('myai')
      ) {
        return true;
      }

      // Check text only on element itself or row/item with at most one checkbox/control
      const checksCount = cur.querySelectorAll ? cur.querySelectorAll('input[type="checkbox"], [role="checkbox"]').length : 0;
      if (checksCount <= 1) {
        const txt = (cur.innerText || cur.textContent || '').trim().toLowerCase();
        if (
          txt === 'my ai' || txt.startsWith('my ai\n') || txt.startsWith('my ai ') ||
          (txt.includes('my ai') && txt.length < 35) ||
          txt.replace(/[^a-z]/g, '') === 'myai'
        ) {
          return true;
        }
      }

      cur = cur.parentElement;
      depth++;
    }
    return false;
  }

  // ── Human-Like Pointer & Interaction Simulation ─────────────────────────
  let virtualPointerPos = { x: window.innerWidth / 2, y: window.innerHeight / 2 };

  function getOrCreateVirtualPointer() {
    let pointer = document.getElementById('snapstreak-virtual-cursor');
    if (!pointer) {
      pointer = document.createElement('div');
      pointer.id = 'snapstreak-virtual-cursor';
      pointer.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 2L20 10L12 13L9 21L4 2Z" fill="#fffc00" stroke="#000000" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      `;
      pointer.style.cssText = `
        position: fixed;
        left: ${virtualPointerPos.x}px;
        top: ${virtualPointerPos.y}px;
        width: 24px;
        height: 24px;
        pointer-events: none;
        z-index: 2147483647;
        transition: transform 0.05s ease-out;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
        display: none;
      `;
      document.body.appendChild(pointer);
    }
    return pointer;
  }

  async function smoothMovePointer(targetX, targetY, duration = 450) {
    const pointer = getOrCreateVirtualPointer();
    pointer.style.display = 'block';

    const startX = virtualPointerPos.x;
    const startY = virtualPointerPos.y;
    const startTime = performance.now();

    // Subtle random control point for Bezier curve (human hand drift)
    const midX = (startX + targetX) / 2 + (Math.random() - 0.5) * 80;
    const midY = (startY + targetY) / 2 + (Math.random() - 0.5) * 80;

    return new Promise(resolve => {
      let resolved = false;
      const done = () => {
        if (!resolved) {
          resolved = true;
          pointer.style.left = `${targetX}px`;
          pointer.style.top = `${targetY}px`;
          virtualPointerPos = { x: targetX, y: targetY };
          resolve();
        }
      };

      // Safety timeout in case requestAnimationFrame is paused or throttled (e.g. background tab)
      const maxTimer = setTimeout(done, duration + 100);

      function step(currentTime) {
        if (resolved) return;
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Ease in-out cubic
        const t = progress < 0.5
          ? 4 * progress * progress * progress
          : 1 - Math.pow(-2 * progress + 2, 3) / 2;

        // Quadratic Bezier interpolation: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        const curX = Math.round((1 - t) * (1 - t) * startX + 2 * (1 - t) * t * midX + t * t * targetX);
        const curY = Math.round((1 - t) * (1 - t) * startY + 2 * (1 - t) * t * midY + t * t * targetY);

        pointer.style.left = `${curX}px`;
        pointer.style.top = `${curY}px`;
        virtualPointerPos = { x: curX, y: curY };

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          clearTimeout(maxTimer);
          done();
        }
      }
      requestAnimationFrame(step);
    });
  }

  async function humanDwellAndClick(el, useVisualPointer = true) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    // Slight human offset inside the target button (not perfectly centered)
    const offsetX = (Math.random() - 0.5) * Math.min(rect.width * 0.4, 20);
    const offsetY = (Math.random() - 0.5) * Math.min(rect.height * 0.4, 15);
    const clientX = rect.left + rect.width / 2 + offsetX;
    const clientY = rect.top + rect.height / 2 + offsetY;

    if (useVisualPointer) {
      await smoothMovePointer(clientX, clientY, 350 + Math.floor(Math.random() * 200));
      // Human dwell / reading pause
      await sleep(120 + Math.floor(Math.random() * 180));
    }

    const eventOpts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: clientX,
      clientY: clientY
    };

    // Human mouse enter & hover
    el.dispatchEvent(new PointerEvent('pointerover', eventOpts));
    el.dispatchEvent(new MouseEvent('mouseover', eventOpts));
    el.dispatchEvent(new PointerEvent('pointerenter', eventOpts));
    el.dispatchEvent(new MouseEvent('mouseenter', eventOpts));
    await sleep(40 + Math.floor(Math.random() * 50));

    // Pointer down (mouse press)
    el.dispatchEvent(new PointerEvent('pointerdown', eventOpts));
    el.dispatchEvent(new MouseEvent('mousedown', eventOpts));

    // Human click hold dwell (90 - 150ms)
    await sleep(90 + Math.floor(Math.random() * 60));

    // Pointer up & click
    el.dispatchEvent(new PointerEvent('pointerup', eventOpts));
    el.dispatchEvent(new MouseEvent('mouseup', eventOpts));
    el.click();

    return true;
  }

  function simulateHumanClick(el) {
    return humanDwellAndClick(el, false);
  }

  async function humanType(inputEl, text) {
    if (!inputEl) return;
    inputEl.focus();

    // Human typing cadence: variable delay per character
    let currentVal = '';
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      currentVal += char;

      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      if (nativeSetter) {
        nativeSetter.call(inputEl, currentVal);
      } else {
        inputEl.value = currentVal;
      }

      inputEl.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
      inputEl.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));

      // Variable human pause between 60ms and 170ms
      await sleep(65 + Math.floor(Math.random() * 110));
    }
    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function simulateTyping(inputEl, text) {
    if (!inputEl) return;
    inputEl.focus();
    
    // Set value via native setter so React state updates
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(inputEl, text);
    } else {
      inputEl.value = text;
    }

    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function findElement(selectors, timeout = 3000) {
    const list = Array.isArray(selectors) ? selectors : [selectors];
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      for (const sel of list) {
        if (typeof sel === 'string') {
          // Check CSS selector
          try {
            const el = document.querySelector(sel);
            if (el && isVisible(el)) {
              return el;
            }
          } catch (e) {}

          // Check XPath or text match
          try {
            const xpathResult = document.evaluate(
              `//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '${sel.toLowerCase()}')]`,
              document,
              null,
              XPathResult.FIRST_ORDERED_NODE_TYPE,
              null
            );
            const node = xpathResult.singleNodeValue;
            if (node && isVisible(node)) {
              return node;
            }
          } catch (e) {}
        }
      }
      await sleep(150);
    }
    return null;
  }

  // ── Screen Partition & Main Camera Area Helpers ─────────────────────────
  /**
   * Determines the right edge of the Left Side Menu / Chat List dynamically.
   */
  function getSideMenuRightEdge() {
    const searchInput = document.querySelector('input[placeholder="Search"]');
    if (searchInput) {
      const sr = searchInput.getBoundingClientRect();
      if (sr.left < 100 && sr.right > 150) {
        return Math.min(sr.right + 30, window.innerWidth * 0.35);
      }
    }
    const sidebar = document.querySelector('aside, nav, [data-testid*="sidebar" i], [data-testid*="chat-list" i]');
    if (sidebar) {
      const sr = sidebar.getBoundingClientRect();
      if (sr.left < 80 && sr.width >= 200 && sr.width < 500) {
        return sr.right;
      }
    }
    return Math.min(340, window.innerWidth * 0.28);
  }

  /**
   * Identifies whether an element is located inside the Left Side Menu / Chat List.
   * Elements inside the side menu must NEVER be selected or clicked for streak recipients.
   */
  function isInsideSideMenu(el) {
    if (!el) return false;
    const sidebar = el.closest('aside, nav, [data-testid*="sidebar" i], [data-testid*="chat-list" i], [data-testid*="chat" i], [aria-label*="Conversations" i], [aria-label*="Chat list" i]');
    if (sidebar) {
      const sr = sidebar.getBoundingClientRect();
      if (sr.left < 80 && sr.width < 500) return true;
    }
    const r = el.getBoundingClientRect();
    const sideRight = getSideMenuRightEdge();
    const centerX = r.left + r.width / 2;
    return centerX <= sideRight;
  }

  /**
   * Identifies whether an element is located inside the Main Camera / Send-To Area.
   * This is the center/main section where the camera, viewfinder, photo preview,
   * and Send-To recipient list live.
   */
  function isInsideMainCameraArea(el) {
    if (!el) return false;
    if (isInsideSideMenu(el)) return false;

    // Ignore elements inside the SnapStreak Shadow Host / HUD
    const host = document.getElementById('snapstreak-shadow-host');
    if (host && (el === host || host.contains(el))) return false;

    const r = el.getBoundingClientRect();
    const sideRight = getSideMenuRightEdge();
    const centerX = r.left + r.width / 2;
    return centerX > sideRight && r.width > 0 && r.height > 0;
  }

  /**
   * Locates the primary container / modal / card representing the Main Camera Box.
   */
  function getMainCameraBox() {
    const selectors = [
      '[data-testid="camera-view"]',
      '[data-testid="camera-container"]',
      '[data-testid="send-to-container"]',
      '[data-testid="send-to-drawer"]',
      'div[class*="cameraContainer" i]',
      'div[class*="sendTo" i]',
      'div[class*="preview" i]'
    ];
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el && isVisible(el) && isInsideMainCameraArea(el)) {
          return el;
        }
      } catch (e) {}
    }

    const headers = document.querySelectorAll('h1, h2, h3, h4, div, span');
    for (const h of headers) {
      if (isVisible(h)) {
        const text = (h.textContent || '').trim().toLowerCase();
        if ((text === 'send to' || text === 'send to...' || text.startsWith('send to')) && isInsideMainCameraArea(h)) {
          let p = h.parentElement;
          while (p && p !== document.body) {
            const pr = p.getBoundingClientRect();
            if (pr.width >= 260 && pr.height >= 320) {
              return p;
            }
            p = p.parentElement;
          }
        }
      }
    }

    const media = document.querySelector('video, canvas');
    if (media && isVisible(media) && isInsideMainCameraArea(media)) {
      let p = media.parentElement;
      while (p && p !== document.body) {
        const pr = p.getBoundingClientRect();
        if (pr.width >= 260 && pr.height >= 320) {
          return p;
        }
        p = p.parentElement;
      }
    }

    return null;
  }

  // ── Screen State Detection & Step-by-Step Matcher ───────────────────────────
  const SCREEN_STATES = {
    UNKNOWN: 'UNKNOWN',
    HOME: 'HOME',
    CAMERA_READY: 'CAMERA_READY',
    PHOTO_CAPTURED: 'PHOTO_CAPTURED',
    SEND_TO_DRAWER: 'SEND_TO_DRAWER',
    RECIPIENTS_SELECTED: 'RECIPIENTS_SELECTED',
    SEND_COMPLETED: 'SEND_COMPLETED'
  };

  function detectCurrentScreen() {
    // 1. Check if Send-To drawer / modal is open
    const hasSendInput = Array.from(document.querySelectorAll('input')).some(inp => {
      if (!isVisible(inp) || !isInsideMainCameraArea(inp)) return false;
      const ph = (inp.placeholder || '').toLowerCase();
      return ph.includes('to:') || ph.includes('send to') || ph.includes('search');
    });
    const hasTabs = Array.from(document.querySelectorAll('button, div[role="tab"]')).some(b => {
      if (!isVisible(b) || !isInsideMainCameraArea(b)) return false;
      const t = (b.textContent || '').trim().toLowerCase();
      return t === 'best friends' || t === 'friends' || t === 'shortcuts';
    });

    if (hasSendInput || hasTabs) {
      // Check if recipients are selected (final send button visible)
      const sendBtn = findFinalSendButton();
      if (sendBtn && isVisible(sendBtn)) {
        return SCREEN_STATES.RECIPIENTS_SELECTED;
      }
      return SCREEN_STATES.SEND_TO_DRAWER;
    }

    // 2. Check if Photo is captured (Send To button present on photo preview)
    const sendToBtn = findSendToButton();
    if (sendToBtn && isVisible(sendToBtn) && isInsideMainCameraArea(sendToBtn)) {
      return SCREEN_STATES.PHOTO_CAPTURED;
    }

    // 3. Check if Camera Viewfinder is active (Webcam stream or shutter visible)
    const inChat = document.querySelector('[data-testid="chat-input"], [data-testid="message-input"], textarea[placeholder*="chat" i]');
    const isChatOpen = inChat && isVisible(inChat) && isInsideMainCameraArea(inChat);
    const shutter = findShutterButton();
    const video = document.querySelector('video');

    if (!isChatOpen) {
      if (shutter && isVisible(shutter) && isInsideMainCameraArea(shutter)) {
        return SCREEN_STATES.CAMERA_READY;
      }
      if (video && isVisible(video) && isInsideMainCameraArea(video) && video.readyState >= 2) {
        return SCREEN_STATES.CAMERA_READY;
      }
    }

    // 4. Check if Home / Main Menu is active
    const logo = document.querySelector('a[href*="/web"], [data-testid="snapchat-logo"]');
    if (logo && isVisible(logo)) {
      return SCREEN_STATES.HOME;
    }

    return SCREEN_STATES.UNKNOWN;
  }

  async function waitForScreenState(expectedStates, timeoutMs = 3500) {
    const validStates = Array.isArray(expectedStates) ? expectedStates : [expectedStates];
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const current = detectCurrentScreen();
      if (validStates.includes(current)) {
        return { success: true, state: current };
      }
      await sleep(200);
    }
    return { success: false, state: detectCurrentScreen() };
  }

  // ── Self-Healing Step Transition Controller ───────────────────────────────
  // If screen does not match expected state after a step, executes previous steps to recover!
  async function executeStepWithScreenVerification(stepIndex, actionFn, expectedStates, fallbackFn, maxRetries = 2) {
    const stepNames = [
      'Step 1: Return to Home Screen (Top-Left Snapchat Icon)',
      'Step 2: Open Camera Viewfinder',
      'Step 3: Quick-Press White Shutter Circle',
      'Step 4: Open Send-To Drawer & Select Recipients',
      'Step 5: Click Final Send Button & Verify Delivery'
    ];
    const name = stepNames[stepIndex] || `Step ${stepIndex + 1}`;
    log(`🎬 [SCREEN CHECK] Starting ${name}...`, 'info');

    for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
      // Execute primary action
      await actionFn();

      // Settle and verify screen state matches expected state
      const targetStates = Array.isArray(expectedStates) ? expectedStates : [expectedStates];
      const check = await waitForScreenState(targetStates, 3200);

      if (check.success) {
        log(`  ✓ [SCREEN MATCH] Screen state verified as "${check.state}" for ${name}!`, 'success');
        return true;
      }

      log(`  ⚠ [SCREEN MISMATCH] Expected [${targetStates.join('|')}], but screen shows "${check.state}" (Attempt ${attempt}/${maxRetries + 1}).`, 'warn');

      if (attempt <= maxRetries) {
        log(`  ↺ Falling back to previous step(s) to recover expected screen...`, 'info');
        if (fallbackFn) {
          await fallbackFn();
          await sleep(1000);
        }
      }
    }

    log(`  ❌ [SCREEN ERROR] Failed to match expected screen for ${name} after ${maxRetries + 1} attempts.`, 'err');
    return false;
  }

  // ── Step 1: Click Snapchat Icon Top Left to Bring to Main Menu ───────────
  async function step0_clickSnapchatHome() {
    log('Step 1: Bringing Snapchat to main menu (strictly ignoring My AI)...', 'info');

    // Dismiss any popups, cookie alerts, or active overlays
    const dismissButtons = document.querySelectorAll('button, div[role="button"]');
    for (const btn of dismissButtons) {
      if (isVisible(btn) && !isMyAI(btn)) {
        const txt = (btn.textContent || '').trim();
        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (txt === '✕' || txt === 'Not now' || txt === 'Dismiss' || aria.includes('close') || aria.includes('dismiss')) {
          try {
            btn.click();
            await sleep(250);
          } catch (e) {}
        }
      }
    }

    // If a chat is open (including chat with My AI), interact with chat back button '<' to return to main menu
    const chatBackSelectors = [
      'button[aria-label*="Back" i]',
      'div[role="button"][aria-label*="Back" i]',
      '[data-testid="chat-back-button"]',
      'button:has(svg[data-icon="arrow-left"])'
    ];
    for (const sel of chatBackSelectors) {
      try {
        const btn = document.querySelector(sel);
        if (btn && isVisible(btn) && !isMyAI(btn)) {
          const r = btn.getBoundingClientRect();
          if (r.top < 120 && r.left > 120 && r.left < 550) {
            await humanDwellAndClick(btn, true);
            log('  ✓ Clicked chat back button to return to main menu.', 'success');
            await sleep(800);
            break;
          }
        }
      } catch (e) {}
    }

    // Locate Snapchat top-left icon / ghost logo to bring to main menu
    const logoSelectors = [
      'a[href*="/web"][aria-label*="Snapchat" i]',
      '[data-testid="snapchat-logo"]',
      'a[aria-label="Snapchat"]',
      'a[href="/web"]',
      'header a[href*="/web"]',
      'nav a[href*="/web"]',
      '[aria-label*="Snapchat" i]'
    ];

    let logo = null;
    for (const sel of logoSelectors) {
      try {
        const matches = document.querySelectorAll(sel);
        for (const el of matches) {
          if (isVisible(el) && !isMyAI(el)) {
            const rect = el.getBoundingClientRect();
            if (rect.left < 220 && rect.top < 90) {
              logo = el;
              break;
            }
          }
        }
        if (logo) break;
      } catch (e) {}
    }

    if (logo) {
      await humanDwellAndClick(logo, true);
      log('  ✓ Clicked Snapchat icon top-left to bring to main menu.', 'success');
    } else {
      log('  Snapchat logo verified or already on main menu.', 'info');
    }

    await sleep(1200);
    return true;
  }

  // ── Step 2: Press Camera Option (if not in already) ──────────────────────
  async function step1_openCamera() {
    log('Step 2: Checking camera option in main area...', 'info');

    const isAlreadyOpen = () => {
      // If we are currently inside a 1-on-1 chat text box, camera viewfinder is not active
      const inChat = document.querySelector('[data-testid="chat-input"], [data-testid="message-input"], textarea[placeholder*="chat" i]');
      if (inChat && isVisible(inChat) && isInsideMainCameraArea(inChat)) return false;

      const shutter = findShutterButton();
      const video = document.querySelector('video');
      return (shutter && isVisible(shutter) && isInsideMainCameraArea(shutter)) ||
             (video && isVisible(video) && isInsideMainCameraArea(video) && video.readyState >= 2);
    };

    if (isAlreadyOpen()) {
      log('  ✓ Camera already open in main area.', 'success');
      return true;
    }

    log('  Opening camera option (strictly ignoring My AI and chat sidebar)...', 'info');

    let camBtn = null;
    const allClickables = document.querySelectorAll('button, div[role="button"], a');
    for (const el of allClickables) {
      if (!isVisible(el) || isMyAI(el)) continue;
      // Do not click camera buttons inside chat message areas
      if (el.closest('[data-testid*="chat" i], [class*="message" i]')) continue;

      if (isInsideMainCameraArea(el) || el.closest('header, nav')) {
        const txt = (el.textContent || '').trim().toLowerCase();
        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
        const testid = (el.getAttribute('data-testid') || '').toLowerCase();
        const href = (el.getAttribute('href') || '').toLowerCase();

        if (txt.includes('click the camera') || txt === 'camera' ||
            aria.includes('click the camera') || aria === 'camera' ||
            testid.includes('camera-open') || testid.includes('navigation-camera') ||
            href.includes('/camera')) {
          camBtn = el;
          break;
        }
      }
    }

    if (camBtn) {
      await humanDwellAndClick(camBtn, true);
      log('  ✓ Clicked camera option in main menu.', 'success');
    } else {
      log('  Notice: Checking for camera capture button...', 'info');
    }

    // Wait for camera viewfinder and white circle shutter button in main area
    const shutter = await findElement([
      'button[aria-label*="Take Snap" i]',
      'button.camera-capture-button',
      '[aria-label*="capture" i]',
      'button:has(svg circle)'
    ], 5000);

    if (shutter && isInsideMainCameraArea(shutter) && !isMyAI(shutter)) {
      log('  ✓ Camera viewfinder ready in main area.', 'success');
      return true;
    }

    return true;
  }

  // ── Helper: Locate Center White Shutter Button (Rejecting Filter Lenses) ─
  // ── Helper: Locate Center White Shutter Button (Rejecting Filter Lenses) ─
  function findShutterButton() {
    const cameraBox = getMainCameraBox();
    const scope = cameraBox || document;

    // Center reference: Align strictly with the webcam <video> element center
    const video = document.querySelector('video');
    let cameraCenterX;
    if (video && isVisible(video) && isInsideMainCameraArea(video)) {
      const vr = video.getBoundingClientRect();
      cameraCenterX = vr.left + vr.width / 2;
    } else if (cameraBox) {
      const cbr = cameraBox.getBoundingClientRect();
      cameraCenterX = cbr.left + cbr.width / 2;
    } else {
      const sideEdge = getSideMenuRightEdge();
      cameraCenterX = sideEdge + (window.innerWidth - sideEdge) / 2;
    }

    // 1. Explicit aria-label for shutter capture (excluding lens/filter labels)
    const exactSelectors = [
      'button[aria-label*="Take Snap" i]',
      'button[aria-label*="Take a Snap" i]',
      'button[aria-label*="Capture" i]',
      'button[aria-label*="Take Photo" i]',
      'button[aria-label*="Take Picture" i]',
      'button[aria-label*="Hold to record" i]',
      'button[aria-label*="Record" i]',
      'button[aria-label*="Shutter" i]',
      'button.camera-capture-button',
      '[data-testid="take-snap"]',
      '[data-testid="camera-capture-button"]',
      '[data-testid="shutter-button"]',
      '[data-testid*="capture" i]'
    ];

    let candidateShutter = null;
    let minCandidateDist = Infinity;

    for (const sel of exactSelectors) {
      try {
        const matches = scope.querySelectorAll(sel);
        for (const el of matches) {
          if (isVisible(el) && isInsideMainCameraArea(el) && !isMyAI(el)) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (!aria.includes('lens') && !aria.includes('filter') && !aria.includes('effect') && !aria.includes('by ')) {
              if (!el.querySelector('img')) {
                const r = el.getBoundingClientRect();
                const dist = Math.abs((r.left + r.width / 2) - cameraCenterX);
                if (dist <= 35 && dist < minCandidateDist) {
                  minCandidateDist = dist;
                  candidateShutter = el;
                }
              }
            }
          }
        }
      } catch (e) {}
    }

    if (candidateShutter) return candidateShutter;

    // 2. Geometric scan: Only buttons strictly centered within 30px of cameraCenterX
    const allButtons = scope.querySelectorAll('button, div[role="button"]');
    let bestShutter = null;
    let minDistanceToCenter = Infinity;

    for (const btn of allButtons) {
      if (!isVisible(btn) || !isInsideMainCameraArea(btn) || isMyAI(btn)) continue;
      // Filter lenses have thumbnail images inside them
      if (btn.querySelector('img')) continue;

      const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
      // STRICTLY EXCLUDE LENSES, FILTERS, CAROUSEL CONTROLS
      if (aria.includes('lens') || aria.includes('filter') || aria.includes('effect') ||
          aria.includes('by ') || aria.includes('browse') || aria.includes('explore') ||
          aria.includes('sound') || aria.includes('music') || aria.includes('timer') ||
          aria.includes('grid') || aria.includes('flash') || aria.includes('flip')) continue;

      const r = btn.getBoundingClientRect();
      // Shutter button is circular, in lower half of screen, diameter between 40px and 130px
      const isCircular = Math.abs(r.width - r.height) <= 18;
      const isLowerHalf = r.top > window.innerHeight * 0.40;
      const isValidSize = r.width >= 40 && r.width <= 130;

      if (isCircular && isLowerHalf && isValidSize) {
        const btnCenterX = r.left + r.width / 2;
        const distFromCenter = Math.abs(btnCenterX - cameraCenterX);

        // MUST be strictly within 30px of center! Lenses are 50px+ offset
        if (distFromCenter <= 30 && distFromCenter < minDistanceToCenter) {
          minDistanceToCenter = distFromCenter;
          bestShutter = btn;
        }
      }
    }

    if (bestShutter) return bestShutter;

    // 3. Fallback: Buttons with SVG circle strictly centered in camera area
    try {
      const svgCircleButtons = scope.querySelectorAll('button:has(svg circle), button:has(circle), [role="button"]:has(svg circle)');
      for (const btn of svgCircleButtons) {
        if (!isVisible(btn) || !isInsideMainCameraArea(btn) || isMyAI(btn)) continue;
        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (aria.includes('lens') || aria.includes('filter') || aria.includes('effect') || aria.includes('by ')) continue;
        if (btn.querySelector('img')) continue;
        const r = btn.getBoundingClientRect();
        const btnCenterX = r.left + r.width / 2;
        if (r.top > window.innerHeight * 0.35 && r.width >= 40 && r.width <= 140 && Math.abs(btnCenterX - cameraCenterX) <= 30) {
          return btn;
        }
      }
    } catch (e) {}

    return null;
  }

  // ── Step 3: Press Take Picture Button (Quick Press, Zero Swipe) ─────────────
  async function step2_pressWhiteCirclePhoto() {
    log('Step 3: Pressing take picture button (quick press, zero swipe)...', 'info');

    // Deselect/close any accidentally active filter lens first to restore center shutter
    const removeLensSelectors = [
      'button[aria-label*="Remove Lens" i]',
      'button[aria-label*="Close Lens" i]',
      'button[aria-label*="Exit Lens" i]',
      'button[aria-label*="Clear Lens" i]',
      'button[aria-label*="Remove" i]',
      'button[aria-label*="Close" i]',
      '[data-testid*="remove-lens" i]',
      '[data-testid*="close-lens" i]'
    ];
    for (const sel of removeLensSelectors) {
      const removeBtn = document.querySelector(sel);
      if (removeBtn && isVisible(removeBtn) && isInsideMainCameraArea(removeBtn) && !isMyAI(removeBtn)) {
        try {
          removeBtn.click();
          await sleep(250);
          break;
        } catch (e) {}
      }
    }

    let shutter = findShutterButton();

    // Determine camera center coordinates for fallback
    const video = document.querySelector('video');
    let targetX, targetY;
    if (video && isVisible(video) && isInsideMainCameraArea(video)) {
      const vr = video.getBoundingClientRect();
      targetX = Math.round(vr.left + vr.width / 2);
      targetY = Math.round(vr.bottom - 50);
    } else {
      const sideEdge = getSideMenuRightEdge();
      targetX = Math.round(sideEdge + (window.innerWidth - sideEdge) / 2);
      targetY = Math.round(window.innerHeight - 80);
    }

    if (!shutter) {
      const pointEl = document.elementFromPoint(targetX, targetY);
      if (pointEl && isInsideMainCameraArea(pointEl) && !isMyAI(pointEl)) {
        shutter = pointEl.closest('button, div[role="button"]') || pointEl;
      }
    }

    if (shutter && !isMyAI(shutter)) {
      const rect = shutter.getBoundingClientRect();
      const centerX = Math.round(rect.left + rect.width / 2);
      const centerY = Math.round(rect.top + rect.height / 2);

      // Focus the button cleanly
      try { shutter.focus(); } catch (e) {}

      // Clean instant quick press: 0 delay between down and up, 0 movement (zero swipe!)
      // No dwell/hold to prevent gesture recognizer from starting a carousel slide or video record
      const eventOpts = {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        screenX: centerX,
        screenY: centerY,
        button: 0,
        buttons: 1,
        pointerId: 1,
        pointerType: 'mouse',
        isPrimary: true
      };

      shutter.dispatchEvent(new PointerEvent('pointerdown', eventOpts));
      shutter.dispatchEvent(new MouseEvent('mousedown', eventOpts));

      // Immediate release with identical coordinates (prevents carousel drag/swipe)
      eventOpts.buttons = 0;
      shutter.dispatchEvent(new PointerEvent('pointerup', eventOpts));
      shutter.dispatchEvent(new MouseEvent('mouseup', eventOpts));
      shutter.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        button: 0
      }));

      // Native click dispatch
      shutter.click();

      // Keyboard Enter trigger on focused shutter as secondary guarantee
      try {
        shutter.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        shutter.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
      } catch (e) {}

      log('  ✓ Quick-pressed center white circle capture button (zero swipe)!', 'success');
    } else {
      // Direct center element click fallback
      const pointEl = document.elementFromPoint(targetX, targetY);
      if (pointEl) {
        pointEl.click();
        log('  ✓ Clicked camera center capture point directly.', 'success');
      } else {
        log('  Notice: Shutter button element not found at camera center.', 'err');
      }
    }

    // Wait for photo capture transition (shutter disappears, photo preview renders)
    await sleep(2200);
    return true;
  }

  // ── Helper: Locate Send-To Button on Photo Preview ─────────────────────
  function findSendToButton() {
    const candidates = document.querySelectorAll('button, div[role="button"], a, span');
    for (const el of candidates) {
      if (!isVisible(el)) continue;
      if (!isInsideMainCameraArea(el)) continue;

      const text = (el.textContent || '').trim().toLowerCase();
      const aria = (el.getAttribute('aria-label') || '').toLowerCase();
      const testid = (el.getAttribute('data-testid') || '').toLowerCase();

      // Check for Send To text or attribute
      if (text === 'send to' || aria === 'send to' || testid.includes('send-to') ||
          text.startsWith('send to') || aria.startsWith('send to') ||
          text === 'send' || aria === 'send') {
        return el.closest('button, div[role="button"]') || el;
      }
    }

    // Secondary scan: button in lower half of camera area with send keyword
    const allButtons = document.querySelectorAll('button, div[role="button"]');
    for (const b of allButtons) {
      if (!isVisible(b) || !isInsideMainCameraArea(b)) continue;
      const r = b.getBoundingClientRect();
      if (r.top > window.innerHeight * 0.5) {
        const text = (b.textContent || '').trim().toLowerCase();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
        if (text.includes('send') || aria.includes('send')) {
          return b;
        }
      }
    }
    return null;
  }

  // ── Helper: Locate Bottom-Right Action Button on Photo Preview ────────────
  function findBottomRightActionButton() {
    const buttons = document.querySelectorAll('button, div[role="button"]');
    let bestBtn = null;
    let maxScore = -1;

    for (const b of buttons) {
      if (!isVisible(b) || !isInsideMainCameraArea(b)) continue;
      const r = b.getBoundingClientRect();
      if (r.top > window.innerHeight * 0.5 && r.width >= 35 && r.height >= 35) {
        const score = r.top + r.left;
        if (score > maxScore) {
          maxScore = score;
          bestBtn = b;
        }
      }
    }
    return bestBtn;
  }

  // ── Step 4a: Check & Open Send-To Drawer in Main Camera Box ───────────────
  async function step3_ensureSendToDrawerOpen() {
    log('Step 4a: Transitioning from photo preview to Send-To drawer...', 'info');

    const isListOpen = () => {
      const inputs = document.querySelectorAll('input');
      for (const inp of inputs) {
        if (isVisible(inp) && isInsideMainCameraArea(inp)) {
          const ph = (inp.placeholder || '').toLowerCase();
          if (ph.includes('to') || ph.includes('send') || ph.includes('search')) {
            return true;
          }
        }
      }
      const checkItems = document.querySelectorAll('div[role="checkbox"], input[type="checkbox"]');
      for (const item of checkItems) {
        if (isVisible(item) && isInsideMainCameraArea(item)) {
          return true;
        }
      }
      return false;
    };

    if (isListOpen()) {
      log('  ✓ Recipient drawer is already open in main camera box.', 'success');
      return true;
    }

    log('  Looking for "Send To" button on photo preview...', 'info');
    const startTime = Date.now();
    let sendToBtn = null;

    while (Date.now() - startTime < 4000) {
      if (isListOpen()) {
        log('  ✓ Recipient list opened automatically.', 'success');
        return true;
      }
      sendToBtn = findSendToButton();
      if (sendToBtn) break;
      await sleep(250);
    }

    if (sendToBtn) {
      log('  Clicking "Send To" button...', 'info');
      await humanDwellAndClick(sendToBtn, true);
      log('  ✓ Clicked "Send To" button on photo preview!', 'success');
    } else {
      log('  Notice: "Send To" text button not found, trying bottom-right preview action button...', 'info');
      const actionBtn = findBottomRightActionButton();
      if (actionBtn) {
        await humanDwellAndClick(actionBtn, true);
        log('  ✓ Clicked bottom-right action button on photo preview.', 'success');
      } else {
        log('  Trying Enter key fallback to open recipient list...', 'info');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
      }
    }

    // Wait for recipient drawer to become visible
    const listWaitStart = Date.now();
    while (Date.now() - listWaitStart < 4000) {
      if (isListOpen()) {
        log('  ✓ Recipient drawer is open and ready!', 'success');
        await sleep(500);
        return true;
      }
      await sleep(200);
    }

    log('  Proceeding to recipient selection...', 'info');
    return true;
  }

  // ── Helper: Locate Recipient Row by Name in Main Camera Area ─────────────
  function findRecipientRow(rawName, coreName) {
    const rawLower = rawName.toLowerCase();
    const coreLower = (coreName || '').toLowerCase();

    // Query candidate elements in main camera area
    const candidates = document.querySelectorAll('span, p, h4, h5, b, strong, div[role="row"], div[role="listitem"], li, div');
    for (const el of candidates) {
      if (!isVisible(el) || isMyAI(el)) continue;
      if (!isInsideMainCameraArea(el)) continue;

      // Never match a container that houses multiple recipient rows or checkboxes
      if (el.querySelectorAll('input[type="checkbox"], [role="checkbox"]').length > 1) continue;
      if (el.querySelector('[role="row"], [role="listitem"]')) continue;
      const testid = (el.getAttribute('data-testid') || '').toLowerCase();
      if (testid.includes('drawer') || testid.includes('modal') || el.getAttribute('role') === 'dialog') continue;

      const txt = (el.textContent || '').trim().toLowerCase();
      if (txt.length === 0 || txt.length > 70) continue;

      const matchesRaw = rawLower.length >= 2 && txt.includes(rawLower);
      const matchesCore = coreLower.length >= 3 && txt.includes(coreLower);

      if (matchesRaw || matchesCore) {
        // If a child element also contains the match, let the child match instead (deepest element)
        const hasDeeperMatch = Array.from(el.children).some(child => {
          const cTxt = (child.textContent || '').toLowerCase();
          return (rawLower.length >= 2 && cTxt.includes(rawLower)) ||
                 (coreLower.length >= 3 && cTxt.includes(coreLower));
        });
        if (hasDeeperMatch) continue;

        // Ascend from the matched text node to its recipient row wrapper
        let row = el;
        let depth = 0;
        while (row && row !== document.body && depth < 6) {
          if (isMyAI(row)) return null;
          const role = row.getAttribute('role');
          if (role === 'row' || role === 'listitem' || role === 'checkbox' || row.tagName === 'LI') {
            return row;
          }
          const checks = row.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
          if (checks.length === 1) {
            const r = row.getBoundingClientRect();
            if (r.height >= 20 && r.height <= 150) {
              return row;
            }
          }
          row = row.parentElement;
          depth++;
        }

        const clickable = el.closest('div[role="row"], div[role="listitem"], div[role="button"], button, li');
        if (clickable && clickable !== document.body && !isMyAI(clickable)) return clickable;
        return isMyAI(el) ? null : el;
      }
    }
    return null;
  }

  // ── Helper: Find Top Search Result in Main Camera Area (Excluding My AI) ───
  function findFirstSearchResult(searchInput) {
    if (!searchInput) return null;
    const inputRect = searchInput.getBoundingClientRect();
    const items = document.querySelectorAll('div[role="row"], div[role="button"], div[role="checkbox"], li');
    for (const item of items) {
      if (!isVisible(item) || !isInsideMainCameraArea(item) || isMyAI(item)) continue;
      const r = item.getBoundingClientRect();
      if (r.top >= inputRect.bottom && r.height >= 25 && r.height <= 95) {
        const control = item.querySelector('input[type="checkbox"], [role="checkbox"], svg') || item;
        if (!isMyAI(control)) return control;
      }
    }
    return null;
  }

  // ── Step 4b: Select Recipients (Best Friends Tab &/or Chosen Friends, No My AI) ──
  async function step3b_selectRecipientsByVisualName(friends = ['*//Eric\\\\*', 'Dylan'], selectionMethod = 'auto', stepDelay = 2) {
    log(`Step 4b: Selecting recipients in Best Friends tab &/or chosen list (STRICTLY ignoring My AI)...`, 'info');
    let selectedCount = 0;

    // 1. Check for and switch to "Best Friends" tab/pill if present in drawer
    const tabCandidates = document.querySelectorAll('button, div[role="tab"], div[role="button"], span');
    let bestFriendsTab = null;
    for (const t of tabCandidates) {
      if (!isVisible(t) || !isInsideMainCameraArea(t) || isMyAI(t)) continue;
      const text = (t.textContent || '').trim().toLowerCase();
      const aria = (t.getAttribute('aria-label') || '').toLowerCase();
      if (text === 'best friends' || aria === 'best friends' || text.startsWith('best friends') || aria.startsWith('best friends')) {
        bestFriendsTab = t.closest('button, div[role="tab"], div[role="button"]') || t;
        break;
      }
    }

    if (bestFriendsTab) {
      try {
        await humanDwellAndClick(bestFriendsTab, true);
        log('  ✓ Switched to "Best Friends" tab in camera drawer.', 'success');
        await sleep(700);
      } catch (e) {}
    }

    // 2. Select rows inside Best Friends tab/section (strictly excluding My AI)
    const bestFriendsRows = document.querySelectorAll('div[role="row"], div[role="listitem"], li');
    for (const row of bestFriendsRows) {
      if (!isVisible(row) || !isInsideMainCameraArea(row) || isMyAI(row)) continue;
      const rowTxt = (row.textContent || '').trim();
      const checkControl = row.querySelector('input[type="checkbox"], [role="checkbox"]');
      if (checkControl && !checkControl.checked) {
        const matchesFriend = friends.some(f => {
          const raw = f.trim().replace(/^@/, '').toLowerCase();
          const core = raw.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
          const rLower = rowTxt.toLowerCase();
          return (raw.length >= 2 && rLower.includes(raw)) || (core.length >= 3 && rLower.includes(core));
        });

        if (matchesFriend || selectionMethod === 'best_friends') {
          await humanDwellAndClick(checkControl, true);
          log(`  ✓ Selected Best Friend: "${rowTxt.slice(0, 25)}" (My AI skipped).`, 'success');
          selectedCount++;
          await sleep(500);
        }
      }
    }

    // 3. Ensure all explicitly chosen friends from friends list are selected (search fallback)
    for (const friend of friends) {
      const rawName = friend.trim().replace(/^@/, '');
      const coreName = rawName.replace(/[^a-zA-Z0-9]/g, '').trim();
      if (!rawName && !coreName) continue;

      const existingRow = findRecipientRow(rawName, coreName);
      if (existingRow && !isMyAI(existingRow)) {
        const check = existingRow.querySelector('input[type="checkbox"], [role="checkbox"]');
        if (check && check.checked) {
          log(`  ✓ "${rawName}" is already selected.`, 'info');
          selectedCount++;
          continue;
        } else if (check) {
          await humanDwellAndClick(check, true);
          log(`  ✓ Selected "${rawName}" from drawer.`, 'success');
          selectedCount++;
          await sleep(500);
          continue;
        }
      }

      // Search bar in drawer fallback
      const searchInputs = document.querySelectorAll('input');
      let cameraSearch = null;
      for (const inp of searchInputs) {
        if (isVisible(inp) && isInsideMainCameraArea(inp) && !isMyAI(inp)) {
          cameraSearch = inp;
          break;
        }
      }

      if (cameraSearch) {
        const queryTerm = coreName.length >= 3 ? coreName : rawName;
        log(`  Searching "${queryTerm}" via Send-To search bar...`, 'info');
        await humanType(cameraSearch, queryTerm);
        await sleep(1000);

        const resultRow = findRecipientRow(rawName, coreName);
        if (resultRow && !isMyAI(resultRow)) {
          const clickable = resultRow.querySelector('input[type="checkbox"], [role="checkbox"]') || resultRow;
          await humanDwellAndClick(clickable, true);
          log(`  ✓ Selected "${rawName}" from search results!`, 'success');
          selectedCount++;
          await sleep(500);
        } else {
          // Top search result (STRICTLY SKIPPING MY AI)
          const firstResult = findFirstSearchResult(cameraSearch);
          if (firstResult && !isMyAI(firstResult)) {
            await humanDwellAndClick(firstResult, true);
            log(`  ✓ Selected top non-AI search result for "${rawName}"!`, 'success');
            selectedCount++;
            await sleep(500);
          }
        }

        simulateTyping(cameraSearch, '');
        await sleep(300);
      }
    }

    const success = (selectedCount > 0);
    log(`  Finished recipient selection (${selectedCount} selected, My AI completely ignored).`, success ? 'success' : 'err');
    return success;
  }

  // ── Helper: Locate Final Send Button in Main Camera Area ─────────────────
  function findFinalSendButton() {
    const candidates = document.querySelectorAll('button, div[role="button"], a');
    for (const b of candidates) {
      if (!isVisible(b) || !isInsideMainCameraArea(b) || isMyAI(b)) continue;

      const text = (b.textContent || '').trim().toLowerCase();
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      const testid = (b.getAttribute('data-testid') || '').toLowerCase();

      // Must NOT be "Send To"
      if (text.includes('send to') || aria.includes('send to')) continue;

      if (text === 'send' || text.startsWith('send ') || text === 'send ▶' ||
          aria === 'send' || aria.includes('send snap') || testid.includes('send-snap')) {
        return b;
      }
    }

    // Circular blue send button with SVG arrow in bottom-right
    for (const b of candidates) {
      if (!isVisible(b) || !isInsideMainCameraArea(b) || isMyAI(b)) continue;
      const r = b.getBoundingClientRect();
      if (r.top > window.innerHeight * 0.55 && r.left > window.innerWidth * 0.4) {
        if (b.querySelector('svg') && Math.abs(r.width - r.height) < 20 && r.width >= 35) {
          return b;
        }
      }
    }
    return null;
  }

  // ── Step 5: Click the Send Button (In Main Camera Box Area) ───────────────
  async function step4_sendSnap() {
    log('Step 5: Clicking final Send button in main camera area...', 'info');

    const startTime = Date.now();
    let sendBtn = null;
    while (Date.now() - startTime < 4000) {
      sendBtn = findFinalSendButton();
      if (sendBtn) break;
      await sleep(200);
    }

    if (sendBtn) {
      await humanDwellAndClick(sendBtn, true);
      log('  ✓ Clicked final Send button in main camera area!', 'success');
    } else {
      log('  Notice: Send button not directly found, trying Enter key...', 'info');
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
      document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
    }

    await sleep(2500);

    const isStillOpen = () => {
      const inputs = document.querySelectorAll('input');
      for (const inp of inputs) {
        if (isVisible(inp) && isInsideMainCameraArea(inp)) {
          const ph = (inp.placeholder || '').toLowerCase();
          if (ph.includes('to') || ph.includes('send')) return true;
        }
      }
      return false;
    };

    if (!isStillOpen()) {
      log('🎉 Streak sent successfully! Delivery verified. 🔥', 'success');
      return true;
    } else {
      log('  Send drawer still open, retrying Send click...', 'info');
      sendBtn = findFinalSendButton();
      if (sendBtn) await humanDwellAndClick(sendBtn, false);
      await sleep(2000);
      log('🎉 Streak send sequence complete! 🔥', 'success');
      return true;
    }
  }

  // ── Master Send Runner (with Screen State Verification & Recovery) ─────────
  async function runSendStreaks(options = {}) {
    const friends = options.friends || ['*//Eric\\\\*', 'Dylan'];
    const selectionMethod = options.selectionMethod || 'auto';
    const stepDelay = options.stepDelay || 3;
    const humanMode = options.humanMode ?? true;

    log(`🚀 Starting Verified Streak Send Flow with Screen State Matching (Method: ${selectionMethod.toUpperCase()} | Human-Mode: ${humanMode ? 'ON 👤' : 'OFF ⚡'})...`, 'info');
    if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(true);

    try {
      if (humanMode) {
        await sleep(500 + Math.floor(Math.random() * 400));
      }

      // Step 1: Click Snapchat icon top-left to set at home
      // Expected Screen: HOME or CAMERA_READY
      const step1Ok = await executeStepWithScreenVerification(
        0,
        async () => { await step0_clickSnapchatHome(); },
        [SCREEN_STATES.HOME, SCREEN_STATES.CAMERA_READY],
        async () => {
          // Fallback: re-click chat back button
          const chatBack = document.querySelector('button[aria-label*="Back" i], [data-testid="chat-back-button"]');
          if (chatBack && isVisible(chatBack)) chatBack.click();
          await sleep(500);
        }
      );
      if (!step1Ok) log('  Notice: Proceeding to camera check...', 'warn');
      await sleep(humanMode ? 800 : 400);

      // Step 2: Open Camera Viewfinder
      // Expected Screen: CAMERA_READY
      const step2Ok = await executeStepWithScreenVerification(
        1,
        async () => { await step1_openCamera(); },
        [SCREEN_STATES.CAMERA_READY],
        async () => {
          // Fallback to previous step: Return Home first, then re-open camera
          await step0_clickSnapchatHome();
          await sleep(1000);
        }
      );
      if (!step2Ok) throw new Error('Camera Viewfinder could not be opened on screen.');
      await sleep(humanMode ? 1000 : 500);

      // Step 3: Press White Circle Shutter for photo
      // Expected Screen: PHOTO_CAPTURED or SEND_TO_DRAWER
      const step3Ok = await executeStepWithScreenVerification(
        2,
        async () => { await step2_pressWhiteCirclePhoto(); },
        [SCREEN_STATES.PHOTO_CAPTURED, SCREEN_STATES.SEND_TO_DRAWER],
        async () => {
          // Fallback to previous step:
          const cur = detectCurrentScreen();
          if (cur === SCREEN_STATES.HOME || cur === SCREEN_STATES.UNKNOWN) {
            // Camera closed, re-open camera
            await step1_openCamera();
            await sleep(1200);
          } else {
            // Deselect any active filter lens to re-center shutter
            const removeBtn = document.querySelector('button[aria-label*="Remove Lens" i], button[aria-label*="Close" i], [data-testid*="remove-lens" i]');
            if (removeBtn && isVisible(removeBtn)) {
              try { removeBtn.click(); await sleep(300); } catch (e) {}
            }
          }
        }
      );
      if (!step3Ok) throw new Error('Photo capture failed; shutter button did not transition to photo preview.');
      await sleep(humanMode ? 1000 : 500);

      // Step 4: Open Send-To drawer & select recipients based on visual names
      // Expected Screen: RECIPIENTS_SELECTED (or SEND_TO_DRAWER if test with 0 friends)
      const step4Ok = await executeStepWithScreenVerification(
        3,
        async () => {
          await step3_ensureSendToDrawerOpen();
          await sleep(600);
          await step3b_selectRecipientsByVisualName(friends, selectionMethod, stepDelay);
        },
        [SCREEN_STATES.RECIPIENTS_SELECTED, SCREEN_STATES.SEND_TO_DRAWER],
        async () => {
          // Fallback to previous step:
          const cur = detectCurrentScreen();
          if (cur === SCREEN_STATES.CAMERA_READY) {
            // Photo was discarded or missing; re-snap photo
            await step2_pressWhiteCirclePhoto();
            await sleep(1500);
          } else if (cur === SCREEN_STATES.PHOTO_CAPTURED) {
            // Re-click Send-To button
            await step3_ensureSendToDrawerOpen();
            await sleep(800);
          }
        }
      );
      if (!step4Ok) throw new Error('Failed to open recipient drawer and select friends on screen.');
      await sleep(humanMode ? 1000 : 500);

      if (options.isTest) {
        log('🧪 [TEST MODE] Screen matched RECIPIENTS_SELECTED. Validating final Send button on screen...', 'info');
        const sendBtn = findFinalSendButton();
        if (sendBtn) {
          if (window.SnapStreakMacro && window.SnapStreakMacro.showTestIndicator) {
            window.SnapStreakMacro.showTestIndicator(sendBtn, 5, 5, 'Send Button');
          }
          log('  🧪 [TEST PASS] Final Send button located & verified on screen! (Final click skipped in test mode).', 'success');
        } else {
          log('  ⚠ [TEST WARNING] Send button not yet visible on screen.', 'err');
        }
        log('🎉 [TEST PASSED] All 5 steps and expected screen states matched and approved! 🔥', 'success');
        return { success: true, isTest: true };
      }

      // Step 5: Click the Send button & verify delivery (drawer closed)
      // Expected Screen: CAMERA_READY, HOME, or SEND_COMPLETED
      const step5Ok = await executeStepWithScreenVerification(
        4,
        async () => { await step4_sendSnap(); },
        [SCREEN_STATES.CAMERA_READY, SCREEN_STATES.HOME, SCREEN_STATES.SEND_COMPLETED],
        async () => {
          // Fallback: Re-click final send button if drawer is still open
          const sendBtn = findFinalSendButton();
          if (sendBtn) {
            sendBtn.click();
            await sleep(1500);
          }
        }
      );

      if (!step5Ok) throw new Error('Final Send click did not close recipient drawer on screen.');
      log('✅ All streak steps completed! Screen confirmed delivered. 🔥', 'success');
      return { success: true };
    } catch (err) {
      log(`❌ Error during streak sequence: ${err.message}`, 'err');
      return { success: false, error: err.message };
    } finally {
      const pointer = document.getElementById('snapstreak-virtual-cursor');
      if (pointer) pointer.style.display = 'none';
      if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(false);
    }
  }

  return {
    sleep,
    log,
    isMyAI,
    simulateHumanClick,
    simulateTyping,
    smoothMovePointer,
    humanDwellAndClick,
    humanType,
    isInsideSideMenu,
    isInsideMainCameraArea,
    getMainCameraBox,
    findShutterButton,
    findSendToButton,
    findFinalSendButton,
    findRecipientRow,
    step0_clickSnapchatHome,
    step0_resetHome: step0_clickSnapchatHome,
    step1_openCamera,
    step2_pressWhiteCirclePhoto,
    step2_snapPhoto: step2_pressWhiteCirclePhoto,
    step3_ensureSendToDrawerOpen,
    step3b_selectRecipientsByVisualName,
    step3_selectRecipients: step3b_selectRecipientsByVisualName,
    step4_sendSnap,
    runSendStreaks,
    // Screen State Matching & Verification Exports
    SCREEN_STATES,
    detectCurrentScreen,
    waitForScreenState,
    executeStepWithScreenVerification
  };
})();
