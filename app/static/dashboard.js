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
const chartRefresh = document.getElementById("chart-refresh");
const template = document.getElementById("summary-card-template");

const HOURLY_PAGE_SIZE = 6;
let hourlyData = [];
let hourlyPage = 0;
let focusedItem = null;
let focusedKind = "hourly";

// Utility Functions
const escapeHtml = (str = "") =>
  str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const formatInlineMarkdown = (text = "") => {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");
  return html;
};

const renderMarkdown = (text = "", fallback = "No content available.") => {
  const content = (text || "").trim();
  if (!content) {
    return `<p>${fallback}</p>`;
  }

  const lines = content.split(/\r?\n/);
  let html = "";
  let inList = false;

  const closeList = () => {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    if (/^---+$/.test(line)) {
      closeList();
      html += "<hr />";
      continue;
    }

    if (line.startsWith("### ")) {
      closeList();
      html += `<h4>${formatInlineMarkdown(line.slice(4))}</h4>`;
      continue;
    }

    if (line.startsWith("## ")) {
      closeList();
      html += `<h3>${formatInlineMarkdown(line.slice(3))}</h3>`;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      const bullet = line.replace(/^[-*]\s+/, "");
      html += `<li>${formatInlineMarkdown(bullet)}</li>`;
      continue;
    }

    closeList();
    html += `<p>${formatInlineMarkdown(line)}</p>`;
  }

  closeList();
  return html;
};

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
  const topAppsList = Object.entries(stats.top_apps || {})
    .slice(0, 3)
    .map(([name, count]) => `<strong>${name}:</strong> ${count}`)
    .join(" • ");
  
  return `
    <p><strong>Total Events:</strong> ${stats.total_events.toLocaleString()}</p>
    <p><strong>Unique Events:</strong> ${stats.unique_events?.toLocaleString() ?? "—"}</p>
    <p><strong>Error Count:</strong> ${errorCount.toLocaleString()}</p>
    <p><strong>Top Hosts:</strong> ${hosts || "—"}</p>
    <p><strong>Top Apps:</strong> ${topAppsList || "—"}</p>
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
  summaryEl.innerHTML = renderMarkdown(item.summary, "No summary available.");
  statsEl.innerHTML = renderStats(item.stats);
  highlightsEl.innerHTML = renderHighlights(item.highlights);
  anomaliesEl.innerHTML = renderMarkdown(item.anomalies || "", "No anomalies reported.");

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
  
  const highlightAnalysis = renderMarkdown(
    item.highlight_analysis || "",
    "AI-powered analysis will appear here after processing. Ensure the analyzer job has completed for this time window.",
  );
  const summaryHtml = renderMarkdown(item.summary || "", "No summary available.");

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
        <span>Top App</span>
        <strong>${topApp ? `${formatContainerTag(topApp[0])}: ${topApp[1]}` : "—"}</strong>
      </div>
    </div>
    <!-- <div class="focus-summary">${summaryHtml}</div> -->
    <div class="ai-highlights">
      <h3>AI-Powered Analysis</h3>
      <div>${highlightAnalysis}</div>
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

const showError = () => {
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
if (chartRefresh) {
  chartRefresh.addEventListener("click", () => loadLogCountChart().catch(console.error));
}

// Chart Functions - D3 Area Chart
const loadLogCountChart = async () => {
  try {
    // Check if D3 is loaded - wait a bit if not
    let d3Lib = typeof d3 !== 'undefined' ? d3 : (typeof window.d3 !== 'undefined' ? window.d3 : null);
    
    if (!d3Lib) {
      // Wait up to 2 seconds for D3 to load
      for (let i = 0; i < 20; i++) {
        await new Promise(resolve => setTimeout(resolve, 100));
        d3Lib = typeof d3 !== 'undefined' ? d3 : (typeof window.d3 !== 'undefined' ? window.d3 : null);
        if (d3Lib) {
          break;
        }
      }
      
      // Final check
      if (!d3Lib) {
        console.error("D3.js is not loaded after waiting");
        const container = document.querySelector(".chart-container");
        if (container) {
          container.innerHTML = '<p class="empty">Error: D3.js library failed to load. Please refresh the page.</p>';
        }
        return;
      }
    }
    
    // Check if SVG element exists (with retry)
    let svgElement = document.getElementById("log-count-chart");
    if (!svgElement) {
      // Wait a bit and try again
      await new Promise(resolve => setTimeout(resolve, 500));
      svgElement = document.getElementById("log-count-chart");
      if (!svgElement) {
        console.error("Chart SVG element not found after retry");
        return;
      }
    }
    
    const response = await fetch("/metrics/log-counts?days=30", {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      credentials: 'same-origin'
    });
    if (!response.ok) {
      throw new Error(`Failed to load log counts: ${response.status}`);
    }
    const data = await response.json();
    const items = data.items || [];
    
    console.log(`Loaded ${items.length} data points for chart`);
    
    const svg = d3Lib.select("#log-count-chart");
    svg.selectAll("*").remove();
    
    if (items.length === 0) {
      const container = document.querySelector(".chart-container");
      if (container) {
        container.innerHTML = '<p class="empty">No log data available for the past 30 days.</p>';
      }
      return;
    }
    
    // Prepare data
    const chartData = items.map(item => ({
      date: new Date(item.timestamp),
      value: item.count
    }));
    
    // Set dimensions and margins
    const container = document.querySelector(".chart-container");
    const width = container ? container.clientWidth - 60 : 800;
    const height = 400;
    const marginTop = 20;
    const marginRight = 20;
    const marginBottom = 40;
    const marginLeft = 60;
    
    // Set up SVG
    svg.attr("width", width)
       .attr("height", height)
       .attr("viewBox", [0, 0, width, height])
       .attr("style", "max-width: 100%; height: auto;");
    
    // Create scales
    const xScale = d3Lib.scaleTime()
      .domain(d3Lib.extent(chartData, d => d.date))
      .range([marginLeft, width - marginRight]);
    
    const yScale = d3Lib.scaleLinear()
      .domain([0, d3Lib.max(chartData, d => d.value)])
      .nice()
      .range([height - marginBottom, marginTop]);
    
    // Create area generator
    const area = d3Lib.area()
      .x(d => xScale(d.date))
      .y0(yScale(0))
      .y1(d => yScale(d.value))
      .curve(d3Lib.curveMonotoneX);
    
    // Create line generator
    const line = d3Lib.line()
      .x(d => xScale(d.date))
      .y(d => yScale(d.value))
      .curve(d3Lib.curveMonotoneX);
    
    // Get CSS variables for colors
    const getCSSVar = (varName) => {
      return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    };
    const accentPrimary = getCSSVar('--accent-primary') || '#3b82f6';
    const accentSecondary = getCSSVar('--accent-secondary') || '#6366f1';
    const textSecondary = getCSSVar('--text-secondary') || '#9ca3af';
    const borderSubtle = getCSSVar('--border-subtle') || '#343842';
    
    // Add area with gradient
    const gradient = svg.append("defs")
      .append("linearGradient")
      .attr("id", "area-gradient")
      .attr("gradientUnits", "userSpaceOnUse")
      .attr("x1", 0)
      .attr("y1", height - marginBottom)
      .attr("x2", 0)
      .attr("y2", marginTop);
    
    gradient.append("stop")
      .attr("offset", "0%")
      .attr("stop-color", accentPrimary)
      .attr("stop-opacity", 0.3);
    
    gradient.append("stop")
      .attr("offset", "100%")
      .attr("stop-color", accentPrimary)
      .attr("stop-opacity", 0.05);
    
    svg.append("path")
      .datum(chartData)
      .attr("fill", "url(#area-gradient)")
      .attr("d", area);
    
    // Add line
    svg.append("path")
      .datum(chartData)
      .attr("fill", "none")
      .attr("stroke", accentPrimary)
      .attr("stroke-width", 2.5)
      .attr("stroke-linecap", "round")
      .attr("stroke-linejoin", "round")
      .attr("d", line);
    
    // Add x-axis
    const xAxis = d3Lib.axisBottom(xScale)
      .ticks(width / 80)
      .tickSizeOuter(0)
      .tickFormat(d3Lib.timeFormat("%b %d"));
    
    // Add x-axis
    const xAxisG = svg.append("g")
      .attr("transform", `translate(0,${height - marginBottom})`)
      .call(xAxis);
    
    xAxisG.selectAll("text")
      .style("fill", textSecondary)
      .style("font-size", "11px")
      .style("font-family", "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif");
    
    xAxisG.selectAll("line, path")
      .style("stroke", borderSubtle)
      .style("stroke-width", 1);
    
    // Add y-axis
    const yAxis = d3Lib.axisLeft(yScale)
      .ticks(height / 40)
      .tickFormat(d => {
        if (d >= 1000) return (d / 1000).toFixed(1) + "k";
        return d;
      });
    
    const yAxisG = svg.append("g")
      .attr("transform", `translate(${marginLeft},0)`)
      .call(yAxis);
    
    yAxisG.selectAll("text")
      .style("fill", textSecondary)
      .style("font-size", "11px")
      .style("font-family", "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif");
    
    yAxisG.selectAll("line, path")
      .style("stroke", borderSubtle)
      .style("stroke-width", 1);
    
    // Add grid lines
    svg.append("g")
      .attr("transform", `translate(${marginLeft},0)`)
      .call(d3Lib.axisLeft(yScale)
        .ticks(height / 40)
        .tickSize(-width + marginLeft + marginRight)
        .tickFormat(""))
      .selectAll("line")
      .style("stroke", borderSubtle)
      .style("stroke-opacity", 0.2)
      .style("stroke-dasharray", "2,4")
      .style("stroke-width", 1);
    
    // Add tooltip matching UI style
    const tooltipBg = getCSSVar('--bg-tertiary') || '#2d3139';
    const tooltipText = getCSSVar('--text-primary') || '#e4e7eb';
    const tooltipBorder = getCSSVar('--border-subtle') || '#343842';
    
    const tooltip = d3Lib.select("body").append("div")
      .attr("class", "chart-tooltip")
      .style("opacity", 0)
      .style("position", "absolute")
      .style("background", tooltipBg)
      .style("color", tooltipText)
      .style("padding", "10px 14px")
      .style("border-radius", "8px")
      .style("border", `1px solid ${tooltipBorder}`)
      .style("font-size", "12px")
      .style("font-family", "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("pointer-events", "none")
      .style("z-index", "1000")
      .style("box-shadow", "0 4px 6px rgba(0, 0, 0, 0.4)");
    
    // Add invisible overlay for mouse tracking
    const overlay = svg.append("rect")
      .attr("fill", "none")
      .attr("pointer-events", "all")
      .attr("width", width)
      .attr("height", height);
    
    // Add vertical line for hover
    const verticalLine = svg.append("line")
      .attr("stroke", accentPrimary)
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", 0.4)
      .attr("stroke-dasharray", "4,4")
      .style("opacity", 0);
    
    // Add hover circle
    const hoverCircle = svg.append("circle")
      .attr("r", 5)
      .attr("fill", accentPrimary)
      .attr("stroke", getCSSVar('--bg-secondary') || '#24272e')
      .attr("stroke-width", 3)
      .style("opacity", 0);
    
    // Mouse move handler
    overlay.on("mousemove", function(event) {
      const [mouseX] = d3Lib.pointer(event, this);
      const x0 = xScale.invert(mouseX);
      const bisect = d3Lib.bisector(d => d.date).left;
      const i = bisect(chartData, x0, 1);
      const d0 = chartData[i - 1];
      const d1 = chartData[i];
      const d = d1 && (x0 - d0.date > d1.date - x0) ? d1 : d0;
      
      if (d) {
        verticalLine
          .attr("x1", xScale(d.date))
          .attr("x2", xScale(d.date))
          .attr("y1", marginTop)
          .attr("y2", height - marginBottom)
          .style("opacity", 1);
        
        hoverCircle
          .attr("cx", xScale(d.date))
          .attr("cy", yScale(d.value))
          .style("opacity", 1);
        
        const dateStr = d.date.toLocaleString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'Asia/Tehran'
        });
        
        tooltip
          .html(`<div style="font-weight: 600; margin-bottom: 4px; color: ${accentPrimary};">${dateStr}</div><div style="color: ${textSecondary};">Logs: <strong style="color: ${tooltipText};">${d.value.toLocaleString()}</strong></div>`)
          .style("opacity", 1)
          .style("left", (event.pageX + 10) + "px")
          .style("top", (event.pageY - 10) + "px");
      }
    });
    
    overlay.on("mouseleave", function() {
      verticalLine.style("opacity", 0);
      hoverCircle.style("opacity", 0);
      tooltip.style("opacity", 0);
    });
    
    console.log("Chart rendered successfully");
    
  } catch (error) {
    console.error("Failed to load log count chart:", error);
    const container = document.querySelector(".chart-container");
    if (container) {
      container.innerHTML = `<p class="empty">Error loading chart: ${error.message}</p>`;
    }
  }
};

// Initialize Dashboard
const bootstrap = async () => {
  try {
    await Promise.all([
      loadHourlyData(),
      loadDailyData(),
      loadErrorInsights(),
      loadLogCountChart()
    ]);
  } catch (error) {
    console.error("Bootstrap failed:", error);
    showError();
  }
};

// Wait for DOM and D3 to be ready
const initDashboard = () => {
  // Check if D3 is available
  if (typeof d3 === 'undefined' && typeof window.d3 === 'undefined') {
    // Wait a bit and try again
    setTimeout(initDashboard, 100);
    return;
  }
  bootstrap();
};

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboard);
} else {
  initDashboard();
}