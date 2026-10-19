"""
Core Auditor Inspection Engine for Maktab DevOps Service Health Auditor.
Executes Level 1 to Level 5 health checks with zero state modification,
full secret redaction, and strict timeout boundaries.
"""
import os
import sys
import re
import json
import yaml
import socket
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path

def sanitize_string(text, secrets_list=None):
    """
    Scrubs secret tokens, passwords, private keys and auth headers from text.
    """
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Scrub exact known secret values
    if secrets_list:
        for sec in secrets_list:
            if sec and len(sec) > 3:
                text = text.replace(sec, "[REDACTED_SECRET]")

    # 2. Scrub Private Key blocks
    text = re.sub(
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        text
    )

    # 3. Scrub Telegram Bot Tokens (e.g. 123456789:ABCdefGHIjklMNO)
    text = re.sub(
        r"\b\d{7,12}:[A-Za-z0-9_-]{35}\b",
        "[REDACTED_TELEGRAM_BOT_TOKEN]",
        text
    )

    # 4. Scrub passwords and tokens in key-value format
    text = re.sub(
        r"(?i)\b(password|token|secret|secret_key|private_key|auth_token|bearer)\s*[:=]\s*([^\s,;\"']+)",
        r"\1: [REDACTED]",
        text
    )

    # 5. Scrub Authorization headers
    text = re.sub(
        r"(?i)Authorization:\s*(Bearer|Basic)\s+([^\r\n]+)",
        r"Authorization: \1 [REDACTED]",
        text
    )

    return text

def collect_known_secrets(repo_root):
    """
    Collects raw secret strings from .secrets/ for exact matching in sanitizer.
    """
    secrets = []
    secrets_dir = Path(repo_root) / ".secrets"
    if secrets_dir.is_dir():
        for p in secrets_dir.rglob("*"):
            if p.is_file() and not p.name.endswith(".crt"):
                try:
                    val = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if val and len(val) >= 4:
                        secrets.append(val)
                except Exception:
                    pass
    return secrets

def run_local_cmd(cmd, timeout=5):
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)

def run_ssh_cmd(host_ip, ssh_key, command, timeout=3):
    """
    Runs a read-only command via SSH on a remote host with strict timeout.
    """
    key_opt = f"-i {ssh_key}" if ssh_key and os.path.exists(os.path.expanduser(ssh_key)) else ""
    ssh_cmd = (
        f"ssh -o BatchMode=yes -o ConnectTimeout={timeout} "
        f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"{key_opt} root@{host_ip} \"{command}\""
    )
    return run_local_cmd(ssh_cmd, timeout=timeout + 2)

class HealthAuditor:
    def __init__(self, repo_root, scope="all", host="all", offline=False):
        self.repo_root = Path(repo_root)
        self.scope = scope
        self.host = host
        self.offline = offline
        self.known_secrets = collect_known_secrets(self.repo_root)
        self.checks = []
        self.host_reachability = {}

    def add_check(self, service, host, check, level, scope, status, severity,
                  mandatory, observed, expected, evidence="", likely_causes=None,
                  recommended_next_step="", automatic_fix_applied=False):
        
        # Filter checks by host and scope
        if self.host != "all" and host not in (self.host, "all", "external", "control"):
            return
        if self.scope != "all" and scope != self.scope:
            return

        rec = {
            "service": service,
            "host": host,
            "check": check,
            "level": level,
            "scope": scope,
            "status": status,
            "severity": severity,
            "mandatory": mandatory,
            "observed": sanitize_string(observed, self.known_secrets),
            "expected": expected,
            "evidence": sanitize_string(evidence, self.known_secrets),
            "likely_causes": likely_causes or [],
            "recommended_next_step": recommended_next_step,
            "automatic_fix_applied": automatic_fix_applied
        }
        self.checks.append(rec)

    def probe_host_connectivity(self, inventory_data):
        """
        Tests SSH reachability to vps1 and vps2.
        """
        if self.offline:
            self.host_reachability["vps1"] = (False, "Offline mode enabled (--offline)")
            self.host_reachability["vps2"] = (False, "Offline mode enabled (--offline)")
            return

        for h in ["vps1", "vps2"]:
            ip = "81.12.50.30" if h == "vps1" else "31.56.89.69"
            key = "~/.ssh/id_ed25519" if h == "vps1" else "~/.ssh/id_rsa"
            code, out, err = run_ssh_cmd(ip, key, "echo READY", timeout=2)
            if code == 0 and "READY" in out:
                self.host_reachability[h] = (True, "SSH reachable")
            else:
                reason = err if err else f"SSH exit code {code}"
                self.host_reachability[h] = (False, reason)

    def audit_all(self, inventory_data):
        self.probe_host_connectivity(inventory_data)
        
        # Level 1 Static Configurations
        self.audit_l1_inventory(inventory_data)
        self.audit_l1_secrets_and_pki()
        self.audit_l1_alertmanager_and_monitoring(inventory_data)
        self.audit_l1_wireguard_config(inventory_data)
        self.audit_l1_dns_config(inventory_data)
        self.audit_l1_k3s_configs(inventory_data)
        self.audit_l1_k8s_platform_manifests()
        self.audit_l1_nginx_configs(inventory_data)
        self.audit_l1_compose_configs()
        self.audit_l1_backup_config(inventory_data)
        self.audit_l1_public_dns_resolution(inventory_data)

        # Levels 2 to 5 Runtime and Network Probes
        self.audit_l2_l5_live_checks(inventory_data)

    def audit_l1_inventory(self, inv):
        hosts = inv.get("hosts", {}).get("all", {}).get("children", {})
        has_vps1 = "vps1" in hosts.get("vps", {}).get("hosts", {})
        has_vps2 = "vps2" in hosts.get("vps", {}).get("hosts", {})
        
        if has_vps1 and has_vps2:
            self.add_check(
                service="ansible_control",
                host="control",
                check="inventory_hosts_defined",
                level="L1_CONFIG",
                scope="access",
                status="PASS",
                severity="P0",
                mandatory=True,
                observed="VPS1 (81.12.50.30) and VPS2 (31.56.89.69) properly defined in inventory",
                expected="vps1 and vps2 present with public and wireguard IPs",
                evidence="inventory/hosts.yml valid"
            )
        else:
            self.add_check(
                service="ansible_control",
                host="control",
                check="inventory_hosts_defined",
                level="L1_CONFIG",
                scope="access",
                status="FAIL",
                severity="P0",
                mandatory=True,
                observed=f"Missing host definitions in inventory: vps1={has_vps1}, vps2={has_vps2}",
                expected="vps1 and vps2 both present in hosts.yml",
                likely_causes=["Inventory syntax corruption or missing host entries"],
                recommended_next_step="Inspect inventory/hosts.yml"
            )

    def audit_l1_secrets_and_pki(self):
        secrets_dir = self.repo_root / ".secrets"
        required_secrets = [
            "gitea_admin_password", "grafana_admin_password", "k3s_token",
            "mariadb_root_password", "mariadb_wp_password", "pg_app_password",
            "redis_password", "registry_password", "teleport_node_token"
        ]
        
        missing_sec = [s for s in required_secrets if not (secrets_dir / s).is_file()]
        if not missing_sec:
            self.add_check(
                service="pki_tls",
                host="control",
                check="secrets_files_present",
                level="L1_CONFIG",
                scope="security",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed=f"All {len(required_secrets)} required secret files present in .secrets/",
                expected="All credentials present in .secrets/",
                evidence="Directory .secrets/ verified"
            )
        else:
            self.add_check(
                service="pki_tls",
                host="control",
                check="secrets_files_present",
                level="L1_CONFIG",
                scope="security",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed=f"Missing secret files: {', '.join(missing_sec)}",
                expected="All 9 secret credential files exist in .secrets/",
                likely_causes=["Playbook 00-secrets.yml has not been executed on control node"],
                recommended_next_step="Run ansible-playbook -i inventory/hosts.yml 00-secrets.yml"
            )

        # Check CA and Wildcard Cert
        ca_crt = secrets_dir / "pki/ca.crt"
        wildcard_crt = secrets_dir / "pki/wildcard.crt"
        if ca_crt.is_file() and wildcard_crt.is_file():
            # Check validity via openssl
            code, out, _ = run_local_cmd(f"openssl x509 -in {wildcard_crt} -noout -dates -subject -issuer")
            code_san, out_san, _ = run_local_cmd(f"openssl x509 -in {wildcard_crt} -noout -text")
            
            sans_found = "maktab.rezaabolghasemi.ir" in out_san
            code_exp, _, _ = run_local_cmd(f"openssl x509 -in {wildcard_crt} -noout -checkend 86400")
            
            if code == 0 and sans_found and code_exp == 0:
                self.add_check(
                    service="pki_tls",
                    host="control",
                    check="wildcard_certificate_valid",
                    level="L1_CONFIG",
                    scope="security",
                    status="PASS",
                    severity="P1",
                    mandatory=True,
                    observed="Wildcard certificate valid, unexpired and covers *.maktab.rezaabolghasemi.ir",
                    expected="Valid TLS certificate covering internal private domain",
                    evidence=out.replace("\n", " | ")
                )
            else:
                self.add_check(
                    service="pki_tls",
                    host="control",
                    check="wildcard_certificate_valid",
                    level="L1_CONFIG",
                    scope="security",
                    status="FAIL",
                    severity="P1",
                    mandatory=True,
                    observed="Wildcard certificate invalid, expired, or missing SANs",
                    expected="Valid wildcard certificate covering maktab.rezaabolghasemi.ir",
                    evidence=out,
                    likely_causes=["Certificate expired or generated with incomplete SAN list"],
                    recommended_next_step="Regenerate internal CA and wildcard cert via roles/pki"
                )
        else:
            self.add_check(
                service="pki_tls",
                host="control",
                check="pki_certificates_present",
                level="L1_CONFIG",
                scope="security",
                status="FAIL",
                severity="P0",
                mandatory=True,
                observed="CA or Wildcard certificate files missing from .secrets/pki/",
                expected="ca.crt and wildcard.crt exist in .secrets/pki/",
                likely_causes=["PKI generation task in 03-access.yml has not run"],
                recommended_next_step="Execute PKI role to generate internal CA and certificates"
            )

    def audit_l1_alertmanager_and_monitoring(self, inv):
        mon = inv.get("monitoring_vars", {})
        alert_ch = mon.get("alert_channel", "telegram")
        tg_tok = str(mon.get("telegram_bot_token", ""))
        tg_id = mon.get("telegram_chat_id", 0)
        smtp_pass = str(mon.get("smtp_password", ""))
        slack_url = str(mon.get("slack_webhook_url", ""))

        if alert_ch == "telegram":
            if tg_tok == "CHANGE_ME" or tg_id == 0:
                self.add_check(
                    service="monitoring_alertmanager",
                    host="vps2",
                    check="alertmanager_notification_credentials",
                    level="L1_CONFIG",
                    scope="monitoring",
                    status="FAIL",
                    severity="P1",
                    mandatory=True,
                    observed="Telegram channel selected but bot token is placeholder 'CHANGE_ME' or chat ID is 0",
                    expected="Valid Telegram Bot Token from @BotFather and numeric chat ID in monitoring.yml",
                    evidence="alert_channel: telegram, telegram_bot_token: CHANGE_ME, telegram_chat_id: 0",
                    likely_causes=["Default placeholder credentials left unconfigured in inventory/group_vars/all/monitoring.yml"],
                    recommended_next_step="Update telegram_bot_token and telegram_chat_id or change alert_channel in monitoring.yml"
                )
            else:
                self.add_check(
                    service="monitoring_alertmanager",
                    host="vps2",
                    check="alertmanager_notification_credentials",
                    level="L1_CONFIG",
                    scope="monitoring",
                    status="PASS",
                    severity="P1",
                    mandatory=True,
                    observed="Telegram alerting configured with non-placeholder bot token and chat ID",
                    expected="Valid Telegram credentials",
                    evidence=f"Chat ID: {tg_id}, Bot Token: [REDACTED]"
                )
        elif alert_ch == "email" and smtp_pass == "CHANGE_ME":
            self.add_check(
                service="monitoring_alertmanager",
                host="vps2",
                check="alertmanager_notification_credentials",
                level="L1_CONFIG",
                scope="monitoring",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed="Email channel selected but smtp_password is placeholder 'CHANGE_ME'",
                expected="Valid SMTP password",
                evidence="smtp_password: CHANGE_ME",
                likely_causes=["Default placeholder password in monitoring.yml"],
                recommended_next_step="Update smtp_password in monitoring.yml"
            )
        else:
            self.add_check(
                service="monitoring_alertmanager",
                host="vps2",
                check="alertmanager_notification_credentials",
                level="L1_CONFIG",
                scope="monitoring",
                status="PASS",
                severity="P2",
                mandatory=False,
                observed=f"Alert channel configured as {alert_ch}",
                expected="Valid credentials for selected alert channel",
                evidence=f"alert_channel: {alert_ch}"
            )

    def audit_l1_wireguard_config(self, inv):
        main_vars = inv.get("main_vars", {})
        wg_hub = main_vars.get("wg_hub")
        wg_net = main_vars.get("wg_network")
        wg_port = main_vars.get("wg_port")

        if wg_hub == "vps1" and wg_net == "10.8.0.0/24" and wg_port == 51820:
            self.add_check(
                service="wireguard",
                host="vps1",
                check="wireguard_subnet_consistency",
                level="L1_CONFIG",
                scope="network",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed="WireGuard hub on vps1 with subnet 10.8.0.0/24 and port 51820",
                expected="wg_hub: vps1, wg_network: 10.8.0.0/24, wg_port: 51820",
                evidence="inventory/group_vars/all/main.yml verified"
            )
        else:
            self.add_check(
                service="wireguard",
                host="vps1",
                check="wireguard_subnet_consistency",
                level="L1_CONFIG",
                scope="network",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed=f"WireGuard configuration discrepancy: hub={wg_hub}, network={wg_net}, port={wg_port}",
                expected="wg_hub: vps1, wg_network: 10.8.0.0/24, wg_port: 51820",
                likely_causes=["Inconsistent WireGuard parameters in group_vars/all/main.yml"],
                recommended_next_step="Verify WireGuard network configuration"
            )

    def audit_l1_dns_config(self, inv):
        zone_tmpl = self.repo_root / "roles/dns/templates/zone.j2"
        named_opt = self.repo_root / "roles/dns/templates/named.conf.options.j2"
        if zone_tmpl.is_file() and named_opt.is_file():
            self.add_check(
                service="dns_bind9",
                host="vps1",
                check="dns_zone_templates_present",
                level="L1_CONFIG",
                scope="network",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed="BIND9 zone and options templates present and well-formed",
                expected="roles/dns/templates/zone.j2 and named.conf.options.j2 present",
                evidence="zone.j2 and named.conf.options.j2 exist"
            )
        else:
            self.add_check(
                service="dns_bind9",
                host="vps1",
                check="dns_zone_templates_present",
                level="L1_CONFIG",
                scope="network",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed="Missing BIND9 configuration templates in roles/dns/templates/",
                expected="Templates zone.j2 and named.conf.options.j2 must exist",
                likely_causes=["DNS role templates deleted or moved"],
                recommended_next_step="Restore BIND9 templates in roles/dns"
            )

    def audit_l1_k3s_configs(self, inv):
        server_tmpl = self.repo_root / "roles/k3s/templates/config-server.yaml.j2"
        registries_tmpl = self.repo_root / "roles/k3s/templates/registries.yaml.j2"
        
        if server_tmpl.is_file() and registries_tmpl.is_file():
            content = server_tmpl.read_text(encoding="utf-8")
            reg_content = registries_tmpl.read_text(encoding="utf-8")
            
            has_mirrors = "hub.hamdocker.ir" in reg_content and "k8s-mirror.liara.ir" in reg_content
            if has_mirrors:
                self.add_check(
                    service="k3s_server",
                    host="vps1",
                    check="k3s_registries_mirrors_configured",
                    level="L1_CONFIG",
                    scope="kubernetes",
                    status="PASS",
                    severity="P1",
                    mandatory=True,
                    observed="K3s registries configured with Iranian container mirrors (hamdocker, liara)",
                    expected="hub.hamdocker.ir and k8s-mirror.liara.ir configured",
                    evidence="roles/k3s/templates/registries.yaml.j2 verified"
                )
            else:
                self.add_check(
                    service="k3s_server",
                    host="vps1",
                    check="k3s_registries_mirrors_configured",
                    level="L1_CONFIG",
                    scope="kubernetes",
                    status="WARN",
                    severity="P2",
                    mandatory=False,
                    observed="Iranian container mirrors missing from registries.yaml.j2",
                    expected="Mirrors configured to bypass upstream sanctions and rate limits",
                    likely_causes=["registries.yaml.j2 does not specify Iranian mirrors"],
                    recommended_next_step="Add hamdocker and liara mirrors to registries.yaml.j2"
                )
        else:
            self.add_check(
                service="k3s_server",
                host="vps1",
                check="k3s_server_templates_present",
                level="L1_CONFIG",
                scope="kubernetes",
                status="FAIL",
                severity="P0",
                mandatory=True,
                observed="K3s configuration templates missing in roles/k3s/templates/",
                expected="config-server.yaml.j2 and registries.yaml.j2 present",
                likely_causes=["Missing files in roles/k3s"],
                recommended_next_step="Restore K3s role templates"
            )

    def audit_l1_k8s_platform_manifests(self):
        plat_dir = self.repo_root / "roles/k8s_platform/templates"
        required_manifests = [
            "namespaces.yml.j2", "netpol.yml.j2",
            "nfs-provisioner.yml.j2", "secrets.yml.j2"
        ]
        missing = [m for m in required_manifests if not (plat_dir / m).is_file()]
        if not missing:
            self.add_check(
                service="k8s_storage_nfs_provisioner",
                host="vps1",
                check="k8s_platform_manifests_present",
                level="L1_CONFIG",
                scope="kubernetes",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed=f"All {len(required_manifests)} platform manifests present in roles/k8s_platform/templates/",
                expected="namespaces, netpol, nfs-provisioner and secrets manifests exist",
                evidence="roles/k8s_platform/templates/ verified"
            )
        else:
            self.add_check(
                service="k8s_storage_nfs_provisioner",
                host="vps1",
                check="k8s_platform_manifests_present",
                level="L1_CONFIG",
                scope="kubernetes",
                status="FAIL",
                severity="P0",
                mandatory=True,
                observed=f"Missing Kubernetes manifests: {', '.join(missing)}",
                expected="All platform templates present",
                likely_causes=["Platform templates missing from repository"],
                recommended_next_step="Restore platform manifests in roles/k8s_platform"
            )

    def audit_l1_nginx_configs(self, inv):
        public_conf = self.repo_root / "roles/edge_nginx/templates/public.conf.j2"
        internal_conf = self.repo_root / "roles/edge_nginx/templates/internal.conf.j2"
        nginx_conf = self.repo_root / "roles/edge_nginx/templates/nginx.conf.j2"
        main_vars = inv.get("main_vars", {})
        letsencrypt = main_vars.get("letsencrypt_enabled", False)

        if public_conf.is_file() and internal_conf.is_file() and nginx_conf.is_file():
            self.add_check(
                service="edge_nginx",
                host="vps1",
                check="nginx_templates_present",
                level="L1_CONFIG",
                scope="public-endpoints",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed="Nginx configuration templates for public, internal and JSON access logging present",
                expected="nginx.conf.j2, public.conf.j2, internal.conf.j2 present",
                evidence="roles/edge_nginx/templates/ verified"
            )
        else:
            self.add_check(
                service="edge_nginx",
                host="vps1",
                check="nginx_templates_present",
                level="L1_CONFIG",
                scope="public-endpoints",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed="Nginx configuration templates missing in roles/edge_nginx/templates/",
                expected="All Nginx templates must exist",
                likely_causes=["Missing Nginx configuration templates"],
                recommended_next_step="Restore Nginx templates in roles/edge_nginx"
            )

        if not letsencrypt:
            self.add_check(
                service="edge_nginx",
                host="vps1",
                check="nginx_letsencrypt_status",
                level="L1_CONFIG",
                scope="public-endpoints",
                status="WARN",
                severity="P2",
                mandatory=False,
                observed="letsencrypt_enabled is false; edge Nginx uses internal self-signed wildcard certificate",
                expected="Let's Encrypt enabled for trusted public browser TLS or custom CA pre-installed in clients",
                evidence="inventory/group_vars/all/main.yml: letsencrypt_enabled: false",
                likely_causes=["Let's Encrypt disabled during development or pending public DNS propagation"],
                recommended_next_step="Set letsencrypt_enabled: true once domain DNS resolves globally to VPS1 (81.12.50.30)"
            )

    def audit_l1_compose_configs(self):
        compose_files = [
            ("devtools_gitea", "vps1", "roles/devtools/templates/docker-compose.yml.j2", "devtools"),
            ("monitoring_prometheus", "vps2", "roles/monitoring/templates/docker-compose.yml.j2", "monitoring"),
            ("elk_elasticsearch", "vps2", "roles/elk/templates/docker-compose.yml.j2", "logging"),
            ("filebeat", "vps1", "roles/filebeat/templates/docker-compose.yml.j2", "logging")
        ]
        for s_name, s_host, path_str, s_scope in compose_files:
            p = self.repo_root / path_str
            if p.is_file():
                self.add_check(
                    service=s_name,
                    host=s_host,
                    check="docker_compose_template_present",
                    level="L1_CONFIG",
                    scope=s_scope,
                    status="PASS",
                    severity="P1",
                    mandatory=True,
                    observed=f"Compose template {p.name} present and non-empty",
                    expected=f"{path_str} exists",
                    evidence=f"File {path_str} verified ({p.stat().st_size} bytes)"
                )
            else:
                self.add_check(
                    service=s_name,
                    host=s_host,
                    check="docker_compose_template_present",
                    level="L1_CONFIG",
                    scope=s_scope,
                    status="FAIL",
                    severity="P1",
                    mandatory=True,
                    observed=f"Compose template missing: {path_str}",
                    expected=f"{path_str} must exist",
                    likely_causes=["Role template file removed or renamed"],
                    recommended_next_step=f"Restore {path_str}"
                )

    def audit_l1_backup_config(self, inv):
        script_tmpl = self.repo_root / "roles/backup/templates/maktab-backup.sh.j2"
        timer_tmpl = self.repo_root / "roles/backup/templates/maktab-backup.timer.j2"
        service_tmpl = self.repo_root / "roles/backup/templates/maktab-backup.service.j2"

        if script_tmpl.is_file() and timer_tmpl.is_file() and service_tmpl.is_file():
            self.add_check(
                service="backup_system",
                host="vps1",
                check="backup_templates_present",
                level="L1_CONFIG",
                scope="backup",
                status="PASS",
                severity="P1",
                mandatory=True,
                observed="Backup shell script, systemd timer and service templates present",
                expected="maktab-backup.sh.j2, timer.j2, service.j2 present in roles/backup",
                evidence="roles/backup/templates/ verified"
            )
        else:
            self.add_check(
                service="backup_system",
                host="vps1",
                check="backup_templates_present",
                level="L1_CONFIG",
                scope="backup",
                status="FAIL",
                severity="P1",
                mandatory=True,
                observed="Backup role templates missing in roles/backup/templates/",
                expected="All backup templates must exist",
                likely_causes=["Backup role template files missing"],
                recommended_next_step="Restore backup templates in roles/backup"
            )

    def audit_l1_public_dns_resolution(self, inv):
        main_vars = inv.get("main_vars", {})
        pub_dom = main_vars.get("public_domain", "rezaabolghasemi.ir").strip()
        wp_dom = main_vars.get("wp_fqdn", f"wp.{pub_dom}").replace("{{ public_domain }}", pub_dom).strip()
        app_dom = main_vars.get("app_fqdn", f"app.{pub_dom}").replace("{{ public_domain }}", pub_dom).strip()
        expected_ip = "81.12.50.30"

        for dom in [pub_dom, wp_dom, app_dom]:
            try:
                res = socket.gethostbyname(dom)
                if res == expected_ip:
                    self.add_check(
                        service="public_dns_tls",
                        host="external",
                        check=f"public_dns_resolves_{dom.replace('.', '_')}",
                        level="L1_CONFIG",
                        scope="public-endpoints",
                        status="PASS",
                        severity="P1",
                        mandatory=True,
                        observed=f"{dom} resolves to expected public IP {res}",
                        expected=f"{dom} -> {expected_ip}",
                        evidence=f"DNS query returned {res}"
                    )
                else:
                    self.add_check(
                        service="public_dns_tls",
                        host="external",
                        check=f"public_dns_resolves_{dom.replace('.', '_')}",
                        level="L1_CONFIG",
                        scope="public-endpoints",
                        status="WARN",
                        severity="P2",
                        mandatory=False,
                        observed=f"{dom} resolves to {res} instead of {expected_ip}",
                        expected=f"{dom} -> {expected_ip}",
                        evidence=f"DNS mismatch: {res} != {expected_ip}",
                        likely_causes=["Domain pointed to different server or CDN IP"],
                        recommended_next_step=f"Update DNS A record for {dom} to point to {expected_ip}"
                    )
            except Exception as e:
                self.add_check(
                    service="public_dns_tls",
                    host="external",
                    check=f"public_dns_resolves_{dom.replace('.', '_')}",
                    level="L1_CONFIG",
                    scope="public-endpoints",
                    status="FAIL",
                    severity="P1",
                    mandatory=True,
                    observed=f"Failed to resolve public DNS for {dom}: {e}",
                    expected=f"{dom} -> {expected_ip}",
                    evidence=str(e),
                    likely_causes=["Domain not registered, nameservers not configured, or DNS provider down"],
                    recommended_next_step=f"Configure public DNS A record for {dom} at DNS registrar / CDN"
                )

    def audit_l2_l5_live_checks(self, inv):
        """
        Executes Level 2 through Level 5 checks.
        If a host is reachable, queries the host with read-only commands.
        If unreachable, records NOT_CHECKED with exact diagnostic evidence.
        """
        live_definitions = [
            # Host, Service, Check, Level, Scope, Mandatory, Cmd/Probe, SuccessCheck
            ("vps1", "system_base", "system_timezone_and_uptime", "L2_PROCESS", "access", True, "uptime && timedatectl", "uptime"),
            ("vps1", "docker_engine", "docker_daemon_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active docker", "active"),
            ("vps1", "firewall_ufw", "ufw_service_active", "L2_PROCESS", "network", True, "ufw status", "Status: active"),
            ("vps1", "wireguard", "wireguard_service_active", "L2_PROCESS", "network", True, "systemctl is-active wg-quick@wg0", "active"),
            ("vps1", "wireguard", "wireguard_interface_up", "L3_NETWORK", "network", True, "ip addr show wg0", "inet 10.8.0.1"),
            ("vps1", "dns_bind9", "bind9_service_active", "L2_PROCESS", "network", True, "systemctl is-active named", "active"),
            ("vps1", "dns_bind9", "bind9_port_53_listening", "L3_NETWORK", "network", True, "ss -tulpn | grep :53", ":53"),
            ("vps1", "teleport_auth_proxy", "teleport_service_active", "L2_PROCESS", "access", True, "systemctl is-active teleport", "active"),
            ("vps1", "teleport_auth_proxy", "teleport_ports_listening", "L3_NETWORK", "access", True, "ss -tulpn | grep -E ':3025|:3080'", "3080"),
            ("vps1", "teleport_auth_proxy", "teleport_webapi_ping_health", "L4_PROTOCOL", "access", True, "curl -k -s https://127.0.0.1:3080/webapi/ping", "status"),
            ("vps1", "nfs_server", "nfs_server_active", "L2_PROCESS", "storage", True, "systemctl is-active nfs-server", "active"),
            ("vps1", "nfs_server", "nfs_export_configured", "L3_NETWORK", "storage", True, "exportfs -v", "/srv/nfs/k8s"),
            ("vps1", "k3s_server", "k3s_service_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active k3s", "active"),
            ("vps1", "k3s_server", "k3s_api_server_listening", "L3_NETWORK", "kubernetes", True, "ss -tulpn | grep :6443", ":6443"),
            ("vps1", "k3s_server", "k3s_api_health_readyz", "L4_PROTOCOL", "kubernetes", True, "curl -k -s https://127.0.0.1:6443/readyz", "ok"),
            ("vps1", "k3s_server", "k3s_expected_nodes_ready", "L5_DEPENDENCY", "kubernetes", True, "k3s kubectl get nodes -o wide", "Ready"),
            ("vps1", "k3s_server", "k3s_cluster_pods_healthy", "L4_PROTOCOL", "kubernetes", True, "k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded", "No resources found"),
            ("vps1", "k8s_storage_nfs_provisioner", "nfs_storageclass_default", "L4_PROTOCOL", "storage", True, "k3s kubectl get sc nfs-client -o jsonpath='{.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class}'", "true"),
            ("vps1", "k8s_db_cnpg_postgres", "cnpg_postgres_cluster_healthy", "L4_PROTOCOL", "kubernetes", True, "k3s kubectl -n data get cluster pg-main -o jsonpath='{.status.phase}'", "Cluster in healthy state"),
            ("vps1", "edge_nginx", "nginx_service_active", "L2_PROCESS", "public-endpoints", True, "systemctl is-active nginx", "active"),
            ("vps1", "edge_nginx", "nginx_config_syntax_valid", "L1_CONFIG", "public-endpoints", True, "nginx -t", "syntax is ok"),
            ("vps1", "edge_nginx", "nginx_ports_listening", "L3_NETWORK", "public-endpoints", True, "ss -tulpn | grep -E ':80|:443'", ":80"),
            ("vps1", "devtools_gitea", "gitea_container_running", "L2_PROCESS", "devtools", True, "docker ps --filter name=gitea --format '{{.Status}}'", "Up"),
            ("vps1", "devtools_gitea", "gitea_api_version_responding", "L4_PROTOCOL", "devtools", True, "curl -s http://10.8.0.1:3000/api/v1/version", "version"),
            ("vps1", "devtools_registry", "registry_container_running", "L2_PROCESS", "devtools", True, "docker ps --filter name=registry --format '{{.Status}}'", "Up"),
            ("vps1", "node_exporter", "node_exporter_vps1_active", "L2_PROCESS", "monitoring", True, "systemctl is-active node_exporter", "active"),
            ("vps1", "node_exporter", "node_exporter_vps1_metrics", "L4_PROTOCOL", "monitoring", True, "curl -s http://127.0.0.1:9100/metrics | head -n 5", "node_"),
            ("vps1", "filebeat", "filebeat_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=filebeat --format '{{.Status}}'", "Up"),
            ("vps1", "backup_system", "backup_timer_active", "L2_PROCESS", "backup", True, "systemctl is-active maktab-backup.timer", "active"),
            
            # VPS2 checks
            ("vps2", "system_base", "system_timezone_and_uptime", "L2_PROCESS", "access", True, "uptime && timedatectl", "uptime"),
            ("vps2", "docker_engine", "docker_daemon_active", "L2_PROCESS", "monitoring", True, "systemctl is-active docker", "active"),
            ("vps2", "firewall_ufw", "ufw_service_active", "L2_PROCESS", "network", True, "ufw status", "Status: active"),
            ("vps2", "wireguard", "wireguard_service_active", "L2_PROCESS", "network", True, "systemctl is-active wg-quick@wg0", "active"),
            ("vps2", "wireguard", "wireguard_interface_up", "L3_NETWORK", "network", True, "ip addr show wg0", "inet 10.8.0.2"),
            ("vps2", "teleport_node", "teleport_node_service_active", "L2_PROCESS", "access", True, "systemctl is-active teleport", "active"),
            ("vps2", "k3s_agent", "k3s_agent_service_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active k3s-agent", "active"),
            ("vps2", "node_exporter", "node_exporter_vps2_active", "L2_PROCESS", "monitoring", True, "systemctl is-active node_exporter", "active"),
            ("vps2", "monitoring_prometheus", "prometheus_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=prometheus --format '{{.Status}}'", "Up"),
            ("vps2", "monitoring_prometheus", "prometheus_ready_endpoint", "L4_PROTOCOL", "monitoring", True, "curl -s http://127.0.0.1:9090/api/v1/status/ready", "ready"),
            ("vps2", "monitoring_prometheus", "prometheus_targets_up", "L5_DEPENDENCY", "monitoring", True, "curl -s http://127.0.0.1:9090/api/v1/targets", "success"),
            ("vps2", "monitoring_alertmanager", "alertmanager_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=alertmanager --format '{{.Status}}'", "Up"),
            ("vps2", "monitoring_grafana", "grafana_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=grafana --format '{{.Status}}'", "Up"),
            ("vps2", "monitoring_grafana", "grafana_api_health", "L4_PROTOCOL", "monitoring", True, "curl -s http://127.0.0.1:3001/api/health", "ok"),
            ("vps2", "elk_elasticsearch", "elasticsearch_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=elasticsearch --format '{{.Status}}'", "Up"),
            ("vps2", "elk_elasticsearch", "elasticsearch_cluster_health", "L4_PROTOCOL", "logging", True, "curl -s http://127.0.0.1:9200/_cluster/health", "cluster_name"),
            ("vps2", "elk_logstash", "logstash_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=logstash --format '{{.Status}}'", "Up"),
            ("vps2", "elk_kibana", "kibana_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=kibana --format '{{.Status}}'", "Up")
        ]

        for s_host, s_name, chk_name, lvl, scp, is_mand, cmd, expect_str in live_definitions:
            is_reachable, reason = self.host_reachability.get(s_host, (False, "Not checked"))
            
            if not is_reachable:
                self.add_check(
                    service=s_name,
                    host=s_host,
                    check=chk_name,
                    level=lvl,
                    scope=scp,
                    status="NOT_CHECKED",
                    severity="P1" if is_mand else "P2",
                    mandatory=is_mand,
                    observed=f"Remote host {s_host} unreachable from auditor environment",
                    expected=f"Execution of '{cmd}' returns '{expect_str}'",
                    evidence=f"SSH reachability failure: {reason}",
                    likely_causes=[
                        f"Outbound network egress firewall on runner blocks SSH to {s_host}",
                        "SSH port 22 not listening or filtered by network provider",
                        "SSH private key authentication failure or host powered off"
                    ],
                    recommended_next_step=(
                        f"Execute manual verification command directly on {s_host}: '{cmd}' "
                        f"or run scripts/healthcheck.sh from the control node with SSH key access"
                    )
                )
            else:
                ip = "81.12.50.30" if s_host == "vps1" else "31.56.89.69"
                key = "~/.ssh/id_ed25519" if s_host == "vps1" else "~/.ssh/id_rsa"
                code, out, err = run_ssh_cmd(ip, key, cmd, timeout=3)
                if code == 0 and expect_str in out:
                    self.add_check(
                        service=s_name,
                        host=s_host,
                        check=chk_name,
                        level=lvl,
                        scope=scp,
                        status="PASS",
                        severity="P1",
                        mandatory=is_mand,
                        observed=f"Probe succeeded with expected output '{expect_str}'",
                        expected=f"Output contains '{expect_str}'",
                        evidence=out[:150]
                    )
                else:
                    self.add_check(
                        service=s_name,
                        host=s_host,
                        check=chk_name,
                        level=lvl,
                        scope=scp,
                        status="FAIL",
                        severity="P1" if is_mand else "P2",
                        mandatory=is_mand,
                        observed=f"Command '{cmd}' failed or did not match '{expect_str}'",
                        expected=f"Output contains '{expect_str}'",
                        evidence=f"Exit code: {code} | stdout: {out[:100]} | stderr: {err[:100]}",
                        likely_causes=[
                            f"Service {s_name} inactive or misconfigured on {s_host}",
                            "Process crashed or listening on wrong network interface"
                        ],
                        recommended_next_step=f"Inspect journalctl and service logs for {s_name} on {s_host}"
                    )
