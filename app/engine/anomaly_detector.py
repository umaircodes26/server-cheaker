import time
from typing import Dict, Any, List, Tuple
from app.database import log_alert
from app.engine.discord import send_immediate_alert, send_recovery_alert


class AnomalyDetector:
    def __init__(self):
        # Track previous states to detect state transitions & recoveries
        self.container_states: Dict[str, str] = {}  # container_name -> state
        self.website_states: Dict[str, bool] = {}   # site_id -> is_up
        self.vps_online_state: bool = True
        self.alert_cooldowns: Dict[str, float] = {}  # alert_key -> last_sent_timestamp
        self.seen_failed_ssh: set = set()

    def is_in_cooldown(self, key: str, cooldown_minutes: float = 15.0) -> bool:
        last_time = self.alert_cooldowns.get(key, 0)
        return (time.time() - last_time) < (cooldown_minutes * 60)

    def mark_alerted(self, key: str):
        self.alert_cooldowns[key] = time.time()

    async def evaluate_and_alert(
        self,
        config: Dict[str, Any],
        system_metrics: Dict[str, Any],
        docker_data: Dict[str, Any],
        websites_data: List[Dict[str, Any]],
        security_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all telemetry data against anomaly rules.
        Sends immediate Discord alerts for critical/unusual events and recovery notices.
        """
        webhook_url = config.get("discord_webhook_url", "")
        server_name = config.get("server_name", "VPS")
        vps_ip = config.get("vps_ip", "127.0.0.1")
        thresholds = config.get("thresholds", {})
        cooldown_mins = float(config.get("alert_cooldown_minutes", 15))

        triggered_alerts = []

        # -------------------------------------------------------------
        # 1. VPS Reachability Check
        # -------------------------------------------------------------
        is_online = system_metrics.get("online", True)
        if not is_online:
            alert_key = "vps_unreachable"
            if not self.is_in_cooldown(alert_key, cooldown_mins):
                alert = {
                    "alert_type": "VPS_OFFLINE",
                    "severity": "CRITICAL",
                    "title": f"VPS Unreachable / SSH Connection Failed",
                    "message": f"Could not connect to VPS `{vps_ip}`. Error: {system_metrics.get('error', 'Timeout')}.",
                    "details": {"recommendation": "Check VPS control panel / cloud provider console to see if server is online."}
                }
                log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                triggered_alerts.append(alert)
                if webhook_url:
                    await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                self.mark_alerted(alert_key)
            self.vps_online_state = False
            return triggered_alerts
        else:
            if not self.vps_online_state:
                # VPS Recovered!
                self.vps_online_state = True
                log_alert("VPS_RECOVERED", "RECOVERY", "VPS Back Online", f"Connection to VPS `{vps_ip}` restored.", {}, bool(webhook_url))
                if webhook_url:
                    await send_recovery_alert(webhook_url, "VPS Reconnected", f"Connection to VPS `{vps_ip}` has been restored.", server_name, vps_ip)

        # -------------------------------------------------------------
        # 2. System Resource Anomaly Checks (CPU, RAM, Disk)
        # -------------------------------------------------------------
        cpu_p = system_metrics.get("cpu_percent", 0.0)
        cpu_thresh = float(thresholds.get("cpu_percent", 85.0))
        if cpu_p >= cpu_thresh:
            alert_key = "high_cpu"
            if not self.is_in_cooldown(alert_key, cooldown_mins):
                alert = {
                    "alert_type": "HIGH_CPU",
                    "severity": "WARNING",
                    "title": f"Unusual High CPU Load ({cpu_p}%)",
                    "message": f"CPU utilization spiked to **{cpu_p}%**, exceeding threshold of {cpu_thresh}%.",
                    "details": {"recommendation": "Inspect top CPU processes on dashboard or run `ps aux --sort=-%cpu`"}
                }
                log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                triggered_alerts.append(alert)
                if webhook_url:
                    await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                self.mark_alerted(alert_key)

        ram_p = system_metrics.get("ram_percent", 0.0)
        ram_thresh = float(thresholds.get("ram_percent", 90.0))
        if ram_p >= ram_thresh:
            alert_key = "high_ram"
            if not self.is_in_cooldown(alert_key, cooldown_mins):
                alert = {
                    "alert_type": "HIGH_RAM",
                    "severity": "CRITICAL",
                    "title": f"Critical RAM Usage ({ram_p}%)",
                    "message": f"RAM usage reached **{ram_p}%** (Used: {system_metrics.get('ram_used_mb')}MB / {system_metrics.get('ram_total_mb')}MB). Risk of OOM crash!",
                    "details": {"recommendation": "Check heavy docker containers or restart memory-leaking services."}
                }
                log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                triggered_alerts.append(alert)
                if webhook_url:
                    await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                self.mark_alerted(alert_key)

        disk_p = system_metrics.get("disk_percent", 0.0)
        disk_thresh = float(thresholds.get("disk_percent", 90.0))
        if disk_p >= disk_thresh:
            alert_key = "high_disk"
            if not self.is_in_cooldown(alert_key, cooldown_mins):
                alert = {
                    "alert_type": "HIGH_DISK",
                    "severity": "CRITICAL",
                    "title": f"Disk Space Almost Full ({disk_p}%)",
                    "message": f"Root disk usage reached **{disk_p}%** ({system_metrics.get('disk_used_gb')}GB / {system_metrics.get('disk_total_gb')}GB).",
                    "details": {"recommendation": "Clean Docker cache with `docker system prune -af` or rotate old logs."}
                }
                log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                triggered_alerts.append(alert)
                if webhook_url:
                    await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                self.mark_alerted(alert_key)

        # -------------------------------------------------------------
        # 3. Docker Containers Status Checks
        # -------------------------------------------------------------
        containers = docker_data.get("containers", [])
        for c in containers:
            c_name = c.get("name", "")
            c_state = c.get("state", "").lower()
            prev_state = self.container_states.get(c_name)

            # Check if container stopped or crashed unexpectedly
            if c_state in ("exited", "dead", "restarting"):
                alert_key = f"container_{c_name}_down"
                if prev_state == "running" or not self.is_in_cooldown(alert_key, cooldown_mins):
                    alert = {
                        "alert_type": "DOCKER_CONTAINER_DOWN",
                        "severity": "CRITICAL",
                        "title": f"Docker Container Crashed / Stopped: {c_name}",
                        "message": f"Container **{c_name}** (`{c.get('image')}`) is in `{c_state}` state! Status: `{c.get('status')}`.",
                        "details": {"recommendation": f"Run `docker logs {c_name}` and `docker restart {c_name}`"}
                    }
                    log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                    triggered_alerts.append(alert)
                    if webhook_url:
                        await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                    self.mark_alerted(alert_key)

            # Check for container recovery
            elif c_state == "running" and prev_state in ("exited", "dead", "restarting"):
                log_alert("DOCKER_RECOVERED", "RECOVERY", f"Container {c_name} Recovered", f"Container {c_name} is running again.", {}, bool(webhook_url))
                if webhook_url:
                    await send_recovery_alert(webhook_url, f"Docker Container Recovered: {c_name}", f"Container **{c_name}** is now back up and healthy (running).", server_name, vps_ip)

            self.container_states[c_name] = c_state

        # -------------------------------------------------------------
        # 4. Websites & Services Health Checks
        # -------------------------------------------------------------
        for site in websites_data:
            s_id = site.get("id", site.get("url"))
            s_name = site.get("name", site.get("url"))
            s_is_up = site.get("is_up", False)
            prev_up = self.website_states.get(s_id)

            if not s_is_up:
                alert_key = f"site_{s_id}_down"
                # If was up before, or cooldown expired
                if prev_up is True or prev_up is None or not self.is_in_cooldown(alert_key, cooldown_mins):
                    alert = {
                        "alert_type": "WEBSITE_DOWN",
                        "severity": "CRITICAL",
                        "title": f"Website / Service DOWN: {s_name}",
                        "message": f"Endpoint `{site.get('url')}` is unreachable or returned error.\nStatus: `{site.get('status_code')}` | Error: `{site.get('error')}`",
                        "details": {"recommendation": "Check web server (Nginx/Apache), SSL certificates, and Docker app logs."}
                    }
                    log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                    triggered_alerts.append(alert)
                    if webhook_url:
                        await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                    self.mark_alerted(alert_key)
            elif s_is_up and prev_up is False:
                # Website recovered!
                log_alert("WEBSITE_RECOVERED", "RECOVERY", f"Website {s_name} Recovered", f"Website {s_name} is back online.", {}, bool(webhook_url))
                if webhook_url:
                    await send_recovery_alert(
                        webhook_url,
                        f"Website Restored: {s_name}",
                        f"Website **{s_name}** (`{site.get('url')}`) is responding normally (Status {site.get('status_code')}, {site.get('response_time_ms')}ms).",
                        server_name,
                        vps_ip
                    )

            self.website_states[s_id] = s_is_up

        # -------------------------------------------------------------
        # 5. Security & Brute-Force Activity Checks
        # -------------------------------------------------------------
        failed_ssh = security_data.get("failed_ssh_attempts", [])
        if len(failed_ssh) >= 5:
            # Group by IP
            ip_counts = {}
            for item in failed_ssh:
                ip = item.get("ip")
                if ip:
                    ip_counts[ip] = ip_counts.get(ip, 0) + 1
            
            for attacker_ip, count in ip_counts.items():
                if count >= 3 and attacker_ip not in self.seen_failed_ssh:
                    alert_key = f"ssh_brute_{attacker_ip}"
                    if not self.is_in_cooldown(alert_key, 60.0):  # 1 hour cooldown per attacker IP
                        self.seen_failed_ssh.add(attacker_ip)
                        alert = {
                            "alert_type": "SECURITY_BRUTE_FORCE",
                            "severity": "WARNING",
                            "title": f"Suspicious Activity: SSH Brute-Force Detected",
                            "message": f"Detected **{count} failed SSH login attempts** targeting user root/admin from IP: `{attacker_ip}`.",
                            "details": {"recommendation": f"Run `ufw deny from {attacker_ip}` or enable Fail2Ban on the VPS."}
                        }
                        log_alert(alert["alert_type"], alert["severity"], alert["title"], alert["message"], alert["details"], bool(webhook_url))
                        triggered_alerts.append(alert)
                        if webhook_url:
                            await send_immediate_alert(webhook_url, alert, server_name, vps_ip)
                        self.mark_alerted(alert_key)

        return triggered_alerts

