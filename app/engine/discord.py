import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


async def send_discord_webhook(webhook_url: str, payload: Dict[str, Any]) -> bool:
    if not webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            return resp.status_code in (200, 204)
    except Exception as e:
        print(f"[Discord] Error sending webhook: {e}")
        return False


async def send_test_notification(webhook_url: str, server_name: str, vps_ip: str) -> bool:
    embed = {
        "title": "🔔 [TEST] VPS Sentinel Connected Successfully!",
        "description": f"Congratulations! Your 24/7 VPS Watchdog is active and connected to Discord.",
        "color": 10070709,  # Purple
        "fields": [
            {"name": "🖥️ Server Name", "value": server_name, "inline": True},
            {"name": "🌐 VPS IP", "value": vps_ip, "inline": True},
            {"name": "⏱️ Check Interval", "value": "Every 30 Seconds", "inline": True},
            {"name": "📊 Periodic Report", "value": "Every 6 Hours", "inline": True},
            {"name": "🚨 Real-Time Alerts", "value": "Enabled (Instant Notification on Unusual Activity)", "inline": False}
        ],
        "footer": {
            "text": "VPS Sentinel 24/7 Monitoring System"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload = {
        "username": "VPS Sentinel Watchdog",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2885/2885417.png",
        "embeds": [embed]
    }
    return await send_discord_webhook(webhook_url, payload)


async def send_immediate_alert(webhook_url: str, alert: Dict[str, Any], server_name: str, vps_ip: str) -> bool:
    severity = alert.get("severity", "WARNING").upper()
    color = 15158332 if severity == "CRITICAL" else 15105570  # Red or Orange
    icon = "🚨" if severity == "CRITICAL" else "⚠️"

    title = f"{icon} [{severity}] Unusual Activity: {alert.get('title', 'Server Issue')}"
    fields = [
        {"name": "🖥️ Target VPS", "value": f"**{server_name}** (`{vps_ip}`)", "inline": True},
        {"name": "⏰ Detected At", "value": f"<t:{int(datetime.now().timestamp())}:R>", "inline": True},
        {"name": "📋 Details", "value": alert.get("message", "No description provided"), "inline": False}
    ]

    details = alert.get("details", {})
    if "recommendation" in details:
        fields.append({"name": "💡 Recommended Action", "value": f"`{details['recommendation']}`", "inline": False})

    embed = {
        "title": title,
        "color": color,
        "fields": fields,
        "footer": {
            "text": "VPS Sentinel Real-Time Watchdog • Immediate Action Recommended"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    payload = {
        "username": "VPS Sentinel Alert",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/564/564619.png",
        "embeds": [embed]
    }
    return await send_discord_webhook(webhook_url, payload)


async def send_recovery_alert(webhook_url: str, title: str, message: str, server_name: str, vps_ip: str) -> bool:
    color = 3066993  # Emerald Green
    embed = {
        "title": f"✅ [RECOVERED] {title}",
        "color": color,
        "fields": [
            {"name": "🖥️ Target VPS", "value": f"**{server_name}** (`{vps_ip}`)", "inline": True},
            {"name": "⏰ Resolved At", "value": f"<t:{int(datetime.now().timestamp())}:R>", "inline": True},
            {"name": "📋 Status", "value": message, "inline": False}
        ],
        "footer": {
            "text": "VPS Sentinel Real-Time Watchdog • Issue Resolved"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload = {
        "username": "VPS Sentinel Watchdog",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/190/190411.png",
        "embeds": [embed]
    }
    return await send_discord_webhook(webhook_url, payload)


async def send_6hour_report(
    webhook_url: str,
    server_name: str,
    vps_ip: str,
    metrics_now: Dict[str, Any],
    metrics_summary: Dict[str, Any],
    docker_data: Dict[str, Any],
    websites_data: List[Dict[str, Any]],
    alert_count_6h: int
) -> bool:
    avg_cpu = metrics_summary.get("avg_cpu", metrics_now.get("cpu_percent", 0))
    peak_cpu = metrics_summary.get("peak_cpu", metrics_now.get("cpu_percent", 0))
    avg_ram = metrics_summary.get("avg_ram", metrics_now.get("ram_percent", 0))
    peak_ram = metrics_summary.get("peak_ram", metrics_now.get("ram_percent", 0))

    cpu_now = metrics_now.get("cpu_percent", 0)
    ram_now = metrics_now.get("ram_percent", 0)
    disk_now = metrics_now.get("disk_percent", 0)
    disk_used = metrics_now.get("disk_used_gb", 0)
    disk_total = metrics_now.get("disk_total_gb", 0)
    uptime_str = metrics_now.get("uptime_str", "Active")
    load_15m = metrics_now.get("load_15m", 0)

    # Health status evaluation
    is_healthy = alert_count_6h == 0 and disk_now < 90 and ram_now < 90
    health_badge = "🟢 Excellent" if is_healthy else ("🟡 Attention Needed" if alert_count_6h < 3 else "🔴 Degraded")

    # Format containers summary
    containers = docker_data.get("containers", [])
    total_containers = len(containers)
    running_containers = sum(1 for c in containers if c.get("state") == "running")
    container_lines = []
    for c in containers[:8]:  # Limit to 8 containers in summary embed
        c_state = "🟢" if c.get("state") == "running" else "🔴"
        container_lines.append(f"{c_state} **{c.get('name')}**: `{c.get('status')}` (CPU: {c.get('cpu_percent', '0%')}, Mem: {c.get('mem_usage', 'N/A')})")
    
    if len(containers) > 8:
        container_lines.append(f"...and {len(containers) - 8} more containers.")
    containers_str = "\n".join(container_lines) if container_lines else "No Docker containers detected."

    # Format websites summary
    website_lines = []
    for w in websites_data:
        w_state = "🟢" if w.get("is_up") else "🔴"
        latency = f"{w.get('response_time_ms', 0)}ms" if w.get("is_up") else "DOWN"
        website_lines.append(f"{w_state} **{w.get('name')}**: `{latency}` (Code {w.get('status_code')})")
    websites_str = "\n".join(website_lines) if website_lines else "No websites registered."

    embed = {
        "title": f"📊 [6-HOUR REPORT] Server Health & Analytics Digest",
        "description": f"Performance and health report for **{server_name}** (`{vps_ip}`) over the last 6 hours.",
        "color": 3447003,  # Blue
        "fields": [
            {
                "name": "🏥 System Health Status",
                "value": f"**Health**: {health_badge}\n**Uptime**: `{uptime_str}`\n**Load (15m)**: `{load_15m}`",
                "inline": True
            },
            {
                "name": "🛡️ Incident Summary",
                "value": f"**Alerts Triggered**: `{alert_count_6h}` in last 6h\n**VPS Status**: `Online & Monitored`",
                "inline": True
            },
            {
                "name": "⚡ Resource Metrics (Current / 6h Avg / 6h Peak)",
                "value": (
                    f"**CPU**: Current `{cpu_now}%` | Avg `{avg_cpu}%` | Peak `{peak_cpu}%`\n"
                    f"**RAM**: Current `{ram_now}%` | Avg `{avg_ram}%` | Peak `{peak_ram}%`\n"
                    f"**Disk**: `{disk_used}GB / {disk_total}GB` (`{disk_now}%` used)"
                ),
                "inline": False
            },
            {
                "name": f"🐳 Docker Containers ({running_containers}/{total_containers} Running)",
                "value": containers_str,
                "inline": False
            },
            {
                "name": f"🌐 Monitored Websites ({sum(1 for w in websites_data if w.get('is_up'))}/{len(websites_data)} Up)",
                "value": websites_str,
                "inline": False
            }
        ],
        "footer": {
            "text": "VPS Sentinel • 6-Hour Scheduled Performance Digest • Next report in 6h"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    payload = {
        "username": "VPS Sentinel Reporter",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "embeds": [embed]
    }
    return await send_discord_webhook(webhook_url, payload)

