/**
 * SnapStreak Background Service Worker (Manifest V3)
 * Manages daily alarms, missed-schedule auto-recovery, heartbeat polling,
 * tab activation, and notifications.
 */

const ALARM_NAME = 'snapstreak_daily_alarm';
const HEARTBEAT_ALARM_NAME = 'snapstreak_heartbeat_alarm';

const DEFAULT_CONFIG = {
  friends: ['*//Eric\\\\*', 'Dylan'],
  sendingEngine: 'direct',
  selectionMethod: 'auto',
  stepDelay: 3,
  humanMode: true,
  waitForUIChanges: true,
  scheduleEnabled: true,
  scheduleTime: '09:00',
  activeMacro: '⚡ Default Streak Macro'
};

function getTodayDateString() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Clean up duplicate Snapchat tabs on browser startup
function closeDuplicateSnapchatTabs() {
  try {
    chrome.tabs.query({ url: '*://web.snapchat.com/*' }, (tabs) => {
      if (tabs && tabs.length > 1) {
        console.log(`[SnapStreak Background] Found ${tabs.length} Snapchat tabs. Keeping primary tab ${tabs[0].id} and closing ${tabs.length - 1} duplicate(s).`);
        for (let i = 1; i < tabs.length; i++) {
          chrome.tabs.remove(tabs[i].id);
        }
      }
    });
  } catch (e) {}
}

// Initialize alarms on extension install or browser startup
chrome.runtime.onInstalled.addListener(() => {
  console.log('[SnapStreak Background] Extension installed/updated.');
  setupAlarms();
});

chrome.runtime.onStartup.addListener(() => {
  console.log('[SnapStreak Background] Browser startup.');
  closeDuplicateSnapchatTabs();
  setTimeout(closeDuplicateSnapchatTabs, 3000);
  setupAlarms();
  // Check if today's scheduled send was missed while browser was closed
  setTimeout(() => checkMissedSchedule(), 6000);
});

// Listen for messages from overlay HUD or content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CONFIG_UPDATED') {
    setupAlarms();
    sendResponse({ ok: true });
  } else if (message.type === 'TRIGGER_TEST_SCHEDULE') {
    console.log('[SnapStreak Background] Manual test trigger requested from HUD.');
    triggerStreakRun(true).then(res => {
      sendResponse({ ok: true, result: res });
    }).catch(err => {
      sendResponse({ ok: false, error: err.message });
    });
    return true; // async sendResponse
  } else if (message.type === 'STREAK_SEND_SUCCESS') {
    const todayStr = getTodayDateString();
    const timeStr = new Date().toLocaleTimeString();
    chrome.storage.local.set({
      lastStreakSentDate: todayStr,
      lastStreakSentTime: timeStr,
      lastStreakStatus: 'success'
    });
    showNotification('SnapStreak Sent! 🔥', `Daily streaks were sent successfully at ${timeStr}!`);
    sendResponse({ ok: true });
  } else if (message.type === 'STREAK_SEND_FAILURE') {
    chrome.storage.local.set({
      lastStreakStatus: 'error',
      lastStreakError: message.error || 'Unknown error'
    });
    showNotification('SnapStreak Alert ⚠️', `Scheduled streak send failed: ${message.error || 'Unknown error'}`);
    sendResponse({ ok: true });
  }
});

async function setupAlarms() {
  chrome.storage.local.get(['snapstreak_config', 'lastStreakSentDate'], (res) => {
    const config = { ...DEFAULT_CONFIG, ...(res.snapstreak_config || {}) };

    // Clear existing daily alarm
    chrome.alarms.clear(ALARM_NAME, () => {
      if (!config.scheduleEnabled) {
        console.log('[SnapStreak Background] Daily schedule is disabled.');
        chrome.storage.local.set({ nextScheduledRunText: 'Schedule Disabled' });
        return;
      }

      const scheduleTime = config.scheduleTime || '09:00';
      const [hourStr, minStr] = scheduleTime.split(':');
      const targetHour = parseInt(hourStr || '9', 10);
      const targetMin = parseInt(minStr || '0', 10);

      const now = new Date();
      const nextRun = new Date();
      nextRun.setHours(targetHour, targetMin, 0, 0);

      // If scheduled time has already passed today, schedule for tomorrow
      if (nextRun.getTime() <= now.getTime()) {
        nextRun.setDate(nextRun.getDate() + 1);
      }

      const diffMs = nextRun.getTime() - now.getTime();
      const diffMins = Math.max(1, Math.round(diffMs / 60000));
      const nextRunStr = nextRun.toLocaleDateString() + ' ' + nextRun.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      console.log(`[SnapStreak Background] Setting primary alarm for ${nextRunStr} (in ${diffMins} min / ${diffMs} ms).`);

      chrome.alarms.create(ALARM_NAME, {
        when: nextRun.getTime(),
        periodInMinutes: 1440 // Repeat every 24 hours
      });

      chrome.storage.local.set({
        nextScheduledRunTime: nextRun.getTime(),
        nextScheduledRunText: nextRunStr
      });
    });

    // Ensure 5-minute heartbeat alarm is always active
    chrome.alarms.get(HEARTBEAT_ALARM_NAME, (alarm) => {
      if (!alarm) {
        console.log('[SnapStreak Background] Registering 5-minute heartbeat alarm for missed-schedule recovery.');
        chrome.alarms.create(HEARTBEAT_ALARM_NAME, {
          periodInMinutes: 5
        });
      }
    });
  });
}

// Alarm listener
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    console.log('[SnapStreak Background] ⏰ Daily streak alarm fired!');
    triggerStreakRun(false);
  } else if (alarm.name === HEARTBEAT_ALARM_NAME) {
    console.log('[SnapStreak Background] 💓 Heartbeat check: verifying schedule health...');
    checkMissedSchedule();
  }
});

// Auto-recovery: If system was sleeping or browser was closed at schedule time
async function checkMissedSchedule() {
  chrome.storage.local.get(['snapstreak_config', 'lastStreakSentDate'], (res) => {
    const config = { ...DEFAULT_CONFIG, ...(res.snapstreak_config || {}) };
    if (!config.scheduleEnabled) return;

    const todayStr = getTodayDateString();
    if (res.lastStreakSentDate === todayStr) {
      // Already sent today
      return;
    }

    const scheduleTime = config.scheduleTime || '09:00';
    const [hStr, mStr] = scheduleTime.split(':');
    const targetH = parseInt(hStr || '9', 10);
    const targetM = parseInt(mStr || '0', 10);

    const now = new Date();
    const scheduledToday = new Date();
    scheduledToday.setHours(targetH, targetM, 0, 0);

    // If scheduled time for today has passed and streaks were not sent yet today:
    if (now.getTime() >= scheduledToday.getTime()) {
      console.log(`[SnapStreak Background] ⚠️ Missed scheduled time detected! (Target was ${scheduleTime}, now is ${now.toLocaleTimeString()}). Auto-recovering now...`);
      triggerStreakRun(false);
    }
  });
}

/**
 * Executes the streak send routine.
 * @param {boolean} force - If true, bypasses the "already sent today" safety check (for testing).
 */
async function triggerStreakRun(force = false) {
  const todayStr = getTodayDateString();

  return new Promise((resolve, reject) => {
    chrome.storage.local.get(['snapstreak_config', 'lastStreakSentDate'], async (res) => {
      const config = { ...DEFAULT_CONFIG, ...(res.snapstreak_config || {}) };

      if (!force && res.lastStreakSentDate === todayStr) {
        console.log('[SnapStreak Background] Streaks already sent today. Skipping duplicate send.');
        resolve({ skipped: true, reason: 'Already sent today' });
        return;
      }

      console.log(`[SnapStreak Background] 🚀 Initiating streak delivery (Force: ${force})...`);

      // 1. Check for existing Snapchat Web tab
      let targetTab = null;
      try {
        const tabs = await chrome.tabs.query({ url: '*://web.snapchat.com/*' });
        if (tabs && tabs.length > 0) {
          targetTab = tabs[0];
        }
      } catch (e) {
        console.log('[SnapStreak Background] Error querying tabs:', e);
      }

      if (targetTab) {
        console.log(`[SnapStreak Background] Found active Snapchat tab (${targetTab.id}). Bringing to foreground...`);
        try {
          // Bring tab to front so webcam and DOM timers run at full performance
          await chrome.tabs.update(targetTab.id, { active: true });
          if (targetTab.windowId) {
            await chrome.windows.update(targetTab.windowId, { focused: true });
          }
        } catch (e) {}

        await sleep(1500);

        // Send trigger to content script with retry attempts
        let sent = false;
        for (let attempt = 1; attempt <= 4; attempt++) {
          try {
            console.log(`[SnapStreak Background] Sending TRIGGER_SCHEDULED_SEND (attempt ${attempt}/4)...`);
            const resp = await chrome.tabs.sendMessage(targetTab.id, {
              type: 'TRIGGER_SCHEDULED_SEND',
              force: force,
              config: config
            });
            if (resp && (resp.status === 'started' || resp.status === 'completed')) {
              sent = true;
              console.log('[SnapStreak Background] ✓ Content script accepted scheduled trigger:', resp);
              resolve(resp);
              break;
            }
          } catch (err) {
            console.log(`[SnapStreak Background] Attempt ${attempt} failed: ${err.message}. Retrying in 2s...`);
            await sleep(2000);
          }
        }

        if (!sent) {
          const err = new Error('Could not communicate with Snapchat tab after 4 attempts.');
          console.error('[SnapStreak Background]', err);
          showNotification('SnapStreak Error', 'Could not communicate with Snapchat Web tab.');
          reject(err);
        }
      } else {
        // 2. Open new Snapchat Web tab automatically
        console.log('[SnapStreak Background] No open Snapchat tab found. Launching new tab...');
        try {
          const newTab = await chrome.tabs.create({
            url: 'https://web.snapchat.com/?snapstreak_scheduled=1',
            active: true
          });

          // Wait for tab load completion
          const onTabLoaded = (tabId, changeInfo) => {
            if (tabId === newTab.id && changeInfo.status === 'complete') {
              chrome.tabs.onUpdated.removeListener(onTabLoaded);

              // Allow 7 seconds for React app to hydrate and camera stream to establish
              setTimeout(async () => {
                let sent = false;
                for (let attempt = 1; attempt <= 4; attempt++) {
                  try {
                    console.log(`[SnapStreak Background] Sending TRIGGER_SCHEDULED_SEND to fresh tab (attempt ${attempt}/4)...`);
                    const resp = await chrome.tabs.sendMessage(newTab.id, {
                      type: 'TRIGGER_SCHEDULED_SEND',
                      force: force,
                      config: config
                    });
                    if (resp && (resp.status === 'started' || resp.status === 'completed')) {
                      sent = true;
                      resolve(resp);
                      break;
                    }
                  } catch (err) {
                    console.log(`[SnapStreak Background] Fresh tab attempt ${attempt} failed: ${err.message}. Retrying in 2.5s...`);
                    await sleep(2500);
                  }
                }
                if (!sent) {
                  reject(new Error('Failed to trigger fresh tab after multiple retries.'));
                }
              }, 7000);
            }
          };

          chrome.tabs.onUpdated.addListener(onTabLoaded);
        } catch (err) {
          console.error('[SnapStreak Background] Error creating tab:', err);
          reject(err);
        }
      }
    });
  });
}

function showNotification(title, message) {
  try {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: title,
      message: message,
      priority: 2
    });
  } catch (e) {
    console.log('[SnapStreak Background] Notification error:', e);
  }
}
