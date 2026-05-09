#!/usr/bin/env bash
# Idempotent bootstrap for Oracle Cloud Always Free ARM Ampere A1
# (Ubuntu 22.04 LTS, 4 OCPU / 24 GB RAM target).
#
# Usage on a fresh VM:
#   ssh ubuntu@<vm-ip>
#   curl -fsSL https://raw.githubusercontent.com/<user>/crypto-trading-bot/main/scripts/oracle-bootstrap.sh | bash
# or from a local clone:
#   scp scripts/oracle-bootstrap.sh ubuntu@<vm-ip>:~/
#   ssh ubuntu@<vm-ip> 'bash oracle-bootstrap.sh'
#
# Reruns are safe — every step checks before changing state.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/CHANGEME/crypto-trading-bot.git}"
REPO_DIR="${HOME}/bot"
ARCH="$(dpkg --print-architecture)"   # arm64 on A1

log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap]\033[0m %s\n' "$*" >&2; }

# -----------------------------------------------------------------------------
# 1. Apt packages
# -----------------------------------------------------------------------------
log "Updating apt and installing base packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl gnupg lsb-release \
  ufw fail2ban git jq \
  iptables-persistent netfilter-persistent

# -----------------------------------------------------------------------------
# 2. Docker + compose plugin (official repo, not the apt-shipped 'docker.io')
# -----------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine + compose plugin"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
else
  log "Docker already installed: $(docker --version)"
fi

if ! groups "$USER" | grep -q '\bdocker\b'; then
  log "Adding $USER to docker group (re-login required)"
  sudo usermod -aG docker "$USER"
fi

sudo systemctl enable --now docker

# -----------------------------------------------------------------------------
# 3. Firewall — Oracle defaults to a permissive iptables that gets clobbered
#    when ufw is enabled. Pin SSH allow at the top of INPUT first.
# -----------------------------------------------------------------------------
log "Configuring firewall"
if ! sudo iptables -C INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 1 -p tcp --dport 22 -j ACCEPT
  sudo netfilter-persistent save
fi

sudo ufw --force reset >/dev/null
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw --force enable

sudo systemctl enable --now fail2ban

# -----------------------------------------------------------------------------
# 4. Cloudflared (ARM64 deb)
# -----------------------------------------------------------------------------
if ! command -v cloudflared >/dev/null 2>&1; then
  log "Installing cloudflared (${ARCH})"
  TMP=$(mktemp -d)
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" \
    -o "${TMP}/cloudflared.deb"
  sudo dpkg -i "${TMP}/cloudflared.deb"
  rm -rf "${TMP}"
else
  log "cloudflared already installed: $(cloudflared --version | head -1)"
fi

# -----------------------------------------------------------------------------
# 5. Repo clone
# -----------------------------------------------------------------------------
if [[ ! -d "${REPO_DIR}/.git" ]]; then
  log "Cloning ${REPO_URL} -> ${REPO_DIR}"
  git clone "${REPO_URL}" "${REPO_DIR}"
else
  log "Repo already present at ${REPO_DIR} — skipping clone"
fi

# Ensure the EMERGENCY_STOP host file exists as a regular file (not a dir,
# which Docker would create silently if the bind-mount target is missing).
touch "${REPO_DIR}/EMERGENCY_STOP"
rm -f "${REPO_DIR}/EMERGENCY_STOP"   # leave absent so the kill switch is OFF
test -e "${REPO_DIR}/EMERGENCY_STOP" || true

# -----------------------------------------------------------------------------
# 6. Next steps
# -----------------------------------------------------------------------------
cat <<EOF

[bootstrap] DONE.

Next steps (run from your laptop):

  scp .env ubuntu@<vm-ip>:${REPO_DIR}/.env
  ssh ubuntu@<vm-ip> 'chmod 600 ${REPO_DIR}/.env'

Then on the VM:

  cd ${REPO_DIR}
  docker compose -f docker-compose.headless.yml pull
  docker compose -f docker-compose.headless.yml up -d
  docker compose -f docker-compose.headless.yml ps

Cloudflare Tunnel (one-time):
  cloudflared tunnel login
  cloudflared tunnel create bot-api
  cloudflared tunnel route dns bot-api bot.<your-domain>
  # Edit ~/.cloudflared/config.yml:
  #   tunnel: <id>
  #   credentials-file: ~/.cloudflared/<id>.json
  #   ingress:
  #     - hostname: bot.<your-domain>
  #       service: http://localhost:8005
  #     - service: http_status:404
  sudo cloudflared service install <token>

EOF
