// VPS Sentinel Dashboard Client
let metricsChart = null;
let currentConfig = {};

// Auth & API Key helpers
function getApiKey() {
  return localStorage.getItem("sentinel_api_key") || "";
}

function setApiKey(key) {
  if (key) {
    localStorage.setItem("sentinel_api_key", key);
  } else {
    localStorage.removeItem("sentinel_api_key");
  }
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  opts.headers = { ...(opts.headers || {}) };
  const key = getApiKey();
  if (key) {
    opts.headers["X-API-Key"] = key;
  }

  const res = await fetch(url, opts);
  if (res.status === 401) {
    openAuthModal();
  }
  return res;
}

function openAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    const input = document.getElementById("auth-input-key");
    if (input) {
      input.value = getApiKey();
      input.focus();
    }
    const err = document.getElementById("auth-error-msg");
    if (err) err.classList.add("hidden");
  }
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

async function submitAuthKey(e) {
  e.preventDefault();
  const input = document.getElementById("auth-input-key");
  const key = input ? input.value.trim() : "";
  const errDiv = document.getElementById("auth-error-msg");

  try {
    const res = await fetch("/api/auth/status", {
      headers: { "X-API-Key": key }
    });
    const data = await res.json();
    if (data.authenticated) {
      setApiKey(key);
      closeAuthModal();
      showToast("Access granted!", "success");
      updateAuthUI();
      fetchTelemetry();
      loadConfig();
      loadAlertsHistory();
    } else {
      if (errDiv) {
        errDiv.textContent = "Invalid API Key. Please try again.";
        errDiv.classList.remove("hidden");
      }
    }
  } catch (err) {
    if (errDiv) {
      errDiv.textContent = "Failed to verify API Key.";
      errDiv.classList.remove("hidden");
    }
  }
}

async function updateAuthUI() {
  try {
    const key = getApiKey();
    const headers = key ? { "X-API-Key": key } : {};
    const res = await fetch("/api/auth/status", { headers });
    if (res.ok) {
      const data = await res.json();
      const label = document.getElementById("header-auth-label");
      const hint = document.getElementById("api-key-status-hint");
      if (data.auth_required) {
        if (data.authenticated) {
          if (label) label.textContent = "Key Active";
          if (hint) hint.innerHTML = 'Status: <span class="text-emerald-400 font-semibold font-mono">Protected & Active</span>';
        } else {
          if (label) label.textContent = "Locked";
          if (hint) hint.innerHTML = 'Status: <span class="text-rose-400 font-semibold font-mono">Locked (Auth Required)</span>';
          openAuthModal();
        }
      } else {
        if (label) label.textContent = "API Key";
        if (hint) hint.innerHTML = 'Status: <span class="text-amber-400 font-medium font-mono">Open Access (No Key)</span>';
      }
    }
  } catch (err) {
    console.error("Auth status error:", err);
  }
}

function toggleApiKeyVisibility() {
  const input = document.getElementById("cfg-api-key");
  const icon = document.getElementById("toggle-eye-icon");
  if (!input) return;
  if (input.type === "password") {
    input.type = "text";
    if (icon) icon.setAttribute("data-lucide", "eye-off");
  } else {
    input.type = "password";
    if (icon) icon.setAttribute("data-lucide", "eye");
  }
  lucide.createIcons();
}

function toggleConnectionModeUI() {
  const mode = document.getElementById("cfg-connection-mode").value;
  const sshGroup = document.getElementById("ssh-fields-group");
  const localInfo = document.getElementById("local-mode-info");
  if (mode === "local") {
    if (sshGroup) sshGroup.classList.add("hidden");
    if (localInfo) localInfo.classList.remove("hidden");
  } else {
    if (sshGroup) sshGroup.classList.remove("hidden");
    if (localInfo) localInfo.classList.add("hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  initChart();
  updateAuthUI();
  loadConfig();
  fetchTelemetry();
  loadAlertsHistory();

  // Auto-refresh telemetry every 10 seconds
  setInterval(fetchTelemetry, 10000);
});

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  const bg = type === "success" ? "bg-emerald-950 border-emerald-600 text-emerald-200" :
             type === "error" ? "bg-rose-950 border-rose-600 text-rose-200" :
             "bg-slate-900 border-cyan-600 text-cyan-200";

  toast.className = `p-3.5 rounded-lg border shadow-xl text-xs flex items-center justify-between gap-3 transition-all duration-300 ${bg}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" class="text-gray-400 hover:text-white">&times;</button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.getElementById(tabId).classList.remove("hidden");

  document.querySelectorAll(".tab-btn").forEach(el => {
    el.classList.remove("border-cyan-500", "text-cyan-400");
    el.classList.add("border-transparent", "text-gray-400");
  });

  const activeBtn = document.getElementById(`btn-${tabId}`);
  if (activeBtn) {
    activeBtn.classList.add("border-cyan-500", "text-cyan-400");
    activeBtn.classList.remove("border-transparent", "text-gray-400");
  }

  if (tabId === "tab-alerts") {
    loadAlertsHistory();
  }
}

// Chart.js Setup
function initChart() {
  const ctx = document.getElementById("metricsChart").getContext("2d");
  metricsChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "CPU Usage (%)",
          borderColor: "#06b6d4",
          backgroundColor: "rgba(6, 182, 212, 0.1)",
          borderWidth: 2,
          pointRadius: 2,
          fill: true,
          tension: 0.3,
          data: []
        },
        {
          label: "RAM Usage (%)",
          borderColor: "#818cf8",
          backgroundColor: "rgba(129, 140, 248, 0.1)",
          borderWidth: 2,
          pointRadius: 2,
          fill: true,
          tension: 0.3,
          data: []
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#6b7280", font: { family: "JetBrains Mono", size: 10 } }
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#6b7280", font: { family: "JetBrains Mono", size: 10 } }
        }
      }
    }
  });
}

// Telemetry Polling
async function fetchTelemetry() {
  try {
    const res = await apiFetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

function updateUI(data) {
  const sys = data.system || {};
  const docker = data.docker || {};
  const sites = data.websites || [];
  const security = data.security || {};

  // Header & IP
  document.getElementById("header-vps-ip").textContent = sys.host || "127.0.0.1";
  const connElem = document.getElementById("header-connection-status");
  if (sys.online) {
    connElem.innerHTML = `<span class="pulse-indicator pulse-green"></span> Online & Active`;
    connElem.className = "flex items-center gap-1.5 ml-2 text-xs text-emerald-400";
  } else {
    connElem.innerHTML = `<span class="pulse-indicator pulse-red"></span> Unreachable`;
    connElem.className = "flex items-center gap-1.5 ml-2 text-xs text-rose-400";
  }

  // CPU Card
  const cpu = sys.cpu_percent || 0;
  document.getElementById("card-cpu-percent").textContent = `${cpu.toFixed(1)}%`;
  document.getElementById("card-cpu-bar").style.width = `${Math.min(100, cpu)}%`;
  document.getElementById("card-cpu-load").textContent = `Load: ${(sys.load_15m || 0).toFixed(2)}`;
  const cpuBadge = document.getElementById("card-cpu-badge");
  if (cpu > 85) {
    cpuBadge.className = "text-xs px-2 py-0.5 rounded bg-rose-950 text-rose-400 border border-rose-800/40";
    cpuBadge.textContent = "High Load";
  } else {
    cpuBadge.className = "text-xs px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/40";
    cpuBadge.textContent = "Normal";
  }

  // RAM Card
  const ram = sys.ram_percent || 0;
  document.getElementById("card-ram-percent").textContent = `${ram.toFixed(1)}%`;
  document.getElementById("card-ram-bar").style.width = `${Math.min(100, ram)}%`;
  document.getElementById("card-ram-mb").textContent = `${sys.ram_used_mb || 0} / ${sys.ram_total_mb || 0} MB`;
  const ramBadge = document.getElementById("card-ram-badge");
  if (ram > 90) {
    ramBadge.className = "text-xs px-2 py-0.5 rounded bg-rose-950 text-rose-400 border border-rose-800/40";
    ramBadge.textContent = "Critical";
  } else {
    ramBadge.className = "text-xs px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/40";
    ramBadge.textContent = "Optimal";
  }

  // Disk Card
  const disk = sys.disk_percent || 0;
  document.getElementById("card-disk-percent").textContent = `${disk.toFixed(1)}%`;
  document.getElementById("card-disk-bar").style.width = `${Math.min(100, disk)}%`;
  document.getElementById("card-disk-gb").textContent = `${sys.disk_used_gb || 0} / ${sys.disk_total_gb || 0} GB`;

  // Docker & Sites Card
  document.getElementById("card-uptime-str").textContent = `Up: ${sys.uptime_str || "N/A"}`;
  document.getElementById("card-containers-count").textContent = `${docker.running_count || 0}/${docker.total_count || 0}`;
  document.getElementById("tab-docker-badge").textContent = `${docker.running_count || 0}/${docker.total_count || 0}`;

  const sitesUp = sites.filter(s => s.is_up).length;
  document.getElementById("card-websites-count").textContent = `${sitesUp}/${sites.length}`;
  document.getElementById("tab-web-badge").textContent = `${sitesUp}/${sites.length}`;
  document.getElementById("card-hostname").textContent = sys.hostname || "vps";

  // Specs & Top Processes
  document.getElementById("spec-server-name").textContent = currentConfig.server_name || "VPS";
  document.getElementById("spec-vps-ip").textContent = sys.host || "127.0.0.1";
  document.getElementById("spec-kernel").textContent = sys.kernel || "Linux";
  document.getElementById("spec-load").textContent = `${sys.load_1m || 0}, ${sys.load_5m || 0}, ${sys.load_15m || 0}`;
  document.getElementById("spec-mode").textContent = currentConfig.connection_mode === "local" ? "Direct Host Mode" : "SSH Remote Agentless";

  renderTopProcesses(security.top_processes || []);
  renderDockerTable(docker.containers || []);
  renderWebsitesTable(sites);

  // Update Chart
  updateChartData(data.history || []);
  lucide.createIcons();
}

function updateChartData(history) {
  if (!metricsChart || !history.length) return;
  const labels = history.map(h => {
    const d = new Date(h.timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  });
  const cpuData = history.map(h => h.cpu_percent || 0);
  const ramData = history.map(h => h.ram_percent || 0);

  metricsChart.data.labels = labels;
  metricsChart.data.datasets[0].data = cpuData;
  metricsChart.data.datasets[1].data = ramData;
  metricsChart.update();
}

function renderTopProcesses(procs) {
  const tbody = document.getElementById("top-processes-tbody");
  if (!procs.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="py-4 text-center text-gray-500">No high-utilization processes detected.</td></tr>`;
    return;
  }
  tbody.innerHTML = procs.map(p => `
    <tr>
      <td class="py-1.5 text-cyan-400">${p.pid}</td>
      <td class="py-1.5 text-gray-400">${p.user}</td>
      <td class="py-1.5 text-gray-200 truncate max-w-xs" title="${p.command}">${p.command}</td>
      <td class="py-1.5 text-right font-medium ${p.cpu > 50 ? 'text-rose-400' : 'text-gray-300'}">${p.cpu}%</td>
      <td class="py-1.5 text-right text-gray-400">${p.mem}%</td>
    </tr>
  `).join("");
}

function renderDockerTable(containers) {
  const tbody = document.getElementById("docker-containers-tbody");
  if (!containers.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-gray-500 font-mono">No Docker containers detected on this server.</td></tr>`;
    return;
  }
  tbody.innerHTML = containers.map(c => {
    const isRunning = c.state === "running";
    const badgeClass = isRunning ? "bg-emerald-950 text-emerald-400 border-emerald-800/50" : "bg-rose-950 text-rose-400 border-rose-800/50";
    return `
      <tr class="hover:bg-white/[0.02] transition-colors">
        <td class="py-2.5 px-3">
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono border ${badgeClass}">
            <span class="w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
            ${c.state.toUpperCase()}
          </span>
        </td>
        <td class="py-2.5 px-3 font-semibold text-white font-mono">${c.name}</td>
        <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px] truncate max-w-[150px]" title="${c.image}">${c.image}</td>
        <td class="py-2.5 px-3 font-mono text-cyan-300">${c.cpu_percent || '0.0%'}</td>
        <td class="py-2.5 px-3 font-mono text-gray-300">${c.mem_usage || '0B'}</td>
        <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px] truncate max-w-[120px]" title="${c.ports}">${c.ports || '-'}</td>
        <td class="py-2.5 px-3 text-right">
          <button onclick="restartContainer('${c.name}')" class="px-2.5 py-1 text-[11px] font-medium rounded bg-white/5 hover:bg-white/10 text-cyan-300 border border-white/10 transition-colors">
            Restart
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderWebsitesTable(sites) {
  const tbody = document.getElementById("websites-tbody");
  if (!sites.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-gray-500 font-mono">No websites configured yet. Add your first site!</td></tr>`;
    return;
  }
  tbody.innerHTML = sites.map(s => {
    const isUp = s.is_up;
    const badgeClass = isUp ? "bg-emerald-950 text-emerald-400 border-emerald-800/50" : "bg-rose-950 text-rose-400 border-rose-800/50";
    return `
      <tr class="hover:bg-white/[0.02] transition-colors">
        <td class="py-2.5 px-3">
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono border ${badgeClass}">
            <span class="w-1.5 h-1.5 rounded-full ${isUp ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
            ${isUp ? 'ONLINE' : 'DOWN'}
          </span>
        </td>
        <td class="py-2.5 px-3 font-medium text-white">${s.name}</td>
        <td class="py-2.5 px-3 font-mono text-cyan-300 text-[11px]">
          <a href="${s.url}" target="_blank" class="hover:underline flex items-center gap-1">
            ${s.url} <i data-lucide="external-link" class="w-3 h-3 inline"></i>
          </a>
        </td>
        <td class="py-2.5 px-3 font-mono ${isUp ? 'text-gray-300' : 'text-rose-400 font-bold'}">${s.status_code || 'N/A'}</td>
        <td class="py-2.5 px-3 font-mono ${s.response_time_ms > 1000 ? 'text-amber-400' : 'text-emerald-400'}">${s.response_time_ms ? s.response_time_ms + ' ms' : '-'}</td>
        <td class="py-2.5 px-3 text-right">
          <button onclick="deleteWebsite('${s.id}')" class="px-2 py-1 text-[11px] rounded bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800/30">
            Remove
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function loadAlertsHistory() {
  try {
    const res = await apiFetch("/api/alerts");
    if (!res.ok) return;
    const alerts = await res.json();
    document.getElementById("card-alerts-count").textContent = `${alerts.length} Incidents`;
    document.getElementById("tab-alert-badge").textContent = `${alerts.length}`;

    const tbody = document.getElementById("alerts-tbody");
    if (!alerts.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-gray-500 font-mono">No unusual activities recorded. Server healthy!</td></tr>`;
      return;
    }
    tbody.innerHTML = alerts.map(a => {
      const isCrit = a.severity === "CRITICAL";
      const isRec = a.severity === "RECOVERY";
      const badge = isCrit ? "bg-rose-950 text-rose-400 border-rose-800/40" :
                    isRec ? "bg-emerald-950 text-emerald-400 border-emerald-800/40" :
                    "bg-amber-950 text-amber-400 border-amber-800/40";
      const timeStr = new Date(a.timestamp).toLocaleString();
      return `
        <tr class="hover:bg-white/[0.02] text-xs">
          <td class="py-2 px-3 font-mono text-gray-400 text-[11px] whitespace-nowrap">${timeStr}</td>
          <td class="py-2 px-3">
            <span class="px-1.5 py-0.5 rounded text-[10px] font-mono border ${badge}">${a.severity}</span>
          </td>
          <td class="py-2 px-3 font-mono text-gray-300 text-[11px]">${a.alert_type}</td>
          <td class="py-2 px-3 font-medium text-white">${a.title}</td>
          <td class="py-2 px-3 text-gray-300 max-w-sm truncate" title="${a.message}">${a.message}</td>
          <td class="py-2 px-3 text-right">
            <span class="text-[11px] font-mono ${a.discord_sent ? 'text-emerald-400' : 'text-gray-500'}">
              ${a.discord_sent ? '✓ Dispatched' : 'No Webhook'}
            </span>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Alerts history error:", err);
  }
}

// Config management
async function loadConfig() {
  try {
    const res = await apiFetch("/api/config");
    if (!res.ok) return;
    currentConfig = await res.json();

    document.getElementById("cfg-server-name").value = currentConfig.server_name || "";
    document.getElementById("cfg-vps-ip").value = currentConfig.vps_ip || "127.0.0.1";
    document.getElementById("cfg-ssh-port").value = currentConfig.ssh_port || 22;
    document.getElementById("cfg-ssh-username").value = currentConfig.ssh_username || "";
    document.getElementById("cfg-ssh-password").value = currentConfig.ssh_password || "";
    document.getElementById("cfg-ssh-key").value = currentConfig.ssh_key || "";
    
    const mode = currentConfig.connection_mode || "local";
    document.getElementById("cfg-connection-mode").value = mode;
    toggleConnectionModeUI();

    document.getElementById("cfg-api-key").value = currentConfig.api_key || "";

    document.getElementById("cfg-discord-webhook").value = currentConfig.discord_webhook_url || "";
    document.getElementById("cfg-report-hours").value = currentConfig.report_interval_hours || 6;
    document.getElementById("cfg-check-seconds").value = currentConfig.check_interval_seconds || 30;
    document.getElementById("cfg-cooldown-mins").value = currentConfig.alert_cooldown_minutes || 15;

    const thresh = currentConfig.thresholds || {};
    document.getElementById("cfg-thresh-cpu").value = thresh.cpu_percent || 85;
    document.getElementById("cfg-thresh-ram").value = thresh.ram_percent || 90;
    document.getElementById("cfg-thresh-disk").value = thresh.disk_percent || 90;

    updateAuthUI();
  } catch (err) {
    console.error("Load config error:", err);
  }
}

async function saveConfiguration(e) {
  e.preventDefault();
  const inputApiKey = document.getElementById("cfg-api-key").value;
  const updated = {
    ...currentConfig,
    server_name: document.getElementById("cfg-server-name").value.trim(),
    vps_ip: document.getElementById("cfg-vps-ip").value.trim(),
    ssh_port: parseInt(document.getElementById("cfg-ssh-port").value) || 22,
    ssh_username: document.getElementById("cfg-ssh-username").value.trim(),
    ssh_password: document.getElementById("cfg-ssh-password").value,
    ssh_key: document.getElementById("cfg-ssh-key").value,
    connection_mode: document.getElementById("cfg-connection-mode").value,
    api_key: inputApiKey,
    discord_webhook_url: document.getElementById("cfg-discord-webhook").value.trim(),
    report_interval_hours: parseFloat(document.getElementById("cfg-report-hours").value),
    check_interval_seconds: parseInt(document.getElementById("cfg-check-seconds").value),
    alert_cooldown_minutes: parseFloat(document.getElementById("cfg-cooldown-mins").value),
    thresholds: {
      cpu_percent: parseFloat(document.getElementById("cfg-thresh-cpu").value),
      ram_percent: parseFloat(document.getElementById("cfg-thresh-ram").value),
      disk_percent: parseFloat(document.getElementById("cfg-thresh-disk").value)
    }
  };

  try {
    const res = await apiFetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated)
    });
    if (res.ok) {
      if (inputApiKey && inputApiKey !== "••••••••") {
        setApiKey(inputApiKey);
      }
      showToast("Configuration saved successfully!", "success");
      currentConfig = updated;
      updateAuthUI();
      fetchTelemetry();
    } else {
      showToast("Failed to save configuration.", "error");
    }
  } catch (err) {
    showToast("Network error saving configuration", "error");
  }
}

// User Actions
async function triggerManualRefresh() {
  const btn = document.getElementById("btn-manual-refresh");
  btn.classList.add("opacity-50", "pointer-events-none");
  showToast("Scanning VPS telemetry...", "info");
  try {
    await apiFetch("/api/scan", { method: "POST" });
    await fetchTelemetry();
    showToast("Scan completed!", "success");
  } catch (err) {
    showToast("Scan encountered an issue", "error");
  } finally {
    btn.classList.remove("opacity-50", "pointer-events-none");
  }
}

async function testDiscordWebhook() {
  showToast("Sending test notification to Discord...", "info");
  try {
    const res = await apiFetch("/api/discord/test", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("Discord test alert sent successfully! Check your channel.", "success");
    } else {
      showToast(`Discord test failed: ${data.message || 'Check Webhook URL'}`, "error");
    }
  } catch (err) {
    showToast("Discord test request failed", "error");
  }
}

async function trigger6HourReport() {
  showToast("Generating and sending 6-Hour Report to Discord...", "info");
  try {
    const res = await apiFetch("/api/discord/report", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("6-Hour Report sent to Discord successfully!", "success");
    } else {
      showToast(`Report dispatch failed: ${data.message || 'Check Discord Webhook'}`, "error");
    }
  } catch (err) {
    showToast("Report dispatch error", "error");
  }
}

async function restartContainer(containerName) {
  if (!confirm(`Are you sure you want to restart container "${containerName}"?`)) return;
  showToast(`Restarting ${containerName}...`, "info");
  try {
    const res = await apiFetch(`/api/docker/restart?name=${encodeURIComponent(containerName)}`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      setTimeout(fetchTelemetry, 2000);
    } else {
      showToast(`Restart error: ${data.message}`, "error");
    }
  } catch (err) {
    showToast("Failed to execute restart", "error");
  }
}

// Website Modal & Actions
function openAddWebsiteModal() {
  document.getElementById("add-website-modal").classList.remove("hidden");
  document.getElementById("add-website-modal").classList.add("flex");
}

function closeAddWebsiteModal() {
  document.getElementById("add-website-modal").classList.add("hidden");
  document.getElementById("add-website-modal").classList.remove("flex");
}

async function saveNewWebsite(e) {
  e.preventDefault();
  const name = document.getElementById("modal-site-name").value.trim();
  const url = document.getElementById("modal-site-url").value.trim();
  const expectedCode = parseInt(document.getElementById("modal-site-code").value);
  const timeout = parseFloat(document.getElementById("modal-site-timeout").value);

  const newSite = {
    id: "site-" + Date.now(),
    name,
    url,
    expected_code: expectedCode,
    timeout_seconds: timeout
  };

  const updatedSites = [...(currentConfig.monitored_websites || []), newSite];
  currentConfig.monitored_websites = updatedSites;

  try {
    await apiFetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfig)
    });
    closeAddWebsiteModal();
    showToast(`Added ${name} to monitoring!`, "success");
    fetchTelemetry();
  } catch (err) {
    showToast("Error adding website", "error");
  }
}

async function deleteWebsite(siteId) {
  if (!confirm("Are you sure you want to remove this website from monitoring?")) return;
  currentConfig.monitored_websites = (currentConfig.monitored_websites || []).filter(s => s.id !== siteId);
  try {
    await apiFetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfig)
    });
    showToast("Website removed.", "info");
    fetchTelemetry();
  } catch (err) {
    showToast("Error removing website", "error");
  }
}

