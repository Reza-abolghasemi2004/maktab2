#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Validating Shell Scripts Syntax ==="
bash -n scripts/bootstrap-control.sh
bash -n show_tree_and_contents.sh
bash -n tests/test_syntax.sh

# Test rendering and checking backup script template
python3 -c "
import os
from jinja2 import Template
with open('roles/backup/templates/maktab-backup.sh.j2') as f:
    t = Template(f.read())
rendered = t.render({
    'backup_root': '/var/backups/maktab',
    'node_exporter_textfile_dir': '/var/lib/prometheus/node-exporter',
    'nfs_export_path': '/srv/nfs/k8s',
    'backup_keep_daily': 7,
    'backup_keep_weekly': 28,
    'backup_keep_monthly': 93,
    'backup_remote_user': 'backup',
    'worker_ip': '10.8.0.2',
    'backup_remote_dir': '/var/backups/maktab-vps1'
})
with open('/tmp/test_backup.sh', 'w') as out:
    out.write(rendered)
"
bash -n /tmp/test_backup.sh
rm -f /tmp/test_backup.sh

echo "All shell scripts passed syntax validation!"
