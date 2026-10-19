#!/usr/bin/env bash
# ==============================================================================
# Automated Test Suite for Service Health Auditor (scripts/healthcheck.sh)
# Validates CLI arguments, JSON/Markdown schemas, secret redaction,
# exit codes, and scope/host filtering.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AUDITOR="${REPO_ROOT}/scripts/healthcheck.sh"
TEST_TMP_DIR=$(mktemp -d /tmp/maktab-auditor-test.XXXXXX)

cleanup() {
  rm -rf "$TEST_TMP_DIR"
}
trap cleanup EXIT

echo "=========================================================="
echo "    TESTING SERVICE HEALTH AUDITOR (scripts/healthcheck.sh)"
echo "=========================================================="

test_pass() {
  echo "  [PASS] $1"
}

test_fail() {
  echo "  [FAIL] $1: $2" >&2
  exit 1
}

# 1. Test --help flag
echo "--> 1. Testing --help flag..."
OUT_HELP=$("$AUDITOR" --help)
if echo "$OUT_HELP" | grep -q "Maktab DevOps Service Health Auditor"; then
  test_pass "--help outputs usage guide with exit code 0"
else
  test_fail "--help" "Unexpected help output"
fi

# 2. Test Invalid CLI Arguments
echo "--> 2. Testing CLI argument validation and Exit Code 3..."
set +e
"$AUDITOR" --invalid-flag &>/dev/null
EXIT_CODE=$?
set -e
if [ "$EXIT_CODE" -eq 3 ]; then
  test_pass "Invalid flag correctly rejected with exit code 3"
else
  test_fail "Invalid flag" "Expected exit code 3, got $EXIT_CODE"
fi

set +e
"$AUDITOR" --host non_existent_host &>/dev/null
EXIT_CODE=$?
set -e
if [ "$EXIT_CODE" -eq 3 ]; then
  test_pass "Invalid host correctly rejected with exit code 3"
else
  test_fail "Invalid host" "Expected exit code 3, got $EXIT_CODE"
fi

set +e
"$AUDITOR" --scope non_existent_scope &>/dev/null
EXIT_CODE=$?
set -e
if [ "$EXIT_CODE" -eq 3 ]; then
  test_pass "Invalid scope correctly rejected with exit code 3"
else
  test_fail "Invalid scope" "Expected exit code 3, got $EXIT_CODE"
fi

# 3. Test Full Audit Execution in Offline Mode
echo "--> 3. Testing Full Audit in Offline Mode..."
set +e
JSON_PATH=$("$AUDITOR" --offline --json-only --output-dir "$TEST_TMP_DIR")
AUDIT_EXIT_CODE=$?
set -e

# Because monitoring_alertmanager has placeholder CHANGE_ME, audit exit code must be 1 (mandatory check failed)
if [ "$AUDIT_EXIT_CODE" -eq 1 ]; then
  test_pass "Auditor correctly returned Exit Code 1 for detected mandatory failures"
else
  test_fail "Audit exit code" "Expected 1 for mandatory failures, got $AUDIT_EXIT_CODE"
fi

if [ -f "$JSON_PATH" ]; then
  test_pass "JSON report file created: $JSON_PATH"
else
  test_fail "JSON report" "File does not exist: $JSON_PATH"
fi

# 4. Validate JSON Schema and Fields
echo "--> 4. Validating JSON Report Schema and Mandatory Fields..."
python3 - <<EOF
import json
import sys

with open("$JSON_PATH", "r") as f:
    data = json.load(f)

meta = data.get("audit_metadata")
assert meta is not None, "Missing audit_metadata in JSON"
assert meta["summary"]["total"] > 0, "No checks recorded in JSON"
assert "pass" in meta["summary"], "Missing pass count"
assert "fail" in meta["summary"], "Missing fail count"

checks = data.get("checks", [])
assert len(checks) > 0, "Checks array is empty"

required_keys = [
    "service", "host", "check", "level", "scope",
    "status", "severity", "mandatory", "observed",
    "expected", "likely_causes", "recommended_next_step",
    "automatic_fix_applied"
]

for idx, c in enumerate(checks):
    for k in required_keys:
        assert k in c, f"Check #{idx} missing key '{k}'"
    assert c["status"] in ["PASS", "FAIL", "WARN", "SKIP", "NOT_CHECKED"], f"Invalid status: {c['status']}"
    assert c["severity"] in ["P0", "P1", "P2", "P3"], f"Invalid severity: {c['severity']}"

print("  [PASS] JSON schema matches exact specification with all required keys.")
EOF

# 5. Validate Markdown Report and 16 Sections
echo "--> 5. Validating Markdown Report Structure (All 16 Sections)..."
MD_FILES=("$TEST_TMP_DIR"/*.md)
MD_FILE="${MD_FILES[0]}"
if [ -f "$MD_FILE" ]; then
  test_pass "Markdown report file created: $MD_FILE"
else
  test_fail "Markdown report" "No Markdown file found in $TEST_TMP_DIR"
fi

python3 - <<EOF
import sys

required_sections = [
    "۱. خلاصه مدیریتی",
    "۲. اطلاعات محیط و زمان اجرای تست",
    "۳. موجودی کامل سرویس‌ها",
    "۴. وضعیت سلامت هر سرویس",
    "۵. وضعیت شبکه و Firewall",
    "۶. وضعیت DNS، CDN و TLS",
    "۷. وضعیت Kubernetes و Workloadها",
    "۸. وضعیت Monitoring و Logging",
    "۹. وضعیت Backup و Storage",
    "۱۰. خطاهای طبقه‌بندی‌شده بر اساس اولویت",
    "۱۱. علل ریشه‌ای اثبات‌شده",
    "۱۲. فرضیه‌های نیازمند بررسی زنده",
    "۱۳. دستورات تشخیصی موردنیاز",
    "۱۴. اقدامات دستی موردنیاز",
    "۱۵. مواردی که به دسترسی بیشتر نیاز دارند",
    "۱۶. چک‌لیست نتیجه نهایی"
]

with open("$MD_FILE", "r", encoding="utf-8") as f:
    content = f.read()

for sec in required_sections:
    assert sec in content, f"Missing section in Markdown report: {sec}"

print("  [PASS] All 16 mandatory sections verified in Markdown report.")
EOF

# 6. Validate Secret Redaction (No passwords, tokens, or private keys leaked)
echo "--> 6. Validating Secret Redaction in Generated Reports..."
python3 - <<EOF
import os
import json
from pathlib import Path

repo_root = Path("$REPO_ROOT")
secrets_dir = repo_root / ".secrets"
raw_secrets = []

if secrets_dir.is_dir():
    for p in secrets_dir.rglob("*"):
        if p.is_file() and not p.name.endswith(".crt"):
            val = p.read_text(encoding="utf-8", errors="ignore").strip()
            if val and len(val) >= 6:
                raw_secrets.append((p.name, val))

with open("$JSON_PATH", "r") as f:
    json_text = f.read()

with open("$MD_FILE", "r") as f:
    md_text = f.read()

for sec_name, val in raw_secrets:
    assert val not in json_text, f"Secret value for '{sec_name}' was leaked in JSON report!"
    assert val not in md_text, f"Secret value for '{sec_name}' was leaked in Markdown report!"

assert "PRIVATE KEY-----" not in json_text, "Private key leaked in JSON report!"
assert "PRIVATE KEY-----" not in md_text, "Private key leaked in Markdown report!"

print("  [PASS] Zero secrets or private keys leaked in JSON or Markdown reports.")
EOF

# 7. Test Scope Filtering
echo "--> 7. Testing Scope Filtering (--scope monitoring)..."
MON_OUT_DIR=$(mktemp -d /tmp/maktab-auditor-mon.XXXXXX)
set +e
MON_JSON=$("$AUDITOR" --scope monitoring --offline --json-only --output-dir "$MON_OUT_DIR")
set -e

python3 - <<EOF
import json
with open("$MON_JSON", "r") as f:
    data = json.load(f)

checks = data.get("checks", [])
assert len(checks) > 0, "No checks under monitoring scope"
for c in checks:
    assert c["scope"] == "monitoring", f"Leaked check from other scope: {c['scope']}"

print("  [PASS] Scope filtering correctly isolated monitoring checks.")
EOF
rm -rf "$MON_OUT_DIR"

# 8. Test Host Filtering
echo "--> 8. Testing Host Filtering (--host vps1)..."
VPS1_OUT_DIR=$(mktemp -d /tmp/maktab-auditor-vps1.XXXXXX)
set +e
VPS1_JSON=$("$AUDITOR" --host vps1 --offline --json-only --output-dir "$VPS1_OUT_DIR")
set -e

python3 - <<EOF
import json
with open("$VPS1_JSON", "r") as f:
    data = json.load(f)

checks = data.get("checks", [])
assert len(checks) > 0, "No checks under vps1 host"
for c in checks:
    assert c["host"] in ["vps1", "all", "external", "control"], f"Leaked check from other host: {c['host']}"

print("  [PASS] Host filtering correctly isolated vps1 checks.")
EOF
rm -rf "$VPS1_OUT_DIR"

echo "=========================================================="
echo "    ALL AUDITOR TESTS PASSED SUCCESSFULLY (EXIT 0)        "
echo "=========================================================="
