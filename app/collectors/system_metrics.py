import os
import re
import shutil
import time
from typing import Dict, Any, Optional
import paramiko


def execute_ssh_command(client: paramiko.SSHClient, command: str, timeout: int = 10) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    return stdout.read().decode("utf-8", errors="ignore").strip()


def parse_uptime_output(output: str) -> Dict[str, Any]:
    """Parse output of `uptime` command: e.g. '14:20:15 up 25 days,  4:12,  2 users,  load average: 0.15, 0.25, 0.30'"""
    res = {
        "uptime_str": "Unknown",
        "load_1m": 0.0,
        "load_5m": 0.0,
        "load_15m": 0.0
    }
    if not output:
        return res
    
    # Load average match
    load_match = re.search(r'load average[s]?:\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)', output)
    if load_match:
        res["load_1m"] = float(load_match.group(1))
        res["load_5m"] = float(load_match.group(2))
        res["load_15m"] = float(load_match.group(3))
        
    # Uptime match
    up_match = re.search(r'up\s+(.*?),\s+\d+\s+user', output)
    if up_match:
        res["uptime_str"] = up_match.group(1)
    else:
        res["uptime_str"] = output.split(",")[0]
        
    return res


def parse_free_output(output: str) -> Dict[str, Any]:
    """Parse `free -m` output"""
    res = {
        "ram_total_mb": 0.0,
        "ram_used_mb": 0.0,
        "ram_free_mb": 0.0,
        "ram_available_mb": 0.0,
        "ram_percent": 0.0
    }
    for line in output.splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            if len(parts) >= 7:
                total = float(parts[1])
                used = float(parts[2])
                available = float(parts[6]) if len(parts) >= 7 else float(parts[3])
                res["ram_total_mb"] = total
                res["ram_used_mb"] = used
                res["ram_free_mb"] = float(parts[3])
                res["ram_available_mb"] = available
                if total > 0:
                    # Linux actual used = total - available
                    actual_used = total - available
                    res["ram_percent"] = round((actual_used / total) * 100.0, 1)
            break
    return res


def parse_df_output(output: str) -> Dict[str, Any]:
    """Parse `df -m /` output"""
    res = {
        "disk_total_gb": 0.0,
        "disk_used_gb": 0.0,
        "disk_free_gb": 0.0,
        "disk_percent": 0.0
    }
    lines = output.splitlines()
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 5:
            try:
                total_mb = float(parts[1])
                used_mb = float(parts[2])
                free_mb = float(parts[3])
                res["disk_total_gb"] = round(total_mb / 1024.0, 2)
                res["disk_used_gb"] = round(used_mb / 1024.0, 2)
                res["disk_free_gb"] = round(free_mb / 1024.0, 2)
                if total_mb > 0:
                    res["disk_percent"] = round((used_mb / total_mb) * 100.0, 1)
            except ValueError:
                pass
    return res


def collect_metrics_via_ssh(config: Dict[str, Any]) -> Dict[str, Any]:
    """Connect to remote VPS via SSH and collect system metrics"""
    host = config.get("vps_ip", "127.0.0.1")
    port = int(config.get("ssh_port", 22))
    username = config.get("ssh_username", "root")
    password = config.get("ssh_password") or None
    key_text = config.get("ssh_key") or None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    result = {
        "online": False,
        "error": None,
        "host": host,
        "cpu_percent": 0.0,
        "ram_percent": 0.0,
        "ram_used_mb": 0.0,
        "ram_total_mb": 0.0,
        "disk_percent": 0.0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
        "load_1m": 0.0,
        "load_5m": 0.0,
        "load_15m": 0.0,
        "uptime_str": "N/A",
        "hostname": "Unknown",
        "kernel": "Linux"
    }

    try:
        # Connect
        if key_text and key_text.strip():
            import io
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_text.strip()))
            client.connect(hostname=host, port=port, username=username, pkey=pkey, timeout=8)
        elif password:
            client.connect(hostname=host, port=port, username=username, password=password, timeout=8)
        else:
            client.connect(hostname=host, port=port, username=username, timeout=8)

        result["online"] = True

        # Collect metrics in a single multi-command script for high speed
        cmd = "hostname && uname -r && uptime && free -m && df -m / && (grep 'cpu ' /proc/stat; sleep 0.3; grep 'cpu ' /proc/stat)"
        raw_output = execute_ssh_command(client, cmd, timeout=10)
        client.close()

        sections = raw_output.splitlines()
        if len(sections) >= 2:
            result["hostname"] = sections[0].strip()
            result["kernel"] = sections[1].strip()

        # Parse uptime
        uptime_line = ""
        for line in sections:
            if "load average" in line:
                uptime_line = line
                break
        if uptime_line:
            up_data = parse_uptime_output(uptime_line)
            result.update(up_data)

        # Parse free -m
        free_output = "\n".join([l for l in sections if "mem:" in l.lower() or "swap:" in l.lower()])
        if free_output:
            free_data = parse_free_output("Mem: " + free_output)
            result.update(free_data)

        # Parse df -m
        df_lines = [l for l in sections if "/" in l and ("%" in l or "Filesystem" in l)]
        if df_lines:
            df_output = "Filesystem 1024-blocks Used Available Capacity Mounted on\n" + df_lines[-1]
            df_data = parse_df_output(df_output)
            result.update(df_data)

        # Parse CPU percentage from /proc/stat lines
        stat_lines = [l for l in sections if l.startswith("cpu ")]
        if len(stat_lines) >= 2:
            s1 = [int(x) for x in stat_lines[0].split()[1:]]
            s2 = [int(x) for x in stat_lines[1].split()[1:]]
            idle1, total1 = s1[3] + s1[4], sum(s1)
            idle2, total2 = s2[3] + s2[4], sum(s2)
            diff_idle = idle2 - idle1
            diff_total = total2 - total1
            if diff_total > 0:
                cpu_usage = 100.0 * (1.0 - diff_idle / diff_total)
                result["cpu_percent"] = round(max(0.0, min(100.0, cpu_usage)), 1)

    except Exception as e:
        result["online"] = False
        result["error"] = str(e)
        try:
            client.close()
        except Exception:
            pass

    return result


def collect_metrics_local() -> Dict[str, Any]:
    """Collect metrics locally (zero credentials, 100% rootless) when deployed directly on the VPS or local machine"""
    import platform
    result = {
        "online": True,
        "error": None,
        "host": "localhost",
        "cpu_percent": 0.0,
        "ram_percent": 0.0,
        "ram_used_mb": 0.0,
        "ram_total_mb": 0.0,
        "disk_percent": 0.0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
        "load_1m": 0.0,
        "load_5m": 0.0,
        "load_15m": 0.0,
        "uptime_str": "Active",
        "hostname": platform.node() or "localhost",
        "kernel": f"{platform.system()} {platform.release()}"
    }

    try:
        import psutil
        # CPU
        result["cpu_percent"] = round(psutil.cpu_percent(interval=0.2), 1)

        # RAM
        vm = psutil.virtual_memory()
        result["ram_total_mb"] = round(vm.total / (1024 * 1024), 1)
        result["ram_used_mb"] = round(vm.used / (1024 * 1024), 1)
        result["ram_percent"] = round(vm.percent, 1)

        # Disk
        root_path = "C:\\" if platform.system().lower() == "windows" else "/"
        du = psutil.disk_usage(root_path)
        result["disk_total_gb"] = round(du.total / (1024 ** 3), 2)
        result["disk_used_gb"] = round(du.used / (1024 ** 3), 2)
        result["disk_percent"] = round(du.percent, 1)

        # Uptime
        boot_time = psutil.boot_time()
        uptime_sec = time.time() - boot_time
        days = int(uptime_sec // 86400)
        hours = int((uptime_sec % 86400) // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        result["uptime_str"] = f"{days}d {hours}h {minutes}m"

        # Load average (Linux/Unix)
        if hasattr(os, "getloadavg"):
            l1, l5, l15 = os.getloadavg()
            result["load_1m"] = round(l1, 2)
            result["load_5m"] = round(l5, 2)
            result["load_15m"] = round(l15, 2)
        elif hasattr(psutil, "getloadavg"):
            try:
                l1, l5, l15 = psutil.getloadavg()
                result["load_1m"] = round(l1, 2)
                result["load_5m"] = round(l5, 2)
                result["load_15m"] = round(l15, 2)
            except Exception:
                pass

        return result
    except ImportError:
        pass
    except Exception as e:
        result["error"] = str(e)

    # Pure standard library / procfs fallback
    try:
        if hasattr(os, "getloadavg"):
            l1, l5, l15 = os.getloadavg()
            result["load_1m"] = round(l1, 2)
            result["load_5m"] = round(l5, 2)
            result["load_15m"] = round(l15, 2)

        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r") as f:
                uptime_sec = float(f.read().split()[0])
                days = int(uptime_sec // 86400)
                hours = int((uptime_sec % 86400) // 3600)
                minutes = int((uptime_sec % 3600) // 60)
                result["uptime_str"] = f"{days}d {hours}h {minutes}m"

        if os.path.exists("/proc/meminfo"):
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0])
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            if total_kb > 0:
                used_kb = total_kb - avail_kb
                result["ram_total_mb"] = round(total_kb / 1024.0, 1)
                result["ram_used_mb"] = round(used_kb / 1024.0, 1)
                result["ram_percent"] = round((used_kb / total_kb) * 100.0, 1)

        root_path = "C:\\" if platform.system().lower() == "windows" else "/"
        disk = shutil.disk_usage(root_path)
        if disk.total > 0:
            result["disk_total_gb"] = round(disk.total / (1024**3), 2)
            result["disk_used_gb"] = round(disk.used / (1024**3), 2)
            result["disk_percent"] = round((disk.used / disk.total) * 100.0, 1)

        if os.path.exists("/proc/stat"):
            def get_cpu_times():
                with open("/proc/stat", "r") as f:
                    line = f.readline()
                parts = [int(x) for x in line.split()[1:]]
                return parts[3] + parts[4], sum(parts)

            idle1, total1 = get_cpu_times()
            time.sleep(0.2)
            idle2, total2 = get_cpu_times()
            diff_idle = idle2 - idle1
            diff_total = total2 - total1
            if diff_total > 0:
                result["cpu_percent"] = round(100.0 * (1.0 - diff_idle / diff_total), 1)
    except Exception as e:
        result["error"] = str(e)

    return result


def get_system_metrics(config: Dict[str, Any]) -> Dict[str, Any]:
    mode = config.get("connection_mode", "ssh")
    if mode == "local":
        return collect_metrics_local()
    return collect_metrics_via_ssh(config)

