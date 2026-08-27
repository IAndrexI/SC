#!/usr/bin/env bash
# =============================================================================
# SnapStreak – Proxmox LXC Helper Script
# Creates a Debian 12 LXC container and installs SnapStreak inside it.
#
# Usage (run on Proxmox host shell):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/proxmox-lxc.sh)"
#
# Or manually:
#   chmod +x proxmox-lxc.sh && ./proxmox-lxc.sh
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
CTID="${CTID:-200}"               # LXC container ID (change if 200 is taken)
HOSTNAME="snapstreak"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
STORAGE="${STORAGE:-local-lvm}"   # Change to your storage pool (e.g. 'local')
DISK_SIZE="6"                     # GB
RAM="512"                         # MB  — Playwright needs ~400MB peak
CORES="1"
BRIDGE="vmbr0"
PORT="8080"                       # Web UI port exposed on the LXC's IP

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}┌──────────────────────────────────────┐${NC}"
echo -e "${GREEN}│     SnapStreak LXC Installer         │${NC}"
echo -e "${GREEN}└──────────────────────────────────────┘${NC}"

# ── Download Debian 12 template if not present ────────────────────────────────
if ! pveam list local | grep -q "$TEMPLATE"; then
  echo -e "${YELLOW}[*] Downloading Debian 12 template…${NC}"
  pveam download local debian-12-standard_12.7-1_amd64.tar.zst
fi

# ── Create the LXC ────────────────────────────────────────────────────────────
echo -e "${YELLOW}[*] Creating LXC ${CTID} (${HOSTNAME})…${NC}"
pct create "${CTID}" "local:vztmpl/${TEMPLATE}" \
  --hostname "${HOSTNAME}" \
  --cores "${CORES}" \
  --memory "${RAM}" \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --net0 name=eth0,bridge="${BRIDGE}",ip=dhcp \
  --unprivileged 1 \
  --features nesting=1 \
  --start 1

# ── Wait for network ──────────────────────────────────────────────────────────
echo -e "${YELLOW}[*] Waiting for container to boot…${NC}"
sleep 8

# ── Run installer inside LXC ──────────────────────────────────────────────────
echo -e "${YELLOW}[*] Running SnapStreak installer inside container…${NC}"
pct exec "${CTID}" -- bash -c "
  apt-get update -qq
  apt-get install -y -qq curl git python3 python3-pip python3-venv

  # Clone the repo
  git clone https://github.com/IAndrexI/SC /opt/snapstreak

  # Run the install script inside the container
  bash /opt/snapstreak/install.sh
"

# ── Get container IP ──────────────────────────────────────────────────────────
IP=$(pct exec "${CTID}" -- hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}✅  SnapStreak is running!${NC}"
echo -e "   LXC ID  : ${CTID}"
echo -e "   Web UI  : http://${IP}:${PORT}"
echo ""
echo -e "${YELLOW}📌 Next step: open the Web UI and log in to Snapchat.${NC}"
