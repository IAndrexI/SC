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
          }
        } catch (err) {
          window.SnapStreakOverlay?.log(`❌ Auto-boot streak send error: ${err.message}`, 'err');
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
    if (request.type === 'TRIGGER_SCHEDULED_SEND') {
      console.log('[SnapStreak] Received scheduled send trigger from background alarm.');
      if (window.SnapStreakOverlay) {
        const config = window.SnapStreakOverlay.getConfig();
        const isDirect = (config.sendingEngine === 'direct');

        if (isDirect && window.SnapStreakAutomation) {
          window.SnapStreakOverlay.log(`⏰ Executing Scheduled Auto-Send via Direct Script (Camera ➔ ${config.selectionMethod.toUpperCase()} ➔ Send)...`, 'info');
          window.SnapStreakAutomation.runSendStreaks({
            friends: config.friends,
            selectionMethod: config.selectionMethod,
            stepDelay: config.stepDelay || 3,
            humanMode: config.humanMode ?? true,
            isTest: false
          }).then(res => {
            sendResponse({ status: 'completed', result: res });
          }).catch(err => {
            sendResponse({ status: 'error', error: err.message });
          });
          return true;
        } else if (window.SnapStreakMacro) {
          const activeMacro = config.activeMacro || window.SnapStreakMacro.DEFAULT_MACRO_NAME || '⚡ Default Streak Macro';
          window.SnapStreakOverlay.log(`⏰ Executing Scheduled Auto-Send via Macro: "${activeMacro}"...`, 'info');
          window.SnapStreakMacro.replayMacro(
            activeMacro,
            config.stepDelay || 3,
            config.waitForUIChanges ?? true,
            false // isTest = false
          ).then(res => {
            sendResponse({ status: 'completed', result: res });
          }).catch(err => {
            sendResponse({ status: 'error', error: err.message });
          });
          return true;
        }
      }
    }
  });

  init();
})();
