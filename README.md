# SnapStreak (SC)

Automated streak management service and personal task scheduler for Snapchat Web, featuring live synthetic webcam streaming and smart anti-detection.

This project is organized into **two distinct variants** depending on where you want to run it:

---

## 🚀 Choose Your Variant

| Feature | 🪟 [Windows Extension](./windows-extension/) | 🐧 [Linux Server (LXC / Docker)](./linux-server/) |
| :--- | :--- | :--- |
| **Best For** | Running on your daily desktop/laptop | 24/7 dedicated home server / Proxmox |
| **Platform** | Windows 10/11 | Debian 12, Proxmox LXC, Docker, Ubuntu |
| **Requires PC On?** | Yes | No (runs on your server 24/7) |
| **Display Mode** | Regular browser window with overlay HUD | Virtual X11 (`Xvfb`) + embedded noVNC viewer |
| **Remote Access** | Local desktop | Web UI accessible from any PC/phone (`:8080`) |
| **IP Footprint** | 100% Residential PC IP | Local home network / Homelab IP |
| **Quick Start** | Double-click `install_extension.bat` | `curl -fsSL .../install.sh \| bash` |

---

### 🪟 Variant 1: Windows Extension
*Located in [`windows-extension/`](./windows-extension/)*

Runs directly inside your Windows Brave or Google Chrome browser as an unpacked Manifest V3 extension.
- **Floating HUD**: Interactive on-screen overlay showing streak countdowns, target friend list, and real-time step progress.
- **Synthetic SJSU Camera**: Injects a live SJSU Meteorology camera feed directly into Snapchat's WebRTC device pipeline.
- **Autologon support**: Includes optional scripts to boot your Windows PC directly into the browser on startup.

👉 **[See Windows Extension Setup Guide](./windows-extension/README.md)**

---

### 🐧 Variant 2: Linux Server (LXC / Headless)
*Located in [`linux-server/`](./linux-server/)*

Runs as a lightweight, 24/7 background daemon on Linux (Debian 12, Proxmox LXC, or Docker).
- **Embedded noVNC Remote Desktop**: View and interact with the real Linux browser window directly from any browser on your other PC or phone via port `8080`.
- **Full Headful Emulation**: Runs Google Chrome in a RAM-only virtual display (`Xvfb :99`) with real GPU/WebGL pipelines to evade bot detection.
- **Built-in APScheduler**: Automatically fires your streak routine daily at your chosen time without needing any PC turned on.

#### Quick Install (Proxmox Host):
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/proxmox-lxc.sh)"
```

#### Quick Install (Inside Debian LXC / Linux Server):
```bash
curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/install.sh | bash
```

👉 **[See Linux Server Setup Guide](./linux-server/README.md)**
