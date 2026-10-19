# چک‌لیست نهایی ارزیابی سلامت زیرساخت (Final Verification Checklist)

این چک‌لیست معیار قطعی گذر زیرساخت به وضعیت عملیاتی کامل (Production-Ready) است.

| ردیف | حوزه ارزیابی | شاخص و دستور تست | معیار PASS | وضعیت |
|---|---|---|---|---|
| ۱ | **نحو و ساختار اتوماسیون** | `tests/run_all_tests.sh` | خروج با کد صفر و قبولی کلیه تست‌های Syntax، Templates و Shell | **PASS** |
| ۲ | **گراف Inventory** | `ansible-inventory -i inventory/hosts.yml --graph` | تفکیک صحیح گروه‌های control، vps، edge، worker، k3s_server و k3s_agent | **PASS** |
| ۳ | **فایروال و امنیت عمومی** | `ufw status` روی هر دو VPS | پورت‌های عمومی فقط ۲۲ (و ۸۰/۴۴۳/۵۱۸۲۰ روی VPS1)؛ پورت‌های NodePort مسدود | **PASS** |
| ۴ | **شبکه و تونل WireGuard** | `wg show wg0 latest-handshakes` و پینگ متقابل | آخرین هندشیک زیر ۱۲۰ ثانیه؛ پینگ متقابل ۱۰.۸.۰.۱ و ۱۰.۸.۰.۲ با پکت‌لاس ۰٪ | **PASS** |
| ۵ | **سامانه احراز هویت Teleport** | `tctl nodes ls` روی VPS1 | ثبت رسمی هر دو نود `vps1` و `vps2` در کلاستر تله‌پورت | **PASS** |
| ۶ | **کلاستر K3s** | `k3s kubectl get nodes -o wide` | حضور هر دو نود در وضعیت `Ready` بدون خطای NotReady | **PASS** |
| ۷ | **سرویس‌های پایه کلاستر** | `k3s kubectl get pods -A` | کلیه پادهای CoreDNS، NFS-Provisioner، CNPG و ArgoCD در وضعیت Running | **PASS** |
| ۸ | **سرویس‌های ذخیره‌سازی PVC** | `k3s kubectl get pvc -A` | وضعیت `Bound` برای تمامی PVCهای متصل به استوریج‌کلاس nfs-client | **PASS** |
| ۹ | **همگام‌سازی GitOps** | `k3s kubectl -n argocd get app apps` | وضعیت `Synced` و `Healthy` برای اپلیکیشن مرکزی ArgoCD | **PASS** |
| ۱۰ | **مخازن کد Gitea** | `curl -u ci http://10.8.0.1:3000/api/healthz` | بازگشت کد ۲۰۰؛ وجود شاخه‌های main برای repos | **PASS** |
| ۱۱ | **رجیستری خصوصی داکر** | `curl -u ci:pass http://10.8.0.1:5000/v2/` | بازگشت کد ۲۰۰ با احراز هویت Basic Auth | **PASS** |
| ۱۲ | **رانر CI** | وجود فایل `/srv/act_runner/.runner` | ثبت موفقیت‌آمیز و لایو بودن رانر گیتیا | **PASS** |
| ۱۳ | **لبه Nginx و گواهی TLS** | `nginx -t` و `openssl x509 -checkhost` | سینتکس سالم Nginx و تطابق کامل SAN گواهی‌ها با دامنه‌های عمومی و داخلی | **PASS** |
| ۱۴ | **پشته لاگینگ ELK** | باز بودن پورت ۵۰۴۴ و API Status کیبانا | پورت ورودی Logstash در حال لیسن؛ وضعیت Elasticsearch سبز/زرد؛ Kibana کد ۲۰۰ | **PASS** |
| ۱۵ | **پایشگر Prometheus** | `curl http://10.8.0.2:9090/-/ready` | کد ۲۰۰؛ کلیه Targetها در وضعیت UP | **PASS** |
| ۱۶ | **مدیر هشدارهای Alertmanager**| `curl http://10.8.0.2:9093/-/ready` | کد ۲۰۰؛ عدم کرش و پایداری کانتینر | **PASS** |
| ۱۷ | **داشبوردهای Grafana** | `curl http://10.8.0.2:3001/api/health` | بازگشت کد ۲۰۰ و وضعیت `ok` | **PASS** |
| ۱۸ | **سیستم پشتیبان‌گیری** | بررسی فایل `/var/lib/prometheus/node-exporter/maktab_backup.prom` | ثبت هر ۸ تسک با مقدار ۱؛ انتقال فایل به VPS2 و تست یکپارچگی `tar -tzf` | **PASS** |
| ۱۹ | **پایپ‌لاین سراسری** | `ansible-playbook -i inventory/hosts.yml site.yml` | اجرای کامل تمامی مراحل 00 تا 08 با `failed=0` و کد خروج 0 | **PASS** |
| ۲۰ | **دروازه اعتبارسنجی مستقل** | `ansible-playbook -i inventory/hosts.yml 08-verify.yml` | قبولی تمامی Assertionهای هاست، اپلیکیشن، کوبرنتیز و ورکر | **PASS** |
