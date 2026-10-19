#!/usr/bin/env python3
"""
Test rendering of Jinja2 templates in Maktab DevOps repository.
"""
import json
import os
import sys
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_env(template_dir):
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['bool'] = lambda v: bool(v) if not isinstance(v, str) else v.lower() in ('true', 'yes', '1', 't', 'y')
    return env

def test_alertmanager_template():
    print("Testing Alertmanager template rendering...")
    env = get_env(os.path.join(REPO_ROOT, "roles/monitoring/templates"))
    template = env.get_template("alertmanager.yml.j2")
    
    # Valid telegram credentials
    context_valid = {
        "alert_channel": "telegram",
        "telegram_bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "telegram_chat_id": 987654321,
        "smtp_host": "smtp.example.com",
        "smtp_password": "CHANGE_ME",
        "slack_webhook_url": "CHANGE_ME"
    }
    rendered_valid = template.render(context_valid)
    parsed_valid = yaml.safe_load(rendered_valid)
    default_rcv_valid = parsed_valid["receivers"][0]
    assert "telegram_configs" in default_rcv_valid, "Valid telegram config was not rendered!"
    assert default_rcv_valid["telegram_configs"][0]["chat_id"] == 987654321
    print("  [PASS] Valid Telegram config correctly rendered.")

    # Fallback when credentials are CHANGE_ME / 0
    context_fallback = {
        "alert_channel": "telegram",
        "telegram_bot_token": "CHANGE_ME",
        "telegram_chat_id": 0,
        "smtp_host": "smtp.example.com",
        "smtp_password": "CHANGE_ME",
        "slack_webhook_url": "CHANGE_ME"
    }
    rendered_fallback = template.render(context_fallback)
    parsed_fallback = yaml.safe_load(rendered_fallback)
    default_rcv_fallback = parsed_fallback["receivers"][0]
    assert "telegram_configs" not in default_rcv_fallback, "Invalid placeholder telegram config rendered!"
    assert default_rcv_fallback["name"] == "default"
    print("  [PASS] Safe fallback null receiver correctly rendered when CHANGE_ME is detected.")

def test_k3s_registries_template():
    print("Testing K3s registries.yaml.j2 template...")
    env = get_env(os.path.join(REPO_ROOT, "roles/k3s/templates"))
    template = env.get_template("registries.yaml.j2")
    context = {
        "registry_endpoint": "10.8.0.1:5000",
        "registry_user": "ci",
        "registry_password": "secretpassword"
    }
    rendered = template.render(context)
    parsed = yaml.safe_load(rendered)
    assert parsed is not None
    print("  [PASS] K3s registries.yaml.j2 rendered valid YAML.")

def test_docker_daemon_template():
    print("Testing Docker daemon.json.j2 template...")
    env = get_env(os.path.join(REPO_ROOT, "roles/docker/templates"))
    template = env.get_template("daemon.json.j2")
    context = {
        "registry_endpoint": "10.8.0.1:5000"
    }
    rendered = template.render(context)
    parsed = json.loads(rendered)
    assert "insecure-registries" in parsed or "registry-mirrors" in parsed
    print("  [PASS] Docker daemon.json rendered valid JSON.")

def test_k3s_server_config_template():
    print("Testing K3s config-server.yaml.j2 template...")
    env = get_env(os.path.join(REPO_ROOT, "roles/k3s/templates"))
    template = env.get_template("config-server.yaml.j2")
    context = {
        "wg_ip": "10.8.0.1",
        "ansible_host": "81.12.50.30",
        "private_domain": "maktab.rezaabolghasemi.ir",
        "k3s_token": "token123"
    }
    rendered = template.render(context)
    parsed = yaml.safe_load(rendered)
    assert parsed.get("node-ip") == "10.8.0.1"
    assert parsed.get("flannel-iface") == "wg0"
    print("  [PASS] K3s server config correctly rendered.")

if __name__ == "__main__":
    test_alertmanager_template()
    test_k3s_registries_template()
    test_docker_daemon_template()
    test_k3s_server_config_template()
    print("All template tests passed successfully!")
