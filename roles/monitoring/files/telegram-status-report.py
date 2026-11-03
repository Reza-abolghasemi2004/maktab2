#!/usr/bin/env python3
"""Send a bounded, point-in-time Prometheus summary; never log Telegram secrets."""
import datetime as dt
import json
import math
import sys
import time
import urllib.parse
import urllib.request

CONFIG = '/etc/maktab/telegram-status-report.json'
TIMEOUT = 10


def clean(value, limit=160):
    return ' '.join(str(value).split())[:limit]


def request_json(url, payload=None, proxy=True):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener() if proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=TIMEOUT) as response:
        return json.load(response)


def collect(config):
    base = config['prometheus_url'].rstrip('/')
    def get(path):
        try:
            result = request_json(base + path, proxy=False)
            if result.get('status') != 'success':
                raise ValueError('API failure')
            return result.get('data')
        except Exception:
            return None

    def query(expr):
        data = get('/api/v1/query?' + urllib.parse.urlencode({'query': expr}))
        if not isinstance(data, dict) or data.get('resultType') != 'vector':
            return None
        return data.get('result')

    return {
        'targets': get('/api/v1/targets?state=active'),
        'alerts': get('/api/v1/alerts'),
        'probes': query('probe_success'),
        'http': query('probe_http_status_code{job="blackbox_http"}'),
        'backups': query('maktab_backup_job_status'),
        'backup_times': query('maktab_backup_last_success_timestamp_seconds'),
        'cpu': query('avg by(instance) (1 - rate(node_cpu_seconds_total{mode="idle"}[5m]))'),
        'memory': query('1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes'),
        'disk': query('1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|rootfs"} / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|rootfs"}'),
    }


def values(series, keys):
    result = {}
    for row in series or []:
        try:
            key = tuple(row['metric'].get(k, '') for k in keys)
            timestamp, raw = row['value']
            value = float(raw)
            if math.isfinite(value) and time.time() - 180 <= float(timestamp) <= time.time() + 30:
                result[key] = value
        except (KeyError, TypeError, ValueError):
            continue
    return result


def render(config, data, now=None):
    now = time.time() if now is None else now
    title = dt.datetime.fromtimestamp(now).astimezone().strftime('%Y-%m-%d %H:%M %Z')
    lines = ['📊 گزارش دوره‌ای زیرساخت', 'زمان: ' + title, 'این گزارش وضعیت فعلی است، نه تاریخچهٔ دو ساعت گذشته.']
    alerts_data = data.get('alerts')
    if not isinstance(alerts_data, dict) or not isinstance(alerts_data.get('alerts'), list):
        lines += ['', '⚠️ وضعیت هشدارها نامشخص: Prometheus پاسخ نداد.']
    else:
        alerts = [a for a in alerts_data['alerts'] if a.get('state') in ('firing', 'pending')]
        alerts.sort(key=lambda a: (a.get('state') != 'firing', a.get('labels', {}).get('severity') != 'critical', a.get('labels', {}).get('alertname', '')))
        lines += ['', f'🚨 هشدارهای فعال یا در انتظار: {len(alerts)}']
        if not alerts:
            lines.append('هیچ هشدار firing یا pending گزارش نشده است.')
        for a in alerts[:25]:
            labels = a.get('labels', {})
            state = 'فعال' if a.get('state') == 'firing' else 'در انتظار'
            lines.append(f"• {state} | {clean(labels.get('severity', 'نامشخص'), 20)} | {clean(labels.get('alertname', '?'), 80)} | {clean(labels.get('instance', labels.get('host', '')), 100)}")
            summary = clean(a.get('annotations', {}).get('summary', ''), 180)
            if summary:
                lines.append('  ' + summary)
        if len(alerts) > 25:
            lines.append(f'… {len(alerts)-25} هشدار دیگر؛ جزئیات در Prometheus.')

    targets_data = data.get('targets')
    if not isinstance(targets_data, dict) or not isinstance(targets_data.get('activeTargets'), list):
        lines += ['', '⚠️ وضعیت scrape targetها نامشخص است.']
    else:
        targets = targets_data['activeTargets']
        lines += ['', f'📡 دریافت متریک: {sum(t.get("health") == "up" for t in targets)}/{len(targets)} target در وضعیت up']
        if not targets:
            lines.append('⚠️ هیچ target فعالی گزارش نشد؛ سلامت نامشخص است.')
        for t in targets:
            if t.get('health') != 'up':
                labels = t.get('labels', {})
                lines.append(f"⚠️ {clean(labels.get('job', '?'), 50)} | {clean(labels.get('instance', '?'), 100)} | {clean(t.get('lastError', ''), 140)}")

    lines += ['', '🌐 سرویس‌ها (بر اساس probe، نه سلامت کامل برنامه):']
    probes = values(data.get('probes'), ('job', 'instance'))
    statuses = values(data.get('http'), ('job', 'instance'))
    for job, target in config.get('expected_probes', []):
        val = probes.get((job, target))
        state = '✅ در دسترس' if val == 1 else '❌ ناموفق' if val == 0 else '⚠️ نامشخص'
        code = statuses.get((job, target))
        suffix = f' | HTTP {int(code)}' if code is not None else ''
        lines.append(f'{state} | {clean(target, 130)}{suffix}')
    if not config.get('expected_probes'):
        lines.append('⚠️ هیچ probe موردانتظاری تنظیم نشده است.')

    lines += ['', '💾 بکاپ‌ها (آخرین اجرای ثبت‌شده، بازیابی تست نشده):']
    jobs = values(data.get('backups'), ('job_name',))
    stamps = values(data.get('backup_times'), ('job_name',))
    for name in config.get('backup_jobs', []):
        status, stamp = jobs.get((name,)), stamps.get((name,))
        age = (now - stamp) / 3600 if stamp is not None and 0 < stamp <= now else None
        state = '❌ ناموفق' if status == 0 else '⚠️ قدیمی' if status == 1 and age is not None and age > 26 else '✅ موفق' if status == 1 and age is not None else '⚠️ نامشخص'
        lines.append(f'{state} | {clean(name, 50)} | ' + (f'{age:.1f} ساعت پیش' if age is not None else 'زمان نامشخص'))

    lines += ['', '🖥 منابع نودها (آخرین متریک):']
    cpu, memory, disk = (values(data.get(name), ('instance',)) for name in ('cpu', 'memory', 'disk'))
    for node in config.get('nodes', []):
        key = (node['instance'],)
        def pct(item):
            v = item.get(key)
            return f'{v*100:.0f}%' if v is not None and 0 <= v <= 1 else 'نامشخص'
        lines.append(f"• {clean(node['name'], 40)} | CPU {pct(cpu)} | RAM {pct(memory)} | دیسک / {pct(disk)}")
    return '\n'.join(lines)


def chunks(message, limit=3500, max_chunks=10):
    # Telegram's limit is measured in UTF-16 code units, not Python characters.
    size = lambda text: len(text.encode('utf-16-le')) // 2
    result, current = [], ''
    for line in message.splitlines():
        line = line[:1000]
        candidate = current + ('\n' if current else '') + line
        if size(candidate) > limit:
            result.append(current)
            current = line
        else:
            current = candidate
        if len(result) >= max_chunks - 1:
            current += '\n… گزارش طولانی است؛ جزئیات را در Prometheus ببینید.'
            break
    if current:
        result.append(current)
    return result


def main():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            config = json.load(f)
        message = render(config, collect(config))
        for part in chunks(message):
            response = request_json('https://api.telegram.org/bot' + config['bot_token'] + '/sendMessage',
                                    {'chat_id': config['chat_id'], 'text': part, 'disable_web_page_preview': True})
            if not response.get('ok'):
                raise RuntimeError('Telegram rejected request')
        print('Periodic Telegram status report sent.')
        return 0
    except Exception as exc:
        # Exceptions may contain the Telegram URL/token: never print their text.
        print('Periodic Telegram report failed (' + type(exc).__name__ + '). Check connectivity and credentials locally.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
