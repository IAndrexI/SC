/**
 * SnapStreak Camera Interceptor (Runs in MAIN world context)
 * Intercepts navigator.mediaDevices.getUserMedia and enumerateDevices on web.snapchat.com
 * to route video capture to the user's selected face webcam, and provides an automatic
 * synthetic live video stream fallback on headless servers / environments without physical cameras.
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

  // Ensure navigator.mediaDevices exists
  if (typeof navigator !== 'undefined' && !navigator.mediaDevices) {
    try {
      navigator.mediaDevices = {};
    } catch(e) {}
  }

  /**
   * Synthesizes an active 30fps MediaStream via an offscreen HTML5 canvas.
   * This guarantees that Snapchat Web's camera viewfinder mounts and renders
   * the shutter button even on headless Linux servers without physical USB webcams.
   */
  function createSyntheticMediaStream(constraints) {
    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext('2d');

    let frame = 0;
    function render() {
      frame++;
      // Dark slate background with smooth radial gradient
      const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      grad.addColorStop(0, '#090d16');
      grad.addColorStop(0.5, '#1e1b4b');
      grad.addColorStop(1, '#020617');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Glowing pulsing camera viewfinder target
      const pulse = Math.sin(frame * 0.08) * 8;
      ctx.beginPath();
      ctx.arc(canvas.width / 2, canvas.height / 2 - 35, 95 + pulse, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 252, 0, 0.12)';
      ctx.fill();
      ctx.lineWidth = 4;
      ctx.strokeStyle = '#fffc00';
      ctx.stroke();

      // Flame streak icon
      ctx.fillStyle = '#fffc00';
      ctx.font = 'bold 56px system-ui, -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('🔥', canvas.width / 2, canvas.height / 2 - 35);

      // SnapStreak Cam branding
      ctx.fillStyle = '#f8fafc';
      ctx.font = 'bold 28px system-ui, -apple-system, sans-serif';
      ctx.fillText('SnapStreak Virtual HD Camera', canvas.width / 2, canvas.height / 2 + 85);

      // Status & timestamp
      ctx.fillStyle = '#94a3b8';
      ctx.font = '18px monospace';
      const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
      ctx.fillText(`ACTIVE LIVE STREAM • ${ts}`, canvas.width / 2, canvas.height / 2 + 125);
    }

    render();
    // Using setInterval ensures frames render even when the tab/window is in background or minimized
    const animInterval = setInterval(render, 1000 / 30);

    const stream = canvas.captureStream ? canvas.captureStream(30) : null;
    if (!stream) {
      clearInterval(animInterval);
      throw new Error('HTMLCanvasElement.captureStream not supported in this browser');
    }

    // Attach cleanup when tracks end
    const vTracks = stream.getVideoTracks();
    if (vTracks.length > 0) {
      const origStop = vTracks[0].stop.bind(vTracks[0]);
      vTracks[0].stop = function() {
        clearInterval(animInterval);
        return origStop();
      };
    }

    // Synthesize silent audio track if requested
    if (constraints && constraints.audio) {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          const audioCtx = new AudioCtx();
          const osc = audioCtx.createOscillator();
          const dst = audioCtx.createMediaStreamDestination();
          const gain = audioCtx.createGain();
          gain.gain.value = 0; // mute
          osc.connect(gain);
          gain.connect(dst);
          osc.start();
          const aTrack = dst.stream.getAudioTracks()[0];
          if (aTrack) stream.addTrack(aTrack);
        }
      } catch (e) {}
    }

    return stream;
  }

  // Polyfill & Hook enumerateDevices to guarantee at least one videoinput device
  if (navigator.mediaDevices) {
    const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices
      ? navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices)
      : null;

    navigator.mediaDevices.enumerateDevices = async function() {
      let devices = [];
      if (originalEnumerateDevices) {
        try {
          devices = await originalEnumerateDevices();
        } catch (e) {
          devices = [];
        }
      }

      const hasVideo = devices.some(d => d.kind === 'videoinput');
      if (!hasVideo) {
        const virtualCam = {
          deviceId: 'snapstreak-virtual-cam-0',
          kind: 'videoinput',
          label: 'SnapStreak HD Virtual Webcam',
          groupId: 'snapstreak-default-group',
          toJSON: function() {
            return {
              deviceId: this.deviceId,
              kind: this.kind,
              label: this.label,
              groupId: this.groupId
            };
          }
        };
        devices = [...devices, virtualCam];
      }
      return devices;
    };
  }

  // Hook getUserMedia
  if (navigator.mediaDevices) {
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia
      ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
      : null;

    navigator.mediaDevices.getUserMedia = async function(constraints) {
      const activeId = window.__SNAPSTREAK_CAMERA_DEVICE_ID__ || selectedCameraId;

      // If activeId is set to virtual camera or we have no originalGetUserMedia, return synthetic stream
      if (activeId === 'snapstreak-virtual-cam-0' || !originalGetUserMedia) {
        console.log('[SnapStreak CamHook] Virtual camera explicitly selected. Generating live synthetic stream.');
        const synthetic = createSyntheticMediaStream(constraints);
        currentActiveStream = synthetic;
        return synthetic;
      }

      const activeConstraints = constraints ? { ...constraints } : { video: true };
      if (activeId && activeConstraints.video) {
        console.log(`[SnapStreak CamHook] Applying selected face webcam: ${activeId}`);
        if (typeof activeConstraints.video === 'boolean') {
          activeConstraints.video = { deviceId: { exact: activeId } };
        } else if (typeof activeConstraints.video === 'object') {
          activeConstraints.video = { ...activeConstraints.video, deviceId: { exact: activeId } };
        }
      }

      // Try capturing real physical webcam
      try {
        const stream = await originalGetUserMedia(activeConstraints);
        currentActiveStream = stream;
        return stream;
      } catch (err) {
        console.warn('[SnapStreak CamHook] Preferred camera constraints failed, attempting fallback:', err);
        // Fallback 1: try without exact deviceId
        try {
          if (activeConstraints.video && typeof activeConstraints.video === 'object' && activeConstraints.video.deviceId) {
            const relaxedConstraints = { ...activeConstraints, video: { ...activeConstraints.video } };
            delete relaxedConstraints.video.deviceId;
            const stream = await originalGetUserMedia(relaxedConstraints);
            currentActiveStream = stream;
            return stream;
          }
        } catch (fallbackErr) {
          console.warn('[SnapStreak CamHook] Relaxed camera constraints failed:', fallbackErr);
        }

        // Fallback 2: System has no physical camera or permission denied on headless server.
        // Return synthetic canvas stream so Snapchat viewfinder mounts and renders shutter button!
        console.log('[SnapStreak CamHook] Physical webcam unavailable on server. Activating SnapStreak Virtual HD Stream!');
        const synthetic = createSyntheticMediaStream(constraints);
        currentActiveStream = synthetic;
        return synthetic;
      }
    };

    console.log('[SnapStreak CamHook] navigator.mediaDevices.getUserMedia & enumerateDevices hooked successfully.');
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
          label: d.label || (d.deviceId.includes('snapstreak') ? 'SnapStreak Virtual HD Camera' : 'Webcam Camera'),
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
