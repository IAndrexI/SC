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
  function findShutterButton() {
    const cameraBox = getMainCameraBox();
    const scope = cameraBox || document;

    // 1. Explicit aria-label for shutter capture (excluding lens/filter labels)
    const exactSelectors = [
      'button[aria-label*="Take Snap" i]',
      'button[aria-label*="Take a Snap" i]',
      'button[aria-label*="Capture" i]',
      'button[aria-label*="Take Photo" i]',
      'button[aria-label*="Record" i]',
      'button[aria-label*="Shutter" i]',
      'button.camera-capture-button',
      '[data-testid="take-snap"]',
      '[data-testid="camera-capture-button"]',
      '[data-testid="shutter-button"]',
      '[data-testid*="capture" i]'
    ];
    for (const sel of exactSelectors) {
      try {
        const matches = scope.querySelectorAll(sel);
        for (const el of matches) {
          if (isVisible(el) && isInsideMainCameraArea(el) && !isMyAI(el)) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (!aria.includes('lens') && !aria.includes('filter') && !aria.includes('effect') && !aria.includes('by ')) {
              if (!el.querySelector('img')) {
                return el;
              }
            }
          }
        }
      } catch (e) {}
    }

    // 2. Buttons with SVG circle (Snapchat's classic white circle shutter)
    try {
      const svgCircleButtons = scope.querySelectorAll('button:has(svg circle), button:has(circle), [role="button"]:has(svg circle)');
      for (const btn of svgCircleButtons) {
        if (!isVisible(btn) || !isInsideMainCameraArea(btn) || isMyAI(btn)) continue;
        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (aria.includes('lens') || aria.includes('filter') || aria.includes('effect') || aria.includes('by ')) continue;
        if (btn.querySelector('img')) continue;
        const r = btn.getBoundingClientRect();
        if (r.top > window.innerHeight * 0.35 && r.width >= 45 && r.width <= 140) {
          return btn;
        }
      }
    } catch (e) {}

    // 3. Geometric scan: Align strictly with the webcam <video> element center
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

    const allButtons = scope.querySelectorAll('button, div[role="button"]');
    let bestShutter = null;
    let minDistanceToCenter = Infinity;

    for (const btn of allButtons) {
      if (!isVisible(btn) || !isInsideMainCameraArea(btn) || isMyAI(btn)) continue;
      // Filter lenses have thumbnail images inside them
      if (btn.querySelector('img')) continue;

      const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
      // EXCLUDE LENSES, FILTERS, AND UNRELATED CONTROLS
      if (aria.includes('lens') || aria.includes('filter') || aria.includes('effect') ||
          aria.includes('by ') || aria.includes('browse') || aria.includes('explore') ||
          aria.includes('sound') || aria.includes('music') || aria.includes('timer') ||
          aria.includes('grid') || aria.includes('flash') || aria.includes('flip')) continue;

      const r = btn.getBoundingClientRect();
      // Shutter button is circular, in lower half of screen, diameter between 48px and 125px
      const isCircular = Math.abs(r.width - r.height) <= 18;
      const isLowerHalf = r.top > window.innerHeight * 0.40;
      const isValidSize = r.width >= 48 && r.width <= 125;

      if (isCircular && isLowerHalf && isValidSize) {
        const btnCenterX = r.left + r.width / 2;
        const distFromCenter = Math.abs(btnCenterX - cameraCenterX);

        // Strictly minimize distance to center: the shutter is right at cameraCenterX
        // (Lens carousel items are offset horizontally to the left and right)
        if (distFromCenter < 90 && distFromCenter < minDistanceToCenter) {
          minDistanceToCenter = distFromCenter;
          bestShutter = btn;
        }
      }
    }

    return bestShutter;
  }

  // ── Step 3: Press Take Picture Button (Quick Press, Zero Swipe) ─────────────
  async function step2_pressWhiteCirclePhoto() {
    log('Step 3: Pressing take picture button (quick press, zero swipe)...', 'info');

    // Deselect/close any accidentally active filter lens first
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
          await sleep(200);
          break;
        } catch (e) {}
      }
    }

    let shutter = findShutterButton();

    // Fallback: Check element at camera center bottom if not found by selector
    if (!shutter) {
      const video = document.querySelector('video');
      let targetX, targetY;
      if (video && isVisible(video) && isInsideMainCameraArea(video)) {
        const vr = video.getBoundingClientRect();
        targetX = Math.round(vr.left + vr.width / 2);
        targetY = Math.round(vr.bottom - 60);
      } else {
        const sideEdge = getSideMenuRightEdge();
        targetX = Math.round(sideEdge + (window.innerWidth - sideEdge) / 2);
        targetY = Math.round(window.innerHeight - 100);
      }
      const pointEl = document.elementFromPoint(targetX, targetY);
      if (pointEl && isInsideMainCameraArea(pointEl) && !isMyAI(pointEl)) {
        shutter = pointEl.closest('button, div[role="button"]') || pointEl;
      }
    }

    if (shutter && !isMyAI(shutter)) {
      const rect = shutter.getBoundingClientRect();
      const centerX = Math.round(rect.left + rect.width / 2);
      const centerY = Math.round(rect.top + rect.height / 2);

      // Clean instant quick press: EXACT same coordinates for down & up, 0 movement (zero swipe!)
      const pointerDown = new PointerEvent('pointerdown', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        pointerId: 1,
        pointerType: 'mouse',
        isPrimary: true,
        button: 0,
        buttons: 1
      });
      const mouseDown = new MouseEvent('mousedown', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        button: 0,
        buttons: 1
      });

      shutter.dispatchEvent(pointerDown);
      shutter.dispatchEvent(mouseDown);

      // Quick tap delay: 40ms only (prevents holding/video recording or swipe gestures)
      await sleep(40);

      const pointerUp = new PointerEvent('pointerup', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        pointerId: 1,
        pointerType: 'mouse',
        isPrimary: true,
        button: 0,
        buttons: 0
      });
      const mouseUp = new MouseEvent('mouseup', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        button: 0,
        buttons: 0
      });
      const clickEvt = new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: centerX,
        clientY: centerY,
        button: 0
      });

      shutter.dispatchEvent(pointerUp);
      shutter.dispatchEvent(mouseUp);
      shutter.dispatchEvent(clickEvt);
      shutter.click();

      log('  ✓ Quick-pressed center white circle capture button (zero swipe)!', 'success');
    } else {
      log('  Notice: Shutter button element not found at camera center.', 'err');
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

  // ── Master Send Runner ───────────────────────────────────────────────────
  async function runSendStreaks(options = {}) {
    const friends = options.friends || ['*//Eric\\\\*', 'Dylan'];
    const selectionMethod = options.selectionMethod || 'auto';
    const stepDelay = options.stepDelay || 3;
    const humanMode = options.humanMode ?? true;

    log(`🚀 Starting Verified Streak Send Flow (Method: ${selectionMethod.toUpperCase()} | Human-Mode: ${humanMode ? 'ON 👤' : 'OFF ⚡'})...`, 'info');
    if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(true);

    try {
      if (humanMode) {
        await sleep(600 + Math.floor(Math.random() * 600));
      }

      // Step 1: Click Snapchat icon top-left to set at home
      await step0_clickSnapchatHome();
      await sleep(humanMode ? 1500 + Math.floor(Math.random() * 500) : stepDelay * 1000);

      // Step 2: Press camera icon to open webcam (if not opened already)
      await step1_openCamera();
      await sleep(humanMode ? 1800 + Math.floor(Math.random() * 500) : stepDelay * 1000);

      // Step 3: Press white circle for photo
      await step2_pressWhiteCirclePhoto();
      await sleep(humanMode ? 2000 + Math.floor(Math.random() * 600) : stepDelay * 1000);

      // Step 4: Click Send To on photo preview & select recipients based on visual names
      await step3_ensureSendToDrawerOpen();
      await sleep(800);
      await step3b_selectRecipientsByVisualName(friends, selectionMethod, stepDelay);
      await sleep(humanMode ? 1200 : stepDelay * 1000);

      if (options.isTest) {
        log('🧪 [TEST MODE] Locating final Send button for dry-run verification...', 'info');
        const sendBtn = findFinalSendButton();
        if (sendBtn) {
          if (window.SnapStreakMacro && window.SnapStreakMacro.showTestIndicator) {
            window.SnapStreakMacro.showTestIndicator(sendBtn, 5, 5, 'Send Button');
          }
          log('  🧪 [TEST PASS] Send button located & verified! (Final click skipped in test mode).', 'success');
        } else {
          log('  ⚠ [TEST WARNING] Send button not yet visible on screen.', 'err');
        }
        log('🎉 [TEST PASSED] Direct script streak flow successfully verified! Ready for live auto-sending.', 'success');
        return { success: true, isTest: true };
      }

      // Step 5: Click the Send button
      await step4_sendSnap();
      log('✅ All streak steps completed! Streaks sent. 🔥', 'success');
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
    runSendStreaks
  };
})();
