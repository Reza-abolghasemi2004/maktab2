# راهنمای اقدامات با دسترسی Root روی سرورها (Root Actions Runbook)

این مستند شامل کلیه اقداماتی است که باید با دسترسی `root` روی ماشین کنترل (Laptop)، سرور لبه (VPS1) و سرور ورکر (VPS2) انجام شوند. دستورات در سه دسته **تشخیصی (Read-Only)**، **اصلاحی (Remediation)** و **تأییدی (Verification)** تدوین شده‌اند.

---

## ۱. سرور VPS1 (`81.12.50.30` / `10.8.0.1`)

### هدف:
بررسی و پاکسازی رول‌های تداخلی فایروال (مانند `ROAMINGBITES-DROP` و رول موقت `TEMP-TELEPORT-WG-DIAG`)، اعتبارسنجی لود گواهی معتبر روی پورت ۳۰۸۰ تله‌پورت، و تضمین سلامت سرویس K3s Server و Nginx.

### دستورات تشخیصی (بدون ریسک / Read-Only):
```bash
# ۱. بررسی زنجیره INPUT و رول‌های فایروال با شماره خط
iptables -L INPUT -n -v --line-numbers | head -n 30

# ۲. جستجوی رول‌های تاریخی DROP و رول‌های موقت
iptables-save -c | grep -E "ROAMINGBITES|TEMP-TELEPORT|DROP"

# ۳. بررسی فایل‌های پایدار iptables
cat /etc/iptables/rules.v4 2>/dev/null || echo "No persistent rules.v4"
grep -rn "TEMP-TELEPORT" /etc/iptables/ /etc/ufw/ 2>/dev/null || true

# ۴. بررسی وضعیت پروسس تله‌پورت و پورت‌های ۳۰۲۵ و ۳۰۸۰
systemctl status teleport --no-pager
ss -lntp | grep -E ":3025|:3080"

# ۵. بررسی گواهی ارائه‌شده روی پورت ۳۰۸۰
echo | openssl s_client -connect 10.8.0.1:3080 -servername teleport.maktab.rezaabolghasemi.ir 2>/dev/null | \
  openssl x509 -noout -subject -issuer -dates -fingerprint -sha256

# ۶. بررسی ثبت نودها در کلاستر تله‌پورت
tctl nodes ls
```

### دستورات اصلاحی (فقط در صورت وجود رول‌های ناسازگار در خروجی تشخیصی):
```bash
# الف) در صورتی که رول TEMP-TELEPORT-WG-DIAG یا ROAMINGBITES در iptables وجود دارد:
# شماره خط رول را پیدا کنید (مثلاً شماره ۲):
# iptables -L INPUT -n --line-numbers | grep "TEMP-TELEPORT"
# رول را با شماره خط آن حذف کنید:
# iptables -D INPUT <LINE_NUMBER>

# ب) در صورتی که iptables-persistent نصب است، وضعیت تمیز را ذخیره کنید:
iptables-save > /etc/iptables/rules.v4

# ج) بازخوانی و اعمال قوانین استاندارد UFW:
ufw reload
```

### دستورات تأییدی:
```bash
# بررسی پاسخگویی پورت ۳۰۸۰ تله‌پورت روی تونل
curl -k -I --connect-timeout 5 https://10.8.0.1:3080/webapi/ping

# بررسی سلامت DNS داخلی
dig +short @10.8.0.1 ns1.maktab.rezaabolghasemi.ir
```

---

## ۲. سرور VPS2 (`31.56.89.69` / `10.8.0.2`)

### هدف:
رفع وضعیت قفل شدن (Hang) سرویس `k3s-agent.service`، بررسی ارتباط تونل WireGuard به سمت سرور، و اتصال سالم Teleport Node.

### دستورات تشخیصی:
```bash
# ۱. بررسی وضعیت K3s Agent و لاگ‌های اخیر
systemctl status k3s-agent --no-pager -l
journalctl -u k3s-agent -n 50 --no-pager

# ۲. تست ارتباط شبکه WireGuard با پورت ۶۴۴۳ سرور
ping -c 3 10.8.0.1
curl -k -I --connect-timeout 5 https://10.8.0.1:6443/cacerts

# ۳. بررسی وضعیت Teleport Node
systemctl status teleport --no-pager
journalctl -u teleport -n 50 --no-pager

# ۴. بررسی CA نصب‌شده در مخزن محلی
openssl x509 -in /usr/local/share/ca-certificates/maktab-ca.crt -noout -fingerprint -sha256
```

### دستورات اصلاحی (در صورت قفل بودن K3s Agent):
```bash
# اعمال Drop-in برای وابستگی سرویس به WireGuard و رفع زمان انتظار نامحدود
mkdir -p /etc/systemd/system/k3s-agent.service.d/
cat <<'EOF' > /etc/systemd/system/k3s-agent.service.d/override.conf
[Unit]
After=wg-quick@wg0.service
Wants=wg-quick@wg0.service

[Service]
TimeoutStartSec=180s
EOF

systemctl daemon-reload
systemctl restart k3s-agent
```

### دستورات تأییدی:
```bash
systemctl is-active k3s-agent
systemctl is-active teleport
```

---

## ۳. سیستم کنترل (Control Node / Laptop)

### هدف:
آماده‌سازی پکیج‌ها و کالکشن‌های Ansible و تولید ایمن Secretها و کلیدهای PKI.

```bash
# اجرای اسکریپت آماده‌سازی ابزارهای لپ‌تاپ
./scripts/bootstrap-control.sh

# راه‌اندازی ارتباط VPN کلاینت
sudo wg-quick up .secrets/wg/maktab-vpn.conf

# بررسی ارتباط روی تونل
ping -c 2 10.8.0.1
ping -c 2 10.8.0.2
```
