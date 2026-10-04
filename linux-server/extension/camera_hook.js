/**
 * SnapStreak Camera Interceptor (Runs in MAIN world context)
 * Intercepts navigator.mediaDevices.getUserMedia on web.snapchat.com
 * to route video capture to the user's selected face webcam.
 */

(function() {
  'use strict';

  function safeGetStorage(key) {
    try {
      return localStorage.getItem(key);
    } catch(e) {
      return null;
    }
  }

  function safeSetStorage(key, val) {
    try {
      if (val) localStorage.setItem(key, val);
      else localStorage.removeItem(key);
    } catch(e) {}
  }

  // Read previously saved camera ID from localStorage
  let selectedCameraId = safeGetStorage('snapstreak_selected_camera_id') || '';
  window.__SNAPSTREAK_CAMERA_DEVICE_ID__ = selectedCameraId;

  // Track active media stream
  let currentActiveStream = null;

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);

    navigator.mediaDevices.getUserMedia = async function(constraints) {
      const activeId = window.__SNAPSTREAK_CAMERA_DEVICE_ID__ || selectedCameraId;

      if (activeId && constraints && constraints.video) {
        console.log(`[SnapStreak CamHook] Applying selected face webcam: ${activeId}`);

        if (typeof constraints.video === 'boolean') {
          constraints.video = {
            deviceId: { exact: activeId }
          };
        } else if (typeof constraints.video === 'object') {
          // Use exact deviceId for the selected face webcam
          constraints.video.deviceId = { exact: activeId };
        }
      }

      try {
        const stream = await originalGetUserMedia(constraints);
        currentActiveStream = stream;
        return stream;
      } catch (err) {
        console.warn('[SnapStreak CamHook] exact deviceId failed, falling back to default:', err);
        if (constraints && constraints.video && typeof constraints.video === 'object') {
          delete constraints.video.deviceId;
        }
        return originalGetUserMedia(constraints);
      }
    };

    console.log('[SnapStreak CamHook] navigator.mediaDevices.getUserMedia hooked for face webcam selection.');
  }

  // Listen for camera switch events from HUD overlay
  window.addEventListener('snapstreak_set_camera', (event) => {
    const newId = event.detail?.deviceId || '';
    selectedCameraId = newId;
    window.__SNAPSTREAK_CAMERA_DEVICE_ID__ = newId;
    safeSetStorage('snapstreak_selected_camera_id', newId);

    if (newId) {
      console.log(`[SnapStreak CamHook] Updated active camera to: ${newId}`);
    } else {
      console.log('[SnapStreak CamHook] Reset camera to system default.');
    }

    // Stop current stream so Snapchat Web re-requests the new camera
    if (event.detail?.restart && currentActiveStream) {
      try {
        currentActiveStream.getTracks().forEach(track => track.stop());
        console.log('[SnapStreak CamHook] Stopped previous camera stream to trigger switch.');
      } catch (e) {}
    }
  });

  // Helper to trigger device enumeration and broadcast to HUD
  window.addEventListener('snapstreak_query_devices', async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices
        .filter(d => d.kind === 'videoinput')
        .map(d => ({
          deviceId: d.deviceId,
          label: d.label || 'Webcam Camera',
          groupId: d.groupId
        }));

      window.dispatchEvent(new CustomEvent('snapstreak_devices_found', {
        detail: { devices: videoDevices, activeId: window.__SNAPSTREAK_CAMERA_DEVICE_ID__ }
      }));
    } catch (e) {
      console.error('[SnapStreak CamHook] enumerateDevices failed:', e);
    }
  });

})();
