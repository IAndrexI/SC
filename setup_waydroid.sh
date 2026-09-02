#!/usr/bin/env bash
# =============================================================================
# setup_waydroid.sh — Run INSIDE the LXC to install Waydroid + Snapchat
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# 1. Check binder
info "Checking binder availability..."
if [ ! -e /dev/binder ]; then
  warn "/dev/binder not found. Run on Proxmox HOST first:"
  echo "  modprobe binder_linux devices=\"binder,hwbinder,vndbinder\""
  echo "  chmod 0666 /dev/binder /dev/hwbinder /dev/vndbinder"
  echo "  echo binder_linux >> /etc/modules-load.d/modules.conf"
  echo "  echo 'options binder_linux devices=\"binder,hwbinder,vndbinder\"' > /etc/modprobe.d/binder.conf"
  echo "  cat >> /etc/pve/lxc/113.conf << 'EOF'"
  echo "  lxc.mount.entry: /dev/binder dev/binder none bind,optional,create=file"
  echo "  lxc.mount.entry: /dev/hwbinder dev/hwbinder none bind,optional,create=file"
  echo "  lxc.mount.entry: /dev/vndbinder dev/vndbinder none bind,optional,create=file"
  echo "  lxc.cgroup2.devices.allow: c 511:0 rwm"
  echo "  lxc.cgroup2.devices.allow: c 511:1 rwm"
  echo "  lxc.cgroup2.devices.allow: c 511:2 rwm"
  echo "  EOF"
  echo "  pct restart 113"
  read -rp "Continue anyway? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# 2. Install deps
info "Installing packages..."
apt-get update -qq
apt-get install -y --no-install-recommends waydroid adb python3-pip curl wget xvfb ffmpeg

# 3. Enable waydroid-container service
info "Enabling waydroid-container..."
systemctl enable --now waydroid-container || true

# 4. Init Waydroid
info "Initialising Waydroid (Android 13 + GApps)..."
waydroid status 2>/dev/null | grep -q "RUNNING" || waydroid init -s GAPPS -f || waydroid init -f

# 5. Start session
info "Starting Waydroid session..."
waydroid session start &
sleep 10

# 6. Wait for ADB
info "Waiting for ADB device..."
for i in $(seq 1 30); do
  adb devices | grep -q "emulator\|192.168" && { info "ADB ready!"; break; }
  sleep 2 && echo -n "."
done
echo ""
adb connect 192.168.240.112:5555 2>/dev/null || true
sleep 3 && adb wait-for-device

# 7. Download Snapchat APK
SNAP_APK="/data/snapchat.apk"
if [ ! -f "$SNAP_APK" ]; then
  info "Downloading Snapchat APK..."
  curl -L --retry 3 \
    "https://d.apkpure.com/b/APK/com.snapchat.android?version=latest" \
    -o "$SNAP_APK" \
    -A "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36" || \
    warn "APK download failed. Place snapchat.apk at /data/snapchat.apk manually."
fi

# 8. Install Snapchat
[ -f "$SNAP_APK" ] && adb install -r "$SNAP_APK" && info "Snapchat installed!" || warn "Run: adb install -r /data/snapchat.apk"

# 9. Python deps
info "Installing Python ADB libs..."
pip3 install --break-system-packages uiautomator2 Pillow requests aiohttp 2>/dev/null || \
pip3 install uiautomator2 Pillow requests aiohttp

# 10. Init uiautomator2
python3 -m uiautomator2 init || warn "Run manually: python3 -m uiautomator2 init"

# 11. Restart sc
systemctl restart sc 2>/dev/null || true

echo ""
echo "========================================"
echo " Waydroid + Snapchat setup complete!"
echo "========================================"
echo " Open dashboard -> Start Android Session"
echo " Log into Snapchat -> Save & Activate"
