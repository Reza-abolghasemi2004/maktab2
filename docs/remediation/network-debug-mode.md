# معماری حالت اشکال‌زدایی مبتنی بر IP مستقیم (Direct-IP Debug Mode)

این مستند معماری، پیاده‌سازی و نحوه بهره‌برداری از حالت اشکال‌زدایی مبتنی بر IP مستقیم (`direct_ip`) را در زیرساخت DevOps مکتب۲ تشریح می‌کند. این قابلیت به تیم عملیات اجازه می‌دهد بدون وابستگی به تونل WireGuard و سرویس DNS داخلی (BIND9)، ارتباط مستقیم و ایزوله بین سرورها را برقرار، عیب‌یابی و آزمایش کنند.

---

## ۱. چرایی و اهداف (Motivation & Objectives)

در معماری اولیه زیرساخت، تمامی سرویس‌های بین‌سروری (Inter-VPS) به تونل WireGuard با رنج شبکه `10.8.0.0/24` و نام‌های دامنه محلی `*.maktab.rezaabolghasemi.ir` روی BIND9 وابسته بودند. در سناریوهایی که:
1. سرویس WireGuard به دلیل فیلترینگ ترافیک UDP یا ناسازگاری لایسنس و کرنل دچار قطعی می‌شود،
2. سرویس DNS محلی به دلیل توقف نود یا عدم دسترسی به پورت ۵۳ دچار تاخیر یا قطعی می‌شود،
3. سیستم ارکستراسیون K3s به دلیل عدم بالا آمدن اینترفیس `wg0` در حلقه خطا و Restart قرار می‌گیرد،

زیرساخت به بن‌بست فنی برخورد می‌کرد. **Direct-IP Debug Mode** این زنجیره وابستگی بحرانی را قطع کرده و ارتباطات را با کنترل دقیق فایروال به صورت مستقیم روی آدرس‌های عمومی VPS1 (`81.12.50.30`) و VPS2 (`31.56.89.69`) هدایت می‌کند.

---

## ۲. متغیرهای ساختاریافته در `group_vars/all/main.yml`

تمامی متغیرهای شبکه، فایروال و کوبرنتیز به شکل صریح و یکپارچه در `inventory/group_vars/all/main.yml` تعریف شده‌اند:

```yaml
# ───────── حالت شبکه و عیب‌یابی ─────────
network_mode: direct_ip            # مقادیر مجاز: 'direct_ip' یا 'wireguard'
wireguard_enabled: false           # فعال/غیرفعال بودن رول و سرویس WireGuard
private_dns_enabled: false         # فعال/غیرفعال بودن رول و سرور BIND9 محلی
firewall_debug_mode: true          # باز کردن ترافیک کنترل‌شده دوطرفه بین VPSها
firewall_debug_scope: inter_vps    # دامنه دسترسی عیب‌یابی (فقط بین دو سرور)
k3s_enabled: true                  # فعال‌سازی K3s

# نگاشت خودکار آدرس‌ها و اینترفیس‌ها بر اساس network_mode:
vps1_public_ip: "81.12.50.30"
vps2_public_ip: "31.56.89.69"

hub_ip: "{{ vps1_public_ip if network_mode == 'direct_ip' else hostvars['vps1'].wg_ip }}"
worker_ip: "{{ vps2_public_ip if network_mode == 'direct_ip' else hostvars['vps2'].wg_ip }}"

node_service_ip: "{{ ansible_host if network_mode == 'direct_ip' else wg_ip }}"
cluster_iface: "{{ public_iface if network_mode == 'direct_ip' else 'wg0' }}"
```

---

## ۳. جدول نگاشت سرویس‌ها و پورت‌های ارتباطی

| نام سرویس | نود میزبان | نود مبدا / کلاینت | آدرس در حالت WireGuard | آدرس در حالت Direct-IP | پورت(ها) | پروتکل |
|:---|:---|:---|:---|:---|:---|:---|
| **K3s Server (Control Plane)** | VPS1 | VPS2 (Agent) | `https://10.8.0.1:6443` | `https://81.12.50.30:6443` | 6443 | TCP / HTTPS |
| **K3s Flannel CNI** | VPS1 & VPS2 | دوطرفه | روی اینترفیس `wg0` | روی اینترفیس `eth0` | 8472 | UDP (VXLAN) |
| **K3s Kubelet Probes** | VPS1 & VPS2 | دوطرفه | `10.8.0.1` / `10.8.0.2` | `81.12.50.30` / `31.56.89.69` | 10250 | TCP |
| **Teleport Auth Service** | VPS1 | VPS2 (Node) | `10.8.0.1:3025` | `81.12.50.30:3025` | 3025 | TCP |
| **Teleport Proxy Service** | VPS1 | کاربر / ادمین | `10.8.0.1:3080` | `81.12.50.30:3080` | 3080 | TCP / HTTPS |
| **NFS Share (`/srv/nfs/k8s`)** | VPS1 | VPS2 (K3s PVs) | `10.8.0.1:2049` | `81.12.50.30:2049` | 2049, 111 | TCP/UDP |
| **Gitea Web & Git** | VPS1 | کاربر / Runner / ArgoCD | `10.8.0.1:3000` | `81.12.50.30:3000` | 3000, 2222 | TCP / HTTP, SSH |
| **Docker Registry** | VPS1 | VPS2 (K3s containerd) | `10.8.0.1:5000` | `81.12.50.30:5000` | 5000 | TCP / HTTP |
| **Prometheus Server** | VPS2 | نود مانیتورینگ | `10.8.0.2:9090` | `127.0.0.1:9090` / `31.56.89.69:9090` | 9090 | TCP / HTTP |
| **Alertmanager** | VPS2 | Prometheus | `10.8.0.2:9093` | `127.0.0.1:9093` | 9093 | TCP / HTTP |
| **Grafana Dashboard** | VPS2 | ادمین / مانیتورینگ | `10.8.0.2:3001` | `31.56.89.69:3001` | 3001 | TCP / HTTP |
| **Node Exporter (VPS1)** | VPS1 | Prometheus (VPS2) | `10.8.0.1:9100` | `81.12.50.30:9100` | 9100 | TCP / HTTP |
| **Node Exporter (VPS2)** | VPS2 | Prometheus (VPS2) | `10.8.0.2:9100` | `127.0.0.1:9100` | 9100 | TCP / HTTP |
| **Elasticsearch** | VPS2 | Logstash / Kibana | `10.8.0.2:9200` | `127.0.0.1:9200` | 9200 | TCP / HTTP |
| **Logstash Beats** | VPS2 | Filebeat (VPS1) | `10.8.0.2:5044` | `31.56.89.69:5044` | 5044 | TCP |
| **Kibana UI** | VPS2 | ادمین | `10.8.0.2:5601` | `31.56.89.69:5601` | 5601 | TCP / HTTP |

---

## ۴. جریان اجرای پلی‌بوک‌ها و بای‌پس سرویس‌ها

پلی‌بوک‌های `site.yml` و به طور خاص `03-access.yml` به گونه‌ای اصلاح شده‌اند که وقتی `wireguard_enabled: false` یا `private_dns_enabled: false` است:
1. وظایف نصب پکیج‌ها، تولید کلیدها و کانفیگ کلاینت‌ها بدون خطا حفظ می‌شوند.
2. وظیفه استارت سرویس‌های `wg-quick@wg0` و `bind9` به طور خودکار `skip` می‌شوند.
3. در صورت فعال بودن سرویس از قبل، سرویس‌ها متوقف و غیرفعال (`state: stopped`, `enabled: false`) می‌گردند تا پورت‌های ۵۳ و ۵۱۸۲۰ آزاد شوند.
4. وابستگی واحدهای systemd برای `k3s.service`، `k3s-agent.service` و `teleport.service` به صورت پویا از `wg-quick@wg0.service` به `network-online.target` تغییر می‌کند.

---

## ۵. امنیت و کنترل ترافیک عمومی

در حالت Direct-IP، ترافیک میان‌سروری روی اینترنت عمومی مسیریابی می‌شود، اما پورت‌های حساس (مانند NFS 2049، K3s API 6443، NodePort 30000-32767، Node Exporter 9100 و Logstash 5044) هرگز به روی عموم اینترنت باز نمی‌شوند:
- **فایروال UFW:** تنها بسته‌های ورودی از آدرس مجاز سرور مقابل پذیرفته می‌شوند (`from {{ hostvars[peer].ansible_host }}`).
- **جدول RAW (PREROUTING):** بسته‌های NodePort که قصد دور زدن فایروال را دارند، ابتدا برای IP سرور مقابل `ACCEPT` و برای بقیه آدرس‌های عمومی فوراً `DROP` می‌شوند.
- **زنجیره DOCKER-USER:** بسته‌های هدایت‌شده به سمت کانتینرهای داکر (پورت‌های پابلیش‌شده) تنها از مبدا سرور مقابل مجاز بوده و ترافیک عمومی اینترنت `DROP` می‌شود.

---

## ۶. نحوه تغییر وضعیت و سوئیچ بین حالت‌ها

### رفتن به حالت Direct-IP Debug Mode:
در فایل `inventory/group_vars/all/main.yml`:
```yaml
network_mode: direct_ip
wireguard_enabled: false
private_dns_enabled: false
firewall_debug_mode: true
```
اجرای پلی‌بوک:
```bash
ansible-playbook -i inventory/hosts.yml site.yml
```

### بازگشت به حالت WireGuard Production Mode:
در فایل `inventory/group_vars/all/main.yml`:
```yaml
network_mode: wireguard
wireguard_enabled: true
private_dns_enabled: true
firewall_debug_mode: false
```
اجرای پلی‌بوک:
```bash
ansible-playbook -i inventory/hosts.yml site.yml
```
