"""
Service Catalog and Configuration Loader for Maktab DevOps Service Health Auditor.
Dynamically extracts all services, hosts, variables, and dependencies from the repository.
"""
import os
import yaml
from pathlib import Path

def load_yaml_file(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Failed to parse YAML file {path}: {e}")
        return {}

def load_inventory_and_vars(repo_root):
    """
    Loads all inventory hosts, group_vars, and host_vars from the repository.
    """
    repo = Path(repo_root)
    hosts_data = load_yaml_file(repo / "inventory/hosts.yml")
    main_vars = load_yaml_file(repo / "inventory/group_vars/all/main.yml")
    monitoring_vars = load_yaml_file(repo / "inventory/group_vars/all/monitoring.yml")
    secrets_vars = load_yaml_file(repo / "inventory/group_vars/all/secrets.yml")
    vps1_vars = load_yaml_file(repo / "inventory/host_vars/vps1.yml")
    vps2_vars = load_yaml_file(repo / "inventory/host_vars/vps2.yml")

    merged_all = {}
    merged_all.update(main_vars)
    merged_all.update(monitoring_vars)
    merged_all.update(secrets_vars)

    return {
        "hosts": hosts_data,
        "all_vars": merged_all,
        "main_vars": main_vars,
        "monitoring_vars": monitoring_vars,
        "secrets_vars": secrets_vars,
        "vps1_vars": vps1_vars,
        "vps2_vars": vps2_vars,
    }

SERVICE_DEFINITIONS = [
    {
        "name": "ansible_control",
        "description": "Ansible control node workspace, credentials, collections and SSH keys",
        "host": "control",
        "scope": "access",
        "mandatory": True,
        "deployment_type": "local",
        "ports": [],
        "endpoints": [],
        "config_files": [
            "ansible.cfg",
            "inventory/hosts.yml",
            "inventory/group_vars/all/main.yml",
            "requirements.yml"
        ],
        "dependencies": []
    },
    {
        "name": "system_base",
        "description": "Host base configuration, swap memory, timezone, and kernel parameters",
        "host": "vps1",
        "scope": "access",
        "mandatory": True,
        "deployment_type": "os",
        "ports": [22],
        "endpoints": ["81.12.50.30:22"],
        "config_files": ["roles/common/defaults/main.yml"],
        "dependencies": []
    },
    {
        "name": "system_base",
        "description": "Host base configuration, swap memory, timezone, and kernel parameters",
        "host": "vps2",
        "scope": "access",
        "mandatory": True,
        "deployment_type": "os",
        "ports": [22],
        "endpoints": ["31.56.89.69:22"],
        "config_files": ["roles/common/defaults/main.yml"],
        "dependencies": []
    },
    {
        "name": "docker_engine",
        "description": "Docker runtime daemon and Iranian mirror configuration",
        "host": "vps1",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [],
        "endpoints": [],
        "config_files": ["roles/docker/templates/daemon.json.j2"],
        "dependencies": ["system_base"]
    },
    {
        "name": "docker_engine",
        "description": "Docker runtime daemon and Iranian mirror configuration",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [],
        "endpoints": [],
        "config_files": ["roles/docker/templates/daemon.json.j2"],
        "dependencies": ["system_base"]
    },
    {
        "name": "firewall_ufw",
        "description": "UFW, iptables raw table (NodePort drop) and DOCKER-USER chain",
        "host": "vps1",
        "scope": "network",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [22, 80, 443, 51820],
        "endpoints": ["81.12.50.30:22"],
        "config_files": [
            "roles/firewall/defaults/main.yml",
            "inventory/host_vars/vps1.yml"
        ],
        "dependencies": []
    },
    {
        "name": "firewall_ufw",
        "description": "UFW, iptables raw table (NodePort drop) and DOCKER-USER chain",
        "host": "vps2",
        "scope": "network",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [22],
        "endpoints": ["31.56.89.69:22"],
        "config_files": [
            "roles/firewall/defaults/main.yml",
            "inventory/host_vars/vps2.yml"
        ],
        "dependencies": []
    },
    {
        "name": "pki_tls",
        "description": "Internal PKI Root CA and Wildcard TLS certificate distribution",
        "host": "control",
        "scope": "security",
        "mandatory": True,
        "deployment_type": "pki",
        "ports": [],
        "endpoints": [],
        "config_files": [
            ".secrets/pki/ca.crt",
            ".secrets/pki/wildcard.crt"
        ],
        "dependencies": []
    },
    {
        "name": "wireguard",
        "description": "WireGuard VPN Hub connecting VPS1, VPS2, and Control Laptop",
        "host": "vps1",
        "scope": "network",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [51820],
        "endpoints": ["10.8.0.1/24"],
        "config_files": ["roles/wireguard/templates/wg0.conf.j2"],
        "dependencies": ["firewall_ufw"]
    },
    {
        "name": "wireguard",
        "description": "WireGuard VPN Client peer connecting to VPS1 Hub",
        "host": "vps2",
        "scope": "network",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [51820],
        "endpoints": ["10.8.0.2/24"],
        "config_files": ["roles/wireguard/templates/wg0.conf.j2"],
        "dependencies": ["firewall_ufw"]
    },
    {
        "name": "dns_bind9",
        "description": "BIND9 authoritative DNS for maktab.rezaabolghasemi.ir on WireGuard IP",
        "host": "vps1",
        "scope": "network",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [53],
        "endpoints": ["10.8.0.1:53"],
        "config_files": [
            "roles/dns/templates/named.conf.local.j2",
            "roles/dns/templates/zone.j2"
        ],
        "dependencies": ["wireguard"]
    },
    {
        "name": "teleport_auth_proxy",
        "description": "Teleport PAM Auth (3025) and Proxy Web UI (3080) on VPS1",
        "host": "vps1",
        "scope": "access",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [3025, 3080],
        "endpoints": ["https://10.8.0.1:3080/webapi/ping"],
        "config_files": [
            "roles/teleport/templates/teleport-server.yaml.j2",
            "roles/teleport/templates/teleport.service.j2"
        ],
        "dependencies": ["wireguard", "pki_tls"]
    },
    {
        "name": "teleport_node",
        "description": "Teleport SSH Node agent on VPS2 registering with Hub Proxy",
        "host": "vps2",
        "scope": "access",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [],
        "endpoints": ["10.8.0.1:3025", "10.8.0.1:3080"],
        "config_files": ["roles/teleport/templates/teleport-node.yaml.j2"],
        "dependencies": ["teleport_auth_proxy", "wireguard"]
    },
    {
        "name": "nfs_server",
        "description": "NFS Server exporting /srv/nfs/k8s to WireGuard subnet 10.8.0.0/24",
        "host": "vps1",
        "scope": "storage",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [2049, 111],
        "endpoints": ["10.8.0.1:2049"],
        "config_files": ["roles/nfs/tasks/main.yml"],
        "dependencies": ["wireguard"]
    },
    {
        "name": "k3s_server",
        "description": "K3s Kubernetes Control Plane / API Server on VPS1",
        "host": "vps1",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [6443, 8472, 10250],
        "endpoints": ["https://10.8.0.1:6443/readyz"],
        "config_files": [
            "roles/k3s/templates/config-server.yaml.j2",
            "roles/k3s/templates/registries.yaml.j2"
        ],
        "dependencies": ["wireguard", "pki_tls"]
    },
    {
        "name": "k3s_agent",
        "description": "K3s Kubernetes Worker Agent on VPS2 connecting to VPS1 Control Plane",
        "host": "vps2",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [8472, 10250],
        "endpoints": ["https://10.8.0.1:6443"],
        "config_files": ["roles/k3s/templates/config-agent.yaml.j2"],
        "dependencies": ["k3s_server", "wireguard"]
    },
    {
        "name": "k8s_storage_nfs_provisioner",
        "description": "NFS Subdir External Provisioner providing default StorageClass in K8s",
        "host": "vps1",
        "scope": "storage",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [],
        "endpoints": [],
        "config_files": ["roles/k8s_platform/templates/nfs-provisioner.yml.j2"],
        "dependencies": ["nfs_server", "k3s_server"]
    },
    {
        "name": "k8s_db_cnpg_postgres",
        "description": "CloudNativePG PostgreSQL cluster (pg-main) in data namespace",
        "host": "vps1",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [5432],
        "endpoints": ["pg-main-rw.data.svc.cluster.local:5432"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/postgres/cluster.yaml.j2"],
        "dependencies": ["k8s_storage_nfs_provisioner"]
    },
    {
        "name": "k8s_db_redis",
        "description": "Redis StatefulSet in data namespace",
        "host": "vps1",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [6379],
        "endpoints": ["redis.data.svc.cluster.local:6379"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/redis/redis.yaml.j2"],
        "dependencies": ["k8s_storage_nfs_provisioner"]
    },
    {
        "name": "k8s_db_mariadb",
        "description": "MariaDB StatefulSet for WordPress in data namespace",
        "host": "vps1",
        "scope": "kubernetes",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [3306],
        "endpoints": ["mariadb.data.svc.cluster.local:3306"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/mariadb/mariadb.yaml.j2"],
        "dependencies": ["k8s_storage_nfs_provisioner"]
    },
    {
        "name": "k8s_app_wordpress",
        "description": "WordPress Deployment and NodePort 30080 in apps namespace",
        "host": "vps1",
        "scope": "public-endpoints",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [30080],
        "endpoints": ["http://10.8.0.1:30080"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/wordpress/wordpress.yaml.j2"],
        "dependencies": ["k8s_db_mariadb", "k8s_storage_nfs_provisioner"]
    },
    {
        "name": "k8s_app_frontend",
        "description": "Frontend static web application on NodePort 30081",
        "host": "vps1",
        "scope": "public-endpoints",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [30081],
        "endpoints": ["http://10.8.0.1:30081"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/frontend/frontend.yaml.j2"],
        "dependencies": ["k3s_server"]
    },
    {
        "name": "k8s_app_backend",
        "description": "Backend Flask API application on NodePort 30082",
        "host": "vps1",
        "scope": "public-endpoints",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [30082],
        "endpoints": ["http://10.8.0.1:30082/health"],
        "config_files": ["roles/gitops/templates/repo-gitops/apps/backend/backend.yaml.j2"],
        "dependencies": ["k8s_db_cnpg_postgres", "k8s_db_redis"]
    },
    {
        "name": "k8s_argocd",
        "description": "ArgoCD GitOps deployment server on NodePort 30090",
        "host": "vps1",
        "scope": "devtools",
        "mandatory": True,
        "deployment_type": "k8s-manifest",
        "ports": [30090],
        "endpoints": ["https://10.8.0.1:30090"],
        "config_files": ["roles/k8s_platform/tasks/main.yml"],
        "dependencies": ["k3s_server"]
    },
    {
        "name": "edge_nginx",
        "description": "Edge Reverse Proxy on VPS1 routing public traffic and internal VPN vhosts",
        "host": "vps1",
        "scope": "public-endpoints",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [80, 443],
        "endpoints": [
            "http://81.12.50.30:80",
            "https://81.12.50.30:443",
            "http://10.8.0.1:80",
            "https://10.8.0.1:443"
        ],
        "config_files": [
            "roles/edge_nginx/templates/nginx.conf.j2",
            "roles/edge_nginx/templates/public.conf.j2",
            "roles/edge_nginx/templates/internal.conf.j2"
        ],
        "dependencies": ["pki_tls", "k8s_app_wordpress", "k8s_app_frontend", "k8s_app_backend"]
    },
    {
        "name": "devtools_gitea",
        "description": "Self-hosted Gitea source control server on port 3000",
        "host": "vps1",
        "scope": "devtools",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [3000, 2222],
        "endpoints": ["http://10.8.0.1:3000/api/v1/version"],
        "config_files": ["roles/devtools/templates/docker-compose.yml.j2"],
        "dependencies": ["docker_engine", "wireguard"]
    },
    {
        "name": "devtools_registry",
        "description": "Internal Docker Container Registry on port 5000",
        "host": "vps1",
        "scope": "devtools",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [5000],
        "endpoints": ["http://10.8.0.1:5000/v2/"],
        "config_files": ["roles/devtools/templates/docker-compose.yml.j2"],
        "dependencies": ["docker_engine", "wireguard"]
    },
    {
        "name": "devtools_runner",
        "description": "Gitea act_runner for automated CI/CD pipelines",
        "host": "vps1",
        "scope": "devtools",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [],
        "endpoints": [],
        "config_files": [
            "roles/devtools/templates/docker-compose.yml.j2",
            "roles/devtools/templates/runner-config.yaml.j2"
        ],
        "dependencies": ["devtools_gitea", "devtools_registry"]
    },
    {
        "name": "gitops_repos",
        "description": "GitOps repository seed and sync status (backend, frontend, gitops)",
        "host": "vps1",
        "scope": "devtools",
        "mandatory": True,
        "deployment_type": "git",
        "ports": [],
        "endpoints": [],
        "config_files": ["roles/gitops/tasks/repo.yml"],
        "dependencies": ["devtools_gitea"]
    },
    {
        "name": "node_exporter",
        "description": "Prometheus Node Exporter on VPS1 metrics listener",
        "host": "vps1",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [9100],
        "endpoints": ["http://10.8.0.1:9100/metrics"],
        "config_files": ["roles/node_exporter/tasks/main.yml"],
        "dependencies": ["wireguard"]
    },
    {
        "name": "node_exporter",
        "description": "Prometheus Node Exporter on VPS2 metrics listener",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [9100],
        "endpoints": ["http://10.8.0.2:9100/metrics"],
        "config_files": ["roles/node_exporter/tasks/main.yml"],
        "dependencies": ["wireguard"]
    },
    {
        "name": "monitoring_prometheus",
        "description": "Prometheus time-series metrics server on VPS2",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [9090],
        "endpoints": ["http://10.8.0.2:9090/api/v1/status/ready"],
        "config_files": [
            "roles/monitoring/templates/docker-compose.yml.j2",
            "roles/monitoring/templates/prometheus.yml.j2"
        ],
        "dependencies": ["docker_engine", "wireguard"]
    },
    {
        "name": "monitoring_alertmanager",
        "description": "Alertmanager alert notification router on VPS2",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [9093],
        "endpoints": ["http://10.8.0.2:9093/-/ready"],
        "config_files": [
            "roles/monitoring/templates/docker-compose.yml.j2",
            "roles/monitoring/templates/alertmanager.yml.j2"
        ],
        "dependencies": ["docker_engine", "monitoring_prometheus"]
    },
    {
        "name": "monitoring_grafana",
        "description": "Grafana metrics dashboards on VPS2",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [3001],
        "endpoints": ["http://10.8.0.2:3001/api/health"],
        "config_files": [
            "roles/monitoring/templates/docker-compose.yml.j2",
            "roles/monitoring/templates/datasources.yml.j2"
        ],
        "dependencies": ["monitoring_prometheus"]
    },
    {
        "name": "monitoring_blackbox",
        "description": "Prometheus Blackbox probe exporter for HTTP, TLS and TCP probes",
        "host": "vps2",
        "scope": "monitoring",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [9115],
        "endpoints": ["http://10.8.0.2:9115/probe"],
        "config_files": [
            "roles/monitoring/templates/docker-compose.yml.j2",
            "roles/monitoring/templates/blackbox.yml.j2"
        ],
        "dependencies": ["docker_engine"]
    },
    {
        "name": "elk_elasticsearch",
        "description": "Elasticsearch single-node log indexing engine on VPS2",
        "host": "vps2",
        "scope": "logging",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [9200],
        "endpoints": ["http://10.8.0.2:9200/_cluster/health"],
        "config_files": ["roles/elk/templates/docker-compose.yml.j2"],
        "dependencies": ["docker_engine", "wireguard"]
    },
    {
        "name": "elk_logstash",
        "description": "Logstash pipeline ingesting Filebeat logs on port 5044",
        "host": "vps2",
        "scope": "logging",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [5044],
        "endpoints": ["10.8.0.2:5044"],
        "config_files": [
            "roles/elk/templates/docker-compose.yml.j2",
            "roles/elk/templates/logstash/logstash.conf.j2"
        ],
        "dependencies": ["elk_elasticsearch"]
    },
    {
        "name": "elk_kibana",
        "description": "Kibana log analysis Web UI on VPS2 port 5601",
        "host": "vps2",
        "scope": "logging",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [5601],
        "endpoints": ["http://10.8.0.2:5601/api/status"],
        "config_files": ["roles/elk/templates/docker-compose.yml.j2"],
        "dependencies": ["elk_elasticsearch"]
    },
    {
        "name": "filebeat",
        "description": "Filebeat container on VPS1 shipping Nginx JSON access logs to Logstash",
        "host": "vps1",
        "scope": "logging",
        "mandatory": True,
        "deployment_type": "docker-compose",
        "ports": [],
        "endpoints": ["10.8.0.2:5044"],
        "config_files": [
            "roles/filebeat/templates/docker-compose.yml.j2",
            "roles/filebeat/templates/filebeat.yml.j2"
        ],
        "dependencies": ["edge_nginx", "elk_logstash"]
    },
    {
        "name": "backup_system",
        "description": "Maktab daily backup timer, databases dump and remote rsync to VPS2",
        "host": "vps1",
        "scope": "backup",
        "mandatory": True,
        "deployment_type": "systemd",
        "ports": [],
        "endpoints": ["31.56.89.69:22"],
        "config_files": [
            "roles/backup/templates/maktab-backup.sh.j2",
            "roles/backup/templates/maktab-backup.service.j2",
            "roles/backup/templates/maktab-backup.timer.j2"
        ],
        "dependencies": ["k8s_db_cnpg_postgres", "k8s_db_mariadb", "devtools_gitea"]
    },
    {
        "name": "public_dns_tls",
        "description": "Public domain DNS A records and edge SSL/TLS certificates",
        "host": "external",
        "scope": "public-endpoints",
        "mandatory": True,
        "deployment_type": "dns-cdn",
        "ports": [80, 443],
        "endpoints": [
            "https://wp.rezaabolghasemi.ir",
            "https://app.rezaabolghasemi.ir"
        ],
        "config_files": ["inventory/group_vars/all/main.yml"],
        "dependencies": ["edge_nginx"]
    }
]

def get_service_catalog(scope=None, host=None):
    services = SERVICE_DEFINITIONS
    if scope and scope != "all":
        services = [s for s in services if s.get("scope") == scope]
    if host and host != "all":
        services = [s for s in services if s.get("host") in (host, "all", "external") or (host == "control" and s.get("host") == "control")]
    return services
