/**
 * SnapStreak Background Service Worker (Manifest V3)
 * Manages daily alarms, background scheduling, and notifications
 */

const ALARM_NAME = 'snapstreak_daily_alarm';

// Initialize alarms on extension install or browser startup
chrome.runtime.onInstalled.addListener(() => {
  console.log('[SnapStreak Background] Extension installed/updated.');
  setupDailyAlarm();
});

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

chrome.runtime.onStartup.addListener(() => {
  console.log('[SnapStreak Background] Browser startup.');
  closeDuplicateSnapchatTabs();
  setTimeout(closeDuplicateSnapchatTabs, 3000);
  setupDailyAlarm();
});

// Listen for config changes from overlay
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CONFIG_UPDATED') {
    setupDailyAlarm();
    sendResponse({ ok: true });
  }
});

async function setupDailyAlarm() {
  chrome.alarms.clear(ALARM_NAME, async () => {
    chrome.storage.local.get(['snapstreak_config'], (res) => {
      const config = res.snapstreak_config || {};
      if (!config.scheduleEnabled) {
        console.log('[SnapStreak Background] Daily schedule is disabled.');
        return;
      }

      const scheduleTime = config.scheduleTime || '09:00';
      const [hourStr, minStr] = scheduleTime.split(':');
      const targetHour = parseInt(hourStr, 10);
      const targetMin = parseInt(minStr, 10);

      const now = new Date();
      const nextRun = new Date();
      nextRun.setHours(targetHour, targetMin, 0, 0);

      if (nextRun <= now) {
        // If scheduled time has already passed today, schedule for tomorrow
        nextRun.setDate(nextRun.getDate() + 1);
      }

      const delayMinutes = Math.max(1, Math.round((nextRun.getTime() - now.getTime()) / 60000));
      console.log(`[SnapStreak Background] Setting alarm for ${nextRun.toLocaleTimeString()} (in ${delayMinutes} minutes).`);

      chrome.alarms.create(ALARM_NAME, {
        delayInMinutes: delayMinutes,
        periodInMinutes: 1440 // 24 hours
      });
    });
  });
}

// Trigger streak run when alarm fires
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    console.log('[SnapStreak Background] ⏰ Daily streak alarm fired!');
    triggerStreakRun();
  }
});

async function triggerStreakRun() {
  // Query for open Snapchat Web tabs
  chrome.tabs.query({ url: '*://web.snapchat.com/*' }, (tabs) => {
    if (tabs && tabs.length > 0) {
      const targetTab = tabs[0];
      console.log(`[SnapStreak Background] Found open Snapchat tab (id ${targetTab.id}), sending trigger...`);
      chrome.tabs.sendMessage(targetTab.id, { type: 'TRIGGER_SCHEDULED_SEND' }, (resp) => {
        showNotification('SnapStreak Sent!', 'Scheduled daily streaks were sent successfully.');
      });
    } else {
      // Open Snapchat Web tab automatically
      console.log('[SnapStreak Background] Opening new Snapchat tab for scheduled send...');
      chrome.tabs.create({ url: 'https://web.snapchat.com/' }, (newTab) => {
        // Wait for page to load
        const listener = (tabId, changeInfo) => {
          if (tabId === newTab.id && changeInfo.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            // Give 5 seconds for React app to hydrate
            setTimeout(() => {
              chrome.tabs.sendMessage(newTab.id, { type: 'TRIGGER_SCHEDULED_SEND' }, (resp) => {
                showNotification('SnapStreak Sent!', 'Scheduled daily streaks were sent successfully.');
              });
            }, 5000);
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
      });
    }
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
