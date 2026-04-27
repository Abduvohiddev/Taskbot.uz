/**
 * TaskBot Mini App - Frontend Logic
 */

const tg = window.Telegram?.WebApp;
const API_BASE = '/api';

// ===== i18n state =====
let I18N = {
    lang: 'uz',
    dict: {},      // { "key.path": "translated text" }
    supported: ['uz', 'ru', 'en'],
};

/** Translate by key, fallback to key itself if missing. */
function tr(key, vars) {
    let s = I18N.dict[key];
    if (s == null) return key;
    if (vars) {
        Object.keys(vars).forEach(k => {
            s = s.replace(new RegExp('\\{' + k + '\\}', 'g'), vars[k]);
        });
    }
    return s;
}

/** Apply data-i18n / data-i18n-ph attributes across the DOM. */
function applyI18n(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const txt = tr(key);
        if (txt && txt !== key) el.textContent = txt;
    });
    root.querySelectorAll('[data-i18n-ph]').forEach(el => {
        const key = el.getAttribute('data-i18n-ph');
        const txt = tr(key);
        if (txt && txt !== key) el.setAttribute('placeholder', txt);
    });
    document.documentElement.setAttribute('lang', I18N.lang);
}

/** Load translations from server (uses user's saved language). */
async function loadI18n() {
    try {
        const headers = {};
        if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        const res = await fetch(API_BASE + '/i18n', { headers });
        if (!res.ok) return;
        const data = await res.json();
        I18N.lang = data.lang || 'uz';
        I18N.dict = data.translations || {};
        I18N.supported = data.supported || ['uz', 'ru', 'en'];
        applyI18n();
    } catch (e) {
        console.warn('i18n load failed:', e);
    }
}

/** Change language from mini app side — syncs with bot. */
async function setAppLanguage(lang) {
    try {
        const headers = { 'Content-Type': 'application/json' };
        if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        const res = await fetch(API_BASE + '/i18n/set-lang', {
            method: 'POST',
            headers,
            body: JSON.stringify({ lang }),
        });
        if (!res.ok) throw new Error('http ' + res.status);
        const data = await res.json();
        I18N.lang = data.lang;
        I18N.dict = data.translations || {};
        applyI18n();
        if (typeof showToast === 'function') showToast(tr('common.success'));
    } catch (e) {
        console.warn('set lang failed:', e);
    }
}
let currentFilter = 'active';
let allTasks = [];
let currentTaskId = null;
let currentWorkspaceId = 'personal';
let currentWorkspaceName = 'Shaxsiy';
let companyMembers = [];
let selectedAssigneeIds = [];
let statusChart = null;
let membersChart = null;
let priorityChart = null;
let trendChart = null;
let overdueChart = null;

// ===== AI Chat State =====
let aiHistory = [];   // [{role:'user'|'assistant', content:'...'}]

// ===== Calendar State =====
let calendarDate = new Date();   // currently viewed month
let selectedCalDate = null;      // 'YYYY-MM-DD' string

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();
        
        // Apply Telegram theme
        document.body.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#0a0a1a');
    }

    // Tarjimalarni eng birinchi yuklaymiz — UI darhol o'z tilida ko'rinsin
    loadI18n();

    initTabs();
    initFilters();
    initForm();
    loadApp();

    // Header scrolled effect
    const headerEl = document.querySelector('.header');
    if (headerEl) {
        const onScroll = () => {
            if (window.scrollY > 8) headerEl.classList.add('scrolled');
            else headerEl.classList.remove('scrolled');
        };
        window.addEventListener('scroll', onScroll, { passive: true });
    }
});

// ===== Avatar loader =====
async function loadAvatar(el) {
    if (!el) return;
    try {
        const headers = {};
        if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        const res = await fetch(API_BASE + '/avatar', { headers });
        if (!res.ok) return;
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        el.style.backgroundImage = `url('${url}')`;
        el.style.backgroundSize = 'cover';
        el.style.backgroundPosition = 'center';
        el.textContent = '';
        el.classList.add('avatar-loaded');
    } catch (e) { /* fallback letter qoladi */ }
}

// ===== API Helper =====
async function apiRequest(endpoint, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    
    if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    try {
        const res = await fetch(API_BASE + endpoint, opts);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'API xatolik');
        return data;
    } catch (err) {
        console.error('API Error:', err);
        throw err;
    }
}

// ===== Load App =====
async function loadApp() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        
        const [wsData, tasksData, statsData] = await Promise.all([
            apiRequest('/workspaces'),
            apiRequest(`/tasks?company_id=${currentWorkspaceId}`),
            apiRequest(`/stats?company_id=${currentWorkspaceId}`),
        ]);

        // Populate Workspaces
        const wsSelect = document.getElementById('workspace-select');
        if (wsSelect && wsData.workspaces) {
            wsSelect.innerHTML = '<option value="all">🌍 Hammasi</option>' +
                wsData.workspaces.map(w =>
                    `<option value="${w.id}">${w.id === 'personal' ? '👤 ' : '🏢 '}${w.name}</option>`
                ).join('');
            wsSelect.value = currentWorkspaceId;
            const opt = wsSelect.options[wsSelect.selectedIndex];
            currentWorkspaceName = opt ? opt.text : 'Shaxsiy';
        }
        updateCreateWorkspaceUI();

        allTasks = tasksData.tasks || [];

        // User info
        const userName = tasksData.user_name || (tg?.initDataUnsafe?.user?.first_name) || 'Foydalanuvchi';
        document.getElementById('user-name').textContent = `Salom, ${userName}!`;
        const avatarEl = document.getElementById('user-avatar');
        avatarEl.textContent = userName.charAt(0).toUpperCase();
        avatarEl.style.backgroundImage = '';
        loadAvatar(avatarEl);

        updateQuickStats(statsData);
        updateStatsTab(statsData);
        renderTasks();

        // Hide loading
        const loading = document.getElementById('loading-screen');
        loading.classList.add('fade-out');
        setTimeout(() => {
            loading.classList.add('hidden');
            document.getElementById('app').classList.remove('hidden');
        }, 400);
    } catch (err) {
        console.error('Load error:', err);
        document.querySelector('.loading-text').textContent = '❗ Yuklashda xatolik';
        // Still show app after delay
        setTimeout(() => {
            document.getElementById('loading-screen').classList.add('hidden');
            document.getElementById('app').classList.remove('hidden');
        }, 1500);
    }
}

// ===== Workspace Switcher =====
async function changeWorkspace() {
    const wsSelect = document.getElementById('workspace-select');
    if (!wsSelect) return;

    currentWorkspaceId = wsSelect.value;
    const opt = wsSelect.options[wsSelect.selectedIndex];
    currentWorkspaceName = opt ? opt.text : 'Shaxsiy';

    if (tg) tg.HapticFeedback?.selectionChanged();

    updateCreateWorkspaceUI();

    try {
        // Pass company_id parameter (supports 'all' for all workspaces)
        const queryParam = currentWorkspaceId === 'all' ? 'all' : currentWorkspaceId;

        const [tasksData, statsData] = await Promise.all([
            apiRequest(`/tasks?company_id=${queryParam}`),
            apiRequest(`/stats?company_id=${queryParam}`),
        ]);

        allTasks = tasksData.tasks || [];
        updateQuickStats(statsData);
        updateStatsTab(statsData);
        renderTasks();

        // Reset calendar when switching workspaces
        selectedCalDate = null;
        const calTab = document.getElementById('tab-calendar');
        if (calTab && !calTab.classList.contains('hidden')) {
            renderCalendar();
        }
    } catch(e) {
        showToast("Xatolik yuz berdi", true);
    }
}

async function updateCreateWorkspaceUI() {
    const label = document.getElementById('create-workspace-label');
    if (label) label.textContent = currentWorkspaceName;

    const group = document.getElementById('assignees-group');
    const list = document.getElementById('assignees-list');
    const hint = document.getElementById('assignees-hint');

    selectedAssigneeIds = [];
    companyMembers = [];

    if (currentWorkspaceId === 'personal' || currentWorkspaceId === 'all') {
        group.classList.add('hidden');
        list.innerHTML = '';
        return;
    }

    try {
        const data = await apiRequest(`/companies/${currentWorkspaceId}/members`);
        companyMembers = data.members || [];
        // O'z-o'zini default tanlash
        const self = companyMembers.find(m => m.is_self);
        if (self) selectedAssigneeIds.push(self.id);
        renderAssignees();
        group.classList.remove('hidden');
        if (hint) hint.textContent = `${companyMembers.length} xodim - Tanlangan: ${selectedAssigneeIds.length}`;
    } catch (e) {
        group.classList.add('hidden');
        list.innerHTML = '';
        console.error('Members load error:', e);
    }
}

function renderAssignees() {
    const list = document.getElementById('assignees-list');
    if (!list) return;
    list.innerHTML = companyMembers.map(m => {
        const selected = selectedAssigneeIds.includes(m.id);
        const initial = (m.name || '?').charAt(0).toUpperCase();
        const roleBadge = m.role === 'owner' ? '👑' : (m.role === 'admin' ? '🛡' : '👤');
        return `
            <div class="assignee-chip ${selected ? 'selected' : ''}" data-uid="${m.id}" onclick="toggleAssignee(${m.id})">
                <span class="assignee-avatar">${escapeHtml(initial)}</span>
                <span class="assignee-name">${roleBadge} ${escapeHtml(m.name)}${m.is_self ? ' (siz)' : ''}</span>
                <span class="assignee-check">${selected ? '✓' : ''}</span>
            </div>
        `;
    }).join('');
}

function toggleAssignee(uid) {
    const idx = selectedAssigneeIds.indexOf(uid);
    if (idx >= 0) selectedAssigneeIds.splice(idx, 1);
    else selectedAssigneeIds.push(uid);
    renderAssignees();
    const hint = document.getElementById('assignees-hint');
    if (hint) hint.textContent = `${companyMembers.length} xodim - Tanlangan: ${selectedAssigneeIds.length}`;
    if (tg) tg.HapticFeedback?.selectionChanged();
}

// ===== Quick Stats =====
function updateQuickStats(stats) {
    animateNumber('stat-total', stats.total || 0);
    animateNumber('stat-active', (stats.in_progress || 0) + (stats.new || 0));
    animateNumber('stat-done', stats.done || 0);
    animateNumber('stat-overdue', stats.overdue || 0);
    
    document.getElementById('user-stats').textContent = 
        `${stats.total || 0} vazifa - ${stats.completion_rate || 0}% bajarildi`;
}

function animateNumber(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    let current = 0;
    const step = Math.max(1, Math.ceil(target / 20));
    const interval = setInterval(() => {
        current = Math.min(current + step, target);
        el.textContent = current;
        if (current >= target) clearInterval(interval);
    }, 30);
}

// ===== Stats Tab =====
function updateStatsTab(stats) {
    document.getElementById('stats-total').textContent = stats.total || 0;
    document.getElementById('stats-done-count').textContent = stats.done || 0;
    document.getElementById('stats-progress').textContent = (stats.in_progress || 0);
    document.getElementById('stats-overdue-count').textContent = stats.overdue || 0;

    // Progress circle
    const rate = stats.completion_rate || 0;
    document.getElementById('completion-rate').textContent = rate;
    const circle = document.getElementById('progress-circle');
    if (circle) {
        const circumference = 2 * Math.PI * 52; // r=52
        const offset = circumference - (rate / 100) * circumference;
        setTimeout(() => { circle.style.strokeDashoffset = offset; }, 300);
    }

    renderStatusChart(stats);
    renderPriorityChart(stats);
    renderTrendChart(stats);
    renderOverdueChart(stats);
    renderMembersChart(stats);
}

function renderStatusChart(stats) {
    const section = document.getElementById('status-chart-section');
    const canvas = document.getElementById('status-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    if (!stats.is_company) {
        section.classList.add('hidden');
        if (statusChart) { statusChart.destroy(); statusChart = null; }
        return;
    }

    section.classList.remove('hidden');
    const data = {
        labels: ['Bajarildi', 'Jarayonda', 'Kechikdi', 'Yangi', "Ko'rilmoqda"],
        datasets: [{
            data: [
                stats.done || 0,
                stats.in_progress || 0,
                stats.overdue || 0,
                stats.new || 0,
                stats.review || 0,
            ],
            backgroundColor: ['#4CAF50', '#FF9800', '#F44336', '#2196F3', '#9C27B0'],
            borderColor: 'rgba(0,0,0,0.2)',
            borderWidth: 2,
        }],
    };

    if (statusChart) statusChart.destroy();
    statusChart = new Chart(canvas, {
        type: 'doughnut',
        data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: 'rgba(255,255,255,0.8)', font: { size: 12 }, padding: 10 },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total ? Math.round(ctx.parsed / total * 100) : 0;
                            return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
                        },
                    },
                },
            },
        },
    });
}

function renderMembersChart(stats) {
    const section = document.getElementById('members-chart-section');
    const canvas = document.getElementById('members-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    const hasData = stats.is_admin && Array.isArray(stats.employee_stats) && stats.employee_stats.length > 0;
    if (!hasData) {
        section.classList.add('hidden');
        if (membersChart) { membersChart.destroy(); membersChart = null; }
        return;
    }

    section.classList.remove('hidden');

    // Faqat birinchi ismi
    const labels     = stats.employee_stats.map(e => (e.name || '').split(' ')[0]);
    const done       = stats.employee_stats.map(e => e.done || 0);
    const inProgress = stats.employee_stats.map(e => (e.in_progress || 0) + (e.review || 0));
    const overdue    = stats.employee_stats.map(e => e.overdue || 0);

    // Dinamik balandlik: har 1 kishi uchun 52px, min 220
    const barH = Math.max(220, labels.length * 52 + 80);
    canvas.parentElement.style.height = barH + 'px';

    if (membersChart) membersChart.destroy();

    // Plugin: faqat 0 dan katta qiymatlarni ko'rsat
    const datalabelsPlugin = window.ChartDataLabels;

    membersChart = new Chart(canvas, {
        type: 'bar',
        plugins: datalabelsPlugin ? [datalabelsPlugin] : [],
        data: {
            labels,
            datasets: [
                {
                    label: 'Bajarildi',
                    data: done,
                    backgroundColor: 'rgba(76,175,80,0.85)',
                    borderColor: '#4CAF50',
                    borderWidth: 1,
                    borderRadius: 5,
                    borderSkipped: false,
                },
                {
                    label: 'Jarayonda',
                    data: inProgress,
                    backgroundColor: 'rgba(255,152,0,0.85)',
                    borderColor: '#FF9800',
                    borderWidth: 1,
                    borderRadius: 5,
                    borderSkipped: false,
                },
                {
                    label: 'Kechikdi',
                    data: overdue,
                    backgroundColor: 'rgba(244,67,54,0.85)',
                    borderColor: '#F44336',
                    borderWidth: 1,
                    borderRadius: 5,
                    borderSkipped: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',          // Gorizontal bar — nom o'qiganda qulay
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { color: 'rgba(255,255,255,0.6)', stepSize: 1, precision: 0 },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    title: { display: true, text: 'Vazifalar soni', color: 'rgba(255,255,255,0.5)', font: { size: 11 } },
                },
                y: {
                    ticks: { color: 'rgba(255,255,255,0.9)', font: { weight: '700', size: 12 } },
                    grid: { display: false },
                },
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: 'rgba(255,255,255,0.85)', font: { size: 12 }, boxWidth: 14, padding: 12 },
                },
                tooltip: {
                    callbacks: {
                        afterBody: (items) => {
                            const idx = items[0]?.dataIndex;
                            const emp = stats.employee_stats[idx];
                            if (!emp) return '';
                            const total = (emp.done||0)+(emp.in_progress||0)+(emp.overdue||0)+(emp.review||0)+(emp.new||0);
                            return [`Jami: ${total} ta`];
                        },
                    },
                },
                datalabels: datalabelsPlugin ? {
                    anchor: 'end',
                    align: 'end',
                    formatter: (val) => val > 0 ? val : '',
                    color: (ctx) => {
                        const colors = ['#81C784', '#FFB74D', '#EF9A9A'];
                        return colors[ctx.datasetIndex] || '#fff';
                    },
                    font: { weight: 'bold', size: 12 },
                } : undefined,
            },
        },
    });
}

function renderPriorityChart(stats) {
    const section = document.getElementById('priority-chart-section');
    const canvas = document.getElementById('priority-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    // Get priority counts from allTasks
    const priorityCounts = { urgent: 0, high: 0, medium: 0, low: 0 };
    allTasks.forEach(t => {
        if (priorityCounts[t.priority] !== undefined) priorityCounts[t.priority]++;
    });

    if (priorityCounts.urgent === 0 && priorityCounts.high === 0 &&
        priorityCounts.medium === 0 && priorityCounts.low === 0) {
        section.classList.add('hidden');
        if (priorityChart) { priorityChart.destroy(); priorityChart = null; }
        return;
    }

    section.classList.remove('hidden');
    if (priorityChart) priorityChart.destroy();
    priorityChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: ['Juda muhim', 'Yuqori', "O'rta", 'Past'],
            datasets: [{
                data: [priorityCounts.urgent, priorityCounts.high, priorityCounts.medium, priorityCounts.low],
                backgroundColor: ['#F44336', '#FF9800', '#FFC107', '#4CAF50'],
                borderColor: 'rgba(255,255,255,0.2)',
                borderWidth: 1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.7)', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: 'rgba(255,255,255,0.8)' }, grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
            },
        },
    });
}

function renderTrendChart(stats) {
    const section = document.getElementById('trend-chart-section');
    const canvas = document.getElementById('trend-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    // Build 7-day trend data
    const today = new Date();
    const data = [];
    for (let i = 6; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

        let done = 0;
        allTasks.forEach(t => {
            if (t.status === 'done' && t.completed_at) {
                const cd = new Date(t.completed_at);
                const ck = `${cd.getFullYear()}-${String(cd.getMonth()+1).padStart(2,'0')}-${String(cd.getDate()).padStart(2,'0')}`;
                if (ck === key) done++;
            }
        });

        data.push({
            date: d.toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric' }),
            done: done
        });
    }

    section.classList.remove('hidden');
    if (trendChart) trendChart.destroy();
    trendChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'Bajarilgan',
                data: data.map(d => d.done),
                borderColor: '#4CAF50',
                backgroundColor: 'rgba(76, 175, 80, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#4CAF50',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { color: 'rgba(255,255,255,0.7)' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.7)', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
            },
            plugins: {
                legend: { labels: { color: 'rgba(255,255,255,0.8)', font: { size: 12 } } },
            },
        },
    });
}

function renderOverdueChart(stats) {
    const section = document.getElementById('overdue-chart-section');
    const canvas = document.getElementById('overdue-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    // Build 7-day overdue trend
    const today = new Date();
    const data = [];
    for (let i = 6; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);

        let overdue = 0;
        allTasks.forEach(t => {
            if (t.deadline) {
                const dl = new Date(t.deadline);
                if (dl <= d && t.status !== 'done' && t.status !== 'cancelled') overdue++;
            }
        });

        data.push({
            date: d.toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric' }),
            overdue: overdue
        });
    }

    section.classList.remove('hidden');
    if (overdueChart) overdueChart.destroy();
    overdueChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'Kechikkan vazifalar',
                data: data.map(d => d.overdue),
                borderColor: '#F44336',
                backgroundColor: 'rgba(244, 67, 54, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#F44336',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { color: 'rgba(255,255,255,0.7)' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.7)', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
            },
            plugins: {
                legend: { labels: { color: 'rgba(255,255,255,0.8)', font: { size: 12 } } },
            },
        },
    });
}

// ===== Tabs =====
function initTabs() {
    document.querySelectorAll('.bnav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.bnav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const tabId = 'tab-' + btn.dataset.tab;
            document.getElementById(tabId).classList.add('active');

            if (btn.dataset.tab === 'workflow') {
                loadWorkflows();
            }

            if (tg) tg.HapticFeedback?.impactOccurred('light');
        });
    });
}

// ===== Workflow tab =====
let _wfData = [];
let _wfFilter = 'all';

async function loadWorkflows() {
    const list = document.getElementById('workflow-list');
    if (!list) return;
    list.innerHTML = '<div class="wf-empty">⏳ Yuklanmoqda...</div>';
    try {
        const data = await apiRequest('/workflows');
        _wfData = data.workflows || [];
        renderWorkflows();
    } catch (e) {
        list.innerHTML = '<div class="wf-empty">❌ Xatolik: ' + (e.message || e) + '</div>';
    }
}

function renderWorkflows() {
    const list = document.getElementById('workflow-list');
    if (!list) return;
    let items = _wfData;
    if (_wfFilter === 'me')     items = items.filter(w => w.current_is_me);
    if (_wfFilter === 'active') items = items.filter(w => w.status !== 'done');
    if (_wfFilter === 'done')   items = items.filter(w => w.status === 'done');

    if (!items.length) {
        list.innerHTML = '<div class="wf-empty">📭 Workflow vazifa yo\'q</div>';
        return;
    }

    list.innerHTML = items.map(w => {
        const stepsHtml = w.steps.map(s => {
            const icon = s.status === 'done' ? '✅'
                       : s.status === 'active' ? '🟢'
                       : s.status === 'blocked' ? '⏸'
                       : '⚪';
            const cls = 'wf-step wf-step-' + s.status + (s.is_me ? ' wf-step-me' : '');
            const meta = s.completed_at
                ? `<span class="wf-step-time">⏱ ${s.completed_at}</span>`
                : (s.status === 'active' ? '<span class="wf-step-time wf-active-pulse">▶ Hozir</span>' : '');

            // Comments ro'yxati
            let commentsHtml = '';
            if (s.comments && s.comments.length) {
                commentsHtml = '<div class="wf-comments">' + s.comments.map(c =>
                    `<div class="wf-comment">
                        <b>${escapeHtml(c.user)}</b> <span class="wf-comment-time">${c.created_at}</span><br>
                        ${escapeHtml(c.content)}
                    </div>`
                ).join('') + '</div>';
            } else if (s.note) {
                commentsHtml = `<div class="wf-step-note">💬 ${escapeHtml(s.note)}</div>`;
            }

            // Attachments ro'yxati
            let attsHtml = '';
            if (s.attachments && s.attachments.length) {
                const typeEm = {photo:'🖼', video:'🎥', document:'📄', audio:'🎵', voice:'🎙'};
                attsHtml = '<div class="wf-atts">' + s.attachments.map(a =>
                    `<div class="wf-att">${typeEm[a.file_type]||'📎'} ${escapeHtml(a.file_name || a.file_type)}</div>`
                ).join('') + '</div>';
            }

            return `
                <div class="${cls}">
                    <div class="wf-step-icon">${icon}</div>
                    <div class="wf-step-body">
                        <div class="wf-step-title">${s.order}. ${escapeHtml(s.title)}</div>
                        <div class="wf-step-assignee">👤 ${escapeHtml(s.assignee_name)}${s.is_me ? ' <b>(siz)</b>' : ''}</div>
                        ${commentsHtml}
                        ${attsHtml}
                    </div>
                    <div class="wf-step-meta">${meta}</div>
                </div>
            `;
        }).join('');

        const stuckBadge = (w.stuck_minutes != null && w.current_is_me === false && w.status !== 'done')
            ? `<div class="wf-stuck">⏳ ${w.current_assignee_name} da: ${formatMinutes(w.stuck_minutes)}</div>`
            : '';

        const curStep = w.steps.find(s => s.is_me);
        const meBadge = w.current_is_me && curStep
            ? `<div class="wf-action-row">
                 <button class="wf-status-btn ${curStep.status === 'pending' ? 'wf-btn-start' : 'wf-btn-done'}"
                         onclick="handleStepAction(${w.task_id}, '${curStep.status}')">
                     ${curStep.status === 'pending' ? '▶️ Boshlash' : curStep.status === 'active' ? '✅ Bajarildi' : '✓ Tugagan'}
                 </button>
               </div>`
            : '';

        const status_em = w.status === 'done' ? '🎉' : '🔄';
        const status_text = w.status === 'done' ? 'Tugagan' : 'Davom etmoqda';

        return `
            <div class="wf-card">
                <div class="wf-card-head">
                    <div>
                        <div class="wf-card-title">${status_em} #${w.task_id} ${escapeHtml(w.title)}</div>
                        <div class="wf-card-meta">${status_text} • ${w.created_at}</div>
                    </div>
                    <div class="wf-progress-wrap">
                        <div class="wf-progress-text">${w.done_steps}/${w.total_steps} qadam</div>
                        <div class="wf-progress-bar"><div class="wf-progress-fill" style="width:${w.progress_percent}%"></div></div>
                    </div>
                </div>
                ${stuckBadge}
                <div class="wf-steps">${stepsHtml}</div>
                ${meBadge}
            </div>
        `;
    }).join('');
}

// Modal — qadam tugatish formasi (izoh + status)
function openStepCompleteModal(taskId) {
    // Mavjud bo'lsa yopamiz
    closeStepCompleteModal();
    const modal = document.createElement('div');
    modal.id = 'wf-step-modal';
    modal.className = 'wf-modal-overlay';
    modal.innerHTML = `
        <div class="wf-modal">
            <div class="wf-modal-head">
                <h3>🪜 Qadamni tugatish</h3>
                <button class="wf-modal-close" onclick="closeStepCompleteModal()">×</button>
            </div>
            <div class="wf-modal-body">
                <label class="wf-lbl">💬 Nimani bajardingiz? (ixtiyoriy)</label>
                <textarea id="wf-comment-input" class="wf-textarea" rows="3"
                          placeholder="Qisqacha yozing..."></textarea>
            </div>
            <div class="wf-modal-foot">
                <button class="wf-btn-secondary" onclick="closeStepCompleteModal()">Bekor</button>
                <button class="wf-btn-primary" onclick="submitStepComplete(${taskId})">✅ Saqlash</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('wf-modal-show'), 10);
}

function closeStepCompleteModal() {
    const m = document.getElementById('wf-step-modal');
    if (m) m.remove();
}

async function submitStepComplete(taskId) {
    const comment = (document.getElementById('wf-comment-input')?.value || '').trim();
    const status = 'done';  // Always mark as done when user clicks Tugat

    try {
        const r = await apiRequest(`/workflows/${taskId}/done`, 'POST', { comment, status });
        closeStepCompleteModal();
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        if (r.finished) {
            tg?.showAlert?.('🎉 Workflow to\'liq tugadi!');
        } else if (r.status === 'blocked') {
            tg?.showAlert?.('⏸ Workflow to\'xtatildi. Yaratuvchiga xabar yuborildi.');
        } else if (r.next_step) {
            tg?.showAlert?.('✅ Qabul qilindi.\n\nKeyingi: ' + r.next_step.title);
        }
        await loadWorkflows();
    } catch (e) {
        tg?.showAlert?.('❌ Xato: ' + (e.message || e));
    }
}

function formatMinutes(m) {
    if (m < 60) return m + ' min';
    const h = Math.floor(m/60);
    if (h < 24) return h + ' soat';
    return Math.floor(h/24) + ' kun';
}

// Eski variant — modal orqali ham chaqirish mumkin
async function markWorkflowStepDone(taskId) {
    openStepCompleteModal(taskId);
}

// Workflow filter chips
document.addEventListener('click', (ev) => {
    const c = ev.target.closest('[data-wf-filter]');
    if (!c) return;
    document.querySelectorAll('[data-wf-filter]').forEach(x => x.classList.remove('active'));
    c.classList.add('active');
    _wfFilter = c.dataset.wfFilter;
    renderWorkflows();
});

// ===== Filters =====
function initFilters() {
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentFilter = chip.dataset.filter;
            renderTasks();
        });
    });
}

// ===== Render Tasks =====
const TC_STATUS = {
    new: 'Yangi', in_progress: 'Jarayonda', review: "Ko'rilmoqda",
    done: 'Bajarildi', overdue: 'Kechikdi', cancelled: 'Bekor',
};

function renderTasks() {
    const list = document.getElementById('task-list');
    const empty = document.getElementById('empty-tasks');

    // Build subtask map from ALL tasks
    const subtaskMap = {};
    allTasks.forEach(t => {
        if (t.parent_id) {
            if (!subtaskMap[t.parent_id]) subtaskMap[t.parent_id] = [];
            subtaskMap[t.parent_id].push(t);
        }
    });

    // Apply filter - only to root tasks
    let filtered = allTasks.filter(t => !t.parent_id);
    if (currentFilter === 'active') {
        filtered = filtered.filter(t => !['done', 'cancelled'].includes(t.status));
    } else if (currentFilter === 'done') {
        filtered = filtered.filter(t => t.status === 'done');
    } else if (currentFilter === 'overdue') {
        filtered = filtered.filter(t => t.status === 'overdue');
    }

    if (filtered.length === 0) {
        list.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }

    list.classList.remove('hidden');
    empty.classList.add('hidden');

    list.innerHTML = filtered.map(task => {
        const children = subtaskMap[task.id] || [];
        return _renderTaskTree(task, children);
    }).join('');
}

function _renderTaskTree(task, children) {
    const parentHtml = `
        <div class="task-card tc-card" data-priority="${task.priority}" onclick="openTask(${task.id})">
            ${_taskCardInner(task, { subtaskCount: children.length })}
        </div>`;

    if (!children.length) return `<div class="tc-group">${parentHtml}</div>`;

    const childrenHtml = children.map(c => `
        <div class="tc-child-wrap">
            <div class="tc-child-dot"></div>
            <div class="task-card tc-card tc-card-child" data-priority="${c.priority}" onclick="openTask(${c.id})">
                ${_taskCardInner(c, { parentName: task.title })}
            </div>
        </div>`).join('');

    return `
        <div class="tc-group">
            <div class="tc-parent-wrap">
                <div class="tc-parent-dot"></div>
                ${parentHtml}
            </div>
            <div class="tc-children">
                ${childrenHtml}
            </div>
        </div>`;
}

function _taskCardInner(task, opts = {}) {
    const { subtaskCount = 0, parentName = null } = opts;
    const dlClass = task.deadline ? getDeadlineClass(task.deadline, task.status) : '';
    const dlUrgent = dlClass === 'deadline-urgent';
    const dlSoon   = dlClass === 'deadline-soon';

    // Assignees row
    let assigneeHtml = '';
    if (task.assignees && task.assignees.length > 0) {
        const chips = task.assignees.slice(0, 3).map(a => {
            const init = (a.name || '?')[0].toUpperCase();
            const aSt = a.status || 'new';
            return `<span class="tc-avatar tc-av-${aSt}" title="${escapeHtml(a.name)}">${escapeHtml(init)}</span>`;
        }).join('');
        const names = task.assignees.slice(0, 2).map(a => escapeHtml(a.name.split(' ')[0])).join(', ')
            + (task.assignees.length > 2 ? ` +${task.assignees.length - 2}` : '');
        assigneeHtml = `<div class="tc-row">${chips}<span class="tc-meta-name">${names}</span></div>`;
    }

    // Subtask / parent ref row
    let refHtml = '';
    if (parentName) {
        refHtml = `<div class="tc-row tc-parent-ref"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 3 12 9 6"/><path d="M21 12H3"/></svg> Parent: ${escapeHtml(parentName)}</div>`;
    } else if (subtaskCount > 0) {
        refHtml = `<div class="tc-row tc-subtask-ref"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 3v12"/><path d="M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M15 6H6"/><path d="M6 18h8a4 4 0 0 0 0-8h-1"/></svg> ${subtaskCount} subtask</div>`;
    }

    // Deadline row
    let dlHtml = '';
    if (task.deadline) {
        const icon = dlUrgent ? '🔥' : '⏰';
        const dlCls = dlUrgent ? 'tc-dl-urgent' : (dlSoon ? 'tc-dl-soon' : 'tc-dl-normal');
        dlHtml = `<div class="tc-row ${dlCls}">${icon} ${formatDeadline(task.deadline)}</div>`;
    }

    return `
        <div class="tc-header">
            <span class="tc-title">${escapeHtml(task.title)}</span>
            <span class="tc-badge tc-badge-${task.status}">${TC_STATUS[task.status] || task.status}</span>
        </div>
        <div class="tc-body">
            ${assigneeHtml}${refHtml}${dlHtml}
        </div>`;
}

// ===== Task Detail Modal =====
async function openTask(taskId) {
    currentTaskId = taskId;
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        const data = await apiRequest(`/tasks/${taskId}`);
        const task = data.task;
        
        document.getElementById('modal-title').textContent = task.title;
        
        const priorityNames = { low: '🟢 Past', medium: '🟡 O\'rta', high: '🟠 Yuqori', urgent: '🔴 Juda muhim' };
        const statusNames = {
            new: '🆕 Yangi', in_progress: '⚙️ Jarayonda', review: '🔍 Ko\'rilmoqda',
            done: '✅ Bajarildi', overdue: '⏰ Kechikdi', cancelled: '🚫 Bekor',
        };

        const priorityColors = { low: 'priority-low', medium: 'priority-medium', high: 'priority-high', urgent: 'priority-urgent' };
        let bodyHtml = `
            <div class="modal-section">
                <div class="modal-detail">
                    <div class="modal-detail-label">📍 Status</div>
                    <div class="modal-detail-value badge-${task.status}">${statusNames[task.status] || task.status}</div>
                </div>
                <div class="modal-detail">
                    <div class="modal-detail-label">⚡ Muhimlik</div>
                    <div class="modal-detail-value ${priorityColors[task.priority] || ''}">${priorityNames[task.priority] || task.priority}</div>
                </div>
            </div>
        `;

        if (task.description) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">Tavsif</div>
                    <div class="modal-detail-value">${escapeHtml(task.description)}</div>
                </div>
            `;
        }

        if (task.deadline) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">Deadline</div>
                    <div class="modal-detail-value">${formatDeadlineFull(task.deadline)}</div>
                </div>
            `;
        }

        if (task.creator_name) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">Yaratgan</div>
                    <div class="modal-detail-value">👤 ${escapeHtml(task.creator_name)}</div>
                </div>
            `;
        }

        const statusShort = {
            new: '🆕 Yangi', in_progress: '⚙️ Jarayonda', review: '🔍 Ko\'rilmoqda',
            done: '✅ Bajarildi', overdue: '⏰ Kechikdi', cancelled: '🚫 Bekor',
        };

        if (task.assignees && task.assignees.length > 0) {
            const rows = task.assignees.map(a => {
                const st = a.status || 'new';
                return `
                    <div class="assignee-row">
                        <span class="assignee-row-name">👤 ${escapeHtml(a.name)}</span>
                        <span class="assignee-row-status badge-${st}">${statusShort[st] || st}</span>
                    </div>
                `;
            }).join('');
            const doneCount = task.assignees.filter(a => (a.status||'new') === 'done').length;
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">Ijrochilar va ularning statusi (${doneCount}/${task.assignees.length} bajardi)</div>
                    <div class="modal-detail-value assignees-status-list">${rows}</div>
                </div>
            `;
        }

        // Subtasks — compact
        const subtasks = task.subtasks || [];
        if (subtasks.length > 0) {
            const subItems = subtasks.slice(0, 3).map(s => `
                <div class="subtask-item" onclick="openTask(${s.id})">
                    <span class="subtask-status badge-${s.status}" style="font-size:10px">${statusShort[s.status] || s.status}</span>
                    <span class="subtask-title">${escapeHtml(s.title.slice(0, 30))}</span>
                </div>
            `).join('');
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">🧩 Subtasklar (${subtasks.length})</div>
                    <div class="subtask-list">${subItems}</div>
                    ${subtasks.length > 3 ? '<div style="font-size:10px;color:#94a3b8;margin-top:4px">+' + (subtasks.length - 3) + ' yana...</div>' : ''}
                </div>
            `;
        }

        // Attachments — compact
        const atts = task.attachments || [];
        if (atts.length > 0) {
            const attItems = atts.slice(0, 3).map(a => {
                const isImg = a.file_type === 'photo' || (a.mime_type||'').startsWith('image/');
                if (isImg) return `<a class="att-item att-img" href="${a.file_url}" target="_blank"><img src="${a.file_url}" alt=""/></a>`;
                return `<a class="att-item att-file" href="${a.file_url}" target="_blank" style="font-size:10px">📎</a>`;
            }).join('');
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">📎 Fayllar (${atts.length})</div>
                    <div class="att-list" style="margin-bottom:6px">${attItems}</div>
                    ${atts.length > 3 ? '<div style="font-size:10px;color:#94a3b8">+' + (atts.length - 3) + ' fayl</div>' : ''}
                </div>
            `;
        }

        // Metadata — minimal
        bodyHtml += `
            <div class="modal-detail">
                <div class="modal-detail-label">📅 Yaratilgan</div>
                <div class="modal-detail-value" style="font-size:12px">${formatDate(task.created_at)}</div>
            </div>
        `;

        // 📊 Vaqt / aktivlik chartlari
        bodyHtml += `
            <div class="modal-detail">
                <div class="modal-detail-label">📊 Vaqt va aktivlik</div>
                <div id="task-chart-${task.id}" class="task-chart-wrap">
                    <div class="task-chart-loading">Yuklanmoqda...</div>
                </div>
            </div>
        `;

        // Tarix / Roadmap — minimal (first 3 only)
        if (task.history && task.history.length > 0) {
            const historyPreview = task.history.slice(0, 3);
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">🕐 So'nggi harakatlari (${task.history.length})</div>
                    <div class="timeline">${_renderTimeline(historyPreview)}</div>
                    ${task.history.length > 3 ? '<div style="font-size:11px;color:#94a3b8;margin-top:6px">+' + (task.history.length - 3) + ' boshqa...</div>' : ''}
                </div>
            `;
        }

        document.getElementById('modal-body').innerHTML = bodyHtml;

        // Actions - single state-based button for regular tasks (no workflow)
        let actionsHtml = '';
        const myStatus = task.my_status;
        const isWorkflow = task.has_workflow === true;

        if (myStatus && !isWorkflow) {
            // Single-button state progression for regular tasks
            let buttonClass = 'wf-btn-start';
            let buttonText = '▶️ Boshlash';

            if (myStatus === 'in_progress') {
                buttonClass = 'wf-btn-done';
                buttonText = '✅ Bajarildi';
            } else if (myStatus === 'done') {
                buttonClass = 'wf-btn-secondary';
                buttonText = '✓ Tugagan';
            }

            actionsHtml += `
                <div class="my-status-hint">Sizning statusingiz: <b>${statusShort[myStatus] || myStatus}</b></div>
                <button class="wf-status-btn ${buttonClass}" onclick="handleTaskAction(${task.id}, '${myStatus}')">
                    ${buttonText}
                </button>
            `;
        } else if (myStatus && isWorkflow) {
            // Original buttons for workflow tasks
            actionsHtml += `<div class="my-status-hint">Sizning statusingiz: <b>${statusShort[myStatus] || myStatus}</b></div>`;
            if (myStatus === 'new') {
                actionsHtml += `<button class="modal-action-btn btn-primary" onclick="changeMyStatus(${task.id}, 'in_progress')">▶️ Men boshladim</button>`;
            }
            if (myStatus === 'in_progress' || myStatus === 'new') {
                actionsHtml += `<button class="modal-action-btn btn-success" onclick="changeMyStatus(${task.id}, 'done')">✅ Men bajardim</button>`;
            }
            if (myStatus === 'done') {
                actionsHtml += `<button class="modal-action-btn btn-primary" onclick="changeMyStatus(${task.id}, 'in_progress')">🔄 Qayta ochish</button>`;
            }
        }
        if (task.is_creator && !['done', 'cancelled'].includes(task.status)) {
            actionsHtml += `<button class="modal-action-btn btn-danger" onclick="changeStatus(${task.id}, 'cancelled')">🚫 Vazifani bekor qilish</button>`;
        }

        actionsHtml += `
            <div class="comment-input-wrap">
                <textarea class="comment-input" id="comment-input-${task.id}"
                    placeholder="💬 Izoh yozing..." rows="2" maxlength="1000"></textarea>
                <button class="comment-send-btn" onclick="sendComment(${task.id})">Yuborish ➤</button>
            </div>
        `;

        document.getElementById('modal-actions').innerHTML = actionsHtml;
        document.getElementById('task-modal').classList.remove('hidden');

        // Chart fon tarzda yuklanadi
        loadTaskChart(task.id);

    } catch (err) {
        showToast('Vazifa yuklanmadi', true);
    }
}

// ===== Task Chart (kim nechi soat ketqazgan) =====
const _taskChartInstances = {};
async function loadTaskChart(taskId) {
    const wrap = document.getElementById(`task-chart-${taskId}`);
    if (!wrap) return;
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js yuklanmagan');
        wrap.innerHTML = '<div class="task-chart-empty">Chart.js yuklanmadi</div>';
        return;
    }
    try {
        const data = await apiRequest(`/tasks/${taskId}/chart`);
        console.log('[chart]', taskId, data);
        if (!data || !data.ok) {
            wrap.innerHTML = '<div class="task-chart-empty">Ma\'lumot yo\'q</div>';
            return;
        }

        const users = data.users || [];
        const steps = data.steps || [];

        // Summary qator
        let html = `
            <div class="tc-summary">
                <div class="tc-sum-item"><span class="tc-sum-val">${data.total_hours}</span><span class="tc-sum-lab">⏱ jami soat</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.lifespan_hours}</span><span class="tc-sum-lab">📅 umumiy davomiylik</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.comments}</span><span class="tc-sum-lab">💬 izoh</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.attachments}</span><span class="tc-sum-lab">📎 fayl</span></div>
            </div>
        `;

        if (users.length === 0 && steps.length === 0) {
            wrap.innerHTML = html + '<div class="task-chart-empty">Hali aktivlik qayd etilmagan</div>';
            return;
        }

        // Chart canvaslari
        if (users.length > 0) {
            html += `
                <div class="tc-chart-block">
                    <div class="tc-chart-title">👥 Kim nechi soat ketqazdi</div>
                    <div class="tc-canvas-wrap" style="height:${Math.max(160, users.length * 38)}px">
                        <canvas id="tc-users-${taskId}"></canvas>
                    </div>
                </div>
            `;
        }

        if (steps.length > 0) {
            html += `
                <div class="tc-chart-block">
                    <div class="tc-chart-title">🪜 Qadamlar davomiyligi</div>
                    <div class="tc-canvas-wrap" style="height:${Math.max(160, steps.length * 38)}px">
                        <canvas id="tc-steps-${taskId}"></canvas>
                    </div>
                </div>
            `;
        }

        // Aktivlik (comments + attachments)
        const actUsers = users.filter(u => (u.comments + u.attachments) > 0);
        if (actUsers.length > 0) {
            html += `
                <div class="tc-chart-block">
                    <div class="tc-chart-title">💬 Aktivlik (izoh + fayl)</div>
                    <div class="tc-canvas-wrap" style="height:${Math.max(160, actUsers.length * 38)}px">
                        <canvas id="tc-activity-${taskId}"></canvas>
                    </div>
                </div>
            `;
        }

        wrap.innerHTML = html;

        // Eski instancelarni tozalash
        ['users', 'steps', 'activity'].forEach(k => {
            const key = `${taskId}_${k}`;
            if (_taskChartInstances[key]) {
                try { _taskChartInstances[key].destroy(); } catch(_) {}
                delete _taskChartInstances[key];
            }
        });

        const palette = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#f472b6', '#22d3ee', '#fb923c'];

        // 1) Users chart (horizontal bar)
        if (users.length > 0) {
            const ctx = document.getElementById(`tc-users-${taskId}`);
            if (ctx) {
                _taskChartInstances[`${taskId}_users`] = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: users.map(u => u.name),
                        datasets: [{
                            label: 'Soat',
                            data: users.map(u => u.hours),
                            backgroundColor: users.map((_, i) => palette[i % palette.length]),
                            borderRadius: 8,
                        }],
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => `${ctx.parsed.x} soat`,
                                },
                            },
                        },
                        scales: {
                            x: { beginAtZero: true, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
                            y: { ticks: { color: '#e2e8f0' }, grid: { display: false } },
                        },
                    },
                });
            }
        }

        // 2) Steps chart
        if (steps.length > 0) {
            const ctx = document.getElementById(`tc-steps-${taskId}`);
            if (ctx) {
                const statusColor = {
                    done: '#34d399', active: '#60a5fa', pending: '#64748b', blocked: '#fb923c',
                };
                _taskChartInstances[`${taskId}_steps`] = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: steps.map(s => `${s.order}. ${s.title.length > 22 ? s.title.slice(0,22)+'…' : s.title}`),
                        datasets: [{
                            label: 'Soat',
                            data: steps.map(s => s.hours),
                            backgroundColor: steps.map(s => statusColor[s.status] || '#64748b'),
                            borderRadius: 8,
                        }],
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => {
                                        const s = steps[ctx.dataIndex];
                                        return [
                                            `${s.hours} soat`,
                                            `👤 ${s.assignee}`,
                                            `📍 ${s.status}`,
                                            `💬 ${s.comments_count} · 📎 ${s.attachments_count}`,
                                        ];
                                    },
                                },
                            },
                        },
                        scales: {
                            x: { beginAtZero: true, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
                            y: { ticks: { color: '#e2e8f0' }, grid: { display: false } },
                        },
                    },
                });
            }
        }

        // 3) Activity chart (stacked)
        if (actUsers.length > 0) {
            const ctx = document.getElementById(`tc-activity-${taskId}`);
            if (ctx) {
                _taskChartInstances[`${taskId}_activity`] = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: actUsers.map(u => u.name),
                        datasets: [
                            { label: '💬 Izoh', data: actUsers.map(u => u.comments), backgroundColor: '#60a5fa', borderRadius: 6 },
                            { label: '📎 Fayl', data: actUsers.map(u => u.attachments), backgroundColor: '#fbbf24', borderRadius: 6 },
                        ],
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { labels: { color: '#e2e8f0' } },
                        },
                        scales: {
                            x: { stacked: true, beginAtZero: true, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
                            y: { stacked: true, ticks: { color: '#e2e8f0' }, grid: { display: false } },
                        },
                    },
                });
            }
        }
    } catch (err) {
        console.error('chart load error', err);
        wrap.innerHTML = '<div class="task-chart-empty">Chart yuklanmadi</div>';
    }
}

function closeModal() {
    document.getElementById('task-modal').classList.add('hidden');
    currentTaskId = null;
}

// Close modal on overlay click
document.getElementById('task-modal')?.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) closeModal();
});

// ===== Change Status =====
async function changeStatus(taskId, newStatus) {
    try {
        await apiRequest(`/tasks/${taskId}/status`, 'PATCH', { status: newStatus });
        
        // Update local
        const task = allTasks.find(t => t.id === taskId);
        if (task) task.status = newStatus;
        
        renderTasks();
        closeModal();
        showToast('✅ Status yangilandi!');
        if (tg) tg.HapticFeedback?.notificationOccurred('success');

        // Refresh stats
        const stats = await apiRequest(`/stats?company_id=${currentWorkspaceId}`);
        updateQuickStats(stats);
        updateStatsTab(stats);
    } catch (err) {
        showToast('Xatolik yuz berdi', true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
    }
}

function changeMyStatus(taskId, newStatus) {
    const actionsEl = document.getElementById('modal-actions');
    if (!actionsEl) return;

    const STATUS_LABELS = {
        in_progress: '▶️ Jarayonda', done: '✅ Bajarildi',
        review: '🔍 Ko\'rilmoqda', cancelled: '🚫 Bekor qilish',
    };
    const sLabel = STATUS_LABELS[newStatus] || newStatus;
    const originalHtml = actionsEl.innerHTML;

    actionsEl.innerHTML = `
        <div class="sc-wrap">
            <div class="sc-header">
                <span class="sc-status-label">Status: <b>${sLabel}</b></span>
                <span class="sc-hint">Ixtiyoriy izoh</span>
            </div>
            <textarea class="sc-textarea" id="sc-ta-${taskId}"
                placeholder="Nima qildingiz? Qanday natija chiqdi? Muammo bormi?..."
                rows="3" maxlength="500"></textarea>
            <div class="sc-btns">
                <button class="sc-btn sc-btn-cancel" id="sc-cancel-${taskId}">Bekor</button>
                <button class="sc-btn sc-btn-confirm" id="sc-confirm-${taskId}">${sLabel}</button>
            </div>
        </div>
    `;

    document.getElementById(`sc-cancel-${taskId}`).onclick = () => {
        actionsEl.innerHTML = originalHtml;
    };
    document.getElementById(`sc-confirm-${taskId}`).onclick = async function() {
        const comment = (document.getElementById(`sc-ta-${taskId}`)?.value || '').trim();
        this.disabled = true;
        this.textContent = '⏳';
        await _submitMyStatus(taskId, newStatus, comment);
    };
    document.getElementById(`sc-ta-${taskId}`)?.focus();
}

async function _submitMyStatus(taskId, newStatus, comment) {
    try {
        const body = { status: newStatus };
        if (comment) body.comment = comment;
        const res = await apiRequest(`/tasks/${taskId}/my-status`, 'PATCH', body);
        const task = allTasks.find(t => t.id === taskId);
        if (task && res.task_status) task.status = res.task_status;
        showToast('✅ Status yangilandi!');
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        closeModal();
        const [tasks, stats] = await Promise.all([
            apiRequest(`/tasks?company_id=${currentWorkspaceId}`),
            apiRequest(`/stats?company_id=${currentWorkspaceId}`),
        ]);
        allTasks = tasks.tasks || [];
        updateQuickStats(stats);
        updateStatsTab(stats);
        renderTasks();
        await openTask(taskId);
    } catch (err) {
        showToast('Xatolik yuz berdi', true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
    }
}

async function sendComment(taskId) {
    const input = document.getElementById(`comment-input-${taskId}`);
    if (!input) return;
    const content = input.value.trim();
    if (!content) { showToast("Izoh bo'sh bo'lmasin", true); return; }

    try {
        const res = await apiRequest(`/tasks/${taskId}/comments`, 'POST', { content });
        input.value = '';
        showToast('💬 Izoh yuborildi!');
        if (tg) tg.HapticFeedback?.notificationOccurred('success');

        // Timeline ga qo'shamiz
        const timeline = document.querySelector('.timeline');
        if (timeline && res.comment) {
            const h = res.comment;
            const item = document.createElement('div');
            item.className = 'timeline-item';
            item.innerHTML = `
                <div class="timeline-dot">💬</div>
                <div class="timeline-body">
                    <div class="timeline-label"><b>${escapeHtml(h.user_name || '?')}</b>: ${escapeHtml(h.content || '')}</div>
                    <div class="timeline-time">${formatDateTime(h.created_at)}</div>
                </div>
            `;
            timeline.appendChild(item);
        }
    } catch (err) {
        showToast('Yuborishda xatolik', true);
    }
}

function formatDateTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${day}.${month}.${d.getFullYear()} ${hh}:${mm}`;
}

// ===== Create Task =====
let currentTaskType = 'regular';  // 'regular' or 'workflow'
let workflowSteps = [];  // [{title, assignee_id, assignee_name}, ...]

function initForm() {
    const titleInput = document.getElementById('task-title');
    const countEl = document.getElementById('title-count');

    titleInput?.addEventListener('input', () => {
        countEl.textContent = titleInput.value.length;
    });

    // Priority buttons
    document.querySelectorAll('.priority-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.priority-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            if (tg) tg.HapticFeedback?.selectionChanged();
        });
    });
}

// Select task type (regular or workflow)
function selectTaskType(type) {
    currentTaskType = type;
    workflowSteps = [];  // Reset steps

    // Update button styles
    document.querySelectorAll('.task-type-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    document.querySelector(`.task-type-btn[data-type="${type}"]`)?.classList.add('selected');

    // Show/hide workflow steps group
    const stepsGroup = document.getElementById('workflow-steps-group');
    const createBtn = document.getElementById('btn-create-task');

    if (type === 'workflow') {
        stepsGroup.classList.remove('hidden');
        createBtn.querySelector('.btn-text').textContent = '✅ Workflow yaratish';
        renderWorkflowSteps();
    } else {
        stepsGroup.classList.add('hidden');
        createBtn.querySelector('.btn-text').textContent = '✅ Vazifa yaratish';
    }

    if (tg) tg.HapticFeedback?.selectionChanged();
}

// Add a new workflow step
function addWorkflowStep() {
    workflowSteps.push({
        title: '',
        assignee_id: null,
        assignee_name: ''
    });
    renderWorkflowSteps();
}

// Render workflow steps UI
function renderWorkflowSteps() {
    const list = document.getElementById('workflow-steps-list');
    if (!list) return;

    if (workflowSteps.length === 0) {
        list.innerHTML = '<div class="wf-step-empty">Hali qadam yo\'q. Boshing!</div>';
        return;
    }

    list.innerHTML = workflowSteps.map((step, idx) => `
        <div class="wf-step-editor" data-index="${idx}">
            <div class="wf-step-num">${idx + 1}.</div>
            <input type="text" class="wf-step-title" placeholder="Qadam nomi" value="${step.title}"
                   onchange="updateWorkflowStep(${idx}, 'title', this.value)">
            <select class="wf-step-assignee" onchange="updateWorkflowStep(${idx}, 'assignee', this.value)">
                <option value="">Ijrochini tanlang</option>
                ${companyMembers.map(m => `
                    <option value="${m.id}" ${step.assignee_id == m.id ? 'selected' : ''}>👤 ${m.name}</option>
                `).join('')}
            </select>
            <button class="btn-remove-step" onclick="removeWorkflowStep(${idx})">🗑</button>
        </div>
    `).join('');
}

// Update workflow step
function updateWorkflowStep(idx, field, value) {
    if (idx >= 0 && idx < workflowSteps.length) {
        if (field === 'title') {
            workflowSteps[idx].title = value;
        } else if (field === 'assignee') {
            workflowSteps[idx].assignee_id = value ? parseInt(value) : null;
            const member = companyMembers.find(m => m.id == value);
            workflowSteps[idx].assignee_name = member?.name || '';
        }
    }
}

// Remove workflow step
function removeWorkflowStep(idx) {
    workflowSteps.splice(idx, 1);
    renderWorkflowSteps();
}

async function createTask() {
    const title = document.getElementById('task-title').value.trim();
    const description = document.getElementById('task-desc').value.trim();
    const priority = document.querySelector('.priority-btn.selected')?.dataset.priority || 'medium';
    const deadline = document.getElementById('task-deadline').value;

    if (!title || title.length < 3) {
        showToast('Vazifa nomi kamida 3 belgi bo\'lsin', true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
        return;
    }

    // Workflow validation
    if (currentTaskType === 'workflow') {
        if (workflowSteps.length === 0) {
            showToast('Kamida bitta qadam qo\'shish majburiy', true);
            return;
        }
        const invalidSteps = workflowSteps.some(s => !s.title.trim() || !s.assignee_id);
        if (invalidSteps) {
            showToast('Barcha qadam nomlari va ijrochilari to\'liq bo\'lish majburiy', true);
            return;
        }
    }

    const btn = document.getElementById('btn-create-task');
    btn.disabled = true;
    btn.querySelector('.btn-text').classList.add('hidden');
    btn.querySelector('.btn-loading').classList.remove('hidden');

    try {
        if (currentTaskType === 'workflow') {
            // Create workflow
            const body = {
                title,
                priority,
                steps: workflowSteps.map(s => ({
                    title: s.title.trim(),
                    assignee_user_id: s.assignee_id
                }))
            };
            if (description) body.description = description;
            if (deadline) body.deadline = new Date(deadline).toISOString();
            if (currentWorkspaceId !== 'personal') {
                body.company_id = currentWorkspaceId;
            }

            await apiRequest('/tasks/create-workflow', 'POST', body);
            showToast('✅ Workflow yaratildi!');
            document.querySelector('.bnav-btn[data-tab="workflow"]').click();
            await loadWorkflows();
        } else {
            // Create regular task
            const body = { title, priority };
            if (description) body.description = description;
            if (deadline) body.deadline = new Date(deadline).toISOString();
            if (currentWorkspaceId !== 'personal') {
                body.company_id = currentWorkspaceId;
                if (selectedAssigneeIds.length === 0) {
                    showToast("Kamida bitta ijrochi tanlang", true);
                    btn.disabled = false;
                    btn.querySelector('.btn-text').classList.remove('hidden');
                    btn.querySelector('.btn-loading').classList.add('hidden');
                    return;
                }
                body.assignee_ids = selectedAssigneeIds;
            }

            const result = await apiRequest('/tasks', 'POST', body);

            // Add to local list
            if (result.task) {
                allTasks.unshift(result.task);
            }

            showToast('✅ Vazifa yaratildi!');
            // Switch to tasks tab
            document.querySelector('.bnav-btn[data-tab="tasks"]').click();

            // Refresh stats
            const stats = await apiRequest(`/stats?company_id=${currentWorkspaceId}`);
            updateQuickStats(stats);
            updateStatsTab(stats);
            renderTasks();
        }

        if (tg) tg.HapticFeedback?.notificationOccurred('success');

        // Clear form
        document.getElementById('task-title').value = '';
        document.getElementById('task-desc').value = '';
        document.getElementById('task-deadline').value = '';
        document.getElementById('title-count').textContent = '0';
        selectedAssigneeIds = [];
        currentTaskType = 'regular';
        workflowSteps = [];
        selectTaskType('regular');
        updateAssigneesList();

    } catch (err) {
        showToast('Yaratishda xatolik: ' + (err.message || err), true);
    } finally {
        btn.disabled = false;
        btn.querySelector('.btn-text').classList.remove('hidden');
        btn.querySelector('.btn-loading').classList.add('hidden');
    }
}

// ===== Toast =====
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    document.getElementById('toast-message').textContent = message;
    toast.className = isError ? 'toast error' : 'toast';
    
    setTimeout(() => { toast.classList.add('hidden'); }, 2500);
}

// ===== Helpers =====
function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    return `${day}.${month}.${d.getFullYear()}`;
}

function formatDeadline(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = d - now;
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(hours / 24);

    if (diff < 0) {
        const absDays = Math.abs(days);
        return absDays > 0 ? `${absDays} kun kechikdi` : `${Math.abs(hours)} soat kechikdi`;
    }
    if (days === 0) return hours < 1 ? '1 soatdan kam!' : `${hours} soat qoldi`;
    if (days === 1) return 'Ertaga';
    if (days < 7) return `${days} kun qoldi`;
    return formatDate(iso);
}

function formatDeadlineFull(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const mins = String(d.getMinutes()).padStart(2, '0');
    return `${day}.${month}.${d.getFullYear()} ${hours}:${mins}`;
}

function getDeadlineClass(iso, status) {
    if (status === 'done' || status === 'cancelled') return '';
    const diff = new Date(iso) - new Date();
    if (diff < 0) return 'deadline-urgent';
    if (diff < 86400000) return 'deadline-urgent'; // 24h
    if (diff < 259200000) return 'deadline-soon'; // 3 days
    return '';
}

// ============ AI Chat ============
const AI_SUGGESTIONS = [
    "Vazifalarimni ko'rsat",
    "Statistikamni ko'rsat",
    "Yangi vazifa yaratish",
    "Kechikkan vazifalar",
    "Muhim vazifalar",
];

function openAiChat() {
    const overlay = document.getElementById('ai-chat-overlay');
    overlay.classList.remove('hidden');
    _renderAiSuggestions();
    setTimeout(() => {
        const input = document.getElementById('ai-chat-input');
        if (input) input.focus();
    }, 120);
}

function closeAiChat() {
    document.getElementById('ai-chat-overlay').classList.add('hidden');
}

function clearAiChat() {
    aiHistory = [];
    const box = document.getElementById('ai-chat-messages');
    box.innerHTML = `<div class="ai-msg ai-msg-bot">
        Salom! Men TaskBot AI yordamchisiman. Menga vazifa yarating, ro'yxat so'rang yoki savol bering. 🎯
    </div>`;
    _renderAiSuggestions();
}

function _renderAiSuggestions() {
    const box = document.getElementById('ai-chat-messages');
    const old = box.querySelector('.ai-suggestions');
    if (old) old.remove();
    if (aiHistory.length > 0) return;
    const wrap = document.createElement('div');
    wrap.className = 'ai-suggestions';
    wrap.innerHTML = AI_SUGGESTIONS.map(s =>
        `<button class="ai-sugg-chip" onclick="_aiSuggClick(this,'${s}')">${s}</button>`
    ).join('');
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
}

function _aiSuggClick(btn, text) {
    const input = document.getElementById('ai-chat-input');
    if (input) { input.value = text; }
    sendAiMessage();
}

function _aiMsgBox() {
    return document.getElementById('ai-chat-messages');
}

function appendAiMsg(text, who) {
    const box = _aiMsgBox();
    const sugg = box.querySelector('.ai-suggestions');
    if (sugg) sugg.remove();
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-' + who;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

function appendAiRich(htmlText, tasks, actions) {
    const box = _aiMsgBox();
    const sugg = box.querySelector('.ai-suggestions');
    if (sugg) sugg.remove();

    const wrap = document.createElement('div');
    wrap.className = 'ai-msg ai-msg-bot ai-msg-html';

    // Text with HTML (safe - generated by backend)
    const textDiv = document.createElement('div');
    textDiv.innerHTML = htmlText;
    wrap.appendChild(textDiv);

    // Task chips
    if (tasks && tasks.length > 0) {
        const chipsDiv = document.createElement('div');
        chipsDiv.className = 'ai-task-chips';
        const S_ICON = {new:'🆕',in_progress:'⚙️',done:'✅',overdue:'⏰',review:'🔍',cancelled:'🚫'};
        const P_ICON = {urgent:'🔴',high:'🟠',medium:'🟡',low:'🟢'};
        tasks.slice(0, 8).forEach(t => {
            const btn = document.createElement('button');
            btn.className = 'ai-task-chip';
            const si = S_ICON[t.status] || '•';
            const pi = P_ICON[t.priority] || '';
            btn.innerHTML = `<span class="ai-chip-icon">${si}${pi}</span><span class="ai-chip-title">${escapeHtml(t.title)}</span><span class="ai-chip-id">#${t.id}</span>`;
            btn.onclick = () => { closeAiChat(); openTask(t.id); };
            chipsDiv.appendChild(btn);
        });
        wrap.appendChild(chipsDiv);
    }

    // Action buttons
    if (actions && actions.length > 0) {
        const actDiv = document.createElement('div');
        actDiv.className = 'ai-action-btns';
        actions.forEach(a => {
            const btn = document.createElement('button');
            btn.className = 'ai-action-btn ' + (a.cls || '');
            btn.textContent = a.label;
            btn.onclick = a.fn;
            actDiv.appendChild(btn);
        });
        wrap.appendChild(actDiv);
    }

    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
}

function _askWorkspaceInChat(proposal) {
    return new Promise((resolve) => {
        const box = _aiMsgBox();
        const wrap = document.createElement('div');
        wrap.className = 'ai-msg ai-msg-bot ai-msg-html ai-proposal';

        // Mavjud workspace ro'yxati
        const wsSel = document.getElementById('workspace-select');
        const opts = wsSel ? Array.from(wsSel.options).filter(o => o.value !== 'all') : [];

        const intro = document.createElement('div');
        intro.innerHTML = `📋 <b>Vazifa tafsilotlari to'plandi:</b><br><br>` +
            `📌 <b>Nomi:</b> ${escapeHtml(proposal.title)}<br>` +
            `📝 <b>Tavsif:</b> ${escapeHtml(proposal.description)}<br>` +
            `⚡ <b>Muhimlik:</b> ${proposal.priority}<br>` +
            `⏰ <b>Deadline:</b> ${escapeHtml(proposal.deadline_display || proposal.deadline)}<br><br>` +
            `📁 <b>Qaysi workspace ga qo'shaman?</b>`;
        wrap.appendChild(intro);

        const btnRow = document.createElement('div');
        btnRow.className = 'ai-proposal-btns ai-ws-btns';

        opts.forEach(o => {
            const btn = document.createElement('button');
            btn.className = 'ai-prop-btn ai-prop-ws';
            btn.textContent = o.text;
            btn.onclick = () => {
                wrap.querySelectorAll('button').forEach(b => b.disabled = true);
                btn.classList.add('ai-prop-ws-active');
                resolve(o.value);
            };
            btnRow.appendChild(btn);
        });

        const cancel = document.createElement('button');
        cancel.className = 'ai-prop-btn ai-prop-cancel';
        cancel.innerHTML = '❌ Bekor';
        cancel.onclick = () => {
            wrap.querySelectorAll('button').forEach(b => b.disabled = true);
            appendAiMsg('Vazifa yaratish bekor qilindi.', 'bot');
            resolve(null);
        };
        btnRow.appendChild(cancel);

        wrap.appendChild(btnRow);
        box.appendChild(wrap);
        box.scrollTop = box.scrollHeight;
    });
}

async function renderTaskProposal(textHtml, proposal) {
    const box = _aiMsgBox();

    // 1-qadam: Workspace tanlash
    let chosenWs = proposal.company_id || null;
    if (!chosenWs || chosenWs === 'all') {
        chosenWs = await _askWorkspaceInChat(proposal);
        if (chosenWs === null) {
            // Bekor qilindi
            return;
        }
    }
    proposal.company_id = chosenWs;

    // Workspace nomini topamiz ko'rsatish uchun
    let wsLabel = '👤 Shaxsiy';
    try {
        const wsSel = document.getElementById('workspace-select');
        if (wsSel) {
            const opt = Array.from(wsSel.options).find(o => o.value === String(chosenWs));
            if (opt) wsLabel = opt.text;
        }
    } catch (_) {}

    // textHtml ichidagi Workspace qatorini yangilaymiz
    const updatedHtml = textHtml.replace(/📁 <b>Workspace:<\/b>[^<\n]*/, `📁 <b>Workspace:</b> ${wsLabel}`);

    const wrap = document.createElement('div');
    wrap.className = 'ai-msg ai-msg-bot ai-msg-html ai-proposal';

    const txt = document.createElement('div');
    txt.innerHTML = updatedHtml;
    wrap.appendChild(txt);

    const btnRow = document.createElement('div');
    btnRow.className = 'ai-proposal-btns';

    const okBtn = document.createElement('button');
    okBtn.className = 'ai-prop-btn ai-prop-ok';
    okBtn.innerHTML = '✅ Tasdiqlash va yaratish';

    const editBtn = document.createElement('button');
    editBtn.className = 'ai-prop-btn ai-prop-edit';
    editBtn.innerHTML = '✏️ O\'zgartirish';

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'ai-prop-btn ai-prop-cancel';
    cancelBtn.innerHTML = '❌ Bekor';

    okBtn.onclick = async () => {
        okBtn.disabled = true; editBtn.disabled = true; cancelBtn.disabled = true;
        okBtn.innerHTML = '⏳ Yaratilmoqda...';
        try {
            const res = await apiRequest('/ai/confirm-task', 'POST', {
                title: proposal.title,
                description: proposal.description,
                priority: proposal.priority,
                deadline: proposal.deadline,
                company_id: proposal.company_id || currentWorkspaceId,
            });
            wrap.remove();
            const actions = [{
                label: '📋 Vazifani ochish',
                cls: 'btn-go-task',
                fn: () => { closeAiChat(); openTask(res.task_id); },
            }];
            appendAiRich(res.text, null, actions);
            // Refresh
            try {
                const [tasks, stats] = await Promise.all([
                    apiRequest(`/tasks?company_id=${currentWorkspaceId}`),
                    apiRequest(`/stats?company_id=${currentWorkspaceId}`),
                ]);
                allTasks = tasks.tasks || [];
                renderTasks();
                updateQuickStats(stats);
                updateStatsTab(stats);
            } catch (_) {}
            if (tg) tg.HapticFeedback?.notificationOccurred('success');
        } catch (e) {
            okBtn.disabled = false; editBtn.disabled = false; cancelBtn.disabled = false;
            okBtn.innerHTML = '✅ Tasdiqlash va yaratish';
            appendAiMsg('Yaratishda xatolik: ' + (e.message || ''), 'bot');
        }
    };

    editBtn.onclick = () => {
        wrap.remove();
        appendAiMsg("Yaxshi, qaysi qismini o'zgartiraman? (nom / tavsif / muhimlik / deadline)", 'bot');
    };

    cancelBtn.onclick = () => {
        wrap.remove();
        appendAiMsg('Vazifa yaratish bekor qilindi.', 'bot');
        aiHistory.push({ role: 'assistant', content: 'Vazifa yaratish bekor qilindi.' });
    };

    btnRow.appendChild(okBtn);
    btnRow.appendChild(editBtn);
    btnRow.appendChild(cancelBtn);
    wrap.appendChild(btnRow);

    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
}

function appendAiTyping() {
    const box = _aiMsgBox();
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-bot ai-msg-typing';
    div.id = 'ai-typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

function removeAiTyping() {
    const t = document.getElementById('ai-typing');
    if (t) t.remove();
}

async function sendAiMessage() {
    const input = document.getElementById('ai-chat-input');
    const sendBtn = document.getElementById('ai-chat-send');
    const text = (input.value || '').trim();
    if (!text) return;

    input.value = '';
    input.style.height = 'auto';
    if (sendBtn) sendBtn.disabled = true;

    appendAiMsg(text, 'user');
    aiHistory.push({ role: 'user', content: text });
    appendAiTyping();

    try {
        const res = await apiRequest('/ai/chat', 'POST', {
            message: text,
            company_id: currentWorkspaceId,
            history: aiHistory.slice(-8),
        });
        removeAiTyping();

        const replyText = res.text || "Tushunmadim, qayta yozib bering.";
        aiHistory.push({ role: 'assistant', content: replyText.replace(/<[^>]+>/g, '') });

        // ===== PROPOSE TASK — tasdiqlash kartasi =====
        if (res.action === 'propose_task' && res.proposal) {
            renderTaskProposal(res.text, res.proposal);
            return;
        }

        // Build action buttons
        const actions = [];
        if (res.task_id) {
            actions.push({
                label: '📋 Vazifani ochish',
                cls: 'btn-go-task',
                fn: () => { closeAiChat(); openTask(res.task_id); },
            });
        }
        if (res.action === 'list_tasks' || res.action === 'search_tasks') {
            actions.push({
                label: '📋 Vazifalar tabiga o\'tish',
                cls: 'btn-go-tasks',
                fn: () => { closeAiChat(); document.querySelector('.bnav-btn[data-tab="tasks"]').click(); },
            });
        }
        if (res.action === 'show_stats') {
            actions.push({
                label: '📊 Statistika tabiga o\'tish',
                cls: 'btn-go-tasks',
                fn: () => { closeAiChat(); document.querySelector('.bnav-btn[data-tab="stats"]').click(); },
            });
        }

        appendAiRich(replyText, res.tasks, actions);

        // Refresh data if AI modified tasks
        if (res.refreshTasks) {
            try {
                const [tasks, stats] = await Promise.all([
                    apiRequest(`/tasks?company_id=${currentWorkspaceId}`),
                    apiRequest(`/stats?company_id=${currentWorkspaceId}`),
                ]);
                allTasks = tasks.tasks || [];
                renderTasks();
                updateQuickStats(stats);
                updateStatsTab(stats);
            } catch (_) {}
            if (tg) tg.HapticFeedback?.notificationOccurred('success');
        }
    } catch (e) {
        removeAiTyping();
        appendAiMsg("Xatolik yuz berdi, qayta urinib ko'ring.", 'bot');
    } finally {
        if (sendBtn) sendBtn.disabled = false;
    }
}

function aiChatKey(event) {
    const ta = event.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendAiMessage();
    }
}

// ============ Subtasks / Attachments / Priority ============
async function addSubtask(parentId) {
    const input = document.getElementById('subtask-input-' + parentId);
    const title = (input.value || '').trim();
    if (title.length < 3) { showToast('Nom 3+ belgi bo\'lsin', true); return; }
    try {
        await apiRequest('/tasks', 'POST', {
            title,
            parent_id: parentId,
            company_id: currentWorkspaceId === 'personal' ? null : currentWorkspaceId,
            priority: 'medium',
        });
        input.value = '';
        showToast('✅ Subtask qo\'shildi');
        openTask(parentId);
    } catch (e) {
        showToast('Xatolik', true);
    }
}

async function uploadAttachment(taskId, inputEl) {
    const file = inputEl.files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { showToast('Fayl 20 MB dan kichik bo\'lsin', true); return; }
    const fd = new FormData();
    fd.append('file', file);
    const headers = {};
    if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
    try {
        const res = await fetch(`/api/tasks/${taskId}/attachments`, { method: 'POST', body: fd, headers });
        if (!res.ok) throw new Error('upload failed');
        showToast('✅ Fayl yuklandi');
        inputEl.value = '';
        openTask(taskId);
    } catch (e) {
        showToast('Yuklab bo\'lmadi', true);
    }
}

async function setTaskPriority(taskId, priority) {
    try {
        await apiRequest(`/tasks/${taskId}/priority`, 'PATCH', { priority });
        showToast('✅ Muhimlik yangilandi');
        const t = allTasks.find(x => x.id === taskId);
        if (t) t.priority = priority;
        renderTasks();
        openTask(taskId);
    } catch (e) {
        showToast('Xatolik', true);
    }
}

// ============ Priority tab ============
const P_CONFIG = {
    urgent: { label: 'Juda muhim', icon: '🔴', cls: 'urgent', pillCls: 'hero-pill-urgent' },
    high:   { label: 'Yuqori',     icon: '🟠', cls: 'high',   pillCls: 'hero-pill-high' },
    medium: { label: "O'rta",      icon: '🟡', cls: 'medium', pillCls: 'hero-pill-medium' },
    low:    { label: 'Past',       icon: '🟢', cls: 'low',    pillCls: 'hero-pill-low' },
};
const STATUS_LABELS_P = {
    new: 'Yangi', in_progress: 'Jarayonda', review: "Ko'rilmoqda",
    done: 'Bajarildi', overdue: 'Kechikdi', cancelled: 'Bekor',
};

async function loadPriorityTab() {
    const box = document.getElementById('priority-list');
    if (!box) return;
    box.innerHTML = '<div class="priority-loading">⚡ Yuklanmoqda...</div>';
    try {
        const all = [];
        const seen = new Set();
        const wsSelect = document.getElementById('workspace-select');
        const workspaces = Array.from(wsSelect?.options || []).map(o => o.value);
        for (const ws of (workspaces.length ? workspaces : ['personal'])) {
            try {
                const r = await apiRequest(`/tasks?company_id=${ws}`);
                for (const t of (r.tasks || [])) {
                    if (seen.has(t.id)) continue;
                    seen.add(t.id); all.push(t);
                }
            } catch (_) {}
        }

        const groups = { urgent: [], high: [], medium: [], low: [] };
        for (const t of all) {
            const p = t.priority || 'medium';
            (groups[p] || groups.medium).push(t);
        }

        // Hero pills
        const pillsHtml = Object.entries(P_CONFIG).map(([p, c]) => {
            const cnt = groups[p].length;
            if (!cnt) return '';
            return `<div class="hero-pill ${c.pillCls}"><span class="hero-pill-dot"></span>${c.label}: ${cnt}</div>`;
        }).join('');

        const totalActive = all.filter(t => !['done','cancelled'].includes(t.status||'')).length;
        const totalUrgent = (groups.urgent||[]).filter(t => !['done','cancelled'].includes(t.status||'')).length;

        let html = `
            <div class="priority-hero">
                <div class="priority-hero-title">⚡ Muhimlik darajasi</div>
                <div class="priority-hero-sub">${all.length} ta vazifa - ${totalActive} ta faol${totalUrgent ? ` - <span style="color:#F87171;font-weight:700">${totalUrgent} juda muhim!</span>` : ''}</div>
                <div class="priority-hero-pills">${pillsHtml || '<span style="color:rgba(255,255,255,0.3)">Vazifalar yo\'q</span>'}</div>
            </div>
        `;

        for (const [p, cfg] of Object.entries(P_CONFIG)) {
            const list = groups[p];
            if (!list.length) continue;
            const cards = list.map((t, i) => _priorityCard(t, p, i)).join('');
            html += `
                <div class="priority-section">
                    <div class="priority-section-header ps-${cfg.cls}">
                        <span class="ps-icon">${cfg.icon}</span>
                        <span class="ps-label">${cfg.label}</span>
                        <span class="ps-count">${list.length}</span>
                    </div>
                    <div class="priority-cards">${cards}</div>
                </div>
            `;
        }

        if (!all.length) html += '<div class="priority-empty">Hali vazifalar yo\'q 🎉</div>';
        box.innerHTML = html;
    } catch (e) {
        box.innerHTML = '<div class="priority-empty">Yuklab bo\'lmadi</div>';
    }
}

function _priorityCard(t, p, idx) {
    const sts = t.status || 'new';
    const isActive = !['done','cancelled'].includes(sts);
    let deadlineHtml = '';
    if (t.deadline) {
        const diff = new Date(t.deadline) - Date.now();
        const urgent = diff < 0;
        const soon = !urgent && diff < 86400000 * 2;
        const label = urgent ? '⏰ ' + formatDeadline(t.deadline) : (soon ? '⌛ ' + formatDeadline(t.deadline) : '📅 ' + formatDeadline(t.deadline));
        const cls = urgent ? 'pc-deadline-urgent' : (soon ? 'pc-deadline-soon' : '');
        deadlineHtml = `<span class="pc-meta-item ${cls}">${label}</span>`;
    }
    const assignees = (t.assignees || []);
    const assigneeHtml = assignees.length
        ? `<span class="pc-meta-item">👤 ${assignees.map(a => escapeHtml(a.name?.split(' ')[0] || '?')).join(', ')}</span>`
        : '';
    return `
        <div class="priority-card pc-${p}" onclick="openTask(${t.id})" style="animation-delay:${idx * 40}ms">
            <div class="pc-top">
                <div class="pc-title">${escapeHtml(t.title)}</div>
                <span class="pc-status-badge pc-status-${sts}">${STATUS_LABELS_P[sts] || sts}</span>
            </div>
            <div class="pc-meta">
                ${deadlineHtml}
                ${assigneeHtml}
            </div>
        </div>
    `;
}

// Hook: when user clicks priority/calendar tab via bottom nav
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.bnav-btn');
    if (btn && btn.dataset.tab === 'priority') loadPriorityTab();
    if (btn && btn.dataset.tab === 'calendar') renderCalendar();
});

// ============ Calendar ============
const CAL_MONTHS = [
    'Yanvar','Fevral','Mart','Aprel','May','Iyun',
    'Iyul','Avgust','Sentabr','Oktabr','Noyabr','Dekabr',
];
const CAL_DAYS_UZ = ['Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba','Yakshanba'];

function _calKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}

function _buildDeadlineMap() {
    const map = {};
    allTasks.forEach(t => {
        if (!t.deadline) return;
        const d = new Date(t.deadline);
        const key = _calKey(d);
        if (!map[key]) map[key] = [];
        map[key].push(t);
    });
    return map;
}

function _taskDotCls(task, isPast) {
    if (task.status === 'done')      return 'cal-dot-done';
    if (task.status === 'cancelled') return 'cal-dot-done';
    if (task.status === 'overdue' || isPast) return 'cal-dot-overdue';
    if (task.priority === 'urgent')  return 'cal-dot-urgent';
    if (task.priority === 'high')    return 'cal-dot-high';
    return 'cal-dot-normal';
}

function renderCalendar() {
    const year  = calendarDate.getFullYear();
    const month = calendarDate.getMonth();

    // Month label
    document.getElementById('cal-month-label').textContent =
        `${CAL_MONTHS[month]} ${year}`;

    // Deadline map
    const dmap = _buildDeadlineMap();

    // Today key
    const today = new Date();
    const todayKey = _calKey(today);

    // First weekday (Mon=0 … Sun=6)
    const firstDow = ((new Date(year, month, 1).getDay()) + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let cells = '';

    // Empty leading cells
    for (let i = 0; i < firstDow; i++) {
        cells += '<div class="cal-cell cal-cell-empty"></div>';
    }

    for (let d = 1; d <= daysInMonth; d++) {
        const key = `${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        const tasks = dmap[key] || [];
        const isToday    = key === todayKey;
        const isSelected = key === selectedCalDate;
        const isPast     = key < todayKey;

        // Up to 3 dots, then "+N"
        const dots = tasks.slice(0, 3).map(t =>
            `<span class="cal-dot ${_taskDotCls(t, isPast)}"></span>`
        ).join('');
        const more = tasks.length > 3
            ? `<span class="cal-more">+${tasks.length - 3}</span>`
            : '';

        const cls = [
            'cal-cell',
            isToday    ? 'cal-today'    : '',
            isSelected ? 'cal-selected' : '',
            tasks.length ? 'cal-has-tasks' : '',
            isPast && tasks.some(t => !['done','cancelled'].includes(t.status)) ? 'cal-past-tasks' : '',
        ].filter(Boolean).join(' ');

        cells += `
            <div class="${cls}" onclick="calCellClick('${key}')">
                <span class="cal-day-num">${d}</span>
                <div class="cal-dots">${dots}${more}</div>
            </div>`;
    }

    document.getElementById('cal-grid-cells').innerHTML = cells;

    // Render selected day panel
    if (selectedCalDate) {
        _renderCalDayPanel(selectedCalDate, dmap[selectedCalDate] || []);
    } else {
        // Auto-select today if it has tasks, otherwise today
        if (dmap[todayKey] && month === today.getMonth() && year === today.getFullYear()) {
            selectedCalDate = todayKey;
            _renderCalDayPanel(todayKey, dmap[todayKey]);
        } else {
            document.getElementById('cal-day-panel').innerHTML = '';
        }
    }
}

function _renderCalDayPanel(key, tasks) {
    const panel = document.getElementById('cal-day-panel');
    if (!panel) return;

    // Parse date for label
    const [yr, mo, dy] = key.split('-').map(Number);
    const dateObj = new Date(yr, mo-1, dy);
    const dow = CAL_DAYS_UZ[(dateObj.getDay() + 6) % 7];
    const dateLabel = `${dy}-${CAL_MONTHS[mo-1]}, ${dow}`;

    const isToday = key === _calKey(new Date());
    const todayBadge = isToday ? '<span class="cal-panel-today-badge">Bugun</span>' : '';

    if (!tasks.length) {
        panel.innerHTML = `
            <div class="cal-panel-header">
                <span class="cal-panel-date">${dateLabel}</span>${todayBadge}
            </div>
            <div class="cal-panel-empty">
                <span>📭</span>
                <p>Bu kunda deadline yo'q</p>
            </div>`;
        return;
    }

    // Sort by time
    const sorted = [...tasks].sort((a, b) => new Date(a.deadline) - new Date(b.deadline));

    const P_EMOJI = { urgent:'🔴', high:'🟠', medium:'🟡', low:'🟢' };
    const ST_SHORT = {
        new:'Yangi', in_progress:'Jarayonda', review:"Ko'rilmoqda",
        done:'Bajarildi', overdue:'Kechikdi', cancelled:'Bekor',
    };

    const rows = sorted.map(t => {
        const dl   = new Date(t.deadline);
        const hh   = String(dl.getHours()).padStart(2,'0');
        const mm   = String(dl.getMinutes()).padStart(2,'0');
        const timeStr = `${hh}:${mm}`;
        const pe   = P_EMOJI[t.priority] || '⚪';
        const st   = t.status || 'new';
        const isPast = new Date(t.deadline) < new Date() && !['done','cancelled'].includes(st);

        return `
            <div class="cal-task-row ${isPast ? 'cal-task-overdue' : ''}" onclick="openTask(${t.id})">
                <div class="cal-task-time ${isPast ? 'time-overdue' : ''}">${timeStr}</div>
                <div class="cal-task-info">
                    <div class="cal-task-title">${pe} ${escapeHtml(t.title)}</div>
                    <div class="cal-task-meta">
                        <span class="tc-badge tc-badge-${st}">${ST_SHORT[st] || st}</span>
                        ${t.assignees && t.assignees.length
                            ? `<span class="cal-task-assignees">👤 ${t.assignees.slice(0,2).map(a=>escapeHtml(a.name.split(' ')[0])).join(', ')}${t.assignees.length>2?' +'+( t.assignees.length-2):''}</span>`
                            : ''}
                    </div>
                </div>
                <svg class="cal-task-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </div>`;
    }).join('');

    panel.innerHTML = `
        <div class="cal-panel-header">
            <span class="cal-panel-date">${dateLabel}</span>
            ${todayBadge}
            <span class="cal-panel-count">${tasks.length} ta deadline</span>
        </div>
        <div class="cal-panel-tasks">${rows}</div>`;
}

function calCellClick(key) {
    selectedCalDate = key;
    if (tg) tg.HapticFeedback?.selectionChanged();
    renderCalendar();
}

function calPrevMonth() {
    calendarDate.setDate(1);
    calendarDate.setMonth(calendarDate.getMonth() - 1);
    selectedCalDate = null;
    renderCalendar();
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function calNextMonth() {
    calendarDate.setDate(1);
    calendarDate.setMonth(calendarDate.getMonth() + 1);
    selectedCalDate = null;
    renderCalendar();
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

// ============ Timeline / Roadmap ============
function _renderTimeline(history) {
    if (!history || !history.length) {
        return '<p style="color:var(--text3);font-size:13px;padding:8px 0">Hali hech narsa bo\'lmagan</p>';
    }

    const STATUS_SHORT = {
        new: '🆕 Yangi', in_progress: '⚙️ Jarayonda', review: '🔍 Ko\'rilmoqda',
        done: '✅ Bajarildi', overdue: '⏰ Kechikdi', cancelled: '🚫 Bekor',
    };
    const PRIORITY_SHORT = {
        low: '🟢 Past', medium: '🟡 O\'rta', high: '🟠 Yuqori', urgent: '🔴 Juda muhim',
    };
    const statusDot = {
        new: 'dot-indigo', in_progress: 'dot-yellow', review: 'dot-purple',
        done: 'dot-green', overdue: 'dot-red', cancelled: 'dot-gray',
    };

    return history.map(h => {
        const time = formatDateTime(h.created_at);
        const uname = escapeHtml(h.user_name || '?');
        let icon = '📌', dotCls = 'dot-indigo', label = '', extra = '';

        switch (h.action) {
            case 'created':
                icon = '🎬'; dotCls = 'dot-indigo';
                label = `<b>${uname}</b> vazifani yaratdi`;
                break;

            case 'status_changed': {
                const nSt = (h.new_value || {}).status || '';
                icon = nSt === 'done' ? '✅' : (nSt === 'cancelled' ? '🚫' : '🔄');
                dotCls = statusDot[nSt] || 'dot-indigo';
                const oLbl = STATUS_SHORT[(h.old_value || {}).status] || '';
                const nLbl = STATUS_SHORT[nSt] || nSt;
                label = `<b>${uname}</b> umumiy statusni o'zgartirdi`;
                extra = oLbl ? `${oLbl} → <b>${nLbl}</b>` : `<b>${nLbl}</b>`;
                break;
            }

            case 'my_status_changed': {
                const mSt = (h.new_value || {}).status || '';
                icon = mSt === 'done' ? '✅' : (mSt === 'in_progress' ? '▶️' : '🔄');
                dotCls = statusDot[mSt] || 'dot-indigo';
                const moLbl = STATUS_SHORT[(h.old_value || {}).status] || '';
                const mnLbl = STATUS_SHORT[mSt] || mSt;
                label = `<b>${uname}</b> o'z statusini o'zgartirdi`;
                extra = (moLbl ? moLbl + ' → ' : '') + `<b>${mnLbl}</b>`;
                const myCmt = (h.new_value || {}).comment;
                if (myCmt) extra += `<div class="tl-comment">💬 ${escapeHtml(myCmt)}</div>`;
                break;
            }

            case 'subtask_created': {
                icon = '🧩'; dotCls = 'dot-cyan';
                const stTitle = escapeHtml((h.new_value || {}).subtask_title || 'Subtask');
                const stId    = (h.new_value || {}).subtask_id;
                label = `<b>${uname}</b> subtask qo'shdi: <i>${stTitle}</i>`;
                if (stId) extra = `<button class="tl-action-btn" onclick="event.stopPropagation();closeModal();openTask(${stId})">📋 Ochish →</button>`;
                break;
            }

            case 'attachment_added': {
                icon = '📎'; dotCls = 'dot-indigo';
                const fname = escapeHtml((h.new_value || {}).file_name || 'fayl');
                label = `<b>${uname}</b> fayl qo'shdi: <i>${fname}</i>`;
                break;
            }

            case 'priority_changed': {
                icon = '⚡'; dotCls = 'dot-yellow';
                const oP = PRIORITY_SHORT[(h.old_value || {}).priority] || '';
                const nP = PRIORITY_SHORT[(h.new_value || {}).priority] || '';
                label = `<b>${uname}</b> muhimlikni o'zgartirdi`;
                extra = oP ? `${oP} → <b>${nP}</b>` : `<b>${nP}</b>`;
                break;
            }

            case 'title_changed': {
                icon = '✏️'; dotCls = 'dot-indigo';
                label = `<b>${uname}</b> sarlavhani o'zgartirdi`;
                extra = `"${escapeHtml((h.new_value || {}).title || '')}"`;
                break;
            }

            case 'comment': {
                icon = '💬'; dotCls = 'dot-glass';
                label = `<b>${uname}</b>`;
                extra = `<div class="tl-comment">${escapeHtml(h.content || '')}</div>`;
                break;
            }

            default:
                icon = '📌'; dotCls = 'dot-indigo';
                label = `<b>${uname}</b>: ${escapeHtml(h.action)}`;
        }

        return `
            <div class="timeline-item">
                <div class="timeline-dot ${dotCls}">${icon}</div>
                <div class="timeline-body">
                    <div class="timeline-label">${label}</div>
                    ${extra ? `<div class="tl-extra">${extra}</div>` : ''}
                    <div class="timeline-time">${time}</div>
                </div>
            </div>`;
    }).join('');
}

function switchTab(tabName) {
    const btn = document.querySelector(`.bnav-btn[data-tab="${tabName}"]`);
    if (btn) btn.click();
}

// Legacy compat (drawer funksiyalari endi ishlatilmaydi)
function toggleNavDrawer() {}
function closeNavDrawer() {}
function openNavDrawer() {}

// ===== Workflow Step 2-State Action =====
async function handleStepAction(taskId, stepStatus) {
    if (stepStatus === 'pending') {
        // Boshlash — call API to mark as active + log to history
        try {
            const r = await apiRequest(`/workflows/${taskId}/start`, 'POST');
            if (r.ok && r.status === 'active') {
                tg?.HapticFeedback?.notificationOccurred('success');
                // Reload workflows to show updated button
                await loadWorkflows();
                tg?.showAlert?.('▶️ Qadamni boshladingiz!');
            }
        } catch (e) {
            tg?.showAlert?.('❌ Xato: ' + (e.message || e));
        }
    } else if (stepStatus === 'active') {
        // Bajarildi — open completion modal
        openStepCompleteModal(taskId);
    } else {
        // Done/Blocked — show status
        tg?.showAlert?.('✓ Bu qadam allaqachon tugagan');
    }
}

// ===== Task 2-State Action (regular tasks, not workflow) =====
async function handleTaskAction(taskId, myStatus) {
    if (myStatus === 'new' || myStatus === 'pending') {
        // Boshlash — call API to mark as in_progress + log to history
        try {
            const r = await apiRequest(`/tasks/${taskId}/start`, 'POST');
            if (r.ok && r.status === 'in_progress') {
                tg?.HapticFeedback?.notificationOccurred('success');
                // Reload task to show updated button
                await openTask(taskId);
                tg?.showAlert?.('▶️ Taskni boshladingiz!');
            }
        } catch (e) {
            tg?.showAlert?.('❌ Xato: ' + (e.message || e));
        }
    } else if (myStatus === 'in_progress') {
        // Bajarildi — open completion modal
        openTaskCompleteModal(taskId);
    } else {
        // Done — show status
        tg?.showAlert?.('✓ Bu task allaqachon tugagan');
    }
}

// Modal — task tugatish formasi (izoh)
function openTaskCompleteModal(taskId) {
    // Mavjud bo'lsa yopamiz
    closeTaskCompleteModal();
    const modal = document.createElement('div');
    modal.id = 'task-complete-modal';
    modal.className = 'wf-modal-overlay';
    modal.innerHTML = `
        <div class="wf-modal">
            <div class="wf-modal-head">
                <h3>✅ Taskni tugatish</h3>
                <button class="wf-modal-close" onclick="closeTaskCompleteModal()">×</button>
            </div>
            <div class="wf-modal-body">
                <label class="wf-lbl">💬 Nimani bajardingiz? (ixtiyoriy)</label>
                <textarea id="task-comment-input" class="wf-textarea" rows="3"
                          placeholder="Qisqacha yozing..."></textarea>
            </div>
            <div class="wf-modal-foot">
                <button class="wf-btn-secondary" onclick="closeTaskCompleteModal()">Bekor</button>
                <button class="wf-btn-primary" onclick="submitTaskComplete(${taskId})">✅ Saqlash</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('wf-modal-show'), 10);
}

function closeTaskCompleteModal() {
    const m = document.getElementById('task-complete-modal');
    if (m) m.remove();
}

async function submitTaskComplete(taskId) {
    const comment = (document.getElementById('task-comment-input')?.value || '').trim();

    try {
        const r = await apiRequest(`/tasks/${taskId}/complete`, 'POST', { comment });
        closeTaskCompleteModal();
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        if (r.all_done) {
            tg?.showAlert?.('🎉 Task to\'liq tugadi!');
        } else {
            tg?.showAlert?.('✅ Qabul qilindi. Boshqa ijrochilar kutilmoqda.');
        }
        // Reload both task list and this task detail
        await loadTasks();
        await openTask(taskId);
    } catch (e) {
        tg?.showAlert?.('❌ Xato: ' + (e.message || e));
    }
}
