# 🛡️ VPS Sentinel — 24/7 Server, Docker & Website Watchdog

**VPS Sentinel** ek powerful, automated aur 24/7 chalne wala monitoring system hai jo aapke VPS ki sari activities, health, Docker containers aur hosted websites ko monitor karta hai.

---

## 🌟 Key Features (Khususiyaat)

1. **24/7 Real-Time Health & Resource Monitoring**:
   - CPU Usage & Load Averages (1m, 5m, 15m).
   - RAM Usage (Total, Used, Free MB aur Percentage).
   - Root Disk Space (Total, Used GB aur Percentage).
   - Server Uptime aur Operating System specs.
   - Top CPU/Memory consuming processes track karna.

2. **Docker Containers Monitoring**:
   - Har custom Docker container ka live status (Running, Exited, Restarting, Dead).
   - Har container ki CPU% aur Memory consumption.
   - Ports mapping aur container details.
   - Dashboard se direct **one-click Container Restart** karne ki sahulat.

3. **Websites & Custom Endpoints Health**:
   - VPS par host hone wali tamam websites aur APIs ka live HTTP status code (200, 404, 502, etc.).
   - Response latency in milliseconds (ms).
   - Instant downtime detection.

4. **🚨 Immediate Discord Alerts (Unusual Activity)**:
   - Kisi bhi Docker container ke crash ya stop hone par **foran alert**.
   - Website ke down hone ya 502/500 error dene par **foran alert**.
   - CPU / RAM / Disk usage ke critical threshold cross karne par **foran alert**.
   - SSH brute-force attack (repeated failed login attempts) detect hone par **foran alert**.
   - **Service Recovery Alert**: Jab issue solve ho jaye to automatically green `[RESOLVED]` notification bhaijta hai.
   - Smart alert cooldown taake Discord channel par bar bar spam na ho.

5. **📊 6-Hour Scheduled Discord Report**:
   - Har 6 ghante baad automatically ek visually rich Discord Embed report deliver karta hai:
     - Overall Health score
     - 6-hour average aur peak CPU/RAM
     - Tamam Docker containers ka status summary
     - Websites ka uptime aur average latency
     - Pichle 6 ghante ke total incidents count

6. **🖥️ Modern Glassmorphism Web GUI**:
   - Clean, interactive dark-theme dashboard.
   - Live Chart.js dynamic graph for CPU & RAM trends.
   - Quick "Scan Now" button.
   - "Send 6-Hour Report to Discord Now" button.
   - "Test Discord Alert" button.
   - GUI se direct websites add/remove karne aur settings update karne ki sahulat.

---

## 📁 Project Structure

```
vps_sentinel/
├── app/
│   ├── config.py              # Configuration storage (data/config.json)
│   ├── database.py            # SQLite database for history & metrics
│   ├── collectors/
│   │   ├── system_metrics.py  # CPU, RAM, Disk, Uptime via SSH / Local
│   │   ├── docker_monitor.py  # Docker ps & stats inspector
│   │   ├── web_checker.py     # HTTP/HTTPS async health checker
│   │   └── security_log.py    # Failed SSH attempts & process hogs
│   ├── engine/
│   │   ├── anomaly_detector.py # Smart threshold & crash detection
│   │   ├── discord.py          # Discord Webhooks (Alerts, Recovery, 6h Reports)
│   │   └── scheduler.py        # 30s monitoring loop & 6h cron report
│   ├── static/
│   │   ├── css/style.css      # Dark glassmorphic styling
│   │   └── js/dashboard.js    # Live GUI logic & Chart.js
│   ├── templates/
│   │   └── index.html         # Web Dashboard
│   └── main.py                # FastAPI backend & REST API
├── data/                      # Auto-created SQLite DB & config file
├── Dockerfile                 # Production Docker image
├── docker-compose.yml         # 1-Command deployment
├── requirements.txt           # Python dependencies
├── run.py                     # Launcher script
└── README.md                  # Documentation
```

---

## 🚀 How to Run Locally (Local Test)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start the System
```bash
python run.py
```

### Step 3: Open Dashboard GUI
Apne browser mein jayein:
👉 **`http://localhost:8000`**

---

## ⚙️ How to Configure in GUI

1. **Dashboard open karein** aur **"Control & Settings"** tab par click karein:
   - **Server Name**: Apne server ka koi bhi naam likhein (e.g. `My Production VPS`).
   - **VPS IP Address**: Apne VPS ka IP enter karein.
   - **SSH Username / Password ya Key**: Enter karein taake watchdog remote VPS se Docker aur system health fetch kar sakay.
   - **Discord Webhook URL**: Apne Discord channel ka webhook URL paste karein.
   - **Thresholds**: CPU%, RAM%, Disk% thresholds set karein (default 85%, 90%, 90%).
2. **"Save Settings"** par click karein.
3. **"Test Alert"** button dabayein — aapke Discord par foran test message aa jaye ga!

---

## 🌐 24/7 Free Deployment Guide (Kahan Deploy Karein?)

### Option 1: Direct on your VPS (Recommended & 100% Free)
Chunky aapke paas already VPS mojood hai, sab se best tareeqa yeh hai ke aap is program ko VPS par direct chala dein:
- **Faida**: 0 latency, koi extra hosting ka kharch nahi, aur Docker socket ko direct monitor kar sakta hai bina kisi SSH password ke!
- **Steps**:
  ```bash
  # 1. Project ko VPS par clone ya copy karein
  git clone <repo_url> vps_sentinel
  cd vps_sentinel

  # 2. Docker compose se 24/7 background mein start karein:
  docker compose up -d
  ```
  Ab aapka watchdog 24/7 background mein chalta rahay ga!

### Option 2: Render.com (Free Tier)
1. GitHub par ye repository push karein.
2. [Render.com](https://render.com) par jayein -> **New Web Service**.
3. Apni repo select karein -> Environment: **Docker**.
4. Free plan select karein aur Deploy par click karein.
5. Render aapko ek live public URL de de ga jahan se aap dashboard access kar sakein ge.

### Option 3: Koyeb / Fly.io (Free Tier)
1. Koyeb ya Fly.io par Docker deployment select karein.
2. Free tier mein deploy karein, ye 24/7 live rehta hai.

### Option 4: Linux Systemd Service (VPS par bina Docker ke)
Agar Docker use nahi karna to Linux VPS par background service bana lein:
```bash
sudo nano /etc/systemd/system/vps-sentinel.service
```
Paste karein:
```ini
[Unit]
Description=VPS Sentinel 24/7 Watchdog
After=network.target

[Service]
User=root
WorkingDirectory=/path/to/vps_sentinel
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Start karein:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vps-sentinel
```

---

## 💬 Discord Notification Preview

### 🚨 Unusual Activity Alert (Instant)
```
🚨 [CRITICAL] Unusual Activity: Docker Container Crashed / Stopped: client-api
🖥️ Target VPS: Production VPS (192.168.1.100)
⏰ Detected At: Just now
📋 Details: Container client-api (node:18) is in exited state! Status: Exited (1) 45 seconds ago.
💡 Recommended Action: Run docker logs client-api and docker restart client-api
```

### 📊 6-Hour Scheduled Report (Every 6h)
```
📊 [6-HOUR REPORT] Server Health & Analytics Digest
Performance and health report for Production VPS (192.168.1.100)

🏥 System Health Status: 🟢 Excellent | Uptime: 45d 12h | Load (15m): 0.35
⚡ Resource Metrics:
   CPU: Current 12.4% | Avg 18.2% | Peak 45.1%
   RAM: Current 42.1% | Avg 41.5% | Peak 58.0%
   Disk: 18.5GB / 50.0GB (37.0% used)
🐳 Docker Containers: 6/6 Running (🟢 nginx, 🟢 postgres, 🟢 redis, 🟢 app)
🌐 Monitored Websites: 3/3 Up (🟢 Store API: 42ms, 🟢 Landing: 18ms)
🛡️ Incident Summary: 0 Alerts in last 6 hours
```

