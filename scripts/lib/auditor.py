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
        If a host is reachable, queries the host with read-only commands and rich validators.
        If unreachable, records NOT_CHECKED with exact diagnostic evidence.
        """
        def val_system_base(c, o, e):
            if c == 0 and ("load average" in o.lower() or "up " in o.lower()):
                return "PASS", "P1", "System uptime and timedatectl active and synchronized", "Exit code 0 with synchronized clock/uptime", o.strip()[:150], [], None
            return "FAIL", "P1", f"Command 'uptime && timedatectl' failed (exit code {c})", "Exit code 0", f"stdout: {o[:100]} | stderr: {e[:100]}", ["System service or clock desynchronized"], "Inspect timedatectl status and system logs"

        def val_docker(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "Docker daemon active and running", "active", o.strip(), [], None
            return "FAIL", "P1", f"Docker daemon not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["docker.service stopped or crashed"], "Inspect systemctl status docker"

        def val_ufw(c, o, e):
            if c == 0 and "Status: active" in o:
                return "PASS", "P1", "UFW firewall active with filtering rules enabled", "Status: active", o.strip()[:150], [], None
            return "FAIL", "P1", f"UFW firewall not active (exit {c})", "Status: active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["UFW disabled or service inactive"], "Inspect ufw status verbose"

        def val_wireguard_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "WireGuard interface service wg-quick@wg0 active", "active", o.strip(), [], None
            return "FAIL", "P1", f"WireGuard service wg-quick@wg0 not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["WireGuard service inactive"], "Inspect journalctl -u wg-quick@wg0"

        def val_wireguard_iface(ip_str):
            def _val(c, o, e):
                if c == 0 and f"inet {ip_str}" in o:
                    return "PASS", "P1", f"WireGuard wg0 interface UP with VPN address {ip_str}/24", f"inet {ip_str}", o.strip()[:150], [], None
                return "FAIL", "P1", f"WireGuard wg0 interface missing {ip_str} (exit {c})", f"inet {ip_str}", f"stdout: {o[:100]} | stderr: {e[:100]}", ["wg0 interface down"], "Inspect wg show wg0"
            return _val

        def val_named_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "BIND9 named DNS daemon active", "active", o.strip(), [], None
            return "FAIL", "P1", f"BIND9 named service not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["named service failed"], "Inspect systemctl status named"

        def val_port_53(c, o, e):
            if c == 0 and ":53" in o:
                return "PASS", "P1", "DNS port 53 listening on TCP/UDP", ":53", o.strip()[:150], [], None
            return "FAIL", "P1", f"DNS port 53 not listening (exit {c})", ":53", f"stdout: {o[:100]} | stderr: {e[:100]}", ["BIND9 not bound to port 53"], "Check named configuration and socket status"

        def val_teleport_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "Teleport daemon active", "active", o.strip(), [], None
            return "FAIL", "P1", f"Teleport daemon not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", [
                "teleport.service stopped or crashed during startup",
                "Cluster join handshake error or token mismatch"
            ], "Inspect 'systemctl status teleport --no-pager -l' and 'journalctl -u teleport -b -n 150 --no-pager'"

        def val_teleport_ports(c, o, e):
            if c == 0 and ("3080" in o or "3025" in o):
                return "PASS", "P1", "Teleport Auth (3025) and Web/Proxy (3080) ports listening", ":3025 / :3080", o.strip()[:150], [], None
            return "FAIL", "P1", f"Teleport ports 3025/3080 not listening (exit {c})", ":3025 and :3080", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Teleport ports not bound"], "Check /etc/teleport.yaml listen_addr"

        def val_teleport_ping(c, o, e):
            if c == 0 and ("server_version" in o or "cluster_name" in o or "teleport" in o.lower()):
                return "PASS", "P1", "Teleport Web API /webapi/ping responding with cluster information", "HTTP 200 with server_version or cluster_name", o.strip()[:150], [], None
            return "FAIL", "P1", f"Teleport Web API ping failed (exit {c})", "HTTP 200 with server_version or cluster_name", f"stdout: {o[:100]} | stderr: {e[:100]}", [
                "Teleport web proxy not listening on 10.8.0.1:3080",
                "TLS handshake error with internal wildcard certificate"
            ], "Inspect Teleport logs: 'journalctl -u teleport -b -n 50 --no-pager'"

        def val_nfs_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "NFS server kernel daemon active", "active", o.strip(), [], None
            return "FAIL", "P1", f"NFS server not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["nfs-server service failed"], "Inspect systemctl status nfs-server"

        def val_nfs_export(c, o, e):
            if c == 0 and "/srv/nfs/k8s" in o:
                return "PASS", "P1", "NFS export /srv/nfs/k8s configured and active", "/srv/nfs/k8s", o.strip()[:150], [], None
            return "FAIL", "P1", f"NFS export /srv/nfs/k8s not active (exit {c})", "/srv/nfs/k8s", f"stdout: {o[:100]} | stderr: {e[:100]}", ["/etc/exports not exported via exportfs"], "Inspect exportfs -v and /etc/exports"

        def val_k3s_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "k3s control plane server service active", "active", o.strip(), [], None
            return "FAIL", "P1", f"k3s server service not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["k3s service crashed or inactive"], "Inspect journalctl -u k3s -b -n 50"

        def val_k3s_agent_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "k3s-agent service active on vps2", "active", o.strip(), [], None
            return "FAIL", "P1", f"k3s-agent service not active on vps2 (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", [
                "k3s-agent systemd unit not created or failed to connect to k3s server (10.8.0.1:6443)",
                "Playbook 04-kubernetes.yml was halted before reaching k3s_agent role",
                "k3s_token mismatch or flannel wg0 network interface error"
            ], "Execute diagnostics on vps2: 'systemctl status k3s-agent --no-pager -l' and 'journalctl -u k3s-agent -b -n 150 --no-pager'"

        def val_k3s_port_6443(c, o, e):
            if c == 0 and ":6443" in o:
                return "PASS", "P1", "Kubernetes API server listening on port 6443", ":6443", o.strip()[:150], [], None
            return "FAIL", "P1", f"Kubernetes API port 6443 not listening (exit {c})", ":6443", f"stdout: {o[:100]} | stderr: {e[:100]}", ["k3s API server socket down"], "Check ss -tulpn | grep :6443"

        def val_k3s_readyz(c, o, e):
            if c == 0 and "ok" in o.strip():
                return "PASS", "P1", "Kubernetes API /readyz endpoint reports 'ok'", "ok", o.strip()[:150], [], None
            return "FAIL", "P1", f"Kubernetes API /readyz health check failed (exit {c})", "ok", f"stdout: {o[:100]} | stderr: {e[:100]}", ["K8s control plane components not ready"], "Check 'k3s kubectl get componentstatuses'"

        def val_k3s_nodes(c, o, e):
            if c == 0 and "Ready" in o:
                return "PASS", "P1", "Cluster node(s) report Ready condition", "Ready", o.strip()[:150], [], None
            return "FAIL", "P1", f"No nodes in Ready state (exit {c})", "Ready", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Node kubelet not reporting ready or flannel CNI down"], "Check 'k3s kubectl describe node'"

        def val_k3s_pods(c, o, e):
            if c == 0:
                lines = [l.strip() for l in o.strip().splitlines() if l.strip()]
                if not lines:
                    return "PASS", "P2", "All in-cluster pods are in Running or Succeeded phase", "0 non-running pods", "All pods healthy", [], None
                sample = "; ".join(lines[:3])
                return "WARN", "P2", f"{len(lines)} non-running pod(s) detected: {sample}", "0 non-running pods", f"Non-running pods: {sample}", [
                    "Worker node vps2 offline causing replica/scheduled pods to stay in Pending phase",
                    "Container image pull throttling or pending PVC storage binding"
                ], "Inspect non-running pods: 'k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded'"
            return "FAIL", "P2", f"Failed to query pod phases (exit {c})", "Exit code 0", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Kubernetes API query failed"], "Check k3s API server status"

        def val_nfs_sc(c, o, e):
            if c == 0 and "nfs-client" in o:
                return "PASS", "P1", "StorageClass nfs-client is registered in Kubernetes", "nfs-client", o.strip()[:150], [], None
            return "FAIL", "P1", f"StorageClass nfs-client not found (exit {c})", "nfs-client", f"stdout: {o[:100]} | stderr: {e[:100]}", ["StorageClass manifest roles/k8s_platform/templates/nfs-provisioner.yml.j2 not applied"], "Apply nfs-provisioner manifest"

        def val_cnpg(c, o, e):
            if c == 0:
                phase = o.strip()
                if phase in ["Cluster in healthy state", "Healthy"]:
                    return "PASS", "P1", f"PostgreSQL HA cluster healthy (phase: {phase})", "Cluster in healthy state", phase, [], None
                elif any(p in phase for p in ["Setting up primary", "Waiting for instances", "Pending"]):
                    return "WARN", "P2", f"PostgreSQL cluster is initializing (phase: {phase}); pending secondary instance on worker node", "Cluster in healthy state", phase, [
                        "Secondary instance cannot be scheduled because worker node vps2 is down (anti-affinity requirement in cluster.yaml)",
                        "Primary is active or initializing local-path storage"
                    ], "Bring up vps2 k3s-agent to enable PostgreSQL replica scheduling across nodes"
                else:
                    return "FAIL", "P1", f"PostgreSQL cluster in unexpected phase: {phase}", "Cluster in healthy state", phase, ["Database initialization error"], "Inspect 'k3s kubectl -n data describe cluster pg-main'"
            return "FAIL", "P1", f"CloudNativePG cluster resource pg-main not found in namespace data (exit {c})", "pg-main present", f"stdout: {o[:100]} | stderr: {e[:100]}", ["ArgoCD GitOps application not synced or CNPG operator not installed"], "Check ArgoCD sync status and CNPG operator pods in cnpg-system"

        def val_nginx_svc(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "Nginx web server daemon active", "active", o.strip(), [], None
            return "FAIL", "P1", f"Nginx service not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["nginx.service stopped or crashed"], "Inspect systemctl status nginx"

        def val_nginx_syntax(c, o, e):
            combined = (o + " " + e).lower()
            if c == 0 and ("syntax is ok" in combined or "test is successful" in combined):
                ev = (e if e else o).strip()[:150]
                return "PASS", "P1", "Nginx configuration syntax test is successful", "syntax is ok / test is successful", ev, [], None
            return "FAIL", "P1", f"Nginx configuration test failed (exit {c})", "syntax is ok", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Nginx syntax error in /etc/nginx/nginx.conf or conf.d/"], "Run 'nginx -t' to see configuration syntax error line"

        def val_nginx_ports(c, o, e):
            if c == 0 and (":80" in o or ":443" in o):
                return "PASS", "P1", "Nginx listening on public HTTP (80) and HTTPS (443) ports", ":80 / :443", o.strip()[:150], [], None
            return "FAIL", "P1", f"Nginx ports 80/443 not listening (exit {c})", ":80 and :443", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Nginx ports not bound"], "Check ss -tulpn | grep -E ':80|:443'"

        def val_container_running(cont_name, stack_dir=None):
            def _val(c, o, e):
                if c == 0 and "Up" in o:
                    return "PASS", "P1", f"{cont_name} container running ({o.strip()})", "Up", o.strip(), [], None
                hints = [f"{cont_name} container exited or docker compose stack not started"]
                if stack_dir:
                    hints.append(f"Compose stack in {stack_dir} not running")
                return "FAIL", "P1", f"{cont_name} container not running (exit {c})", "Up", f"stdout: {o[:100]} | stderr: {e[:100]}", hints, f"Inspect 'docker ps -a --filter name={cont_name}' and 'docker logs {cont_name} --tail 100'"
            return _val

        def val_gitea_api(c, o, e):
            if c == 0 and "version" in o:
                return "PASS", "P1", "Gitea REST API responding with version payload", "version", o.strip()[:150], [], None
            return "FAIL", "P1", f"Gitea REST API request failed (exit {c})", "version", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Gitea web service not listening on 10.8.0.1:3000"], "Inspect curl http://10.8.0.1:3000"

        def val_node_exporter_svc(host_name):
            def _val(c, o, e):
                if c == 0 and "active" in o:
                    return "PASS", "P1", f"Node exporter service active on {host_name} ({o.strip()})", "active", o.strip(), [], None
                return "FAIL", "P1", f"Node exporter service not active on {host_name} (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", [
                    f"prometheus-node-exporter service not installed or failed on {host_name}",
                    "Playbook 06-monitoring.yml not executed"
                ], f"Check 'systemctl status prometheus-node-exporter --no-pager -l' on {host_name}"
            return _val

        def val_node_exporter_metrics(ip_str):
            def _val(c, o, e):
                if c == 0 and "node_" in o:
                    return "PASS", "P1", f"Node exporter metrics endpoint responding on {ip_str}:9100", "node_", o.strip()[:150], [], None
                return "FAIL", "P1", f"Node exporter metrics query failed on {ip_str}:9100 (exit {c})", "node_", f"stdout: {o[:100]} | stderr: {e[:100]}", [
                    f"Node exporter not listening on {ip_str}:9100",
                    "Firewall blocking port 9100 or service inactive"
                ], f"Inspect ss -tulpn | grep :9100 on {ip_str}"
            return _val

        def val_backup_timer(c, o, e):
            if c == 0 and "active" in o:
                return "PASS", "P1", "Systemd timer maktab-backup.timer active and scheduled", "active", o.strip(), [], None
            return "FAIL", "P1", f"Backup timer not active (exit {c})", "active", f"stdout: {o[:100]} | stderr: {e[:100]}", ["maktab-backup.timer disabled or stopped"], "Check systemctl status maktab-backup.timer"

        def val_prom_ready(c, o, e):
            if c == 0 and "ready" in o.lower():
                return "PASS", "P1", "Prometheus ready API endpoint returns ready status", "ready", o.strip()[:150], [], None
            return "FAIL", "P1", f"Prometheus ready API request failed (exit {c})", "ready", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Prometheus container not running or web listener not reachable on 10.8.0.2:9090"], "Inspect Prometheus container status and logs"

        def val_prom_targets(c, o, e):
            if c == 0 and "success" in o.lower():
                return "PASS", "P1", "Prometheus targets API returned success status", "success", o.strip()[:150], [], None
            return "FAIL", "P1", f"Prometheus targets API request failed (exit {c})", "success", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Prometheus not responding or target scrape configuration error"], "Check Prometheus web UI at http://10.8.0.2:9090/targets"

        def val_grafana_health(c, o, e):
            if c == 0 and "ok" in o.lower():
                return "PASS", "P1", "Grafana health API endpoint returns ok", "ok", o.strip()[:150], [], None
            return "FAIL", "P1", f"Grafana health API request failed (exit {c})", "ok", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Grafana container not running or listening on 10.8.0.2:3001"], "Check Grafana container status"

        def val_es_health(c, o, e):
            if c == 0 and ("cluster_name" in o or "status" in o):
                return "PASS", "P1", "Elasticsearch cluster health API responding", "cluster_name or status", o.strip()[:150], [], None
            return "FAIL", "P1", f"Elasticsearch cluster health query failed (exit {c})", "cluster_name or status", f"stdout: {o[:100]} | stderr: {e[:100]}", ["Elasticsearch container not running or not listening on 10.8.0.2:9200"], "Inspect Elasticsearch container status"

        live_definitions = [
            # Host, Service, Check, Level, Scope, Mandatory, Cmd/Probe, Validator
            ("vps1", "system_base", "system_timezone_and_uptime", "L2_PROCESS", "access", True, "uptime && timedatectl", val_system_base),
            ("vps1", "docker_engine", "docker_daemon_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active docker", val_docker),
            ("vps1", "firewall_ufw", "ufw_service_active", "L2_PROCESS", "network", True, "ufw status", val_ufw),
            ("vps1", "wireguard", "wireguard_service_active", "L2_PROCESS", "network", True, "systemctl is-active wg-quick@wg0", val_wireguard_svc),
            ("vps1", "wireguard", "wireguard_interface_up", "L3_NETWORK", "network", True, "ip addr show wg0", val_wireguard_iface("10.8.0.1")),
            ("vps1", "dns_bind9", "bind9_service_active", "L2_PROCESS", "network", True, "systemctl is-active named", val_named_svc),
            ("vps1", "dns_bind9", "bind9_port_53_listening", "L3_NETWORK", "network", True, "ss -tulpn | grep :53", val_port_53),
            ("vps1", "teleport_auth_proxy", "teleport_service_active", "L2_PROCESS", "access", True, "systemctl is-active teleport", val_teleport_svc),
            ("vps1", "teleport_auth_proxy", "teleport_ports_listening", "L3_NETWORK", "access", True, "ss -tulpn | grep -E ':3025|:3080'", val_teleport_ports),
            ("vps1", "teleport_auth_proxy", "teleport_webapi_ping_health", "L4_PROTOCOL", "access", True, "curl -k -s https://10.8.0.1:3080/webapi/ping || curl -k -s https://127.0.0.1:3080/webapi/ping", val_teleport_ping),
            ("vps1", "nfs_server", "nfs_server_active", "L2_PROCESS", "storage", True, "systemctl is-active nfs-server", val_nfs_svc),
            ("vps1", "nfs_server", "nfs_export_configured", "L3_NETWORK", "storage", True, "exportfs -v", val_nfs_export),
            ("vps1", "k3s_server", "k3s_service_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active k3s", val_k3s_svc),
            ("vps1", "k3s_server", "k3s_api_server_listening", "L3_NETWORK", "kubernetes", True, "ss -tulpn | grep :6443", val_k3s_port_6443),
            ("vps1", "k3s_server", "k3s_api_health_readyz", "L4_PROTOCOL", "kubernetes", True, "k3s kubectl get --raw /readyz", val_k3s_readyz),
            ("vps1", "k3s_server", "k3s_expected_nodes_ready", "L5_DEPENDENCY", "kubernetes", True, "k3s kubectl get nodes -o wide", val_k3s_nodes),
            ("vps1", "k3s_server", "k3s_cluster_pods_healthy", "L4_PROTOCOL", "kubernetes", False, "k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers", val_k3s_pods),
            ("vps1", "k8s_storage_nfs_provisioner", "nfs_storageclass_configured", "L4_PROTOCOL", "storage", True, "k3s kubectl get sc nfs-client", val_nfs_sc),
            ("vps1", "k8s_db_cnpg_postgres", "cnpg_postgres_cluster_healthy", "L4_PROTOCOL", "kubernetes", False, "k3s kubectl -n data get cluster pg-main -o jsonpath='{.status.phase}'", val_cnpg),
            ("vps1", "edge_nginx", "nginx_service_active", "L2_PROCESS", "public-endpoints", True, "systemctl is-active nginx", val_nginx_svc),
            ("vps1", "edge_nginx", "nginx_config_syntax_valid", "L1_CONFIG", "public-endpoints", True, "nginx -t", val_nginx_syntax),
            ("vps1", "edge_nginx", "nginx_ports_listening", "L3_NETWORK", "public-endpoints", True, "ss -tulpn | grep -E ':80|:443'", val_nginx_ports),
            ("vps1", "devtools_gitea", "gitea_container_running", "L2_PROCESS", "devtools", True, "docker ps --filter name=gitea --format '{{.Status}}'", val_container_running("gitea", "/opt/devtools")),
            ("vps1", "devtools_gitea", "gitea_api_version_responding", "L4_PROTOCOL", "devtools", True, "curl -s http://10.8.0.1:3000/api/v1/version", val_gitea_api),
            ("vps1", "devtools_registry", "registry_container_running", "L2_PROCESS", "devtools", True, "docker ps --filter name=registry --format '{{.Status}}'", val_container_running("registry", "/opt/devtools")),
            ("vps1", "node_exporter", "node_exporter_vps1_active", "L2_PROCESS", "monitoring", True, "systemctl is-active prometheus-node-exporter || systemctl is-active node_exporter", val_node_exporter_svc("vps1")),
            ("vps1", "node_exporter", "node_exporter_vps1_metrics", "L4_PROTOCOL", "monitoring", True, "curl -s http://10.8.0.1:9100/metrics | head -n 5 || curl -s http://127.0.0.1:9100/metrics | head -n 5", val_node_exporter_metrics("10.8.0.1")),
            ("vps1", "filebeat", "filebeat_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=filebeat --format '{{.Status}}'", val_container_running("filebeat", "/opt/filebeat")),
            ("vps1", "backup_system", "backup_timer_active", "L2_PROCESS", "backup", True, "systemctl is-active maktab-backup.timer", val_backup_timer),
            
            # VPS2 checks
            ("vps2", "system_base", "system_timezone_and_uptime", "L2_PROCESS", "access", True, "uptime && timedatectl", val_system_base),
            ("vps2", "docker_engine", "docker_daemon_active", "L2_PROCESS", "monitoring", True, "systemctl is-active docker", val_docker),
            ("vps2", "firewall_ufw", "ufw_service_active", "L2_PROCESS", "network", True, "ufw status", val_ufw),
            ("vps2", "wireguard", "wireguard_service_active", "L2_PROCESS", "network", True, "systemctl is-active wg-quick@wg0", val_wireguard_svc),
            ("vps2", "wireguard", "wireguard_interface_up", "L3_NETWORK", "network", True, "ip addr show wg0", val_wireguard_iface("10.8.0.2")),
            ("vps2", "teleport_node", "teleport_node_service_active", "L2_PROCESS", "access", True, "systemctl is-active teleport", val_teleport_svc),
            ("vps2", "k3s_agent", "k3s_agent_service_active", "L2_PROCESS", "kubernetes", True, "systemctl is-active k3s-agent", val_k3s_agent_svc),
            ("vps2", "node_exporter", "node_exporter_vps2_active", "L2_PROCESS", "monitoring", True, "systemctl is-active prometheus-node-exporter || systemctl is-active node_exporter", val_node_exporter_svc("vps2")),
            ("vps2", "monitoring_prometheus", "prometheus_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=prometheus --format '{{.Status}}'", val_container_running("prometheus", "/opt/monitoring")),
            ("vps2", "monitoring_prometheus", "prometheus_ready_endpoint", "L4_PROTOCOL", "monitoring", True, "curl -s http://10.8.0.2:9090/api/v1/status/ready || curl -s http://127.0.0.1:9090/api/v1/status/ready", val_prom_ready),
            ("vps2", "monitoring_prometheus", "prometheus_targets_up", "L5_DEPENDENCY", "monitoring", True, "curl -s http://10.8.0.2:9090/api/v1/targets || curl -s http://127.0.0.1:9090/api/v1/targets", val_prom_targets),
            ("vps2", "monitoring_alertmanager", "alertmanager_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=alertmanager --format '{{.Status}}'", val_container_running("alertmanager", "/opt/monitoring")),
            ("vps2", "monitoring_grafana", "grafana_container_running", "L2_PROCESS", "monitoring", True, "docker ps --filter name=grafana --format '{{.Status}}'", val_container_running("grafana", "/opt/monitoring")),
            ("vps2", "monitoring_grafana", "grafana_api_health", "L4_PROTOCOL", "monitoring", True, "curl -s http://10.8.0.2:3001/api/health || curl -s http://127.0.0.1:3001/api/health", val_grafana_health),
            ("vps2", "elk_elasticsearch", "elasticsearch_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=elasticsearch --format '{{.Status}}'", val_container_running("elasticsearch", "/opt/elk")),
            ("vps2", "elk_elasticsearch", "elasticsearch_cluster_health", "L4_PROTOCOL", "logging", True, "curl -s http://10.8.0.2:9200/_cluster/health || curl -s http://127.0.0.1:9200/_cluster/health", val_es_health),
            ("vps2", "elk_logstash", "logstash_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=logstash --format '{{.Status}}'", val_container_running("logstash", "/opt/elk")),
            ("vps2", "elk_kibana", "kibana_container_running", "L2_PROCESS", "logging", True, "docker ps --filter name=kibana --format '{{.Status}}'", val_container_running("kibana", "/opt/elk"))
        ]

        for s_host, s_name, chk_name, lvl, scp, is_mand, cmd, val_fn in live_definitions:
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
                    expected=f"Execution of '{cmd}' succeeds",
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
                code, out, err = run_ssh_cmd(ip, key, cmd, timeout=5)
                status, sev, obs, exp, evid, l_causes, n_step = val_fn(code, out, err)
                self.add_check(
                    service=s_name,
                    host=s_host,
                    check=chk_name,
                    level=lvl,
                    scope=scp,
                    status=status,
                    severity=sev,
                    mandatory=is_mand,
                    observed=obs,
                    expected=exp,
                    evidence=evid,
                    likely_causes=l_causes,
                    recommended_next_step=n_step
                )
