# دستورالعمل جامع بازگشت به وضعیت قبلی (Comprehensive Rollback Runbook)

این مستند مراحل دقیق بازگردانی زیرساخت، سرویس‌ها، تنظیمات شبکه و فایروال را در صورت بروز هرگونه اختلال یا پس از اتمام فاز اشکال‌زدایی مستقیم تشریح می‌کند.

---

## ۱. بازگردانی وضعیت شبکه (Direct-IP Debug Mode → WireGuard Production)

هنگامی که تست‌ها و عیب‌یابی‌ها در حالت Direct-IP پایان یافته و قرار است زیرساخت به تونل امن WireGuard و DNS داخلی بازگردد:

### ۱.۱. تغییر متغیرها در `inventory/group_vars/all/main.yml`
مقادیر زیر را به حالت Production بازگردانید:
```yaml
# ───────── بازگشت به حالت امن پیش‌فرض ─────────
network_mode: wireguard
wireguard_enabled: true
private_dns_enabled: true
firewall_debug_mode: false
```

### ۱.۲. اجرای پلی‌بوک ارکستراسیون
پلی‌بوک اصلی را اجرا کنید تا تمام سرویس‌ها و بایندینگ‌ها روی اینترفیس `wg0` بازپیکربندی شوند:
```bash
ansible-playbook -i inventory/hosts.yml site.yml
```

### ۱.۳. راستی‌آزمایی بازگشت
```bash
# بررسی فعال بودن تونل و اینترفیس وایرگارد در هر دو سرور:
wg show
ip addr show wg0

# بررسی پاسخ‌دهی DNS داخلی روی VPS1:
dig +short @10.8.0.1 k8s.maktab.rezaabolghasemi.ir

# تست دسترسی K3s Agent به سرور روی IP وایرگارد:
curl -k https://10.8.0.1:6443/readyz
```

---

## ۲. بازگردانی کدهای مخزن در سطح Git (Repository Rollback)

در صورتی که تغییرات در مخزن Git نیاز به بازگشت کامل به کامیت پایه داشته باشند:
```bash
# بازگردانی به کامیت پایه پروژه:
git checkout 2a8cd76ad29bac83551dd68b58e14975efc5864b

# یا ساخت یک شاخه ترمیمی مستقل:
git checkout -b rollback/restore-baseline 2a8cd76ad29bac83551dd68b58e14975efc5864b
```

---

## ۳. بازگردانی دستی سرویس‌های K3s

در صورت بروز مشکل در اجرای خودکار پلی‌بوک و نیاز به مداخله فوری دستی:

### ۳.۱. بازگردانی K3s Server روی VPS1
```bash
# بازگرداندن فایل کانفیگ به نسخه پشتیبان یا استاندارد:
cat <<'EOF' > /etc/rancher/k3s/config.yaml
node-ip: 10.8.0.1
advertise-address: 10.8.0.1
bind-address: 0.0.0.0
tls-san:
  - 10.8.0.1
  - 81.12.50.30
  - k8s.maktab.rezaabolghasemi.ir
flannel-iface: wg0
disable:
  - traefik
  - servicelb
write-kubeconfig-mode: "0600"
EOF

# بازگرداندن دراپ‌این سیستم‌دی به وابستگی وایرگارد:
cat <<'EOF' > /etc/systemd/system/k3s.service.d/override.conf
[Unit]
After=wg-quick@wg0.service
Wants=wg-quick@wg0.service
[Service]
TimeoutStartSec=180s
EOF

systemctl daemon-reload
systemctl restart k3s.service
```

### ۳.۲. بازگردانی K3s Agent روی VPS2
```bash
cat <<'EOF' > /etc/rancher/k3s/config.yaml
server: https://10.8.0.1:6443
node-ip: 10.8.0.2
flannel-iface: wg0
EOF

cat <<'EOF' > /etc/systemd/system/k3s-agent.service.d/override.conf
[Unit]
After=wg-quick@wg0.service
Wants=wg-quick@wg0.service
[Service]
TimeoutStartSec=180s
EOF

systemctl daemon-reload
systemctl restart k3s-agent.service
```

---

## ۴. بازگردانی تنظیمات فایروال (Firewall Rollback)

در صورتی که تغییرات رول‌های UFW یا iptables باعث قطعی ارتباط یا رفتارهای غیرمنتظره شد:
```bash
# غیرفعال‌سازی موقت UFW برای بازگرداندن فوری دسترسی:
ufw disable

# حذف قوانین موقت debug از before.rules و after.rules:
sed -i '/# BEGIN MAKTAB RAW/,/# END MAKTAB RAW/d' /etc/ufw/before.rules
sed -i '/# BEGIN MAKTAB DOCKER-USER/,/# END MAKTAB DOCKER-USER/d' /etc/ufw/after.rules

# بازگردانی فایل قوانین قبل از تغییرات (در صورت وجود بکاپ):
if [ -f /etc/iptables/rules.v4.bak ]; then
    iptables-restore < /etc/iptables/rules.v4.bak
fi

# راه‌اندازی مجدد فایروال:
ufw enable
```

---

## ۵. بازگردانی کانتینرهای مانیتورینگ، ابزارهای توسعه و الستیک

### مانیتورینگ (VPS2):
```bash
cd /opt/monitoring
# بازگرداندن کانفیگ Prometheus به نسخه پیش‌فرض:
git checkout -- prometheus/prometheus.yml alertmanager/alertmanager.yml
docker compose up -d --force-recreate
```

### ابزارهای توسعه (VPS1):
```bash
cd /opt/devtools
git checkout -- docker-compose.yml
docker compose up -d --force-recreate
```

### استک لاگ (VPS2):
```bash
cd /opt/elk
git checkout -- docker-compose.yml
docker compose up -d --force-recreate
```

---

## ۶. بازگردانی پشتیبان‌های داده‌ای (Data Restore)

در صورت لزوم برای بازگردانی اطلاعات پایگاه‌های داده:

### بازگردانی دیتابیس PostgreSQL (CloudNativePG):
```bash
LATEST_SQL=$(ls -t /var/backups/maktab/daily/*/postgres.sql.gz | head -n 1)
PRIMARY_POD=$(k3s kubectl -n data get pod -l cnpg.io/cluster=pg-main,cnpg.io/instanceRole=primary -o jsonpath='{.items[0].metadata.name}')
zcat "$LATEST_SQL" | k3s kubectl -n data exec -i "$PRIMARY_POD" -c postgres -- psql -U postgres
```

### بازگردانی دیتابیس MariaDB (WordPress):
```bash
LATEST_MARIADB=$(ls -t /var/backups/maktab/daily/*/mariadb.sql.gz | head -n 1)
zcat "$LATEST_MARIADB" | k3s kubectl -n data exec -i mariadb-0 -- sh -c 'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"'
```
