#!/usr/bin/env python3
"""Exercise the actual rendered backup setup twice against hard-linked snapshots."""
from pathlib import Path
import os
import subprocess
import tempfile
import jinja2

source = Path('roles/backup/templates/maktab-backup.sh.j2').read_text()
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp) / 'backup'
    original = root / 'daily' / '2026-11-01' / 'data'
    original.parent.mkdir(parents=True)
    original.write_text('preserve me')
    weekly = root / 'weekly' / 'existing' / 'data'
    weekly.parent.mkdir(parents=True)
    os.link(original, weekly)
    rendered = jinja2.Template(source).render(
        backup_root=root, node_exporter_textfile_dir=temp,
        nfs_export_path='/tmp/example', backup_keep_daily=7,
        backup_keep_weekly=30, backup_keep_monthly=365,
        backup_remote_user='backup', worker_ip='127.0.0.1', backup_remote_dir='/tmp/x',
    )
    subprocess.run(['bash', '-n'], input=rendered, text=True, check=True)
    setup = rendered.split('TMP=$(mktemp)', 1)[0]
    command = setup + 'printf "%s\\n" "$DEST"\nprintf replacement > "$DEST/data"\n'
    first = subprocess.check_output(['bash'], input=command, text=True).strip()
    second = subprocess.check_output(['bash'], input=command, text=True).strip()
    assert first != second
    assert original.read_text() == weekly.read_text() == 'preserve me'
    assert Path(first, 'data').read_text() == Path(second, 'data').read_text() == 'replacement'
print('Repeated runs preserve existing hard-linked snapshots')
