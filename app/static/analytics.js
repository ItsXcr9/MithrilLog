// MithrilLog Enterprise Analytics JavaScript
// Custom chart rendering and KPI updates

// Color palette for charts
const CHART_COLORS = {
  severity: {
    emerg: '#dc2626',
    alert: '#ea580c',
    crit: '#f97316',
    err: '#ef4444',
    warn: '#fbbf24',
    notice: '#22c55e',
    info: '#3b82f6',
    debug: '#6b7280'
  },
  palette: [
    '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd',
    '#22c55e', '#f59e0b', '#ef4444', '#ec4899',
    '#14b8a6', '#06b6d4'
  ]
};

// Simple Canvas Chart Library
class SimpleChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.width = this.canvas.width;
    this.height = this.canvas.height;
  }

  clear() {
    if (!this.ctx) return;
    this.ctx.clearRect(0, 0, this.width, this.height);
  }

  drawPieChart(data, options = {}) {
    if (!this.ctx || !data.length) return;
    
    const centerX = this.width / 2;
    const centerY = this.height / 2;
    const radius = Math.min(centerX, centerY) - 20;
    
    const total = data.reduce((sum, d) => sum + d.value, 0);
    if (total === 0) return;
    
    let startAngle = -Math.PI / 2;
    
    data.forEach((item, i) => {
      const sliceAngle = (item.value / total) * 2 * Math.PI;
      
      this.ctx.beginPath();
      this.ctx.moveTo(centerX, centerY);
      this.ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
      this.ctx.closePath();
      
      this.ctx.fillStyle = item.color || CHART_COLORS.palette[i % CHART_COLORS.palette.length];
      this.ctx.fill();
      
      // Draw label if slice is big enough
      if (sliceAngle > 0.3) {
        const labelAngle = startAngle + sliceAngle / 2;
        const labelX = centerX + (radius * 0.65) * Math.cos(labelAngle);
        const labelY = centerY + (radius * 0.65) * Math.sin(labelAngle);
        
        this.ctx.fillStyle = '#fff';
        this.ctx.font = 'bold 11px system-ui, sans-serif';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(item.label, labelX, labelY);
      }
      
      startAngle += sliceAngle;
    });
  }

  drawBarChart(data, options = {}) {
    if (!this.ctx || !data.length) return;
    
    const padding = { top: 20, right: 20, bottom: 30, left: 10 };
    const chartWidth = this.width - padding.left - padding.right;
    const chartHeight = this.height - padding.top - padding.bottom;
    
    const maxValue = Math.max(...data.map(d => d.value));
    if (maxValue === 0) return;
    
    const barWidth = (chartWidth / data.length) - 8;
    const barSpacing = 8;
    
    data.forEach((item, i) => {
      const barHeight = (item.value / maxValue) * chartHeight;
      const x = padding.left + i * (barWidth + barSpacing) + barSpacing / 2;
      const y = padding.top + chartHeight - barHeight;
      
      // Draw bar with gradient
      const gradient = this.ctx.createLinearGradient(x, y + barHeight, x, y);
      gradient.addColorStop(0, item.color || CHART_COLORS.palette[i % CHART_COLORS.palette.length]);
      gradient.addColorStop(1, this.lightenColor(item.color || CHART_COLORS.palette[i % CHART_COLORS.palette.length], 30));
      
      this.ctx.fillStyle = gradient;
      this.ctx.beginPath();
      this.ctx.roundRect(x, y, barWidth, barHeight, [4, 4, 0, 0]);
      this.ctx.fill();
      
      // Draw value
      this.ctx.fillStyle = 'rgba(255,255,255,0.9)';
      this.ctx.font = 'bold 10px system-ui, sans-serif';
      this.ctx.textAlign = 'center';
      this.ctx.fillText(this.formatNumber(item.value), x + barWidth / 2, y - 5);
      
      // Draw label
      this.ctx.fillStyle = 'rgba(255,255,255,0.6)';
      this.ctx.font = '9px system-ui, sans-serif';
      this.ctx.fillText(item.label.substring(0, 8), x + barWidth / 2, this.height - 8);
    });
  }

  drawLineChart(data, options = {}) {
    if (!this.ctx || !data.length) return;
    
    const padding = { top: 20, right: 20, bottom: 30, left: 40 };
    const chartWidth = this.width - padding.left - padding.right;
    const chartHeight = this.height - padding.top - padding.bottom;
    
    const maxValue = Math.max(...data.map(d => d.value));
    const minValue = Math.min(...data.map(d => d.value));
    const range = maxValue - minValue || 1;
    
    // Draw grid
    this.ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    this.ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartHeight / 4) * i;
      this.ctx.beginPath();
      this.ctx.moveTo(padding.left, y);
      this.ctx.lineTo(this.width - padding.right, y);
      this.ctx.stroke();
    }
    
    // Draw area fill
    const gradient = this.ctx.createLinearGradient(0, padding.top, 0, this.height - padding.bottom);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.4)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0.0)');
    
    this.ctx.beginPath();
    this.ctx.moveTo(padding.left, this.height - padding.bottom);
    
    data.forEach((item, i) => {
      const x = padding.left + (chartWidth / (data.length - 1)) * i;
      const y = padding.top + chartHeight - ((item.value - minValue) / range) * chartHeight;
      this.ctx.lineTo(x, y);
    });
    
    this.ctx.lineTo(this.width - padding.right, this.height - padding.bottom);
    this.ctx.closePath();
    this.ctx.fillStyle = gradient;
    this.ctx.fill();
    
    // Draw line
    this.ctx.beginPath();
    this.ctx.strokeStyle = '#6366f1';
    this.ctx.lineWidth = 2.5;
    
    data.forEach((item, i) => {
      const x = padding.left + (chartWidth / (data.length - 1)) * i;
      const y = padding.top + chartHeight - ((item.value - minValue) / range) * chartHeight;
      
      if (i === 0) {
        this.ctx.moveTo(x, y);
      } else {
        this.ctx.lineTo(x, y);
      }
    });
    
    this.ctx.stroke();
    
    // Draw points
    data.forEach((item, i) => {
      const x = padding.left + (chartWidth / (data.length - 1)) * i;
      const y = padding.top + chartHeight - ((item.value - minValue) / range) * chartHeight;
      
      this.ctx.beginPath();
      this.ctx.arc(x, y, 3, 0, 2 * Math.PI);
      this.ctx.fillStyle = '#6366f1';
      this.ctx.fill();
      this.ctx.strokeStyle = '#fff';
      this.ctx.lineWidth = 1;
      this.ctx.stroke();
    });
  }

  lightenColor(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (
      0x1000000 +
      (R < 255 ? (R < 1 ? 0 : R) : 255) * 0x10000 +
      (G < 255 ? (G < 1 ? 0 : G) : 255) * 0x100 +
      (B < 255 ? (B < 1 ? 0 : B) : 255)
    ).toString(16).slice(1);
  }

  formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  }
}

// Analytics Data Manager
class AnalyticsManager {
  constructor() {
    this.severityChart = new SimpleChart('severity-chart');
    this.hostsChart = new SimpleChart('hosts-chart');
    this.errorTrendChart = new SimpleChart('error-trend-chart');
  }

  async loadAnalytics() {
    try {
      // Load from hourly summaries for KPIs and charts
      // Use relative path to work with gateway proxy
      const response = await fetch('summaries/hourly?limit=24');
      if (!response.ok) throw new Error('Failed to load analytics data');
      
      const data = await response.json();
      const items = data.items || [];
      
      this.updateKPIs(items);
      this.renderSeverityChart(items);
      this.renderHostsChart(items);
      this.renderErrorTrendChart(items);
      this.renderProcessActivities(items);
      this.renderServiceHealth(items);
      
    } catch (error) {
      console.error('Analytics load error:', error);
    }
  }

  updateKPIs(items) {
    if (!items.length) return;
    
    // Calculate 24h totals
    let totalEvents = 0;
    let totalErrors = 0;
    const hostsSet = new Set();
    const errorSeverities = ['emerg', 'alert', 'crit', 'err', 'error'];
    
    items.slice(0, 24).forEach(item => {
      const stats = item.stats || {};
      totalEvents += stats.total_events || 0;
      
      // Count errors
      Object.entries(stats.by_severity || {}).forEach(([sev, count]) => {
        if (errorSeverities.includes(sev.toLowerCase())) {
          totalErrors += count;
        }
      });
      
      // Count unique hosts
      Object.keys(stats.top_hosts || {}).forEach(host => hostsSet.add(host));
    });
    
    const errorRate = totalEvents > 0 ? ((totalErrors / totalEvents) * 100).toFixed(2) : 0;
    
    // Detect anomalies (simplified: count hours with error rate > 10%)
    let anomalyCount = 0;
    items.slice(0, 24).forEach(item => {
      const stats = item.stats || {};
      const hourEvents = stats.total_events || 0;
      let hourErrors = 0;
      Object.entries(stats.by_severity || {}).forEach(([sev, count]) => {
        if (errorSeverities.includes(sev.toLowerCase())) {
          hourErrors += count;
        }
      });
      if (hourEvents > 0 && (hourErrors / hourEvents) > 0.1) {
        anomalyCount++;
      }
    });
    
    // Update DOM
    const kpiEvents = document.getElementById('kpi-events');
    const kpiErrorRate = document.getElementById('kpi-error-rate');
    const kpiHosts = document.getElementById('kpi-hosts');
    const kpiAnomalies = document.getElementById('kpi-anomalies');
    
    if (kpiEvents) kpiEvents.textContent = this.formatNumber(totalEvents);
    if (kpiErrorRate) kpiErrorRate.textContent = errorRate + '%';
    if (kpiHosts) kpiHosts.textContent = hostsSet.size;
    if (kpiAnomalies) kpiAnomalies.textContent = anomalyCount;
    
    // Update trends
    const eventsTrend = document.getElementById('kpi-events-trend');
    const errorTrend = document.getElementById('kpi-error-trend');
    
    if (eventsTrend && items.length > 1) {
      const prev = items.slice(24, 48).reduce((sum, i) => sum + (i.stats?.total_events || 0), 0);
      if (prev > 0) {
        const change = ((totalEvents - prev) / prev * 100).toFixed(1);
        eventsTrend.textContent = change >= 0 ? `+${change}%` : `${change}%`;
        eventsTrend.className = 'kpi-trend' + (change >= 0 ? '' : ' success');
      }
    }
  }

  renderSeverityChart(items) {
    if (!this.severityChart.ctx) return;
    
    const severityCounts = {};
    items.slice(0, 24).forEach(item => {
      Object.entries(item.stats?.by_severity || {}).forEach(([sev, count]) => {
        severityCounts[sev] = (severityCounts[sev] || 0) + count;
      });
    });
    
    const data = Object.entries(severityCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label, value]) => ({
        label,
        value,
        color: CHART_COLORS.severity[label.toLowerCase()] || CHART_COLORS.palette[0]
      }));
    
    this.severityChart.clear();
    this.severityChart.drawPieChart(data);
  }

  renderHostsChart(items) {
    if (!this.hostsChart.ctx) return;
    
    const hostCounts = {};
    items.slice(0, 24).forEach(item => {
      Object.entries(item.stats?.top_hosts || {}).forEach(([host, count]) => {
        hostCounts[host] = (hostCounts[host] || 0) + count;
      });
    });
    
    const data = Object.entries(hostCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label, value], i) => ({
        label,
        value,
        color: CHART_COLORS.palette[i % CHART_COLORS.palette.length]
      }));
    
    this.hostsChart.clear();
    this.hostsChart.drawBarChart(data);
  }

  renderErrorTrendChart(items) {
    if (!this.errorTrendChart.ctx) return;
    
    const errorSeverities = ['emerg', 'alert', 'crit', 'err', 'error'];
    
    const data = items.slice(0, 24).reverse().map((item, i) => {
      let errorCount = 0;
      Object.entries(item.stats?.by_severity || {}).forEach(([sev, count]) => {
        if (errorSeverities.includes(sev.toLowerCase())) {
          errorCount += count;
        }
      });
      return { label: `H${i}`, value: errorCount };
    });
    
    this.errorTrendChart.clear();
    this.errorTrendChart.drawLineChart(data);
  }

  renderProcessActivities(items) {
    const container = document.getElementById('process-activities');
    if (!container) return;
    
    // Aggregate app counts as proxy for activities
    const appCounts = {};
    items.slice(0, 24).forEach(item => {
      Object.entries(item.stats?.top_apps || {}).forEach(([app, count]) => {
        appCounts[app] = (appCounts[app] || 0) + count;
      });
    });
    
    const topApps = Object.entries(appCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
    
    if (topApps.length === 0) {
      container.innerHTML = '<p class="muted">No activity data available</p>';
      return;
    }
    
    container.innerHTML = topApps.map(([name, count]) => `
      <div class="activity-item">
        <span class="activity-name">${this.escapeHtml(name)}</span>
        <span class="activity-count">${this.formatNumber(count)}</span>
      </div>
    `).join('');
  }

  renderServiceHealth(items) {
    const serviceListEl = document.getElementById('service-health-list');
    const anomalyListEl = document.getElementById('anomaly-list');
    if (!serviceListEl || !anomalyListEl) return;

    // Use backend aggregation if available, otherwise client-side fallback
    let services = {};
    let recentAnomalies = [];
    
    // Check if latest item has service_health (new feature)
    const hasBackendData = items.length > 0 && items[0].service_health;
    
    if (hasBackendData) {
      // Merge last 24h of backend data
      items.slice(0, 24).forEach(item => {
        if (!item.service_health) return;
        Object.entries(item.service_health).forEach(([app, data]) => {
          if (!services[app]) {
            services[app] = { anomalies: 0, severities: {}, top_issues: [] };
          }
          services[app].anomalies += data.anomalies || 0;
          // Merge severities
          Object.entries(data.severities || {}).forEach(([sev, count]) => {
            services[app].severities[sev] = (services[app].severities[sev] || 0) + count;
          });
          // Collect issues
          services[app].top_issues.push(...(data.top_issues || []));
        });
      });
    } else {
      // Client-side fallback using highlights
      services = this._aggregateServiceHealthClientSide(items);
    }

    // Process Recent Anomalies List (flatten issues)
    Object.entries(services).forEach(([app, data]) => {
      if (data.top_issues) {
        data.top_issues.forEach(issue => {
           recentAnomalies.push({ ...issue, app });
        });
      }
    });
    
    // Sort anomalies by severity/recency
    const sevPriority = { emerg:0, alert:1, crit:2, error:3, err:3, warning:4, warn:4, info:5 };
    recentAnomalies.sort((a, b) => {
      const pA = sevPriority[a.severity] ?? 9;
      const pB = sevPriority[b.severity] ?? 9;
      return pA - pB;
    });

    // Render Services
    const serviceArray = Object.entries(services)
        .map(([name, data]) => ({ name, ...data }))
        .sort((a, b) => b.anomalies - a.anomalies); // Sort by anomaly count

    if (serviceArray.length === 0) {
      serviceListEl.innerHTML = '<div class="empty-state-small">No service data available</div>';
    } else {
      serviceListEl.innerHTML = serviceArray.map(svc => {
        let statusClass = 'healthy';
        if (svc.anomalies > 10) statusClass = 'critical';
        else if (svc.anomalies > 0) statusClass = 'warning';
        
        return `
        <div class="service-item">
          <div class="service-info">
            <span class="service-name">${this.escapeHtml(svc.name)}</span>
            <span class="service-meta">${svc.anomalies} anomalies</span>
          </div>
          <div class="service-score">
            <span class="score-badge ${statusClass}">${statusClass.toUpperCase()}</span>
          </div>
        </div>
        `;
      }).join('');
    }

    // Render Anomalies
    if (recentAnomalies.length === 0) {
      anomalyListEl.innerHTML = '<div class="empty-state-small">No anomalies detected recently.</div>';
    } else {
      anomalyListEl.innerHTML = recentAnomalies.slice(0, 15).map(issue => {
        const sevClass = issue.severity.toLowerCase();
        return `
        <div class="anomaly-item">
          <div class="anomaly-header">
            <span class="anomaly-sev ${sevClass}">${this.escapeHtml(issue.severity)}</span>
            <span class="muted">${this.escapeHtml(issue.app)}</span>
          </div>
          <div class="anomaly-msg" title="${this.escapeHtml(issue.message)}">
            ${this.escapeHtml(issue.message)}
          </div>
        </div>
        `;
      }).join('');
    }

    // Filter Logic
    const filterInput = document.getElementById('service-filter');
    if (filterInput) {
      filterInput.onkeyup = () => {
        const filter = filterInput.value.toLowerCase();
        const items = serviceListEl.getElementsByClassName('service-item');
        Array.from(items).forEach(item => {
          const name = item.querySelector('.service-name').textContent.toLowerCase();
          item.style.display = name.includes(filter) ? 'grid' : 'none';
        });
      };
    }
  }

  _aggregateServiceHealthClientSide(items) {
    const services = {};
    items.slice(0, 24).forEach(item => {
      // Use highlights if available
      (item.highlights || []).forEach(h => {
         const app = h.app || 'unknown';
         if (!services[app]) services[app] = { anomalies: 0, severities: {}, top_issues: [] };
         services[app].anomalies += h.occurrences || 1;
         services[app].top_issues.push({
           severity: h.severity,
           message: h.message,
           count: h.occurrences
         });
      });
    });
    return services;
  }

  formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toLocaleString();
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

// Initialize analytics on page load
let analyticsManager;

document.addEventListener('DOMContentLoaded', () => {
  // Wait for main dashboard to load first
  setTimeout(() => {
    analyticsManager = new AnalyticsManager();
    analyticsManager.loadAnalytics();
    
    // Bind refresh button
    const refreshBtn = document.getElementById('analytics-refresh');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => analyticsManager.loadAnalytics());
    }
  }, 1000);
});

// Export for use in main dashboard.js
if (typeof window !== 'undefined') {
  window.AnalyticsManager = AnalyticsManager;
}
