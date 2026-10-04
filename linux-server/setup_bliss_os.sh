#!/usr/bin/env bash
# ==============================================================================
# Setup Bliss OS (Android x86) Connection & ADB Bridge for SnapStreak
# ==============================================================================
# Bliss OS runs as a standalone KVM Virtual Machine in Proxmox with full
# Google Play Services and native Snapchat Android support.
#
# Usage:
#   ./setup_bliss_os.sh <BLISS_OS_IP>
# ==============================================================================
set -e

BLISS_IP="${1:-127.0.0.1}"
BLISS_PORT="${2:-5555}"

echo "============================================================"
echo " Setting up Bliss OS ADB Connection: ${BLISS_IP}:${BLISS_PORT}"
echo "============================================================"

# 1. Install adb tool on this container/server if missing
if ! command -v adb &> /dev/null; then
    echo "Installing ADB..."
    apt-get update -qq && apt-get install -y -qq adb curl
fi

# 2. Kill and restart ADB server
adb kill-server || true
adb start-server

# 3. Connect to Bliss OS over TCP/IP
echo "Connecting to Bliss OS at ${BLISS_IP}:${BLISS_PORT}..."
adb connect "${BLISS_IP}:${BLISS_PORT}"

sleep 2
echo ""
echo "=== Connected Devices ==="
adb devices -l
echo "========================="

echo ""
echo "Testing screen capture..."
if adb -s "${BLISS_IP}:${BLISS_PORT}" shell wm size 2>/dev/null; then
    echo "✓ Success! Bliss OS display detected."
else
    echo "⚠ Could not query Bliss OS display. Please ensure:"
    echo "  1. Bliss OS is booted and connected to your local network."
    echo "  2. Network ADB is enabled in Bliss OS Settings -> System -> Developer Options -> Network ADB debugging."
fi

echo ""
echo "To auto-send streaks with Bliss OS, set 'mode': 'bliss' and 'bliss_host': '${BLISS_IP}' in the Web UI."
