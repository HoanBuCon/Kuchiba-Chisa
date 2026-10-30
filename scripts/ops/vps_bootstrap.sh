#!/usr/bin/env bash
# One-time hardening for an Ubuntu VPS hosting Chisa (4 vCPU / 8 GB / 80 GB). Run as root.
# Idempotent. It refuses to disable SSH passwords unless an authorized key exists.
set -euo pipefail

ADMIN_USER="${ADMIN_USER:-${SUDO_USER:-root}}"
ADMIN_HOME="$(getent passwd "${ADMIN_USER}" | cut -d: -f6)"

echo "[1/6] Firewall: allow only SSH, HTTP, HTTPS"
apt-get update -y
apt-get install -y ufw unattended-upgrades curl
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "[2/6] SSH: key-only authentication"
if [ -s "${ADMIN_HOME}/.ssh/authorized_keys" ]; then
  cat > /etc/ssh/sshd_config.d/60-chisa-hardening.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
CONF
  sshd -t && systemctl reload ssh
else
  echo "  !! ${ADMIN_HOME}/.ssh/authorized_keys is empty — NOT disabling password login." >&2
  echo "  !! Install your public key first, then re-run this script." >&2
fi

echo "[3/6] Unattended security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

echo "[4/6] Swap 2 GB (OOM buffer, swappiness 10)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/60-chisa-swap.conf
sysctl --system > /dev/null

echo "[5/6] Docker log rotation (default for all containers)"
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
CONF
  systemctl restart docker 2>/dev/null || true
else
  echo "  /etc/docker/daemon.json exists — verify it sets json-file max-size/max-file."
fi

echo "[6/6] Backup and monitor state directories"
install -d -m 700 /var/backups/chisa /var/lib/chisa-monitor
echo "Done. Next: docs/DEPLOYMENT_RUNBOOK.md"
