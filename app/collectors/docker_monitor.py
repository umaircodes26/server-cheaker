import json
import subprocess
from typing import Dict, Any, List
import paramiko


def parse_docker_ps_json(output: str) -> List[Dict[str, Any]]:
    containers = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            containers.append({
                "id": data.get("ID", "")[:12],
                "name": data.get("Names", "").replace("/", ""),
                "image": data.get("Image", ""),
                "state": data.get("State", "").lower(),
                "status": data.get("Status", ""),
                "created": data.get("CreatedAt", ""),
                "ports": data.get("Ports", ""),
                "cpu_percent": "0.0%",
                "mem_usage": "0B / 0B",
                "mem_percent": "0.0%"
            })
        except Exception:
            continue
    return containers


def parse_docker_stats_json(output: str, containers: List[Dict[str, Any]]):
    stats_map = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            name = data.get("Name", "").replace("/", "")
            stats_map[name] = {
                "cpu_percent": data.get("CPUPerc", "0%"),
                "mem_usage": data.get("MemUsage", "0B / 0B"),
                "mem_percent": data.get("MemPerc", "0%"),
                "net_io": data.get("NetIO", "0B / 0B"),
                "block_io": data.get("BlockIO", "0B / 0B")
            }
        except Exception:
            continue

    # Merge stats into container objects
    for c in containers:
        name = c["name"]
        if name in stats_map:
            c.update(stats_map[name])


def collect_docker_via_ssh(config: Dict[str, Any]) -> Dict[str, Any]:
    host = config.get("vps_ip", "127.0.0.1")
    port = int(config.get("ssh_port", 22))
    username = config.get("ssh_username", "root")
    password = config.get("ssh_password") or None
    key_text = config.get("ssh_key") or None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    res = {
        "docker_available": False,
        "containers": [],
        "total_count": 0,
        "running_count": 0,
        "stopped_count": 0,
        "error": None
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

        # 1. Check if docker is installed
        cmd_ps = "docker ps -a --format '{{json .}}'"
        stdin, stdout, stderr = client.exec_command(cmd_ps, timeout=10)
        ps_out = stdout.read().decode("utf-8", errors="ignore")
        err_out = stderr.read().decode("utf-8", errors="ignore")

        if err_out and "command not found" in err_out.lower():
            res["error"] = "Docker command not found on VPS."
            client.close()
            return res

        containers = parse_docker_ps_json(ps_out)
        res["docker_available"] = True

        # 2. Get live stats for running containers
        if containers:
            cmd_stats = "docker stats --no-stream --format '{{json .}}'"
            stdin, stdout, stderr = client.exec_command(cmd_stats, timeout=12)
            stats_out = stdout.read().decode("utf-8", errors="ignore")
            parse_docker_stats_json(stats_out, containers)

        client.close()

        res["containers"] = containers
        res["total_count"] = len(containers)
        res["running_count"] = sum(1 for c in containers if c["state"] == "running")
        res["stopped_count"] = res["total_count"] - res["running_count"]

    except Exception as e:
        res["error"] = str(e)
        try:
            client.close()
        except Exception:
            pass

    return res


def collect_docker_local() -> Dict[str, Any]:
    res = {
        "docker_available": False,
        "containers": [],
        "total_count": 0,
        "running_count": 0,
        "stopped_count": 0,
        "error": None
    }
    try:
        cmd_ps = ["docker", "ps", "-a", "--format", "{{json .}}"]
        proc = subprocess.run(cmd_ps, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            res["error"] = proc.stderr.strip() or "Docker daemon not running"
            return res

        containers = parse_docker_ps_json(proc.stdout)
        res["docker_available"] = True

        if containers:
            cmd_stats = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
            stat_proc = subprocess.run(cmd_stats, capture_output=True, text=True, timeout=12)
            if stat_proc.returncode == 0:
                parse_docker_stats_json(stat_proc.stdout, containers)

        res["containers"] = containers
        res["total_count"] = len(containers)
        res["running_count"] = sum(1 for c in containers if c["state"] == "running")
        res["stopped_count"] = res["total_count"] - res["running_count"]
    except Exception as e:
        res["error"] = str(e)

    return res


def restart_container_via_ssh(config: Dict[str, Any], container_id_or_name: str) -> Dict[str, Any]:
    """Helper to restart a container remotely"""
    host = config.get("vps_ip", "127.0.0.1")
    port = int(config.get("ssh_port", 22))
    username = config.get("ssh_username", "root")
    password = config.get("ssh_password") or None
    key_text = config.get("ssh_key") or None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_text and key_text.strip():
            import io
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_text.strip()))
            client.connect(hostname=host, port=port, username=username, pkey=pkey, timeout=8)
        elif password:
            client.connect(hostname=host, port=port, username=username, password=password, timeout=8)
        else:
            client.connect(hostname=host, port=port, username=username, timeout=8)

        cmd = f"docker restart {container_id_or_name}"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
        out = stdout.read().decode("utf-8", errors="ignore").strip()
        err = stderr.read().decode("utf-8", errors="ignore").strip()
        client.close()

        if err:
            return {"success": False, "message": err}
        return {"success": True, "message": f"Container {out} restarted successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_docker_status(config: Dict[str, Any]) -> Dict[str, Any]:
    mode = config.get("connection_mode", "ssh")
    if mode == "local":
        return collect_docker_local()
    return collect_docker_via_ssh(config)

