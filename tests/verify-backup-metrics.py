#!/usr/bin/env python3
"""Verify successful, failed, and stale backup metrics are distinguished."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
import yaml
import jinja2

plays = yaml.safe_load(Path('08-verify.yml').read_text())
task = next(t for t in plays[1]['tasks'] if t.get('name') == 'Verify last backup run recorded all successful backup jobs')
script = jinja2.Template(task['ansible.builtin.shell']).render(node_exporter_textfile_dir='/unused', verify_backup_max_age_seconds=93600)
with tempfile.TemporaryDirectory() as tmp:
    metrics = Path(tmp) / 'maktab_backup.prom'
    script = script.replace('/unused/maktab_backup.prom', str(metrics))
    now = int(time.time())
    def run(stale=False, failed=False):
        lines = []
        for i in range(8):
            stamp = now - (100000 if stale and i == 0 else 100)
            lines += [f'maktab_backup_job_status{{job_name="job{i}"}} {0 if failed and i == 0 else 1}',
                      f'maktab_backup_last_success_timestamp_seconds{{job_name="job{i}"}} {stamp}']
        metrics.write_text('\n'.join(lines) + '\n')
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    assert run().returncode == 0
    assert run(stale=True).returncode == 1
    assert run(failed=True).returncode == 1
print('Backup status and freshness checks passed')
