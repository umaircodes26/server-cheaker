import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config, save_config
from app.database import (
    init_db,
    get_cached_state,
    get_recent_metrics,
    get_recent_alerts
)
from app.engine.scheduler import (
    start_scheduler,
    restart_scheduler,
    run_monitoring_cycle,
    run_scheduled_6h_report
)
from app.engine.discord import send_test_notification
from app.collectors.docker_monitor import restart_container_via_ssh


BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[VPS Sentinel] Initializing database and background watchdog...")
    init_db()
    start_scheduler()
    # Run immediate initial scan in background
    import asyncio
    asyncio.create_task(run_monitoring_cycle())
    yield
    # Shutdown


app = FastAPI(
    title="VPS Sentinel 24/7 Watchdog",
    description="24/7 VPS Resource, Website & Docker Monitor with Discord Alerting & GUI",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in ("/api/auth/status", "/api/health"):
        config = load_config()
        required_key = (config.get("api_key") or "").strip()
        if required_key:
            client_key = request.headers.get("X-API-Key") or request.query_params.get("api_key") or ""
            if client_key != required_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: Invalid or missing API Key", "auth_required": True}
                )
    return await call_next(request)

# Mount static and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health_check():
    """Healthcheck endpoint for free cloud hosting platforms (Render, Fly.io, etc.)"""
    return {"status": "ok", "app": "vps_sentinel", "version": "1.0.0"}


@app.get("/api/auth/status")
async def get_auth_status(request: Request):
    config = load_config()
    required_key = (config.get("api_key") or "").strip()
    if not required_key:
        return {"auth_required": False, "authenticated": True}
    client_key = request.headers.get("X-API-Key") or request.query_params.get("api_key") or ""
    return {
        "auth_required": True,
        "authenticated": client_key == required_key
    }


@app.get("/api/status")
async def get_current_status():
    telemetry = get_cached_state("latest_telemetry")
    if not telemetry:
        # If cache is not ready yet, return fallback placeholder
        config = load_config()
        telemetry = {
            "timestamp": None,
            "system": {
                "online": True,
                "host": config.get("vps_ip", "127.0.0.1"),
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "disk_percent": 0.0,
                "uptime_str": "Scanning..."
            },
            "docker": {"containers": [], "running_count": 0, "total_count": 0},
            "websites": [],
            "security": {"top_processes": []}
        }
    
    # Also attach recent metric points for the chart
    history = get_recent_metrics(limit=30)
    return {
        **telemetry,
        "history": history
    }


@app.post("/api/scan")
async def trigger_scan():
    result = await run_monitoring_cycle()
    return {"success": True, "data": result}


@app.get("/api/alerts")
async def get_alerts():
    alerts = get_recent_alerts(limit=50)
    return alerts


@app.get("/api/config")
async def get_config():
    config = load_config()
    masked = config.copy()
    if masked.get("ssh_password"):
        masked["ssh_password"] = "••••••••"
    if masked.get("api_key"):
        masked["api_key"] = "••••••••"
    return masked


@app.post("/api/config")
async def update_config(updated: Dict[str, Any]):
    current = load_config()
    if updated.get("ssh_password") == "••••••••":
        updated["ssh_password"] = current.get("ssh_password", "")
    if updated.get("api_key") == "••••••••":
        updated["api_key"] = current.get("api_key", "")

    save_config(updated)
    restart_scheduler()
    return {"success": True, "message": "Configuration updated and scheduler refreshed."}


@app.post("/api/discord/test")
async def test_discord():
    config = load_config()
    webhook_url = config.get("discord_webhook_url", "")
    if not webhook_url:
        return {"success": False, "message": "Discord Webhook URL is empty. Please enter it in Settings."}

    success = await send_test_notification(
        webhook_url=webhook_url,
        server_name=config.get("server_name", "VPS"),
        vps_ip=config.get("vps_ip", "127.0.0.1")
    )
    if success:
        return {"success": True, "message": "Test message sent to Discord successfully!"}
    else:
        return {"success": False, "message": "Failed to send message. Please verify your Discord Webhook URL."}


@app.post("/api/discord/report")
async def trigger_report():
    config = load_config()
    webhook_url = config.get("discord_webhook_url", "")
    if not webhook_url:
        return {"success": False, "message": "Discord Webhook URL is empty."}

    success = await run_scheduled_6h_report()
    if success:
        return {"success": True, "message": "6-Hour report successfully sent to Discord!"}
    else:
        return {"success": False, "message": "Failed to send 6-Hour report. Check Webhook URL."}


@app.post("/api/docker/restart")
async def restart_container(name: str):
    config = load_config()
    if config.get("connection_mode") == "local":
        import subprocess
        try:
            res = subprocess.run(["docker", "restart", name], capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return {"success": True, "message": f"Container {name} restarted successfully."}
            return {"success": False, "message": res.stderr}
        except Exception as e:
            return {"success": False, "message": str(e)}
    else:
        res = restart_container_via_ssh(config, name)
        return res
