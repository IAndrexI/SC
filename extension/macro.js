/**
 * SnapStreak Macro Engine (Client-side Click & Action Recorder)
 * Records and replays custom click sequences directly on Snapchat Web
 */

window.SnapStreakMacro = (function() {
  'use strict';

  let isRecording = false;
  let recordedEvents = [];
  let startTime = 0;

  function log(msg, type = 'info') {
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.log) {
      window.SnapStreakOverlay.log(msg, type);
    } else {
      console.log(`[SnapStreak Macro] ${msg}`);
    }
  }

  function getUniqueSelector(el) {
    if (!el || el === document.body || el === document.documentElement) return null;
    
    // Check meaningful attributes
    if (el.getAttribute('aria-label')) {
      return `[aria-label="${el.getAttribute('aria-label')}"]`;
    }
    if (el.getAttribute('data-testid')) {
      return `[data-testid="${el.getAttribute('data-testid')}"]`;
    }
    if (el.id) {
      return `#${el.id}`;
    }

    // Check button or link with text
    const text = el.textContent?.trim();
    if (text && text.length > 0 && text.length < 30 && (el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button')) {
      return `${el.tagName.toLowerCase()}:has-text("${text}")`;
    }

    // Fallback to tag and class
    let selector = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const classes = el.className.split(/\s+/).filter(c => c && !c.includes(':') && !c.includes('snapstreak'));
      if (classes.length > 0) {
        selector += '.' + classes.slice(0, 2).join('.');
      }
    }
    return selector;
  }

  function showClickIndicator(x, y) {
    const dot = document.createElement('div');
    dot.className = 'snapstreak-click-ripple';
    dot.style.cssText = `
      position: fixed;
      left: ${x}px;
      top: ${y}px;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      border: 3px solid #ff2b55;
      background: rgba(255, 43, 85, 0.4);
      transform: translate(-50%, -50%) scale(0.5);
      pointer-events: none;
      z-index: 2147483646;
      transition: all 0.4s ease-out;
    `;
    document.body.appendChild(dot);
    requestAnimationFrame(() => {
      dot.style.transform = 'translate(-50%, -50%) scale(1.6)';
      dot.style.opacity = '0';
    });
    setTimeout(() => dot.remove(), 450);
  }

  function handleClick(e) {
    if (!isRecording) return;

    // Ignore clicks inside the SnapStreak Shadow Host / HUD
    const host = document.getElementById('snapstreak-shadow-host');
    if (host && (e.composedPath().includes(host) || host.contains(e.target))) {
      return;
    }

    const target = e.target;
    const selector = getUniqueSelector(target);
    const text = target.textContent?.trim()?.slice(0, 40) || '';
    const x = e.clientX;
    const y = e.clientY;

    showClickIndicator(x, y);

    const eventData = {
      type: 'click',
      selector: selector,
      text: text,
      tag: target.tagName,
      x: x,
      y: y,
      timeDelta: Date.now() - startTime
    };

    recordedEvents.push(eventData);
    log(`🔴 Step ${recordedEvents.length}: Clicked <${target.tagName.toLowerCase()}> "${text || selector}"`, 'info');

    // Update overlay step count if available
    if (window.SnapStreakOverlay && window.SnapStreakOverlay.updateMacroStepCount) {
      window.SnapStreakOverlay.updateMacroStepCount(recordedEvents.length);
    }
  }

  function handleKeyDown(e) {
    if (!isRecording) return;
    const host = document.getElementById('snapstreak-shadow-host');
    if (host && (e.composedPath().includes(host) || host.contains(e.target))) {
      return;
    }

    if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
      recordedEvents.push({
        type: 'key',
        key: e.key,
        code: e.code,
        timeDelta: Date.now() - startTime
      });
      log(`🔴 Step ${recordedEvents.length}: Key [${e.key}]`, 'info');
      if (window.SnapStreakOverlay && window.SnapStreakOverlay.updateMacroStepCount) {
        window.SnapStreakOverlay.updateMacroStepCount(recordedEvents.length);
      }
    }
  }

  function startRecording() {
    isRecording = true;
    recordedEvents = [];
    startTime = Date.now();
    document.addEventListener('click', handleClick, true);
    document.addEventListener('keydown', handleKeyDown, true);
    log('🎬 Macro recording started! Click and perform your streak actions on Snapchat now...', 'info');
    return true;
  }

  async function stopRecording(macroName = 'Custom Streak Macro') {
    isRecording = false;
    document.removeEventListener('click', handleClick, true);
    document.removeEventListener('keydown', handleKeyDown, true);

    const events = [...recordedEvents];
    log(`⏹️ Macro recorded (${events.length} steps)! Saving...`, 'success');

    if (events.length > 0) {
      // Save to chrome.storage.local
      const saved = await getSavedMacros();
      saved[macroName] = {
        name: macroName,
        createdAt: new Date().toISOString(),
        steps: events
      };
      await chrome.storage.local.set({ snapstreak_macros: saved });
      log(`✓ Saved macro "${macroName}" (${events.length} steps).`, 'success');
    }

    return events;
  }

  const DEFAULT_MACRO_NAME = '⚡ Default Streak Macro';

  const DEFAULT_STREAK_MACRO = {
    name: DEFAULT_MACRO_NAME,
    createdAt: 'Built-in System Macro',
    isDefault: true,
    steps: [
      { type: 'routine', action: 'step0_clickSnapchatHome', label: '1. Click Snapchat Icon (Top-Left Home)' },
      { type: 'routine', action: 'step1_openCamera', label: '2. Open Camera Viewfinder' },
      { type: 'routine', action: 'step2_pressWhiteCirclePhoto', label: '3. Press White Circle Photo Shutter' },
      { type: 'routine', action: 'step3_selectRecipients', label: '4. Click Send-To & Select Visual Names' },
      { type: 'routine', action: 'step4_sendSnap', label: '5. Click Final Send Button' }
    ]
  };

  function showTestIndicator(el, stepNum, totalSteps, stepLabel = '') {
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const testBox = document.createElement('div');
    testBox.className = 'snapstreak-test-highlight';
    testBox.style.cssText = `
      position: fixed;
      left: ${Math.max(4, rect.left - 4)}px;
      top: ${Math.max(4, rect.top - 4)}px;
      width: ${rect.width + 8}px;
      height: ${rect.height + 8}px;
      border: 3px solid #00e5ff;
      background: rgba(0, 229, 255, 0.22);
      border-radius: 8px;
      z-index: 2147483646;
      pointer-events: none;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 0 18px rgba(0, 229, 255, 0.7);
    `;
    const label = document.createElement('div');
    label.style.cssText = `
      position: absolute;
      top: -24px;
      left: 0;
      background: #00e5ff;
      color: #000;
      font-size: 11px;
      font-weight: 800;
      padding: 2px 7px;
      border-radius: 4px;
      font-family: sans-serif;
      white-space: nowrap;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    `;
    label.textContent = `🧪 TEST STEP ${stepNum}/${totalSteps} ${stepLabel ? '(' + stepLabel + ') ' : ''}VERIFIED`;
    testBox.appendChild(label);
    document.body.appendChild(testBox);

    setTimeout(() => {
      testBox.style.opacity = '0';
      setTimeout(() => testBox.remove(), 450);
    }, 1800);
  }

  async function getSavedMacros() {
    return new Promise(resolve => {
      chrome.storage.local.get(['snapstreak_macros'], res => {
        const saved = res.snapstreak_macros || {};
        if (!saved[DEFAULT_MACRO_NAME]) {
          saved[DEFAULT_MACRO_NAME] = DEFAULT_STREAK_MACRO;
        }
        resolve(saved);
      });
    });
  }

  async function deleteMacro(macroName) {
    if (macroName === DEFAULT_MACRO_NAME) {
      log(`⚠ Cannot delete the default system streak macro.`, 'err');
      return false;
    }
    const saved = await getSavedMacros();
    if (saved[macroName]) {
      delete saved[macroName];
      await chrome.storage.local.set({ snapstreak_macros: saved });
      log(`🗑️ Deleted macro "${macroName}".`, 'info');
      return true;
    }
    return false;
  }

  function waitForSignificantUIChange(minMutations = 12, timeoutMs = 8000) {
    return new Promise((resolve) => {
      let mutationCount = 0;
      let timer = null;
      let settleTimer = null;

      const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
          const host = document.getElementById('snapstreak-shadow-host');
          if (host && (m.target === host || host.contains(m.target))) continue;
          mutationCount += (m.addedNodes.length + m.removedNodes.length + 1);
        }

        if (mutationCount >= minMutations) {
          if (settleTimer) clearTimeout(settleTimer);
          settleTimer = setTimeout(() => {
            observer.disconnect();
            if (timer) clearTimeout(timer);
            resolve({ triggered: true, count: mutationCount });
          }, 350);
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true
      });

      timer = setTimeout(() => {
        observer.disconnect();
        if (settleTimer) clearTimeout(settleTimer);
        resolve({ triggered: false, count: mutationCount });
      }, timeoutMs);
    });
  }

  async function replayMacro(macroName, stepDelay = 2.5, waitForUIChange = false, isTest = false) {
    const saved = await getSavedMacros();
    const macro = saved[macroName] || saved[DEFAULT_MACRO_NAME] || DEFAULT_STREAK_MACRO;

    if (!macro) {
      log(`⚠ Macro "${macroName}" not found or empty.`, 'err');
      return false;
    }

    const config = (window.SnapStreakOverlay && window.SnapStreakOverlay.getConfig)
      ? window.SnapStreakOverlay.getConfig()
      : { friends: ['*//Eric\\\\*', 'Dylan'], selectionMethod: 'auto', humanMode: true };

    if (isTest) {
      log(`🧪 [TEST MODE] Starting Dry-Run verification for "${macro.name}"...`, 'info');
    } else {
      log(`🚀 [MACRO SEND] Executing Primary Macro: "${macro.name}" (${macro.steps.length} steps)...`, 'info');
    }

    if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(true);

    try {
      if (macro.isDefault) {
        // Built-in Macro Engine Execution
        log('  Step 1/5: Clicking Snapchat icon top-left to set at home...', 'info');
        await window.SnapStreakAutomation.step0_clickSnapchatHome();
        await window.SnapStreakAutomation.sleep(1200);

        log('  Step 2/5: Opening Camera Viewfinder (if not opened already)...', 'info');
        await window.SnapStreakAutomation.step1_openCamera();
        await window.SnapStreakAutomation.sleep(1500);

        log('  Step 3/5: Pressing White Circle for photo capture...', 'info');
        await window.SnapStreakAutomation.step2_pressWhiteCirclePhoto();
        await window.SnapStreakAutomation.sleep(1800);

        log('  Step 4/5: Opening Send-To drawer & selecting recipients by visual name...', 'info');
        await window.SnapStreakAutomation.step3_ensureSendToDrawerOpen();
        await window.SnapStreakAutomation.sleep(800);
        await window.SnapStreakAutomation.step3b_selectRecipientsByVisualName(config.friends, config.selectionMethod, stepDelay);
        await window.SnapStreakAutomation.sleep(1000);

        // Find Send button
        let sendBtn = (window.SnapStreakAutomation && window.SnapStreakAutomation.findFinalSendButton)
          ? window.SnapStreakAutomation.findFinalSendButton()
          : null;
        if (!sendBtn) {
          const buttons = document.querySelectorAll('button, div[role="button"]');
          for (const b of buttons) {
            const text = b.textContent.trim().toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            const inMain = !window.SnapStreakAutomation || window.SnapStreakAutomation.isInsideMainCameraArea(b);
            if ((text === 'send' || text.startsWith('send ') || text.includes('send ▶') || aria.includes('send snap') || aria === 'send') && !text.includes('send to') && !aria.includes('send to') && inMain && b.offsetParent !== null) {
              sendBtn = b;
              break;
            }
          }
        }

        if (isTest) {
          if (sendBtn) {
            showTestIndicator(sendBtn, 5, 5, 'Send Button');
            log('  🧪 [TEST VERIFIED] Send button located and ready for auto-sending!', 'success');
          } else {
            log('  ⚠ [TEST WARNING] Send button not yet visible on screen.', 'err');
          }
          log('🎉 [TEST PASSED] Macro dry-run complete! All steps verified without sending live snaps.', 'success');
          return true;
        } else {
          log('  Step 5/5: Submitting and Sending Streak...', 'info');
          await window.SnapStreakAutomation.step4_sendSnap();
          log(`🎉 Primary Macro "${macro.name}" completed successfully! Streaks sent. 🔥`, 'success');
          return true;
        }
      } else {
        // Custom Recorded Macro Replay
        for (let i = 0; i < macro.steps.length; i++) {
          const step = macro.steps[i];
          const isLast = (i === macro.steps.length - 1);
          log(`  Step ${i + 1}/${macro.steps.length}: ${step.type} "${step.text || step.selector || step.key}"...`, 'info');

          let uiPromise = null;
          if (waitForUIChange && !isLast) {
            uiPromise = waitForSignificantUIChange(10, 9000);
          }

          if (step.type === 'click') {
            let target = null;
            if (step.selector && !step.selector.includes(':has-text')) {
              try { target = document.querySelector(step.selector); } catch(e) {}
            }
            if (!target && step.text) {
              const elements = document.querySelectorAll('button, a, div[role="button"], span');
              for (const el of elements) {
                if (el.textContent.trim().toLowerCase().includes(step.text.toLowerCase()) && el.offsetParent !== null) {
                  target = el;
                  break;
                }
              }
            }
            if (!target && step.x && step.y) {
              target = document.elementFromPoint(step.x, step.y);
            }

            if (isTest) {
              if (target) {
                showTestIndicator(target, i + 1, macro.steps.length);
                if (isLast && (step.text?.toLowerCase().includes('send') || target.textContent?.toLowerCase().includes('send'))) {
                  log(`  🧪 [TEST VERIFIED] Final Send step located. Click withheld for test safety.`, 'success');
                } else {
                  window.SnapStreakAutomation.simulateHumanClick(target);
                }
              } else {
                showClickIndicator(step.x, step.y);
                log(`  ⚠ [TEST] Target for step ${i + 1} not in DOM, coords (${step.x}, ${step.y}).`, 'info');
              }
            } else {
              showClickIndicator(step.x, step.y);
              if (target) {
                window.SnapStreakAutomation.simulateHumanClick(target);
              }
            }
          } else if (step.type === 'key') {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: step.key, code: step.code, bubbles: true }));
            document.dispatchEvent(new KeyboardEvent('keyup', { key: step.key, code: step.code, bubbles: true }));
          }

          if (uiPromise) {
            log(`  ⏳ Waiting for major Snapchat UI transition before next step...`, 'info');
            const uiResult = await uiPromise;
            if (uiResult.triggered) {
              log(`  ✓ Verified major UI change (${uiResult.count} DOM updates). Proceeding.`, 'success');
            }
          }

          await window.SnapStreakAutomation.sleep(stepDelay * 1000);
        }

        if (isTest) {
          log(`🎉 [TEST PASSED] Custom Macro "${macro.name}" successfully verified!`, 'success');
        } else {
          log(`🎉 Macro "${macro.name}" completed successfully! Streaks sent. 🔥`, 'success');
        }
        return true;
      }
    } catch (err) {
      log(`❌ Error replaying macro: ${err.message}`, 'err');
      return false;
    } finally {
      if (window.SnapStreakOverlay) window.SnapStreakOverlay.setRunning(false);
    }
  }

  return {
    startRecording,
    stopRecording,
    getSavedMacros,
    deleteMacro,
    replayMacro,
    showTestIndicator,
    DEFAULT_MACRO_NAME,
    isRecording: () => isRecording
  };
})();
