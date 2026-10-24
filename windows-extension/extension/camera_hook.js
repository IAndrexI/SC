/**
 * SnapStreak Camera & Permissions Interceptor (Runs in MAIN world context)
 * Intercepts navigator.mediaDevices.getUserMedia, enumerateDevices, and navigator.permissions.query
 * on web.snapchat.com to route video capture to the user's selected webcam or an automatic
 * hardware-spoofed 30fps HD synthetic stream on headless Linux servers.
 */

(function() {
  'use strict';

  if (window.__SNAPSTREAK_CAM_HOOK_ACTIVE__) return;
  window.__SNAPSTREAK_CAM_HOOK_ACTIVE__ = true;

  function safeGetStorage(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function safeSetStorage(key, val) {
    try {
      if (val) localStorage.setItem(key, val);
      else localStorage.removeItem(key);
    } catch (e) {}
  }

  let selectedCameraId = safeGetStorage('snapstreak_selected_camera_id') || '';
  window.__SNAPSTREAK_CAMERA_DEVICE_ID__ = selectedCameraId;
  let currentActiveStream = null;

  // 1. Hook navigator.permissions.query so Snapchat Web never blocks on Camera/Mic/Notification prompts
  try {
    if (typeof navigator !== 'undefined' && navigator.permissions && navigator.permissions.query) {
      const origQuery = navigator.permissions.query.bind(navigator.permissions);
      const grantedStatus = {
        state: 'granted',
        status: 'granted',
        onchange: null,
        addEventListener: function() {},
        removeEventListener: function() {},
        dispatchEvent: function() { return false; }
      };
      navigator.permissions.query = function( descriptor ) {
        const name = descriptor && descriptor.name ? String(descriptor.name).toLowerCase() : '';
        if (
          name === 'camera' ||
          name === 'microphone' ||
          name === 'notifications' ||
          name === 'persistent-storage' ||
          name === 'clipboard-read' ||
          name === 'clipboard-write' ||
          name === 'video_capture' ||
          name === 'audio_capture'
        ) {
          return Promise.resolve(grantedStatus);
        }
        return origQuery(descriptor).catch(() => grantedStatus);
      };
    }
  } catch (e) {}

  // Ensure navigator.mediaDevices exists
  if (typeof navigator !== 'undefined' && !navigator.mediaDevices) {
    try {
      navigator.mediaDevices = {};
    } catch (e) {}
  }

  /**
   * Synthesizes an active 30fps 1280x720 MediaStream via an offscreen HTML5 canvas
   * with full MediaStreamTrack.getSettings() and getCapabilities() hardware spoofing.
   */
  function createSyntheticMediaStream(constraints) {
    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext('2d');

    // Optional background image from SJSU meteorology cam if reachable
    const bgImg = new Image();
    bgImg.crossOrigin = 'anonymous';
    let bgLoaded = false;
    bgImg.onload = () => { bgLoaded = true; };
    try {
      bgImg.src = 'https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg?t=' + Math.floor(Date.now() / 60000);
    } catch (e) {}

    let frame = 0;
    function render() {
      frame++;
      if (bgLoaded) {
        try {
          ctx.drawImage(bgImg, 0, 0, canvas.width, canvas.height);
          ctx.fillStyle = 'rgba(8, 12, 22, 0.28)';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
        } catch (e) {
          bgLoaded = false;
        }
      }
      if (!bgLoaded) {
        const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
        grad.addColorStop(0, '#090d16');
        grad.addColorStop(0.5, '#1e1b4b');
        grad.addColorStop(1, '#020617');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const pulse = Math.sin(frame * 0.08) * 8;
        ctx.beginPath();
        ctx.arc(canvas.width / 2, canvas.height / 2 - 35, 95 + pulse, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 252, 0, 0.12)';
        ctx.fill();
        ctx.lineWidth = 4;
        ctx.strokeStyle = '#fffc00';
        ctx.stroke();

        ctx.fillStyle = '#fffc00';
        ctx.font = 'bold 56px system-ui, -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🔥', canvas.width / 2, canvas.height / 2 - 35);

        ctx.fillStyle = '#f8fafc';
        ctx.font = 'bold 28px system-ui, -apple-system, sans-serif';
        ctx.fillText('SnapStreak Virtual HD Camera', canvas.width / 2, canvas.height / 2 + 85);
      }

      // Subtle live timestamp badge in bottom corner
      ctx.fillStyle = 'rgba(10, 14, 23, 0.72)';
      ctx.fillRect(24, canvas.height - 56, 410, 34);
      ctx.fillStyle = '#fffc00';
      ctx.font = 'bold 15px monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
      ctx.fillText(`⚡ SNAPSTREAK HD LIVE • ${ts}`, 36, canvas.height - 39);
    }

    render();
    const animInterval = setInterval(render, 1000 / 30);

    const stream = canvas.captureStream ? canvas.captureStream(30) : null;
    if (!stream) {
      clearInterval(animInterval);
      throw new Error('HTMLCanvasElement.captureStream not supported in this browser');
    }

    const vTracks = stream.getVideoTracks();
    if (vTracks.length > 0) {
      const vt = vTracks[0];
      const origStop = vt.stop.bind(vt);
      vt.stop = function() {
        clearInterval(animInterval);
        return origStop();
      };
      // Spoof hardware track metadata for Snapchat Web camera validation
      try {
        Object.defineProperty(vt, 'label', {
          get: () => 'SnapStreak HD Virtual Webcam (046d:082d)',
          configurable: true
        });
      } catch (e) {}
      vt.getSettings = function() {
        return {
          width: 1280,
          height: 720,
          aspectRatio: 1280 / 720,
          frameRate: 30,
          facingMode: 'user',
          resizeMode: 'none',
          deviceId: 'snapstreak-virtual-cam-0',
          groupId: 'snapstreak-default-group'
        };
      };
      vt.getCapabilities = function() {
        return {
          width: { min: 320, max: 1920 },
          height: { min: 240, max: 1080 },
          aspectRatio: { min: 0.5, max: 2.0 },
          frameRate: { min: 1, max: 60 },
          facingMode: ['user', 'environment'],
          resizeMode: ['none', 'crop-and-scale'],
          deviceId: 'snapstreak-virtual-cam-0',
          groupId: 'snapstreak-default-group'
        };
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
          gain.gain.value = 0;
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

  // 2. Polyfill & Hook enumerateDevices to guarantee a valid videoinput + audioinput device
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

      const virtualCam = {
        deviceId: 'snapstreak-virtual-cam-0',
        kind: 'videoinput',
        label: 'SnapStreak HD Virtual Webcam (046d:082d)',
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

      const hasVirtual = devices.some(d => d.deviceId === 'snapstreak-virtual-cam-0');
      const hasVideo = devices.some(d => d.kind === 'videoinput');
      if (!hasVideo) {
        devices = [virtualCam, ...devices];
      } else if (!hasVirtual) {
        devices = [...devices, virtualCam];
      }

      const hasAudio = devices.some(d => d.kind === 'audioinput');
      if (!hasAudio) {
        devices.push({
          deviceId: 'default',
          kind: 'audioinput',
          label: 'Default Virtual Microphone',
          groupId: 'snapstreak-default-group',
          toJSON: function() {
            return { deviceId: this.deviceId, kind: this.kind, label: this.label, groupId: this.groupId };
          }
        });
      }

      return devices;
    };
  }

  // 3. Hook getUserMedia with automatic synthetic stream fallback
  if (navigator.mediaDevices) {
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia
      ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
      : null;

    navigator.mediaDevices.getUserMedia = async function(constraints) {
      const activeId = window.__SNAPSTREAK_CAMERA_DEVICE_ID__ || selectedCameraId;

      if (activeId === 'snapstreak-virtual-cam-0' || !originalGetUserMedia) {
        const synthetic = createSyntheticMediaStream(constraints);
        currentActiveStream = synthetic;
        return synthetic;
      }

      const activeConstraints = constraints ? { ...constraints } : { video: true };
      if (activeId && activeConstraints.video) {
        if (typeof activeConstraints.video === 'boolean') {
          activeConstraints.video = { deviceId: { exact: activeId } };
        } else if (typeof activeConstraints.video === 'object') {
          activeConstraints.video = { ...activeConstraints.video, deviceId: { exact: activeId } };
        }
      }

      try {
        const stream = await originalGetUserMedia(activeConstraints);
        const vTracks = stream.getVideoTracks();
        if (vTracks.length > 0 && vTracks[0].readyState === 'live') {
          currentActiveStream = stream;
          return stream;
        }
        throw new Error('Physical video track not live');
      } catch (err) {
        try {
          if (activeConstraints.video && typeof activeConstraints.video === 'object' && activeConstraints.video.deviceId) {
            const relaxedConstraints = { ...activeConstraints, video: { ...activeConstraints.video } };
            delete relaxedConstraints.video.deviceId;
            const stream = await originalGetUserMedia(relaxedConstraints);
            if (stream.getVideoTracks().length > 0) {
              currentActiveStream = stream;
              return stream;
            }
          }
        } catch (fallbackErr) {}

        // Fallback to synthetic 30fps HD canvas stream so Snapchat Web viewfinder always mounts
        const synthetic = createSyntheticMediaStream(constraints);
        currentActiveStream = synthetic;
        return synthetic;
      }
    };
  }

  window.addEventListener('snapstreak_set_camera', (event) => {
    const newId = event.detail?.deviceId || '';
    selectedCameraId = newId;
    window.__SNAPSTREAK_CAMERA_DEVICE_ID__ = newId;
    safeSetStorage('snapstreak_selected_camera_id', newId);

    if (event.detail?.restart && currentActiveStream) {
      try {
        currentActiveStream.getTracks().forEach(track => track.stop());
      } catch (e) {}
    }
  });

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
    } catch (e) {}
  });
})();
