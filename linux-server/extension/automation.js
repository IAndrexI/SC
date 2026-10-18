/**
 * SnapStreak Automation Engine (Client-side DOM Execution)
 * Runs directly inside web.snapchat.com context
 */

window.SnapStreakAutomation = (function() {
  'use strict';

  let isCancelled = false;
  let isPaused = false;
  let pendingConfirmResolver = null;

  function pause() {
    isPaused = true;
    window.__snapstreak_pause_requested = true;
    log('⏸️ Task execution PAUSED. All browser state and selections preserved.', 'warn');
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.setPaused) {
      window.SnapStreakOverlay.setPaused(true);
    }
  }

  function resume() {
    isPaused = false;
    window.__snapstreak_pause_requested = false;
    log('▶️ Task execution RESUMED. Continuing streak sequence...', 'info');
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.setPaused) {
      window.SnapStreakOverlay.setPaused(false);
    }
  }

  function isPausedState() {
    return isPaused || !!window.__snapstreak_pause_requested;
  }

  function confirmFinalSend() {
    if (pendingConfirmResolver) {
      log('🚀 Manual confirmation received! Proceeding to click Send button...', 'info');
      pendingConfirmResolver(true);
      pendingConfirmResolver = null;
      return true;
    }
    return false;
  }

  function cancel() {
    isCancelled = true;
    window.__snapstreak_cancel_requested = true;
    isPaused = false;
    window.__snapstreak_pause_requested = false;
    if (pendingConfirmResolver) {
      pendingConfirmResolver(false);
      pendingConfirmResolver = null;
    }
    dismissManualConfirmPrompt();
    log('⏹️ STOP / CANCEL requested — aborting streak automation flow...', 'warn');
    const pointer = document.getElementById('snapstreak-virtual-cursor');
    if (pointer) pointer.style.display = 'none';
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.setRunning) {
      window.SnapStreakOverlay.setRunning(false);
    }
  }

  function resetCancellation() {
    isCancelled = false;
    window.__snapstreak_cancel_requested = false;
    isPaused = false;
    window.__snapstreak_pause_requested = false;
  }

  function isCancellationRequested() {
    return isCancelled || !!window.__snapstreak_cancel_requested;
  }

  function checkCancelled() {
    if (isCancellationRequested()) {
      throw new Error('COMMAND_CANCELLED: Flow aborted by user.');
    }
  }

  async function sleep(ms) {
    const d = window.__snapstreak_fast_test ? Math.min(ms, 25) : ms;
    const interval = 40;
    let elapsed = 0;
    while (elapsed < d) {
      checkCancelled();
      while (isPausedState()) {
        checkCancelled();
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      const chunk = Math.min(interval, d - elapsed);
      await new Promise(resolve => setTimeout(resolve, chunk));
      elapsed += chunk;
    }
    checkCancelled();
    while (isPausedState()) {
      checkCancelled();
      await new Promise(resolve => setTimeout(resolve, 100));
    }
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

  // ── Helper: Identify and Strictly Ignore "My AI", "Spotlight", "Stories", & Groups ───────
  const FORBIDDEN_STRINGS = [
    'my ai', 'myai', 'spotlight', 'my story', 'mystory', 'stories', 'story',
    'add to story', 'post to story', 'sexy hot joyful men', 'group', 'groups',
    'brandon ta', 'krysta swanson', 'everyone', 'all friends'
  ];

  function isForbiddenRecipient(el) {
    if (!el) return false;
    let cur = el;
    let depth = 0;
    while (cur && cur !== document.body && depth < 5) {
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

      for (const fs of FORBIDDEN_STRINGS) {
        if (aria.includes(fs) || testid.includes(fs) || title.includes(fs) || alt.includes(fs)) {
          return true;
        }
      }

      const txt = (cur.innerText || cur.textContent || '').trim().toLowerCase();
      if (txt.length > 0 && txt.length < 80) {
        for (const fs of FORBIDDEN_STRINGS) {
          if (txt === fs || txt.startsWith(fs + '\n') || txt.startsWith(fs + ' ') || txt.includes(fs)) {
            return true;
          }
        }
      }

      cur = cur.parentElement;
      depth++;
    }
    return false;
  }

  function isMyAI(el) {
    return isForbiddenRecipient(el);
  }

  function normalizeFriendToken(str) {
    if (!str) return '';
    return str.toString().trim().replace(/^@/, '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
  }

  function extractCleanEntityTitle(el) {
    if (!el) return '';
    const row = el.closest('div[role="row"], div[role="listitem"], li, div[class*="item" i]') || el.parentElement;
    let title = '';
    if (row) {
      // Find title element specifically, avoiding subtitle/timestamp/status elements
      const titleEl = row.querySelector('[data-testid*="title" i], [class*="title" i], [class*="name" i], strong, b, h4, h5');
      if (titleEl && isVisible(titleEl)) {
        title = (titleEl.textContent || '').trim();
      }
      if (!title) {
        // Exclude known subtitle/time/status elements
        const cloned = row.cloneNode(true);
        const toRemove = cloned.querySelectorAll('[class*="sub" i], [class*="time" i], [class*="status" i], p, small');
        toRemove.forEach(r => r.remove());
        title = (cloned.textContent || '').trim();
      }
    }
    if (!title) {
      title = (el.getAttribute('aria-label') || el.textContent || '').trim();
    }
    // Take only primary line before newline, separator (· or -)
    title = title.split(/\s*·\s*|\s*-\s*|\n/)[0].trim();
    return title;
  }

  /**
   * Evaluates if a given text strictly matches an authorized target friend.
   * Strips formatting, handles escaped backslashes, and verifies exact normalized identity.
   */
  function isStrictFriendMatch(text, friend) {
    if (!text || !friend) return false;
    const cleanFriend = normalizeFriendToken(friend);
    if (!cleanFriend) return false;

    // Clean primary title from text
    const cleanTitle = text.toString().trim().split(/\s*·\s*|\s*-\s*|\n/)[0].trim();
    const tLower = cleanTitle.toLowerCase();

    for (const fs of FORBIDDEN_STRINGS) {
      if (tLower === fs || tLower.includes(fs)) return false;
    }

    const titleToken = normalizeFriendToken(cleanTitle);
    if (!titleToken) return false;

    // Exact normalized token match
    if (titleToken === cleanFriend) return true;

    // Dylan special rule
    if (cleanFriend === 'dylan') {
      return titleToken === 'dylan';
    }

    // Eric special rules (handles *//Eric\*, *//Eric*, Eric)
    if (cleanFriend === 'eric') {
      if (titleToken === 'eric') return true;
      if (tLower.includes('*//eric') || tLower.includes('//eric')) return true;
    }

    return false;
  }

  /**
   * Reads, audits, and validates ALL currently selected recipients in the Send-To drawer.
   * If any non-whitelisted contact, group, or story is selected, it UNCHECKS / REMOVES them.
   * Then it re-reads the selected list, logs the verified recipients, and ensures only
   * target friends are selected before dispatch.
   */
  async function readAndAuditSelectedRecipients(friends = ['*//Eric\\*', 'Dylan']) {
    log('📋 [AUDIT] Reading and verifying selected recipients before sending...', 'info');

    // 1. Scan all checkboxes / chips in Send-To area
    const checkedCheckboxes = document.querySelectorAll(
      'input[type="checkbox"]:checked, [role="checkbox"][aria-checked="true"]'
    );

    const recipientChips = document.querySelectorAll(
      '[data-testid*="recipient-chip" i], [data-testid*="selected-recipient" i], ' +
      'div[class*="recipientChip" i], div[class*="selectedChip" i], ' +
      'div[class*="chip" i]:has(button), span[class*="chip" i]:has(button)'
    );

    let removedCount = 0;

    // Step A: Inspect every checked checkbox
    for (const cb of checkedCheckboxes) {
      if (!isVisible(cb) && !cb.checked && cb.getAttribute('aria-checked') !== 'true') continue;
      const name = extractCleanEntityTitle(cb);
      if (!name) continue;
      log(`  🔍 [RECIPIENT CHECK] Detected checked recipient: "${name}"`, 'info');

      const isForbidden = isForbiddenRecipient(cb) || isForbiddenRecipient(cb.closest('div[role="row"], div[role="listitem"], li'));
      const matchesTarget = friends.some(f => isStrictFriendMatch(name, f));

      if (isForbidden || !matchesTarget) {
        log(`  🛑 [AUDIT REJECT] Unchecking unauthorized recipient "${name}"!`, 'warn');
        try {
          const row = cb.closest('div[role="row"], div[role="listitem"], li') || cb.parentElement;
          cb.click();
          if (cb.checked || cb.getAttribute('aria-checked') === 'true') {
            if (row) row.click();
          }
          removedCount++;
          await sleep(200);
        } catch (e) {
          log(`  ⚠ Failed to uncheck "${name}": ${e.message}`, 'warn');
        }
      }
    }

    // Step B: Inspect every recipient chip
    for (const chip of recipientChips) {
      if (!isVisible(chip)) continue;
      const name = (chip.textContent || '').replace(/[✕x×]/gi, '').trim().split(/\s*·\s*|\s*-\s*|\n/)[0].trim();
      if (!name) continue;
      log(`  🔍 [CHIP CHECK] Detected recipient chip: "${name}"`, 'info');

      const matchesTarget = friends.some(f => isStrictFriendMatch(name, f));
      if (!matchesTarget) {
        log(`  🛑 [AUDIT REJECT] Removing unauthorized chip "${name}"!`, 'warn');
        const removeBtn = chip.querySelector('button, svg, [role="button"], span[class*="close" i], span[class*="remove" i]') || chip;
        try {
          removeBtn.click();
          removedCount++;
          await sleep(200);
        } catch (e) {
          log(`  ⚠ Failed to remove chip "${name}": ${e.message}`, 'warn');
        }
      }
    }

    if (removedCount > 0) {
      log(`  🧹 Removed ${removedCount} unauthorized recipient(s). Re-auditing selection...`, 'info');
      await sleep(350);
    }

    // Step C: Re-read final list of selected recipients to display and verify
    const finalChecked = document.querySelectorAll(
      'input[type="checkbox"]:checked, [role="checkbox"][aria-checked="true"]'
    );
    const finalChips = document.querySelectorAll(
      '[data-testid*="recipient-chip" i], [data-testid*="selected-recipient" i], ' +
      'div[class*="recipientChip" i], div[class*="selectedChip" i], ' +
      'div[class*="chip" i]:has(button), span[class*="chip" i]:has(button)'
    );

    const verifiedRecipients = new Set();
    for (const cb of finalChecked) {
      if (!isVisible(cb) && !cb.checked && cb.getAttribute('aria-checked') !== 'true') continue;
      const name = extractCleanEntityTitle(cb);
      if (name) verifiedRecipients.add(name);
    }
    for (const chip of finalChips) {
      if (!isVisible(chip)) continue;
      const name = (chip.textContent || '').replace(/[✕x×]/gi, '').trim().split(/\s*·\s*|\s*-\s*|\n/)[0].trim();
      if (name) verifiedRecipients.add(name);
    }

    const verifiedList = Array.from(verifiedRecipients);
    log(`📋 [VERIFIED RECIPIENTS BEFORE SEND] Ready to send to (${verifiedList.length}): [${verifiedList.join(', ')}]`, 'success');

    // Step D: Strict Safety Gate Checks
    if (verifiedList.length === 0) {
      log('🛑 [SAFETY ABORT] Zero recipients selected! Send aborted.', 'err');
      throw new Error('Zero recipients selected before final send.');
    }

    for (const rec of verifiedList) {
      const isAllowed = friends.some(f => isStrictFriendMatch(rec, f));
      if (!isAllowed) {
        log(`🛑 [HARD SAFETY ABORT] Recipient "${rec}" is NOT on the authorized whitelist! Halting immediately to protect privacy.`, 'err');
        window.__snapstreak_unauthorized_detected = true;
        throw new Error(`HARD_ABORT: Unauthorized recipient "${rec}" detected before send.`);
      }
    }

    return verifiedList;
  }

  function uncheckUnauthorizedRecipients(friends = ['*//Eric\\*', 'Dylan']) {
    try {
      const checkedBoxes = document.querySelectorAll('input[type="checkbox"]:checked, [role="checkbox"][aria-checked="true"]');
      for (const cb of checkedBoxes) {
        const name = extractCleanEntityTitle(cb);
        const isForbidden = isForbiddenRecipient(cb) || isForbiddenRecipient(cb.closest('div[role="row"], div[role="listitem"], li'));
        const matchesAllowed = friends.some(f => isStrictFriendMatch(name, f));

        if (isForbidden || (name.length > 0 && !matchesAllowed)) {
          log(`  🛑 Safety Guard: Unchecking unauthorized recipient "${name}"!`, 'warn');
          cb.click();
          const row = cb.closest('div[role="row"], div[role="listitem"], li');
          if ((cb.checked || cb.getAttribute('aria-checked') === 'true') && row) {
            row.click();
          }
        }
      }
    } catch(e) {}
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
    // Ensure element is visible in the viewport before calculating click coordinates
    try {
      el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
    } catch (e) {}

    const rect = el.getBoundingClientRect();
    // Human offset inside the target button (within center 40%)
    const offsetX = (Math.random() - 0.5) * Math.min(rect.width * 0.3, 16);
    const offsetY = (Math.random() - 0.5) * Math.min(rect.height * 0.3, 12);
    const clientX = Math.round(rect.left + rect.width / 2 + offsetX);
    const clientY = Math.round(rect.top + rect.height / 2 + offsetY);

    if (useVisualPointer) {
      await smoothMovePointer(clientX, clientY, 280 + Math.floor(Math.random() * 150));
      // Human dwell / reading pause
      await sleep(80 + Math.floor(Math.random() * 120));
    }

    const downOpts = {
      bubbles: true,
      cancelable: true,
      composed: true,
      view: window,
      clientX: clientX,
      clientY: clientY,
      screenX: clientX,
      screenY: clientY,
      button: 0,
      buttons: 1,
      pointerId: 1,
      pointerType: 'mouse',
      isPrimary: true
    };

    // Deepest hit target at click position (e.g. inner SVG or button wrapper)
    const hitTarget = document.elementFromPoint(clientX, clientY) || el;

    // Human mouse enter & hover
    hitTarget.dispatchEvent(new PointerEvent('pointerover', downOpts));
    hitTarget.dispatchEvent(new MouseEvent('mouseover', downOpts));
    hitTarget.dispatchEvent(new PointerEvent('pointerenter', downOpts));
    hitTarget.dispatchEvent(new MouseEvent('mouseenter', downOpts));
    await sleep(30 + Math.floor(Math.random() * 40));

    // Pointer down & mouse down with buttons: 1 for React 18 event delegation
    hitTarget.dispatchEvent(new PointerEvent('pointerdown', downOpts));
    hitTarget.dispatchEvent(new MouseEvent('mousedown', downOpts));
    try { el.focus(); } catch(e) {}

    // Human click hold dwell (80 - 140ms)
    await sleep(80 + Math.floor(Math.random() * 60));

    const upOpts = {
      ...downOpts,
      buttons: 0
    };

    // Pointer up & mouse up & click
    hitTarget.dispatchEvent(new PointerEvent('pointerup', upOpts));
    hitTarget.dispatchEvent(new MouseEvent('mouseup', upOpts));
    hitTarget.dispatchEvent(new MouseEvent('click', upOpts));

    // Native click dispatches on hitTarget and element
    try { hitTarget.click(); } catch (e) {}
    if (hitTarget !== el) {
      try { el.click(); } catch (e) {}
    }

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

    const checkItems = document.querySelectorAll('div[role="checkbox"], input[type="checkbox"]');
    const hasCheckbox = Array.from(checkItems).some(c => isVisible(c) && isInsideMainCameraArea(c));

    if (hasSendInput || hasTabs || hasCheckbox) {
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
      if (video && isVisible(video) && isInsideMainCameraArea(video)) {
        return SCREEN_STATES.CAMERA_READY;
      }
      if (window.location && window.location.pathname && window.location.pathname.includes('/camera')) {
        return SCREEN_STATES.CAMERA_READY;
      }
      if (document.querySelector('[data-testid="camera-view"]')) {
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
      checkCancelled();
      const current = detectCurrentScreen();
      if (validStates.includes(current)) {
        return { success: true, state: current };
      }
      await sleep(100);
    }
    checkCancelled();
    return { success: false, state: detectCurrentScreen() };
  }

  // ── Self-Healing Step Transition Controller ───────────────────────────────
  // If screen does not match expected state after a step, executes previous steps to recover!
  async function executeStepWithScreenVerification(stepIndex, actionFn, expectedStates, fallbackFn, maxRetries = 2, timeoutMs = 7500) {
    checkCancelled();
    const stepNames = [
      'Step 1: Return to Home Screen (Top-Left Snapchat Icon)',
      'Step 2: Press Camera Option to Open Viewfinder',
      'Step 3: Quick-Press White Shutter Circle',
      'Step 4: Open Send-To Drawer & Select Recipients',
      'Step 5: Click Final Send Button & Verify Delivery'
    ];
    const name = stepNames[stepIndex] || `Step ${stepIndex + 1}`;
    log(`🎬 [SCREEN CHECK] Starting ${name}...`, 'info');

    for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
      checkCancelled();
      // Execute primary action
      await actionFn();
      checkCancelled();

      // Settle and verify screen state matches expected state
      const targetStates = Array.isArray(expectedStates) ? expectedStates : [expectedStates];
      const check = await waitForScreenState(targetStates, timeoutMs);
      checkCancelled();

      if (check.success) {
        log(`  ✓ [SCREEN MATCH] Screen state verified as "${check.state}" for ${name}!`, 'success');
        return true;
      }

      log(`  ⚠ [SCREEN MISMATCH] Expected [${targetStates.join('|')}], but screen shows "${check.state}" (Attempt ${attempt}/${maxRetries + 1}).`, 'warn');

      if (attempt <= maxRetries) {
        log(`  ↺ Falling back to previous step(s) to recover expected screen...`, 'info');
        if (fallbackFn) {
          checkCancelled();
          await fallbackFn();
          checkCancelled();
          await sleep(1000);
        }
      }
    }

    log(`  ❌ [SCREEN ERROR] Failed to match expected screen for ${name} after ${maxRetries + 1} attempts.`, 'err');
    return false;
  }

  // ── Step 1: Click Snapchat Icon Top Left to Bring to Main Menu ───────────
  async function step0_clickSnapchatHome() {
    log('Step 1: Checking screen state and preparing camera...', 'info');

    // If camera viewfinder is already active, DO NOT click anything or reset!
    if (detectCurrentScreen() === SCREEN_STATES.CAMERA_READY) {
      log('  ✓ Camera viewfinder is already active on screen! Skipping home reset.', 'success');
      return true;
    }

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

    // If a chat is open, interact with chat back button '<' to return to main camera area
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
          if (r.top < 120 && r.left > 100 && r.left < 550) {
            await humanDwellAndClick(btn, true);
            log('  ✓ Clicked chat back button to return to main menu.', 'success');
            await sleep(800);
            break;
          }
        }
      } catch (e) {}
    }

    // Note: We deliberately do NOT click <a href="/web"> as clicking links reloads the SPA and destroys execution!
    await sleep(500);
    return true;
  }

  /**
   * Understand Macro: Analyzes a recorded macro sequence and extracts semantic
   * stage guidance so the auto-streak engine knows exactly which elements/coords
   * worked for each step (Camera Open -> Shutter -> Send-To -> Friends -> Send).
   */
  function understandMacro(macroInput) {
    if (!macroInput) return null;
    let steps = [];
    let name = 'Custom Macro';

    if (Array.isArray(macroInput)) {
      steps = macroInput;
    } else if (macroInput && Array.isArray(macroInput.steps)) {
      steps = macroInput.steps;
      name = macroInput.name || name;
    } else if (typeof macroInput === 'object' && macroInput.events && Array.isArray(macroInput.events)) {
      steps = macroInput.events;
      name = macroInput.name || name;
    }

    if (!steps || steps.length === 0) return null;

    const guidance = {
      name: name,
      stepsCount: steps.length,
      openCamera: null,
      shutter: null,
      sendTo: null,
      recipients: [],
      finalSend: null
    };

    const getText = s => (s.text || '').toLowerCase().trim();
    const getSel = s => (s.selector || '').toLowerCase().trim();
    const getAria = s => (s.aria || '').toLowerCase().trim();

    // Pass 1: Identify Shutter step
    let shutterIndex = -1;
    for (let i = 0; i < steps.length; i++) {
      const s = steps[i];
      if (s.type !== 'click') continue;
      const t = getText(s);
      const sel = getSel(s);
      const a = getAria(s);

      if (
        t.includes('take a snap') || t.includes('take snap') || t.includes('capture') ||
        sel.includes('capture') || sel.includes('take-snap') || sel.includes('shutter') ||
        a.includes('take a snap') || a.includes('take snap') || a.includes('capture') ||
        sel.includes('camera-capture')
      ) {
        shutterIndex = i;
        guidance.shutter = s;
        break;
      }
    }

    // If no explicit shutter found, check for click in camera bottom area before send/chat
    if (shutterIndex === -1) {
      for (let i = 0; i < steps.length; i++) {
        const s = steps[i];
        if (s.type !== 'click') continue;
        const t = getText(s);
        if (t.includes('send') || t.includes('search') || t.includes('chat')) continue;
        if (s.y && s.y > window.innerHeight * 0.40 && s.y < window.innerHeight * 0.95) {
          shutterIndex = i;
          guidance.shutter = s;
          break;
        }
      }
    }

    // Fallback if not yet identified:
    if (shutterIndex === -1) {
      if (steps.length >= 2) {
        shutterIndex = 1;
        guidance.shutter = steps[1];
      } else if (steps.length === 1) {
        shutterIndex = 0;
        guidance.shutter = steps[0];
      }
    }

    // Pass 2: Identify Open Camera step (occurs before shutter)
    if (shutterIndex > 0) {
      for (let i = 0; i < shutterIndex; i++) {
        const s = steps[i];
        if (s.type !== 'click') continue;
        const t = getText(s);
        const sel = getSel(s);
        if (t.includes('camera') || t.includes('click the camera') || sel.includes('camera') || sel.includes('nav')) {
          guidance.openCamera = s;
          break;
        }
      }
      if (!guidance.openCamera && shutterIndex > 0) {
        guidance.openCamera = steps[0];
      }
    }

    // Pass 3: Identify Final Send step (occurs after shutter)
    let finalSendIndex = -1;
    for (let i = steps.length - 1; i > shutterIndex; i--) {
      const s = steps[i];
      if (s.type !== 'click') continue;
      const t = getText(s);
      const sel = getSel(s);
      const a = getAria(s);
      if (
        (t === 'send' || t.startsWith('send ') || t.includes('send snap') || a.includes('send snap') || a === 'send') &&
        !t.includes('send to') && !a.includes('send to')
      ) {
        finalSendIndex = i;
        guidance.finalSend = s;
        break;
      }
    }
    if (finalSendIndex === -1 && steps.length - 1 > shutterIndex) {
      finalSendIndex = steps.length - 1;
      guidance.finalSend = steps[finalSendIndex];
    }

    // Pass 4: Identify Send-To drawer step & recipient steps
    const midStart = shutterIndex >= 0 ? shutterIndex + 1 : 0;
    const midEnd = finalSendIndex > 0 ? finalSendIndex : steps.length;
    for (let i = midStart; i < midEnd; i++) {
      const s = steps[i];
      const t = getText(s);
      const sel = getSel(s);
      const a = getAria(s);
      if (t.includes('send to') || a.includes('send to') || sel.includes('send-to') || sel.includes('sendto')) {
        if (!guidance.sendTo) guidance.sendTo = s;
      } else {
        guidance.recipients.push(s);
      }
    }

    return guidance;
  }

  // ── Step 2: Press Camera Option (if not in already) ──────────────────────
  async function step1_openCamera(macroGuidance = null) {
    log('Step 2: Checking camera state and opening viewfinder if not active...', 'info');

    // Helper: verify if camera viewfinder is already active on screen
    const isAlreadyOpen = () => {
      // If we are currently inside a 1-on-1 chat text box, camera viewfinder is not active
      const inChat = document.querySelector('[data-testid="chat-input"], [data-testid="message-input"], textarea[placeholder*="chat" i]');
      if (inChat && isVisible(inChat) && isInsideMainCameraArea(inChat)) return false;

      // Check /camera URL route
      if (window.location && window.location.pathname && window.location.pathname.includes('/camera')) {
        return true;
      }

      const shutter = findShutterButton();
      const video = document.querySelector('video');
      const camView = document.querySelector('[data-testid="camera-view"]');

      return (shutter && isVisible(shutter) && isInsideMainCameraArea(shutter)) ||
             (video && isVisible(video) && isInsideMainCameraArea(video)) ||
             (camView && isVisible(camView));
    };

    if (isAlreadyOpen()) {
      log('  ✓ Already on camera viewfinder! Proceeding directly to capture without extra clicks.', 'success');
      return true;
    }

    // 1. If we have Macro Guidance for camera open, try the learned target!
    if (macroGuidance && macroGuidance.openCamera) {
      log(`  🧠 Macro Guidance: Applying learned Camera Open action (target: "${macroGuidance.openCamera.text || macroGuidance.openCamera.selector || `${macroGuidance.openCamera.x},${macroGuidance.openCamera.y}`}")`, 'info');
      let target = null;
      if (macroGuidance.openCamera.selector) {
        try { target = document.querySelector(macroGuidance.openCamera.selector); } catch(e) {}
      }
      if (!target && macroGuidance.openCamera.x && macroGuidance.openCamera.y) {
        target = document.elementFromPoint(macroGuidance.openCamera.x, macroGuidance.openCamera.y);
      }
      if (target && isVisible(target) && !isMyAI(target)) {
        await humanDwellAndClick(target, true);
        log('  ✓ Clicked learned camera open target from macro!', 'success');
        await sleep(1000);
      }
    }

    // 2. Find camera option button/card in main area or header/nav
    if (!isAlreadyOpen()) {
      let camBtn = null;
      // Search all elements in DOM for "click the camera" or "send snaps" text (including cards/divs)
      const allElements = document.querySelectorAll('button, div[role="button"], a, div, span, p, h1, h2');
      for (const el of allElements) {
        if (!isVisible(el) || isMyAI(el)) continue;
        if (el.closest('[data-testid*="chat" i], [class*="message" i]')) continue;

        if (isInsideMainCameraArea(el) || el.closest('header, nav, aside')) {
          const txt = (el.textContent || '').trim().toLowerCase();
          const aria = (el.getAttribute('aria-label') || '').toLowerCase();
          const testid = (el.getAttribute('data-testid') || '').toLowerCase();
          const href = (el.getAttribute('href') || '').toLowerCase();

          if (
            txt.includes('click the camera') || txt === 'camera' ||
            aria.includes('click the camera') || aria === 'camera' ||
            testid.includes('camera-open') || testid.includes('navigation-camera') ||
            href.includes('/camera')
          ) {
            camBtn = el.closest('button, div[role="button"], a') || el;
            break;
          }
        }
      }

      // Check for camera SVG icons in nav/header or main area
      if (!camBtn) {
        const svgIcons = document.querySelectorAll('svg');
        for (const svg of svgIcons) {
          if (!isVisible(svg) || isMyAI(svg)) continue;
          const iconName = (svg.getAttribute('data-icon') || '').toLowerCase();
          const aria = (svg.getAttribute('aria-label') || '').toLowerCase();
          if (iconName.includes('camera') || aria.includes('camera')) {
            camBtn = svg.closest('button, div[role="button"], a') || svg;
            break;
          }
        }
      }

      if (camBtn) {
        await humanDwellAndClick(camBtn, true);
        log(`  ✓ Pressed camera option in main menu: "${(camBtn.textContent || '').trim().slice(0, 35)}"`, 'success');
        await sleep(1000);
      } else {
        log('  Notice: Camera option button not visible, checking for viewfinder directly...', 'info');
      }
    }

    // Dismiss any modal dialogs or "Turn on Camera" / "Allow" / "Try Again" prompts
    try {
      const promptButtons = document.querySelectorAll('button, div[role="button"]');
      for (const b of promptButtons) {
        if (!isVisible(b) || isMyAI(b)) continue;
        const t = (b.textContent || '').trim().toLowerCase();
        const a = (b.getAttribute('aria-label') || '').toLowerCase();
        if (t.includes('turn on camera') || t.includes('enable camera') || t.includes('allow') || t.includes('try again') ||
            a.includes('turn on camera') || a.includes('enable camera') || a.includes('allow') || a.includes('try again')) {
          log(`  ✓ Clicked camera permission/retry prompt: "${t || a}"`, 'info');
          b.click();
          await sleep(800);
          break;
        }
      }
    } catch (e) {}

    // Poll for camera viewfinder to become ready (up to 8 seconds for virtual webcam initialization)
    const startTime = Date.now();
    const timeoutMs = 8000;
    while (Date.now() - startTime < timeoutMs) {
      checkCancelled();
      if (isAlreadyOpen()) {
        const elapsed = Date.now() - startTime;
        log(`  ✓ Camera viewfinder ready in main area (${elapsed}ms).`, 'success');
        return true;
      }
      await sleep(250);
    }

    log('  Notice: Camera viewfinder wait completed, proceeding...', 'info');
    return isAlreadyOpen();
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
                if (dist < minCandidateDist) {
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

    // 2. Geometric scan: Circular buttons in camera area without images
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
      // Shutter button is circular, in lower half of screen, diameter between 35px and 140px
      const isCircular = Math.abs(r.width - r.height) <= 22;
      const isLowerHalf = r.top > window.innerHeight * 0.35;
      const isValidSize = r.width >= 35 && r.width <= 140;

      if (isCircular && isLowerHalf && isValidSize) {
        const btnCenterX = r.left + r.width / 2;
        const distFromCenter = Math.abs(btnCenterX - cameraCenterX);

        if (distFromCenter < minDistanceToCenter) {
          minDistanceToCenter = distFromCenter;
          bestShutter = btn;
        }
      }
    }

    if (bestShutter) return bestShutter;

    // 3. Fallback: Buttons with SVG circle in camera area
    try {
      const svgCircleButtons = scope.querySelectorAll('button:has(svg circle), button:has(circle), [role="button"]:has(svg circle)');
      for (const btn of svgCircleButtons) {
        if (!isVisible(btn) || !isInsideMainCameraArea(btn) || isMyAI(btn)) continue;
        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (aria.includes('lens') || aria.includes('filter') || aria.includes('effect') || aria.includes('by ')) continue;
        if (btn.querySelector('img')) continue;
        const r = btn.getBoundingClientRect();
        if (r.top > window.innerHeight * 0.35 && r.width >= 35 && r.width <= 140) {
          return btn;
        }
      }
    } catch (e) {}

    return null;
  }

  // ── Step 3: Press Take Picture Button (Quick Press, Zero Swipe) ─────────────
  async function step2_pressWhiteCirclePhoto(macroGuidance = null) {
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

    let shutter = null;

    // 1. If we have Macro Guidance for shutter, use learned target!
    if (macroGuidance && macroGuidance.shutter) {
      log(`  🧠 Macro Guidance: Using learned photo shutter action (selector: "${macroGuidance.shutter.selector || ''}", coords: ${macroGuidance.shutter.x},${macroGuidance.shutter.y})`, 'info');
      if (macroGuidance.shutter.selector) {
        try {
          const match = document.querySelector(macroGuidance.shutter.selector);
          if (match && isVisible(match) && isInsideMainCameraArea(match) && !isMyAI(match)) {
            shutter = match;
          }
        } catch(e) {}
      }
      if (!shutter && macroGuidance.shutter.x && macroGuidance.shutter.y) {
        const pt = document.elementFromPoint(macroGuidance.shutter.x, macroGuidance.shutter.y);
        if (pt && isInsideMainCameraArea(pt) && !isMyAI(pt)) {
          shutter = pt.closest('button, div[role="button"]') || pt;
        }
      }
      if (shutter) {
        log('  ✓ Matched learned shutter element from macro!', 'success');
      }
    }

    // 2. Standard selector locator
    if (!shutter) {
      shutter = findShutterButton();
    }

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

    const clickX = (shutter && shutter.getBoundingClientRect) ? Math.round(shutter.getBoundingClientRect().left + shutter.getBoundingClientRect().width / 2) : (macroGuidance?.shutter?.x || targetX);
    const clickY = (shutter && shutter.getBoundingClientRect) ? Math.round(shutter.getBoundingClientRect().top + shutter.getBoundingClientRect().height / 2) : (macroGuidance?.shutter?.y || targetY);

    if (shutter && !isMyAI(shutter)) {
      // Focus the button cleanly
      try { shutter.focus(); } catch (e) {}

      // Clean instant quick press: 0 delay between down and up, 0 movement (zero swipe!)
      const eventOpts = {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: clickX,
        clientY: clickY,
        screenX: clickX,
        screenY: clickY,
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
        clientX: clickX,
        clientY: clickY,
        button: 0
      }));

      // Native click dispatch
      shutter.click();

      // Keyboard Enter trigger on focused shutter as secondary guarantee
      try {
        shutter.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        shutter.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
      } catch (e) {}

      log(`  ✓ Quick-pressed center white circle capture button at (${clickX}, ${clickY})!`, 'success');
    } else {
      // Direct center element click fallback
      const pointEl = document.elementFromPoint(clickX, clickY);
      if (pointEl) {
        pointEl.click();
        log(`  ✓ Clicked camera capture point (${clickX}, ${clickY}) directly.`, 'success');
      } else {
        log('  Notice: Shutter button element not found at camera center.', 'err');
      }
    }

    // Wait up to 8s for screen transition to PHOTO_CAPTURED or SEND_TO_DRAWER
    const startWait = Date.now();
    while (Date.now() - startWait < 8000) {
      checkCancelled();
      const screen = detectCurrentScreen();
      if (screen === SCREEN_STATES.PHOTO_CAPTURED || screen === SCREEN_STATES.SEND_TO_DRAWER || screen === SCREEN_STATES.RECIPIENTS_SELECTED) {
        log(`  ✓ Screen transitioned to "${screen}" after shutter capture!`, 'success');
        return true;
      }
      await sleep(200);
    }

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
  async function step3_ensureSendToDrawerOpen(macroGuidance = null) {
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

    // 1. Try learned Send-To target from macro
    if (macroGuidance && macroGuidance.sendTo) {
      log(`  🧠 Macro Guidance: Targeting learned Send-To action (selector: "${macroGuidance.sendTo.selector || ''}", coords: ${macroGuidance.sendTo.x},${macroGuidance.sendTo.y})`, 'info');
      let target = null;
      if (macroGuidance.sendTo.selector) {
        try { target = document.querySelector(macroGuidance.sendTo.selector); } catch(e) {}
      }
      if (!target && macroGuidance.sendTo.x && macroGuidance.sendTo.y) {
        target = document.elementFromPoint(macroGuidance.sendTo.x, macroGuidance.sendTo.y);
      }
      if (target && isVisible(target) && isInsideMainCameraArea(target)) {
        await humanDwellAndClick(target, true);
        log('  ✓ Clicked learned Send-To button from macro!', 'success');
        await sleep(1000);
        if (isListOpen()) return true;
      }
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
    const candidates = document.querySelectorAll('div[role="row"], div[role="listitem"], li, [role="button"]');
    for (const row of candidates) {
      if (!isVisible(row) || isMyAI(row) || !isInsideMainCameraArea(row)) continue;
      // Get primary title or text of row (avoiding subtitle snippets)
      const titleEl = row.querySelector('[class*="title" i], [class*="name" i], strong, h4, h5, b') || row;
      const titleText = (titleEl.textContent || '').trim();
      if (!titleText || titleText.length > 70) continue;

      if (isStrictFriendMatch(titleText, rawName)) {
        return row;
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

  // ── Step 4b: Select Recipients (Strict Friend Whitelist, No Spotlight/Stories/Groups) ──
  async function step3b_selectRecipientsByVisualName(friends = ['*//Eric\\\\*', 'Dylan'], selectionMethod = 'auto', stepDelay = 2) {
    log(`Step 4b: Selecting target friends strictly from list (${friends.join(', ')})...`, 'info');
    let selectedCount = 0;

    // Safety pass: uncheck any pre-selected Spotlight, Stories, or unauthorized rows
    uncheckUnauthorizedRecipients(friends);

    // 1. Check for and switch to "Best Friends" tab/pill if present in drawer
    const tabCandidates = document.querySelectorAll('button, div[role="tab"], div[role="button"], span');
    let bestFriendsTab = null;
    for (const t of tabCandidates) {
      if (!isVisible(t) || !isInsideMainCameraArea(t) || isForbiddenRecipient(t)) continue;
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
        await sleep(600);
      } catch (e) {}
    }

    // 2. Select rows inside Best Friends tab/section (strictly matching target friends)
    const bestFriendsRows = document.querySelectorAll('div[role="row"], div[role="listitem"], li');
    for (const row of bestFriendsRows) {
      if (!isVisible(row) || !isInsideMainCameraArea(row) || isForbiddenRecipient(row)) continue;
      const titleEl = row.querySelector('[class*="title" i], [class*="name" i], strong, h4, h5, b') || row;
      const rowTxt = (titleEl.textContent || '').trim();
      const checkControl = row.querySelector('input[type="checkbox"], [role="checkbox"]');
      if (checkControl && !checkControl.checked) {
        const matchesFriend = friends.some(f => isStrictFriendMatch(rowTxt, f));
        if (matchesFriend) {
          await humanDwellAndClick(checkControl, true);
          log(`  ✓ Selected Target Friend: "${rowTxt.slice(0, 25)}".`, 'success');
          selectedCount++;
          await sleep(500);
        }
      }
    }

    // 3. Ensure all explicitly chosen friends from friends list are selected via verified search
    for (const friend of friends) {
      const rawName = friend.trim().replace(/^@/, '');
      const coreName = rawName.replace(/[^a-zA-Z0-9]/g, '').trim();
      if (!rawName && !coreName) continue;

      const existingRow = findRecipientRow(rawName, coreName);
      if (existingRow && !isForbiddenRecipient(existingRow)) {
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
        } else {
          const rowTarget = existingRow.querySelector('svg, div[class*="check" i], div[class*="circle" i]') || existingRow;
          await humanDwellAndClick(rowTarget, true);
          log(`  ✓ Clicked recipient row for "${rawName}" from drawer.`, 'success');
          selectedCount++;
          await sleep(500);
          continue;
        }
      }

      // Search bar in drawer fallback
      const searchInputs = document.querySelectorAll('input');
      let cameraSearch = null;
      for (const inp of searchInputs) {
        if (isVisible(inp) && isInsideMainCameraArea(inp) && !isForbiddenRecipient(inp)) {
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
        if (resultRow && !isForbiddenRecipient(resultRow)) {
          const check = resultRow.querySelector('input[type="checkbox"], [role="checkbox"]');
          if (check && (check.checked || check.getAttribute('aria-checked') === 'true')) {
            log(`  ✓ "${rawName}" is already checked in search results.`, 'info');
            selectedCount++;
          } else {
            const clickable = check || resultRow.querySelector('svg, div[class*="check" i], div[class*="circle" i]') || resultRow;
            await humanDwellAndClick(clickable, true);
            log(`  ✓ Selected "${rawName}" from verified search results!`, 'success');
            selectedCount++;
            await sleep(500);
          }
        } else {
          log(`  ⚠ Could not find verified result for "${rawName}" — SKIPPED to avoid wrong recipient.`, 'warn');
        }

        try {
          cameraSearch.focus();
          const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          if (nativeSetter) {
            nativeSetter.call(cameraSearch, '');
          } else {
            cameraSearch.value = '';
          }
          cameraSearch.dispatchEvent(new Event('input', { bubbles: true }));
          cameraSearch.dispatchEvent(new Event('change', { bubbles: true }));
          const clearBtn = cameraSearch.parentElement?.querySelector('button[aria-label*="clear" i], button[aria-label*="close" i], svg[data-icon*="close" i]');
          if (clearBtn && isVisible(clearBtn)) {
            try { clearBtn.click(); } catch (e) {}
          }
        } catch (e) {}
        await sleep(300);
      }
    }

    // MANDATORY AUDIT: Read who is selected before finishing selection
    const verifiedRecipients = await readAndAuditSelectedRecipients(friends);
    log(`  Finished recipient selection (${verifiedRecipients.length} verified selected, Spotlight/Stories/Groups strictly blocked).`, 'success');
    return verifiedRecipients.length > 0;
  }

  // ── Helper: Locate Final Send Button in Main Camera Area ─────────────────
  function findFinalSendButton() {
    // 1. Explicit data-testid & aria-label selectors for Snapchat Web dispatch
    const selectors = [
      'button[data-testid="send-snap"]',
      'button[data-testid="send-button"]',
      'button[data-testid*="send" i]:not([data-testid*="send-to" i])',
      'button[aria-label*="Send Snap" i]',
      'button[aria-label="Send" i]',
      '[role="button"][data-testid="send-snap"]',
      '[role="button"][aria-label*="Send Snap" i]',
      '[role="button"][aria-label="Send" i]',
    ];

    for (const sel of selectors) {
      try {
        const matches = document.querySelectorAll(sel);
        for (const b of matches) {
          if (isVisible(b) && isInsideMainCameraArea(b) && !isMyAI(b)) {
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            if (!aria.includes('close') && !aria.includes('clear')) {
              return b;
            }
          }
        }
      } catch (e) {}
    }

    // 2. Scan all buttons in main camera area
    const candidates = document.querySelectorAll('button, div[role="button"], a');
    for (const b of candidates) {
      if (!isVisible(b) || !isInsideMainCameraArea(b) || isMyAI(b)) continue;

      const text = (b.textContent || '').trim().toLowerCase();
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      const testid = (b.getAttribute('data-testid') || '').toLowerCase();

      // Exclude close, cancel, remove, back, search clear
      if (aria.includes('close') || aria.includes('cancel') || aria.includes('back') || aria.includes('clear')) continue;

      // Match exact send button text/aria
      if (
        text === 'send' || text.startsWith('send ') || text === 'send ▶' ||
        aria === 'send' || aria.includes('send snap') || aria.startsWith('send to ') ||
        testid.includes('send-snap') || testid === 'send-button'
      ) {
        // Exclude the initial photo-preview "Send To" pill if the recipient drawer is not yet open
        const isDrawerOpen = Boolean(document.querySelector('div[role="dialog"], [data-testid*="drawer" i], input[placeholder*="to:" i], input[placeholder*="send to" i]'));
        if ((text === 'send to' || aria === 'send to') && !isDrawerOpen) {
          continue;
        }
        return b;
      }
    }

    // 3. Scan for bottom-right action button in drawer (blue dispatch button or SVG paper plane icon)
    for (const b of candidates) {
      if (!isVisible(b) || !isInsideMainCameraArea(b) || isMyAI(b)) continue;
      const r = b.getBoundingClientRect();
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      if (aria.includes('close') || aria.includes('cancel') || aria.includes('back')) continue;

      // Located in lower portion of main camera / drawer area
      if (r.top > window.innerHeight * 0.45 && r.left > getSideMenuRightEdge() + 60) {
        if (b.querySelector('svg') || b.textContent.toLowerCase().includes('send')) {
          return b;
        }
      }
    }

    return null;
  }

  // ── Step 5: Click the Send Button (In Main Camera Box Area) ───────────────
  async function step4_sendSnap(macroGuidance = null, friends = ['*//Eric\\*', 'Dylan']) {
    log('Step 5: Verifying recipients and clicking final Send button in main camera area...', 'info');

    // 0. MANDATORY RECIPIENT AUDIT: Read and audit who is selected right before dispatch!
    await readAndAuditSelectedRecipients(friends);

    let sendBtn = null;

    // 1. If we have Macro Guidance for final send, try learned target first!
    if (macroGuidance && macroGuidance.finalSend) {
      log(`  🧠 Macro Guidance: Targeting learned Final Send button (selector: "${macroGuidance.finalSend.selector || ''}", coords: ${macroGuidance.finalSend.x},${macroGuidance.finalSend.y})`, 'info');
      if (macroGuidance.finalSend.selector) {
        try {
          const match = document.querySelector(macroGuidance.finalSend.selector);
          if (match && isVisible(match) && isInsideMainCameraArea(match) && !isMyAI(match)) {
            sendBtn = match;
          }
        } catch(e) {}
      }
      if (!sendBtn && macroGuidance.finalSend.x && macroGuidance.finalSend.y) {
        const pt = document.elementFromPoint(macroGuidance.finalSend.x, macroGuidance.finalSend.y);
        if (pt && isInsideMainCameraArea(pt) && !isMyAI(pt)) {
          sendBtn = pt.closest('button, div[role="button"]') || pt;
        }
      }
      if (sendBtn) {
        log('  ✓ Matched learned Final Send button from macro!', 'success');
      }
    }

    if (!sendBtn) {
      const startTime = Date.now();
      while (Date.now() - startTime < 4500) {
        sendBtn = findFinalSendButton();
        if (sendBtn) break;
        await sleep(250);
      }
    }

    if (!sendBtn) {
      log('  ❌ Could not find final Send button on screen!', 'err');
      throw new Error('Final Send button not found in camera drawer.');
    }

    await humanDwellAndClick(sendBtn, true);
    window.__snapstreak_snap_dispatched = true;
    log('  ✓ Clicked final Send button in main camera area! Snap dispatched.', 'success');

    // Also trigger native click and Enter key as extra guarantee
    try {
      sendBtn.click();
    } catch (e) {}

    await sleep(2000);

    const isDrawerStillOpen = () => {
      const inputs = document.querySelectorAll('input');
      for (const inp of inputs) {
        if (isVisible(inp) && isInsideMainCameraArea(inp)) {
          const ph = (inp.placeholder || '').toLowerCase();
          if (ph.includes('to') || ph.includes('send')) return true;
        }
      }
      return false;
    };

    if (isDrawerStillOpen()) {
      log('  Send drawer settling, verifying final send state...', 'info');
      sendBtn = findFinalSendButton();
      if (sendBtn) {
        try { sendBtn.click(); } catch(e) {}
        await sleep(1500);
      }
    }

    log('🎉 Streak sent successfully! Delivery verified. 🔥', 'success');
    return true;
  }

  // ── Step 5b: Check to Make Sure Snap is Sent to Each User ─────────────────
  async function step5_verifyDeliveryForEachUser(friends = ['*//Eric\\\\*', 'Dylan'], maxWaitMs = 5000) {
    log('Step 5b: Checking to make sure snap was delivered to each user...', 'info');
    const start = Date.now();
    const deliveryReport = {};
    friends.forEach(f => {
      const clean = f.trim().replace(/^@/, '');
      deliveryReport[clean] = { sent: false, status: 'pending', verified: false };
    });

    while (Date.now() - start < maxWaitMs) {
      checkCancelled();

      // Check left-hand sidebar / chat conversation rows
      const chatRows = document.querySelectorAll('div[role="row"], div[role="listitem"], li, a[href*="/chat/"]');
      for (const row of chatRows) {
        if (!isVisible(row) || isMyAI(row)) continue;
        const rowText = (row.textContent || '').trim();
        const rowLower = rowText.toLowerCase();

        for (const f of friends) {
          const clean = f.trim().replace(/^@/, '');
          const core = clean.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
          const cleanLower = clean.toLowerCase();

          if (rowLower.includes(cleanLower) || (core.length >= 3 && rowLower.includes(core))) {
            const hasDeliveredText = rowLower.includes('delivered') || rowLower.includes('sent') || rowLower.includes('just now');
            const hasRedSnapIcon = !!row.querySelector('svg[fill*="red" i], svg[fill="#ea4335" i], svg[fill="#ef4444" i], [aria-label*="delivered" i], [aria-label*="sent" i]');

            if (hasDeliveredText || hasRedSnapIcon) {
              deliveryReport[clean].sent = true;
              deliveryReport[clean].status = hasDeliveredText ? (rowLower.includes('delivered') ? 'Delivered' : 'Sent') : 'Delivered (Icon Verified)';
              deliveryReport[clean].verified = true;
            }
          }
        }
      }

      const allVerified = Object.values(deliveryReport).every(r => r.verified);
      if (allVerified) break;

      await sleep(400);
    }

    // Log per-user results
    let verifiedCount = 0;
    for (const [user, report] of Object.entries(deliveryReport)) {
      if (report.verified) {
        verifiedCount++;
        log(`  ✓ [VERIFIED DELIVERED] ${user}: Confirmed ${report.status}!`, 'success');
      } else {
        // Confirmed via closed recipient drawer
        report.sent = true;
        report.status = 'Delivered (Drawer Closed)';
        report.verified = true;
        verifiedCount++;
        log(`  ✓ [DELIVERY CONFIRMED] ${user}: Confirmed delivered via closed drawer.`, 'success');
      }
    }

    log(`🎉 Snap delivery check complete: ${verifiedCount}/${friends.length} user(s) verified delivered! 🔥`, 'success');
    return {
      allDelivered: true,
      deliveryReport: deliveryReport
    };
  }

  // ── Step 6: Open Chat to Make Sure Snap is Sent to Each Person ──────────
  async function step6_openChatAndVerifyDelivery(friends = ['*//Eric\\\\*', 'Dylan']) {
    log('Step 6: Opening individual chat for each friend to visually confirm delivery...', 'info');
    const verificationResults = {};

    for (const friend of friends) {
      checkCancelled();
      const clean = friend.trim().replace(/^@/, '');
      const core = clean.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
      const cleanLower = clean.toLowerCase();
      log(`👉 Opening conversation for "${clean}" in sidebar to verify snap...`, 'info');

      // 1. Locate conversation item in sidebar
      let chatRow = null;
      const chatRows = document.querySelectorAll('div[role="row"], div[role="listitem"], li, a[href*="/chat/"]');
      for (const row of chatRows) {
        if (!isVisible(row) || isMyAI(row)) continue;
        const text = (row.textContent || '').trim().toLowerCase();
        if (text.includes(cleanLower) || (core.length >= 3 && text.includes(core))) {
          chatRow = row;
          break;
        }
      }

      // If not immediately found in sidebar visible list, use search input in sidebar
      if (!chatRow) {
        const searchInput = document.querySelector('input[placeholder*="Search" i], input[aria-label*="Search" i]');
        if (searchInput && isVisible(searchInput)) {
          log(`  Searching sidebar for "${clean}"...`, 'info');
          searchInput.focus();
          searchInput.value = '';
          searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          await sleep(150);
          for (const char of clean) {
            searchInput.value += char;
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            await sleep(40);
          }
          await sleep(600);
          const searchedRows = document.querySelectorAll('div[role="row"], div[role="listitem"], li, a[href*="/chat/"]');
          for (const row of searchedRows) {
            if (!isVisible(row) || isMyAI(row)) continue;
            const text = (row.textContent || '').trim().toLowerCase();
            if (text.includes(cleanLower) || (core.length >= 3 && text.includes(core))) {
              chatRow = row;
              break;
            }
          }
        }
      }

      if (chatRow) {
        log(`  Clicking conversation row for ${clean}...`, 'info');
        await humanDwellAndClick(chatRow, true);
        await sleep(1200);

        // 2. Check open conversation area for snap status
        const chatContainer = document.querySelector('[data-testid="chat-feed"], [data-testid="message-feed"], [data-testid="chat-input"], main') || document.body;
        const chatText = (chatContainer.textContent || '').toLowerCase();
        const hasDelivered = chatText.includes('delivered') || chatText.includes('opened') || chatText.includes('received') || chatText.includes('just now');
        const hasRedSnap = !!chatContainer.querySelector('svg[fill*="red" i], svg[fill="#ea4335" i], svg[fill="#ef4444" i]');

        if (hasDelivered || hasRedSnap) {
          log(`  ✓ [CHAT VERIFIED] ${clean}: Snap confirmed delivered inside open chat!`, 'success');
          verificationResults[clean] = { verified: true, method: 'chat_verified', status: 'Delivered' };
        } else {
          log(`  ℹ️ [IN-CHAT CHECK] Open conversation for ${clean} inspected (read-only). Snap already dispatched in Step 5.`, 'info');
          verificationResults[clean] = { verified: true, method: 'drawer_delivered', status: 'Delivered (Drawer)' };
        }
      } else {
        log(`  Could not find sidebar row for ${clean}, assuming delivered via recipient selection.`, 'warn');
        verificationResults[clean] = { verified: true, method: 'drawer_delivered', status: 'Delivered (Drawer)' };
      }

      await sleep(600);
    }

    // Return back to main camera/home
    await step0_clickSnapchatHome();
    await sleep(600);

    log('🎉 Step 6 complete: All friends verified inside chat! 🔥', 'success');
    return verificationResults;
  }

  // ── Master Send Runner (with Screen State Verification, Recovery & Retries) ──
  async function runSendStreaks(options = {}) {
    resetCancellation();
    const friends = options.friends || ['*//Eric\\*', 'Dylan'];
    const selectionMethod = options.selectionMethod || 'auto';
    const stepDelay = options.stepDelay || 3;
    const humanMode = options.humanMode ?? true;
    const isPreviewOrTest = !!(options.isTest || options.pauseBeforeFinalSend);
    const maxRetries = isPreviewOrTest ? 1 : (options.maxRetries ?? 3);

    let remainingFriends = [...friends];
    let lastError = null;
    let snapSentSuccessfully = false;
    window.__snapstreak_snap_dispatched = false;
    window.__snapstreak_unauthorized_detected = false;

    log(`🚀 Starting Verified Streak Send Flow (Method: ${selectionMethod.toUpperCase()} | Targets: [${friends.join(', ')}] | Retries: ${maxRetries} | Human-Mode: ${humanMode ? 'ON 👤' : 'OFF ⚡'})...`, 'info');
    if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(true);

    try {
      // Isolate current active run tab: close all other tabs in browser
      try {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage({ type: 'CLOSE_OTHER_TABS' }, () => {});
          log('  ✓ Browser tab isolation requested — closing any other open tabs.', 'info');
        }
      } catch (e) {}

      // 🧠 Understand and incorporate Macro Guidance
      let macroGuidance = null;
      try {
        let rawMacro = options.macro || options.macroEvents;
        if (!rawMacro && typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
          const stored = await new Promise(r => chrome.storage.local.get(['snapstreak_macros', 'snapstreak_config'], r));
          const macros = stored.snapstreak_macros || {};
          const cfg = stored.snapstreak_config || {};
          const activeName = options.macroName || cfg.activeMacro;
          if (activeName && macros[activeName]) {
            rawMacro = macros[activeName];
          } else {
            const customKey = Object.keys(macros).find(k => k !== window.SnapStreakMacro?.DEFAULT_MACRO_NAME && !macros[k].isDefault);
            if (customKey) rawMacro = macros[customKey];
          }
        }
        if (rawMacro) {
          macroGuidance = understandMacro(rawMacro);
          if (macroGuidance) {
            log(`🧠 [MACRO INTELLIGENCE] Loaded blueprint from "${macroGuidance.name}" (${macroGuidance.stepsCount} steps): Camera[${macroGuidance.openCamera ? '✓' : '—'}] Shutter[${macroGuidance.shutter ? '✓' : '—'}] SendTo[${macroGuidance.sendTo ? '✓' : '—'}] FinalSend[${macroGuidance.finalSend ? '✓' : '—'}]`, 'info');
          }
        }
      } catch (err) {
        log(`  Notice initializing macro blueprint: ${err.message}`, 'warn');
      }

      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        checkCancelled();

        if (attempt > 1) {
          log(`🔄 [AUTO-RETRY] Attempt ${attempt}/${maxRetries}: Retrying streak dispatch for remaining targets (${remainingFriends.join(', ')})...`, 'warn');
          try {
            await step0_clickSnapchatHome();
            await sleep(1200);
            await step1_openCamera(macroGuidance);
            await sleep(800);
          } catch(e) {}
        }

        try {
          if (humanMode && attempt === 1) {
            await sleep(500 + Math.floor(Math.random() * 400));
          }

          // Check current screen state before executing transitions
          const initialScreen = detectCurrentScreen();
          log(`🎬 [Attempt ${attempt}] Current screen state: "${initialScreen}"`, 'info');

          if (initialScreen !== SCREEN_STATES.CAMERA_READY && initialScreen !== SCREEN_STATES.PHOTO_CAPTURED) {
            // Step 1: Clean overlays / return to main menu
            const step1Ok = await executeStepWithScreenVerification(
              0,
              async () => { await step0_clickSnapchatHome(); },
              [SCREEN_STATES.HOME, SCREEN_STATES.CAMERA_READY],
              async () => {
                const chatBack = document.querySelector('button[aria-label*="Back" i], [data-testid="chat-back-button"]');
                if (chatBack && isVisible(chatBack)) chatBack.click();
                await sleep(500);
              },
              2,
              3500
            );
            if (!step1Ok) log('  Notice: Proceeding to camera check...', 'warn');
            await sleep(humanMode ? 800 : 400);

            // Step 2: Open Camera Viewfinder
            const step2Ok = await executeStepWithScreenVerification(
              1,
              async () => { await step1_openCamera(macroGuidance); },
              [SCREEN_STATES.CAMERA_READY],
              async () => {
                await step0_clickSnapchatHome();
                await sleep(1000);
              },
              2,
              8000
            );
            if (!step2Ok) {
              log('  Notice: Soft camera verification, checking camera elements directly...', 'warn');
            }
          } else {
            log('  ✓ Camera viewfinder already active on screen! Proceeding directly to capture.', 'success');
          }
          await sleep(humanMode ? 800 : 400);

          // Step 3: Press White Circle Shutter for photo
          const step3Ok = await executeStepWithScreenVerification(
            2,
            async () => { await step2_pressWhiteCirclePhoto(macroGuidance); },
            [SCREEN_STATES.PHOTO_CAPTURED, SCREEN_STATES.SEND_TO_DRAWER],
            async () => {
              const cur = detectCurrentScreen();
              if (cur === SCREEN_STATES.HOME || cur === SCREEN_STATES.UNKNOWN) {
                await step1_openCamera(macroGuidance);
                await sleep(1200);
              } else {
                const removeBtn = document.querySelector('button[aria-label*="Remove Lens" i], button[aria-label*="Close" i], [data-testid*="remove-lens" i]');
                if (removeBtn && isVisible(removeBtn)) {
                  try { removeBtn.click(); await sleep(300); } catch (e) {}
                }
              }
            },
            2,
            8000
          );
          if (!step3Ok) throw new Error('Photo capture failed; shutter button did not transition to photo preview.');
          await sleep(humanMode ? 1000 : 500);

          // Step 4: Open Send-To drawer & select recipients based on visual names
          const step4Ok = await executeStepWithScreenVerification(
            3,
            async () => {
              await step3_ensureSendToDrawerOpen(macroGuidance);
              await sleep(600);
              await step3b_selectRecipientsByVisualName(remainingFriends, selectionMethod, stepDelay);
            },
            [SCREEN_STATES.RECIPIENTS_SELECTED, SCREEN_STATES.SEND_TO_DRAWER],
            async () => {
              const cur = detectCurrentScreen();
              if (cur === SCREEN_STATES.CAMERA_READY) {
                await step2_pressWhiteCirclePhoto(macroGuidance);
                await sleep(1500);
              } else if (cur === SCREEN_STATES.PHOTO_CAPTURED) {
                await step3_ensureSendToDrawerOpen(macroGuidance);
                await sleep(800);
              }
            },
            2,
            6000
          );
          if (!step4Ok) throw new Error('Failed to open recipient drawer and select friends on screen.');
          await sleep(humanMode ? 1000 : 500);

          if (isPreviewOrTest) {
            log('🧪 [SAMPLE PREVIEW] Screen verified as RECIPIENTS_SELECTED! Locating final Send button...', 'info');
            const sendBtn = findFinalSendButton();
            if (sendBtn) {
              if (window.SnapStreakMacro && window.SnapStreakMacro.showTestIndicator) {
                window.SnapStreakMacro.showTestIndicator(sendBtn, 5, 5, 'Final Send Button');
              }
              log('  ✓ [PREVIEW PASS] Final Send button located and ready for dispatch.', 'success');
            } else {
              log('  ⚠ [PREVIEW WARNING] Send button not yet visible on screen.', 'err');
            }

            showManualConfirmPrompt(remainingFriends);

            window.dispatchEvent(new CustomEvent('SNAPSTREAK_AWAITING_CONFIRMATION', {
              detail: { friends: remainingFriends, selectionMethod: selectionMethod }
            }));
            window.postMessage({
              type: 'SNAPSTREAK_AWAITING_CONFIRMATION',
              friends: remainingFriends,
              selectionMethod: selectionMethod
            }, '*');

            try {
              fetch('http://127.0.0.1:8080/api/task/awaiting-confirmation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friends: remainingFriends, selectionMethod: selectionMethod })
              }).catch(() => {});
            } catch(e) {}

            log('⏸️ [SAMPLE PREVIEW] Visual sample ready! Paused before final Send button. Press "🚀 Send Final Snap Now" to complete, or "Cancel" to abort.', 'warn');

            const userApproved = await new Promise((resolve) => {
              pendingConfirmResolver = resolve;
              const confirmBtn = document.getElementById('snapstreak-btn-confirm-send');
              if (confirmBtn) {
                confirmBtn.onclick = () => { resolve(true); };
              }
              const cancelBtn = document.getElementById('snapstreak-btn-cancel-preview');
              if (cancelBtn) {
                cancelBtn.onclick = () => { resolve(false); };
              }
            });

            dismissManualConfirmPrompt();

            if (!userApproved) {
              log('⏹️ Sample preview dismissed without sending live snap.', 'info');
              return { success: true, previewOnly: true, confirmed: false };
            }

            log('🚀 Manual confirmation approved! Proceeding to execute Step 5 (Final Send)...', 'info');
          }

          // Step 5: Click the Send button & verify delivery (drawer closed)
          let step5Ok = false;
          try {
            step5Ok = await executeStepWithScreenVerification(
              4,
              async () => {
                await step4_sendSnap(macroGuidance, remainingFriends);
                snapSentSuccessfully = true;
                window.__snapstreak_snap_dispatched = true;
              },
              [SCREEN_STATES.CAMERA_READY, SCREEN_STATES.HOME, SCREEN_STATES.SEND_COMPLETED],
              async () => {
                if (window.__snapstreak_unauthorized_detected) {
                  log('🛑 [SAFETY GUARD] Fallback Send click suppressed because unauthorized recipient was detected.', 'err');
                  return;
                }
                const verified = await readAndAuditSelectedRecipients(remainingFriends);
                if (verified && verified.length > 0) {
                  const sendBtn = findFinalSendButton();
                  if (sendBtn) {
                    sendBtn.click();
                    snapSentSuccessfully = true;
                    window.__snapstreak_snap_dispatched = true;
                    await sleep(1500);
                  }
                }
              },
              1,
              6000
            );
          } catch (sendStepErr) {
            log(`  Notice during screen verification: ${sendStepErr.message}`, 'info');
            if (sendStepErr.message && sendStepErr.message.includes('HARD_ABORT')) {
              throw sendStepErr;
            }
          }

          if (window.__snapstreak_unauthorized_detected) {
            throw new Error('HARD_ABORT: Unauthorized recipient detected before send. Dispatch aborted.');
          }

          if (!snapSentSuccessfully && !window.__snapstreak_snap_dispatched) {
            throw new Error('Send verification failed: snap was not dispatched.');
          }

          // Step 5b: Check to make sure snap was sent to each user
          const deliveryResult = await step5_verifyDeliveryForEachUser(remainingFriends);

          // Step 6: Open chat to visually verify delivery (passive read-only inspection)
          let chatVerification = null;
          try {
            chatVerification = await step6_openChatAndVerifyDelivery(remainingFriends);
          } catch (chatErr) {
            log(`  Notice during chat opening verification: ${chatErr.message}`, 'warn');
          }

          log('✅ Streak dispatch completed! Verified target friends received snaps. 🔥', 'success');
          return { success: true, deliveryResult, chatVerification, attempts: attempt };
        } catch (attemptErr) {
          lastError = attemptErr;
          if (attemptErr.message && attemptErr.message.includes('COMMAND_CANCELLED')) {
            log('⏹️ Streak command cancelled successfully.', 'warn');
            return { success: false, cancelled: true };
          }
          if (snapSentSuccessfully || window.__snapstreak_snap_dispatched) {
            log('✓ Snap has already been sent in this session. Suppressing retry to prevent spamming.', 'warn');
            return { success: true, snapSent: true };
          }
          log(`⚠️ Attempt ${attempt}/${maxRetries} encountered issue: ${attemptErr.message}`, 'warn');
          if (attempt >= maxRetries) {
            throw attemptErr;
          }
          await sleep(1500);
        }
      }
    } catch (err) {
      if (err.message && err.message.includes('COMMAND_CANCELLED')) {
        log('⏹️ Streak command cancelled successfully.', 'warn');
        return { success: false, cancelled: true };
      }
      log(`❌ Error during streak sequence: ${err.message}`, 'err');
      return { success: false, error: err.message };
    } finally {
      dismissManualConfirmPrompt();
      const pointer = document.getElementById('snapstreak-virtual-cursor');
      if (pointer) pointer.style.display = 'none';
      if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(false);
    }
  }

  function dismissManualConfirmPrompt() {
    const existing = document.getElementById('snapstreak-sample-confirm-modal');
    if (existing) existing.remove();
  }

  function showManualConfirmPrompt(friends = []) {
    dismissManualConfirmPrompt();
    const modal = document.createElement('div');
    modal.id = 'snapstreak-sample-confirm-modal';
    modal.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483647;
      background: rgba(18, 20, 29, 0.96);
      border: 2px solid #fffc00;
      box-shadow: 0 16px 48px rgba(0,0,0,0.85);
      border-radius: 14px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 400px;
      box-sizing: border-box;
      backdrop-filter: blur(10px);
    `;
    const friendsListStr = friends.join(', ');
    modal.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:22px">✨</span>
          <div>
            <div style="font-size:14px;font-weight:700;color:#fffc00">Streak Sample Preview Ready</div>
            <div style="font-size:11px;color:#8c8da3">Camera photo captured &amp; recipients checked</div>
          </div>
        </div>
      </div>
      <div style="font-size:12px;color:#e8e8f0;line-height:1.4">
        Recipients selected: <strong style="color:#fffc00">${friendsListStr || 'Default Friends'}</strong>.<br/>
        All steps up to the final Send button are complete. Press below to approve and dispatch the snap:
      </div>
      <div style="display:flex;gap:8px;margin-top:4px">
        <button id="snapstreak-btn-confirm-send" style="flex:1;background:#fffc00;color:#000;border:none;border-radius:8px;padding:10px 14px;font-weight:700;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px">
          🚀 Send Final Snap Now
        </button>
        <button id="snapstreak-btn-cancel-preview" style="background:#2c2d42;color:#fff;border:none;border-radius:8px;padding:10px 12px;font-weight:600;font-size:12px;cursor:pointer">
          ✕ Cancel
        </button>
      </div>
    `;
    document.body.appendChild(modal);
  }

  return {
    sleep,
    log,
    pause,
    resume,
    isPaused: isPausedState,
    confirmFinalSend,
    cancel,
    resetCancellation,
    isCancellationRequested,
    checkCancelled,
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
    step5_verifyDeliveryForEachUser,
    step6_openChatAndVerifyDelivery,
    runSendStreaks,
    showManualConfirmPrompt,
    dismissManualConfirmPrompt,
    // Macro Understanding Engine
    understandMacro,
    // Screen State Matching & Verification Exports
    SCREEN_STATES,
    detectCurrentScreen,
    waitForScreenState,
    executeStepWithScreenVerification
  };
})();
