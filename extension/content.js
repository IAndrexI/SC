/**
 * SnapStreak Content Script Entry Point
 * Injected into web.snapchat.com
 */

(function() {
  'use strict';

  // Inject camera_hook.js into page context if needed
  function ensureCameraHook() {
    try {
      if (!document.getElementById('snapstreak-camera-hook-script')) {
        const script = document.createElement('script');
        script.id = 'snapstreak-camera-hook-script';
        script.src = chrome.runtime.getURL('camera_hook.js');
        (document.head || document.documentElement).appendChild(script);
      }
    } catch(e) {}
  }

  ensureCameraHook();

  function isVisible(el) {
    if (!el) return false;
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true });
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // Startup Auto-Refresh & Multi-Tab Error Resolver
  function setupStartupMultiTabHandler() {
    // 1. Resolve "Use Here" / "Snapchat is open in another window" modals
    function checkAndResolveMultiTab() {
      const buttons = document.querySelectorAll('button, div[role="button"], a');
      for (const btn of buttons) {
        if (!isVisible(btn)) continue;
        const text = (btn.textContent || '').trim().toLowerCase();
        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (
          text === 'use here' || text.includes('use here') ||
          text === 'open here' || text.includes('open here') ||
          text.includes('open here instead') ||
          text.includes('open web') ||
          text === 'reload' || text.includes('reload page') ||
          aria.includes('use here') || aria.includes('open here')
        ) {
          console.log('[SnapStreak] Found "Use Here" multi-tab override button, auto-clicking...', btn);
          window.SnapStreakOverlay?.log('✓ Auto-clicked "Use Here" to resolve multi-tab session conflict!', 'success');
          btn.click();
          return true;
        }
      }

      const bodyText = (document.body?.innerText || '').toLowerCase();
      if (
        bodyText.includes('open in another tab') ||
        bodyText.includes('open in another window') ||
        bodyText.includes('snapchat is open in another') ||
        bodyText.includes('multiple tabs of it are opened') ||
        bodyText.includes('multiple tabs')
      ) {
        console.log('[SnapStreak] Multi-tab error text detected on screen. Auto-refreshing page to clear lock...');
        window.SnapStreakOverlay?.log('⚠️ Multi-tab error detected. Auto-refreshing to clear session lock...', 'warning');
        setTimeout(() => {
          window.location.reload();
        }, 1200);
        return true;
      }
      return false;
    }

    const intervalId = setInterval(checkAndResolveMultiTab, 1000);
    setTimeout(() => clearInterval(intervalId), 25000);

    const observer = new MutationObserver(checkAndResolveMultiTab);
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => observer.disconnect(), 25000);
    }

    // 2. Perform one-time startup refresh to clear stale sessions on initial boot
    const hasStartupRefreshed = sessionStorage.getItem('snapstreak_startup_refreshed');
    if (!hasStartupRefreshed) {
      if (window.location.search.includes('snapstreak_scheduled') || window.location.search.includes('snapstreak_autoboot')) {
        sessionStorage.setItem('snapstreak_startup_refreshed', 'true');
      } else {
        sessionStorage.setItem('snapstreak_startup_refreshed', 'true');
        console.log('[SnapStreak] New browser session detected. Performing initial refresh in 3s to clear multi-tab lock...');
        setTimeout(() => {
          window.SnapStreakOverlay?.log('🔄 Performing initial startup refresh to clear multi-tab session lock...', 'info');
          setTimeout(() => {
            window.location.reload();
          }, 800);
        }, 3000);
      }
    }
  }

  // Auto-Boot Streak Trigger (when launched on startup/reboot)
  function checkAutoBootRoutine() {
    const isAutoBoot = window.location.search.includes('snapstreak_autoboot=1') ||
                       localStorage.getItem('snapstreak_autoboot_enabled') === 'true';
    if (!isAutoBoot) return;

    if (sessionStorage.getItem('snapstreak_autoboot_done') === 'true') return;

    console.log('[SnapStreak] Auto-boot sequence active! Scheduling streak delivery...');
    window.SnapStreakOverlay?.log('🚀 Auto-boot streak routine scheduled on boot...', 'info');

    // Wait 8.5 seconds for page load, camera feed, and initial refresh to settle
    setTimeout(async () => {
      sessionStorage.setItem('snapstreak_autoboot_done', 'true');
      if (window.SnapStreakAutomation) {
        window.SnapStreakOverlay?.log('🔥 Starting automated streak sequence...', 'info');
        try {
          const cfg = window.SnapStreakOverlay?.getConfig() || {};
          const res = await window.SnapStreakAutomation.runSendStreaks({
            friends: cfg.friends || ['*//Eric\\*', 'Dylan'],
            selectionMethod: cfg.selectionMethod || 'auto',
            stepDelay: cfg.stepDelay || 3,
            humanMode: cfg.humanMode ?? true,
            isTest: false
          });
          if (res && res.success) {
            window.SnapStreakOverlay?.log('🎉 Auto-boot streaks sent successfully!', 'success');
            chrome.runtime.sendMessage({ type: 'STREAK_SEND_SUCCESS', recipientsCount: (cfg.friends || []).length });
          } else {
            chrome.runtime.sendMessage({ type: 'STREAK_SEND_FAILURE', error: res?.error || 'Auto-boot sequence incomplete' });
          }
        } catch (err) {
          window.SnapStreakOverlay?.log(`❌ Auto-boot streak send error: ${err.message}`, 'err');
          chrome.runtime.sendMessage({ type: 'STREAK_SEND_FAILURE', error: err.message });
        }
      }
    }, 8500);
  }

  function init() {
    if (window.location.hostname.includes('snapchat.com')) {
      // Ensure UI is initialized once DOM is ready
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
          window.SnapStreakOverlay?.initUI();
          setupStartupMultiTabHandler();
          checkAutoBootRoutine();
        });
      } else {
        window.SnapStreakOverlay?.initUI();
        setupStartupMultiTabHandler();
        checkAutoBootRoutine();
      }
    }
  }

  // Listen for scheduled automation requests from background service worker
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === 'CANCEL_RUNNING_COMMAND') {
      console.log('[SnapStreak Content] Received CANCEL_RUNNING_COMMAND.');
      if (window.SnapStreakAutomation && window.SnapStreakAutomation.cancel) {
        window.SnapStreakAutomation.cancel();
      }
      if (window.SnapStreakOverlay && window.SnapStreakOverlay.setRunning) {
        window.SnapStreakOverlay.setRunning(false);
      }
      sendResponse({ status: 'cancelled' });
      return true;
    }

    if (request.type === 'TRIGGER_SCHEDULED_SEND') {
      console.log('[SnapStreak] Received scheduled send trigger from background alarm.');
      sendResponse({ status: 'started' }); // Acknowledge receipt immediately

      (async () => {
        try {
          // Resolve any multi-tab "Use Here" modal if present
          const modalBtns = document.querySelectorAll('button, div[role="button"], a');
          for (const btn of modalBtns) {
            if (!isVisible(btn)) continue;
            const txt = (btn.textContent || '').trim().toLowerCase();
            if (txt === 'use here' || txt.includes('use here') || txt === 'open here' || txt.includes('open here')) {
              console.log('[SnapStreak] Clearing multi-tab modal before scheduled run...');
              btn.click();
              await new Promise(r => setTimeout(r, 1500));
              break;
            }
          }

          let cfg = window.SnapStreakOverlay ? window.SnapStreakOverlay.getConfig() : null;
          if (!cfg || !cfg.friends) {
            const stored = await new Promise(r => chrome.storage.local.get(['snapstreak_config'], r));
            cfg = { ...(cfg || {}), ...(stored.snapstreak_config || {}) };
          }

          const friends = cfg.friends && cfg.friends.length > 0 ? cfg.friends : ['*//Eric\\*', 'Dylan'];
          const selectionMethod = cfg.selectionMethod || 'auto';
          const stepDelay = cfg.stepDelay || 3;
          const humanMode = cfg.humanMode ?? true;
          const isDirect = (cfg.sendingEngine !== 'macro');

          if (isDirect && window.SnapStreakAutomation) {
            window.SnapStreakOverlay?.log(`⏰ Executing Scheduled Auto-Send via Direct Script (Camera ➔ ${selectionMethod.toUpperCase()} ➔ Send)...`, 'info');
            const res = await window.SnapStreakAutomation.runSendStreaks({
              friends: friends,
              selectionMethod: selectionMethod,
              stepDelay: stepDelay,
              humanMode: humanMode,
              isTest: false
            });
            if (res && res.success) {
              window.SnapStreakOverlay?.log('🎉 Scheduled streaks sent successfully!', 'success');
              chrome.runtime.sendMessage({ type: 'STREAK_SEND_SUCCESS', recipientsCount: friends.length, result: res });
            } else {
              chrome.runtime.sendMessage({ type: 'STREAK_SEND_FAILURE', error: res?.error || 'Send sequence incomplete' });
            }
          } else if (window.SnapStreakMacro) {
            const activeMacro = cfg.activeMacro || window.SnapStreakMacro.DEFAULT_MACRO_NAME || '⚡ Default Streak Macro';
            window.SnapStreakOverlay?.log(`⏰ Executing Scheduled Auto-Send via Macro: "${activeMacro}"...`, 'info');
            const res = await window.SnapStreakMacro.replayMacro(
              activeMacro,
              stepDelay,
              cfg.waitForUIChanges ?? true,
              false
            );
            if (res && res.success) {
              window.SnapStreakOverlay?.log('🎉 Scheduled macro streaks sent successfully!', 'success');
              chrome.runtime.sendMessage({ type: 'STREAK_SEND_SUCCESS', recipientsCount: friends.length, result: res });
            } else {
              chrome.runtime.sendMessage({ type: 'STREAK_SEND_FAILURE', error: res?.error || 'Macro replay failed' });
            }
          }
        } catch (err) {
          console.error('[SnapStreak] Scheduled send failed:', err);
          window.SnapStreakOverlay?.log(`❌ Scheduled send error: ${err.message}`, 'err');
          chrome.runtime.sendMessage({ type: 'STREAK_SEND_FAILURE', error: err.message });
        }
      })();

      return true;
    }
  });

  init();
})();
