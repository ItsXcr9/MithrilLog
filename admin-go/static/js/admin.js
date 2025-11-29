// Admin Dashboard JavaScript

// API Base URL
const API_BASE = '/api/admin';

// Current filter state
let currentProjectFilter = 'all';

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadDashboard();
    
    // Refresh data every 30 seconds
    setInterval(() => {
        const activePage = document.querySelector('.page.active').id;
        if (activePage === 'dashboard-page') {
            loadDashboard();
        } else if (activePage === 'projects-page') {
            loadProjects(currentProjectFilter);
        }
    }, 30000);
});

// Navigation
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            switchPage(page);
            
            // Update active state
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
        });
    });
    
    // Project filters
    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const status = btn.dataset.status;
            currentProjectFilter = status;
            
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Only pass status if it's not 'all'
            const filterStatus = (status === 'all' || !status) ? null : status;
            loadProjects(filterStatus);
        });
    });
    
    // Modal close
    const modalClose = document.querySelector('.modal-close');
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            document.getElementById('project-modal').classList.remove('active');
        });
    }
}

function switchPage(page) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    
    // Show selected page
    const targetPage = document.getElementById(`${page}-page`);
    if (targetPage) {
        targetPage.classList.add('active');
    }
    
    // Update nav tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.page === page) {
            tab.classList.add('active');
        }
    });
    
    // Load page data
    if (page === 'dashboard') {
        loadDashboard();
    } else if (page === 'projects') {
        loadProjects();
    } else if (page === 'analytics') {
        loadAnalytics();
    } else if (page === 'billing') {
        loadPlans();
    } else if (page === 'settings') {
        loadGlobalSettings();
    }
}

// Load Dashboard Data
async function loadDashboard() {
    try {
        const [statsResponse, projectsResponse] = await Promise.all([
            fetch(`${API_BASE}/stats/overview`),
            fetch(`${API_BASE}/projects`)
        ]);
        
        if (!statsResponse.ok || !projectsResponse.ok) {
            throw new Error('Failed to load dashboard data');
        }
        
        const stats = await statsResponse.json();
        const projects = await projectsResponse.json();
        
        if (!Array.isArray(projects)) {
            console.error('Projects response is not an array:', projects);
            projects = [];
        }
        
        // Calculate total storage
        const totalStorage = projects.reduce((sum, p) => sum + (p.storage_mb || 0), 0);
        
        // Update stats
        document.getElementById('stat-total-projects').textContent = stats.total_projects || 0;
        document.getElementById('stat-active-projects').textContent = stats.active_projects || 0;
        document.getElementById('stat-events-today').textContent = formatNumber(stats.total_events_today || 0);
        document.getElementById('stat-total-storage').textContent = `${(totalStorage / 1024).toFixed(2)} GB`;
        
        // Render projects table
        renderProjectsTable(projects);
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

// Load Projects
async function loadProjects(status = null) {
    try {
        // Only add status parameter if it's a valid status (not null, not 'all')
        let url = `${API_BASE}/projects`;
        if (status && status !== 'all' && ['active', 'suspended', 'cancelled'].includes(status)) {
            url += `?status=${status}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error loading projects:', response.status, errorText);
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const projects = await response.json();
        
        if (!Array.isArray(projects)) {
            console.error('Projects response is not an array:', projects);
            const container = document.getElementById('projects-list');
            container.innerHTML = '<p>Error: Invalid response format</p>';
            return;
        }
        
        const container = document.getElementById('projects-list');
        container.innerHTML = projects.map(project => `
            <div class="project-card" onclick="showProjectDetail('${project.id}')">
                <div class="project-header">
                    <div>
                        <div class="project-name">${project.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace; margin-top: 0.25rem;">${project.id}</div>
                    </div>
                    <span class="quota-badge ${project.quota_status || 'green'}">
                        ${(project.usage_percent || 0).toFixed(1)}%
                    </span>
                </div>
                <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.75rem;">
                    <strong style="color: var(--text-primary);">${formatNumber(project.current_day_events || 0)}</strong> / ${formatNumber(project.daily_limit || 0)} events today
                </div>
                <div class="usage-bar">
                    <div class="usage-fill ${project.quota_status || 'green'}" style="width: ${Math.min(project.usage_percent || 0, 100)}%"></div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-subtle);">
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">
                        <span style="color: var(--text-primary); font-weight: 500;">${project.plan_name || 'N/A'}</span>
                    </div>
                    <span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.75rem; font-weight: 600; text-transform: capitalize; background: ${project.status === 'active' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${project.status === 'active' ? '#86efac' : '#fbbf24'}; border: 1px solid ${project.status === 'active' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'};">
                        ${project.status}
                    </span>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading projects:', error);
        const container = document.getElementById('projects-list');
        if (container) {
            container.innerHTML = '<p>Error loading projects. Please try again.</p>';
        }
    }
}

// Show Project Detail
async function showProjectDetail(projectId) {
    try {
        const [projectResponse, hourlyUsageResponse] = await Promise.all([
            fetch(`${API_BASE}/projects/${projectId}`),
            fetch(`${API_BASE}/projects/${projectId}/usage/hourly?hours=24`)
        ]);
        
        if (!projectResponse.ok) {
            const errorText = await projectResponse.text();
            console.error('Error loading project:', projectResponse.status, errorText);
            alert(`Failed to load project: ${errorText}`);
            return;
        }
        
        const project = await projectResponse.json();
        const hourlyUsage = hourlyUsageResponse.ok ? await hourlyUsageResponse.json() : [];
        
        const detailContainer = document.getElementById('project-detail');
        detailContainer.innerHTML = `
            <h2>${project.name}</h2>
            <div class="nav-tabs" style="margin-bottom: 1.5rem; width: 100%;">
                <button class="nav-tab active" onclick="switchModalTab('overview')">Overview</button>
                <button class="nav-tab" onclick="switchModalTab('settings')">Settings</button>
            </div>

            <div id="modal-tab-overview" class="modal-tab-content active">
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin-bottom: 2rem;">
                    <div style="background: var(--bg-primary); padding: 1.5rem; border-radius: 0.75rem;">
                        <div style="color: var(--text-secondary); font-size: 0.875rem;">Current Hour</div>
                        <div style="font-size: 2rem; font-weight: 700;">${formatNumber(project.current_hour_events || 0)}</div>
                    </div>
                    <div style="background: var(--bg-primary); padding: 1.5rem; border-radius: 0.75rem;">
                        <div style="color: var(--text-secondary); font-size: 0.875rem;">Today</div>
                        <div style="font-size: 2rem; font-weight: 700;">${formatNumber(project.current_day_events || 0)}</div>
                    </div>
                </div>
                
                <div style="margin: 2rem 0;">
                    <h3 style="margin-bottom: 1rem;">Quota Status</h3>
                    <div class="usage-bar" style="height: 12px;">
                        <div class="usage-fill ${project.quota_status || 'green'}" style="width: ${Math.min(project.usage_percent || 0, 100)}%"></div>
                    </div>
                    <div style="margin-top: 0.5rem; color: var(--text-secondary);">
                        ${formatNumber(project.current_day_events || 0)} / ${formatNumber(project.daily_limit || 0)} events (${(project.usage_percent || 0).toFixed(1)}%)
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 2rem; margin: 2rem 0;">
                    <div>
                        <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">Plan</div>
                        <div style="font-weight: 600;">${project.plan_name || 'N/A'}</div>
                    </div>
                    <div>
                        <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">Status</div>
                        <div style="font-weight: 600;">${project.status}</div>
                    </div>
                    <div>
                        <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">Upstream</div>
                        <div style="font-weight: 600; font-size: 0.875rem;">${project.upstream_url || 'N/A'}</div>
                    </div>
                    <div>
                        <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">Billing Email</div>
                        <div style="font-weight: 600; font-size: 0.875rem;">${project.billing_email || 'Not set'}</div>
                    </div>
                </div>
                
                <div style="display: flex; gap: 1rem; margin-top: 2rem; padding-top: 2rem; border-top: 1px solid var(--border-subtle); flex-wrap: wrap;">
                    <button onclick="changeProjectPlan('${project.id}')" style="background: var(--accent-primary); color: white; border: none; padding: 0.75rem 1.5rem; border-radius: var(--radius-sm); cursor: pointer; font-weight: 500; transition: var(--transition);">
                        Change Plan
                    </button>
                    <button onclick="updateQuota('${project.id}')" style="background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-subtle); padding: 0.75rem 1.5rem; border-radius: var(--radius-sm); cursor: pointer; font-weight: 500; transition: var(--transition);">
                        Update Quota
                    </button>
                    <button onclick="toggleProjectStatus('${project.id}', '${project.status}')" style="background: ${project.status === 'active' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(34, 197, 94, 0.2)'}; color: ${project.status === 'active' ? '#fbbf24' : '#86efac'}; border: 1px solid ${project.status === 'active' ? 'rgba(245, 158, 11, 0.3)' : 'rgba(34, 197, 94, 0.3)'}; padding: 0.75rem 1.5rem; border-radius: var(--radius-sm); cursor: pointer; font-weight: 500; transition: var(--transition);">
                        ${project.status === 'active' ? 'Suspend' : 'Activate'}
                    </button>
                </div>
            </div>

            <div id="modal-tab-settings" class="modal-tab-content" style="display: none;">
                <form id="project-settings-form" onsubmit="saveProjectSettings(event, '${project.id}')">
                    <!-- AI Settings -->
                    <div class="settings-section glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
                        <div class="settings-header">
                            <h3>AI & Intelligence</h3>
                        </div>
                        <div class="form-group">
                            <label>Backend Provider</label>
                            <select name="llm_backend" onchange="toggleProjectLLMFields(this)">
                                <option value="gemini" ${project.settings?.llm?.backend === 'gemini' ? 'selected' : ''}>Google Gemini</option>
                                <option value="openai" ${project.settings?.llm?.backend === 'openai' ? 'selected' : ''}>OpenAI GPT</option>
                                <option value="local" ${project.settings?.llm?.backend === 'local' ? 'selected' : ''}>Local (Llama.cpp)</option>
                            </select>
                        </div>
                        <div class="form-group project-gemini-group" style="display: ${(!project.settings?.llm?.backend || project.settings?.llm?.backend === 'gemini') ? 'block' : 'none'}">
                            <label>Gemini API Key</label>
                            <input type="password" name="gemini_key" value="${project.settings?.llm?.gemini_key || ''}" placeholder="Inherit from global if empty">
                        </div>
                        <div class="form-group project-openai-group" style="display: ${project.settings?.llm?.backend === 'openai' ? 'block' : 'none'}">
                            <label>OpenAI API Key</label>
                            <input type="password" name="openai_key" value="${project.settings?.llm?.openai_key || ''}" placeholder="Inherit from global if empty">
                        </div>
                        <div class="form-group">
                            <label>Model Name</label>
                            <input type="text" name="llm_model" value="${project.settings?.llm?.model || ''}" placeholder="Default: gemini-2.5-flash-lite">
                        </div>
                        <div class="form-group">
                            <label>Temperature</label>
                            <input type="number" name="llm_temp" min="0" max="1" step="0.1" value="${project.settings?.llm?.temperature || 0.2}">
                        </div>
                    </div>

                    <!-- Summary & Display Settings -->
                    <div class="settings-section glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
                        <div class="settings-header">
                            <h3>Summary & Display</h3>
                        </div>
                        <div class="form-group">
                            <label>Summary Interval</label>
                            <select name="summary_interval">
                                <option value="3600" ${project.settings?.summary_interval === 3600 ? 'selected' : ''}>1 Hour</option>
                                <option value="10800" ${project.settings?.summary_interval === 10800 ? 'selected' : ''}>3 Hours</option>
                                <option value="21600" ${project.settings?.summary_interval === 21600 ? 'selected' : ''}>6 Hours</option>
                                <option value="43200" ${project.settings?.summary_interval === 43200 ? 'selected' : ''}>12 Hours</option>
                                <option value="86400" ${project.settings?.summary_interval === 86400 ? 'selected' : ''}>24 Hours</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Web Dashboard Title</label>
                            <input type="text" name="web_title" value="${project.settings?.web_title || project.name + ' Dashboard'}" placeholder="Custom dashboard title">
                        </div>
                    </div>

                    <!-- Processing Settings -->
                    <div class="settings-section glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
                        <div class="settings-header">
                            <h3>Processing</h3>
                        </div>
                        <div class="form-group">
                            <label>CPU Cores</label>
                            <input type="number" name="cores" min="1" max="32" value="${project.settings?.cores || 4}">
                            <small style="color: var(--text-tertiary); font-size: 0.85rem; margin-top: 0.25rem; display: block;">Number of CPU cores allocated for log processing</small>
                        </div>
                        <div class="form-group">
                            <label>Log Pattern Filter (Regex)</label>
                            <textarea name="log_pattern" rows="3" placeholder="^.*$" style="font-family: monospace;">${project.settings?.log_pattern || '^.*$'}</textarea>
                            <small style="color: var(--text-tertiary); font-size: 0.85rem; margin-top: 0.25rem; display: block;">Regular expression to filter incoming logs (default: match all)</small>
                        </div>
                    </div>

                    <!-- Ingestion Settings -->
                    <div class="settings-section glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
                        <div class="settings-header">
                            <h3>Ingestion</h3>
                        </div>
                        <div class="form-group">
                            <label>Retention (Days)</label>
                            <input type="number" name="retention_days" value="${project.settings?.ingest?.retention_days || 30}">
                        </div>
                    </div>

                    <!-- Notification Settings -->
                    <div class="settings-section glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
                        <div class="settings-header">
                            <h3>Notifications</h3>
                        </div>
                        <div class="form-group">
                            <label>Telegram Bot Token</label>
                            <input type="password" name="telegram_token" value="${project.settings?.alert?.telegram_token || ''}" placeholder="Inherit from global">
                        </div>
                        <div class="form-group">
                            <label>Telegram Chat ID</label>
                            <input type="text" name="telegram_chat" value="${project.settings?.alert?.telegram_chat || ''}" placeholder="Inherit from global">
                        </div>
                    </div>

                    <div style="display: flex; justify-content: flex-end; gap: 1rem;">
                        <button type="submit" class="primary-btn">Save Settings</button>
                    </div>
                </form>
            </div>
        `;
        
        const modal = document.getElementById('project-modal');
        if (modal) {
            modal.classList.add('active');
        }
        
    } catch (error) {
        console.error('Error loading project detail:', error);
        alert('Error loading project details: ' + error.message);
    }
}

// Render Projects Table
function renderProjectsTable(projects) {
    const container = document.getElementById('projects-table-container');
    
    if (!Array.isArray(projects) || projects.length === 0) {
        container.innerHTML = '<div class="empty"><p>No projects found</p></div>';
        return;
    }
    
    container.innerHTML = `
        <div style="overflow-x: auto;">
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Plan</th>
                        <th>Status</th>
                        <th>Today's Usage</th>
                        <th>Quota Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${projects.slice(0, 10).map(project => `
                        <tr style="cursor: pointer;" onclick="showProjectDetail('${project.id}')">
                            <td>
                                <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">${project.name}</div>
                                <div style="font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace;">${project.id}</div>
                            </td>
                            <td>
                                <span style="font-weight: 500; color: var(--text-primary);">${project.plan_name || 'N/A'}</span>
                            </td>
                            <td>
                                <span style="display: inline-flex; align-items: center; padding: 0.35rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.8rem; font-weight: 600; text-transform: capitalize; background: ${project.status === 'active' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${project.status === 'active' ? '#86efac' : '#fbbf24'}; border: 1px solid ${project.status === 'active' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'};">
                                    ${project.status}
                                </span>
                            </td>
                            <td>
                                <div style="font-weight: 600; color: var(--text-primary);">${formatNumber(project.current_day_events || 0)}</div>
                                <div style="font-size: 0.75rem; color: var(--text-tertiary);">of ${formatNumber(project.daily_limit || 0)}</div>
                            </td>
                            <td>
                                <span class="quota-badge ${project.quota_status || 'green'}">
                                    ${(project.usage_percent || 0).toFixed(1)}%
                                </span>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// Utility Functions
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function refreshData() {
    const activePage = document.querySelector('.page.active').id.replace('-page', '');
    switchPage(activePage);
}

// Admin Actions
let currentPlanChangeProjectId = null;
let currentProjectPlanId = null;

async function changeProjectPlan(projectId) {
    currentPlanChangeProjectId = projectId;
    
    try {
        const plansResponse = await fetch(`${API_BASE}/plans`);
        if (!plansResponse.ok) {
            throw new Error('Failed to load plans');
        }
        const plans = await plansResponse.json();
        
        if (!Array.isArray(plans) || plans.length === 0) {
            alert('No plans available');
            return;
        }
        
        // Get current project to show current plan
        const projectResponse = await fetch(`${API_BASE}/projects/${projectId}`);
        const project = projectResponse.ok ? await projectResponse.json() : null;
        currentProjectPlanId = project ? project.plan_id : null;
        
        // Build plan selection UI
        const content = document.getElementById('plan-selection-content');
        content.innerHTML = `
            <div style="margin-bottom: 1.5rem;">
                <label style="display: block; margin-bottom: 0.75rem; color: var(--text-secondary); font-size: 0.875rem; font-weight: 500;">
                    Select a plan:
                </label>
                <div style="display: flex; flex-direction: column; gap: 1rem;">
                    ${plans.map(plan => {
                        const isCurrent = currentProjectPlanId === plan.id;
                        return `
                        <div class="plan-option" 
                             data-plan-id="${plan.id}"
                             onclick="selectPlan('${plan.id}')"
                             style="
                                 padding: 1.25rem;
                                 border: 2px solid ${isCurrent ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)'};
                                 border-radius: var(--radius-sm);
                                 cursor: pointer;
                                 transition: all 0.2s;
                                 background: ${isCurrent ? 'rgba(59, 130, 246, 0.1)' : 'transparent'};
                             "
                             onmouseover="if (!this.dataset.selected) { this.style.borderColor='#3b82f6'; this.style.background='rgba(59, 130, 246, 0.05)'; }"
                             onmouseout="if (!this.dataset.selected) { this.style.borderColor='${isCurrent ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)'}'; this.style.background='${isCurrent ? 'rgba(59, 130, 246, 0.1)' : 'transparent'}'; }">
                            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                                <div>
                                    <div style="font-size: 1.125rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">
                                        ${plan.name}
                                        ${currentProjectPlanId === plan.id ? '<span style="margin-left: 0.5rem; font-size: 0.75rem; color: var(--accent-primary); font-weight: 500;">(Current)</span>' : ''}
                                    </div>
                                    ${plan.description ? `<div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">${plan.description}</div>` : ''}
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-primary);">
                                        $${plan.price_monthly}
                                    </div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">/month</div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-subtle);">
                                <div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Daily Limit</div>
                                    <div style="font-size: 0.875rem; font-weight: 600; color: var(--text-primary);">
                                        ${formatNumber(plan.events_per_day_limit)} events
                                    </div>
                                </div>
                                <div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Retention</div>
                                    <div style="font-size: 0.875rem; font-weight: 600; color: var(--text-primary);">
                                        ${plan.retention_days} days
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    }).join('')}
                </div>
            </div>
            <div style="display: flex; gap: 1rem; justify-content: flex-end; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border-subtle);">
                <button onclick="closePlanModal()" style="
                    padding: 0.75rem 1.5rem;
                    border: 1px solid var(--border-subtle);
                    border-radius: var(--radius-sm);
                    background: transparent;
                    color: var(--text-primary);
                    cursor: pointer;
                    font-weight: 500;
                    transition: var(--transition);
                ">Cancel</button>
                <button id="confirm-plan-btn" onclick="confirmPlanChange()" disabled style="
                    padding: 0.75rem 1.5rem;
                    border: none;
                    border-radius: var(--radius-sm);
                    background: var(--accent-primary);
                    color: white;
                    cursor: not-allowed;
                    font-weight: 500;
                    opacity: 0.5;
                    transition: var(--transition);
                ">Confirm Change</button>
            </div>
        `;
        
        // Show modal
        document.getElementById('plan-selection-modal').classList.add('active');
        
    } catch (error) {
        console.error('Error loading plans:', error);
        alert('Error loading plans: ' + error.message);
    }
}

let selectedPlanId = null;

function selectPlan(planId) {
    selectedPlanId = planId;
    
    // Update UI
    document.querySelectorAll('.plan-option').forEach(option => {
        const isSelected = option.dataset.planId === planId;
        if (isSelected) {
            option.style.borderColor = '#3b82f6';
            option.style.background = 'rgba(59, 130, 246, 0.1)';
            option.dataset.selected = 'true';
        } else {
            // Check if this was the original current plan
            const originalCurrentPlanId = currentProjectPlanId;
            const isCurrent = option.dataset.planId === originalCurrentPlanId;
            option.style.borderColor = isCurrent ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)';
            option.style.background = isCurrent ? 'rgba(59, 130, 246, 0.1)' : 'transparent';
            delete option.dataset.selected;
        }
    });
    
    // Enable confirm button
    const confirmBtn = document.getElementById('confirm-plan-btn');
    if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.style.opacity = '1';
        confirmBtn.style.cursor = 'pointer';
    }
}

async function confirmPlanChange() {
    if (!selectedPlanId || !currentPlanChangeProjectId) {
        return;
    }
    
    const confirmBtn = document.getElementById('confirm-plan-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Updating...';
    }
    
    try {
        const response = await fetch(`${API_BASE}/projects/${currentPlanChangeProjectId}/plan`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan_id: selectedPlanId })
        });
        
        if (response.ok) {
            closePlanModal();
            closeModal(); // Close project detail modal too
            loadDashboard();
            loadProjects(currentProjectFilter);
            
            // Show success message
            const successMsg = document.createElement('div');
            successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--accent-primary); color: white; padding: 1rem 1.5rem; border-radius: var(--radius-sm); z-index: 10000; box-shadow: 0 4px 12px rgba(0,0,0,0.15);';
            successMsg.textContent = '✓ Plan updated successfully!';
            document.body.appendChild(successMsg);
            setTimeout(() => successMsg.remove(), 3000);
        } else {
            const errorText = await response.text();
            alert(`Failed to update plan: ${errorText}`);
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = 'Confirm Change';
            }
        }
    } catch (error) {
        console.error('Error changing plan:', error);
        alert('Error changing plan: ' + error.message);
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm Change';
        }
    }
}

function closePlanModal() {
    const modal = document.getElementById('plan-selection-modal');
    if (modal) {
        modal.classList.remove('active');
    }
    selectedPlanId = null;
    currentPlanChangeProjectId = null;
    currentProjectPlanId = null;
}

async function updateQuota(projectId) {
    const newLimit = prompt('Enter new daily event limit:');
    if (!newLimit) return;
    
    const limitNum = parseInt(newLimit);
    if (isNaN(limitNum) || limitNum <= 0) {
        alert('Please enter a valid positive number');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/projects/${projectId}/quota`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ daily_limit: limitNum })
        });
        
        if (response.ok) {
            alert('Quota updated successfully!');
            closeModal();
            loadDashboard();
            loadProjects(currentProjectFilter);
        } else {
            const errorText = await response.text();
            alert(`Failed to update quota: ${errorText}`);
        }
    } catch (error) {
        console.error('Error updating quota:', error);
        alert('Error updating quota: ' + error.message);
    }
}

async function toggleProjectStatus(projectId, currentStatus) {
    const newStatus = currentStatus === 'active' ? 'suspended' : 'active';
    
    if (!confirm(`Are you sure you want to ${newStatus} this project?`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/projects/${projectId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (response.ok) {
            alert('Status updated successfully!');
            closeModal();
            loadDashboard();
            loadProjects(currentProjectFilter);
        } else {
            const errorText = await response.text();
            alert(`Failed to update status: ${errorText}`);
        }
    } catch (error) {
        console.error('Error updating status:', error);
        alert('Error updating status: ' + error.message);
    }
}

// Load Analytics
async function loadAnalytics() {
    try {
        const container = document.getElementById('analytics-content');
        if (!container) {
            console.error('Analytics container not found');
            return;
        }
        
        // Get all projects with usage data
        const projects = await fetch(`${API_BASE}/projects`).then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        });
        
        if (!Array.isArray(projects) || projects.length === 0) {
            container.innerHTML = '<div class="empty"><p>No projects found</p></div>';
            return;
        }
        
        // Calculate analytics
        const totalEvents = projects.reduce((sum, p) => sum + (p.current_day_events || 0), 0);
        const totalLimit = projects.reduce((sum, p) => sum + (p.daily_limit || 0), 0);
        const totalStorage = projects.reduce((sum, p) => sum + (p.storage_mb || 0), 0);
        const avgUsage = projects.length > 0 ? projects.reduce((sum, p) => sum + (p.usage_percent || 0), 0) / projects.length : 0;
        const activeProjects = projects.filter(p => p.status === 'active').length;
        const suspendedProjects = projects.filter(p => p.status === 'suspended').length;
        
        // Find projects with highest usage
        const topProjects = [...projects]
            .sort((a, b) => (b.current_day_events || 0) - (a.current_day_events || 0))
            .slice(0, 5);
        
        // Render analytics
        container.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="focus-card">
                    <header>
                        <span class="eyebrow">TOTAL EVENTS TODAY</span>
                        <h2 style="font-size: 2rem; margin-top: 0.5rem; color: var(--text-primary);">${formatNumber(totalEvents)}</h2>
                        <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">of ${formatNumber(totalLimit)} total limit</div>
                    </header>
                </div>
                <div class="focus-card">
                    <header>
                        <span class="eyebrow">TOTAL STORAGE</span>
                        <h2 style="font-size: 2rem; margin-top: 0.5rem; color: var(--text-primary);">${(totalStorage / 1024).toFixed(2)} GB</h2>
                        <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">across all projects</div>
                    </header>
                </div>
                <div class="focus-card">
                    <header>
                        <span class="eyebrow">AVERAGE USAGE</span>
                        <h2 style="font-size: 2rem; margin-top: 0.5rem; color: var(--text-primary);">${avgUsage.toFixed(1)}%</h2>
                        <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">across all projects</div>
                    </header>
                </div>
                <div class="focus-card">
                    <header>
                        <span class="eyebrow">ACTIVE PROJECTS</span>
                        <h2 style="font-size: 2rem; margin-top: 0.5rem; color: var(--text-primary);">${activeProjects}</h2>
                        <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">of ${projects.length} total (${suspendedProjects} suspended)</div>
                    </header>
                </div>
            </div>
            
            <div style="margin-bottom: 2rem;">
                <h3 style="font-size: 1.25rem; font-weight: 600; color: var(--text-primary); margin-bottom: 1.5rem; padding-bottom: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.1);">Top Projects by Usage Today</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem;">
                    ${topProjects.map(project => `
                        <div class="project-card" onclick="showProjectDetail('${project.id}')" style="cursor: pointer;">
                            <div class="project-header">
                                <div>
                                    <div class="project-name">${project.name}</div>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace; margin-top: 0.25rem;">${project.id}</div>
                                </div>
                                <span class="quota-badge ${project.quota_status || 'green'}">
                                    ${(project.usage_percent || 0).toFixed(1)}%
                                </span>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1rem 0; padding: 1rem; background: rgba(255,255,255,0.03); border-radius: var(--radius-sm);">
                                <div>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary); margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em;">Events Today</div>
                                    <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary);">${formatNumber(project.current_day_events || 0)}</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">of ${formatNumber(project.daily_limit || 0)}</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary); margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em;">Storage</div>
                                    <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary);">${(project.storage_mb || 0).toFixed(0)} MB</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${((project.storage_mb || 0) / 1024).toFixed(2)} GB</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary); margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em;">Plan</div>
                                    <div style="font-size: 1rem; font-weight: 600; color: var(--text-primary);">${project.plan_name || 'N/A'}</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); text-transform: capitalize;">${project.status}</div>
                                </div>
                            </div>
                            <div class="usage-bar" style="height: 10px; margin-top: 0.5rem;">
                                <div class="usage-fill ${project.quota_status || 'green'}" style="width: ${Math.min(project.usage_percent || 0, 100)}%"></div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div style="margin-top: 2rem;">
                <h3 style="font-size: 1.25rem; font-weight: 600; color: var(--text-primary); margin-bottom: 1.5rem; padding-bottom: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.1);">All Projects Usage Overview</h3>
                <div style="overflow-x: auto;">
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>Project</th>
                                <th>Plan</th>
                                <th>Today's Events</th>
                                <th>Daily Limit</th>
                                <th>Storage</th>
                                <th>Usage %</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${projects.map(project => `
                                <tr style="cursor: pointer;" onclick="showProjectDetail('${project.id}')">
                                    <td>
                                        <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">${project.name}</div>
                                        <div style="font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace;">${project.id}</div>
                                    </td>
                                    <td>${project.plan_name || 'N/A'}</td>
                                    <td>
                                        <div style="font-weight: 600; color: var(--text-primary);">${formatNumber(project.current_day_events || 0)}</div>
                                    </td>
                                    <td>${formatNumber(project.daily_limit || 0)}</td>
                                    <td>
                                        <div style="font-weight: 600; color: var(--text-primary);">${(project.storage_mb || 0).toFixed(0)} MB</div>
                                        <div style="font-size: 0.75rem; color: var(--text-tertiary);">${((project.storage_mb || 0) / 1024).toFixed(2)} GB</div>
                                    </td>
                                    <td>
                                        <span class="quota-badge ${project.quota_status || 'green'}">
                                            ${(project.usage_percent || 0).toFixed(1)}%
                                        </span>
                                    </td>
                                    <td>
                                        <span style="display: inline-flex; align-items: center; padding: 0.35rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.8rem; font-weight: 600; text-transform: capitalize; background: ${project.status === 'active' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${project.status === 'active' ? '#86efac' : '#fbbf24'}; border: 1px solid ${project.status === 'active' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'}">
                                            ${project.status}
                                        </span>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading analytics:', error);
        const container = document.getElementById('analytics-content');
        if (container) {
            container.innerHTML = '<div class="empty"><p>Error loading analytics data: ' + error.message + '</p></div>';
        }
    }
}

// Load Plans
async function loadPlans() {
    try {
        const response = await fetch(`${API_BASE}/plans`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const plans = await response.json();
        
        if (!Array.isArray(plans) || plans.length === 0) {
            document.getElementById('plans-grid').innerHTML = '<div class="empty"><p>No subscription plans available</p></div>';
            return;
        }
        
        const container = document.getElementById('plans-grid');
        container.innerHTML = plans.map((plan, index) => `
            <div class="plan-card" style="position: relative; ${index === 1 ? 'border: 2px solid var(--accent-primary);' : ''}">
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <h3 style="font-size: 1.75rem; margin-bottom: 0.5rem; color: var(--text-primary); font-weight: 700;">${plan.name}</h3>
                    <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1.5rem; line-height: 1.6;">${plan.description || ''}</p>
                    <div class="plan-price" style="margin: 1.5rem 0;">
                        <span style="font-size: 0.875rem; color: var(--text-secondary); vertical-align: top;">$</span>
                        <span style="font-size: 3rem; font-weight: 700; color: var(--text-primary); line-height: 1;">${plan.price_monthly}</span>
                        <span style="font-size: 1rem; color: var(--text-secondary); font-weight: 400;">/mo</span>
                    </div>
                </div>
                <div style="padding-top: 1.5rem; border-top: 1px solid var(--border-subtle);">
                    <ul style="list-style: none; margin: 0; padding: 0; color: var(--text-secondary); font-size: 0.875rem; display: flex; flex-direction: column; gap: 1rem;">
                        <li style="display: flex; align-items: center; gap: 0.75rem;">
                            <span style="color: var(--accent-primary); font-size: 1.25rem; font-weight: bold;">✓</span>
                            <span><strong style="color: var(--text-primary); font-size: 1rem;">${formatNumber(plan.events_per_day_limit)}</strong> events per day</span>
                        </li>
                        <li style="display: flex; align-items: center; gap: 0.75rem;">
                            <span style="color: var(--accent-primary); font-size: 1.25rem; font-weight: bold;">✓</span>
                            <span><strong style="color: var(--text-primary); font-size: 1rem;">${plan.retention_days}</strong> days data retention</span>
                        </li>
                    </ul>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading plans:', error);
    }
}

// Settings Functions
function toggleGlobalLLMFields() {
    const backend = document.getElementById('global-llm-backend').value;
    document.getElementById('global-gemini-group').style.display = backend === 'gemini' ? 'block' : 'none';
    document.getElementById('global-openai-group').style.display = backend === 'openai' ? 'block' : 'none';
}

async function saveGlobalSettings() {
    const settings = {
        prompts: {
            summary: document.getElementById('summary-prompt').value,
            trend: document.getElementById('trend-prompt').value
        },
        default_llm: {
            backend: document.getElementById('global-llm-backend').value,
            gemini_key: document.getElementById('global-gemini-key').value,
            openai_key: document.getElementById('global-openai-key').value,
            model: document.getElementById('global-llm-model').value,
            temperature: parseFloat(document.getElementById('global-llm-temp').value)
        }
    };
    
    try {
        const response = await fetch(`${API_BASE}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            alert('Global settings saved successfully!');
        } else {
            const errorText = await response.text();
            alert(`Failed to save settings: ${errorText}`);
        }
    } catch (error) {
        console.error('Error saving global settings:', error);
        alert('Error saving settings: ' + error.message);
    }
}

async function loadGlobalSettings() {
    try {
        const response = await fetch(`${API_BASE}/settings`);
        if (response.ok) {
            const settings = await response.json();
            if (settings.prompts) {
                document.getElementById('summary-prompt').value = settings.prompts.summary || '';
                document.getElementById('trend-prompt').value = settings.prompts.trend || '';
            }
            if (settings.default_llm) {
                document.getElementById('global-llm-backend').value = settings.default_llm.backend || 'gemini';
                document.getElementById('global-gemini-key').value = settings.default_llm.gemini_key || '';
                document.getElementById('global-openai-key').value = settings.default_llm.openai_key || '';
                document.getElementById('global-llm-model').value = settings.default_llm.model || '';
                document.getElementById('global-llm-temp').value = settings.default_llm.temperature || 0.2;
                toggleGlobalLLMFields();
            }
        }
    } catch (error) {
        console.error('Error loading global settings:', error);
    }
}

function switchModalTab(tabName) {
    document.querySelectorAll('.modal .nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.modal-tab-content').forEach(content => {
        content.style.display = 'none';
        content.classList.remove('active');
    });
    
    const target = document.getElementById(`modal-tab-${tabName}`);
    if (target) {
        target.style.display = 'block';
        target.classList.add('active');
    }
}

function toggleProjectLLMFields(select) {
    const form = select.closest('form');
    const geminiGroup = form.querySelector('.project-gemini-group');
    const openaiGroup = form.querySelector('.project-openai-group');
    
    if (select.value === 'gemini') {
        geminiGroup.style.display = 'block';
        openaiGroup.style.display = 'none';
    } else if (select.value === 'openai') {
        geminiGroup.style.display = 'none';
        openaiGroup.style.display = 'block';
    } else {
        geminiGroup.style.display = 'none';
        openaiGroup.style.display = 'none';
    }
}

async function saveProjectSettings(event, projectId) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    
    const settings = {
        summary_interval: parseInt(formData.get('summary_interval')),
        web_title: formData.get('web_title'),
        cores: parseInt(formData.get('cores')),
        log_pattern: formData.get('log_pattern'),
        llm: {
            backend: formData.get('llm_backend'),
            gemini_key: formData.get('gemini_key'),
            openai_key: formData.get('openai_key'),
            model: formData.get('llm_model'),
            temperature: parseFloat(formData.get('llm_temp'))
        },
        ingest: {
            retention_days: parseInt(formData.get('retention_days'))
        },
        alert: {
            telegram_token: formData.get('telegram_token'),
            telegram_chat: formData.get('telegram_chat')
        }
    };
    
    try {
        const response = await fetch(`${API_BASE}/projects/${projectId}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings })
        });
        
        if (response.ok) {
            alert('Project settings saved successfully!');
        } else {
            const errorText = await response.text();
            alert(`Failed to save settings: ${errorText}`);
        }
    } catch (error) {
        console.error('Error saving project settings:', error);
        alert('Error saving settings: ' + error.message);
    }
}

