# SnapStreak — Linux Server Variant

The **Linux Server Variant** is a headless, 24/7 background automation service designed for Proxmox LXC containers, Debian 12 servers, or Docker.

### Why Use This Variant?
- **24/7 Unattended Operation**: Runs continuously in the background on a schedule via `APScheduler` and `systemd`. Your personal PC does not need to stay powered on.
- **Embedded noVNC Remote Browser**: Streams a real X11 virtual display (`Xvfb :99`) directly into your browser on another PC over port `8080` (or `6080`). You can type, click, solve captchas, and control the browser in real time.
- **Normal Browser Emulation**: Runs Google Chrome with `headless: False` inside a virtual display with genuine WebGL, audio, and fake camera stream to evade bot detection.

---

## Installation

### Option A: Proxmox Host (Automated LXC Creation)
Run this command in your **Proxmox Node Shell**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/proxmox-lxc.sh)"
```
*(Automatically detects your Debian 12 template, provisions an LXC container, installs dependencies, and starts the service).*

### Option B: Existing Debian / Ubuntu Server or Existing LXC
Run this command inside the **shell of your Linux machine or container**:

```bash
curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/install.sh | bash
```

---

## How to Check Status & Manage

From your host (e.g. for container ID `116`):
```bash
# Check container status
pct status 116

# Check bot service status
pct exec 116 -- systemctl status sc

# Restart the service
pct exec 116 -- systemctl restart sc

# View real-time logs
pct exec 116 -- journalctl -u sc -f
```

Inside the container:
```bash
systemctl status sc
journalctl -u sc -f
```

---

## Accessing the Dashboard

Open your web browser on any computer or phone on your network:
```
http://<SERVER-IP>:8080
```
- Click **Start Live Browser** to open the embedded noVNC view and log into Snapchat.
- Click **Save Session** once authenticated.
- Configure your scheduled send time and target friends list in the web UI.
