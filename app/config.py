import json
import os
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "server_name": "My Production VPS",
    "vps_ip": "127.0.0.1",
    "ssh_port": 22,
    "ssh_username": "root",
    "ssh_password": "",
    "ssh_key": "",
    "connection_mode": "local",  # "local" (zero credentials - running directly on VPS) or "ssh"
    "api_key": "",  # Optional dashboard & API access key to protect public dashboard
    "discord_webhook_url": "",
    "report_interval_hours": 6,
    "check_interval_seconds": 30,
    "alert_cooldown_minutes": 15,
    "thresholds": {
        "cpu_percent": 85.0,
        "ram_percent": 90.0,
        "disk_percent": 90.0,
        "load_15m": 5.0
    },
    "monitored_websites": [
        {
            "id": "site-1",
            "name": "Main Application",
            "url": "http://127.0.0.1:8000/health",
            "expected_code": 200,
            "timeout_seconds": 10
        }
    ],
    "monitored_containers": []  # Empty means monitor all docker containers automatically
}


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    ensure_data_dir()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with default config to ensure all keys exist
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            if "thresholds" in data:
                merged["thresholds"] = {**DEFAULT_CONFIG["thresholds"], **data["thresholds"]}
            return merged
    except Exception as e:
        print(f"[Config] Error reading {CONFIG_FILE}: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    ensure_data_dir()
    temp_file = CONFIG_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    temp_file.replace(CONFIG_FILE)

