/**
 * SnapStreak In-Page HUD Overlay Controller
 * Injects and manages the Shadow DOM UI over web.snapchat.com
 */

window.SnapStreakOverlay = (function() {
  'use strict';
  const OVERLAY_STYLES = `/* SnapStreak In-Page HUD Styles (Shadow DOM Encapsulated) */

:host {
  --bg-primary: #0e111a;
  --bg-card: #151926;
  --bg-input: #1f2538;
  --accent: #fffc00;
  --accent-text: #000000;
  --green: #10b981;
  --blue: #3b82f6;
  --red: #ef4444;
  --purple: #8b5cf6;
  --border: #262c42;
  --border-active: #3b4468;
  --text: #f8fafc;
  --text-dim: #94a3b8;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono-font: "Consolas", "Fira Mono", monospace;
  font-family: var(--font);
  font-size: 13px;
  line-height: 1.4;
  color: var(--text);
  box-sizing: border-box;
  all: initial;
  font-family: var(--font);
}

*, *::before, *::after {
  box-sizing: border-box;
}

/* Floating Launcher Pill Button */
#snapstreak-pill {
  position: fixed;
  top: 18px;
  right: 24px;
  z-index: 2147483647;
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #181c2c 0%, #0d101a 100%);
  border: 1.5px solid #333a56;
  border-radius: 28px;
  padding: 8px 14px;
  color: #fff;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.55), 0 0 12px rgba(255, 252, 0, 0.2);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

#snapstreak-pill:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.7), 0 0 18px rgba(255, 252, 0, 0.4);
}

.pill-icon {
  font-size: 16px;
  line-height: 1;
}

.pill-label {
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.pill-badge {
  background: var(--green);
  color: #000;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 10px;
}

/* Main HUD Window */
#snapstreak-window {
  position: fixed;
  top: 70px;
  right: 24px;
  width: 380px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 100px);
  z-index: 2147483647;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 20px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: opacity 0.2s, transform 0.2s;
  backdrop-filter: blur(12px);
}

#snapstreak-window.hidden {
  display: none !important;
}

/* Embedded Dock Mode (Default: Docked to right side of Snapchat Web) */
#snapstreak-window.embedded-dock {
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  left: auto !important;
  width: 360px !important;
  max-width: 90vw !important;
  height: 100vh !important;
  max-height: 100vh !important;
  border-radius: 0 !important;
  border: none !important;
  border-left: 2px solid var(--border-active) !important;
  box-shadow: -10px 0 35px rgba(0, 0, 0, 0.75) !important;
  transform: translateX(0);
  transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s !important;
}

#snapstreak-window.embedded-dock.collapsed {
  transform: translateX(100%) !important;
  pointer-events: none;
}

#snapstreak-window.embedded-dock.collapsed #snapstreak-dock-tab {
  pointer-events: auto;
}

/* Edge Dock Tab Handle */
#snapstreak-dock-tab {
  display: none;
  position: absolute;
  left: -36px;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 78px;
  background: #141825;
  border: 1px solid var(--border-active);
  border-right: none;
  border-radius: 12px 0 0 12px;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 4px;
  box-shadow: -6px 0 16px rgba(0, 0, 0, 0.6);
  transition: background 0.2s, border-color 0.2s, transform 0.2s;
  user-select: none;
  z-index: 2147483646;
}

#snapstreak-window.embedded-dock #snapstreak-dock-tab {
  display: flex;
}

#snapstreak-dock-tab:hover {
  background: #1d2236;
  border-color: var(--accent);
}

.dock-tab-icon {
  font-size: 16px;
  line-height: 1;
}

.dock-tab-arrow {
  font-size: 11px;
  color: var(--accent);
  font-weight: 800;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

#snapstreak-window.embedded-dock.collapsed #snapstreak-dock-tab .dock-tab-arrow {
  transform: rotate(180deg);
}

/* Embedded Top Quickbar Ribbon on Snapchat Web */
#snapstreak-quickbar {
  position: fixed;
  top: 10px;
  right: 380px;
  z-index: 2147483645;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(14, 17, 26, 0.94);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 4px 10px;
  border-radius: 24px;
  border: 1px solid var(--border-active);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.65), 0 0 12px rgba(255, 252, 0, 0.12);
  transition: right 0.28s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s;
  user-select: none;
}

#snapstreak-quickbar.dock-collapsed {
  right: 48px;
}

.quickbar-brand {
  display: flex;
  align-items: center;
  gap: 5px;
  padding-right: 6px;
  border-right: 1px solid var(--border);
}

.quickbar-title {
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 0.4px;
  color: #fff;
}

.quickbar-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--text-dim);
  padding-right: 4px;
}

.quickbar-btn {
  border: none;
  border-radius: 14px;
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.quickbar-btn-primary {
  background: var(--accent);
  color: #000;
}

.quickbar-btn-primary:hover {
  background: #ffe600;
  transform: translateY(-1px);
}

.quickbar-btn-test {
  background: #20273c;
  color: var(--accent);
  border: 1px solid var(--border-active);
}

.quickbar-btn-test:hover {
  background: #2b3452;
  border-color: var(--accent);
}

.quickbar-btn-warn {
  background: #f59e0b;
  color: #000;
}

.quickbar-btn-danger {
  background: var(--red);
  color: #fff;
}

.quickbar-btn-secondary {
  background: #181c2c;
  color: #cbd5e1;
  border: 1px solid var(--border);
}

.quickbar-btn-secondary:hover {
  color: #fff;
  border-color: var(--border-active);
}

/* Window Header */
.hud-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: #141825;
  border-bottom: 1px solid var(--border);
  cursor: move;
  user-select: none;
}

.hud-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hud-logo {
  width: 24px;
  height: 24px;
  border-radius: 6px;
}

.hud-title {
  font-weight: 800;
  font-size: 13px;
  color: #fff;
  letter-spacing: 0.3px;
}

.hud-header-actions {
  display: flex;
  gap: 6px;
}

.hud-btn-icon {
  background: transparent;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.hud-btn-icon:hover {
  background: var(--bg-input);
  color: #fff;
}

/* Tab Navigation */
.hud-tabs {
  display: flex;
  background: #111420;
  border-bottom: 1px solid var(--border);
  padding: 2px 6px;
  gap: 2px;
  overflow-x: auto;
}

.hud-tab-btn {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
  border-radius: 4px 4px 0 0;
}

.hud-tab-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.04);
}

.hud-tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: rgba(255, 252, 0, 0.08);
}

/* Body & Content */
.hud-body {
  padding: 14px;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tab-pane {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.tab-pane.active {
  display: flex;
}

/* Cards & Sections */
.hud-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hud-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Status Banner */
.hud-status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #111524;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 12px;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}

.status-dot.busy {
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent);
  animation: blink 1s infinite;
}

.status-dot.error {
  background: var(--red);
  box-shadow: 0 0 8px var(--red);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Form Controls */
label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
}

select, input[type="text"], input[type="time"], input[type="number"], textarea {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 8px 10px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

select:focus, input:focus, textarea:focus {
  border-color: var(--accent);
}

textarea {
  resize: vertical;
  min-height: 70px;
  font-family: var(--mono-font);
  font-size: 11px;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 14px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
  box-shadow: 0 4px 14px rgba(255, 252, 0, 0.25);
}

.btn-primary:hover:not(:disabled) {
  background: #fff833;
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(255, 252, 0, 0.4);
}

.btn-success {
  background: var(--green);
  color: #000;
}

.btn-success:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-danger {
  background: var(--red);
  color: #fff;
}

.btn-danger:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-test {
  background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
  color: #ffffff;
  border: 1px solid #38bdf8;
  box-shadow: 0 4px 14px rgba(2, 132, 199, 0.35);
}

.btn-test:hover:not(:disabled) {
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  box-shadow: 0 6px 18px rgba(2, 132, 199, 0.55);
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--bg-input);
  color: var(--text);
  border: 1px solid var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: #283049;
  border-color: var(--border-active);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
}

.btn-full {
  width: 100%;
}

.btn-row {
  display: flex;
  gap: 8px;
}

/* Switch Toggle */
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background-color: #242b40;
  border-radius: 22px;
  transition: .2s;
  border: 1px solid var(--border);
}

.toggle-slider::before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: #94a3b8;
  border-radius: 50%;
  transition: .2s;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: var(--green);
  border-color: var(--green);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(18px);
  background-color: #000;
}

/* Log Box */
#hud-log-box {
  background: #090b12;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-family: var(--mono-font);
  font-size: 11px;
  line-height: 1.6;
  max-height: 180px;
  min-height: 90px;
  overflow-y: auto;
  color: #79f79e;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-info { color: var(--accent); }
.log-err { color: var(--red); }
.log-success { color: var(--green); font-weight: 700; }

/* Macro Recorder Banner */
.macro-recording-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #3b111b;
  border: 1px solid #771d32;
  color: #ff88a3;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}

.rec-pulse-dot {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: blink 0.8s infinite;
}

/* Custom Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
}
::-webkit-scrollbar-thumb {
  background: #2a324b;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #3d476b;
}
`;


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
    endTaskOnComplete: true,
    alwaysCloseOtherTabs: true,
    activeMacro: '⚡ Default Streak Macro',
    isDocked: true,
    isDockCollapsed: false
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

    try {
      fetch('http://127.0.0.1:8080/api/extension/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, type: type })
      }).catch(() => {});
    } catch(e) {}
  }

  function setRunning(running, isTest = false) {
    isRunning = running;
    if (!shadowRoot) return;
    const autoSendBtn = shadowRoot.getElementById('btn-auto-send-streaks') || shadowRoot.getElementById('btn-send-streaks');
    const testBtn = shadowRoot.getElementById('btn-test-streaks');
    const pauseBtn = shadowRoot.getElementById('btn-pause-resume');
    const cancelBtn = shadowRoot.getElementById('btn-cancel-running');
    const quickCancelBtn = shadowRoot.getElementById('btn-quick-cancel');
    const macroCancelBtn = shadowRoot.getElementById('btn-macro-cancel');
    const macroReplayBtn = shadowRoot.getElementById('btn-macro-replay');
    const dot = shadowRoot.getElementById('status-dot');
    const label = shadowRoot.getElementById('status-text');
    const pillBadge = shadowRoot.getElementById('pill-badge');
    const qbSend = shadowRoot.getElementById('qb-btn-send');
    const qbPrev = shadowRoot.getElementById('qb-btn-preview');
    const qbPause = shadowRoot.getElementById('qb-btn-pause');
    const qbStop = shadowRoot.getElementById('qb-btn-stop');
    const qbDot = shadowRoot.getElementById('quickbar-dot');
    const qbText = shadowRoot.getElementById('quickbar-text');

    if (running) {
      if (autoSendBtn) {
        autoSendBtn.disabled = true;
        autoSendBtn.textContent = isTest ? '🔥 Auto Send Streaks' : '⏳ Auto Sending...';
      }
      if (testBtn) {
        testBtn.disabled = true;
        testBtn.textContent = isTest ? '🧪 Sample Running...' : '🧪 Sample Preview';
      }
      if (macroReplayBtn) macroReplayBtn.disabled = true;
      if (pauseBtn) {
        pauseBtn.style.display = 'inline-flex';
        pauseBtn.textContent = '⏸️ Pause';
      }
      if (cancelBtn) cancelBtn.style.display = 'inline-flex';
      if (quickCancelBtn) quickCancelBtn.style.display = 'inline-flex';
      if (macroCancelBtn) macroCancelBtn.style.display = 'block';
      if (dot) dot.className = 'status-dot busy';
      if (label) label.textContent = isTest ? 'Sample Preview (Pauses before Send)...' : 'Executing Streak Send...';
      if (pillBadge) {
        pillBadge.textContent = isTest ? 'Previewing' : 'Busy';
        pillBadge.style.background = isTest ? 'var(--blue)' : 'var(--green)';
      }
      if (qbSend) { qbSend.disabled = true; qbSend.textContent = isTest ? '🔥 Send Streaks' : '⏳ Sending...'; }
      if (qbPrev) { qbPrev.disabled = true; qbPrev.textContent = isTest ? '🧪 Previewing...' : '🧪 Preview'; }
      if (qbPause) { qbPause.style.display = 'inline-flex'; qbPause.textContent = '⏸️ Pause'; }
      if (qbStop) { qbStop.style.display = 'inline-flex'; }
      if (qbDot) { qbDot.className = 'status-dot busy'; }
      if (qbText) { qbText.textContent = isTest ? 'Previewing' : 'Sending'; }
    } else {
      if (autoSendBtn) {
        autoSendBtn.disabled = false;
        autoSendBtn.textContent = '🔥 Auto Send Streaks';
      }
      if (testBtn) {
        testBtn.disabled = false;
        testBtn.textContent = '🧪 Sample Preview';
      }
      if (macroReplayBtn) macroReplayBtn.disabled = false;
      if (pauseBtn) {
        pauseBtn.style.display = 'none';
        pauseBtn.textContent = '⏸️ Pause';
      }
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (quickCancelBtn) quickCancelBtn.style.display = 'none';
      if (macroCancelBtn) macroCancelBtn.style.display = 'none';
      if (dot) dot.className = 'status-dot';
      if (label) label.textContent = 'Idle (Ready)';
      if (pillBadge) {
        pillBadge.textContent = 'Ready';
        pillBadge.style.background = 'var(--green)';
      }
      if (qbSend) { qbSend.disabled = false; qbSend.textContent = '🔥 Send Streaks'; }
      if (qbPrev) { qbPrev.disabled = false; qbPrev.textContent = '🧪 Preview'; }
      if (qbPause) { qbPause.style.display = 'none'; }
      if (qbStop) { qbStop.style.display = 'none'; }
      if (qbDot) { qbDot.className = 'status-dot'; }
      if (qbText) { qbText.textContent = 'Idle'; }
    }
  }

  function updateMacroStepCount(count) {
    if (!shadowRoot) return;
    const badge = shadowRoot.getElementById('rec-step-count');
    if (badge) badge.textContent = `${count} step${count !== 1 ? 's' : ''}`;
  }

  async function loadConfig() {
    return new Promise(resolve => {
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local.get(['snapstreak_config'], res => {
          if (res && res.snapstreak_config) {
            config = { ...config, ...res.snapstreak_config };
          }
          resolve(config);
        });
      } else {
        try {
          const saved = localStorage.getItem('snapstreak_config');
          if (saved) config = { ...config, ...JSON.parse(saved) };
        } catch(e) {}
        resolve(config);
      }
    });
  }

  async function saveConfig() {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        await chrome.storage.local.set({ snapstreak_config: config });
      }
      localStorage.setItem('snapstreak_config', JSON.stringify(config));
    } catch(e) {}
    try {
      if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
        chrome.runtime.sendMessage({
          type: 'CONFIG_UPDATED',
          config: config
        });
      }
    } catch(e) {}
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
    if (!document.body) {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI, { once: true });
      } else {
        setTimeout(initUI, 200);
      }
      return;
    }

    if (document.getElementById('snapstreak-shadow-host')) return;

    const host = document.createElement('div');
    host.id = 'snapstreak-shadow-host';
    host.style.position = 'fixed';
    host.style.top = '0';
    host.style.left = '0';
    host.style.width = '0';
    host.style.height = '0';
    host.style.zIndex = '2147483647';
    host.style.pointerEvents = 'none';
    document.body.appendChild(host);

    shadowRoot = host.attachShadow({ mode: 'open' });

    const styleEl = document.createElement('style');
    styleEl.textContent = OVERLAY_STYLES;
    shadowRoot.appendChild(styleEl);

    try {
      if (typeof chrome !== 'undefined' && chrome.runtime?.getURL) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = chrome.runtime.getURL('overlay.css');
        shadowRoot.appendChild(link);
      }
    } catch(e) {}

    const LOGO_SVG = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='48' fill='%23fffc00'/><text x='50' y='68' font-size='42' text-anchor='middle' fill='%23000'>⚡</text></svg>";
    let logoSrc = LOGO_SVG;
    try {
      if (typeof chrome !== 'undefined' && chrome.runtime?.getURL) {
        logoSrc = chrome.runtime.getURL('icons/icon48.png');
      }
    } catch(e) {}

    if (window.innerWidth >= 800) {
      isWindowOpen = true;
      config.isDockCollapsed = false;
    }

    const container = document.createElement('div');
    container.innerHTML = `
      <!-- Launcher Pill Button (Visible in Floating Mode) -->
      <div id="snapstreak-pill" title="Toggle SnapStreak Controls">
        <span class="pill-icon">🔥</span>
        <span class="pill-label">SnapStreak</span>
        <span class="pill-badge" id="pill-badge">Ready</span>
      </div>

      <!-- Embedded Top Quickbar Ribbon on Snapchat Web -->
      <div id="snapstreak-quickbar" class="${(config.isDocked && config.isDockCollapsed) ? 'dock-collapsed' : ''}" title="SnapStreak Quick Action Ribbon">
        <div class="quickbar-brand">
          <span style="font-size: 15px;">🔥</span>
          <span class="quickbar-title">SnapStreak</span>
        </div>
        <div class="quickbar-status">
          <div class="status-dot" id="quickbar-dot"></div>
          <span id="quickbar-text">Idle</span>
        </div>
        <button class="quickbar-btn quickbar-btn-primary" id="qb-btn-send" title="Auto Send Streaks">
          🔥 Send Streaks
        </button>
        <button class="quickbar-btn quickbar-btn-test" id="qb-btn-preview" title="Preview streak capture without sending">
          🧪 Preview
        </button>
        <button class="quickbar-btn quickbar-btn-warn" id="qb-btn-pause" style="display: none;" title="Pause / Resume">
          ⏸️ Pause
        </button>
        <button class="quickbar-btn quickbar-btn-danger" id="qb-btn-stop" style="display: none;" title="Stop active task">
          ⏹️ Stop
        </button>
        <button class="quickbar-btn quickbar-btn-secondary" id="qb-btn-toggle-dock" title="Toggle SnapStreak Sidebar">
          📌 Panel
        </button>
      </div>

      <!-- Main HUD Window (Embedded Right Dock) -->
      <div id="snapstreak-window" class="${config.isDocked ? 'embedded-dock' : ''} ${(!isWindowOpen || config.isDockCollapsed) ? (config.isDocked ? 'collapsed' : 'hidden') : ''}">
        <!-- Edge Dock Tab Handle -->
        <div id="snapstreak-dock-tab" title="Toggle SnapStreak Embedded Sidebar">
          <span class="dock-tab-icon">🔥</span>
          <span class="dock-tab-arrow">◀</span>
        </div>

        <!-- Header -->
        <div class="hud-header" id="hud-header">
          <div class="hud-title-wrap">
            <img class="hud-logo" src="${logoSrc}" alt="SnapStreak Logo" />
            <span class="hud-title">SnapStreak Controller</span>
          </div>
          <div class="hud-header-actions">
            <button class="hud-btn-icon" id="btn-toggle-dock" title="Switch Docked / Float Window">${config.isDocked ? '📌' : '🪟'}</button>
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
            <div style="display: flex; align-items: center; gap: 6px;">
              <button class="btn btn-warning" id="btn-keep-open" style="display: none; padding: 3px 8px; font-size: 11px; font-weight: 700; border-radius: 4px;" title="Keep browser open and cancel auto-close">
                🪟 Keep Open
              </button>
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
                <button class="btn btn-test btn-full" id="btn-test-streaks" style="font-size: 13px; padding: 11px; font-weight: 700;" title="Test camera & recipient selection with visual confirmation before final send">
                  🧪 Sample Preview
                </button>
              </div>
              <div class="btn-row" style="margin-top: 6px;">
                <button class="btn btn-secondary" id="btn-pause-resume" style="flex: 1; font-size: 12px; padding: 8px; font-weight: 700; display: none;" title="Pause or Resume active automation task">
                  ⏸️ Pause
                </button>
                <button class="btn btn-danger" id="btn-cancel-running" style="flex: 1; font-size: 12px; padding: 8px; font-weight: 700; display: none;" title="Abort in-flight streak execution immediately">
                  ⏹️ Stop Task
                </button>
              </div>
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
              <div class="toggle-row" style="margin-top: 10px;">
                <div>
                  <div style="font-size: 11px; font-weight: 600; color: #fff;">🔚 End Task on Completion</div>
                  <div style="font-size: 10px; color: var(--text-dim);">Close browser window when daily streaks finish</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="chk-end-task-on-complete" checked />
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <div class="toggle-row" style="margin-top: 10px;">
                <div>
                  <div style="font-size: 11px; font-weight: 600; color: #fff;">🛡️ Always Close Other Tabs</div>
                  <div style="font-size: 10px; color: var(--text-dim);">Auto-close any other tabs to keep only active run</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="chk-always-close-other-tabs" checked />
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <label style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span>Daily Send Times (Local Time)</span>
                <button type="button" class="btn btn-secondary" id="btn-add-schedule-time" style="padding: 2px 8px; font-size: 11px; font-weight: bold; color: var(--accent); border-color: var(--accent);" title="Add another daily send time">
                  ➕ Add Time
                </button>
              </label>
              <div id="schedule-times-container" style="display: flex; flex-direction: column; gap: 6px; margin-top: 6px; margin-bottom: 6px;">
                <!-- Populated dynamically -->
              </div>
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

  function toggleDock(force) {
    const win = shadowRoot?.getElementById('snapstreak-window');
    const qb = shadowRoot?.getElementById('snapstreak-quickbar');
    if (!win) return;
    const isCurrentlyCollapsed = win.classList.contains('collapsed');
    const shouldCollapse = (typeof force === 'boolean') ? !force : !isCurrentlyCollapsed;

    if (shouldCollapse) {
      win.classList.add('collapsed');
      qb?.classList.add('dock-collapsed');
      config.isDockCollapsed = true;
    } else {
      win.classList.remove('collapsed');
      win.classList.remove('hidden');
      qb?.classList.remove('dock-collapsed');
      config.isDockCollapsed = false;
    }
  }

  function setDockedMode(docked) {
    const win = shadowRoot?.getElementById('snapstreak-window');
    const btn = shadowRoot?.getElementById('btn-toggle-dock');
    if (!win) return;
    config.isDocked = docked;
    if (docked) {
      win.classList.add('embedded-dock');
      win.style.left = '';
      win.style.top = '';
      win.style.right = '';
      if (btn) btn.textContent = '📌';
      if (btn) btn.title = 'Switch to Floating Window';
    } else {
      win.classList.remove('embedded-dock');
      win.classList.remove('collapsed');
      win.style.right = '24px';
      win.style.top = '70px';
      if (btn) btn.textContent = '🪟';
      if (btn) btn.title = 'Switch to Embedded Dock';
    }
    saveConfig();
  }

  function toggleWindow(force) {
    const win = shadowRoot?.getElementById('snapstreak-window');
    if (!win) return;
    if (config.isDocked && win.classList.contains('embedded-dock')) {
      toggleDock(force);
      return;
    }
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

    // Edge Dock Tab and header toggle
    const dockTab = shadowRoot.getElementById('snapstreak-dock-tab');
    if (dockTab) dockTab.addEventListener('click', () => toggleDock());

    const btnToggleDock = shadowRoot.getElementById('btn-toggle-dock');
    if (btnToggleDock) btnToggleDock.addEventListener('click', () => setDockedMode(!config.isDocked));

    // Top Quickbar Buttons
    const qbSend = shadowRoot.getElementById('qb-btn-send');
    if (qbSend) qbSend.addEventListener('click', () => {
      const autoSendBtn = shadowRoot.getElementById('btn-auto-send-streaks') || shadowRoot.getElementById('btn-send-streaks');
      autoSendBtn?.click();
    });

    const qbPrev = shadowRoot.getElementById('qb-btn-preview');
    if (qbPrev) qbPrev.addEventListener('click', () => {
      const testBtn = shadowRoot.getElementById('btn-test-streaks');
      testBtn?.click();
    });

    const qbPause = shadowRoot.getElementById('qb-btn-pause');
    if (qbPause) qbPause.addEventListener('click', () => {
      const pauseBtn = shadowRoot.getElementById('btn-pause-resume');
      pauseBtn?.click();
    });

    const qbStop = shadowRoot.getElementById('qb-btn-stop');
    if (qbStop) qbStop.addEventListener('click', () => {
      const cancelBtn = shadowRoot.getElementById('btn-cancel-running');
      cancelBtn?.click();
    });

    const qbToggle = shadowRoot.getElementById('qb-btn-toggle-dock');
    if (qbToggle) qbToggle.addEventListener('click', () => toggleDock());

    // Tab switching
    const tabButtons = shadowRoot.querySelectorAll('.hud-tab-btn');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        switchTab(btn.dataset.tab);
      });
    });

    // Drag-and-drop window repositioning (only in floating mode)
    const header = shadowRoot.getElementById('hud-header');
    const win = shadowRoot.getElementById('snapstreak-window');
    let isDragging = false, startX, startY, origLeft, origTop;

    header.addEventListener('pointerdown', (e) => {
      if (win.classList.contains('embedded-dock')) return; // Keep cleanly docked
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

    // ⏸️ Pause / ▶️ Resume running task
    const pauseBtn = shadowRoot.getElementById('btn-pause-resume');
    if (pauseBtn) {
      pauseBtn.addEventListener('click', () => {
        if (!window.SnapStreakAutomation) return;
        if (window.SnapStreakAutomation.isPaused && window.SnapStreakAutomation.isPaused()) {
          window.SnapStreakAutomation.resume();
          pauseBtn.textContent = '⏸️ Pause';
          const label = shadowRoot.getElementById('status-text');
          if (label) label.textContent = 'Executing Streak Send...';
          log('▶️ Automation task resumed.', 'info');
        } else {
          window.SnapStreakAutomation.pause();
          pauseBtn.textContent = '▶️ Resume';
          const label = shadowRoot.getElementById('status-text');
          if (label) label.textContent = '⏸️ Task Paused';
          log('⏸️ Automation task paused.', 'warn');
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
        if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
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

    // Multi-Schedule Times Management
    renderScheduleTimesUI();

    const addTimeBtn = shadowRoot.getElementById('btn-add-schedule-time');
    if (addTimeBtn) {
      addTimeBtn.addEventListener('click', () => {
        if (!config.scheduleTimes) config.scheduleTimes = [config.scheduleTime || '09:00'];
        config.scheduleTimes.push('18:00');
        saveConfig();
        renderScheduleTimesUI();
        updateScheduleUIStatus();
        log('➕ Added new schedule time slot (18:00). Update to desired time.', 'info');
      });
    }

    // Schedule Tab Handlers
    const chkSchedule = shadowRoot.getElementById('chk-schedule-enabled');
    const handleScheduleUpdate = () => {
      config.scheduleEnabled = chkSchedule.checked;
      const inputs = shadowRoot.querySelectorAll('.inp-sched-item');
      if (inputs.length > 0) {
        config.scheduleTimes = Array.from(inputs).map(i => i.value || '09:00');
        config.scheduleTime = config.scheduleTimes[0] || '09:00';
      }
      saveConfig();
      updateScheduleUIStatus();
      log(`⏰ Schedule updated: ${config.scheduleEnabled ? (config.scheduleTimes || [config.scheduleTime]).join(', ') : 'Disabled'}`, 'success');
    };

    chkSchedule.addEventListener('change', handleScheduleUpdate);
    shadowRoot.getElementById('btn-save-schedule').addEventListener('click', handleScheduleUpdate);

    // End Task On Complete Toggle
    const chkEndTask = shadowRoot.getElementById('chk-end-task-on-complete');
    if (chkEndTask) {
      chkEndTask.addEventListener('change', (e) => {
        config.endTaskOnComplete = e.target.checked;
        saveConfig();
        log(`End task on complete: ${config.endTaskOnComplete ? 'Enabled (Browser closes on finish) 🔚' : 'Disabled (Browser stays open) 🪟'}`, 'info');
      });
    }

    // Always Close Other Tabs Toggle
    const chkAlwaysClose = shadowRoot.getElementById('chk-always-close-other-tabs');
    if (chkAlwaysClose) {
      chkAlwaysClose.addEventListener('change', (e) => {
        config.alwaysCloseOtherTabs = e.target.checked;
        saveConfig();
        log(`Always close other tabs: ${config.alwaysCloseOtherTabs ? 'Enabled (Single tab mode) 🛡️' : 'Disabled'}`, 'info');
      });
    }

    // Keep Open Button (cancel auto-closing after daily automation completes)
    const keepOpenBtn = shadowRoot.getElementById('btn-keep-open');
    if (keepOpenBtn) {
      keepOpenBtn.addEventListener('click', () => {
        cancelEndTaskCountdown();
      });
    }

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
    const chkEndTask = shadowRoot.getElementById('chk-end-task-on-complete');
    if (chkEndTask) chkEndTask.checked = (config.endTaskOnComplete !== false);
    const chkAlwaysClose = shadowRoot.getElementById('chk-always-close-other-tabs');
    if (chkAlwaysClose) chkAlwaysClose.checked = (config.alwaysCloseOtherTabs !== false);

    updateFriendsCount();
    refreshMacroDropdowns();
    renderScheduleTimesUI();
    updateScheduleUIStatus();
  }

  function renderScheduleTimesUI() {
    if (!shadowRoot) return;
    const container = shadowRoot.getElementById('schedule-times-container');
    if (!container) return;
    container.innerHTML = '';

    const times = (config.scheduleTimes && config.scheduleTimes.length > 0)
      ? config.scheduleTimes
      : [config.scheduleTime || '09:00'];

    times.forEach((timeVal, idx) => {
      const row = document.createElement('div');
      row.style.cssText = 'display: flex; gap: 6px; align-items: center;';
      row.innerHTML = `
        <input type="time" class="inp-sched-item" value="${timeVal}" style="flex: 1;" />
        <button type="button" class="btn btn-secondary btn-del-time" data-idx="${idx}" style="padding: 4px 8px; font-size: 11px; color: var(--red); border-color: var(--red);" title="Remove this time">✕</button>
      `;
      container.appendChild(row);
    });

    // Bind input changes and delete clicks
    container.querySelectorAll('.inp-sched-item').forEach((inp, idx) => {
      inp.addEventListener('change', () => {
        if (!config.scheduleTimes) config.scheduleTimes = [];
        config.scheduleTimes[idx] = inp.value || '09:00';
        config.scheduleTime = config.scheduleTimes[0] || '09:00';
        saveConfig();
        updateScheduleUIStatus();
      });
    });

    container.querySelectorAll('.btn-del-time').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.idx, 10);
        if (config.scheduleTimes && config.scheduleTimes.length > 1) {
          config.scheduleTimes.splice(idx, 1);
          config.scheduleTime = config.scheduleTimes[0] || '09:00';
          saveConfig();
          renderScheduleTimesUI();
          updateScheduleUIStatus();
          log(`Removed schedule time slot #${idx + 1}.`, 'info');
        } else {
          alert('At least one schedule time must remain.');
        }
      });
    });
  }

  function updateScheduleUIStatus() {
    if (!shadowRoot) return;
    const nextRunEl = shadowRoot.getElementById('schedule-next-run');
    const lastRunEl = shadowRoot.getElementById('schedule-last-run');
    const syncPill = shadowRoot.getElementById('schedule-sync-pill');

    if (syncPill) {
      syncPill.textContent = config.scheduleEnabled ? '● Active' : '○ Disabled';
      syncPill.style.color = config.scheduleEnabled ? 'var(--green)' : 'var(--text-dim)';
    }

    if (nextRunEl) {
      nextRunEl.textContent = !config.scheduleEnabled ? 'Next Run: Schedule Disabled' : `Next Run: Daily at ${config.scheduleTime || '09:00'}`;
    }

    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['nextScheduledRunText', 'lastStreakSentDate', 'lastStreakSentTime', 'lastStreakStatus'], (res) => {
        if (!res) return;
        if (nextRunEl && res.nextScheduledRunText && config.scheduleEnabled) {
          nextRunEl.textContent = `Next Run: ${res.nextScheduledRunText}`;
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
  }

  let endTaskTimer = null;
  let endTaskSecondsLeft = 0;

  function triggerEndTaskCountdown(seconds = 5) {
    cancelEndTaskCountdown();
    endTaskSecondsLeft = seconds;

    const keepOpenBtn = shadowRoot?.getElementById('btn-keep-open');
    if (keepOpenBtn) keepOpenBtn.style.display = 'inline-block';

    const quickCancelBtn = shadowRoot?.getElementById('btn-quick-cancel');
    if (quickCancelBtn) quickCancelBtn.style.display = 'none';

    log(`🏁 Daily automation completed! Ending task & closing browser in ${seconds}s... (Click "Keep Open" to cancel)`, 'success');

    const updateStatus = () => {
      const statusText = shadowRoot?.getElementById('status-text');
      const statusDot = shadowRoot?.getElementById('status-dot');
      if (statusText) statusText.textContent = `Completed! Closing in ${endTaskSecondsLeft}s...`;
      if (statusDot) {
        statusDot.style.background = 'var(--green)';
        statusDot.style.boxShadow = '0 0 8px rgba(0, 230, 118, 0.6)';
      }
    };

    updateStatus();

    endTaskTimer = setInterval(() => {
      endTaskSecondsLeft--;
      if (endTaskSecondsLeft <= 0) {
        cancelEndTaskCountdown();
        log('🔚 Daily automation task finished. Closing browser window now.', 'info');
        try {
          if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
            chrome.runtime.sendMessage({ type: 'END_TASK_AND_CLOSE', reason: 'daily_automation_complete' });
          }
        } catch (e) {}
      } else {
        updateStatus();
      }
    }, 1000);
  }

  function cancelEndTaskCountdown() {
    if (endTaskTimer) {
      clearInterval(endTaskTimer);
      endTaskTimer = null;
      log('ℹ️ Auto-close cancelled by user. Browser will remain open.', 'info');
    }
    const keepOpenBtn = shadowRoot?.getElementById('btn-keep-open');
    if (keepOpenBtn) keepOpenBtn.style.display = 'none';
    const statusText = shadowRoot?.getElementById('status-text');
    if (statusText && statusText.textContent.includes('Closing in')) {
      statusText.textContent = 'Idle (Ready)';
    }
  }

  // Auto-mount HUD overlay when loaded on Snapchat Web
  function autoMount() {
    if (typeof window !== 'undefined' && window.location) {
      const href = window.location.href || '';
      const host = window.location.hostname || '';
      if (host.includes('snapchat.com') || href.includes('snapchat')) {
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', () => initUI());
        } else {
          initUI();
        }
      }
    }
  }

  try {
    autoMount();
  } catch(e) {}

  return {
    initUI,
    log,
    setRunning,
    updateMacroStepCount,
    toggleWindow,
    toggleDock,
    setDockedMode,
    isDocked: () => config.isDocked,
    getConfig: () => config,
    refreshSJSUFrame,
    triggerEndTaskCountdown,
    cancelEndTaskCountdown
  };
})();
