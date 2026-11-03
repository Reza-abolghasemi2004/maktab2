#!/usr/bin/env python3
"""Existing registry images must not be loaded or overwritten by recovery."""
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Handler(BaseHTTPRequestHandler):
    status = 200
    def do_HEAD(self):
        self.send_response(self.status)
        self.end_headers()
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory() as tmp:
        inventory = Path(tmp) / 'hosts'
        inventory.write_text('[edge]\nlocalhost ansible_connection=local\n')
        extra = json.dumps({'registry_endpoint': '127.0.0.1:' + str(server.server_port),
                            'gitea_org': 'maktab', 'registry_user': 'test',
                            'registry_password': 'test', 'app_image_recovery_confirmed': True})
        result = subprocess.run(['python3', '-m', 'ansible.cli.playbook', '-i', str(inventory),
                                 '10-recover-app-images.yml', '-e', extra],
                                env=os.environ, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'No archives were loaded' in result.stdout, result.stdout
        assert 'changed=0' in result.stdout, result.stdout
        Handler.status = 404
        bad = subprocess.run(['python3', '-m', 'ansible.cli.playbook', '-i', str(inventory),
                              '10-recover-app-images.yml', '-e', extra],
                             env=os.environ, text=True, capture_output=True)
        assert bad.returncode != 0, bad.stdout
        assert 'Archive missing or checksum mismatch' in bad.stdout, bad.stdout
        assert 'Load approved image archives' not in bad.stdout, bad.stdout
finally:
    server.shutdown()
print('Existing tags are untouched; missing archives fail before image loading')
