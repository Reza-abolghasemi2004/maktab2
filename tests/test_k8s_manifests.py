#!/usr/bin/env python3
"""
Test validation of Kubernetes YAML templates.
"""
import os
import yaml
import base64
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_k8s_templates():
    print("Testing K8s platform templates...")
    template_dir = os.path.join(REPO_ROOT, "roles/k8s_platform/templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters["b64encode"] = lambda s: base64.b64encode(str(s).encode()).decode()
    
    context = {
        "hub_ip": "10.8.0.1",
        "worker_ip": "10.8.0.2",
        "nfs_export_path": "/srv/nfs/k8s",
        "np_ksm": 30085,
        "np_blackbox_k8s": 30115,
        "pg_app_password": "dummy_pg_password",
        "mariadb_root_password": "dummy_maria_root",
        "mariadb_wp_password": "dummy_maria_wp",
        "redis_password": "dummy_redis_pass"
    }
    
    for tmpl_file in os.listdir(template_dir):
        if not tmpl_file.endswith(".j2"):
            continue
        print(f"  Validating {tmpl_file}...")
        tmpl = env.get_template(tmpl_file)
        rendered = tmpl.render(context)
        # Parse all YAML documents in the file
        docs = list(yaml.safe_load_all(rendered))
        assert len(docs) > 0, f"Template {tmpl_file} produced empty document"
        for idx, doc in enumerate(docs):
            if doc is not None:
                assert "apiVersion" in doc, f"Doc {idx} in {tmpl_file} missing apiVersion"
                assert "kind" in doc, f"Doc {idx} in {tmpl_file} missing kind"
                assert "metadata" in doc, f"Doc {idx} in {tmpl_file} missing metadata"
        print(f"    [PASS] {tmpl_file} is valid Kubernetes YAML ({len(docs)} documents).")

if __name__ == "__main__":
    test_k8s_templates()
    print("All K8s templates passed validation!")
