# ریشه‌یابی و رفع شکست سرویس K3s Server در VPS1 (K3s Server Failure Analysis)

این گزارش مستندسازی جامع، فنی و گام‌به‌گام در خصوص دلایل خرابی سرویس `k3s.service` روی VPS1 (`81.12.50.30`)، شواهد مستقیم، استنباط‌های مهندسی و راه‌حل‌های اعمال‌شده در مخزن را ارائه می‌دهد.

---

## ۱. دسته‌بندی شواهد و تحلیل فنی

طبق اصول ممیزی مهندسی زیرساخت:

### ۱.۱. شواهد مستقیم (Direct Evidence)
1. **وابستگی سخت به اینترفیس غایب:** در فایل کانفیگ `roles/k3s/templates/config-server.yaml.j2` مقادیر زیر به صورت هاردکد تنظیم شده بودند:
   - `node-ip: 10.8.0.1`
   - `advertise-address: 10.8.0.1`
   - `flannel-iface: wg0`
2. **وابستگی سیستمی مسدودکننده (Systemd Block):** فایل دراپ‌این `/etc/systemd/system/k3s.service.d/override.conf` صراحتاً شامل موارد زیر بود:
   ```ini
   [Unit]
   After=wg-quick@wg0.service
   Wants=wg-quick@wg0.service
   ```
   هرگاه سرویس WireGuard با خطا مواجه می‌شد یا اینترفیس `wg0` بالا نمی‌آمد، Systemd از اجرای K3s Server جلوگیری می‌کرد یا اجرای آن را در انتظار قرار می‌داد تا به خطای Timeout برسد.
3. **عدم گوش دادن به تمام اینترفیس‌ها:** نبود عبارت صریح `bind-address: 0.0.0.0` در برخی ویرایش‌ها باعث می‌شد K3s تنها سعی در بایند کردن روی `10.8.0.1` کند که در صورت فقدان اینترفیس، با خطای `bind: cannot assign requested address` بلافاصله متوقف (Fatal Crash) می‌شد.

### ۱.۲. استنباط فنی (Technical Inference)
- موتور Flannel با پارامتر `--flannel-iface=wg0` هنگام راه‌اندازی اینترفیس CNI تلاش می‌کند آدرس MTU و آدرس IP متناظر با `wg0` را بخواند. در صورتی که این اینترفیس در هسته لینوکس وجود نداشته باشد، راه‌اندازی Flannel CNI با شکست مواجه شده و پادهای کنترلی (`coredns`, `local-path-provisioner`, `metrics-server`) در وضعیت `ContainerCreating` یا `CrashLoopBackOff` باقی می‌مانند.
- فرآیند ثبت و الحاق نود دوم (Agent Join) به دلیل گوش دادن سرور فقط روی آدرس وایرگارد، در شرایط نقص شبکه خصوصی کاملاً قطع می‌شد.

### ۱.۳. حدس نیازمند بررسی محیطی (Unverified Guess)
- تداخل احتمالی Cgroups v2 با محدودیت‌های حافظه در سرورهای با رم پایین (کمتر از ۲ گیگابایت) یا وجود قفل‌های موقت در فایل دیتابیس توکار SQLite / Kine (`/var/lib/rancher/k3s/server/db/state.db`) پس از ریست‌های ناگهانی ماشین.

---

## ۲. ریشه‌های فنی شکست (Root Causes)

| شماره | ریشه فنی | فایل‌های درگیر | پیامد مستقیم |
|:---:|:---|:---|:---|
| **۱** | اتصال آدرس گره به `10.8.0.1` بدون فالبک به IP عمومی | `roles/k3s/templates/config-server.yaml.j2` | خروج فوری K3s با خطای `cannot assign requested address` |
| **۲** | وابستگی یک‌طرفه و صلب سرویس K3s به `wg-quick@wg0.service` | `roles/k3s/tasks/main.yml` | عدم استارت K3s در صورت خوابیدن تونل شبکه |
| **۳** | هدایت اینترفیس Flannel به `wg0` ناموجود | `roles/k3s/templates/config-server.yaml.j2` | خرابی زیرسیستم CNI و شبکه پادها |
| **۴** | توکن خوشه‌ای متغیر یا گم‌شده هنگام بوت اول | `roles/k3s/tasks/main.yml` | خطای اعتبارسنجی در نود Worker و ناتوانی در اتصال |

---

## ۳. اصلاحات انجام‌شده در کد مخزن (Implemented Fixes)

### اصلاح ۱: پارامتریک و پویاسازی `config-server.yaml.j2`
کانفیگ سرور K3s به صورت کاملاً پویا بازنویسی شد:
```yaml
node-ip: {{ node_service_ip }}
advertise-address: {{ node_service_ip }}
bind-address: 0.0.0.0
tls-san:
  - {{ node_service_ip }}
  - {{ ansible_host }}
  - {{ hub_public_ip }}
{% if (wireguard_enabled | default(true) | bool) and (hostvars is defined and 'vps1' in hostvars and 'wg_ip' in hostvars['vps1']) %}
  - {{ hostvars['vps1'].wg_ip }}
{% elif wg_ip is defined %}
  - {{ wg_ip }}
{% endif %}
  - k8s.{{ private_domain }}
flannel-iface: {{ cluster_iface }}
disable:
  - traefik
  - servicelb
write-kubeconfig-mode: "0600"
token: "{{ (hostvars[groups['k3s_server'][0]].k3s_cluster_token if (hostvars is defined and groups is defined and 'k3s_server' in groups and groups['k3s_server'][0] in hostvars and 'k3s_cluster_token' in hostvars[groups['k3s_server'][0]]) else k3s_token) | default(k3s_token) }}"
kubelet-arg:
  - "system-reserved=cpu=200m,memory=512Mi"
  - "eviction-hard=memory.available<250Mi"
```
**مزایا:**
- با `bind-address: 0.0.0.0`، سرور روی تمام اینترفیس‌ها به پورت ۶۴۴۳ گوش می‌دهد.
- در گواهی‌های TLS (`tls-san`) هر دو آدرس عمومی و خصوصی سرور درج می‌شوند، بنابراین ارتباط کلاینت و ورکر از هر دو مسیر بدون خطای x509 تایید می‌شود.
- اینترفیس `flannel-iface` در حالت Direct-IP برابر با `eth0` و در حالت WireGuard برابر با `wg0` خواهد بود.

### اصلاح ۲: پویاسازی وابستگی‌های Systemd در `roles/k3s/tasks/main.yml`
فایل دراپ‌این به صورت شرطی تولید می‌شود:
```yaml
- name: Ensure K3s has bounded start timeout and proper network dependency
  ansible.builtin.copy:
    dest: "/etc/systemd/system/{{ 'k3s' if inventory_hostname in groups['k3s_server'] else 'k3s-agent' }}.service.d/override.conf"
    mode: "0644"
    content: |
      [Unit]
      {% if wireguard_enabled | default(true) | bool %}
      After=wg-quick@wg0.service
      Wants=wg-quick@wg0.service
      {% else %}
      After=network-online.target
      Wants=network-online.target
      {% endif %}
      [Service]
      TimeoutStartSec=180s
  register: k3s_unit_override
```
**مزایا:**
- در صورت غیرفعال بودن WireGuard، هیچ‌گونه وابستگی به سرویس آن وجود ندارد و مستقیماً به `network-online.target` متصل می‌شود.
- مهلت زمانی راه‌اندازی با `TimeoutStartSec=180s` تعیین شده تا از فریز شدن نامحدود سیستم‌دی جلوگیری کند.

---

## ۴. دستورالعمل تشخیصی و راستی‌آزمایی (Runbook)

### ۴.۱. آزمایش‌های پیش از اعمال (Pre-Change Diagnostics)
روی VPS1 این دستورات را اجرا کنید تا وضعیت و دلیل خطای قبلی ثبت شود:
```bash
# بررسی آخرین خطاهای ثبت‌شده در ژورنال سیستم‌دی:
journalctl -u k3s.service -n 100 --no-pager

# بررسی اینترفیس‌های موجود روی سرور:
ip addr show

# بررسی فایل‌های دراپ‌این فعال:
systemctl cat k3s.service

# بررسی اشغال بودن پورت ۶۴۴۳ توسط پروسه‌های دیگر:
ss -tulpn | grep :6443
```

### ۴.۲. دستورات اعمال و راه‌اندازی (Execution)
```bash
# بارگذاری مجدد پیکربندی سیستم‌دی:
systemctl daemon-reload

# راه‌اندازی سرویس K3s:
systemctl restart k3s.service

# بررسی وضعیت سرویس:
systemctl status k3s.service --no-pager
```

### ۴.۳. آزمایش‌های پس از اعمال (Post-Change Verification)
```bash
# بررسی آماده بودن نود در کوبرنتیز:
k3s kubectl get nodes -o wide

# بررسی وضعیت پادهای سیستمی در kube-system:
k3s kubectl get pods -n kube-system -o wide

# بررسی دسترسی به پورت API سرور از طریق cURL:
curl -k https://127.0.0.1:6443/readyz
curl -k https://81.12.50.30:6443/readyz
```
نتیجه مورد انتظار برای دستورات فوق پاسخ `ok` و وضعیت `Ready` برای نود سرور است.
