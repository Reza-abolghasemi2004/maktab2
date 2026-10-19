#!/usr/bin/env bash
# ==============================================================================
# Maktab DevOps - Comprehensive Service Health Auditor Tool
# Independent, Read-Only Diagnostic and Health Reporting Tool
# Does NOT execute any Ansible playbooks or make state modifications.
# ==============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default CLI parameters
TARGET_HOST="all"
TARGET_SCOPE="all"
OUTPUT_DIR="${REPO_ROOT}/reports/healthcheck"
JSON_ONLY=false
OFFLINE_MODE=false

show_help() {
  cat <<'EOF'
Maktab DevOps Service Health Auditor

Usage:
  ./scripts/healthcheck.sh [OPTIONS]

Options:
  --host <vps1|vps2|control|all>    Target host to audit (default: all)
  --scope <SCOPE>                   Specific subsystem scope to audit (default: all)
                                    Available scopes:
                                      all, network, kubernetes, monitoring,
                                      storage, public-endpoints, access,
                                      logging, devtools, security, backup
  --output-dir <PATH>               Custom directory to save reports (default: reports/healthcheck)
  --json-only                       Suppress terminal UI table and print only the JSON report path
  --offline                         Run in offline static mode (bypass remote SSH connectivity probes)
  -h, --help                        Show this help message and exit

Exit Codes:
  0: All mandatory checks passed successfully.
  1: At least one mandatory check failed.
  2: Incomplete audit (one or more mandatory checks could not be executed / NOT_CHECKED).
  3: Internal auditor error or invalid arguments.

Examples:
  ./scripts/healthcheck.sh
  ./scripts/healthcheck.sh --host vps1
  ./scripts/healthcheck.sh --scope kubernetes
  ./scripts/healthcheck.sh --scope monitoring --output-dir /tmp/audit-results
  ./scripts/healthcheck.sh --offline --json-only
EOF
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      TARGET_HOST="$2"
      shift 2
      ;;
    --scope)
      TARGET_SCOPE="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --json-only)
      JSON_ONLY=true
      shift
      ;;
    --offline)
      OFFLINE_MODE=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      show_help >&2
      exit 3
      ;;
  esac
done

# Validate target host
VALID_HOSTS=("all" "vps1" "vps2" "control")
HOST_VALID=false
for h in "${VALID_HOSTS[@]}"; do
  if [[ "$TARGET_HOST" == "$h" ]]; then
    HOST_VALID=true
    break
  fi
done
if [[ "$HOST_VALID" != "true" ]]; then
  echo "Error: Invalid host '$TARGET_HOST'. Choose from: ${VALID_HOSTS[*]}" >&2
  exit 3
fi

# Validate target scope
VALID_SCOPES=("all" "network" "kubernetes" "monitoring" "storage" "public-endpoints" "access" "logging" "devtools" "security" "backup")
SCOPE_VALID=false
for s in "${VALID_SCOPES[@]}"; do
  if [[ "$TARGET_SCOPE" == "$s" ]]; then
    SCOPE_VALID=true
    break
  fi
done
if [[ "$SCOPE_VALID" != "true" ]]; then
  echo "Error: Invalid scope '$TARGET_SCOPE'. Choose from: ${VALID_SCOPES[*]}" >&2
  exit 3
fi

# Validate local prerequisites
for tool in python3 openssl curl; do
  if ! command -v "$tool" &>/dev/null; then
    echo "Error: Required local tool '$tool' is not installed." >&2
    exit 3
  fi
done

# Execute Python audit engine
PYTHONPATH="${REPO_ROOT}/scripts" python3 - <<EOF
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from lib.catalog import load_inventory_and_vars, get_service_catalog
from lib.auditor import HealthAuditor
from lib.reporter import print_terminal_summary, save_reports

repo_root = "${REPO_ROOT}"
target_host = "${TARGET_HOST}"
target_scope = "${TARGET_SCOPE}"
output_dir = "${OUTPUT_DIR}"
json_only = True if "${JSON_ONLY}" == "true" else False
offline_mode = True if "${OFFLINE_MODE}" == "true" else False

try:
    inv_data = load_inventory_and_vars(repo_root)
    service_catalog = get_service_catalog(scope=target_scope, host=target_host)

    # Git metadata
    def get_git_info(cmd):
        try:
            import subprocess
            res = subprocess.run(cmd, shell=True, cwd=repo_root, stdout=subprocess.PIPE, text=True)
            return res.stdout.strip()
        except Exception:
            return "unknown"

    branch = get_git_info("git rev-parse --abbrev-ref HEAD")
    commit = get_git_info("git rev-parse HEAD")

    auditor = HealthAuditor(repo_root, scope=target_scope, host=target_host, offline=offline_mode)
    auditor.audit_all(inv_data)

    checks = auditor.checks

    # Calculate summary counters
    total = len(checks)
    pass_cnt = sum(1 for c in checks if c['status'] == 'PASS')
    fail_cnt = sum(1 for c in checks if c['status'] == 'FAIL')
    warn_cnt = sum(1 for c in checks if c['status'] == 'WARN')
    skip_cnt = sum(1 for c in checks if c['status'] == 'SKIP')
    not_checked_cnt = sum(1 for c in checks if c['status'] == 'NOT_CHECKED')

    p0_cnt = sum(1 for c in checks if c['severity'] == 'P0' and c['status'] in ('FAIL', 'WARN'))
    p1_cnt = sum(1 for c in checks if c['severity'] == 'P1' and c['status'] in ('FAIL', 'WARN'))
    p2_cnt = sum(1 for c in checks if c['severity'] == 'P2' and c['status'] in ('FAIL', 'WARN'))
    p3_cnt = sum(1 for c in checks if c['severity'] == 'P3' and c['status'] in ('FAIL', 'WARN'))

    # Determine Exit Code:
    # 0: all mandatory checks pass
    # 1: at least one mandatory check fails
    # 2: incomplete (mandatory checks NOT_CHECKED)
    # 3: internal error
    mandatory_fails = [c for c in checks if c['mandatory'] and c['status'] == 'FAIL']
    mandatory_uninspected = [c for c in checks if c['mandatory'] and c['status'] == 'NOT_CHECKED']

    if mandatory_fails:
        exit_code = 1
    elif mandatory_uninspected:
        exit_code = 2
    else:
        exit_code = 0

    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "auditor_version": "1.0.0",
        "repo_path": repo_root,
        "git_branch": branch,
        "git_commit": commit,
        "cli_args": {
            "host": target_host,
            "scope": target_scope,
            "offline": offline_mode
        },
        "summary": {
            "total": total,
            "pass": pass_cnt,
            "fail": fail_cnt,
            "warn": warn_cnt,
            "skip": skip_cnt,
            "not_checked": not_checked_cnt,
            "p0_count": p0_cnt,
            "p1_count": p1_cnt,
            "p2_count": p2_cnt,
            "p3_count": p3_cnt
        },
        "exit_code": exit_code
    }

    md_path, json_path = save_reports(checks, metadata, service_catalog, output_dir)

    if json_only:
        print(json_path)
    else:
        print_terminal_summary(checks, metadata)

    sys.exit(exit_code)

except Exception as e:
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(3)
EOF
EXIT_STATUS=$?
exit $EXIT_STATUS
