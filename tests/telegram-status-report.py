#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import time
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('report', 'roles/monitoring/files/telegram-status-report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)

class ReporterTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.config = {'expected_probes': [['blackbox_http', 'https://app.example'], ['blackbox_tcp_k8s', 'db:5432']],
                       'backup_jobs': ['postgres', 'mariadb'], 'nodes': [{'name': 'vps1', 'instance': '10.8.0.1:9100'}]}
        def sample(labels, value): return {'metric': labels, 'value': [self.now, str(value)]}
        self.sample = sample
        self.data = {
            'alerts': {'alerts': [{'state': 'firing', 'labels': {'alertname': 'ServiceDown', 'severity': 'critical', 'instance': 'db:5432'}, 'annotations': {'summary': 'DB down'}}]},
            'targets': {'activeTargets': [{'health': 'up'}, {'health': 'down', 'labels': {'job': 'node', 'instance': 'vps2'}, 'lastError': 'timeout'}]},
            'probes': [sample({'job': 'blackbox_http', 'instance': 'https://app.example'}, 1), sample({'job': 'blackbox_tcp_k8s', 'instance': 'db:5432'}, 0)],
            'http': [sample({'job': 'blackbox_http', 'instance': 'https://app.example'}, 200)],
            'backups': [sample({'job_name': 'postgres'}, 1), sample({'job_name': 'mariadb'}, 0)],
            'backup_times': [sample({'job_name': 'postgres'}, self.now - 3600), sample({'job_name': 'mariadb'}, self.now - 90000)],
            'cpu': [sample({'instance': '10.8.0.1:9100'}, .25)], 'memory': [sample({'instance': '10.8.0.1:9100'}, .6)], 'disk': [],
        }

    def test_states_alerts_and_resources(self):
        text = report.render(self.config, self.data, self.now)
        for phrase in ('ServiceDown', 'DB down', '✅ در دسترس', '❌ ناموفق', 'HTTP 200', 'postgres', '1.0 ساعت', 'CPU 25%', 'RAM 60%', 'دیسک / نامشخص', 'timeout'):
            self.assertIn(phrase, text)

    def test_missing_is_never_healthy(self):
        text = report.render(self.config, {}, self.now)
        self.assertIn('هشدارها نامشخص', text)
        self.assertIn('⚠️ نامشخص', text)
        self.assertNotIn('✅ در دسترس', text)
        self.assertNotIn('✅ موفق', text)

    def test_stale_and_failed_backups(self):
        self.data['backup_times'][0]['value'][1] = str(self.now - 100000)
        text = report.render(self.config, self.data, self.now)
        self.assertIn('⚠️ قدیمی | postgres', text)
        self.assertIn('❌ ناموفق | mariadb', text)

    def test_chunk_limits_count_utf16(self):
        pieces = report.chunks('\n'.join(['😀' * 300] * 100))
        self.assertLessEqual(len(pieces), 10)
        self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 3500 for p in pieces))
        self.assertIn('گزارش طولانی', pieces[-1])

    def test_unreachable_prometheus_is_reported_as_unknown(self):
        with mock.patch.object(report, 'request_json', side_effect=TimeoutError):
            data = report.collect({'prometheus_url': 'http://127.0.0.1:9090'})
        text = report.render(self.config, data, self.now)
        self.assertIn('هشدارها نامشخص', text)
        self.assertIn('⚠️ نامشخص', text)

    def test_telegram_payload_is_plain_text(self):
        payload = {'bot_token': 'private-token', 'chat_id': 123, **self.config}
        with mock.patch('builtins.open', mock.mock_open(read_data=__import__('json').dumps(payload))), \
             mock.patch.object(report, 'collect', return_value=self.data), \
             mock.patch.object(report, 'request_json', return_value={'ok': True}) as send, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.main(), 0)
            args = send.call_args.args
            self.assertEqual(args[1]['chat_id'], 123)
            self.assertNotIn('parse_mode', args[1])
            self.assertIn('ServiceDown', args[1]['text'])

    def test_exception_does_not_leak_token(self):
        with mock.patch('builtins.open', side_effect=RuntimeError('secret-token')), contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(report.main(), 1)
            self.assertNotIn('secret-token', stderr.getvalue())

if __name__ == '__main__': unittest.main()
