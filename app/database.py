import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "sentinel.db"


def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_percent REAL,
                ram_percent REAL,
                ram_used_mb REAL,
                ram_total_mb REAL,
                disk_percent REAL,
                disk_used_gb REAL,
                disk_total_gb REAL,
                load_1m REAL,
                load_5m REAL,
                load_15m REAL,
                containers_running INTEGER,
                containers_total INTEGER,
                websites_up INTEGER,
                websites_total INTEGER
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                discord_sent INTEGER DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
    conn.close()


def save_metric_snapshot(snapshot: Dict[str, Any]):
    conn = get_db()
    with conn:
        conn.execute("""
            INSERT INTO metrics (
                timestamp, cpu_percent, ram_percent, ram_used_mb, ram_total_mb,
                disk_percent, disk_used_gb, disk_total_gb, load_1m, load_5m, load_15m,
                containers_running, containers_total, websites_up, websites_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            snapshot.get("cpu_percent", 0.0),
            snapshot.get("ram_percent", 0.0),
            snapshot.get("ram_used_mb", 0.0),
            snapshot.get("ram_total_mb", 0.0),
            snapshot.get("disk_percent", 0.0),
            snapshot.get("disk_used_gb", 0.0),
            snapshot.get("disk_total_gb", 0.0),
            snapshot.get("load_1m", 0.0),
            snapshot.get("load_5m", 0.0),
            snapshot.get("load_15m", 0.0),
            snapshot.get("containers_running", 0),
            snapshot.get("containers_total", 0),
            snapshot.get("websites_up", 0),
            snapshot.get("websites_total", 0)
        ))
        # Keep metrics database size under control (retain last 2000 points, approx 24-48 hours)
        conn.execute("""
            DELETE FROM metrics WHERE id NOT IN (
                SELECT id FROM metrics ORDER BY id DESC LIMIT 2000
            )
        """)
    conn.close()


def log_alert(alert_type: str, severity: str, title: str, message: str, details: Optional[Dict[str, Any]] = None, discord_sent: bool = False) -> int:
    conn = get_db()
    details_str = json.dumps(details or {})
    timestamp = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute("""
            INSERT INTO alerts (timestamp, alert_type, severity, title, message, details_json, discord_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, alert_type, severity, title, message, details_str, 1 if discord_sent else 0))
        alert_id = cursor.lastrowid
    conn.close()
    return alert_id


def get_recent_metrics(limit: int = 60) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute("""
        SELECT * FROM metrics ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return list(reversed(rows))


def get_recent_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute("""
        SELECT * FROM alerts ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_metrics_summary(hours: float = 6.0) -> Dict[str, Any]:
    """Calculate summary analytics (avg, peak) over the past specified hours"""
    conn = get_db()
    cursor = conn.execute("""
        SELECT 
            COUNT(*) as sample_count,
            AVG(cpu_percent) as avg_cpu,
            MAX(cpu_percent) as peak_cpu,
            AVG(ram_percent) as avg_ram,
            MAX(ram_percent) as peak_ram,
            AVG(disk_percent) as avg_disk,
            MAX(disk_percent) as peak_disk,
            MIN(containers_running) as min_containers_running,
            MAX(containers_running) as max_containers_running
        FROM metrics
        WHERE datetime(timestamp) >= datetime('now', ?)
    """, (f"-{hours} hours",))
    row = cursor.fetchone()
    conn.close()
    if row and row["sample_count"] > 0:
        return {
            "sample_count": row["sample_count"],
            "avg_cpu": round(row["avg_cpu"] or 0, 1),
            "peak_cpu": round(row["peak_cpu"] or 0, 1),
            "avg_ram": round(row["avg_ram"] or 0, 1),
            "peak_ram": round(row["peak_ram"] or 0, 1),
            "avg_disk": round(row["avg_disk"] or 0, 1),
            "peak_disk": round(row["peak_disk"] or 0, 1),
            "min_containers_running": row["min_containers_running"] or 0,
            "max_containers_running": row["max_containers_running"] or 0
        }
    return {
        "sample_count": 0,
        "avg_cpu": 0, "peak_cpu": 0,
        "avg_ram": 0, "peak_ram": 0,
        "avg_disk": 0, "peak_disk": 0,
        "min_containers_running": 0, "max_containers_running": 0
    }


def set_cached_state(key: str, data: Any):
    conn = get_db()
    with conn:
        conn.execute("""
            INSERT INTO state_cache (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, json.dumps(data), datetime.now(timezone.utc).isoformat()))
    conn.close()


def get_cached_state(key: str) -> Optional[Any]:
    conn = get_db()
    cursor = conn.execute("SELECT value FROM state_cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return None
    return None

