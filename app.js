const refreshMs = 60000;
let timer = null;

const $ = (id) => document.getElementById(id);

// Theme handling
function initTheme() {
  const root = document.documentElement;
  const toggleBtn = $("theme-toggle");
  const saved = localStorage.getItem("theme");

  const applyTheme = (theme) => {
    if (theme === "dark") {
      root.setAttribute("data-theme", "dark");
      if (toggleBtn) toggleBtn.textContent = "☀️";
      if (toggleBtn) toggleBtn.title = "Switch to light mode";
    } else {
      root.removeAttribute("data-theme");
      if (toggleBtn) toggleBtn.textContent = "🌙";
      if (toggleBtn) toggleBtn.title = "Switch to dark mode";
    }
  };

  // Apply saved or default (light)
  applyTheme(saved === "dark" ? "dark" : "light");

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const isDark = root.getAttribute("data-theme") === "dark";
      const newTheme = isDark ? "light" : "dark";
      localStorage.setItem("theme", newTheme);
      applyTheme(newTheme);
    });
  }
}

function fmtNumber(value) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat().format(value);
}

function fmtBytes(bytes) {
  if (bytes === null || bytes === undefined) return "--";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function fmtSeconds(seconds) {
  if (seconds === null || seconds === undefined) return "--";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function fmtTime(epochSeconds) {
  if (!epochSeconds) return "--";
  return new Date(epochSeconds * 1000).toLocaleString();
}

function serviceLabel(service) {
  if (!service) return "unknown";
  const state = service.running ? "running" : "stopped";
  if (service.progress_percent !== undefined && service.progress_percent !== null) {
    return `${state}, ${service.progress_percent.toFixed(1)}%`;
  }
  return service.uptime_seconds ? `${state}, ${fmtSeconds(service.uptime_seconds)}` : state;
}

function statusWord(value) {
  return value ? "OK" : "No";
}

function applyFeatures(data) {
  const features = data.features || {};
  document.querySelectorAll("[data-feature]").forEach((element) => {
    const feature = features[element.dataset.feature];
    element.classList.toggle("hidden", !feature || !feature.enabled);
  });

  const explorer = features.mempool_explorer || {};
  const mempoolLink = $("mempool-link");
  if (mempoolLink && explorer.enabled && explorer.url) {
    mempoolLink.href = explorer.url;
    mempoolLink.target = "_blank";
    mempoolLink.rel = "noopener noreferrer";
    mempoolLink.title = "Open mempool explorer";
  } else if (mempoolLink) {
    mempoolLink.removeAttribute("href");
    mempoolLink.removeAttribute("target");
    mempoolLink.removeAttribute("rel");
    mempoolLink.removeAttribute("title");
  }
}

function setWarningBox(data) {
  const box = $("warning-box");
  const items = [...(data.warnings || []), ...(data.errors || []).map((e) => `${e.source}: ${e.message}`)];
  if (!items.length) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = items.map((item) => `<div>${escapeHtml(item)}</div>`).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderAddresses(addresses, onionHostname) {
  const el = $("addresses");
  // Prefer the onion address (the important one for Tor)
  let onion = null;
  for (const item of addresses || []) {
    if (item.address && item.address.endsWith(".onion")) {
      onion = `${item.address}:${item.port || 8333}`;
      break;
    }
  }
  if (!onion && onionHostname) {
    onion = onionHostname.includes(":") ? onionHostname : `${onionHostname}:8333`;
  }
  if (onion) {
    el.innerHTML = `<code>${escapeHtml(onion)}</code>`;
    el.style.fontSize = "13px";
  } else {
    el.innerHTML = "--";
  }
}

function fmtRelativeTime(secondsAgo) {
  if (!secondsAgo || secondsAgo < 0) return "--";
  const m = Math.floor(secondsAgo / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ago`;
  if (m > 0) return `${m}m ago`;
  return `${secondsAgo}s ago`;
}

function renderRecentBlocks(blocks) {
  const grid = $("latest-blocks-grid");
  const summary = $("recent-blocks-summary");
  if (!grid) return;
  if (!blocks || !blocks.length) {
    grid.innerHTML = '<div class="block-card empty">No recent blocks</div>';
    if (summary) summary.textContent = "--";
    return;
  }
  const now = Math.floor(Date.now() / 1000);
  const shownBlocks = blocks.slice(0, 6);
  const html = shownBlocks.map((b) => {
    const ageSec = now - (b.time || now);
    const age = fmtRelativeTime(ageSec);
    const sizeMB = b.size ? (b.size / 1024 / 1024).toFixed(2) + " MB" : "--";
    const height = fmtNumber(b.height);
    return `
      <div class="block-card">
        <div class="block-height">${height}</div>
        <div class="block-meta">
          <span class="block-size">${sizeMB}</span>
          <span class="block-age">${age}</span>
        </div>
      </div>
    `;
  }).join("");
  grid.innerHTML = html;
  if (summary) summary.textContent = `${shownBlocks.length} blocks`;
}

function renderPeers(peers) {
  const body = $("peers-body");
  const sorted = [...(peers || [])].sort((a, b) => Number(b.inbound) - Number(a.inbound));
  if (!sorted.length) {
    body.innerHTML = '<tr><td colspan="6">No peers reported.</td></tr>';
    return;
  }
  body.innerHTML = sorted
    .map((peer) => {
      const direction = peer.inbound ? "IN" : "OUT";
      const synced = `${peer.synced_blocks ?? "--"} / ${peer.synced_headers ?? "--"}`;
      const ping = peer.pingtime_ms === null || peer.pingtime_ms === undefined ? "--" : `${peer.pingtime_ms} ms`;
      return `<tr>
        <td><span class="pill ${peer.inbound ? "good" : "neutral"}">${direction}</span></td>
        <td>${escapeHtml(peer.network || "--")}</td>
        <td><code>${escapeHtml(peer.addr || "--")}</code></td>
        <td>${escapeHtml(peer.connection_type || "--")}</td>
        <td>${escapeHtml(ping)}</td>
        <td>${escapeHtml(synced)}</td>
      </tr>`;
    })
    .join("");
}

function render(data) {
  const sync = data.sync || {};
  const connections = data.connections || {};
  const reachable = (data.network && data.network.reachable) || {};
  const services = data.services || {};
  const progress = sync.progress_percent ?? 0;
  const progressClamped = Math.max(0, Math.min(100, progress));

  applyFeatures(data);
  const instanceName = (data.node && data.node.name) || "bitcoin-knots";
  $("node-name").textContent = instanceName;
  document.title = `${instanceName} · Bitcoin Knots Status`;

  $("sync-label").textContent = sync.initial_block_download ? "Initial block download" : "Synced";
  $("sync-percent").textContent = `${progress.toFixed ? progress.toFixed(2) : progress}%`;
  $("height-label").textContent = `${fmtNumber(sync.blocks)} / ${fmtNumber(sync.headers)} headers`;
  $("sync-bar").style.width = `${progressClamped}%`;

  $("connections-in").textContent = fmtNumber(connections.in);
  $("connections-out").textContent = fmtNumber(connections.out);
  $("ipv4-status").textContent = statusWord(reachable.ipv4);
  $("onion-status").textContent = statusWord(reachable.onion);
  $("mempool-size").textContent = fmtNumber(data.mempool && data.mempool.size);

  // Fee estimates (from estimatesmartfee)
  const fees = (data.mempool && data.mempool.fee_estimates) || {};
  const fmtFee = (est) => (est && est.feerate != null) ? Math.round(est.feerate * 100000) + " sat/vB" : "--";
  $("fee-next").textContent = fmtFee(fees.next_block);
  $("fee-30m").textContent = fmtFee(fees["30min"]);
  $("fee-1h").textContent = fmtFee(fees["1h"]);

  $("disk-size").textContent = fmtBytes(sync.size_on_disk_bytes);
  if (sync.pruned === true) {
    $("storage-label").textContent = "Pruned data";
    $("pruning-status").textContent = sync.prune_target_size_bytes != null
      ? `Pruned · ${fmtBytes(sync.prune_target_size_bytes)} target`
      : "Pruned";
    $("pruning-status").title = sync.prune_height != null
      ? `Blocks below height ${fmtNumber(sync.prune_height)} may be unavailable`
      : "Older block data may be unavailable";
  } else if (sync.pruned === false) {
    $("storage-label").textContent = "Blockchain data";
    $("pruning-status").textContent = "Full history";
    $("pruning-status").removeAttribute("title");
  } else {
    $("storage-label").textContent = "Blockchain data";
    $("pruning-status").textContent = "Mode unavailable";
    $("pruning-status").removeAttribute("title");
  }

  $("knots-service").textContent = serviceLabel(services.knots);
  if (services.tor) $("tor-service").textContent = serviceLabel(services.tor);
  if (services.onion_hostname) {
    $("tor-onion-address").textContent = services.onion_hostname;
  } else {
    $("tor-onion-address").textContent = "--";
  }
  if (services.electrs) $("electrs-service").textContent = serviceLabel(services.electrs);
  $("node-uptime").textContent = fmtSeconds(services.knots_uptime_seconds);
  $("best-block-time").textContent = sync.best_block_time_text || fmtTime(sync.best_block_time);

  // System metrics (CPU temp + Load) - single clean block
  const cpuEl = $("cpu-temp");
  if (cpuEl && data.system && data.system.cpu_temp_c != null) {
    cpuEl.textContent = `${data.system.cpu_temp_c.toFixed(1)}°C`;
  } else if (cpuEl) {
    cpuEl.textContent = "--";
  }

  const loadEl = $("load-avg");
  if (loadEl && data.system && data.system.load_1m != null) {
    loadEl.textContent = `${data.system.load_1m.toFixed(2)} / ${data.system.load_5m.toFixed(2)} / ${data.system.load_15m.toFixed(2)}`;
  } else if (loadEl) {
    loadEl.textContent = "--";
  }

  $("peer-summary").textContent = `${fmtNumber(connections.total)} total, ${fmtNumber(connections.onion_peers)} onion`;

  renderRecentBlocks(data.recent_blocks || []);
  $("last-updated").textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()} in ${data.duration_ms} ms`;

  // renderAddresses removed (onion now shown in Tor row)
  renderPeers(data.peers || []);
  setWarningBox(data);
}

async function refresh() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    setWarningBox({ errors: [{ source: "dashboard", message: error.message }] });
    $("last-updated").textContent = "Refresh failed";
  } finally {
    clearTimeout(timer);
    timer = setTimeout(refresh, refreshMs);
  }
}

$("refresh-now").addEventListener("click", refresh);

// Initialize theme toggle
initTheme();

refresh();
