#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

echo "=== Running Ansible Syntax Checks ==="
ansible-playbook -i inventory/hosts.yml site.yml --syntax-check
ansible-playbook -i inventory/hosts.yml 08-verify.yml --syntax-check

for pb in 0*.yml; do
  echo "Checking $pb..."
  ansible-playbook -i inventory/hosts.yml "$pb" --syntax-check
done

echo "All playbooks passed syntax check successfully!"
