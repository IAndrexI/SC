#!/usr/bin/env bash
# =============================================================================
# SnapStreak – Application Installer
# Runs INSIDE the LXC container (or any Debian 12 machine).
# Can also be used standalone:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/snapstreak-server/main/install.sh | bash
# =============================================================================

set -euo pipefail

APP_DIR="/opt/snapstreak"
DATA_DIR="/data/snapstreak"
SERVICE_USER="snapstreak"
PORT="${PORT:-8080}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
step()  { echo -e "${YELLOW}[*]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# ── Must be root ──────────────────────────────────────────────────────────────
[[ "$EUID" -ne 0 ]] && error "Please run as root (or with sudo)."

step "Updating packages…"
apt-get update -qq
apt-get install -y -qq \
  git curl python3 python3-pip python3-venv \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 \
  libasound2 libdbus-1-3 libexpat1 libx11-6 libxcb1 \
  fonts-liberation xdg-utils

# ── Clone / update repo ───────────────────────────────────────────────────────
if [[ -d "$APP_DIR/.git" ]]; then
  step "Updating existing installation…"
  git -C "$APP_DIR" pull --ff-only
else
  step "Cloning SnapStreak…"
  git clone https://github.com/IAndrexI/SC "$APP_DIR"
fi

# ── Data directory ────────────────────────────────────────────────────────────
step "Creating data directory at ${DATA_DIR}…"
mkdir -p "$DATA_DIR"

# ── Python venv + dependencies ────────────────────────────────────────────────
step "Setting up Python virtual environment…"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# ── Install Playwright browsers (Chromium only — lightest) ────────────────────
step "Installing Playwright Chromium browser…"
"$APP_DIR/.venv/bin/playwright" install chromium
"$APP_DIR/.venv/bin/playwright" install-deps chromium

# ── Create system user ────────────────────────────────────────────────────────
step "Creating service user '${SERVICE_USER}'…"
id -u "$SERVICE_USER" &>/dev/null || useradd -r -s /bin/false -d "$APP_DIR" "$SERVICE_USER"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR" "$DATA_DIR"

# ── systemd service ───────────────────────────────────────────────────────────
step "Installing systemd service…"
cat > /etc/systemd/system/snapstreak.service <<EOF
[Unit]
Description=SnapStreak – Automated Snapchat Streak Sender
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/app
Environment="DATA_DIR=${DATA_DIR}"
Environment="PORT=${PORT}"
ExecStart=${APP_DIR}/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now snapstreak

# ── Done ──────────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  SnapStreak installed successfully!     ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Web UI  → ${YELLOW}http://${IP}:${PORT}${NC}"
echo -e "  Logs    → journalctl -u snapstreak -f"
echo -e "  Data    → ${DATA_DIR}"
echo ""
echo -e "📌 Open the Web UI and click ${YELLOW}'Login to Snapchat'${NC} to get started."
