#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

echo "=========================================================="
echo "    MAKTAB DEVOPS COMPREHENSIVE AUTOMATED TEST SUITE    "
echo "=========================================================="

echo
echo "--> 1. Inventory Validation"
ansible-inventory -i inventory/hosts.yml --graph

echo
echo "--> 2. Playbook Syntax Validation"
./tests/test_syntax.sh

echo
echo "--> 3. Jinja2 Template Unit Tests"
python3 tests/test_templates.py

echo
echo "--> 4. Kubernetes Manifests Validation"
python3 tests/test_k8s_manifests.py

echo
echo "--> 5. Shell Scripts Validation"
./tests/test_scripts.sh

echo
echo "--> 6. Service Health Auditor Validation"
./tests/test_healthcheck.sh

echo
echo "=========================================================="
echo "    ALL AUTOMATED TESTS PASSED SUCCESSFULLY (EXIT 0)    "
echo "=========================================================="
