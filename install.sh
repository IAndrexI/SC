#!/usr/bin/env bash
# install.sh — run inside any existing Debian LXC shell
# curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/install.sh | bash

set -euo pipefail

APP_DIR="/opt/sc"
DATA_DIR="/data/sc"
SERVICE_USER="scbot"
PORT="${PORT:-8080}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

step()  { echo -e "${YELLOW}[*]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# auto-elevate if not root
if [[ "$EUID" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

step "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
  git curl python3 python3-pip python3-venv \
  xvfb x11vnc websockify novnc \
  libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 \
  libasound2t64 libdbus-1-3 libexpat1 libx11-6 libxcb1 \
  libgtk-3-0t64 libatspi2.0-0t64 libglib2.0-0t64 \
  fonts-liberation fonts-unifont \
  xdg-utils

if ! command -v google-chrome &>/dev/null && ! command -v google-chrome-stable &>/dev/null; then
  step "Installing official Google Chrome..."
  curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/chrome.deb
  apt-get install -y -qq /tmp/chrome.deb 2>/dev/null || apt-get install -f -y -qq
  rm -f /tmp/chrome.deb
fi


# clone or update
if [[ -d "$APP_DIR/.git" ]]; then
  step "Updating repo..."
  git -C "$APP_DIR" pull --ff-only
else
  step "Cloning repo..."
  git clone https://github.com/IAndrexI/SC "$APP_DIR"
fi

step "Creating data directory..."
mkdir -p "$DATA_DIR"

# always wipe and rebuild the venv for a clean install
step "Building fresh Python environment..."
rm -rf "$APP_DIR/.venv"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# install Chromium — skip install-deps (we handled them above manually)
step "Downloading Chromium..."
PLAYWRIGHT_BROWSERS_PATH=/opt/sc-browsers \
  "$APP_DIR/.venv/bin/playwright" install chromium

step "Creating service user..."
id -u "$SERVICE_USER" &>/dev/null || useradd -r -s /bin/false -d "$APP_DIR" "$SERVICE_USER"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR" "$DATA_DIR" /opt/sc-browsers

step "Registering systemd service..."
cat > /etc/systemd/system/sc.service <<EOF
[Unit]
Description=sc automation service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/app
Environment="DATA_DIR=${DATA_DIR}"
Environment="PORT=${PORT}"
Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/sc-browsers"
ExecStart=${APP_DIR}/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=5


[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now sc

IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}✓ Done.${NC}"
echo -e "  Open → ${YELLOW}http://${IP}:${PORT}${NC}"
echo ""
