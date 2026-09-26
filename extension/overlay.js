/**
 * SnapStreak In-Page HUD Overlay Controller
 * Injects and manages the Shadow DOM UI over web.snapchat.com
 */

window.SnapStreakOverlay = (function() {
  'use strict';

  let shadowRoot = null;
  let isWindowOpen = false;
  let isRunning = false;

  // Configuration state
  let config = {
    friends: ['*//Eric\\\\*', 'Dylan'],
    sendingEngine: 'direct',
    selectionMethod: 'shortcut',
    stepDelay: 3,
    humanMode: true,
    waitForUIChanges: true,
    scheduleEnabled: true,
    scheduleTime: '09:00',
    activeMacro: '⚡ Default Streak Macro'
  };

  const SJSU_WEBCAM_URL = 'https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg';

  function log(msg, type = 'info') {
    console.log(`[SnapStreak] ${msg}`);
    if (!shadowRoot) return;
    const box = shadowRoot.getElementById('hud-log-box');
    if (!box) return;

    const line = document.createElement('div');
    if (type === 'err') line.className = 'log-err';
    else if (type === 'success') line.className = 'log-success';
    else if (type === 'info') line.className = 'log-info';

    const time = new Date().toLocaleTimeString();
    line.textContent = `[${time}] ${msg}`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;

    while (box.children.length > 200) {
      box.removeChild(box.firstChild);
    }
  }

  function setRunning(running, isTest = false) {
    isRunning = running;
    if (!shadowRoot) return;
    const autoSendBtn = shadowRoot.getElementById('btn-auto-send-streaks') || shadowRoot.getElementById('btn-send-streaks');
    const testBtn = shadowRoot.getElementById('btn-test-streaks');
    const cancelBtn = shadowRoot.getElementById('btn-cancel-running');
    const quickCancelBtn = shadowRoot.getElementById('btn-quick-cancel');
    const macroCancelBtn = shadowRoot.getElementById('btn-macro-cancel');
    const macroReplayBtn = shadowRoot.getElementById('btn-macro-replay');
    const dot = shadowRoot.getElementById('status-dot');
    const label = shadowRoot.getElementById('status-text');
    const pillBadge = shadowRoot.getElementById('pill-badge');

    if (running) {
      if (autoSendBtn) {
        autoSendBtn.disabled = true;
        autoSendBtn.textContent = isTest ? '🔥 Auto Send Streaks' : '⏳ Auto Sending...';
      }
      if (testBtn) {
        testBtn.disabled = true;
        testBtn.textContent = isTest ? '🧪 Testing Macro...' : '🧪 Test Streak';
      }
      if (macroReplayBtn) macroReplayBtn.disabled = true;
      if (cancelBtn) cancelBtn.style.display = 'block';
      if (quickCancelBtn) quickCancelBtn.style.display = 'inline-flex';
      if (macroCancelBtn) macroCancelBtn.style.display = 'block';
      if (dot) dot.className = 'status-dot busy';
      if (label) label.textContent = isTest ? 'Testing Macro (Dry-Run)...' : 'Executing Macro Send...';
      if (pillBadge) {
        pillBadge.textContent = isTest ? 'Testing' : 'Busy';
        pillBadge.style.background = isTest ? 'var(--blue)' : 'var(--green)';
      }
    } else {
      if (autoSendBtn) {
        autoSendBtn.disabled = false;
        autoSendBtn.textContent = '🔥 Auto Send Streaks';
      }
      if (testBtn) {
        testBtn.disabled = false;
        testBtn.textContent = '🧪 Test Streak';
      }
      if (macroReplayBtn) macroReplayBtn.disabled = false;
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (quickCancelBtn) quickCancelBtn.style.display = 'none';
      if (macroCancelBtn) macroCancelBtn.style.display = 'none';
      if (dot) dot.className = 'status-dot';
      if (label) label.textContent = 'Idle (Ready)';
      if (pillBadge) {
        pillBadge.textContent = 'Ready';
        pillBadge.style.background = 'var(--green)';
      }
    }
  }

  function updateMacroStepCount(count) {
    if (!shadowRoot) return;
    const badge = shadowRoot.getElementById('rec-step-count');
    if (badge) badge.textContent = `${count} step${count !== 1 ? 's' : ''}`;
  }

  async function loadConfig() {
    return new Promise(resolve => {
      chrome.storage.local.get(['snapstreak_config'], res => {
        if (res.snapstreak_config) {
          config = { ...config, ...res.snapstreak_config };
        }
        resolve(config);
      });
    });
  }

  async function saveConfig() {
    await chrome.storage.local.set({ snapstreak_config: config });
    chrome.runtime.sendMessage({
      type: 'CONFIG_UPDATED',
      config: config
    });
    log('✓ Settings saved.', 'success');
  }

  function toggleWebcamPreview() {
    if (!shadowRoot) return;
    const box = shadowRoot.getElementById('cam-preview-box');
    const img = shadowRoot.getElementById('hud-sjsu-img');
    const btn = shadowRoot.getElementById('btn-preview-cam');
    if (!box || !img || !btn) return;

    if (box.style.display !== 'none') {
      box.style.display = 'none';
      btn.textContent = '👁️ View Live SJSU Visual';
      log('Closed webcam preview.', 'info');
    } else {
      img.src = `${SJSU_WEBCAM_URL}?t=${Date.now()}`;
      box.style.display = 'block';
      btn.textContent = '✕ Close Preview';
      log('Displaying live SJSU Meteorology visual.', 'success');
    }
  }

  function refreshSJSUFrame() {
    if (!shadowRoot) return;
    const img = shadowRoot.getElementById('hud-sjsu-img');
    const timeLabel = shadowRoot.getElementById('sjsu-timestamp');
    const newSrc = `${SJSU_WEBCAM_URL}?t=${Date.now()}`;
    if (img) img.src = newSrc;
    if (timeLabel) timeLabel.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
    log('✓ Refreshed live SJSU Meteorology frame.', 'success');
  }

  function initUI() {
    if (document.getElementById('snapstreak-shadow-host')) return;

    const host = document.createElement('div');
    host.id = 'snapstreak-shadow-host';
    document.body.appendChild(host);

    shadowRoot = host.attachShadow({ mode: 'open' });

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('overlay.css');
    shadowRoot.appendChild(link);

    const container = document.createElement('div');
    container.innerHTML = `
      <!-- Launcher Pill Button -->
      <div id="snapstreak-pill" title="Toggle SnapStreak Controls">
        <span class="pill-icon">🔥</span>
        <span class="pill-label">SnapStreak</span>
        <span class="pill-badge" id="pill-badge">Ready</span>
      </div>

      <!-- Main HUD Window -->
      <div id="snapstreak-window" class="hidden">
        <!-- Header -->
        <div class="hud-header" id="hud-header">
          <div class="hud-title-wrap">
            <img class="hud-logo" src="${chrome.runtime.getURL('icons/icon48.png')}" alt="SnapStreak Logo" />
            <span class="hud-title">SnapStreak Controller</span>
          </div>
          <div class="hud-header-actions">
            <button class="hud-btn-icon" id="btn-minimize" title="Minimize Window">─</button>
            <button class="hud-btn-icon" id="btn-close" title="Close Window">✕</button>
          </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="hud-tabs">
          <button class="hud-tab-btn active" data-tab="tab-streaks">⚡ Streaks</button>
          <button class="hud-tab-btn" data-tab="tab-macros">🎬 Macros</button>
          <button class="hud-tab-btn" data-tab="tab-friends">👥 Friends</button>
          <button class="hud-tab-btn" data-tab="tab-schedule">⏰ Schedule</button>
          <button class="hud-tab-btn" data-tab="tab-logs">📋 Logs</button>
        </div>

        <!-- Body Content -->
        <div class="hud-body">
          <!-- Status Banner -->
          <div class="hud-status-banner">
            <div class="status-indicator">
              <div class="status-dot" id="status-dot"></div>
              <span id="status-text">Idle (Ready)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button class="btn btn-danger" id="btn-quick-cancel" style="display: none; padding: 3px 8px; font-size: 11px; font-weight: 700; border-radius: 4px;" title="Cancel running streak command">
                ⏹️ Cancel
              </button>
              <div style="font-size: 11px; color: var(--text-dim);" id="friends-count-badge">2 Friends</div>
            </div>
          </div>

          <!-- TAB 1: STREAKS -->
          <div class="tab-pane active" id="tab-streaks">
            <!-- Primary Execution Engine Card -->
            <div class="hud-card" style="border-color: #ffd000; background: linear-gradient(180deg, #1d2133 0%, #151926 100%);">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 700; color: var(--accent); font-size: 13px; display: flex; align-items: center; gap: 6px;">
                  🚀 Streak Sending Engine
                </span>
                <span class="pill-badge" id="engine-badge" style="background: var(--green); color: #000; font-weight: 800;">DIRECT</span>
              </div>

              <label style="font-size: 11px; color: var(--text-dim); margin-bottom: 4px; display: block;">Sending Method</label>
              <select id="sel-sending-engine" style="margin-bottom: 8px;">
                <option value="direct">⚡ Direct Script (No Macro: Camera ➔ Shortcut/Users ➔ Send)</option>
                <option value="macro">🎬 Macro Replay Engine (Click Sequences)</option>
              </select>

              <!-- Direct Script Options -->
              <div id="box-direct-options" style="margin-bottom: 8px;">
                <label style="font-size: 11px; color: var(--text-dim); margin-bottom: 4px; display: block;">Recipient Target</label>
                <select id="sel-direct-target">
                  <option value="shortcut">✨ Snapchat Shortcut (Auto-clicks Shortcut & Selects All)</option>
                  <option value="direct">👥 Specific Users (Searches users from Friends tab)</option>
                  <option value="auto">⚡ Auto (Shortcut with Friend Search fallback)</option>
                </select>
              </div>

              <!-- Macro Options -->
              <div id="box-macro-options" style="display: none; margin-bottom: 8px;">
                <label style="font-size: 11px; color: var(--text-dim); margin-bottom: 4px; display: block;">Active Streak Macro</label>
                <div style="display: flex; gap: 6px;">
                  <select id="sel-active-macro" style="flex: 1;"></select>
                  <button class="btn btn-secondary" id="btn-quick-record" title="Record New Macro" style="padding: 0 10px; font-size: 11px; white-space: nowrap;">➕ Record</button>
                </div>
              </div>

              <div class="btn-row" style="margin-top: 6px;">
                <button class="btn btn-primary btn-full" id="btn-auto-send-streaks" style="font-size: 13px; padding: 11px; font-weight: 700;">
                  🔥 Auto Send Streaks
                </button>
                <button class="btn btn-test btn-full" id="btn-test-streaks" style="font-size: 13px; padding: 11px; font-weight: 700;" title="Test camera & recipient selection without sending live snap">
                  🧪 Test Streak
                </button>
              </div>
              <button class="btn btn-danger btn-full" id="btn-cancel-running" style="display: none; font-size: 13px; padding: 11px; font-weight: 700; margin-top: 6px;" title="Abort in-flight streak execution immediately">
                ⏹️ Cancel Running Streak
              </button>
            </div>

            <!-- SJSU Meteorology Live Webcam Card -->
            <div class="hud-card" style="border-color: #3b4468;">
              <div class="hud-card-title">
                <span style="color: var(--accent);">📡 Live SJSU Meteorology Webcam</span>
                <button class="btn btn-secondary" id="btn-refresh-sjsu" style="padding: 2px 8px; font-size: 10px;" title="Fetch latest SJSU frame">↻ Refresh</button>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 11px; color: var(--green); font-weight: 600;">● Active System Webcam Stream</span>
                <span style="font-size: 10px; color: var(--text-dim);" id="sjsu-timestamp">Live Feed</span>
              </div>
              <div class="btn-row" style="margin-top: 4px;">
                <button class="btn btn-secondary btn-full" id="btn-preview-cam">👁️ View Live SJSU Visual</button>
              </div>
              <div id="cam-preview-box" style="display: none; margin-top: 8px; border-radius: 8px; overflow: hidden; background: #000; border: 1px solid var(--border); position: relative;">
                <img id="hud-sjsu-img" src="" alt="SJSU Meteorology Webcam" style="width: 100%; height: 160px; object-fit: cover; display: block;" />
                <button id="btn-close-cam-preview" style="position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,0.7); color: #fff; border: none; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 11px;">✕</button>
              </div>
              <small style="font-size: 10px; color: var(--text-dim); margin-top: 2px;">
                Snapchat's camera viewfinder displays this live SJSU Meteorology visual as your system webcam.
              </small>
            </div>

            <div class="hud-card">
              <div class="hud-card-title">Execution Settings</div>
              <label>Step Delay (seconds)</label>
              <input type="number" id="inp-step-delay" min="1" max="15" value="3" />

              <div class="toggle-row" style="margin-top: 10px;">
                <div>
                  <div style="font-size: 11px; font-weight: 600; color: #fff;">👤 Human-Like Natural Mode</div>
                  <div style="font-size: 10px; color: var(--text-dim);">Realistic cursor path, dwell & typing cadence</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="chk-human-mode" checked />
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>
          </div>

          <!-- TAB 2: MACROS -->
          <div class="tab-pane" id="tab-macros">
            <div class="hud-card">
              <div class="hud-card-title">Macro Progression Control</div>
              <div class="toggle-row">
                <div>
                  <div style="font-size: 11px; font-weight: 600; color: #fff;">⏳ Wait for Large UI Changes</div>
                  <div style="font-size: 10px; color: var(--text-dim);">Pause step until page visually mutates</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="chk-wait-ui" checked />
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>

            <div class="hud-card">
              <div class="hud-card-title">Record Custom Macro</div>
              <p style="font-size: 11px; color: var(--text-dim); margin: 0;">
                Click Record, then click your exact streak steps on Snapchat Web (Camera, Select, Send).
              </p>
              <div class="macro-recording-banner" id="rec-banner" style="display: none;">
                <div class="rec-pulse-dot"></div>
                <span>RECORDING ACTIVE: <b id="rec-step-count">0 steps</b></span>
              </div>
              <div class="btn-row">
                <button class="btn btn-danger btn-full" id="btn-macro-record">🔴 Start Recording</button>
                <button class="btn btn-secondary btn-full" id="btn-macro-stop" style="display: none;">⏹️ Stop & Save</button>
              </div>
            </div>

            <div class="hud-card">
              <div class="hud-card-title">Saved Macros</div>
              <label>Select Macro to Replay</label>
              <select id="sel-saved-macros">
                <option value="">(No saved macros)</option>
              </select>
              <div class="btn-row" style="margin-top: 4px;">
                <button class="btn btn-primary btn-full" id="btn-macro-replay">▶ Replay Macro</button>
                <button class="btn btn-secondary" id="btn-macro-delete">🗑️ Delete</button>
              </div>
              <button class="btn btn-danger btn-full" id="btn-macro-cancel" style="display: none; font-size: 12px; padding: 9px; font-weight: 700; margin-top: 6px;" title="Stop replaying macro">
                ⏹️ Cancel Replay
              </button>
            </div>
          </div>

          <!-- TAB 3: FRIENDS -->
          <div class="tab-pane" id="tab-friends">
            <div class="hud-card">
              <div class="hud-card-title">
                <span>Streak Recipients</span>
                <span id="friends-counter" style="color: var(--accent);">2 Added</span>
              </div>
              <label>Usernames (one per line, no @)</label>
              <textarea id="inp-friends" placeholder="user_one&#10;user_two"></textarea>
              <button class="btn btn-success btn-full" id="btn-save-friends">💾 Save Recipients</button>
            </div>
          </div>

          <!-- TAB 4: SCHEDULE -->
          <div class="tab-pane" id="tab-schedule">
            <div class="hud-card">
              <div class="hud-card-title">Daily Auto-Send</div>
              <div class="toggle-row">
                <label style="margin: 0;">Enable Daily Schedule</label>
                <label class="toggle-switch">
                  <input type="checkbox" id="chk-schedule-enabled" checked />
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <label style="margin-top: 10px;">Daily Send Time (Local Time)</label>
              <input type="time" id="inp-schedule-time" value="09:00" />
              <button class="btn btn-primary btn-full" id="btn-save-schedule" style="margin-top: 6px;">
                ⏰ Update Schedule
              </button>

              <!-- Live Schedule Status Banner -->
              <div id="schedule-status-banner" style="margin-top: 10px; padding: 8px 10px; background: rgba(0,0,0,0.3); border-radius: 6px; border-left: 3px solid var(--accent); font-size: 11px;">
                <div style="font-weight: 700; color: var(--accent); margin-bottom: 3px; display: flex; justify-content: space-between;">
                  <span>Schedule Status</span>
                  <span id="schedule-sync-pill" style="font-size: 10px; color: var(--green); font-weight: normal;">● Active</span>
                </div>
                <div id="schedule-next-run" style="color: var(--text-light);">Next Run: Calculating...</div>
                <div id="schedule-last-run" style="color: var(--text-dim); margin-top: 2px;">Last Run: Not sent yet today</div>
              </div>

              <button class="btn btn-test btn-full" id="btn-test-schedule-now" style="margin-top: 8px; font-size: 11px; padding: 8px;" title="Trigger the background alarm sequence immediately to verify scheduling">
                ⚡ Test Scheduled Trigger Now
              </button>

              <small style="font-size: 10px; color: var(--text-dim); margin-top: 6px; display: block;">
                The background extension alarms automatically trigger streaks daily at this time, with automatic missed-schedule recovery if your PC was sleeping.
              </small>
            </div>
          </div>

          <!-- TAB 5: LOGS -->
          <div class="tab-pane" id="tab-logs">
            <div class="hud-card" style="padding: 8px;">
              <div class="hud-card-title" style="margin-bottom: 6px;">
                <span>Activity Console</span>
                <button class="btn btn-secondary" id="btn-clear-logs" style="padding: 2px 8px; font-size: 10px;">Clear</button>
              </div>
              <div id="hud-log-box"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    shadowRoot.appendChild(container);
    bindEvents();
    populateUI();
    log('SnapStreak Overlay HUD initialized with live SJSU Meteorology feed! 📡', 'success');
  }

  function toggleWindow(force) {
    const win = shadowRoot.getElementById('snapstreak-window');
    if (!win) return;
    isWindowOpen = (typeof force === 'boolean') ? force : win.classList.contains('hidden');
    if (isWindowOpen) {
      win.classList.remove('hidden');
    } else {
      win.classList.add('hidden');
    }
  }

  function switchTab(tabId) {
    if (!shadowRoot) return;
    const tabButtons = shadowRoot.querySelectorAll('.hud-tab-btn');
    tabButtons.forEach(btn => {
      if (btn.dataset.tab === tabId) btn.classList.add('active');
      else btn.classList.remove('active');
    });
    shadowRoot.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    shadowRoot.getElementById(tabId)?.classList.add('active');
  }

  function bindEvents() {
    // Launcher pill toggle
    shadowRoot.getElementById('snapstreak-pill').addEventListener('click', () => toggleWindow());
    shadowRoot.getElementById('btn-close').addEventListener('click', () => toggleWindow(false));
    shadowRoot.getElementById('btn-minimize').addEventListener('click', () => toggleWindow(false));

    // Tab switching
    const tabButtons = shadowRoot.querySelectorAll('.hud-tab-btn');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        switchTab(btn.dataset.tab);
      });
    });

    // Drag-and-drop window repositioning
    const header = shadowRoot.getElementById('hud-header');
    const win = shadowRoot.getElementById('snapstreak-window');
    let isDragging = false, startX, startY, origLeft, origTop;

    header.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.hud-header-actions')) return;
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = win.getBoundingClientRect();
      origLeft = rect.left;
      origTop = rect.top;
      win.style.right = 'auto';
      win.style.left = `${origLeft}px`;
      win.style.top = `${origTop}px`;
      header.setPointerCapture(e.pointerId);
    });

    header.addEventListener('pointermove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      win.style.left = `${origLeft + dx}px`;
      win.style.top = `${origTop + dy}px`;
    });

    header.addEventListener('pointerup', (e) => {
      isDragging = false;
      try { header.releasePointerCapture(e.pointerId); } catch(err) {}
    });

    // SJSU Live Webcam Controls
    shadowRoot.getElementById('btn-preview-cam').addEventListener('click', () => {
      toggleWebcamPreview();
    });

    shadowRoot.getElementById('btn-close-cam-preview').addEventListener('click', () => {
      toggleWebcamPreview();
    });

    shadowRoot.getElementById('btn-refresh-sjsu').addEventListener('click', () => {
      refreshSJSUFrame();
    });

    // Engine Mode Toggle & UI Visibility
    const engineSel = shadowRoot.getElementById('sel-sending-engine');
    const boxDirect = shadowRoot.getElementById('box-direct-options');
    const boxMacro = shadowRoot.getElementById('box-macro-options');
    const engineBadge = shadowRoot.getElementById('engine-badge');

    function updateEngineVisibility() {
      if (config.sendingEngine === 'direct') {
        if (boxDirect) boxDirect.style.display = 'block';
        if (boxMacro) boxMacro.style.display = 'none';
        if (engineBadge) {
          engineBadge.textContent = 'DIRECT';
          engineBadge.style.background = 'var(--green)';
          engineBadge.style.color = '#000';
        }
      } else {
        if (boxDirect) boxDirect.style.display = 'none';
        if (boxMacro) boxMacro.style.display = 'block';
        if (engineBadge) {
          engineBadge.textContent = 'MACRO';
          engineBadge.style.background = 'var(--accent)';
          engineBadge.style.color = '#000';
        }
      }
    }

    if (engineSel) {
      engineSel.addEventListener('change', (e) => {
        config.sendingEngine = e.target.value;
        updateEngineVisibility();
        saveConfig();
        log(`Switched sending engine to: ${config.sendingEngine === 'direct' ? '⚡ Direct Script (No Macro)' : '🎬 Macro Engine'}`, 'info');
      });
    }

    // Direct Target selection (Shortcut vs Users vs Auto)
    const directTargetSel = shadowRoot.getElementById('sel-direct-target');
    if (directTargetSel) {
      directTargetSel.addEventListener('change', (e) => {
        config.selectionMethod = e.target.value;
        saveConfig();
        log(`Target recipient mode set to: ${config.selectionMethod.toUpperCase()}`, 'info');
      });
    }

    // 🔥 AUTO SEND STREAKS: Dual-Engine Support
    const autoSendBtn = shadowRoot.getElementById('btn-auto-send-streaks') || shadowRoot.getElementById('btn-send-streaks');
    if (autoSendBtn) {
      autoSendBtn.addEventListener('click', async () => {
        setRunning(true, false);
        try {
          if (config.sendingEngine === 'direct') {
            log('⚡ Executing Direct Script (Camera ➔ Shortcut/Users ➔ Send)...', 'info');
            await window.SnapStreakAutomation.runSendStreaks({
              friends: config.friends,
              selectionMethod: config.selectionMethod,
              stepDelay: config.stepDelay,
              humanMode: config.humanMode,
              isTest: false
            });
          } else {
            const macroName = config.activeMacro || '⚡ Default Streak Macro';
            log(`🎬 Executing Macro: "${macroName}"...`, 'info');
            await window.SnapStreakMacro.replayMacro(macroName, config.stepDelay, config.waitForUIChanges, false);
          }
        } finally {
          setRunning(false);
        }
      });
    }

    // 🧪 TEST STREAK: Dual-Engine Dry-Run Verification
    const testBtn = shadowRoot.getElementById('btn-test-streaks');
    if (testBtn) {
      testBtn.addEventListener('click', async () => {
        setRunning(true, true);
        try {
          if (config.sendingEngine === 'direct') {
            log('🧪 [TEST] Running Direct Script Dry-Run (Verifying camera + shortcut/users)...', 'info');
            await window.SnapStreakAutomation.runSendStreaks({
              friends: config.friends,
              selectionMethod: config.selectionMethod,
              stepDelay: config.stepDelay,
              humanMode: config.humanMode,
              isTest: true
            });
          } else {
            const macroName = config.activeMacro || '⚡ Default Streak Macro';
            log(`🧪 [TEST] Running Macro Dry-Run: "${macroName}"...`, 'info');
            await window.SnapStreakMacro.replayMacro(macroName, config.stepDelay, config.waitForUIChanges, true);
          }
        } finally {
          setRunning(false);
        }
      });
    }

    // ⏹️ Cancel running streak / macro command
    const handleCancelRequest = () => {
      log('⏹️ User requested cancellation of running command.', 'warn');
      if (window.SnapStreakAutomation && window.SnapStreakAutomation.cancel) {
        window.SnapStreakAutomation.cancel();
      }
      try {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage({ type: 'CANCEL_RUNNING_COMMAND' });
        }
      } catch (e) {}
      setRunning(false);
    };

    const cancelBtn = shadowRoot.getElementById('btn-cancel-running');
    if (cancelBtn) cancelBtn.addEventListener('click', handleCancelRequest);

    const quickCancelBtn = shadowRoot.getElementById('btn-quick-cancel');
    if (quickCancelBtn) quickCancelBtn.addEventListener('click', handleCancelRequest);

    const macroCancelBtn = shadowRoot.getElementById('btn-macro-cancel');
    if (macroCancelBtn) macroCancelBtn.addEventListener('click', handleCancelRequest);

    // Active Streak Macro Selection
    const activeMacroSel = shadowRoot.getElementById('sel-active-macro');
    if (activeMacroSel) {
      activeMacroSel.addEventListener('change', (e) => {
        config.activeMacro = e.target.value;
        saveConfig();
        log(`🎯 Active Primary Streak Macro set to: "${config.activeMacro}"`, 'info');
      });
    }

    // Quick Record Button (switch to Macros tab and trigger record)
    const quickRecBtn = shadowRoot.getElementById('btn-quick-record');
    if (quickRecBtn) {
      quickRecBtn.addEventListener('click', () => {
        switchTab('tab-macros');
        const recBtn = shadowRoot.getElementById('btn-macro-record');
        if (recBtn && recBtn.style.display !== 'none') {
          recBtn.click();
        }
      });
    }

    shadowRoot.getElementById('inp-step-delay').addEventListener('change', (e) => {
      config.stepDelay = parseFloat(e.target.value) || 3;
      saveConfig();
    });

    shadowRoot.getElementById('chk-human-mode').addEventListener('change', (e) => {
      config.humanMode = e.target.checked;
      saveConfig();
      log(`Human-like mode ${config.humanMode ? 'enabled 👤' : 'disabled ⚡'}.`, 'info');
    });

    shadowRoot.getElementById('chk-wait-ui').addEventListener('change', (e) => {
      config.waitForUIChanges = e.target.checked;
      saveConfig();
      log(`Wait for significant UI changes ${config.waitForUIChanges ? 'enabled ⏳' : 'disabled'}.`, 'info');
    });

    // Friends Tab
    shadowRoot.getElementById('btn-save-friends').addEventListener('click', () => {
      const raw = shadowRoot.getElementById('inp-friends').value;
      const list = raw.split('\n').map(s => s.trim().replace(/^@/, '')).filter(Boolean);
      config.friends = list;
      saveConfig();
      updateFriendsCount();
    });

    // Schedule Tab Handlers
    const chkSchedule = shadowRoot.getElementById('chk-schedule-enabled');
    const inpSchedule = shadowRoot.getElementById('inp-schedule-time');

    const handleScheduleUpdate = () => {
      config.scheduleEnabled = chkSchedule.checked;
      config.scheduleTime = inpSchedule.value || '09:00';
      saveConfig();
      updateScheduleUIStatus();
      log(`⏰ Schedule updated: ${config.scheduleEnabled ? config.scheduleTime : 'Disabled'}`, 'success');
    };

    chkSchedule.addEventListener('change', handleScheduleUpdate);
    inpSchedule.addEventListener('change', handleScheduleUpdate);
    shadowRoot.getElementById('btn-save-schedule').addEventListener('click', handleScheduleUpdate);

    // Test Scheduled Trigger Now button
    const testSchedBtn = shadowRoot.getElementById('btn-test-schedule-now');
    if (testSchedBtn) {
      testSchedBtn.addEventListener('click', () => {
        log('⚡ Testing background scheduled trigger...', 'info');
        chrome.runtime.sendMessage({ type: 'TRIGGER_TEST_SCHEDULE' }, (resp) => {
          if (chrome.runtime.lastError) {
            log(`❌ Background trigger error: ${chrome.runtime.lastError.message}`, 'err');
          } else {
            log('✓ Background service worker accepted schedule test trigger!', 'success');
          }
        });
      });
    }

    // Macro Recording Buttons
    const recBtn = shadowRoot.getElementById('btn-macro-record');
    const stopBtn = shadowRoot.getElementById('btn-macro-stop');
    const recBanner = shadowRoot.getElementById('rec-banner');

    recBtn.addEventListener('click', () => {
      window.SnapStreakMacro.startRecording();
      recBtn.style.display = 'none';
      stopBtn.style.display = 'block';
      recBanner.style.display = 'flex';
      updateMacroStepCount(0);
    });

    stopBtn.addEventListener('click', async () => {
      const name = prompt('Enter a name for this macro:', `Streak Macro ${new Date().toLocaleDateString()}`) || 'Streak Macro';
      await window.SnapStreakMacro.stopRecording(name);
      recBtn.style.display = 'block';
      stopBtn.style.display = 'none';
      recBanner.style.display = 'none';
      refreshMacroDropdowns();
    });

    // Macro Replay & Delete
    shadowRoot.getElementById('btn-macro-replay').addEventListener('click', async () => {
      const selected = shadowRoot.getElementById('sel-saved-macros').value;
      if (!selected) {
        alert('Please select a macro to replay first.');
        return;
      }
      await window.SnapStreakMacro.replayMacro(selected, config.stepDelay, config.waitForUIChanges);
    });

    shadowRoot.getElementById('btn-macro-delete').addEventListener('click', async () => {
      const selected = shadowRoot.getElementById('sel-saved-macros').value;
      if (!selected) return;
      if (confirm(`Delete macro "${selected}"?`)) {
        await window.SnapStreakMacro.deleteMacro(selected);
        refreshMacroDropdowns();
      }
    });

    // Clear Logs
    shadowRoot.getElementById('btn-clear-logs').addEventListener('click', () => {
      const box = shadowRoot.getElementById('hud-log-box');
      if (box) box.innerHTML = '';
    });
  }

  function updateFriendsCount() {
    const count = config.friends.length;
    const badge = shadowRoot.getElementById('friends-count-badge');
    const counter = shadowRoot.getElementById('friends-counter');
    if (badge) badge.textContent = `${count} Friend${count !== 1 ? 's' : ''}`;
    if (counter) counter.textContent = `${count} Added`;
  }

  async function refreshMacroDropdowns() {
    const saved = await window.SnapStreakMacro.getSavedMacros();
    const activeSelect = shadowRoot.getElementById('sel-active-macro');
    const macroSelect = shadowRoot.getElementById('sel-saved-macros');
    if (!activeSelect && !macroSelect) return;

    if (activeSelect) activeSelect.innerHTML = '';
    if (macroSelect) macroSelect.innerHTML = '';

    const keys = Object.keys(saved);
    if (keys.length === 0) {
      if (activeSelect) activeSelect.innerHTML = '<option value="">(No macros available)</option>';
      if (macroSelect) macroSelect.innerHTML = '<option value="">(No saved macros)</option>';
      return;
    }

    keys.forEach(k => {
      const isDef = saved[k].isDefault;
      const count = saved[k].steps ? saved[k].steps.length : 0;

      if (activeSelect) {
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = isDef ? `⚡ ${k} (${count} steps)` : `🎬 ${k} (${count} steps)`;
        activeSelect.appendChild(opt);
      }

      if (macroSelect) {
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = isDef ? `⚡ ${k} (${count} steps)` : `${k} (${count} steps)`;
        macroSelect.appendChild(opt);
      }
    });

    if (activeSelect) {
      if (config.activeMacro && saved[config.activeMacro]) {
        activeSelect.value = config.activeMacro;
      } else if (activeSelect.options.length > 0) {
        activeSelect.selectedIndex = 0;
        config.activeMacro = activeSelect.value;
      }
    }
  }

  async function populateUI() {
    await loadConfig();
    if (!shadowRoot) return;

    const engineSel = shadowRoot.getElementById('sel-sending-engine');
    if (engineSel) engineSel.value = config.sendingEngine || 'direct';

    const directTargetSel = shadowRoot.getElementById('sel-direct-target');
    if (directTargetSel) directTargetSel.value = config.selectionMethod || 'shortcut';

    // Update visibility of sub-cards
    const boxDirect = shadowRoot.getElementById('box-direct-options');
    const boxMacro = shadowRoot.getElementById('box-macro-options');
    const engineBadge = shadowRoot.getElementById('engine-badge');
    if (config.sendingEngine === 'direct') {
      if (boxDirect) boxDirect.style.display = 'block';
      if (boxMacro) boxMacro.style.display = 'none';
      if (engineBadge) {
        engineBadge.textContent = 'DIRECT';
        engineBadge.style.background = 'var(--green)';
        engineBadge.style.color = '#000';
      }
    } else {
      if (boxDirect) boxDirect.style.display = 'none';
      if (boxMacro) boxMacro.style.display = 'block';
      if (engineBadge) {
        engineBadge.textContent = 'MACRO';
        engineBadge.style.background = 'var(--accent)';
        engineBadge.style.color = '#000';
      }
    }

    shadowRoot.getElementById('inp-friends').value = config.friends.join('\n');
    shadowRoot.getElementById('inp-step-delay').value = config.stepDelay;
    shadowRoot.getElementById('chk-human-mode').checked = config.humanMode ?? true;
    shadowRoot.getElementById('chk-wait-ui').checked = config.waitForUIChanges ?? true;
    shadowRoot.getElementById('chk-schedule-enabled').checked = config.scheduleEnabled;
    shadowRoot.getElementById('inp-schedule-time').value = config.scheduleTime;

    updateFriendsCount();
    refreshMacroDropdowns();
    updateScheduleUIStatus();
  }

  function updateScheduleUIStatus() {
    if (!shadowRoot) return;
    chrome.storage.local.get(['nextScheduledRunText', 'lastStreakSentDate', 'lastStreakSentTime', 'lastStreakStatus'], (res) => {
      const nextRunEl = shadowRoot.getElementById('schedule-next-run');
      const lastRunEl = shadowRoot.getElementById('schedule-last-run');
      const syncPill = shadowRoot.getElementById('schedule-sync-pill');

      if (syncPill) {
        syncPill.textContent = config.scheduleEnabled ? '● Active' : '○ Disabled';
        syncPill.style.color = config.scheduleEnabled ? 'var(--green)' : 'var(--text-dim)';
      }

      if (nextRunEl) {
        if (!config.scheduleEnabled) {
          nextRunEl.textContent = 'Next Run: Schedule Disabled';
        } else if (res.nextScheduledRunText) {
          nextRunEl.textContent = `Next Run: ${res.nextScheduledRunText}`;
        } else {
          nextRunEl.textContent = `Next Run: Daily at ${config.scheduleTime || '09:00'}`;
        }
      }

      if (lastRunEl) {
        if (res.lastStreakSentDate) {
          const statusIcon = res.lastStreakStatus === 'success' ? '🔥' : '⚠️';
          lastRunEl.textContent = `Last Run: ${res.lastStreakSentDate} at ${res.lastStreakSentTime || ''} (${statusIcon})`;
        } else {
          lastRunEl.textContent = 'Last Run: Not sent yet today';
        }
      }
    });
  }

  return {
    initUI,
    log,
    setRunning,
    updateMacroStepCount,
    toggleWindow,
    getConfig: () => config,
    refreshSJSUFrame
  };
})();
