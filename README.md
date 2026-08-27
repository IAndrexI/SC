# SnapStreak – Server Edition

> Automated Snapchat streak sender running headlessly on a Proxmox LXC.  
> Controlled via a clean web dashboard from any browser.

---

## ⚡ Quick Start (Proxmox)

### Step 1 — Run the LXC helper on your Proxmox host shell

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/YOUR_USER/snapstreak-server/main/proxmox-lxc.sh)"
```

This will:
- Download the Debian 12 template (if needed)
- Create an unprivileged LXC (512 MB RAM, 6 GB disk, 1 core)
- Install all dependencies + the SnapStreak service inside it
- Print the web UI URL when done

### Step 2 — Open the Web UI

Navigate to `http://<LXC-IP>:8080` in your browser.

### Step 3 — Log in to Snapchat

**Option A – Cookie Import (Recommended, easiest):**
1. Open [web.snapchat.com](https://web.snapchat.com) in your regular browser and log in.
2. Install the **[Cookie-Editor](https://cookie-editor.com/)** extension (available for Chrome & Firefox).
3. Click the extension → **Export** → copy the JSON.
4. In the SnapStreak web UI, paste the JSON into the **Cookie Import** box and click **Import Cookies**.

**Option B – Server Browser Login:**  
Click **Login to Snapchat** in the web UI. A browser will open on the server (visible only if you have VNC/X11 access to the LXC). Complete the login and the session will be saved.

### Step 4 — Add Friends & Set Schedule

1. Enter your friends' Snapchat usernames (one per line, no @ needed).
2. Choose a daily send time.
3. Toggle **Auto-send enabled** ON.
4. Click **Send Streaks Now** to test it immediately.

---

## 📦 LXC Specs (Why Debian 12?)

| Option | RAM | Works? | Notes |
|--------|-----|--------|-------|
| **Debian 12** ✅ | 512 MB | ✅ Best | Playwright Chromium needs glibc — Alpine won't work |
| Alpine | ~256 MB | ❌ | musl libc breaks Chromium |
| Ubuntu 22.04 | 512 MB | ✅ | Works but heavier than Debian 12 |

---

## 🔧 Manual Install (Any Debian 12 Machine)

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/snapstreak-server/main/install.sh | sudo bash
```

---

## 📁 File Structure

```
snapstreak-server/
├── app/
│   ├── main.py          # FastAPI server + scheduler + WebSocket
│   ├── automation.py    # Playwright Snapchat Web automation
│   ├── config.py        # JSON config persistence
│   └── static/
│       └── index.html   # Web dashboard UI
├── requirements.txt
├── install.sh           # Installer (runs inside LXC)
├── proxmox-lxc.sh       # Proxmox helper (runs on host)
└── README.md
```

---

## 🛠️ Useful Commands (inside LXC)

```bash
# Check service status
systemctl status snapstreak

# View live logs
journalctl -u snapstreak -f

# Restart service
systemctl restart snapstreak

# Update to latest version
cd /opt/snapstreak && git pull && systemctl restart snapstreak
```

---

## ⚠️ Disclaimer

This tool automates the official Snapchat web interface. Use it responsibly and at your own risk. Snapchat's Terms of Service prohibit unauthorized automation.
