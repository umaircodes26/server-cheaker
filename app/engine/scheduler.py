import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import load_config
from app.database import (
    save_metric_snapshot,
    set_cached_state,
    get_cached_state,
    get_metrics_summary,
    get_recent_alerts
)
from app.collectors.system_metrics import get_system_metrics
from app.collectors.docker_monitor import get_docker_status
from app.collectors.web_checker import check_all_websites
from app.collectors.security_log import get_security_info
from app.engine.anomaly_detector import AnomalyDetector
from app.engine.discord import send_6hour_report

scheduler: Optional[AsyncIOScheduler] = None
detector = AnomalyDetector()
is_check_running = False


async def run_monitoring_cycle() -> Dict[str, Any]:
    global is_check_running
    if is_check_running:
        return {}
    is_check_running = True
    try:
        config = load_config()

        # 1. Collect in parallel / sequence
        # System metrics & Docker metrics
        loop = asyncio.get_event_loop()
        sys_metrics = await loop.run_in_executor(None, get_system_metrics, config)
        docker_data = await loop.run_in_executor(None, get_docker_status, config)
        security_data = await loop.run_in_executor(None, get_security_info, config)
        
        # Websites check (already async)
        websites_data = await check_all_websites(config.get("monitored_websites", []))

        # 2. Record to database
        running_c = docker_data.get("running_count", 0)
        total_c = docker_data.get("total_count", 0)
        up_w = sum(1 for w in websites_data if w.get("is_up"))
        total_w = len(websites_data)

        snapshot = {
            **sys_metrics,
            "containers_running": running_c,
            "containers_total": total_c,
            "websites_up": up_w,
            "websites_total": total_w
        }
        save_metric_snapshot(snapshot)

        # 3. Cache latest full telemetry for instant GUI access
        full_telemetry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system": sys_metrics,
            "docker": docker_data,
            "websites": websites_data,
            "security": security_data
        }
        set_cached_state("latest_telemetry", full_telemetry)

        # 4. Run Anomaly Evaluation (sends Discord alert if anomaly detected)
        await detector.evaluate_and_alert(
            config=config,
            system_metrics=sys_metrics,
            docker_data=docker_data,
            websites_data=websites_data,
            security_data=security_data
        )

        return full_telemetry
    except Exception as e:
        print(f"[Scheduler] Error during monitoring cycle: {e}")
        return {}
    finally:
        is_check_running = False


async def run_scheduled_6h_report() -> bool:
    try:
        config = load_config()
        webhook_url = config.get("discord_webhook_url", "")
        if not webhook_url:
            print("[Scheduler] Discord Webhook URL not set. Skipping 6-hour report.")
            return False

        report_hours = float(config.get("report_interval_hours", 6))
        summary = get_metrics_summary(hours=report_hours)

        latest = get_cached_state("latest_telemetry") or {}
        sys_metrics = latest.get("system", {})
        docker_data = latest.get("docker", {})
        websites_data = latest.get("websites", [])

        # Count alerts in the last 6 hours
        recent_alerts = get_recent_alerts(limit=100)
        cutoff = time.time() - (report_hours * 3600)
        alerts_in_period = 0
        for a in recent_alerts:
            try:
                dt = datetime.fromisoformat(a["timestamp"])
                if dt.timestamp() >= cutoff:
                    alerts_in_period += 1
            except Exception:
                pass

        success = await send_6hour_report(
            webhook_url=webhook_url,
            server_name=config.get("server_name", "VPS"),
            vps_ip=config.get("vps_ip", "127.0.0.1"),
            metrics_now=sys_metrics,
            metrics_summary=summary,
            docker_data=docker_data,
            websites_data=websites_data,
            alert_count_6h=alerts_in_period
        )
        return success
    except Exception as e:
        print(f"[Scheduler] Error generating 6-hour report: {e}")
        return False


def start_scheduler():
    global scheduler
    if scheduler is not None and scheduler.running:
        return

    config = load_config()
    check_interval = int(config.get("check_interval_seconds", 30))
    report_hours = float(config.get("report_interval_hours", 6))

    scheduler = AsyncIOScheduler()
    # Check cycle
    scheduler.add_job(
        run_monitoring_cycle,
        trigger=IntervalTrigger(seconds=check_interval),
        id="monitoring_cycle",
        replace_existing=True,
        max_instances=1
    )
    # 6-Hour Report cycle
    scheduler.add_job(
        run_scheduled_6h_report,
        trigger=IntervalTrigger(hours=report_hours),
        id="six_hour_report",
        replace_existing=True,
        max_instances=1
    )
    scheduler.start()
    print(f"[Scheduler] Started background monitoring (Checks every {check_interval}s, Reports every {report_hours}h)")


def restart_scheduler():
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler = None
    start_scheduler()

