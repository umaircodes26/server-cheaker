import re
from typing import Dict, Any, List
import paramiko


def parse_failed_ssh_log(log_text: str) -> List[Dict[str, str]]:
    """Extract failed SSH login attempts from auth log"""
    events = []
    # Match: Failed password for invalid user root from 192.168.1.1 port 52123 ssh2
    # or Failed password for root from 1.2.3.4 port 22
    pattern = re.compile(r'Failed password for (?:invalid user )?(\S+) from (\d+\.\d+\.\d+\.\d+)')
    for line in log_text.splitlines():
        match = pattern.search(line)
        if match:
            events.append({
                "user": match.group(1),
                "ip": match.group(2),
                "raw": line.strip()
            })
    return events


def parse_top_processes(proc_text: str) -> List[Dict[str, Any]]:
    """Parse output of ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu | head -n 6"""
    processes = []
    lines = proc_text.splitlines()
    if len(lines) > 1:
        for line in lines[1:]:
            parts = line.split(maxsplit=4)
            if len(parts) >= 5:
                try:
                    processes.append({
                        "pid": parts[0],
                        "user": parts[1],
                        "cpu": float(parts[2]),
                        "mem": float(parts[3]),
                        "command": parts[4]
                    })
                except ValueError:
                    pass
    return processes


def collect_security_info_via_ssh(config: Dict[str, Any]) -> Dict[str, Any]:
    host = config.get("vps_ip", "127.0.0.1")
    port = int(config.get("ssh_port", 22))
    username = config.get("ssh_username", "root")
    password = config.get("ssh_password") or None
    key_text = config.get("ssh_key") or None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    res = {
        "failed_ssh_attempts": [],
        "recent_oom_events": [],
        "top_processes": []
    }

    try:
        if key_text and key_text.strip():
            import io
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_text.strip()))
            client.connect(hostname=host, port=port, username=username, pkey=pkey, timeout=8)
        elif password:
            client.connect(hostname=host, port=port, username=username, password=password, timeout=8)
        else:
            client.connect(hostname=host, port=port, username=username, timeout=8)

        # 1. Failed SSH attempts
        cmd_auth = "tail -n 30 /var/log/auth.log 2>/dev/null || journalctl -u ssh -n 30 2>/dev/null || journalctl -u sshd -n 30 2>/dev/null"
        stdin, stdout, stderr = client.exec_command(cmd_auth, timeout=6)
        auth_out = stdout.read().decode("utf-8", errors="ignore")
        res["failed_ssh_attempts"] = parse_failed_ssh_log(auth_out)

        # 2. OOM Killer checks
        cmd_oom = "dmesg | grep -i -E 'oom-killer|out of memory' | tail -n 5 2>/dev/null"
        stdin, stdout, stderr = client.exec_command(cmd_oom, timeout=6)
        oom_out = stdout.read().decode("utf-8", errors="ignore")
        res["recent_oom_events"] = [l.strip() for l in oom_out.splitlines() if l.strip()]

        # 3. Top resource hog processes
        cmd_proc = "ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu | head -n 6"
        stdin, stdout, stderr = client.exec_command(cmd_proc, timeout=6)
        proc_out = stdout.read().decode("utf-8", errors="ignore")
        res["top_processes"] = parse_top_processes(proc_out)

        client.close()
    except Exception:
        try:
            client.close()
        except Exception:
            pass

    return res


def collect_security_info_local() -> Dict[str, Any]:
    """Collect security telemetry locally without root privileges"""
    import os
    res = {
        "failed_ssh_attempts": [],
        "recent_oom_events": [],
        "top_processes": []
    }

    # 1. Top resource processes locally via psutil or ps command
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                procs.append({
                    "pid": str(info.get('pid', '')),
                    "user": str(info.get('username') or 'system').split('\\')[-1],
                    "cpu": round(float(info.get('cpu_percent') or 0.0), 1),
                    "mem": round(float(info.get('memory_percent') or 0.0), 1),
                    "command": str(info.get('name') or 'unknown')
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Sort by CPU descending
        procs.sort(key=lambda x: x["cpu"], reverse=True)
        res["top_processes"] = procs[:6]
    except Exception:
        try:
            import subprocess
            proc = subprocess.run(
                ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
                capture_output=True, text=True, timeout=5
            )
            if proc.returncode == 0:
                res["top_processes"] = parse_top_processes(proc.stdout)
        except Exception:
            pass

    # 2. Failed SSH attempts (safe read, ignores permission issues on non-root)
    try:
        import subprocess
        cmd_journal = ["journalctl", "-u", "ssh", "-n", "30", "--no-pager"]
        proc = subprocess.run(cmd_journal, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout:
            res["failed_ssh_attempts"] = parse_failed_ssh_log(proc.stdout)
        elif os.path.exists("/var/log/auth.log"):
            with open("/var/log/auth.log", "r", errors="ignore") as f:
                lines = f.readlines()[-30:]
                res["failed_ssh_attempts"] = parse_failed_ssh_log("".join(lines))
    except Exception:
        pass

    # 3. OOM Killer checks (safe read)
    try:
        import subprocess
        proc = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout:
            matches = [l.strip() for l in proc.stdout.splitlines() if re.search(r'oom-killer|out of memory', l, re.IGNORECASE)]
            res["recent_oom_events"] = matches[-5:]
    except Exception:
        pass

    return res


def get_security_info(config: Dict[str, Any]) -> Dict[str, Any]:
    mode = config.get("connection_mode", "ssh")
    if mode == "local":
        return collect_security_info_local()
    return collect_security_info_via_ssh(config)

