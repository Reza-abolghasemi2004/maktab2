# Maktab Sharif – SRS DevOps Project (Ansible)

## منابع و نقش‌ها

| ماشین | مشخصات | نقش |
|---|---|---|
| لپ‌تاپ | 4 core / 8 GB | Ansible control node، کلاینت VPN (10.8.0.10)، kubectl |
| **vps1** `81.12.50.30` (wg 10.8.0.1) | 3 core / 6 GB | VPN hub، DNS خصوصی، Teleport (PAM)، nginx edge، k3s server، NFS، Gitea + Registry + CI runner، ArgoCD، Backup |
| **vps2** `31.56.89.69` (wg 10.8.0.2) | 3 core / 6 GB | k3s agent، Prometheus/Alertmanager/Grafana/Blackbox، ELK، مقصد بکاپ، replica ‌PostgreSQL |

مانیتورینگ عمداً روی نودی جدا از edge/control-plane است تا با افتادن vps1 هم هشدار ارسال شود.

```
Internet ─ 22/80/443/51820 ─► vps1 (ufw: deny all else)
                 WireGuard 10.8.0.0/24  (vps1 hub ⇄ vps2 ⇄ laptop)
  همه‌ی سرویس‌های داخلی، k3s (flannel روی wg0)، NFS، ELK، Prometheus فقط روی تونل
  *.maktab.internal ← bind9 روی 10.8.0.1 + گواهی CA خصوصی
```

## اجرا

```bash
./scripts/bootstrap-control.sh                 # یک‌بار روی لپ‌تاپ
# ویرایش: inventory/group_vars/all/main.yml  (public_domain, ...)
#         inventory/group_vars/all/monitoring.yml (telegram/email/slack)
ansible-playbook site.yml                      # همه‌چیز
ansible-playbook 02-firewall.yml               # یا مرحله‌به‌مرحله
```
بعد از `03-access.yml`:
```bash
sudo wg-quick up .secrets/wg/maktab-vpn.conf   # اتصال VPN
export KUBECONFIG=$PWD/.secrets/kubeconfig     # kubectl از طریق VPN
```
رمزها خودکار در `.secrets/` ساخته می‌شوند (commit نکنید). لینک دعوت Teleport: `/root/teleport-admin-invite.txt` روی vps1. رمز Gitea/Grafana: `.secrets/*_password`.

## نگاشت به SRS

| بند | پیاده‌سازی |
|---|---|
| 1. VM | `01` : `common` (پکیج‌ها، swap، sysctl، SSH hardening، fail2ban)، کاربر `viewer` (بدون sudo، گروه adm/systemd-journal)، `docker`، `ansible_control` |
| 2. Firewall | `02` : ufw؛ فقط SSH/HTTP/HTTPS/VPN باز؛ رنج‌های Docker/Pod/Service/VPN مورد اعتماد؛ دور زدن ufw توسط Docker و NodePort با DOCKER-USER و raw/PREROUTING بسته شده |
| 3. دسترسی | `03` : bind9 (`maktab.internal`)، WireGuard routed، Teleport فقط روی VPN با دامنه‌ی خصوصی |
| 4. Kubernetes | `04` : k3s دو نود، NFS (StorageClass `nfs-client` RWX)، NetworkPolicy (default-deny ورودی + allow صریح) |
| 5. اپلیکیشن | `05` : Gitea + Registry خصوصی + runner، CI → build/push → تغییر تگ در repo `gitops` → ArgoCD؛ CloudNativePG (۲ instance روی دو نود)؛ Redis؛ WordPress پیش‌فرض + MariaDB؛ cache فایل‌های استاتیک در nginx |
| 6. Monitoring | `06` : Alertmanager (Telegram/Email/Slack)، VM resources (RAM/CPU/IOPS/Network/Storage)، status code و انقضای گواهی، uptime PostgreSQL/Redis، kube-state-metrics، ELK، بکاپ‌ها، داشبورد Nginx (50 درخواست برتر، cache status، req/time) در Grafana |
| 7. Backup | `07` : postgres، mariadb، gitea، فایل‌های WordPress، registry، k3s state، configs؛ نگهداری روزانه 7 / هفتگی 4 / ماهانه 3؛ کپی offsite به vps2؛ متریک‌ها و alert |

## نکات و محدودیت‌ها

- فرض: Ubuntu 24.04 روی هر دو VPS و دسترسی root با SSH key.
- **RAM محدود (6GB)**: heap الاستیک ۷۶۸MB و Logstash ۳۸۴MB تنظیم شده؛ هر VPS ‏2GB swap دارد. در صورت فشار، Logstash را حذف و Filebeat را مستقیم به Elasticsearch وصل کنید.
- WordPress با PostgreSQL کار نمی‌کند، پس MariaDB جدا در namespace `data` دارد؛ PostgreSQL برای backend است.
- دامنه‌ی عمومی (`public_domain`) باید A record به `81.12.50.30` داشته باشد؛ با `letsencrypt_enabled: true` گواهی عمومی گرفته می‌شود، وگرنه گواهی CA خصوصی استفاده می‌شود.
- Registry و Gitea روی HTTP داخل تونل WireGuard (رمزنگاری‌شده) هستند.
- NetworkPolicy ورودی را محدود می‌کند؛ egress محدود نشده. در `allow-edge-to-web` به‌خاطر SNAT ‏NodePort رنج pod هم مجاز است.
- seed ریپوها فقط یک‌بار انجام می‌شود؛ بعد از آن مانیفست‌ها را از طریق Git تغییر دهید.
- نسخه‌ها (Teleport، Argo، k3s، …) در `group_vars/all/main.yml` است و اجرای واقعی روی سرور را باید خودتان تست کنید؛ من فقط syntax را بررسی کرده‌ام.
- گواهی wildcard داخلی ۸۲۵ روزه است؛ قبل از انقضا با حذف `.secrets/pki/wildcard.*` و اجرای `03-access.yml` تمدید کنید.

## پاک‌سازی سرورها (09-backtofirst)

`09-backtofirst.yml` جدا از `site.yml` است و اجرای آن **مخرب و غیرقابل بازگشت** است: سرویس‌های پروژه، کلاستر k3s و داده‌های محلی آن، Composeهای پروژه و داده‌های Gitea، Registry، مانیتورینگ و ELK حذف می‌شوند. قبل از اجرا بکاپ مستقل بگیرید و دسترسی کنسول ارائه‌دهنده را آماده کنید. روی هر سرور با آدرس عمومی و کلید SSH فعلی یک اتصال مستقل را امتحان کنید؛ از VPN، Teleport یا اتصال local برای اجرای آن استفاده نکنید. playbook سرورها را یکی‌یکی پردازش می‌کند:

```bash
ansible-playbook 09-backtofirst.yml -e backtofirst_confirm=true
# برای یک سرور: ... --limit vps1
```

این بازنشانی کارخانه‌ای سیستم‌عامل نیست: SSH و کلیدهای مجاز و سخت‌سازی SSH حفظ می‌شوند و سرویس SSH بررسی و فعال می‌شود. UFW غیرفعال می‌شود (قوانین موجود آن باقی می‌مانند و بلوک‌های پروژه حذف می‌شوند)، بنابراین تا تنظیم مجدد فایروال، سرور در معرض شبکه است؛ فایروال ارائه‌دهنده و سایر فایروال‌ها توسط این playbook تغییر نمی‌کنند و دسترسی بیرونی را نمی‌توان تضمین کرد. پکیج‌ها، Docker و کانتینرهای غیرپروژه، تنظیمات بازنویسی‌شده عمومی nginx و bind، sysctl، swap، hostname، timezone و کاربران دست‌نخورده می‌مانند؛ برای بازیابی دقیق وضعیت قبلی باید از بکاپ یا نصب مجدد سیستم‌عامل استفاده کرد. داده‌های NFS (`nfs_export_path`)، بکاپ‌های محلی و offsite و `.secrets` روی کنترل‌نود عمداً نگه داشته می‌شوند و باید پس از بررسی جداگانه پاک شوند. اجرای مجدد فقط در صورتی ایمن است که مسیرهای ثابت پروژه برای کاربرد دیگری استفاده نشده باشند. uninstall رسمی k3s ممکن است تنظیمات شبکه مرتبط با k3s را نیز حذف کند.

## اجرای مجدد و بررسی استقرار

- `control` در inventory محل اجرای Ansible است؛ اگر از vps1 اجرا می‌کنید، `laptop` به همان سیستم محلی اشاره دارد. تغییر فایل کلاینت VPN نباید سرویس `wg-quick@wg0` این میزبان را ری‌استارت کند. فایل `.secrets/wg/maktab-vpn.conf` برای کلاینت جداگانه است؛ آن را روی خود hub بالا نیاورید. فایل `.secrets` را قبل از تغییر یا استقرار مجدد بکاپ و با دسترسی محدود نگهداری کنید.
- در خروجی قبلی کلیدهای CA و wildcard تازه ایجاد شده‌اند. اگر فایل گواهی و کلید جفت نباشند، استقرار PKI متوقف می‌شود؛ کلید و گواهی منطبق را از بکاپ بازیابی کنید. تعویض CA نیاز به بازتوزیع اعتماد به همه کلاینت‌ها دارد. به‌ویژه از کپی کردن جداگانهٔ گواهی‌های قدیمی کنار کلیدهای جدید خودداری کنید.
- **هشدار امنیتی:** فایل‌های `.secrets` در تاریخچه و نسخه فعلی Git وجود دارند. آن‌ها را افشاشده فرض کنید: کلید CA، گواهی‌ها، توکن‌ها و رمزها را با برنامهٔ چرخش امن عوض کنید؛ حذف از آخرین commit به‌تنهایی تاریخچه را پاک نمی‌کند. رمزها و کلیدهای واقعی را در خروجی عیب‌یابی منتشر نکنید.
- تنظیم واقعی کانال هشدار در `inventory/group_vars/all/monitoring.yml` و DNS عمومی و گواهی معتبر برای دامنه‌های عمومی پیش‌نیاز است؛ مقادیر پیش‌فرض `CHANGE_ME` اعلان عملیاتی نیستند. با `letsencrypt_enabled: false` گواهی داخلی wildcard برای دامنه عمومی معتبر نیست.
- پس از تنظیم پیش‌نیازها `ansible-playbook site.yml` را از ابتدا اجرا کنید؛ در خطا خروجی نام task و پیام خطا (بدون رمزها) را بررسی کنید. بعد از تکمیل، `ansible-playbook 08-verify.yml` را اجرا کنید. وضعیت واقعی CI، رسیدن اعلان، تهیه و بازیابی بکاپ و دسترسی از کلاینت بیرونی باید جداگانه آزمایش شود؛ صرف موفقیت syntax تضمین سلامت سرویس‌ها نیست.

### رفع اشکال Alertmanager

کانتینر Alertmanager با UID/GID ‏65534 اجرا می‌شود و کانفیگ با دسترسی `root:65534` و `0640` نصب می‌شود. اگر اطلاعات کانال اعلان هنوز تنظیم نشده باشد، یک receiver بدون مقصد فعال می‌شود تا سرویس بالا بیاید، اما **هیچ اعلانی ارسال نمی‌شود** و verify همچنان تنظیمات اعلان را بررسی می‌کند. توکن و chat ID معتبر یا تنظیمات واقعی email/Slack را با استفاده از Ansible Vault تنظیم و `ansible-playbook 06-monitoring.yml` را مجدداً اجرا کنید. اجرای موفق سرویس جایگزین آزمایش دریافت واقعی اعلان نیست.

در صورت عدم آمادگی، لاگ `docker logs --tail 100 alertmanager` را روی نود monitoring بررسی کنید. قبل از ارسال لاگ یا فایل پیکربندی به دیگران، توکن‌ها و اطلاعات حساس را حذف کنید.

### ارتباط نود Teleport

Proxy در حالت listener جداگانه از `10.8.0.1:3080` برای وب و از `10.8.0.1:3024` برای reverse tunnel استفاده می‌کند؛ هر دو باید فقط از شبکه VPN در دسترس باشند. پس از تغییرات `03-access.yml` اجرا و ثبت نودهای worker بررسی می‌شود. اگر ثبت نشد، وضعیت WireGuard، `ss -lnt` روی hub و `journalctl -u teleport` روی هر دو نود را بررسی کنید؛ داده‌های Teleport را بدون بکاپ پاک نکنید.

### تصویر kube-state-metrics

اگر `registry.k8s.io` در سرور قابل دسترسی نیست، بعد از بررسی اصالت و دسترس‌پذیری mirror روی هر دو نود، متغیر `kube_state_metrics_image` را در یک فایل متغیر محلی تنظیم کنید و با `-e @/path/to/file.yml` به همه اجراهای بعدی `04-kubernetes.yml` یا `site.yml` بدهید. نمونهٔ مقدار: `mirror.example/kube-state-metrics/kube-state-metrics:v2.13.0` (نشانی نمونه است). تغییر متغیر پس از اجرای مجدد مرحله 04 اعمال می‌شود؛ صرف pull کردن تصویر در یک نود Deployment را تغییر نمی‌دهد. Mirror شخص ثالث را از نظر اعتماد و digest بررسی کنید.
