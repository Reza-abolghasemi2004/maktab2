#!/usr/bin/env bash
# آماده‌سازی لپ‌تاپ (Ubuntu/Debian) به‌عنوان Ansible control node + کلاینت VPN
set -euo pipefail
sudo apt-get update
sudo apt-get install -y ansible python3-cryptography python3-netaddr python3-kubernetes wireguard-tools git openssh-client
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
ansible-galaxy collection install -r "$(dirname "$0")/../requirements.yml"
echo "کلید عمومی را روی هر دو VPS برای root نصب کنید:"
echo "  ssh-copy-id -i ~/.ssh/id_ed25519.pub root@81.12.50.30"
echo "  ssh-copy-id -i ~/.ssh/id_ed25519.pub root@31.56.89.69"
