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
HOSTNAME="${HOSTNAME:-snapstreak}"
STORAGE="${STORAGE:-local-lvm}"   # Change to your storage pool (e.g. 'local')
DISK_SIZE="${DISK_SIZE:-8}"       # GB
RAM="${RAM:-1024}"                # MB  — Chrome needs ~500-600MB peak
CORES="${CORES:-1}"
BRIDGE="${BRIDGE:-vmbr0}"
PORT="${PORT:-8080}"                       # Web UI port exposed on the LXC's IP

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}┌──────────────────────────────────────┐${NC}"
echo -e "${GREEN}│     SnapStreak LXC Installer         │${NC}"
echo -e "${GREEN}└──────────────────────────────────────┘${NC}"

# ── Auto-detect & Download Debian 12 template if not present ─────────────────
pveam update >/dev/null 2>&1 || true

DETECTED_TEMPLATE=$(pveam available --section system 2>/dev/null | grep -o 'debian-12-standard_.*_amd64\.tar\.[a-z0-9]*' | head -n1)
TEMPLATE="${TEMPLATE:-${DETECTED_TEMPLATE:-debian-12-standard_12.7-1_amd64.tar.zst}}"

if ! pveam list local | grep -q "$TEMPLATE"; then
  echo -e "${YELLOW}[*] Downloading Debian 12 template (${TEMPLATE})…${NC}"
  pveam download local "${TEMPLATE}"
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
  if [[ -f /opt/snapstreak/linux-server/install.sh ]]; then
    bash /opt/snapstreak/linux-server/install.sh
  else
    bash /opt/snapstreak/install.sh
  fi
"

# ── Get container IP ──────────────────────────────────────────────────────────
IP=$(pct exec "${CTID}" -- hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}✅  SnapStreak is running!${NC}"
echo -e "   LXC ID  : ${CTID}"
echo -e "   Web UI  : http://${IP}:${PORT}"
echo ""
echo -e "${YELLOW}📌 Next step: open the Web UI and log in to Snapchat.${NC}"
