# مستند فنی، عملیاتی و راهنمای دفاع پروژه DevOps مکتب‌شریف

> **نسخه و دامنه:** این مستند بر اساس فایل‌های مخزن در شاخهٔ `arena/11c66ba7-maktab2` تا کامیت `c56d51e` و خروجی‌هایی است که اپراتور در این جلسه ارائه کرده است. تنظیمات واقعی محلی، وضعیت زمان اجرا و مقادیر Vault ممکن است با نسخهٔ Git متفاوت باشند. تاریخ هر مشاهده در بخش رخدادها آمده است؛ این سند گزارش پایش لحظه‌ای نیست. مقادیر رمز، کلید و token عمداً درج نشده‌اند.
>
> **قاعدهٔ دفاع:** «در کد تعریف شده»، «در آزمایش مشاهده شد» و «واقعاً end-to-end تست شد» یکسان نیستند. ادعاهای اثبات‌نشده را به‌صورت محدودیت بیان کنید.

## ۱. خلاصهٔ اجرایی و نقشهٔ معماری

پروژه دو VPS و یک کنترل‌نود Ansible دارد. vps1 نقش hub شبکهٔ خصوصی، ورودی وب، DNS، رجیستری، Git و k3s server را دارد؛ vps2 نقش worker Kubernetes و میزبان مانیتورینگ، ELK و مقصد بکاپ را دارد. ارتباط بین نودها در WireGuard انجام می‌شود. دسترسی عمومی به وب‌سایت‌ها از Nginx و دسترسی به ابزارهای خصوصی از VPN و DNS خصوصی در نظر گرفته شده است.

```text
کاربر اینترنت ─HTTPS─> vps1/Nginx ─NodePort─> frontend/backend یا WordPress
                              │                     │
                              │               PostgreSQL / Redis / MariaDB
کاربر خصوصی ─WireGuard─> 10.8.0.1 ─DNS/HTTPS─> Gitea, Argo CD, Grafana, ...
                              │
                       k3s server ─── WireGuard ─── k3s agent (vps2)
                              │                         │
                       NFS + registry           Prometheus/Alertmanager/ELK
                              └──────── بکاپ با rsync ──> vps2
```

| ماشین / گروه inventory | وظایف اصلی | آدرس‌های نمونهٔ همین استقرار |
|---|---|---|
| `laptop` در `control` | اجرای Ansible، فایل‌های محرمانه و کلاینت VPN؛ در این جلسه `rezaserver` کنترل‌نود بود | VPN `10.8.0.10` |
| `vps1`: `edge`, `k3s_server` | WireGuard hub، BIND، Teleport auth/proxy/node، Nginx، NFS، k3s server، Gitea، registry، runner، بکاپ | عمومی `81.12.50.30`، VPN `10.8.0.1` |
| `vps2`: `worker`, `k3s_agent`, `monitoring`, `elk` | worker، سرویس‌های نظارت و لاگ، مقصد بکاپ، Teleport node | عمومی `31.56.89.69`، VPN `10.8.0.2` |

آدرس‌ها و گروه‌ها از `inventory/hosts.yml` می‌آیند. IP عمومی و کلیدهای SSH را هنگام تغییر محیط در inventory بازبینی کنید. یک control-plane واحد و NFS تکی به معنی نبود HA کامل زیرساخت است؛ وجود دو نود و یک replica دیتابیس به‌تنهایی کل سامانه را HA نمی‌کند.

## ۲. نگاشت به SRS و وضعیت شواهد

منبع نیازمندی، فایل HTML ارسالی `Maktab-Sharif-SRS-DevOps-Project.html` است. وضعیت‌های زیر فقط بر اساس کد و آخرین خروجی‌های ارائه‌شده‌اند.

| نیازمندی | محل پیاده‌سازی | شواهد/محدودیت |
|---|---|---|
| آماده‌سازی VM، ابزارها، viewer، Ansible | `01-prepare-vm.yml`، roles `common`, `docker`, `ansible_control` | سرویس‌های پایه در یک اجرای ۰۸ سالم گزارش شدند؛ آزمون همهٔ قابلیت‌های viewer ارائه نشده است. |
| فایروال و شبکه‌های خصوصی/عمومی | `02-firewall.yml`، `roles/firewall`، host vars | UFW فعال گزارش شد؛ تست نفوذ مستقل و اثبات همهٔ مسیرهای IPv4/IPv6 ارائه نشده است. |
| DNS خصوصی، VPN مسیریابی‌شده، PAM | `03-access.yml`، `dns`, `wireguard`, `teleport`, `pki` | DNS، handshake نودها و ثبت vps2 در Teleport دیده شد. handshake و DNS کنترل‌نود هم دیده شد؛ ورود کامل کاربر جدید/OTP هنوز اثبات نشده است. |
| Kubernetes، NFS و NetworkPolicy | `04-kubernetes.yml`، `k3s`, `nfs`, `k8s_platform` | هر دو Node Ready، NFS provisioner Running، PVCها Bound و تست نوشتن NFS در اجرای پیشین موفق؛ آزمون جامع محدودسازی policy انجام نشده است. |
| backend/frontend، CI/CD، GitOps، Git و registry خصوصی | `05-platform.yml`، `devtools`, `gitops` | Podها Running، مخازن و API در یک بررسی سالم؛ ایمیج‌ها دستی بازیابی شدند. موفقیت workflow CI و رفع `OutOfSync` MariaDB هنوز تأیید نشده است. |
| PostgreSQL cluster و WordPress پیش‌فرض با cache استاتیک Nginx | GitOps app templates، `edge_nginx` | دو PostgreSQL Pod، MariaDB و WordPress Running بودند؛ صحت دیتای قبلی، failover واقعی، WordPress از بیرون و cache HIT تست end-to-end نشده است. |
| مانیتورینگ، alert، منابع VM، دامنه، گواهی، دیتابیس، Kubernetes، ELK، backup | `06-monitoring.yml`، `roles/monitoring`, `node_exporter`, `elk`, `filebeat` | endpointهای Prometheus، Alertmanager، Grafana و Elasticsearch و ingest آزمایشی در یک اجرای پیشین موفق؛ دریافت هشدار واقعی Telegram مشاهده شده. دریافت گزارش دو‌ساعته هنوز تأیید نشده. |
| نمایش ترافیک Nginx، ۵۰ مورد، cache، زمان و تعداد | `roles/monitoring/files/nginx-traffic.json` و Logstash | dashboard تعریف شده؛ درستی همهٔ پنل‌ها در UI و queryهای Grafana مستقلاً اثبات نشده است. |
| بکاپ، پایش و retention | `07-backup.yml`, `roles/backup` | متریک و journal اجرای ۳ نوامبر success نشان دادند؛ restore مستقل انجام نشده و offsite را نباید بکاپ مستقل غیرقابل‌حذف فرض کرد. |

## ۳. فایل‌های کلیدی ریشه و ترتیب اجرا

### مفاهیم Ansible برای دفاع

- **Inventory** مشخص می‌کند هر host در چه گروه‌هایی است؛ roleها با `when` یا group انتخاب می‌شوند. `inventory/host_vars` override مختص host دارد. `inventory/group_vars/all` برای همهٔ میزبان‌هاست. متغیر extra-vars با `-e` اولویت بالاتری از inventory و role defaults دارد.
- **Playbook** چند play با میزبان و role مشخص است؛ **role** مجموعهٔ tasks، defaults، templates، files و handlers است. **Jinja2** قالب را با متغیرهای محیط به فایل/manifest قابل اجرا تبدیل می‌کند.
- **Handler** در پاسخ به `notify` اجرا می‌شود؛ `flush_handlers` اجرا را تا قبل از تست readiness جلو می‌اندازد. بسیاری از taskها idempotent هستند، اما اجرای مجدد الزاماً بدون اثر یا بدون restart نیست؛ `kubectl apply --force-conflicts` و auto-sync می‌توانند منابع را تغییر دهند.
- `no_log` احتمال افشای مقدار را در خروجی Ansible کاهش می‌دهد، اما جایگزین Vault، محدودسازی دسترسی و چرخش credential نیست.

| فایل | وظیفه / اثر مهم |
|---|---|
| `ansible.cfg` | inventory پیش‌فرض، `roles_path`، host-key checking در پروژه، pipelining و forks. تنظیم مستقل `/etc/ansible/ansible.cfg` که role `ansible_control` روی vps1 می‌سازد host-key checking را غیرفعال می‌کند؛ این دو را اشتباه نگیرید. |
| `requirements.yml` | مجموعه‌های `ansible.posix`, `community.general`, `community.docker`, `community.crypto`, `kubernetes.core`. |
| `scripts/bootstrap-control.sh` | نصب پیش‌نیازهای Debian/Ubuntu روی کنترل‌نود، ایجاد SSH key در صورت فقدان، نصب collections؛ دستورهای نمونهٔ `ssh-copy-id` باید با کلید/host واقعی سنجیده شوند. |
| `00-secrets.yml` | تولید یا بارگذاری secretهای نام‌برده در متغیر `secret_names` در `.secrets`؛ تولید مجدد بدون نگهداری فایل‌های قبلی می‌تواند اعتبارنامه‌ها را ناسازگار کند. |
| `01-prepare-vm.yml` | نقش‌های `common` و `docker` روی VPSها و `ansible_control` روی edge. |
| `02-firewall.yml` | اجرای نقش `firewall` روی VPSها؛ ممکن است شبکه/SSH را قطع کند. |
| `03-access.yml` | CA و WireGuard، DNS و Teleport، سپس تست tunnel و ثبت worker. |
| `04-kubernetes.yml` | NFS، نصب k3s server و agent، namespaces، secrets، policy، provisioner، CNPG، metrics و Argo CD. |
| `05-platform.yml` | Gitea، registry، runner، seed اولیهٔ مخازن و Application، Nginx edge. |
| `06-monitoring.yml` | node exporter، ELK، Filebeat، Prometheus/Alertmanager/Grafana/Blackbox و گزارش دوره‌ای تلگرام. |
| `07-backup.yml` | key و حساب مقصد، اسکریپت و timer بکاپ. خود role timer را فعال می‌کند. |
| `08-verify.yml` | سنجش پس از استقرار؛ تنظیم سرویس یا اجرای backup نیست؛ marker موقت NFS و request ساختگی لاگ می‌سازد. با خطای assertion زودتر از مراحل بعدی متوقف می‌شود. |
| `09-backtofirst.yml` | cleanup مستقل و **مخرب**، نه factory reset؛ فقط با تأیید و SSH عمومی مستقل، `serial: 1`؛ هرگز داخل `site.yml` نیست. |
| `10-recover-app-images.yml` | بازیابی صریح و اختیاری archiveهای تأییدشده به registry؛ checksum و تگ را بررسی می‌کند و در بررسی اولیه تگ موجود را بازنویسی نمی‌کند. توقف CI هنگام بازیابی لازم است؛ این بررسی اتمی نیست. |
| `site.yml` | import مراحل ۰۰ تا ۰۷؛ ۰۸ کامنت است و ۰۹ و ۱۰ اجرا نمی‌شوند. اجرای مجدد ممکن است تنظیمات را اعمال یا سرویس را restart کند. |
| `k3s-server-only.yml` / `pki-vps1.yml` | playbookهای محدود برای k3s server یا توزیع PKI روی vps1؛ وابستگی‌ها و متغیرها همچنان لازم‌اند. |
| `show_tree_and_contents.sh` | ابزار نمایش ساختار و محتوا. اجرای بدون فیلتر می‌تواند secretهای track‌شده یا محلی را افشا کند؛ خروجی خام آن را عمومی نکنید. |
| `README.md` | راهنمای اجمالی؛ در موارد اختلاف، کد و وضعیت واقعی محیط را بررسی کنید. |

نمونهٔ اجرای کنترل‌شده از `~/maktab2`:

```bash
git status --short
ansible-playbook 04-kubernetes.yml --ask-vault-pass
ansible-playbook 08-verify.yml --ask-vault-pass
```

قبل از هر `git pull`، تغییرات محلی را بررسی کنید؛ قبل از اجرای `site.yml` یا ۰۲/۰۳/۰۴/۰۵/۰۷، اثر بر شبکه، certificate، workload و retention را ارزیابی کنید. از `git reset --hard` روی کنترل‌نود حاوی تنظیمات و secret استفاده نکنید. `git add .` می‌تواند فایل‌های حساس track‌شده را stage کند.

## ۴. تنظیمات، شبکه و امنیت

### ۴.۱ دامنه‌ها، پورت‌ها و مرزهای اعتماد

`inventory/group_vars/all/main.yml` در نسخهٔ مخزن `private_domain=maktab.rezaabolghasemi.ir`، `public_domain=rezaabolghasemi.ir`، شبکهٔ WG `10.8.0.0/24`، Pod CIDR `10.42.0.0/16` و Service CIDR `10.43.0.0/16` را تعریف می‌کند. این مقادیر ممکن است با override محیط تغییر کرده باشند.

| مسیر | پورت/مقصد | توضیح |
|---|---|---|
| اینترنت به vps1 | TCP `22,80,443`، UDP `51820` | مطابق host vars؛ SSH با UFW limit. |
| اینترنت به vps2 | TCP `22` | host vars پیش‌فرض vps2. |
| DNS خصوصی | `10.8.0.1:53` | BIND فقط localhost و WG؛ forwarderها طبق inventory. |
| VPN | `81.12.50.30:51820/UDP` | hub-and-spoke، peerهای hub با `/32`؛ کلاینت‌ها AllowedIPs برابر شبکهٔ WG دارند. |
| Teleport | `10.8.0.1:3080` وب/proxy، `3025` auth، `3024` reverse tunnel | در تنظیمات VPN-only؛ OTP برای local authentication تعریف شده است. |
| k3s API | `10.8.0.1:6443` | agent و kubeconfig کنترل‌نود از آن استفاده می‌کنند. |
| Gitea / registry | `10.8.0.1:3000` / `:5000` | HTTP داخلی روی مسیر VPN؛ registry از Basic Auth استفاده می‌کند. |
| node exporter | `10.8.0.1:9100`, `10.8.0.2:9100` | فقط روی VPN IP. |
| وب ابزار خصوصی | `*.maktab.rezaabolghasemi.ir:443` | Nginx روی WG IP برای Gitea، Argo CD، Grafana، Prometheus، Alertmanager و Kibana. Teleport در ۳۰۸۰ است. |
| ابزار worker | `3001` Grafana، `9090` Prometheus، `9093` Alertmanager، `9200` Elasticsearch، `5044` Logstash، `5601` Kibana، `9114` ES exporter | دسترسی/احراز هویت و firewall باید در محیط واقعی جداگانه تست شوند. |
| NodePortها | WordPress `30080`، frontend `30081`، backend `30082`، KSM `30085`، Argo `30090`، blackbox `30115` | Nginx یا Prometheus از مسیر خصوصی استفاده می‌کنند؛ raw/PREROUTING برای drop روی public interface تعریف شده است. |

فایروال UFW ورودی پیش‌فرض را deny و outbound/routed را allow می‌کند. قانون `DOCKER-USER` برای اتصال forwarded جدید از interface عمومی و قانون raw برای NodePort TCP/UDP به‌منظور کاهش bypass توسط Docker/kube-proxy هستند. لیست interfaceها و رفتار واقعی ruleset بستگی به محیط و backend iptables دارد. `AllowedIPs` در WireGuard هم route و هم محدودهٔ مجاز peer است؛ به تنهایی policy کامل لایهٔ برنامه نیست.

### ۴.۲ DNS، WireGuard و CA

- فایل WG روی سرورها `/etc/wireguard/wg0.conf` و روی کنترل‌نود `.secrets/wg/maktab-vpn.conf` ساخته می‌شود. private key را نباید به چت یا Git فرستاد. روی hub، IP هر peer `/32` ثبت می‌شود؛ استفادهٔ هم‌زمان از یک کلید/IP در دو دستگاه موجب جابه‌جایی endpoint و اختلال می‌شود.
- BIND از `roles/dns/templates/zone.j2` رکوردها را تولید می‌کند. کنترل‌نود Linux از `resolvectl` برای split DNS دامنهٔ خصوصی استفاده می‌کند؛ ممکن است شبکه یا DNS-over-HTTPS مرورگر نیاز به تنظیم جداگانه داشته باشد.
- `roles/pki` CA خصوصی و wildcard می‌سازد و روی سرورها certificate/key را توزیع می‌کند. کلیدهای CA، TLS و WireGuard حساس‌اند. اعتماد به CA خصوصی در دستگاه مشتری قدرت اعتباردهی گسترده می‌دهد؛ fingerprint را از مسیر قابل اعتماد مقایسه کنید. CA کلید خصوصی را هرگز انتقال ندهید.
- `letsencrypt_enabled` در **نسخهٔ مخزن false** است؛ اپراتور در محیط خود آن را فعال کرد و دریافت certificate و بررسی نام/اعتبار زمانی موفق گزارش شد. این به معنی تأیید خودکار دسترسی بیرونی یا تمدید آتی نیست. certbot در زمان صدور اولیه و hookهای renewal ممکن است Nginx را موقت متوقف کند.
- registry/Gitea داخلی از HTTP با Basic Auth در مسیر VPN استفاده می‌کنند؛ امنیت به شبکهٔ رمزگذاری‌شده و محدودسازی دسترسی متکی است. در مواردی مثل درخواست خود hub به IP خودش، الزاماً ترافیک داخل tunnel نیست. برای محیط عملیاتی TLS معتبر، مدیریت هویت و جداسازی مناسب پیشنهاد می‌شود.

### ۴.۳ اتصال ویندوز به VPN

روش ثبت‌شده در جلسه: نصب WireGuard for Windows؛ انتقال امن فایل VPN کنترل‌نود و **فقط certificate عمومی** `ca.crt`؛ حذف `PostUp` و `PostDown` مختص Linux از فایل کپی‌شده و افزودن `DNS = 10.8.0.1` در `[Interface]`؛ قبل از فعال‌سازی ویندوز، غیرفعال‌کردن همان peer روی کنترل‌نود از طریق اتصال مستقل. کلیدها و Endpoint و AllowedIPs را بدون دلیل تغییر ندهید. handshake و `nslookup argocd.maktab.rezaabolghasemi.ir 10.8.0.1` باید تست شوند. برای کار هم‌زمان، peer جدید با کلید و IP متفاوت روی hub لازم است. نصب CA در Windows Current User Trusted Root فقط پس از مقایسهٔ fingerprint و با پذیرش ریسک انجام شود. **اتصال و ورود ویندوز در خروجی‌های جلسه تأیید نشده است.**

### ۴.۴ امنیت و بدهی‌های موجود

1. تعدادی فایل `.secrets` در تاریخچهٔ Git track شده‌اند. `.gitignore` جدید مانع افزودن تصادفی فایل جدید است، اما فایل track‌شده یا تاریخچه را حذف نمی‌کند. بررسی سطح دسترسی مخزن و چرخش هماهنگ secretها ضروری است؛ بازنویسی تاریخچه بدون برنامه و هماهنگی انجام نشود.
2. token تلگرام قبلاً در گفتگو افشا شد؛ تأیید چرخش آن ارائه نشده است. از BotFather revoke و از Vault برای مقدار جدید استفاده شود. لینک دعوت Teleport قبلاً افشا شد؛ اعتبار/لغو آن باید جداگانه بررسی شود.
3. Kubernetes Secret در `data` فقط base64 است، رمزنگاری محسوب نمی‌شود؛ دسترسی RBAC و encryption-at-rest جداگانه باید ارزیابی شود. فایل‌های بکاپ configs نیز حاوی secret و کلید هستند.
4. NFS با `no_root_squash` و مسیر mode `0777` و Elasticsearch با `xpack.security.enabled=false` پیاده شده‌اند؛ صرف private بودن VPN ریسک‌های آن‌ها را صفر نمی‌کند. این‌ها محدودیت‌های امنیتی، نه توصیهٔ عمومی production هستند.
5. `kubectl` روی vps2 بدون kubeconfig به `localhost:8080` fallback کرد؛ این نشان‌دهندهٔ خرابی کلاستر نیست. استفادهٔ ترجیحی روی vps1 با `k3s kubectl` است. kubeconfig کنترل‌نود دارای credential است و باید محافظت شود.

## ۵. Kubernetes، Storage و GitOps

### ۵.۱ k3s و networking

k3s نسخهٔ `v1.30.5+k3s1` در inventory ثبت شده است. server روی VPN IP advertise می‌کند، SAN شامل IP و دامنهٔ خصوصی است و agent به `https://10.8.0.1:6443` می‌پیوندد. `flannel-iface: wg0` ترافیک inter-node را روی WG می‌برد. Traefik و ServiceLB غیرفعال‌اند؛ Nginx edge از NodePort استفاده می‌کند. kubelet منابع سیستمی را reserve و آستانهٔ eviction حافظه را تنظیم می‌کند. فایل `registries.yaml` مسیر HTTP registry و اعتبارنامهٔ containerd را تنظیم می‌کند؛ از چاپ آن خودداری کنید.

Namespaces اصلی: `apps`, `data`, `monitoring`, `argocd`، به‌علاوهٔ `cnpg-system` و `kube-system`. `roles/k8s_platform/templates/netpol.yml.j2` default-deny **ingress** برای apps/data/monitoring دارد و مجوزهای مشخصی برای وب، backend→PostgreSQL/Redis، WordPress→MariaDB، CNPG و blackbox می‌دهد. این معادل default-deny egress نیست؛ آدرس‌های probe نودها در template ثابت‌اند و هنگام تغییر CIDR باید بررسی شوند.

### ۵.۲ منابع persistent و دیتابیس‌ها

| workload | نوع و تعداد | storage / ارتباط |
|---|---|---|
| PostgreSQL `pg-main` | CloudNativePG، دو instance و anti-affinity اجباری، یک primary و یک replica | هر instance PVC `5Gi` و `local-path`؛ سرویس `pg-main-rw` برای نوشتن. HA/failover واقعی باید تست شود و local-path یک storage مشترک نیست. |
| MariaDB | StatefulSet، یک replica | PVC `3Gi local-path`، دیتابیس WordPress؛ `mariadb-0`. |
| Redis | Deployment یک replica | requirepass و maxmemory/LRU؛ template هیچ PVC پایداری برای Redis تعیین نمی‌کند. |
| WordPress | image استاندارد `wordpress:6.6-apache`، یک replica | PVC `5Gi RWX` از `nfs-client` روی `/var/www/html`؛ به MariaDB وصل می‌شود. |
| NFS provisioner | Deployment در `kube-system` | NFS server روی vps1، StorageClass `nfs-client` با `Retain`, `archiveOnDelete=true` و قابلیت expansion در manifest؛ عمل واقعی expansion را باید تست کرد. |
| frontend/backend | هرکدام دو replica | image registry خصوصی؛ frontend پورت ۸۰، backend ۸۰۸۰. `/healthz` backend فقط `ok` می‌دهد و سلامت PostgreSQL/Redis را به‌تنهایی ثابت نمی‌کند. |

Nginx برای فایل‌های استاتیک WordPress cache با `max_size=1g`, `inactive=7d` و TTLهای جداگانه دارد؛ مسیرهای پویا cache نمی‌شوند. header `X-Cache-Status` امکان مشاهدهٔ MISS/HIT را می‌دهد. `/api/` به backend و بقیهٔ درخواست‌های app به frontend فرستاده می‌شوند. تابع `/api/ping` در کد seed روی PostgreSQL جدول/رکورد می‌نویسد و شمارندهٔ Redis را تغییر می‌دهد؛ آن را یک تست **دارای اثر روی داده** بدانید.

### ۵.۳ Git، Registry، CI و Argo CD

`devtools`، Gitea و Docker Registry و act_runner را با Compose اجرا می‌کند. `gitops` سه مخزن `gitops`, `backend`, `frontend` را فقط در seed اولیه پر می‌کند؛ بعد از آن توسعه‌دهنده/CI مالک مخزن است و تغییر template در Ansible، مخزن Gitea موجود را الزاماً به‌روز نمی‌کند. marker `.seeding-<repo>` برای بازگشت از seed ناقص استفاده می‌شود.

workflowهای seed به‌ازای push روی `main` image را با تگ commit کوتاه و `latest` build/push می‌کنند، سپس فایل image در GitOps را با tag جدید تغییر می‌دهند. Argo CD application `apps` مخزن خصوصی را با `ServerSideApply=true`، `automated`, `prune` و `selfHeal` دنبال می‌کند. **prune می‌تواند منابع حذف‌شده از Git را حذف کند.** runner ثبت‌شده بودن یا task دریافت‌کردن به معنی موفقیت workflow نیست؛ خروجی این جلسه موفقیت CI را اثبات نکرد.

در بازیابی این جلسه، archiveهای backend/frontend تأییدشده توسط اپراتور به registry منتشر شدند. هر image هم `latest` و هم `recovery-20261021` گرفت؛ تگ فعلی GitOps در مشاهدهٔ ارائه‌شده `latest` بود، نه digest pin. digest منتشرشدهٔ backend برابر `sha256:02cbc04eb366057720af0d480ac32010b93be3480869416e34cc63966b24032a` و frontend برابر `sha256:b72ce385bbbd71e31143e33a25b7e4988dc2811df929290e76adb7691ae392b1` گزارش شد. این مقادیر مربوط به همان push هستند؛ ممکن است registry در آینده تغییر کند. `latest` mutable است، archiveها commit قابل‌انتسابِ تأییدشده ندارند و جایگزین CI سالم نیستند. قبل از تغییر به digest، سازگاری workflow با قالب image را اصلاح و تست کنید.

`inventory/group_vars/all/zz-image-mirrors.yml` برای KSM، NFS provisioner و Argo CD از mirror شخص ثالث استفاده می‌کند. موفقیت pull نشان‌دهندهٔ دسترس‌پذیری است، نه اصالت یا تطابق digest با upstream. image config ID خروجی `crictl` با manifest digest همیشه مستقیماً قابل مقایسه نیست. overrideهای `-e @/root/maktab-images.yml` اولویت بیشتری دارند و می‌توانند مقدار inventory را عوض کنند.

## ۶. Monitoring، اعلان و لاگ

### ۶.۱ اجزا و جریان

Prometheus هر ۳۰ ثانیه scrape/evaluate می‌کند و دادهٔ محلی آن ۱۵ روز نگهداری می‌شود. targetها شامل node exporter، kube-state-metrics، Elasticsearch exporter، خود Prometheus/Alertmanager و blackbox هستند. blackbox روی vps2 برای HTTP و TCP میزبان و blackbox داخل کلاستر برای TCP دیتابیس‌ها استفاده می‌شود. `up=1` برای exporter با `probe_success=1` برای سرویس هدف متفاوت است.

Alertmanager هشدارها را گروه‌بندی می‌کند (`group_wait=30s`, `group_interval=5m`, repeat پیش‌فرض ۴ ساعت و critical یک ساعت) و resolved را هم می‌فرستد. کانال‌ها Telegram/email/Slack هستند؛ وقتی credential معتبر تنظیم نشده، receiver عمداً no-op است و هشداری تحویل نمی‌شود. وصول پیام Telegram در این جلسه مشاهده شد؛ این به معنی تست همهٔ کانال‌ها نیست.

| نمونه rule | شرط و مدت | اهمیت |
|---|---|---|
| `NodeDown` | `up{job="node"} == 0` برای ۲ دقیقه | critical |
| `HighCPU` | بالای ۸۵٪ برای ۱۰ دقیقه | warning |
| `HighMemory` | بالای ۹۰٪ برای ۱۰ دقیقه | warning |
| `DiskSpaceLow/Critical` | فضای آزاد زیر ۱۵٪/۵٪ برای ۱۰/۵ دقیقه | warning/critical |
| `DomainDown/DomainBadStatusCode` | probe ناموفق یا HTTP ≥ 400 برای ۳ دقیقه | critical |
| `CertExpiringSoon/Critical` | کمتر از ۱۴/۳ روز با شرط زمانی rule | warning/critical |
| `ServiceDown` | TCP probe ناموفق ۲ دقیقه | critical؛ فقط TCP است، نه query کاربردی دیتابیس |
| `KubePodCrashLooping`, `KubePodNotRunning`, replica mismatch, PVC pending | threshold و `for` در `alerts.yml` | warning |
| `ElasticsearchRed/Yellow` | وضعیت cluster برای ۲/۲۰ دقیقه | critical/warning |
| `BackupJobFailed`, `BackupTooOld`, `BackupMetricsMissing` | status صفر، سن بیش از ۲۶ ساعت یا فقدان متریک | critical؛ موفقیت متریک اثبات restore نیست. |

فهرست کامل، query دقیق و thresholdها منبع حقیقت در `roles/monitoring/files/alerts.yml` است. Grafana سه dashboard از تعریف panelهای VM/platform و فایل `nginx-traffic.json` فراهم می‌کند.

### ۶.۲ گزارش دوره‌ای تلگرام

از کامیت `c56d51e`، با کانال Telegram و credential معتبر، `06-monitoring.yml` روی vps2 یک timer و service نصب می‌کند. دورهٔ پیش‌فرض `7200` ثانیه است؛ `telegram_status_report_enabled` و `telegram_status_report_interval_seconds` قابل override هستند. سرویس از API Prometheus وضعیت فعلی firing/pending، scrape targetها، probeهای موردانتظار، وضعیت/سن هشت job بکاپ و درصد CPU/RAM/دیسک ریشهٔ دو نود را می‌گیرد. مقادیر گمشده/نامعتبر «نامشخص» هستند؛ پیام طولانی با محدودیت اندازه چندبخشی یا خلاصه می‌شود. این سیستم مدل هوش مصنوعی، تحلیل روند یا گزارش رخدادهای resolved در دو ساعت گذشته نیست.

- secret در `/etc/maktab/telegram-status-report.json` با mode `0600` روی monitoring است، محتوای آن نباید چاپ/ارسال شود.
- failure اتصال Telegram در systemd ثبت می‌شود؛ اگر Telegram در دسترس نباشد، ممکن است هیچ پیام سلامت نرسد. `08-verify` فعال‌بودن timer را در صورت پیکربندی بررسی می‌کند، نه دریافت پیام.
- در خروجی ارائه‌شده ۰۶ بدون خطا تمام شد و `list-timers` اجرای قبلی و زمان بعدی را نشان داد، ولی **دریافت واقعی گزارش دو‌ساعته تأیید نشده است**.

```bash
# روی کنترل‌نود؛ ارسال پیام واقعی و شروع دوبارهٔ فاصلهٔ timer
ansible vps2 -b --ask-vault-pass -m command -a 'systemctl start maktab-telegram-report.service'
ansible vps2 -b --ask-vault-pass -m command -a 'systemctl show maktab-telegram-report.service -p Result -p ExecMainStatus'
ansible vps2 -b --ask-vault-pass -m command -a 'systemctl list-timers --all maktab-telegram-report.timer'
```

### ۶.۳ مسیر لاگ و dashboard

Nginx روی vps1 access log ساختاریافته تولید می‌کند. Filebeat روی هر دو سرور syslog/auth و روی edge access log را به Logstash `10.8.0.2:5044` می‌فرستد؛ Logstash JSON را parse، زمان و upstream/cache status را نرمال و به Elasticsearch با indexهای `nginx-*` / `syslog-*` ارسال می‌کند. ILM با حذف پس از ۱۴ روز تعریف شده است. Elasticsearch تک‌نود است و replica index در template صفر است. Grafana پنل top 50 بر اساس تعداد URI با آخرین status/cache و میانگین upstream time، پنل last 50 raw، نمودار cache status، request per time و status code دارد. لاگ‌ها ممکن است URI یا اطلاعات حساس داشته باشند.

## ۷. بکاپ، retention و بازیابی

`07-backup.yml` کلید SSH اختصاصی روی hub، کاربر مقصد روی worker و محدودیت authorized key بر اساس IP hub را تنظیم می‌کند. systemd timer روزانه حدود ساعت ۰۲:۳۰ با `RandomizedDelaySec=10m` اجرا می‌شود. فایل script و تنظیمات را پیش از اجرای دستی ببینید.

| job | روش | محدودیت مهم |
|---|---|---|
| postgres | پیدا کردن primary از label CNPG و `pg_dumpall` داخل container، gzip | موفقیت dump صحت دادهٔ مورد انتظار یا PITR را اثبات نمی‌کند. |
| mariadb | `mariadb-dump --all-databases --single-transaction` داخل Pod و gzip | باید صحت SQL و سازگاری بازیابی بررسی شود. |
| gitea | `gitea dump` و copy از container | صحت و سازگاری نسخهٔ بازیابی نشده است. |
| wordpress | tar مسیر NFS | فایل‌ها جدا از دیتابیس MariaDB هستند. |
| registry | tar `/srv/registry` شامل داده/auth | snapshot هنگام نوشتن هم‌زمان الزاماً سازگار نیست. |
| k3s_state | SQLite `.backup` و gzip | روی ساختار datastore فعلی وابسته است، restore کلاستر تست نشده است. |
| configs | tar پیکربندی‌ها و `/opt` | حاوی اطلاعات محرمانه؛ محافظت و رمزگذاری ضروری است. |
| offsite_rsync | rsync روی SSH به vps2 | `--delete` حذف در مقصد را نیز منعکس می‌کند؛ مقصد مستقلِ immutable نیست. |

اسکریپت جدید برای هر بار اجرا مسیر daily یکتا و lock می‌سازد تا اجرای مجدد فایل hard-linked قدیمی را truncate نکند. snapshotهای weekly/monthly با hard link از اولین اجرای بدون شکست jobهای محلی در روز مربوط ساخته می‌شوند و اگر مقصد موجود باشد جایگزین نمی‌شوند. `find -mtime` برای پاکسازی local بر اساس مقادیر پیش‌فرض ۷/۲۸/۹۳ روز است؛ این اعداد روزند، نه تعداد کپی. `tar` با کد ۱ به‌عنوان قابل قبول تلقی می‌شود، بنابراین سازگاری حین تغییر داده باید به‌طور جداگانه ارزیابی شود. `rsync --delete` می‌تواند فایل‌های مقصد را حذف کند. وجود backup مستقلِ جدا از این چرخه و تست restore ایزوله ضروری است.

**شواهد ۳ نوامبر:** journal اجرای روزانه را موفق گزارش کرد و متریک همهٔ هشت job مقدار `1` داشت؛ dump PostgreSQL حدود ۱۷۵۱ بایت و MariaDB حدود ۸۹۵۴۶۸ بایت بود. اندازهٔ کوچک یا status موفق برای اطمینان از وجود داده‌های مورد انتظار کافی نیست. قبل‌تر dumpهای نوامبر ۱ در daily/weekly/monthly سه hard link داشتند. اجرای نسخهٔ جدید script روی VPS پس از `ae56c05` به‌صورت مستقل تأیید نشده است.

## ۸. مستند رخدادها، عیب‌یابی و اصلاحات

| مسئله و نشانه | علت/شواهد | اقدام و نتیجه | وضعیت |
|---|---|---|---|
| خطای cleanup در probe واحدهای systemd | شرط loop و unitهای not-found | `1e121c1`, `98a23df`: جمع‌آوری نتیجهٔ هر unit و تست fake systemctl | تست محلی موفق؛ cleanup مخرب است و لزوماً reset کارخانه نیست. |
| مشکلات WireGuard/control، BIND، CA، بکاپ و seed پس از قطع اجرا | handler اشتباه روی control، service اشتباه، ناسازگاری certificate/key و seed ناقص | `da1acd2`: اصلاح handler، بررسی PKI، marker seed و verification | بخش‌هایی با خروجی کاربر تأیید شدند؛ هر deployment واقعی جداست. |
| Alertmanager فعال نماند و Nginx 502 داد | permission فایل config و UID کانتینر؛ تنظیم ناقص receiver | `158e8d3`: UID/permissions، no-op receiver در نبود credential، readiness | ۰۶ و readiness موفق؛ اعلان Telegram بعدها دریافت شد. |
| Teleport worker ثبت نشده | reverse tunnel روی `10.8.0.1:3024` دسترس‌پذیر نبود | `e38f362`: separate listener و بررسی tunnel | `tctl nodes ls` هر دو نود را نشان داد؛ ورود کامل کاربر مستقل اثبات نشده. |
| hostname certificate عمومی مطابقت نداشت | certificate فعلی شامل نام‌های عمومی نبود | اپراتور Let’s Encrypt را محلی فعال و ۰۵ را اجرا کرد | hostname/validity موفق؛ renew و دسترسی بیرونی جداگانه لازم است. |
| KSM `ImagePullBackOff` و Prometheus target down | pull upstream `registry.k8s.io` در یک تست 403 | `76b7eba` متغیر image و mirror قابل override؛ mirror دستی روی هر دو نود pull شد | target در اجرای بعدی سالم؛ اصالت mirror ثابت نشده. |
| Argo CD و NFS provisioner در pull backoff | registry اصلی در آن شرایط موفق نبود؛ علت شبکه‌ای دقیق رویداد اولیه معلوم نبود | `8ac5718` override imageها؛ `e43cb89` inventory mirror و حذف محدود Pod قدیمی گیرکرده | mirror pull موفق؛ NFS و Argo بعداً Running. |
| application-controller Pod قدیمی تغییر نکرد | StatefulSet image جدید داشت، Pod قدیمی با image قبلی آماده نبود | حذف عادی همان Pod توسط اپراتور؛ controller آن را ساخت | rollout موفق؛ بعد از آن GitOps منابع را ایجاد کرد. |
| backend/frontend در pull backoff | لاگ registry پس از authentication پاسخ `404 manifest unknown` برای `latest` نشان داد؛ HTTPS fallback خطای نهایی گمراه‌کننده بود | archiveهای تأییدشدهٔ اپراتور load/push شدند؛ `10-recover-app-images.yml` برای بازیابی opt-in بعدی | rollout هر دو Deployment موفق؛ CI واقعی هنوز تست نشده است. |
| هشدارهای TCP دیتابیس و بکاپ قدیمی/ناموفق | پیش از فعال‌شدن controller، Podهای MariaDB و primary PostgreSQL وجود نداشتند | پس از شروع GitOps دیتابیس‌ها Running شدند؛ اجرای روزانهٔ ۳ نوامبر متریک موفق داشت | restore و دادهٔ قبلی تأیید نشده‌اند. |
| ریسک بازنویسی نسخه‌های backup با hard link | نوامبر ۱ دارای link count ۳ در daily/weekly/monthly بود | `ae56c05`: پوشهٔ یکتای هر اجرا، lock و حفظ snapshot موجود | تست محلی دارد؛ نصب script جدید روی VPS باید بررسی شود. |
| Argo `OutOfSync / Healthy` و sync مکرر MariaDB | `kubectl diff` فقط حذف label ردیابی را نشان داد؛ علت اصلی diff Argo هنوز معلوم نیست | درخواست بررسی Diff در UI | **باز**؛ به‌صورت حدسی ignore نشده است. |
| `kubectl` روی vps2 به localhost:8080 وصل نشد | kubeconfig پیش‌فرض worker وجود نداشت | اجرای `k3s kubectl` روی vps1 یا استفادهٔ امن از kubeconfig مجاز | کلاستر از vps1 هر دو Node را Ready نشان داد. |
| گزارش منظم Telegram وجود نداشت | Alertmanager فقط هنگام event اعلان می‌دهد | `c56d51e`: گزارش وضعیت فعلی و timer دو‌ساعته | استقرار ۰۶ و timer مشاهده شدند؛ دریافت گزارش هنوز تأیید نشده است. |

### ۸.۱ اصل عیب‌یابی ImagePullBackOff

۱) `describe pod` و Events را ببینید؛ ۲) image reference و نود را پیدا کنید؛ ۳) برای registry خصوصی، لاگ registry و پاسخ authenticated را بررسی کنید؛ ۴) وضعیت tag و pipeline را بررسی کنید؛ ۵) تنها پس از تأیید منشأ mirror/archive، remediation انجام دهید. پیام HTTPS ممکن است خطای fallback بعد از شکست HTTP mirror باشد، نه علت نخست. delete کردن Pod بدون اصلاح علت پایدار، درمان نیست.

## ۹. runbook عملیاتی و آزمون‌ها

### ۹.۱ خواندن وضعیت بدون تغییرات مخرب

```bash
# روی rezaserver در ریشهٔ repo
ansible vps -b --ask-vault-pass -m command -a 'systemctl is-active wg-quick@wg0'
ansible vps1 -b --ask-vault-pass -m command -a '/usr/local/bin/k3s kubectl get nodes -o wide'
ansible vps1 -b --ask-vault-pass -m command -a '/usr/local/bin/k3s kubectl get pods,pvc -A -o wide'
ansible vps1 -b --ask-vault-pass -m command -a '/usr/local/bin/k3s kubectl -n argocd get applications'
ansible vps1 -b --ask-vault-pass -m command -a 'journalctl -u maktab-backup.service -n 30 --no-pager'
```

در خروجی‌ها ممکن است نام‌های داخلی و اطلاعات حساس وجود داشته باشد. `kubectl describe` یا log را قبل از ارسال بررسی کنید. از نمایش Secret، kubeconfig، bot token، registry config، کلیدها و invite link خودداری کنید.

### ۹.۲ تفسیر `08-verify.yml`

۰۸ روی VPSها systemd، UFW، WG، Docker و node exporter را می‌سنجد؛ سپس DNS، HTTPS داخلی، Gitea/registry، TLS عمومی، Teleport و متریک بکاپ؛ سپس اتصال worker، تست نوشتن NFS، observability و ingest marker لاگ؛ در پایان node/Pod/deployment/PVC و وضعیت Argo `Synced Healthy`. هنگام پیکربندی Telegram timer هم فعال بودن آن بررسی می‌شود. `ok` روی taskهایی با `failed_when: false` فقط به معنی اجرای probe است؛ assertion پایانی همان play تعیین‌کننده است. اولین assertion شکست‌خورده ممکن است باعث شود playهای بعدی اجرا نشوند. بررسی بدون ارسال مستقیم report تلگرام و بدون restore است.

```bash
ansible-playbook 08-verify.yml --ask-vault-pass
```

در آخرین ۰۸ کاملِ ارائه‌شده پیش از بازیابی، failure مربوط به متریک backup بود و play به Kubernetes نرسید؛ موفقیت backup بعدی با متریک/journal جداگانه مشاهده شد. پس از آن `OutOfSync` MariaDB هنوز گزارش شد. نباید از Running بودن Podها نتیجه گرفت اجرای نهایی ۰۸ موفق شده است.

### ۹.۳ تست بازیابی پیشنهادی، بدون تخریب production

۱. یک کپی مستقل، دسترسی‌محدود و رمزگذاری‌شده از فایل‌های انتخابی روی محیط آزمایشی بگیرید و تاریخ، checksum و مبدأ را ثبت کنید. ۲. محتویات archive را بدون انتشار secret بررسی و `gzip -t` انجام دهید؛ این فقط سلامت فشرده‌سازی است. ۳. در دیتابیس و کلاستر **ایزوله و خالی** با نسخه‌های سازگار restore کنید؛ هرگز dump را روی DB فعال production اجرا نکنید. ۴. جداول، رکوردها و رفتار برنامه را با معیار مورد توافق مقایسه کنید و زمان بازیابی را ثبت کنید. ۵. به‌طور جداگانه بازگردانی WordPress فایل + DB، Gitea، registry و datastore k3s را با دستورالعمل نسخه‌سازگار تمرین کنید. وضعیت restore در این جلسه **انجام نشده** است؛ این بخش دستور اجرای destructive نیست.

### ۹.۴ ادامهٔ بررسی GitOps/CI

- در Argo UI: `apps` → StatefulSet `mariadb` → Diff واقعی را ببینید؛ `kubectl diff` با حذف label ردیابی جایگزین آن نیست. اصلاح باید تفاوت مشخص را هدف بگیرد، نه حذف یا بازسازی PVC.
- در Gitea Actions نتیجه و log taskهای backend/frontend را ببینید؛ status runner فقط ثبت‌نام را اثبات می‌کند. logها را از secret پاک کنید.
- برای تحویل قابل تکرار، تغییر کد کنترل‌شده، build/push image نسخه‌دار، تغییر GitOps و مشاهدهٔ rollout و endpoint را end-to-end آزمون کنید. بعد از تأیید pipeline، pin کردن digest با اصلاح سازگار workflow را انجام دهید.

## ۱۰. پرسش‌های متداول جلسهٔ دفاع

**چرا WireGuard و نه دسترسی عمومی به ابزارها؟** مسیر خصوصی بین نودها/کلاینت فراهم می‌کند و سرویس‌های داخلی روی WG IP یا توسط firewall محدود می‌شوند. اما خود VPN جایگزین احراز هویت، RBAC و ایمن‌سازی سرویس نیست.

**چرا Kubernetes و Docker Compose کنار هم؟** workloadهای اپلیکیشن و data با GitOps در k3s اجرا می‌شوند؛ سرویس‌های زیرساختی Gitea/registry/monitoring/ELK به صورت Compose روی میزبان مستقرند. این تفکیک پیچیدگی و وابستگی bootstrap دارد و HA آن باید جدا بررسی شود.

**تفاوت Deployment و StatefulSet چیست؟** Deployment برای replicaهای قابل‌تعویض مثل frontend/backend؛ StatefulSet برای هویت پایدار و PVC هر replica مثل MariaDB. PostgreSQL توسط operator و resource `Cluster` مدیریت می‌شود، نه StatefulSet دست‌نویس.

**PVC، PV و StorageClass چه می‌کنند؟** PVC درخواست ذخیره‌سازی است، PV منبع واقعی و StorageClass روش provisioning را تعیین می‌کند. WordPress به RWX روی NFS نیاز دارد؛ local-path دیتابیس به نود وابسته است. `Bound` فقط اتصال claim است، نه صحت داده.

**چرا PostgreSQL و MariaDB هر دو هستند؟** backend نمونه به PostgreSQL وصل است؛ WordPress استاندارد به MySQL/MariaDB نیاز دارد. Redis برای شمارنده/cache نمونه استفاده می‌شود.

**CI با GitOps چه فرقی دارد؟** CI در این قالب کد را build و image را push و مرجع GitOps را به‌روزرسانی می‌کند؛ Argo CD وضعیت GitOps را با cluster reconcile می‌کند. تحقق عملی آن باید با اجرای pipeline و مشاهدهٔ نتیجه اثبات شود.

**چرا `OutOfSync` با `Healthy` هم‌زمان است؟** اولی اختلاف desired/live، دومی سلامت منابع را توصیف می‌کند. سلامت Podها اختلاف پیکربندی را رفع نمی‌کند؛ diff واقعی Argo را بررسی کنید.

**`up` و `probe_success` چه فرقی دارند؟** `up` موفقیت scrape exporter توسط Prometheus است؛ `probe_success` نتیجهٔ تست خود سرویس مقصد توسط blackbox. هر دو برای تشخیص لازم‌اند.

**چرا `ImagePullBackOff` صرفاً خطای اینترنت نیست؟** می‌تواند نبود tag، registry auth، DNS، TLS، شبکه یا quota باشد. در این استقرار برای backend/frontend پاسخ authenticated `manifest unknown` مشاهده شد؛ خطای HTTPS fallback علت اصلی نبودن image نبود.

**`Running` یعنی سرویس واقعاً سالم است؟** خیر؛ readiness محدود، درخواست کاربر، وابستگی دیتابیس، داده‌های موجود و دسترسی بیرونی باید جداگانه بررسی شوند.

**چرا backup موفق اثبات restore نیست؟** فایل ممکن است ناقص، ناسازگار، فاقد دادهٔ مورد انتظار یا غیرقابل‌استفاده باشد؛ restore ایزوله و مقایسهٔ داده لازم است.

**چرا `08` با یک assertion متوقف می‌شود؟** آزمون playهای بعدی ممکن است اجرا نشود؛ به `PLAY RECAP` و خطای نهایی توجه کنید و پس از رفع علت، مجدداً اجرا کنید.

**تفاوت config ID، manifest digest و tag چیست؟** tag نام mutable است؛ config ID شناسهٔ config image و manifest digest شناسهٔ manifest است. SHAهای گزارش‌شده در ابزارهای مختلف بدون دانستن نوع digest قابل مقایسهٔ مستقیم نیستند.

**گزارش تلگرام هوش مصنوعی است؟** خیر؛ خلاصهٔ قانون‌محور/متریک‌های لحظه‌ای Prometheus است. دادهٔ گم‌شده «نامشخص» می‌شود و گزارش تحویل پیام‌های گذشته یا تحلیل ۲ ساعت گذشته نیست.

**آیا کل پروژه production-ready و کاملاً HA است؟** خیر؛ control-plane/NFS تکی، CA و secretهای track‌شده، registry داخلی HTTP، NFS `no_root_squash`، Elasticsearch بدون security، تست‌نشدن restore و CI و OutOfSync باز محدودیت‌های مهم‌اند.

## ۱۱. چک‌لیست ارائه / کارهای باقی‌مانده

- [ ] تأیید حذف staging فایل‌های محرمانه و بررسی دسترسی به تاریخچهٔ Git؛ برنامهٔ چرخش امن credentialها و CA.
- [ ] بررسی اینکه backup script جدید روی vps1 واقعاً نصب شده و ایجاد بکاپ مستقل خارج از چرخهٔ `rsync --delete`.
- [ ] آزمایش restore جداگانه و مقایسهٔ داده‌های مورد انتظار PostgreSQL/MariaDB، فایل‌های WordPress، Git، registry و k3s.
- [ ] گرفتن Argo CD Diff واقعی MariaDB و رفع دلیل `OutOfSync` بدون حذف PVC.
- [ ] بررسی runهای Gitea Actions، رفع مشکل و تست build → registry → تغییر GitOps → rollout؛ برنامه‌ریزی pin digest.
- [ ] تأیید receipt گزارش دوره‌ای تلگرام و بررسی journal سرویس timer.
- [ ] آزمون endpointهای عمومی از شبکهٔ بیرونی، cache MISS/HIT، تمدید certificate و ورود Windows/VPN/Teleport با حساب مجاز.
- [ ] تست failover PostgreSQL، دسترسی‌های NetworkPolicy و dashboardهای Grafana/ELK با دادهٔ واقعی.
- [ ] اجرای `08-verify.yml` بعد از اصلاحات، ذخیرهٔ نتیجهٔ کامل و شفاف‌سازی هر failure.

## ۱۲. جزئیات اقدامات دستی انجام‌شده در محیط کاربر

این موارد سوابق عملیاتی‌اند، نه الزام به تکرار. عملیات دستی لزوماً با هر deployment تازه بازتولید نمی‌شود و نباید به‌جای راهکار پایدار یا تست restore تلقی شود.

1. **TLS عمومی:** اپراتور در تنظیمات محلی، Let's Encrypt را فعال و `05-platform.yml` را اجرا کرد. گواهی `/etc/letsencrypt/live/maktab/fullchain.pem` در ۰۸ برای نام‌های public و اعتبار زمانی عبور کرد. مقدار محلی و email آن با Git قابل یکی‌دانستن نیست؛ اجرای ۰۵ اثر پیکربندی و احتمال توقف موقت Nginx دارد.
2. **دسترسی به imageهای خارجی:** اپراتور به دستور ما از روی control و با Ansible، روی هر دو VPS `k3s crictl pull` را برای mirrorهای KSM، Argo و NFS اجرا کرد. نتیجهٔ هر سه pull در هر دو نود موفق گزارش شد. فایل محلی `/root/maktab-images.yml` با سه override ساخته و ۰۴ با `-e @/root/maktab-images.yml` اجرا شد. بعداً همین انتخاب‌ها در `inventory/group_vars/all/zz-image-mirrors.yml` ثبت شد؛ extra-vars همچنان اولویت دارد. pull دستی image را به‌تنهایی به manifest وصل نمی‌کند؛ خود ۰۴ manifest را اعمال می‌کند.
3. **Argo و NFS:** ۰۴ پس از override، Deployment NFS را به mirror تغییر داد. StatefulSet آرگو template جدید داشت ولی Pod قدیمی در backoff بود؛ اپراتور تنها `argocd-application-controller-0` را حذف عادی کرد و rollout موفق شد. بعد از شروع controller، auto-sync با prune/self-heal منابع برنامه را ساخت. guard محدود برای همان وضعیت بعداً در ۰۴ اضافه شد؛ اجرای guard روی این سرورها هنوز مستقل تأیید نشده است.
4. **بازیابی imageهای خصوصی:** اپراتور اعلام کرد `/tmp/backend.tar` و `/tmp/frontend.tar` را خود از پروژه ساخته و با SCP به vps1 منتقل کرده است؛ commit دقیق شناخته نشده. checksum و manifest آن‌ها بررسی شد. با اسکریپت یک‌بارمصرف، قبل از push عدم وجود tagها بررسی و هر image با tag `latest` و `recovery-20261021` منتشر شد. برنامه‌ها سپس rollout شدند. `10-recover-app-images.yml` بعداً برای تکرار کنترل‌شده اضافه شد؛ اجرای واقعی این playbook در گفتگو دیده نشده است. فایل‌های tar دائمی تضمین نشده و `/tmp` ممکن است پاک شود. اگر بازیابی لازم شود، قبل از اجرا CI/publisherهای هم‌زمان را متوقف و provenance و checksum را مستقل بررسی کنید؛ registry به طور اتمی از race محافظت نمی‌کند.
5. **بکاپ و اعلان:** اجرای برنامه‌ریزی‌شدهٔ ۳ نوامبر تمام jobها را موفق ثبت کرد. پیام‌های firing و resolved هشدار بکاپ در تلگرام دیده شد. receipt گزارش دوره‌ای جدید تأیید نشده؛ خروجی ۰۶ نصب timer و زمان‌بندی را نشان داد.
6. **VPN کنترل‌نود:** اپراتور `wg-quick up /root/maktab2/.secrets/wg/maktab-vpn.conf` را روی `rezaserver` اجرا کرد؛ handshake و پاسخ DNS روی همان interface مشاهده شد. تبدیل فایل برای ویندوز و غیرفعال‌سازی موقت peer روی کنترل‌نود به اپراتور توضیح داده شد، اما انجام آن تأیید نشده است. peer مشترک را هم‌زمان روی دو دستگاه فعال نکنید.
7. **Git و secret:** اپراتور `git add .` اجرا کرد و فایل‌های حساس staged شدند؛ راهنمای unstage بدون حذف تغییرات داده شد، اما انجام آن در خروجی بعدی مستقلاً تأیید نشده است. هیچ‌گاه وضعیت staging یا محتویات `.secrets` را با commit/push خودکار عوض نکنید.

### آزمون‌های موجود و محدودیت آن‌ها

تست‌های پوشهٔ `tests/` غالباً render، منطق موضعی و fake service/API را تست می‌کنند و استقرار واقعی دو VPS یا restore را شبیه‌سازی نمی‌کنند. با Ansible/collections و Python/Jinja2 نصب‌شده، از ریشهٔ مخزن می‌توان نمونه‌های زیر را اجرا کرد:

```bash
ansible-playbook --syntax-check 04-kubernetes.yml
ansible-playbook --syntax-check 06-monitoring.yml
ansible-playbook --syntax-check 08-verify.yml
ansible-playbook -i localhost, tests/backtofirst-units.yml
ansible-playbook -i localhost, tests/alertmanager-config.yml
ansible-playbook -i localhost, tests/platform-image-overrides.yml
ansible-playbook -i inventory/hosts.yml tests/telegram-status-template.yml
python3 tests/backup-snapshot-safety.py
python3 tests/verify-backup-metrics.py
python3 tests/recovery-noop.py
python3 tests/telegram-status-report.py
```

`--syntax-check` تنها parse playbook را کنترل می‌کند و عملکرد runtime را تضمین نمی‌کند. `tests/recovery-noop.py` از HTTP server محلی ساختگی استفاده می‌کند، نه registry واقعی؛ تست Telegram شبکهٔ واقعی را فراخوانی نمی‌کند. برای سایر تست‌ها فایل داخل `tests/` و پیش‌نیازهای آن منبع حقیقت است.

## ۱۳. فرهنگ فایل‌ها: ریشه، roleها، templates و tests

این بخش برای پاسخ به سؤال «هر فایل چه می‌کند؟» است. فایل‌های `.secrets` به‌دلیل امنیت **فقط به‌عنوان دستهٔ محرمانه** توصیف می‌شوند و محتوای آن‌ها هرگز در سند کپی نشده است. فایل‌های `.bak.*` نسخهٔ پشتیبان قدیمی هستند و محل task فعال محسوب نمی‌شوند؛ قبل از حذف یا اصلاح، اثر احتمالی را بررسی کنید. فایل‌های محلی خارج از Git، Vaultهای محیط و archiveهای vps1 ممکن است در این فهرست وجود نداشته باشند.

| مسیر فایل | کاربرد |
|---|---|
| `.gitignore` | نادیده‌گرفتن فایل‌های محرمانهٔ جدید؛ فایل‌های track‌شده را حذف نمی‌کند. |
| `00-secrets.yml` | تولید/بارگذاری اولیهٔ رمزها در کنترل‌نود. |
| `01-prepare-vm.yml` | آماده‌سازی میزبان، Docker و Ansible. |
| `02-firewall.yml` | UFW و حفاظت شبکه‌های داخلی. |
| `03-access.yml` | PKI، VPN، DNS، Teleport و بررسی tunnel. |
| `04-kubernetes.yml` | NFS، k3s و منابع پایهٔ کلاستر. |
| `05-platform.yml` | Gitea، registry، GitOps و Nginx. |
| `06-monitoring.yml` | exporter، ELK، Filebeat، monitoring و Telegram. |
| `07-backup.yml` | اسکریپت، حساب مقصد و timer بکاپ. |
| `08-verify.yml` | بررسی سطح میزبان، edge، worker و Kubernetes/GitOps. |
| `09-backtofirst.yml` | cleanup مستقل مخرب با تأیید صریح. |
| `10-recover-app-images.yml` | بازیابی opt-in imageهای آرشیوشده به رجیستری. |
| `README.md` | راهنمای اولیه و نکته‌های عملیاتی. |
| `ansible.cfg` | تنظیم اجرای Ansible در ریشهٔ مخزن. |
| `inventory/group_vars/all/main.yml` | دامنه‌ها، IPها، پورت‌ها، نسخه‌ها و تنظیمات مشترک. |
| `inventory/group_vars/all/monitoring.yml` | کانال اعلان و targetهای probe؛ مقادیر عملیاتی ممکن است محلی/Vault باشند. |
| `inventory/group_vars/all/secrets.yml` | نام و روش بارگذاری secretها؛ خود مقدارها را منتشر نکنید. |
| `inventory/group_vars/all/zz-image-mirrors.yml` | override mirrorهای KSM، NFS و Argo CD. |
| `inventory/host_vars/vps1.yml` | پورت‌های عمومی vps1. |
| `inventory/host_vars/vps2.yml` | پورت‌های عمومی vps2. |
| `inventory/hosts.yml` | گروه‌ها، hostها، آدرس‌ها و کلید SSH نمونه. |
| `k3s-server-only.yml` | اجرای محدود role k3s روی server. |
| `pki-vps1.yml` | اجرای محدود role PKI روی vps1. |
| `requirements.yml` | وابستگی‌های Ansible collections. |
| `roles/ansible_control/tasks/main.yml` | taskهای اصلی نقش ansible_control؛ آماده‌سازی ابزار Ansible و inventory مستقل روی edge. |
| `roles/backtofirst/tasks/main.yml` | taskهای اصلی نقش backtofirst؛ حذف مخرب و مرحله‌ای مؤلفه‌های پروژه. |
| `roles/backtofirst/tasks/probe_units.yml` | شناسایی امن unitهای موجود و نبودن آن‌ها پیش از پاک‌سازی. |
| `roles/backup/handlers/main.yml` | handlerهای reload/restart مرتبط با تولید بکاپ، retention، انتقال و متریک. |
| `roles/backup/tasks/main.yml` | taskهای اصلی نقش backup؛ تولید بکاپ، retention، انتقال و متریک. |
| `roles/backup/templates/maktab-backup.service.j2` | واحد systemd برای اجرای oneshot اسکریپت بکاپ. |
| `roles/backup/templates/maktab-backup.sh.j2` | اسکریپت هشت job، پوشهٔ یکتای هر اجرا، متریک، retention و rsync. |
| `roles/backup/templates/maktab-backup.timer.j2` | زمان‌بندی روزانهٔ بکاپ با تأخیر تصادفی. |
| `roles/common/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای پکیج‌های پایه، حساب‌ها، SSH، sysctl و زمان. |
| `roles/common/handlers/main.yml` | handlerهای reload/restart مرتبط با پکیج‌های پایه، حساب‌ها، SSH، sysctl و زمان. |
| `roles/common/tasks/main.yml` | taskهای اصلی نقش common؛ پکیج‌های پایه، حساب‌ها، SSH، sysctl و زمان. |
| `roles/devtools/handlers/main.yml` | handlerهای reload/restart مرتبط با Gitea، registry و runner. |
| `roles/devtools/tasks/main.yml` | taskهای اصلی نقش devtools؛ Gitea، registry و runner. |
| `roles/devtools/templates/docker-compose.yml.j2` | تعریف سرویس‌های Gitea، registry و act_runner و bind/volumeها. |
| `roles/devtools/templates/runner-config.yaml.j2` | پیکربندی act_runner. |
| `roles/dns/handlers/main.yml` | handlerهای reload/restart مرتبط با BIND و DNS خصوصی. |
| `roles/dns/tasks/main.yml` | taskهای اصلی نقش dns؛ BIND و DNS خصوصی. |
| `roles/dns/templates/named.conf.local.j2` | تعریف zone خصوصی BIND. |
| `roles/dns/templates/named.conf.options.j2` | listen، recursion، ACL و forwarderهای BIND. |
| `roles/dns/templates/zone.j2` | رکوردهای zone خصوصی مبتنی بر inventory. |
| `roles/docker/handlers/main.yml` | handlerهای reload/restart مرتبط با نصب/تنظیم Docker. |
| `roles/docker/tasks/main.yml` | taskهای اصلی نقش docker؛ نصب/تنظیم Docker. |
| `roles/docker/templates/daemon.json.j2` | تنظیم Docker daemon، از جمله رجیستری HTTP داخلی. |
| `roles/edge_nginx/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای reverse proxy، TLS و cache در edge. |
| `roles/edge_nginx/handlers/main.yml` | handlerهای reload/restart مرتبط با reverse proxy، TLS و cache در edge. |
| `roles/edge_nginx/tasks/main.yml` | taskهای اصلی نقش edge_nginx؛ reverse proxy، TLS و cache در edge. |
| `roles/edge_nginx/templates/internal.conf.j2` | virtual hostهای HTTPS خصوصی روی WG IP. |
| `roles/edge_nginx/templates/maktab-http.conf.j2` | cache zone و upstreamهای NodePort. |
| `roles/edge_nginx/templates/nginx.conf.j2` | پیکربندی سراسری Nginx و log JSON. |
| `roles/edge_nginx/templates/proxy.conf.j2` | headerها و تنظیمات مشترک reverse proxy. |
| `roles/edge_nginx/templates/public.conf.j2` | میزبان‌های عمومی app و WordPress، HTTPS و static cache. |
| `roles/elk/tasks/main.yml` | taskهای اصلی نقش elk؛ Elasticsearch، Logstash و Kibana. |
| `roles/elk/templates/docker-compose.yml.j2` | تعریف Elasticsearch، Logstash، Kibana و exporter با محدودیت منابع. |
| `roles/elk/templates/logstash/logstash.conf.j2` | پردازش رویداد Filebeat و ارسال به indexهای Elasticsearch. |
| `roles/filebeat/tasks/main.yml` | taskهای اصلی نقش filebeat؛ جمع‌آوری و ارسال لاگ. |
| `roles/filebeat/templates/docker-compose.yml.j2` | اجرای Filebeat و mountهای مورد نیاز. |
| `roles/filebeat/templates/filebeat.yml.j2` | ورودی لاگ nginx/syslog و مقصد Logstash. |
| `roles/firewall/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای UFW و قواعد محافظ Docker/NodePort. |
| `roles/firewall/handlers/main.yml` | handlerهای reload/restart مرتبط با UFW و قواعد محافظ Docker/NodePort. |
| `roles/firewall/tasks/main.yml` | taskهای اصلی نقش firewall؛ UFW و قواعد محافظ Docker/NodePort. |
| `roles/gitops/tasks/main.yml` | taskهای اصلی نقش gitops؛ seed اولیهٔ Git و Application آرگو. |
| `roles/gitops/tasks/repo.yml` | seed، marker رفع وقفه، commit و push اولیهٔ هر مخزن. |
| `roles/gitops/tasks/repo.yml.bak.20261017-102753` | نسخهٔ پشتیبان قدیمی؛ task فعال نیست. |
| `roles/gitops/templates/repo-backend/.gitea/workflows/ci.yml.j2` | workflow seed ساخت/push backend و تغییر tag GitOps. |
| `roles/gitops/templates/repo-backend/Dockerfile.j2` | ساخت image Python/Gunicorn برای backend. |
| `roles/gitops/templates/repo-backend/app.py.j2` | Flask demo، healthz و endpoint نوشتن PostgreSQL/Redis. |
| `roles/gitops/templates/repo-backend/requirements.txt.j2` | نسخهٔ وابستگی‌های Python backend. |
| `roles/gitops/templates/repo-frontend/.gitea/workflows/ci.yml.j2` | workflow seed ساخت/push frontend و تغییر tag GitOps. |
| `roles/gitops/templates/repo-frontend/Dockerfile.j2` | ساخت image Nginx frontend. |
| `roles/gitops/templates/repo-frontend/index.html.j2` | صفحهٔ ساده و درخواست `/api/ping`. |
| `roles/gitops/templates/repo-gitops/README.md.j2` | توضیح کوتاه مخزن GitOps seed. |
| `roles/gitops/templates/repo-gitops/apps/backend/backend.yaml.j2` | Deployment دو replica و Service NodePort backend. |
| `roles/gitops/templates/repo-gitops/apps/frontend/frontend.yaml.j2` | Deployment دو replica و Service NodePort frontend. |
| `roles/gitops/templates/repo-gitops/apps/mariadb/mariadb.yaml.j2` | StatefulSet، volumeClaimTemplate و Service MariaDB. |
| `roles/gitops/templates/repo-gitops/apps/postgres/cluster.yaml.j2` | منبع Cluster برای CloudNativePG با دو instance. |
| `roles/gitops/templates/repo-gitops/apps/redis/redis.yaml.j2` | Deployment و Service Redis با رمز و سقف حافظه. |
| `roles/gitops/templates/repo-gitops/apps/wordpress/wordpress.yaml.j2` | PVC، Deployment و Service WordPress. |
| `roles/k3s/handlers/main.yml` | handlerهای reload/restart مرتبط با نصب و تنظیم کلاستر k3s. |
| `roles/k3s/tasks/main.yml` | taskهای اصلی نقش k3s؛ نصب و تنظیم کلاستر k3s. |
| `roles/k3s/templates/config-agent.yaml.j2` | آدرس server، token، node IP و flannel برای agent. |
| `roles/k3s/templates/config-server.yaml.j2` | آدرس server، TLS SAN، flannel، غیرفعال‌سازی Traefik و reserve kubelet. |
| `roles/k3s/templates/registries.yaml.j2` | mirror HTTP و credential رجیستری containerd؛ محرمانه. |
| `roles/k8s_platform/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای منابع پایه Kubernetes، policy، NFS، CNPG و Argo. |
| `roles/k8s_platform/handlers/main.yml` | handlerهای reload/restart مرتبط با منابع پایه Kubernetes، policy، NFS، CNPG و Argo. |
| `roles/k8s_platform/tasks/main.yml` | taskهای اصلی نقش k8s_platform؛ منابع پایه Kubernetes، policy، NFS، CNPG و Argo. |
| `roles/k8s_platform/templates/monitoring-agents.yml.j2` | Deployment و Serviceهای KSM و blackbox داخل کلاستر. |
| `roles/k8s_platform/templates/namespaces.yml.j2` | ساخت namespaces پروژه. |
| `roles/k8s_platform/templates/netpol.yml.j2` | default-deny ingress و مجوزهای مشخص inter-service. |
| `roles/k8s_platform/templates/nfs-provisioner.yml.j2` | RBAC، Deployment و StorageClass provisioner NFS. |
| `roles/k8s_platform/templates/secrets.yml.j2` | Secretهای Kubernetes برای برنامه‌ها و دیتابیس‌ها. |
| `roles/monitoring/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای Prometheus، alerting، dashboard و گزارش تلگرام. |
| `roles/monitoring/files/alerts.yml` | تمام Prometheus alert rules و آستانه‌ها. |
| `roles/monitoring/files/nginx-traffic.json` | dashboard Grafana ترافیک و cache Nginx. |
| `roles/monitoring/files/telegram-status-report.py` | گرفتن snapshot متریک‌ها و ارسال گزارش تلگرام بدون ثبت token. |
| `roles/monitoring/handlers/main.yml` | handlerهای reload/restart مرتبط با Prometheus، alerting، dashboard و گزارش تلگرام. |
| `roles/monitoring/tasks/main.yml` | taskهای اصلی نقش monitoring؛ Prometheus، alerting، dashboard و گزارش تلگرام. |
| `roles/monitoring/templates/alertmanager.yml.j2` | route، receiver و channel اعلان‌ها. |
| `roles/monitoring/templates/blackbox.yml.j2` | ماژول‌های probe HTTP و TCP. |
| `roles/monitoring/templates/dashboard.json.j2` | قالب تولید dashboardهای منابع و platform. |
| `roles/monitoring/templates/datasources.yml.j2` | datasourceهای Grafana. |
| `roles/monitoring/templates/docker-compose.yml.j2` | Compose مربوط به Prometheus، Alertmanager، Blackbox و Grafana. |
| `roles/monitoring/templates/maktab-telegram-report.service.j2` | واحد oneshot گزارش دوره‌ای. |
| `roles/monitoring/templates/maktab-telegram-report.timer.j2` | زمان‌بندی گزارش دوره‌ای. |
| `roles/monitoring/templates/prometheus.yml.j2` | targetها، scrape، rule files و Alertmanager. |
| `roles/monitoring/templates/telegram-status-report.json.j2` | پیکربندی محرمانهٔ token/chat، probeهای مورد انتظار و نودها. |
| `roles/nfs/handlers/main.yml` | handlerهای reload/restart مرتبط با NFS server/client و export. |
| `roles/nfs/tasks/main.yml` | taskهای اصلی نقش nfs؛ NFS server/client و export. |
| `roles/node_exporter/tasks/main.yml` | taskهای اصلی نقش node_exporter؛ متریک‌های میزبان و textfile collector. |
| `roles/pki/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای صدور و توزیع CA و گواهی خصوصی. |
| `roles/pki/handlers/main.yml` | handlerهای reload/restart مرتبط با صدور و توزیع CA و گواهی خصوصی. |
| `roles/pki/tasks/ca.yml` | تولید CA و wildcard و کنترل تطابق کلید و گواهی. |
| `roles/pki/tasks/distribute.yml` | توزیع گواهی، زنجیره، کلید و trust CA به سرورها. |
| `roles/pki/tasks/distribute.yml.bak.20261015224503` | نسخهٔ پشتیبان قدیمی، نه task فعال. |
| `roles/pki/tasks/main.yml` | taskهای اصلی نقش pki؛ صدور و توزیع CA و گواهی خصوصی. |
| `roles/teleport/handlers/main.yml` | handlerهای reload/restart مرتبط با PAM، auth/proxy/node و systemd. |
| `roles/teleport/tasks/main.yml` | taskهای اصلی نقش teleport؛ PAM، auth/proxy/node و systemd. |
| `roles/teleport/templates/teleport-node.yaml.j2` | پیکربندی node و join از طریق proxy. |
| `roles/teleport/templates/teleport-server.yaml.j2` | پیکربندی auth/proxy، listenerهای خصوصی و OTP. |
| `roles/teleport/templates/teleport.service.j2` | واحد systemd برای Teleport. |
| `roles/wireguard/defaults/main.yml` | مقادیر پیش‌فرض قابل override برای کلیدها، تنظیمات و tunnel شبکه خصوصی. |
| `roles/wireguard/handlers/main.yml` | handlerهای reload/restart مرتبط با کلیدها، تنظیمات و tunnel شبکه خصوصی. |
| `roles/wireguard/tasks/main.yml` | taskهای اصلی نقش wireguard؛ کلیدها، تنظیمات و tunnel شبکه خصوصی. |
| `roles/wireguard/templates/wg0.conf.j2` | Interface و peerها، routeها و split DNS Linux. |
| `scripts/bootstrap-control.sh` | نصب پیش‌نیازهای کنترل‌نود. |
| `show_tree_and_contents.sh` | نمایش ساختار و محتوا؛ خطر افشای دادهٔ محرمانه. |
| `site.yml` | ترتیب اجرای مراحل ۰۰ تا ۰۷؛ ۰۸/۰۹/۱۰ مستقل‌اند. |
| `tests/alertmanager-config.yml` | تست محلی: render receiver Telegram و حالت بدون اعلان. |
| `tests/backtofirst-units.yml` | تست محلی: probe unitهای cleanup با systemctl ساختگی. |
| `tests/backup-snapshot-safety.py` | تست محلی: جلوگیری از بازنویسی فایل hard-linked با اجرای تکراری. |
| `tests/kube-state-metrics-image.yml` | تست محلی: اعمال override ایمیج KSM در template. |
| `tests/pki.yml` | تست محلی: بررسی تولید و سازگاری PKI. |
| `tests/platform-image-overrides.yml` | تست محلی: render ایمیج NFS و جایگزینی نمونهٔ Argo. |
| `tests/recovery-noop.py` | تست محلی: تگ‌های موجود دست‌نخورده و archive گمشده قبل از load رد می‌شود. |
| `tests/telegram-status-report.py` | تست محلی: تست گزارش، دادهٔ نامشخص، هشدار، محدودیت پیام و عدم افشای token. |
| `tests/telegram-status-template.yml` | تست محلی: render تنظیمات گزارش و فهرست probeها. |
| `tests/teleport-tunnel.yml` | تست محلی: render تنظیمات tunnel و listenerهای Teleport. |
| `tests/verify-backup-metrics.py` | تست محلی: قبول متریک موفق و رد متریک failed/stale. |
| `tests/wireguard-control-handler.yml` | تست محلی: بررسی handler WireGuard روی control. |

فایل جاری `docs/PROJECT-DEFENSE-FA.md` همین مستند است. موجودی بالا از فایل‌های track‌شدهٔ غیرمحرمانه در زمان نگارش ساخته شده است؛ فایل‌های نصب‌شده روی VPS و فایل‌های محلی خارج از Git در بخش‌های مربوط توضیح داده شده‌اند.

### فهرست نام فایل‌های محرمانهٔ track‌شده

نام‌ها برای شناسایی و مدیریت امنیت آمده‌اند؛ **مقادیر در این مستند نیستند**. وجود یک فایل در Git دلیل سالم یا امن بودن آن نیست. این فایل‌ها را در چت ارسال نکنید و بدون برنامه برای بازتولیدشان حذف نکنید.

| مسیر | نقش |
|---|---|
| `.secrets/gitea_admin_password` | رمز حساب مدیریتی Gitea |
| `.secrets/grafana_admin_password` | رمز حساب مدیریتی Grafana |
| `.secrets/k3s_token` | token پیوستن کلاستر k3s |
| `.secrets/mariadb_root_password` | رمز root برای MariaDB |
| `.secrets/mariadb_wp_password` | رمز حساب دیتابیس WordPress |
| `.secrets/pg_app_password` | رمز کاربر دیتابیس backend |
| `.secrets/redis_password` | رمز Redis |
| `.secrets/registry_password` | رمز registry خصوصی |
| `.secrets/teleport_node_token` | token پیوستن node به Teleport |
| `.secrets/pki/ca.crt` | گواهی عمومی CA خصوصی؛ اثر اعتماد آن باید تأیید شود. |
| `.secrets/pki/ca.key` | **کلید خصوصی CA** و بسیار حساس. |
| `.secrets/pki/wildcard.crt` | گواهی wildcard دامنهٔ خصوصی. |
| `.secrets/pki/wildcard.key` | کلید خصوصی گواهی wildcard. |
| `.secrets/wg/maktab-vpn.conf` | تنظیم VPN کلاینت حاوی کلید خصوصی. |
| `.secrets/wg/private.key` | کلید خصوصی WireGuard کنترل‌نود. |
| `.secrets/wg/public.key` | کلید عمومی متناظر WireGuard. |

`.secrets/kubeconfig` در خروجی اپراتور یک فایل محلی untracked بود و credential مدیریت cluster دارد. فایل‌های local دیگری نیز ممکن است وجود داشته باشند. اگر `.secrets` قبلاً در تاریخچهٔ remote موجود بوده، فرض کنید ممکن است برای افراد دارای دسترسی به مخزن قابل مشاهده بوده باشد و چرخش مرحله‌ای و امن برنامه‌ریزی کنید.
