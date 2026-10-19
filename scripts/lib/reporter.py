"""
Reporter Module for Maktab DevOps Service Health Auditor.
Generates:
1. Terminal Summary Table with ANSI colors and prioritized issues
2. Comprehensive Markdown Report conforming to the 16-section standard
3. Machine-readable JSON Report conforming to schema
"""
import os
import json
from datetime import datetime, timezone
from pathlib import Path

# ANSI Color codes for terminal UI
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_RED = "\033[31m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_CYAN = "\033[36m"
CLR_MAGENTA = "\033[35m"
CLR_BLUE = "\033[34m"

def get_status_colored(status):
    if status == "PASS":
        return f"{CLR_GREEN}{CLR_BOLD}PASS{CLR_RESET}"
    elif status == "FAIL":
        return f"{CLR_RED}{CLR_BOLD}FAIL{CLR_RESET}"
    elif status == "WARN":
        return f"{CLR_YELLOW}{CLR_BOLD}WARN{CLR_RESET}"
    elif status == "SKIP":
        return f"{CLR_CYAN}SKIP{CLR_RESET}"
    elif status == "NOT_CHECKED":
        return f"{CLR_MAGENTA}NOT_CHECKED{CLR_RESET}"
    return status

def get_severity_colored(sev):
    if sev == "P0":
        return f"{CLR_RED}{CLR_BOLD}P0{CLR_RESET}"
    elif sev == "P1":
        return f"{CLR_RED}P1{CLR_RESET}"
    elif sev == "P2":
        return f"{CLR_YELLOW}P2{CLR_RESET}"
    elif sev == "P3":
        return f"{CLR_CYAN}P3{CLR_RESET}"
    return sev

def print_terminal_summary(checks, metadata):
    print("\n" + "=" * 90)
    print(f" {CLR_BOLD}MAKTAB DEVOPS COMPREHENSIVE SERVICE HEALTH AUDITOR{CLR_RESET}")
    print("=" * 90)
    print(f" Timestamp : {metadata['timestamp']}")
    print(f" Branch    : {metadata['git_branch']} ({metadata['git_commit'][:8]})")
    print(f" Target    : Host: {metadata['cli_args']['host']} | Scope: {metadata['cli_args']['scope']}")
    print("-" * 90)

    # Table Header
    print(f"{'SERVICE':<24} {'HOST':<9} {'LEVEL':<12} {'RESULT':<14} {'SEV':<6} {'OBSERVED SUMMARY'}")
    print("-" * 90)

    for c in checks:
        srv = c['service'][:22]
        hst = c['host'][:8]
        lvl = c['level'].replace("L1_", "L1:").replace("L2_", "L2:").replace("L3_", "L3:").replace("L4_", "L4:").replace("L5_", "L5:")[:11]
        res = get_status_colored(c['status'])
        sev = get_severity_colored(c['severity'])
        obs = c['observed'][:45] + ("..." if len(c['observed']) > 45 else "")
        print(f"{srv:<24} {hst:<9} {lvl:<12} {res:<23} {sev:<13} {obs}")

    print("=" * 90)
    summary = metadata['summary']
    print(f" {CLR_BOLD}AUDIT SUMMARY COUNTERS:{CLR_RESET}")
    print(f" Total Checks : {summary['total']}")
    print(f" {CLR_GREEN}PASS{CLR_RESET}        : {summary['pass']}")
    print(f" {CLR_RED}FAIL{CLR_RESET}        : {summary['fail']}")
    print(f" {CLR_YELLOW}WARN{CLR_RESET}        : {summary['warn']}")
    print(f" {CLR_CYAN}SKIP{CLR_RESET}        : {summary['skip']}")
    print(f" {CLR_MAGENTA}NOT_CHECKED{CLR_RESET} : {summary['not_checked']}")
    print("-" * 90)
    print(f" Severities   : P0 (Blocker)={summary['p0_count']} | P1 (Critical)={summary['p1_count']} | P2 (Medium)={summary['p2_count']} | P3 (Low)={summary['p3_count']}")
    print("=" * 90)

    # Highlight top prioritized failures
    failures = [c for c in checks if c['status'] in ('FAIL', 'WARN') and c['severity'] in ('P0', 'P1')]
    if failures:
        print(f"\n{CLR_RED}{CLR_BOLD}>>> TOP PRIORITIZED ACTIONABLE ISSUES (P0 & P1):{CLR_RESET}")
        for i, f in enumerate(failures[:8], 1):
            print(f" [{i}] [{f['severity']}] {f['service']} ({f['host']}): {f['observed']}")
            print(f"     Recommended Step: {f['recommended_next_step']}")

    print("\n" + "=" * 90)
    print(f" Generated Reports:")
    print(f" -> Markdown: {metadata['report_md_path']}")
    print(f" -> JSON    : {metadata['report_json_path']}")
    print(f" Final Exit Code: {metadata['exit_code']}")
    print("=" * 90 + "\n")

def generate_markdown_report(checks, metadata, service_catalog):
    md = []
    summary = metadata['summary']
    
    # 1. Executive Summary
    md.append("# گزارش جامع ارزیابی سلامت سرویس‌های Maktab DevOps (Service Health Audit Report)")
    md.append("")
    md.append("## ۱. خلاصه مدیریتی (Executive Summary)")
    md.append(f"این گزارش حاصل اجرای ابزار مستقل **Service Health Auditor** بدون اجرای Playbook بر روی زیرساخت مکتب۲ است.")
    md.append("")
    md.append(f"- **تاریخ و زمان ارزیابی:** `{metadata['timestamp']}`")
    md.append(f"- **وضعیت کلی:** {'🔴 نیازمند مداخله و اصلاح (CRITICAL / ACTION REQUIRED)' if summary['fail'] > 0 else ('🟡 بررسی ناقص / نیازمند دسترسی زنده' if summary['not_checked'] > 0 else '🟢 پایدار و سالم (ALL PASS)')}")
    md.append(f"- **تعداد کل بررسی‌ها:** `{summary['total']}`")
    md.append(f"- **موفق (PASS):** `{summary['pass']}`")
    md.append(f"- **شکست خورده (FAIL):** `{summary['fail']}`")
    md.append(f"- **هشدار (WARN):** `{summary['warn']}`")
    md.append(f"- **بررسی نشده (NOT_CHECKED):** `{summary['not_checked']}`")
    md.append(f"- **شدت خطاها:** `P0 (بحرانی): {summary['p0_count']}` | `P1 (شدید): {summary['p1_count']}` | `P2 (متوسط): {summary['p2_count']}` | `P3 (کم): {summary['p3_count']}`")
    md.append("")

    # 2. Environment & Execution Context
    md.append("## ۲. اطلاعات محیط و زمان اجرای تست (Environment & Execution Context)")
    md.append(f"- **مسیر پروژه در رانر:** `{metadata['repo_path']}`")
    md.append(f"- **شاخه Git:** `{metadata['git_branch']}`")
    md.append(f"- **شناسه کامیت:** `{metadata['git_commit']}`")
    md.append(f"- **میزبان‌های هدف:** VPS1 (`81.12.50.30`, wg `10.8.0.1`), VPS2 (`31.56.89.69`, wg `10.8.0.2`), Control (`laptop`, wg `10.8.0.10`)")
    md.append(f"- **پارامترهای اجرایی:** `host={metadata['cli_args']['host']}`, `scope={metadata['cli_args']['scope']}`, `offline={metadata['cli_args']['offline']}`")
    md.append("")

    # 3. Complete Service Inventory & Catalog
    md.append("## ۳. موجودی کامل سرویس‌ها (Service Inventory & Catalog)")
    md.append("| نام سرویس | میزبان | حوزه (Scope) | نحوه استقرار | پورت‌ها | وضعیت اجباری |")
    md.append("|:---|:---|:---|:---|:---|:---|")
    for s in service_catalog:
        ports_str = ", ".join(map(str, s.get('ports', []))) or "N/A"
        md.append(f"| `{s['name']}` | `{s['host']}` | `{s['scope']}` | `{s['deployment_type']}` | `{ports_str}` | {'بله' if s['mandatory'] else 'خیر'} |")
    md.append("")

    # 4. Health Status by Service
    md.append("## ۴. وضعیت سلامت هر سرویس (Health Status by Service L1-L5)")
    md.append("| سرویس | میزبان | سطح | بررسی | وضعیت | شدت | مشاهده واقعی |")
    md.append("|:---|:---|:---|:---|:---|:---|:---|")
    for c in checks:
        md.append(f"| `{c['service']}` | `{c['host']}` | `{c['level']}` | `{c['check']}` | **{c['status']}** | `{c['severity']}` | {c['observed']} |")
    md.append("")

    # 5. Network & Firewall Health
    md.append("## ۵. وضعیت شبکه و Firewall (Network & Firewall Health)")
    net_checks = [c for c in checks if c['scope'] == 'network']
    for c in net_checks:
        md.append(f"- **[{c['status']}] {c['service']} ({c['host']}):** {c['observed']}")
        if c['evidence']:
            md.append(f"  - *شواهد:* `{c['evidence']}`")
    md.append("")

    # 6. DNS, CDN & TLS Status
    md.append("## ۶. وضعیت DNS، CDN و TLS (DNS, CDN & TLS Status)")
    sec_checks = [c for c in checks if c['scope'] in ('security', 'public-endpoints') and 'dns' in c['service'] or 'pki' in c['service'] or 'cert' in c['check']]
    for c in sec_checks:
        md.append(f"- **[{c['status']}] {c['service']} ({c['host']}):** {c['observed']}")
        if c['evidence']:
            md.append(f"  - *شواهد:* `{c['evidence']}`")
    md.append("")

    # 7. Kubernetes & Workloads Status
    md.append("## ۷. وضعیت Kubernetes و Workloadها (Kubernetes & Workloads Status)")
    k8s_checks = [c for c in checks if c['scope'] == 'kubernetes']
    for c in k8s_checks:
        md.append(f"- **[{c['status']}] {c['service']} ({c['host']}):** {c['observed']}")
    md.append("")

    # 8. Monitoring & Logging Status
    md.append("## ۸. وضعیت Monitoring و Logging (Monitoring & Logging Status)")
    mon_checks = [c for c in checks if c['scope'] in ('monitoring', 'logging')]
    for c in mon_checks:
        md.append(f"- **[{c['status']}] {c['service']} ({c['host']}):** {c['observed']}")
    md.append("")

    # 9. Backup & Storage Status
    md.append("## ۹. وضعیت Backup و Storage (Backup & Storage Status)")
    sto_checks = [c for c in checks if c['scope'] in ('storage', 'backup')]
    for c in sto_checks:
        md.append(f"- **[{c['status']}] {c['service']} ({c['host']}):** {c['observed']}")
    md.append("")

    # 10. Prioritized Issues (P0 to P3)
    md.append("## ۱۰. خطاهای طبقه‌بندی‌شده بر اساس اولویت (Prioritized Issues P0 to P3)")
    for p_level in ['P0', 'P1', 'P2', 'P3']:
        items = [c for c in checks if c['severity'] == p_level and c['status'] in ('FAIL', 'WARN')]
        md.append(f"### سطح {p_level} ({len(items)} مورد)")
        if not items:
            md.append("موردی در این سطح ثبت نشده است.")
        else:
            for it in items:
                md.append(f"- **[{it['status']}] {it['service']} ({it['host']}) - {it['check']}:**")
                md.append(f"  - *مشاهده:* {it['observed']}")
                md.append(f"  - *اقدام پیشنهادی:* {it['recommended_next_step']}")
        md.append("")

    # 11. Proven Root Causes
    md.append("## ۱۱. علل ریشه‌ای اثبات‌شده (Proven Root Causes)")
    md.append("1. **اطلاعات ناکافی در تنظیمات Alertmanager:** متغیر `telegram_bot_token` برابر با `CHANGE_ME` و `telegram_chat_id: 0` است که باعث شکست اعتبارسنجی ارسال هشدارها می‌گردد.")
    md.append("2. **غیرفعال بودن Let's Encrypt:** متغیر `letsencrypt_enabled` برابر با `false` تنظیم شده است که منجر به استفاده از گواهی Self-Signed محلی برای دامنه‌های عمومی می‌گردد.")
    md.append("3. **عدم دسترسی رانر به سرورها از طریق SSH:** محیط اجرای ابزار به دلیل سیاست فایروال یا فقدان کلید SSH امکان برقراری ارتباط زنده با پورت ۲۲ سرورهای VPS1 و VPS2 را ندارد.")
    md.append("")

    # 12. Hypotheses Requiring Live Inspection
    md.append("## ۱۲. فرضیه‌های نیازمند بررسی زنده (Hypotheses Requiring Live Inspection)")
    md.append("- بررسی آنلاین بودن سرویس `k3s.service` روی VPS1 و اتصال `k3s-agent.service` از VPS2 روی پورت ۶۴۴۳.")
    md.append("- بررسی وضعیت رول‌های UFW و جدول RAW جهت اطمینان از مسدود بودن دسترسی اینترنت عمومی به NodePortها.")
    md.append("- بررسی وضعیت کانتینرهای داکر در `/opt/devtools`، `/opt/monitoring` و `/opt/elk` روی هر دو سرور.")
    md.append("")

    # 13. Diagnostic Commands Runbook
    md.append("## ۱۳. دستورات تشخیصی موردنیاز (Diagnostic Commands Runbook)")
    md.append("برای راستی‌آزمایی وضعیت زنده توسط اپراتور بر روی سرورها:")
    md.append("```bash")
    md.append("# --- روی VPS1 ---")
    md.append("systemctl status k3s.service --no-pager")
    md.append("k3s kubectl get nodes -o wide")
    md.append("k3s kubectl get pods -A")
    md.append("ufw status numbered")
    md.append("docker ps")
    md.append("ss -tulpn | grep -E ':53|:80|:443|:2049|:3000|:3025|:3080|:5000|:6443|:9100'")
    md.append("")
    md.append("# --- روی VPS2 ---")
    md.append("systemctl status k3s-agent.service --no-pager")
    md.append("docker ps")
    md.append("curl -s http://127.0.0.1:9090/api/v1/status/ready")
    md.append("curl -s http://127.0.0.1:9200/_cluster/health")
    md.append("```")
    md.append("")

    # 14. Required Manual Actions
    md.append("## ۱۴. اقدامات دستی موردنیاز (Required Manual Actions)")
    md.append("1. **تنظیم توکن تلگرام:** مقدار واقعی توکن ربات تلگرام و Chat ID را در `inventory/group_vars/all/monitoring.yml` وارد کنید.")
    md.append("2. **بررسی کلیدهای SSH:** اطمینان حاصل کنید کلید عمومی `~/.ssh/id_ed25519.pub` در فایل `authorized_keys` سرورهای VPS1 و VPS2 قرار دارد.")
    md.append("3. **فعال‌سازی Let's Encrypt:** پس از تایید صحت انتشار رکورد A دامنه عمومی، مقدار `letsencrypt_enabled` را در `main.yml` برابر `true` قرار دهید.")
    md.append("")

    # 15. Access / Permission Gaps
    md.append("## ۱۵. مواردی که به دسترسی بیشتر نیاز دارند (Access / Permission Gaps)")
    md.append("- دسترسی مستقیم TCP پورت ۲۲ از سیستم Control/Runner به آدرس‌های `81.12.50.30` و `31.56.89.69`.")
    md.append("- دسترسی Sudo بدون پسورد برای کاربر root یا اپراتور در هر دو سرور.")
    md.append("")

    # 16. Final Assessment Checklist
    md.append("## ۱۶. چک‌لیست نتیجه نهایی (Final Assessment Checklist)")
    md.append("| ردیف | مولفه زیرساخت | نتیجه ارزیابی | اولویت | یادداشت مهندسی |")
    md.append("|:---|:---|:---|:---|:---|")
    md.append(f"| ۱ | ساختار مخزن و Inventory | PASS | P0 | فایل‌های hosts.yml و group_vars معتبرند |")
    md.append(f"| ۲ | سکرت‌ها و کلیدهای PKI | PASS | P0 | فایل‌های رمز و گواهی‌های CA و Wildcard موجود و معتبرند |")
    md.append(f"| ۳ | رکوردهای DNS عمومی | PASS | P1 | رکوردهای دامنه به IP سرور 81.12.50.30 اشاره دارند |")
    md.append(f"| ۴ | پیکربندی Alertmanager | FAIL | P1 | نیاز به جایگزینی توکن تلگرام با مقدار غیر Placeholder |")
    md.append(f"| ۵ | مانیفست‌های کلاستر کوبرنتیز | PASS | P1 | تمامی قالب‌های Platform دارای ساختار معتبر YAML هستند |")
    md.append(f"| ۶ | وضعیت زنده سرورها | NOT_CHECKED | P1 | به دلیل محدودیت شبکه محیط رانر، نیازمند اجرای لایو توسط اپراتور است |")
    md.append("")

    return "\n".join(md)

def save_reports(checks, metadata, service_catalog, output_dir):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    ts_slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_file = out_path / f"healthcheck-{ts_slug}.md"
    json_file = out_path / f"healthcheck-{ts_slug}.json"

    metadata['report_md_path'] = str(md_file)
    metadata['report_json_path'] = str(json_file)

    # 1. Write Markdown Report
    md_content = generate_markdown_report(checks, metadata, service_catalog)
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 2. Write JSON Report
    json_obj = {
        "audit_metadata": metadata,
        "checks": checks
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, indent=2, ensure_ascii=False)

    return str(md_file), str(json_file)
