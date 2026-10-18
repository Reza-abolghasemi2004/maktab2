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
