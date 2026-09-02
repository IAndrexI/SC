#!/usr/bin/env bash
# ==============================================================================
# Setup ReDroid (Android 11 in Container) + ADB + Snapchat for SnapStreak Server
# ==============================================================================
set -e

echo "=========================================="
echo " Setting up Android Container on LXC...   "
echo "=========================================="

# 1. Update and install prerequisites
apt-get update
apt-get install -y adb curl wget docker.io docker-compose

# 2. Start Docker service
systemctl enable --now docker

# 3. Pull and run ReDroid Android 11 container
echo "Pulling ReDroid Android 11 image..."
docker pull redroid/redroid:11.0.0-latest

echo "Starting ReDroid container on port 5555..."
docker rm -f redroid || true
docker run -itd \
    --name redroid \
    --memory-swappiness=0 \
    --privileged \
    --restart always \
    -v /data/android-data:/data \
    -p 5555:5555 \
    redroid/redroid:11.0.0-latest \
    androidboot.redroid_width=720 \
    androidboot.redroid_height=1280 \
    androidboot.redroid_dpi=320 \
    androidboot.redroid_fps=30

echo "Waiting for Android to boot..."
sleep 15

# 4. Connect ADB
adb connect 127.0.0.1:5555
echo "ADB device list:"
adb devices

echo "=========================================="
echo " Android container is running!            "
echo " You can install Snapchat APK using:      "
echo "   adb install /path/to/snapchat.apk      "
echo "=========================================="
