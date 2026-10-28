/**
 * camera_hook.js – Live SJSU Meteorology Virtual Webcam Hook (MAIN World)
 * Intercepts navigator.mediaDevices.getUserMedia & enumerateDevices so Snapchat Web
 * always receives a 30 FPS 1280x720 video stream displaying the live San José State University
 * Meteorology camera (https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg) without CORS errors.
 */

(function () {
  if (window.__SNAPSTREAK_CAMERA_HOOKED__) return;
  window.__SNAPSTREAK_CAMERA_HOOKED__ = true;

  const SJSU_WEBCAM_URL = 'https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg';
  const VIRTUAL_CAM_ID = 'snapstreak-sjsu-webcam-id';
  const VIRTUAL_CAM_LABEL = 'SJSU Meteorology Live Webcam (1080p)';

  let activeCanvas = null;
  let activeStream = null;
  let renderInterval = null;
  let bgLoaded = false;
  let lastFrameSource = 'initializing';

  const bgImg = new Image();
  bgImg.onload = () => {
    if (bgImg.naturalWidth > 0) {
      bgLoaded = true;
    }
  };

  function applyDataUrl(dataUrl, sourceName) {
    if (!dataUrl || typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) return false;
    window.__SNAPSTREAK_SJSU_DATA_URL__ = dataUrl;
    lastFrameSource = sourceName || 'data_url';
    bgImg.removeAttribute('crossOrigin');
    bgImg.src = dataUrl;
    return true;
  }

  // Listen for base64 Data URL frames pushed by Python server or content.js/background.js
  window.addEventListener('SNAPSTREAK_WEBCAM_FRAME', (evt) => {
    const dataUrl = evt && evt.detail && evt.detail.dataUrl;
    if (dataUrl) {
      applyDataUrl(dataUrl, 'injected_event');
    }
  });

  async function refreshWebcamFrame() {
    // 1. Check if server or extension already injected a base64 Data URL
    if (window.__SNAPSTREAK_SJSU_DATA_URL__ && typeof window.__SNAPSTREAK_SJSU_DATA_URL__ === 'string') {
      applyDataUrl(window.__SNAPSTREAK_SJSU_DATA_URL__, 'window_data_url');
    }

    // 2. Request fresh base64 frame from extension content.js -> background.js (bypasses CORS via extension host_permissions)
    try {
      window.dispatchEvent(new CustomEvent('SNAPSTREAK_REQUEST_SJSU_FRAME'));
    } catch (e) {}

    // 3. Try local server CORS-enabled base64 endpoint if running on localhost:8080 or desktop server
    const apiCandidates = [];
    if (window.location.port === '8080' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      apiCandidates.push(`${window.location.origin}/api/webcam-b64`);
    }
    apiCandidates.push('http://localhost:8080/api/webcam-b64', 'http://127.0.0.1:8080/api/webcam-b64');

    for (const url of apiCandidates) {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 2500);
        const res = await fetch(url, { signal: ctrl.signal, mode: 'cors', cache: 'no-store' });
        clearTimeout(timer);
        if (res.ok) {
          const data = await res.json();
          if (data && data.data_url && applyDataUrl(data.data_url, 'local_api_b64')) {
            return;
          }
        }
      } catch (e) {}
    }
  }

  // Initial load + periodic refresh every 30 seconds
  refreshWebcamFrame();
  setInterval(refreshWebcamFrame, 30000);

  window.__SNAPSTREAK_REFRESH_WEBCAM__ = refreshWebcamFrame;
  window.__SNAPSTREAK_WEBCAM_URL__ = SJSU_WEBCAM_URL;
  window.__SNAPSTREAK_WEBCAM_STATUS__ = () => ({
    loaded: bgLoaded,
    source: lastFrameSource,
    width: bgImg.naturalWidth || 1280,
    height: bgImg.naturalHeight || 720,
  });

  function drawFrame(ctx, w, h) {
    if (bgLoaded && bgImg.complete && bgImg.naturalWidth > 0) {
      ctx.fillStyle = '#07090e';
      ctx.fillRect(0, 0, w, h);

      const iw = bgImg.naturalWidth;
      const ih = bgImg.naturalHeight;
      const scale = Math.max(w / iw, h / ih);
      const sw = iw * scale;
      const sh = ih * scale;
      const ox = (w - sw) / 2;
      const oy = (h - sh) / 2;

      ctx.drawImage(bgImg, ox, oy, sw, sh);

      // Subtle micro-pixel keepalive in bottom-right corner so WebRTC encoder continuously emits key/delta frames
      const pulse = (Date.now() % 1000) / 1000;
      ctx.fillStyle = `rgba(255, 252, 0, ${0.01 + pulse * 0.02})`;
      ctx.fillRect(w - 2, h - 2, 2, 2);
      return;
    }

    // Fallback while first SJSU frame is loading
    const grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#0f172a');
    grad.addColorStop(0.5, '#1e293b');
    grad.addColorStop(1, '#0f172a');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = '#fffc00';
    ctx.font = 'bold 34px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('📷 SJSU Meteorology Live Webcam', w / 2, h / 2 - 20);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '20px system-ui, -apple-system, sans-serif';
    ctx.fillText(new Date().toLocaleString(), w / 2, h / 2 + 28);
  }

  function decorateVideoTrack(videoTrack, w, h) {
    if (!videoTrack) return;
    try {
      Object.defineProperty(videoTrack, 'label', {
        get: () => VIRTUAL_CAM_LABEL,
        configurable: true,
      });
    } catch (e) {}

    const origGetSettings = videoTrack.getSettings ? videoTrack.getSettings.bind(videoTrack) : () => ({});
    videoTrack.getSettings = function () {
      return Object.assign({}, origGetSettings(), {
        width: w,
        height: h,
        frameRate: 30,
        facingMode: 'user',
        deviceId: VIRTUAL_CAM_ID,
        groupId: 'snapstreak-sjsu-group',
      });
    };

    const origGetCapabilities = videoTrack.getCapabilities ? videoTrack.getCapabilities.bind(videoTrack) : () => ({});
    videoTrack.getCapabilities = function () {
      return Object.assign({}, origGetCapabilities(), {
        width: { min: 640, max: 1920 },
        height: { min: 480, max: 1080 },
        frameRate: { min: 15, max: 60 },
        facingMode: ['user', 'environment'],
        deviceId: VIRTUAL_CAM_ID,
      });
    };

    videoTrack.stop = function () {};
  }

  function getOrCreateVirtualStream(width = 1280, height = 720) {
    try {
      if (activeStream && activeStream.active) {
        const tracks = activeStream.getVideoTracks();
        if (tracks.length > 0 && tracks[0].readyState === 'live') {
          const out = activeStream.clone ? activeStream.clone() : activeStream;
          decorateVideoTrack(out.getVideoTracks()[0], activeCanvas ? activeCanvas.width : width, activeCanvas ? activeCanvas.height : height);
          return out;
        }
      }

      if (!activeCanvas) {
        activeCanvas = document.createElement('canvas');
        activeCanvas.width = width;
        activeCanvas.height = height;
      }

      const ctx = activeCanvas.getContext('2d', { alpha: false });
      drawFrame(ctx, activeCanvas.width, activeCanvas.height);

      if (renderInterval) clearInterval(renderInterval);
      renderInterval = setInterval(() => {
        try {
          drawFrame(ctx, activeCanvas.width, activeCanvas.height);
        } catch (e) {}
      }, 33); // ~30 FPS

      activeStream = activeCanvas.captureStream(30);
      decorateVideoTrack(activeStream.getVideoTracks()[0], activeCanvas.width, activeCanvas.height);

      const out = activeStream.clone ? activeStream.clone() : activeStream;
      decorateVideoTrack(out.getVideoTracks()[0], activeCanvas.width, activeCanvas.height);
      return out;
    } catch (err) {
      return null;
    }
  }

  if (!navigator.mediaDevices) {
    try {
      navigator.mediaDevices = {};
    } catch (e) {}
  }

  if (navigator.mediaDevices) {
    const origGetUserMedia = navigator.mediaDevices.getUserMedia
      ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
      : null;

    const customGetUserMedia = async function (constraints) {
      if (constraints && constraints.video) {
        let w = 1280;
        let h = 720;
        if (typeof constraints.video === 'object') {
          if (constraints.video.width) {
            w = constraints.video.width.ideal || constraints.video.width.exact || constraints.video.width || 1280;
          }
          if (constraints.video.height) {
            h = constraints.video.height.ideal || constraints.video.height.exact || constraints.video.height || 720;
          }
        }
        const stream = getOrCreateVirtualStream(
          Math.min(1920, Math.max(640, Number(w) || 1280)),
          Math.min(1080, Math.max(480, Number(h) || 720))
        );
        if (stream) return stream;
      }
      if (origGetUserMedia) {
        return origGetUserMedia(constraints);
      }
      throw new DOMException('Requested device not found', 'NotFoundError');
    };

    try {
      navigator.mediaDevices.getUserMedia = customGetUserMedia;
      if (typeof MediaDevices !== 'undefined' && MediaDevices.prototype) {
        MediaDevices.prototype.getUserMedia = customGetUserMedia;
      }
    } catch (e) {}

    const origEnumerate = navigator.mediaDevices.enumerateDevices
      ? navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices)
      : null;

    const customEnumerateDevices = async function () {
      let devices = [];
      if (origEnumerate) {
        try {
          devices = await origEnumerate();
        } catch (e) {}
      }
      const virtualCam = {
        deviceId: VIRTUAL_CAM_ID,
        kind: 'videoinput',
        label: VIRTUAL_CAM_LABEL,
        groupId: 'snapstreak-sjsu-group',
        toJSON() {
          return {
            deviceId: this.deviceId,
            kind: this.kind,
            label: this.label,
            groupId: this.groupId,
          };
        },
      };
      return [virtualCam, ...devices.filter((d) => d.deviceId !== VIRTUAL_CAM_ID)];
    };

    try {
      navigator.mediaDevices.enumerateDevices = customEnumerateDevices;
      if (typeof MediaDevices !== 'undefined' && MediaDevices.prototype) {
        MediaDevices.prototype.enumerateDevices = customEnumerateDevices;
      }
    } catch (e) {}
  }

  if (navigator.permissions && navigator.permissions.query) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = async function (desc) {
      if (desc && (desc.name === 'camera' || desc.name === 'microphone' || desc.name === 'notifications')) {
        return {
          state: 'granted',
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
        };
      }
      return origQuery(desc);
    };
  }
})();
