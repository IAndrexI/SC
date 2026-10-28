# 👻 SnapStreak Studio — Snapchat Web Auto Streak Maker & Live SJSU Camera

A complete, self-contained Snapchat Web automation studio featuring **persistent Login Cookie Vault protection**, a **Dual-Mode Auto Streak Maker** (**🧠 AI / Expected Steps Mode** + **🎬 Custom Macro Mode**), and **Live San José State University (SJSU) Meteorology Webcam** injection.

---

## ✨ Key Features

### 1. 🌐 Full Interactive Access to Snapchat Web (`https://web.snapchat.com/`)
- Embedded real-time interactive Snapchat Web viewport on **Port 8080** (`http://localhost:8080`).
- **Click, Scroll & Direct Keyboard Mode**: Click anywhere on the live Snapchat screen, scroll with your mouse wheel, or toggle **Direct Keyboard** to type directly into Snapchat Web.
- **1-Click Session Repair**: Automatically resolves *"Snapchat is already open in another tab"* (`Use Here`) without ever touching your login cookies.

### 2. 🍪 Persistent Cookie Vault (Zero Cookie Loss)
- Automatically syncs and backs up all Snapchat & Google authentication cookies (`sc_at`, `__Host-sc-a-auth-session`, `__Host-X-Snap-Client-Cookie`, `sc-a-nonce`, `sc-a-csrf`) plus `IndexedDB` and `localStorage` across `browser_profile/`, `session.json`, and `session_backup.json`.
- **Non-Destructive Save**: Clicking **Save Cookies** snapshots your live browser cookies immediately *without* closing or interrupting your open Snapchat session.
- **Import / Export / Restore**: Supports importing cookies from Cookie-Editor JSON, Playwright `storage_state`, or raw `Cookie:` headers.

### 3. 🔥 Dual-Mode Auto Streak Maker
Switch seamlessly between two execution engines in the Studio UI or via `/api/config`:

- **🧠 Mode A — AI / Expected Steps Mode (`streak_mode: "ai_steps"`)**:
  - **Step 1 (Prepare)**: Dismisses blockers (`Use Here` / `Not now`) and injects the latest SJSU webcam frame.
  - **Step 2 (Open Camera)**: Detects screen state and activates the camera viewfinder.
  - **Step 3 (Capture Snap)**: Performs a zero-drag quick click on the center shutter circle (ignoring filter lenses).
  - **Step 4 (Open Send To)**: Clicks `"Send To"` on the captured snap preview.
  - **Step 5 (Select Friends & Safety Audit)**: Supports **Direct Friend Search & Click** (`direct`), **Snapchat Shortcut Pill + Select All** (`shortcut`), or **Smart Hybrid** (`auto`). Runs a mandatory safety audit that forcibly unchecks `My AI`, `My Story`, `Spotlight`, and `Team Snapchat`.
  - **Step 6 (Final Send)**: Clicks the final `"Send"` button (or pauses before sending in **Sample Preview** mode).

- **🎬 Mode B — Custom Macro Mode (`streak_mode: "macro"`)**:
  - **Smart Live Recording**: Click **🔴 Record Clicks on Screen** and perform your steps on the live Snapchat viewport. Every click records both DOM metadata (`selector`, `text`, `aria-label`) and relative/absolute coordinates (`rx`, `ry`, `x`, `y`).
  - **Visual Macro Step Editor**: Inspect, reorder, or delete individual steps, reset to the built-in **5-Step Default Streak Template**, and replay with configurable step delay (`0.5s`–`10s`).

### 4. 📡 SJSU Meteorology Live Webcam (`met.sjsu.edu`)
- Fetches live frames from `https://www.met.sjsu.edu/cam_directory/webcam1/latest.jpg`.
- **CORS-Immune WebRTC Canvas Stream**: Injects the live frame as a base64 Data URL (`data:image/jpeg;base64,...`) into `camera_hook.js` so `navigator.mediaDevices.getUserMedia` streams a 30 FPS 1280×720 SJSU camera feed with zero CORS tainting, alongside native Chromium `.y4m` video capture.

---

## 🚀 Quick Start

### Windows (Local Studio Server on Port 8080)
Run [`windows-extension/run_server.bat`](windows-extension/run_server.bat) or:
```powershell
python windows-extension/run_server.py
```
Then open **`http://localhost:8080`** in your browser.

### Windows (Direct Desktop Runner)
```powershell
python windows-extension/run_desktop.py --mode ai_steps --method direct
# Or run in Macro mode:
python windows-extension/run_desktop.py --mode macro
```

### Linux / Proxmox LXC Server
```bash
cd linux-server
bash install.sh
```
