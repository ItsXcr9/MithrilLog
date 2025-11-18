// MithrilLog Dashboard JavaScript

const focusedPanel = document.getElementById("focused-panel");
const hourlyList = document.getElementById("hourly-list");
const dailyContainer = document.getElementById("daily-container");
const errorFeed = document.getElementById("error-feed");
const hourlyHistory = document.getElementById("hourly-history");
const hourlyRefresh = document.getElementById("hourly-refresh");
const hourlyPrev = document.getElementById("hourly-prev");
const hourlyNext = document.getElementById("hourly-next");
const hourlyPageIndicator = document.getElementById("hourly-page-indicator");
const dailyLimit = document.getElementById("daily-limit");
const dailyRefresh = document.getElementById("daily-refresh");
const errorLimit = document.getElementById("error-limit");
const errorRefresh = document.getElementById("error-refresh");
const globalRefresh = document.getElementById("global-refresh");
const template = document.getElementById("summary-card-template");

const HOURLY_PAGE_SIZE = 6;
let hourlyData = [];
let hourlyPage = 0;
let focusedItem = null;
let focusedKind = "hourly";

// Utility Functions
const formatDateRange = (start, end) => {
  try {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const options = { 
      month: 'short', 
      day: 'numeric', 
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'Asia/Tehran'
    };
    return `${startDate.toLocaleString('en-US', options)} → ${endDate.toLocaleString('en-US', options)}`;
  } catch (e) {
    return `${start} → ${end}`;
  }
};

const renderStats = (stats) => {
  if (!stats || stats.total_events === undefined) return "<p>No statistics available</p>";
  
  // Calculate error count
  const errorSeverities = ['err', 'error', 'crit', 'critical', 'alert', 'emerg', 'emergency'];
  const errorCount = Object.entries(stats.by_severity || {})
    .filter(([sev]) => errorSeverities.includes(sev.toLowerCase()))
    .reduce((sum, [, count]) => sum + count, 0);
  
  const hosts = Object.entries(stats.top_hosts || {})
    .slice(0, 3)
    .map(([name, count]) => `<strong>${name}:</strong> ${count}`)
    .join(" • ");
  const containers = Object.entries(stats.top_apps || {})
    .slice(0, 3)
    .map(([name, count]) => `<strong>${name}:</strong> ${count}`)
    .join(" • ");
  
  return `
    <p><strong>Total Events:</strong> ${stats.total_events.toLocaleString()}</p>
    <p><strong>Unique Events:</strong> ${stats.unique_events?.toLocaleString() ?? "—"}</p>
    <p><strong>Error Count:</strong> ${errorCount.toLocaleString()}</p>
    <p><strong>Top Hosts:</strong> ${hosts || "—"}</p>
    <p><strong>Container Tags:</strong> ${containers || "—"}</p>
  `;
};

const renderHighlightSources = (highlight) => {
  const sources = highlight.source_hosts || highlight.sources;
  if (!sources || !Object.keys(sources).length) return "";
  
  const chips = Object.entries(sources)
    .slice(0, 3)
    .map(([host, count]) => `<span class="chip">${host} ×${count}</span>`)
    .join("");
  return `<div class="highlight-sources">${chips}</div>`;
};

const renderHighlights = (highlights = []) => {
  if (!highlights.length) return "<p>No highlight samples captured.</p>";
  
  return `
    <h4>Event Highlights</h4>
    <ul>
      ${highlights
        .slice(0, 10)
        .map(h => `
          <li>
            <strong>[${h.severity}] ${h.host}/${h.app}</strong>
            (${h.occurrences ?? 1}×) — ${h.message}
            ${renderHighlightSources(h)}
          </li>
        `)
        .join("")}
    </ul>
  `;
};

const buildCard = (item, kind, options = {}) => {
  const card = template.content.firstElementChild.cloneNode(true);
  const titleEl = card.querySelector(".card-title");
  const metaEl = card.querySelector(".card-meta");
  const summaryEl = card.querySelector(".card-summary");
  const statsEl = card.querySelector(".stats-grid");
  const highlightsEl = card.querySelector(".highlights-list");
  const anomaliesEl = card.querySelector(".anomalies-text");

  if (kind === "hourly") {
    titleEl.textContent = formatDateRange(item.window_start, item.window_end);
  } else {
    titleEl.textContent = formatDateRange(item.day_start, item.day_end);
  }
  
  metaEl.textContent = `${item?.stats?.total_events?.toLocaleString() ?? 0} events`;
  summaryEl.textContent = item.summary || "No summary available.";
  statsEl.innerHTML = renderStats(item.stats);
  highlightsEl.innerHTML = renderHighlights(item.highlights);
  anomaliesEl.textContent = (item.anomalies || "").trim() || "No anomalies reported.";

  if (options.selectable) {
    card.classList.add("selectable-card");
    card.style.cursor = "pointer";
    card.addEventListener("click", (e) => {
      // Don't trigger if clicking on details toggle
      if (e.target.closest("details")) {
        return;
      }
      options.onSelect();
    });
  }

  return card;
};

const renderFocus = () => {
  if (!focusedItem) {
    focusedPanel.innerHTML = `
      <div class="empty">
        <p>Select a time window to view detailed analysis</p>
      </div>
    `;
    return;
  }

  const item = focusedItem;
  const stats = item.stats || {};
  const title = focusedKind === "hourly"
    ? formatDateRange(item.window_start, item.window_end)
    : formatDateRange(item.day_start, item.day_end);
  
  // Calculate total error count (err, crit, alert, emerg)
  const errorSeverities = ['err', 'error', 'crit', 'critical', 'alert', 'emerg', 'emergency'];
  const errorCount = Object.entries(stats.by_severity || {})
    .filter(([sev]) => errorSeverities.includes(sev.toLowerCase()))
    .reduce((sum, [, count]) => sum + count, 0);
  
  const topHost = Object.entries(stats.top_hosts || {})[0];
  const topApp = Object.entries(stats.top_apps || {})[0];
  
  // Format container tag (if app looks like a container name)
  const formatContainerTag = (appName) => {
    if (!appName || appName === '-') return '—';
    // If it looks like a container name (contains / or : or docker patterns)
    if (appName.includes('/') || appName.includes(':') || appName.includes('docker') || appName.includes('container')) {
      return appName;
    }
    return appName;
  };
  
  const highlightHtml = (item.highlights || [])
    .slice(0, 4)
    .map(h => `
      <div class="focus-highlight">
        <span class="pill severity-${h.severity || 'info'}">${h.severity || 'info'}</span>
        <p>${h.message || "No message provided."}</p>
        <small>${h.host || "unknown"} / ${h.app || "-"} • ${h.occurrences ?? 1}×</small>
      </div>
    `)
    .join("");
  
  const highlightAnalysis = (item.highlight_analysis || "").trim() 
    || "AI-powered analysis will appear here after processing. Ensure the analyzer job has completed for this time window.";

  focusedPanel.innerHTML = `
    <div class="focus-header">
      <span class="eyebrow">${focusedKind === 'hourly' ? 'HOURLY' : 'DAILY'} SUMMARY</span>
      <h2>${title}</h2>
    </div>
    <div class="focus-metrics">
      <div>
        <span>Total Events</span>
        <strong>${stats.total_events?.toLocaleString() ?? 0}</strong>
      </div>
      <div>
        <span>Unique Events</span>
        <strong>${stats.unique_events?.toLocaleString() ?? "—"}</strong>
      </div>
      <div>
        <span>Error Count</span>
        <strong>${errorCount.toLocaleString()}</strong>
      </div>
      <div>
        <span>Top Host</span>
        <strong>${topHost ? `${topHost[0]}: ${topHost[1]}` : "—"}</strong>
      </div>
      <div>
        <span>Container Tags</span>
        <strong>${topApp ? `${formatContainerTag(topApp[0])}: ${topApp[1]}` : "—"}</strong>
      </div>
    </div>
    <p class="focus-summary">${item.summary || "No summary available."}</p>
    <div class="ai-highlights">
      <h3>AI-Powered Analysis</h3>
      <p>${highlightAnalysis}</p>
    </div>
    <div class="focus-highlight-wrap">
      ${highlightHtml || '<p class="empty">No highlights captured for this period.</p>'}
    </div>
  `;
};

const renderHourlyList = () => {
  const history = hourlyData.slice(1);
  hourlyList.innerHTML = "";
  
  if (!history.length) {
    hourlyList.innerHTML = '<div class="empty"><p>No additional hourly summaries available</p></div>';
    hourlyPageIndicator.textContent = "—";
    hourlyPrev.disabled = true;
    hourlyNext.disabled = true;
    return;
  }
  
  const totalPages = Math.max(1, Math.ceil(history.length / HOURLY_PAGE_SIZE));
  hourlyPage = Math.min(hourlyPage, totalPages - 1);
  const start = hourlyPage * HOURLY_PAGE_SIZE;
  const pageItems = history.slice(start, start + HOURLY_PAGE_SIZE);
  
  for (const item of pageItems) {
    hourlyList.appendChild(
      buildCard(item, "hourly", {
        selectable: true,
        onSelect: () => setFocus(item, "hourly"),
      })
    );
  }
  
  hourlyPageIndicator.textContent = `${hourlyPage + 1} / ${totalPages}`;
  hourlyPrev.disabled = hourlyPage === 0;
  hourlyNext.disabled = hourlyPage >= totalPages - 1;
};

const loadHourlyData = async () => {
  const limit = parseInt(hourlyHistory.value, 10);
  const response = await fetch(`/summaries/hourly?limit=${limit}`);
  
  if (!response.ok) {
    throw new Error("Failed to load hourly summaries");
  }
  
  const data = await response.json();
  hourlyData = data.items || [];
  hourlyPage = 0;
  
  if (hourlyData.length) {
    setFocus(hourlyData[0], "hourly");
  } else {
    setFocus(null, "hourly");
  }
  
  renderHourlyList();
};

const loadDailyData = async () => {
  const limit = parseInt(dailyLimit.value, 10);
  const response = await fetch(`/summaries/daily?limit=${limit}`);
  
  if (!response.ok) {
    throw new Error("Failed to load daily summaries");
  }
  
  const data = await response.json();
  dailyContainer.innerHTML = "";
  
  if (!data.items || !data.items.length) {
    dailyContainer.innerHTML = '<div class="empty"><p>No daily summaries available</p></div>';
    return;
  }
  
  for (const item of data.items) {
    dailyContainer.appendChild(
      buildCard(item, "daily", {
        selectable: true,
        onSelect: () => setFocus(item, "daily"),
      })
    );
  }
};

const buildErrorCard = (item) => {
  const card = document.createElement("article");
  card.className = "card error-card";
  card.style.cursor = "pointer";
  card.addEventListener("click", () => {
    // Find the corresponding hourly summary and focus on it
    const matchingHourly = hourlyData.find(h => 
      h.window_start === item.window_start && h.window_end === item.window_end
    );
    if (matchingHourly) {
      setFocus(matchingHourly, "hourly");
      // Scroll to top
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
  
  const windowLabel = formatDateRange(item.window_start, item.window_end);
  const severityPills = (item.severity_breakdown || [])
    .map(entry => `<span class="pill severity-${entry.severity}">${entry.severity}: ${entry.count}</span>`)
    .join("");
  
  const topHosts = (item.top_hosts || [])
    .map(host => `<span class="chip">${host.host} ×${host.count}</span>`)
    .join("");
  
  const topApps = (item.top_apps || [])
    .map(app => `<span class="chip">${app.app} ×${app.count}</span>`)
    .join("");
  
  const highlights = (item.highlights || [])
    .map(h => `
      <li>
        <strong>[${h.severity}] ${h.host}/${h.app}</strong>
        (${h.occurrences ?? 1}×) — ${h.message}
      </li>
    `)
    .join("");
  
  const topHighlight = (item.highlights || [])[0];
  const incidentSummary = topHighlight
    ? `${topHighlight.message} — ${topHighlight.host}/${topHighlight.app}`
    : "Multiple error patterns detected. Review severity distribution for details.";
  
  const actionHint = topHighlight
    ? `Investigate ${topHighlight.host} (${topHighlight.app}) for recurring ${topHighlight.severity} level events.`
    : "Examine affected hosts and applications for root cause analysis.";
  
  card.innerHTML = `
    <div class="card-header">
      <h3 class="card-title">${windowLabel}</h3>
      <span class="card-meta">${item.total_errors.toLocaleString()} critical events</span>
    </div>
    <p class="incident-summary">${incidentSummary}</p>
    <div class="error-meta">
      <div>
        <h4>Severity Mix</h4>
        <div class="pill-row">
          ${severityPills || '<span class="pill">No data</span>'}
        </div>
      </div>
      <div>
        <h4>Top Hosts</h4>
        <div class="pill-row">
          ${topHosts || '<span class="chip">None</span>'}
        </div>
      </div>
      ${topApps ? `<div>
        <h4>Top Apps</h4>
        <div class="pill-row">${topApps}</div>
      </div>` : ''}
    </div>
    <div class="error-highlights">
      <h4>Sample Events</h4>
      <ul>${highlights || '<li>No error highlights captured.</li>'}</ul>
    </div>
    <p class="action-hint">${actionHint}</p>
  `;
  
  return card;
};

const setFocus = (item, kind) => {
  focusedItem = item;
  focusedKind = kind;
  renderFocus();
};

const loadErrorInsights = async () => {
  const limit = parseInt(errorLimit.value, 10);
  const response = await fetch(`/insights/errors?limit=${limit}`);
  
  if (!response.ok) {
    throw new Error("Failed to load error insights");
  }
  
  const data = await response.json();
  errorFeed.innerHTML = "";
  const items = data.items || [];
  
  if (!items.length) {
    errorFeed.innerHTML = '<div class="empty"><p>No critical errors detected in recent time windows</p></div>';
    return;
  }
  
  for (const item of items) {
    errorFeed.appendChild(buildErrorCard(item));
  }
};

const bootstrap = async () => {
  try {
    await Promise.all([
      loadHourlyData(),
      loadDailyData(),
      loadErrorInsights()
    ]);
  } catch (err) {
    console.error("Bootstrap error:", err);
    const errorBox = document.createElement("div");
    errorBox.className = "error";
    errorBox.style.margin = "2rem";
    errorBox.style.padding = "1rem";
    errorBox.style.background = "var(--error-bg)";
    errorBox.style.border = "1px solid var(--error-border)";
    errorBox.style.borderRadius = "var(--radius-md)";
    errorBox.style.color = "var(--error-text)";
    errorBox.textContent = "Failed to load dashboard data. Please check API connectivity and try again.";
    const main = document.querySelector("main");
    if (main) {
      main.prepend(errorBox);
    } else {
      document.body.prepend(errorBox);
    }
  }
};

// Event Listeners
hourlyRefresh.addEventListener("click", () => loadHourlyData().catch(console.error));
hourlyHistory.addEventListener("change", () => loadHourlyData().catch(console.error));

hourlyPrev.addEventListener("click", () => {
  if (hourlyPage > 0) {
    hourlyPage -= 1;
    renderHourlyList();
  }
});

hourlyNext.addEventListener("click", () => {
  const history = hourlyData.slice(1);
  const totalPages = Math.max(1, Math.ceil(history.length / HOURLY_PAGE_SIZE));
  if (hourlyPage < totalPages - 1) {
    hourlyPage += 1;
    renderHourlyList();
  }
});

dailyRefresh.addEventListener("click", () => loadDailyData().catch(console.error));
dailyLimit.addEventListener("change", () => loadDailyData().catch(console.error));

errorRefresh.addEventListener("click", () => loadErrorInsights().catch(console.error));
errorLimit.addEventListener("change", () => loadErrorInsights().catch(console.error));

globalRefresh.addEventListener("click", () => bootstrap().catch(console.error));

// Initialize Dashboard
bootstrap();